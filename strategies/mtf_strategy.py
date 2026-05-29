"""
strategies/mtf_strategy.py — Multi-Timeframe (MTF) Trading Strategy Engine

Implements four distinct play horizons, each with its own entry logic,
TP/SL parameters, and position sizing:

  SCALP_1H   — 1-hour momentum plays (RSI + MACD + volume breakout)
  SWING_4H   — 4-hour trend-following (EMA crossover + 4H RSI + OBV)
  POSITION_12_24H — 12–24h macro-trend plays (daily structure + Fib levels)
  RUNNER_5D  — 5-day gem runners (weekly trend + on-chain accumulation)

Entry signals are confirmed across multiple timeframes (MTF confluence).
Each play type has independent TP/SL tiers that are stored in the position
so the position monitor can execute the correct exit logic.

Data source: GeckoTerminal OHLCV (same as mtf_confirmer.py) + Moralis analytics.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Optional

from data.http_session import get_session

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Feature flag
# ─────────────────────────────────────────────────────────────────────────────
MTF_STRATEGY_ENABLED = os.getenv("MTF_STRATEGY_ENABLED", "true").lower() == "true"

# GeckoTerminal API base
_GT_BASE = "https://api.geckoterminal.com/api/v2"

# Chain mapping for GeckoTerminal network IDs
_CHAIN_MAP = {
    "ethereum": "eth",
    "base": "base",
    "arbitrum": "arbitrum",
    "polygon": "polygon_pos",
    "bsc": "bsc",
    "solana": "solana",
}

# OHLCV cache: key → (timestamp, candles_list)
_OHLCV_CACHE: dict[str, tuple[float, list]] = {}
_CACHE_TTL = 180  # 3-minute cache for live trading responsiveness


# ─────────────────────────────────────────────────────────────────────────────
# Play Horizon Profiles
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class MTFPlayProfile:
    """
    Defines entry requirements and exit parameters for one play horizon.
    """
    name: str

    # Timeframes to analyze (primary first)
    primary_tf: str = "1h"          # "15m", "1h", "4h", "12h", "1d"
    confirm_tf: str = "4h"          # Confirmation timeframe (higher = more reliable)
    trend_tf: str = "1d"            # Macro trend timeframe

    # Entry requirements
    min_rsi: float = 30.0           # RSI floor (oversold entry)
    max_rsi: float = 65.0           # RSI ceiling (not overbought)
    require_macd_cross: bool = True  # Require MACD bullish cross
    require_ema_bull: bool = True    # Require EMA9 > EMA21 on primary TF
    require_confirm_bull: bool = True  # Require confirm_tf to be bullish
    min_volume_ratio: float = 1.5   # Min volume vs 24h avg

    # Take-profit tiers (as % gain from entry)
    tp1_pct: float = 8.0
    tp1_sell_pct: float = 0.40      # Sell 40% at TP1
    tp2_pct: float = 20.0
    tp2_sell_pct: float = 0.35      # Sell 35% of remaining at TP2
    tp3_pct: float = 50.0
    tp3_sell_pct: float = 0.50      # Sell 50% of remaining at TP3

    # Stop loss
    hard_stop_pct: float = 7.0      # Hard stop below entry
    trailing_stop_pct: float = 12.0  # Trailing stop after TP1

    # Position sizing
    max_position_pct: float = 5.0   # Max % of wallet
    max_position_usd: float = 500.0
    min_position_usd: float = 25.0

    # Score requirements (from gem scorer)
    min_gem_score: float = 65.0
    high_conviction_score: float = 80.0  # Score for full position size

    # Expected hold time (for stale exit logic)
    expected_hold_hours: float = 4.0


# ── Pre-built profiles for each horizon ──────────────────────────────────────

SCALP_1H_PROFILE = MTFPlayProfile(
    name="scalp_1h",
    primary_tf="1h",
    confirm_tf="4h",
    trend_tf="1d",
    min_rsi=28.0,
    max_rsi=60.0,
    require_macd_cross=True,
    require_ema_bull=True,
    require_confirm_bull=False,    # 4h doesn't need to be bull for 1h scalp
    min_volume_ratio=2.0,          # Need strong volume for 1h plays
    tp1_pct=5.0,
    tp1_sell_pct=0.50,             # Take half off quickly
    tp2_pct=12.0,
    tp2_sell_pct=0.50,
    tp3_pct=25.0,
    tp3_sell_pct=1.0,              # Full exit at TP3
    hard_stop_pct=4.0,             # Tight stop for scalp
    trailing_stop_pct=6.0,
    max_position_pct=4.0,
    max_position_usd=300.0,
    min_position_usd=20.0,
    min_gem_score=62.0,
    high_conviction_score=78.0,
    expected_hold_hours=12.0,       # Optimized: Hold up to 12 hours (up from 2.0)
)

SWING_4H_PROFILE = MTFPlayProfile(
    name="swing_4h",
    primary_tf="4h",
    confirm_tf="1d",
    trend_tf="1d",
    min_rsi=32.0,
    max_rsi=65.0,
    require_macd_cross=True,
    require_ema_bull=True,
    require_confirm_bull=True,     # Daily must confirm 4h swing
    min_volume_ratio=1.5,
    tp1_pct=10.0,
    tp1_sell_pct=0.40,
    tp2_pct=25.0,
    tp2_sell_pct=0.35,
    tp3_pct=60.0,
    tp3_sell_pct=0.50,
    hard_stop_pct=7.0,
    trailing_stop_pct=12.0,
    max_position_pct=5.0,
    max_position_usd=500.0,
    min_position_usd=30.0,
    min_gem_score=65.0,
    high_conviction_score=80.0,
    expected_hold_hours=72.0,       # Optimized: Hold up to 72 hours / 3 days (up from 12.0)
)

POSITION_12_24H_PROFILE = MTFPlayProfile(
    name="position_12_24h",
    primary_tf="4h",
    confirm_tf="1d",
    trend_tf="1d",
    min_rsi=35.0,
    max_rsi=62.0,
    require_macd_cross=True,
    require_ema_bull=True,
    require_confirm_bull=True,
    min_volume_ratio=1.3,
    tp1_pct=15.0,
    tp1_sell_pct=0.35,
    tp2_pct=40.0,
    tp2_sell_pct=0.35,
    tp3_pct=100.0,                 # 2x target for 12-24h plays
    tp3_sell_pct=0.50,
    hard_stop_pct=10.0,
    trailing_stop_pct=15.0,
    max_position_pct=6.0,
    max_position_usd=750.0,
    min_position_usd=40.0,
    min_gem_score=68.0,
    high_conviction_score=82.0,
    expected_hold_hours=48.0,       # Optimized: Hold up to 48 hours / 2 days (up from 18.0)
)

RUNNER_5D_PROFILE = MTFPlayProfile(
    name="runner_5d",
    primary_tf="1d",
    confirm_tf="1d",
    trend_tf="1d",
    min_rsi=38.0,
    max_rsi=60.0,
    require_macd_cross=True,
    require_ema_bull=True,
    require_confirm_bull=True,
    min_volume_ratio=1.2,
    tp1_pct=25.0,
    tp1_sell_pct=0.30,             # Hold more for the run
    tp2_pct=75.0,
    tp2_sell_pct=0.30,
    tp3_pct=200.0,                 # 3x target for 5-day runners
    tp3_sell_pct=0.50,
    hard_stop_pct=12.0,
    trailing_stop_pct=18.0,
    max_position_pct=7.0,
    max_position_usd=1000.0,
    min_position_usd=50.0,
    min_gem_score=70.0,
    high_conviction_score=85.0,
    expected_hold_hours=120.0,      # Optimized: Hold up to 120 hours / 5 days (up from 72.0)
)

ALL_PROFILES = [SCALP_1H_PROFILE, SWING_4H_PROFILE, POSITION_12_24H_PROFILE, RUNNER_5D_PROFILE]


# ─────────────────────────────────────────────────────────────────────────────
# Data Models
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class MTFAnalysis:
    """Full multi-timeframe analysis result for a token."""
    # Per-timeframe data
    tf_1h_rsi: Optional[float] = None
    tf_1h_trend: str = "unknown"       # "bullish", "bearish", "neutral"
    tf_1h_macd_bull: bool = False
    tf_1h_volume_ratio: float = 0.0

    tf_4h_rsi: Optional[float] = None
    tf_4h_trend: str = "unknown"
    tf_4h_macd_bull: bool = False
    tf_4h_obv_rising: bool = False

    tf_1d_rsi: Optional[float] = None
    tf_1d_trend: str = "unknown"
    tf_1d_macd_bull: bool = False

    # Fibonacci levels (from 1d candles)
    fib_support: Optional[float] = None
    fib_resistance: Optional[float] = None
    near_fib_support: bool = False

    # Overall conviction
    mtf_score: float = 50.0           # 0–100 composite
    recommended_profile: Optional[str] = None  # Best matching profile name
    detail: str = ""


@dataclass
class MTFDecision:
    """Result of MTF strategy evaluation for a specific profile."""
    action: str = "skip"              # "buy" or "skip"
    profile_name: str = ""
    symbol: str = ""
    chain: str = ""
    token_address: str = ""
    reason: str = ""
    confidence: float = 0.0

    # Trade parameters
    entry_price: float = 0.0
    tp1_price: float = 0.0
    tp2_price: float = 0.0
    tp3_price: float = 0.0
    stop_loss_price: float = 0.0
    trailing_stop_pct: float = 12.0
    position_size_usd: float = 0.0
    expected_hold_hours: float = 4.0

    # MTF analysis snapshot
    mtf_analysis: Optional[MTFAnalysis] = None

    def __str__(self) -> str:
        if self.action == "buy" and self.entry_price > 0:
            return (
                f"MTFDecision(✅ BUY [{self.profile_name}] {self.symbol}/{self.chain} | "
                f"confidence={self.confidence:.0f} | "
                f"TP1=+{((self.tp1_price/self.entry_price)-1)*100:.0f}% | "
                f"TP2=+{((self.tp2_price/self.entry_price)-1)*100:.0f}% | "
                f"SL=-{((1-(self.stop_loss_price/self.entry_price))*100):.0f}% | "
                f"hold≈{self.expected_hold_hours:.0f}h)"
            )
        elif self.action == "buy":
            return (
                f"MTFDecision(✅ BUY [{self.profile_name}] {self.symbol}/{self.chain} | "
                f"confidence={self.confidence:.0f} | entry_price=N/A)"
            )
        return f"MTFDecision(⏭ SKIP [{self.profile_name}] {self.symbol} | {self.reason})"


# ─────────────────────────────────────────────────────────────────────────────
# OHLCV Fetcher
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_candles(
    pair_address: str,
    chain: str,
    timeframe: str,
    limit: int = 60,
) -> list[dict]:
    """
    Fetch OHLCV candles from GeckoTerminal with caching.
    timeframe: "15m", "1h", "4h", "12h", "1d"
    """
    cache_key = f"mtf_ohlcv:{chain}:{pair_address}:{timeframe}"
    now = time.monotonic()
    if cache_key in _OHLCV_CACHE:
        cached_at, cached_candles = _OHLCV_CACHE[cache_key]
        if now - cached_at < _CACHE_TTL:
            return cached_candles

    network = _CHAIN_MAP.get(chain.lower(), chain.lower())

    # GeckoTerminal timeframe mapping
    tf_map = {
        "15m": ("minute", 15),
        "1h":  ("hour", 1),
        "4h":  ("hour", 4),
        "12h": ("hour", 12),
        "1d":  ("day", 1),
    }
    aggregate_unit, aggregate_val = tf_map.get(timeframe, ("hour", 1))

    url = f"{_GT_BASE}/networks/{network}/pools/{pair_address}/ohlcv/{aggregate_unit}"
    params = {
        "aggregate": str(aggregate_val),
        "limit": str(limit),
        "currency": "usd",
    }

    try:
        resp = get_session().get(url, params=params, timeout=12, headers={
            "Accept": "application/json;version=20230302"
        })
        resp.raise_for_status()
        data = resp.json()

        candles = []
        for attr in data.get("data", {}).get("attributes", {}).get("ohlcv_list", []):
            if len(attr) >= 6:
                candles.append({
                    "timestamp": attr[0],
                    "open":   float(attr[1]),
                    "high":   float(attr[2]),
                    "low":    float(attr[3]),
                    "close":  float(attr[4]),
                    "volume": float(attr[5]),
                })

        _OHLCV_CACHE[cache_key] = (now, candles)
        return candles

    except Exception as e:
        logger.debug(f"MTF OHLCV fetch failed ({timeframe} {pair_address} {chain}): {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Technical Indicator Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _ema(data: list[float], period: int) -> list[float]:
    if len(data) < period:
        return []
    k = 2.0 / (period + 1)
    result = [sum(data[:period]) / period]
    for val in data[period:]:
        result.append(val * k + result[-1] * (1 - k))
    return result


def _rsi(closes: list[float], period: int = 14) -> Optional[float]:
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    if len(gains) < period:
        return None
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _macd(closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9):
    """Returns (macd_line, signal_line, histogram) for latest candle."""
    if len(closes) < slow + signal:
        return None, None, None
    ema_fast = _ema(closes, fast)
    ema_slow = _ema(closes, slow)
    if not ema_fast or not ema_slow:
        return None, None, None
    # Align lengths
    min_len = min(len(ema_fast), len(ema_slow))
    macd_line = [ema_fast[-(min_len - i)] - ema_slow[-(min_len - i)]
                 for i in range(min_len - 1, -1, -1)]
    macd_line.reverse()
    if len(macd_line) < signal:
        return None, None, None
    signal_line = _ema(macd_line, signal)
    if not signal_line:
        return None, None, None
    hist = macd_line[-1] - signal_line[-1]
    return macd_line[-1], signal_line[-1], hist


def _get_trend(closes: list[float]) -> str:
    """EMA9/EMA21 trend direction."""
    if len(closes) < 21:
        return "neutral"
    ema9 = _ema(closes, 9)
    ema21 = _ema(closes, 21)
    if not ema9 or not ema21:
        return "neutral"
    return "bullish" if ema9[-1] > ema21[-1] else ("bearish" if ema9[-1] < ema21[-1] else "neutral")


def _obv_rising(candles: list[dict]) -> bool:
    """On-Balance Volume: returns True if OBV is trending up over last 10 candles."""
    if len(candles) < 10:
        return False
    obv = 0.0
    obv_series = []
    for i, c in enumerate(candles):
        if i == 0:
            obv_series.append(0.0)
            continue
        if c["close"] > candles[i - 1]["close"]:
            obv += c["volume"]
        elif c["close"] < candles[i - 1]["close"]:
            obv -= c["volume"]
        obv_series.append(obv)
    # OBV rising = last 5 avg > prior 5 avg
    if len(obv_series) < 10:
        return False
    recent = sum(obv_series[-5:]) / 5
    prior = sum(obv_series[-10:-5]) / 5
    return recent > prior


def _fib_levels(highs: list[float], lows: list[float]) -> dict:
    """Calculate Fibonacci retracement levels from swing high/low."""
    if not highs or not lows:
        return {}
    swing_high = max(highs[-20:]) if len(highs) >= 20 else max(highs)
    swing_low = min(lows[-20:]) if len(lows) >= 20 else min(lows)
    diff = swing_high - swing_low
    if diff <= 0:
        return {}
    return {
        "0.0":   swing_high,
        "0.236": swing_high - diff * 0.236,
        "0.382": swing_high - diff * 0.382,
        "0.500": swing_high - diff * 0.500,
        "0.618": swing_high - diff * 0.618,
        "0.786": swing_high - diff * 0.786,
        "1.0":   swing_low,
    }


def _near_fib_support(price: float, fib: dict, tolerance_pct: float = 3.0) -> bool:
    """Returns True if price is within tolerance% of a Fibonacci support level."""
    support_levels = [fib.get("0.382"), fib.get("0.500"), fib.get("0.618"), fib.get("0.786")]
    for level in support_levels:
        if level and abs((price - level) / level) * 100 <= tolerance_pct:
            return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Core Analysis Engine
# ─────────────────────────────────────────────────────────────────────────────

def analyze_token_mtf(
    pair_address: str,
    chain: str,
    current_price: float = 0.0,
) -> MTFAnalysis:
    """
    Full multi-timeframe analysis for a token.
    Fetches 1H, 4H, and 1D candles and computes all indicators.

    Returns MTFAnalysis with per-TF signals and a composite mtf_score.
    """
    analysis = MTFAnalysis()

    if not pair_address:
        analysis.detail = "no_pair_address"
        return analysis

    # ── Fetch candles ─────────────────────────────────────────────────────────
    candles_1h = _fetch_candles(pair_address, chain, "1h", limit=60)
    candles_4h = _fetch_candles(pair_address, chain, "4h", limit=60)
    candles_1d = _fetch_candles(pair_address, chain, "1d", limit=30)

    # ── 1H Analysis ──────────────────────────────────────────────────────────
    if candles_1h and len(candles_1h) >= 14:
        closes_1h = [c["close"] for c in candles_1h]
        volumes_1h = [c["volume"] for c in candles_1h]

        analysis.tf_1h_rsi = _rsi(closes_1h)
        analysis.tf_1h_trend = _get_trend(closes_1h)

        macd_line, signal_line, hist = _macd(closes_1h)
        if macd_line is not None and signal_line is not None:
            # Bullish MACD: line above signal AND histogram positive
            analysis.tf_1h_macd_bull = macd_line > signal_line and hist > 0

        # Volume ratio: last 1h vs 24h avg
        if len(volumes_1h) >= 24:
            avg_vol = sum(volumes_1h[-24:]) / 24
            if avg_vol > 0:
                analysis.tf_1h_volume_ratio = volumes_1h[-1] / avg_vol

    # ── 4H Analysis ──────────────────────────────────────────────────────────
    if candles_4h and len(candles_4h) >= 14:
        closes_4h = [c["close"] for c in candles_4h]

        analysis.tf_4h_rsi = _rsi(closes_4h)
        analysis.tf_4h_trend = _get_trend(closes_4h)

        macd_line_4h, signal_line_4h, hist_4h = _macd(closes_4h)
        if macd_line_4h is not None and signal_line_4h is not None:
            analysis.tf_4h_macd_bull = macd_line_4h > signal_line_4h and hist_4h > 0

        analysis.tf_4h_obv_rising = _obv_rising(candles_4h)

    # ── 1D Analysis + Fibonacci ───────────────────────────────────────────────
    if candles_1d and len(candles_1d) >= 10:
        closes_1d = [c["close"] for c in candles_1d]
        highs_1d = [c["high"] for c in candles_1d]
        lows_1d = [c["low"] for c in candles_1d]

        analysis.tf_1d_rsi = _rsi(closes_1d)
        analysis.tf_1d_trend = _get_trend(closes_1d)

        macd_line_1d, signal_line_1d, hist_1d = _macd(closes_1d)
        if macd_line_1d is not None and signal_line_1d is not None:
            analysis.tf_1d_macd_bull = macd_line_1d > signal_line_1d and hist_1d > 0

        # Fibonacci levels
        fib = _fib_levels(highs_1d, lows_1d)
        if fib:
            analysis.fib_support = fib.get("0.618")
            analysis.fib_resistance = fib.get("0.236")
            if current_price > 0:
                analysis.near_fib_support = _near_fib_support(current_price, fib)

    # ── Composite MTF Score ───────────────────────────────────────────────────
    score = 50.0
    details = []

    # 1H signals (weight: 30%)
    if analysis.tf_1h_trend == "bullish":
        score += 8
        details.append("1h_bull")
    elif analysis.tf_1h_trend == "bearish":
        score -= 8
        details.append("1h_bear")

    if analysis.tf_1h_rsi is not None:
        if analysis.tf_1h_rsi < 35:
            score += 10
            details.append(f"1h_rsi_oversold({analysis.tf_1h_rsi:.0f})")
        elif analysis.tf_1h_rsi > 70:
            score -= 12
            details.append(f"1h_rsi_overbought({analysis.tf_1h_rsi:.0f})")

    if analysis.tf_1h_macd_bull:
        score += 7
        details.append("1h_macd_bull")

    if analysis.tf_1h_volume_ratio >= 2.0:
        score += 8
        details.append(f"1h_vol_surge({analysis.tf_1h_volume_ratio:.1f}x)")
    elif analysis.tf_1h_volume_ratio >= 1.5:
        score += 4

    # 4H signals (weight: 40%)
    if analysis.tf_4h_trend == "bullish":
        score += 12
        details.append("4h_bull")
    elif analysis.tf_4h_trend == "bearish":
        score -= 15
        details.append("4h_bear")

    if analysis.tf_4h_rsi is not None:
        if analysis.tf_4h_rsi < 35:
            score += 12
            details.append(f"4h_rsi_oversold({analysis.tf_4h_rsi:.0f})")
        elif analysis.tf_4h_rsi > 70:
            score -= 15
            details.append(f"4h_rsi_overbought({analysis.tf_4h_rsi:.0f})")

    if analysis.tf_4h_macd_bull:
        score += 10
        details.append("4h_macd_bull")

    if analysis.tf_4h_obv_rising:
        score += 6
        details.append("4h_obv_rising")

    # 1D signals (weight: 30%)
    if analysis.tf_1d_trend == "bullish":
        score += 10
        details.append("1d_bull")
    elif analysis.tf_1d_trend == "bearish":
        score -= 12
        details.append("1d_bear")

    if analysis.tf_1d_rsi is not None:
        if analysis.tf_1d_rsi < 40:
            score += 8
            details.append(f"1d_rsi_low({analysis.tf_1d_rsi:.0f})")
        elif analysis.tf_1d_rsi > 75:
            score -= 10
            details.append(f"1d_rsi_high({analysis.tf_1d_rsi:.0f})")

    if analysis.tf_1d_macd_bull:
        score += 8
        details.append("1d_macd_bull")

    # Fibonacci bonus
    if analysis.near_fib_support:
        score += 10
        details.append("near_fib_support")

    analysis.mtf_score = max(0.0, min(100.0, score))
    analysis.detail = " | ".join(details) if details else "no_data"

    # Recommend best profile based on score and trend alignment
    if analysis.mtf_score >= 80 and analysis.tf_1d_trend == "bullish":
        analysis.recommended_profile = "runner_5d"
    elif analysis.mtf_score >= 70 and analysis.tf_4h_trend == "bullish":
        analysis.recommended_profile = "position_12_24h"
    elif analysis.mtf_score >= 60 and analysis.tf_4h_trend in ("bullish", "neutral"):
        analysis.recommended_profile = "swing_4h"
    elif analysis.mtf_score >= 50:
        analysis.recommended_profile = "scalp_1h"
    else:
        analysis.recommended_profile = None

    logger.info(
        f"🕐 MTF Analysis: score={analysis.mtf_score:.0f} | "
        f"rec={analysis.recommended_profile} | {analysis.detail}"
    )

    return analysis


# ─────────────────────────────────────────────────────────────────────────────
# Strategy Evaluator
# ─────────────────────────────────────────────────────────────────────────────

class MTFStrategy:
    """
    Evaluates a token against all MTF play profiles and returns the best
    matching trade decision.
    """

    def __init__(self):
        self.profiles = {p.name: p for p in ALL_PROFILES}

    def evaluate(
        self,
        token_address: str,
        token_symbol: str,
        chain: str,
        pair_address: str,
        current_price: float,
        gem_score: float = 0.0,
        wallet_balance_usd: float = 100.0,
        force_profile: Optional[str] = None,
    ) -> MTFDecision:
        """
        Run full MTF analysis and return the best trade decision.

        Args:
            token_address: Token contract address
            token_symbol: Token symbol (for logging)
            chain: Chain name
            pair_address: DEX pair address (for OHLCV)
            current_price: Current token price in USD
            gem_score: Gem scorer output (0–100)
            wallet_balance_usd: Available wallet balance for sizing
            force_profile: Override profile selection (e.g., "scalp_1h")

        Returns:
            MTFDecision with action, TP/SL levels, and position size
        """
        if not MTF_STRATEGY_ENABLED:
            return MTFDecision(action="skip", reason="mtf_strategy_disabled")

        if not pair_address:
            return MTFDecision(action="skip", reason="no_pair_address")

        # Run full MTF analysis
        analysis = analyze_token_mtf(pair_address, chain, current_price)

        # Select profile
        if force_profile and force_profile in self.profiles:
            profile = self.profiles[force_profile]
        elif analysis.recommended_profile and analysis.recommended_profile in self.profiles:
            profile = self.profiles[analysis.recommended_profile]
        else:
            return MTFDecision(
                action="skip",
                profile_name="none",
                symbol=token_symbol,
                chain=chain,
                token_address=token_address,
                reason=f"mtf_score_too_low ({analysis.mtf_score:.0f})",
                mtf_analysis=analysis,
            )

        # Check gem score gate
        if gem_score < profile.min_gem_score:
            return MTFDecision(
                action="skip",
                profile_name=profile.name,
                symbol=token_symbol,
                chain=chain,
                token_address=token_address,
                reason=f"gem_score_below_threshold ({gem_score:.0f} < {profile.min_gem_score:.0f})",
                mtf_analysis=analysis,
            )

        # Check RSI gates
        primary_rsi = analysis.tf_1h_rsi if profile.primary_tf == "1h" else (
            analysis.tf_4h_rsi if profile.primary_tf == "4h" else analysis.tf_1d_rsi
        )
        if primary_rsi is not None:
            if primary_rsi < profile.min_rsi:
                return MTFDecision(
                    action="skip",
                    profile_name=profile.name,
                    symbol=token_symbol,
                    chain=chain,
                    token_address=token_address,
                    reason=f"rsi_too_low ({primary_rsi:.0f} < {profile.min_rsi:.0f})",
                    mtf_analysis=analysis,
                )
            if primary_rsi > profile.max_rsi:
                return MTFDecision(
                    action="skip",
                    profile_name=profile.name,
                    symbol=token_symbol,
                    chain=chain,
                    token_address=token_address,
                    reason=f"rsi_overbought ({primary_rsi:.0f} > {profile.max_rsi:.0f})",
                    mtf_analysis=analysis,
                )

        # Check EMA trend
        primary_trend = (
            analysis.tf_1h_trend if profile.primary_tf == "1h" else
            analysis.tf_4h_trend if profile.primary_tf == "4h" else
            analysis.tf_1d_trend
        )
        if profile.require_ema_bull and primary_trend == "bearish":
            return MTFDecision(
                action="skip",
                profile_name=profile.name,
                symbol=token_symbol,
                chain=chain,
                token_address=token_address,
                reason=f"primary_tf_bearish ({profile.primary_tf})",
                mtf_analysis=analysis,
            )

        # Check confirmation TF
        confirm_trend = (
            analysis.tf_4h_trend if profile.confirm_tf == "4h" else
            analysis.tf_1d_trend if profile.confirm_tf == "1d" else
            analysis.tf_1h_trend
        )
        if profile.require_confirm_bull and confirm_trend == "bearish":
            return MTFDecision(
                action="skip",
                profile_name=profile.name,
                symbol=token_symbol,
                chain=chain,
                token_address=token_address,
                reason=f"confirm_tf_bearish ({profile.confirm_tf})",
                mtf_analysis=analysis,
            )

        # Check volume
        if analysis.tf_1h_volume_ratio < profile.min_volume_ratio:
            return MTFDecision(
                action="skip",
                profile_name=profile.name,
                symbol=token_symbol,
                chain=chain,
                token_address=token_address,
                reason=f"volume_too_low ({analysis.tf_1h_volume_ratio:.1f}x < {profile.min_volume_ratio:.1f}x)",
                mtf_analysis=analysis,
            )

        # ── All gates passed — calculate trade parameters ─────────────────────
        if current_price <= 0:
            return MTFDecision(
                action="skip",
                profile_name=profile.name,
                symbol=token_symbol,
                chain=chain,
                token_address=token_address,
                reason="no_valid_price",
                mtf_analysis=analysis,
            )

        tp1_price = current_price * (1 + profile.tp1_pct / 100)
        tp2_price = current_price * (1 + profile.tp2_pct / 100)
        tp3_price = current_price * (1 + profile.tp3_pct / 100)
        stop_loss_price = current_price * (1 - profile.hard_stop_pct / 100)

        # Position sizing: scale with gem score conviction
        base_size = wallet_balance_usd * (profile.max_position_pct / 100)
        if gem_score >= profile.high_conviction_score:
            size = base_size * 1.0   # Full size
        elif gem_score >= profile.min_gem_score + 10:
            size = base_size * 0.75  # 75% for mid conviction
        else:
            size = base_size * 0.50  # 50% for minimum conviction

        size = min(size, profile.max_position_usd)
        if size < profile.min_position_usd:
            return MTFDecision(
                action="skip",
                profile_name=profile.name,
                symbol=token_symbol,
                chain=chain,
                token_address=token_address,
                reason=f"position_size_too_small (${size:.0f} < ${profile.min_position_usd:.0f})",
                mtf_analysis=analysis,
            )

        # Confidence score: blend gem score + MTF score
        confidence = (gem_score * 0.6 + analysis.mtf_score * 0.4)

        decision = MTFDecision(
            action="buy",
            profile_name=profile.name,
            symbol=token_symbol,
            chain=chain,
            token_address=token_address,
            reason=f"mtf_confirmed ({analysis.detail})",
            confidence=confidence,
            entry_price=current_price,
            tp1_price=tp1_price,
            tp2_price=tp2_price,
            tp3_price=tp3_price,
            stop_loss_price=stop_loss_price,
            trailing_stop_pct=profile.trailing_stop_pct,
            position_size_usd=round(size, 2),
            expected_hold_hours=profile.expected_hold_hours,
            mtf_analysis=analysis,
        )

        logger.info(str(decision))
        return decision

    def get_best_decision(
        self,
        token_address: str,
        token_symbol: str,
        chain: str,
        pair_address: str,
        current_price: float,
        gem_score: float = 0.0,
        wallet_balance_usd: float = 100.0,
    ) -> Optional[MTFDecision]:
        """
        Try all profiles and return the highest-confidence buy decision.
        Returns None if no profile produces a buy signal.
        """
        best: Optional[MTFDecision] = None
        for profile in ALL_PROFILES:
            decision = self.evaluate(
                token_address=token_address,
                token_symbol=token_symbol,
                chain=chain,
                pair_address=pair_address,
                current_price=current_price,
                gem_score=gem_score,
                wallet_balance_usd=wallet_balance_usd,
                force_profile=profile.name,
            )
            if decision.action == "buy":
                if best is None or decision.confidence > best.confidence:
                    best = decision
        return best


# ─────────────────────────────────────────────────────────────────────────────
# Profile Name Translation
# Maps MTFPlayProfile.name → StrategyProfile.name (used by _PROFILE_MAP)
# This bridges the MTF engine's internal names to the position monitor's registry.
# ─────────────────────────────────────────────────────────────────────────────
_MTF_PROFILE_NAME_MAP = {
    "scalp_1h":         "mtf_1h_scalp",
    "swing_4h":         "mtf_4h_swing",
    "position_12_24h":  "mtf_12h_momentum",
    "runner_5d":        "mtf_5d_position",
}


# ─────────────────────────────────────────────────────────────────────────────
# Convenience singleton
# ─────────────────────────────────────────────────────────────────────────────
_mtf_strategy = MTFStrategy()


def evaluate_mtf(
    token_address: str,
    token_symbol: str,
    chain: str,
    pair_address: str,
    current_price: float,
    gem_score: float = 0.0,
    wallet_balance_usd: float = 100.0,
) -> Optional[MTFDecision]:
    """
    Module-level convenience function. Returns best MTFDecision or None.

    IMPORTANT: The returned MTFDecision.profile_name is translated from the
    MTFPlayProfile internal name (e.g. "scalp_1h") to the StrategyProfile
    registry key (e.g. "mtf_1h_scalp") so the position monitor can look it
    up in _PROFILE_MAP and apply the correct TP/SL tiers.
    """
    decision = _mtf_strategy.get_best_decision(
        token_address=token_address,
        token_symbol=token_symbol,
        chain=chain,
        pair_address=pair_address,
        current_price=current_price,
        gem_score=gem_score,
        wallet_balance_usd=wallet_balance_usd,
    )
    if decision and decision.action == "buy":
        # Translate internal MTFPlayProfile name → StrategyProfile registry key
        decision.profile_name = _MTF_PROFILE_NAME_MAP.get(
            decision.profile_name, decision.profile_name
        )
    return decision
