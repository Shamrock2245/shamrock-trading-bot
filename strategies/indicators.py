"""
strategies/indicators.py — Technical Analysis Indicators.

Implements 10 professional-grade TA indicators using pandas-ta.
Each indicator returns a normalized score (0–100) and a signal label.

Trend Indicators:
  - EMA Crossover (9/21 fast, 50/200 slow)
  - MACD (12, 26, 9)
  - ADX (14-period)

Momentum Indicators:
  - RSI (14-period)
  - Stochastic RSI (14, 14, 3, 3)
  - Bollinger Bands (20, 2.0)
  - VWAP (session-based)

Volume Indicators:
  - OBV (On-Balance Volume)
  - Volume Spike Detection (3x 20-period average)
  - Accumulation/Distribution Line

All indicators gracefully degrade when pandas-ta is unavailable,
falling back to manual calculations for the most critical ones.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Try to import pandas-ta (requires git install)
try:
    import pandas_ta as ta
    HAS_PANDAS_TA = True
except ImportError:
    HAS_PANDAS_TA = False
    logger.warning(
        "pandas-ta not installed. Using fallback calculations. "
        "Install: pip install git+https://github.com/twopirllc/pandas-ta.git@development"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Data Classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class IndicatorResult:
    """Result from a single indicator calculation."""
    name: str
    score: float = 50.0        # 0–100 normalized score
    signal: str = "neutral"    # "bullish", "bearish", "neutral"
    value: Optional[float] = None
    detail: str = ""           # Human-readable detail

    def __str__(self) -> str:
        return f"{self.name}: {self.score:.0f} ({self.signal}) {self.detail}"


@dataclass
class TAResult:
    """Complete TA analysis — all indicators combined."""
    trend_indicators: list = field(default_factory=list)
    momentum_indicators: list = field(default_factory=list)
    volume_indicators: list = field(default_factory=list)

    # Category scores (0–100)
    trend_score: float = 50.0
    momentum_score: float = 50.0
    volume_score: float = 50.0

    # Individual indicator shortcuts
    rsi: Optional[float] = None
    macd_signal: str = "neutral"
    ema_signal: str = "neutral"
    bb_signal: str = "normal"
    adx_value: Optional[float] = None
    volume_spike: bool = False

    def __str__(self) -> str:
        return (
            f"TAResult(trend={self.trend_score:.0f}, momentum={self.momentum_score:.0f}, "
            f"volume={self.volume_score:.0f} | RSI={self.rsi} | MACD={self.macd_signal} | "
            f"EMA={self.ema_signal} | BB={self.bb_signal})"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Fallback Calculations (when pandas-ta is not available)
# ─────────────────────────────────────────────────────────────────────────────

def _manual_ema(series: pd.Series, period: int) -> pd.Series:
    """Calculate EMA manually."""
    return series.ewm(span=period, adjust=False).mean()


def _manual_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Calculate RSI using Wilder's smoothing method."""
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def _manual_macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    """Calculate MACD manually. Returns (macd_line, signal_line, histogram)."""
    ema_fast = _manual_ema(close, fast)
    ema_slow = _manual_ema(close, slow)
    macd_line = ema_fast - ema_slow
    signal_line = _manual_ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def _manual_bollinger(close: pd.Series, period: int = 20, std_dev: float = 2.0):
    """Calculate Bollinger Bands. Returns (upper, middle, lower, bandwidth)."""
    middle = close.rolling(window=period).mean()
    std = close.rolling(window=period).std()
    upper = middle + (std * std_dev)
    lower = middle - (std * std_dev)
    bandwidth = (upper - lower) / middle
    return upper, middle, lower, bandwidth


# ─────────────────────────────────────────────────────────────────────────────
# Trend Indicators
# ─────────────────────────────────────────────────────────────────────────────

