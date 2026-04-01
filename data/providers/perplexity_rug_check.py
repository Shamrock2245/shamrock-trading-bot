"""
data/providers/perplexity_rug_check.py — Perplexity Real-Time Rug/Scam Intelligence
=====================================================================================
Uses Perplexity's Sonar API (web-search-backed LLM) to search the open web for
rug alerts, scam reports, developer exposure, and red flags for any token.

This is DIFFERENT from Grok sentiment (which only searches X/Twitter).
Perplexity searches the full web: Reddit, Telegram leaks, audit sites, crypto
news, rug-pull databases, and community warning threads.

Cost: ~$0.005 per query (sonar-small model). At 50 queries/day = ~$7.50/month.
Rate limit: Controlled by PERPLEXITY_DAILY_LIMIT setting (default 50/day).

API key: PERPLEXITY_API_KEY in .env
Model: sonar (web-search backed, real-time results)

Output:
  - rug_risk_score: 0–100 (0 = clean, 100 = confirmed rug)
  - hard_reject: bool (True = immediate disqualify)
  - score_penalty: float (0–20 pts deducted from gem score)
  - flags: list[str] (human-readable red flags found)
  - sources: list[str] (URLs of evidence)
  - summary: str (one-line verdict)

Integration:
  - Called in safety.py after GoPlus + ChainAware checks pass
  - Hard reject if rug_risk_score >= 70
  - Score penalty applied in gem_scanner.py
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
_API_KEY = os.getenv("PERPLEXITY_API_KEY", "")
_BASE_URL = "https://api.perplexity.ai"
_MODEL = "sonar"  # Web-search backed, real-time
_TIMEOUT = 30
_CACHE_TTL = 600  # 10 minutes — rug reports don't change fast

# Daily call budget (cost control)
_DAILY_LIMIT = int(os.getenv("PERPLEXITY_DAILY_LIMIT", "50"))
_call_count_today: int = 0
_call_count_date: str = ""

# Cache: {cache_key: (timestamp, result)}
_cache: dict[str, tuple[float, dict]] = {}

# Hard reject threshold
_HARD_REJECT_THRESHOLD = 70  # rug_risk_score >= 70 = immediate disqualify
_SCORE_PENALTY_THRESHOLD = 30  # rug_risk_score >= 30 = apply score penalty


def _get_api_key() -> str:
    return _API_KEY or os.getenv("PERPLEXITY_API_KEY", "")


def _check_daily_limit() -> bool:
    """Returns True if we're under the daily call limit."""
    global _call_count_today, _call_count_date
    today = time.strftime("%Y-%m-%d")
    if _call_count_date != today:
        _call_count_today = 0
        _call_count_date = today
    return _call_count_today < _DAILY_LIMIT


def _increment_call_count():
    global _call_count_today
    _call_count_today += 1


def _build_rug_check_prompt(symbol: str, name: str, address: str, chain: str) -> str:
    """Build a focused prompt for rug/scam detection."""
    return (
        f"Search for any rug pull alerts, scam reports, developer wallet exposure, "
        f"or red flags for the crypto token {symbol} ({name}) "
        f"with contract address {address} on {chain} blockchain. "
        f"Check: crypto rug pull databases, Reddit r/CryptoMoonShots, r/CryptoCurrency, "
        f"Telegram leak channels, audit sites (CertiK, Hacken, PeckShield), "
        f"and any news articles or community warnings. "
        f"Return a JSON object with these exact fields: "
        f"{{\"rug_risk_score\": 0-100, \"hard_reject\": true/false, "
        f"\"flags\": [\"list of specific red flags found\"], "
        f"\"sources\": [\"list of source URLs\"], "
        f"\"summary\": \"one sentence verdict\"}}. "
        f"rug_risk_score 0=clean, 100=confirmed rug. "
        f"hard_reject=true only if confirmed rug/scam/honeypot. "
        f"If no red flags found, return rug_risk_score=5, hard_reject=false, flags=[], summary=\"No red flags found\"."
    )


