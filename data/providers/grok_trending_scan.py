"""
data/providers/grok_trending_scan.py — Grok Real-Time CT Trending Token Scanner.

Every scan cycle, asks Grok (xAI) to identify the top 5 tokens being
discussed on Crypto Twitter (CT) right now using the x_search tool.
Returned tokens are resolved to tradeable pairs via DexScreener and
injected into the scoring pipeline.

This is a DISCOVERY source — it finds tokens the bot wouldn't find
through on-chain signals alone. Social narrative precedes price action
in meme/micro-cap markets.

API: POST https://api.x.ai/v1/responses
Model: grok-4-1-fast-non-reasoning (fast, non-reasoning with x_search tool)
Cache: 10 minutes per cycle (controls API cost)

Refactored: Uses shared grok_client.py for global rate limiting, correct API
format, and prompt caching via prompt_cache_key.

Usage:
    from data.providers.grok_trending_scan import discover_grok_trending
    trending = discover_grok_trending()
    # Returns list of {symbol, chain, token_address, signals, buzz_level, ...}
"""

import json
import logging
import time
from typing import Optional

import requests  # kept for exception types
from data.providers.grok_client import call_grok, get_usage_stats as _get_global_stats

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────
MAX_TRENDING_TOKENS = 5

# ─────────────────────────────────────────────────────────────────────────────
# Cache — 10 minute TTL (same as grok_sentiment.py)
# ─────────────────────────────────────────────────────────────────────────────
_cache: dict[str, tuple[float, list]] = {}
_CACHE_TTL = 600  # 10 minutes


# ─────────────────────────────────────────────────────────────────────────────
# System Prompt — kept static for optimal prompt caching
# xAI caches identical system prompt prefixes server-side. Do NOT embed
# dynamic content here — all variable data goes in the user message.
# ─────────────────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a crypto market intelligence analyst. Your job is to identify the TOP 5 cryptocurrency tokens being discussed RIGHT NOW on Crypto Twitter (CT).

Use the x_search tool to search for the latest crypto discussions, trending tokens, and meme coin chatter. Focus on:

1. **Tokens with viral momentum** — mentioned in many posts in the last 1-2 hours
2. **New launches getting attention** — fresh tokens people are excited about
3. **Tokens with influencer/KOL mentions** — big accounts talking about specific tokens
4. **Meme coins with narrative momentum** — cultural moments driving demand
5. **DeFi/Base/Solana tokens** — prioritize Base and Solana ecosystems

IMPORTANT: Only return tokens that are actually TRADEABLE on DEXs (have liquidity pools).
Do NOT return BTC, ETH, SOL, BNB, or other major L1/L2 tokens.
Focus on micro-cap and small-cap tokens under $100M market cap.

Return ONLY valid JSON with this exact structure (no markdown, no code fences):
{
  "trending_tokens": [
    {
      "symbol": "<TOKEN_SYMBOL>",
      "name": "<full token name>",
      "chain": "<ethereum|base|solana|arbitrum|bsc|polygon>",
      "buzz_level": "<low|medium|high|viral>",
      "mention_count_estimate": <int>,
      "key_narrative": "<one line: why people are talking about it>",
      "influencer_mentioned": <true|false>,
      "sentiment": "<bullish|neutral|bearish>"
    }
  ],
  "overall_ct_mood": "<risk_on|neutral|risk_off>",
  "scan_summary": "<one line summary of current CT activity>"
}

