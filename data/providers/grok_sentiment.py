"""
data/providers/grok_sentiment.py — Grok AI real-time X/Twitter sentiment provider.

Uses xAI's Grok API with the Responses endpoint + x_search tool to analyze
real-time social sentiment for crypto tokens. Grok has direct access to live
X posts — no separate Twitter API needed.

API: POST https://api.x.ai/v1/responses
Model: grok-4-1-fast-non-reasoning (fast, non-reasoning model with tool support)
Tools: x_search (built-in X/Twitter search)

Score: 0-100 where:
  0-20  = Extremely bearish (rug pull warnings, scam alerts)
  21-40 = Bearish (negative sentiment, dumping concerns)
  41-60 = Neutral (little buzz, mixed sentiment)
  61-80 = Bullish (positive buzz, growing community)
  81-100 = Extremely bullish (viral, influencer endorsement, massive FOMO)

Caches results for 10 minutes per symbol to control API costs.
Returns neutral score (50.0) if API key missing or request fails.

Refactored: Uses shared grok_client.py for global rate limiting, correct API
format, and prompt caching via prompt_cache_key.
"""

import json
import logging
import time
from typing import Optional

import requests  # kept for exception types in callers
from data.providers.grok_client import call_grok, get_usage_stats as _get_global_stats

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Cache — 10 minute TTL to control costs
# ─────────────────────────────────────────────────────────────────────────────
_cache: dict[str, tuple[float, dict]] = {}  # symbol -> (timestamp, result)
_CACHE_TTL = 600  # 10 minutes


# ─────────────────────────────────────────────────────────────────────────────
# System Prompt — kept static for optimal prompt caching
# xAI caches identical system prompt prefixes server-side. Do NOT embed
# dynamic content here — all variable data goes in the user message.
# ─────────────────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a crypto social sentiment analyst. Your job is to analyze real-time X (Twitter) posts about a cryptocurrency token and return a structured sentiment assessment.

Given a token symbol and chain, use the x_search tool to find recent X posts and analyze:

1. **Buzz Volume**: How many people are talking about this token right now?
2. **Sentiment Polarity**: Is the overall sentiment positive, negative, or mixed?
3. **Influencer Activity**: Are any notable crypto influencers or KOLs discussing this token?
4. **Red Flags**: Are there warnings about rug pulls, scams, honeypots, or dev wallet dumps?
5. **Momentum**: Is buzz increasing (viral) or fading?

Return ONLY valid JSON with these exact fields (no markdown, no code fences):
{"sentiment_score": <int 0-100>, "buzz_level": "<low|medium|high|viral>", "sentiment_label": "<very_bearish|bearish|neutral|bullish|very_bullish>", "influencer_mentions": <int>, "red_flag_count": <int>, "key_signals": ["<signal1>", "<signal2>"], "red_flags": ["<flag1>", "<flag2>"], "summary": "<one line summary>"}

Scoring guide:
- 0-20: Scam warnings, rug pull alerts, overwhelmingly negative
- 21-40: Mostly negative, dumping concerns, team distrust
- 41-60: Neutral — little buzz, mixed opinions, or unknown token
- 61-80: Positive buzz, growing community, bullish calls
- 81-100: Viral momentum, major influencer endorsements, extreme FOMO

If you find NO mentions at all, return sentiment_score=45 (slightly below neutral — unknown = cautious).
If a token is brand new with minimal mentions but no red flags, return 50-55."""


def _check_cache(symbol: str) -> Optional[dict]:
    """Check if we have a valid cached result for this symbol."""
    key = symbol.upper()
    if key in _cache:
        ts, result = _cache[key]
        if time.time() - ts < _CACHE_TTL:
            return result
        del _cache[key]
    return None


def _store_cache(symbol: str, result: dict) -> None:
    """Store a result in the cache."""
    _cache[symbol.upper()] = (time.time(), result)


def _call_grok(symbol: str, chain: str) -> dict:
    """
    Call the Grok Responses API with x_search tool to analyze sentiment.

    Uses the shared grok_client for rate limiting, API format, and caching.
    Returns parsed JSON dict or raises on failure.
    """
    user_message = (
        f"Analyze the current X (Twitter) sentiment for the crypto token ${symbol.upper()} "
        f"on the {chain} blockchain. Search for recent posts mentioning ${symbol.upper()}, "
        f"#{symbol.upper()}, and any related project names. "
        f"Focus on posts from the last few hours."
    )

    result = call_grok(
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        cache_key="grok_sentiment",
        tools=[{"type": "x_search"}],
        temperature=0.3,
        max_output_tokens=500,
        parse_json=True,
        timeout=60,
        module="sentiment",
    )

    if result is None:
        raise ValueError("No result from Grok sentiment call")

    # Validate and clamp score
    score = int(result.get("sentiment_score", result.get("score", 50)))
    result["sentiment_score"] = max(0, min(100, score))

    return result


def get_grok_sentiment(symbol: str, chain: str = "unknown") -> Optional[dict]:
    """
    Get full Grok sentiment analysis for a token.

    Returns dict with:
        sentiment_score, buzz_level, sentiment_label, influencer_mentions,
        red_flag_count, key_signals, red_flags, summary

    Returns None on failure.
    """
    # Check cache first
    cached = _check_cache(symbol)
    if cached is not None:
        logger.debug(f"Grok sentiment [cached]: {symbol} → {cached.get('sentiment_score', '?')}")
        return cached

    try:
        result = _call_grok(symbol, chain)
        _store_cache(symbol, result)

        logger.info(
            f"Grok sentiment: {symbol} → score={result['sentiment_score']}, "
            f"buzz={result.get('buzz_level', '?')}, "
            f"influencers={result.get('influencer_mentions', 0)}, "
            f"red_flags={result.get('red_flag_count', 0)}"
        )
        return result

    except RuntimeError as e:
        if "not configured" in str(e):
            logger.debug("Grok sentiment: no API key configured, returning neutral")
            return None
        raise
    except json.JSONDecodeError as e:
        logger.warning(f"Grok sentiment: failed to parse response for {symbol}: {e}")
        return None
    except requests.exceptions.RequestException as e:
        logger.warning(f"Grok sentiment: API request failed for {symbol}: {e}")
        return None
    except Exception as e:
        logger.warning(f"Grok sentiment: unexpected error for {symbol}: {e}")
        return None


def get_grok_sentiment_score(symbol: str, chain: str = "unknown") -> float:
    """
    Get just the 0-100 sentiment score for a token.

    This is the main function called by gem_scanner.py.
    Returns 50.0 (neutral) on failure.
    """
    result = get_grok_sentiment(symbol, chain)
    if result is None:
        return 50.0
    return float(result.get("sentiment_score", 50))


def get_usage_stats() -> dict:
    """Return current usage stats for monitoring (delegates to global client)."""
    stats = _get_global_stats()
    stats["cached_symbols"] = len(_cache)
    return stats
