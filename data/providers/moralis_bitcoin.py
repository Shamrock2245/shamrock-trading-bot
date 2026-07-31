"""
data/providers/moralis_bitcoin.py — Moralis Bitcoin Data API Wrapper.

Provides real-time and historical Bitcoin price data, wallet monitoring,
and block tracking using the Moralis Bitcoin API endpoints.
Uses a robust caching layer to conserve Moralis API Compute Units (CUs).
"""

import logging
import time
import threading
from typing import Any, Optional
from data.http_session import get_session
from config import settings

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Config & Caching
# ─────────────────────────────────────────────────────────────────────────────
MORALIS_API_KEY: str = getattr(settings, "MORALIS_API_KEY", "")
BASE_URL = "https://deep-index.moralis.io/api/v2.2"

# Cache TTLs
FAST_CACHE_TTL = 120   # 2 minutes for real-time prices
SLOW_CACHE_TTL = 3600  # 1 hour for historical/structural data

_cache: dict[str, dict] = {}
_cache_lock = threading.Lock()

# Rate Limiting
# Rate limiter — shared Pro-tier global limiter (60 RPS, CU-budget-aware)
from data.providers.moralis_rate_limiter import rate_check as _rate_check
_rate_lock = threading.Lock()


def _headers() -> dict:
    return {
        "accept": "application/json",
        "X-API-Key": MORALIS_API_KEY
    }


def _available() -> bool:
    return bool(MORALIS_API_KEY)




def _is_cached(key: str, ttl: int = SLOW_CACHE_TTL) -> bool:
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
# Bitcoin Price & Market Overview
# ─────────────────────────────────────────────────────────────────────────────

def get_bitcoin_price() -> Optional[dict]:
    """
    Fetch the real-time Bitcoin price and 24h change.
    Uses WBTC ERC-20 price endpoint as primary source (reliable, 17 CU).
    Falls back to CoinGecko free API if Moralis fails.
    
    CU Cost: 17
    """
    if not _available():
        return None
        
    cache_key = "btc_realtime_price"
    if _is_cached(cache_key, FAST_CACHE_TTL):
        return _get_cache(cache_key)
        
    _rate_check()
    try:
        # Primary: WBTC price on Ethereum (reliable endpoint, 17 CU)
        # WBTC address: 0x2260fac5e5542a773aa44fbcfedf7c193bc2c599
        resp = get_session().get(
            f"{BASE_URL}/erc20/0x2260fac5e5542a773aa44fbcfedf7c193bc2c599/price",
            params={"chain": "eth", "include": "percent_change"},
            headers=_headers(),
            timeout=10,
        )
        resp.raise_for_status()
        price_data = resp.json()
        result = {
            "price_usd": _safe_float(price_data.get("usdPrice")),
            "market_cap_usd": 0.0,  # Not available from this endpoint
            "price_change_24h_pct": _safe_float(price_data.get("24hrPercentChange", 0.0)),
            "price_change_7d_pct": 0.0,
            "volume_24h_usd": 0.0,
            "last_updated": time.time()
        }
        if result["price_usd"] > 0:
            _set_cache(cache_key, result)
            return result
    except Exception as e:
        logger.debug(f"WBTC price fetch failed: {e}")

    # Fallback: CoinGecko free API (no key required)
    try:
        resp = get_session().get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": "bitcoin", "vs_currencies": "usd", "include_24hr_change": "true"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json().get("bitcoin", {})
        result = {
            "price_usd": _safe_float(data.get("usd")),
            "market_cap_usd": 0.0,
            "price_change_24h_pct": _safe_float(data.get("usd_24h_change", 0.0)),
            "price_change_7d_pct": 0.0,
            "volume_24h_usd": 0.0,
            "last_updated": time.time()
        }
        if result["price_usd"] > 0:
            _set_cache(cache_key, result)
            return result
    except Exception as e:
        logger.error(f"Error fetching Bitcoin price (all sources failed): {e}")
    
    return None

