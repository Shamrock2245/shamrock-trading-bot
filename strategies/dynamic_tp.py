"""
strategies/dynamic_tp.py — Dynamic ATR-Relative Take-Profit Calculator

Inspired by Freqtrade's custom_exit() and the quant-trading repo's
Monte Carlo approaches. Core insight: fixed TP multipliers (1.5x, 2.5x, 5x)
don't adapt to the token's actual volatility. A token with 2% daily ATR
needs wider TPs than one with 15% daily ATR.

How it works:
  1. Takes ATR, entry price, position age, and macro regime as inputs
  2. Calculates ATR-relative TP levels:
     - TP1: entry + 3×ATR (adapts to current volatility)
     - TP2: entry + 6×ATR
     - TP3: entry + 12×ATR
  3. In high-vol environments, TPs are naturally wider (bigger expected moves)
  4. In low-vol environments, TPs are naturally tighter (take what market gives)
  5. Estimates probability of reaching each TP based on recent price velocity
  6. Recommends early exit if velocity is too low to reach TP1

Probability estimation:
  - Uses recent candle velocity (close-to-close drift / ATR) to estimate
    whether the token has enough momentum to reach each TP level.
  - P(TP1) > 60% → standard execution
  - P(TP1) 30-60% → suggest tighter trailing stop
  - P(TP1) < 30% → early_exit_recommended = True

Feature flag: DYNAMIC_TP_ENABLED (default: false)
"""

from __future__ import annotations


import logging
import math
import os
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────
DYNAMIC_TP_ENABLED = os.getenv("DYNAMIC_TP_ENABLED", "false").lower() == "true"

# ATR multipliers for each TP level (in units of ATR)
TP1_ATR_MULT = float(os.getenv("TP1_ATR_MULT", "3.0"))
TP2_ATR_MULT = float(os.getenv("TP2_ATR_MULT", "6.0"))
TP3_ATR_MULT = float(os.getenv("TP3_ATR_MULT", "12.0"))

# Minimum TP gain (%) — even in low-vol, we need at least this gain
TP1_MIN_GAIN_PCT = float(os.getenv("TP1_MIN_GAIN_PCT", "20.0"))
TP2_MIN_GAIN_PCT = float(os.getenv("TP2_MIN_GAIN_PCT", "50.0"))
TP3_MIN_GAIN_PCT = float(os.getenv("TP3_MIN_GAIN_PCT", "100.0"))

# Maximum TP gain (%) — cap in ultra-high vol to avoid unrealistic targets
TP1_MAX_GAIN_PCT = float(os.getenv("TP1_MAX_GAIN_PCT", "150.0"))
TP2_MAX_GAIN_PCT = float(os.getenv("TP2_MAX_GAIN_PCT", "400.0"))
TP3_MAX_GAIN_PCT = float(os.getenv("TP3_MAX_GAIN_PCT", "1000.0"))

# Early exit: if P(TP1) < this threshold, recommend early exit
EARLY_EXIT_PROBABILITY_THRESHOLD = float(os.getenv("EARLY_EXIT_PROBABILITY_THRESHOLD", "0.30"))

# Velocity check: hours of flat price action before early exit flag
VELOCITY_STALL_HOURS = float(os.getenv("VELOCITY_STALL_HOURS", "4.0"))


# ─────────────────────────────────────────────────────────────────────────────
# Data model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DynamicTP:
    """Dynamic take-profit levels based on ATR."""
    # Price levels
    tp1_price: float = 0.0
    tp2_price: float = 0.0
    tp3_price: float = 0.0

    # Gain percentages (for logging / override fields)
    tp1_gain_pct: float = 50.0    # Default 50% gain (1.5x)
    tp2_gain_pct: float = 150.0   # Default 150% gain (2.5x)
    tp3_gain_pct: float = 400.0   # Default 400% gain (5x)

    # Probability estimates
    p_tp1: float = 0.5            # Estimated probability of reaching TP1
    p_tp2: float = 0.25           # Estimated probability of reaching TP2
    p_tp3: float = 0.10           # Estimated probability of reaching TP3

    # Recommendation
    early_exit_recommended: bool = False
    tighter_trail_recommended: bool = False
    recommended_trail_pct: float = 15.0  # Adjusted trailing stop %

    # Analysis
    atr_pct: float = 0.0          # ATR as % of entry price
    velocity_ratio: float = 1.0   # Recent drift / expected drift
    detail: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# ATR calculation (reusable, same as volatility_sizer)
