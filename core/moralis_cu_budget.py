"""
core/moralis_cu_budget.py — Moralis Compute Unit (CU) Budget Enforcer

Tracks, forecasts, and enforces Moralis API CU consumption to stay within
the monthly subscription limit.

Strategy:
  - Track CUs consumed per endpoint category in a rolling 30-day window
  - Forecast end-of-month consumption based on current burn rate
  - Automatically throttle expensive endpoints when approaching budget
  - Provide a per-scan-cycle CU budget that adapts to remaining allowance

Endpoint CU Costs (reference):
  Cheap (1–50 CU):
    - Token price:                   5 CU
    - Token metadata:               10 CU
    - Entity categories:            10 CU
    - Token pairs:                  10 CU
    - Entity search:                50 CU
    - Entity by ID:                 50 CU

  Medium (100–500 CU):
    - Wallet insights:              30 CU
    - Wallet swaps:                 50 CU
    - Token score:                 100 CU
    - Volume by chain:             150 CU
    - Volume by category:          150 CU
    - Global market cap:           200 CU
    - Top coins by market cap:     200 CU
    - Wallet profitability summary: 100 CU
    - Wallet profitability:        100 CU
    - Wallet active chains:         50 CU

  Expensive (1000+ CU):
    - Token top traders:          1000 CU
    - Token snipers:              1000 CU
    - Wallet DeFi summary:        5000 CU
    - Wallet DeFi positions:      5000 CU

Monthly Budget Tiers (based on Moralis plan):
  - Starter:    25,000 CU/month
  - Growth:    100,000 CU/month  ← Most common
  - Business:  500,000 CU/month
  - Enterprise: Unlimited

Default assumption: Growth plan (100,000 CU/month)
"""

from __future__ import annotations

import json
import logging
import threading
import time
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
BUDGET_LOCK = threading.Lock()

# Monthly CU budget — set via MORALIS_MONTHLY_CU_BUDGET in settings
MONTHLY_CU_BUDGET: int = getattr(settings, "MORALIS_MONTHLY_CU_BUDGET", 100_000)

# Safety buffer — stop expensive calls at this % of budget remaining
SAFETY_BUFFER_PCT: float = getattr(settings, "MORALIS_SAFETY_BUFFER_PCT", 0.15)  # 15%

# Per-scan-cycle CU budget (auto-calculated but can be overridden)
# Default: budget / 30 days / 48 cycles per day = budget per cycle
CYCLES_PER_DAY = 48  # 30-min cycles
DAILY_BUDGET = MONTHLY_CU_BUDGET / 30
CYCLE_BUDGET = DAILY_BUDGET / CYCLES_PER_DAY


