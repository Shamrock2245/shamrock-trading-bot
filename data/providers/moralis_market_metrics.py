"""
data/providers/moralis_market_metrics.py — Market Metrics Provider (Migrated June 2026)

MIGRATION NOTES (June 4, 2026 — updated June 15, 2026):
  The following Moralis endpoints were REMOVED June 4, 2026:
    ❌ GET /volume/chains                          → DEAD
    ❌ GET /volume/categories                      → DEAD
    ❌ GET /volume/timeseries                      → DEAD
    ❌ GET /market-data/global/market-cap          → DEAD
    ❌ GET /market-data/top-cryptocurrencies-by-market-cap → DEAD
    ❌ ALL /discovery/* endpoints                  → DEAD (entire namespace removed)

  REPLACEMENT OPTIONS:
    ✅ POST /tokens/filtered                       → server-side screener (replaces discovery)
    ✅ GET /tokens/{addr}/analytics                → per-token buy/sell velocity
    ✅ GET /tokens/trending                        → chain-level heat proxy

  CURRENT FALLBACK (working):
    - CoinGecko /api/v3/global  → global market cap, BTC dominance (free, no key)
    - CoinGecko /api/v3/coins/markets → top coins by market cap (free, no key)
"""


from __future__ import annotations

import logging
import threading
import time
from typing import Optional, Any

import requests as _requests

from data.http_session import get_session
from config import settings

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────
MORALIS_API_KEY: str = getattr(settings, "MORALIS_API_KEY", "")
BASE_URL = "https://deep-index.moralis.io/api/v2.2"
COINGECKO_BASE = "https://api.coingecko.com/api/v3"

# Cache TTLs
VOLUME_CACHE_TTL = 600      # 10 minutes
MARKET_CAP_CACHE_TTL = 900  # 15 minutes

_cache: dict[str, dict] = {}
_cache_lock = threading.Lock()

# Rate limiter — shared Pro-tier global limiter (60 RPS, CU-budget-aware)
from data.providers.moralis_rate_limiter import rate_check as _rate_check

# Chain hex IDs (kept for reference / future Universal API migration)
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


