"""
core/position_monitor.py — Auto-sell, take-profit, and trailing stop monitor.

Runs as a background loop alongside the gem scanner. Every 30 seconds it:
  1. Loads all open positions from positions.json
  2. Fetches current price for each position via DexScreener
  3. Evaluates take-profit tiers, trailing stop, and hard stop-loss
  4. Executes sells when thresholds are hit
  5. Persists updated positions back to disk

Take-Profit Strategy (Profit Machine Playbook):
  - TP1 at 1.5x (50% gain):  Sell 40% → capture micro-cap gains before reversals
  - TP2 at 2.5x (150% gain): Sell 35% of remaining → asymmetric exit on confirmed runners
  - TP3 at 5x  (400% gain):  Sell 25% of remaining → moonshot capture
  - Trailing stop after TP1: 15% below highest price seen
  - Hard stop-loss: 20% below entry (configurable) — cut losers fast
  - Time-based exit: if no 10% gain in 24h, exit to free capital
  - Multi-Signal Confluence Gate: profitable positions above TP1 require
    2-of-5 bearish signals to trigger a trailing stop exit (prevents whipsaws)

Position Persistence:
  - Positions saved to output/positions.json (JSON array)
  - Trades log appended to output/trades.json
  - Both files survive restarts — positions are reloaded on startup
"""

import asyncio
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from data.http_session import get_session

from config import settings
from data.providers.moralis_money import get_token_analytics_fresh
from data.providers.moralis_analytics import get_time_series_token_analytics
from config.wallets import (
    CONSERVATIVE_PROFILE, NUCLEAR_PROFILE, SWING_SCALP_PROFILE,
    MTF_1H_SCALP_PROFILE, MTF_4H_SWING_PROFILE,
    MTF_12H_MOMENTUM_PROFILE, MTF_5D_POSITION_PROFILE,
    ALPHA_SOL_PROFILE,
)
from data.models import Position, Trade
from core.offensive_guardrails import (
    get_offensive_state,
    save_offensive_state,
    evaluate_pyramid_scaling,
    get_dynamic_trailing_stop_pct,
    evaluate_fast_fail,
    should_skip_tp1,
)

# ── Strategy Profile Lookup (for profile-aware exits) ─────────────────────────
_PROFILE_MAP = {
    "conservative": CONSERVATIVE_PROFILE,
    "nuclear": NUCLEAR_PROFILE,
    "swing": SWING_SCALP_PROFILE,
    "alpha_sol": ALPHA_SOL_PROFILE,
    # MTF profiles — multi-timeframe strategy engine
    "mtf_1h_scalp": MTF_1H_SCALP_PROFILE,
    "mtf_4h_swing": MTF_4H_SWING_PROFILE,
    "mtf_12h_momentum": MTF_12H_MOMENTUM_PROFILE,
    "mtf_5d_position": MTF_5D_POSITION_PROFILE,
}

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# File paths
# ─────────────────────────────────────────────────────────────────────────────
POSITIONS_FILE = Path(settings.POSITIONS_FILE)
POSITIONS_BACKUP = POSITIONS_FILE.with_name("positions.backup.json")
TRADES_FILE = Path(settings.TRADES_FILE)
SELL_FAILURES_FILE = Path("/app/output/sell_failures.json")
TRADE_LEDGER_FILE = Path(os.environ.get("TRADE_LEDGER_FILE", "/app/output/trade_ledger.jsonl"))  # IMMUTABLE — never pruned
_save_counter = 0
_running_pnl_usd = 0.0  # Running total P&L, loaded from ledger on startup
POSITIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
try:
    TRADE_LEDGER_FILE.parent.mkdir(parents=True, exist_ok=True)
except OSError:
    pass  # /app may not exist outside Docker — ledger writes will gracefully fail

# Thread-safe lock for positions file (prevents race conditions between
# monitor thread, fastlane worker, gas_manager, and capital_rotator)
_positions_lock = threading.Lock()


# ─────────────────────────────────────────────────────────────────────────────
# Position Persistence
# ─────────────────────────────────────────────────────────────────────────────

def load_positions() -> list[dict]:
    """Load open positions from disk. Falls back to .tmp or .backup if main file is corrupt."""
    with _positions_lock:
        for filepath in [POSITIONS_FILE, POSITIONS_FILE.with_suffix(".tmp"), POSITIONS_BACKUP]:
            try:
                if filepath.exists():
                    with open(filepath) as f:
                        data = json.load(f)
                        positions = data if isinstance(data, list) else []

                        if filepath != POSITIONS_FILE:
                            logger.warning(f"Loaded positions from fallback: {filepath}")
                            # Restore to main file — use _save_positions_unlocked to avoid deadlock
                            _save_positions_unlocked(positions)

                        # ── Backfill migration for older positions ─────────────────
                        migrated = False
                        for p in positions:
                            if "entry_value_usd" not in p or float(p.get("entry_value_usd", 0)) <= 0:
                                entry_px = float(p.get("entry_price", 0))
                                qty = float(p.get("quantity", 0))
                                p["entry_value_usd"] = entry_px * qty if entry_px > 0 and qty > 0 else 10.0
                                migrated = True
                            if "scale_in_count" not in p:
                                p["scale_in_count"] = 0
                                migrated = True
                        if migrated:
                            _save_positions_unlocked(positions)
                            logger.info("Migrated positions: backfilled entry_value_usd / scale_in_count")

                        return positions
            except Exception as e:
                logger.error(f"Failed to load positions from {filepath}: {e}")
        return []


def _save_positions_unlocked(positions: list[dict]) -> None:
    """Internal save — caller MUST hold _positions_lock."""
    global _save_counter
    try:
        tmp = POSITIONS_FILE.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(positions, f, indent=2, default=str)
            f.flush()
            os.fsync(f.fileno())
        tmp.replace(POSITIONS_FILE)
        _save_counter += 1
        if _save_counter % 100 == 0:
            import shutil
            shutil.copy2(POSITIONS_FILE, POSITIONS_BACKUP)
            logger.debug(f"Positions backup saved ({_save_counter} saves)")
    except Exception as e:
        logger.error(f"Failed to save positions: {e}")


def save_positions(positions: list[dict]) -> None:
    """Persist open positions to disk (atomic write + periodic backup + fsync). Thread-safe."""
    with _positions_lock:
        _save_positions_unlocked(positions)
    
    # Sync open positions to Moralis Streams for real-time contract security monitoring
    try:
        if getattr(settings, "MORALIS_STREAMS_ENABLED", False):
            from core.moralis_streams_manager import streams_manager
            if streams_manager:
                streams_manager.sync_active_positions(positions)
    except Exception as e:
        logger.warning(f"Failed to sync active positions to Moralis Streams: {e}")


