"""
data/providers/moralis_http.py — Shared Moralis HTTP client with live CU accounting.

Every Moralis REST call should go through moralis_get() / moralis_post() so we:
  1. Enforce the global RPS limiter (Business plan ~80 RPS, we target 60)
  2. Gate expensive endpoints against the monthly CU budget
  3. Read x-request-weight / X-Request-Weight from responses (actual CU cost)
  4. Persist usage into core.moralis_cu_budget

Live probes (2026-07-30) confirmed header shapes:
  EVM deep-index:  x-request-weight: "50"
  Solana gateway:  X-Request-Weight: "10"  (+ X-Operation-Id)

Sunset note (July 31 2026):
  Solana top-holders / pump.fun discovery / Solana token-score REST endpoints
  stop returning data. Prefer Data Feeds (0 CU) or free fallbacks — see
  moralis_datafeeds.py and the solana discovery fallbacks in moralis_solana.py.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from data.http_session import get_session
from data.providers.moralis_rate_limiter import rate_check, record_cu
from config import settings

logger = logging.getLogger(__name__)

MORALIS_API_KEY: str = getattr(settings, "MORALIS_API_KEY", "")

# Known CU costs when headers are missing (from docs + live probes)
DEFAULT_CU_BY_ENDPOINT: dict[str, int] = {
    "token_price": 50,
    "token_price_sol": 10,
    "token_score": 100,
    "token_score_historical": 150,
    "token_analytics": 80,
    "token_metadata": 10,
    "token_pairs": 50,
    "token_holders": 50,
    "token_holders_historical": 50,
    "token_owners": 50,
    "token_top_holders": 50,
    "token_top_traders": 50,
    "token_swaps": 50,
    "pair_stats": 100,
    "wallet_swaps": 50,
    "wallet_history": 150,
    "wallet_profitability": 50,
    "wallet_defi_summary": 5000,
    "wallet_defi_positions": 5000,
    "search_tokens": 150,
    "trending_tokens": 150,
    "filtered_tokens": 150,
    "graduated_by_exchange": 50,
    "new_by_exchange": 50,
    "bonding_status": 20,
    "pumpfun_new": 50,
    "pumpfun_bonding": 50,
    "pumpfun_graduated": 50,
    "entity_search": 50,
    "endpoint_weights": 1,
    "unknown": 50,
}

# Endpoints that die on July 31 2026 — never call REST after hard cutover
SUNSET_JULY_31_2026: frozenset[str] = frozenset({
    "solana_top_holders",
    "solana_holder_metrics",
    "solana_holders_historical",
    "evm_holders_historical",
    "pumpfun_new",
    "pumpfun_bonding",
    "pumpfun_graduated",
    "solana_bonding_status",
    "solana_token_score",
    "solana_token_score_historical",
})

# Hard cutover date (UTC date string). After this, REST calls for sunset keys are blocked.
_SUNSET_DATE = "2026-07-31"


def _headers() -> dict[str, str]:
    return {"accept": "application/json", "X-API-Key": MORALIS_API_KEY}


def available() -> bool:
    """False unless the global Moralis kill switch is explicitly enabled."""
    if not getattr(settings, "MORALIS_ENABLED", False):
        return False
    return bool(MORALIS_API_KEY)


def is_past_sunset() -> bool:
    """True once the July 31 2026 sunset has arrived (local/UTC day)."""
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return today >= _SUNSET_DATE


def is_sunset_blocked(endpoint_key: str) -> bool:
    """Block REST for sunsetting keys on/after cutover day."""
    if endpoint_key in SUNSET_JULY_31_2026 and is_past_sunset():
        return True
    return False


def _parse_request_weight(resp) -> int:
    """Extract CU cost from Moralis response headers."""
    for key in ("x-request-weight", "X-Request-Weight", "X-REQUEST-WEIGHT"):
        raw = resp.headers.get(key)
        if raw is not None:
            try:
                return max(0, int(float(str(raw).strip())))
            except (TypeError, ValueError):
                pass
    return 0


def _record_usage(endpoint_key: str, cu_cost: int) -> None:
    """Record CU into rate limiter + monthly budget enforcer."""
    if cu_cost <= 0:
        return
    try:
        record_cu(cu_cost)
    except Exception:
        pass
    try:
        from core.moralis_cu_budget import cu_budget
        # Record under endpoint key; budget manager multiplies by CU_COSTS —
        # we override by recording raw weight via a dedicated method if present.
        if hasattr(cu_budget, "record_raw"):
            cu_budget.record_raw(endpoint_key, cu_cost)
        else:
            # Fallback: record once; CU_COSTS may differ slightly from header
            cu_budget.record(endpoint_key, count=1)
            # Correct drift if header differs from registry estimate
            estimated = DEFAULT_CU_BY_ENDPOINT.get(endpoint_key, 50)
            if cu_cost != estimated and hasattr(cu_budget, "adjust"):
                cu_budget.adjust(cu_cost - estimated)
    except Exception as e:
        logger.debug(f"moralis_http: budget record failed: {e}")


def can_afford(endpoint_key: str) -> bool:
    """Budget gate — fail closed (block) on any error so we never overspend."""
    try:
        from core.moralis_cu_budget import cu_budget
        return bool(cu_budget.can_afford(endpoint_key))
    except Exception as e:
        logger.warning(f"moralis_http: budget check failed closed for {endpoint_key}: {e}")
        return False


def moralis_get(
    url: str,
    *,
    params: Optional[dict] = None,
    endpoint_key: str = "unknown",
    timeout: float = 15.0,
    require_budget: bool = True,
    allow_sunset: bool = False,
) -> Optional[Any]:
    """
    GET with rate limit + CU accounting.

    Returns parsed JSON on success, None on skip/error.
    """
    if not available():
        return None
    if not allow_sunset and is_sunset_blocked(endpoint_key):
        logger.debug(f"moralis_http: blocked sunset endpoint {endpoint_key}")
        return None
    if require_budget and not can_afford(endpoint_key):
        logger.debug(f"moralis_http: budget skip {endpoint_key}")
        return None

    rate_check()
    try:
        resp = get_session().get(
            url,
            headers=_headers(),
            params=params or {},
            timeout=timeout,
        )
        weight = _parse_request_weight(resp)
        if weight <= 0:
            weight = DEFAULT_CU_BY_ENDPOINT.get(endpoint_key, 50)
        _record_usage(endpoint_key, weight)

        if resp.status_code in (400, 402, 403, 404, 410, 429):
            logger.debug(
                f"moralis_http: {endpoint_key} HTTP {resp.status_code} "
                f"(cu={weight})"
            )
            return None
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.debug(f"moralis_http: {endpoint_key} error: {e}")
        return None


def moralis_post(
    url: str,
    *,
    json_body: Optional[dict] = None,
    params: Optional[dict] = None,
    endpoint_key: str = "unknown",
    timeout: float = 20.0,
    require_budget: bool = True,
) -> Optional[Any]:
    """POST with rate limit + CU accounting."""
    if not available():
        return None
    if require_budget and not can_afford(endpoint_key):
        logger.debug(f"moralis_http: budget skip {endpoint_key}")
        return None

    rate_check()
    try:
        resp = get_session().post(
            url,
            headers=_headers(),
            params=params or {},
            json=json_body or {},
            timeout=timeout,
        )
        weight = _parse_request_weight(resp)
        if weight <= 0:
            weight = DEFAULT_CU_BY_ENDPOINT.get(endpoint_key, 50)
        _record_usage(endpoint_key, weight)

        if resp.status_code in (400, 402, 403, 404, 410, 429):
            return None
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.debug(f"moralis_http: {endpoint_key} POST error: {e}")
        return None
