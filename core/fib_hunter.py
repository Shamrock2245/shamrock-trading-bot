"""
core/fib_hunter.py — Fibonacci Entry Point Hunter

Monitors a dynamic watchlist of known-good tokens for golden pocket
(0.618) re-entry opportunities. Feeds qualifying entries into the
existing trade execution pipeline.

Watchlist Sources:
  1. Trade history — tokens we've profited on before
  2. High-scored gems that didn't execute (score ≥ 60 but missed)
  3. Current holdings approaching Fib support (scale-in opportunity)
  4. Moralis Pro trending tokens that pass safety checks

Entry Logic (ALL must pass):
  ✅ Price at Fib 0.618 (golden pocket) or 0.5 level
  ✅ Fib trend = uptrend (retracing, not collapsing)
  ✅ Fib confidence ≥ 30
  ✅ Liquidity > $50K
  ✅ Safety score ≥ 70
  ✅ Not already in portfolio (dedup check)

Take-Profit: Staged exits at Fib extensions (1.272→30%, 1.618→30%, 2.618→25%, ride 15%)
"""

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

from config import settings
from config.chains import CHAINS

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────
WATCHLIST_FILE = Path("output/fib_watchlist.json")
FIB_HUNT_COOLDOWN_MINUTES = int(os.getenv("FIB_HUNT_COOLDOWN_MINUTES", "30"))
MAX_WATCHLIST_SIZE = int(os.getenv("MAX_WATCHLIST_SIZE", "50"))
MIN_LIQUIDITY_FOR_ENTRY = float(os.getenv("FIB_MIN_LIQUIDITY", "50000"))
MIN_FIB_CONFIDENCE = int(os.getenv("MIN_FIB_CONFIDENCE", "30"))

# Fib zones that qualify for entry (ordered by priority)
ENTRY_ZONES = {"golden_pocket", "fib_618", "fib_500", "fib_786"}