# ─────────────────────────────────────────────────────────────────────────────

def _calculate_atr_from_ohlcv(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 14,
) -> float:
    """Calculate Average True Range (ATR) from OHLC data."""
    if len(closes) < period + 1:
        return 0.0

    true_ranges = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        true_ranges.append(tr)

    if len(true_ranges) < period:
        return sum(true_ranges) / len(true_ranges) if true_ranges else 0.0

    k = 2 / (period + 1)
    atr = sum(true_ranges[:period]) / period
    for tr in true_ranges[period:]:
        atr = tr * k + atr * (1 - k)
    return atr


# ─────────────────────────────────────────────────────────────────────────────
# Velocity estimation
# ─────────────────────────────────────────────────────────────────────────────

def _estimate_velocity(closes: list[float], atr: float, lookback: int = 6) -> float:
    """
    Estimate price velocity as a ratio of actual drift to expected drift.

    velocity_ratio > 1.0 → price is moving faster than average
    velocity_ratio < 0.5 → price is stalling (momentum dying)
    """
    if len(closes) < lookback + 1 or atr <= 0:
        return 1.0

    recent = closes[-lookback:]
    actual_drift = abs(recent[-1] - recent[0])  # Total price movement
    expected_drift = atr * math.sqrt(lookback)   # Expected random walk distance

    if expected_drift <= 0:
        return 1.0

    return actual_drift / expected_drift


def _estimate_tp_probability(
    velocity_ratio: float,
    tp_distance_atr: float,
    position_age_hours: float = 0,
) -> float:
    """
    Estimate probability of reaching a TP level given current velocity.

    Simple heuristic based on:
    - velocity_ratio: how fast price is moving vs expected
    - tp_distance_atr: how far TP is in ATR units
    - position_age_hours: older positions with low velocity → lower probability

    Returns probability 0.0–1.0
    """
    if tp_distance_atr <= 0:
        return 1.0

    # Base probability decreases with distance
    base_p = max(0.05, 1.0 / (1.0 + tp_distance_atr * 0.3))

    # Velocity adjustment
    vel_adj = min(2.0, velocity_ratio)  # Cap velocity boost
    adjusted_p = base_p * vel_adj

    # Age penalty: after 6 hours with low velocity, probability drops
    if position_age_hours > 6 and velocity_ratio < 0.5:
        age_penalty = max(0.3, 1.0 - (position_age_hours - 6) * 0.05)
        adjusted_p *= age_penalty

    return max(0.01, min(0.99, adjusted_p))


# ─────────────────────────────────────────────────────────────────────────────
# Main API
# ─────────────────────────────────────────────────────────────────────────────

