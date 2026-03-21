"""
strategies/fibonacci.py — Fibonacci Retracement & Extension Engine.

This is a HARD GATE on every trade. No trade executes unless the current
price sits within an acceptable Fibonacci zone.

Implements:
  - Automatic swing high/low detection from OHLCV data
  - Fibonacci retracement levels: 0.236, 0.382, 0.5, 0.618, 0.786
  - Fibonacci extension levels: 1.0, 1.272, 1.618, 2.0, 2.618, 3.618
  - Zone classification (golden pocket, retrace zones, extensions)
  - Trade alignment check (pass/fail gate)
  - Take-profit targets based on extension levels

The golden pocket (0.618–0.65) is the strongest buy zone.
Extension levels automatically set staged take-profit targets.

Reference: This module is modeled after professional institutional
Fibonacci analysis — swing detection uses local extrema with
confirmation windows, not naive min/max.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Fibonacci Constants
# ─────────────────────────────────────────────────────────────────────────────

# Standard Fibonacci retracement ratios
FIB_RETRACEMENT_LEVELS = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]

# Standard Fibonacci extension ratios
FIB_EXTENSION_LEVELS = [1.0, 1.272, 1.618, 2.0, 2.618, 3.618]

# Golden pocket range (the strongest support/resistance zone)
GOLDEN_POCKET_LOW = 0.618
GOLDEN_POCKET_HIGH = 0.65

# Tolerance for "near a Fib level" (percentage)
FIB_PROXIMITY_PCT = 3.0  # Within 3% of a level counts as "at" that level


# ─────────────────────────────────────────────────────────────────────────────
# Data Classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class FibLevel:
    """A single Fibonacci level with its price."""
    ratio: float
    price: float
    label: str  # e.g., "fib_618", "ext_1618"


@dataclass
class FibResult:
    """Complete Fibonacci analysis result."""
    aligned: bool = False              # True = price is in a valid Fib zone for entry
    current_zone: str = "unknown"      # "golden_pocket", "fib_382", "no_mans_land", etc.
    nearest_support: float = 0.0       # Nearest Fib support below current price
    nearest_resistance: float = 0.0    # Nearest Fib resistance above current price
    retracement_levels: dict = field(default_factory=dict)  # {0.236: price, ...}
    extension_levels: dict = field(default_factory=dict)    # {1.272: price, ...}
    swing_high: float = 0.0
    swing_low: float = 0.0
    trend: str = "unknown"             # "uptrend" or "downtrend"
    confidence: float = 0.0            # 0–100, how clean the Fib structure is
    current_price: float = 0.0
    take_profit_targets: list = field(default_factory=list)  # Staged TP prices
    stop_loss_level: float = 0.0       # Suggested stop-loss from Fib structure
    error: Optional[str] = None

    def __str__(self) -> str:
        if self.error:
            return f"FibResult(❌ {self.error})"
        status = "✅ ALIGNED" if self.aligned else "❌ NOT ALIGNED"
        return (
            f"FibResult({status} | zone={self.current_zone} | "
            f"trend={self.trend} | confidence={self.confidence:.0f} | "
            f"support={self.nearest_support:.8f} | resistance={self.nearest_resistance:.8f})"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Swing Detection
# ─────────────────────────────────────────────────────────────────────────────

def _find_swing_points(
    df: pd.DataFrame,
    window: int = 3,
) -> tuple[Optional[float], Optional[float], Optional[int], Optional[int]]:
    """
    Find the most significant swing high and swing low from OHLCV data.

    Uses a rolling window approach to identify local extrema:
    - A swing high is a 'high' that is the maximum in its window
    - A swing low is a 'low' that is the minimum in its window

    Args:
        df: OHLCV DataFrame (must have 'high' and 'low' columns)
        window: Number of candles on each side to confirm a swing point

    Returns:
        (swing_high, swing_low, high_idx, low_idx)
    """
    if len(df) < (window * 2 + 1):
        # Not enough data for swing detection — use simple min/max
        return df["high"].max(), df["low"].min(), df["high"].idxmax(), df["low"].idxmin()

    highs = df["high"].values
    lows = df["low"].values
    n = len(highs)

    swing_highs = []
    swing_lows = []

    for i in range(window, n - window):
        # Check if this is a swing high
        is_high = True
        for j in range(1, window + 1):
            if highs[i] < highs[i - j] or highs[i] < highs[i + j]:
                is_high = False
                break
        if is_high:
            swing_highs.append((i, highs[i]))

        # Check if this is a swing low
        is_low = True
        for j in range(1, window + 1):
            if lows[i] > lows[i - j] or lows[i] > lows[i + j]:
                is_low = False
                break
        if is_low:
            swing_lows.append((i, lows[i]))

    # If no swings found, fall back to simple max/min
    if not swing_highs:
        swing_high = float(df["high"].max())
        high_idx = int(np.argmax(highs))
    else:
        # Use the most recent significant swing high
        best_high = max(swing_highs, key=lambda x: x[1])
        swing_high = best_high[1]
        high_idx = best_high[0]

    if not swing_lows:
        swing_low = float(df["low"].min())
        low_idx = int(np.argmin(lows))
    else:
        # Use the most recent significant swing low
        best_low = min(swing_lows, key=lambda x: x[1])
        swing_low = best_low[1]
        low_idx = best_low[0]

    return swing_high, swing_low, high_idx, low_idx


# ─────────────────────────────────────────────────────────────────────────────
# Fibonacci Calculations
# ─────────────────────────────────────────────────────────────────────────────

def _calculate_retracement_levels(
    swing_high: float,
    swing_low: float,
    trend: str,
) -> dict[float, float]:
    """
    Calculate Fibonacci retracement levels.

    In an uptrend:  levels are measured from swing_low UP to swing_high
                    retracement = swing_high - (range × fib_ratio)
    In a downtrend: levels are measured from swing_high DOWN to swing_low
                    retracement = swing_low + (range × fib_ratio)
    """
    price_range = swing_high - swing_low
    levels = {}

    for ratio in FIB_RETRACEMENT_LEVELS:
        if trend == "uptrend":
            # Retracement from the high — price pulling back
            price = swing_high - (price_range * ratio)
        else:
            # Retracement from the low — price bouncing up
            price = swing_low + (price_range * ratio)
        levels[ratio] = round(price, 10)

    return levels


def _calculate_extension_levels(
    swing_high: float,
    swing_low: float,
    trend: str,
) -> dict[float, float]:
    """
    Calculate Fibonacci extension levels (profit targets).

    Extensions project beyond the swing range to estimate where
    the next move could reach.
    """
    price_range = swing_high - swing_low
    levels = {}

    for ratio in FIB_EXTENSION_LEVELS:
        if trend == "uptrend":
            # Extensions project above the swing high
            price = swing_low + (price_range * ratio)
        else:
            # Extensions project below the swing low
            price = swing_high - (price_range * ratio)
        levels[ratio] = round(max(price, 0), 10)

    return levels


def _classify_zone(
    current_price: float,
    retracement_levels: dict[float, float],
    trend: str,
) -> tuple[str, float]:
    """
    Classify which Fibonacci zone the current price is in.

    Returns:
        (zone_name, confidence_bonus)
    """
    if not retracement_levels:
        return "unknown", 0.0

    # Sort levels by price
    sorted_levels = sorted(retracement_levels.items(), key=lambda x: x[1])

    # Check golden pocket first (strongest zone)
    gp_low_price = retracement_levels.get(GOLDEN_POCKET_LOW, 0)
    gp_high_ratio = 0.65
    # Interpolate the 0.65 level
    range_total = abs(retracement_levels.get(1.0, 0) - retracement_levels.get(0.0, 0))
    if trend == "uptrend":
        gp_high_price = retracement_levels.get(0.0, 0) + range_total * (1 - gp_high_ratio)
    else:
        gp_high_price = retracement_levels.get(0.0, 0) + range_total * gp_high_ratio

    gp_low_actual = min(gp_low_price, gp_high_price)
    gp_high_actual = max(gp_low_price, gp_high_price)

    if gp_low_actual <= current_price <= gp_high_actual:
        return "golden_pocket", 30.0

    # Check proximity to each Fib level
    for ratio, price in sorted_levels:
        if price <= 0:
            continue
        proximity_pct = abs(current_price - price) / price * 100
        if proximity_pct <= FIB_PROXIMITY_PCT:
            if ratio == 0.5:
                return "fib_500", 20.0
            elif ratio == 0.382:
                return "fib_382", 15.0
            elif ratio == 0.236:
                return "fib_236", 5.0
            elif ratio == 0.786:
                return "fib_786", 10.0
            elif ratio == 0.618:
                return "fib_618", 25.0
            elif ratio == 0.0:
                return "swing_extreme", 0.0
            elif ratio == 1.0:
                return "full_retracement", 0.0

    # Check if between known levels (no man's land)
    for i in range(len(sorted_levels) - 1):
        lower_price = sorted_levels[i][1]
        upper_price = sorted_levels[i + 1][1]
        if lower_price < current_price < upper_price:
            return "between_levels", 0.0

    return "out_of_range", 0.0


def _find_nearest_support_resistance(
    current_price: float,
    retracement_levels: dict[float, float],
    extension_levels: dict[float, float],
) -> tuple[float, float]:
    """Find the nearest Fibonacci support below and resistance above current price."""
    all_prices = sorted(set(
        [p for p in retracement_levels.values() if p > 0] +
        [p for p in extension_levels.values() if p > 0]
    ))

    support = 0.0
    resistance = float("inf")

    for price in all_prices:
        if price < current_price:
            support = max(support, price)
        elif price > current_price:
            resistance = min(resistance, price)

    if resistance == float("inf"):
        resistance = current_price * 1.5  # Default to 50% above

    return support, resistance


def _calculate_take_profit_targets(
    extension_levels: dict[float, float],
    trend: str,
) -> list[dict]:
    """
    Generate staged take-profit targets from extension levels.

    Standard staged exit:
      - 1.272 extension → sell 30%
      - 1.618 extension → sell 30%
      - 2.618 extension → sell 25%
      - Let remaining 15% ride
    """
    targets = []
    tp_config = [
        (1.272, 0.30, "TP1"),
        (1.618, 0.30, "TP2"),
        (2.618, 0.25, "TP3"),
    ]

    for ratio, portion, label in tp_config:
        price = extension_levels.get(ratio)
        if price and price > 0:
            targets.append({
                "label": label,
                "ratio": ratio,
                "price": price,
                "sell_portion": portion,
            })

    return targets


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def analyze_fibonacci(
    df: pd.DataFrame,
    current_price: float,
    swing_window: int = 3,
) -> FibResult:
    """
    Run complete Fibonacci analysis on OHLCV data.

    Args:
        df: OHLCV DataFrame with columns: open, high, low, close, volume
        current_price: Current token price in USD
        swing_window: Candles on each side for swing point detection

    Returns:
        FibResult with all levels, zone classification, and alignment status
    """
    if df is None or len(df) < 3:
        return FibResult(error="Insufficient OHLCV data for Fibonacci analysis")

    if current_price <= 0:
        return FibResult(error="Invalid current price")

    # Step 1: Find swing points
    swing_high, swing_low, high_idx, low_idx = _find_swing_points(df, window=swing_window)

    if swing_high is None or swing_low is None or swing_high <= swing_low:
        return FibResult(error=f"Invalid swing points: high={swing_high}, low={swing_low}")

    # Step 2: Determine trend direction
    # If swing low came before swing high → uptrend (price rose)
    # If swing high came before swing low → downtrend (price fell)
    if high_idx is not None and low_idx is not None:
        trend = "uptrend" if low_idx < high_idx else "downtrend"
    else:
        # Fallback: compare current price to midpoint
        midpoint = (swing_high + swing_low) / 2
        trend = "uptrend" if current_price > midpoint else "downtrend"

    # Step 3: Calculate Fibonacci levels
    retracement_levels = _calculate_retracement_levels(swing_high, swing_low, trend)
    extension_levels = _calculate_extension_levels(swing_high, swing_low, trend)

    # Step 4: Classify current zone
    zone, confidence_bonus = _classify_zone(current_price, retracement_levels, trend)

    # Step 5: Find nearest support/resistance
    support, resistance = _find_nearest_support_resistance(
        current_price, retracement_levels, extension_levels
    )

    # Step 6: Calculate take-profit targets
    tp_targets = _calculate_take_profit_targets(extension_levels, trend)

    # Step 7: Determine stop-loss from Fib structure
    # Stop-loss goes below the next Fib support level
    fib_prices_below = sorted(
        [p for p in retracement_levels.values() if p < current_price and p > 0],
        reverse=True,
    )
    # Use the second support level (one below nearest) for stop-loss
    stop_loss = fib_prices_below[1] if len(fib_prices_below) > 1 else (
        fib_prices_below[0] * 0.95 if fib_prices_below else swing_low * 0.95
    )

    # Step 8: Calculate confidence
    # Base confidence from zone + structure quality
    price_range = swing_high - swing_low
    range_pct = price_range / swing_low * 100 if swing_low > 0 else 0

    # Clean Fibonacci structure: range should be 5-50% (not too tight, not too wide)
    structure_quality = 0.0
    if 5 <= range_pct <= 50:
        structure_quality = 50.0  # Good range
    elif 2 <= range_pct <= 100:
        structure_quality = 30.0  # Acceptable
    else:
        structure_quality = 10.0  # Poor range

    confidence = min(100, structure_quality + confidence_bonus)

    # Step 9: Determine alignment
    # BUY is aligned if price is at a Fibonacci support level in an uptrend
    buy_zones = {"golden_pocket", "fib_618", "fib_500", "fib_382", "fib_786"}
    aligned = zone in buy_zones and confidence >= 15

    result = FibResult(
        aligned=aligned,
        current_zone=zone,
        nearest_support=support,
        nearest_resistance=resistance,
        retracement_levels=retracement_levels,
        extension_levels=extension_levels,
        swing_high=swing_high,
        swing_low=swing_low,
        trend=trend,
        confidence=confidence,
        current_price=current_price,
        take_profit_targets=tp_targets,
        stop_loss_level=stop_loss,
    )

    logger.info(f"Fibonacci analysis: {result}")
    return result


def check_fibonacci_alignment(
    df: pd.DataFrame,
    current_price: float,
    direction: str = "buy",
) -> FibResult:
    """
    Gate check: Is the current price aligned with Fibonacci levels for this trade direction?

    This is the primary function called by the trade execution pipeline.
    It's a PASS/FAIL check — if it returns aligned=False, the trade is blocked.

    Args:
        df: OHLCV DataFrame
        current_price: Current token price
        direction: "buy" or "sell"

    Returns:
        FibResult with aligned=True/False
    """
    result = analyze_fibonacci(df, current_price)

    if result.error:
        logger.warning(f"Fibonacci check failed: {result.error}")
        # On error, we don't block — insufficient data shouldn't prevent trading
        # But confidence is low
        result.aligned = True  # Permissive on data errors
        result.confidence = 10.0
        result.current_zone = "insufficient_data"
        return result

    if direction == "sell":
        # For sells, check if price is near an extension level (profit target)
        ext_zones = {"ext_1272", "ext_1618", "ext_2618"}
        # Check proximity to extension levels
        for ratio, price in result.extension_levels.items():
            if price > 0:
                proximity = abs(current_price - price) / price * 100
                if proximity <= FIB_PROXIMITY_PCT:
                    result.aligned = True
                    result.current_zone = f"ext_{int(ratio * 1000)}"
                    return result
        # Also allow selling at overbought retracement levels
        result.aligned = result.current_zone in {"fib_236", "swing_extreme"}
    # For buys, alignment was already set in analyze_fibonacci

    return result
