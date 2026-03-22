"""
data/providers/defillama.py — DefiLlama API wrapper.

Free API, no key required. Provides TVL data and token prices.

Endpoints used:
   - GET https://api.llama.fi/protocols         → All protocols with TVL
   - GET https://api.llama.fi/protocol/{slug}    → Detailed protocol data
   - GET https://coins.llama.fi/prices/current/{chain}:{address} → Token price

Rate limit: ~500 req/min (generous, no key needed).
"""

import logging
import time
from typing import Optional

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

LLAMA_BASE = "https://api.llama.fi"
COINS_BASE = "https://coins.llama.fi"

# ── In-memory cache ──────────────────────────────────────────────────────────
_protocol_cache: Optional[list[dict]] = None
_protocol_cache_time: float = 0.0
_PROTOCOL_CACHE_TTL = 3600  # 1 hour

_tvl_score_cache: dict[str, tuple[float, float]] = {}  # address -> (score, timestamp)
_TVL_CACHE_TTL = 1800  # 30 min


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _get(url: str, timeout: int = 15) -> dict:
    """Make a GET request to DefiLlama API."""
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _get_all_protocols() -> list[dict]:
    """Fetch and cache all DeFi protocols from DefiLlama."""
    global _protocol_cache, _protocol_cache_time
    now = time.time()
    if _protocol_cache and (now - _protocol_cache_time) < _PROTOCOL_CACHE_TTL:
        return _protocol_cache

    try:
        data = _get(f"{LLAMA_BASE}/protocols")
        if isinstance(data, list):
            _protocol_cache = data
            _protocol_cache_time = now
            logger.info(f"DefiLlama: cached {len(data)} protocols")
            return data
    except Exception as e:
        logger.warning(f"DefiLlama protocols fetch failed: {e}")

    return _protocol_cache or []


def search_protocol_by_token(token_address: str) -> Optional[dict]:
    """
    Try to match a token address to a DeFi protocol.
    Checks the 'address' field in protocol data (case-insensitive).
    """
    protocols = _get_all_protocols()
    addr_lower = token_address.lower()

    for proto in protocols:
        # DefiLlama stores address as chain:addr or just addr
        proto_addr = (proto.get("address") or "").lower()
        if addr_lower in proto_addr:
            return proto

        # Also check gecko_id and symbol as fuzzy fallbacks
        # (some protocols store token address in different fields)

    return None


def get_protocol_tvl(slug: str) -> Optional[dict]:
    """
    GET /protocol/{slug}
    Returns detailed protocol data including TVL, tvlHistory, chains.
    """
    try:
        data = _get(f"{LLAMA_BASE}/protocol/{slug}")
        return {
            "name": data.get("name", ""),
            "tvl": float(data.get("tvl", 0) or 0),
            "mcap": float(data.get("mcap", 0) or 0),
            "fdv": float(data.get("fdv", 0) or 0),
            "chains": data.get("chains", []),
            "category": data.get("category", ""),
        }
    except Exception as e:
        logger.warning(f"DefiLlama protocol '{slug}' fetch failed: {e}")
        return None


def get_token_price(chain: str, token_address: str) -> Optional[float]:
    """
    GET /prices/current/{chain}:{address}
    Returns current USD price for a token. Useful as a backup to DexScreener.
    """
    # DefiLlama uses specific chain identifiers
    chain_map = {
        "ethereum": "ethereum",
        "base": "base",
        "arbitrum": "arbitrum",
        "polygon": "polygon",
        "bsc": "bsc",
    }
    ll_chain = chain_map.get(chain.lower())
    if not ll_chain:
        return None

    try:
        key = f"{ll_chain}:{token_address}"
        data = _get(f"{COINS_BASE}/prices/current/{key}")
        coins = data.get("coins", {})
        coin_data = coins.get(key, {})
        return float(coin_data.get("price", 0) or 0) or None
    except Exception as e:
        logger.debug(f"DefiLlama price lookup failed for {chain}:{token_address}: {e}")
        return None


def get_tvl_score(token_address: str, chain: str) -> float:
    """
    Compute a 0–100 TVL score for a token.

    Scoring tiers:
        TVL > $10M  → 100
        TVL > $1M   → 80
        TVL > $100K → 60
        TVL > $10K  → 40
        No protocol → 30 (neutral — most micro-cap gems won't be tracked)
    """
    cache_key = f"{chain}:{token_address}".lower()

    # Check cache
    if cache_key in _tvl_score_cache:
        score, cached_at = _tvl_score_cache[cache_key]
        if (time.time() - cached_at) < _TVL_CACHE_TTL:
            return score

    score = 30.0  # Default: neutral (no protocol found)

    try:
        proto = search_protocol_by_token(token_address)
        if proto:
            tvl = float(proto.get("tvl", 0) or 0)
            slug = proto.get("slug", "")
            logger.info(f"DefiLlama: matched {token_address} → {proto.get('name')} (TVL=${tvl:,.0f})")

            if tvl > 10_000_000:
                score = 100.0
            elif tvl > 1_000_000:
                score = 80.0
            elif tvl > 100_000:
                score = 60.0
            elif tvl > 10_000:
                score = 40.0
            else:
                score = 25.0
    except Exception as e:
        logger.warning(f"DefiLlama TVL scoring failed for {token_address}: {e}")

    _tvl_score_cache[cache_key] = (score, time.time())
    return score


def get_mcap_fdv_ratio(token_address: str, chain: str) -> Optional[float]:
    """
    Get the mcap/fdv ratio for dilution risk assessment.
    Returns ratio between 0.0 and 1.0, or None if unavailable.
    Used by token_unlocks provider.
    """
    proto = search_protocol_by_token(token_address)
    if not proto:
        return None

    mcap = float(proto.get("mcap", 0) or 0)
    fdv = float(proto.get("fdv", 0) or 0)

    if fdv > 0 and mcap > 0:
        return min(mcap / fdv, 1.0)

    return None
