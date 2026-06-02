"""
data/providers/moralis_price.py — Moralis Pro Token Price & OHLCV Provider.

Provides high-performance, cached access to Moralis pricing endpoints:

  1. get_token_price(address, chain)   → Single token price (1 CU)
  2. get_batch_prices(tokens)          → Up to 25 tokens in one call (100 CU)
  3. get_ohlcv(pair_address, chain)    → OHLCV candles for Fib engine (150 CU)
  4. get_token_metadata(address, chain) → Name, symbol, decimals (1 CU)

All endpoints use the deep-index.moralis.io/api/v2.2 base URL.
Rate limited to 25 req/min with 5-minute caching.
"""

import logging
import time
from typing import Optional

import pandas as pd
from data.http_session import get_session

from config import settings

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────
MORALIS_API_KEY: str = getattr(settings, "MORALIS_API_KEY", "")
BASE_URL = "https://deep-index.moralis.io/api/v2.2"

# Internal chain name → Moralis chain hex (required for API calls)
CHAIN_HEX: dict[str, str] = {
    "ethereum":  "0x1",
    "base":      "0x2105",
    "arbitrum":  "0xa4b1",
    "polygon":   "0x89",
    "bsc":       "0x38",
    "avalanche": "0xa86a",
}

# Moralis OHLCV timeframe slugs
TIMEFRAME_MAP = {
    "1m": "1min", "5m": "5min", "15m": "15min", "30m": "30min",
    "1h": "1hour", "4h": "4hour", "1d": "1day", "1w": "1week",
}

# Cache
CACHE_TTL = 300  # 5 minutes
_cache: dict[str, dict] = {}

# Rate limiter — shared Pro-tier global limiter (60 RPS, CU-budget-aware)
from data.providers.moralis_rate_limiter import rate_check as _rate_check, get_stats as _get_rate_stats


def _headers() -> dict:
    return {"accept": "application/json", "X-API-Key": MORALIS_API_KEY}


def _json_headers() -> dict:
    return {
        "accept": "application/json",
        "Content-Type": "application/json",
        "X-API-Key": MORALIS_API_KEY,
    }


def _is_cached(key: str) -> bool:
    entry = _cache.get(key)
    return bool(entry and (time.time() - entry.get("ts", 0)) < CACHE_TTL)


def _set_cache(key: str, data) -> None:
    _cache[key] = {"data": data, "ts": time.time()}


def _get_cache(key: str):
    return _cache.get(key, {}).get("data")


def _available(chain: str) -> bool:
    return bool(MORALIS_API_KEY) and chain in CHAIN_HEX


