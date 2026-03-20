"""
data/providers/coingecko.py — CoinGecko API wrapper.

Provides market data, trending coins, and OHLCV for technical analysis.
Rate limit: 30 req/min (free), higher with Pro key.
"""

import logging
import time
from typing import Optional

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from config import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://api.coingecko.com/api/v3"
PRO_URL = "https://pro-api.coingecko.com/api/v3"
_last_request_time = 0.0
_MIN_INTERVAL = 2.1  # 30 req/min = 2s interval


def _rate_limit():
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)
    _last_request_time = time.time()


def _get_url() -> str:
    return PRO_URL if settings.COINGECKO_API_KEY else BASE_URL


def _headers() -> dict:
    if settings.COINGECKO_API_KEY:
        return {"x-cg-pro-api-key": settings.COINGECKO_API_KEY}
    return {}


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=3, max=20))
def _get(endpoint: str, params: dict = None) -> dict:
    _rate_limit()
    url = f"{_get_url()}{endpoint}"
    resp = requests.get(url, headers=_headers(), params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def get_trending_coins() -> list[dict]:
    """Get currently trending coins on CoinGecko."""
    try:
        data = _get("/search/trending")
        return data.get("coins", [])
    except Exception as e:
        logger.error(f"CoinGecko trending error: {e}")
        return []


def get_top_gainers(vs_currency: str = "usd", top_n: int = 50) -> list[dict]:
    """Get top gainers in the last 24 hours."""
    try:
        data = _get("/coins/markets", params={
            "vs_currency": vs_currency,
            "order": "percent_change_24h_desc",
            "per_page": top_n,
            "page": 1,
            "sparkline": "false",
            "price_change_percentage": "1h,24h,7d",
        })
        return data
    except Exception as e:
        logger.error(f"CoinGecko top gainers error: {e}")
        return []


def get_coin_ohlcv(coin_id: str, vs_currency: str = "usd", days: int = 7) -> list:
    """
    Get OHLCV data for a coin.
    Returns list of [timestamp, open, high, low, close, volume].
    """
    try:
        data = _get(f"/coins/{coin_id}/ohlc", params={
            "vs_currency": vs_currency,
            "days": days,
        })
        return data
    except Exception as e:
        logger.error(f"CoinGecko OHLCV error for {coin_id}: {e}")
        return []


def get_coin_market_data(coin_id: str) -> Optional[dict]:
    """Get full market data for a specific coin."""
    try:
        return _get(f"/coins/{coin_id}", params={
            "localization": "false",
            "tickers": "false",
            "market_data": "true",
            "community_data": "true",
            "developer_data": "false",
        })
    except Exception as e:
        logger.error(f"CoinGecko market data error for {coin_id}: {e}")
        return None


def get_microcap_gems(
    min_mcap: int = 100_000,
    max_mcap: int = 10_000_000,
    min_volume: int = 50_000,
) -> list[dict]:
    """
    Find microcap tokens with strong volume — potential breakouts.
    Filters: $100K–$10M market cap, >$50K daily volume.
    """
    try:
        data = _get("/coins/markets", params={
            "vs_currency": "usd",
            "order": "volume_desc",
            "per_page": 250,
            "page": 1,
            "sparkline": "false",
            "price_change_percentage": "1h,24h",
        })
        return [
            coin for coin in data
            if (coin.get("market_cap") or 0) >= min_mcap
            and (coin.get("market_cap") or 0) <= max_mcap
            and (coin.get("total_volume") or 0) >= min_volume
        ]
    except Exception as e:
        logger.error(f"CoinGecko microcap gems error: {e}")
        return []
