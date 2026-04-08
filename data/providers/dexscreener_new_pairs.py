"""
data/providers/dexscreener_new_pairs.py — DexScreener New Pair Creation Feed.

Discovers brand-new trading pairs on Base and Solana created in the last
10 minutes. These are the earliest possible entries — before social buzz,
before boosting, before any other scanner can find them.

Strategy: Fetch latest token profiles from DexScreener, then get pair data
and filter by `pairCreatedAt` timestamp. Only return pairs that are:
  - On Base or Solana
  - Created within the last 10 minutes
  - Have at least $5,000 liquidity (lower floor for ultra-early entry)
  - Have non-zero volume (not dead on arrival)

Data source: DexScreener GET /token-profiles/latest/v1 + /latest/dex/tokens/{address}
Rate: 60 req/min (profiles), 300 req/min (token pairs)
Cache: 2 minutes (fast refresh to catch new pairs)

Usage:
    from data.providers.dexscreener_new_pairs import discover_new_pairs
    pairs = discover_new_pairs()
    # Returns list of extract_gem_signals()-format dicts
"""

import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────
NEW_PAIR_MAX_AGE_MINUTES = 10     # Only pairs created within last 10 minutes
NEW_PAIR_MIN_LIQUIDITY_USD = 5000  # Lower floor for ultra-early entry
TARGET_CHAINS = {"base", "solana"}  # Only scan these chains for new pairs

# ─────────────────────────────────────────────────────────────────────────────
# Cache — 2 minute TTL for fast refresh
# ─────────────────────────────────────────────────────────────────────────────
_cache: dict[str, tuple[float, list]] = {}
_CACHE_TTL = 120  # 2 minutes