# ─────────────────────────────────────────────────────────────────────────────
# 1. Single Token Price  (GET /erc20/{address}/price)  — 1 CU
# ─────────────────────────────────────────────────────────────────────────────
def get_token_price(
    token_address: str,
    chain: str,
    include_percent_change: bool = True,
) -> Optional[dict]:
    """
    Get real-time price for a single ERC20 token.

    Returns dict with:
      - usd_price: float
      - native_price: dict with value + symbol
      - percent_change_24h: float (if requested)
      - token_name, token_symbol, token_decimals

    Cost: 1 Compute Unit per call.
    """
    if not _available(chain):
        return None

    cache_key = f"price_{chain}_{token_address.lower()}"
    if _is_cached(cache_key):
        return _get_cache(cache_key)

    _rate_check()
    try:
        params = {"chain": CHAIN_HEX[chain]}
        if include_percent_change:
            params["include"] = "percent_change"

        resp = get_session().get(
            f"{BASE_URL}/erc20/{token_address}/price",
            params=params,
            headers=_headers(),
            timeout=10,
        )
        if resp.status_code in (400, 404):
            logger.debug(f"Moralis price: token not found {token_address[:12]}... on {chain}")
            return None
        if resp.status_code in (402, 403):
            return None
        resp.raise_for_status()

        data = resp.json()
        result = {
            "token_address": data.get("tokenAddress", token_address),
            "token_name": data.get("tokenName", ""),
            "token_symbol": data.get("tokenSymbol", ""),
            "token_decimals": int(data.get("tokenDecimals", 18)),
            "usd_price": float(data.get("usdPrice", 0) or 0),
            "usd_price_formatted": data.get("usdPriceFormatted", ""),
            "native_price_value": data.get("nativePrice", {}).get("value", "0"),
            "native_price_symbol": data.get("nativePrice", {}).get("symbol", ""),
            "percent_change_24h": float(data.get("24hrPercentChange", 0) or 0),
            "exchange_name": data.get("exchangeName", ""),
            "exchange_address": data.get("exchangeAddress", ""),
            "pair_address": data.get("pairAddress", ""),
            "chain": chain,
        }
        _set_cache(cache_key, result)
        return result

    except Exception as e:
        logger.debug(f"Moralis price error for {token_address[:12]}... on {chain}: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 2. Batch Token Prices  (POST /erc20/prices)  — 100 CU per call
# ─────────────────────────────────────────────────────────────────────────────
def get_batch_prices(
    tokens: list[dict],
) -> dict[str, dict]:
    """
    Get prices for multiple tokens in a single API call.

    Args:
        tokens: list of {"token_address": "0x...", "chain": "base"}
                Max 25 tokens per call.

    Returns:
        Dict keyed by lowercase token_address → price data.

    Cost: 100 Compute Units per call.
    """
    if not MORALIS_API_KEY or not tokens:
        return {}

    tokens = tokens[:25]  # Moralis max is 25

    # Build request body
    payload = {
        "tokens": [
            {
                "token_address": t["token_address"],
                "chain": CHAIN_HEX.get(t.get("chain", ""), "0x1"),
            }
            for t in tokens
            if t.get("token_address") and t.get("chain") in CHAIN_HEX
        ]
    }
    if not payload["tokens"]:
        return {}

    _rate_check()
    try:
        resp = get_session().post(
            f"{BASE_URL}/erc20/prices",
            json=payload,
            headers=_json_headers(),
            timeout=20,
        )
        if resp.status_code in (402, 403):
            logger.debug("Moralis batch prices: plan limitation")
            return {}
        resp.raise_for_status()

        data = resp.json()
        results: dict[str, dict] = {}

        # Response is a list of price objects
        items = data if isinstance(data, list) else data.get("result", [])
        for item in items:
            addr = (item.get("tokenAddress", "") or "").lower()
            if not addr:
                continue
            results[addr] = {
                "token_address": addr,
                "token_name": item.get("tokenName", ""),
                "token_symbol": item.get("tokenSymbol", ""),
                "usd_price": float(item.get("usdPrice", 0) or 0),
                "percent_change_24h": float(item.get("24hrPercentChange", 0) or 0),
            }
            # Also populate cache for individual lookups
            for t in tokens:
                if t["token_address"].lower() == addr:
                    cache_key = f"price_{t['chain']}_{addr}"
                    _set_cache(cache_key, results[addr])
                    break

        logger.info(f"Moralis batch prices: {len(results)}/{len(tokens)} tokens priced")
        return results

    except Exception as e:
        logger.warning(f"Moralis batch prices error: {e}")
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# 3. OHLCV Candles  (GET /pairs/{address}/ohlcv)  — 150 CU per call
# ─────────────────────────────────────────────────────────────────────────────
def get_ohlcv(
    pair_address: str,
    chain: str,
    timeframe: str = "1h",
    limit: int = 200,
    currency: str = "usd",
) -> Optional[pd.DataFrame]:
    """
    Fetch OHLCV candles from Moralis for a DEX pair.

    Args:
        pair_address: DEX pair/pool contract address
        chain: Internal chain name (e.g., "base")
        timeframe: Candle timeframe — "1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"
        limit: Max candles to return (Moralis max varies by timeframe)
        currency: "usd" or "token" denominated prices

    Returns:
        DataFrame with DatetimeIndex and columns: open, high, low, close, volume
        Returns None if insufficient data.

    Cost: 150 Compute Units per call.
    """
    if not _available(chain):
        return None
    if not pair_address:
        return None

    moralis_tf = TIMEFRAME_MAP.get(timeframe, "1hour")
    cache_key = f"ohlcv_{chain}_{pair_address.lower()}_{moralis_tf}_{limit}"
    if _is_cached(cache_key):
        cached = _get_cache(cache_key)
        if cached is not None:
            return cached

    _rate_check()
    try:
        params = {
            "chain": CHAIN_HEX[chain],
            "timeframe": moralis_tf,
            "limit": min(limit, 500),
            "currency": currency,
        }
        resp = get_session().get(
            f"{BASE_URL}/pairs/{pair_address}/ohlcv",
            params=params,
            headers=_headers(),
            timeout=20,
        )
        if resp.status_code in (400, 404):
            logger.debug(f"Moralis OHLCV: pair not found {pair_address[:12]}... on {chain}")
            _set_cache(cache_key, None)
            return None
        if resp.status_code in (402, 403):
            return None
        resp.raise_for_status()

        data = resp.json()
        candles = data.get("result", data) if isinstance(data, dict) else data

        if not candles or not isinstance(candles, list):
            _set_cache(cache_key, None)
            return None

        rows = []
        for candle in candles:
            try:
                # Moralis returns ISO timestamps or Unix timestamps
                ts_raw = candle.get("timestamp", candle.get("time", ""))
                if isinstance(ts_raw, (int, float)):
                    ts = pd.Timestamp(ts_raw, unit="s", tz="UTC")
                else:
                    ts = pd.Timestamp(ts_raw)
                    if ts.tzinfo is None:
                        ts = ts.tz_localize("UTC")

                rows.append({
                    "timestamp": ts,
                    "open": float(candle.get("open", 0) or 0),
                    "high": float(candle.get("high", 0) or 0),
                    "low": float(candle.get("low", 0) or 0),
                    "close": float(candle.get("close", 0) or 0),
                    "volume": float(candle.get("volume", 0) or 0),
                })
            except Exception:
                continue

        if len(rows) < 5:
            _set_cache(cache_key, None)
            return None

        df = pd.DataFrame(rows)
        df.set_index("timestamp", inplace=True)
        df.sort_index(inplace=True)
        df = df[df["close"] > 0]  # Filter zero-price candles

        if len(df) < 5:
            _set_cache(cache_key, None)
            return None

        _set_cache(cache_key, df)
        logger.info(
            f"Moralis OHLCV: {len(df)} candles ({moralis_tf}) for "
            f"pair {pair_address[:12]}... on {chain}"
        )
        return df

    except Exception as e:
        logger.debug(f"Moralis OHLCV error for {pair_address[:12]}... on {chain}: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 4. Token Metadata  (GET /erc20/metadata)  — 1 CU
# ─────────────────────────────────────────────────────────────────────────────
def get_token_metadata(token_address: str, chain: str) -> Optional[dict]:
    """
    Get token name, symbol, decimals, logo, and total supply.
    Cost: 1 CU.
    """
    if not _available(chain):
        return None

    cache_key = f"meta_{chain}_{token_address.lower()}"
    if _is_cached(cache_key):
        return _get_cache(cache_key)

    _rate_check()
    try:
        resp = get_session().get(
            f"{BASE_URL}/erc20/metadata",
            params={
                "chain": CHAIN_HEX[chain],
                "addresses[]": token_address,
            },
            headers=_headers(),
            timeout=10,
        )
        if resp.status_code in (400, 404):
            return None
        resp.raise_for_status()

        data = resp.json()
        items = data if isinstance(data, list) else [data]
        if not items:
            return None

        item = items[0]
        result = {
            "address": item.get("address", token_address).lower(),
            "name": item.get("name", ""),
            "symbol": item.get("symbol", ""),
            "decimals": int(item.get("decimals", 18)),
            "logo": item.get("logo", item.get("thumbnail", "")),
            "total_supply": item.get("total_supply", "0"),
            "total_supply_formatted": item.get("total_supply_formatted", "0"),
            "verified_contract": item.get("verified_contract", False),
            "chain": chain,
        }
        _set_cache(cache_key, result)
        return result

    except Exception as e:
        logger.debug(f"Moralis metadata error for {token_address[:12]}... on {chain}: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Helper: Quick price lookup (convenience wrapper)
# ─────────────────────────────────────────────────────────────────────────────
def get_price_usd(token_address: str, chain: str) -> float:
    """Return just the USD price. Returns 0.0 on failure."""
    data = get_token_price(token_address, chain)
    return data["usd_price"] if data else 0.0


def get_usage_stats() -> dict:
    """Return cache stats for monitoring."""
    stats = _get_rate_stats()
    return {
        "api_key_configured": bool(MORALIS_API_KEY),
        "cached_keys": len(_cache),
        "rate_limiter": stats,
    }
