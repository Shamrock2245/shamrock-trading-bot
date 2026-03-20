"""
data/providers/dexscreener.py — DexScreener API wrapper.

Endpoints used:
  - /token-profiles/latest    → New token profiles
  - /token-boosts/latest      → Currently boosted tokens
  - /token-boosts/top         → Most boosted tokens
  - /dex/search               → Search by name/symbol
  - /dex/tokens/{addresses}   → Pairs for specific tokens
  - /dex/pairs/{chain}/{pair} → Detailed pair data

Rate limit: 60 req/min (free tier). Handled via tenacity retry.
"""

import logging
import time
from typing import Optional

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

BASE_URL = "https://api.dexscreener.com"
_last_request_time = 0.0
_MIN_REQUEST_INTERVAL = 1.0  # 60 req/min = 1 req/sec minimum spacing


def _rate_limit():
    """Simple rate limiter — enforces minimum interval between requests."""
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < _MIN_REQUEST_INTERVAL:
        time.sleep(_MIN_REQUEST_INTERVAL - elapsed)
    _last_request_time = time.time()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=15))
def _get(endpoint: str, params: dict = None) -> dict:
    """Make a GET request to DexScreener API."""
    _rate_limit()
    url = f"{BASE_URL}{endpoint}"
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def get_latest_token_profiles() -> list[dict]:
    """
    GET /token-profiles/latest
    Returns newest token profiles (new projects listing on DexScreener).
    """
    try:
        data = _get("/token-profiles/latest")
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"DexScreener latest profiles error: {e}")
        return []


def get_latest_boosts() -> list[dict]:
    """
    GET /token-boosts/latest
    Returns currently boosted tokens (paid visibility = community hype signal).
    """
    try:
        data = _get("/token-boosts/latest")
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"DexScreener latest boosts error: {e}")
        return []


def get_top_boosts() -> list[dict]:
    """
    GET /token-boosts/top
    Returns most boosted tokens (strongest community push).
    """
    try:
        data = _get("/token-boosts/top")
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"DexScreener top boosts error: {e}")
        return []


def search_pairs(query: str) -> list[dict]:
    """
    GET /dex/search?q={query}
    Search pairs by token name or symbol.
    """
    try:
        data = _get("/dex/search", params={"q": query})
        return data.get("pairs", [])
    except Exception as e:
        logger.error(f"DexScreener search error for '{query}': {e}")
        return []


def get_token_pairs(token_address: str) -> list[dict]:
    """
    GET /dex/tokens/{address}
    Get all DEX pairs for a specific token address.
    """
    try:
        data = _get(f"/dex/tokens/{token_address}")
        return data.get("pairs", [])
    except Exception as e:
        logger.error(f"DexScreener token pairs error for {token_address}: {e}")
        return []


def get_pair_data(chain_id: str, pair_address: str) -> Optional[dict]:
    """
    GET /dex/pairs/{chainId}/{pairAddress}
    Get detailed pair data: price, volume, liquidity, txns.
    """
    try:
        data = _get(f"/dex/pairs/{chain_id}/{pair_address}")
        pairs = data.get("pairs", [])
        return pairs[0] if pairs else None
    except Exception as e:
        logger.error(f"DexScreener pair data error: {e}")
        return None


def extract_gem_signals(pair: dict) -> dict:
    """
    Extract key signals from a DexScreener pair object for gem scoring.

    Returns a normalized dict with all fields needed by the scanner.
    """
    price_change = pair.get("priceChange", {})
    volume = pair.get("volume", {})
    txns = pair.get("txns", {})
    liquidity = pair.get("liquidity", {})
    info = pair.get("info", {})

    # Token age in hours
    created_at = pair.get("pairCreatedAt")
    age_hours = None
    if created_at:
        import time as t
        age_hours = (t.time() * 1000 - created_at) / (1000 * 3600)

    return {
        "chain_id": pair.get("chainId", ""),
        "dex_id": pair.get("dexId", ""),
        "pair_address": pair.get("pairAddress", ""),
        "base_token_address": pair.get("baseToken", {}).get("address", ""),
        "base_token_symbol": pair.get("baseToken", {}).get("symbol", ""),
        "base_token_name": pair.get("baseToken", {}).get("name", ""),
        "quote_token_symbol": pair.get("quoteToken", {}).get("symbol", ""),
        "price_usd": float(pair.get("priceUsd", 0) or 0),
        "price_change_5m": float(price_change.get("m5", 0) or 0),
        "price_change_1h": float(price_change.get("h1", 0) or 0),
        "price_change_6h": float(price_change.get("h6", 0) or 0),
        "price_change_24h": float(price_change.get("h24", 0) or 0),
        "volume_5m": float(volume.get("m5", 0) or 0),
        "volume_1h": float(volume.get("h1", 0) or 0),
        "volume_6h": float(volume.get("h6", 0) or 0),
        "volume_24h": float(volume.get("h24", 0) or 0),
        "buys_1h": int(txns.get("h1", {}).get("buys", 0) or 0),
        "sells_1h": int(txns.get("h1", {}).get("sells", 0) or 0),
        "liquidity_usd": float(liquidity.get("usd", 0) or 0),
        "market_cap": float(pair.get("marketCap", 0) or 0),
        "fdv": float(pair.get("fdv", 0) or 0),
        "age_hours": age_hours,
        "websites": [w.get("url") for w in info.get("websites", [])],
        "socials": info.get("socials", []),
        "is_boosted": False,  # Set by caller if from boost endpoint
        "boost_amount": 0,
        "url": pair.get("url", ""),
    }