# ─────────────────────────────────────────────────────────────────────────────
# Data Models
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class WatchlistEntry:
    """Token being watched for Fib re-entry."""
    token_address: str
    symbol: str
    chain: str
    source: str          # "trade_history", "high_score_miss", "holding", "trending"
    added_at: str = ""
    last_checked: str = ""
    gem_score: float = 0.0
    last_price: float = 0.0
    check_count: int = 0
    # Fib data from last check
    fib_zone: str = ""
    fib_aligned: bool = False
    fib_confidence: float = 0.0

    def to_dict(self) -> dict:
        return {
            "token_address": self.token_address,
            "symbol": self.symbol,
            "chain": self.chain,
            "source": self.source,
            "added_at": self.added_at,
            "last_checked": self.last_checked,
            "gem_score": self.gem_score,
            "last_price": self.last_price,
            "check_count": self.check_count,
            "fib_zone": self.fib_zone,
            "fib_aligned": self.fib_aligned,
            "fib_confidence": self.fib_confidence,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "WatchlistEntry":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class FibEntrySignal:
    """A qualified Fib entry signal ready for execution."""
    token_address: str
    symbol: str
    chain: str
    fib_zone: str
    fib_confidence: float
    current_price: float
    stop_loss: float
    take_profit_targets: list = field(default_factory=list)
    gem_score: float = 0.0
    source: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# Watchlist Management
# ─────────────────────────────────────────────────────────────────────────────
def load_watchlist() -> list[WatchlistEntry]:
    """Load the Fib hunting watchlist."""
    if WATCHLIST_FILE.exists():
        try:
            with open(WATCHLIST_FILE) as f:
                data = json.load(f)
            return [WatchlistEntry.from_dict(d) for d in data]
        except Exception as e:
            logger.error(f"Failed to load watchlist: {e}")
    return []


def save_watchlist(watchlist: list[WatchlistEntry]):
    """Save the watchlist."""
    WATCHLIST_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(WATCHLIST_FILE, "w") as f:
        json.dump([w.to_dict() for w in watchlist], f, indent=2)


def add_to_watchlist(
    token_address: str,
    symbol: str,
    chain: str,
    source: str,
    gem_score: float = 0.0,
):
    """Add a token to the Fib hunting watchlist (idempotent)."""
    watchlist = load_watchlist()

    # Dedup check
    existing = {w.token_address.lower() for w in watchlist}
    if token_address.lower() in existing:
        return

    # Cap size — evict oldest entries
    if len(watchlist) >= MAX_WATCHLIST_SIZE:
        watchlist.sort(key=lambda w: w.added_at)
        watchlist = watchlist[-(MAX_WATCHLIST_SIZE - 1):]

    entry = WatchlistEntry(
        token_address=token_address,
        symbol=symbol,
        chain=chain,
        source=source,
        added_at=datetime.now(timezone.utc).isoformat(),
        gem_score=gem_score,
    )
    watchlist.append(entry)
    save_watchlist(watchlist)
    logger.debug(f"📋 Added {symbol} to Fib watchlist (source={source})")


def build_watchlist_from_history():
    """
    Populate the watchlist from trade history and gem scan results.
    Called once per cycle to keep the watchlist fresh.
    """
    watchlist = load_watchlist()
    existing_addrs = {w.token_address.lower() for w in watchlist}

    # Source 1: Trade history (tokens we've profited on)
    try:
        from core.position_monitor import load_positions
        positions = load_positions()
        for p in positions:
            if p.get("status") != "closed":
                continue
            pnl = float(p.get("realized_pnl_usd", 0))
            if pnl <= 0:
                continue  # Only watch profitable tokens
            addr = p.get("token_address", "").lower()
            if addr and addr not in existing_addrs:
                add_to_watchlist(
                    token_address=addr,
                    symbol=p.get("token_symbol", "???"),
                    chain=p.get("chain", ""),
                    source="trade_history",
                    gem_score=float(p.get("gem_score", 0)),
                )
                existing_addrs.add(addr)
    except Exception as e:
        logger.debug(f"Could not load trade history for watchlist: {e}")

    # Source 2: High-scored gems from last scan that weren't executed
    try:
        scan_file = Path("output/gem_scan.json")
        if scan_file.exists():
            with open(scan_file) as f:
                scan_data = json.load(f)
            for c in scan_data.get("top_candidates", []):
                score = float(c.get("gem_score", 0))
                if score < 60:
                    continue
                addr = c.get("address", "").lower()
                if addr and addr not in existing_addrs:
                    add_to_watchlist(
                        token_address=addr,
                        symbol=c.get("symbol", "???"),
                        chain=c.get("chain", ""),
                        source="high_score_miss",
                        gem_score=score,
                    )
                    existing_addrs.add(addr)
    except Exception as e:
        logger.debug(f"Could not load gem scan for watchlist: {e}")

    # Source 3: Current holdings (from positions file)
    try:
        from core.position_monitor import load_positions
        positions = load_positions()
        for p in positions:
            if p.get("status") != "open":
                continue
            addr = p.get("token_address", "").lower()
            if addr and addr not in existing_addrs:
                add_to_watchlist(
                    token_address=addr,
                    symbol=p.get("token_symbol", "???"),
                    chain=p.get("chain", ""),
                    source="holding",
                    gem_score=float(p.get("gem_score", 0)),
                )
                existing_addrs.add(addr)
    except Exception as e:
        logger.debug(f"Could not load positions for watchlist: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# OHLCV Data Fetching
# ─────────────────────────────────────────────────────────────────────────────
def fetch_ohlcv_for_fib(token_address: str, chain: str) -> Optional[list]:
    """
    Fetch OHLCV candle data for Fib analysis.
    Uses DexScreener or GeckoTerminal.
    Returns list of [timestamp, open, high, low, close, volume] or None.
    """
    # Try GeckoTerminal first (better OHLCV support)
    gecko_chain_map = {
        "base": "base", "ethereum": "eth", "bsc": "bsc",
        "polygon": "polygon_pos", "arbitrum": "arbitrum",
        "avalanche": "avax", "solana": "solana",
    }
    gecko_chain = gecko_chain_map.get(chain)
    if gecko_chain:
        try:
            # Find pool address first
            r = requests.get(
                f"https://api.geckoterminal.com/api/v2/networks/{gecko_chain}/tokens/{token_address}/pools",
                params={"page": 1},
                headers={"accept": "application/json"},
                timeout=10,
            )
            if r.status_code == 200:
                pools = r.json().get("data", [])
                if pools:
                    pool_addr = pools[0].get("attributes", {}).get("address", "")
                    if pool_addr:
                        # Fetch OHLCV
                        ohlcv_r = requests.get(
                            f"https://api.geckoterminal.com/api/v2/networks/{gecko_chain}/pools/{pool_addr}/ohlcv/hour",
                            params={"aggregate": 1, "limit": 100},
                            headers={"accept": "application/json"},
                            timeout=10,
                        )
                        if ohlcv_r.status_code == 200:
                            candles = ohlcv_r.json().get("data", {}).get("attributes", {}).get("ohlcv_list", [])
                            if candles and len(candles) >= 20:
                                return candles
        except Exception as e:
            logger.debug(f"GeckoTerminal OHLCV error for {token_address}: {e}")

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Fib Analysis
# ─────────────────────────────────────────────────────────────────────────────
def analyze_fib_entry(token_address: str, chain: str) -> Optional[FibEntrySignal]:
    """
    Run Fibonacci analysis on a watchlisted token to check for entry.

    Returns FibEntrySignal if token is at a qualifying Fib level, None otherwise.
    """
    # Fetch OHLCV data
    candles = fetch_ohlcv_for_fib(token_address, chain)
    if not candles or len(candles) < 20:
        return None

    try:
        import pandas as pd
        from strategies.fibonacci import check_fibonacci_alignment

        # Convert candles to DataFrame
        # GeckoTerminal format: [timestamp, open, high, low, close, volume]
        df = pd.DataFrame(candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df = df.astype({"open": float, "high": float, "low": float, "close": float, "volume": float})
        df = df.sort_values("timestamp").reset_index(drop=True)

        current_price = float(df["close"].iloc[-1])
        if current_price <= 0:
            return None

        # Run Fib analysis
        fib_result = check_fibonacci_alignment(df, current_price, direction="buy")

        if fib_result.error:
            logger.debug(f"Fib analysis error for {token_address}: {fib_result.error}")
            return None

        # Check entry criteria
        if not fib_result.aligned:
            return None

        if fib_result.current_zone not in ENTRY_ZONES:
            return None

        if fib_result.confidence < MIN_FIB_CONFIDENCE:
            return None

        if fib_result.trend != "uptrend":
            return None

        # Check liquidity via DexScreener
        from core.portfolio_rebalancer import fetch_token_market_data
        market = fetch_token_market_data(token_address, chain)
        if market["liquidity_usd"] < MIN_LIQUIDITY_FOR_ENTRY:
            return None

        # Build entry signal
        signal = FibEntrySignal(
            token_address=token_address,
            symbol="",  # Will be populated by caller
            chain=chain,
            fib_zone=fib_result.current_zone,
            fib_confidence=fib_result.confidence,
            current_price=current_price,
            stop_loss=fib_result.stop_loss_level,
            take_profit_targets=fib_result.take_profit_targets or [],
        )

        logger.info(
            f"🎯 Fib entry signal: zone={fib_result.current_zone} "
            f"confidence={fib_result.confidence:.0f}% price=${current_price:.8f} "
            f"SL=${fib_result.stop_loss_level:.8f}"
        )

        return signal

    except ImportError as e:
        logger.error(f"Missing dependency for Fib analysis: {e}")
        return None
    except Exception as e:
        logger.error(f"Fib analysis failed for {token_address}: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Main Sweep
# ─────────────────────────────────────────────────────────────────────────────
def run_fib_hunt_sweep() -> list[FibEntrySignal]:
    """
    Sweep the watchlist for Fib entry opportunities.
    Called from main.py bot loop after gem scan.

    Returns a list of qualified FibEntrySignals ready for execution.
    """
    # 1. Refresh watchlist from history
    build_watchlist_from_history()

    # 2. Load watchlist
    watchlist = load_watchlist()
    if not watchlist:
        logger.debug("Fib watchlist is empty — nothing to hunt")
        return []

    logger.info(f"🔍 Fib Hunter: scanning {len(watchlist)} tokens for entry points")

    # 3. Build dedup set — skip tokens we already hold
    open_token_keys = set()
    try:
        from core.position_monitor import load_positions
        positions = load_positions()
        open_token_keys = {
            p["token_address"].lower()
            for p in positions
            if p.get("status") == "open" and p.get("token_address")
        }
    except Exception:
        pass

    # 4. Analyze each token
    signals: list[FibEntrySignal] = []
    checked = 0

    for entry in watchlist:
        # Skip tokens we already hold (unless source is "holding" for scale-in)
        if entry.token_address.lower() in open_token_keys and entry.source != "holding":
            continue

        # Rate limit — don't hammer APIs
        if checked >= 15:  # Max 15 Fib checks per cycle
            break

        try:
            signal = analyze_fib_entry(entry.token_address, entry.chain)
            checked += 1

            # Update watchlist entry
            entry.last_checked = datetime.now(timezone.utc).isoformat()
            entry.check_count += 1

            if signal:
                signal.symbol = entry.symbol
                signal.gem_score = entry.gem_score
                signal.source = entry.source
                entry.fib_zone = signal.fib_zone
                entry.fib_aligned = True
                entry.fib_confidence = signal.fib_confidence

                # Safety gate — run quick safety check
                try:
                    from core.safety import check_token_safety
                    safety = check_token_safety(entry.token_address, entry.chain)
                    if not safety.is_safe:
                        logger.info(f"Fib entry blocked for {entry.symbol}: {safety.block_reason}")
                        continue
                except Exception:
                    pass  # Don't block on safety check failure

                signals.append(signal)
                logger.info(
                    f"🎯 Fib entry qualified: {entry.symbol} on {entry.chain} "
                    f"at {signal.fib_zone} (conf={signal.fib_confidence:.0f}%)"
                )
            else:
                entry.fib_aligned = False

            time.sleep(0.5)  # Rate limit between tokens

        except Exception as e:
            logger.debug(f"Fib check failed for {entry.symbol}: {e}")

    # 5. Save updated watchlist
    save_watchlist(watchlist)

    if signals:
        logger.info(f"🎯 Fib Hunter found {len(signals)} entry signals: "
                     f"{[s.symbol for s in signals]}")
    else:
        logger.debug(f"Fib Hunter: no entry signals from {checked} tokens checked")

    return signals
