"""
data/providers/binance_pulse.py — Binance Web3 Pulse API integration.

Free, keyless APIs from Binance's Web3 wallet platform. Provides:
  1. Smart Money Inflow Rank — tokens smart money is buying RIGHT NOW
  2. Social Hype Leaderboard — social buzz/sentiment scoring
  3. Unified Token Rank — trending + top-searched token discovery

No API key required — only a User-Agent header.
All responses cached 60s to avoid rate limiting.

Chain ID mapping:
  BSC = "56", Ethereum = "1", Base = "8453", Solana = "CT_501"
"""

import logging
import requests
import time
from typing import Optional

from data.http_session import get_session

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

_BASE_URL = "https://web3.binance.com/bapi/defi/v1/public/wallet-direct"
_USER_AGENT = "binance-web3/2.1 (Skill)"
_HEADERS = {
    "Accept-Encoding": "identity",
    "User-Agent": _USER_AGENT,
}
_JSON_HEADERS = {
    **_HEADERS,
    "Content-Type": "application/json",
}

# Internal chain name → Binance chain ID
_CHAIN_ID_MAP = {
    "bsc": "56",
    "ethereum": "1",
    "base": "8453",
    "solana": "CT_501",
    "arbitrum": "42161",
    "polygon": "137",
    "avalanche": "43114",
}

# Reverse: Binance chain ID → internal chain name
_REVERSE_CHAIN_MAP = {v: k for k, v in _CHAIN_ID_MAP.items()}

# ─────────────────────────────────────────────────────────────────────────────
# Cache
# ─────────────────────────────────────────────────────────────────────────────

_cache: dict[str, tuple[float, object]] = {}
_CACHE_TTL = 60  # 60 seconds — Binance data refreshes frequently


def _cached(key: str) -> Optional[object]:
    if key in _cache:
        ts, val = _cache[key]
        if time.time() - ts < _CACHE_TTL:
            return val
    return None


def _store(key: str, value: object) -> object:
    _cache[key] = (time.time(), value)
    return value


# ─────────────────────────────────────────────────────────────────────────────
# API 1: Smart Money Inflow Rank
# ─────────────────────────────────────────────────────────────────────────────

