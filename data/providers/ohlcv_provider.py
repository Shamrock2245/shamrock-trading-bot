"""
data/providers/ohlcv_provider.py — OHLCV candle data provider.

Fetches historical Open/High/Low/Close/Volume data from multiple sources
in priority order. GeckoTerminal is the primary source because it provides
real pool-level candles (not reconstructed from snapshots), which gives
RSI, MACD, and Bollinger Bands real data to work with.

Source priority:
  1. GeckoTerminal (primary — real pool candles, free, no key, Solana supported)
  2. CoinGecko (secondary — hourly market data for established tokens)
  3. DexScreener snapshot reconstruction (last resort — only 4-5 data points)

The RSI=None issue was caused by DexScreener snapshot data having only 4-5
candles, which is insufficient for RSI(14). GeckoTerminal returns up to 1000
real hourly candles per pool, solving this completely.

Returns pandas DataFrames in the standard format that pandas-ta expects:
  columns: ['open', 'high', 'low', 'close', 'volume']
  index:   DatetimeIndex (UTC)
"""

import logging
import time
from typing import Optional

import pandas as pd
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from config.chains import DEXSCREENER_CHAIN_MAP

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# In-memory OHLCV cache (avoids redundant API calls within a scan cycle)
# ─────────────────────────────────────────────────────────────────────────────

_ohlcv_cache: dict[str, tuple[float, Optional[pd.DataFrame]]] = {}
_OHLCV_CACHE_TTL = 300  # 5 minutes


def _cache_key(token_address: str, chain: str, days: int) -> str:
    return f"ohlcv:{chain}:{token_address.lower()}:{days}"


def _get_cached_ohlcv(token_address: str, chain: str, days: int) -> Optional[pd.DataFrame]:
    key = _cache_key(token_address, chain, days)
    if key in _ohlcv_cache:
        ts, df = _ohlcv_cache[key]
        if time.time() - ts < _OHLCV_CACHE_TTL:
            return df
        del _ohlcv_cache[key]
    return None


def _set_cached_ohlcv(token_address: str, chain: str, days: int, df: Optional[pd.DataFrame]) -> None:
    key = _cache_key(token_address, chain, days)
    _ohlcv_cache[key] = (time.time(), df)


# ─────────────────────────────────────────────────────────────────────────────
# Source 1: GeckoTerminal (primary — real pool candles)
# ─────────────────────────────────────────────────────────────────────────────

GECKOTERMINAL_BASE = "https://api.geckoterminal.com/api/v2"
_last_gt_request = 0.0
_GT_MIN_INTERVAL = 0.5  # GeckoTerminal allows ~2 req/sec on free tier


# Map our chain names to GeckoTerminal network slugs
GECKOTERMINAL_CHAIN_MAP = {
    "ethereum": "eth",
    "base": "base",
    "arbitrum": "arbitrum",
    "polygon": "polygon_pos",
    "bsc": "bsc",
    "solana": "solana",
}


def _gt_rate_limit():
    global _last_gt_request
    elapsed = time.time() - _last_gt_request
    if elapsed < _GT_MIN_INTERVAL:
        time.sleep(_GT_MIN_INTERVAL - elapsed)
    _last_gt_request = time.time()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _fetch_geckoterminal_pools(token_address: str, chain: str) -> list[dict]:
    """Fetch all pools for a token from GeckoTerminal."""
    _gt_rate_limit()
    gt_chain = GECKOTERMINAL_CHAIN_MAP.get(chain, chain)
    url = f"{GECKOTERMINAL_BASE}/networks/{gt_chain}/tokens/{token_address.lower()}/pools"
    params = {"page": 1}
    resp = requests.get(url, params=params, timeout=15)
    if resp.status_code == 404:
        return []
    resp.raise_for_status()
    data = resp.json()
    return data.get("data", [])


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _fetch_geckoterminal_ohlcv(
    chain: str,
    pool_address: str,
    timeframe: str = "hour",
    aggregate: int = 1,
    limit: int = 200,
) -> Optional[pd.DataFrame]:
    """
    Fetch real OHLCV candles from GeckoTerminal for a specific pool.

    Args:
        chain: Our internal chain name (e.g., "base")
        pool_address: DEX pool/pair address
        timeframe: "minute", "hour", or "day"
        aggregate: Candle size (e.g., 1 = 1h, 4 = 4h)
        limit: Max candles to fetch (max 1000)

    Returns:
        DataFrame with DatetimeIndex and OHLCV columns, or None.
    """
    _gt_rate_limit()
    gt_chain = GECKOTERMINAL_CHAIN_MAP.get(chain, chain)
    url = (
        f"{GECKOTERMINAL_BASE}/networks/{gt_chain}"
        f"/pools/{pool_address.lower()}/ohlcv/{timeframe}"
    )
    params = {"aggregate": aggregate, "limit": min(limit, 1000), "currency": "usd"}
    resp = requests.get(url, params=params, timeout=20)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    data = resp.json()

    ohlcv_list = data.get("data", {}).get("attributes", {}).get("ohlcv_list", [])
    if not ohlcv_list:
        return None

    rows = []
    for candle in ohlcv_list:
        # GeckoTerminal format: [timestamp_ms, open, high, low, close, volume]
        if len(candle) < 6:
            continue
        rows.append({
            "timestamp": pd.Timestamp(candle[0], unit="ms", tz="UTC"),
            "open": float(candle[1] or 0),
            "high": float(candle[2] or 0),
            "low": float(candle[3] or 0),
            "close": float(candle[4] or 0),
            "volume": float(candle[5] or 0),
        })

    if not rows:
        return None

    df = pd.DataFrame(rows)
    df.set_index("timestamp", inplace=True)
    df.sort_index(inplace=True)

    # Filter out zero-price candles
    df = df[df["close"] > 0]
    return df if len(df) >= 5 else None


