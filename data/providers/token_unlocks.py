"""
data/providers/token_unlocks.py — Token unlock / dilution risk analysis.

Alternative to paid Token Unlocks APIs (Messari, CryptoRank, Coinglass).
Uses FDV/mcap ratio from DexScreener pair data and DefiLlama as a proxy
for upcoming token dilution risk.

No API key required.

Logic: A large gap between FDV and mcap means a significant portion of
tokens are not yet circulating — either locked, vesting, or scheduled
for future unlock. The wider the gap, the higher the dilution risk.
"""

import logging
import time
from typing import Optional

from data.providers.dexscreener import get_token_pairs

logger = logging.getLogger(__name__)

# ── In-memory cache ──────────────────────────────────────────────────────────
_unlock_cache: dict[str, tuple[float, float]] = {}  # address -> (score, timestamp)
_CACHE_TTL = 1800  # 30 min


def get_dilution_metrics(token_address: str, chain: str) -> dict:
    """
    Get dilution risk metrics from DexScreener pair data.

    Returns:
        mcap: current market cap (circulating supply × price)
        fdv: fully diluted valuation (total supply × price)
        mcap_fdv_ratio: mcap/fdv (1.0 = fully circulating, 0.1 = 90% locked)
        circulating_pct: percentage of tokens currently in circulation
    """
    try:
        pairs = get_token_pairs(token_address)
        if not pairs:
            return {"status": "no_data"}

        best_pair = pairs[0]
        mcap = float(best_pair.get("marketCap", 0) or 0)
        fdv = float(best_pair.get("fdv", 0) or 0)

        if fdv <= 0:
            return {"status": "no_fdv"}

        # If mcap is 0 but fdv exists, token hasn't launched / no price data
        if mcap <= 0:
            return {"status": "no_mcap"}

        ratio = min(mcap / fdv, 1.0)
        circulating_pct = ratio * 100

        return {
            "status": "ok",
            "mcap": mcap,
            "fdv": fdv,
            "mcap_fdv_ratio": round(ratio, 4),
            "circulating_pct": round(circulating_pct, 2),
        }

    except Exception as e:
        logger.warning(f"Dilution metrics failed for {token_address}: {e}")
        return {"status": "error", "error": str(e)}


def get_unlock_risk_score(token_address: str, chain: str) -> float:
    """
    Compute a 0–100 unlock/dilution risk score.

    Based on mcap / fdv ratio (higher = less dilution risk):
        Ratio > 90%  (most tokens circulating) → 100
        Ratio 70–90% → 80
        Ratio 50–70% → 60
        Ratio 30–50% → 40
        Ratio < 30%  (heavy dilution coming)  → 15
        Unknown      → 50 (neutral)

    For micro-cap meme coins, mcap ≈ fdv (no vesting), so they score high.
    For VC-backed tokens with vesting, this catches dilution risk.
    """
    cache_key = f"{chain}:{token_address}".lower()

    # Check cache
    if cache_key in _unlock_cache:
        score, cached_at = _unlock_cache[cache_key]
        if (time.time() - cached_at) < _CACHE_TTL:
            return score

    metrics = get_dilution_metrics(token_address, chain)

    if metrics.get("status") != "ok":
        score = 50.0  # Neutral — can't determine
        _unlock_cache[cache_key] = (score, time.time())
        return score

    ratio = metrics["mcap_fdv_ratio"]
    circulating = metrics["circulating_pct"]

    if ratio > 0.90:
        score = 100.0
    elif ratio > 0.70:
        score = 80.0
    elif ratio > 0.50:
        score = 60.0
    elif ratio > 0.30:
        score = 40.0
    else:
        score = 15.0

    _unlock_cache[cache_key] = (score, time.time())

    logger.info(
        f"UnlockRisk: {token_address[:10]}… → score={score:.0f} "
        f"(circulating={circulating:.1f}%, mcap/fdv={ratio:.3f})"
    )

    return score