If you cannot find 5 trending tokens, return fewer. If CT is quiet, return an empty list.
Prioritize ACCURACY over quantity — only return tokens you are confident are real and being discussed."""


def _call_grok_trending() -> dict:
    """
    Call Grok Responses API with x_search to get trending CT tokens.
    Returns parsed JSON dict.
    """
    user_message = (
        "Search Crypto Twitter (CT) right now and identify the TOP 5 tokens "
        "being discussed the most in the last 1-2 hours. "
        "Focus on meme coins, new launches, and micro-cap tokens on Base, "
        "Solana, Ethereum, and BSC. "
        "Look for $TICKER mentions, trending hashtags, and KOL posts. "
        "Exclude BTC, ETH, SOL, BNB, USDC, USDT."
    )

    result = call_grok(
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        cache_key="grok_trending",
        tools=[{"type": "x_search"}],
        temperature=0.3,
        max_output_tokens=800,
        parse_json=True,
        timeout=60,
        module="trending",
    )

    if result is None:
        raise ValueError("No result from Grok trending call")

    return result


def _resolve_token_to_pair(symbol: str, chain: str) -> Optional[dict]:
    """
    Search DexScreener for a tradeable pair matching the symbol.
    Returns extract_gem_signals()-format dict or None.
    """
    try:
        from data.providers.dexscreener import search_pairs, extract_gem_signals
    except ImportError:
        return None

    try:
        pairs = search_pairs(symbol)
        if not pairs:
            return None

        # Find the best pair matching the chain (or any chain if chain is unknown)
        best_pair = None
        for pair in pairs:
            pair_chain = pair.get("chainId", "").lower()
            pair_symbol = pair.get("baseToken", {}).get("symbol", "").upper()

            # Must match the symbol
            if pair_symbol != symbol.upper():
                continue

            # Prefer matching chain
            if chain and pair_chain == chain.lower():
                best_pair = pair
                break
            elif not best_pair:
                best_pair = pair

        if not best_pair:
            return None

        # Must have minimum liquidity
        liquidity = float(best_pair.get("liquidity", {}).get("usd", 0) or 0)
        if liquidity < 5000:
            return None

        signals = extract_gem_signals(best_pair)
        return signals

    except Exception as e:
        logger.debug(f"Grok trending: failed to resolve {symbol} on {chain}: {e}")
        return None


def discover_grok_trending() -> list[dict]:
    """
    Main discovery function — called by gem_scanner.py every scan cycle.

    Asks Grok for the top 5 trending CT tokens, resolves each to a
    tradeable DexScreener pair, and returns them in standard signals format.

    Returns:
        List of dicts, each containing:
            - Standard extract_gem_signals() fields (for _signals_to_token)
            - source: "grok_trending"
            - grok_buzz_level: str
            - grok_narrative: str
            - grok_influencer_mentioned: bool
    """
    cache_key = "grok_trending_scan"
    if cache_key in _cache:
        ts, cached = _cache[cache_key]
        if time.time() - ts < _CACHE_TTL:
            logger.debug(f"Grok trending [cached]: {len(cached)} tokens")
            return cached

    try:
        from data.providers.grok_client import _get_api_key
        if not _get_api_key():
            logger.debug("Grok trending: no API key configured, skipping")
            return []
    except Exception:
        return []

    results = []

    try:
        grok_data = _call_grok_trending()
        trending = grok_data.get("trending_tokens", [])
        ct_mood = grok_data.get("overall_ct_mood", "neutral")

        logger.info(
            f"🐦 Grok CT scan: {len(trending)} trending tokens found, "
            f"CT mood: {ct_mood}"
        )

        for token_info in trending[:MAX_TRENDING_TOKENS]:
            symbol = token_info.get("symbol", "").strip().upper()
            chain = token_info.get("chain", "").strip().lower()
            buzz = token_info.get("buzz_level", "low")
            narrative = token_info.get("key_narrative", "")
            influencer = token_info.get("influencer_mentioned", False)
            sentiment = token_info.get("sentiment", "neutral")

            if not symbol:
                continue

            # Skip bearish tokens — we only want bullish/neutral momentum plays
            if sentiment == "bearish":
                logger.debug(f"Grok trending: skipping {symbol} (bearish sentiment)")
                continue

            # Resolve to DexScreener pair
            signals = _resolve_token_to_pair(symbol, chain)
            if not signals:
                logger.debug(f"Grok trending: could not resolve {symbol} to tradeable pair")
                continue

            # Enrich with Grok metadata
            signals["source"] = "grok_trending"
            signals["grok_buzz_level"] = buzz
            signals["grok_narrative"] = narrative
            signals["grok_influencer_mentioned"] = influencer
            signals["grok_ct_mood"] = ct_mood
            signals["is_boosted"] = True
            # Higher boost for viral tokens, lower for medium/low
            if buzz == "viral":
                signals["boost_amount"] = 150
            elif buzz == "high":
                signals["boost_amount"] = 100
            elif buzz == "medium":
                signals["boost_amount"] = 60
            else:
                signals["boost_amount"] = 30

            results.append(signals)

            logger.info(
                f"🐦 CT TRENDING: ${symbol} on {chain} — "
                f"buzz={buzz}, influencer={influencer}, "
                f"narrative=\"{narrative[:60]}...\""
            )

    except RuntimeError as e:
        if "not configured" in str(e):
            logger.debug("Grok trending: no API key configured")
        else:
            logger.warning(f"Grok trending scan error: {e}")
    except json.JSONDecodeError as e:
        logger.warning(f"Grok trending: failed to parse response: {e}")
    except requests.exceptions.RequestException as e:
        logger.warning(f"Grok trending: API request failed: {e}")
    except Exception as e:
        logger.warning(f"Grok trending: unexpected error: {e}")

    _cache[cache_key] = (time.time(), results)

    if results:
        logger.info(
            f"🐦 Grok trending: {len(results)} tokens resolved to tradeable pairs "
            f"(injecting into scoring pipeline)"
        )

    return results


def get_trending_stats() -> dict:
    """Return current stats for monitoring/dashboard."""
    cached = _cache.get("grok_trending_scan")
    cached_count = len(cached[1]) if cached else 0
    stats = _get_global_stats()
    stats["cached_tokens"] = cached_count
    stats["cache_ttl_seconds"] = _CACHE_TTL
    stats["max_tokens_per_scan"] = MAX_TRENDING_TOKENS
    return stats