# ─────────────────────────────────────────────────────────────────────────────
# CU Cost Registry
# ─────────────────────────────────────────────────────────────────────────────
CU_COSTS: dict[str, int] = {
    # Token API
    "token_price": 5,
    "token_metadata": 10,
    "token_pairs": 10,
    "token_score": 100,
    "token_top_traders": 1000,
    "token_snipers": 1000,
    "token_holders": 100,
    "token_swaps": 100,
    "token_stats": 50,
    "token_analytics": 200,
    # Wallet API
    "wallet_insights": 30,
    "wallet_swaps": 50,
    "wallet_profitability_summary": 100,
    "wallet_profitability": 100,
    "wallet_active_chains": 50,
    "wallet_labels": 50,
    "wallet_defi_summary": 5000,
    "wallet_defi_positions": 5000,
    # Entity API
    "entity_search": 50,
    "entity_by_id": 50,
    "entity_categories": 10,
    # Market Metrics API
    "volume_by_chain": 150,
    "volume_by_category": 150,
    "global_market_cap": 200,
    "top_coins_by_market_cap": 200,
    # Bitcoin API
    "btc_blocks": 50,
    "btc_transactions": 50,
    "btc_address_stats": 100,
    # Streams API (no CU cost — webhook-based)
    "streams_webhook": 0,
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
    throttle_mode: str = "NORMAL"  # NORMAL | CONSERVATIVE | EMERGENCY
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, d: dict) -> "CUBudgetState":
        state = cls()
        state.month_start_ts = d.get("month_start_ts", time.time())
        state.total_consumed = d.get("total_consumed", 0)
        state.consumed_by_category = d.get("consumed_by_category", {})
        state.cycle_count = d.get("cycle_count", 0)
        state.last_reset_ts = d.get("last_reset_ts", time.time())
        state.throttle_mode = d.get("throttle_mode", "NORMAL")
        return state


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
    
    def _load(self) -> None:
        """Load budget state from disk."""
        try:
            BUDGET_FILE.parent.mkdir(parents=True, exist_ok=True)
            if BUDGET_FILE.exists():
                with open(BUDGET_FILE) as f:
                    data = json.load(f)
                self._state = CUBudgetState.from_dict(data)
                logger.info(
                    f"CUBudget: Loaded state — consumed={self._state.total_consumed:,} CU "
                    f"/ {MONTHLY_CU_BUDGET:,} budget | mode={self._state.throttle_mode}"
                )
        except Exception as e:
            logger.warning(f"CUBudget: Could not load budget state: {e}")
    
    def _save(self) -> None:
        """Persist budget state to disk."""
        try:
            BUDGET_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(BUDGET_FILE, "w") as f:
                json.dump(self._state.to_dict(), f, indent=2)
        except Exception as e:
            logger.debug(f"CUBudget: Could not save budget state: {e}")
    
    def _check_monthly_reset(self) -> None:
        """Reset counters if we've crossed into a new billing month."""
        now = datetime.now(timezone.utc)
        month_start = datetime.fromtimestamp(self._state.month_start_ts, tz=timezone.utc)
        
        if now.month != month_start.month or now.year != month_start.year:
            logger.info(
                f"CUBudget: Monthly reset — previous consumption: {self._state.total_consumed:,} CU"
            )
            self._state = CUBudgetState()
            self._save()
    
    def record(self, endpoint: str, count: int = 1) -> None:
        """Record CU consumption for an endpoint."""
        cu_cost = CU_COSTS.get(endpoint, 50) * count
        with BUDGET_LOCK:
            self._state.total_consumed += cu_cost
            self._state.consumed_by_category[endpoint] = (
                self._state.consumed_by_category.get(endpoint, 0) + cu_cost
            )
            self._update_throttle_mode()
            # Save every 100 CU consumed to avoid too many disk writes
            if self._state.total_consumed % 100 < cu_cost:
                self._save()
    
    def _update_throttle_mode(self) -> None:
        """Update throttle mode based on remaining budget."""
        remaining_pct = 1.0 - (self._state.total_consumed / MONTHLY_CU_BUDGET)

        # Tightened thresholds (2026-06 budget crunch: 86M/100M used with 15 days left):
        # CONSERVATIVE kicks in at 25% remaining (was 30%) — blocks calls >= 500 CU
        # EMERGENCY kicks in at SAFETY_BUFFER_PCT (15%) — only allows calls < 50 CU
        if remaining_pct < SAFETY_BUFFER_PCT:
            new_mode = "EMERGENCY"
        elif remaining_pct < 0.25:  # Tightened from 0.30 — go conservative sooner
            new_mode = "CONSERVATIVE"
        else:
            new_mode = "NORMAL"
        
        if new_mode != self._state.throttle_mode:
            logger.warning(
                f"CUBudget: Throttle mode changed {self._state.throttle_mode} → {new_mode} | "
                f"Remaining: {remaining_pct:.1%} of {MONTHLY_CU_BUDGET:,} CU"
            )
            self._state.throttle_mode = new_mode
    
    def can_afford(self, endpoint: str, count: int = 1) -> bool:
        """
        Check if we can afford to make this API call.
        Returns False if we're in EMERGENCY mode and the call is expensive.
        """
        cu_cost = CU_COSTS.get(endpoint, 50) * count
        remaining = MONTHLY_CU_BUDGET - self._state.total_consumed
        
        if remaining <= 0:
            return False
        
        mode = self._state.throttle_mode
        
        if mode == "EMERGENCY":
            # Only allow cheap calls (< 50 CU) in emergency mode
            return cu_cost < 50
        elif mode == "CONSERVATIVE":
            # Block expensive calls (>= 500 CU) in conservative mode (tightened from 1000)
            return cu_cost < 500
        else:
            return True
    
    def get_remaining_budget(self) -> int:
        """Return remaining CU budget for this month."""
        return max(0, MONTHLY_CU_BUDGET - self._state.total_consumed)
    
    def get_remaining_pct(self) -> float:
        """Return remaining budget as a percentage (0.0–1.0)."""
        return max(0.0, 1.0 - (self._state.total_consumed / MONTHLY_CU_BUDGET))
    
    def get_cycle_budget(self) -> float:
        """
        Return the recommended CU budget for the current scan cycle.
        Adapts based on remaining monthly budget and days left.
        """
        now = datetime.now(timezone.utc)
        month_start = datetime.fromtimestamp(self._state.month_start_ts, tz=timezone.utc)
        days_elapsed = max(1, (now - month_start).days)
        days_in_month = 30
        days_remaining = max(1, days_in_month - days_elapsed)
        
        remaining_cu = self.get_remaining_budget()
        # Spread remaining CU evenly over remaining days and cycles
        daily_remaining = remaining_cu / days_remaining
        return daily_remaining / CYCLES_PER_DAY
    
    def get_status(self) -> dict:
        """Return full budget status for dashboard/logging."""
        remaining = self.get_remaining_budget()
        remaining_pct = self.get_remaining_pct()
        
        # Forecast end-of-month consumption
        now = datetime.now(timezone.utc)
        month_start = datetime.fromtimestamp(self._state.month_start_ts, tz=timezone.utc)
        days_elapsed = max(1, (now - month_start).days)
        daily_burn_rate = self._state.total_consumed / days_elapsed
        forecast_eom = daily_burn_rate * 30
        
        return {
            "monthly_budget": MONTHLY_CU_BUDGET,
            "total_consumed": self._state.total_consumed,
            "remaining_cu": remaining,
            "remaining_pct": round(remaining_pct * 100, 1),
            "throttle_mode": self._state.throttle_mode,
            "daily_burn_rate": round(daily_burn_rate, 0),
            "forecast_eom_consumption": round(forecast_eom, 0),
            "forecast_over_budget": forecast_eom > MONTHLY_CU_BUDGET,
            "cycle_budget": round(self.get_cycle_budget(), 0),
            "top_consumers": sorted(
                self._state.consumed_by_category.items(),
                key=lambda x: x[1],
                reverse=True,
            )[:10],
        }
    
    def log_status(self) -> None:
        """Log current budget status."""
        status = self.get_status()
        logger.info(
            f"CUBudget: {status['total_consumed']:,}/{status['monthly_budget']:,} CU used "
            f"({100 - status['remaining_pct']:.1f}%) | "
            f"Mode: {status['throttle_mode']} | "
            f"Daily burn: {status['daily_burn_rate']:,.0f} CU | "
            f"EOM forecast: {status['forecast_eom_consumption']:,.0f} CU"
        )
        if status["forecast_over_budget"]:
            logger.warning(
                f"CUBudget: ⚠️ OVER BUDGET FORECAST — "
                f"projected {status['forecast_eom_consumption']:,.0f} CU vs {MONTHLY_CU_BUDGET:,} budget"
            )


