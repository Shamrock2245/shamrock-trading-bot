"""
strategies/volatility_sizer.py — ATR-Based Volatility-Adaptive Position Sizing

Calculates a position size multiplier based on current market volatility,
inspired by Freqtrade's custom_stake_amount() and the quant-trading repo's
VIX-based strategies. Core insight: smaller positions in choppy markets,
larger positions in smooth trends.

How it works:
  1. Fetches recent OHLCV candles (1h timeframe, last 24 candles)
  2. Calculates ATR(14) normalized by current price → atr_pct
  3. Calculates rolling realized volatility using log returns
  4. Detects Bollinger Band squeeze (breakout imminent)
  5. Returns a volatility_multiplier (0.5x–1.5x)

Volatility Zones:
  Ultra-high  (atr_pct > 15%)  → 0.50x (half size, protect capital)
  High        (atr_pct > 8%)   → 0.75x
  Normal      (atr_pct 3-8%)   → 1.00x (baseline)
  Low         (atr_pct < 3%)   → 1.25x (trend running smoothly)
  BB Squeeze                   → 1.50x (breakout imminent, press it)

Integration: called from offensive_guardrails.calculate_offensive_position_size()

Feature flag: VOLATILITY_SIZING_ENABLED (default: true — aligned with config/settings.py)
"""

from __future__ import annotations


import logging
import math
import os
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────
# Default changed from "false" to "true" to match config/settings.py VOLATILITY_SIZING_ENABLED default
VOLATILITY_SIZING_ENABLED = os.getenv("VOLATILITY_SIZING_ENABLED", "true").lower() == "true"

# ATR thresholds (as % of price)
ATR_ULTRA_HIGH_PCT = float(os.getenv("ATR_ULTRA_HIGH_PCT", "15.0"))
ATR_HIGH_PCT = float(os.getenv("ATR_HIGH_PCT", "8.0"))
ATR_LOW_PCT = float(os.getenv("ATR_LOW_PCT", "3.0"))

# Multipliers for each zone
VOL_MULT_ULTRA_HIGH = float(os.getenv("VOL_MULT_ULTRA_HIGH", "0.50"))
VOL_MULT_HIGH = float(os.getenv("VOL_MULT_HIGH", "0.75"))
VOL_MULT_NORMAL = float(os.getenv("VOL_MULT_NORMAL", "1.00"))
VOL_MULT_LOW = float(os.getenv("VOL_MULT_LOW", "1.25"))
VOL_MULT_SQUEEZE = float(os.getenv("VOL_MULT_SQUEEZE", "1.50"))

# BB Squeeze detection thresholds
BB_SQUEEZE_PERIOD = int(os.getenv("BB_SQUEEZE_PERIOD", "20"))
BB_SQUEEZE_RATIO = float(os.getenv("BB_SQUEEZE_RATIO", "0.03"))  # Width / price < 3% = squeeze

# Cache TTL (seconds) — avoid re-fetching on every position size calculation
_CACHE_TTL = 300  # 5 minutes
_cache: dict[str, tuple[float, float]] = {}  # key → (timestamp, multiplier)


# ─────────────────────────────────────────────────────────────────────────────
# Data model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class VolatilityResult:
    """Result of volatility analysis for a token."""
    atr_pct: float = 0.0           # ATR as % of current price
    realized_vol: float = 0.0      # 7-day realized vol (annualized)
    bb_squeeze: bool = False       # Bollinger Band squeeze detected
    volatility_zone: str = "normal"  # ultra_high, high, normal, low, squeeze
    multiplier: float = 1.0        # Position size multiplier


# ─────────────────────────────────────────────────────────────────────────────
# Core calculations
# ─────────────────────────────────────────────────────────────────────────────

def _calculate_atr(highs: list[float], lows: list[float], closes: list[float],
                   period: int = 14) -> float:
    """
    Calculate Average True Range (ATR) from OHLC data.
    ATR = EMA of True Range over `period` candles.
    """
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

    # EMA of true ranges
    k = 2 / (period + 1)
    atr = sum(true_ranges[:period]) / period  # SMA seed
    for tr in true_ranges[period:]:
        atr = tr * k + atr * (1 - k)

    return atr


def _calculate_realized_volatility(closes: list[float], window: int = 7) -> float:
    """
    Calculate realized volatility using log returns (annualized).

    Inspired by quant-trading's heikin_ashi.py approach — uses the
    standard deviation of log returns over the lookback window.
    """
    if len(closes) < window + 1:
        return 0.0

    log_returns = []
    for i in range(1, len(closes)):
        if closes[i - 1] > 0 and closes[i] > 0:
            log_returns.append(math.log(closes[i] / closes[i - 1]))

    if len(log_returns) < window:
        return 0.0

    # Use only the last `window` returns
    recent = log_returns[-window:]
    mean_ret = sum(recent) / len(recent)
    variance = sum((r - mean_ret) ** 2 for r in recent) / len(recent)
    daily_vol = math.sqrt(variance)

    # Annualize (crypto = 365 days, but we're using hourly candles)
    # 24 candles/day × 365 days → sqrt(8760) ≈ 93.6
    annualized = daily_vol * math.sqrt(24 * 365)
    return annualized