def _call_perplexity(symbol: str, name: str, address: str, chain: str) -> dict:
    """Call Perplexity Sonar API for rug/scam intelligence."""
    api_key = _get_api_key()
    if not api_key:
        raise RuntimeError("PERPLEXITY_API_KEY not configured")

    prompt = _build_rug_check_prompt(symbol, name, address, chain)

    payload = {
        "model": _MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a crypto security analyst specializing in rug pull detection. "
                    "Search the web thoroughly for any evidence of scams, rug pulls, or red flags. "
                    "Always respond with valid JSON only, no markdown."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 500,
        "search_recency_filter": "week",  # Focus on recent reports
        "return_citations": True,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    resp = requests.post(
        f"{_BASE_URL}/chat/completions",
        json=payload,
        headers=headers,
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()

    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    citations = data.get("citations", [])

    # Parse JSON response
    import re
    # Strip markdown code fences if present
    content = re.sub(r"```(?:json)?", "", content).strip()
    result = json.loads(content)

    # Validate fields
    result["rug_risk_score"] = max(0, min(100, int(result.get("rug_risk_score", 5))))
    result["hard_reject"] = bool(result.get("hard_reject", False))
    result["flags"] = result.get("flags", [])
    result["sources"] = result.get("sources", citations[:5])  # Use API citations if not in response
    result["summary"] = result.get("summary", "No red flags found")

    return result


def check_token_rug_risk(
    symbol: str,
    address: str,
    chain: str,
    name: str = "",
) -> dict:
    """
    Check a token for rug pull risk using Perplexity web search.

    Returns:
        {
            "rug_risk_score": int (0–100),
            "hard_reject": bool,
            "score_penalty": float (pts to deduct from gem score),
            "flags": list[str],
            "sources": list[str],
            "summary": str,
            "skipped": bool (True if API key not set or limit reached),
        }
    """
    default_clean = {
        "rug_risk_score": 0,
        "hard_reject": False,
        "score_penalty": 0.0,
        "flags": [],
        "sources": [],
        "summary": "Perplexity check skipped",
        "skipped": True,
    }

    api_key = _get_api_key()
    if not api_key:
        return default_clean

    if not _check_daily_limit():
        logger.debug(f"Perplexity daily limit ({_DAILY_LIMIT}) reached — skipping {symbol}")
        return {**default_clean, "summary": f"Daily limit ({_DAILY_LIMIT}) reached"}

    cache_key = f"rug:{chain}:{address.lower()}"
    cached = _cache.get(cache_key)
    if cached and (time.time() - cached[0]) < _CACHE_TTL:
        return cached[1]

    try:
        _increment_call_count()
        result = _call_perplexity(symbol, name, address, chain)

        # Calculate score penalty
        rug_score = result["rug_risk_score"]
        if rug_score >= _HARD_REJECT_THRESHOLD:
            result["hard_reject"] = True
            result["score_penalty"] = 0.0  # Hard reject — score doesn't matter
        elif rug_score >= _SCORE_PENALTY_THRESHOLD:
            # Linear penalty: 30 risk = -3 pts, 69 risk = -20 pts
            result["score_penalty"] = round(
                (rug_score - _SCORE_PENALTY_THRESHOLD) / (70 - _SCORE_PENALTY_THRESHOLD) * 20.0, 1
            )
        else:
            result["score_penalty"] = 0.0

        result["skipped"] = False

        if result["flags"]:
            logger.info(
                f"🚨 Perplexity rug check [{symbol}]: "
                f"risk={rug_score} | reject={result['hard_reject']} | "
                f"penalty={result['score_penalty']:.1f} | "
                f"flags={result['flags'][:2]}"
            )
        else:
            logger.debug(f"Perplexity rug check [{symbol}]: clean (risk={rug_score})")

        _cache[cache_key] = (time.time(), result)
        return result

    except json.JSONDecodeError as e:
        logger.debug(f"Perplexity response parse failed for {symbol}: {e}")
        return default_clean
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 401:
            logger.warning("Perplexity API key invalid — disabling rug checks")
            global _API_KEY
            _API_KEY = ""
        return default_clean
    except Exception as e:
        logger.debug(f"Perplexity rug check failed for {symbol}: {e}")
        return default_clean


def get_daily_usage() -> dict:
    """Return current daily usage stats."""
    return {
        "calls_today": _call_count_today,
        "daily_limit": _DAILY_LIMIT,
        "remaining": max(0, _DAILY_LIMIT - _call_count_today),
        "api_key_set": bool(_get_api_key()),
    }