def get_smart_money_inflow(
    chain: str = "bsc",
    period: str = "24h",
    limit: int = 50,
) -> list[dict]:
    """
    Get tokens with highest smart money inflow.

    Args:
        chain: Internal chain name (bsc, ethereum, base, solana)
        period: Time period — "5m", "1h", "4h", "24h"
        limit: Max results (API returns up to ~100)

    Returns:
        List of dicts with keys:
          - token_address: str
          - token_symbol: str
          - token_name: str
          - chain: str (internal name)
          - chain_id: str (Binance ID)
          - inflow_amount_usd: float
          - smart_money_count: int
          - price_usd: float
          - percent_change_24h: float
          - market_cap: float
          - logo_url: str
    """
    chain_id = _CHAIN_ID_MAP.get(chain)
    if not chain_id:
        logger.debug(f"Binance Pulse: unsupported chain '{chain}'")
        return []

    cache_key = f"bp:sm:{chain}:{period}"
    cached = _cached(cache_key)
    if cached is not None:
        return cached

    url = f"{_BASE_URL}/tracker/wallet/token/inflow/rank/query/ai"

    try:
        resp = get_session().post(
            url,
            json={
                "chainId": chain_id,
                "period": period,
                "tagType": 2,  # Smart money tag
            },
            headers=_JSON_HEADERS,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        if not data.get("success") or data.get("code") != "000000":
            logger.debug(f"Binance SM Inflow: non-success response for {chain}")
            return _store(cache_key, [])

        results = []
        for item in (data.get("data") or [])[:limit]:
            token_addr = item.get("ca", "")  # Binance uses 'ca' for contract address
            if not token_addr:
                continue
            results.append({
                "token_address": token_addr,
                "token_symbol": item.get("tokenName", ""),  # Binance 'tokenName' = symbol
                "token_name": item.get("tokenName", ""),
                "chain": chain,
                "chain_id": chain_id,
                "inflow_amount_usd": _safe_float(item.get("volume", "0")),
                "smart_money_count": _safe_int(item.get("tokenCautionNum", "0")),
                "price_usd": _safe_float(item.get("price", "0")),
                "percent_change_24h": _safe_float(item.get("priceChangeRate", "0")),
                "market_cap": _safe_float(item.get("marketCap", "0")),
                "logo_url": _logo_url(item.get("tokenIconUrl", "")),
            })

        logger.info(
            f"Binance SM Inflow [{chain}/{period}]: "
            f"{len(results)} tokens with smart money buying"
        )
        return _store(cache_key, results)

    except requests.Timeout:
        logger.debug(f"Binance SM Inflow timeout for {chain}/{period}")
        return _store(cache_key, [])
    except Exception as e:
        logger.debug(f"Binance SM Inflow error for {chain}/{period}: {e}")
        return _store(cache_key, [])


def is_smart_money_buying(
    token_address: str,
    chain: str = "bsc",
    period: str = "24h",
) -> dict:
    """
    Check if a specific token has smart money inflow.

    Returns:
        Dict with:
          - confirmed: bool — True if token is in smart money inflow top 50
          - inflow_amount_usd: float — USD inflow amount (0 if not found)
          - smart_money_count: int — number of smart money wallets buying
          - rank: int — position in inflow ranking (0 if not found)
    """
    inflows = get_smart_money_inflow(chain=chain, period=period)
    addr_lower = token_address.lower()

    for i, item in enumerate(inflows):
        if item["token_address"].lower() == addr_lower:
            return {
                "confirmed": True,
                "inflow_amount_usd": item["inflow_amount_usd"],
                "smart_money_count": item["smart_money_count"],
                "rank": i + 1,
            }

    return {
        "confirmed": False,
        "inflow_amount_usd": 0.0,
        "smart_money_count": 0,
        "rank": 0,
    }


# ─────────────────────────────────────────────────────────────────────────────
# API 2: Social Hype Leaderboard
# ─────────────────────────────────────────────────────────────────────────────

def get_social_hype(
    chain: str = "bsc",
    sentiment: str = "All",
    time_range: int = 1,
) -> list[dict]:
    """
    Get tokens ranked by social hype/buzz.

    Args:
        chain: Internal chain name
        sentiment: "All", "Positive", "Negative", "Neutral"
        time_range: 1 = last period

    Returns:
        List of dicts with keys:
          - token_address: str
          - token_symbol: str
          - chain: str
          - social_score: float (0-100 normalized)
          - sentiment: str
          - mentions: int
          - price_usd: float
          - percent_change_24h: float
    """
    chain_id = _CHAIN_ID_MAP.get(chain)
    if not chain_id:
        return []

    cache_key = f"bp:social:{chain}:{sentiment}:{time_range}"
    cached = _cached(cache_key)
    if cached is not None:
        return cached

    url = (
        f"{_BASE_URL}/buw/wallet/market/token/pulse/social/hype/"
        f"rank/leaderboard/ai"
    )

    try:
        resp = get_session().get(
            url,
            params={
                "chainId": chain_id,
                "sentiment": sentiment,
                "socialLanguage": "ALL",
                "targetLanguage": "en",
                "timeRange": time_range,
            },
            headers=_HEADERS,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        if not data.get("success") or data.get("code") != "000000":
            return _store(cache_key, [])

        results = []
        leaderboard = (
            data.get("data", {}).get("leaderBoardList", [])
            if isinstance(data.get("data"), dict)
            else []
        )

        for item in leaderboard:
            token_addr = item.get("tokenAddress", "")
            if not token_addr:
                continue

            # Normalize social score to 0-100
            raw_score = _safe_float(item.get("socialScore", "0"))
            # Binance scores vary — clamp to 0-100
            normalized_score = max(0.0, min(100.0, raw_score))

            results.append({
                "token_address": token_addr,
                "token_symbol": item.get("tokenSymbol", ""),
                "chain": chain,
                "social_score": normalized_score,
                "sentiment": item.get("sentiment", "unknown"),
                "mentions": _safe_int(item.get("mentionCount", "0")),
                "price_usd": _safe_float(item.get("tokenPrice", "0")),
                "percent_change_24h": _safe_float(
                    item.get("percentChange24h", "0")
                ),
            })

        logger.info(
            f"Binance Social Hype [{chain}]: "
            f"{len(results)} tokens with social buzz"
        )
        return _store(cache_key, results)

    except Exception as e:
        logger.debug(f"Binance Social Hype error for {chain}: {e}")
        return _store(cache_key, [])


def get_social_hype_score(token_address: str, chain: str = "bsc") -> float:
    """
    Get social hype score for a specific token.

    Returns:
        Score 0-100, or 50.0 (neutral) if not found.
    """
    hype_list = get_social_hype(chain=chain)
    addr_lower = token_address.lower()

    for item in hype_list:
        if item["token_address"].lower() == addr_lower:
            return item["social_score"]

    return 50.0  # Neutral — no data


# ─────────────────────────────────────────────────────────────────────────────
# API 3: Unified Token Rank (Discovery)
# ─────────────────────────────────────────────────────────────────────────────

def get_trending_tokens(
    chain: str = "bsc",
    rank_type: int = 10,
    period: int = 50,
    limit: int = 20,
) -> list[dict]:
    """
    Get trending/top-searched tokens from Binance Pulse.

    Args:
        chain: Internal chain name
        rank_type: 10=trending, 11=top searched, 20=Binance Alpha
        period: Sort period (10=1h, 20=4h, 30=12h, 40=24h, 50=7d)
        limit: Results per page (max ~50)

    Returns:
        List of dicts with discovery data for each token.
    """
    chain_id = _CHAIN_ID_MAP.get(chain)
    if not chain_id:
        return []

    cache_key = f"bp:trending:{chain}:{rank_type}:{period}"
    cached = _cached(cache_key)
    if cached is not None:
        return cached

    url = (
        f"{_BASE_URL}/buw/wallet/market/token/pulse/unified/"
        f"rank/list/ai"
    )

    try:
        resp = get_session().post(
            url,
            json={
                "rankType": rank_type,
                "chainId": chain_id,
                "period": period,
                "sortBy": 70,  # Sort by trending score
                "orderAsc": False,
                "page": 1,
                "size": limit,
            },
            headers=_JSON_HEADERS,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        if not data.get("success") or data.get("code") != "000000":
            return _store(cache_key, [])

        results = []
        tokens = data.get("data", {}).get("tokens", [])

        for item in tokens:
            token_addr = item.get("contractAddress", "")  # Binance uses 'contractAddress'
            if not token_addr:
                continue

            results.append({
                "token_address": token_addr,
                "token_symbol": item.get("symbol", ""),
                "token_name": item.get("symbol", ""),  # Name not always available, use symbol
                "chain": chain,
                "chain_id": chain_id,
                "price_usd": _safe_float(item.get("price", "0")),
                "market_cap": _safe_float(item.get("marketCap", "0")),
                "volume_24h": _safe_float(item.get("volume24h", "0")),
                "percent_change_1h": _safe_float(
                    item.get("percentChange1h", "0")
                ),
                "percent_change_24h": _safe_float(
                    item.get("percentChange24h", "0")
                ),
                "holder_count": _safe_int(item.get("holderCount", "0")),
                "liquidity_usd": _safe_float(item.get("liquidity", "0")),
                "logo_url": _logo_url(item.get("icon", "")),
            })

        logger.info(
            f"Binance Trending [{chain}/type={rank_type}]: "
            f"{len(results)} tokens"
        )
        return _store(cache_key, results)

    except Exception as e:
        logger.debug(f"Binance Trending error for {chain}: {e}")
        return _store(cache_key, [])


# ─────────────────────────────────────────────────────────────────────────────
# Batch helpers — for concurrent enrichment
# ─────────────────────────────────────────────────────────────────────────────

def enrich_candidate(token_address: str, chain: str) -> dict:
    """
    One-call enrichment for the gem scanner thread pool.

    Checks both smart money inflow and social hype for a single token.
    Returns a dict to merge into the candidate's enrichment results.
    """
    result = {
        "binance_smart_money_confirmed": False,
        "binance_smart_money_inflow_usd": 0.0,
        "binance_smart_money_count": 0,
        "binance_smart_money_rank": 0,
        "binance_social_hype_score": 50.0,
    }

    # Smart money check
    try:
        sm = is_smart_money_buying(token_address, chain=chain, period="24h")
        result["binance_smart_money_confirmed"] = sm["confirmed"]
        result["binance_smart_money_inflow_usd"] = sm["inflow_amount_usd"]
        result["binance_smart_money_count"] = sm["smart_money_count"]
        result["binance_smart_money_rank"] = sm["rank"]
    except Exception as e:
        logger.debug(f"Binance SM enrichment failed for {token_address[:10]}: {e}")

    # Social hype check
    try:
        result["binance_social_hype_score"] = get_social_hype_score(
            token_address, chain=chain
        )
    except Exception as e:
        logger.debug(f"Binance social enrichment failed for {token_address[:10]}: {e}")

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────────────────────────────────────

def _safe_float(val) -> float:
    """Parse string/number to float, returning 0.0 on failure."""
    try:
        return float(val) if val else 0.0
    except (ValueError, TypeError):
        return 0.0


def _safe_int(val) -> int:
    """Parse string/number to int, returning 0 on failure."""
    try:
        return int(float(val)) if val else 0
    except (ValueError, TypeError):
        return 0


def _logo_url(path: str) -> str:
    """Prepend Binance static CDN prefix if path is relative."""
    if not path:
        return ""
    if path.startswith("http"):
        return path
    return f"https://bin.bnbstatic.com{path}"


def get_supported_chains() -> list[str]:
    """Return list of internal chain names supported by Binance Pulse."""
    return list(_CHAIN_ID_MAP.keys())
