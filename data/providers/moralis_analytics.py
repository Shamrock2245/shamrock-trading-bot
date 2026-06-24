"""
data/providers/moralis_analytics.py — Moralis API wrapper for Token Analytics.

Provides access to Token Analytics and Time-Series Token Analytics.
"""
import logging
import time
from typing import Any, List, Dict, Optional

from data.http_session import get_session
from config import settings
from data.providers.moralis_rate_limiter import rate_check as _rate_check

logger = logging.getLogger(__name__)

MORALIS_API_KEY = getattr(settings, "MORALIS_API_KEY", "")
BASE_URL = "https://deep-index.moralis.io/api/v2.2"

def _headers() -> dict:
    return {
        "accept": "application/json",
        "X-API-Key": MORALIS_API_KEY
    }

def _available() -> bool:
    return bool(MORALIS_API_KEY)

def get_token_analytics(token_address: str, chain: str = "eth") -> Optional[dict]:
    """
    Fetch analytics for a token (e.g., net volume, holders, liquidity).
    """
    if not _available():
        return None
    
    _rate_check(10)
    try:
        resp = get_session().get(
            f"{BASE_URL}/erc20/{token_address}/analytics",
            headers=_headers(),
            params={"chain": chain},
            timeout=10.0
        )
        if resp.status_code == 200:
            return resp.json()
        return None
    except Exception as e:
        logger.error(f"Error fetching token analytics for {token_address}: {e}")
        return None

def get_time_series_token_analytics(token_address: str, chain: str = "eth", limit: int = 10) -> List[dict]:
    """
    Fetch time-series analytics for a token to track trends over time.
    """
    if not _available():
        return []
        
    _rate_check(10)
    try:
        resp = get_session().get(
            f"{BASE_URL}/erc20/{token_address}/analytics/time-series",
            headers=_headers(),
            params={"chain": chain, "limit": limit},
            timeout=10.0
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("result", [])
        return []
    except Exception as e:
        logger.error(f"Error fetching time-series analytics for {token_address}: {e}")
        return []