def calculate_ema_crossover(df: pd.DataFrame) -> IndicatorResult:
    """
    EMA Crossover — Trend direction detection.

    Fast cross: 9 EMA crosses 21 EMA (short-term momentum)
    Slow cross: 50 EMA crosses 200 EMA (golden/death cross)

    Score: 0 = strong bearish, 50 = neutral, 100 = strong bullish
    """
    close = df["close"]

    if len(close) < 21:
        return IndicatorResult(name="EMA", detail="Insufficient data")

    ema_9 = _manual_ema(close, 9)
    ema_21 = _manual_ema(close, 21)

    # Fast cross signals
    current_fast = ema_9.iloc[-1] > ema_21.iloc[-1]
    prev_fast = ema_9.iloc[-2] > ema_21.iloc[-2] if len(close) > 2 else current_fast

    score = 50.0
    signal = "neutral"
    detail = ""

    if current_fast and not prev_fast:
        score = 85.0
        signal = "bullish"
        detail = "9/21 EMA golden cross (bullish crossover)"
    elif not current_fast and prev_fast:
        score = 15.0
        signal = "bearish"
        detail = "9/21 EMA death cross (bearish crossover)"
    elif current_fast:
        # EMA 9 above 21 — bullish trend in progress
        spread_pct = (ema_9.iloc[-1] - ema_21.iloc[-1]) / ema_21.iloc[-1] * 100
        score = min(80, 60 + spread_pct * 5)
        signal = "bullish"
        detail = f"9 EMA above 21 EMA (spread: {spread_pct:.2f}%)"
    else:
        spread_pct = (ema_21.iloc[-1] - ema_9.iloc[-1]) / ema_21.iloc[-1] * 100
        score = max(20, 40 - spread_pct * 5)
        signal = "bearish"
        detail = f"9 EMA below 21 EMA (spread: {spread_pct:.2f}%)"

    # Slow cross bonus (50/200) — if enough data
    if len(close) >= 200:
        ema_50 = _manual_ema(close, 50)
        ema_200 = _manual_ema(close, 200)
        if ema_50.iloc[-1] > ema_200.iloc[-1]:
            score = min(100, score + 10)
            detail += " | 50/200 golden cross active"
        else:
            score = max(0, score - 10)
            detail += " | 50/200 death cross active"

    ema_signal = "golden_cross" if signal == "bullish" else "death_cross" if signal == "bearish" else "neutral"

    return IndicatorResult(
        name="EMA",
        score=max(0, min(100, score)),
        signal=signal,
        value=ema_9.iloc[-1],
        detail=detail,
    )


def calculate_macd(df: pd.DataFrame) -> IndicatorResult:
    """
    MACD (12, 26, 9) — Trend momentum confirmation.

    Bullish: MACD line crosses above signal line, histogram positive
    Bearish: MACD line crosses below signal line, histogram negative
    """
    close = df["close"]

    if len(close) < 26:
        return IndicatorResult(name="MACD", detail="Insufficient data")

    if HAS_PANDAS_TA:
        macd_df = ta.macd(close, fast=12, slow=26, signal=9)
        if macd_df is not None and not macd_df.empty:
            macd_line = macd_df.iloc[:, 0]
            signal_line = macd_df.iloc[:, 2]
            histogram = macd_df.iloc[:, 1]
        else:
            macd_line, signal_line, histogram = _manual_macd(close)
    else:
        macd_line, signal_line, histogram = _manual_macd(close)

    current_hist = histogram.iloc[-1]
    prev_hist = histogram.iloc[-2] if len(histogram) > 1 else 0

    score = 50.0
    signal = "neutral"

    if current_hist > 0 and prev_hist <= 0:
        # Histogram just turned positive — strong bullish
        score = 85.0
        signal = "bullish"
        detail = "MACD histogram crossed positive (bullish momentum)"
    elif current_hist < 0 and prev_hist >= 0:
        # Histogram just turned negative — strong bearish
        score = 15.0
        signal = "bearish"
        detail = "MACD histogram crossed negative (bearish momentum)"
    elif current_hist > 0:
        # Positive and increasing
        if current_hist > prev_hist:
            score = 75.0
            detail = "MACD histogram positive and increasing"
        else:
            score = 60.0
            detail = "MACD histogram positive but weakening"
        signal = "bullish"
    elif current_hist < 0:
        if current_hist < prev_hist:
            score = 25.0
            detail = "MACD histogram negative and deepening"
        else:
            score = 40.0
            detail = "MACD histogram negative but recovering"
        signal = "bearish"
    else:
        detail = "MACD at zero line"

    return IndicatorResult(
        name="MACD",
        score=max(0, min(100, score)),
        signal=signal,
        value=float(current_hist),
        detail=detail,
    )


