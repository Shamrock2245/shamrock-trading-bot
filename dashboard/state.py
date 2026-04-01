"""
dashboard/state.py — Bot state persistence for the trading dashboard.

The main bot writes structured JSON state files after each scan cycle.
The Streamlit dashboard reads these files for real-time display.

State directory: /app/data/dashboard/ (shared Docker volume)

Schema notes:
  - Positions are bridged from output/positions.json (position_monitor format)
    to dashboard format on every read. No separate write needed.
  - Trades are bridged from output/trades.json (position_monitor format).
  - express_lane, Solana chain, and all new fields are supported.
"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


STATE_DIR = Path(os.getenv("DASHBOARD_STATE_DIR", "./data/dashboard"))

# Paths to the position_monitor output files (source of truth for positions/trades)
_POSITIONS_FILE = Path(os.getenv("POSITIONS_FILE", "output/positions.json"))
_TRADES_FILE = Path(os.getenv("TRADES_FILE", "output/trades.json"))


def _ensure_dir():
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def _read_json(filename: str, default: Any = None) -> Any:
    """Read a JSON state file, returning default if missing or corrupt."""
    path = STATE_DIR / filename
    if not path.exists():
        return default if default is not None else {}
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return default if default is not None else {}


def _write_json(filename: str, data: Any):
    """Atomically write a JSON state file."""
    _ensure_dir()
    path = STATE_DIR / filename
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, default=str)
    tmp.replace(path)


def _read_raw_json(path: Path, default: Any = None) -> Any:
    """Read any JSON file by absolute path."""
    if not path.exists():
        return default if default is not None else []
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return default if default is not None else []


# ─────────────────────────────────────────────────────────────────────────────
# Schema Bridge: position_monitor → dashboard
# ─────────────────────────────────────────────────────────────────────────────

def _bridge_position(p: dict) -> dict:
    """
    Convert a position_monitor position dict to dashboard format.

    position_monitor keys:
      token_symbol, chain, entry_price, current_price, remaining_quantity,
      unrealized_pnl_pct, status, entry_time, tp1_hit, tp2_hit, tp3_hit,
      realized_pnl_usd, gem_score, is_paper, express_lane, wallet

    Dashboard keys expected by pages/3_Positions.py:
      symbol, chain, entry_price, current_price, amount_eth_spent,
      unrealized_pnl_pct, is_open, fib_zone, fib_support, fib_resistance,
      opened_at, tp1_hit, tp2_hit, tp3_hit, express_lane, wallet
    """
    entry_price = float(p.get("entry_price", 0))
    current_price = float(p.get("current_price", entry_price))
    qty = float(p.get("remaining_quantity", p.get("quantity", 0)))
    # Estimate ETH/SOL spent from entry price × quantity (approximate)
    chain = p.get("chain", "")
    native_price = 3000.0 if chain != "solana" else 150.0  # rough fallback
    amount_native = (entry_price * qty) / native_price if native_price > 0 else 0

    return {
        "symbol": p.get("token_symbol", p.get("symbol", "???")),
        "chain": chain,
        "entry_price": entry_price,
        "current_price": current_price,
        "amount_eth_spent": amount_native,
        "amount_sol_spent": amount_native if chain == "solana" else 0,
        "unrealized_pnl_pct": float(p.get("unrealized_pnl_pct", 0)),
        "realized_pnl_usd": float(p.get("realized_pnl_usd", 0)),
        "is_open": p.get("status", "open") == "open",
        "fib_zone": p.get("fib_zone", ""),
        "fib_support": p.get("fib_support", 0),
        "fib_resistance": p.get("fib_resistance", 0),
        "opened_at": p.get("entry_time", p.get("opened_at", "")),
        "tp1_hit": p.get("tp1_hit", False),
        "tp2_hit": p.get("tp2_hit", False),
        "tp3_hit": p.get("tp3_hit", False),
        "gem_score": p.get("gem_score", 0),
        "express_lane": p.get("express_lane", False),
        "wallet": p.get("wallet", "primary"),
        "is_paper": p.get("is_paper", True),
        "tx_hash_buy": p.get("tx_hash_buy", ""),
    }


def _bridge_trade(t: dict) -> dict:
    """
    Convert a position_monitor trade dict to dashboard format.

    position_monitor keys:
      timestamp, token_symbol, chain, wallet, action (BUY/SELL), reason,
      quantity, price_usd, value_usd, pnl_usd, pnl_pct, is_paper, tx_hash

    Dashboard keys expected by pages/3_Positions.py:
      timestamp, symbol, chain, direction (buy/sell), amount_in, amount_out,
      price_usd, gas_cost_eth, execution_path, status, gem_score
    """
    action = t.get("action", t.get("direction", "")).upper()
    direction = "buy" if action == "BUY" else "sell"
    qty = float(t.get("quantity", 0))
    price = float(t.get("price_usd", 0))
    pnl_usd = float(t.get("pnl_usd", 0))

    return {
        "timestamp": t.get("timestamp", ""),
        "symbol": t.get("token_symbol", t.get("symbol", "???")),
        "chain": t.get("chain", ""),
        "direction": direction,
        "amount_in": qty if direction == "buy" else qty,
        "amount_out": qty + (pnl_usd / price if price > 0 else 0) if direction == "sell" else qty,
        "price_usd": price,
        "gas_cost_eth": float(t.get("gas_cost_eth", 0)),
        "execution_path": t.get("execution_path", t.get("reason", "")),
        "status": "success" if not t.get("error") else "failed",
        "gem_score": float(t.get("gem_score", 0)),
        "pnl_usd": pnl_usd,
        "pnl_pct": float(t.get("pnl_pct", 0)),
        "wallet": t.get("wallet", ""),
        "is_paper": t.get("is_paper", True),
        "tx_hash": t.get("tx_hash", ""),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Writer (called from main.py)
# ─────────────────────────────────────────────────────────────────────────────

class BotStateWriter:
    """Writes bot state to JSON files after each scan cycle."""

    def __init__(self):
        _ensure_dir()
        self.cycle_count = 0
        self._start_time = datetime.now(timezone.utc).isoformat()

    def write_cycle(
        self,
        candidates: list,
        trades: Optional[list] = None,
        positions: Optional[list] = None,
        chains_scanned: Optional[list] = None,
        errors: Optional[list] = None,
    ):
        """Write complete state after a scan cycle."""
        self.cycle_count += 1
        now = datetime.now(timezone.utc)

        # ── Bot Status ───────────────────────────────────────────────────
        status = _read_json("bot_status.json", {})
        status.update({
            "is_running": True,
            "mode": os.getenv("MODE", "paper"),
            "started_at": self._start_time,
            "last_cycle_at": now.isoformat(),
            "cycle_count": self.cycle_count,
            "chains_scanned": chains_scanned or [],
            "uptime_seconds": int(
                (now - datetime.fromisoformat(self._start_time)).total_seconds()
            ),
        })
        _write_json("bot_status.json", status)

        # ── Scan History (append, cap at 2000) ───────────────────────────
        history = _read_json("scan_history.json", [])
        cycle_entry = {
            "cycle": self.cycle_count,
            "timestamp": now.isoformat(),
            "candidates_found": len(candidates),
            "trades_attempted": len(trades) if trades else 0,
            "errors": len(errors) if errors else 0,
            "chains": chains_scanned or [],
        }
        history.append(cycle_entry)
        if len(history) > 2000:
            history = history[-2000:]
        _write_json("scan_history.json", history)

        # ── Gem Candidates (latest batch + cumulative) ────────────────────
        latest_gems = []
        for c in candidates:
            token = c.token if hasattr(c, "token") else c
            gem_data = {
                "symbol": getattr(token, "symbol", "???"),
                "name": getattr(token, "name", ""),
                "chain": getattr(token, "chain", ""),
                "address": getattr(token, "address", ""),
                "price_usd": getattr(token, "price_usd", 0),
                "market_cap": getattr(token, "market_cap", 0),
                "liquidity_usd": getattr(token, "liquidity_usd", 0),
                "volume_24h": getattr(token, "volume_24h", 0),
                "volume_1h": getattr(token, "volume_1h", 0),
                "price_change_1h": getattr(token, "price_change_1h", 0),
                "age_hours": getattr(token, "age_hours", None),
                "is_boosted": getattr(token, "is_boosted", False),
                "boost_amount": getattr(token, "boost_amount", 0),
                "dex_url": getattr(token, "dex_url", ""),
                "gem_score": getattr(c, "gem_score", 0),
                "express_lane": getattr(c, "express_lane", False),
                "safety_passed": getattr(c, "safety_passed", False),
                "is_safe": getattr(c, "is_safe", False),
                "discovered_at": now.isoformat(),
                # Entry timing intelligence fields
                "timing_score": getattr(c, "timing_score", 50.0),
                "timing_bp_trend": getattr(c, "timing_bp_trend", "flat"),
                "timing_volume_acceleration": getattr(c, "timing_volume_acceleration", 1.0),
                "timing_buyer_velocity": getattr(c, "timing_buyer_velocity", 1.0),
                "timing_bp_micro_ratio": getattr(c, "timing_bp_micro_ratio", 1.0),
                "is_accumulation_zone": getattr(c, "is_accumulation_zone", False),
                "is_near_ath": getattr(c, "is_near_ath", False),
                "price_range_position": getattr(c, "price_range_position", 0.5),
                "vol_trend_7d": getattr(c, "vol_trend_7d", "neutral"),
                "moralis_buy_pressure": getattr(c, "moralis_buy_pressure", 0.5),
                "moralis_exp_net_buyers_1w": getattr(c, "moralis_exp_net_buyers_1w", 0),
                "strategy_tag": getattr(c, "strategy_tag", "gem_snipe"),
                "scores": {
                    "age": getattr(c, "age_score", 0),
                    "volume": getattr(c, "volume_score", 0),
                    "liquidity": getattr(c, "liquidity_score", 0),
                    "contract": getattr(c, "contract_score", 0),
                    "holder": getattr(c, "holder_score", 0),
                    "tax": getattr(c, "tax_score", 0),
                    "social": getattr(c, "social_score", 0),
                    "boost": getattr(c, "boost_score", 0),
                    "smart_money": getattr(c, "smart_money_score", 0),
                    "tvl": getattr(c, "tvl_score", 0),
                    "social_sentiment": getattr(c, "social_sentiment_score", 0),
                    "holder_concentration": getattr(c, "holder_concentration_score", 0),
                    "unlock_risk": getattr(c, "unlock_risk_score", 0),
                    "moralis": getattr(c, "moralis_score", 0),
                    "dev_wallet": getattr(c, "dev_wallet_score", 0),
                    "copycat": getattr(c, "copycat_score", 0),
                },
            }

            # Add signal score if present
            sig = getattr(c, "signal_score", None)
            if sig:
                gem_data["signal"] = {
                    "trend": getattr(sig, "trend_score", 0),
                    "momentum": getattr(sig, "momentum_score", 0),
                    "volume": getattr(sig, "volume_score", 0),
                    "onchain": getattr(sig, "onchain_score", 0),
                    "fib_score": getattr(sig, "fib_score", 0),
                    "fib_zone": getattr(sig, "fib_zone", ""),
                    "fib_aligned": getattr(sig, "fib_aligned", False),
                    "composite": sig.composite if hasattr(sig, "composite") else 0,
                    "signal": sig.signal if hasattr(sig, "signal") else "N/A",
                }

            latest_gems.append(gem_data)

        _write_json("latest_gems.json", latest_gems)

        # Cumulative gem history
        all_gems = _read_json("gem_history.json", [])
        all_gems.extend(latest_gems)
        if len(all_gems) > 5000:
            all_gems = all_gems[-5000:]
        _write_json("gem_history.json", all_gems)

        # ── Errors ────────────────────────────────────────────────────────
        if errors:
            err_log = _read_json("errors.json", [])
            for e in errors:
                err_log.append({
                    "timestamp": now.isoformat(),
                    "cycle": self.cycle_count,
                    "error": str(e),
                })
            if len(err_log) > 500:
                err_log = err_log[-500:]
            _write_json("errors.json", err_log)


# ─────────────────────────────────────────────────────────────────────────────
# Reader (called from Streamlit dashboard)
# ─────────────────────────────────────────────────────────────────────────────

def get_bot_status() -> dict:
    return _read_json("bot_status.json", {})

def get_scan_history() -> list:
    return _read_json("scan_history.json", [])

def get_latest_gems() -> list:
    return _read_json("latest_gems.json", [])

def get_gem_history() -> list:
    return _read_json("gem_history.json", [])

def get_errors() -> list:
    return _read_json("errors.json", [])


# ─────────────────────────────────────────────────────────────────────────────
# Force-Scan Trigger (Dashboard → Bot IPC via shared JSON file)
# The dashboard writes scan_trigger.json; the bot checks it each cycle.
# ─────────────────────────────────────────────────────────────────────────────

def request_force_scan(reason: str = "manual") -> None:
    """Write a scan trigger file. The bot loop checks this at the top of each cycle."""
    _ensure_dir()
    _write_json("scan_trigger.json", {
        "requested": True,
        "reason": reason,
        "requested_at": datetime.now(timezone.utc).isoformat(),
    })


def get_force_scan_request() -> dict:
    """Read the scan trigger file. Returns {} if no pending request."""
    data = _read_json("scan_trigger.json", {})
    if data.get("requested"):
        return data
    return {}


def clear_force_scan_request() -> None:
    """Clear the scan trigger after the bot has processed it."""
    _write_json("scan_trigger.json", {"requested": False, "cleared_at": datetime.now(timezone.utc).isoformat()})


def get_positions() -> list:
    """
    Read positions from output/positions.json (position_monitor source of truth)
    and bridge to dashboard format. Falls back to dashboard state file.
    """
    raw = _read_raw_json(_POSITIONS_FILE, [])
    if raw:
        return [_bridge_position(p) for p in raw]
    # Fallback: legacy dashboard state
    return _read_json("positions.json", [])


def get_trades() -> list:
    """
    Read trades from output/trades.json (position_monitor source of truth)
    and bridge to dashboard format. Falls back to dashboard state file.
    """
    raw = _read_raw_json(_TRADES_FILE, [])
    if raw:
        return [_bridge_trade(t) for t in raw[-500:]]  # Last 500 trades
    # Fallback: legacy dashboard state
    return _read_json("trades.json", [])


# ─────────────────────────────────────────────────────────────────────────────
# Manual Intervention IPC (Dashboard → Bot)
#
# The dashboard writes command files; the bot loop checks them each cycle.
# Commands are processed in order and cleared after execution.
#
# Supported commands:
#   manual_sell  — force-sell a % of an open position immediately
#   manual_close — force-close 100% of an open position immediately
#   manual_buy   — force-buy a specific token with a given USD amount
# ─────────────────────────────────────────────────────────────────────────────

_MANUAL_COMMANDS_FILE = "manual_commands.json"


def _get_manual_commands() -> list:
    """Read all pending manual commands."""
    return _read_json(_MANUAL_COMMANDS_FILE, [])


def _write_manual_commands(commands: list) -> None:
    """Persist the manual commands list."""
    _write_json(_MANUAL_COMMANDS_FILE, commands)


def request_manual_sell(
    token_address: str,
    chain: str,
    symbol: str,
    sell_pct: float = 100.0,
    reason: str = "dashboard_manual_sell",
) -> None:
    """
    Queue a manual sell command.  The bot will execute it at the top of the
    next cycle, bypassing TP/SL logic.

    Args:
        token_address: Contract address of the token to sell.
        chain:         Chain name (e.g. "base", "solana").
        symbol:        Human-readable ticker (for logging).
        sell_pct:      Fraction of remaining position to sell (0–100).
        reason:        Tag written to the trade log.
    """
    _ensure_dir()
    commands = _get_manual_commands()
    commands.append({
        "type": "manual_sell",
        "token_address": token_address,
        "chain": chain,
        "symbol": symbol,
        "sell_pct": float(sell_pct),
        "reason": reason,
        "requested_at": datetime.now(timezone.utc).isoformat(),
        "processed": False,
    })
    _write_manual_commands(commands)


def request_manual_close(
    token_address: str,
    chain: str,
    symbol: str,
    reason: str = "dashboard_force_close",
) -> None:
    """Queue a 100% force-close command for a position."""
    request_manual_sell(
        token_address=token_address,
        chain=chain,
        symbol=symbol,
        sell_pct=100.0,
        reason=reason,
    )


def request_manual_buy(
    token_address: str,
    chain: str,
    symbol: str,
    usd_amount: float,
    wallet: str = "primary",
    reason: str = "dashboard_manual_buy",
) -> None:
    """
    Queue a manual buy command.  The bot will execute it at the top of the
    next cycle, bypassing the score gate (but NOT safety/honeypot checks).

    Args:
        token_address: Contract address of the token to buy.
        chain:         Chain name.
        symbol:        Human-readable ticker.
        usd_amount:    USD value to spend (converted to native at execution time).
        wallet:        Wallet alias ("primary", "wallet_b", "wallet_c").
        reason:        Tag written to the trade log.
    """
    _ensure_dir()
    commands = _get_manual_commands()
    commands.append({
        "type": "manual_buy",
        "token_address": token_address,
        "chain": chain,
        "symbol": symbol,
        "usd_amount": float(usd_amount),
        "wallet": wallet,
        "reason": reason,
        "requested_at": datetime.now(timezone.utc).isoformat(),
        "processed": False,
    })
    _write_manual_commands(commands)


def get_pending_manual_commands() -> list:
    """Return all unprocessed manual commands."""
    return [c for c in _get_manual_commands() if not c.get("processed")]


def mark_manual_command_processed(requested_at: str, result: str = "ok") -> None:
    """Mark a command as processed so it is not re-executed."""
    commands = _get_manual_commands()
    for cmd in commands:
        if cmd.get("requested_at") == requested_at:
            cmd["processed"] = True
            cmd["processed_at"] = datetime.now(timezone.utc).isoformat()
            cmd["result"] = result
            break
    # Keep only last 200 commands (processed + pending)
    _write_manual_commands(commands[-200:])


def clear_processed_manual_commands() -> None:
    """Purge all processed commands older than 24 h (housekeeping)."""
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    commands = _get_manual_commands()
    kept = []
    for cmd in commands:
        if not cmd.get("processed"):
            kept.append(cmd)  # Always keep pending
            continue
        try:
            ts = datetime.fromisoformat(cmd.get("processed_at", ""))
            if ts.replace(tzinfo=timezone.utc) > cutoff:
                kept.append(cmd)  # Keep recent processed
        except (ValueError, TypeError):
            pass
    _write_manual_commands(kept)
