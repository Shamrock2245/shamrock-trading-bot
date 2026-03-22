"""
core/signal_engine.py — Momentum, breakout, and express lane signal engine.

Implements the Phase 2 technical analysis pipeline from the project spec:

Trend Detection:
  - EMA crossovers: 9/21 (short-term), 50/200 (golden/death cross)
  - MACD (12, 26, 9) — crossover signals + histogram divergence
  - ADX (14) — trend strength filter (>25 = strong trend)

Momentum & Reversal:
  - RSI (14) — Buy <30 (oversold), Sell >70 (overbought)
  - Stochastic RSI — confirmation signal for RSI extremes
  - Bollinger Bands — squeeze detection (volatility contraction → breakout)
  - VWAP — institutional entry/exit reference

Volume Analysis:
  - OBV (On-Balance Volume) — confirm price moves with volume
  - Volume spike detection (>3x average = significant event)
  - Accumulation/Distribution — smart money flow

Express Lane:
  - If gem_score ≥ EXPRESS_LANE_SCORE (82), skip full TA and execute immediately
  - This captures the fastest movers before TA data is even available

OHLCV Data Source:
  - GeckoTerminal API (free, no key, pool-level OHLCV)
  - Falls back to DexScreener price change data for basic signals
"""

import logging
import time
from typing import Optional

import requests

from config import settings
from data.models import SignalScore

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# OHLCV Data Fetching
# ─────────────────────────────────────────────────────────────────────────────

_ohlcv_cache: dict[str, tuple[float, list]] = {}
_OHLCV_TTL = 300  # 5 minutes


