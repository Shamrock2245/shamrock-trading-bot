"""
data/providers/moralis_money.py — Moralis Money: PRIMARY data source for the Shamrock Trading Bot.

Moralis Money is one of the most powerful on-chain intelligence platforms available.
This module wires in EVERY relevant Moralis endpoint as a first-class data source:

  Discovery (Pro):
    POST /discovery/tokens              → Filtered Tokens (custom filters: buyers, volume, liquidity)
    GET  /discovery/tokens/trending     → Trending tokens by chain
    GET  /discovery/tokens/top-gainers  → Top price gainers with on-chain strength
    GET  /discovery/tokens/top-losers   → Oversold tokens (mean-reversion candidates)
    GET  /discovery/tokens/buying-pressure → Rising buy:sell ratio (momentum signal)

  Intelligence (Pro):
    GET  /tokens/{address}/score        → Moralis token score (0–100) with volume/tx/supply metrics
    GET  /tokens/{address}/analytics    → Buy/sell volume, buyers, sellers, net buyers (5m–30d)
    POST /tokens/analytics              → Batch analytics for up to 30 tokens at once

  Enrichment (Free):
    GET  /erc20/{address}/stats         → Transfer count (activity proxy)
    GET  /erc20/{address}/owners        → Holder count

All discovery results feed directly into the gem scanner as high-priority candidates.
Token Score and Analytics results enrich the gem scoring pipeline.

Chain support: ethereum, base, arbitrum, polygon, bsc, avalanche (+ solana for score/analytics)

Rate limiting: 25 req/min enforced via token bucket. 10-minute cache per chain/token.
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
MORALIS_API_KEY: str = getattr(settings, "MORALIS_API_KEY", "")
BASE_URL = "https://deep-index.moralis.io/api/v2.2"

# Internal chain name → Moralis chain slug
CHAIN_MAP: dict[str, str] = {
    "ethereum": "eth",
    "base":     "base",
    "arbitrum": "arbitrum",
    "polygon":  "polygon",
    "bsc":      "bsc",
    "avalanche":"avalanche",
    "solana":   "solana",
}

# Moralis chain slug → hex chain ID (for filtered-tokens endpoint)
CHAIN_HEX: dict[str, str] = {
    "eth":       "0x1",
    "base":      "0x2105",
    "arbitrum":  "0xa4b1",
    "polygon":   "0x89",
    "bsc":       "0x38",
    "avalanche": "0xa86a",
}

CACHE_TTL = 600  # 10 minutes
_cache: dict[str, dict] = {}

# Simple rate limiter — 25 calls/min
_rate_window_start: float = time.time()
_rate_calls_in_window: int = 0
RATE_LIMIT_PER_MIN = 25


def _headers() -> dict:
    return {
        "accept": "application/json",
        "X-API-Key": MORALIS_API_KEY,
    }


def _json_headers() -> dict:
    return {
        "accept": "application/json",
        "Content-Type": "application/json",
        "X-API-Key": MORALIS_API_KEY,
    }


def _rate_check() -> None:
    """Block briefly if we're approaching the rate limit."""
    global _rate_window_start, _rate_calls_in_window
    now = time.time()
    if now - _rate_window_start >= 60:
        _rate_window_start = now
        _rate_calls_in_window = 0
    _rate_calls_in_window += 1
    if _rate_calls_in_window >= RATE_LIMIT_PER_MIN:
        sleep_for = 60 - (now - _rate_window_start) + 1
        if sleep_for > 0:
            logger.debug(f"Moralis rate limit: sleeping {sleep_for:.1f}s")
            time.sleep(sleep_for)
        _rate_window_start = time.time()
        _rate_calls_in_window = 1


def _is_cached(key: str) -> bool:
    entry = _cache.get(key)
    if not entry:
        return False
    return (time.time() - entry.get("ts", 0)) < CACHE_TTL


def _set_cache(key: str, data) -> None:
    _cache[key] = {"data": data, "ts": time.time()}


def _get_cache(key: str):
    return _cache.get(key, {}).get("data")


def _safe_float(val) -> float:
    try:
        return float(val) if val is not None else 0.0
    except (ValueError, TypeError):
        return 0.0


def _safe_int(val) -> int:
    try:
        return int(val) if val is not None else 0
    except (ValueError, TypeError):
        return 0


def _available(chain: str) -> bool:
    """Return True if we have an API key and the chain is supported."""
    return bool(MORALIS_API_KEY) and chain in CHAIN_MAP


