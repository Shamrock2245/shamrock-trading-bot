import os
import time
import threading
from data.http_session import get_session
import logging

logger = logging.getLogger(__name__)

# Rate limiter — shared with all other Moralis providers
try:
    from data.providers.moralis_rate_limiter import rate_check as _rate_check
except ImportError:
    def _rate_check() -> None:  # type: ignore[misc]
        pass

MORALIS_API_KEY = os.environ.get("MORALIS_API_KEY", "")
MORALIS_API_BASE = "https://deep-index.moralis.io/api/v2.2"
SOLANA_API_BASE = "https://solana-gateway.moralis.io"

# ── TTL caches ────────────────────────────────────────────────────────────────
# Moralis score/analytics data changes on a ~5-minute cadence; caching for
# 3 minutes prevents redundant CU spend when the same token is scored multiple
# times within a single scan cycle.
_SCORE_TTL = 180        # 3 minutes
_ANALYTICS_TTL = 180    # 3 minutes
_METADATA_TTL = 300     # 5 minutes (metadata rarely changes)

_score_cache: dict[str, tuple[float, dict]] = {}
_analytics_cache: dict[str, tuple[float, dict]] = {}
_metadata_cache: dict[str, tuple[float, list]] = {}
_cache_lock = threading.Lock()


def _score_key(token_address: str, chain: str) -> str:
    return f"{chain}:{token_address.lower()}"


def _get_cached_score(token_address: str, chain: str) -> dict | None:
    key = _score_key(token_address, chain)
    with _cache_lock:
        entry = _score_cache.get(key)
    if entry and (time.time() - entry[0]) < _SCORE_TTL:
        return entry[1]
    return None


def _set_cached_score(token_address: str, chain: str, result: dict) -> None:
    key = _score_key(token_address, chain)
    with _cache_lock:
        _score_cache[key] = (time.time(), result)


def _get_cached_analytics(token_address: str, chain: str) -> dict | None:
    key = _score_key(token_address, chain)
    with _cache_lock:
        entry = _analytics_cache.get(key)
    if entry and (time.time() - entry[0]) < _ANALYTICS_TTL:
        return entry[1]
    return None


def _set_cached_analytics(token_address: str, chain: str, result: dict) -> None:
    key = _score_key(token_address, chain)
    with _cache_lock:
        _analytics_cache[key] = (time.time(), result)


def _metadata_key(token_addresses: list, chain: str) -> str:
    return f"{chain}:{','.join(sorted(a.lower() for a in token_addresses))}"


def _get_cached_metadata(token_addresses: list, chain: str) -> list | None:
    key = _metadata_key(token_addresses, chain)
    with _cache_lock:
        entry = _metadata_cache.get(key)
    if entry and (time.time() - entry[0]) < _METADATA_TTL:
        return entry[1]
    return None


def _set_cached_metadata(token_addresses: list, chain: str, result: list) -> None:
    key = _metadata_key(token_addresses, chain)
    with _cache_lock:
        _metadata_cache[key] = (time.time(), result)


def _get_headers():
    return {
        "accept": "application/json",
        "X-API-Key": MORALIS_API_KEY
    }

def _chain_to_hex(chain: str) -> str:
    """Map internal chain names to Moralis hex."""
    cmap = {
        "ethereum": "0x1",
        "polygon": "0x89",
        "bsc": "0x38",
        "arbitrum": "0xa4b1",
        "optimism": "0xa",
        "base": "0x2105",
        "avalanche": "0xa86a"
    }
    return cmap.get(chain.lower(), "0x1")

