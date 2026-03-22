"""
data/providers/social_scoring.py — Real social signal scoring for gem candidates.

Aggregates signals from:
  1. DexScreener token profile (Twitter, Telegram, website links)
  2. LunarCrush API (social volume, galaxy score, alt rank)
  3. CoinGecko trending / community data
  4. Token metadata completeness (website, docs, socials present)

Score 0-100:
  - Social presence (links exist)     → 0-25 pts
  - LunarCrush galaxy score           → 0-35 pts
  - CoinGecko trending                → 0-20 pts
  - Community size / activity         → 0-20 pts

Caches results for 10 minutes.
"""

import logging
import time
from typing import Optional

import requests

from config import settings

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Cache
# ─────────────────────────────────────────────────────────────────────────────
_cache: dict[str, tuple[float, float]] = {}
_CACHE_TTL = 600  # 10 minutes


def _cached(key: str) -> Optional[float]:
    if key in _cache:
        ts, val = _cache[key]
        if time.time() - ts < _CACHE_TTL:
            return val
    return None


def _store(key: str, value: float) -> float:
    _cache[key] = (time.time(), value)
    return value


# ─────────────────────────────────────────────────────────────────────────────
# Social Presence Score (from DexScreener token profile data)
# ─────────────────────────────────────────────────────────────────────────────

def _score_social_presence(websites: list[str], socials: list[dict]) -> float:
    """
    Score based on what social links are present in the token profile.
    Max 25 points.
    """
    score = 0.0

    # Website presence
    if websites:
        score += 8.0

    # Social platforms
    social_types = {s.get("type", "").lower() for s in socials}
    if "twitter" in social_types:
        score += 8.0
    if "telegram" in social_types:
        score += 5.0
    if "discord" in social_types:
        score += 4.0

    return min(score, 25.0)


# ─────────────────────────────────────────────────────────────────────────────
# LunarCrush API
# ─────────────────────────────────────────────────────────────────────────────

def _get_lunarcrush_score(symbol: str) -> float:
    """
    Query LunarCrush for galaxy score and social volume.
    Returns 0-35 points.
    """
    api_key = settings.LUNARCRUSH_API_KEY
    if not api_key:
        return 0.0

    try:
        url = "https://lunarcrush.com/api4/public/coins/list/v1"
        headers = {"Authorization": f"Bearer {api_key}"}
        params = {"symbol": symbol.upper()}
        resp = requests.get(url, headers=headers, params=params, timeout=10)

        if resp.status_code != 200:
            return 0.0

        data = resp.json()
        coins = data.get("data", [])
        if not coins:
            return 0.0

        coin = coins[0]
        galaxy_score = float(coin.get("galaxy_score", 0) or 0)
        alt_rank = int(coin.get("alt_rank", 9999) or 9999)
        social_volume_24h = float(coin.get("social_volume_24h", 0) or 0)

        # Galaxy score is 0-100; normalize to 0-25 pts
        galaxy_pts = (galaxy_score / 100.0) * 25.0

        # Alt rank bonus: top 50 = 10 pts, top 200 = 5 pts
        rank_pts = 0.0
        if alt_rank <= 50:
            rank_pts = 10.0
        elif alt_rank <= 200:
            rank_pts = 5.0

        return min(galaxy_pts + rank_pts, 35.0)

    except Exception as e:
        logger.debug(f"LunarCrush error for {symbol}: {e}")
        return 0.0


# ─────────────────────────────────────────────────────────────────────────────
# CoinGecko Trending
# ─────────────────────────────────────────────────────────────────────────────

_trending_cache: tuple[float, set[str]] = (0.0, set())
_TRENDING_TTL = 300  # 5 min


def _get_trending_symbols() -> set[str]:
    """Fetch CoinGecko trending coins list (cached 5 min)."""
    global _trending_cache
    ts, symbols = _trending_cache
    if time.time() - ts < _TRENDING_TTL:
        return symbols

    try:
        url = "https://api.coingecko.com/api/v3/search/trending"
        headers = {}
        if settings.COINGECKO_API_KEY:
            headers["x-cg-demo-api-key"] = settings.COINGECKO_API_KEY
        resp = requests.get(url, headers=headers, timeout=10)
        data = resp.json()
        coins = data.get("coins", [])
        trending = {c["item"]["symbol"].upper() for c in coins if c.get("item")}
        _trending_cache = (time.time(), trending)
        return trending
    except Exception as e:
        logger.debug(f"CoinGecko trending error: {e}")
        return set()