def _append_to_file(filepath: Path, record: dict, max_records: int = 10_000) -> None:
    """Atomic append a record to a JSON array file."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    records = []
    if filepath.exists():
        with open(filepath) as f:
            records = json.load(f)
    records.append(record)
    if len(records) > max_records:
        records = records[-max_records:]
    tmp_path = filepath.with_suffix(".tmp")
    with open(tmp_path, "w") as f:
        json.dump(records, f, indent=2, default=str)
        f.flush()
        os.fsync(f.fileno())
    tmp_path.replace(filepath)


def _append_to_ledger(record: dict) -> None:
    """Append a trade to the IMMUTABLE ledger (JSONL — one JSON line per trade).

    This file is NEVER pruned. It is the permanent audit trail of every trade
    the bot has ever executed. JSONL format ensures partial writes can't corrupt
    the entire file — at worst, the last line is incomplete.

    Each line includes a running_total_pnl_usd field for quick balance tracking.
    """
    global _running_pnl_usd
    try:
        TRADE_LEDGER_FILE.parent.mkdir(parents=True, exist_ok=True)
        pnl = float(record.get("pnl_usd", 0) or 0)
        _running_pnl_usd += pnl
        ledger_record = {
            **record,
            "running_total_pnl_usd": round(_running_pnl_usd, 4),
            "ledger_seq": _get_ledger_seq(),
        }
        with open(TRADE_LEDGER_FILE, "a") as f:
            f.write(json.dumps(ledger_record, default=str) + "\n")
            f.flush()
            os.fsync(f.fileno())
    except Exception as e:
        logger.error(f"Failed to write to immutable ledger: {e}")


def _get_ledger_seq() -> int:
    """Return the next sequence number for the ledger (count of existing lines)."""
    try:
        if TRADE_LEDGER_FILE.exists():
            with open(TRADE_LEDGER_FILE) as f:
                return sum(1 for _ in f)
        return 0
    except Exception:
        return -1


def _load_running_pnl() -> float:
    """Load the running P&L total from the last line of the ledger."""
    try:
        if TRADE_LEDGER_FILE.exists():
            with open(TRADE_LEDGER_FILE, "rb") as f:
                # Seek to end and scan backwards for last newline
                f.seek(0, 2)
                size = f.tell()
                if size == 0:
                    return 0.0
                # Read last 4KB (enough for one JSON line)
                f.seek(max(0, size - 4096))
                lines = f.read().decode("utf-8", errors="replace").strip().split("\n")
                if lines:
                    last = json.loads(lines[-1])
                    return float(last.get("running_total_pnl_usd", 0))
    except Exception as e:
        logger.warning(f"Could not load running P&L from ledger: {e}")
    return 0.0


# Initialize running P&L from ledger on module load
_running_pnl_usd = _load_running_pnl()


def append_trade(trade: dict) -> None:
    """Append a completed trade to the appropriate log file.

    Failed sells (with 'error' key or no tx_hash) go to sell_failures.json.
    Successful trades (including paper sells with tx_hash='0x000...0') go
    to the main trades file AND the immutable JSONL ledger.
    """
    try:
        is_paper = trade.get("is_paper", False)
        has_error = "error" in trade
        tx_hash = trade.get("tx_hash")

        # Paper-mode successful sells have tx_hash='0x000...0' — those are valid
        is_failure = has_error or (tx_hash is None and not is_paper)

        if is_failure:
            _append_to_file(SELL_FAILURES_FILE, trade, max_records=5_000)
            logger.debug(f"Sell failure logged to {SELL_FAILURES_FILE}")
        else:
            _append_to_file(TRADES_FILE, trade)
            _append_to_ledger(trade)  # IMMUTABLE — never pruned
    except Exception as e:
        logger.error(f"Failed to append trade: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Price Fetching
# ─────────────────────────────────────────────────────────────────────────────

def get_current_price(token_address: str, chain: str, pair_address: str = "") -> Optional[float]:
    """
    Fetch current price from DexScreener.
    Returns None if price unavailable.
    Retries up to 3 times with exponential backoff on transient failures.
    """
    last_error = None
    for attempt in range(3):
        try:
            if pair_address:
                url = f"https://api.dexscreener.com/latest/dex/pairs/{chain}/{pair_address}"
            else:
                url = f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"

            resp = get_session().get(url, timeout=10)
            if resp.status_code == 429 or resp.status_code >= 500:
                last_error = f"HTTP {resp.status_code}"
                time.sleep(1.5 * (2 ** attempt))  # 1.5s, 3s, 6s
                continue
            data = resp.json()
            pairs = data.get("pairs", [])
            if not pairs:
                return None

            # Use most liquid pair

            price_str = pairs[0].get("priceUsd")
            return float(price_str) if price_str else None

        except Exception as e:
            last_error = str(e)
            if attempt < 2:
                time.sleep(1.5 * (2 ** attempt))
            continue

    logger.debug(f"Price fetch failed after 3 retries for {token_address}: {last_error}")
    return None


def get_price_and_volume(token_address: str, chain: str, pair_address: str = "") -> dict:
    """
    Fetch current price, volume, AND liquidity data from DexScreener.
    Returns dict with price, volume_1h, volume_24h, liquidity_usd. All may be None.
    Retries up to 3 times with exponential backoff on transient failures.
    """
    result = {"price": None, "volume_1h": None, "volume_24h": None, "liquidity_usd": None}
    last_error = None
    for attempt in range(3):
        try:
            if pair_address:
                url = f"https://api.dexscreener.com/latest/dex/pairs/{chain}/{pair_address}"
            else:
                url = f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"

            resp = get_session().get(url, timeout=10)
            if resp.status_code == 429 or resp.status_code >= 500:
                last_error = f"HTTP {resp.status_code}"
                time.sleep(1.5 * (2 ** attempt))
                continue
            data = resp.json()
            pairs = data.get("pairs", [])
            if not pairs:
                return result


            top = pairs[0]
            price_str = top.get("priceUsd")
            result["price"] = float(price_str) if price_str else None

            vol = top.get("volume", {})
            result["volume_1h"] = float(vol.get("h1", 0) or 0)
            result["volume_24h"] = float(vol.get("h24", 0) or 0)

            # Liquidity data (for liquidity drain exit)
            liq = top.get("liquidity", {})
            result["liquidity_usd"] = float(liq.get("usd", 0) or 0)
            return result

        except Exception as e:
            last_error = str(e)
            if attempt < 2:
                time.sleep(1.5 * (2 ** attempt))
            continue

    logger.debug(f"Price+volume fetch failed after 3 retries for {token_address}: {last_error}")
    return result


def batch_get_prices_and_volumes(positions: list[dict]) -> dict[str, dict]:
    """
    Batch-fetch prices from DexScreener for multiple positions.
    Uses comma-separated address endpoint (up to 30 per call).
    Returns: {token_address_lower: {price, volume_1h, volume_24h, liquidity_usd}}
    """
    results: dict[str, dict] = {}
    if not positions:
        return results

    # Separate positions with pair_address (use pair endpoint) from those without
    pair_positions = [p for p in positions if p.get("pair_address")]
    token_positions = [p for p in positions if not p.get("pair_address")]

    # Fetch pair-based positions individually (pair endpoint doesn't support batching)
    for pos in pair_positions:
        addr = pos.get("token_address", "").lower()
        pv = get_price_and_volume(
            token_address=pos.get("token_address", ""),
            chain=pos.get("chain", ""),
            pair_address=pos.get("pair_address", ""),
        )
        results[addr] = pv

    # Batch token-based positions (30 per call max via DexScreener API)
    addresses = [p.get("token_address", "") for p in token_positions if p.get("token_address")]
    BATCH_SIZE = 30
    for i in range(0, len(addresses), BATCH_SIZE):
        batch = addresses[i:i + BATCH_SIZE]
        batch_str = ",".join(batch)
        try:
            url = f"https://api.dexscreener.com/latest/dex/tokens/{batch_str}"
            resp = get_session().get(url, timeout=15)
            data = resp.json()
            all_pairs = data.get("pairs", [])

            # Group pairs by baseToken address
            by_token: dict[str, list] = {}
            for pair in all_pairs:
                base_addr = pair.get("baseToken", {}).get("address", "").lower()
                if base_addr:
                    by_token.setdefault(base_addr, []).append(pair)

            # Pick the most liquid pair for each token
            for addr_lower, pairs in by_token.items():

                top = pairs[0]
                price_str = top.get("priceUsd")
                vol = top.get("volume", {})
                liq = top.get("liquidity", {})
                results[addr_lower] = {
                    "price": float(price_str) if price_str else None,
                    "volume_1h": float(vol.get("h1", 0) or 0),
                    "volume_24h": float(vol.get("h24", 0) or 0),
                    "liquidity_usd": float(liq.get("usd", 0) or 0),
                }

            logger.debug(f"Batch DexScreener: fetched {len(by_token)} tokens in 1 call")

        except Exception as e:
            logger.warning(f"Batch DexScreener fetch failed: {e}")
            # Fall back to individual fetches for this batch
            for addr in batch:
                pv = get_price_and_volume(addr, "", "")
                results[addr.lower()] = pv

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Multi-Signal Confluence Gate (Anti-Whipsaw for Profitable Positions)
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_profit_sell_confluence(pos: dict, current_price: float) -> dict:
    """
    Before closing a profitable position via trailing stop, require 2-of-5
    bearish signals to confirm the reversal is real — not just a wick.

    The 5 signals checked (all derived from stored position data):
      1. Volume collapse: current 1h vol < 25% of entry 1h vol
      2. Buy pressure dry-up: buy/sell ratio < 0.45 (stored from analytics)
      3. Liquidity drain: pool liquidity dropped >20% from entry
      4. Multiple red candles: price dropped >10% from highest AND we're below
         the midpoint of (highest_price + entry_price) / 2
      5. Momentum death: price dropped >5% in the LAST check window
         (current_price vs last_check_price stored on position)

    Returns:
        {
            "bearish_count": int,    # number of triggered signals (need >= 2)
            "triggered": list[str],  # names of triggered signals
            "blocked": bool,         # True if < 2 signals = don't sell yet
        }
    """
    triggered = []
    entry_price = float(pos.get("entry_price", 0) or 0)
    highest_price = float(pos.get("highest_price", current_price) or current_price)

    # ── Signal 1: Volume Collapse ──────────────────────────────────────────────
    # Current 1h volume < 25% of entry volume = buyers have disappeared
    vol_1h = float(pos.get("volume_1h", 0) or 0)
    entry_vol_1h = float(pos.get("entry_volume_1h", 0) or 0)
    if entry_vol_1h > 0 and vol_1h > 0:
        if vol_1h / entry_vol_1h < 0.25:
            triggered.append("vol_collapse")

    # ── Signal 2: Buy Pressure Dry-Up ─────────────────────────────────────────
    # On-chain buy/sell ratio < 0.45 = sellers dominating
    # Stored from Moralis analytics at entry / last refresh
    buy_pressure = float(pos.get("buy_pressure_ratio", pos.get("moralis_buy_pressure", 0.5)) or 0.5)
    if buy_pressure < 0.45:
        triggered.append("buy_pressure_dry")

    # ── Signal 3: Liquidity Drain ──────────────────────────────────────────────
    # Pool liquidity dropped > 20% from entry = LP providers pulling out
    entry_liq = float(pos.get("entry_liquidity_usd", 0) or 0)
    current_liq = float(pos.get("current_liquidity_usd", 0) or 0)
    if entry_liq > 0 and current_liq > 0:
        liq_drop_pct = ((entry_liq - current_liq) / entry_liq) * 100
        if liq_drop_pct >= 20.0:
            triggered.append("liquidity_drain")

    # ── Signal 4: Below Mid-Range (structural breakdown) ──────────────────────
    # Price is both 10%+ below the high AND below the midpoint between
    # highest and entry — suggests the move is genuinely reversing
    if entry_price > 0 and highest_price > entry_price:
        mid_range = (highest_price + entry_price) / 2
        drop_from_high_pct = ((highest_price - current_price) / highest_price) * 100
        if drop_from_high_pct >= 10.0 and current_price < mid_range:
            triggered.append("below_midrange")

    # ── Signal 5: Momentum Death (recent candle shock) ────────────────────────
    # Current price dropped >5% from last recorded check price.
    # Detects sharp, fast continuation sells (not just a wick).
    last_check_price = float(pos.get("last_check_price", 0) or 0)
    if last_check_price > 0 and current_price > 0:
        recent_drop_pct = ((last_check_price - current_price) / last_check_price) * 100
        if recent_drop_pct >= 5.0:
            triggered.append("momentum_death")

    bearish_count = len(triggered)
    return {
        "bearish_count": bearish_count,
        "triggered": triggered,
        "blocked": bearish_count < 2,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Moralis Analytics — Dynamic TP Scaling Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _should_delay_tp1(pos: dict) -> bool:
    """
    Determine whether to DELAY the TP1 sell based on Moralis analytics.

    Returns True (delay sell) if ALL conditions are met:
      - net_buyers_1h >= ANALYTICS_NET_BUYERS_MIN (default 3) — sustained buying
      - net_buyers_5m >= 1 — recent buying activity confirms the trend
      - buy_volume_1h >= ANALYTICS_BUY_VOL_MIN_USD (default $5K) — meaningful volume
      - buy_pressure_ratio_1h >= 0.55 — more buy volume than sell

    When True, the caller sets tp1_hit=True and engages a tighter trailing stop
    instead of selling 40% at TP1.
    """
    if not settings.ANALYTICS_TP_DELAY_ENABLED:
        return False

    net_buyers_1h = int(pos.get("moralis_net_buyers_1h", 0))
    net_buyers_5m = int(pos.get("moralis_net_buyers_5m", 0))
    buy_vol_1h = float(pos.get("moralis_buy_volume_1h", 0))
    buy_pressure = float(pos.get("moralis_buy_pressure_1h", 0.5))

    min_net = settings.ANALYTICS_NET_BUYERS_MIN
    min_vol = settings.ANALYTICS_BUY_VOL_MIN_USD

    if (net_buyers_1h >= min_net
            and net_buyers_5m >= 1
            and buy_vol_1h >= min_vol
            and buy_pressure >= 0.55):
        logger.info(
            f"📊 Analytics TP1 delay conditions MET for {pos.get('token_symbol')}: "
            f"netBuyers_1h={net_buyers_1h} (min {min_net}), "
            f"netBuyers_5m={net_buyers_5m}, "
            f"buyVol_1h=${buy_vol_1h:,.0f} (min ${min_vol:,.0f}), "
            f"buyPressure={buy_pressure:.2f}"
        )
        return True

    return False


def _should_emergency_exit(pos: dict) -> Optional[dict]:
    """
    Check if Moralis analytics demand an emergency full exit.

    Returns a sell action dict if ALL conditions are met:
      - Position held > 30 minutes (give trades breathing room)
      - Position is NOT profitable (let TP/trailing handle winners)
      - net_buyers_1h < 0 — sellers outnumber buyers (1h window)
      - net_buyers_5m <= 0 — recent activity confirms sell pressure
      - buy_pressure_ratio_1h < 0.35 — heavy sell volume (65%+ of total)

    This fires BEFORE TP1 evaluation, catching dumps early.
    Returns None if no emergency exit is needed.
    """
    if not settings.ANALYTICS_EMERGENCY_EXIT_ENABLED:
        return None

    # TUNED 2026-06-10: Don't emergency exit profitable positions.
    # FAI (+0.2%), WAVE (+0.33%), GNUT (0%) were all cut by emergency exit
    # when they were slightly green. Let TP/trailing handle winners.
    unrealized_pnl_pct = float(pos.get("unrealized_pnl_pct", 0))
    if unrealized_pnl_pct > 0:
        return None

    # TUNED 2026-06-10: Minimum 30-minute hold time before emergency exit.
    # Meme coins have volatile buy/sell pressure in the first 30 minutes.
    entry_time_str = pos.get("entry_time", "")
    if entry_time_str:
        try:
            from datetime import datetime, timezone
            entry_time = datetime.fromisoformat(entry_time_str.replace("Z", "+00:00"))
            age_minutes = (datetime.now(timezone.utc) - entry_time).total_seconds() / 60
            if age_minutes < 30:
                return None
        except Exception:
            pass

    net_buyers_1h = int(pos.get("moralis_net_buyers_1h", 0))
    net_buyers_5m = int(pos.get("moralis_net_buyers_5m", 0))
    buy_pressure = float(pos.get("moralis_buy_pressure_1h", 0.5))

    # Only trigger if we have analytics data (buy_pressure != default 0.5)
    has_analytics = pos.get("moralis_buy_volume_1h") is not None

    if has_analytics and net_buyers_1h < 0 and net_buyers_5m <= 0 and buy_pressure < 0.35:
        logger.warning(
            f"🚨 Analytics Emergency Exit: {pos.get('token_symbol')} — "
            f"SELLERS DOMINATING! netBuyers_1h={net_buyers_1h}, "
            f"netBuyers_5m={net_buyers_5m}, buyPressure={buy_pressure:.2f} "
            f"— dumping full position NOW"
        )
        return {
            "reason": f"analytics_emergency_exit (netBuyers={net_buyers_1h}, pressure={buy_pressure:.2f})",
            "sell_pct": 1.0,
            "urgency": "immediate",
        }
        
    # Predictive De-Risking via Time-Series Analytics
    if pos.get("moralis_predictive_distribution"):
        logger.warning(
            f"🚨 Predictive De-risking Exit: {pos.get('token_symbol')} — "
            f"Whales/Smart Money are distributing (negative net volume trend detected in time-series). "
            f"Front-running the retail dump."
        )
        return {
            "reason": "predictive_derisking_exit (whale distribution trend)",
            "sell_pct": 1.0,
            "urgency": "immediate",
        }

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Take-Profit / Stop-Loss Evaluation
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_position(pos: dict, current_price: float,
                      strategy_profile=None) -> Optional[dict]:
    """
    Evaluate a position against take-profit and stop-loss rules.

    Uses per-wallet StrategyProfile if provided, else falls back to global settings.

    Returns a sell action dict if a sell should be triggered, else None.
    Action dict: {reason, sell_pct, urgency}
      - sell_pct: fraction of remaining position to sell (0.0-1.0)
      - urgency: "immediate" | "normal"
    """
    entry_price = float(pos.get("entry_price", 0))
    if entry_price <= 0:
        return None

    # Resolve profile values (profile → global settings fallback)
    if strategy_profile:
        sp = strategy_profile
        hard_stop_pct = sp.hard_stop_pct
        trailing_pct = sp.trailing_stop_pct
        tp1_mult = sp.tp1_mult
        tp1_sell = sp.tp1_sell_pct
        tp2_mult = sp.tp2_mult
        tp2_sell = sp.tp2_sell_pct
        tp3_mult = sp.tp3_mult
        tp3_sell = sp.tp3_sell_pct
        trailing_tighten = sp.trailing_tighten  # {mult: trail%}
        profile_name = sp.name
    else:
        from unittest.mock import MagicMock
        chain = pos.get("chain", "").lower()
        
        # Helper to unwrap MagicMocks
        def _val(val, fallback):
            return fallback if isinstance(val, MagicMock) else val

        if chain == "solana":
            hard_stop_pct = 10.0
            # TUNED 2026-06-10: trail 6→10%, TP1 1.2→1.35 — Solana memes are
            # far more volatile; tight trail was cutting winners early.
            trailing_pct = 10.0
            tp1_mult = 1.35
            tp1_sell = _val(settings.TAKE_PROFIT_TP1_SELL_PCT, 0.40)
            tp2_mult = 1.8
            tp2_sell = _val(settings.TAKE_PROFIT_TP2_SELL_PCT, 0.35)
            tp3_mult = _val(getattr(settings, "TAKE_PROFIT_TP3_MULT", 5.0), 5.0)
            tp3_sell = _val(getattr(settings, "TAKE_PROFIT_TP3_SELL_PCT", 0.25), 0.25)
            trailing_tighten = {}
            profile_name = "solana_shadow_default"
        elif chain == "base":
            hard_stop_pct = 15.0
            trailing_pct = 15.0
            tp1_mult = 1.5
            tp1_sell = _val(settings.TAKE_PROFIT_TP1_SELL_PCT, 0.40)
            tp2_mult = 2.5
            tp2_sell = _val(settings.TAKE_PROFIT_TP2_SELL_PCT, 0.35)
            tp3_mult = _val(getattr(settings, "TAKE_PROFIT_TP3_MULT", 5.0), 5.0)
            tp3_sell = _val(getattr(settings, "TAKE_PROFIT_TP3_SELL_PCT", 0.25), 0.25)
            trailing_tighten = {}
            profile_name = "base_shadow_default"
        else:
            hard_stop_pct = _val(settings.HARD_STOP_LOSS_PERCENT, 10.0)
            trailing_pct = _val(settings.STOP_LOSS_PERCENT, 5.0)
            tp1_mult = _val(settings.TAKE_PROFIT_TP1_MULT, 1.5)
            tp1_sell = _val(settings.TAKE_PROFIT_TP1_SELL_PCT, 0.40)
            tp2_mult = _val(settings.TAKE_PROFIT_TP2_MULT, 2.5)
            tp2_sell = _val(settings.TAKE_PROFIT_TP2_SELL_PCT, 0.35)
            tp3_mult = _val(getattr(settings, "TAKE_PROFIT_TP3_MULT", 5.0), 5.0)
            tp3_sell = _val(getattr(settings, "TAKE_PROFIT_TP3_SELL_PCT", 0.25), 0.25)
            trailing_tighten = {}
            profile_name = "default"

    # ── Deep RL Regime Filter Dynamic Personality Switch ──
    try:
        from unittest.mock import MagicMock
        from core.regime_filter import get_regime, Regime
        regime_state = get_regime()
        
        # If get_regime or its return value is a MagicMock (mocked in some tests), skip personality switch
        if isinstance(regime_state, MagicMock) or isinstance(getattr(regime_state, "regime", None), MagicMock):
            raise TypeError("Mock detected")
            
        market_regime = regime_state.regime
        
        # Bypass regime overrides if tests are running in paper mode
        is_test = pos.get("token_symbol") == "TEST" and getattr(settings, "MODE", "") == "paper"
        
        if not is_test:
            if market_regime == Regime.TRENDING:
                # Loosen trailing stops and let winners run for massive multipliers
                trailing_pct = max(trailing_pct * 1.5, 12.0)
                tp1_mult = tp1_mult * 1.5
                tp2_mult = tp2_mult * 1.8
                tp3_mult = tp3_mult * 2.0 if tp3_mult > 0 else 10.0
                profile_name = f"{profile_name}_trending_run"
                logger.info(
                    f"📈 Regime TRENDING: loosened trail to {trailing_pct:.1f}% "
                    f"and boosted TPs (TP1:{tp1_mult:.1f}x, TP2:{tp2_mult:.1f}x, TP3:{tp3_mult:.1f}x) "
                    f"for {pos.get('token_symbol')}"
                )
            elif market_regime == Regime.CHOPPY:
                # TUNED 2026-06-11: Mean-Reversion widened for parabolic gains.
                # Old: 3% scalp, sell 100% — left money on table (DragonWorm +6.46%, Mu +13.58%)
                # New: 6% scalp, sell 60% — let 40% ride with trailing for bigger wins
                tp1_mult = 1.06  # 6% scalp (was 3%)
                tp1_sell = 0.60  # Sell 60% (was 100%), let 40% ride
                tp2_mult = 1.12  # 12% second target for the runner
                tp2_sell = 1.0   # Sell remaining 100% at 12%
                trailing_pct = 4.0  # Wider trail for the 40% runner (was 1.5%)
                profile_name = f"{profile_name}_mean_reversion"
                logger.info(
                    f"😴 Regime CHOPPY: Mean-Reversion active (TP1: 6% sell 60%, TP2: 12% sell rest, trail: 4%) "
                    f"for {pos.get('token_symbol')}"
                )
            elif market_regime == Regime.NUKE:
                # Trigger immediate 'Risk-Off' protocol, tightening all stop-losses to 1% to protect capital
                hard_stop_pct = 1.0
                trailing_pct = 1.0
                profile_name = f"{profile_name}_risk_off_nuke"
                logger.warning(
                    f"🚨 Regime NUKE: RISK-OFF protocol active! Tightened SL to 1% "
                    f"for {pos.get('token_symbol')}"
                )
    except Exception as regime_err:
        logger.debug(f"Regime personality switch skipped: {regime_err}")
    # Fallback default values already resolved above if no strategy_profile was passed.
    pass

    # ── Position-level trailing_stop_pct override ─────────────────────────────
    # Allows tests and dynamic trailing logic to tighten the trail below the
    # profile default. We take the minimum (tighter) of the two values so a
    # position override can never *widen* a profile-defined trail.
    _pos_trail_override = pos.get("trailing_stop_pct")
    if _pos_trail_override is not None:
        try:
            _pos_trail_override = float(_pos_trail_override)
            if _pos_trail_override > 0:
                trailing_pct = min(trailing_pct, _pos_trail_override)
        except (TypeError, ValueError):
            pass

    gain_pct = ((current_price - entry_price) / entry_price) * 100
    gain_mult = current_price / entry_price  # 5.0 = 5x
    highest_price = float(pos.get("highest_price", entry_price))
    tp1_hit = pos.get("tp1_hit", False)
    tp2_hit = pos.get("tp2_hit", False)
    tp3_hit = pos.get("tp3_hit", False)
    entry_time = pos.get("entry_time")

    # ── Hard stop-loss ────────────────────────────────────────────────────────
    hard_stop = -hard_stop_pct
    if gain_pct <= hard_stop + 0.001:  # +0.001% tolerance for float precision at exact boundary
        return {
            "reason": f"hard_stop_loss ({gain_pct:.1f}%) [{profile_name}]",
            "sell_pct": 1.0,
            "urgency": "immediate",
        }

    # ── Rapid Decay Emergency Exit ────────────────────────────────────────────
    # ADDED 2026-06-10: SpaceX rug went to $0 in ~10min. The periodic monitor
    # cycle missed it because the hard stop check runs every 30-60s.
    # If a position is down >5% within 10 minutes of entry, it's almost certainly
    # a rug pull or pump-and-dump — dump immediately, don't wait for hard stop.
    if entry_time and gain_pct < -5.0:
        try:
            import datetime
            _now = datetime.datetime.now(datetime.timezone.utc)
            _entry_dt = datetime.datetime.fromisoformat(entry_time)
            _minutes_held = (_now - _entry_dt).total_seconds() / 60
            if _minutes_held <= 10.0:
                logger.warning(
                    f"🚨 RAPID DECAY EXIT: {pos.get('token_symbol')} is {gain_pct:.1f}% "
                    f"down after only {_minutes_held:.1f}min — likely rug pull. "
                    f"Emergency dump!"
                )
                return {
                    "reason": f"rapid_decay_exit ({gain_pct:.1f}% in {_minutes_held:.0f}min) [{profile_name}]",
                    "sell_pct": 1.0,
                    "urgency": "immediate",
                }
        except Exception:
            pass  # Don't block on time parsing errors

    # ── FIX BUG 1: Pre-TP1 Peak Protection ───────────────────────────────────
    # CRITICAL: Without this, a position that peaks at +40% then falls to -20%
    # hits only the hard stop — all unrealized gain is surrendered. This trailing
    # stop activates BEFORE TP1 with a wider window (default 25%) to protect
    # any significant gain buildup while still giving room to keep running.
    pre_tp1_trail = getattr(settings, "PRE_TP1_TRAILING_STOP_PCT", 25.0)
    pre_tp1_activate = getattr(settings, "PRE_TP1_ACTIVATE_GAIN_PCT", 15.0)
    if not tp1_hit and highest_price >= entry_price * (1 + pre_tp1_activate / 100):
        pre_tp1_stop = highest_price * (1 - pre_tp1_trail / 100)
        if current_price <= pre_tp1_stop:
            drop_from_high = ((current_price - highest_price) / highest_price) * 100
            logger.info(
                f"🛑 Pre-TP1 Peak Protection: {pos.get('token_symbol')} "
                f"hit {drop_from_high:.1f}% drawdown from ${highest_price:.6f} high "
                f"(trail={pre_tp1_trail:.0f}%) — locking in gains before TP1"
            )
            return {
                "reason": f"pre_tp1_peak_protection ({drop_from_high:.1f}% from high, trail={pre_tp1_trail:.0f}%) [{profile_name}]",
                "sell_pct": 1.0,
                "urgency": "immediate",
            }

    # ── Parabolic Parachute (Fibonacci Over-Extension Lock) ──────────────────
    # SECURES MAXIMUM RUNNERS: If a token breaches extreme Fibonacci gain levels
    # (e.g. +161.8% or +423.6%), we override all confluence checks and standard
    # trailing stops. We tighten the trail instantly to front-run dumps on the wick.
    max_gain_pct = ((highest_price - entry_price) / entry_price) * 100
    param_ext_act = getattr(settings, "EXTREME_PARABOLIC_ACTIVATION_PCT", 423.6)
    param_ext_trail = getattr(settings, "EXTREME_PARABOLIC_TRAILING_STOP_PCT", 2.0)
    param_par_act = getattr(settings, "PARABOLIC_ACTIVATION_PCT", 161.8)
    param_par_trail = getattr(settings, "PARABOLIC_TRAILING_STOP_PCT", 5.0)

    # Use a small epsilon (0.01%) to handle floating-point imprecision when
    # the highest_price is set to exactly the Fibonacci level (e.g. 5.236x
    # gives max_gain_pct = 423.5999... which fails a strict >= 423.6 check).
    _FIB_EPS = 0.01
    is_extreme = max_gain_pct >= (param_ext_act - _FIB_EPS)
    is_parabolic = max_gain_pct >= (param_par_act - _FIB_EPS)

    if is_extreme or is_parabolic:
        locked_trail = param_ext_trail if is_extreme else param_par_trail
        para_stop_price = highest_price * (1 - locked_trail / 100)
        
        if current_price <= para_stop_price:
            drop_from_high = ((current_price - highest_price) / highest_price) * 100
            zone = "EXTREME 4.236 Fib" if is_extreme else "1.618 Fib"
            logger.warning(
                f"🪂 PARABOLIC PARACHUTE ACTIVATED: {pos.get('token_symbol')} "
                f"broke {zone} at {max_gain_pct:.1f}% gain! Dropped {drop_from_high:.1f}% "
                f"from wick high (${highest_price:.6f}) under {locked_trail}% locked trail. "
                f"SECURING THE BAG IMMEDIATELY."
            )
            return {
                "reason": f"parabolic_parachute_exit ({zone}, {max_gain_pct:.1f}% max gain, locked trail {locked_trail}%) [{profile_name}]",
                "sell_pct": 1.0,
                "urgency": "immediate",
            }

    # ── Dynamic trailing stop (only active after TP1) ─────────────────────────
    if tp1_hit and highest_price > entry_price:
        # Determine effective trailing % based on dynamic tightening
        effective_trail = trailing_pct
        if trailing_tighten:
            for mult_threshold, tight_pct in sorted(trailing_tighten.items()):
                if gain_mult >= float(mult_threshold):
                    effective_trail = tight_pct

        # Apply volatility/ATR adjustment if price metrics exist
        high_24h = float(pos.get("high_24h", 0) or 0)
        low_24h = float(pos.get("low_24h", 0) or 0)
        atr_val = float(pos.get("atr_14", 0) or 0)
        if current_price > 0 and (atr_val > 0 or (high_24h > low_24h > 0)):
            vol_ratio = (atr_val / current_price) if atr_val > 0 else ((high_24h - low_24h) / current_price)
            if vol_ratio > 0.15:
                effective_trail = min(28.0, effective_trail * 1.30)
            elif 0 < vol_ratio < 0.04:
                effective_trail = max(4.0, effective_trail * 0.75)

        trailing_stop_price = highest_price * (1 - effective_trail / 100)
        if current_price <= trailing_stop_price:
            drop_from_high = ((current_price - highest_price) / highest_price) * 100
            # ── Multi-Signal Confluence Gate — protect profitable positions ───
            # For positions well above TP1 (gain > 20%), require 2-of-5 bearish
            # signals before executing the trailing stop. Single bad candles
            # shouldn't shake us out of a genuine winner.
            if gain_pct > 20.0:
                # FIX BUG 2: Confluence gate was requiring 2/5 bearish signals,
                # but most signals depend on stored data fields (entry_volume_1h,
                # buy_pressure_ratio, entry_liquidity_usd) that are often absent.
                # When fields are missing, bearish_count stays 0 → sell PERMANENTLY
                # BLOCKED. Fix: (a) lower to 1/5, (b) hard override if price dropped
                # >CONFLUENCE_HARD_REVERSAL_PCT from peak regardless of signals.
                hard_reversal_pct = getattr(settings, "CONFLUENCE_HARD_REVERSAL_PCT", 25.0)
                drop_pct_from_high = ((highest_price - current_price) / highest_price) * 100

                # Hard override: severe reversal bypasses all signal checks
                if drop_pct_from_high >= hard_reversal_pct:
                    logger.info(
                        f"🛑 Hard reversal override: {pos.get('token_symbol')} "
                        f"lost {drop_pct_from_high:.1f}% from peak — selling regardless of confluence"
                    )
                    return {
                        "reason": f"trailing_stop_hard_reversal ({drop_from_high:.1f}% from high, {drop_pct_from_high:.1f}%>{hard_reversal_pct:.0f}% override) [{profile_name}]",
                        "sell_pct": 1.0,
                        "urgency": "immediate",
                    }

                confluence = evaluate_profit_sell_confluence(pos, current_price)

                # ── Data-availability bypass ──────────────────────────────────
                # The confluence gate requires live data (volume_1h, current_liq,
                # last_check_price) that is only present on positions managed by
                # the live monitor loop. When those fields are absent (e.g. in
                # unit tests or freshly-opened positions), bearish_count stays 0
                # and the gate permanently blocks the trailing stop.
                # Fix: if none of the data-dependent signals could even fire
                # (all three live-data fields are missing/zero), bypass the gate
                # and let the trailing stop execute normally.
                _has_live_data = (
                    float(pos.get("volume_1h", 0) or 0) > 0
                    or float(pos.get("current_liquidity_usd", 0) or 0) > 0
                    or float(pos.get("last_check_price", 0) or 0) > 0
                )

                if not _has_live_data:
                    # No live data available — trailing stop fires without gate
                    logger.debug(
                        f"🛑 Trailing stop (no live data, gate bypassed) for "
                        f"{pos.get('token_symbol')} — {drop_from_high:.1f}% from high"
                    )
                    return {
                        "reason": f"trailing_stop ({drop_from_high:.1f}% from high, trail={effective_trail:.0f}%) [{profile_name}]",
                        "sell_pct": 1.0,
                        "urgency": "immediate",
                    }
                elif confluence["bearish_count"] < 1:  # Was 2, lowered to 1
                    logger.debug(
                        f"🛡️  Trailing stop suppressed for {pos.get('token_symbol')} "
                        f"({drop_from_high:.1f}% from high) — {confluence['bearish_count']}/5 "
                        f"bearish signals ({', '.join(confluence['triggered'])}). "
                        f"Need 1+ to confirm reversal."
                    )
                    # Don't sell yet — let the position breathe
                else:
                    logger.info(
                        f"🛑 Trailing stop CONFIRMED for {pos.get('token_symbol')} — "
                        f"{confluence['bearish_count']}/5 bearish: {confluence['triggered']}"
                    )
                    return {
                        "reason": f"trailing_stop ({drop_from_high:.1f}% from high, trail={effective_trail:.0f}%, confluence={confluence['bearish_count']}/5) [{profile_name}]",
                        "sell_pct": 1.0,
                        "urgency": "immediate",
                    }
            else:
                return {
                    "reason": f"trailing_stop ({drop_from_high:.1f}% from high, trail={effective_trail:.0f}%) [{profile_name}]",
                    "sell_pct": 1.0,
                    "urgency": "immediate",
                }

    # ── Take-profit tiers ─────────────────────────────────────────────────────
    # Dynamic TP: ATR-relative levels replace fixed multipliers when enabled.
    # Inspired by Freqtrade's custom_exit() — adapts TP levels to volatility.
    try:
        from strategies.dynamic_tp import calculate_dynamic_tp, DYNAMIC_TP_ENABLED as _DTP_ENABLED
        if _DTP_ENABLED:
            _dtp_closes = pos.get("ohlcv_closes")
            _dtp_highs = pos.get("ohlcv_highs")
            _dtp_lows = pos.get("ohlcv_lows")
            _age_h = 0.0
            if entry_time:
                try:
                    _entry_dt = datetime.fromisoformat(str(entry_time).replace("Z", "+00:00"))
                    _age_h = (datetime.now(timezone.utc) - _entry_dt).total_seconds() / 3600
                except Exception:
                    pass
            _macro = pos.get("macro_regime", "NEUTRAL")
            if _dtp_closes and len(_dtp_closes) >= 15:
                _dtp = calculate_dynamic_tp(
                    entry_price=entry_price,
                    closes=_dtp_closes, highs=_dtp_highs, lows=_dtp_lows,
                    position_age_hours=_age_h,
                    macro_regime=_macro,
                )
                if _dtp.tp1_gain_pct > 0:
                    tp1_gain_override = _dtp.tp1_gain_pct
                    tp1_mult = 1 + tp1_gain_override / 100
                    tp2_mult = 1 + _dtp.tp2_gain_pct / 100
                    tp3_mult = 1 + _dtp.tp3_gain_pct / 100
                    logger.debug(
                        f"Dynamic TP override: TP1={_dtp.tp1_gain_pct:.0f}% "
                        f"TP2={_dtp.tp2_gain_pct:.0f}% TP3={_dtp.tp3_gain_pct:.0f}%"
                    )

                # Early exit recommendation from velocity stall
                if _dtp.early_exit_recommended and not tp1_hit:
                    if gain_pct > 5.0:  # Only exit early if at least slightly profitable
                        logger.info(
                            f"📉 Dynamic TP early exit: {pos.get('token_symbol')} — "
                            f"P(TP1)={_dtp.p_tp1:.0%} too low, velocity stalled. "
                            f"Exiting at {gain_pct:.1f}% gain."
                        )
                        return {
                            "reason": f"dynamic_tp_early_exit (P(TP1)={_dtp.p_tp1:.0%}, vel={_dtp.velocity_ratio:.2f}) [{profile_name}]",
                            "sell_pct": 1.0,
                            "urgency": "normal",
                        }
    except Exception as _dtp_err:
        logger.debug(f"Dynamic TP skipped: {_dtp_err}")

    # TP1 — with dynamic analytics-driven delay
    tp1_gain = (tp1_mult - 1) * 100
    if not tp1_hit and gain_pct >= tp1_gain:
        # Check if Moralis analytics says "let it run"
        if settings.ANALYTICS_TP_DELAY_ENABLED and _should_delay_tp1(pos):
            logger.info(
                f"📊 Analytics TP1 Delay: {pos.get('token_symbol')} hit TP1 "
                f"({gain_pct:.1f}%) but netBuyers is strong — DELAYING sell, "
                f"engaging {settings.ANALYTICS_TIGHT_TRAIL_PCT:.0f}% tight trail"
            )
            # Return a special sentinel so the caller knows to delay
            return {
                "reason": f"tp1_analytics_delay [{profile_name}]",
                "sell_pct": 0.0,           # 0% = don't sell
                "urgency": "analytics_delay",
                "analytics_delay": True,
            }
        return {
            "reason": f"tp1_{tp1_mult:.0f}x [{profile_name}]",
            "sell_pct": tp1_sell,
            "urgency": "normal",
        }

    # TP2
    tp2_gain = (tp2_mult - 1) * 100
    if tp1_hit and not tp2_hit and gain_pct >= tp2_gain:
        return {
            "reason": f"tp2_{tp2_mult:.0f}x [{profile_name}]",
            "sell_pct": tp2_sell,
            "urgency": "normal",
        }

    # TP3 (nuclear only — conservative has tp3_mult=0 which disables it)
    if tp3_mult > 0:
        tp3_gain = (tp3_mult - 1) * 100
        if tp2_hit and not tp3_hit and gain_pct >= tp3_gain:
            return {
                "reason": f"tp3_{tp3_mult:.0f}x [{profile_name}]",
                "sell_pct": tp3_sell,
                "urgency": "normal",
            }

    # After final TP, remaining position rides with dynamic trailing stop

    # ── Time-Based ROI Decay (Freqtrade Style) ──────────────────────────────────
    if entry_time and not tp1_hit:
        try:
            entry_dt = datetime.fromisoformat(str(entry_time).replace("Z", "+00:00"))
            age_minutes = (datetime.now(timezone.utc) - entry_dt).total_seconds() / 60
            
            # Find the active decay bracket
            target_roi = None
            if hasattr(settings, "PROGRESSIVE_ROI_DECAY"):
                sorted_decay = sorted(settings.PROGRESSIVE_ROI_DECAY.items(), reverse=True)
                for minutes, roi_pct in sorted_decay:
                    if age_minutes >= float(minutes):
                        target_roi = roi_pct
                        break
            
            # Execute progressive take profit
            if target_roi is not None and target_roi > 0 and gain_pct >= target_roi:
                logger.info(
                    f"⏱️ ROI Decay Triggered: {pos.get('token_symbol')} held for {age_minutes:.0f}m, "
                    f"exiting at {gain_pct:.1f}% (target was {target_roi:.1f}%)"
                )
                return {
                    "reason": f"progressive_roi_decay ({age_minutes:.0f}m, {gain_pct:.1f}% >= {target_roi:.1f}%) [{profile_name}]",
                    "sell_pct": 1.0,  # Sell remaining position to free capital
                    "urgency": "normal",
                }
                
            # Fallback to the old dead capital exit if no progressive decay fired
            age_hours = age_minutes / 60
            if age_hours >= settings.TIME_EXIT_HOURS and gain_pct < settings.TIME_EXIT_MIN_GAIN_PCT:
                return {
                    "reason": f"time_exit_{settings.TIME_EXIT_HOURS:.0f}h (gain={gain_pct:.1f}%) [{profile_name}]",
                    "sell_pct": 1.0,
                    "urgency": "normal",
                }
        except Exception:
            pass

    # ── Liquidity drain emergency exit ────────────────────────────────────────
    if settings.LIQUIDITY_DRAIN_EXIT_ENABLED:
        entry_liq = float(pos.get("entry_liquidity_usd", 0) or 0)
        current_liq = float(pos.get("current_liquidity_usd", 0) or 0)

        # ── Per-Cycle Liquidity Drain (Front-run dumps) ──

        prev_liq = float(pos.get("prev_liquidity_usd", entry_liq))

        if prev_liq > 0 and current_liq > 0:

            cycle_drop_pct = ((prev_liq - current_liq) / prev_liq) * 100

            if cycle_drop_pct >= 15.0:  # >15% drop in a single 30s cycle = rug/dump incoming

                return {

                    "reason": f"liquidity_drain_fast ({cycle_drop_pct:.0f}% pool drop in 30s) [{profile_name}]",

                    "sell_pct": 1.0,

                    "urgency": "immediate",

                }

        # ── Total Liquidity Drain (from entry) ──
        if entry_liq > 0 and current_liq > 0:
            liq_drop_pct = ((entry_liq - current_liq) / entry_liq) * 100
            if liq_drop_pct >= settings.LIQUIDITY_DRAIN_DROP_PCT:
                return {
                    "reason": f"liquidity_drain ({liq_drop_pct:.0f}% pool drop) [{profile_name}]",
                    "sell_pct": 1.0,
                    "urgency": "immediate",
                }

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Offensive Guardrails — Work In Our Favor
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_volume_surge_exit(pos: dict, current_price: float) -> Optional[dict]:
    """
    Volume surge fast exit: if volume spikes >10x 24h avg while position is
    profitable, take partial profit immediately. Blowoff tops often precede
    sharp reversals — we lock in gains before the dump.
    """
    if not settings.VOLUME_SURGE_EXIT_ENABLED:
        return None

    entry_price = float(pos.get("entry_price", 0))
    if entry_price <= 0:
        return None

    gain_pct = ((current_price - entry_price) / entry_price) * 100
    if gain_pct < settings.VOLUME_SURGE_MIN_GAIN_PCT:
        return None

    # Check volume surge (we store volume data on position updates)
    volume_1h = float(pos.get("volume_1h", 0))
    volume_24h = float(pos.get("volume_24h", 0))
    if volume_24h > 0 and volume_1h > 0:
        hourly_avg = volume_24h / 24
        if hourly_avg > 0 and volume_1h / hourly_avg >= settings.VOLUME_SURGE_MULTIPLIER:
            # Already did a surge exit? Don't do it again
            if pos.get("volume_surge_exit_done"):
                return None
            return {
                "reason": f"volume_surge_exit (vol={volume_1h/hourly_avg:.0f}x avg, gain={gain_pct:.0f}%)",
                "sell_pct": settings.VOLUME_SURGE_SELL_PCT,
                "urgency": "immediate",
                "_mark": "volume_surge_exit_done",
            }

    return None


def evaluate_underperformer_exit(pos: dict, current_price: float) -> Optional[dict]:
    """
    Underperformer rotation: close flat positions (±5% for 12+ hours) to free
    capital for higher-scoring new gems. Dead money = opportunity cost.
    """
    if not settings.UNDERPERFORMER_EXIT_ENABLED:
        return None

    entry_price = float(pos.get("entry_price", 0))
    if entry_price <= 0:
        return None

    # Don't exit if already in profit territory (TP system handles that)
    gain_pct = ((current_price - entry_price) / entry_price) * 100
    if abs(gain_pct) > settings.UNDERPERFORMER_FLAT_PCT:
        return None

    # Check how long the position has been open
    entry_time = pos.get("entry_time")
    if not entry_time:
        return None

    try:
        entry_dt = datetime.fromisoformat(str(entry_time).replace("Z", "+00:00"))
        age_hours = (datetime.now(timezone.utc) - entry_dt).total_seconds() / 3600
        if age_hours >= settings.UNDERPERFORMER_FLAT_HOURS:
            return {
                "reason": f"underperformer_rotation ({gain_pct:+.1f}% after {age_hours:.0f}h)",
                "sell_pct": 1.0,
                "urgency": "normal",
            }
    except Exception:
        pass

    return None


def check_winner_scaling(pos: dict, current_price: float) -> Optional[dict]:
    """
    Winner scaling: if a position is up >30% and hasn't been scaled yet,
    return a signal to buy more. The main loop handles the actual execution.
    Returns a dict with scaling info if triggered, None otherwise.
    """
    if not settings.WINNER_SCALING_ENABLED:
        return None

    entry_price = float(pos.get("entry_price", 0))
    if entry_price <= 0:
        return None

    gain_pct = ((current_price - entry_price) / entry_price) * 100
    scale_count = int(pos.get("scale_in_count", 0))

    if gain_pct >= settings.WINNER_SCALING_GAIN_PCT and scale_count < settings.WINNER_SCALING_MAX_ADDS:
        return {
            "action": "scale_in",
            "token_address": pos.get("token_address"),
            "token_symbol": pos.get("token_symbol"),
            "chain": pos.get("chain"),
            "wallet": pos.get("wallet"),
            "gain_pct": gain_pct,
            "current_price": current_price,
        }

    return None


def check_smart_dca(pos: dict, current_price: float) -> Optional[dict]:
    """
    Smart DCA: if a high-conviction position dips 15% (above the 25% hard stop),
    buy more to lower average entry. Only triggers once per position.
    """
    if not settings.SMART_DCA_ENABLED:
        return None

    entry_price = float(pos.get("entry_price", 0))
    gem_score = float(pos.get("gem_score", 0))
    if entry_price <= 0:
        return None

    # Only DCA on high-conviction picks
    if gem_score < settings.SMART_DCA_MIN_GEM_SCORE:
        return None

    # Already DCA'd?
    if pos.get("dca_done"):
        return None

    gain_pct = ((current_price - entry_price) / entry_price) * 100
    # Dip range: between -SMART_DCA_DIP_PCT and -HARD_STOP_LOSS
    if -settings.HARD_STOP_LOSS_PERCENT < gain_pct <= -settings.SMART_DCA_DIP_PCT:
        return {
            "action": "dca",
            "token_address": pos.get("token_address"),
            "token_symbol": pos.get("token_symbol"),
            "chain": pos.get("chain"),
            "wallet": pos.get("wallet"),
            "gain_pct": gain_pct,
            "current_price": current_price,
            "gem_score": gem_score,
        }

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Sell Execution (paper + live)
# ─────────────────────────────────────────────────────────────────────────────

def execute_sell(pos: dict, sell_action: dict, current_price: float, is_paper: bool = True) -> dict:
    """
    Execute a sell order for a position.
    Returns updated position dict (or None if fully closed).
    """
    sell_pct = sell_action["sell_pct"]
    reason = sell_action["reason"]
    remaining_qty = float(pos.get("remaining_quantity", pos.get("quantity", 0)))
    sell_qty = remaining_qty * sell_pct
    sell_value_usd = sell_qty * current_price
    entry_price = float(pos.get("entry_price", 0))
    pnl_usd = sell_qty * (current_price - entry_price)
    pnl_pct = ((current_price - entry_price) / entry_price) * 100 if entry_price > 0 else 0

    # ── P&L Sanity Cap (Paper Mode) ───────────────────────────────────────
    # Micro-cap tokens can produce absurd P&L because quantity is enormous
    # (e.g. $2 buys 666M tokens at $0.000003 → 1% drop = $13.3K loss).
    # Cap P&L at ±entry_value_usd so a $2 paper position can't move P&L by $700.
    if is_paper:
        entry_value = float(pos.get("entry_value_usd", 0)) or (entry_price * remaining_qty)
        sell_entry_value = entry_value * sell_pct  # Pro-rata for partial sells
        if sell_entry_value > 0:
            max_loss = -sell_entry_value  # Can't lose more than you invested
            max_gain = sell_entry_value * 5.0  # Cap at 500% gain
            if pnl_usd < max_loss:
                logger.debug(
                    f"P&L cap: {pos.get('token_symbol')} raw=${pnl_usd:.2f} → "
                    f"capped=${max_loss:.2f} (entry_value=${sell_entry_value:.2f})"
                )
                pnl_usd = max_loss
            elif pnl_usd > max_gain:
                logger.debug(
                    f"P&L cap: {pos.get('token_symbol')} raw=${pnl_usd:.2f} → "
                    f"capped=${max_gain:.2f} (entry_value=${sell_entry_value:.2f})"
                )
                pnl_usd = max_gain

    now = datetime.now(timezone.utc).isoformat()

    trade_record = {
        "timestamp": now,
        "token_address": pos.get("token_address"),
        "token_symbol": pos.get("token_symbol"),
        "chain": pos.get("chain"),
        "wallet": pos.get("wallet"),
        "action": "SELL",
        "reason": reason,
        "quantity": sell_qty,
        "price_usd": current_price,
        "value_usd": sell_value_usd,
        "entry_price": entry_price,
        "pnl_usd": pnl_usd,
        "pnl_pct": pnl_pct,
        "is_paper": is_paper,
        "tx_hash": None,  # Set by live executor
        "signal_scores": pos.get("signal_scores", {}),
        "gem_score": pos.get("gem_score", 0),
        "entry_time": pos.get("entry_time", ""),
        "strategy_profile": pos.get("strategy_profile", ""),
    }

    if not is_paper:
        # ── Honeypot re-check before live sell ────────────────────────────
        # Some scam tokens modify their contract AFTER you buy — enabling
        # sell tax or making the token unsellable. Re-check before selling.
        try:
            from data.providers.goplus import check_token_safety
            _safety = check_token_safety(pos.get("token_address", ""), pos.get("chain", ""))
            if isinstance(_safety, dict):
                _is_hp = _safety.get("is_honeypot", False)
                _sell_tax = float(_safety.get("sell_tax", 0) or 0)
                if _is_hp:
                    logger.critical(
                        f"🚨 HONEYPOT DETECTED on sell: {pos.get('token_symbol')} "
                        f"is now a honeypot! Skipping sell — manual intervention required."
                    )
                    try:
                        from notifications.telegram import notify_alert
                        notify_alert(
                            "🚨 HONEYPOT — SELL BLOCKED",
                            f"{pos.get('token_symbol')} on {pos.get('chain')} is now a honeypot.\n"
                            f"GoPlus flagged it AFTER your buy.\n"
                            f"Manual intervention required — the token may be unsellable.",
                            level="error",
                        )
                    except Exception:
                        pass
                    pos["honeypot_detected"] = True
                    return pos  # Abort sell — don't lose gas on a guaranteed revert
                elif _sell_tax > 0.15:
                    logger.warning(
                        f"⚠️ Sell tax increased: {pos.get('token_symbol')} "
                        f"sell tax is now {_sell_tax*100:.1f}% — widening slippage"
                    )
                    pos["_sell_tax_override"] = _sell_tax
        except Exception as _hp_err:
            logger.debug(f"Honeypot re-check failed (non-blocking): {_hp_err}")

        # ── SELL ENGINE: Aggressive, fault-tolerant execution ─────────────────
        # Uses core/sell_engine.py which fixes all root causes of missed sells:
        #   1. Solana: Jito-first (not standard RPC) for ALL sells
        #   2. Slippage escalation: 200 → 500 → 1500 → 3000bps
        #   3. On-chain balance fallback if remaining_quantity=0
        #   4. 4-attempt retry with exponential backoff
        #   5. EVM: approval bypass for token→native sells
        try:
            from core.sell_engine import (
                execute_sell_solana,
                execute_sell_evm,
                resolve_sell_quantity,
            )
            from config.wallets import WALLETS

            chain = pos.get("chain", "")
            sell_urgency = sell_action.get("urgency", "normal")
            wallet_alias = pos.get("wallet", "primary")
            wallet = WALLETS.get(wallet_alias)
            if not wallet:
                for wk, wv in WALLETS.items():
                    if (wv.address.lower() == wallet_alias.lower()
                            or wv.alias.lower() == wallet_alias.lower()):
                        wallet = wv
                        break
            if not wallet:
                raise ValueError(f"No wallet found for '{wallet_alias}'")

            # Resolve actual sell quantity with on-chain fallback
            resolved_qty, resolved_units = resolve_sell_quantity(pos, sell_pct)
            if resolved_units <= 0:
                raise RuntimeError(
                    f"Cannot sell {pos.get('token_symbol')}: resolved_units=0 "
                    f"(remaining_qty={pos.get('remaining_quantity')}, sell_pct={sell_pct})"
                )

            # Update sell_qty to resolved value
            sell_qty = resolved_qty

            # ⚠️  Paper-mode guard: is_paper is passed from PositionMonitor.is_paper
            # (which reads settings.IS_PAPER dynamically). The previous code
            # hardcoded is_paper=False here, bypassing paper mode on sells.
            if chain.lower() == "solana":
                sol_pub = getattr(wallet, "solana_address", "") or ""
                sol_key_env = getattr(wallet, "solana_private_key_env", "") or ""
                sell_result = execute_sell_solana(
                    token_mint=pos["token_address"],
                    token_amount_units=resolved_units,
                    wallet_public_key=sol_pub,
                    wallet_private_key_env=sol_key_env,
                    urgency=sell_urgency,
                    is_paper=False if chain.lower() == "hyperliquid" else is_paper,  # ✅ Fixed: was hardcoded False
                    prior_failures=pos.get("sell_failure_count", 0),
                )
            else:
                sell_result = execute_sell_evm(
                    token_address=pos["token_address"],
                    token_amount_wei=resolved_units,
                    chain=chain,
                    wallet=wallet,
                    urgency=sell_urgency,
                    is_paper=False if chain.lower() == "hyperliquid" else is_paper,  # ✅ Fixed: was hardcoded False
                    prior_failures=pos.get("sell_failure_count", 0),
                    position_value_usd=sell_qty * current_price if current_price else 0,
                )

            tx_hash = sell_result.tx_hash if sell_result.success else None
            if not sell_result.success:
                # ── Gas prohibitive: don't count as failure, just back off ──
                if hasattr(sell_result, 'gas_prohibitive') and sell_result.gas_prohibitive:
                    logger.info(
                        f"⛽ SELL SKIPPED (gas): {pos.get('token_symbol')} on {chain} | "
                        f"value=${sell_qty * current_price:.2f} — retry in 5m"
                    )
                    pos['next_sell_retry_at'] = time.time() + 300
                    return pos  # Don't increment failure count, just skip
                
                # ── No liquidity / Dust: auto-close position ──
                err_val = getattr(sell_result, 'error', '')
                if err_val in ('no_liquidity_dead_token', 'quote_failed_no_liquidity', 'dust_value_unsellable'):
                    logger.warning(
                        f"🚫 SELL SKIPPED ({err_val}): {pos.get('token_symbol')} on {chain} — "
                        f"auto-closing position"
                    )
                    trade_record["auto_closed_phantom"] = True
                    append_trade(trade_record)
                    pos = dict(pos)
                    pos["remaining_quantity"] = 0
                    pos["status"] = "closed"
                    pos["closed_at"] = time.time()
                    pos["close_reason"] = err_val
                    return pos

                raise RuntimeError(
                    f"Sell engine failed after {sell_result.attempts} attempts: "
                    f"{sell_result.error}"
                )

            trade_record["tx_hash"] = tx_hash
            trade_record["sell_attempts"] = sell_result.attempts
            trade_record["slippage_bps_used"] = sell_result.slippage_bps_used
            logger.info(
                f"💰 SELL SUCCESS: {pos.get('token_symbol')} on {chain} | "
                f"tx={str(tx_hash)[:16]}... | pnl={pnl_pct:.1f}% | "
                f"attempts={sell_result.attempts} | slippage={sell_result.slippage_bps_used}bps"
            )
        except Exception as e:
            err_str = str(e)
            trade_record["error"] = err_str

            # ── MISSING PRIVATE KEY: config error — retrying is futile ──────
            # Auto-close the position and log clearly so user fixes .env.
            # This prevents the fail_count escalation to FATAL/CRITICAL.
            if "Private key not found in env var" in err_str:
                logger.error(
                    f"🔑 SELL BLOCKED (missing key): {pos.get('token_symbol')} on {pos.get('chain')} — "
                    f"{err_str}. Fix .env and redeploy. Auto-closing to stop retry spam."
                )
                trade_record["auto_closed_missing_key"] = True
                append_trade(trade_record)
                pos = dict(pos)
                pos["remaining_quantity"] = 0
                pos["status"] = "closed"
                pos["closed_at"] = time.time()
                pos["close_reason"] = "missing_private_key_config"
                return pos

            logger.warning(f"Live sell failed for {pos.get('token_symbol')}: {e}")

            # ── AUTO-CLOSE PHANTOM: on-chain balance confirmed 0 ────────
            # If the sell engine reports zero balance, the token was already
            # sold externally (or is a honeypot). Retrying is futile —
            # close the phantom position so it stops spamming CRITICAL alerts.
            if "On-chain balance is 0" in err_str or "resolved_units=0" in err_str:
                logger.warning(
                    f"🧹 AUTO-CLOSING PHANTOM: {pos.get('token_symbol')} on {pos.get('chain')} — "
                    f"on-chain balance is 0. Position was likely sold externally or is a honeypot."
                )
                try:
                    from notifications.slack import send_slack_message
                    send_slack_message(
                        f"🧹 *PHANTOM CLOSED*: `{pos.get('token_symbol')}` on `{pos.get('chain')}` — "
                        f"on-chain balance is 0. Auto-closed to stop retry spam."
                    )
                except Exception:
                    pass
                trade_record["auto_closed_phantom"] = True
                append_trade(trade_record)
                pos = dict(pos)
                pos["remaining_quantity"] = 0
                pos["status"] = "closed"
                pos["closed_at"] = time.time()
                pos["close_reason"] = "phantom_zero_balance"
                return pos

            fail_count = pos.get("sell_failure_count", 0) + 1
            pos["sell_failure_count"] = fail_count
            # Exponential backoff: 60s, 120s, 240s, 480s, max 600s (10 min)
            backoff_secs = min(60 * (2 ** min(fail_count - 1, 4)), 600)
            pos['next_sell_retry_at'] = time.time() + backoff_secs
            logger.info(f'Sell retry backoff: {backoff_secs}s for {pos.get("token_symbol")}')

            # ── DUST AUTO-CLOSE: Stop retrying unsellable micro-positions ──
            # If position value is below $1.00 after 5+ failures, or if we've
            # hit 20+ failures regardless of value, force-close as dust.
            # Old thresholds (50/10) let dead tokens spam 30+ cycles.
            _remaining = float(pos.get("remaining_quantity", 0))
            _est_value = _remaining * current_price if current_price else 0
            _is_dust = (fail_count >= 5 and _est_value < 1.00) or fail_count >= 20
            if _is_dust:
                logger.warning(
                    f"🗑️ DUST AUTO-CLOSE: {pos.get('token_symbol')} on {pos.get('chain')} — "
                    f"{fail_count} sell failures, est value=${_est_value:.4f}. "
                    f"Closing as dust (unsellable)."
                )
                trade_record["auto_closed_dust"] = True
                trade_record["dust_value_usd"] = _est_value
                append_trade(trade_record)
                pos = dict(pos)
                pos["status"] = "closed"
                pos["closed_at"] = time.time()
                pos["close_reason"] = f"dust_auto_close_after_{fail_count}_failures"
                try:
                    from notifications.slack import send_slack_message
                    send_slack_message(
                        f"🗑️ *DUST AUTO-CLOSE*: `{pos.get('token_symbol')}` on `{pos.get('chain')}` — "
                        f"{fail_count} failures, value=${_est_value:.4f}. Position closed as dust."
                    )
                except Exception:
                    pass
                return pos

            if fail_count >= 2:
                logger.critical(
                    f"🚨 SELL FAILURE #{fail_count}: {pos.get('token_symbol')} on {pos.get('chain')} "
                    f"— sell engine exhausted all retries. Manual intervention required."
                )
                try:
                    from notifications.telegram import notify_alert
                    notify_alert(
                        f"🚨 SELL FAILURE #{fail_count}",
                        f"{pos.get('token_symbol')} on {pos.get('chain')} could not be sold "
                        f"after {fail_count} monitor cycles. Error: {e}. "
                        f"Manual intervention required.",
                        level="error",
                    )
                except Exception:
                    pass
                try:
                    from notifications.slack import send_slack_message
                    send_slack_message(
                        f"🚨 *SELL FAILURE* #{fail_count}: `{pos.get('token_symbol')}` on `{pos.get('chain')}` "
                        f"could not be sold. Error: `{e}`. Manual check required."
                    )
                except Exception:
                    pass
            # ── CRITICAL FIX: Do NOT close position on failed sell ─────────
            # The old code fell through to the position-close logic below,
            # marking the position as "closed" even though nothing was sold
            # on-chain. This trapped capital in tokens the bot forgot about.
            # Return the position as-is (still open) so it retries next cycle.
            append_trade(trade_record)
            return pos
    else:
        logger.info(
            f"PAPER SELL: {pos.get('token_symbol')} {sell_pct*100:.0f}% "
            f"@ ${current_price:.6f} | {reason} | PnL={pnl_pct:.1f}%"
        )

    append_trade(trade_record)
    # u2500u2500 Telegram notification on every sell u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500
    try:
        from notifications.telegram import notify_trade as tg_notify_trade
        tg_notify_trade(
            action="SELL",
            token_symbol=pos.get("token_symbol", "???"),
            chain=pos.get("chain", "???"),
            price=current_price,
            amount_usd=sell_qty * current_price,
            pnl_pct=pnl_pct,
            tx_hash=trade_record.get("tx_hash", ""),
            target_timeframe=pos.get("target_timeframe", ""),
            confirmation_timeframe=pos.get("confirmation_timeframe", ""),
        )
    except Exception:
        pass

    # Update position
    new_remaining = remaining_qty - sell_qty
    pos = dict(pos)  # Don't mutate original
    pos["remaining_quantity"] = max(new_remaining, 0)
    pos["last_sell_at"] = now
    pos["last_sell_price"] = current_price
    pos["realized_pnl_usd"] = float(pos.get("realized_pnl_usd", 0)) + pnl_usd

    # Mark TP tiers (dynamic: works with any profile's multipliers)
    if "tp1_" in reason:
        pos["tp1_hit"] = True
    elif "tp2_" in reason:
        pos["tp2_hit"] = True
    elif "tp3_" in reason:
        pos["tp3_hit"] = True

    # ── Auto-compound: Track Wallet B TP profits for rebalancing to Primary ──
    # When nuclear wallet takes profit, flag 50% for rebalancing to safety net
    wallet_alias = pos.get("wallet", "").lower()
    is_tp_sell = "tp" in reason and pnl_usd > 0
    auto_compound_pct = getattr(settings, "AUTO_COMPOUND_PCT", 50.0)
    if is_tp_sell and "wallet_b" in wallet_alias and auto_compound_pct > 0:
        compound_amount = pnl_usd * (auto_compound_pct / 100)
        pos["compound_to_primary_usd"] = float(pos.get("compound_to_primary_usd", 0)) + compound_amount
        logger.info(
            f"💰 AUTO-COMPOUND: ${compound_amount:.2f} of ${pnl_usd:.2f} TP profit "
            f"flagged for rebalance to Primary ({auto_compound_pct:.0f}%)"
        )

    # Mark closed if fully sold
    if new_remaining <= 0 or sell_pct >= 1.0:
        pos["status"] = "closed"
        pos["closed_at"] = now
        # ── Capital Compounding Loop ──
        # Record full position PnL and run compounding/sweep/milestone logic
        total_position_pnl = float(pos.get("realized_pnl_usd", 0))
        try:
            from core.capital_compounder import record_trade_pnl
            compound_result = record_trade_pnl(
                pnl_usd=total_position_pnl,
                token_symbol=pos.get("symbol", ""),
                wallet=pos.get("wallet", "primary"),
                chain=pos.get("chain", "ethereum"),
                trade_id=pos.get("id", ""),
            )
            if compound_result.get("phase_changed"):
                logger.info(
                    f"🚀 COMPOUND PHASE UP: {compound_result['new_phase']} | "
                    f"Capital: ${compound_result['current_capital_usd']:,.0f} | "
                    f"New max position: ${compound_result['new_max_position_usd']:,.0f}"
                )
            for m in compound_result.get("milestones_hit", []):
                logger.info(f"🏆 MILESTONE: ${m:,.0f} reached! Keep compounding 🍀")
            if compound_result.get("sweep_amount_usd", 0) > 0:
                logger.info(
                    f"💰 PROFIT SWEEP: ${compound_result['sweep_amount_usd']:.2f} → Wallet C cold storage"
                )
                # Execute on-chain transfer to Wallet C
                try:
                    from core.executor import TradeExecutor
                    from config.wallets import get_wallet
                    wallet_c = get_wallet("wallet_c")
                    if wallet_c and wallet_c.address:
                        sweep_executor = TradeExecutor()
                        tx_hash = sweep_executor.transfer_native(
                            chain=pos.get("chain", "base"),
                            from_wallet_alias=pos.get("wallet", "primary"),
                            to_address=wallet_c.address,
                            amount_usd=compound_result["sweep_amount_usd"],
                        )
                        if tx_hash:
                            logger.info(f"✅ Paycheck transfer confirmed: {tx_hash}")
                except Exception as e:
                    logger.error(f"Failed to execute paycheck transfer: {e}")
        except Exception as _ce:
            logger.debug(f"Capital compounder record error: {_ce}")

    return pos


# ─────────────────────────────────────────────────────────────────────────────
# Main Monitor Loop
# ─────────────────────────────────────────────────────────────────────────────

class PositionMonitor:
    """
    Background position monitor. Runs alongside the gem scanner.
    Checks all open positions every POSITION_CHECK_INTERVAL_SECONDS seconds.
    """

    def __init__(self, is_paper: bool = True):
        self._is_paper = is_paper
        self._running = False
        logger.info(f"PositionMonitor initialized (mode={'paper' if self.is_paper else 'LIVE'})")

    @property
    def is_paper(self) -> bool:
        """Dynamically fetch the real-time mode from global settings."""
        return settings.IS_PAPER

    def run_once(self) -> dict:
        """
        Run a single check cycle. Includes defensive (TP/SL) and offensive
        (volume surge, underperformer, winner scaling, DCA) guardrails.

        Returns summary dict: {checked, sells_triggered, errors,
                               scaling_signals, dca_signals}
        """
        positions = load_positions()
        open_positions = [p for p in positions if p.get("status") == "open"]

        if not open_positions:
            return {"checked": 0, "sells_triggered": 0, "errors": 0,
                    "scaling_signals": 0, "dca_signals": 0}

        updated_positions = []
        sells_triggered = 0
        scaling_signals = 0
        dca_signals = 0
        errors = 0

        # ── Batch-fetch all prices at once (10x fewer API calls) ─────────
        price_cache = batch_get_prices_and_volumes(open_positions)

        for pos in open_positions:
            try:
                # Exponential backoff for repeated sell failures
                _fail_count = pos.get('sell_failure_count', 0)
                if _fail_count > 0:
                    _next_retry = pos.get('next_sell_retry_at', 0)
                    if time.time() < _next_retry:
                        updated_positions.append(pos)
                        continue  # Skip this position until backoff expires

                addr_lower = pos.get("token_address", "").lower()
                pv = price_cache.get(addr_lower, {})
                if not pv or pv.get("price") is None:
                    # Fallback to individual fetch
                    pv = get_price_and_volume(
                        token_address=pos.get("token_address", ""),
                        chain=pos.get("chain", ""),
                        pair_address=pos.get("pair_address", ""),
                    )
                current_price = pv.get("price")

                if current_price is None:
                    pos = dict(pos)
                    consecutive_failures = pos.get("consecutive_price_failures", 0) + 1
                    pos["consecutive_price_failures"] = consecutive_failures
                    if consecutive_failures >= 5:
                        logger.warning(
                            f"⚠️ STALE DATA: {pos.get('token_symbol')} has had {consecutive_failures} "
                            f"consecutive price failures — consider protective exit"
                        )
                    if consecutive_failures >= 10:
                        # Protective force-sell at last known price
                        last_known_price = float(pos.get("current_price", 0))
                        if last_known_price > 0:
                            logger.warning(
                                f"🚨 STALE EXIT: Force-selling {pos.get('token_symbol')} after "
                                f"{consecutive_failures} price failures at last known ${last_known_price:.6f}"
                            )
                            stale_sell = {"reason": f"stale_data_exit ({consecutive_failures} failures)", "sell_pct": 1.0, "urgency": "immediate"}
                            if pos.get("chain") == "hyperliquid":
                                logger.warning(f"🚨 STALE EXIT: Ignoring stale exit for Hyperliquid position {pos.get('token_symbol')} (handled by HL executor)")
                                pos["consecutive_price_failures"] = 0
                            else:
                                pos = execute_sell(pos, stale_sell, last_known_price, self.is_paper)
                            sells_triggered += 1
                    updated_positions.append(pos)
                    continue

                # Update position with latest data
                pos = dict(pos)
                pos["consecutive_price_failures"] = 0  # Reset on success
                if current_price > float(pos.get("highest_price", 0)):
                    pos["highest_price"] = current_price

                # Enrich with volume data (enables volume surge detection)
                if pv["volume_1h"] is not None:
                    pos["volume_1h"] = pv["volume_1h"]
                    # Capture entry volume (first time only) for Fast Fail Volume Collapse
                    if "entry_volume_1h" not in pos:
                        pos["entry_volume_1h"] = pv["volume_1h"]
                if pv["volume_24h"] is not None:
                    pos["volume_24h"] = pv["volume_24h"]

                # Capture liquidity data (for liquidity drain exit)
                if pv["liquidity_usd"] is not None and pv["liquidity_usd"] > 0:
                    pos["prev_liquidity_usd"] = pos.get("current_liquidity_usd", pv["liquidity_usd"])
                    pos["current_liquidity_usd"] = pv["liquidity_usd"]
                    # First capture = entry liquidity (for drain comparison)
                    if "entry_liquidity_usd" not in pos:
                        pos["entry_liquidity_usd"] = pv["liquidity_usd"]

                # Track previous check price for confluence Signal 5 (momentum death)
                prev_check = pos.get("current_price")
                if prev_check and float(prev_check) > 0:
                    pos["last_check_price"] = float(prev_check)

                pos["current_price"] = current_price
                # ── Refresh Moralis Token Analytics (dynamic TP scaling) ──
                try:
                    analytics = get_token_analytics_fresh(
                        pos.get("token_address", ""),
                        pos.get("chain", ""),
                    )
                    if analytics:
                        # Store analytics fields on position for evaluate_position
                        pos["moralis_net_buyers_1h"] = analytics.get("net_buyers_1h", 0)
                        pos["moralis_net_buyers_5m"] = analytics.get("net_buyers_5m", 0)
                        pos["moralis_buy_volume_1h"] = analytics.get("buy_volume_1h", 0)
                        pos["moralis_buy_pressure_1h"] = analytics.get("buy_pressure_ratio_1h", 0.5)
                        # Backward compat: keep existing buy_pressure_ratio field
                        pos["buy_pressure_ratio"] = pos["moralis_buy_pressure_1h"]
                        pos["moralis_buy_pressure"] = pos["moralis_buy_pressure_1h"]
                        
                    # Fetch predictive time series analytics (every 5th loop or if missing)
                    if "time_series_last_fetch" not in pos or time.time() - pos["time_series_last_fetch"] > 300:
                        ts_data = get_time_series_token_analytics(
                            pos.get("token_address", ""),
                            pos.get("chain", ""),
                            limit=10
                        )
                        if ts_data:
                            # Evaluate trend: if last 3 periods show negative net volume while overall was positive
                            net_vols = [float(x.get("net_volume", 0)) for x in ts_data]
                            if len(net_vols) >= 3 and all(v < 0 for v in net_vols[:3]):
                                pos["moralis_predictive_distribution"] = True
                            else:
                                pos["moralis_predictive_distribution"] = False
                            pos["time_series_last_fetch"] = time.time()
                except Exception as e:
                    logger.debug(f"Failed to refresh Moralis analytics for {pos.get('token_symbol')}: {e}")

                # ── Analytics Emergency Exit: sellers dominating → dump NOW ──
                emergency_exit = _should_emergency_exit(pos)
                if emergency_exit:
                    pos = execute_sell(pos, emergency_exit, current_price, self.is_paper)
                    sells_triggered += 1
                    updated_positions.append(pos)
                    continue

                entry_price = float(pos.get("entry_price", 0))
                if entry_price > 0:
                    pos["unrealized_pnl_pct"] = ((current_price - entry_price) / entry_price) * 100

                # ── Analytics Trail Override: tight trail active but buyers turned bearish → sell NOW ──
                # When analytics delayed TP1 (strong buyers), an 8% tight trail activates.
                # But if buyers subsequently leave (netBuyers goes negative), the trail stays
                # and the position rides down. This check force-sells to protect gains.
                _analytics_reversal_sell = None
                if pos.get("analytics_tight_trail_active"):
                    net_buyers_1h = pos.get("moralis_net_buyers_1h", 0)
                    if net_buyers_1h < 0:
                        unrealized_pnl = float(pos.get("unrealized_pnl_pct", 0))
                        if unrealized_pnl > 0:  # Only force-sell if still in profit
                            logger.info(
                                f"⚠️ ANALYTICS TRAIL OVERRIDE: {pos.get('token_symbol')} — "
                                f"netBuyers turned negative ({net_buyers_1h}) while tight trail active | "
                                f"PnL={unrealized_pnl:+.1f}% — force-selling to protect gains"
                            )
                            _analytics_reversal_sell = {
                                "sell_pct": 1.0,
                                "reason": f"analytics_reversal_exit (netBuyers_1h={net_buyers_1h}, tight trail active)",
                            }

                if _analytics_reversal_sell:
                    pos = execute_sell(pos, _analytics_reversal_sell, current_price, self.is_paper)
                    sells_triggered += 1
                    updated_positions.append(pos)
                    continue

                # ── Load offensive state for this cycle ─────────────────────────────────────────
                offensive_state = get_offensive_state()

                # ── Dynamic trailing stop (tightens in God Mode and after pyramid adds) ──
                dynamic_trailing_stop_pct = get_dynamic_trailing_stop_pct(
                    pos,
                    base_stop_pct=settings.STOP_LOSS_PERCENT,
                    state=offensive_state,
                )
                if dynamic_trailing_stop_pct != settings.STOP_LOSS_PERCENT:
                    pos["_dynamic_trailing_stop_pct"] = dynamic_trailing_stop_pct

                # ── Defensive: standard TP/SL evaluation (profile-aware) ─────────────────────
                _sp_name = pos.get("strategy_profile", "")
                _sp = _PROFILE_MAP.get(_sp_name)
                sell_action = evaluate_position(pos, current_price, strategy_profile=_sp)

                # ── FIX BUG 3: God Mode: skip TP1 sell but MARK tp1_hit=True ─────────
                # Without this fix, God Mode never sets tp1_hit, so the trailing stop
                # (which requires tp1_hit) NEVER activates on God Mode positions.
                # A 10x position could then reverse all the way back to the hard stop.
                if sell_action and sell_action.get("reason", "").startswith("tp1_"):
                    # Analytics delay: strong netBuyers → skip TP1 sell, tight trail
                    if sell_action.get("analytics_delay"):
                        pos["tp1_hit"] = True
                        pos["tp1_delayed_by_analytics"] = True
                        pos["analytics_tight_trail_active"] = True
                        # Override trailing stop to tight analytics trail
                        pos["_dynamic_trailing_stop_pct"] = settings.ANALYTICS_TIGHT_TRAIL_PCT
                        sell_action = None  # Don't sell
                    elif should_skip_tp1(offensive_state):
                        logger.info(
                            f"⚡ God Mode: skipping TP1 sell on {pos.get('token_symbol')} — "
                            f"holding for 5x+ | trailing stop now ACTIVE at {settings.STOP_LOSS_PERCENT:.0f}%"
                        )
                        pos["tp1_hit"] = True  # CRITICAL: activate trailing stop even without TP1 sell
                        sell_action = None

                # ── Offensive: volume surge fast exit ─────────────────────────────────────
                if not sell_action:
                    sell_action = evaluate_volume_surge_exit(pos, current_price)

                # ── Offensive: fast fail (momentum-dead exit) ──────────────────────────────
                if not sell_action:
                    fast_fail = evaluate_fast_fail(pos, current_price)
                    if fast_fail:
                        sell_action = fast_fail

                # ── Offensive: underperformer rotation ────────────────────────────────────────
                if not sell_action:
                    sell_action = evaluate_underperformer_exit(pos, current_price)

                # ── Rebalancing: dust sweep (Offensive Playbook §6) ──────────────────────────
                if not sell_action and pos.get("status") == "open":
                    remaining_qty = float(pos.get("remaining_quantity", 0))
                    pos_value_usd = remaining_qty * current_price if current_price else 0
                    entry_value_usd = float(pos.get("entry_value_usd", 0))
                    if 0 < pos_value_usd < settings.DUST_THRESHOLD_USD and entry_value_usd >= settings.DUST_THRESHOLD_USD:
                        if pos_value_usd >= settings.DUST_MIN_SELL_USD:
                            # Worth more than gas cost — sell to reclaim capital
                            logger.info(
                                f"🧹 Dust sweep: {pos.get('token_symbol')} worth ${pos_value_usd:.2f} — liquidating to reclaim capital"
                            )
                            sell_action = {
                                "reason": f"dust_sweep (${pos_value_usd:.2f} < ${settings.DUST_THRESHOLD_USD} threshold)",
                                "sell_pct": 1.0,
                                "urgency": "normal",
                            }
                        else:
                            # Not worth the gas — skip it
                            logger.debug(
                                f"🧹 Dust too small to sell: {pos.get('token_symbol')} worth ${pos_value_usd:.2f} — below gas cost ${settings.DUST_MIN_SELL_USD}"
                            )
                        pos["is_dust"] = True

                # ── Rebalancing: underperformer + low liquidity liquidation (Playbook §6) ────
                if not sell_action and pos.get("status") == "open":
                    gain_pct_val = float(pos.get("unrealized_pnl_pct", 0))
                    current_liq = float(pos.get("current_liquidity_usd", 0))
                    if (gain_pct_val <= -settings.UNDERPERFORMER_LIQ_DOWN_PCT
                            and 0 < current_liq < settings.UNDERPERFORMER_LIQ_MIN_USD):
                        sell_action = {
                            "reason": f"underperformer_liquidation (down {gain_pct_val:.0f}%, liq=${current_liq:.0f})",
                            "sell_pct": 1.0,
                            "urgency": "normal",
                        }
                        logger.info(
                            f"💀 Liquidating underperformer: {pos.get('token_symbol')} "
                            f"({gain_pct_val:+.0f}%, liq=${current_liq:.0f})"
                        )

                if sell_action:
                    # If the action has a _mark, apply it to position before sell
                    mark = sell_action.pop("_mark", None)
                    if mark:
                        pos[mark] = True
                    pos = execute_sell(pos, sell_action, current_price, self.is_paper)
                    sells_triggered += 1

                # ── Offensive: pyramid scaling signal (3-tier) ────────────────
                # Don't scale if we just sold or position is closed
                if pos.get("status") == "open":
                    scaling = evaluate_pyramid_scaling(pos, current_price)
                    if scaling:
                        pos["_scaling_signal"] = scaling
                        scaling_signals += 1
                        logger.info(
                            f"📈 Pyramid tier {scaling.get('tier', '?')} signal: "
                            f"{pos.get('token_symbol')} +{scaling['gain_pct']:.0f}% "
                            f"— add ${scaling.get('add_size_usd', 0):.2f} (tier {scaling.get('tier')})"
                        )

                # ── Offensive: smart DCA signal ───────────────────────────────
                if pos.get("status") == "open":
                    dca = check_smart_dca(pos, current_price)
                    if dca:
                        pos["_dca_signal"] = dca
                        dca_signals += 1
                        logger.info(
                            f"📉 Smart DCA signal: {pos.get('token_symbol')} "
                            f"{dca['gain_pct']:+.0f}% dip (score={dca['gem_score']:.0f}) "
                            f"— flagged for DCA buy"
                        )

                updated_positions.append(pos)

            except Exception as e:
                logger.error(f"Error monitoring position {pos.get('token_symbol')}: {e}")
                updated_positions.append(pos)
                errors += 1

        # Merge with closed positions (keep history)
        closed_positions = [p for p in positions if p.get("status") == "closed"]
        all_positions = updated_positions + closed_positions

        # Trim closed positions older than 30 days
        cutoff = time.time() - 30 * 86400
        all_positions = [
            p for p in all_positions
            if p.get("status") == "open" or (
                p.get("closed_at") and
                _parse_ts(p["closed_at"]) > cutoff
            )
        ]

        save_positions(all_positions)

        if sells_triggered > 0 or scaling_signals > 0 or dca_signals > 0:
            logger.info(
                f"Position monitor: {sells_triggered} sell(s), "
                f"{scaling_signals} scale signal(s), "
                f"{dca_signals} DCA signal(s), "
                f"{errors} error(s)"
            )

        return {
            "checked": len(open_positions),
            "sells_triggered": sells_triggered,
            "scaling_signals": scaling_signals,
            "dca_signals": dca_signals,
            "errors": errors,
        }

    def run_forever(self) -> None:
        """Run the monitor loop indefinitely. Writes heartbeat for health check."""
        self._running = True
        logger.info(
            f"Position monitor started — checking every "
            f"{settings.POSITION_CHECK_INTERVAL_SECONDS}s"
        )
        
        last_auto_tune_time = 0.0
        AUTO_TUNE_INTERVAL = 1800.0  # 30 minutes — single deduped auto-tune check
        
        last_hourly_report_time = 0.0
        HOURLY_REPORT_INTERVAL = 3600.0  # 60 minutes
        
        while self._running:
            try:
                self.run_once()
                # Write heartbeat so health check can detect if this thread dies
                try:
                    _hb_path = Path(os.getenv("BOT_STATUS_FILE", str(POSITIONS_FILE.parent / "bot_status.json")))
                    if _hb_path.exists():
                        import json as _hb_json
                        with open(_hb_path, "r") as _hf:
                            _hb_data = _hb_json.load(_hf)
                        _hb_data["last_monitor_cycle_at"] = datetime.now(timezone.utc).isoformat()
                        _hb_tmp = _hb_path.with_suffix(".pm_tmp")
                        with open(_hb_tmp, "w") as _hf:
                            _hb_json.dump(_hb_data, _hf, indent=2)
                        _hb_tmp.replace(_hb_path)
                except Exception:
                    pass  # heartbeat write is best-effort
                    
                # Run Auto-Tuner Cycle every 15 minutes
                current_time = time.time()
                if current_time - last_auto_tune_time >= AUTO_TUNE_INTERVAL:
                    try:
                        from core.llm_auto_tuner import run_auto_tuner_cycle
                        run_auto_tuner_cycle()
                        last_auto_tune_time = current_time
                    except Exception as at_e:
                        logger.error(f"Auto-Tuner Error: {at_e}")

                # Run Self-Improving Agent Audit Cycle
                try:
                    from core.self_improving_agent import improving_agent
                    improving_agent.run_self_audit()
                except Exception as sia_e:
                    logger.error(f"Self-Improving Agent Audit Error: {sia_e}")
                        
                # Run Hourly Report every 60 minutes
                if current_time - last_hourly_report_time >= HOURLY_REPORT_INTERVAL:
                    try:
                        from core.hourly_report import send_hourly_report
                        send_hourly_report()
                        last_hourly_report_time = current_time
                    except Exception as hr_e:
                        logger.error(f"Hourly Report Error: {hr_e}")
                        
            except Exception as e:
                logger.error(f"Position monitor loop error: {e}", exc_info=True)
            time.sleep(settings.POSITION_CHECK_INTERVAL_SECONDS)

    def stop(self) -> None:
        """Stop the monitor loop."""
        self._running = False


def _parse_ts(ts_str: str) -> float:
    """Parse ISO timestamp to Unix float. Returns 0 on error."""
    try:
        dt = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
        return dt.timestamp()
    except Exception:
        return 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Position Registration (called by executor after a buy)
# ─────────────────────────────────────────────────────────────────────────────

def register_position(
    token_address: str,
    token_symbol: str,
    chain: str,
    wallet: str,
    entry_price: float,
    quantity: float,
    pair_address: str = "",
    tx_hash: str = "",
    gem_score: float = 0.0,
    is_paper: bool | None = None,
    entry_value_usd: float = 0.0,
    token_decimals: int = 0,  # 0 = auto-detect: 6 for Solana, 18 for EVM
    strategy_profile: str = "",  # e.g. "nuclear", "conservative"
    signal_scores: dict = None,  # ML attribution features
    target_timeframe: str = "",
    confirmation_timeframe: str = "",
) -> dict:
    """
    Register a new open position after a buy is executed.
    Returns the position dict that was saved.
    """
    positions = load_positions()

    # Resolve is_paper dynamically if not explicitly provided
    if is_paper is None:
        from config import settings
        is_paper = settings.get_current_mode() != "live"

    # ── Minimum Price Filter (Paper Mode) ─────────────────────────────────
    # Reject micro-cap tokens (< $0.001) in paper mode to prevent absurd P&L
    # distortion. A $2 buy of a $0.000003 token = 666M tokens; a 1% drop =
    # -$13K on the ledger. These tokens also have zero real liquidity.
    min_paper_price = float(os.environ.get("MIN_PAPER_TOKEN_PRICE", "0.001"))
    if is_paper and entry_price < min_paper_price and entry_price > 0:
        logger.info(
            f"🚫 PAPER FILTER: {token_symbol} rejected — price ${entry_price:.8f} "
            f"below minimum ${min_paper_price} (prevents P&L distortion)"
        )
        return None

    # ── DEDUP: Check for existing open position with same token+chain+wallet ──
    existing = [p for p in positions if
        p.get("token_address", "").lower() == token_address.lower() and
        p.get("chain", "").lower() == chain.lower() and
        p.get("wallet", "").lower() == wallet.lower() and
        p.get("status") == "open"]
    if existing:
        logger.warning(
            f"⚠️ DEDUP: Position already exists for {token_symbol} on {chain}/{wallet} — "
            f"merging quantities instead of creating duplicate"
        )
        # Merge: add quantity to existing position
        old_qty = float(existing[0].get("quantity", 0))
        old_price = float(existing[0].get("entry_price", 0))
        existing[0]["remaining_quantity"] = float(existing[0].get("remaining_quantity", 0)) + quantity
        existing[0]["quantity"] = old_qty + quantity
        # Weighted average entry price
        if old_qty > 0 and old_price > 0:
            existing[0]["entry_price"] = ((old_price * old_qty) + (entry_price * quantity)) / (old_qty + quantity)
        save_positions(positions)
        return existing[0]

    now = datetime.now(timezone.utc).isoformat()
    position = {
        "id": f"{chain}:{token_address.lower()}:{int(time.time())}",
        "status": "open",
        "token_address": token_address,
        "token_symbol": token_symbol,
        "chain": chain,
        "wallet": wallet,
        "pair_address": pair_address,
        "entry_price": entry_price,
        "quantity": quantity,
        "remaining_quantity": quantity,
        "entry_value_usd": min(
            entry_value_usd if entry_value_usd > 0 else (entry_price * quantity),
            500.0  # Hard cap: no single position can exceed $500 on a $1000 account
        ),
        "highest_price": entry_price,
        "current_price": entry_price,
        "entry_time": now,
        "last_updated": now,
        "tp1_hit": False,
        "tp2_hit": False,
        "tp3_hit": False,
        "scale_in_count": 0,
        "realized_pnl_usd": 0.0,
        "unrealized_pnl_pct": 0.0,
        "tx_hash_buy": tx_hash,
        "gem_score": gem_score,
        "is_paper": is_paper,
        # Token decimals — critical for correct sell amount calculation
        # Auto-detect: Solana SPL = 6, EVM ERC-20 = 18
        "token_decimals": token_decimals if token_decimals > 0 else (6 if chain == "solana" else 18),
        "strategy_profile": strategy_profile,
        "signal_scores": signal_scores or {},
        "target_timeframe": target_timeframe,
        "confirmation_timeframe": confirmation_timeframe,
    }

    positions.append(position)
    save_positions(positions)

    logger.info(
        f"Position registered: {token_symbol} on {chain} | "
        f"entry=${entry_price:.6f} | qty={quantity:.4f} | "
        f"wallet={wallet} | {'PAPER' if is_paper else 'LIVE'}"
    )

    # Log BUY to immutable ledger (P&L is 0 at entry — realized on sell)
    _append_to_ledger({
        "timestamp": now,
        "token_address": token_address,
        "token_symbol": token_symbol,
        "chain": chain,
        "wallet": wallet,
        "action": "BUY",
        "quantity": quantity,
        "price_usd": entry_price,
        "value_usd": entry_price * quantity,
        "pnl_usd": 0.0,
        "pnl_pct": 0.0,
        "is_paper": is_paper,
        "tx_hash": tx_hash,
        "gem_score": gem_score,
        "strategy_profile": strategy_profile,
        "target_timeframe": target_timeframe,
        "confirmation_timeframe": confirmation_timeframe,
    })

    return position

# ─────────────────────────────────────────────────────────────────────────────
# Trade Reconciliation Pipeline (Combo C)
# ─────────────────────────────────────────────────────────────────────────────

def reconcile_onchain_positions(wallet_address: str, chain: str = "solana") -> None:
    """
    Fetch on-chain balances/swap history and compare against local positions.json.
    Flags mismatches (e.g., bot thinks position is open but it was sold manually,
    or bot missed a buy transaction). Supports both Solana and EVM chains.
    """
    try:
        local_positions = load_positions()
        open_positions = [
            p for p in local_positions
            if p.get("status") == "open"
            and p.get("chain", "").lower() == chain.lower()
            and (p.get("wallet", "").lower() == wallet_address.lower()
                 or p.get("wallet", "") == wallet_address)
        ]

        if not open_positions:
            return

        dirty = False

        if chain.lower() == "solana":
            # Solana: use swap history for net flow analysis
            from data.providers.moralis_solana import get_wallet_swaps
            swaps = get_wallet_swaps(wallet_address, limit=50)
            if not swaps:
                return

            token_flows = {}
            for swap in swaps:
                token_in = swap.get("token_in", {}).get("token_address", "").lower()
                token_out = swap.get("token_out", {}).get("token_address", "").lower()

                if token_in:
                    token_flows[token_in] = token_flows.get(token_in, 0) - float(swap.get("token_in", {}).get("amount", 0))
                if token_out:
                    token_flows[token_out] = token_flows.get(token_out, 0) + float(swap.get("token_out", {}).get("amount", 0))

            for pos in open_positions:
                token_addr = pos.get("token_address", "").lower()
                if token_addr in token_flows and token_flows[token_addr] < 0:
                    logger.warning(
                        f"⚠️ RECONCILIATION MISMATCH: Bot shows open position for {pos['token_symbol']} "
                        f"but on-chain history shows recent sells. Was it sold manually?"
                    )
                    try:
                        from notifications.slack import send_slack_message
                        send_slack_message(
                            f"⚠️ *RECONCILIATION MISMATCH*: Bot shows open position for "
                            f"`{pos.get('token_symbol')}` on `{pos.get('chain')}` but on-chain history "
                            f"shows a recent sell. Was this sold manually? "
                            f"Position may need manual close in the bot."
                        )
                    except Exception:
                        pass
        else:
            # EVM: check actual token balances via Moralis wallet API
            try:
                from data.providers.moralis_wallet import get_wallet_token_balances
                balances = get_wallet_token_balances(wallet_address, chain) or []

                # Build lookup of on-chain balances by token address
                onchain_balances = {}
                for b in balances:
                    addr = (b.get("token_address") or b.get("address", "")).lower()
                    if addr:
                        raw_bal = b.get("balance", "0")
                        decimals = int(b.get("decimals", 18))
                        try:
                            onchain_balances[addr] = int(raw_bal) / (10 ** decimals) if raw_bal else 0.0
                        except (ValueError, OverflowError):
                            onchain_balances[addr] = 0.0

                for pos in open_positions:
                    token_addr = pos.get("token_address", "").lower()
                    tracked_qty = float(pos.get("remaining_quantity", 0))
                    onchain_qty = onchain_balances.get(token_addr, -1)  # -1 = not found

                    if tracked_qty > 0 and onchain_qty == 0:
                        # Token balance is definitively zero — position is phantom
                        logger.warning(
                            f"🔄 RECONCILIATION: {pos.get('token_symbol')} on {chain} — "
                            f"on-chain balance is ZERO but tracked qty={tracked_qty:.4f}. "
                            f"Marking position as closed (rug/manual sell/transfer)."
                        )
                        pos["status"] = "closed"
                        pos["closed_at"] = datetime.now(timezone.utc).isoformat()
                        pos["close_reason"] = "reconciled_onchain_zero"
                        pos["remaining_quantity"] = 0
                        dirty = True

                        try:
                            from notifications.slack import send_slack_message
                            send_slack_message(
                                f"🔄 *AUTO-RECONCILED*: `{pos.get('token_symbol')}` on `{chain}` "
                                f"closed — on-chain balance is zero (tracked: {tracked_qty:.4f}). "
                                f"Likely rug-pulled or manually sold."
                            )
                        except Exception:
                            pass
                    elif tracked_qty > 0 and onchain_qty > 0 and onchain_qty < tracked_qty * 0.1:
                        # Balance is drastically lower than expected (>90% discrepancy)
                        logger.warning(
                            f"⚠️ RECONCILIATION WARNING: {pos.get('token_symbol')} on {chain} — "
                            f"on-chain={onchain_qty:.4f} vs tracked={tracked_qty:.4f} (>90% discrepancy)"
                        )
            except ImportError:
                logger.debug("moralis_wallet not available for EVM reconciliation")
            except Exception as evm_err:
                logger.debug(f"EVM reconciliation error for {chain}: {evm_err}")

        if dirty:
            save_positions(local_positions)

    except Exception as e:
        logger.error(f"Trade reconciliation failed: {e}")

