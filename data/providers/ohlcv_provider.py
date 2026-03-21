"""
data/providers/ohlcv_provider.py — OHLCV candle data provider.

Fetches historical Open/High/Low/Close/Volume data from multiple sources:
  1. DexScreener (primary — free, no key required)
  2. CoinGecko (fallback — OHLC endpoint)

Returns pandas DataFrames in the standard format that pandas-ta expects:
  columns: ['timestamp', 'open', 'high', 'low', 'close', 'volume']
  index:   DatetimeIndex

Used by:
  - strategies/fibonacci.py (swing detection)
  - strategies/indicators.py (all TA calculations)
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
# DexScreener OHLCV
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
    data = resp.json()
    return data.get("pairs", [])


def _build_ohlcv_from_pair_snapshots(pairs: list[dict], chain: str) -> Optional[pd.DataFrame]:
    """
    Build OHLCV-like data from DexScreener pair data.

    DexScreener doesn't expose raw candles on the free API, but provides
    price change percentages at multiple intervals (5m, 1h, 6h, 24h).
    We reconstruct approximate candles from these data points.
    """
    if not pairs:
        return None

    # Filter to pairs on the correct chain
    dex_chain = DEXSCREENER_CHAIN_MAP.get(chain)
    chain_pairs = [p for p in pairs if p.get("chainId") == dex_chain] if dex_chain else pairs

    if not chain_pairs:
        chain_pairs = pairs  # fallback to all pairs

    # Use the most liquid pair
    pair = max(chain_pairs, key=lambda p: float(p.get("liquidity", {}).get("usd", 0) or 0))

    price_usd = float(pair.get("priceUsd", 0) or 0)
    if price_usd <= 0:
        return None

    price_change = pair.get("priceChange", {})
    volume = pair.get("volume", {})
    now = time.time()

    # Reconstruct price history from percentage changes
    # Working backwards: current price → derive historical prices
    intervals = [
        {"label": "5m",  "seconds": 300,    "pct": float(price_change.get("m5", 0) or 0),  "vol": float(volume.get("m5", 0) or 0)},
        {"label": "1h",  "seconds": 3600,   "pct": float(price_change.get("h1", 0) or 0),  "vol": float(volume.get("h1", 0) or 0)},
        {"label": "6h",  "seconds": 21600,  "pct": float(price_change.get("h6", 0) or 0),  "vol": float(volume.get("h6", 0) or 0)},
        {"label": "24h", "seconds": 86400,  "pct": float(price_change.get("h24", 0) or 0), "vol": float(volume.get("h24", 0) or 0)},
    ]

    rows = []
    for iv in intervals:
        pct = iv["pct"]
        if pct == 0:
            historical_price = price_usd
        else:
            # Current = Historical × (1 + pct/100)
            # Historical = Current / (1 + pct/100)
            historical_price = price_usd / (1 + pct / 100) if (1 + pct / 100) != 0 else price_usd

        ts = now - iv["seconds"]

        # Estimate OHLC — with limited data, open = historical, close = current-ish
        # We use the price change to estimate the high/low spread
        spread = abs(price_usd - historical_price)
        high = max(price_usd, historical_price) + spread * 0.1
        low = min(price_usd, historical_price) - spread * 0.1
        low = max(low, 0)  # price can't be negative

        rows.append({
            "timestamp": pd.Timestamp(ts, unit="s", tz="UTC"),
            "open": historical_price,
            "high": high,
            "low": low,
            "close": price_usd if iv == intervals[0] else historical_price * (1 + pct / 200) if pct else price_usd,
            "volume": iv["vol"],
        })

    # Add current candle
    rows.append({
        "timestamp": pd.Timestamp(now, unit="s", tz="UTC"),
        "open": price_usd,
        "high": price_usd * 1.001,
        "low": price_usd * 0.999,
        "close": price_usd,
        "volume": float(volume.get("m5", 0) or 0),
    })

    # Sort chronologically
    rows.sort(key=lambda r: r["timestamp"])

    df = pd.DataFrame(rows)
    df.set_index("timestamp", inplace=True)
    return df


# ─────────────────────────────────────────────────────────────────────────────
# CoinGecko OHLCV (fallback)
# ─────────────────────────────────────────────────────────────────────────────

COINGECKO_BASE = "https://api.coingecko.com/api/v3"
_last_cg_request = 0.0
_CG_MIN_INTERVAL = 2.1


def _cg_rate_limit():
    global _last_cg_request
    elapsed = time.time() - _last_cg_request
    if elapsed < _CG_MIN_INTERVAL:
        time.sleep(_CG_MIN_INTERVAL - elapsed)
    _last_cg_request = time.time()


# Map our chain names to CoinGecko platform IDs
COINGECKO_PLATFORM_MAP = {
    "ethereum": "ethereum",
    "base": "base",
    "arbitrum": "arbitrum-one",
    "polygon": "polygon-pos",
    "bsc": "binance-smart-chain",
}


@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=3, max=20))
def _fetch_coingecko_ohlc(
    token_address: str,
    chain: str,
    days: int = 7,
) -> Optional[pd.DataFrame]:
    """
    Fetch OHLCV from CoinGecko's contract OHLC endpoint.
    Returns DataFrame or None if not found.
    """
    platform = COINGECKO_PLATFORM_MAP.get(chain)
    if not platform:
        return None

    _cg_rate_limit()
    url = f"{COINGECKO_BASE}/coins/{platform}/contract/{token_address.lower()}/market_chart"
    params = {"vs_currency": "usd", "days": days}

    try:
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code == 404:
            logger.debug(f"CoinGecko: token not found on {platform}: {token_address}")
            return None
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.warning(f"CoinGecko OHLCV fetch error: {e}")
        return None

    prices = data.get("prices", [])
    volumes = data.get("total_volumes", [])

    if len(prices) < 5:
        return None

    # Build OHLCV from market_chart (which gives price points, not candles)
    # Group into 1-hour candles
    price_df = pd.DataFrame(prices, columns=["ts", "price"])
    price_df["timestamp"] = pd.to_datetime(price_df["ts"], unit="ms", utc=True)
    price_df.set_index("timestamp", inplace=True)

    vol_df = pd.DataFrame(volumes, columns=["ts", "volume"])
    vol_df["timestamp"] = pd.to_datetime(vol_df["ts"], unit="ms", utc=True)
    vol_df.set_index("timestamp", inplace=True)

    # Resample to 1-hour candles
    ohlc = price_df["price"].resample("1h").ohlc()
    ohlc.columns = ["open", "high", "low", "close"]
    vol_resampled = vol_df["volume"].resample("1h").sum()
    ohlc["volume"] = vol_resampled

    # Drop NaN rows
    ohlc.dropna(subset=["open", "close"], inplace=True)
    return ohlc


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def fetch_ohlcv(
    token_address: str,
    chain: str,
    days: int = 7,
    min_candles: int = 5,
) -> Optional[pd.DataFrame]:
    """
    Fetch OHLCV data for a token. Tries multiple sources in order:
      1. CoinGecko (best data quality for established tokens)
      2. DexScreener (works for newer/micro-cap tokens)

    Args:
        token_address: Token contract address
        chain: Chain name (e.g., 'ethereum', 'base')
        days: Number of days of history to fetch
        min_candles: Minimum candles required for valid analysis

    Returns:
        DataFrame with DatetimeIndex and columns: open, high, low, close, volume
        Returns None if insufficient data available.
    """
    logger.debug(f"Fetching OHLCV for {token_address[:10]}... on {chain} ({days}d)")

    # Source 1: CoinGecko (best for established tokens)
    try:
        df = _fetch_coingecko_ohlc(token_address, chain, days=days)
        if df is not None and len(df) >= min_candles:
            logger.info(f"OHLCV from CoinGecko: {len(df)} candles for {token_address[:10]}...")
            return df
    except Exception as e:
        logger.debug(f"CoinGecko OHLCV failed: {e}")

    # Source 2: DexScreener (works for everything on DEXes)
    try:
        pairs = _fetch_dexscreener_pairs(token_address)
        df = _build_ohlcv_from_pair_snapshots(pairs, chain)
        if df is not None and len(df) >= min_candles:
            logger.info(f"OHLCV from DexScreener: {len(df)} candles for {token_address[:10]}...")
            return df
    except Exception as e:
        logger.debug(f"DexScreener OHLCV failed: {e}")

    logger.warning(f"No OHLCV data available for {token_address[:10]}... on {chain}")
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
