"""
data/providers/moralis_defi.py — Moralis Universal DeFi API.

Provides DeFi protocol position data across EVM chains and Solana.
Used to detect smart money DeFi activity around gem tokens:
  - Which tokens are being provided as liquidity by smart wallets?
  - Which tokens are being used as collateral in lending protocols?
  - What is the total TVL locked in a token's DeFi positions?

Endpoints used:
  GET /wallets/{address}/defi/positions        → Wallet DeFi positions (5000 CU per call)
  GET /wallets/{address}/defi/summary          → Summary of all DeFi positions (5000 CU)
  GET /defi/{protocol}/positions               → Protocol-level positions (5000 CU)

CU Conservation Strategy:
  - DeFi positions are EXPENSIVE (5000 CU each) — only called for top-tier alpha wallets
  - 30-minute cache to avoid redundant calls
  - Only called when a token passes the gem score threshold of 65+
  - Batch lookup: one call per wallet covers all protocols
  - Gated by MORALIS_DEFI_ENABLED setting (default: True)
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

# DeFi calls are expensive (5000 CU) — cache aggressively
DEFI_CACHE_TTL = 1800  # 30 minutes

_cache: dict[str, dict] = {}
_cache_lock = threading.Lock()

# Rate limiter — shared Pro-tier global limiter (60 RPS, CU-budget-aware)
from data.providers.moralis_rate_limiter import rate_check as _rate_check
_rate_lock = threading.Lock()

# Chain hex IDs for EVM chains
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
    return bool(MORALIS_API_KEY) and getattr(settings, "MORALIS_DEFI_ENABLED", True)




def _is_cached(key: str, ttl: int = DEFI_CACHE_TTL) -> bool:
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


# ─────────────────────────────────────────────────────────────────────────────
# Wallet DeFi Position Functions
# ─────────────────────────────────────────────────────────────────────────────

def get_wallet_defi_summary(wallet_address: str, chain: str = "ethereum") -> Optional[dict]:
    """
    Get a high-level summary of a wallet's DeFi positions.
    Returns total USD value locked, protocol count, and top protocols.
    
    CU Cost: 5000 (EXPENSIVE — use sparingly, cache aggressively)
    Cache TTL: 30 minutes
    """
    if not _available() or not wallet_address:
        return None
    
    cache_key = f"defi_summary_{chain}_{wallet_address.lower()}"
    if _is_cached(cache_key):
        return _get_cache(cache_key)
    
    chain_hex = CHAIN_HEX.get(chain)
    if not chain_hex and chain != "solana":
        return None
    
    _rate_check()
    try:
        params = {}
        if chain == "solana":
            params["chain"] = "solana"
        else:
            params["chain"] = chain_hex
        
        resp = get_session().get(
            f"{BASE_URL}/wallets/{wallet_address}/defi/summary",
            params=params,
            headers=_headers(),
            timeout=15,
        )
        if resp.status_code in (400, 404, 422, 429):
            return None
        resp.raise_for_status()
        data = resp.json()
        
        result = {
            "total_usd_value": _safe_float(data.get("total_usd_value", 0)),
            "protocol_count": len(data.get("protocols", [])),
            "protocols": [p.get("protocol_name", "") for p in data.get("protocols", [])],
            "active_positions": data.get("active_positions", 0),
        }
        _set_cache(cache_key, result)
        return result
    except Exception as e:
        logger.debug(f"DeFi summary error {chain}/{wallet_address[:8]}: {e}")
        return None


def get_wallet_defi_positions(wallet_address: str, chain: str = "ethereum") -> list[dict]:
    """
    Get detailed DeFi protocol positions for a wallet.
    Returns positions in Uniswap, Aave, Compound, Curve, etc.
    
    CU Cost: 5000 (EXPENSIVE — only call for top-tier alpha wallets)
    Cache TTL: 30 minutes
    """
    if not _available() or not wallet_address:
        return []
    
    cache_key = f"defi_pos_{chain}_{wallet_address.lower()}"
    if _is_cached(cache_key):
        return _get_cache(cache_key)
    
    chain_hex = CHAIN_HEX.get(chain)
    if not chain_hex and chain != "solana":
        return []
    
    _rate_check()
    try:
        params = {}
        if chain == "solana":
            params["chain"] = "solana"
        else:
            params["chain"] = chain_hex
        
        resp = get_session().get(
            f"{BASE_URL}/wallets/{wallet_address}/defi/positions",
            params=params,
            headers=_headers(),
            timeout=15,
        )
        if resp.status_code in (400, 404, 422, 429):
            return []
        resp.raise_for_status()
        data = resp.json()
        positions = data.get("result", data) if isinstance(data, dict) else data
        
        result = []
        for p in (positions or []):
            result.append({
                "protocol_name": p.get("protocol_name", ""),
                "protocol_id": p.get("protocol_id", ""),
                "position_type": p.get("position_type", ""),
                "usd_value": _safe_float(p.get("usd_value", 0)),
                "tokens": p.get("tokens", []),
            })
        
        _set_cache(cache_key, result)
        return result
    except Exception as e:
        logger.debug(f"DeFi positions error {chain}/{wallet_address[:8]}: {e}")
        return []


def get_token_defi_exposure(token_address: str, chain: str, alpha_wallets: list[str]) -> dict:
    """
    Check if any alpha wallets have DeFi positions involving a specific token.
    Returns a summary of DeFi exposure for the token.
    
    This is the key integration point with gem_scanner:
    - If top alpha wallets are providing liquidity for this token, it's a strong signal
    - If top alpha wallets are using this token as collateral, it's a strong signal
    
    CU Cost: 5000 per wallet (EXPENSIVE — only call for top 3 alpha wallets max)
    """
    if not _available() or not token_address or not alpha_wallets:
        return {"defi_exposure_score": 0.0, "exposed_wallets": 0, "total_usd_value": 0.0}
    
    token_lower = token_address.lower()
    exposed_wallets = 0
    total_usd_value = 0.0
    protocols_found = set()
    
    # Only check top 3 alpha wallets to conserve CUs
    for wallet in alpha_wallets[:3]:
        positions = get_wallet_defi_positions(wallet, chain)
        for pos in positions:
            # Check if this token appears in the position's token list
            for token_info in pos.get("tokens", []):
                if token_info.get("token_address", "").lower() == token_lower:
                    exposed_wallets += 1
                    total_usd_value += pos.get("usd_value", 0.0)
                    protocols_found.add(pos.get("protocol_name", ""))
                    break
    
    # Score: 0-100 based on number of wallets and USD value
    defi_exposure_score = min(100.0, (exposed_wallets * 25.0) + (total_usd_value / 10_000.0))
    
    return {
        "defi_exposure_score": round(defi_exposure_score, 1),
        "exposed_wallets": exposed_wallets,
        "total_usd_value": total_usd_value,
        "protocols": list(protocols_found),
    }


def get_protocol_tvl_for_token(token_address: str, chain: str) -> float:
    """
    Estimate total TVL locked in DeFi positions for a specific token.
    Uses the Uniswap V3 pair stats as a proxy for DeFi TVL.
    
    Returns total USD value locked in DeFi positions.
    """
    # This is a lightweight proxy using existing pair stats
    try:
        from data.providers.moralis_money import get_aggregated_pair_stats
        pair_stats = get_aggregated_pair_stats(token_address, chain)
        if pair_stats:
            return _safe_float(pair_stats.get("total_liquidity_usd", 0))
    except Exception as e:
        logger.debug(f"DeFi TVL proxy error for {token_address[:8]}: {e}")
    return 0.0


def get_usage_stats() -> dict:
    """Return cache and rate-limit stats for monitoring."""
    with _cache_lock:
        cached_count = len(_cache)
    return {
        "api_key_configured": bool(MORALIS_API_KEY),
        "defi_enabled": getattr(settings, "MORALIS_DEFI_ENABLED", True),
        "cached_keys": cached_count,
        "rate_limiter": "shared_pro_tier",
        "endpoints_covered": [
            "getDefiSummary (5000 CU)",
            "getDefiPositionsSummary (5000 CU)",
            "getDefiPositionsByProtocol (5000 CU)",
        ],
        "note": "DeFi endpoints are expensive (5000 CU each). Only called for top-tier alpha wallets.",
    }
