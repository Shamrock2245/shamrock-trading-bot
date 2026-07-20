"""
core/profit_lock_manager.py — Dynamic Profit-Locking & Time-Out Decision Engine

Pure decision helper used by the HL trailing monitor in main.py.
Does NOT own on-chain order state (that lives on HyperliquidExecutor /
hl_trailing_state.json). This module only answers: given price + entry + age,
what should the SL be and should we force-close?

Rules (price-move %, not ROE — works at any leverage):
1. Break-even Lock: once +1.5% profit → SL to entry ± 0.1% (covers fees)
2. Early trail: once +3.0% profit → trail 1.5% from peak (longs: peak*0.985)
3. Hard Time-Out: any position still in loss after 4 hours → force close

Tunable via env (read at import / process call):
  PROFIT_LOCK_ENABLED=true
  PROFIT_LOCK_BE_PCT=1.5
  PROFIT_LOCK_BE_BUFFER_PCT=0.1
  PROFIT_LOCK_TRAIL_ACTIVATE_PCT=3.0
  PROFIT_LOCK_TRAIL_DISTANCE_PCT=1.5
  PROFIT_LOCK_LOSS_TIMEOUT_HOURS=4.0
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


# Defaults — also overridable per-call via ProfitLockConfig
PROFIT_LOCK_ENABLED: bool = _env_bool("PROFIT_LOCK_ENABLED", True)
BE_PCT: float = _env_float("PROFIT_LOCK_BE_PCT", 1.5)
BE_BUFFER_PCT: float = _env_float("PROFIT_LOCK_BE_BUFFER_PCT", 0.1)
TRAIL_ACTIVATE_PCT: float = _env_float("PROFIT_LOCK_TRAIL_ACTIVATE_PCT", 3.0)
TRAIL_DISTANCE_PCT: float = _env_float("PROFIT_LOCK_TRAIL_DISTANCE_PCT", 1.5)
LOSS_TIMEOUT_HOURS: float = _env_float("PROFIT_LOCK_LOSS_TIMEOUT_HOURS", 4.0)


@dataclass(frozen=True)
class ProfitLockConfig:
    enabled: bool = True
    be_pct: float = 1.5
    be_buffer_pct: float = 0.1
    trail_activate_pct: float = 3.0
    trail_distance_pct: float = 1.5
    loss_timeout_hours: float = 4.0


@dataclass
class ProfitLockDecision:
    """Result of evaluating one open position."""
    status: str  # "active" | "timeout_close"
    sl_price: Optional[float]  # recommended SL (None = no change)
    locked_profit_pct: float = 0.0
    reason: str = ""
    pnl_pct: float = 0.0
    hold_hours: float = 0.0

    @property
    def should_close(self) -> bool:
        return self.status == "timeout_close"

    @property
    def should_update_sl(self) -> bool:
        return self.sl_price is not None and self.status == "active"


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def default_config() -> ProfitLockConfig:
    """Fresh config from current env (allows tests to monkeypatch env)."""
    return ProfitLockConfig(
        enabled=_env_bool("PROFIT_LOCK_ENABLED", True),
        be_pct=_env_float("PROFIT_LOCK_BE_PCT", 1.5),
        be_buffer_pct=_env_float("PROFIT_LOCK_BE_BUFFER_PCT", 0.1),
        trail_activate_pct=_env_float("PROFIT_LOCK_TRAIL_ACTIVATE_PCT", 3.0),
        trail_distance_pct=_env_float("PROFIT_LOCK_TRAIL_DISTANCE_PCT", 1.5),
        loss_timeout_hours=_env_float("PROFIT_LOCK_LOSS_TIMEOUT_HOURS", 4.0),
    )


def evaluate_position(
    *,
    coin: str,
    current_price: float,
    entry_price: float,
    entry_time: datetime,
    side: str = "long",
    peak_price: Optional[float] = None,
    current_sl: Optional[float] = None,
    now: Optional[datetime] = None,
    config: Optional[ProfitLockConfig] = None,
) -> ProfitLockDecision:
    """
    Evaluate break-even lock, early trail, and hard loss time-out.

    Returns a ProfitLockDecision. Callers apply SL updates via
    HyperliquidExecutor.update_trailing_stop and closes via close_position.
    """
    cfg = config or default_config()
    side = (side or "long").lower()
    if side not in ("long", "short"):
        side = "long"

    if not cfg.enabled:
        return ProfitLockDecision(status="active", sl_price=None, reason="disabled")

    if entry_price <= 0 or current_price <= 0:
        return ProfitLockDecision(status="active", sl_price=None, reason="invalid_price")

    now_utc = _to_utc(now or datetime.now(timezone.utc))
    entry_utc = _to_utc(entry_time)
    hold_hours = max(0.0, (now_utc - entry_utc).total_seconds() / 3600.0)

    if side == "long":
        pnl_pct = ((current_price - entry_price) / entry_price) * 100.0
        peak = peak_price if peak_price and peak_price > 0 else current_price
        peak = max(peak, current_price)
    else:
        pnl_pct = ((entry_price - current_price) / entry_price) * 100.0
        # For shorts peak is the lowest favorable price
        if peak_price and peak_price > 0:
            peak = min(peak_price, current_price)
        else:
            peak = current_price

    # ── Hard time-out: free capital stuck in multi-hour losers ────────────────
    # trade_history (28): losers held ≥4h were −$55 last 7d (KAITO/LDO/PUMP/TRB).
    if pnl_pct < 0 and hold_hours >= cfg.loss_timeout_hours:
        logger.warning(
            f"[{coin}] Hard time-out: {hold_hours:.1f}h in loss ({pnl_pct:.2f}%). "
            f"Marking for closure to free capital."
        )
        return ProfitLockDecision(
            status="timeout_close",
            sl_price=None,
            locked_profit_pct=0.0,
            reason=f"loss_timeout_{hold_hours:.1f}h",
            pnl_pct=pnl_pct,
            hold_hours=hold_hours,
        )

    recommended_sl: Optional[float] = None
    locked = 0.0
    reason = "hold"

    # ── Break-even lock ──────────────────────────────────────────────────────
    if pnl_pct >= cfg.be_pct:
        if side == "long":
            be_sl = entry_price * (1.0 + cfg.be_buffer_pct / 100.0)
            if current_sl is None or current_sl < be_sl:
                recommended_sl = be_sl
                locked = cfg.be_buffer_pct
                reason = "break_even_lock"
        else:
            be_sl = entry_price * (1.0 - cfg.be_buffer_pct / 100.0)
            if current_sl is None or current_sl > be_sl:
                recommended_sl = be_sl
                locked = cfg.be_buffer_pct
                reason = "break_even_lock"

    # ── Early profit trail (price-based, before ROE trail kicks in) ───────────
    if pnl_pct >= cfg.trail_activate_pct:
        trail_frac = cfg.trail_distance_pct / 100.0
        if side == "long":
            trail_sl = peak * (1.0 - trail_frac)
            if recommended_sl is None or trail_sl > recommended_sl:
                if current_sl is None or trail_sl > current_sl:
                    recommended_sl = trail_sl
                    locked = cfg.trail_distance_pct
                    reason = "early_trail"
        else:
            trail_sl = peak * (1.0 + trail_frac)
            if recommended_sl is None or trail_sl < recommended_sl:
                if current_sl is None or trail_sl < current_sl:
                    recommended_sl = trail_sl
                    locked = cfg.trail_distance_pct
                    reason = "early_trail"

    if recommended_sl is not None and reason == "break_even_lock":
        logger.info(
            f"[{coin}] Break-even SL recommended @ {recommended_sl:.8f} "
            f"(entry={entry_price:.8f}, pnl={pnl_pct:.2f}%)"
        )
    elif recommended_sl is not None and reason == "early_trail":
        logger.info(
            f"[{coin}] Early trail SL recommended @ {recommended_sl:.8f} "
            f"(peak={peak:.8f}, trail={cfg.trail_distance_pct}%, pnl={pnl_pct:.2f}%)"
        )

    return ProfitLockDecision(
        status="active",
        sl_price=recommended_sl,
        locked_profit_pct=locked,
        reason=reason,
        pnl_pct=pnl_pct,
        hold_hours=hold_hours,
    )


class ProfitLockManager:
    """
    Thin compatibility wrapper around evaluate_position.

    Manus originally shipped a stateful manager that wrote a conflicting
    hl_trailing_state.json format and deadlocked on threading.Lock re-entry.
    This class keeps the public API (process_position / mark_closed) but
    delegates decisions to the pure evaluate_position() helper and does not
    own executor order state.
    """

    def __init__(self, state_file: str | None = None, config: Optional[ProfitLockConfig] = None):
        # state_file retained for API compatibility; unused (executor owns state).
        self.state_file = state_file
        self.config = config
        self._closed: set[str] = set()

    def process_position(
        self,
        coin: str,
        current_price: float,
        entry_price: float,
        entry_time: datetime,
        side: str = "long",
        peak_price: Optional[float] = None,
        current_sl: Optional[float] = None,
        now: Optional[datetime] = None,
    ) -> dict:
        decision = evaluate_position(
            coin=coin,
            current_price=current_price,
            entry_price=entry_price,
            entry_time=entry_time,
            side=side,
            peak_price=peak_price,
            current_sl=current_sl,
            now=now,
            config=self.config,
        )
        return {
            "entry_price": entry_price,
            "entry_time": entry_time.isoformat() if isinstance(entry_time, datetime) else entry_time,
            "peak_price": peak_price if peak_price is not None else current_price,
            "sl_price": decision.sl_price if decision.sl_price is not None else current_sl,
            "status": decision.status,
            "locked_profit_pct": decision.locked_profit_pct,
            "side": side,
            "reason": decision.reason,
            "pnl_pct": decision.pnl_pct,
            "hold_hours": decision.hold_hours,
            "recommended_sl": decision.sl_price,
        }

    def get_position_state(self, coin: str) -> Optional[dict]:
        return None

    def mark_closed(self, coin: str) -> None:
        self._closed.add(coin)

    def cleanup_closed(self) -> None:
        self._closed.clear()


# Global instance for convenience imports
profit_lock_manager = ProfitLockManager()
