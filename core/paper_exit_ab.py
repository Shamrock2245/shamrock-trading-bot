"""Paper-only exit A/B: current structure stop vs 2×ATR stop + 8h loss timeout.

Why: the offline walk-forward (docs/backtest/WALK_FORWARD_2026-10-21.md and the
follow-up stop sweep) found a 2×ATR(14, 1h) stop with an 8h loss timeout beat
the structure stop + 4h timeout in every out-of-sample fold. Backtests are not
proof, so we A/B it in paper before anyone proposes it for live.

Arms
  control   : unchanged (structure/fib SL from the scanner, WINNING_LOSS_TIMEOUT_HOURS).
  atr2x_8h  : SL = entry ∓ PAPER_EXIT_AB_ATR_MULT × ATR(14) on 1h candles, and
              loss timeout PAPER_EXIT_AB_ATR_TIMEOUT_HOURS. Everything else is
              identical: same entry filter (R/R is checked on the structure SL
              BEFORE the arm is applied, so both arms admit exactly the same
              signals), same TP, BE, TP1, trail ladder, 45-min rule (−1.5%)
              and the −$15 / −5% hard loss cap.

Split method: deterministic hash randomisation, not alternation.
  arm = sha256(f"{salt}|{coin}|{UTC open hour}")[0] & 1
  Alternation leaks the scanner's ranking (within one scan the best-scored
  signal opens first, so a global even/odd counter would hand the top-ranked
  signal to the same arm whenever the counter parity lines up). A hash of
  coin + open hour is independent of score, rank, regime and restart state,
  needs no persisted counter, and is reproducible offline from trades.json.
  Expected split is 50/50; with small n it can drift a few trades.
  If 1h candles are unavailable for an atr2x_8h trade, it keeps the structure
  SL, still uses the 8h timeout and is tagged ab_atr_fallback=true so the
  review can drop it.

Scope: paper only. ab_enabled() is False unless the global mode is paper, so
live order placement, live stops and live timeouts are untouched.
Settings (Three-File Rule: code default, .env.example, CI sed):
  PAPER_EXIT_AB_ENABLED (true), PAPER_EXIT_AB_ATR_MULT (2.0),
  PAPER_EXIT_AB_ATR_TIMEOUT_HOURS (8.0), PAPER_EXIT_AB_SALT (predator-ab-v1).
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import replace
from datetime import datetime, timezone
from typing import Iterable, Optional

CONTROL = "control"
ATR_ARM = "atr2x_8h"
ATR_PERIOD = 14


def _paper_mode_active() -> bool:
    try:
        from config import settings as _s
        return _s.get_current_mode() == "paper"
    except Exception:
        return False


def _env_float(name: str, default: float, lo: float, hi: float) -> float:
    try:
        v = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        v = default
    if v != v:  # NaN
        v = default
    return max(lo, min(v, hi))


def ab_enabled() -> bool:
    if not _paper_mode_active():
        return False
    return os.getenv("PAPER_EXIT_AB_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")


def atr_mult() -> float:
    return _env_float("PAPER_EXIT_AB_ATR_MULT", 2.0, 0.5, 5.0)


def atr_timeout_hours() -> float:
    return _env_float("PAPER_EXIT_AB_ATR_TIMEOUT_HOURS", 8.0, 1.0, 48.0)


def _salt() -> str:
    return (os.getenv("PAPER_EXIT_AB_SALT", "predator-ab-v1") or "predator-ab-v1").strip()


def assign_variant(coin: str, opened_at: Optional[datetime] = None) -> str:
    ts = opened_at or datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    bucket = ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H")
    h = hashlib.sha256(f"{_salt()}|{str(coin).upper()}|{bucket}".encode()).digest()
    return ATR_ARM if (h[0] & 1) else CONTROL


def compute_atr(candles: Iterable[dict], period: int = ATR_PERIOD) -> Optional[float]:
    """Wilder-free simple ATR over the last `period` true ranges of HL candles
    (dicts with h/l/c as str or float). Returns None if too few bars."""
    rows = []
    for c in candles or []:
        try:
            rows.append((float(c["h"]), float(c["l"]), float(c["c"])))
        except (KeyError, TypeError, ValueError):
            continue
    if len(rows) < period + 1:
        return None
    trs = []
    for i in range(len(rows) - period, len(rows)):
        h, l, _ = rows[i]
        pc = rows[i - 1][2]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    atr = sum(trs) / len(trs)
    return atr if atr > 0 else None


def atr_stop(side: str, entry: float, atr: float, mult: Optional[float] = None) -> float:
    m = atr_mult() if mult is None else mult
    return entry - m * atr if side == "long" else entry + m * atr


def winning_config_for(variant: str, is_paper: bool):
    """Winning v32 config override for a position, or None to use the default.
    Only the loss timeout differs, and only for paper ATR-arm positions."""
    if not is_paper or variant != ATR_ARM or not _paper_mode_active():
        return None
    from core.winning_risk_manager import default_config
    return replace(default_config(), loss_timeout_hours=atr_timeout_hours())
