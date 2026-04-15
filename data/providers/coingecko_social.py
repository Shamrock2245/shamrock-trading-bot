"""
data/providers/coingecko_social.py — Free social sentiment provider using CoinGecko.

Replaces LunarCrush (which has no free API). Uses CoinGecko's free public API
to gauge social momentum and sentiment without requiring an API key.

Endpoints used:
  - GET /search/trending (Top 15 trending coins)
  - GET /search (Fuzzy match symbol to CoinGecko ID)
  - GET /coins/{id} (Community data: Twitter followers, Telegram users)

Rate limit: 10-30 req/min (free tier).
Cache: 15-minute TTL to conserve API calls.
"""

import logging
import time
from typing import Optional

from data.http_session import get_session
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

BASE_URL = "https://api.coingecko.com/api/v3"

# Cache structures
_trending_cache: list[dict] = []
_trending_cache_time: float = 0
_id_cache: dict[str, str] = {}  # symbol -> cg_id
_social_cache: dict[str, tuple[dict, float]] = {}  # cg_id -> (data, timestamp)

_CACHE_TTL = 900  # 15 minutes
_TRENDING_TTL = 300  # 5 minutes

# Rate limiting state
_request_times: list[float] = []
_MAX_REQUESTS_PER_MINUTE = 15  # Conservative for free tier


def _rate_limit():
    """Enforce 15 req/min limit for free tier."""
    global _request_times
    now = time.time()
    _request_times = [t for t in _request_times if now - t < 60]
    if len(_request_times) >= _MAX_REQUESTS_PER_MINUTE:
        wait_time = 60 - (now - _request_times[0])
        if wait_time > 0:
            logger.debug(f"CoinGecko: rate limiting, waiting {wait_time:.1f}s")
            time.sleep(wait_time)
    _request_times.append(now)


@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=2, min=2, max=10))
def _get(endpoint: str, params: dict = None) -> dict:
    """Make a GET request to CoinGecko API."""
    _rate_limit()
    url = f"{BASE_URL}{endpoint}"
    headers = {"Accept": "application/json"}
    resp = get_session().get(url, headers=headers, params=params, timeout=10)
    if resp.status_code == 429:
        logger.warning("CoinGecko: Rate limit hit (429), backing off...")
        time.sleep(10)
        resp.raise_for_status()
    resp.raise_for_status()
    return resp.json()


def get_trending_coins() -> list[dict]:
    """Fetch top 15 trending coins on CoinGecko."""
    global _trending_cache, _trending_cache_time
    now = time.time()
    if _trending_cache and (now - _trending_cache_time) < _TRENDING_TTL:
        return _trending_cache

    try:
        data = _get("/search/trending")
        coins = data.get("coins", [])
        _trending_cache = [c.get("item", {}) for c in coins]
        _trending_cache_time = now
        return _trending_cache
    except Exception as e:
        logger.debug(f"CoinGecko trending fetch failed: {e}")
        return _trending_cache


def _get_coin_id(symbol: str) -> Optional[str]:
    """Resolve a ticker symbol to a CoinGecko ID."""
    symbol_lower = symbol.lower()
    if symbol_lower in _id_cache:
        return _id_cache[symbol_lower]

    try:
        data = _get("/search", params={"query": symbol_lower})
        coins = data.get("coins", [])
        for coin in coins:
            if coin.get("symbol", "").lower() == symbol_lower:
                cg_id = coin.get("id")
                _id_cache[symbol_lower] = cg_id
                return cg_id
    except Exception as e:
        logger.debug(f"CoinGecko search failed for {symbol}: {e}")
    return None


def get_social_score(symbol: str) -> float:
    """
    Compute a 0–100 social sentiment score for a token using CoinGecko.
    
    Scoring logic:
      - Top 3 trending: 90
      - Top 15 trending: 75
      - High Twitter followers (>50k): +15
      - Moderate Twitter (>10k): +10
      - Base score: 30 (neutral)
    """
    score = 30.0  # Neutral base
    symbol_lower = symbol.lower()

    # 1. Check trending status (strongest signal)
    trending = get_trending_coins()
    for i, coin in enumerate(trending):
        if coin.get("symbol", "").lower() == symbol_lower:
            if i < 3:
                score = max(score, 90.0)
            else:
                score = max(score, 75.0)
            logger.debug(f"CoinGecko: {symbol} is trending #{i+1} -> score {score}")
            break

    # 2. Check community stats if not top trending
    if score < 75.0:
        cg_id = _get_coin_id(symbol)
        if cg_id:
            now = time.time()
            if cg_id in _social_cache and (now - _social_cache[cg_id][1]) < _CACHE_TTL:
                community_data = _social_cache[cg_id][0]
            else:
                try:
                    data = _get(
                        f"/coins/{cg_id}",
                        params={
                            "localization": "false",
                            "tickers": "false",
                            "market_data": "false",
                            "community_data": "true",
                            "developer_data": "false",
                            "sparkline": "false",
                        }
                    )
                    community_data = data.get("community_data", {})
                    _social_cache[cg_id] = (community_data, now)
                except Exception as e:
                    logger.debug(f"CoinGecko community data failed for {symbol}: {e}")
                    community_data = {}

            twitter_followers = community_data.get("twitter_followers", 0) or 0
            tg_users = community_data.get("telegram_channel_user_count", 0) or 0
            
            if twitter_followers > 50000 or tg_users > 20000:
                score = min(score + 20.0, 100.0)
            elif twitter_followers > 10000 or tg_users > 5000:
                score = min(score + 10.0, 100.0)
            elif twitter_followers > 1000:
                score = min(score + 5.0, 100.0)

    return score