def _fetch_geckoterminal_for_token(
    token_address: str,
    chain: str,
    pair_address: Optional[str] = None,
    limit: int = 200,
) -> Optional[pd.DataFrame]:
    """
    Fetch GeckoTerminal OHLCV for a token.
    Uses pair_address directly if provided (faster), otherwise discovers pools.
    """
    # Try the known pair address first (fastest path)
    if pair_address:
        try:
            df = _fetch_geckoterminal_ohlcv(chain, pair_address, timeframe="hour", limit=limit)
            if df is not None and len(df) >= 14:  # Need at least 14 candles for RSI
                logger.info(
                    f"GeckoTerminal OHLCV (pair): {len(df)} candles for "
                    f"{token_address[:10]}... on {chain}"
                )
                return df
        except Exception as e:
            logger.debug(f"GeckoTerminal pair fetch failed: {e}")

    # Discover pools for this token
    try:
        pools = _fetch_geckoterminal_pools(token_address, chain)
        if not pools:
            return None

        # Sort by liquidity (highest first)
        pools_sorted = sorted(
            pools,
            key=lambda p: float(
                p.get("attributes", {}).get("reserve_in_usd", 0) or 0
            ),
            reverse=True,
        )

        # Try top 3 pools
        for pool in pools_sorted[:3]:
            pool_addr = pool.get("attributes", {}).get("address", "")
            if not pool_addr:
                continue
            try:
                df = _fetch_geckoterminal_ohlcv(chain, pool_addr, timeframe="hour", limit=limit)
                if df is not None and len(df) >= 14:
                    logger.info(
                        f"GeckoTerminal OHLCV (pool discovery): {len(df)} candles for "
                        f"{token_address[:10]}... on {chain}"
                    )
                    return df
            except Exception as e:
                logger.debug(f"GeckoTerminal pool {pool_addr[:10]}... failed: {e}")
                continue

    except Exception as e:
        logger.debug(f"GeckoTerminal pool discovery failed for {token_address}: {e}")

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Source 2: CoinGecko (secondary — hourly market data)
# ─────────────────────────────────────────────────────────────────────────────

COINGECKO_BASE = "https://api.coingecko.com/api/v3"
_last_cg_request = 0.0
_CG_MIN_INTERVAL = 2.1

COINGECKO_PLATFORM_MAP = {
    "ethereum": "ethereum",
    "base": "base",
    "arbitrum": "arbitrum-one",
    "polygon": "polygon-pos",
    "bsc": "binance-smart-chain",
}


def _cg_rate_limit():
    global _last_cg_request
    elapsed = time.time() - _last_cg_request
    if elapsed < _CG_MIN_INTERVAL:
        time.sleep(_CG_MIN_INTERVAL - elapsed)
    _last_cg_request = time.time()


