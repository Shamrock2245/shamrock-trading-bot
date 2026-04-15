"""
core/slippage_tracker.py — Slippage analytics for trade execution.

Tracks actual vs expected trade outcomes to measure sandwich attack losses,
pool depth issues, and overall execution quality.

Usage:
    from core.slippage_tracker import record_slippage, get_slippage_summary

    # After each trade:
    record_slippage(
        token_symbol="PEPE",
        chain="base",
        direction="buy",
        expected_amount_out=1000.0,
        actual_amount_out=970.0,
        slippage_bps_configured=100,
    )

    # Dashboard / analytics:
    summary = get_slippage_summary(days=7)
"""

import json
import logging
import os
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

SLIPPAGE_FILE = Path(os.getenv("SLIPPAGE_LOG_FILE", "output/slippage_log.json"))
SLIPPAGE_FILE.parent.mkdir(parents=True, exist_ok=True)


def _load_log() -> list[dict]:
    """Load the slippage log."""
    if SLIPPAGE_FILE.exists():
        try:
            with open(SLIPPAGE_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []
    return []


def _save_log(entries: list[dict]) -> None:
    """Save the slippage log (keep last 500 entries max)."""
    entries = entries[-500:]  # Rolling window
    try:
        tmp = SLIPPAGE_FILE.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(entries, f, indent=2, default=str)
            f.flush()
            os.fsync(f.fileno())
        tmp.replace(SLIPPAGE_FILE)
    except Exception as e:
        logger.debug(f"Failed to save slippage log: {e}")


def record_slippage(
    token_symbol: str,
    chain: str,
    direction: str,  # "buy" or "sell"
    expected_amount_out: float,
    actual_amount_out: float,
    slippage_bps_configured: int = 100,
    tx_hash: str = "",
    execution_path: str = "",
) -> Optional[dict]:
    """
    Record a trade's slippage for analytics.
    Returns the slippage record, or None if inputs are invalid.
    """
    if expected_amount_out <= 0 or actual_amount_out < 0:
        return None

    actual_slippage_bps = round((expected_amount_out - actual_amount_out) / expected_amount_out * 10000, 2)

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "token_symbol": token_symbol,
        "chain": chain,
        "direction": direction,
        "expected_out": round(expected_amount_out, 8),
        "actual_out": round(actual_amount_out, 8),
        "slippage_bps": actual_slippage_bps,
        "configured_bps": slippage_bps_configured,
        "excess_slippage_bps": max(0, actual_slippage_bps - slippage_bps_configured),
        "tx_hash": tx_hash,
        "execution_path": execution_path,
    }

    try:
        entries = _load_log()
        entries.append(record)
        _save_log(entries)
    except Exception as e:
        logger.debug(f"Failed to record slippage: {e}")

    # Log notable slippage
    if actual_slippage_bps > 200:
        logger.warning(
            f"⚠️ HIGH SLIPPAGE: {token_symbol}/{chain} {direction} — "
            f"{actual_slippage_bps:.0f}bps (configured: {slippage_bps_configured}bps)"
        )
    elif actual_slippage_bps > 0:
        logger.debug(
            f"Slippage: {token_symbol}/{chain} {direction} — "
            f"{actual_slippage_bps:.0f}bps"
        )

    return record


def get_slippage_summary(days: int = 7) -> dict:
    """
    Compute slippage analytics for the last N days.
    Returns summary dict with aggregated metrics.
    """
    entries = _load_log()
    if not entries:
        return {"total_trades": 0, "avg_slippage_bps": 0, "message": "No slippage data"}

    cutoff = time.time() - (days * 86400)
    recent = []
    for e in entries:
        try:
            ts = datetime.fromisoformat(e["timestamp"].replace("Z", "+00:00")).timestamp()
            if ts >= cutoff:
                recent.append(e)
        except Exception:
            continue

    if not recent:
        return {"total_trades": 0, "avg_slippage_bps": 0, "message": f"No trades in last {days} days"}

    slippages = [e["slippage_bps"] for e in recent]
    buy_slippages = [e["slippage_bps"] for e in recent if e["direction"] == "buy"]
    sell_slippages = [e["slippage_bps"] for e in recent if e["direction"] == "sell"]
    excess = [e["excess_slippage_bps"] for e in recent if e["excess_slippage_bps"] > 0]

    # Per-chain breakdown
    chains = {}
    for e in recent:
        c = e.get("chain", "unknown")
        if c not in chains:
            chains[c] = []
        chains[c].append(e["slippage_bps"])

    chain_avg = {c: round(sum(v) / len(v), 1) for c, v in chains.items()}

    return {
        "period_days": days,
        "total_trades": len(recent),
        "avg_slippage_bps": round(sum(slippages) / len(slippages), 1),
        "max_slippage_bps": round(max(slippages), 1),
        "median_slippage_bps": round(sorted(slippages)[len(slippages) // 2], 1),
        "buy_avg_bps": round(sum(buy_slippages) / len(buy_slippages), 1) if buy_slippages else 0,
        "sell_avg_bps": round(sum(sell_slippages) / len(sell_slippages), 1) if sell_slippages else 0,
        "excess_slippage_events": len(excess),
        "avg_excess_bps": round(sum(excess) / len(excess), 1) if excess else 0,
        "chain_breakdown": chain_avg,
    }