def calculate_adx(df: pd.DataFrame, period: int = 14) -> IndicatorResult:
    """
    ADX (Average Directional Index) — Trend strength filter.

    >25 = trending market, >40 = strong trend, <20 = ranging/choppy
    """
    if len(df) < period + 5:
        return IndicatorResult(name="ADX", detail="Insufficient data")

    if HAS_PANDAS_TA:
        adx_df = ta.adx(df["high"], df["low"], df["close"], length=period)
        if adx_df is not None and not adx_df.empty:
            adx_val = float(adx_df.iloc[-1, 0])
            plus_di = float(adx_df.iloc[-1, 1])
            minus_di = float(adx_df.iloc[-1, 2])
        else:
            adx_val = 20.0
            plus_di = minus_di = 0
    else:
        # Manual ADX calculation
        high = df["high"]
        low = df["low"]
        close = df["close"]
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()

        plus_dm = high.diff()
        minus_dm = -low.diff()
        plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
        minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)

        plus_di_s = 100 * (plus_dm.rolling(window=period).mean() / atr)
        minus_di_s = 100 * (minus_dm.rolling(window=period).mean() / atr)
        dx = 100 * abs(plus_di_s - minus_di_s) / (plus_di_s + minus_di_s).replace(0, np.nan)
        adx_series = dx.rolling(window=period).mean()
        adx_val = float(adx_series.iloc[-1]) if not adx_series.empty else 20.0
        plus_di = float(plus_di_s.iloc[-1]) if not plus_di_s.empty else 0
        minus_di = float(minus_di_s.iloc[-1]) if not minus_di_s.empty else 0

    # Score: strong trend = more reliable signals
    if adx_val >= 40:
        score = 90.0
        detail = f"ADX {adx_val:.1f} — STRONG trend"
    elif adx_val >= 25:
        score = 70.0
        detail = f"ADX {adx_val:.1f} — trending"
    elif adx_val >= 20:
        score = 50.0
        detail = f"ADX {adx_val:.1f} — weak trend"
    else:
        score = 30.0
        detail = f"ADX {adx_val:.1f} — ranging/choppy (avoid trend strategies)"

    signal = "bullish" if plus_di > minus_di else "bearish" if minus_di > plus_di else "neutral"
    detail += f" | +DI={plus_di:.1f} -DI={minus_di:.1f}"

    return IndicatorResult(
        name="ADX",
        score=max(0, min(100, score)),
        signal=signal,
        value=adx_val,
        detail=detail,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Momentum Indicators
# ─────────────────────────────────────────────────────────────────────────────

def calculate_rsi(df: pd.DataFrame, period: int = 14) -> IndicatorResult:
    """
    RSI (Relative Strength Index) — Overbought/Oversold detection.

    <30 = oversold (potential buy), >70 = overbought (potential sell)
    Includes divergence detection between price and RSI.
    """
    close = df["close"]

    if len(close) < period + 1:
        return IndicatorResult(name="RSI", detail="Insufficient data")

    if HAS_PANDAS_TA:
        rsi_series = ta.rsi(close, length=period)
        if rsi_series is not None and not rsi_series.empty:
            rsi_val = float(rsi_series.iloc[-1])
        else:
            rsi_val = float(_manual_rsi(close, period).iloc[-1])
    else:
        rsi_val = float(_manual_rsi(close, period).iloc[-1])

    if np.isnan(rsi_val):
        return IndicatorResult(name="RSI", detail="RSI calculation returned NaN")

    # Score mapping — oversold = high buy score, overbought = low buy score
    if rsi_val <= 20:
        score = 95.0
        signal = "bullish"
        detail = f"RSI {rsi_val:.1f} — EXTREME oversold (strong buy zone)"
    elif rsi_val <= 30:
        score = 85.0
        signal = "bullish"
        detail = f"RSI {rsi_val:.1f} — oversold (buy zone)"
    elif rsi_val <= 45:
        score = 65.0
        signal = "bullish"
        detail = f"RSI {rsi_val:.1f} — approaching oversold"
    elif rsi_val <= 55:
        score = 50.0
        signal = "neutral"
        detail = f"RSI {rsi_val:.1f} — neutral"
    elif rsi_val <= 70:
        score = 35.0
        signal = "bearish"
        detail = f"RSI {rsi_val:.1f} — approaching overbought"
    elif rsi_val <= 80:
        score = 15.0
        signal = "bearish"
        detail = f"RSI {rsi_val:.1f} — overbought (sell zone)"
    else:
        score = 5.0
        signal = "bearish"
        detail = f"RSI {rsi_val:.1f} — EXTREME overbought (strong sell zone)"

    return IndicatorResult(
        name="RSI",
        score=max(0, min(100, score)),
        signal=signal,
        value=rsi_val,
        detail=detail,
    )


def calculate_stoch_rsi(df: pd.DataFrame) -> IndicatorResult:
    """
    Stochastic RSI — Confirmation signal for RSI extremes.

    K crosses above D below 20 = buy signal
    K crosses below D above 80 = sell signal
    """
    close = df["close"]

    if len(close) < 20:
        return IndicatorResult(name="StochRSI", detail="Insufficient data")

    if HAS_PANDAS_TA:
        stoch = ta.stochrsi(close, length=14, rsi_length=14, k=3, d=3)
        if stoch is not None and not stoch.empty:
            k_val = float(stoch.iloc[-1, 0])
            d_val = float(stoch.iloc[-1, 1])
        else:
            # Fallback
            rsi = _manual_rsi(close, 14)
            k_val = float((rsi.iloc[-1] - rsi.rolling(14).min().iloc[-1]) /
                         (rsi.rolling(14).max().iloc[-1] - rsi.rolling(14).min().iloc[-1] + 1e-10) * 100)
            d_val = k_val  # Simplified
    else:
        rsi = _manual_rsi(close, 14)
        rsi_min = rsi.rolling(14).min()
        rsi_max = rsi.rolling(14).max()
        stoch_rsi = (rsi - rsi_min) / (rsi_max - rsi_min + 1e-10) * 100
        k_val = float(stoch_rsi.rolling(3).mean().iloc[-1]) if not stoch_rsi.empty else 50.0
        d_val = float(stoch_rsi.rolling(3).mean().rolling(3).mean().iloc[-1]) if not stoch_rsi.empty else 50.0

    if np.isnan(k_val):
        k_val = 50.0
    if np.isnan(d_val):
        d_val = 50.0

    score = 50.0
    signal = "neutral"

    if k_val < 20 and k_val > d_val:
        score = 90.0
        signal = "bullish"
        detail = f"StochRSI K={k_val:.0f} crossed above D={d_val:.0f} in oversold zone"
    elif k_val < 20:
        score = 75.0
        signal = "bullish"
        detail = f"StochRSI K={k_val:.0f} D={d_val:.0f} — oversold"
    elif k_val > 80 and k_val < d_val:
        score = 10.0
        signal = "bearish"
        detail = f"StochRSI K={k_val:.0f} crossed below D={d_val:.0f} in overbought zone"
    elif k_val > 80:
        score = 25.0
        signal = "bearish"
        detail = f"StochRSI K={k_val:.0f} D={d_val:.0f} — overbought"
    else:
        detail = f"StochRSI K={k_val:.0f} D={d_val:.0f} — neutral range"

    return IndicatorResult(
        name="StochRSI",
        score=max(0, min(100, score)),
        signal=signal,
        value=k_val,
        detail=detail,
    )


def calculate_bollinger_bands(df: pd.DataFrame) -> IndicatorResult:
    """
    Bollinger Bands (20, 2.0) — Volatility and mean reversion.

    Squeeze (bandwidth < threshold) = breakout imminent
    Price at lower band = potential buy
    Price at upper band = potential sell
    """
    close = df["close"]

    if len(close) < 20:
        return IndicatorResult(name="BB", detail="Insufficient data")

    upper, middle, lower, bandwidth = _manual_bollinger(close)

    current_price = close.iloc[-1]
    upper_val = upper.iloc[-1]
    lower_val = lower.iloc[-1]
    middle_val = middle.iloc[-1]
    bw = bandwidth.iloc[-1]

    if any(np.isnan(v) for v in [upper_val, lower_val, middle_val, bw]):
        return IndicatorResult(name="BB", detail="Bollinger calculation returned NaN")

    # Calculate %B (where price is within the bands)
    band_range = upper_val - lower_val
    pct_b = (current_price - lower_val) / band_range if band_range > 0 else 0.5

    # Squeeze detection
    avg_bw = bandwidth.rolling(20).mean().iloc[-1] if len(bandwidth) >= 40 else bw
    is_squeeze = bw < avg_bw * 0.5 if not np.isnan(avg_bw) and avg_bw > 0 else False

    score = 50.0
    signal = "neutral"
    bb_signal = "normal"

    if is_squeeze:
        score = 70.0  # Squeeze = breakout imminent, opportunity
        signal = "neutral"
        bb_signal = "squeeze"
        detail = f"BB SQUEEZE — bandwidth {bw:.4f} (breakout imminent)"
    elif pct_b <= 0.0:
        score = 85.0  # Price below lower band — oversold
        signal = "bullish"
        bb_signal = "oversold"
        detail = f"Price BELOW lower band (%B={pct_b:.2f})"
    elif pct_b <= 0.2:
        score = 75.0
        signal = "bullish"
        bb_signal = "near_lower"
        detail = f"Price near lower band (%B={pct_b:.2f})"
    elif pct_b >= 1.0:
        score = 15.0  # Price above upper band — overbought
        signal = "bearish"
        bb_signal = "overbought"
        detail = f"Price ABOVE upper band (%B={pct_b:.2f})"
    elif pct_b >= 0.8:
        score = 25.0
        signal = "bearish"
        bb_signal = "near_upper"
        detail = f"Price near upper band (%B={pct_b:.2f})"
    else:
        detail = f"Price within bands (%B={pct_b:.2f})"

    return IndicatorResult(
        name="BB",
        score=max(0, min(100, score)),
        signal=signal,
        value=pct_b,
        detail=detail,
    )


def calculate_vwap(df: pd.DataFrame) -> IndicatorResult:
    """
    VWAP (Volume-Weighted Average Price) — Institutional reference.

    Price below VWAP = undervalued relative to volume
    Price above VWAP = overvalued relative to volume
    """
    if len(df) < 5 or "volume" not in df.columns:
        return IndicatorResult(name="VWAP", detail="Insufficient data")

    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    vol = df["volume"].replace(0, np.nan)

    if vol.sum() == 0 or np.isnan(vol.sum()):
        return IndicatorResult(name="VWAP", detail="No volume data")

    cumulative_tp_vol = (typical_price * vol).cumsum()
    cumulative_vol = vol.cumsum()
    vwap = cumulative_tp_vol / cumulative_vol

    current_price = df["close"].iloc[-1]
    vwap_val = vwap.iloc[-1]

    if np.isnan(vwap_val) or vwap_val <= 0:
        return IndicatorResult(name="VWAP", detail="VWAP calculation error")

    deviation_pct = (current_price - vwap_val) / vwap_val * 100

    if deviation_pct < -5:
        score = 85.0
        signal = "bullish"
        detail = f"Price {abs(deviation_pct):.1f}% BELOW VWAP (undervalued)"
    elif deviation_pct < -2:
        score = 70.0
        signal = "bullish"
        detail = f"Price {abs(deviation_pct):.1f}% below VWAP"
    elif deviation_pct > 5:
        score = 15.0
        signal = "bearish"
        detail = f"Price {deviation_pct:.1f}% ABOVE VWAP (overvalued)"
    elif deviation_pct > 2:
        score = 30.0
        signal = "bearish"
        detail = f"Price {deviation_pct:.1f}% above VWAP"
    else:
        score = 50.0
        signal = "neutral"
        detail = f"Price at VWAP (deviation: {deviation_pct:.1f}%)"

    return IndicatorResult(
        name="VWAP",
        score=max(0, min(100, score)),
        signal=signal,
        value=vwap_val,
        detail=detail,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Volume Indicators
# ─────────────────────────────────────────────────────────────────────────────

def calculate_obv(df: pd.DataFrame) -> IndicatorResult:
    """
    OBV (On-Balance Volume) — Confirm price moves with volume flow.

    Rising OBV + rising price = confirmed trend (bullish)
    Rising OBV + falling price = accumulation (bullish divergence)
    Falling OBV + rising price = distribution (bearish divergence)
    """
    if len(df) < 10 or "volume" not in df.columns:
        return IndicatorResult(name="OBV", detail="Insufficient data")

    close = df["close"]
    volume = df["volume"]

    # Calculate OBV
    obv = pd.Series(0.0, index=df.index)
    for i in range(1, len(close)):
        if close.iloc[i] > close.iloc[i - 1]:
            obv.iloc[i] = obv.iloc[i - 1] + volume.iloc[i]
        elif close.iloc[i] < close.iloc[i - 1]:
            obv.iloc[i] = obv.iloc[i - 1] - volume.iloc[i]
        else:
            obv.iloc[i] = obv.iloc[i - 1]

    # Trend of OBV (using short EMA)
    obv_ema = _manual_ema(obv, 5)
    obv_trend = "rising" if obv_ema.iloc[-1] > obv_ema.iloc[-2] else "falling"
    price_trend = "rising" if close.iloc[-1] > close.iloc[-3] else "falling"

    score = 50.0
    signal = "neutral"

    if obv_trend == "rising" and price_trend == "rising":
        score = 80.0
        signal = "bullish"
        detail = "OBV rising + price rising — confirmed uptrend"
    elif obv_trend == "rising" and price_trend == "falling":
        score = 70.0
        signal = "bullish"
        detail = "OBV rising + price falling — BULLISH DIVERGENCE (accumulation)"
    elif obv_trend == "falling" and price_trend == "rising":
        score = 25.0
        signal = "bearish"
        detail = "OBV falling + price rising — BEARISH DIVERGENCE (distribution)"
    elif obv_trend == "falling" and price_trend == "falling":
        score = 20.0
        signal = "bearish"
        detail = "OBV falling + price falling — confirmed downtrend"
    else:
        detail = f"OBV trend: {obv_trend}, price trend: {price_trend}"

    return IndicatorResult(
        name="OBV",
        score=max(0, min(100, score)),
        signal=signal,
        value=float(obv.iloc[-1]),
        detail=detail,
    )


def calculate_volume_spike(df: pd.DataFrame, threshold: float = 3.0) -> IndicatorResult:
    """
    Volume Spike Detection — Identifies unusual volume activity.

    Volume > 3x the 20-period average = significant event.
    On a green candle = bullish institutional buying.
    On a red candle = bearish institutional selling.
    """
    if len(df) < 20 or "volume" not in df.columns:
        return IndicatorResult(name="VolSpike", detail="Insufficient data")

    volume = df["volume"]
    close = df["close"]

    avg_volume = volume.rolling(20).mean().iloc[-1]
    current_volume = volume.iloc[-1]

    if np.isnan(avg_volume) or avg_volume <= 0:
        return IndicatorResult(name="VolSpike", detail="No volume history")

    volume_ratio = current_volume / avg_volume
    is_green = close.iloc[-1] >= close.iloc[-2] if len(close) > 1 else True
    is_spike = volume_ratio >= threshold

    if is_spike and is_green:
        score = 90.0
        signal = "bullish"
        detail = f"🔥 VOLUME SPIKE {volume_ratio:.1f}x on GREEN candle (institutional buying)"
    elif is_spike and not is_green:
        score = 20.0
        signal = "bearish"
        detail = f"⚠️ VOLUME SPIKE {volume_ratio:.1f}x on RED candle (institutional selling)"
    elif volume_ratio >= 1.5 and is_green:
        score = 65.0
        signal = "bullish"
        detail = f"Elevated volume {volume_ratio:.1f}x on green candle"
    elif volume_ratio >= 1.5 and not is_green:
        score = 35.0
        signal = "bearish"
        detail = f"Elevated volume {volume_ratio:.1f}x on red candle"
    elif volume_ratio < 0.5:
        score = 40.0
        signal = "neutral"
        detail = f"Low volume {volume_ratio:.1f}x — low conviction"
    else:
        score = 50.0
        signal = "neutral"
        detail = f"Normal volume {volume_ratio:.1f}x average"

    return IndicatorResult(
        name="VolSpike",
        score=max(0, min(100, score)),
        signal=signal,
        value=volume_ratio,
        detail=detail,
    )


def calculate_ad_line(df: pd.DataFrame) -> IndicatorResult:
    """
    Accumulation/Distribution Line — Smart money flow tracking.

    Rising A/D = accumulation (smart money buying)
    Falling A/D = distribution (smart money selling)
    """
    if len(df) < 10 or "volume" not in df.columns:
        return IndicatorResult(name="A/D", detail="Insufficient data")

    high = df["high"]
    low = df["low"]
    close = df["close"]
    volume = df["volume"]

    # Money Flow Multiplier = [(Close - Low) - (High - Close)] / (High - Low)
    hl_range = high - low
    mfm = ((close - low) - (high - close)) / hl_range.replace(0, np.nan)
    mfm = mfm.fillna(0)

    # Money Flow Volume = MFM × Volume
    mfv = mfm * volume

    # A/D Line = cumulative sum of MFV
    ad = mfv.cumsum()

    # Trend detection
    ad_short = _manual_ema(ad, 5)
    ad_trend = "rising" if ad_short.iloc[-1] > ad_short.iloc[-3] else "falling"

    score = 50.0
    signal = "neutral"

    if ad_trend == "rising":
        score = 70.0
        signal = "bullish"
        detail = "A/D line rising — accumulation (smart money buying)"
    else:
        score = 30.0
        signal = "bearish"
        detail = "A/D line falling — distribution (smart money selling)"

    return IndicatorResult(
        name="A/D",
        score=max(0, min(100, score)),
        signal=signal,
        value=float(ad.iloc[-1]),
        detail=detail,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Master Analysis Function
# ─────────────────────────────────────────────────────────────────────────────

def run_all_indicators(df: pd.DataFrame) -> TAResult:
    """
    Run all 10 TA indicators and return aggregated results.

    Args:
        df: OHLCV DataFrame (DatetimeIndex, columns: open, high, low, close, volume)

    Returns:
        TAResult with category scores and individual indicator results
    """
    logger.info(f"Running TA indicators on {len(df)} candles...")

    result = TAResult()

    # ── Trend Indicators ──────────────────────────────────────────────────
    ema = calculate_ema_crossover(df)
    macd = calculate_macd(df)
    adx = calculate_adx(df)
    result.trend_indicators = [ema, macd, adx]
    result.ema_signal = ema.signal
    result.macd_signal = macd.signal
    result.adx_value = adx.value

    # Trend score = weighted average of trend indicators
    # ADX acts as a confidence multiplier rather than direction
    trend_direction = (ema.score * 0.45 + macd.score * 0.55)
    adx_multiplier = 1.0 + (adx.score - 50) / 200  # 0.75 to 1.25
    result.trend_score = max(0, min(100, trend_direction * adx_multiplier))

    # ── Momentum Indicators ───────────────────────────────────────────────
    rsi = calculate_rsi(df)
    stoch_rsi = calculate_stoch_rsi(df)
    bb = calculate_bollinger_bands(df)
    vwap = calculate_vwap(df)
    result.momentum_indicators = [rsi, stoch_rsi, bb, vwap]
    result.rsi = rsi.value
    result.bb_signal = bb.detail.split("—")[0].strip() if "—" in bb.detail else bb.signal

    # Momentum score = weighted average
    result.momentum_score = (
        rsi.score * 0.35 +
        stoch_rsi.score * 0.20 +
        bb.score * 0.25 +
        vwap.score * 0.20
    )

    # ── Volume Indicators ─────────────────────────────────────────────────
    obv = calculate_obv(df)
    vol_spike = calculate_volume_spike(df)
    ad = calculate_ad_line(df)
    result.volume_indicators = [obv, vol_spike, ad]
    result.volume_spike = vol_spike.value is not None and vol_spike.value >= 3.0

    # Volume score = weighted average
    result.volume_score = (
        obv.score * 0.35 +
        vol_spike.score * 0.35 +
        ad.score * 0.30
    )

    logger.info(f"TA complete: {result}")
    return result
