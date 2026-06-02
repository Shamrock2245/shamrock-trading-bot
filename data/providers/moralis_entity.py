"""
data/providers/moralis_entity.py — Moralis Universal Entity API.

Provides entity resolution for wallet addresses and token deployers.
The Entity API maps on-chain addresses to known real-world entities
(exchanges, protocols, funds, whales, bridges, etc.) which is critical
for safety scoring and whale detection.

Endpoints used:
  GET /entities/search?query={address}   → Search for entity by address (50 CU)
  GET /entities/{id}                     → Get entity by ID (50 CU)
  GET /entities/categories               → Get entity categories (10 CU)

CU Conservation Strategy:
  - 24-hour cache for entity lookups (entities don't change often)
  - Batch lookup with dedup to avoid repeated calls for same address
  - Returns None fast if API key not configured
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional, Any

from data.http_session import get_session
from config import settings

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────
MORALIS_API_KEY: str = getattr(settings, "MORALIS_API_KEY", "")
BASE_URL = "https://deep-index.moralis.io/api/v2.2"

# Long cache TTL — entity labels rarely change
ENTITY_CACHE_TTL = 86400  # 24 hours
CATEGORY_CACHE_TTL = 3600  # 1 hour

_cache: dict[str, dict] = {}
_cache_lock = threading.Lock()

# Rate limiter — shared Pro-tier global limiter (60 RPS, CU-budget-aware)
from data.providers.moralis_rate_limiter import rate_check as _rate_check
_rate_lock = threading.Lock()


def _headers() -> dict:
    return {
        "accept": "application/json",
        "X-API-Key": MORALIS_API_KEY,
    }


def _available() -> bool:
    return bool(MORALIS_API_KEY)




def _is_cached(key: str, ttl: int = ENTITY_CACHE_TTL) -> bool:
    with _cache_lock:
        if key not in _cache:
            return False
        return (time.time() - _cache[key]["ts"]) < ttl


def _set_cache(key: str, data: Any) -> None:
    with _cache_lock:
        _cache[key] = {"data": data, "ts": time.time()}


def _get_cache(key: str) -> Any:
    with _cache_lock:
        return _cache.get(key, {}).get("data")


# ─────────────────────────────────────────────────────────────────────────────
# Entity Lookup Functions
# ─────────────────────────────────────────────────────────────────────────────

def get_entity_by_address(address: str) -> Optional[dict]:
    """
    Look up a known entity by wallet/contract address.
    Returns entity metadata if found, None if unknown.
    
    CU Cost: 50
    Cache TTL: 24 hours
    """
    if not _available() or not address:
        return None
    
    addr_lower = address.lower()
    cache_key = f"entity_addr_{addr_lower}"
    if _is_cached(cache_key, ENTITY_CACHE_TTL):
        return _get_cache(cache_key)
    
    _rate_check()
    try:
        resp = get_session().get(
            f"{BASE_URL}/entities/search",
            params={"query": addr_lower, "limit": 1},
            headers=_headers(),
            timeout=10,
        )
        if resp.status_code in (400, 404, 422, 429):
            _set_cache(cache_key, None)
            return None
        resp.raise_for_status()
        data = resp.json()
        results = data.get("result", []) if isinstance(data, dict) else []
        
        if not results:
            _set_cache(cache_key, None)
            return None
        
        entity = results[0]
        result = {
            "entity_id": entity.get("id", ""),
            "name": entity.get("name", ""),
            "type": entity.get("entity_type", ""),
            "category": entity.get("category", ""),
            "website": entity.get("website", ""),
            "twitter": entity.get("twitter", ""),
            "is_exchange": entity.get("entity_type", "").lower() in ("exchange", "cex", "dex"),
            "is_fund": entity.get("entity_type", "").lower() in ("fund", "vc", "investment"),
            "is_protocol": entity.get("entity_type", "").lower() in ("protocol", "defi", "bridge"),
            "is_whale": entity.get("category", "").lower() in ("whale", "large_holder"),
            "risk_flag": entity.get("category", "").lower() in ("scam", "hack", "rug", "exploit", "blacklist"),
        }
        _set_cache(cache_key, result)
        return result
    except Exception as e:
        logger.debug(f"Entity lookup error for {address[:8]}: {e}")
        return None


def get_entity_by_id(entity_id: str) -> Optional[dict]:
    """
    Get detailed entity data by Moralis entity ID.
    
    CU Cost: 50
    Cache TTL: 24 hours
    """
    if not _available() or not entity_id:
        return None
    
    cache_key = f"entity_id_{entity_id}"
    if _is_cached(cache_key, ENTITY_CACHE_TTL):
        return _get_cache(cache_key)
    
    _rate_check()
    try:
        resp = get_session().get(
            f"{BASE_URL}/entities/{entity_id}",
            headers=_headers(),
            timeout=10,
        )
        if resp.status_code in (400, 404, 422, 429):
            return None
        resp.raise_for_status()
        data = resp.json()
        _set_cache(cache_key, data)
        return data
    except Exception as e:
        logger.debug(f"Entity by ID error {entity_id}: {e}")
        return None


def get_entity_categories() -> list[dict]:
    """
    Get all available entity categories.
    Useful for understanding what types of entities Moralis tracks.
    
    CU Cost: 10
    Cache TTL: 1 hour
    """
    if not _available():
        return []
    
    cache_key = "entity_categories"
    if _is_cached(cache_key, CATEGORY_CACHE_TTL):
        return _get_cache(cache_key)
    
    _rate_check()
    try:
        resp = get_session().get(
            f"{BASE_URL}/entities/categories",
            headers=_headers(),
            timeout=10,
        )
        if resp.status_code in (400, 404, 429):
            return []
        resp.raise_for_status()
        data = resp.json()
        categories = data.get("result", []) if isinstance(data, dict) else []
        _set_cache(cache_key, categories)
        return categories
    except Exception as e:
        logger.debug(f"Entity categories error: {e}")
        return []


def is_known_bad_actor(address: str) -> bool:
    """
    Quick check: is this address a known scammer, hacker, or rug puller?
    Returns True if the entity is flagged as risky.
    
    CU Cost: 50 (first call) / 0 (cached)
    """
    entity = get_entity_by_address(address)
    if not entity:
        return False
    return bool(entity.get("risk_flag", False))


def is_known_exchange(address: str) -> bool:
    """
    Quick check: is this address a known CEX or DEX?
    Used to filter out exchange wallet transfers from whale detection.
    
    CU Cost: 50 (first call) / 0 (cached)
    """
    entity = get_entity_by_address(address)
    if not entity:
        return False
    return bool(entity.get("is_exchange", False))


def classify_wallet(address: str) -> str:
    """
    Classify a wallet address into a category string.
    Returns one of: 'exchange', 'fund', 'protocol', 'whale', 'bad_actor', 'unknown'
    
    CU Cost: 50 (first call) / 0 (cached)
    """
    entity = get_entity_by_address(address)
    if not entity:
        return "unknown"
    if entity.get("risk_flag"):
        return "bad_actor"
    if entity.get("is_exchange"):
        return "exchange"
    if entity.get("is_fund"):
        return "fund"
    if entity.get("is_protocol"):
        return "protocol"
    if entity.get("is_whale"):
        return "whale"
    return "unknown"


def batch_classify_wallets(addresses: list[str]) -> dict[str, str]:
    """
    Classify multiple wallet addresses in batch.
    Deduplicates to avoid redundant API calls.
    
    CU Cost: 50 per unique uncached address
    """
    unique_addrs = list(set(a.lower() for a in addresses if a))
    result = {}
    for addr in unique_addrs:
        result[addr] = classify_wallet(addr)
    return result


def get_usage_stats() -> dict:
    """Return cache and rate-limit stats for monitoring."""
    with _cache_lock:
        cached_count = len(_cache)
    return {
        "api_key_configured": bool(MORALIS_API_KEY),
        "cached_keys": cached_count,
        "rate_limiter": "shared_pro_tier",
        "endpoints_covered": [
            "searchEntities (50 CU)",
            "getEntity (50 CU)",
            "getEntityCategories (10 CU)",
        ],
    }
