"""
data/providers/moralis_market_metrics.py — Moralis Universal Market Metrics API.

Provides on-chain market-wide volume and activity metrics across chains and categories.
Used to power the macro regime filter and adaptive mode system.

Endpoints used:
  GET /volume/chains                          → Volume stats per chain (150 CU)
  GET /volume/categories                      → Volume stats per DeFi category (150 CU)
  GET /volume/timeseries                      → Time-series volume data (150 CU)
  GET /volume/timeseries/categories           → Category time-series volume (150 CU)
  GET /market-data/global/market-cap          → Global crypto market cap + BTC dominance (200 CU)
  GET /market-data/top-cryptocurrencies-by-market-cap → Top coins by market cap (200 CU)

CU Conservation Strategy:
  - 10-minute cache for chain/category volume (fast-moving but not tick-level)
  - 15-minute cache for global market cap (changes slowly)
  - Only called once per scan cycle (not per token)
  - Results shared across all scan cycle consumers via module-level cache
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

# Cache TTLs
VOLUME_CACHE_TTL = 600     # 10 minutes
MARKET_CAP_CACHE_TTL = 900  # 15 minutes

_cache: dict[str, dict] = {}
_cache_lock = threading.Lock()

# Rate limiter — shared Pro-tier global limiter (60 RPS, CU-budget-aware)
from data.providers.moralis_rate_limiter import rate_check as _rate_check
_rate_lock = threading.Lock()

# Chain hex IDs
CHAIN_HEX = {
    "ethereum": "0x1",
    "base": "0x2105",
    "arbitrum": "0xa4b1",
    "polygon": "0x89",
    "bsc": "0x38",
}


def _headers() -> dict:
    return {
        "accept": "application/json",
        "X-API-Key": MORALIS_API_KEY,
    }


def _available() -> bool:
    return bool(MORALIS_API_KEY)




def _is_cached(key: str, ttl: int = VOLUME_CACHE_TTL) -> bool:
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


def _safe_float(val: Any) -> float:
    try:
        return float(val) if val is not None else 0.0
    except (ValueError, TypeError):
        return 0.0


def _safe_int(val: Any) -> int:
    try:
        return int(val) if val is not None else 0
    except (ValueError, TypeError):
        return 0


# ─────────────────────────────────────────────────────────────────────────────
# Chain Volume Metrics
# ─────────────────────────────────────────────────────────────────────────────

def get_volume_by_chain() -> dict[str, dict]:
    """
    Get 24h on-chain volume statistics per chain.
    Returns a dict keyed by chain name with volume, tx count, and heat score.
    
    CU Cost: 150
    Cache TTL: 10 minutes
    """
    if not _available():
        return {}
    
    cache_key = "volume_by_chain"
    if _is_cached(cache_key, VOLUME_CACHE_TTL):
        return _get_cache(cache_key)
    
    _rate_check()
    try:
        resp = get_session().get(
            f"{BASE_URL}/volume/chains",
            headers=_headers(),
            timeout=10,
        )
        if resp.status_code in (400, 404, 429):
            return {}
        resp.raise_for_status()
        data = resp.json()
        chains_raw = data.get("result", data) if isinstance(data, dict) else data
        
        result = {}
        for c in (chains_raw or []):
            chain_id = c.get("chain_id", "")
            chain_name = next((k for k, v in CHAIN_HEX.items() if v == chain_id), chain_id)
            vol_24h = _safe_float(c.get("volume_24h", 0))
            result[chain_name] = {
                "volume_24h": vol_24h,
                "volume_change_pct": _safe_float(c.get("volume_change_24h_percentage", 0)),
                "transactions_24h": _safe_int(c.get("transactions_24h", 0)),
                "active_addresses": _safe_int(c.get("active_addresses_24h", 0)),
                "heat_score": min(100.0, vol_24h / 1_000_000),  # Normalize to 0-100
            }
        
        _set_cache(cache_key, result)
        logger.info(f"Market Metrics: Chain volumes loaded for {len(result)} chains")
        return result
    except Exception as e:
        logger.debug(f"Volume by chain error: {e}")
        return {}


def get_chain_heat(chain: str) -> float:
    """
    Get a 0-100 heat score for a specific chain based on 24h volume.
    Higher = more active = better conditions for gem sniping.
    """
    volumes = get_volume_by_chain()
    return volumes.get(chain, {}).get("heat_score", 50.0)


def get_volume_by_category() -> dict[str, dict]:
    """
    Get 24h volume statistics per DeFi category (DEX, Lending, Derivatives, etc.)
    Used to identify which DeFi sectors are hot.
    
    CU Cost: 150
    Cache TTL: 10 minutes
    """
    if not _available():
        return {}
    
    cache_key = "volume_by_category"
    if _is_cached(cache_key, VOLUME_CACHE_TTL):
        return _get_cache(cache_key)
    
    _rate_check()
    try:
        resp = get_session().get(
            f"{BASE_URL}/volume/categories",
            headers=_headers(),
            timeout=10,
        )
        if resp.status_code in (400, 404, 429):
            return {}
        resp.raise_for_status()
        data = resp.json()
        categories_raw = data.get("result", data) if isinstance(data, dict) else data
        
        result = {}
        for cat in (categories_raw or []):
            cat_name = cat.get("category", cat.get("name", ""))
            if cat_name:
                result[cat_name] = {
                    "volume_24h": _safe_float(cat.get("volume_24h", 0)),
                    "volume_change_pct": _safe_float(cat.get("volume_change_24h_percentage", 0)),
                    "transactions_24h": _safe_int(cat.get("transactions_24h", 0)),
                }
        
        _set_cache(cache_key, result)
        return result
    except Exception as e:
        logger.debug(f"Volume by category error: {e}")
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# Global Market Cap & BTC Dominance
# ─────────────────────────────────────────────────────────────────────────────

def get_global_market_metrics() -> Optional[dict]:
    """
    Fetch global crypto market metrics: total market cap, BTC dominance, 24h change.
    Used by macro_filter.py to determine overall market regime.
    
    CU Cost: 200
    Cache TTL: 15 minutes
    """
    if not _available():
        return None
    
    cache_key = "global_market_metrics"
    if _is_cached(cache_key, MARKET_CAP_CACHE_TTL):
        return _get_cache(cache_key)
    
    _rate_check()
    try:
        resp = get_session().get(
            f"{BASE_URL}/market-data/global/market-cap",
            headers=_headers(),
            timeout=10,
        )
        if resp.status_code in (400, 404, 429):
            return None
        resp.raise_for_status()
        data = resp.json()
        
        result = {
            "total_market_cap_usd": _safe_float(data.get("total_market_cap", 0)),
            "btc_dominance_pct": _safe_float(data.get("btc_dominance", 0)),
            "eth_dominance_pct": _safe_float(data.get("eth_dominance", 0)),
            "market_cap_change_24h_pct": _safe_float(data.get("market_cap_change_24h_percentage", 0)),
            "total_volume_24h_usd": _safe_float(data.get("total_volume_24h", 0)),
            "defi_market_cap_usd": _safe_float(data.get("defi_market_cap", 0)),
            "last_updated": time.time(),
        }
        _set_cache(cache_key, result)
        logger.info(
            f"Market Metrics: Global market cap=${result['total_market_cap_usd']/1e12:.2f}T | "
            f"BTC dominance={result['btc_dominance_pct']:.1f}%"
        )
        return result
    except Exception as e:
        logger.debug(f"Global market metrics error: {e}")
        return None


def get_top_coins_by_market_cap(limit: int = 10) -> list[dict]:
    """
    Fetch top cryptocurrencies by market cap.
    Used to check BTC, ETH, SOL price trends for macro regime.
    
    CU Cost: 200
    Cache TTL: 15 minutes
    """
    if not _available():
        return []
    
    cache_key = f"top_coins_mcap_{limit}"
    if _is_cached(cache_key, MARKET_CAP_CACHE_TTL):
        return _get_cache(cache_key)
    
    _rate_check()
    try:
        resp = get_session().get(
            f"{BASE_URL}/market-data/top-cryptocurrencies-by-market-cap",
            params={"top": limit},
            headers=_headers(),
            timeout=10,
        )
        if resp.status_code in (400, 404, 429):
            return []
        resp.raise_for_status()
        data = resp.json()
        coins = data.get("result", []) if isinstance(data, dict) else []
        
        result = [
            {
                "symbol": c.get("symbol", "").upper(),
                "name": c.get("name", ""),
                "price_usd": _safe_float(c.get("price_usd", 0)),
                "market_cap_usd": _safe_float(c.get("market_cap_usd", 0)),
                "price_change_24h_pct": _safe_float(c.get("price_24h_percent_change", 0)),
                "price_change_7d_pct": _safe_float(c.get("price_7d_percent_change", 0)),
                "volume_24h_usd": _safe_float(c.get("volume_usd", 0)),
            }
            for c in coins
        ]
        _set_cache(cache_key, result)
        return result
    except Exception as e:
        logger.debug(f"Top coins by market cap error: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Composite Regime Signal
# ─────────────────────────────────────────────────────────────────────────────

def get_market_regime_signal() -> dict:
    """
    Compute a composite market regime signal from all available metrics.
    Returns a dict with regime classification and supporting data.
    
    Used by macro_filter.py as a primary data source.
    """
    result = {
        "regime": "NEUTRAL",
        "btc_dominance": 0.0,
        "total_market_cap_usd": 0.0,
        "market_cap_change_24h_pct": 0.0,
        "btc_price_usd": 0.0,
        "btc_change_24h_pct": 0.0,
        "eth_change_24h_pct": 0.0,
        "chain_volumes": {},
        "hot_chains": [],
        "confidence": 0.0,
    }
    
    # 1. Global market metrics
    global_metrics = get_global_market_metrics()
    if global_metrics:
        result["btc_dominance"] = global_metrics.get("btc_dominance_pct", 0.0)
        result["total_market_cap_usd"] = global_metrics.get("total_market_cap_usd", 0.0)
        result["market_cap_change_24h_pct"] = global_metrics.get("market_cap_change_24h_pct", 0.0)
    
    # 2. Top coins for BTC/ETH price context
    top_coins = get_top_coins_by_market_cap(limit=5)
    for coin in top_coins:
        if coin["symbol"] == "BTC":
            result["btc_price_usd"] = coin["price_usd"]
            result["btc_change_24h_pct"] = coin["price_change_24h_pct"]
        elif coin["symbol"] == "ETH":
            result["eth_change_24h_pct"] = coin["price_change_24h_pct"]
    
    # 3. Chain volumes
    chain_volumes = get_volume_by_chain()
    result["chain_volumes"] = chain_volumes
    result["hot_chains"] = [
        chain for chain, data in chain_volumes.items()
        if data.get("heat_score", 0) > 60
    ]
    
    # 4. Regime classification
    market_cap_change = result["market_cap_change_24h_pct"]
    btc_change = result["btc_change_24h_pct"]
    btc_dominance = result["btc_dominance"]
    
    # Strong bull: market cap up >3%, BTC up >2%
    if market_cap_change > 3.0 and btc_change > 2.0:
        result["regime"] = "BULL"
        result["confidence"] = min(100.0, (market_cap_change + btc_change) * 5)
    # Strong bear: market cap down >3%, BTC down >2%
    elif market_cap_change < -3.0 and btc_change < -2.0:
        result["regime"] = "BEAR"
        result["confidence"] = min(100.0, abs(market_cap_change + btc_change) * 5)
    # BTC dominance rising + altcoin bleed = altcoin bear
    elif btc_dominance > 60.0 and market_cap_change < -1.0:
        result["regime"] = "BTC_DOMINANCE"
        result["confidence"] = min(100.0, btc_dominance - 50.0)
    # Mild positive
    elif market_cap_change > 0.5:
        result["regime"] = "MILD_BULL"
        result["confidence"] = min(100.0, market_cap_change * 10)
    # Mild negative
    elif market_cap_change < -0.5:
        result["regime"] = "MILD_BEAR"
        result["confidence"] = min(100.0, abs(market_cap_change) * 10)
    else:
        result["regime"] = "NEUTRAL"
        result["confidence"] = 50.0
    
    logger.info(
        f"Market Regime: {result['regime']} | "
        f"BTC={result['btc_change_24h_pct']:+.1f}% | "
        f"MCap={result['market_cap_change_24h_pct']:+.1f}% | "
        f"BTC Dom={result['btc_dominance']:.1f}% | "
        f"Hot chains: {result['hot_chains']}"
    )
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
            "getVolumeStatsByChain (150 CU)",
            "getVolumeStatsByCategory (150 CU)",
            "getGlobalMarketCap (200 CU)",
            "getTopCryptocurrenciesByMarketCap (200 CU)",
        ],
    }
