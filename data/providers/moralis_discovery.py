"""
data/providers/moralis_discovery.py — Moralis token discovery provider.

Surfaces trending tokens and buying pressure signals across all supported
chains using Moralis' Discovery & Market Data APIs. Feeds directly into
the gem scanner as Source 6 alongside DexScreener.

Endpoints used:
  - GET /discovery/tokens/trending — Hot tokens by volume + momentum (Pro)
  - GET /discovery/tokens/buying-pressure — Rising buy:sell ratio (Pro)
  - GET /erc20/{address}/stats — Transfer count enrichment (Free)
  - GET /erc20/{address}/owners — Holder distribution enrichment (Free)

Rate limit: 25 req/min (configurable in settings.py).
Cache: 10-minute TTL per chain to conserve API calls.
"""

import logging
import time
from typing import Optional

import requests

from config import settings

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

MORALIS_API_KEY = settings.MORALIS_API_KEY
BASE_URL = "https://deep-index.moralis.io/api/v2.2"

# Map our internal chain names → Moralis chain slugs
CHAIN_MAP = {
    "ethereum": "eth",
    "base": "base",
    "arbitrum": "arbitrum",
    "polygon": "polygon",
    "bsc": "bsc",
    "avalanche": "avalanche",
    "solana": "solana",
}

# Reverse map for incoming data
REVERSE_CHAIN_MAP = {v: k for k, v in CHAIN_MAP.items()}

# Cache: {chain: {tokens: [...], fetched_at: float}}
_cache: dict[str, dict] = {}
CACHE_TTL_SECONDS = 600  # 10 minutes


def _headers() -> dict:
    """Build Moralis API headers."""
    return {
        "accept": "application/json",
        "X-API-Key": MORALIS_API_KEY,
    }


def _is_cached(chain: str) -> bool:
    """Check if we have fresh cached data for this chain."""
    entry = _cache.get(chain)
    if not entry:
        return False
    return (time.time() - entry.get("fetched_at", 0)) < CACHE_TTL_SECONDS


# ─────────────────────────────────────────────────────────────────────────────
# Discovery Endpoints (Pro plan)
# ─────────────────────────────────────────────────────────────────────────────

def get_trending_tokens(chain: str) -> list[dict]:
    """
    Fetch trending tokens for a chain from Moralis Discovery API.
    Returns list of token dicts with address, symbol, volume, price, etc.
    """
    moralis_chain = CHAIN_MAP.get(chain)
    if not moralis_chain or not MORALIS_API_KEY:
        return []

    cache_key = f"trending_{chain}"
    if _is_cached(cache_key):
        return _cache[cache_key]["tokens"]

    try:
        url = f"{BASE_URL}/discovery/tokens/trending"
        params = {"chain": moralis_chain}
        resp = requests.get(url, params=params, headers=_headers(), timeout=15)

        if resp.status_code == 403:
            logger.debug(f"Moralis trending not available for {chain} (plan limitation)")
            return []

        resp.raise_for_status()
        data = resp.json()
        tokens = data if isinstance(data, list) else data.get("result", data.get("tokens", []))

        # Normalize to our format
        result = []
        for t in tokens:
            result.append({
                "token_address": t.get("token_address", t.get("address", "")),
                "token_symbol": t.get("token_symbol", t.get("symbol", "")),
                "token_name": t.get("token_name", t.get("name", "")),
                "chain": chain,
                "price_usd": _safe_float(t.get("price_usd", t.get("usd_price", 0))),
                "volume_usd": _safe_float(t.get("volume_usd", t.get("volume_24h", 0))),
                "market_cap": _safe_float(t.get("market_cap", 0)),
                "price_change_24h": _safe_float(t.get("price_24h_percent_change", 0)),
                "source": "moralis_trending",
            })

        _cache[cache_key] = {"tokens": result, "fetched_at": time.time()}
        logger.info(f"Moralis: fetched {len(result)} trending tokens for {chain}")
        return result

    except requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code == 403:
            logger.debug(f"Moralis trending endpoint not on current plan for {chain}")
        else:
            logger.warning(f"Moralis trending failed for {chain}: {e}")
        return []
    except Exception as e:
        logger.warning(f"Moralis trending error for {chain}: {e}")
        return []


