"""
core/position_monitor.py — Auto-sell, take-profit, and trailing stop monitor.

Runs as a background loop alongside the gem scanner. Every 30 seconds it:
  1. Loads all open positions from positions.json
  2. Fetches current price for each position via DexScreener
  3. Evaluates take-profit tiers, trailing stop, and hard stop-loss
  4. Executes sells when thresholds are hit
  5. Persists updated positions back to disk

Take-Profit Strategy (Alex Becker playbook):
  - TP1 at 2x (100% gain): Sell 40% of position → lock in initial capital + profit
  - TP2 at 5x (400% gain): Sell 35% more → ride the rest with house money
  - TP3 at 10x (900% gain): Sell 20% → let 5% ride to potential 100x
  - Trailing stop after TP1: 20% below highest price seen
  - Hard stop-loss: 25% below entry (configurable)
  - Time-based exit: if no 50% gain in 48h, exit to free capital

Position Persistence:
  - Positions saved to output/positions.json (JSON array)
  - Trades log appended to output/trades.json
  - Both files survive restarts — positions are reloaded on startup
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

from config import settings
from data.models import Position, Trade
from core.offensive_guardrails import (
    get_offensive_state,
    save_offensive_state,
    evaluate_pyramid_scaling,
    get_dynamic_trailing_stop_pct,
    evaluate_fast_fail,
    should_skip_tp1,
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# File paths
# ─────────────────────────────────────────────────────────────────────────────
POSITIONS_FILE = Path(settings.POSITIONS_FILE)
POSITIONS_BACKUP = POSITIONS_FILE.with_name("positions.backup.json")
TRADES_FILE = Path(settings.TRADES_FILE)
_save_counter = 0
POSITIONS_FILE.parent.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# Position Persistence
# ─────────────────────────────────────────────────────────────────────────────

def load_positions() -> list[dict]:
    """Load open positions from disk. Falls back to .tmp or .backup if main file is corrupt."""
    for filepath in [POSITIONS_FILE, POSITIONS_FILE.with_suffix(".tmp"), POSITIONS_BACKUP]:
        try:
            if filepath.exists():
                with open(filepath) as f:
                    data = json.load(f)
                    positions = data if isinstance(data, list) else []

                    if filepath != POSITIONS_FILE:
                        logger.warning(f"Loaded positions from fallback: {filepath}")
                        # Restore to main file
                        save_positions(positions)

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
                        save_positions(positions)
                        logger.info("Migrated positions: backfilled entry_value_usd / scale_in_count")

                    return positions
        except Exception as e:
            logger.error(f"Failed to load positions from {filepath}: {e}")
    return []


def save_positions(positions: list[dict]) -> None:
    """Persist open positions to disk (atomic write + periodic backup)."""
    global _save_counter
    try:
        tmp = POSITIONS_FILE.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(positions, f, indent=2, default=str)
        tmp.replace(POSITIONS_FILE)
        # Periodic backup every 100 saves
        _save_counter += 1
        if _save_counter % 100 == 0:
            import shutil
            shutil.copy2(POSITIONS_FILE, POSITIONS_BACKUP)
            logger.debug(f"Positions backup saved ({_save_counter} saves)")
    except Exception as e:
        logger.error(f"Failed to save positions: {e}")


def append_trade(trade: dict) -> None:
    """Append a completed trade to the trades log."""
    try:
        trades = []
        if TRADES_FILE.exists():
            with open(TRADES_FILE) as f:
                trades = json.load(f)
        trades.append(trade)
        # Keep last 10,000 trades
        if len(trades) > 10_000:
            trades = trades[-10_000:]
        with open(TRADES_FILE, "w") as f:
            json.dump(trades, f, indent=2, default=str)
    except Exception as e:
        logger.error(f"Failed to append trade: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Price Fetching
# ─────────────────────────────────────────────────────────────────────────────

def get_current_price(token_address: str, chain: str, pair_address: str = "") -> Optional[float]:
    """
    Fetch current price from DexScreener.
    Returns None if price unavailable.
    """
    try:
        if pair_address:
            url = f"https://api.dexscreener.com/latest/dex/pairs/{chain}/{pair_address}"
        else:
            url = f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"

        resp = requests.get(url, timeout=10)
        data = resp.json()
        pairs = data.get("pairs", [])
        if not pairs:
            return None

        # Use most liquid pair
        pairs.sort(key=lambda p: float(p.get("liquidity", {}).get("usd", 0) or 0), reverse=True)
        price_str = pairs[0].get("priceUsd")
        return float(price_str) if price_str else None

    except Exception as e:
        logger.debug(f"Price fetch failed for {token_address}: {e}")
        return None


def get_price_and_volume(token_address: str, chain: str, pair_address: str = "") -> dict:
    """
    Fetch current price, volume, AND liquidity data from DexScreener.
    Returns dict with price, volume_1h, volume_24h, liquidity_usd. All may be None.
    """
    result = {"price": None, "volume_1h": None, "volume_24h": None, "liquidity_usd": None}
    try:
        if pair_address:
            url = f"https://api.dexscreener.com/latest/dex/pairs/{chain}/{pair_address}"
        else:
            url = f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"

        resp = requests.get(url, timeout=10)
        data = resp.json()
        pairs = data.get("pairs", [])
        if not pairs:
            return result

        pairs.sort(key=lambda p: float(p.get("liquidity", {}).get("usd", 0) or 0), reverse=True)
        top = pairs[0]
        price_str = top.get("priceUsd")
        result["price"] = float(price_str) if price_str else None

        vol = top.get("volume", {})
        result["volume_1h"] = float(vol.get("h1", 0) or 0)
        result["volume_24h"] = float(vol.get("h24", 0) or 0)

        # Liquidity data (for liquidity drain exit)
        liq = top.get("liquidity", {})
        result["liquidity_usd"] = float(liq.get("usd", 0) or 0)

    except Exception as e:
        logger.debug(f"Price+volume fetch failed for {token_address}: {e}")

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
            resp = requests.get(url, timeout=15)
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
                pairs.sort(key=lambda p: float(p.get("liquidity", {}).get("usd", 0) or 0), reverse=True)
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
        hard_stop_pct = settings.HARD_STOP_LOSS_PERCENT
        trailing_pct = settings.STOP_LOSS_PERCENT
        tp1_mult = settings.TAKE_PROFIT_TP1_MULT
        tp1_sell = settings.TAKE_PROFIT_TP1_SELL_PCT
        tp2_mult = settings.TAKE_PROFIT_TP2_MULT
        tp2_sell = settings.TAKE_PROFIT_TP2_SELL_PCT
        tp3_mult = 0
        tp3_sell = 0
        trailing_tighten = {}
        profile_name = "default"

    gain_pct = ((current_price - entry_price) / entry_price) * 100
    gain_mult = current_price / entry_price  # 5.0 = 5x
    highest_price = float(pos.get("highest_price", entry_price))
    tp1_hit = pos.get("tp1_hit", False)
    tp2_hit = pos.get("tp2_hit", False)
    tp3_hit = pos.get("tp3_hit", False)
    entry_time = pos.get("entry_time")

    # ── Hard stop-loss ────────────────────────────────────────────────────────
    hard_stop = -hard_stop_pct
    if gain_pct <= hard_stop:
        return {
            "reason": f"hard_stop_loss ({gain_pct:.1f}%) [{profile_name}]",
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

        trailing_stop_price = highest_price * (1 - effective_trail / 100)
        if current_price <= trailing_stop_price:
            drop_from_high = ((current_price - highest_price) / highest_price) * 100
            return {
                "reason": f"trailing_stop ({drop_from_high:.1f}% from high, trail={effective_trail:.0f}%) [{profile_name}]",
                "sell_pct": 1.0,
                "urgency": "immediate",
            }

    # ── Take-profit tiers ─────────────────────────────────────────────────────
    # TP1
    tp1_gain = (tp1_mult - 1) * 100
    if not tp1_hit and gain_pct >= tp1_gain:
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

    # ── Time-based exit: dead capital is wasted capital ───────────────────────
    if entry_time and not tp1_hit:
        try:
            entry_dt = datetime.fromisoformat(str(entry_time).replace("Z", "+00:00"))
            age_hours = (datetime.now(timezone.utc) - entry_dt).total_seconds() / 3600
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
        entry_liq = float(pos.get("entry_liquidity_usd", 0))
        current_liq = float(pos.get("current_liquidity_usd", 0))
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
    }

    if not is_paper:
        # Live execution — delegate to executor (EVM or Solana)
        try:
            chain = pos.get("chain", "")
            if chain == "solana":
                from core.solana_executor import execute_solana_sell
                from config.wallets import WALLETS
                wallet_alias = pos.get("wallet", "primary")
                wallet = WALLETS.get(wallet_alias)
                sol_pub = wallet.solana_address if wallet else ""
                sol_key_env = wallet.solana_private_key_env if wallet else ""
                # Convert quantity to token units using stored decimals.
                # Solana SPL tokens are most commonly 6 decimals (USDC, most memes)
                # but some are 9 (SOL-native) or other values.
                # We store token_decimals at buy time; fall back to 6 if missing.
                sol_decimals = int(pos.get("token_decimals", 6))
                if sol_decimals not in (6, 9):  # Sanity check — only trust known-good values
                    logger.warning(
                        f"Unexpected Solana token decimals={sol_decimals} for "
                        f"{pos.get('token_symbol')} — defaulting to 6"
                    )
                    sol_decimals = 6
                token_amount_units = int(sell_qty * (10 ** sol_decimals))
                logger.info(
                    f"Solana sell: {sell_qty:.4f} tokens × 10^{sol_decimals} "
                    f"= {token_amount_units:,} units"
                )
                # Use urgency-based slippage: immediate exits get wider slippage
                sell_urgency = sell_action.get("urgency", "normal")
                sol_slippage = 500 if sell_urgency == "immediate" else 250
                tx_hash = execute_solana_sell(
                    token_mint=pos["token_address"],
                    token_amount=token_amount_units,
                    wallet_public_key=sol_pub,
                    wallet_private_key_env=sol_key_env,
                    slippage_bps=sol_slippage,
                    is_paper=False,
                )
            else:
                from core.executor import TradeExecutor, build_take_profit_params
                from config.wallets import WALLETS
                wallet_alias = pos.get("wallet", "primary")
                wallet = WALLETS.get(wallet_alias)
                if not wallet:
                    # Try matching by address or alias
                    for wk, wv in WALLETS.items():
                        if (wv.address.lower() == wallet_alias.lower()
                                or wv.alias.lower() == wallet_alias.lower()):
                            wallet = wv
                            break
                if not wallet:
                    raise ValueError(f"No wallet found for '{wallet_alias}'")
                # Convert sell_qty to token wei (use decimals from position or default 18)
                decimals = int(pos.get("token_decimals", 18))
                token_amount_wei = int(sell_qty * (10 ** decimals))
                params = build_take_profit_params(
                    wallet=wallet,
                    chain=chain,
                    token_address=pos["token_address"],
                    token_amount_wei=token_amount_wei,
                    slippage_bps=300,  # wider slippage for exits
                )
                sell_executor = TradeExecutor()
                result = sell_executor.execute_trade(params)
                tx_hash = result.tx_hash if result.success else None
                if not result.success:
                    raise RuntimeError(f"EVM sell failed: {result.error}")
            trade_record["tx_hash"] = tx_hash
            logger.info(
                f"LIVE SELL: {pos['token_symbol']} {sell_pct*100:.0f}% "
                f"@ ${current_price:.6f} | {reason} | tx={tx_hash}"
            )
        except Exception as e:
            logger.error(f"Live sell failed for {pos.get('token_symbol')}: {e}")
            trade_record["error"] = str(e)
    else:
        logger.info(
            f"PAPER SELL: {pos.get('token_symbol')} {sell_pct*100:.0f}% "
            f"@ ${current_price:.6f} | {reason} | PnL={pnl_pct:.1f}%"
        )

    append_trade(trade_record)

    # Update position
    new_remaining = remaining_qty - sell_qty
    pos = dict(pos)  # Don't mutate original
    pos["remaining_quantity"] = max(new_remaining, 0)
    pos["last_sell_at"] = now
    pos["last_sell_price"] = current_price
    pos["realized_pnl_usd"] = float(pos.get("realized_pnl_usd", 0)) + pnl_usd

    # Mark TP tiers
    if reason == "tp1_2x":
        pos["tp1_hit"] = True
    elif reason == "tp2_5x":
        pos["tp2_hit"] = True
    elif reason == "tp3_10x":
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
        self.is_paper = is_paper
        self._running = False
        logger.info(f"PositionMonitor initialized (mode={'paper' if is_paper else 'LIVE'})")

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
                    logger.debug(f"No price for {pos.get('token_symbol')} — skipping")
                    updated_positions.append(pos)
                    continue

                # Update position with latest data
                pos = dict(pos)
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
                    pos["current_liquidity_usd"] = pv["liquidity_usd"]
                    # First capture = entry liquidity (for drain comparison)
                    if "entry_liquidity_usd" not in pos:
                        pos["entry_liquidity_usd"] = pv["liquidity_usd"]

                pos["current_price"] = current_price
                entry_price = float(pos.get("entry_price", 0))
                if entry_price > 0:
                    pos["unrealized_pnl_pct"] = ((current_price - entry_price) / entry_price) * 100

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

                # ── Defensive: standard TP/SL evaluation ─────────────────────────────────────
                sell_action = evaluate_position(pos, current_price)

                # ── God Mode: skip TP1 (hold for higher target) ────────────────────────
                if sell_action and sell_action.get("reason", "").startswith("tp1_"):
                    if should_skip_tp1(offensive_state):
                        logger.info(
                            f"⚡ God Mode: skipping TP1 on {pos.get('token_symbol')} — holding for 5x+"
                        )
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
                    if 0 < pos_value_usd < settings.DUST_THRESHOLD_USD:
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
        """Run the monitor loop indefinitely."""
        self._running = True
        logger.info(
            f"Position monitor started — checking every "
            f"{settings.POSITION_CHECK_INTERVAL_SECONDS}s"
        )
        while self._running:
            try:
                self.run_once()
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
    is_paper: bool = True,
    entry_value_usd: float = 0.0,
    token_decimals: int = 0,  # 0 = auto-detect: 6 for Solana, 18 for EVM
    strategy_profile: str = "",  # e.g. "nuclear", "conservative"
) -> dict:
    """
    Register a new open position after a buy is executed.
    Returns the position dict that was saved.
    """
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
        "entry_value_usd": entry_value_usd if entry_value_usd > 0 else (entry_price * quantity),
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
    }

    positions = load_positions()
    positions.append(position)
    save_positions(positions)

    logger.info(
        f"Position registered: {token_symbol} on {chain} | "
        f"entry=${entry_price:.6f} | qty={quantity:.4f} | "
        f"wallet={wallet} | {'PAPER' if is_paper else 'LIVE'}"
    )
    return position

# ─────────────────────────────────────────────────────────────────────────────
# Trade Reconciliation Pipeline (Combo C)
# ─────────────────────────────────────────────────────────────────────────────

def reconcile_onchain_positions(wallet_address: str, chain: str = "solana") -> None:
    """
    Fetch on-chain swap history and compare against local positions.json.
    Flags mismatches (e.g., bot thinks position is open but it was sold manually,
    or bot missed a buy transaction).
    """
    if chain != "solana":
        logger.debug(f"Reconciliation currently only supports Solana. Skipped {chain}.")
        return
        
    try:
        from data.providers.moralis_solana import get_wallet_swaps
        swaps = get_wallet_swaps(wallet_address, limit=50)
        if not swaps:
            return
            
        local_positions = load_positions()
        open_positions = {p["token_address"].lower(): p for p in local_positions if p["status"] == "open" and p["chain"] == "solana"}
        
        # Build a map of net token changes from recent swaps
        token_flows = {}
        for swap in swaps:
            # Moralis swap format
            token_in = swap.get("token_in", {}).get("token_address", "").lower()
            token_out = swap.get("token_out", {}).get("token_address", "").lower()
            
            if token_in:
                token_flows[token_in] = token_flows.get(token_in, 0) - float(swap.get("token_in", {}).get("amount", 0))
            if token_out:
                token_flows[token_out] = token_flows.get(token_out, 0) + float(swap.get("token_out", {}).get("amount", 0))
                
        # Check for mismatches
        for token_addr, pos in open_positions.items():
            if token_addr in token_flows and token_flows[token_addr] < 0:
                # We have an open position, but on-chain shows a net sell recently
                logger.warning(
                    f"⚠️ RECONCILIATION MISMATCH: Bot shows open position for {pos['token_symbol']} "
                    f"but on-chain history shows recent sells. Was it sold manually?"
                )
                # TODO: Send Slack alert here
                
    except Exception as e:
        logger.error(f"Trade reconciliation failed: {e}")