def _detect_bb_squeeze(closes: list[float], period: int = BB_SQUEEZE_PERIOD,
                        threshold: float = BB_SQUEEZE_RATIO) -> bool:
    """
    Detect Bollinger Band squeeze — when BB width / price < threshold.
    Squeeze = low volatility → imminent breakout.
    """
    if len(closes) < period:
        return False

    recent = closes[-period:]
    sma = sum(recent) / len(recent)
    if sma <= 0:
        return False

    # Standard deviation
    variance = sum((p - sma) ** 2 for p in recent) / len(recent)
    std = math.sqrt(variance)

    # BB width = 4 × std (upper - lower = 2×2×std)
    bb_width = 4 * std
    width_ratio = bb_width / sma

    return width_ratio < threshold


# ─────────────────────────────────────────────────────────────────────────────
# Main API
# ─────────────────────────────────────────────────────────────────────────────

def analyze_volatility(
    ohlcv: list[dict] | None = None,
    closes: list[float] | None = None,
    highs: list[float] | None = None,
    lows: list[float] | None = None,
) -> VolatilityResult:
    """
    Analyze current volatility and return sizing multiplier.

    Args:
        ohlcv: list of candle dicts with keys: open, high, low, close, volume
        OR
        closes, highs, lows: separate lists of OHLC data

    Returns:
        VolatilityResult with multiplier and analysis details.
    """
    result = VolatilityResult()

    # Extract price data
    if ohlcv:
        closes = [float(c.get("close", c.get("c", 0))) for c in ohlcv]
        highs = [float(c.get("high", c.get("h", 0))) for c in ohlcv]
        lows = [float(c.get("low", c.get("l", 0))) for c in ohlcv]

    if not closes or len(closes) < 15:
        logger.debug("Volatility sizer: insufficient candle data, returning 1.0x")
        return result

    current_price = closes[-1]
    if current_price <= 0:
        return result

    # ATR calculation
    if highs and lows:
        atr = _calculate_atr(highs, lows, closes, period=14)
        result.atr_pct = (atr / current_price) * 100
    else:
        # Fallback: estimate ATR from close-to-close ranges
        ranges = [abs(closes[i] - closes[i - 1]) for i in range(1, len(closes))]
        if ranges:
            result.atr_pct = (sum(ranges[-14:]) / min(14, len(ranges)) / current_price) * 100

    # Realized volatility
    result.realized_vol = _calculate_realized_volatility(closes, window=min(7, len(closes) - 1))

    # BB Squeeze detection
    result.bb_squeeze = _detect_bb_squeeze(closes)

    # Determine zone and multiplier
    if result.bb_squeeze and result.atr_pct < ATR_HIGH_PCT:
        result.volatility_zone = "squeeze"
        result.multiplier = VOL_MULT_SQUEEZE
    elif result.atr_pct > ATR_ULTRA_HIGH_PCT:
        result.volatility_zone = "ultra_high"
        result.multiplier = VOL_MULT_ULTRA_HIGH
    elif result.atr_pct > ATR_HIGH_PCT:
        result.volatility_zone = "high"
        result.multiplier = VOL_MULT_HIGH
    elif result.atr_pct < ATR_LOW_PCT:
        result.volatility_zone = "low"
        result.multiplier = VOL_MULT_LOW
    else:
        result.volatility_zone = "normal"
        result.multiplier = VOL_MULT_NORMAL

    logger.debug(
        f"Volatility analysis: ATR={result.atr_pct:.2f}% "
        f"realized_vol={result.realized_vol:.2f} "
        f"squeeze={result.bb_squeeze} "
        f"zone={result.volatility_zone} → {result.multiplier:.2f}x"
    )
    return result


def get_volatility_multiplier(
    token_address: str,
    chain: str,
    ohlcv: list[dict] | None = None,
    closes: list[float] | None = None,
    highs: list[float] | None = None,
    lows: list[float] | None = None,
) -> float:
    """
    Get the volatility-based position size multiplier for a token.
    Uses a 5-minute cache to avoid redundant calculations.

    Returns:
        float multiplier (0.5–1.5)
    """
    if not VOLATILITY_SIZING_ENABLED:
        return 1.0

    cache_key = f"{chain}:{token_address}"
    now = time.monotonic()

    # Check cache
    if cache_key in _cache:
        cached_at, cached_mult = _cache[cache_key]
        if now - cached_at < _CACHE_TTL:
            return cached_mult

    # Analyze
    result = analyze_volatility(ohlcv=ohlcv, closes=closes, highs=highs, lows=lows)

    # Cache result
    _cache[cache_key] = (now, result.multiplier)

    if result.multiplier != 1.0:
        logger.info(
            f"📊 Volatility sizing: {result.volatility_zone} "
            f"(ATR={result.atr_pct:.1f}%) → {result.multiplier:.2f}x position"
        )

    return result.multiplier