# ─────────────────────────────────────────────────────────────────────────────
# Singleton instance
# ─────────────────────────────────────────────────────────────────────────────
cu_budget = MoralisCUBudgetManager()


# ─────────────────────────────────────────────────────────────────────────────
# Decorator for automatic CU tracking
# ─────────────────────────────────────────────────────────────────────────────
def track_cu(endpoint: str, count: int = 1):
    """
    Decorator that automatically records CU consumption when a function is called.
    Also checks budget before calling and skips if in EMERGENCY mode.
    
    Usage:
        @track_cu("token_score")
        def get_token_score(address, chain):
            ...
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            if not cu_budget.can_afford(endpoint, count):
                logger.warning(
                    f"CUBudget: Skipping {endpoint} — budget mode={cu_budget._state.throttle_mode}"
                )
                return None
            result = func(*args, **kwargs)
            if result is not None:
                cu_budget.record(endpoint, count)
            return result
        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper
    return decorator


# ─────────────────────────────────────────────────────────────────────────────
# Convenience functions
# ─────────────────────────────────────────────────────────────────────────────
def is_expensive_call_allowed() -> bool:
    """Check if expensive calls (>= 1000 CU) are currently allowed."""
    return cu_budget.can_afford("token_top_traders")  # 1000 CU


def is_defi_call_allowed() -> bool:
    """Check if DeFi position calls (5000 CU) are currently allowed."""
    return cu_budget.can_afford("wallet_defi_positions")  # 5000 CU


def get_throttle_mode() -> str:
    """Get current throttle mode: NORMAL | CONSERVATIVE | EMERGENCY."""
    return cu_budget._state.throttle_mode
