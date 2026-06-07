"""
data/providers/grok_client.py — Shared Grok API Client

Centralized client for all Grok-powered modules. Provides:
  - Global thread-safe rate limiter (shared 60 RPM budget across all callers)
  - Correct /v1/responses API format (input/output, NOT messages/choices)
  - Prompt caching via xAI's `prompt_cache_key` for sticky server routing
  - Centralized response parsing, citation stripping, and JSON extraction
  - Unified usage statistics (requests, tokens, cache hits)

All Grok modules (sentiment, trending, CRO, MiroFish, autoresearch)
MUST use this client instead of making raw API calls.

Usage:
    from data.providers.grok_client import call_grok, get_usage_stats

    result = call_grok(
        cache_key="cro_agent",        # Enables prompt caching
        system_prompt=SYSTEM_PROMPT,
        user_message="Evaluate this trade...",
        temperature=0.3,
        parse_json=True,
    )
"""

import json
import logging
import os
import re
import threading
import time
from typing import Optional, Union

from data.http_session import get_session

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# API Configuration
# ─────────────────────────────────────────────────────────────────────────────
GROK_RESPONSES_URL = "https://api.x.ai/v1/responses"
GROK_MODEL = "grok-4-1-fast-non-reasoning"

# ─────────────────────────────────────────────────────────────────────────────
# Global Rate Limiter — shared across ALL Grok modules
# ─────────────────────────────────────────────────────────────────────────────
_lock = threading.Lock()
_api_key_invalid = False
_request_times: list[float] = []
_MAX_RPM = int(os.getenv("GROK_RPM", "60"))

# ─────────────────────────────────────────────────────────────────────────────
# Unified Usage Stats
# ─────────────────────────────────────────────────────────────────────────────
_stats_lock = threading.Lock()
_total_requests = 0
_total_input_tokens = 0
_total_output_tokens = 0
_total_cached_tokens = 0
_per_module_requests: dict[str, int] = {}


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


def rate_limit() -> None:
    """
    Thread-safe global rate limiter for all Grok modules.

    Enforces a shared RPM budget so that sentiment + trending + CRO +
    MiroFish + autoresearch collectively stay under the API limit.
    """
    with _lock:
        now = time.time()
        # Prune requests older than 60s
        _request_times[:] = [t for t in _request_times if now - t < 60]
        if len(_request_times) >= _MAX_RPM:
            wait_time = 60 - (now - _request_times[0])
            if wait_time > 0:
                logger.debug(f"Grok global rate limit: {len(_request_times)}/{_MAX_RPM} RPM, waiting {wait_time:.1f}s")
                time.sleep(wait_time)
        _request_times.append(now)


def extract_response_text(data: dict) -> str:
    """
    Extract the assistant's text from the /v1/responses response format.

    Walks `output[]` items in reverse to find the last assistant message
    with output_text content.
    """
    for item in reversed(data.get("output", [])):
        if item.get("type") == "message" and item.get("role") == "assistant":
            for content_block in item.get("content", []):
                if content_block.get("type") == "output_text":
                    return content_block.get("text", "")
    return ""


def clean_json_text(text: str) -> str:
    """
    Strip Grok response artifacts that break JSON parsing:
    - Citation links like [[1]](url)
    - Markdown code fences (```json ... ```)
    """
    # Strip citation references
    text = re.sub(r'\[\[\d+\]\]\([^)]*\)', '', text).strip()
    # Strip code fences
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]) if len(lines) > 2 else text
    return text.strip()


def _track_usage(data: dict, module: str) -> None:
    """Track token usage from API response."""
    global _total_requests, _total_input_tokens, _total_output_tokens, _total_cached_tokens
    usage = data.get("usage", {})
    with _stats_lock:
        _total_requests += 1
        _total_input_tokens += usage.get("input_tokens", 0)
        _total_output_tokens += usage.get("output_tokens", 0)
        # xAI reports cached tokens in prompt_tokens_details.cached_tokens
        prompt_details = usage.get("prompt_tokens_details", {})
        _total_cached_tokens += prompt_details.get("cached_tokens", 0)
        _per_module_requests[module] = _per_module_requests.get(module, 0) + 1