def get_native_bitcoin_balance(address: str) -> Optional[float]:
    """
    Fetch native Bitcoin balance using Moralis Bitcoin address API.

    NOTE: The EVM-style ``/{address}/balance?chain=bitcoin`` endpoint returns
    HTTP 400 for bc1/xpub addresses (PYTHON-6A). Use the Bitcoin-specific path.

    CU Cost: 10
    """
    if not _available() or not address:
        return None

    cache_key = f"btc_balance_{address}"
    if _is_cached(cache_key, SLOW_CACHE_TTL):
        return _get_cache(cache_key)

    _rate_check(10)
    try:
        # Correct Bitcoin API path (also used by get_bitcoin_wallet_balance)
        resp = get_session().get(
            f"{BASE_URL}/bitcoin/mainnet/address/{address}/balance",
            headers=_headers(),
            timeout=10,
        )
        if resp.status_code != 200:
            body = (resp.text or "")[:200]
            # 4xx = unsupported address / API shape — not a code crash
            log_fn = logger.warning if 400 <= resp.status_code < 500 else logger.error
            log_fn(
                f"Bitcoin balance fetch failed for {address[:16]}… "
                f"({resp.status_code}): {body}"
            )
            return None
        data = resp.json()
        # Same field parse as get_bitcoin_wallet_balance (BTC units)
        balance_btc = _safe_float(data.get("balance"))
        _set_cache(cache_key, balance_btc)
        return balance_btc
    except Exception as e:
        logger.warning(f"Error fetching native Bitcoin balance for {address[:16]}…: {e}")
        return None


def get_bitcoin_sparkline() -> list[float]:
    """
    Fetch historical price context for Bitcoin (daily close prices for moving averages).
    Uses CoinGecko free API (no key needed) for 200-day daily closes.
    
    CU Cost: 0 (uses CoinGecko, not Moralis)
    """
    cache_key = "btc_sparkline_200d"
    if _is_cached(cache_key, SLOW_CACHE_TTL):
        return _get_cache(cache_key)
        
    try:
        # CoinGecko free API: /coins/{id}/market_chart with 200 days
        resp = get_session().get(
            "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart",
            params={"vs_currency": "usd", "days": 200, "interval": "daily"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        prices = data.get("prices", [])
        
        # prices is [[timestamp_ms, price], ...] in chronological order
        closes = [float(p[1]) for p in prices if len(p) >= 2]
        
        if closes:
            _set_cache(cache_key, closes)
            return closes
            
        return []
    except Exception as e:
        logger.error(f"Error fetching Bitcoin historical sparkline: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Bitcoin Blockchain & Wallet API
# ─────────────────────────────────────────────────────────────────────────────

def get_bitcoin_block(block_height_or_hash: str) -> Optional[dict]:
    """
    Get block details for confirmation tracking.
    
    CU Cost: 100
    """
    if not _available():
        return None
        
    cache_key = f"btc_block_{block_height_or_hash}"
    if _is_cached(cache_key, SLOW_CACHE_TTL):
        return _get_cache(cache_key)
        
    _rate_check()
    try:
        # Moralis Bitcoin Blockchain API
        resp = get_session().get(
            f"{BASE_URL}/bitcoin/mainnet/block/{block_height_or_hash}",
            headers=_headers(),
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        _set_cache(cache_key, data)
        return data
    except Exception as e:
        logger.error(f"Error fetching Bitcoin block {block_height_or_hash}: {e}")
        return None


def get_bitcoin_wallet_balance(address: str) -> float:
    """
    Get Bitcoin balance for our cold/reserve wallet address.
    
    CU Cost: 10
    """
    if not _available() or not address:
        return 0.0
        
    cache_key = f"btc_bal_{address}"
    if _is_cached(cache_key, FAST_CACHE_TTL):
        return _get_cache(cache_key)
        
    _rate_check()
    try:
        resp = get_session().get(
            f"{BASE_URL}/bitcoin/mainnet/address/{address}/balance",
            headers=_headers(),
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        balance_btc = _safe_float(data.get("balance"))
        _set_cache(cache_key, balance_btc)
        return balance_btc
    except Exception as e:
        logger.error(f"Error fetching Bitcoin balance for {address}: {e}")
        return 0.0
