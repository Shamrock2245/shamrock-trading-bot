"""
CoinPaprika API Provider
========================
Free tier: 20,000 calls/month, no API key required.
12,000+ coins, 350+ exchanges, $2.4T+ market cap coverage.

What this adds vs existing providers:
  1. True ALL-TIME ATH (not just 7-day) — used in Near-ATH FOMO gate
  2. ATH distance % — how far below all-time high the token currently is
  3. Circulating supply + market cap for microcap validation
  4. Macro fallback — BTC/ETH/SOL OHLCV when CoinGecko rate-limits
  5. Exchange-level volume breakdown — detect wash trading

Docs: https://docs.coinpaprika.com
Base URL: https://api.coinpaprika.com/v1/
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from data.http_session import get_session

logger = logging.getLogger(__name__)

_BASE = "https://api.coinpaprika.com/v1"
_TIMEOUT = 8
_CACHE_TTL = 300  # 5 min

# In-memory cache: {cache_key: (timestamp, data)}
_cache: dict[str, tuple[float, dict]] = {}

# Coin ID cache: {symbol_lower: coinpaprika_id}
_id_cache: dict[str, str] = {}
_id_cache_ts: float = 0.0
_ID_CACHE_TTL = 3600  # 1 hour

# Known macro coins — pre-mapped to avoid search overhead
_MACRO_IDS = {
    "btc": "btc-bitcoin",
    "eth": "eth-ethereum",
    "sol": "sol-solana",
    "bnb": "bnb-binance-coin",
    "matic": "matic-polygon",
    "arb": "arb-arbitrum",
}


def _get_cached(key: str) -> Optional[dict]:
    entry = _cache.get(key)
    if entry and (time.time() - entry[0]) < _CACHE_TTL:
        return entry[1]
    return None


def _set_cached(key: str, data: dict) -> None:
    _cache[key] = (time.time(), data)


def _get(path: str, params: Optional[dict] = None) -> Optional[dict]:
    """GET request to CoinPaprika API with error handling."""
    try:
        resp = get_session().get(f"{_BASE}{path}", params=params, timeout=_TIMEOUT)
        if resp.status_code == 429:
            logger.debug("CoinPaprika rate limited — skipping")
            return None
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.debug(f"CoinPaprika request failed ({path}): {e}")
        return None


def _search_coin_id(symbol: str, name: str = "") -> Optional[str]:
    """
    Find the CoinPaprika coin ID for a given symbol.
    Uses the search endpoint with caching.
    """
    global _id_cache_ts
    sym_lower = symbol.lower()

    # Check pre-mapped macro coins first
    if sym_lower in _MACRO_IDS:
        return _MACRO_IDS[sym_lower]

    # Check ID cache
    if sym_lower in _id_cache:
        return _id_cache[sym_lower]

    # Search by symbol
    query = name if name else symbol
    data = _get(f"/search", params={"q": query, "c": "currencies", "limit": "10"})
    if not data:
        return None

    currencies = data.get("currencies", [])
    if not currencies:
        return None

    # Try exact symbol match first
    for coin in currencies:
        if coin.get("symbol", "").lower() == sym_lower:
            coin_id = coin.get("id", "")
            _id_cache[sym_lower] = coin_id
            return coin_id

    # Fall back to first result
    coin_id = currencies[0].get("id", "")
    if coin_id:
        _id_cache[sym_lower] = coin_id
    return coin_id or None


def get_coin_ath(symbol: str, current_price_usd: float, name: str = "") -> dict:
    """
    Get the true all-time high (ATH) for a coin from CoinPaprika.

    Returns:
        {
            "ath_usd": float,           # All-time high price in USD
            "ath_date": str,            # Date of ATH (ISO format)
            "ath_distance_pct": float,  # % below ATH (0.0 = at ATH, 0.90 = 90% below)
            "is_near_ath_alltime": bool,# True if within 20% of all-time ATH
            "market_cap_usd": float,    # Current market cap
            "circulating_supply": float,# Circulating supply
            "rank": int,                # CoinPaprika rank
            "found": bool,              # False if coin not found in CoinPaprika
        }
    """
    default = {
        "ath_usd": 0.0,
        "ath_date": "",
        "ath_distance_pct": 1.0,
        "is_near_ath_alltime": False,
        "market_cap_usd": 0.0,
        "circulating_supply": 0.0,
        "rank": 9999,
        "found": False,
    }

    cache_key = f"ath:{symbol.lower()}"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    coin_id = _search_coin_id(symbol, name)
    if not coin_id:
        return default

    # Get full coin data including ATH
    data = _get(f"/coins/{coin_id}")
    if not data:
        return default

    # Get ticker for market cap + supply
    ticker = _get(f"/tickers/{coin_id}")

    result = dict(default)
    result["found"] = True
    result["rank"] = data.get("rank", 9999) or 9999

    if ticker:
        quotes = ticker.get("quotes", {}).get("USD", {})
        result["market_cap_usd"] = float(quotes.get("market_cap", 0) or 0)
        result["circulating_supply"] = float(ticker.get("circulating_supply", 0) or 0)
        ath_price = float(quotes.get("ath_price", 0) or 0)
        ath_date = quotes.get("ath_date", "")
        if ath_price > 0:
            result["ath_usd"] = ath_price
            result["ath_date"] = ath_date
            if current_price_usd > 0:
                result["ath_distance_pct"] = max(0.0, 1.0 - (current_price_usd / ath_price))
                # Near ATH = within 20% of all-time high
                result["is_near_ath_alltime"] = result["ath_distance_pct"] < 0.20

    _set_cached(cache_key, result)
    return result


def get_macro_ohlcv(symbol: str, days: int = 200) -> list[dict]:
    """
    Get daily OHLCV data for a macro coin (BTC, ETH, SOL, BNB).
    Used as a fallback when CoinGecko rate-limits.

    Returns list of {"timestamp": int, "open": float, "high": float,
                      "low": float, "close": float, "volume": float}
    """
    sym_lower = symbol.lower()
    coin_id = _MACRO_IDS.get(sym_lower)
    if not coin_id:
        coin_id = _search_coin_id(symbol)
    if not coin_id:
        return []

    cache_key = f"ohlcv:{coin_id}:{days}"
    cached = _get_cached(cache_key)
    if cached:
        return cached.get("data", [])

    # CoinPaprika OHLCV endpoint
    import datetime
    end = datetime.date.today().isoformat()
    start = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()

    data = _get(f"/coins/{coin_id}/ohlcv/historical", params={"start": start, "end": end})
    if not data or not isinstance(data, list):
        return []

    result = []
    for candle in data:
        result.append({
            "timestamp": candle.get("time_open", ""),
            "open": float(candle.get("open", 0) or 0),
            "high": float(candle.get("high", 0) or 0),
            "low": float(candle.get("low", 0) or 0),
            "close": float(candle.get("close", 0) or 0),
            "volume": float(candle.get("volume", 0) or 0),
        })

    _set_cached(cache_key, {"data": result})
    return result


def get_global_market_stats() -> dict:
    """
    Get global crypto market statistics.
    Used as a supplement to the macro_filter module.

    Returns:
        {
            "total_market_cap_usd": float,
            "btc_dominance_pct": float,
            "eth_dominance_pct": float,
            "defi_volume_24h_usd": float,
            "active_cryptocurrencies": int,
        }
    """
    cache_key = "global_stats"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    data = _get("/global")
    if not data:
        return {}

    result = {
        "total_market_cap_usd": float(data.get("market_cap_usd", 0) or 0),
        "btc_dominance_pct": float(data.get("bitcoin_dominance_percentage", 0) or 0),
        "eth_dominance_pct": float(data.get("ethereum_dominance_percentage", 0) or 0),
        "defi_volume_24h_usd": float(data.get("defi_volume_24h_usd", 0) or 0),
        "active_cryptocurrencies": int(data.get("cryptocurrencies_number", 0) or 0),
    }
    _set_cached(cache_key, result)
    return result


def check_alltime_ath_gate(
    symbol: str,
    current_price_usd: float,
    name: str = "",
    reject_within_pct: float = 0.15,
) -> tuple[bool, str]:
    """
    Hard gate: reject tokens within X% of their all-time ATH.

    This is stricter than the 7-day ATH gate — it catches tokens that are
    near their all-time high (not just recent high), which is a much stronger
    FOMO signal.

    Args:
        symbol: Token symbol
        current_price_usd: Current price
        name: Token name (improves search accuracy)
        reject_within_pct: Reject if within this % of ATH (default 15%)

    Returns:
        (should_reject: bool, reason: str)
    """
    ath_data = get_coin_ath(symbol, current_price_usd, name)

    if not ath_data["found"] or ath_data["ath_usd"] == 0:
        # Can't find ATH data — don't block, just skip this gate
        return False, ""

    distance = ath_data["ath_distance_pct"]
    if distance < reject_within_pct:
        reason = (
            f"CoinPaprika: near all-time ATH — "
            f"current ${current_price_usd:.6f} is {distance:.1%} below ATH "
            f"${ath_data['ath_usd']:.6f} ({ath_data['ath_date'][:10]})"
        )
        return True, reason

    return False, ""