# ─────────────────────────────────────────────────────────────────────────────
# 1. Filtered Tokens  (POST /discovery/tokens)
#    PRIMARY discovery — custom filter by experienced buyers, volume, liquidity
# ─────────────────────────────────────────────────────────────────────────────
def get_filtered_tokens(
    chain: str,
    min_experienced_buyers_1h: int = 5,
    min_liquidity_usd: float = 50_000,
    min_security_score: int = 60,
    limit: int = 50,
) -> list[dict]:
    """
    Filtered token discovery — the most powerful Moralis Money endpoint.
    Finds tokens with rising experienced buyer counts, minimum liquidity,
    and acceptable security scores. This is the core gem discovery signal.
    """
    if not _available(chain):
        return []
    moralis_chain = CHAIN_MAP[chain]
    chain_hex = CHAIN_HEX.get(moralis_chain, "0x1")
    cache_key = f"filtered_{chain}_{min_experienced_buyers_1h}"
    if _is_cached(cache_key):
        return _get_cache(cache_key)

    _rate_check()
    try:
        payload = {
            "chain": chain_hex,
            "filters": [
                {
                    "metric": "experiencedBuyers",
                    "timeFrame": "oneHour",
                    "gt": min_experienced_buyers_1h,
                },
                {
                    "metric": "totalLiquidityUsd",
                    "timeFrame": "oneDay",  # Point-in-time metric — must use oneDay
                    "gt": min_liquidity_usd,
                },
                {
                    "metric": "securityScore",
                    "timeFrame": "oneDay",  # Point-in-time metric — must use oneDay
                    "gt": min_security_score,
                },
            ],
            "sortBy": {
                "metric": "experiencedBuyers",
                "timeFrame": "oneHour",
                "type": "DESC",
            },
            "limit": limit,
            "metricsToReturn": [
                "experiencedBuyers",
                "netBuyers",
                "volumeUsd",
                "buyVolumeUsd",
                "sellVolumeUsd",
                "netVolumeUsd",
                "usdPrice",
                "usdPricePercentChange",
                "liquidityChangeUSD",
                "totalLiquidityUsd",
                "totalHolders",
                "securityScore",
            ],
            "timeFramesToReturn": ["oneHour", "fourHours", "oneDay"],
            "excludeMetadata": False,
        }
        resp = requests.post(
            f"{BASE_URL}/discovery/tokens",
            json=payload,
            headers=_json_headers(),
            timeout=20,
        )
        if resp.status_code in (402, 403):
            logger.debug(f"Moralis filtered tokens: plan limitation for {chain}")
            return []
        resp.raise_for_status()
        raw = resp.json()
        items = raw if isinstance(raw, list) else raw.get("result", [])
        result = []
        for item in items:
            meta = item.get("metadata", item)
            metrics = item.get("metrics", {})
            result.append({
                "token_address": meta.get("tokenAddress", meta.get("token_address", "")),
                "token_symbol":  meta.get("symbol", meta.get("token_symbol", "")),
                "token_name":    meta.get("name", meta.get("token_name", "")),
                "chain":         chain,
                "price_usd":     _safe_float(meta.get("usdPrice", 0)),
                "market_cap":    _safe_float(meta.get("marketCap", 0)),
                "liquidity_usd": _safe_float(meta.get("totalLiquidityUsd", 0)),
                "total_holders": _safe_int(meta.get("totalHolders", 0)),
                "security_score": _safe_int(meta.get("security", {}).get("securityScore", meta.get("securityScore", 0))),
                "is_honeypot":   meta.get("security", {}).get("isHoneyPot", False),
                "buy_tax":       _safe_float(meta.get("security", {}).get("buyTax", 0)),
                "sell_tax":      _safe_float(meta.get("security", {}).get("sellTax", 0)),
                "is_open_source": meta.get("security", {}).get("isOpenSource", True),
                # Metrics (1h timeframe)
                "experienced_buyers_1h": _safe_int(
                    (metrics.get("experiencedBuyers") or {}).get("oneHour", 0)
                ),
                "net_buyers_1h": _safe_float(
                    (metrics.get("netBuyers") or {}).get("oneHour", 0)
                ),
                "volume_usd_1h": _safe_float(
                    (metrics.get("volumeUsd") or {}).get("oneHour", 0)
                ),
                "net_volume_usd_1h": _safe_float(
                    (metrics.get("netVolumeUsd") or {}).get("oneHour", 0)
                ),
                "price_change_1h": _safe_float(
                    (metrics.get("usdPricePercentChange") or {}).get("oneHour", 0)
                ),
                "price_change_24h": _safe_float(
                    (metrics.get("usdPricePercentChange") or {}).get("oneDay", 0)
                ),
                "source": "moralis_filtered",
            })
        _set_cache(cache_key, result)
        logger.info(f"Moralis filtered tokens: {len(result)} gems on {chain}")
        return result
    except requests.exceptions.HTTPError as e:
        code = e.response.status_code if e.response is not None else 0
        if code in (402, 403):
            logger.debug(f"Moralis filtered tokens: plan limitation ({code}) for {chain}")
        else:
            logger.warning(f"Moralis filtered tokens error for {chain}: {e}")
        return []
    except Exception as e:
        logger.warning(f"Moralis filtered tokens error for {chain}: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# 1b. Whale Accumulation Discovery  (POST /discovery/tokens)
#     Uses netExperiencedBuyers — the most powerful smart-money signal.
#     Finds tokens where experienced wallets are net BUYING heavily.
# ─────────────────────────────────────────────────────────────────────────────
def get_whale_accumulation_tokens(
    chain: str,
    min_net_experienced_buyers_1w: int = 20,
    min_net_volume_usd_1d: float = 50_000,
    min_liquidity_usd: float = 100_000,
    limit: int = 15,
) -> list[dict]:
    """
    Whale accumulation detector — finds tokens where experienced wallets
    (500+ lifetime txns) are net accumulating over the past week.

    This is the single highest-signal discovery filter because it identifies
    tokens that smart money is buying BEFORE price moves.

    Filters:
      - netExperiencedBuyers > threshold over 1 week
      - netVolumeUsd > threshold over 1 day (positive buy pressure)
      - totalLiquidityUsd > threshold (not illiquid)
    """
    if not _available(chain) or chain == "solana":
        return []  # getFilteredTokens is EVM-only for now
    moralis_chain = CHAIN_MAP[chain]
    chain_hex = CHAIN_HEX.get(moralis_chain, "0x1")
    cache_key = f"whale_accum_{chain}"
    if _is_cached(cache_key):
        return _get_cache(cache_key)

    _rate_check()
    try:
        payload = {
            "chain": chain_hex,
            "filters": [
                {
                    "metric": "netExperiencedBuyers",
                    "timeFrame": "oneWeek",
                    "gt": min_net_experienced_buyers_1w,
                },
                {
                    "metric": "netVolumeUsd",
                    "timeFrame": "oneDay",
                    "gt": min_net_volume_usd_1d,
                },
                {
                    "metric": "totalLiquidityUsd",
                    "timeFrame": "oneDay",
                    "gt": min_liquidity_usd,
                },
            ],
            "sortBy": {
                "metric": "netExperiencedBuyers",
                "timeFrame": "oneWeek",
                "type": "DESC",
            },
            "limit": limit,
            "categories": {"exclude": ["stablecoin"]},
            "metricsToReturn": [
                "netExperiencedBuyers",
                "experiencedBuyers",
                "experiencedSellers",
                "netBuyers",
                "netVolumeUsd",
                "volumeUsd",
                "holders",
                "totalHolders",
                "usdPrice",
                "usdPricePercentChange",
                "totalLiquidityUsd",
                "securityScore",
                "fullyDilutedValuation",
            ],
            "timeFramesToReturn": ["oneDay", "oneWeek"],
            "excludeMetadata": False,
        }
        resp = requests.post(
            f"{BASE_URL}/discovery/tokens",
            json=payload,
            headers=_json_headers(),
            timeout=20,
        )
        if resp.status_code in (402, 403):
            logger.debug(f"Moralis whale accumulation: plan limitation for {chain}")
            return []
        resp.raise_for_status()
        raw = resp.json()
        items = raw if isinstance(raw, list) else raw.get("result", [])
        result = []
        for item in items:
            meta = item.get("metadata", item)
            metrics = item.get("metrics", {})
            net_exp_buyers_1w = _safe_int(
                (metrics.get("netExperiencedBuyers") or {}).get("oneWeek", 0)
            )
            result.append({
                "token_address": meta.get("tokenAddress", meta.get("token_address", "")),
                "token_symbol":  meta.get("symbol", meta.get("token_symbol", "")),
                "token_name":    meta.get("name", meta.get("token_name", "")),
                "chain":         chain,
                "price_usd":     _safe_float(meta.get("usdPrice", 0)),
                "market_cap":    _safe_float(meta.get("marketCap", 0)),
                "liquidity_usd": _safe_float(meta.get("totalLiquidityUsd", 0)),
                "security_score": _safe_int(meta.get("security", {}).get("securityScore", meta.get("securityScore", 0))),
                # Whale accumulation signals
                "net_experienced_buyers_1w": net_exp_buyers_1w,
                "experienced_buyers_1d": _safe_int(
                    (metrics.get("experiencedBuyers") or {}).get("oneDay", 0)
                ),
                "net_volume_usd_1d": _safe_float(
                    (metrics.get("netVolumeUsd") or {}).get("oneDay", 0)
                ),
                "holder_change_1d": _safe_int(
                    (metrics.get("holders") or {}).get("oneDay", 0)
                ),
                "holder_change_1w": _safe_int(
                    (metrics.get("holders") or {}).get("oneWeek", 0)
                ),
                "total_holders": _safe_int(
                    (metrics.get("totalHolders") or {}).get("oneDay", 0)
                ),
                "fdv": _safe_float(
                    (metrics.get("fullyDilutedValuation") or {}).get("oneDay", 0)
                ),
                "price_change_1d": _safe_float(
                    (metrics.get("usdPricePercentChange") or {}).get("oneDay", 0)
                ),
                "price_change_1w": _safe_float(
                    (metrics.get("usdPricePercentChange") or {}).get("oneWeek", 0)
                ),
                "source": "moralis_whale_accumulation",
                "whale_signal_strength": min(100, net_exp_buyers_1w * 2),  # 0–100 signal
            })
        _set_cache(cache_key, result)
        logger.info(
            f"🐋 Moralis whale accumulation: {len(result)} tokens on {chain}"
        )
        return result
    except requests.exceptions.HTTPError as e:
        code = e.response.status_code if e.response is not None else 0
        if code in (402, 403):
            logger.debug(f"Moralis whale accumulation: plan limitation ({code}) for {chain}")
        else:
            logger.warning(f"Moralis whale accumulation error for {chain}: {e}")
        return []
    except Exception as e:
        logger.warning(f"Moralis whale accumulation error for {chain}: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# 2. Trending Tokens  (GET /discovery/tokens/trending)
#    HIGH PRIORITY — tokens with the most momentum right now
# ─────────────────────────────────────────────────────────────────────────────
def get_trending_tokens(chain: str) -> list[dict]:
    """Fetch trending tokens by chain. High-momentum discovery signal."""
    if not _available(chain):
        return []
    moralis_chain = CHAIN_MAP[chain]
    cache_key = f"trending_{chain}"
    if _is_cached(cache_key):
        return _get_cache(cache_key)

    _rate_check()
    try:
        resp = requests.get(
            f"{BASE_URL}/discovery/tokens/trending",
            params={"chain": moralis_chain},
            headers=_headers(),
            timeout=15,
        )
        if resp.status_code in (402, 403):
            logger.debug(f"Moralis trending: plan limitation for {chain}")
            return []
        resp.raise_for_status()
        data = resp.json()
        tokens = data if isinstance(data, list) else data.get("result", [])
        result = [_normalize_discovery_token(t, chain, "moralis_trending") for t in tokens]
        result = [r for r in result if r]
        _set_cache(cache_key, result)
        logger.info(f"Moralis trending: {len(result)} tokens on {chain}")
        return result
    except Exception as e:
        logger.warning(f"Moralis trending error for {chain}: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# 3. Top Gainers  (GET /discovery/tokens/top-gainers)
#    Tokens with the highest price % gain — breakout detection
# ─────────────────────────────────────────────────────────────────────────────
def get_top_gainers(chain: str, time_frame: str = "1h") -> list[dict]:
    """
    Fetch top-gaining tokens. Use time_frame='1h' for short-term momentum,
    '1d' for swing trades, '1w' for position trades.
    """
    if not _available(chain) or chain == "solana":
        return []
    moralis_chain = CHAIN_MAP[chain]
    cache_key = f"gainers_{chain}_{time_frame}"
    if _is_cached(cache_key):
        return _get_cache(cache_key)

    _rate_check()
    try:
        resp = requests.get(
            f"{BASE_URL}/discovery/tokens/top-gainers",
            params={"chain": moralis_chain, "time_frame": time_frame},
            headers=_headers(),
            timeout=15,
        )
        if resp.status_code in (402, 403):
            logger.debug(f"Moralis top-gainers: plan limitation for {chain}")
            return []
        resp.raise_for_status()
        data = resp.json()
        tokens = data if isinstance(data, list) else data.get("result", [])
        result = []
        for t in tokens:
            addr = t.get("token_address", "")
            if not addr:
                continue
            result.append({
                "token_address":       addr,
                "token_symbol":        t.get("token_symbol", t.get("symbol", "")),
                "token_name":          t.get("token_name", t.get("name", "")),
                "chain":               chain,
                "price_usd":           _safe_float(t.get("price_usd", 0)),
                "market_cap":          _safe_float(t.get("market_cap", 0)),
                "token_age_days":      _safe_float(t.get("token_age_in_days", 0)),
                "on_chain_strength":   _safe_float(t.get("on_chain_strength_index", 0)),
                "security_score":      _safe_int(t.get("security_score", 0)),
                "twitter_followers":   _safe_int(t.get("twitter_followers", 0)),
                "holders_change_1h":   _safe_float((t.get("holders_change") or {}).get("1h", 0)),
                "volume_change_1h":    _safe_float((t.get("volume_change_usd") or {}).get("1h", 0)),
                "net_volume_1h":       _safe_float((t.get("net_volume_change_usd") or {}).get("1h", 0)),
                "price_change_1h":     _safe_float((t.get("price_percent_change_usd") or {}).get("1h", 0)),
                "price_change_24h":    _safe_float((t.get("price_percent_change_usd") or {}).get("1d", 0)),
                "experienced_net_buyers_1h": _safe_float(
                    (t.get("experienced_net_buyers_change") or {}).get("1h", 0)
                ),
                "source": "moralis_top_gainers",
            })
        _set_cache(cache_key, result)
        logger.info(f"Moralis top-gainers: {len(result)} tokens on {chain} ({time_frame})")
        return result
    except Exception as e:
        logger.warning(f"Moralis top-gainers error for {chain}: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# 4. Top Losers  (GET /discovery/tokens/top-losers)
#    Oversold tokens — mean-reversion / dip-buy candidates for Wallet B
# ─────────────────────────────────────────────────────────────────────────────
def get_top_losers(chain: str, time_frame: str = "1h") -> list[dict]:
    """
    Fetch top-losing tokens. Used by Wallet B (DCA / mean-reversion strategy).
    Tokens with strong fundamentals but short-term price drops are prime dip buys.
    """
    if not _available(chain) or chain == "solana":
        return []
    moralis_chain = CHAIN_MAP[chain]
    cache_key = f"losers_{chain}_{time_frame}"
    if _is_cached(cache_key):
        return _get_cache(cache_key)

    _rate_check()
    try:
        resp = requests.get(
            f"{BASE_URL}/discovery/tokens/top-losers",
            params={"chain": moralis_chain, "time_frame": time_frame},
            headers=_headers(),
            timeout=15,
        )
        if resp.status_code in (402, 403):
            logger.debug(f"Moralis top-losers: plan limitation for {chain}")
            return []
        resp.raise_for_status()
        data = resp.json()
        tokens = data if isinstance(data, list) else data.get("result", [])
        result = []
        for t in tokens:
            addr = t.get("token_address", "")
            if not addr:
                continue
            result.append({
                "token_address":     addr,
                "token_symbol":      t.get("token_symbol", t.get("symbol", "")),
                "token_name":        t.get("token_name", t.get("name", "")),
                "chain":             chain,
                "price_usd":         _safe_float(t.get("price_usd", 0)),
                "market_cap":        _safe_float(t.get("market_cap", 0)),
                "on_chain_strength": _safe_float(t.get("on_chain_strength_index", 0)),
                "security_score":    _safe_int(t.get("security_score", 0)),
                "price_change_1h":   _safe_float((t.get("price_percent_change_usd") or {}).get("1h", 0)),
                "price_change_24h":  _safe_float((t.get("price_percent_change_usd") or {}).get("1d", 0)),
                "volume_change_1h":  _safe_float((t.get("volume_change_usd") or {}).get("1h", 0)),
                "source": "moralis_top_losers",
            })
        _set_cache(cache_key, result)
        logger.info(f"Moralis top-losers: {len(result)} tokens on {chain} ({time_frame})")
        return result
    except Exception as e:
        logger.warning(f"Moralis top-losers error for {chain}: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# 5. Buying Pressure  (GET /discovery/tokens/buying-pressure)
#    Rising buy:sell ratio — momentum signal before price moves
# ─────────────────────────────────────────────────────────────────────────────
def get_buying_pressure_tokens(chain: str) -> list[dict]:
    """Tokens with rising buy:sell ratio — early momentum signal."""
    if not _available(chain):
        return []
    moralis_chain = CHAIN_MAP[chain]
    cache_key = f"buying_pressure_{chain}"
    if _is_cached(cache_key):
        return _get_cache(cache_key)

    _rate_check()
    try:
        resp = requests.get(
            f"{BASE_URL}/discovery/tokens/buying-pressure",
            params={"chain": moralis_chain},
            headers=_headers(),
            timeout=15,
        )
        if resp.status_code in (402, 403):
            logger.debug(f"Moralis buying-pressure: plan limitation for {chain}")
            return []
        resp.raise_for_status()
        data = resp.json()
        tokens = data if isinstance(data, list) else data.get("result", data.get("tokens", []))
        result = [_normalize_discovery_token(t, chain, "moralis_buying_pressure") for t in tokens]
        result = [r for r in result if r]
        _set_cache(cache_key, result)
        logger.info(f"Moralis buying-pressure: {len(result)} tokens on {chain}")
        return result
    except Exception as e:
        logger.warning(f"Moralis buying-pressure error for {chain}: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# 6. Token Score  (GET /tokens/{address}/score)
#    Moralis proprietary 0–100 score with volume/tx/supply breakdown
#    Used to ENRICH gem candidates already found by other sources
# ─────────────────────────────────────────────────────────────────────────────
def get_token_score(token_address: str, chain: str) -> Optional[dict]:
    """
    Get Moralis token score (0–100) for a specific token.
    Includes volume, transaction count, and supply concentration metrics.
    This score directly feeds into the gem scorer as the 'moralis_score' field.
    """
    if not _available(chain):
        return None
    moralis_chain = CHAIN_MAP[chain]
    cache_key = f"score_{chain}_{token_address.lower()}"
    if _is_cached(cache_key):
        return _get_cache(cache_key)

    _rate_check()
    try:
        resp = requests.get(
            f"{BASE_URL}/tokens/{token_address}/score",
            params={"chain": moralis_chain},
            headers=_headers(),
            timeout=10,
        )
        if resp.status_code in (402, 403):
            return None
        resp.raise_for_status()
        data = resp.json()
        metrics = data.get("metrics", {})
        result = {
            "token_address": data.get("tokenAddress", token_address),
            "chain":         chain,
            "score":         _safe_int(data.get("score", 0)),
            "updated_at":    data.get("updatedAt", ""),
            # Volume breakdown
            "volume_10m":    _safe_float((metrics.get("volumeUsd") or {}).get("10m", 0)),
            "volume_1h":     _safe_float((metrics.get("volumeUsd") or {}).get("1h", 0)),
            "volume_4h":     _safe_float((metrics.get("volumeUsd") or {}).get("4h", 0)),
            "volume_24h":    _safe_float((metrics.get("volumeUsd") or {}).get("1d", 0)),
            "volume_7d":     _safe_float((metrics.get("volumeUsd") or {}).get("7d", 0)),
            # Transaction count
            "txns_10m":      _safe_int((metrics.get("transactions") or {}).get("10m", 0)),
            "txns_1h":       _safe_int((metrics.get("transactions") or {}).get("1h", 0)),
            "txns_24h":      _safe_int((metrics.get("transactions") or {}).get("1d", 0)),
            # Supply
            "supply_total":  _safe_float((metrics.get("supply") or {}).get("total", 0)),
            "top10_pct":     _safe_float((metrics.get("supply") or {}).get("top10Percent", 0)),
            "liquidity_usd": _safe_float(metrics.get("liquidityUsd", 0)),
            "price_usd":     _safe_float(metrics.get("usdPrice", 0)),
        }
        _set_cache(cache_key, result)
        return result
    except Exception as e:
        logger.debug(f"Moralis token score error for {token_address} on {chain}: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 7. Token Analytics  (GET /tokens/{address}/analytics)
#    Buy/sell volume, buyers vs sellers, net buyers — money flow signal
# ─────────────────────────────────────────────────────────────────────────────
def get_token_analytics(token_address: str, chain: str) -> Optional[dict]:
    """
    Get detailed buy/sell analytics for a token.
    Net buyers > 0 and rising buy volume = strong buy signal.
    """
    if not _available(chain):
        return None
    moralis_chain = CHAIN_MAP[chain]
    cache_key = f"analytics_{chain}_{token_address.lower()}"
    if _is_cached(cache_key):
        return _get_cache(cache_key)

    _rate_check()
    try:
        resp = requests.get(
            f"{BASE_URL}/tokens/{token_address}/analytics",
            params={"chain": moralis_chain},
            headers=_headers(),
            timeout=10,
        )
        if resp.status_code in (402, 403):
            return None
        resp.raise_for_status()
        data = resp.json()
        # Parse the most important timeframes: 5m, 1h, 6h, 24h
        result = {
            "token_address": token_address,
            "chain":         chain,
        }
        for tf_key, tf_label in [("5m", "5m"), ("1h", "1h"), ("6h", "6h"), ("24h", "24h")]:
            result[f"buy_volume_{tf_label}"]    = _safe_float(data.get(f"totalBuyVolume", {}).get(tf_key, 0))
            result[f"sell_volume_{tf_label}"]   = _safe_float(data.get(f"totalSellVolume", {}).get(tf_key, 0))
            result[f"buyers_{tf_label}"]        = _safe_int(data.get(f"totalBuyers", {}).get(tf_key, 0))
            result[f"sellers_{tf_label}"]       = _safe_int(data.get(f"totalSellers", {}).get(tf_key, 0))
            result[f"net_buyers_{tf_label}"]    = result[f"buyers_{tf_label}"] - result[f"sellers_{tf_label}"]
            result[f"unique_wallets_{tf_label}"]= _safe_int(data.get(f"uniqueWallets", {}).get(tf_key, 0))
        # Derived signal: buy pressure ratio
        bv_1h = result.get("buy_volume_1h", 0)
        sv_1h = result.get("sell_volume_1h", 0)
        total_1h = bv_1h + sv_1h
        result["buy_pressure_ratio_1h"] = bv_1h / total_1h if total_1h > 0 else 0.5
        _set_cache(cache_key, result)
        return result
    except Exception as e:
        logger.debug(f"Moralis analytics error for {token_address} on {chain}: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 8. Batch Token Analytics  (POST /tokens/analytics)
#    Enrich up to 200 tokens at once — used after gem scan to bulk-score
# ─────────────────────────────────────────────────────────────────────────────
def get_batch_analytics(tokens: list[dict]) -> list[dict]:
    """
    Batch analytics for up to 200 tokens.
    tokens: list of {"chain": "base", "token_address": "0x..."}
    Returns analytics results in the same order.
    """
    if not MORALIS_API_KEY or not tokens:
        return []
        
    # Moralis accepts max 30 per call, so we chunk up to 200 tokens
    tokens = tokens[:200]
    all_results = []
    
    for i in range(0, len(tokens), 30):
        chunk = tokens[i:i+30]
        payload = {
            "tokens": [
                {
                    "chain": CHAIN_HEX.get(CHAIN_MAP.get(t["chain"], ""), "0x1"),
                    "tokenAddress": t["token_address"],
                }
                for t in chunk
                if t.get("chain") in CHAIN_MAP and t.get("token_address")
            ]
        }
        if not payload["tokens"]:
            continue

        _rate_check()
        try:
            resp = requests.post(
                f"{BASE_URL}/tokens/analytics",
                json=payload,
                headers=_json_headers(),
                timeout=20,
            )
            if resp.status_code in (402, 403):
                logger.debug("Moralis batch analytics: plan limitation")
                continue
            resp.raise_for_status()
            data = resp.json()
            results = data.get("categories", data) if isinstance(data, dict) else data
            if isinstance(results, list):
                all_results.extend(results)
        except Exception as e:
            logger.warning(f"Moralis batch analytics error for chunk: {e}")
            
    return all_results


# ─────────────────────────────────────────────────────────────────────────────
# 9. Token Stats  (GET /erc20/{address}/stats)  — Free tier
# ─────────────────────────────────────────────────────────────────────────────
def get_token_stats(token_address: str, chain: str) -> Optional[dict]:
    """Transfer count stats — activity proxy. Free tier endpoint."""
    if not _available(chain) or chain == "solana":
        return None
    moralis_chain = CHAIN_MAP[chain]
    _rate_check()
    try:
        resp = requests.get(
            f"{BASE_URL}/erc20/{token_address}/stats",
            params={"chain": moralis_chain},
            headers=_headers(),
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 10. Holder Count  (GET /erc20/{address}/owners)  — Free tier
# ─────────────────────────────────────────────────────────────────────────────
def get_holder_count(token_address: str, chain: str) -> int:
    """Approximate holder count. Free tier endpoint."""
    if not _available(chain) or chain == "solana":
        return 0
    moralis_chain = CHAIN_MAP[chain]
    _rate_check()
    try:
        resp = requests.get(
            f"{BASE_URL}/erc20/{token_address}/owners",
            params={"chain": moralis_chain, "limit": 1},
            headers=_headers(),
            timeout=10,
        )
        resp.raise_for_status()
        return _safe_int(resp.json().get("total", 0))
    except Exception:
        return 0


# ─────────────────────────────────────────────────────────────────────────────
# 11. Discovery Token Details (GET /discovery/token)
#     Deep per-token intel — works for BOTH EVM and Solana (chain=solana)
#     Returns security_score, holders_change, experienced_net_buyers_change,
#     liquidity_change_usd, on_chain_strength_index, and social links.
# ─────────────────────────────────────────────────────────────────────────────
def get_discovery_token_details(token_address: str, chain: str) -> Optional[dict]:
    """
    Get comprehensive discovery details for a specific token.
    This is the richest single-token endpoint — provides security score,
    holder growth, experienced buyer trends, liquidity trends, and social links.

    Works for Solana via chain=solana parameter (same EVM endpoint).
    Lower CU cost than combining multiple separate calls.
    """
    if not _available(chain):
        return None
    moralis_chain = CHAIN_MAP[chain]
    cache_key = f"discovery_detail_{chain}_{token_address.lower()}"
    if _is_cached(cache_key):
        return _get_cache(cache_key)

    _rate_check()
    try:
        resp = requests.get(
            f"{BASE_URL}/discovery/token",
            params={"chain": moralis_chain, "token_address": token_address},
            headers=_headers(),
            timeout=15,
        )
        if resp.status_code in (402, 403, 404):
            return None
        resp.raise_for_status()
        data = resp.json()
        result = {
            "token_address":   data.get("token_address", token_address),
            "token_name":      data.get("token_name", ""),
            "token_symbol":    data.get("token_symbol", ""),
            "chain":           chain,
            "price_usd":       _safe_float(data.get("price_usd", 0)),
            "market_cap":      _safe_float(data.get("market_cap", 0)),
            "fdv":             _safe_float(data.get("fully_diluted_valuation", 0)),
            "security_score":  _safe_int(data.get("security_score", 0)),
            "token_age_days":  _safe_float(data.get("token_age_in_days", 0)),
            "on_chain_strength": _safe_float(data.get("on_chain_strength_index", 0)),
            "twitter_followers": _safe_int(data.get("twitter_followers", 0)),
            # Time-series holder changes
            "holders_change_1h": _safe_int((data.get("holders_change") or {}).get("1h", 0)),
            "holders_change_1d": _safe_int((data.get("holders_change") or {}).get("1d", 0)),
            "holders_change_1w": _safe_int((data.get("holders_change") or {}).get("1w", 0)),
            "holders_change_1m": _safe_int((data.get("holders_change") or {}).get("1M", 0)),
            # Experienced net buyers — whale signal
            "exp_net_buyers_1h": _safe_int((data.get("experienced_net_buyers_change") or {}).get("1h", 0)),
            "exp_net_buyers_1d": _safe_int((data.get("experienced_net_buyers_change") or {}).get("1d", 0)),
            "exp_net_buyers_1w": _safe_int((data.get("experienced_net_buyers_change") or {}).get("1w", 0)),
            # Liquidity changes
            "liquidity_change_1h": _safe_float((data.get("liquidity_change_usd") or {}).get("1h", 0)),
            "liquidity_change_1d": _safe_float((data.get("liquidity_change_usd") or {}).get("1d", 0)),
            "liquidity_change_1w": _safe_float((data.get("liquidity_change_usd") or {}).get("1w", 0)),
            # Volume trends
            "volume_change_1h": _safe_float((data.get("volume_change_usd") or {}).get("1h", 0)),
            "volume_change_1d": _safe_float((data.get("volume_change_usd") or {}).get("1d", 0)),
            # Net volume (buy - sell)
            "net_volume_1h": _safe_float((data.get("net_volume_change_usd") or {}).get("1h", 0)),
            "net_volume_1d": _safe_float((data.get("net_volume_change_usd") or {}).get("1d", 0)),
            # Price changes
            "price_change_1h": _safe_float((data.get("price_percent_change_usd") or {}).get("1h", 0)),
            "price_change_1d": _safe_float((data.get("price_percent_change_usd") or {}).get("1d", 0)),
            "price_change_1w": _safe_float((data.get("price_percent_change_usd") or {}).get("1w", 0)),
            # Social links
            "links": data.get("links", {}),
            # Locked supply/liquidity percentages
            "total_liquidity_locked_pct": _safe_float(data.get("total_liquidity_locked_in_percent", 0)),
            "total_supply_locked_pct": _safe_float(data.get("total_supply_locked_in_percent", 0)),
        }
        _set_cache(cache_key, result)
        return result
    except Exception as e:
        logger.debug(f"Moralis discovery token detail error for {token_address} on {chain}: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Unified Discovery  — called by gem_scanner.py
# ─────────────────────────────────────────────────────────────────────────────
def discover_tokens(chains: list[str] = None) -> list[dict]:
    """
    PRIMARY DISCOVERY FUNCTION — called by GemScanner on every cycle.

    Aggregates tokens from ALL six Moralis discovery endpoints:
      1. Filtered Tokens (experienced buyers + liquidity + security filters)
      1b. Whale Accumulation (netExperiencedBuyers — strongest smart-money signal)
      2. Trending Tokens
      3. Top Gainers (1h)
      4. Buying Pressure
      5. Top Losers (for Wallet B mean-reversion)

    Deduplicates by address+chain. Tags each token with its source so the
    gem scorer can apply appropriate weight multipliers.

    Returns a combined, deduplicated list ready for DexScreener pair lookup
    and full gem scoring.
    """
    if not MORALIS_API_KEY:
        logger.warning(
            "⚠️  MORALIS_API_KEY not set — Moralis Money is configured as a PRIMARY data source. "
            "Add MORALIS_API_KEY to your .env file to enable it. "
            "Get a free key at https://moralis.io"
        )
        return []

    if chains is None:
        chains = list(CHAIN_MAP.keys())

    all_tokens: list[dict] = []
    seen: set[str] = set()

    for chain in chains:
        # 1. Filtered tokens — highest signal quality
        for t in get_filtered_tokens(chain):
            _dedup_add(t, chain, seen, all_tokens)

        # 1b. Whale accumulation — strongest smart-money signal
        for t in get_whale_accumulation_tokens(chain):
            _dedup_add(t, chain, seen, all_tokens)

        # 2. Trending
        for t in get_trending_tokens(chain):
            _dedup_add(t, chain, seen, all_tokens)

        # 3. Top gainers (1h momentum)
        for t in get_top_gainers(chain, time_frame="1h"):
            _dedup_add(t, chain, seen, all_tokens)

        # 4. Buying pressure
        for t in get_buying_pressure_tokens(chain):
            _dedup_add(t, chain, seen, all_tokens)

        # 5. Top losers — flag for Wallet B mean-reversion
        for t in get_top_losers(chain, time_frame="1h"):
            t["mean_reversion_candidate"] = True
            _dedup_add(t, chain, seen, all_tokens)

    logger.info(
        f"🍀 Moralis Money (PRIMARY): {len(all_tokens)} unique tokens discovered "
        f"across {len(chains)} chains"
    )
    return all_tokens


def _dedup_add(token: dict, chain: str, seen: set, result: list) -> None:
    """Add token to result if not already seen (dedup by address+chain)."""
    addr = token.get("token_address", "").lower()
    if not addr:
        return
    key = f"{chain}:{addr}"
    if key not in seen:
        seen.add(key)
        result.append(token)


# ─────────────────────────────────────────────────────────────────────────────
# Enrichment  — called by gem_scorer.py to add Moralis signals to candidates
# ─────────────────────────────────────────────────────────────────────────────
def enrich_candidate(token_address: str, chain: str) -> dict:
    """
    Enrich a gem candidate with Moralis token score + analytics + discovery details.
    Returns a dict with moralis_score, buy_pressure_ratio, net_buyers_1h,
    whale accumulation signals, and comprehensive discovery data.
    Called by the gem scorer for each candidate that passes initial filters.
    """
    score_data = get_token_score(token_address, chain)
    analytics_data = get_token_analytics(token_address, chain)
    discovery_data = get_discovery_token_details(token_address, chain)

    enrichment = {
        "moralis_score":         0,
        "moralis_volume_1h":     0.0,
        "moralis_txns_1h":       0,
        "moralis_top10_pct":     0.0,
        "moralis_net_buyers_1h": 0,
        "moralis_buy_pressure":  0.5,
        "moralis_buyers_1h":     0,
        "moralis_sellers_1h":    0,
        # Discovery token intel
        "moralis_security_score":    0,
        "moralis_on_chain_strength": 0.0,
        "moralis_exp_net_buyers_1d": 0,
        "moralis_exp_net_buyers_1w": 0,
        "moralis_holders_change_1d": 0,
        "moralis_holders_change_1w": 0,
        "moralis_liquidity_change_1d": 0.0,
        "moralis_net_volume_1d":     0.0,
        "moralis_token_age_days":    0.0,
        "moralis_liquidity_locked_pct": 0.0,
    }

    if score_data:
        enrichment["moralis_score"]        = score_data.get("score", 0)
        enrichment["moralis_volume_1h"]    = score_data.get("volume_1h", 0.0)
        enrichment["moralis_txns_1h"]      = score_data.get("txns_1h", 0)
        enrichment["moralis_top10_pct"]    = score_data.get("top10_pct", 0.0)

    if analytics_data:
        enrichment["moralis_net_buyers_1h"] = analytics_data.get("net_buyers_1h", 0)
        enrichment["moralis_buy_pressure"]  = analytics_data.get("buy_pressure_ratio_1h", 0.5)
        enrichment["moralis_buyers_1h"]     = analytics_data.get("buyers_1h", 0)
        enrichment["moralis_sellers_1h"]    = analytics_data.get("sellers_1h", 0)

    # Discovery token deep intel — works for both EVM and Solana
    if discovery_data:
        enrichment["moralis_security_score"]     = discovery_data.get("security_score", 0)
        enrichment["moralis_on_chain_strength"]  = discovery_data.get("on_chain_strength", 0.0)
        enrichment["moralis_exp_net_buyers_1d"]  = discovery_data.get("exp_net_buyers_1d", 0)
        enrichment["moralis_exp_net_buyers_1w"]  = discovery_data.get("exp_net_buyers_1w", 0)
        enrichment["moralis_holders_change_1d"]  = discovery_data.get("holders_change_1d", 0)
        enrichment["moralis_holders_change_1w"]  = discovery_data.get("holders_change_1w", 0)
        enrichment["moralis_liquidity_change_1d"]= discovery_data.get("liquidity_change_1d", 0.0)
        enrichment["moralis_net_volume_1d"]      = discovery_data.get("net_volume_1d", 0.0)
        enrichment["moralis_token_age_days"]     = discovery_data.get("token_age_days", 0.0)
        enrichment["moralis_liquidity_locked_pct"]= discovery_data.get("total_liquidity_locked_pct", 0.0)
        # Override security score with discovery data if higher (more accurate)
        if discovery_data.get("security_score", 0) > enrichment.get("moralis_score", 0):
            enrichment["moralis_score"] = max(
                enrichment["moralis_score"],
                discovery_data["security_score"]
            )

    return enrichment


# ─────────────────────────────────────────────────────────────────────────────
# Score Contribution  — converts Moralis enrichment into a gem score boost
# ─────────────────────────────────────────────────────────────────────────────
def calculate_moralis_score_contribution(enrichment: dict) -> float:
    """
    Convert Moralis enrichment data into a 0–100 score contribution.
    This is added to the gem candidate's composite score with a 15% weight.

    Scoring logic (base — 80% of contribution):
      - Moralis token score (0–100):          35% of contribution
      - Buy pressure ratio (0–1 → 0–100):     20% of contribution
      - Net buyers 1h (capped at 100):         15% of contribution
      - Transaction count 1h (capped at 100):  10% of contribution

    Whale accumulation bonus (20% of contribution — from discovery token details):
      - Experienced net buyers 1d/1w:          8%  (whale accumulation signal)
      - Holder growth 1d:                      4%  (organic adoption signal)
      - On-chain strength index:               4%  (overall health signal)
      - Liquidity locked %:                    4%  (rug-pull protection signal)
    """
    moralis_score    = min(100.0, enrichment.get("moralis_score", 0))
    buy_pressure     = enrichment.get("moralis_buy_pressure", 0.5)
    buy_pressure_pct = min(100.0, buy_pressure * 100)  # 0–1 → 0–100
    net_buyers       = min(100.0, max(0.0, enrichment.get("moralis_net_buyers_1h", 0) * 2))
    txns             = min(100.0, enrichment.get("moralis_txns_1h", 0) / 10)  # 1000 txns = 100

    # Base contribution (80%)
    base = (
        moralis_score    * 0.35
        + buy_pressure_pct * 0.20
        + net_buyers       * 0.15
        + txns             * 0.10
    )

    # Whale accumulation bonus (20%) — from discovery token details
    exp_net_buyers_1w = enrichment.get("moralis_exp_net_buyers_1w", 0)
    exp_net_buyers_1d = enrichment.get("moralis_exp_net_buyers_1d", 0)
    # Scale whale signal: 50+ experienced net buyers over 1 week = max score
    whale_signal = min(100.0, max(0.0, (exp_net_buyers_1w + exp_net_buyers_1d) * 1.5))

    holder_growth = enrichment.get("moralis_holders_change_1d", 0)
    # Scale holder growth: 200+ new holders/day = max score
    holder_signal = min(100.0, max(0.0, holder_growth * 0.5))

    on_chain_strength = min(100.0, enrichment.get("moralis_on_chain_strength", 0))

    liquidity_locked = min(100.0, enrichment.get("moralis_liquidity_locked_pct", 0))

    whale_bonus = (
        whale_signal       * 0.08
        + holder_signal    * 0.04
        + on_chain_strength * 0.04
        + liquidity_locked  * 0.04
    )

    contribution = base + whale_bonus
    return round(min(100.0, contribution), 2)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def _normalize_discovery_token(t: dict, chain: str, source: str) -> Optional[dict]:
    """Normalize a raw Moralis discovery token to our standard format."""
    addr = t.get("token_address", t.get("address", ""))
    if not addr:
        return None
    return {
        "token_address":  addr,
        "token_symbol":   t.get("token_symbol", t.get("symbol", "")),
        "token_name":     t.get("token_name", t.get("name", "")),
        "chain":          chain,
        "price_usd":      _safe_float(t.get("price_usd", t.get("usd_price", 0))),
        "volume_usd":     _safe_float(t.get("volume_usd", t.get("volume_24h", 0))),
        "market_cap":     _safe_float(t.get("market_cap", 0)),
        "price_change_24h": _safe_float(t.get("price_change_24h", t.get("price_24h_percent_change", 0))),
        "buying_pressure":  _safe_float(t.get("buyer_to_seller_ratio", t.get("buying_pressure", 0))),
        "on_chain_strength": _safe_float(t.get("on_chain_strength_index", 0)),
        "security_score": _safe_int(t.get("security_score", 0)),
        "source":         source,
    }


def get_usage_stats() -> dict:
    """Return cache stats for monitoring."""
    return {
        "api_key_configured": bool(MORALIS_API_KEY),
        "cached_keys": len(_cache),
        "cache_entries": {k: "cached" for k in _cache},
    }
