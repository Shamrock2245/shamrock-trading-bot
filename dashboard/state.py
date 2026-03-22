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
