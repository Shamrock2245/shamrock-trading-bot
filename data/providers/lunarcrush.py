"""
data/providers/lunarcrush.py — LunarCrush API v4 wrapper.

Provides social sentiment metrics: Galaxy Score, AltRank, social volume,
average sentiment, and engagement data.

Free tier: 100 requests/day, 4 requests/minute.
Requires LUNARCRUSH_API_KEY env var.

Endpoints used:
   - GET https://lunarcrush.com/api4/public/coins/{symbol}/v1
"""

import logging
import time
from typing import Optional

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

BASE_URL = "https://lunarcrush.com/api4/public"

# ── In-memory cache ──────────────────────────────────────────────────────────
_social_cache: dict[str, tuple[dict, float]] = {}  # symbol -> (data, timestamp)
_CACHE_TTL = 3600  # 1 hour — we only get 100 req/day, cache aggressively

# Rate limiter state
_request_times: list[float] = []  # Track last 4 request timestamps
_MAX_REQUESTS_PER_MINUTE = 4
_daily_count = 0
_daily_reset_time = 0.0
_MAX_DAILY_REQUESTS = 95  # Leave buffer from 100 limit


def _get_api_key() -> str:
    """Load API key from settings."""
    from config import settings
    key = getattr(settings, "LUNARCRUSH_API_KEY", "")
    if not key:
        import os
        key = os.getenv("LUNARCRUSH_API_KEY", "")
    return key


def _rate_limit():
    """Enforce 4 req/min and 100 req/day limits."""
    global _request_times, _daily_count, _daily_reset_time
    now = time.time()

    # Daily reset check
    if now - _daily_reset_time > 86400:
        _daily_count = 0
        _daily_reset_time = now

    if _daily_count >= _MAX_DAILY_REQUESTS:
        logger.warning("LunarCrush: daily request limit reached, returning cached/default data")
        raise RuntimeError("LunarCrush daily limit reached")

    # Per-minute rate limit
    _request_times = [t for t in _request_times if now - t < 60]
    if len(_request_times) >= _MAX_REQUESTS_PER_MINUTE:
        wait_time = 60 - (now - _request_times[0])
        if wait_time > 0:
            logger.debug(f"LunarCrush: rate limiting, waiting {wait_time:.1f}s")
            time.sleep(wait_time)

    _request_times.append(now)
    _daily_count += 1


@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=2, min=3, max=30))
def _get(endpoint: str) -> dict:
    """Make a GET request to LunarCrush API with auth header."""
    api_key = _get_api_key()
    if not api_key:
        raise RuntimeError("LUNARCRUSH_API_KEY not configured")

    _rate_limit()

    url = f"{BASE_URL}{endpoint}"
    headers = {"Authorization": f"Bearer {api_key}"}
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json()


def get_coin_social(symbol: str) -> Optional[dict]:
    """
    GET /coins/{symbol}/v1
    Returns social metrics for a token.

    Response includes:
        galaxy_score, alt_rank, social_volume, social_score,
        average_sentiment, social_dominance, market_cap,
        categories, engagements, posts_created
    """
    symbol_upper = symbol.upper()

    # Check cache
    if symbol_upper in _social_cache:
        data, cached_at = _social_cache[symbol_upper]
        if (time.time() - cached_at) < _CACHE_TTL:
            return data

    try:
        raw = _get(f"/coins/{symbol_upper}/v1")
        data = raw.get("data", raw)

        result = {
            "symbol": symbol_upper,
            "galaxy_score": float(data.get("galaxy_score", 0) or 0),
            "alt_rank": int(data.get("alt_rank", 0) or 0),
            "social_volume": int(data.get("social_volume", 0) or 0),
            "social_score": float(data.get("social_score", 0) or 0),
            "average_sentiment": float(data.get("average_sentiment", 0) or 0),
            "social_dominance": float(data.get("social_dominance", 0) or 0),
            "engagements": int(data.get("engagements", 0) or 0),
            "posts_created": int(data.get("posts_created", 0) or 0),
            "market_cap": float(data.get("market_cap", 0) or 0),
        }

        _social_cache[symbol_upper] = (result, time.time())
        logger.info(
            f"LunarCrush: {symbol_upper} → GalaxyScore={result['galaxy_score']}, "
            f"AltRank={result['alt_rank']}, SocialVol={result['social_volume']}"
        )
        return result

    except RuntimeError as e:
        if "daily limit" in str(e):
            # Return cached data if available, even if stale
            if symbol_upper in _social_cache:
                return _social_cache[symbol_upper][0]
            return None
        raise
    except Exception as e:
        logger.warning(f"LunarCrush: failed to fetch {symbol_upper}: {e}")
        # Return stale cache if available
        if symbol_upper in _social_cache:
            return _social_cache[symbol_upper][0]
        return None


def get_social_score(symbol: str) -> float:
    """
    Compute a 0–100 social sentiment score for a token.

    Scoring based on Galaxy Score (0–100 proprietary metric):
        Galaxy Score ≥ 70 → 90  (strong social momentum)
        Galaxy Score 50–69 → 70
        Galaxy Score 30–49 → 50
        Galaxy Score < 30  → 25
        AltRank top 50    → +10 bonus
        No data           → 30  (neutral)
    """
    api_key = _get_api_key()
    if not api_key:
        logger.debug("LunarCrush: no API key configured, returning neutral score")
        return 30.0

    data = get_coin_social(symbol)
    if not data:
        return 30.0  # Neutral — no data available

    galaxy = data.get("galaxy_score", 0)
    alt_rank = data.get("alt_rank", 0)

    # Base score from Galaxy Score
    if galaxy >= 70:
        score = 90.0
    elif galaxy >= 50:
        score = 70.0
    elif galaxy >= 30:
        score = 50.0
    elif galaxy > 0:
        score = 25.0
    else:
        return 30.0  # No Galaxy Score = neutral

    # AltRank bonus (lower rank = better)
    if 0 < alt_rank <= 50:
        score = min(score + 10, 100.0)
    elif 0 < alt_rank <= 100:
        score = min(score + 5, 100.0)

    return score


def get_daily_usage() -> dict:
    """Return current rate limit usage stats for monitoring."""
    return {
        "daily_requests_used": _daily_count,
        "daily_limit": _MAX_DAILY_REQUESTS,
        "cached_symbols": len(_social_cache),
    }
