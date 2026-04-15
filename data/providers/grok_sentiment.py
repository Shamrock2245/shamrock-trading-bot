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
"""

import json
import logging
import os
import time
from typing import Optional

import requests  # kept for exceptions
from data.http_session import get_session

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────
GROK_RESPONSES_URL = "https://api.x.ai/v1/responses"
GROK_MODEL = "grok-4-1-fast-non-reasoning"

# ─────────────────────────────────────────────────────────────────────────────
# Cache — 10 minute TTL to control costs
# ─────────────────────────────────────────────────────────────────────────────
_cache: dict[str, tuple[float, dict]] = {}  # symbol -> (timestamp, result)
_CACHE_TTL = 600  # 10 minutes

# Rate limiter
_request_times: list[float] = []
_MAX_REQUESTS_PER_MINUTE = 30  # Conservative — Grok allows more


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


def _get_api_key() -> str:
    """Load Grok API key from settings or environment."""
    try:
        from config import settings
        key = getattr(settings, "GROK_API_KEY", "")
        if key:
            return key
    except ImportError:
        pass
    return os.getenv("GROK_API_KEY", "")


def _rate_limit():
    """Enforce per-minute rate limit."""
    global _request_times
    now = time.time()
    _request_times = [t for t in _request_times if now - t < 60]
    if len(_request_times) >= _MAX_REQUESTS_PER_MINUTE:
        wait_time = 60 - (now - _request_times[0])
        if wait_time > 0:
            logger.debug(f"Grok sentiment: rate limiting, waiting {wait_time:.1f}s")
            time.sleep(wait_time)
    _request_times.append(now)


def _check_cache(symbol: str) -> Optional[dict]:
    """Return cached result if valid."""
    key = symbol.upper()
    if key in _cache:
        ts, result = _cache[key]
        if time.time() - ts < _CACHE_TTL:
            return result
    return None


def _store_cache(symbol: str, result: dict) -> dict:
    """Store result in cache."""
    _cache[symbol.upper()] = (time.time(), result)
    return result


def _extract_response_text(data: dict) -> str:
    """
    Extract the assistant's text from the /v1/responses response format.

    The response has an 'output' array. We look for the last item with
    type='message' and role='assistant', then extract text from its content.
    """
    for item in reversed(data.get("output", [])):
        if item.get("type") == "message" and item.get("role") == "assistant":
            for content_block in item.get("content", []):
                if content_block.get("type") == "output_text":
                    return content_block.get("text", "")
    return ""


def _call_grok(symbol: str, chain: str) -> dict:
    """
    Call the Grok Responses API with x_search tool to analyze sentiment.

    Uses POST /v1/responses with the x_search built-in tool.
    Returns parsed JSON dict or raises on failure.
    """
    api_key = _get_api_key()
    if not api_key:
        raise RuntimeError("GROK_API_KEY not configured")

    _rate_limit()

    user_message = (
        f"Analyze the current X (Twitter) sentiment for the crypto token ${symbol.upper()} "
        f"on the {chain} blockchain. Search for recent posts mentioning ${symbol.upper()}, "
        f"#{symbol.upper()}, and any related project names. "
        f"Focus on posts from the last few hours."
    )

    payload = {
        "model": GROK_MODEL,
        "input": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        "tools": [{"type": "x_search"}],
        "temperature": 0.3,
        "max_output_tokens": 500,
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    resp = get_session().post(GROK_RESPONSES_URL, json=payload, headers=headers, timeout=60)
    resp.raise_for_status()

    data = resp.json()
    content = _extract_response_text(data)

    if not content:
        raise ValueError("No text output in Grok response")

    # Clean up — strip citations like [[1]](url) and code fences
    import re
    content = re.sub(r'\[\[\d+\]\]\([^)]*\)', '', content).strip()

    # Strip markdown code fences if present
    if content.startswith("```"):
        lines = content.split("\n")
        content = "\n".join(lines[1:-1]) if len(lines) > 2 else content
    content = content.strip()

    result = json.loads(content)

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
    """Return current usage stats for monitoring."""
    now = time.time()
    recent_requests = len([t for t in _request_times if now - t < 60])
    return {
        "cached_symbols": len(_cache),
        "requests_last_minute": recent_requests,
        "max_per_minute": _MAX_REQUESTS_PER_MINUTE,
    }