def calculate_dynamic_tp(
    entry_price: float,
    closes: list[float] | None = None,
    highs: list[float] | None = None,
    lows: list[float] | None = None,
    position_age_hours: float = 0.0,
    macro_regime: str = "NEUTRAL",
) -> DynamicTP:
    """
    Calculate dynamic ATR-relative take-profit levels.

    Args:
        entry_price: position entry price
        closes: recent close prices (for ATR calculation)
        highs/lows: recent high/low prices
        position_age_hours: how long position has been open
        macro_regime: current macro regime ("BULL", "NEUTRAL", "BEAR")

    Returns:
        DynamicTP with ATR-adjusted price levels and probability estimates.
    """
    if not DYNAMIC_TP_ENABLED:
        return DynamicTP()

    result = DynamicTP()

    if not closes or len(closes) < 15 or entry_price <= 0:
        return result

    # Calculate ATR
    if highs and lows and len(highs) == len(closes) and len(lows) == len(closes):
        atr = _calculate_atr_from_ohlcv(highs, lows, closes, period=14)
    else:
        # Fallback: estimate ATR from close-to-close ranges
        ranges = [abs(closes[i] - closes[i - 1]) for i in range(1, len(closes))]
        atr = sum(ranges[-14:]) / min(14, len(ranges)) if ranges else 0.0

    if atr <= 0:
        return result

    result.atr_pct = (atr / entry_price) * 100

    # ── Regime adjustment for ATR multipliers ────────────────────────────────
    # Bull markets: slightly wider TPs (let runners run)
    # Bear markets: tighter TPs (take what you can get)
    regime_adj = 1.0
    if macro_regime.upper() == "BULL":
        regime_adj = 1.15  # 15% wider TPs in bull
    elif macro_regime.upper() in ("BEAR", "EXTREME_FEAR"):
        regime_adj = 0.75  # 25% tighter TPs in bear

    # ── Calculate ATR-relative TP prices ─────────────────────────────────────
    tp1_atr_dist = TP1_ATR_MULT * regime_adj
    tp2_atr_dist = TP2_ATR_MULT * regime_adj
    tp3_atr_dist = TP3_ATR_MULT * regime_adj

    tp1_raw_gain = (tp1_atr_dist * atr / entry_price) * 100
    tp2_raw_gain = (tp2_atr_dist * atr / entry_price) * 100
    tp3_raw_gain = (tp3_atr_dist * atr / entry_price) * 100

    # Clamp to min/max bounds
    result.tp1_gain_pct = max(TP1_MIN_GAIN_PCT, min(TP1_MAX_GAIN_PCT, tp1_raw_gain))
    result.tp2_gain_pct = max(TP2_MIN_GAIN_PCT, min(TP2_MAX_GAIN_PCT, tp2_raw_gain))
    result.tp3_gain_pct = max(TP3_MIN_GAIN_PCT, min(TP3_MAX_GAIN_PCT, tp3_raw_gain))

    # Calculate price levels
    result.tp1_price = entry_price * (1 + result.tp1_gain_pct / 100)
    result.tp2_price = entry_price * (1 + result.tp2_gain_pct / 100)
    result.tp3_price = entry_price * (1 + result.tp3_gain_pct / 100)

    # ── Velocity and probability estimation ──────────────────────────────────
    result.velocity_ratio = _estimate_velocity(closes, atr, lookback=6)

    result.p_tp1 = _estimate_tp_probability(result.velocity_ratio, tp1_atr_dist, position_age_hours)
    result.p_tp2 = _estimate_tp_probability(result.velocity_ratio, tp2_atr_dist, position_age_hours)
    result.p_tp3 = _estimate_tp_probability(result.velocity_ratio, tp3_atr_dist, position_age_hours)

    # ── Early exit and trailing stop recommendations ─────────────────────────
    if result.p_tp1 < EARLY_EXIT_PROBABILITY_THRESHOLD:
        result.early_exit_recommended = True
        result.detail = (
            f"P(TP1)={result.p_tp1:.0%} < {EARLY_EXIT_PROBABILITY_THRESHOLD:.0%} — "
            f"velocity_ratio={result.velocity_ratio:.2f}, "
            f"ATR={result.atr_pct:.1f}%, age={position_age_hours:.1f}h"
        )
    elif result.p_tp1 < 0.60:
        result.tighter_trail_recommended = True
        result.recommended_trail_pct = max(8.0, 15.0 * result.p_tp1)  # Scale trail with probability
        result.detail = (
            f"P(TP1)={result.p_tp1:.0%} — tighter trail recommended "
            f"({result.recommended_trail_pct:.0f}%)"
        )
    else:
        result.detail = f"P(TP1)={result.p_tp1:.0%} — standard execution"

    logger.info(
        f"📐 Dynamic TP: "
        f"ATR={result.atr_pct:.1f}% | "
        f"TP1={result.tp1_gain_pct:.0f}% (P={result.p_tp1:.0%}) | "
        f"TP2={result.tp2_gain_pct:.0f}% (P={result.p_tp2:.0%}) | "
        f"TP3={result.tp3_gain_pct:.0f}% (P={result.p_tp3:.0%}) | "
        f"vel={result.velocity_ratio:.2f} | "
        f"{'⚠️ EARLY EXIT' if result.early_exit_recommended else '✅ standard'}"
    )

    return result