def _get_coingecko_score(symbol: str) -> float:
    """
    Score based on CoinGecko trending list.
    Returns 0-20 points.
    """
    try:
        trending = _get_trending_symbols()
        if symbol.upper() in trending:
            return 20.0
    except Exception as e:
        logger.debug(f"CoinGecko score error for {symbol}: {e}")
    return 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Community Activity (from DexScreener transaction data proxy)
# ─────────────────────────────────────────────────────────────────────────────

def _score_community_activity(
    buys_1h: int,
    sells_1h: int,
    volume_1h: float,
    market_cap: float,
) -> float:
    """
    Score community activity based on transaction counts and volume/mcap ratio.
    Max 20 points.
    """
    score = 0.0

    # Buy/sell ratio: more buys than sells = bullish community
    total_txns = buys_1h + sells_1h
    if total_txns > 0:
        buy_ratio = buys_1h / total_txns
        if buy_ratio >= 0.65:
            score += 8.0
        elif buy_ratio >= 0.55:
            score += 5.0
        elif buy_ratio >= 0.45:
            score += 2.0

    # Transaction count: >100/hr = active community
    if total_txns >= 200:
        score += 7.0
    elif total_txns >= 100:
        score += 5.0
    elif total_txns >= 50:
        score += 3.0
    elif total_txns >= 20:
        score += 1.0

    # Volume/market cap ratio: >5% hourly = high community engagement
    if market_cap > 0 and volume_1h > 0:
        vol_mcap_ratio = volume_1h / market_cap
        if vol_mcap_ratio >= 0.10:
            score += 5.0
        elif vol_mcap_ratio >= 0.05:
            score += 3.0
        elif vol_mcap_ratio >= 0.02:
            score += 1.0

    return min(score, 20.0)


# ─────────────────────────────────────────────────────────────────────────────
# Main scoring function
# ─────────────────────────────────────────────────────────────────────────────

def get_social_score(
    symbol: str,
    websites: list[str],
    socials: list[dict],
    buys_1h: int = 0,
    sells_1h: int = 0,
    volume_1h: float = 0.0,
    market_cap: float = 0.0,
    is_boosted: bool = False,
    boost_amount: float = 0.0,
) -> float:
    """
    Compute a 0-100 social score for a token.

    Args:
        symbol: Token symbol (e.g. "PEPE")
        websites: List of website URLs from DexScreener profile
        socials: List of social dicts from DexScreener profile
        buys_1h: Buy transactions in last 1 hour
        sells_1h: Sell transactions in last 1 hour
        volume_1h: USD volume in last 1 hour
        market_cap: Token market cap in USD
        is_boosted: Whether token is currently boosted on DexScreener
        boost_amount: Amount of boost (higher = more community investment)

    Returns:
        Float score 0-100
    """
    cache_key = f"social:{symbol.upper()}"
    cached = _cached(cache_key)
    if cached is not None:
        # Still apply dynamic community score on top of cached base
        community_score = _score_community_activity(buys_1h, sells_1h, volume_1h, market_cap)
        return min(cached + community_score * 0.3, 100.0)

    # 1. Social presence (static data from DexScreener profile)
    presence_score = _score_social_presence(websites, socials)

    # 2. LunarCrush (cached separately)
    lunar_score = _get_lunarcrush_score(symbol)

    # 3. CoinGecko trending
    cg_score = _get_coingecko_score(symbol)

    # 4. Community activity (dynamic — not cached)
    community_score = _score_community_activity(buys_1h, sells_1h, volume_1h, market_cap)

    # 5. DexScreener boost bonus (community investing in visibility = signal)
    boost_bonus = 0.0
    if is_boosted:
        boost_bonus = min(boost_amount / 100.0 * 5.0, 10.0)  # Max 10 pts

    total = presence_score + lunar_score + cg_score + community_score + boost_bonus

    # Cache the static components (not community score)
    static_score = presence_score + lunar_score + cg_score + boost_bonus
    _store(cache_key, static_score)

    logger.debug(
        f"Social score {symbol}: presence={presence_score:.0f} lunar={lunar_score:.0f} "
        f"cg={cg_score:.0f} community={community_score:.0f} boost={boost_bonus:.0f} "
        f"total={total:.1f}"
    )

    return min(total, 100.0)
