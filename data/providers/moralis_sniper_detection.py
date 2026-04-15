"""
data/providers/moralis_sniper_detection.py — Moralis Sniper Convergence Detector.

Scans known sniper wallets (ALPHA_WALLETS_EVM + ALPHA_WALLETS_SOLANA) for
tokens that multiple snipers have bought within the last 5 minutes. When ≥3
distinct snipers converge on the same token, it's flagged as an express-lane
candidate — these wallets are historically profitable and their convergence
is a high-conviction accumulation signal.

Data source: Moralis GET /wallets/{address}/swaps (50 CU per call)
Cache: 5 minutes per wallet
Rate: Shares the global Moralis 25 req/min pool

Usage:
    from data.providers.moralis_sniper_detection import discover_sniper_convergence
    convergence = discover_sniper_convergence()
    # Returns list of {token_address, chain, sniper_count, sniper_wallets, ...}
"""

import json
import logging
import os
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from data.http_session import get_session

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────
MORALIS_BASE_URL = "https://deep-index.moralis.io/api/v2.2"
CONVERGENCE_WINDOW_SECONDS = 300  # 5 minutes
MIN_SNIPERS_FOR_FLAG = 3          # Minimum distinct snipers on same token
MAX_WALLETS_PER_CYCLE = 20        # Cap to control CU burn (20 × 50 CU = 1000 CU)

CHAIN_HEX = {
    "ethereum": "0x1",
    "base": "0x2105",
    "arbitrum": "0xa4b1",
    "polygon": "0x89",
    "bsc": "0x38",
    "avalanche": "0xa86a",
}

# ─────────────────────────────────────────────────────────────────────────────
# Cache — 5 minute TTL per wallet's recent swaps
# ─────────────────────────────────────────────────────────────────────────────
_cache: dict[str, tuple[float, list]] = {}  # wallet -> (timestamp, swaps)
_CACHE_TTL = 300  # 5 minutes

# Global rate limiter (shared with moralis_wallet.py in practice,
# but we track our own window to be safe)
_rate_window_start: float = time.time()
_rate_calls_in_window: int = 0
_RATE_LIMIT_PER_MIN = 25


def _get_api_key() -> str:
    """Load Moralis API key."""
    try:
        from config import settings
        return getattr(settings, "MORALIS_API_KEY", "") or ""
    except ImportError:
        return os.getenv("MORALIS_API_KEY", "")


def _headers() -> dict:
    return {"accept": "application/json", "X-API-Key": _get_api_key()}


def _rate_check() -> None:
    global _rate_window_start, _rate_calls_in_window
    now = time.time()
    if now - _rate_window_start >= 60:
        _rate_window_start = now
        _rate_calls_in_window = 0
    _rate_calls_in_window += 1
    if _rate_calls_in_window >= _RATE_LIMIT_PER_MIN:
        sleep_for = 60 - (now - _rate_window_start) + 1
        if sleep_for > 0:
            logger.debug(f"Sniper detection rate limit: sleeping {sleep_for:.1f}s")
            time.sleep(sleep_for)
        _rate_window_start = time.time()
        _rate_calls_in_window = 1


def _get_known_sniper_wallets() -> list[dict]:
    """
    Gather known sniper wallets from all available sources.
    Returns list of {address, chain, source}.
    """
    wallets = []

    try:
        from config import settings

        # EVM alpha wallets
        for addr in getattr(settings, "SMART_MONEY_WALLETS", []):
            if addr:
                wallets.append({"address": addr, "chain": "evm", "source": "alpha_evm"})

        # Solana alpha wallets
        for addr in getattr(settings, "ALPHA_WALLETS_SOLANA", []):
            if addr:
                wallets.append({"address": addr, "chain": "solana", "source": "alpha_solana"})
    except ImportError:
        pass

    # Sniper leaderboard (if exists)
    try:
        lb_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "data", "dashboard", "sniper_leaderboard.json",
        )
        if os.path.exists(lb_path):
            with open(lb_path) as f:
                lb = json.loads(f.read())
            for w in lb:
                if w.get("is_active") and w.get("address"):
                    wallets.append({
                        "address": w["address"],
                        "chain": w.get("chain", "evm"),
                        "source": "leaderboard",
                    })
    except Exception:
        pass

    # Deduplicate by address
    seen = set()
    unique = []
    for w in wallets:
        addr_lower = w["address"].lower()
        if addr_lower not in seen:
            seen.add(addr_lower)
            unique.append(w)

    return unique[:MAX_WALLETS_PER_CYCLE]


