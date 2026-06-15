"""
data/providers/moralis_rate_limiter.py — Shared Global Rate Limiter for Moralis Pro
===================================================================================
Moralis Pro Plan:
  - 80 requests per second (evaluated over a rolling 4-second window)
  - 100 million CU/month
  - Auto-scaling on CU overage (billed, not blocked)

PROBLEM SOLVED:
  Previously, each of the 10 Moralis modules had its own independent rate limiter
  set to 25 req/min (0.4 RPS per module). Combined throughput was capped at
  ~200 req/min (3.3 RPS) — that's 96% below the Pro limit of 4,800 req/min.

  This module replaces all per-module rate limiters with a single shared instance
  using a proper sliding window algorithm tuned for Pro-tier throughput.

BUDGET CONTROL:
  CU budget read from settings.MORALIS_MONTHLY_CU_BUDGET (set via .env).
  Current plan: 394M CU/month. Average endpoint costs ~50 CU.
  We set our ceiling at 60 RPS (75% of 80) to leave headroom and avoid overage.

  CU tracking: each call records its CU cost. If monthly CU budget approaches
  90%, we downshift to 20 RPS to prevent overage billing.

Usage:
  from data.providers.moralis_rate_limiter import rate_check, record_cu

  rate_check()         # Call before every Moralis API request
  record_cu(cost)      # Call after each request with the CU cost (from response headers)
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import deque

from config import settings

logger = logging.getLogger(__name__)

# ── Plan Constants (read from settings → .env for single source of truth) ─────
PRO_RPS_LIMIT = 60           # 75% of 80 RPS — leaves 20 RPS headroom
PRO_WINDOW_SECONDS = 4.0     # Moralis evaluates over a 4-second rolling window
PRO_MAX_IN_WINDOW = int(PRO_RPS_LIMIT * PRO_WINDOW_SECONDS)  # 240 calls per 4s window

# CU Budget Control — reads from settings.MORALIS_MONTHLY_CU_BUDGET (.env)
# to stay in sync with core/moralis_cu_budget.py
MONTHLY_CU_BUDGET: int = getattr(settings, "MORALIS_MONTHLY_CU_BUDGET", 100_000_000)
CU_BUDGET_WARNING_PCT = 0.70     # Downshift at 70% budget consumed
CU_BUDGET_CRITICAL_PCT = 0.85    # Hard throttle at 85% budget consumed
DOWNSHIFT_RPS = 20               # Reduced RPS when approaching budget limit
AVG_CU_PER_CALL = 100            # Conservative avg CU per call for auto-estimation

# ── State ─────────────────────────────────────────────────────────────────────
_lock = threading.Lock()
_timestamps: deque[float] = deque()  # Sliding window of request timestamps
_cu_used_this_month: float = 0.0
_cu_month: str = ""                  # "YYYY-MM" to track monthly reset
_total_calls: int = 0
_total_sleeps: int = 0
_total_sleep_seconds: float = 0.0

# Override via env for testing or emergency throttle
_env_rps = os.getenv("MORALIS_RPS_LIMIT", "")
if _env_rps:
    try:
        PRO_RPS_LIMIT = int(_env_rps)
        PRO_MAX_IN_WINDOW = int(PRO_RPS_LIMIT * PRO_WINDOW_SECONDS)
        logger.info(f"Moralis RPS override from env: {PRO_RPS_LIMIT} RPS")
    except ValueError:
        pass


def _current_month() -> str:
    return time.strftime("%Y-%m")


def _get_effective_limit() -> int:
    """Return the current effective requests-per-window limit, accounting for CU budget."""
    global _cu_used_this_month, _cu_month
    month = _current_month()
    if _cu_month != month:
        _cu_used_this_month = 0.0
        _cu_month = month

    # If record_cu() hasn't been called, estimate from call count
    cu_estimate = max(_cu_used_this_month, _total_calls * AVG_CU_PER_CALL)
    budget_pct = cu_estimate / MONTHLY_CU_BUDGET if MONTHLY_CU_BUDGET > 0 else 0
    if budget_pct >= CU_BUDGET_CRITICAL_PCT:
        return int(DOWNSHIFT_RPS * PRO_WINDOW_SECONDS * 0.5)  # 40 calls/4s
    elif budget_pct >= CU_BUDGET_WARNING_PCT:
        return int(DOWNSHIFT_RPS * PRO_WINDOW_SECONDS)  # 80 calls/4s
    return PRO_MAX_IN_WINDOW  # 240 calls/4s


def rate_check() -> None:
    """
    Global Moralis rate limiter. Call before EVERY Moralis API request.
    Uses a sliding window algorithm matching Moralis's 4-second evaluation window.
    Thread-safe via lock.
    """
    global _total_calls, _total_sleeps, _total_sleep_seconds
    with _lock:
        now = time.time()
        cutoff = now - PRO_WINDOW_SECONDS

        # Purge timestamps outside the window
        while _timestamps and _timestamps[0] < cutoff:
            _timestamps.popleft()

        effective_limit = _get_effective_limit()

        if len(_timestamps) >= effective_limit:
            # Window is full — sleep until the oldest timestamp exits the window
            oldest = _timestamps[0]
            sleep_for = (oldest + PRO_WINDOW_SECONDS) - now + 0.05  # 50ms buffer
            if sleep_for > 0:
                _total_sleeps += 1
                _total_sleep_seconds += sleep_for
                logger.debug(f"Moralis rate limit: sleeping {sleep_for:.2f}s "
                             f"({len(_timestamps)}/{effective_limit} in window)")
                time.sleep(sleep_for)
                # Re-purge after sleep
                now = time.time()
                cutoff = now - PRO_WINDOW_SECONDS
                while _timestamps and _timestamps[0] < cutoff:
                    _timestamps.popleft()

        _timestamps.append(now)
        _total_calls += 1


def record_cu(cu_cost: float) -> None:
    """
    Record CU usage from a Moralis API response.
    Call after each request with the CU cost (from x-moralis-compute-units header).
    """
    global _cu_used_this_month, _cu_month
    month = _current_month()
    with _lock:
        if _cu_month != month:
            _cu_used_this_month = 0.0
            _cu_month = month
        _cu_used_this_month += cu_cost


def get_stats() -> dict:
    """Return current rate limiter stats for health monitoring."""
    with _lock:
        now = time.time()
        cutoff = now - PRO_WINDOW_SECONDS
        active = sum(1 for t in _timestamps if t >= cutoff)
        effective_limit = _get_effective_limit()
        budget_pct = (_cu_used_this_month / MONTHLY_CU_BUDGET * 100) if MONTHLY_CU_BUDGET > 0 else 0

        cu_estimate = max(_cu_used_this_month, _total_calls * AVG_CU_PER_CALL)
        return {
            "calls_in_window": active,
            "window_limit": effective_limit,
            "effective_rps": round(active / PRO_WINDOW_SECONDS, 1) if active > 0 else 0,
            "max_rps": PRO_RPS_LIMIT,
            "total_calls": _total_calls,
            "total_sleeps": _total_sleeps,
            "total_sleep_seconds": round(_total_sleep_seconds, 2),
            "cu_used_this_month": round(cu_estimate, 0),
            "cu_budget_pct": round(cu_estimate / MONTHLY_CU_BUDGET * 100, 1) if MONTHLY_CU_BUDGET > 0 else 0,
            "cu_remaining": round(MONTHLY_CU_BUDGET - cu_estimate, 0),
            "mode": "critical" if (cu_estimate / MONTHLY_CU_BUDGET) >= CU_BUDGET_CRITICAL_PCT
                    else "warning" if (cu_estimate / MONTHLY_CU_BUDGET) >= CU_BUDGET_WARNING_PCT
                    else "normal",
        }
