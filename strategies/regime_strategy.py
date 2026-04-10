"""
strategies/regime_strategy.py — Regime-Adaptive Strategy Selector

Inspired by Freqtrade's most profitable strategies and the quant-trading
repo's regime-based approaches. Core insight: the same indicator can be
a winning signal in a trending market and a losing signal in a ranging one.

How it works:
  1. Takes the current MacroRegime and ADX value as inputs
  2. Returns adjusted indicator weight multipliers for the signal engine
  3. In trending markets: boost trend-following signals (EMA, MACD, Fib)
  4. In ranging markets: boost mean-reversion signals (RSI, BB, VWAP)
  5. In bear markets: boost safety/volume signals, reduce all others

Regime Detection:
  - Trending: ADX > 25 AND macro BULL
  - Ranging:  ADX < 20 AND macro NEUTRAL
  - Bear:     macro BEAR or EXTREME_FEAR
  - Default:  macro NEUTRAL with moderate ADX → balanced weights

The weight multipliers are applied to the TA-29 blend step in signal_engine.py,
modifying the 60/40 blend between core TA and TA-29 scores.

Feature flag: REGIME_STRATEGY_ENABLED (default: false)
"""

from __future__ import annotations


import logging
import os
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────
REGIME_STRATEGY_ENABLED = os.getenv("REGIME_STRATEGY_ENABLED", "false").lower() == "true"

# ADX thresholds for regime classification
ADX_TRENDING_THRESHOLD = float(os.getenv("ADX_TRENDING_THRESHOLD", "25.0"))
ADX_RANGING_THRESHOLD = float(os.getenv("ADX_RANGING_THRESHOLD", "20.0"))


# ─────────────────────────────────────────────────────────────────────────────
# Data model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class RegimeWeights:
    """
    Multipliers for each score category in the signal engine.

    1.0 = no change (default).
    > 1.0 = boost this signal category.
    < 1.0 = reduce this signal category.
    """
    trend_mult: float = 1.0        # EMA, MACD, golden cross signals
    momentum_mult: float = 1.0     # RSI, BB, MFI signals
    volume_mult: float = 1.0       # Volume spike, OBV signals
    onchain_mult: float = 1.0      # Buy pressure, holder signals

    # Score blend ratios (replace static 0.60/0.40)
    core_ta_weight: float = 0.60   # Weight for core TA signals
    ta29_weight: float = 0.40      # Weight for 29-indicator blend

    regime_name: str = "balanced"  # For logging
    detail: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# Regime weight profiles
# ─────────────────────────────────────────────────────────────────────────────

def _trending_weights() -> RegimeWeights:
    """
    TRENDING regime (ADX > 25, BULL macro):
    - Trend-following dominates. EMAs and MACD are king.
    - RSI overbought signals cause premature exits → reduce momentum weight.
    - Volume confirmation gets a slight boost.
    """
    return RegimeWeights(
        trend_mult=1.40,        # Boost EMA, MACD, golden cross by 40%
        momentum_mult=0.70,     # Reduce RSI/BB sensitivity by 30%
        volume_mult=1.15,       # Slight volume boost for breakout confirmation
        onchain_mult=1.00,      # On-chain signals unchanged
        core_ta_weight=0.50,    # Give TA-29 slightly more weight (trend-confirmed)
        ta29_weight=0.50,
        regime_name="trending",
        detail="ADX>25 + BULL macro → trend-following dominates",
    )


def _ranging_weights() -> RegimeWeights:
    """
    RANGING regime (ADX < 20, NEUTRAL macro):
    - Mean-reversion dominates. RSI and Bollinger Bands are king.
    - EMA crossovers whipsaw constantly → reduce trend weight.
    - Volume spikes become more significant (breakout from range).
    """
    return RegimeWeights(
        trend_mult=0.65,        # Reduce EMA/MACD by 35% (whipsaw filter)
        momentum_mult=1.40,     # Boost RSI/BB by 40% (mean-reversion)
        volume_mult=1.30,       # Volume breakout from range is very significant
        onchain_mult=1.10,      # On-chain slightly more relevant
        core_ta_weight=0.70,    # Core TA (simpler) is more reliable in ranges
        ta29_weight=0.30,       # TA-29 has too many trend indicators for ranges
        regime_name="ranging",
        detail="ADX<20 + NEUTRAL macro → mean-reversion dominates",
    )


def _bear_weights() -> RegimeWeights:
    """
    BEAR regime (BEAR or EXTREME_FEAR macro):
    - Only extreme oversold + institutional buying deserves capital.
    - ALL signal weights reduced → only exceptional setups pass.
    - Smart money and volume signals boosted (institutional accumulation).
    """
    return RegimeWeights(
        trend_mult=0.60,        # Strong trend reduction (bear rallies are traps)
        momentum_mult=1.20,     # Boost RSI extreme oversold detection
        volume_mult=1.40,       # Volume confirmation critical (real vs dead cat bounce)
        onchain_mult=1.50,      # On-chain / smart money is KEY in bears
        core_ta_weight=0.55,    # Slightly favor core TA
        ta29_weight=0.45,
        regime_name="bear",
        detail="BEAR/EXTREME_FEAR macro → safety-first, only exceptional entries",
    )


def _balanced_weights() -> RegimeWeights:
    """Default balanced weights — no adjustment."""
    return RegimeWeights(
        regime_name="balanced",
        detail="no regime bias — standard weights",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Main API
# ─────────────────────────────────────────────────────────────────────────────

def get_regime_weights(
    macro_regime: str = "NEUTRAL",
    adx_value: float | None = None,
) -> RegimeWeights:
    """
    Get regime-adaptive indicator weight multipliers.

    Args:
        macro_regime: Current macro regime from macro_filter.py
                      ("BULL", "NEUTRAL", "BEAR", "EXTREME_FEAR")
        adx_value: Current ADX value from TA indicators (0–100).
                   None if unavailable.

    Returns:
        RegimeWeights with multipliers for each signal category.
    """
    if not REGIME_STRATEGY_ENABLED:
        return _balanced_weights()

    macro = macro_regime.upper()
    adx = adx_value if adx_value is not None else 22.0  # Assume neutral if unknown

    # Determine regime
    if macro in ("BEAR", "EXTREME_FEAR"):
        weights = _bear_weights()
    elif macro == "BULL" and adx >= ADX_TRENDING_THRESHOLD:
        weights = _trending_weights()
    elif macro == "NEUTRAL" and adx < ADX_RANGING_THRESHOLD:
        weights = _ranging_weights()
    elif macro == "BULL":
        # BULL but not strongly trending — mild trend bias
        weights = RegimeWeights(
            trend_mult=1.15,
            momentum_mult=0.90,
            volume_mult=1.10,
            onchain_mult=1.00,
            core_ta_weight=0.55,
            ta29_weight=0.45,
            regime_name="mild_bull",
            detail=f"BULL macro but ADX={adx:.0f}<{ADX_TRENDING_THRESHOLD} → mild trend bias",
        )
    else:
        weights = _balanced_weights()

    logger.info(
        f"📊 Regime strategy: {weights.regime_name} | "
        f"trend={weights.trend_mult:.2f}x momentum={weights.momentum_mult:.2f}x "
        f"volume={weights.volume_mult:.2f}x onchain={weights.onchain_mult:.2f}x | "
        f"blend={weights.core_ta_weight:.0%}/{weights.ta29_weight:.0%} | "
        f"{weights.detail}"
    )

    return weights