def discover_new_pairs() -> list[dict]:
    """
    Main discovery function — called by gem_scanner.py every scan cycle.

    Fetches the latest token profiles from DexScreener, gets pair data for
    each, and filters for brand-new pairs on Base and Solana.

    Returns:
        List of dicts in extract_gem_signals() format, ready for
        _signals_to_token() and _score_token() in the scanner.
        Each dict also includes:
            - source: "new_pair_snipe"
            - pair_age_minutes: float
    """
    cache_key = "new_pairs_discovery"
    if cache_key in _cache:
        ts, cached = _cache[cache_key]
        if time.time() - ts < _CACHE_TTL:
            logger.debug(f"New pairs [cached]: {len(cached)} pairs")
            return cached

    try:
        from data.providers.dexscreener import (
            get_latest_token_profiles,
            get_token_pairs,
            extract_gem_signals,
        )
    except ImportError as e:
        logger.warning(f"New pairs discovery: DexScreener import failed: {e}")
        return []

    now_ms = time.time() * 1000  # DexScreener uses millisecond timestamps
    max_age_ms = NEW_PAIR_MAX_AGE_MINUTES * 60 * 1000
    results = []
    seen_addresses = set()

    # ── Step 1: Fetch latest token profiles ───────────────────────────────
    try:
        profiles = get_latest_token_profiles()
    except Exception as e:
        logger.warning(f"New pairs: failed to fetch profiles: {e}")
        profiles = []

    logger.debug(f"New pairs: scanning {len(profiles)} profiles for ultra-fresh pairs")

    for profile in profiles:
        token_addr = profile.get("tokenAddress", "")
        chain_id = profile.get("chainId", "")

        # Only target chains
        if chain_id.lower() not in TARGET_CHAINS:
            continue

        if not token_addr or token_addr.lower() in seen_addresses:
            continue

        # ── Step 2: Get pair data for this token ───────────────────────────
        try:
            pairs = get_token_pairs(token_addr) or []
        except Exception:
            continue

        for pair in pairs:
            pair_chain = pair.get("chainId", "").lower()
            if pair_chain not in TARGET_CHAINS:
                continue

            # Check creation time
            created_at = pair.get("pairCreatedAt")
            if not created_at:
                continue

            age_ms = now_ms - created_at
            age_minutes = age_ms / (1000 * 60)

            # Only ultra-fresh pairs
            if age_minutes > NEW_PAIR_MAX_AGE_MINUTES:
                continue

            # Minimum liquidity check (lower floor)
            liquidity_usd = float(pair.get("liquidity", {}).get("usd", 0) or 0)
            if liquidity_usd < NEW_PAIR_MIN_LIQUIDITY_USD:
                continue

            # Must have some volume (not dead on arrival)
            volume_5m = float(pair.get("volume", {}).get("m5", 0) or 0)
            volume_1h = float(pair.get("volume", {}).get("h1", 0) or 0)
            if volume_5m <= 0 and volume_1h <= 0:
                continue

            # Extract signals in standard format
            signals = extract_gem_signals(pair)
            signals["source"] = "new_pair_snipe"
            signals["pair_age_minutes"] = round(age_minutes, 1)
            signals["is_boosted"] = True   # Treat as boosted for scoring
            signals["boost_amount"] = 60   # Moderate boost for new pair discovery

            results.append(signals)
            seen_addresses.add(token_addr.lower())

            logger.info(
                f"🆕 NEW PAIR: {signals.get('base_token_symbol', '???')} "
                f"on {pair_chain} — {age_minutes:.1f}m old, "
                f"liq=${liquidity_usd:,.0f}, vol_5m=${volume_5m:,.0f}"
            )
            break  # Use first (most liquid) pair only

    # ── Step 3: Also check latest boosts for new pairs ────────────────────
    # Boosted tokens that are also brand new = highest conviction
    try:
        from data.providers.dexscreener import get_latest_boosts
        boosts = get_latest_boosts()
        for boost in boosts:
            token_addr = boost.get("tokenAddress", "")
            chain_id = boost.get("chainId", "")
            if chain_id.lower() not in TARGET_CHAINS:
                continue
            if not token_addr or token_addr.lower() in seen_addresses:
                continue

            try:
                pairs = get_token_pairs(token_addr) or []
            except Exception:
                continue

            for pair in pairs:
                pair_chain = pair.get("chainId", "").lower()
                if pair_chain not in TARGET_CHAINS:
                    continue

                created_at = pair.get("pairCreatedAt")
                if not created_at:
                    continue

                age_ms = now_ms - created_at
                age_minutes = age_ms / (1000 * 60)

                if age_minutes > NEW_PAIR_MAX_AGE_MINUTES:
                    continue

                liquidity_usd = float(pair.get("liquidity", {}).get("usd", 0) or 0)
                if liquidity_usd < NEW_PAIR_MIN_LIQUIDITY_USD:
                    continue

                signals = extract_gem_signals(pair)
                signals["source"] = "new_pair_snipe"
                signals["pair_age_minutes"] = round(age_minutes, 1)
                signals["is_boosted"] = True
                boost_amt = int(boost.get("amount", 0) or 0)
                signals["boost_amount"] = max(100, boost_amt)  # Boosted new pair = strong

                results.append(signals)
                seen_addresses.add(token_addr.lower())

                logger.info(
                    f"🆕🔥 NEW BOOSTED PAIR: {signals.get('base_token_symbol', '???')} "
                    f"on {pair_chain} — {age_minutes:.1f}m old, "
                    f"boost={boost_amt}, liq=${liquidity_usd:,.0f}"
                )
                break

    except Exception as e:
        logger.debug(f"New pairs boost scan error: {e}")

    _cache[cache_key] = (time.time(), results)

    if results:
        logger.info(
            f"🆕 New pairs: {len(results)} ultra-fresh pairs found "
            f"(Base + Solana, ≤{NEW_PAIR_MAX_AGE_MINUTES}m old)"
        )
    else:
        logger.debug(f"New pairs: no pairs younger than {NEW_PAIR_MAX_AGE_MINUTES}m found")

    return results


def get_new_pairs_stats() -> dict:
    """Return current stats for monitoring/dashboard."""
    cached = _cache.get("new_pairs_discovery")
    cached_count = len(cached[1]) if cached else 0
    return {
        "cached_pairs": cached_count,
        "max_age_minutes": NEW_PAIR_MAX_AGE_MINUTES,
        "min_liquidity_usd": NEW_PAIR_MIN_LIQUIDITY_USD,
        "target_chains": list(TARGET_CHAINS),
        "cache_ttl_seconds": _CACHE_TTL,
    }
