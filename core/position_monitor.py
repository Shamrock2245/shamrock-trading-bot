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
from data.models import Position, Trade, TradeAction

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# File paths
# ─────────────────────────────────────────────────────────────────────────────
POSITIONS_FILE = Path(settings.POSITIONS_FILE)
TRADES_FILE = Path(settings.TRADES_FILE)
POSITIONS_FILE.parent.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# Position Persistence
# ─────────────────────────────────────────────────────────────────────────────

def load_positions() -> list[dict]:
    """Load open positions from disk. Returns empty list if file missing."""
    try:
        if POSITIONS_FILE.exists():
            with open(POSITIONS_FILE) as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"Failed to load positions: {e}")
    return []


def save_positions(positions: list[dict]) -> None:
    """Persist open positions to disk (atomic write)."""
    try:
        tmp = POSITIONS_FILE.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(positions, f, indent=2, default=str)
        tmp.replace(POSITIONS_FILE)
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


# ─────────────────────────────────────────────────────────────────────────────
# Take-Profit / Stop-Loss Evaluation
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_position(pos: dict, current_price: float) -> Optional[dict]:
    """
    Evaluate a position against take-profit and stop-loss rules.

    Returns a sell action dict if a sell should be triggered, else None.
    Action dict: {reason, sell_pct, urgency}
      - sell_pct: fraction of remaining position to sell (0.0-1.0)
      - urgency: "immediate" | "normal"
    """
    entry_price = float(pos.get("entry_price", 0))
    if entry_price <= 0:
        return None

    gain_pct = ((current_price - entry_price) / entry_price) * 100
    highest_price = float(pos.get("highest_price", entry_price))
    tp1_hit = pos.get("tp1_hit", False)
    tp2_hit = pos.get("tp2_hit", False)
    tp3_hit = pos.get("tp3_hit", False)
    entry_time = pos.get("entry_time")

    # ── Hard stop-loss ────────────────────────────────────────────────────────
    hard_stop = -settings.HARD_STOP_LOSS_PERCENT
    if gain_pct <= hard_stop:
        return {
            "reason": f"hard_stop_loss ({gain_pct:.1f}%)",
            "sell_pct": 1.0,
            "urgency": "immediate",
        }

    # ── Trailing stop (only active after TP1) ─────────────────────────────────
    if tp1_hit and highest_price > entry_price:
        trailing_stop_price = highest_price * (1 - settings.STOP_LOSS_PERCENT / 100)
        if current_price <= trailing_stop_price:
            drop_from_high = ((current_price - highest_price) / highest_price) * 100
            return {
                "reason": f"trailing_stop ({drop_from_high:.1f}% from high)",
                "sell_pct": 1.0,
                "urgency": "immediate",
            }

    # ── Take-profit tiers ─────────────────────────────────────────────────────
    # TP1: 2x (100% gain) → sell 40%
    if not tp1_hit and gain_pct >= 100.0:
        return {
            "reason": "tp1_2x",
            "sell_pct": 0.40,
            "urgency": "normal",
        }

    # TP2: 5x (400% gain) → sell 35% of remaining
    if tp1_hit and not tp2_hit and gain_pct >= 400.0:
        return {
            "reason": "tp2_5x",
            "sell_pct": 0.35,
            "urgency": "normal",
        }

    # TP3: 10x (900% gain) → sell 20% of remaining
    if tp2_hit and not tp3_hit and gain_pct >= 900.0:
        return {
            "reason": "tp3_10x",
            "sell_pct": 0.20,
            "urgency": "normal",
        }

    # ── Time-based exit: no 50% gain in 48h → exit ───────────────────────────
    if entry_time and not tp1_hit:
        try:
            entry_dt = datetime.fromisoformat(str(entry_time).replace("Z", "+00:00"))
            age_hours = (datetime.now(timezone.utc) - entry_dt).total_seconds() / 3600
            if age_hours >= 48 and gain_pct < 50.0:
                return {
                    "reason": f"time_exit_48h (gain={gain_pct:.1f}%)",
                    "sell_pct": 1.0,
                    "urgency": "normal",
                }
        except Exception:
            pass

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
                # Convert quantity to token units (approximate — use 6 decimals default)
                token_amount_units = int(sell_qty * 1_000_000)
                tx_hash = execute_solana_sell(
                    token_mint=pos["token_address"],
                    token_amount=token_amount_units,
                    wallet_public_key=sol_pub,
                    wallet_private_key_env=sol_key_env,
                    slippage_bps=200,
                    is_paper=False,
                )
            else:
                from core.executor import execute_token_sell
                tx_hash = execute_token_sell(
                    token_address=pos["token_address"],
                    chain=chain,
                    wallet_alias=pos.get("wallet", "primary"),
                    quantity=sell_qty,
                    urgency=sell_action.get("urgency", "normal"),
                )
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
        Run a single check cycle.
        Returns summary dict: {checked, sells_triggered, errors}
        """
        positions = load_positions()
        open_positions = [p for p in positions if p.get("status") == "open"]

        if not open_positions:
            return {"checked": 0, "sells_triggered": 0, "errors": 0}

        updated_positions = []
        sells_triggered = 0
        errors = 0

        for pos in open_positions:
            try:
                current_price = get_current_price(
                    token_address=pos.get("token_address", ""),
                    chain=pos.get("chain", ""),
                    pair_address=pos.get("pair_address", ""),
                )

                if current_price is None:
                    logger.debug(f"No price for {pos.get('token_symbol')} — skipping")
                    updated_positions.append(pos)
                    continue

                # Update highest price seen
                pos = dict(pos)
                if current_price > float(pos.get("highest_price", 0)):
                    pos["highest_price"] = current_price

                # Update current price and unrealized PnL
                pos["current_price"] = current_price
                entry_price = float(pos.get("entry_price", 0))
                if entry_price > 0:
                    pos["unrealized_pnl_pct"] = ((current_price - entry_price) / entry_price) * 100

                # Evaluate sell conditions
                sell_action = evaluate_position(pos, current_price)
                if sell_action:
                    pos = execute_sell(pos, sell_action, current_price, self.is_paper)
                    sells_triggered += 1

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

        if sells_triggered > 0:
            logger.info(f"Position monitor: {sells_triggered} sell(s) triggered, {errors} errors")

        return {
            "checked": len(open_positions),
            "sells_triggered": sells_triggered,
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
        "highest_price": entry_price,
        "current_price": entry_price,
        "entry_time": now,
        "last_updated": now,
        "tp1_hit": False,
        "tp2_hit": False,
        "tp3_hit": False,
        "realized_pnl_usd": 0.0,
        "unrealized_pnl_pct": 0.0,
        "tx_hash_buy": tx_hash,
        "gem_score": gem_score,
        "is_paper": is_paper,
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