def _fetch_recent_swaps(wallet_address: str, chain: str) -> list[dict]:
    """
    Fetch recent DEX swaps for a wallet from Moralis.
    Returns list of swap dicts with parsed fields.
    """
    cache_key = f"sniper_{wallet_address.lower()}_{chain}"
    if cache_key in _cache:
        ts, cached_swaps = _cache[cache_key]
        if time.time() - ts < _CACHE_TTL:
            return cached_swaps

    if not _get_api_key():
        return []

    # Solana wallets can't use EVM swap endpoint
    if chain == "solana":
        # Skip — Moralis /wallets/{address}/swaps is EVM-only
        return []

    # Try all EVM chains for this wallet
    all_swaps = []
    for chain_name, chain_hex in CHAIN_HEX.items():
        _rate_check()
        try:
            resp = get_session().get(
                f"{MORALIS_BASE_URL}/wallets/{wallet_address}/swaps",
                params={
                    "chain": chain_hex,
                    "order": "DESC",
                    "limit": "10",
                },
                headers=_headers(),
                timeout=8,
            )
            if resp.status_code in (400, 404, 402, 403):
                continue
            resp.raise_for_status()

            data = resp.json()
            result_items = data.get("result", data)
            items = result_items if isinstance(result_items, list) else []

            for swap in items:
                block_ts = swap.get("block_timestamp", "")
                if not block_ts:
                    continue

                # Parse timestamp
                try:
                    swap_time = datetime.fromisoformat(
                        block_ts.replace("Z", "+00:00")
                    )
                except (ValueError, TypeError):
                    continue

                age_seconds = (
                    datetime.now(timezone.utc) - swap_time
                ).total_seconds()

                # Only care about swaps in the convergence window
                if age_seconds > CONVERGENCE_WINDOW_SECONDS:
                    continue

                # Determine if this is a buy (native → token)
                token_bought = swap.get("token_bought_address", "")
                token_bought_symbol = swap.get("token_bought_symbol", "")
                token_sold_symbol = swap.get("token_sold_symbol", "")

                # Skip if buying native (ETH, WETH, etc.)
                native_symbols = {"ETH", "WETH", "WBNB", "BNB", "MATIC",
                                  "WMATIC", "AVAX", "WAVAX", "USDC", "USDT", "DAI"}
                if token_bought_symbol.upper() in native_symbols:
                    continue

                if token_bought:
                    all_swaps.append({
                        "token_address": token_bought.lower(),
                        "token_symbol": token_bought_symbol,
                        "chain": chain_name,
                        "swap_time": swap_time.isoformat(),
                        "age_seconds": age_seconds,
                        "wallet": wallet_address,
                        "usd_value": float(swap.get("token_bought_usd_value", 0) or 0),
                    })

        except Exception as e:
            logger.debug(f"Sniper swap fetch error for {wallet_address[:12]}... on {chain_name}: {e}")
            continue

    _cache[cache_key] = (time.time(), all_swaps)
    return all_swaps


def discover_sniper_convergence() -> list[dict]:
    """
    Main discovery function — called by gem_scanner.py every scan cycle.

    Scans known sniper wallets for recent buys (last 5 minutes) and
    identifies tokens where ≥3 distinct snipers are converging.

    Returns:
        List of dicts:
        [
            {
                "token_address": str,
                "chain": str,
                "symbol": str,
                "sniper_count": int,
                "sniper_wallets": [str, ...],
                "total_usd_value": float,
                "express_lane": bool,  # True when ≥ MIN_SNIPERS_FOR_FLAG
            }
        ]
    """
    if not _get_api_key():
        logger.debug("Sniper convergence: no Moralis API key, skipping")
        return []

    wallets = _get_known_sniper_wallets()
    if not wallets:
        logger.debug("Sniper convergence: no known sniper wallets configured")
        return []

    # Only process EVM wallets (Moralis swaps endpoint is EVM-only)
    evm_wallets = [w for w in wallets if w["chain"] != "solana"]
    if not evm_wallets:
        logger.debug("Sniper convergence: no EVM sniper wallets available")
        return []

    logger.info(f"🎯 Sniper convergence: scanning {len(evm_wallets)} wallets...")

    # Collect all recent buys
    token_buyers: dict[str, dict] = defaultdict(lambda: {
        "wallets": set(),
        "symbol": "",
        "chain": "",
        "total_usd": 0.0,
    })

    for wallet_info in evm_wallets:
        swaps = _fetch_recent_swaps(wallet_info["address"], wallet_info["chain"])
        for swap in swaps:
            key = f"{swap['token_address']}_{swap['chain']}"
            entry = token_buyers[key]
            entry["wallets"].add(swap["wallet"])
            entry["symbol"] = swap["token_symbol"]
            entry["chain"] = swap["chain"]
            entry["total_usd"] += swap["usd_value"]
            # Store token_address for extraction
            entry["token_address"] = swap["token_address"]

    # Filter for convergence
    results = []
    for _key, data in token_buyers.items():
        sniper_count = len(data["wallets"])
        if sniper_count >= MIN_SNIPERS_FOR_FLAG:
            results.append({
                "token_address": data["token_address"],
                "chain": data["chain"],
                "symbol": data["symbol"],
                "sniper_count": sniper_count,
                "sniper_wallets": list(data["wallets"]),
                "total_usd_value": data["total_usd"],
                "express_lane": True,
            })
            logger.info(
                f"🎯 SNIPER CONVERGENCE: {data['symbol']} on {data['chain']} — "
                f"{sniper_count} snipers, ${data['total_usd']:,.0f} total value"
            )

    # Sort by sniper count descending
    results.sort(key=lambda r: r["sniper_count"], reverse=True)

    if results:
        logger.info(
            f"🎯 Sniper convergence: {len(results)} tokens flagged "
            f"(top: {results[0]['symbol']} with {results[0]['sniper_count']} snipers)"
        )
    else:
        logger.debug("Sniper convergence: no convergence detected this cycle")

    return results


def get_convergence_stats() -> dict:
    """Return current stats for monitoring/dashboard."""
    return {
        "cached_wallets": len(_cache),
        "convergence_window_seconds": CONVERGENCE_WINDOW_SECONDS,
        "min_snipers_threshold": MIN_SNIPERS_FOR_FLAG,
        "max_wallets_per_cycle": MAX_WALLETS_PER_CYCLE,
    }
