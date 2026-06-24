"""
data/providers/moralis_discovery.py — Moralis API wrapper for Discovery features.

Provides access to Trending Tokens, Top Gainers per Token, and Wallet Profitability Summary.
"""
import logging
import time
import threading
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

def get_trending_tokens(chain: str = "eth") -> List[dict]:
    """
    Fetch trending tokens.
    """
    if not _available():
        return []
    
    _rate_check(150)
    try:
        resp = get_session().get(
            f"{BASE_URL}/tokens/trending",
            headers=_headers(),
            params={"chain": chain},
            timeout=15.0
        )
        if resp.status_code == 200:
            data = resp.json()
            return data if isinstance(data, list) else data.get("result", [])
        return []
    except Exception as e:
        logger.error(f"Error fetching trending tokens: {e}")
        return []

def get_top_profitable_wallets(token_address: str, chain: str = "eth") -> List[dict]:
    """
    Fetch top profitable wallets for a specific token.
    """
    if not _available():
        return []
        
    _rate_check(50)
    try:
        resp = get_session().get(
            f"{BASE_URL}/erc20/{token_address}/top-gainers",
            headers=_headers(),
            params={"chain": chain},
            timeout=15.0
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("result", [])
        return []
    except Exception as e:
        logger.error(f"Error fetching top gainers for {token_address}: {e}")
        return []

def get_wallet_profitability_summary(wallet_address: str, chain: str = "eth") -> Optional[dict]:
    """
    Fetch profitability summary for a wallet.
    """
    if not _available():
        return None
        
    _rate_check(30)
    try:
        resp = get_session().get(
            f"{BASE_URL}/wallets/{wallet_address}/profitability/summary",
            headers=_headers(),
            params={"chain": chain},
            timeout=15.0
        )
        if resp.status_code == 200:
            return resp.json()
        return None
    except Exception as e:
        logger.error(f"Error fetching profitability for {wallet_address}: {e}")
        return None
