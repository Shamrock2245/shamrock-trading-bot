"""
strategies/indicators.py — 29-Indicator Technical Analysis Arsenal.

Full coverage per crypto-ta-analyzer spec. Each indicator returns a
normalized score (0–100) and a signal label via IndicatorResult.

Core Indicators (weight 1.0):
  RSI, MACD, BB, OBV, Ichimoku, EMA, SMA, MFI, KDJ, SAR

Strong Indicators (weight 0.75):
  DEMA, MESA, CCI, AROON, APO

Supporting Indicators (weight 0.5):
  ADX, DMI, CMO, KAMA, Momentum, PPO, ROC, TRIMA, TRIX, T3,
  WMA, VWAP, ATR Signal, CAD

Features:
  - Divergence detection (RSI, MACD, OBV)
  - Regime detection (trending vs ranging via ADX)
  - 7-tier signal system (STRONG_BUY → STRONG_SELL)

All indicators gracefully degrade when pandas-ta is unavailable,
falling back to manual calculations.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Insufficient data fallback score — mildly bullish bias for new tokens
# that lack price history. 50 = dead neutral (blocks all micro-cap gems),
# 55 = slight tailwind (still requires strong on-chain signals to qualify).
INSUFFICIENT_DATA_SCORE = 55.0

# Try to import pandas-ta (requires git install)
# Catches both ImportError and RuntimeError (numba caching fails in Docker)
try:
    import pandas_ta as ta
    HAS_PANDAS_TA = True
except Exception:
    HAS_PANDAS_TA = False
    logger.warning(
        "pandas-ta not available. Using fallback calculations. "
        "This is normal in Docker — manual indicators are production-ready."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Data Classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class IndicatorResult:
    """Result from a single indicator calculation."""
    name: str
    score: float = 50.0        # 0–100 normalized score (50=neutral, 55=insufficient data bias)
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
        return IndicatorResult(name="EMA", score=INSUFFICIENT_DATA_SCORE, detail="Insufficient data")

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
        return IndicatorResult(name="MACD", score=INSUFFICIENT_DATA_SCORE, detail="Insufficient data")

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
        return IndicatorResult(name="ADX", score=INSUFFICIENT_DATA_SCORE, detail="Insufficient data")

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
        return IndicatorResult(name="RSI", score=INSUFFICIENT_DATA_SCORE, detail="Insufficient data")

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
        return IndicatorResult(name="StochRSI", score=INSUFFICIENT_DATA_SCORE, detail="Insufficient data")

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
        return IndicatorResult(name="BB", score=INSUFFICIENT_DATA_SCORE, detail="Insufficient data")

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
        return IndicatorResult(name="VWAP", score=INSUFFICIENT_DATA_SCORE, detail="Insufficient data")

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
        return IndicatorResult(name="OBV", score=INSUFFICIENT_DATA_SCORE, detail="Insufficient data")

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
        return IndicatorResult(name="VolSpike", score=INSUFFICIENT_DATA_SCORE, detail="Insufficient data")

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
        return IndicatorResult(name="A/D", score=INSUFFICIENT_DATA_SCORE, detail="Insufficient data")

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
# CORE Indicators (weight 1.0) — 5 New
# ─────────────────────────────────────────────────────────────────────────────

def calculate_ichimoku(df: pd.DataFrame) -> IndicatorResult:
    """
    Ichimoku Cloud — Crypto-optimized (10/30/60).

    Bullish: price above cloud, tenkan > kijun, future cloud is green
    Bearish: price below cloud, tenkan < kijun, future cloud is red
    """
    close = df["close"]
    high = df["high"]
    low = df["low"]

    if len(close) < 60:
        return IndicatorResult(name="ICHIMOKU", score=INSUFFICIENT_DATA_SCORE, detail="Insufficient data")

    # Crypto-optimized periods (10/30/60 instead of 9/26/52)
    tenkan = (high.rolling(10).max() + low.rolling(10).min()) / 2  # Conversion line
    kijun = (high.rolling(30).max() + low.rolling(30).min()) / 2   # Base line
    senkou_a = (tenkan + kijun) / 2                                 # Leading Span A
    senkou_b = (high.rolling(60).max() + low.rolling(60).min()) / 2 # Leading Span B

    price = close.iloc[-1]
    cloud_top = max(senkou_a.iloc[-1], senkou_b.iloc[-1])
    cloud_bottom = min(senkou_a.iloc[-1], senkou_b.iloc[-1])
    tk = tenkan.iloc[-1]
    kj = kijun.iloc[-1]

    score = 50.0
    signal = "neutral"

    # Price vs cloud
    if price > cloud_top:
        score += 20
    elif price < cloud_bottom:
        score -= 20

    # Tenkan vs Kijun
    if tk > kj:
        score += 15
    elif tk < kj:
        score -= 15

    # Future cloud color (senkou A vs B)
    if senkou_a.iloc[-1] > senkou_b.iloc[-1]:
        score += 10
    else:
        score -= 10

    # Cloud thickness as confidence
    cloud_pct = abs(cloud_top - cloud_bottom) / price * 100 if price > 0 else 0
    if cloud_pct > 5:
        score += 5 if price > cloud_top else -5

    score = max(0, min(100, score))
    signal = "bullish" if score > 55 else "bearish" if score < 45 else "neutral"
    detail = f"Ichimoku: price {'above' if price > cloud_top else 'below' if price < cloud_bottom else 'in'} cloud, TK {'>' if tk > kj else '<'} KJ"

    return IndicatorResult(name="ICHIMOKU", score=score, signal=signal, value=price, detail=detail)


def calculate_sma_crossover(df: pd.DataFrame) -> IndicatorResult:
    """
    SMA Crossover — 10/30 fast, 50/200 slow.

    Simple moving average crossovers. Slower than EMA but less noise.
    """
    close = df["close"]

    if len(close) < 30:
        return IndicatorResult(name="SMA", score=INSUFFICIENT_DATA_SCORE, detail="Insufficient data")

    sma_10 = close.rolling(10).mean()
    sma_30 = close.rolling(30).mean()

    current_above = sma_10.iloc[-1] > sma_30.iloc[-1]
    prev_above = sma_10.iloc[-2] > sma_30.iloc[-2] if len(close) > 2 else current_above

    score = 50.0
    signal = "neutral"

    if current_above and not prev_above:
        score = 85.0
        signal = "bullish"
        detail = "SMA 10/30 golden cross"
    elif not current_above and prev_above:
        score = 15.0
        signal = "bearish"
        detail = "SMA 10/30 death cross"
    elif current_above:
        spread = (sma_10.iloc[-1] - sma_30.iloc[-1]) / sma_30.iloc[-1] * 100
        score = min(80, 60 + spread * 4)
        signal = "bullish"
        detail = f"SMA 10 above 30 (spread: {spread:.2f}%)"
    else:
        spread = (sma_30.iloc[-1] - sma_10.iloc[-1]) / sma_30.iloc[-1] * 100
        score = max(20, 40 - spread * 4)
        signal = "bearish"
        detail = f"SMA 10 below 30 (spread: {spread:.2f}%)"

    return IndicatorResult(name="SMA", score=max(0, min(100, score)), signal=signal, detail=detail)


def calculate_mfi(df: pd.DataFrame, period: int = 14) -> IndicatorResult:
    """
    MFI (Money Flow Index) — Volume-weighted RSI.

    <20 = oversold (buy), >80 = overbought (sell).
    More reliable than RSI because it incorporates volume.
    """
    if len(df) < period + 1 or "volume" not in df.columns:
        return IndicatorResult(name="MFI", score=INSUFFICIENT_DATA_SCORE, detail="Insufficient data")

    if HAS_PANDAS_TA:
        mfi_series = ta.mfi(df["high"], df["low"], df["close"], df["volume"], length=period)
        if mfi_series is not None and not mfi_series.empty:
            mfi_val = float(mfi_series.iloc[-1])
        else:
            mfi_val = _manual_mfi(df, period)
    else:
        mfi_val = _manual_mfi(df, period)

    if np.isnan(mfi_val):
        return IndicatorResult(name="MFI", detail="MFI returned NaN")

    if mfi_val <= 20:
        score, signal = 90.0, "bullish"
        detail = f"MFI {mfi_val:.1f} — OVERSOLD with volume confirmation"
    elif mfi_val <= 35:
        score, signal = 70.0, "bullish"
        detail = f"MFI {mfi_val:.1f} — approaching oversold"
    elif mfi_val >= 80:
        score, signal = 10.0, "bearish"
        detail = f"MFI {mfi_val:.1f} — OVERBOUGHT with volume confirmation"
    elif mfi_val >= 65:
        score, signal = 30.0, "bearish"
        detail = f"MFI {mfi_val:.1f} — approaching overbought"
    else:
        score, signal = 50.0, "neutral"
        detail = f"MFI {mfi_val:.1f} — neutral"

    return IndicatorResult(name="MFI", score=score, signal=signal, value=mfi_val, detail=detail)


def _manual_mfi(df: pd.DataFrame, period: int = 14) -> float:
    """Manual MFI (Money Flow Index) calculation."""
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    money_flow = typical_price * df["volume"]
    tp_diff = typical_price.diff()
    positive_flow = money_flow.where(tp_diff > 0, 0).rolling(period).sum()
    negative_flow = money_flow.where(tp_diff <= 0, 0).rolling(period).sum()
    mfr = positive_flow / negative_flow.replace(0, np.nan)
    mfi = 100 - (100 / (1 + mfr))
    return float(mfi.iloc[-1])


def calculate_kdj(df: pd.DataFrame) -> IndicatorResult:
    """
    KDJ (Stochastic with J-line) — Overbought/oversold with momentum.

    J = 3K - 2D. J > 100 = extreme overbought, J < 0 = extreme oversold.
    More responsive than standard Stochastic in fast crypto markets.
    """
    if len(df) < 14:
        return IndicatorResult(name="KDJ", score=INSUFFICIENT_DATA_SCORE, detail="Insufficient data")

    high = df["high"]
    low = df["low"]
    close = df["close"]

    lowest_low = low.rolling(9).min()
    highest_high = high.rolling(9).max()
    rsv = (close - lowest_low) / (highest_high - lowest_low + 1e-10) * 100

    k = rsv.ewm(com=2, adjust=False).mean()
    d = k.ewm(com=2, adjust=False).mean()
    j = 3 * k - 2 * d

    k_val = float(k.iloc[-1])
    d_val = float(d.iloc[-1])
    j_val = float(j.iloc[-1])

    if j_val < 0 and k_val > d_val:
        score, signal = 90.0, "bullish"
        detail = f"KDJ J={j_val:.0f} extreme oversold + K>D crossover"
    elif j_val < 20:
        score, signal = 75.0, "bullish"
        detail = f"KDJ J={j_val:.0f} K={k_val:.0f} D={d_val:.0f} — oversold"
    elif j_val > 100 and k_val < d_val:
        score, signal = 10.0, "bearish"
        detail = f"KDJ J={j_val:.0f} extreme overbought + K<D cross"
    elif j_val > 80:
        score, signal = 25.0, "bearish"
        detail = f"KDJ J={j_val:.0f} K={k_val:.0f} D={d_val:.0f} — overbought"
    elif k_val > d_val:
        score, signal = 65.0, "bullish"
        detail = f"KDJ K={k_val:.0f} > D={d_val:.0f} — bullish momentum"
    else:
        score, signal = 40.0, "neutral"
        detail = f"KDJ K={k_val:.0f} D={d_val:.0f} J={j_val:.0f}"

    return IndicatorResult(name="KDJ", score=score, signal=signal, value=j_val, detail=detail)


def calculate_sar(df: pd.DataFrame) -> IndicatorResult:
    """
    Parabolic SAR — Trend reversal detection.

    SAR below price = uptrend, SAR above price = downtrend.
    SAR flip = trend reversal signal.
    """
    if len(df) < 14:
        return IndicatorResult(name="SAR", score=INSUFFICIENT_DATA_SCORE, detail="Insufficient data")

    if HAS_PANDAS_TA:
        sar = ta.psar(df["high"], df["low"], df["close"])
        if sar is not None and not sar.empty:
            # pandas-ta returns columns like PSARl_0.02_0.2, PSARs_0.02_0.2
            long_col = [c for c in sar.columns if "PSARl" in c]
            short_col = [c for c in sar.columns if "PSARs" in c]
            if long_col and not np.isnan(sar[long_col[0]].iloc[-1]):
                sar_val = float(sar[long_col[0]].iloc[-1])
                in_uptrend = True
            elif short_col and not np.isnan(sar[short_col[0]].iloc[-1]):
                sar_val = float(sar[short_col[0]].iloc[-1])
                in_uptrend = False
            else:
                return _manual_sar(df)
        else:
            return _manual_sar(df)
    else:
        return _manual_sar(df)

    price = float(df["close"].iloc[-1])

    if in_uptrend:
        distance_pct = (price - sar_val) / price * 100 if price > 0 else 0
        score = min(85, 60 + distance_pct * 3)
        signal = "bullish"
        detail = f"SAR BELOW price ({distance_pct:.1f}% cushion) — uptrend"
    else:
        distance_pct = (sar_val - price) / price * 100 if price > 0 else 0
        score = max(15, 40 - distance_pct * 3)
        signal = "bearish"
        detail = f"SAR ABOVE price ({distance_pct:.1f}%) — downtrend"

    return IndicatorResult(name="SAR", score=max(0, min(100, score)), signal=signal, value=sar_val, detail=detail)


def _manual_sar(df: pd.DataFrame) -> IndicatorResult:
    """Simplified SAR using price vs trailing high/low."""
    close = df["close"]
    high = df["high"]
    low = df["low"]
    price = float(close.iloc[-1])

    # Approximate SAR with adaptive trailing stop
    recent_high = float(high.rolling(5).max().iloc[-1])
    recent_low = float(low.rolling(5).min().iloc[-1])
    mid = (recent_high + recent_low) / 2

    if price > mid:
        score = 65.0
        signal = "bullish"
        detail = f"Price above midpoint ({mid:.6f}) — uptrend bias"
    else:
        score = 35.0
        signal = "bearish"
        detail = f"Price below midpoint ({mid:.6f}) — downtrend bias"

    return IndicatorResult(name="SAR", score=score, signal=signal, value=mid, detail=detail)


# ─────────────────────────────────────────────────────────────────────────────
# STRONG Indicators (weight 0.75) — 5 New
# ─────────────────────────────────────────────────────────────────────────────

def calculate_dema(df: pd.DataFrame, period: int = 21) -> IndicatorResult:
    """DEMA (Double Exponential MA) — Reduced lag moving average."""
    close = df["close"]
    if len(close) < period * 2:
        return IndicatorResult(name="DEMA", score=INSUFFICIENT_DATA_SCORE, detail="Insufficient data")

    ema1 = _manual_ema(close, period)
    ema2 = _manual_ema(ema1, period)
    dema = 2 * ema1 - ema2
    price = close.iloc[-1]
    dema_val = dema.iloc[-1]
    dev_pct = (price - dema_val) / dema_val * 100 if dema_val != 0 else 0

    if dev_pct > 3:
        score, signal = 70.0, "bullish"
        detail = f"Price {dev_pct:.1f}% above DEMA — strong uptrend"
    elif dev_pct > 0:
        score, signal = 60.0, "bullish"
        detail = f"Price {dev_pct:.1f}% above DEMA"
    elif dev_pct > -3:
        score, signal = 40.0, "bearish"
        detail = f"Price {abs(dev_pct):.1f}% below DEMA"
    else:
        score, signal = 25.0, "bearish"
        detail = f"Price {abs(dev_pct):.1f}% below DEMA — strong downtrend"

    return IndicatorResult(name="DEMA", score=score, signal=signal, value=float(dema_val), detail=detail)


def calculate_mesa(df: pd.DataFrame) -> IndicatorResult:
    """MESA Adaptive MA (Ehlers) — Phase/trend detection via Hilbert Transform."""
    close = df["close"]
    if len(close) < 32:
        return IndicatorResult(name="MESA", score=INSUFFICIENT_DATA_SCORE, detail="Insufficient data")

    # Simplified MESA: compare fast adaptive EMA to slow
    fast = _manual_ema(close, 5)
    slow = _manual_ema(close, 21)
    mama = fast.iloc[-1]
    fama = slow.iloc[-1]

    if mama > fama:
        diff_pct = (mama - fama) / fama * 100 if fama != 0 else 0
        score = min(85, 60 + diff_pct * 5)
        signal = "bullish"
        detail = f"MESA MAMA > FAMA ({diff_pct:.2f}%) — bullish phase"
    else:
        diff_pct = (fama - mama) / fama * 100 if fama != 0 else 0
        score = max(15, 40 - diff_pct * 5)
        signal = "bearish"
        detail = f"MESA MAMA < FAMA ({diff_pct:.2f}%) — bearish phase"

    return IndicatorResult(name="MESA", score=max(0, min(100, score)), signal=signal, detail=detail)


def calculate_cci(df: pd.DataFrame, period: int = 20) -> IndicatorResult:
    """CCI (Commodity Channel Index) — Cyclical trend identification."""
    if len(df) < period + 5:
        return IndicatorResult(name="CCI", score=INSUFFICIENT_DATA_SCORE, detail="Insufficient data")

    tp = (df["high"] + df["low"] + df["close"]) / 3
    sma_tp = tp.rolling(period).mean()
    mad = tp.rolling(period).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
    cci = (tp - sma_tp) / (0.015 * mad)
    cci_val = float(cci.iloc[-1])

    if np.isnan(cci_val):
        return IndicatorResult(name="CCI", detail="CCI returned NaN")

    if cci_val > 200:
        score, signal = 15.0, "bearish"
        detail = f"CCI {cci_val:.0f} — extreme overbought"
    elif cci_val > 100:
        score, signal = 30.0, "bearish"
        detail = f"CCI {cci_val:.0f} — overbought"
    elif cci_val < -200:
        score, signal = 85.0, "bullish"
        detail = f"CCI {cci_val:.0f} — extreme oversold"
    elif cci_val < -100:
        score, signal = 70.0, "bullish"
        detail = f"CCI {cci_val:.0f} — oversold"
    else:
        score, signal = 50.0, "neutral"
        detail = f"CCI {cci_val:.0f} — neutral range"

    return IndicatorResult(name="CCI", score=score, signal=signal, value=cci_val, detail=detail)


def calculate_aroon(df: pd.DataFrame, period: int = 25) -> IndicatorResult:
    """AROON — Trend timing indicator. Detects new trends early."""
    if len(df) < period + 1:
        return IndicatorResult(name="AROON", score=INSUFFICIENT_DATA_SCORE, detail="Insufficient data")

    high = df["high"]
    low = df["low"]
    aroon_up = ((period - (period - high.rolling(period + 1).apply(lambda x: x.argmax(), raw=True))) / period) * 100
    aroon_down = ((period - (period - low.rolling(period + 1).apply(lambda x: x.argmin(), raw=True))) / period) * 100

    up_val = float(aroon_up.iloc[-1])
    down_val = float(aroon_down.iloc[-1])

    if np.isnan(up_val) or np.isnan(down_val):
        return IndicatorResult(name="AROON", detail="AROON returned NaN")

    oscillator = up_val - down_val

    if oscillator > 50:
        score, signal = 80.0, "bullish"
        detail = f"AROON Up={up_val:.0f} Down={down_val:.0f} — strong uptrend"
    elif oscillator > 0:
        score, signal = 60.0, "bullish"
        detail = f"AROON Up={up_val:.0f} Down={down_val:.0f} — mild uptrend"
    elif oscillator < -50:
        score, signal = 20.0, "bearish"
        detail = f"AROON Up={up_val:.0f} Down={down_val:.0f} — strong downtrend"
    elif oscillator < 0:
        score, signal = 40.0, "bearish"
        detail = f"AROON Up={up_val:.0f} Down={down_val:.0f} — mild downtrend"
    else:
        score, signal = 50.0, "neutral"
        detail = f"AROON Up={up_val:.0f} Down={down_val:.0f} — consolidation"

    return IndicatorResult(name="AROON", score=score, signal=signal, value=oscillator, detail=detail)


def calculate_apo(df: pd.DataFrame) -> IndicatorResult:
    """APO (Absolute Price Oscillator) — Trend strength via EMA difference."""
    close = df["close"]
    if len(close) < 26:
        return IndicatorResult(name="APO", score=INSUFFICIENT_DATA_SCORE, detail="Insufficient data")

    ema_fast = _manual_ema(close, 12)
    ema_slow = _manual_ema(close, 26)
    apo = ema_fast - ema_slow
    apo_val = float(apo.iloc[-1])
    prev_apo = float(apo.iloc[-2]) if len(apo) > 1 else 0

    if apo_val > 0 and prev_apo <= 0:
        score, signal = 80.0, "bullish"
        detail = f"APO crossed positive ({apo_val:.4f}) — bullish"
    elif apo_val > 0:
        score, signal = 65.0, "bullish"
        detail = f"APO positive ({apo_val:.4f})"
    elif apo_val < 0 and prev_apo >= 0:
        score, signal = 20.0, "bearish"
        detail = f"APO crossed negative ({apo_val:.4f}) — bearish"
    elif apo_val < 0:
        score, signal = 35.0, "bearish"
        detail = f"APO negative ({apo_val:.4f})"
    else:
        score, signal = 50.0, "neutral"
        detail = "APO at zero"

    return IndicatorResult(name="APO", score=score, signal=signal, value=apo_val, detail=detail)


# ─────────────────────────────────────────────────────────────────────────────
# SUPPORTING Indicators (weight 0.5) — 11 New
# ─────────────────────────────────────────────────────────────────────────────

def calculate_cmo(df: pd.DataFrame, period: int = 14) -> IndicatorResult:
    """CMO (Chande Momentum Oscillator) — Modified RSI (-100 to +100)."""
    close = df["close"]
    if len(close) < period + 1:
        return IndicatorResult(name="CMO", score=INSUFFICIENT_DATA_SCORE, detail="Insufficient data")

    diff = close.diff()
    gains = diff.where(diff > 0, 0).rolling(period).sum()
    losses = (-diff.where(diff < 0, 0)).rolling(period).sum()
    cmo = ((gains - losses) / (gains + losses + 1e-10)) * 100
    cmo_val = float(cmo.iloc[-1])

    score = 50 + cmo_val / 4  # Map -100..100 to 25..75
    signal = "bullish" if cmo_val > 10 else "bearish" if cmo_val < -10 else "neutral"
    return IndicatorResult(name="CMO", score=max(0, min(100, score)), signal=signal, value=cmo_val,
                           detail=f"CMO {cmo_val:.1f}")


def calculate_kama(df: pd.DataFrame, period: int = 10) -> IndicatorResult:
    """KAMA (Kaufman Adaptive MA) — Volatility-adjusted moving average."""
    close = df["close"]
    if len(close) < period + 10:
        return IndicatorResult(name="KAMA", score=INSUFFICIENT_DATA_SCORE, detail="Insufficient data")

    # Efficiency ratio
    direction = abs(close - close.shift(period))
    volatility = close.diff().abs().rolling(period).sum()
    er = direction / (volatility + 1e-10)

    fast_sc = 2 / (2 + 1)
    slow_sc = 2 / (30 + 1)
    sc = (er * (fast_sc - slow_sc) + slow_sc) ** 2

    kama = pd.Series(index=close.index, dtype=float)
    kama.iloc[period - 1] = close.iloc[period - 1]
    for i in range(period, len(close)):
        kama.iloc[i] = kama.iloc[i - 1] + sc.iloc[i] * (close.iloc[i] - kama.iloc[i - 1])

    price = close.iloc[-1]
    kama_val = kama.iloc[-1]
    if np.isnan(kama_val):
        return IndicatorResult(name="KAMA", detail="KAMA returned NaN")

    dev_pct = (price - kama_val) / kama_val * 100 if kama_val != 0 else 0
    score = 50 + dev_pct * 5
    signal = "bullish" if dev_pct > 0.5 else "bearish" if dev_pct < -0.5 else "neutral"
    return IndicatorResult(name="KAMA", score=max(0, min(100, score)), signal=signal, value=float(kama_val),
                           detail=f"KAMA dev {dev_pct:.2f}%")


def calculate_momentum(df: pd.DataFrame, period: int = 10) -> IndicatorResult:
    """Momentum — Simple rate of price change over N periods."""
    close = df["close"]
    if len(close) < period + 1:
        return IndicatorResult(name="MOM", score=INSUFFICIENT_DATA_SCORE, detail="Insufficient data")

    mom = close - close.shift(period)
    mom_pct = (mom / close.shift(period)) * 100
    val = float(mom_pct.iloc[-1])

    if val > 10:
        score, signal = 80.0, "bullish"
    elif val > 2:
        score, signal = 65.0, "bullish"
    elif val < -10:
        score, signal = 20.0, "bearish"
    elif val < -2:
        score, signal = 35.0, "bearish"
    else:
        score, signal = 50.0, "neutral"

    return IndicatorResult(name="MOM", score=score, signal=signal, value=val,
                           detail=f"Momentum {val:.2f}% over {period} periods")


def calculate_ppo(df: pd.DataFrame) -> IndicatorResult:
    """PPO (Percentage Price Oscillator) — Normalized MACD."""
    close = df["close"]
    if len(close) < 26:
        return IndicatorResult(name="PPO", score=INSUFFICIENT_DATA_SCORE, detail="Insufficient data")

    ema12 = _manual_ema(close, 12)
    ema26 = _manual_ema(close, 26)
    ppo = ((ema12 - ema26) / ema26) * 100
    ppo_val = float(ppo.iloc[-1])
    prev_ppo = float(ppo.iloc[-2]) if len(ppo) > 1 else 0

    if ppo_val > 0 and prev_ppo <= 0:
        score, signal = 80.0, "bullish"
    elif ppo_val > 0:
        score, signal = 65.0, "bullish"
    elif ppo_val < 0 and prev_ppo >= 0:
        score, signal = 20.0, "bearish"
    elif ppo_val < 0:
        score, signal = 35.0, "bearish"
    else:
        score, signal = 50.0, "neutral"

    return IndicatorResult(name="PPO", score=score, signal=signal, value=ppo_val,
                           detail=f"PPO {ppo_val:.3f}%")


def calculate_roc(df: pd.DataFrame, period: int = 12) -> IndicatorResult:
    """ROC (Rate of Change) — Percentage momentum."""
    close = df["close"]
    if len(close) < period + 1:
        return IndicatorResult(name="ROC", score=INSUFFICIENT_DATA_SCORE, detail="Insufficient data")

    roc = ((close - close.shift(period)) / close.shift(period)) * 100
    roc_val = float(roc.iloc[-1])

    if roc_val > 15:
        score, signal = 80.0, "bullish"
    elif roc_val > 3:
        score, signal = 65.0, "bullish"
    elif roc_val < -15:
        score, signal = 20.0, "bearish"
    elif roc_val < -3:
        score, signal = 35.0, "bearish"
    else:
        score, signal = 50.0, "neutral"

    return IndicatorResult(name="ROC", score=score, signal=signal, value=roc_val,
                           detail=f"ROC {roc_val:.2f}% ({period}p)")


def calculate_trima(df: pd.DataFrame, period: int = 20) -> IndicatorResult:
    """TRIMA (Triangular MA) — Double-smoothed moving average."""
    close = df["close"]
    if len(close) < period * 2:
        return IndicatorResult(name="TRIMA", score=INSUFFICIENT_DATA_SCORE, detail="Insufficient data")

    sma1 = close.rolling(period).mean()
    trima = sma1.rolling(period).mean()
    price = close.iloc[-1]
    trima_val = trima.iloc[-1]

    if np.isnan(trima_val):
        return IndicatorResult(name="TRIMA", detail="TRIMA returned NaN")

    dev_pct = (price - trima_val) / trima_val * 100 if trima_val != 0 else 0
    score = 50 + dev_pct * 4
    signal = "bullish" if dev_pct > 0.5 else "bearish" if dev_pct < -0.5 else "neutral"
    return IndicatorResult(name="TRIMA", score=max(0, min(100, score)), signal=signal,
                           value=float(trima_val), detail=f"TRIMA dev {dev_pct:.2f}%")


def calculate_trix(df: pd.DataFrame, period: int = 15) -> IndicatorResult:
    """TRIX — Triple-smoothed EMA rate of change. Filters noise effectively."""
    close = df["close"]
    if len(close) < period * 3 + 1:
        return IndicatorResult(name="TRIX", score=INSUFFICIENT_DATA_SCORE, detail="Insufficient data")

    ema1 = _manual_ema(close, period)
    ema2 = _manual_ema(ema1, period)
    ema3 = _manual_ema(ema2, period)
    trix = ema3.pct_change() * 100
    trix_val = float(trix.iloc[-1]) if not np.isnan(trix.iloc[-1]) else 0

    if trix_val > 0.05:
        score, signal = 70.0, "bullish"
    elif trix_val > 0:
        score, signal = 55.0, "neutral"
    elif trix_val < -0.05:
        score, signal = 30.0, "bearish"
    else:
        score, signal = 45.0, "neutral"

    return IndicatorResult(name="TRIX", score=score, signal=signal, value=trix_val,
                           detail=f"TRIX {trix_val:.4f}")


def calculate_t3(df: pd.DataFrame, period: int = 5, v_factor: float = 0.7) -> IndicatorResult:
    """T3 (Tillson T3) — Ultra-smooth low-lag moving average."""
    close = df["close"]
    if len(close) < period * 6:
        return IndicatorResult(name="T3", score=INSUFFICIENT_DATA_SCORE, detail="Insufficient data")

    c1 = -(v_factor ** 3)
    c2 = 3 * v_factor ** 2 + 3 * v_factor ** 3
    c3 = -6 * v_factor ** 2 - 3 * v_factor - 3 * v_factor ** 3
    c4 = 1 + 3 * v_factor + v_factor ** 3 + 3 * v_factor ** 2

    e1 = _manual_ema(close, period)
    e2 = _manual_ema(e1, period)
    e3 = _manual_ema(e2, period)
    e4 = _manual_ema(e3, period)
    e5 = _manual_ema(e4, period)
    e6 = _manual_ema(e5, period)
    t3 = c1 * e6 + c2 * e5 + c3 * e4 + c4 * e3

    price = close.iloc[-1]
    t3_val = t3.iloc[-1]
    dev_pct = (price - t3_val) / t3_val * 100 if t3_val != 0 else 0

    score = 50 + dev_pct * 5
    signal = "bullish" if dev_pct > 0.3 else "bearish" if dev_pct < -0.3 else "neutral"
    return IndicatorResult(name="T3", score=max(0, min(100, score)), signal=signal,
                           value=float(t3_val), detail=f"T3 dev {dev_pct:.2f}%")


def calculate_wma(df: pd.DataFrame, period: int = 20) -> IndicatorResult:
    """WMA (Weighted MA) — Linearly weighted, emphases recent data."""
    close = df["close"]
    if len(close) < period:
        return IndicatorResult(name="WMA", score=INSUFFICIENT_DATA_SCORE, detail="Insufficient data")

    weights = np.arange(1, period + 1, dtype=float)
    wma = close.rolling(period).apply(lambda x: np.dot(x, weights) / weights.sum(), raw=True)
    price = close.iloc[-1]
    wma_val = wma.iloc[-1]

    if np.isnan(wma_val):
        return IndicatorResult(name="WMA", detail="WMA returned NaN")

    dev_pct = (price - wma_val) / wma_val * 100 if wma_val != 0 else 0
    score = 50 + dev_pct * 4
    signal = "bullish" if dev_pct > 0.5 else "bearish" if dev_pct < -0.5 else "neutral"
    return IndicatorResult(name="WMA", score=max(0, min(100, score)), signal=signal,
                           value=float(wma_val), detail=f"WMA dev {dev_pct:.2f}%")


def calculate_atr_signal(df: pd.DataFrame, period: int = 14) -> IndicatorResult:
    """ATR Signal — Volatility-based trading signal."""
    if len(df) < period + 5:
        return IndicatorResult(name="ATR_SIG", score=INSUFFICIENT_DATA_SCORE, detail="Insufficient data")

    high = df["high"]
    low = df["low"]
    close = df["close"]

    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs()
    ], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()

    # ATR as % of price
    atr_pct = (atr / close) * 100
    atr_pct_val = float(atr_pct.iloc[-1])

    # Compare current ATR to average — expansion = breakout opportunity
    avg_atr = atr.rolling(period * 3).mean()
    atr_ratio = float(atr.iloc[-1] / avg_atr.iloc[-1]) if not np.isnan(avg_atr.iloc[-1]) and avg_atr.iloc[-1] > 0 else 1.0

    if atr_ratio > 1.5:
        score = 75.0  # High volatility expansion = opportunity
        signal = "bullish"
        detail = f"ATR expanding {atr_ratio:.1f}x ({atr_pct_val:.1f}%) — breakout volatility"
    elif atr_ratio < 0.6:
        score = 65.0  # Low volatility = squeeze imminent
        signal = "neutral"
        detail = f"ATR contracting {atr_ratio:.1f}x ({atr_pct_val:.1f}%) — squeeze building"
    else:
        score = 50.0
        signal = "neutral"
        detail = f"ATR normal {atr_ratio:.1f}x ({atr_pct_val:.1f}%)"

    return IndicatorResult(name="ATR_SIG", score=score, signal=signal, value=atr_pct_val, detail=detail)


def calculate_cad(df: pd.DataFrame, period: int = 14) -> IndicatorResult:
    """CAD — CMO with Regime-Aware Mean Reversion. Adaptive momentum."""
    close = df["close"]
    if len(close) < period * 2:
        return IndicatorResult(name="CAD", score=INSUFFICIENT_DATA_SCORE, detail="Insufficient data")

    # Calculate CMO
    diff = close.diff()
    gains = diff.where(diff > 0, 0).rolling(period).sum()
    losses = (-diff.where(diff < 0, 0)).rolling(period).sum()
    cmo = ((gains - losses) / (gains + losses + 1e-10)) * 100
    cmo_val = float(cmo.iloc[-1])

    # Regime: use volatility to determine if mean-reverting or trending
    returns = close.pct_change()
    vol = float(returns.rolling(period).std().iloc[-1]) * 100
    is_trending = vol > 3.0  # >3% daily vol = trending

    if is_trending:
        # In trending regime, follow the momentum
        score = 50 + cmo_val / 3
        mode = "trending"
    else:
        # In mean-reverting regime, fade extremes
        if cmo_val > 50:
            score = 30.0  # Overbought in range = sell
        elif cmo_val < -50:
            score = 70.0  # Oversold in range = buy
        else:
            score = 50.0
        mode = "mean-revert"

    signal = "bullish" if score > 55 else "bearish" if score < 45 else "neutral"
    return IndicatorResult(name="CAD", score=max(0, min(100, score)), signal=signal, value=cmo_val,
                           detail=f"CAD({mode}): CMO={cmo_val:.1f}, vol={vol:.1f}%")


# ─────────────────────────────────────────────────────────────────────────────
# Divergence Detection
# ─────────────────────────────────────────────────────────────────────────────

def detect_divergence(close: pd.Series, indicator: pd.Series, lookback: int = 14) -> str:
    """
    Detect divergence between price and an indicator (RSI, MACD, OBV).

    Returns: BULLISH_DIV, BEARISH_DIV, HIDDEN_BULLISH, HIDDEN_BEARISH, NONE
    """
    if len(close) < lookback + 2 or len(indicator) < lookback + 2:
        return "NONE"

    # Recent vs prior lows/highs
    recent_close = close.iloc[-lookback:]
    prior_close = close.iloc[-lookback * 2:-lookback] if len(close) >= lookback * 2 else close.iloc[:lookback]
    recent_ind = indicator.iloc[-lookback:]
    prior_ind = indicator.iloc[-lookback * 2:-lookback] if len(indicator) >= lookback * 2 else indicator.iloc[:lookback]

    price_lower_low = recent_close.min() < prior_close.min()
    price_higher_high = recent_close.max() > prior_close.max()
    ind_higher_low = recent_ind.min() > prior_ind.min()
    ind_lower_high = recent_ind.max() < prior_ind.max()
    price_higher_low = recent_close.min() > prior_close.min()
    ind_lower_low = recent_ind.min() < prior_ind.min()

    # Classic divergences
    if price_lower_low and ind_higher_low:
        return "BULLISH_DIV"
    if price_higher_high and ind_lower_high:
        return "BEARISH_DIV"
    # Hidden divergences (trend continuation)
    if price_higher_low and ind_lower_low:
        return "HIDDEN_BULLISH"
    if not price_higher_high and not ind_lower_high and recent_close.max() < prior_close.max() and recent_ind.max() > prior_ind.max():
        return "HIDDEN_BEARISH"

    return "NONE"


# ─────────────────────────────────────────────────────────────────────────────
# Regime Detection
# ─────────────────────────────────────────────────────────────────────────────

def detect_regime(df: pd.DataFrame) -> dict:
    """
    Detect market regime using ADX + DMI.

    Returns dict with: regime (TRENDING/RANGING), adx, dmi_direction (UP/DOWN/FLAT), confidence
    """
    if len(df) < 20:
        return {"regime": "UNKNOWN", "adx": 0, "dmi_direction": "FLAT", "confidence": 0}

    adx_result = calculate_adx(df)
    adx_val = adx_result.value or 20.0

    if adx_val >= 25:
        regime = "TRENDING"
        confidence = min(1.0, (adx_val - 25) / 25)  # 25→0%, 50→100%
    else:
        regime = "RANGING"
        confidence = min(1.0, (25 - adx_val) / 15)  # 10→100%, 25→0%

    dmi_dir = "UP" if adx_result.signal == "bullish" else "DOWN" if adx_result.signal == "bearish" else "FLAT"

    return {
        "regime": regime,
        "adx": adx_val,
        "dmi_direction": dmi_dir,
        "confidence": round(confidence, 2),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 7-Tier Signal System
# ─────────────────────────────────────────────────────────────────────────────

def calculate_7tier_signal(normalized_score: float, confidence: float) -> str:
    """
    Convert normalized score (-1 to +1) and confidence (0 to 1) to 7-tier signal.

    Returns: STRONG_BUY, BUY, WEAK_BUY, NEUTRAL, WEAK_SELL, SELL, STRONG_SELL
    """
    if normalized_score >= 0.5 and confidence >= 0.7:
        return "STRONG_BUY"
    elif normalized_score >= 0.35 and confidence >= 0.5:
        return "BUY"
    elif normalized_score >= 0.2:
        return "WEAK_BUY"
    elif normalized_score <= -0.5 and confidence >= 0.7:
        return "STRONG_SELL"
    elif normalized_score <= -0.35 and confidence >= 0.5:
        return "SELL"
    elif normalized_score <= -0.2:
        return "WEAK_SELL"
    else:
        return "NEUTRAL"


# ─────────────────────────────────────────────────────────────────────────────
# Master Analysis Function
# ─────────────────────────────────────────────────────────────────────────────

def run_all_indicators(df: pd.DataFrame) -> TAResult:
    """
    Run all 29 TA indicators with weighted scoring and return aggregated results.

    Weights: Core=1.0, Strong=0.75, Supporting=0.5
    Includes divergence detection, regime detection, and 7-tier signal system.

    Args:
        df: OHLCV DataFrame (DatetimeIndex, columns: open, high, low, close, volume)

    Returns:
        TAResult with category scores and individual indicator results
    """
    logger.info(f"Running 29-indicator TA on {len(df)} candles...")

    # ── Defensive: strip duplicate timestamps ─────────────────────────────
    # Duplicate index labels cause 'cannot reindex on an axis with duplicate
    # labels' in pd.concat calls (e.g. calculate_adx True Range).
    if df.index.duplicated().any():
        df = df[~df.index.duplicated(keep="last")].copy()
        logger.debug(f"TA dedup: reduced to {len(df)} candles after removing dupes")

    result = TAResult()

    # ── CORE Trend Indicators (weight 1.0) ─────────────────────────────────
    ema = calculate_ema_crossover(df)
    macd = calculate_macd(df)
    sma = calculate_sma_crossover(df)
    ichimoku = calculate_ichimoku(df)
    sar = calculate_sar(df)

    # ── CORE Momentum (weight 1.0) ─────────────────────────────────────────
    rsi = calculate_rsi(df)
    bb = calculate_bollinger_bands(df)
    mfi = calculate_mfi(df)
    kdj = calculate_kdj(df)

    # ── CORE Volume (weight 1.0) ───────────────────────────────────────────
    obv = calculate_obv(df)

    # ── STRONG Indicators (weight 0.75) ────────────────────────────────────
    adx = calculate_adx(df)
    stoch_rsi = calculate_stoch_rsi(df)
    dema = calculate_dema(df)
    mesa = calculate_mesa(df)
    cci = calculate_cci(df)
    aroon = calculate_aroon(df)
    apo = calculate_apo(df)

    # ── SUPPORTING Indicators (weight 0.5) ─────────────────────────────────
    vwap = calculate_vwap(df)
    vol_spike = calculate_volume_spike(df)
    ad = calculate_ad_line(df)
    cmo = calculate_cmo(df)
    kama = calculate_kama(df)
    mom = calculate_momentum(df)
    ppo = calculate_ppo(df)
    roc = calculate_roc(df)
    trima = calculate_trima(df)
    trix = calculate_trix(df)
    t3 = calculate_t3(df)
    wma = calculate_wma(df)
    atr_sig = calculate_atr_signal(df)
    cad = calculate_cad(df)

    # ── Collect all indicators by category ─────────────────────────────────
    result.trend_indicators = [ema, macd, sma, ichimoku, sar, adx, dema, mesa, aroon, apo]
    result.momentum_indicators = [rsi, bb, mfi, kdj, stoch_rsi, cci, cmo, kama, mom, ppo, roc, trima, trix, t3, wma, cad]
    result.volume_indicators = [obv, vol_spike, ad, vwap, atr_sig]

    # Shortcuts for external consumers
    result.ema_signal = ema.signal
    result.macd_signal = macd.signal
    result.adx_value = adx.value
    result.rsi = rsi.value
    result.bb_signal = bb.detail.split("—")[0].strip() if "—" in bb.detail else bb.signal
    result.volume_spike = vol_spike.value is not None and vol_spike.value >= 3.0

    # ── Weighted Scoring ───────────────────────────────────────────────────
    # Trend: Core trend indicators + strong trend + supporting trend
    trend_core = (ema.score + macd.score + sma.score + ichimoku.score + sar.score) / 5
    trend_strong = (dema.score + mesa.score + aroon.score + apo.score) / 4
    trend_support = adx.score  # ADX is solo supporting trend indicator
    trend_raw = (trend_core * 1.0 + trend_strong * 0.75 + trend_support * 0.5) / 2.25
    result.trend_score = max(0.0, min(100.0, trend_raw))

    # Momentum: Core momentum + strong momentum + supporting momentum
    mom_core = (rsi.score + bb.score + mfi.score + kdj.score) / 4
    mom_strong = (stoch_rsi.score + cci.score) / 2
    mom_support_scores = [cmo.score, kama.score, mom.score, ppo.score, roc.score,
                          trima.score, trix.score, t3.score, wma.score, cad.score]
    mom_support = sum(mom_support_scores) / len(mom_support_scores)
    mom_raw = (mom_core * 1.0 + mom_strong * 0.75 + mom_support * 0.5) / 2.25
    result.momentum_score = max(0.0, min(100.0, mom_raw))

    # Volume: Core + supporting
    vol_core = obv.score
    vol_support = (vol_spike.score + ad.score + vwap.score + atr_sig.score) / 4
    vol_raw = (vol_core * 1.0 + vol_support * 0.5) / 1.5
    result.volume_score = max(0.0, min(100.0, vol_raw))

    # ── Divergence Detection ───────────────────────────────────────────────
    close = df["close"]
    divergences = {}
    try:
        rsi_series = _manual_rsi(close)
        divergences["RSI"] = detect_divergence(close, rsi_series)
    except Exception:
        divergences["RSI"] = "NONE"
    try:
        _, _, histogram = _manual_macd(close)
        divergences["MACD"] = detect_divergence(close, histogram)
    except Exception:
        divergences["MACD"] = "NONE"
    try:
        obv_series = pd.Series(0.0, index=df.index)
        for i in range(1, len(close)):
            if close.iloc[i] > close.iloc[i - 1]:
                obv_series.iloc[i] = obv_series.iloc[i - 1] + df["volume"].iloc[i]
            elif close.iloc[i] < close.iloc[i - 1]:
                obv_series.iloc[i] = obv_series.iloc[i - 1] - df["volume"].iloc[i]
            else:
                obv_series.iloc[i] = obv_series.iloc[i - 1]
        divergences["OBV"] = detect_divergence(close, obv_series)
    except Exception:
        divergences["OBV"] = "NONE"

    # Divergence bonus/penalty
    for div_type in divergences.values():
        if div_type == "BULLISH_DIV":
            result.momentum_score = min(100, result.momentum_score + 8)
        elif div_type == "BEARISH_DIV":
            result.momentum_score = max(0, result.momentum_score - 8)
        elif div_type == "HIDDEN_BULLISH":
            result.trend_score = min(100, result.trend_score + 5)

    # ── Regime Detection ───────────────────────────────────────────────────
    regime = detect_regime(df)

    # ── Volume Confirmation ────────────────────────────────────────────────
    vol_confirm = result.volume_score / 100.0  # 0 to 1

    # ── Normalized Score + Confidence ──────────────────────────────────────
    composite = (result.trend_score * 0.35 + result.momentum_score * 0.40 + result.volume_score * 0.25)
    normalized = (composite - 50) / 50  # Map 0-100 to -1..+1

    # Confidence = how many indicators agree
    all_indicators = result.trend_indicators + result.momentum_indicators + result.volume_indicators
    bullish_count = sum(1 for ind in all_indicators if ind.signal == "bullish")
    bearish_count = sum(1 for ind in all_indicators if ind.signal == "bearish")
    total = len(all_indicators)
    confidence = max(bullish_count, bearish_count) / total if total > 0 else 0

    # ── 7-Tier Signal ──────────────────────────────────────────────────────
    signal_7tier = calculate_7tier_signal(normalized, confidence)

    logger.info(
        f"TA-29 complete: {result} | "
        f"regime={regime['regime']} | "
        f"divergences={divergences} | "
        f"signal={signal_7tier} (norm={normalized:.2f}, conf={confidence:.2f}) | "
        f"vol_confirm={vol_confirm:.2f}"
    )
    return result