def call_grok(
    system_prompt: str,
    user_message: str,
    *,
    cache_key: str = "",
    tools: list[dict] | None = None,
    temperature: float = 0.3,
    max_output_tokens: int = 500,
    parse_json: bool = True,
    timeout: int = 30,
    module: str = "unknown",
) -> Optional[Union[dict, str]]:
    """
    Call the Grok Responses API with correct format and shared rate limiting.

    Prompt Caching:
        xAI automatically caches identical message prefixes server-side.
        The `cache_key` parameter maps to xAI's `prompt_cache_key`, which
        enables sticky server routing so repeated calls with the same
        system prompt hit the cache. Each module should use a unique,
        stable cache_key (e.g., "cro_agent", "sentiment", "trending").

    Args:
        system_prompt: Static system prompt (front-loaded for caching).
        user_message: Dynamic user message (appended after cached prefix).
        cache_key: Stable key for xAI prompt caching (sticky routing).
        tools: Optional tools list, e.g. [{"type": "x_search"}].
        temperature: Sampling temperature (0.0-2.0).
        max_output_tokens: Max tokens in response.
        parse_json: If True, parse response as JSON dict.
        timeout: Request timeout in seconds.
        module: Caller module name for per-module usage tracking.

    Returns:
        Parsed JSON dict if parse_json=True, raw text string otherwise,
        or None on failure.
    """
    global _api_key_invalid
    if _api_key_invalid:
        return None

    api_key = _get_api_key()
    if not api_key:
        logger.warning(f"Grok client [{module}]: GROK_API_KEY not configured")
        return None

    rate_limit()

    # ── Build payload in correct Responses API format ────────────────────
    payload: dict = {
        "model": GROK_MODEL,
        "input": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": temperature,
        "max_output_tokens": max_output_tokens,
    }

    # Prompt caching: sticky server routing via prompt_cache_key
    if cache_key:
        payload["prompt_cache_key"] = cache_key

    if tools:
        payload["tools"] = tools

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    try:
        resp = get_session().post(
            GROK_RESPONSES_URL, json=payload, headers=headers, timeout=timeout
        )
        resp.raise_for_status()
    except Exception as e:
        if hasattr(e, "response") and e.response is not None and e.response.status_code in (401, 403):
            _api_key_invalid = True
            logger.warning(f"Grok client [{module}]: API Key is invalid or expired (403 Forbidden). Disabling Grok for this session.")
        else:
            logger.error(f"Grok client [{module}]: API request failed: {e}")
        return None

    data = resp.json()
    _track_usage(data, module)

    # ── Extract text from Responses API output format ────────────────────
    text = extract_response_text(data)
    if not text:
        logger.warning(f"Grok client [{module}]: No text output in response")
        return None

    if not parse_json:
        return text

    # ── Parse JSON response ──────────────────────────────────────────────
    cleaned = clean_json_text(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.warning(f"Grok client [{module}]: JSON parse failed: {e} | raw: {cleaned[:200]}")
        return None


def get_usage_stats() -> dict:
    """
    Return unified usage stats across all Grok modules.

    Useful for monitoring dashboards and cost tracking.
    """
    with _stats_lock:
        now = time.time()
        with _lock:
            recent = len([t for t in _request_times if now - t < 60])
        return {
            "total_requests": _total_requests,
            "total_input_tokens": _total_input_tokens,
            "total_output_tokens": _total_output_tokens,
            "total_cached_tokens": _total_cached_tokens,
            "cache_hit_rate": (
                f"{(_total_cached_tokens / max(1, _total_input_tokens)) * 100:.1f}%"
            ),
            "requests_last_minute": recent,
            "rpm_limit": _MAX_RPM,
            "per_module": dict(_per_module_requests),
        }