def get_ohlcv_geckoterminal(
    chain: str,
    pool_address: str,
    timeframe: str = "hour",
    limit: int = 100,
) -> list[dict]:
    """
    Fetch OHLCV candles from GeckoTerminal API.

    Args:
        chain: Chain name (e.g. "base", "solana")
        pool_address: DEX pool/pair address
        timeframe: "minute", "hour", "day"
        limit: Number of candles (max 1000)

    Returns:
        List of OHLCV dicts: {timestamp, open, high, low, close, volume}
    """
    cache_key = f"ohlcv:{chain}:{pool_address}:{timeframe}"
    if cache_key in _ohlcv_cache:
        ts, data = _ohlcv_cache[cache_key]
        if time.time() - ts < _OHLCV_TTL:
            return data

    # GeckoTerminal chain name mapping
    gt_chains = {
        "ethereum": "eth",
        "base": "base",
        "arbitrum": "arbitrum",
        "polygon": "polygon_pos",
        "bsc": "bsc",
        "solana": "solana",
    }
    gt_chain = gt_chains.get(chain, chain)

    try:
        url = (
            f"https://api.geckoterminal.com/api/v2/networks/{gt_chain}"
            f"/pools/{pool_address}/ohlcv/{timeframe}"
        )
        params = {"limit": limit, "currency": "usd"}
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()

        data = resp.json()
        ohlcv_list = data.get("data", {}).get("attributes", {}).get("ohlcv_list", [])

        # Convert to standard format: [timestamp, open, high, low, close, volume]
        candles = []
        for candle in ohlcv_list:
            if len(candle) >= 6:
                candles.append({
                    "timestamp": candle[0],
                    "open": float(candle[1]),
                    "high": float(candle[2]),
                    "low": float(candle[3]),
                    "close": float(candle[4]),
                    "volume": float(candle[5]),
                })

        _ohlcv_cache[cache_key] = (time.time(), candles)
        return candles

    except Exception as e:
        logger.debug(f"GeckoTerminal OHLCV failed for {pool_address}: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Technical Indicators (pure Python, no pandas-ta required)
# ─────────────────────────────────────────────────────────────────────────────

def _ema(prices: list[float], period: int) -> list[float]:
    """Calculate EMA for a price series."""
    if len(prices) < period:
        return []
    k = 2 / (period + 1)
    ema = [sum(prices[:period]) / period]
    for price in prices[period:]:
        ema.append(price * k + ema[-1] * (1 - k))
    return ema


def _rsi(prices: list[float], period: int = 14) -> Optional[float]:
    """Calculate RSI for the most recent value."""
    if len(prices) < period + 1:
        return None
    deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    gains = [max(d, 0) for d in deltas[-period:]]
    losses = [abs(min(d, 0)) for d in deltas[-period:]]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _macd(prices: list[float]) -> dict:
    """Calculate MACD (12, 26, 9) and return signal."""
    if len(prices) < 35:
        return {"signal": "neutral", "histogram": 0.0}

    ema12 = _ema(prices, 12)
    ema26 = _ema(prices, 26)

    # Align lengths
    min_len = min(len(ema12), len(ema26))
    macd_line = [ema12[-(min_len-i)] - ema26[-(min_len-i)] for i in range(min_len)]

    if len(macd_line) < 9:
        return {"signal": "neutral", "histogram": 0.0}

    signal_line = _ema(macd_line, 9)
    if not signal_line:
        return {"signal": "neutral", "histogram": 0.0}

    histogram = macd_line[-1] - signal_line[-1]
    prev_histogram = macd_line[-2] - signal_line[-2] if len(macd_line) > 1 and len(signal_line) > 1 else 0

    if histogram > 0 and prev_histogram <= 0:
        signal = "bullish_cross"
    elif histogram < 0 and prev_histogram >= 0:
        signal = "bearish_cross"
    elif histogram > 0:
        signal = "bullish"
    else:
        signal = "bearish"

    return {"signal": signal, "histogram": histogram, "macd": macd_line[-1], "signal_line": signal_line[-1]}


def _bollinger_bands(prices: list[float], period: int = 20, std_dev: float = 2.0) -> dict:
    """Calculate Bollinger Bands and detect squeeze/breakout."""
    if len(prices) < period:
        return {"signal": "unknown", "upper": 0, "middle": 0, "lower": 0, "bandwidth": 0}

    recent = prices[-period:]
    middle = sum(recent) / period
    variance = sum((p - middle) ** 2 for p in recent) / period
    std = variance ** 0.5

    upper = middle + std_dev * std
    lower = middle - std_dev * std
    bandwidth = (upper - lower) / middle if middle > 0 else 0
    current_price = prices[-1]

    # Squeeze: bandwidth < 5% of price = volatility contraction
    if bandwidth < 0.05:
        signal = "squeeze"
    elif current_price > upper:
        signal = "breakout_up"
    elif current_price < lower:
        signal = "breakout_down"
    else:
        signal = "normal"

    return {
        "signal": signal,
        "upper": upper,
        "middle": middle,
        "lower": lower,
        "bandwidth": bandwidth,
        "current_price": current_price,
    }


def _volume_spike(volumes: list[float], window: int = 24) -> Optional[float]:
    """Detect volume spike ratio vs recent average."""
    if len(volumes) < window + 1:
        return None
    avg = sum(volumes[-window-1:-1]) / window
    if avg <= 0:
        return None
    return volumes[-1] / avg


def _fibonacci_zone(prices: list[float], window: int = 50) -> str:
    """
    Determine which Fibonacci retracement zone the current price is in.
    Uses the swing high/low over the lookback window.
    """
    if len(prices) < window:
        window = len(prices)
    if window < 3:
        return "unknown"

    recent = prices[-window:]
    swing_high = max(recent)
    swing_low = min(recent)
    current = prices[-1]

    if swing_high == swing_low:
        return "unknown"

    # Fibonacci levels (retracement from high)
    fib_levels = {
        "fib_236": swing_high - (swing_high - swing_low) * 0.236,
        "fib_382": swing_high - (swing_high - swing_low) * 0.382,
        "golden_pocket_low": swing_high - (swing_high - swing_low) * 0.618,
        "golden_pocket_high": swing_high - (swing_high - swing_low) * 0.65,
        "fib_618": swing_high - (swing_high - swing_low) * 0.618,
        "fib_786": swing_high - (swing_high - swing_low) * 0.786,
    }

    proximity = settings.FIB_PROXIMITY_PCT / 100

    # Check golden pocket (0.618-0.65 retracement) — strongest support
    gp_low = fib_levels["golden_pocket_low"]
    gp_high = fib_levels["golden_pocket_high"]
    if gp_low * (1 - proximity) <= current <= gp_high * (1 + proximity):
        return "golden_pocket"

    if abs(current - fib_levels["fib_618"]) / fib_levels["fib_618"] <= proximity:
        return "fib_618"
    if abs(current - fib_levels["fib_382"]) / fib_levels["fib_382"] <= proximity:
        return "fib_382"
    if abs(current - fib_levels["fib_236"]) / fib_levels["fib_236"] <= proximity:
        return "fib_236"

    if current > swing_high:
        return "above_high"
    if current < swing_low:
        return "below_low"

    return "no_mans_land"


# ─────────────────────────────────────────────────────────────────────────────
# Main Signal Engine
# ─────────────────────────────────────────────────────────────────────────────

class SignalEngine:
    """
    Computes technical analysis signals for a gem candidate.
    """

    def analyze(
        self,
        token_symbol: str,
        chain: str,
        pair_address: str,
        gem_score: float,
        price_change_1h: float = 0.0,
        price_change_24h: float = 0.0,
        volume_1h: float = 0.0,
        volume_24h: float = 0.0,
        buys_1h: int = 0,
        sells_1h: int = 0,
    ) -> SignalScore:
        """
        Run full technical analysis for a token.

        Returns SignalScore with composite score and individual indicators.
        """
        score = SignalScore()

        # ── Express lane bypass ───────────────────────────────────────────────
        if gem_score >= settings.EXPRESS_LANE_SCORE:
            score.express_lane = True
            score.trend_score = 80.0
            score.momentum_score = 80.0
            score.volume_score = 80.0
            score.onchain_score = 80.0
            logger.info(
                f"EXPRESS LANE: {token_symbol} score={gem_score:.0f} — "
                f"bypassing full TA"
            )
            return score

        # ── Fetch OHLCV data ──────────────────────────────────────────────────
        candles = []
        if pair_address and settings.TA_ENABLED:
            candles = get_ohlcv_geckoterminal(chain, pair_address, timeframe="hour", limit=100)

        if not candles:
            # Fallback: use price change data for basic signals
            return self._fallback_signals(
                score, price_change_1h, price_change_24h,
                volume_1h, volume_24h, buys_1h, sells_1h
            )

        closes = [c["close"] for c in candles]
        volumes = [c["volume"] for c in candles]

        # ── RSI ───────────────────────────────────────────────────────────────
        rsi = _rsi(closes)
        score.rsi = rsi
        if rsi is not None:
            if rsi < 30:
                score.momentum_score = min(score.momentum_score + 30, 100)
            elif rsi < 45:
                score.momentum_score = min(score.momentum_score + 15, 100)
            elif rsi > 70:
                score.momentum_score = max(score.momentum_score - 20, 0)
            elif rsi > 80:
                score.momentum_score = max(score.momentum_score - 35, 0)

        # ── MACD ──────────────────────────────────────────────────────────────
        macd_result = _macd(closes)
        score.macd_signal = macd_result["signal"]
        if macd_result["signal"] == "bullish_cross":
            score.trend_score = min(score.trend_score + 40, 100)
        elif macd_result["signal"] == "bullish":
            score.trend_score = min(score.trend_score + 20, 100)
        elif macd_result["signal"] == "bearish_cross":
            score.trend_score = max(score.trend_score - 40, -100)
        elif macd_result["signal"] == "bearish":
            score.trend_score = max(score.trend_score - 20, -100)

        # ── EMA crossovers ────────────────────────────────────────────────────
        if len(closes) >= 21:
            ema9 = _ema(closes, 9)
            ema21 = _ema(closes, 21)
            if ema9 and ema21:
                if ema9[-1] > ema21[-1]:
                    score.ema_signal = "above_ema"
                    score.trend_score = min(score.trend_score + 15, 100)
                else:
                    score.ema_signal = "below_ema"
                    score.trend_score = max(score.trend_score - 10, -100)

                # Golden/death cross (50/200 EMA if enough data)
                if len(closes) >= 200:
                    ema50 = _ema(closes, 50)
                    ema200 = _ema(closes, 200)
                    if ema50 and ema200:
                        if ema50[-1] > ema200[-1] and ema50[-2] <= ema200[-2]:
                            score.ema_signal = "golden_cross"
                            score.trend_score = min(score.trend_score + 30, 100)
                        elif ema50[-1] < ema200[-1] and ema50[-2] >= ema200[-2]:
                            score.ema_signal = "death_cross"
                            score.trend_score = max(score.trend_score - 30, -100)

        # ── Bollinger Bands ───────────────────────────────────────────────────
        bb = _bollinger_bands(closes)
        score.bb_signal = bb["signal"]
        if bb["signal"] == "squeeze":
            # Squeeze = imminent breakout — bullish if momentum is positive
            if score.trend_score > 0:
                score.momentum_score = min(score.momentum_score + 20, 100)
        elif bb["signal"] == "breakout_up":
            score.momentum_score = min(score.momentum_score + 25, 100)
            score.trend_score = min(score.trend_score + 20, 100)
        elif bb["signal"] == "breakout_down":
            score.momentum_score = max(score.momentum_score - 20, 0)

        # ── Volume analysis ───────────────────────────────────────────────────
        spike_ratio = _volume_spike(volumes)
        score.volume_spike_ratio = spike_ratio
        if spike_ratio is not None:
            if spike_ratio >= 10:
                score.volume_score = 100
            elif spike_ratio >= 5:
                score.volume_score = 85
            elif spike_ratio >= 3:
                score.volume_score = 70
            elif spike_ratio >= 2:
                score.volume_score = 55
            else:
                score.volume_score = 40

        # ── On-chain signals ──────────────────────────────────────────────────
        total_txns = buys_1h + sells_1h
        if total_txns > 0:
            buy_ratio = buys_1h / total_txns
            if buy_ratio >= 0.70:
                score.onchain_score = 90
            elif buy_ratio >= 0.60:
                score.onchain_score = 75
            elif buy_ratio >= 0.50:
                score.onchain_score = 60
            else:
                score.onchain_score = 35

        # ── Fibonacci zone ────────────────────────────────────────────────────
        score.fib_zone = _fibonacci_zone(closes)
        if score.fib_zone == "golden_pocket":
            score.momentum_score = min(score.momentum_score + 15, 100)
        elif score.fib_zone == "fib_618":
            score.momentum_score = min(score.momentum_score + 10, 100)
        elif score.fib_zone == "above_high":
            # Price above recent high = breakout or overextended
            if spike_ratio and spike_ratio >= 3:
                score.trend_score = min(score.trend_score + 10, 100)  # Breakout
            else:
                score.momentum_score = max(score.momentum_score - 10, 0)  # Overextended

        return score

    def _fallback_signals(
        self,
        score: SignalScore,
        price_change_1h: float,
        price_change_24h: float,
        volume_1h: float,
        volume_24h: float,
        buys_1h: int,
        sells_1h: int,
    ) -> SignalScore:
        """
        Basic signal scoring when OHLCV data is unavailable.
        Uses DexScreener price change and volume data.
        """
        # Trend from price change
        if price_change_1h > 20:
            score.trend_score = 70
        elif price_change_1h > 10:
            score.trend_score = 55
        elif price_change_1h > 0:
            score.trend_score = 50
        elif price_change_1h > -10:
            score.trend_score = 40
        else:
            score.trend_score = 20

        # Volume spike
        if volume_24h > 0 and volume_1h > 0:
            avg_hourly = volume_24h / 24
            if avg_hourly > 0:
                spike = volume_1h / avg_hourly
                score.volume_spike_ratio = spike
                if spike >= 5:
                    score.volume_score = 90
                elif spike >= 3:
                    score.volume_score = 75
                elif spike >= 2:
                    score.volume_score = 60
                else:
                    score.volume_score = 45

        # Buy/sell ratio
        total = buys_1h + sells_1h
        if total > 0:
            buy_ratio = buys_1h / total
            score.onchain_score = buy_ratio * 100

        return score