def _coingecko_get(path: str, params: dict | None = None) -> dict | list | None:
    """CoinGecko public API call — free tier, no key required."""
    try:
        resp = get_session().get(
            f"{COINGECKO_BASE}{path}",
            params=params or {},
            timeout=12,
        )
        if resp.status_code == 429:
            logger.debug("CoinGecko rate limited — returning None")
            return None
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.debug(f"CoinGecko error ({path}): {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Chain Volume / Heat Metrics
# Moralis /volume/chains REMOVED June 2026 — replaced with CoinGecko fallback
# ─────────────────────────────────────────────────────────────────────────────

def get_volume_by_chain() -> dict[str, dict]:
    """
    Get 24h on-chain activity heat scores per chain.

    NOTE: Moralis /volume/chains was removed June 4 2026. The Universal Market
    Metrics API replacement is documented but not yet live (returns 404).
    Uses CoinGecko /global for market cap dominance as a chain heat proxy.
    Cache TTL: 10 minutes
    """
    cache_key = "volume_by_chain"
    if _is_cached(cache_key, VOLUME_CACHE_TTL):
        return _get_cache(cache_key)

    cg_data = _coingecko_get("/global")
    if cg_data:
        data = cg_data.get("data", {})
        total_vol = _safe_float(data.get("total_volume", {}).get("usd", 0))
        mcp = data.get("market_cap_percentage", {})
        # Approximate chain heat from market cap dominance
        chain_proxies = {
            "ethereum": mcp.get("eth", 10.0),
            "base":     mcp.get("eth", 10.0) * 0.15,
            "arbitrum": mcp.get("eth", 10.0) * 0.20,
            "polygon":  mcp.get("matic", 1.0),
            "bsc":      mcp.get("bnb", 3.0),
            "solana":   mcp.get("sol", 3.0),
        }
        result = {}
        for chain, dominance_pct in chain_proxies.items():
            est_vol = total_vol * (dominance_pct / 100.0)
            result[chain] = {
                "volume_24h": est_vol,
                "volume_change_pct": 0.0,
                "transactions_24h": 0,
                "active_addresses": 0,
                "heat_score": min(100.0, dominance_pct * 3),
                "source": "coingecko_dominance_proxy",
            }
        _set_cache(cache_key, result)
        logger.info(f"Market Metrics: Chain heat loaded via CoinGecko proxy ({len(result)} chains)")
        return result

    # Last resort: neutral heat scores so macro_filter never fully blocks
    fallback = {
        ch: {"volume_24h": 0, "volume_change_pct": 0, "transactions_24h": 0,
             "active_addresses": 0, "heat_score": 50.0, "source": "static_fallback"}
        for ch in ["ethereum", "base", "arbitrum", "polygon", "bsc", "solana"]
    }
    _set_cache(cache_key, fallback)
    return fallback


def get_chain_heat(chain: str) -> float:
    """
    Get a 0-100 heat score for a specific chain based on 24h activity.
    Higher = more active = better conditions for gem sniping.
    """
    volumes = get_volume_by_chain()
    return volumes.get(chain, {}).get("heat_score", 50.0)


def get_volume_by_category() -> dict[str, dict]:
    """
    Get 24h volume statistics per DeFi category.

    NOTE: Moralis /volume/categories was removed June 4 2026. No direct
    replacement exists. Returns empty dict — callers must handle gracefully.
    """
    cache_key = "volume_by_category"
    if _is_cached(cache_key, VOLUME_CACHE_TTL):
        return _get_cache(cache_key)

    # Moralis endpoint dead, Universal API not yet live.
    # Return static category placeholders so callers don't crash.
    result = {
        "DEX":         {"volume_24h": 0, "volume_change_pct": 0, "transactions_24h": 0, "source": "unavailable"},
        "Lending":     {"volume_24h": 0, "volume_change_pct": 0, "transactions_24h": 0, "source": "unavailable"},
        "Derivatives": {"volume_24h": 0, "volume_change_pct": 0, "transactions_24h": 0, "source": "unavailable"},
        "Yield":       {"volume_24h": 0, "volume_change_pct": 0, "transactions_24h": 0, "source": "unavailable"},
    }
    _set_cache(cache_key, result)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Global Market Cap & BTC Dominance
# Moralis /market-data/global/market-cap REMOVED June 2026 → CoinGecko
# ─────────────────────────────────────────────────────────────────────────────

def get_global_market_metrics() -> Optional[dict]:
    """
    Fetch global crypto market metrics: total market cap, BTC dominance, 24h change.
    Used by macro_filter.py to determine overall market regime.

    NOTE: Moralis /market-data/global/market-cap removed June 4 2026.
    Now uses CoinGecko /global (free, no key required).
    Cache TTL: 15 minutes
    """
    cache_key = "global_market_metrics"
    if _is_cached(cache_key, MARKET_CAP_CACHE_TTL):
        return _get_cache(cache_key)

    cg_data = _coingecko_get("/global")
    if not cg_data:
        return None

    data = cg_data.get("data", {})
    total_mcap = _safe_float(data.get("total_market_cap", {}).get("usd", 0))
    total_vol = _safe_float(data.get("total_volume", {}).get("usd", 0))
    mcp = data.get("market_cap_percentage", {})

    result = {
        "total_market_cap_usd": total_mcap,
        "btc_dominance_pct": _safe_float(mcp.get("btc", 0)),
        "eth_dominance_pct": _safe_float(mcp.get("eth", 0)),
        "market_cap_change_24h_pct": _safe_float(data.get("market_cap_change_percentage_24h_usd", 0)),
        "total_volume_24h_usd": total_vol,
        "defi_market_cap_usd": 0.0,  # Not available from CoinGecko free tier
        "last_updated": time.time(),
        "source": "coingecko",
    }
    _set_cache(cache_key, result)
    logger.info(
        f"Market Metrics: Global mcap=${result['total_market_cap_usd']/1e12:.2f}T | "
        f"BTC dom={result['btc_dominance_pct']:.1f}% | "
        f"24h chg={result['market_cap_change_24h_pct']:+.2f}%"
    )
    return result


def get_top_coins_by_market_cap(limit: int = 10) -> list[dict]:
    """
    Fetch top cryptocurrencies by market cap.
    Used to check BTC, ETH, SOL price trends for macro regime.

    NOTE: Moralis /market-data/top-cryptocurrencies-by-market-cap removed June 4 2026.
    Now uses CoinGecko /coins/markets (free, no key required).
    Cache TTL: 15 minutes
    """
    cache_key = f"top_coins_mcap_{limit}"
    if _is_cached(cache_key, MARKET_CAP_CACHE_TTL):
        return _get_cache(cache_key)

    cg_data = _coingecko_get("/coins/markets", {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": limit,
        "page": 1,
        "sparkline": "false",
        "price_change_percentage": "24h,7d",
    })
    if not cg_data:
        return []

    result = [
        {
            "symbol": c.get("symbol", "").upper(),
            "name": c.get("name", ""),
            "price_usd": _safe_float(c.get("current_price", 0)),
            "market_cap_usd": _safe_float(c.get("market_cap", 0)),
            "price_change_24h_pct": _safe_float(c.get("price_change_percentage_24h", 0)),
            "price_change_7d_pct": _safe_float(c.get("price_change_percentage_7d_in_currency", 0)),
            "volume_24h_usd": _safe_float(c.get("total_volume", 0)),
            "source": "coingecko",
        }
        for c in (cg_data if isinstance(cg_data, list) else [])
    ]
    _set_cache(cache_key, result)
    return result


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

    # 1. Global market metrics (CoinGecko fallback)
    global_metrics = get_global_market_metrics()
    if global_metrics:
        result["btc_dominance"] = global_metrics.get("btc_dominance_pct", 0.0)
        result["total_market_cap_usd"] = global_metrics.get("total_market_cap_usd", 0.0)
        result["market_cap_change_24h_pct"] = global_metrics.get("market_cap_change_24h_pct", 0.0)

    # 2. Top coins for BTC/ETH price context (CoinGecko fallback)
    top_coins = get_top_coins_by_market_cap(limit=5)
    for coin in top_coins:
        if coin["symbol"] == "BTC":
            result["btc_price_usd"] = coin["price_usd"]
            result["btc_change_24h_pct"] = coin["price_change_24h_pct"]
        elif coin["symbol"] == "ETH":
            result["eth_change_24h_pct"] = coin["price_change_24h_pct"]

    # 3. Chain heat scores (CoinGecko dominance proxy)
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

    if market_cap_change > 3.0 and btc_change > 2.0:
        result["regime"] = "BULL"
        result["confidence"] = min(100.0, (market_cap_change + btc_change) * 5)
    elif market_cap_change < -3.0 and btc_change < -2.0:
        result["regime"] = "BEAR"
        result["confidence"] = min(100.0, abs(market_cap_change + btc_change) * 5)
    elif btc_dominance > 60.0 and market_cap_change < -1.0:
        result["regime"] = "BTC_DOMINANCE"
        result["confidence"] = min(100.0, btc_dominance - 50.0)
    elif market_cap_change > 0.5:
        result["regime"] = "MILD_BULL"
        result["confidence"] = min(100.0, market_cap_change * 10)
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