@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=3, max=20))
def _fetch_coingecko_ohlc(
    token_address: str,
    chain: str,
    days: int = 7,
) -> Optional[pd.DataFrame]:
    """Fetch OHLCV from CoinGecko's contract market_chart endpoint."""
    platform = COINGECKO_PLATFORM_MAP.get(chain)
    if not platform:
        return None

    _cg_rate_limit()
    url = f"{COINGECKO_BASE}/coins/{platform}/contract/{token_address.lower()}/market_chart"
    params = {"vs_currency": "usd", "days": days}

    try:
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.debug(f"CoinGecko OHLCV fetch error: {e}")
        return None

    prices = data.get("prices", [])
    volumes = data.get("total_volumes", [])

    if len(prices) < 14:
        return None

    price_df = pd.DataFrame(prices, columns=["ts", "price"])
    price_df["timestamp"] = pd.to_datetime(price_df["ts"], unit="ms", utc=True)
    price_df.set_index("timestamp", inplace=True)

    vol_df = pd.DataFrame(volumes, columns=["ts", "volume"])
    vol_df["timestamp"] = pd.to_datetime(vol_df["ts"], unit="ms", utc=True)
    vol_df.set_index("timestamp", inplace=True)

    ohlc = price_df["price"].resample("1h").ohlc()
    ohlc.columns = ["open", "high", "low", "close"]
    ohlc["volume"] = vol_df["volume"].resample("1h").sum()
    ohlc.dropna(subset=["open", "close"], inplace=True)

    return ohlc if len(ohlc) >= 14 else None


# ─────────────────────────────────────────────────────────────────────────────
# Source 3: DexScreener snapshot reconstruction (last resort)
# ─────────────────────────────────────────────────────────────────────────────

DEXSCREENER_BASE = "https://api.dexscreener.com"
_last_dex_request = 0.0
_DEX_MIN_INTERVAL = 1.0


def _dex_rate_limit():
    global _last_dex_request
    elapsed = time.time() - _last_dex_request
    if elapsed < _DEX_MIN_INTERVAL:
        time.sleep(_DEX_MIN_INTERVAL - elapsed)
    _last_dex_request = time.time()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=15))
def _fetch_dexscreener_pairs(token_address: str) -> list[dict]:
    """Fetch all pairs for a token from DexScreener."""
    _dex_rate_limit()
    url = f"{DEXSCREENER_BASE}/dex/tokens/{token_address}"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    return resp.json().get("pairs", [])