def get_buying_pressure_tokens(chain: str) -> list[dict]:
    """
    Fetch tokens with rising buying pressure (buy:sell ratio increasing).
    These are early indicators of accumulation before a pump.
    """
    moralis_chain = CHAIN_MAP.get(chain)
    if not moralis_chain or not MORALIS_API_KEY:
        return []

    cache_key = f"buying_pressure_{chain}"
    if _is_cached(cache_key):
        return _cache[cache_key]["tokens"]

    try:
        url = f"{BASE_URL}/discovery/tokens/buying-pressure"
        params = {"chain": moralis_chain}
        resp = requests.get(url, params=params, headers=_headers(), timeout=15)

        if resp.status_code == 403:
            logger.debug(f"Moralis buying-pressure not available for {chain}")
            return []

        resp.raise_for_status()
        data = resp.json()
        tokens = data if isinstance(data, list) else data.get("result", data.get("tokens", []))

        result = []
        for t in tokens:
            result.append({
                "token_address": t.get("token_address", t.get("address", "")),
                "token_symbol": t.get("token_symbol", t.get("symbol", "")),
                "token_name": t.get("token_name", t.get("name", "")),
                "chain": chain,
                "price_usd": _safe_float(t.get("price_usd", t.get("usd_price", 0))),
                "volume_usd": _safe_float(t.get("volume_usd", t.get("volume_24h", 0))),
                "market_cap": _safe_float(t.get("market_cap", 0)),
                "price_change_24h": _safe_float(t.get("price_24h_percent_change", 0)),
                "buying_pressure": _safe_float(t.get("buyer_to_seller_ratio", t.get("buying_pressure", 0))),
                "source": "moralis_buying_pressure",
            })

        _cache[cache_key] = {"tokens": result, "fetched_at": time.time()}
        logger.info(f"Moralis: fetched {len(result)} buying-pressure tokens for {chain}")
        return result

    except Exception as e:
        logger.warning(f"Moralis buying-pressure error for {chain}: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Enrichment Endpoints (Free tier)
# ─────────────────────────────────────────────────────────────────────────────

def get_token_stats(token_address: str, chain: str) -> Optional[dict]:
    """Get token transfer statistics (total transfers = activity indicator)."""
    moralis_chain = CHAIN_MAP.get(chain)
    if not moralis_chain or not MORALIS_API_KEY or chain == "solana":
        return None

    try:
        url = f"{BASE_URL}/erc20/{token_address}/stats"
        params = {"chain": moralis_chain}
        resp = requests.get(url, params=params, headers=_headers(), timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


def get_holder_count(token_address: str, chain: str) -> int:
    """Get approximate holder count from Moralis token owners endpoint."""
    moralis_chain = CHAIN_MAP.get(chain)
    if not moralis_chain or not MORALIS_API_KEY or chain == "solana":
        return 0

    try:
        url = f"{BASE_URL}/erc20/{token_address}/owners"
        params = {"chain": moralis_chain, "limit": 1}
        resp = requests.get(url, params=params, headers=_headers(), timeout=10)
        resp.raise_for_status()
        data = resp.json()
        # page_size * total pages gives approximate count
        return int(data.get("total", 0) or 0)
    except Exception:
        return 0


# ─────────────────────────────────────────────────────────────────────────────
# Unified Discovery Function
# ─────────────────────────────────────────────────────────────────────────────

def discover_tokens(chains: list[str] = None) -> list[dict]:
    """
    Discover tokens across all chains using both trending and buying pressure.
    Deduplicates by address+chain. Returns combined list ready for DexScreener
    pair lookup and gem scoring.

    This is the main entry point called by gem_scanner.py.
    """
    if not MORALIS_API_KEY:
        logger.debug("Moralis: no API key configured, skipping discovery")
        return []

    if chains is None:
        chains = list(CHAIN_MAP.keys())

    all_tokens: list[dict] = []
    seen: set[str] = set()

    for chain in chains:
        # Fetch from both endpoints
        trending = get_trending_tokens(chain)
        buying = get_buying_pressure_tokens(chain)

        for t in trending + buying:
            addr = t.get("token_address", "").lower()
            dedup_key = f"{chain}:{addr}"
            if addr and dedup_key not in seen:
                seen.add(dedup_key)
                all_tokens.append(t)

    logger.info(f"Moralis discovery: {len(all_tokens)} unique tokens across {len(chains)} chains")
    return all_tokens


def get_usage_stats() -> dict:
    """Return cache stats for monitoring."""
    return {
        "cached_keys": len(_cache),
        "cache_entries": {k: len(v.get("tokens", [])) for k, v in _cache.items()},
    }


def _safe_float(val) -> float:
    """Safely convert to float, handling None and strings."""
    try:
        return float(val) if val is not None else 0.0
    except (ValueError, TypeError):
        return 0.0