def get_token_score(token_address: str, chain: str) -> dict:
    """
    Get token security score.
    https://docs.moralis.com/data-api/evm/reference/get-token-score

    Results are cached for 3 minutes (TTL) to avoid redundant CU spend when
    the same token is scored multiple times within a single scan cycle.
    """
    if not MORALIS_API_KEY:
        return {}

    # ── Cache hit ─────────────────────────────────────────────────────────────
    cached = _get_cached_score(token_address, chain)
    if cached is not None:
        return cached

    try:
        chain_lower = chain.lower()
        # Solana Token Score sunsets July 31 2026 (EVM-only thereafter)
        if chain_lower == "solana":
            _set_cached_score(token_address, chain, {})
            return {}

        hex_chain = _chain_to_hex(chain_lower)
        url = f"{MORALIS_API_BASE}/erc20/{token_address}/score?chain={hex_chain}"

        try:
            from core.moralis_cu_budget import cu_budget
            if not cu_budget.can_afford("token_score"):
                return {}
        except Exception:
            pass

        _rate_check()
        res = get_session().get(url, headers=_get_headers(), timeout=4)
        try:
            from data.providers.moralis_http import _parse_request_weight, _record_usage
            w = _parse_request_weight(res) or 100
            _record_usage("token_score", w)
        except Exception:
            pass
        if res.status_code == 200:
            result = res.json()
            _set_cached_score(token_address, chain, result)
            return result
        elif res.status_code == 404:
            # Not found / no score yet — cache empty result to avoid repeat 404s
            _set_cached_score(token_address, chain, {})
            return {}
        else:
            logger.debug(f"Moralis score error for {token_address}: {res.status_code} - {res.text}")
            return {}
    except Exception as e:
        logger.debug(f"Exception fetching Moralis score for {token_address}: {e}")
        return {}

def get_token_analytics(token_address: str, chain: str) -> dict:
    """
    Get deep token analytics (net buyers, volume USD, experienced buyers).
    Returns period-keyed dict: {"1d": {...}, "1w": {...}, "1m": {...}}
    Endpoint: /erc20/{address}/analytics  (NOT /tokens/{address}/analytics)
    https://docs.moralis.com/data-api/evm/reference/get-token-analytics

    Results are cached for 3 minutes (TTL) to avoid redundant CU spend when
    the same token is scored multiple times within a single scan cycle.
    """
    if not MORALIS_API_KEY:
        return {}

    # ── Cache hit ─────────────────────────────────────────────────────────────
    cached = _get_cached_analytics(token_address, chain)
    if cached is not None:
        return cached

    try:
        chain_lower = chain.lower()
        if chain_lower == "solana":
            url = f"{SOLANA_API_BASE}/token/mainnet/{token_address}/analytics"
        else:
            hex_chain = _chain_to_hex(chain_lower)
            url = f"{MORALIS_API_BASE}/erc20/{token_address}/analytics?chain={hex_chain}"

        _rate_check()
        res = get_session().get(url, headers=_get_headers(), timeout=5)
        if res.status_code == 200:
            result = res.json()
            _set_cached_analytics(token_address, chain, result)
            return result
        elif res.status_code == 404:
            _set_cached_analytics(token_address, chain, {})
            return {}
        else:
            logger.debug(f"Moralis analytics error for {token_address}: {res.status_code} - {res.text}")
            return {}
    except Exception as e:
        logger.debug(f"Exception fetching Moralis analytics for {token_address}: {e}")
        return {}

def get_token_metadata(token_addresses: list, chain: str) -> list:
    """
    Get token metadata (including possible_spam flags).
    https://docs.moralis.com/data-api/evm/reference/get-token-metadata

    Results are cached for 5 minutes (TTL) — metadata rarely changes.
    """
    if not MORALIS_API_KEY or not token_addresses:
        return []

    # ── Cache hit ─────────────────────────────────────────────────────────────
    cached = _get_cached_metadata(token_addresses, chain)
    if cached is not None:
        return cached

    try:
        chain_lower = chain.lower()
        if chain_lower == "solana":
            url = f"{SOLANA_API_BASE}/token/mainnet/{token_addresses[0]}/metadata"
            _rate_check()
            res = get_session().get(url, headers=_get_headers(), timeout=4)
            if res.status_code == 200:
                data = res.json()
                if isinstance(data, dict):
                    result = [data]
                    _set_cached_metadata(token_addresses, chain, result)
                    return result
            return []
        else:
            hex_chain = _chain_to_hex(chain_lower)
            url = f"{MORALIS_API_BASE}/erc20/metadata?chain={hex_chain}"
            for addr in token_addresses:
                url += f"&addresses={addr}"

            _rate_check()
            res = get_session().get(url, headers=_get_headers(), timeout=4)
            if res.status_code == 200:
                result = res.json()
                _set_cached_metadata(token_addresses, chain, result)
                return result
            return []
    except Exception as e:
        logger.debug(f"Exception fetching Moralis metadata: {e}")
        return []