def _build_ohlcv_from_pair_snapshots(pairs: list[dict], chain: str) -> Optional[pd.DataFrame]:
    """
    Build OHLCV-like data from DexScreener pair snapshots.
    NOTE: This only produces 5 data points — insufficient for RSI(14).
    Only used as a last resort when GeckoTerminal and CoinGecko both fail.
    """
    if not pairs:
        return None

    dex_chain = DEXSCREENER_CHAIN_MAP.get(chain)
    chain_pairs = [p for p in pairs if p.get("chainId") == dex_chain] if dex_chain else pairs
    if not chain_pairs:
        chain_pairs = pairs

    pair = max(chain_pairs, key=lambda p: float(p.get("liquidity", {}).get("usd", 0) or 0))
    price_usd = float(pair.get("priceUsd", 0) or 0)
    if price_usd <= 0:
        return None

    price_change = pair.get("priceChange", {})
    volume = pair.get("volume", {})
    now = time.time()

    intervals = [
        {"seconds": 300,   "pct": float(price_change.get("m5", 0) or 0),  "vol": float(volume.get("m5", 0) or 0)},
        {"seconds": 3600,  "pct": float(price_change.get("h1", 0) or 0),  "vol": float(volume.get("h1", 0) or 0)},
        {"seconds": 21600, "pct": float(price_change.get("h6", 0) or 0),  "vol": float(volume.get("h6", 0) or 0)},
        {"seconds": 86400, "pct": float(price_change.get("h24", 0) or 0), "vol": float(volume.get("h24", 0) or 0)},
    ]

    rows = []
    for iv in intervals:
        pct = iv["pct"]
        historical_price = price_usd / (1 + pct / 100) if (1 + pct / 100) != 0 else price_usd
        ts = now - iv["seconds"]
        spread = abs(price_usd - historical_price)
        high = max(price_usd, historical_price) + spread * 0.1
        low = max(min(price_usd, historical_price) - spread * 0.1, 0)
        rows.append({
            "timestamp": pd.Timestamp(ts, unit="s", tz="UTC"),
            "open": historical_price,
            "high": high,
            "low": low,
            "close": price_usd,
            "volume": iv["vol"],
        })

    rows.append({
        "timestamp": pd.Timestamp(now, unit="s", tz="UTC"),
        "open": price_usd,
        "high": price_usd * 1.001,
        "low": price_usd * 0.999,
        "close": price_usd,
        "volume": float(volume.get("m5", 0) or 0),
    })

    rows.sort(key=lambda r: r["timestamp"])
    df = pd.DataFrame(rows)
    df.set_index("timestamp", inplace=True)
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def fetch_ohlcv(
    token_address: str,
    chain: str,
    days: int = 7,
    min_candles: int = 14,
    pair_address: Optional[str] = None,
) -> Optional[pd.DataFrame]:
    """
    Fetch OHLCV data for a token. Tries multiple sources in priority order:
      1. GeckoTerminal (real pool candles — best for new tokens and Solana)
      2. CoinGecko (hourly market data — best for established tokens)
      3. DexScreener snapshot (last resort — only 5 data points, RSI will be None)

    The min_candles default is 14 because RSI(14) needs at least 14 candles.
    GeckoTerminal typically returns 100-1000 hourly candles for active pools.

    Args:
        token_address: Token contract address
        chain: Chain name (e.g., 'ethereum', 'base', 'solana')
        days: Number of days of history to fetch (for CoinGecko)
        min_candles: Minimum candles required for valid TA analysis
        pair_address: Known pair/pool address (speeds up GeckoTerminal lookup)

    Returns:
        DataFrame with DatetimeIndex and columns: open, high, low, close, volume
        Returns None if insufficient data available.
    """
    # Check cache first
    cached = _get_cached_ohlcv(token_address, chain, days)
    if cached is not None:
        logger.debug(f"OHLCV cache HIT: {token_address[:10]}... ({chain})")
        return cached

    logger.debug(f"Fetching OHLCV for {token_address[:10]}... on {chain} ({days}d)")

    # Source 1: GeckoTerminal (primary — real candles, works for new tokens)
    try:
        df = _fetch_geckoterminal_for_token(
            token_address, chain,
            pair_address=pair_address,
            limit=max(200, days * 24),
        )
        if df is not None and len(df) >= min_candles:
            _set_cached_ohlcv(token_address, chain, days, df)
            return df
    except Exception as e:
        logger.debug(f"GeckoTerminal OHLCV failed: {e}")

    # Source 2: CoinGecko (secondary — established tokens)
    if chain != "solana":  # CoinGecko doesn't support Solana contract lookups
        try:
            df = _fetch_coingecko_ohlc(token_address, chain, days=days)
            if df is not None and len(df) >= min_candles:
                logger.info(f"OHLCV from CoinGecko: {len(df)} candles for {token_address[:10]}...")
                _set_cached_ohlcv(token_address, chain, days, df)
                return df
        except Exception as e:
            logger.debug(f"CoinGecko OHLCV failed: {e}")

    # Source 3: DexScreener snapshot (last resort — insufficient for RSI)
    try:
        pairs = _fetch_dexscreener_pairs(token_address)
        df = _build_ohlcv_from_pair_snapshots(pairs, chain)
        if df is not None and len(df) >= 3:
            logger.warning(
                f"OHLCV from DexScreener snapshots only ({len(df)} points) for "
                f"{token_address[:10]}... — TA indicators will be limited"
            )
            _set_cached_ohlcv(token_address, chain, days, df)
            return df
    except Exception as e:
        logger.debug(f"DexScreener OHLCV failed: {e}")

    logger.warning(f"No OHLCV data available for {token_address[:10]}... on {chain}")
    _set_cached_ohlcv(token_address, chain, days, None)
    return None


def get_current_price(token_address: str, chain: str) -> Optional[float]:
    """Quick price lookup from DexScreener (single API call)."""
    try:
        pairs = _fetch_dexscreener_pairs(token_address)
        if not pairs:
            return None
        dex_chain = DEXSCREENER_CHAIN_MAP.get(chain)
        chain_pairs = [p for p in pairs if p.get("chainId") == dex_chain] if dex_chain else pairs
        if not chain_pairs:
            chain_pairs = pairs
        best = max(chain_pairs, key=lambda p: float(p.get("liquidity", {}).get("usd", 0) or 0))
        return float(best.get("priceUsd", 0) or 0)
    except Exception as e:
        logger.error(f"Price lookup error: {e}")
        return None


def get_current_price_geckoterminal(chain: str, pool_address: str) -> Optional[float]:
    """Quick price lookup from GeckoTerminal pool (more accurate for new tokens)."""
    try:
        gt_chain = GECKOTERMINAL_CHAIN_MAP.get(chain, chain)
        _gt_rate_limit()
        url = f"{GECKOTERMINAL_BASE}/networks/{gt_chain}/pools/{pool_address.lower()}"
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            return None
        data = resp.json()
        attrs = data.get("data", {}).get("attributes", {})
        price = float(attrs.get("base_token_price_usd", 0) or 0)
        return price if price > 0 else None
    except Exception as e:
        logger.debug(f"GeckoTerminal price lookup error: {e}")
        return None
