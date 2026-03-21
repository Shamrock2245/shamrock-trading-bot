"""
dashboard/state.py — Bot state persistence for the trading dashboard.

The main bot writes structured JSON state files after each scan cycle.
The Streamlit dashboard reads these files for real-time display.

State directory: /app/data/dashboard/ (shared Docker volume)
"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


STATE_DIR = Path(os.getenv("DASHBOARD_STATE_DIR", "./data/dashboard"))


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
            "uptime_seconds": int((now - datetime.fromisoformat(self._start_time)).total_seconds()),
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

        # ── Trades ────────────────────────────────────────────────────────
        if trades:
            trade_data = []
            for t in trades:
                trade_data.append({
                    "id": getattr(t, "id", None),
                    "symbol": getattr(t, "token_symbol", ""),
                    "chain": getattr(t, "chain", ""),
                    "direction": getattr(t, "direction", ""),
                    "amount_in": getattr(t, "amount_in", 0),
                    "amount_out": getattr(t, "amount_out", 0),
                    "price_usd": getattr(t, "price_usd", 0),
                    "gas_cost_eth": getattr(t, "gas_cost_eth", 0),
                    "execution_path": getattr(t, "execution_path", ""),
                    "status": getattr(t, "status", ""),
                    "gem_score": getattr(t, "gem_score", 0),
                    "signal_score": getattr(t, "signal_score", 0),
                    "timestamp": getattr(t, "timestamp", now).isoformat() if hasattr(getattr(t, "timestamp", now), "isoformat") else str(getattr(t, "timestamp", now)),
                })
            all_trades = _read_json("trades.json", [])
            all_trades.extend(trade_data)
            _write_json("trades.json", all_trades)

        # ── Positions ─────────────────────────────────────────────────────
        if positions:
            pos_data = []
            for p in positions:
                pos_data.append({
                    "symbol": getattr(p, "token_symbol", ""),
                    "chain": getattr(p, "chain", ""),
                    "entry_price": getattr(p, "entry_price_usd", 0),
                    "current_price": getattr(p, "current_price_usd", 0),
                    "amount_tokens": getattr(p, "amount_tokens", 0),
                    "amount_eth_spent": getattr(p, "amount_eth_spent", 0),
                    "unrealized_pnl_pct": p.unrealized_pnl_pct if hasattr(p, "unrealized_pnl_pct") else 0,
                    "is_open": getattr(p, "is_open", True),
                    "fib_zone": getattr(p, "fib_zone", ""),
                    "fib_support": getattr(p, "fib_support", 0),
                    "fib_resistance": getattr(p, "fib_resistance", 0),
                    "opened_at": getattr(p, "opened_at", now).isoformat() if hasattr(getattr(p, "opened_at", now), "isoformat") else str(getattr(p, "opened_at", now)),
                })
            _write_json("positions.json", pos_data)

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

def get_trades() -> list:
    return _read_json("trades.json", [])

def get_positions() -> list:
    return _read_json("positions.json", [])

def get_errors() -> list:
    return _read_json("errors.json", [])
