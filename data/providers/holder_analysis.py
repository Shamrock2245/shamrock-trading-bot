"""
data/providers/holder_analysis.py — On-chain holder concentration analysis.

Alternative to BubbleMaps (whose API is partner-only beta).
Uses DexScreener pair data + on-chain FDV/mcap ratios to estimate
holder concentration and distribution health.

No API key required — uses existing DexScreener data.
"""

import logging
import time
from typing import Optional

from data.providers.dexscreener import get_token_pairs

logger = logging.getLogger(__name__)

# ── In-memory cache ──────────────────────────────────────────────────────────
_holder_cache: dict[str, tuple[float, float]] = {}  # address -> (score, timestamp)
_CACHE_TTL = 1800  # 30 min


def analyze_holder_distribution(token_address: str, chain: str) -> dict:
    """
    Analyze holder distribution using DexScreener pair data.

    Metrics extracted:
        - buy/sell ratio (1h + 24h) → measure of accumulation vs distribution
        - unique buyer count vs seller count → holder growth signal
        - liquidity / market_cap ratio → LP concentration risk
        - fdv / market_cap ratio → dilution risk proxy

    Returns dict with analysis results.
    """
    try:
        pairs = get_token_pairs(token_address)
        if not pairs:
            return {"status": "no_data"}

        # Use the most liquid pair (first result)
        best_pair = pairs[0]
        txns = best_pair.get("txns", {})
        liquidity = best_pair.get("liquidity", {})
        mcap = float(best_pair.get("marketCap", 0) or 0)
        fdv = float(best_pair.get("fdv", 0) or 0)
        liq_usd = float(liquidity.get("usd", 0) or 0)

        # ── Buy/sell ratio analysis ──────────────────────────────────────
        buys_1h = int(txns.get("h1", {}).get("buys", 0) or 0)
        sells_1h = int(txns.get("h1", {}).get("sells", 0) or 0)
        buys_24h = int(txns.get("h24", {}).get("buys", 0) or 0)
        sells_24h = int(txns.get("h24", {}).get("sells", 0) or 0)

        total_txns_1h = buys_1h + sells_1h
        total_txns_24h = buys_24h + sells_24h

        # Buy/sell ratio (>1 = accumulation, <1 = distribution)
        buy_ratio_1h = buys_1h / max(sells_1h, 1)
        buy_ratio_24h = buys_24h / max(sells_24h, 1)

        # ── Liquidity concentration ──────────────────────────────────────
        # LP as % of mcap — high ratio means LP providers own large share
        lp_concentration = (liq_usd / mcap * 100) if mcap > 0 else 0

        # ── FDV/mcap ratio (dilution risk) ───────────────────────────────
        mcap_fdv_ratio = (mcap / fdv) if fdv > 0 else 1.0

        return {
            "status": "ok",
            "buys_1h": buys_1h,
            "sells_1h": sells_1h,
            "buy_ratio_1h": round(buy_ratio_1h, 2),
            "buys_24h": buys_24h,
            "sells_24h": sells_24h,
            "buy_ratio_24h": round(buy_ratio_24h, 2),
            "total_txns_24h": total_txns_24h,
            "lp_concentration_pct": round(lp_concentration, 2),
            "mcap_fdv_ratio": round(mcap_fdv_ratio, 4),
            "market_cap": mcap,
            "fdv": fdv,
            "liquidity_usd": liq_usd,
        }

    except Exception as e:
        logger.warning(f"Holder analysis failed for {token_address}: {e}")
        return {"status": "error", "error": str(e)}


def get_holder_score(token_address: str, chain: str) -> float:
    """
    Compute a 0–100 holder concentration score.

    Scoring logic (composite of multiple signals):

    1. Buy/sell ratio (40% weight):
       - ratio > 2.0 (strong accumulation) → 100
       - ratio 1.5–2.0 → 80
       - ratio 1.0–1.5 → 60
       - ratio 0.5–1.0 → 30
       - ratio < 0.5 (heavy selling) → 10

    2. Transaction count health (30% weight):
       - > 500 txns/24h → 100
       - > 200 txns/24h → 80
       - > 100 txns/24h → 60
       - > 50 txns/24h → 40
       - < 50 → 20 (thin, risky)

    3. LP concentration risk (30% weight):
       - LP < 10% of mcap → 100 (well distributed)
       - LP 10–25% → 70
       - LP 25–50% → 40
       - LP > 50% → 15 (concentrated — rug risk)
    """
    cache_key = f"{chain}:{token_address}".lower()

    # Check cache
    if cache_key in _holder_cache:
        score, cached_at = _holder_cache[cache_key]
        if (time.time() - cached_at) < _CACHE_TTL:
            return score

    analysis = analyze_holder_distribution(token_address, chain)

    if analysis.get("status") != "ok":
        score = 40.0  # Cautious neutral
        _holder_cache[cache_key] = (score, time.time())
        return score

    # ── 1. Buy/sell ratio score (40%) ────────────────────────────────────
    ratio_24h = analysis["buy_ratio_24h"]
    if ratio_24h > 2.0:
        ratio_score = 100.0
    elif ratio_24h > 1.5:
        ratio_score = 80.0
    elif ratio_24h > 1.0:
        ratio_score = 60.0
    elif ratio_24h > 0.5:
        ratio_score = 30.0
    else:
        ratio_score = 10.0

    # ── 2. Transaction count health (30%) ────────────────────────────────
    txns_24h = analysis["total_txns_24h"]
    if txns_24h > 500:
        txn_score = 100.0
    elif txns_24h > 200:
        txn_score = 80.0
    elif txns_24h > 100:
        txn_score = 60.0
    elif txns_24h > 50:
        txn_score = 40.0
    else:
        txn_score = 20.0

    # ── 3. LP concentration risk (30%) ───────────────────────────────────
    lp_pct = analysis["lp_concentration_pct"]
    if lp_pct < 10:
        lp_score = 100.0
    elif lp_pct < 25:
        lp_score = 70.0
    elif lp_pct < 50:
        lp_score = 40.0
    else:
        lp_score = 15.0

    # ── Composite ────────────────────────────────────────────────────────
    score = round(
        ratio_score * 0.40
        + txn_score * 0.30
        + lp_score * 0.30,
        2,
    )

    _holder_cache[cache_key] = (score, time.time())

    logger.info(
        f"HolderAnalysis: {token_address[:10]}… → score={score:.0f} "
        f"(buy_ratio={ratio_24h:.1f}, txns={txns_24h}, lp_conc={lp_pct:.1f}%)"
    )

    return score
