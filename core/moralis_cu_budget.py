"""
core/moralis_cu_budget.py — Moralis Compute Unit (CU) Budget Enforcer

Hard guarantees:
  1. Never spend more than MONTHLY_CU_BUDGET (soft cap, default 394M of ~500M plan)
  2. Pace daily burn so we do not front-load the month
  3. Progressive throttle: NORMAL → CONSERVATIVE → EMERGENCY → EXHAUSTED
  4. Fail closed: if budget state is unknown/broken, block paid REST calls
  5. Persist state for the Streamlit dashboard (bot process writes, UI reads)

Actual CU preferred from response header x-request-weight via moralis_http.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from calendar import monthrange
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────
BUDGET_FILE = Path("output/moralis_cu_budget.json")
DASHBOARD_SNAPSHOT = (
    Path(os.environ.get("DASHBOARD_STATE_DIR", "./data/dashboard"))
    / "moralis_cu_status.json"
)
BUDGET_LOCK = threading.Lock()

# Soft monthly cap (leave headroom under Business ~500M allotment)
MONTHLY_CU_BUDGET: int = int(getattr(settings, "MORALIS_MONTHLY_CU_BUDGET", 394_000_000) or 0)

# EMERGENCY when remaining fraction drops below this
SAFETY_BUFFER_PCT: float = float(getattr(settings, "MORALIS_SAFETY_BUFFER_PCT", 0.10) or 0.10)

# CONSERVATIVE when remaining fraction drops below this
CONSERVATIVE_PCT: float = float(getattr(settings, "MORALIS_CONSERVATIVE_PCT", 0.25) or 0.25)

# Daily pace: allow at most this fraction of (remaining/days_left) extra burst
DAILY_PACE_BURST: float = float(getattr(settings, "MORALIS_DAILY_PACE_BURST", 1.15) or 1.15)

# Scan-cycle heuristic
CYCLES_PER_DAY = 48

# Max CU for EMERGENCY band (prices, metadata, holders, swaps)
EMERGENCY_MAX_CU = 50
# Max CU for CONSERVATIVE band (block DeFi / heavy)
CONSERVATIVE_MAX_CU = 499


# ─────────────────────────────────────────────────────────────────────────────
# CU Cost Registry (docs + live x-request-weight probes 2026-07-30)
# ─────────────────────────────────────────────────────────────────────────────
CU_COSTS: dict[str, int] = {
    "token_price": 50,
    "token_price_sol": 10,
    "token_metadata": 10,
    "token_pairs": 50,
    "token_score": 100,
    "token_score_historical": 150,
    "token_top_traders": 50,
    "token_snipers": 50,
    "token_holders": 50,
    "token_holders_historical": 50,
    "token_owners": 50,
    "token_top_holders": 50,
    "token_swaps": 50,
    "token_stats": 50,
    "token_analytics": 80,
    "pair_stats": 100,
    "search_tokens": 150,
    "trending_tokens": 150,
    "filtered_tokens": 150,
    "graduated_by_exchange": 50,
    "new_by_exchange": 50,
    "bonding_status": 20,
    "pumpfun_new": 50,
    "pumpfun_bonding": 50,
    "pumpfun_graduated": 50,
    "wallet_insights": 100,
    "wallet_swaps": 50,
    "wallet_history": 150,
    "wallet_profitability_summary": 30,
    "wallet_profitability": 50,
    "wallet_active_chains": 50,
    "wallet_labels": 50,
    "wallet_defi_summary": 5000,
    "wallet_defi_positions": 5000,
    "entity_search": 50,
    "entity_by_id": 50,
    "entity_categories": 10,
    "volume_by_chain": 150,
    "volume_by_category": 150,
    "global_market_cap": 200,
    "top_coins_by_market_cap": 200,
    "btc_blocks": 50,
    "btc_transactions": 50,
    "btc_address_stats": 100,
    "streams_webhook": 0,
    "datafeeds_sql": 0,
    "unknown": 50,
}


# ─────────────────────────────────────────────────────────────────────────────
# Budget State
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class CUBudgetState:
    """Tracks CU consumption for the current billing cycle."""
    month_start_ts: float = field(default_factory=lambda: time.time())
    total_consumed: int = 0
    consumed_by_category: dict[str, int] = field(default_factory=dict)
    cycle_count: int = 0
    last_reset_ts: float = field(default_factory=lambda: time.time())
    throttle_mode: str = "NORMAL"  # NORMAL | CONSERVATIVE | EMERGENCY | EXHAUSTED
    day_key: str = ""              # YYYY-MM-DD UTC
    daily_consumed: int = 0
    last_updated_ts: float = field(default_factory=lambda: time.time())
    blocked_calls: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "CUBudgetState":
        state = cls()
        if not isinstance(d, dict):
            return state
        state.month_start_ts = float(d.get("month_start_ts") or time.time())
        state.total_consumed = max(0, int(d.get("total_consumed") or 0))
        cats = d.get("consumed_by_category") or {}
        state.consumed_by_category = {
            str(k): max(0, int(v or 0)) for k, v in cats.items()
        } if isinstance(cats, dict) else {}
        state.cycle_count = max(0, int(d.get("cycle_count") or 0))
        state.last_reset_ts = float(d.get("last_reset_ts") or time.time())
        mode = str(d.get("throttle_mode") or "NORMAL").upper()
        if mode not in ("NORMAL", "CONSERVATIVE", "EMERGENCY", "EXHAUSTED"):
            mode = "NORMAL"
        state.throttle_mode = mode
        state.day_key = str(d.get("day_key") or "")
        state.daily_consumed = max(0, int(d.get("daily_consumed") or 0))
        state.last_updated_ts = float(d.get("last_updated_ts") or time.time())
        state.blocked_calls = max(0, int(d.get("blocked_calls") or 0))
        return state


def _utc_day_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _days_in_current_month() -> int:
    now = datetime.now(timezone.utc)
    return monthrange(now.year, now.month)[1]


def _days_remaining_in_month() -> int:
    now = datetime.now(timezone.utc)
    dim = monthrange(now.year, now.month)[1]
    return max(1, dim - now.day + 1)


# ─────────────────────────────────────────────────────────────────────────────
# Budget Manager
# ─────────────────────────────────────────────────────────────────────────────
class MoralisCUBudgetManager:
    """
    Singleton that tracks and enforces Moralis CU budget.
    Thread-safe for concurrent scanner/enrichment calls.
    """

    def __init__(self):
        self._state = CUBudgetState()
        self._load()
        self._check_monthly_reset()
        self._check_daily_reset()
        self._update_throttle_mode()
        self._save()  # snapshot for dashboard

    def _load(self) -> None:
        try:
            BUDGET_FILE.parent.mkdir(parents=True, exist_ok=True)
            if BUDGET_FILE.exists():
                with open(BUDGET_FILE) as f:
                    data = json.load(f)
                self._state = CUBudgetState.from_dict(data)
                logger.info(
                    f"CUBudget: Loaded — consumed={self._state.total_consumed:,} CU "
                    f"/ {MONTHLY_CU_BUDGET:,} | mode={self._state.throttle_mode}"
                )
        except Exception as e:
            logger.warning(f"CUBudget: Could not load budget state: {e}")
            self._state = CUBudgetState()

    def _save(self) -> None:
        """Persist budget state + dashboard snapshot."""
        self._state.last_updated_ts = time.time()
        try:
            BUDGET_FILE.parent.mkdir(parents=True, exist_ok=True)
            payload = self._state.to_dict()
            tmp = BUDGET_FILE.with_suffix(".tmp")
            with open(tmp, "w") as f:
                json.dump(payload, f, indent=2)
            tmp.replace(BUDGET_FILE)
        except Exception as e:
            logger.debug(f"CUBudget: Could not save budget state: {e}")
        self._write_dashboard_snapshot()

    def _write_dashboard_snapshot(self) -> None:
        """Write a UI-friendly snapshot (safe for Streamlit process)."""
        try:
            snap = self.get_status()
            DASHBOARD_SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
            tmp = DASHBOARD_SNAPSHOT.with_suffix(".tmp")
            with open(tmp, "w") as f:
                json.dump(snap, f, indent=2, default=str)
            tmp.replace(DASHBOARD_SNAPSHOT)
        except Exception as e:
            logger.debug(f"CUBudget: dashboard snapshot failed: {e}")

    def _check_monthly_reset(self) -> None:
        now = datetime.now(timezone.utc)
        try:
            month_start = datetime.fromtimestamp(self._state.month_start_ts, tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            month_start = now
        if now.month != month_start.month or now.year != month_start.year:
            logger.info(
                f"CUBudget: Monthly reset — previous consumption: "
                f"{self._state.total_consumed:,} CU"
            )
            self._state = CUBudgetState(
                month_start_ts=time.time(),
                day_key=_utc_day_key(),
            )

    def _check_daily_reset(self) -> None:
        today = _utc_day_key()
        if self._state.day_key != today:
            self._state.day_key = today
            self._state.daily_consumed = 0

    def record(self, endpoint: str, count: int = 1) -> None:
        cu_cost = CU_COSTS.get(endpoint, 50) * max(1, int(count))
        self.record_raw(endpoint, cu_cost)

    def record_raw(self, endpoint: str, cu_cost: int) -> None:
        """Record exact CU from response header x-request-weight."""
        try:
            cost = int(cu_cost)
        except (TypeError, ValueError):
            return
        if cost <= 0:
            return
        with BUDGET_LOCK:
            self._check_monthly_reset()
            self._check_daily_reset()
            self._state.total_consumed += cost
            self._state.daily_consumed += cost
            key = str(endpoint or "unknown")
            self._state.consumed_by_category[key] = (
                self._state.consumed_by_category.get(key, 0) + cost
            )
            self._update_throttle_mode()
            # Save often near budget; less often when healthy
            remaining_pct = self.get_remaining_pct()
            should_save = (
                remaining_pct < 0.30
                or self._state.total_consumed % 500 < cost
                or cost >= 500
            )
            if should_save:
                self._save()

    def adjust(self, delta: int) -> None:
        """Correct registry estimate vs live header weight."""
        try:
            d = int(delta)
        except (TypeError, ValueError):
            return
        if not d:
            return
        with BUDGET_LOCK:
            self._state.total_consumed = max(0, self._state.total_consumed + d)
            self._state.daily_consumed = max(0, self._state.daily_consumed + d)
            self._update_throttle_mode()

    def _daily_allowance(self) -> float:
        """Max CU we should spend today to pace through the month."""
        if MONTHLY_CU_BUDGET <= 0:
            return 0.0
        remaining = max(0, MONTHLY_CU_BUDGET - self._state.total_consumed)
        days_left = _days_remaining_in_month()
        # Base share of remaining + small burst headroom
        return (remaining / days_left) * DAILY_PACE_BURST

    def _update_throttle_mode(self) -> None:
        """Update throttle mode based on remaining budget + daily pace."""
        if MONTHLY_CU_BUDGET <= 0:
            new_mode = "EXHAUSTED"
        else:
            remaining = MONTHLY_CU_BUDGET - self._state.total_consumed
            remaining_pct = remaining / MONTHLY_CU_BUDGET
            if remaining <= 0 or remaining_pct <= 0:
                new_mode = "EXHAUSTED"
            elif remaining_pct < SAFETY_BUFFER_PCT:
                new_mode = "EMERGENCY"
            elif remaining_pct < CONSERVATIVE_PCT:
                new_mode = "CONSERVATIVE"
            else:
                # Daily pace: if already over today's allowance → CONSERVATIVE
                daily_cap = self._daily_allowance()
                if daily_cap > 0 and self._state.daily_consumed >= daily_cap:
                    new_mode = "CONSERVATIVE"
                else:
                    new_mode = "NORMAL"

                # Forecast overspend → tighten early
                days_elapsed = max(
                    1,
                    (
                        datetime.now(timezone.utc)
                        - datetime.fromtimestamp(self._state.month_start_ts, tz=timezone.utc)
                    ).days,
                )
                if days_elapsed >= 2 and self._state.total_consumed > 0:
                    daily_burn = self._state.total_consumed / days_elapsed
                    forecast = daily_burn * _days_in_current_month()
                    if forecast > MONTHLY_CU_BUDGET and remaining_pct < 0.50:
                        new_mode = "CONSERVATIVE" if new_mode == "NORMAL" else new_mode

        if new_mode != self._state.throttle_mode:
            logger.warning(
                f"CUBudget: Throttle {self._state.throttle_mode} → {new_mode} | "
                f"used={self._state.total_consumed:,}/{MONTHLY_CU_BUDGET:,} CU | "
                f"daily={self._state.daily_consumed:,}"
            )
            self._state.throttle_mode = new_mode

    def _effective_mode(self) -> str:
        """
        Compute throttle mode from current counters without mutating state.
        Always at least as restrictive as stored mode if stored is tighter
        due to same-day pace (handled below).
        """
        if MONTHLY_CU_BUDGET <= 0:
            return "EXHAUSTED"
        remaining = MONTHLY_CU_BUDGET - self._state.total_consumed
        if remaining <= 0:
            return "EXHAUSTED"
        remaining_pct = remaining / MONTHLY_CU_BUDGET
        if remaining_pct < SAFETY_BUFFER_PCT:
            return "EMERGENCY"
        if remaining_pct < CONSERVATIVE_PCT:
            return "CONSERVATIVE"
        daily_cap = self._daily_allowance()
        if daily_cap > 0 and self._state.daily_consumed >= daily_cap:
            return "CONSERVATIVE"
        return "NORMAL"

    def can_afford(self, endpoint: str, count: int = 1) -> bool:
        """
        Hard budget gate. Returns False if the call would violate monthly or
        throttle policy. Fail closed on invalid config.

        Does not loosen throttle mode as a side effect — mode is updated on
        record() / init only (via _update_throttle_mode).
        """
        try:
            with BUDGET_LOCK:
                self._check_monthly_reset()
                self._check_daily_reset()

                if MONTHLY_CU_BUDGET <= 0:
                    self._state.blocked_calls += 1
                    return False

                cu_cost = int(CU_COSTS.get(endpoint, 50)) * max(1, int(count))
                remaining = MONTHLY_CU_BUDGET - self._state.total_consumed

                # HARD STOP: never exceed monthly soft cap
                if remaining <= 0:
                    self._state.blocked_calls += 1
                    self._state.throttle_mode = "EXHAUSTED"
                    return False
                if cu_cost > remaining:
                    # This call alone would overspend — block it, but leave budget
                    # open for cheaper calls that still fit.
                    self._state.blocked_calls += 1
                    return False

                # Effective mode = max(stored, recomputed) by severity
                rank = {"NORMAL": 0, "CONSERVATIVE": 1, "EMERGENCY": 2, "EXHAUSTED": 3}
                computed = self._effective_mode()
                stored = self._state.throttle_mode
                mode = computed if rank.get(computed, 0) >= rank.get(stored, 0) else stored
                # Keep stored mode in sync if we tightened
                if rank.get(mode, 0) > rank.get(stored, 0):
                    self._state.throttle_mode = mode

                if mode == "EXHAUSTED":
                    self._state.blocked_calls += 1
                    return False

                if mode == "EMERGENCY":
                    allowed = cu_cost <= EMERGENCY_MAX_CU
                    if not allowed:
                        self._state.blocked_calls += 1
                    return allowed

                if mode == "CONSERVATIVE":
                    daily_cap = self._daily_allowance()
                    if daily_cap > 0 and self._state.daily_consumed >= daily_cap:
                        allowed = cu_cost <= EMERGENCY_MAX_CU
                    else:
                        allowed = cu_cost <= CONSERVATIVE_MAX_CU
                    if not allowed:
                        self._state.blocked_calls += 1
                    return allowed

                # NORMAL — still respect daily pace for expensive calls
                daily_cap = self._daily_allowance()
                if (
                    daily_cap > 0
                    and self._state.daily_consumed >= daily_cap
                    and cu_cost > EMERGENCY_MAX_CU
                ):
                    self._state.blocked_calls += 1
                    return False

                return True
        except Exception as e:
            logger.warning(f"CUBudget: can_afford fail-closed ({endpoint}): {e}")
            return False

    def get_remaining_budget(self) -> int:
        return max(0, MONTHLY_CU_BUDGET - self._state.total_consumed)

    def get_remaining_pct(self) -> float:
        if MONTHLY_CU_BUDGET <= 0:
            return 0.0
        return max(0.0, 1.0 - (self._state.total_consumed / MONTHLY_CU_BUDGET))

    def get_cycle_budget(self) -> float:
        remaining_cu = self.get_remaining_budget()
        days_remaining = _days_remaining_in_month()
        daily_remaining = remaining_cu / days_remaining
        return daily_remaining / CYCLES_PER_DAY

    def get_status(self) -> dict:
        """Full status for dashboard/logging."""
        remaining = self.get_remaining_budget()
        remaining_pct = self.get_remaining_pct()
        now = datetime.now(timezone.utc)
        try:
            month_start = datetime.fromtimestamp(self._state.month_start_ts, tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            month_start = now
        days_elapsed = max(1, (now - month_start).days)
        days_in_month = _days_in_current_month()
        days_remaining = _days_remaining_in_month()
        daily_burn_rate = self._state.total_consumed / days_elapsed
        forecast_eom = daily_burn_rate * days_in_month
        used_pct = round((1.0 - remaining_pct) * 100, 1) if MONTHLY_CU_BUDGET > 0 else 100.0
        daily_cap = self._daily_allowance()

        health = "healthy"
        if self._state.throttle_mode == "EXHAUSTED" or remaining <= 0:
            health = "exhausted"
        elif self._state.throttle_mode == "EMERGENCY":
            health = "critical"
        elif self._state.throttle_mode == "CONSERVATIVE" or forecast_eom > MONTHLY_CU_BUDGET:
            health = "warning"

        return {
            "monthly_budget": MONTHLY_CU_BUDGET,
            "total_consumed": self._state.total_consumed,
            "remaining_cu": remaining,
            "remaining_pct": round(remaining_pct * 100, 1),
            "used_pct": used_pct,
            "throttle_mode": self._state.throttle_mode,
            "health": health,
            "daily_consumed": self._state.daily_consumed,
            "daily_allowance": round(daily_cap, 0),
            "daily_burn_rate": round(daily_burn_rate, 0),
            "forecast_eom_consumption": round(forecast_eom, 0),
            "forecast_over_budget": bool(MONTHLY_CU_BUDGET > 0 and forecast_eom > MONTHLY_CU_BUDGET),
            "cycle_budget": round(self.get_cycle_budget(), 0),
            "days_elapsed": days_elapsed,
            "days_remaining": days_remaining,
            "blocked_calls": self._state.blocked_calls,
            "last_updated_ts": self._state.last_updated_ts,
            "last_updated_iso": datetime.fromtimestamp(
                self._state.last_updated_ts, tz=timezone.utc
            ).isoformat(),
            "top_consumers": sorted(
                self._state.consumed_by_category.items(),
                key=lambda x: x[1],
                reverse=True,
            )[:10],
            "within_budget": remaining > 0 and self._state.total_consumed <= MONTHLY_CU_BUDGET,
        }

    def log_status(self) -> None:
        status = self.get_status()
        logger.info(
            f"CUBudget: {status['total_consumed']:,}/{status['monthly_budget']:,} CU "
            f"({status['used_pct']:.1f}% used) | Mode: {status['throttle_mode']} | "
            f"Daily: {status['daily_consumed']:,.0f}/{status['daily_allowance']:,.0f} | "
            f"EOM forecast: {status['forecast_eom_consumption']:,.0f}"
        )
        if status["forecast_over_budget"]:
            logger.warning(
                f"CUBudget: ⚠️ OVER BUDGET FORECAST — "
                f"projected {status['forecast_eom_consumption']:,.0f} vs "
                f"{MONTHLY_CU_BUDGET:,}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# Disk reader for dashboard (separate process from bot)
# ─────────────────────────────────────────────────────────────────────────────
def load_status_from_disk() -> dict:
    """
    Read CU status for Streamlit. Prefers dashboard snapshot; falls back to
    raw budget file + live recompute.
    """
    # Prefer snapshot written by bot
    for path in (DASHBOARD_SNAPSHOT, BUDGET_FILE):
        try:
            if path.exists():
                with open(path) as f:
                    data = json.load(f)
                if path == DASHBOARD_SNAPSHOT and "monthly_budget" in data:
                    return data
                if path == BUDGET_FILE:
                    # Recompute status from raw state without mutating singleton
                    state = CUBudgetState.from_dict(data)
                    mgr = MoralisCUBudgetManager.__new__(MoralisCUBudgetManager)
                    mgr._state = state
                    return mgr.get_status()
        except Exception:
            continue
    # Live singleton fallback
    try:
        return cu_budget.get_status()
    except Exception:
        return {
            "monthly_budget": MONTHLY_CU_BUDGET,
            "total_consumed": 0,
            "remaining_cu": MONTHLY_CU_BUDGET,
            "remaining_pct": 100.0,
            "used_pct": 0.0,
            "throttle_mode": "UNKNOWN",
            "health": "unknown",
            "within_budget": True,
            "top_consumers": [],
            "daily_consumed": 0,
            "daily_allowance": 0,
            "forecast_eom_consumption": 0,
            "forecast_over_budget": False,
            "blocked_calls": 0,
            "days_remaining": _days_remaining_in_month(),
            "last_updated_iso": "",
        }


# ─────────────────────────────────────────────────────────────────────────────
# Singleton
# ─────────────────────────────────────────────────────────────────────────────
cu_budget = MoralisCUBudgetManager()


# ─────────────────────────────────────────────────────────────────────────────
# Decorator
# ─────────────────────────────────────────────────────────────────────────────
def track_cu(endpoint: str, count: int = 1):
    """
    Decorator: budget-gate + record after success.
    Usage:
        @track_cu("token_score")
        def get_token_score(address, chain):
            ...
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            if not cu_budget.can_afford(endpoint, count):
                logger.warning(
                    f"CUBudget: Skipping {endpoint} — mode={cu_budget._state.throttle_mode}"
                )
                return None
            result = func(*args, **kwargs)
            if result is not None:
                cu_budget.record(endpoint, count)
            return result
        wrapper.__name__ = getattr(func, "__name__", "wrapped")
        wrapper.__doc__ = getattr(func, "__doc__", None)
        return wrapper
    return decorator


def is_expensive_call_allowed() -> bool:
    """True if medium+ enrichment (score/analytics tier) is allowed."""
    return cu_budget.can_afford("token_score")


def is_defi_call_allowed() -> bool:
    return cu_budget.can_afford("wallet_defi_positions")


def get_throttle_mode() -> str:
    return cu_budget._state.throttle_mode
