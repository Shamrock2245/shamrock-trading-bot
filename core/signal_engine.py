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

from data.http_session import get_session

try:
    import pandas as pd
except ImportError:
    pd = None  # RSI divergence will gracefully skip


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
        resp = get_session().get(url, params=params, timeout=15)
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
        # ── Enrichment data from gem scanner ────────────────────────────────
        holder_concentration_score: float = 0.0,
        smart_money_score: float = 0.0,
        unlock_risk_score: float = 0.0,
        grok_sentiment_score: float = 0.0,
        age_hours: float = None,
        safety_passed: bool = False,
    ) -> SignalScore:
        """
        Run full technical analysis for a token.

        For tokens with OHLCV data: uses RSI, MACD, Bollinger Bands, etc.
        For micro-cap gems without OHLCV: uses gem_score + enrichment data
        (Moralis, holder analysis, smart money, safety) as quality proxy.

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
        # Fallback: if no pair_address or GeckoTerminal returned nothing, try ohlcv_provider
        # (covers tokens that have a token_address but no pool address yet indexed)
        if (not candles or len(candles) < 24) and settings.TA_ENABLED:
            try:
                from data.providers.ohlcv_provider import fetch_ohlcv as _fetch_ohlcv
                _raw = _fetch_ohlcv(token_symbol, chain, timeframe="1h", limit=100)
                if _raw and len(_raw) >= 24:
                    candles = _raw
                    logger.debug(
                        f"OHLCV fallback: {len(candles)} candles for {token_symbol} via ohlcv_provider"
                    )
            except Exception as _ohlcv_err:
                logger.debug(f"OHLCV provider fallback failed for {token_symbol}: {_ohlcv_err}")

        if not candles or len(candles) < 24:
            # Micro-cap gem fallback: not enough candles for meaningful TA
            # RSI needs 14+ periods, MACD needs 26+, BB needs 20+
            # With sparse data, TA produces garbage scores (composite ~20)
            if candles:
                logger.info(
                    f"Only {len(candles)} candles for {token_symbol} — "
                    f"using micro-cap scoring instead of sparse TA"
                )
            return self._microcap_signals(
                score=score,
                token_symbol=token_symbol,
                gem_score=gem_score,
                price_change_1h=price_change_1h,
                price_change_24h=price_change_24h,
                volume_1h=volume_1h,
                volume_24h=volume_24h,
                buys_1h=buys_1h,
                sells_1h=sells_1h,
                holder_concentration_score=holder_concentration_score,
                smart_money_score=smart_money_score,
                unlock_risk_score=unlock_risk_score,
                grok_sentiment_score=grok_sentiment_score,
                age_hours=age_hours,
                safety_passed=safety_passed,
            )

        closes = [c["close"] for c in candles]
        volumes = [c["volume"] for c in candles]

        # ── 29-Indicator TA Arsenal (strategies/indicators.py) ──────────────────
        # Run the full 29-indicator weighted engine and blend its scores into
        # the signal score. This adds Ichimoku, MFI, KDJ, SAR, DEMA, MESA,
        # CCI, AROON, divergence detection, and regime awareness on top of
        # the existing RSI/MACD/BB/EMA/OBV calculations.
        # Scores are blended at 40% TA-29 + 60% existing for backward compat.
        _ta29_trend = None
        _ta29_momentum = None
        _ta29_volume = None
        try:
            import pandas as pd
            from strategies.indicators import run_all_indicators
            highs  = [c.get("high",  c["close"]) for c in candles]
            lows   = [c.get("low",   c["close"]) for c in candles]
            opens  = [c.get("open",  c["close"]) for c in candles]
            df29 = pd.DataFrame({
                "open":   opens,
                "high":   highs,
                "low":    lows,
                "close":  closes,
                "volume": volumes,
            })
            ta29 = run_all_indicators(df29)
            _ta29_trend    = ta29.trend_score
            _ta29_momentum = ta29.momentum_score
            _ta29_volume   = ta29.volume_score
            if ta29.rsi is not None:
                score.rsi = ta29.rsi
            score.macd_signal = ta29.macd_signal
            score.ema_signal  = ta29.ema_signal
            score.bb_signal   = ta29.bb_signal
            logger.debug(
                f"TA-29 blend for {token_symbol}: "
                f"trend={_ta29_trend:.0f} momentum={_ta29_momentum:.0f} "
                f"volume={_ta29_volume:.0f}"
            )
        except Exception as _ta29_err:
            logger.debug(f"TA-29 blend skipped for {token_symbol}: {_ta29_err}")

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

        # ── RSI Divergence Detection (quant-trading pattern) ─────────────────
        # Detects bullish divergences (price ↓ while RSI ↑ = reversal signal)
        # and bearish divergences (price ↑ while RSI ↓ = weakness signal).
        try:
            from strategies.indicators import detect_divergence, _manual_rsi
            _rsi_series = _manual_rsi(pd.Series(closes))
            _div_type = detect_divergence(pd.Series(closes), _rsi_series)
            if _div_type == "BULLISH_DIV":
                score.momentum_score = min(score.momentum_score + 15, 100)
                logger.info(f"🔄 RSI BULLISH DIVERGENCE: {token_symbol} — price ↓ but RSI ↑")
            elif _div_type == "BEARISH_DIV":
                score.momentum_score = max(score.momentum_score - 15, 0)
                logger.info(f"🔄 RSI BEARISH DIVERGENCE: {token_symbol} — price ↑ but RSI ↓")
            elif _div_type == "HIDDEN_BULLISH":
                score.momentum_score = min(score.momentum_score + 8, 100)
                logger.debug(f"RSI hidden bullish divergence: {token_symbol}")
        except Exception as _div_err:
            logger.debug(f"RSI divergence detection skipped for {token_symbol}: {_div_err}")

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

        # ── Regime-Adaptive Strategy Weights (Freqtrade + quant-trading) ────
        # In trending markets: boost trend signals, reduce mean-reversion.
        # In ranging markets: boost RSI/BB, reduce EMA/MACD.
        # In bear markets: boost safety/volume, reduce all trend signals.
        _regime_weights = None
        try:
            from strategies.regime_strategy import get_regime_weights, REGIME_STRATEGY_ENABLED
            if REGIME_STRATEGY_ENABLED:
                _macro_regime = "NEUTRAL"
                try:
                    from core.macro_filter import get_macro_regime
                    _macro = get_macro_regime()
                    _macro_regime = _macro.regime
                except Exception:
                    pass
                _adx_val = None
                if _ta29_trend is not None:
                    try:
                        _adx_val = ta29.adx_value
                    except Exception:
                        pass
                _regime_weights = get_regime_weights(_macro_regime, _adx_val)
        except Exception as _rw_err:
            logger.debug(f"Regime strategy skipped: {_rw_err}")

        # ── Blend TA-29 scores with existing scores ──────────────────────────
        # Uses regime-adaptive blend ratios when available, otherwise 60/40.
        if _ta29_trend is not None:
            if _regime_weights:
                _core_w = _regime_weights.core_ta_weight
                _ta29_w = _regime_weights.ta29_weight
                # Apply regime multipliers to scores before blending
                score.trend_score    = round(score.trend_score    * _regime_weights.trend_mult, 1)
                score.momentum_score = round(score.momentum_score * _regime_weights.momentum_mult, 1)
                score.volume_score   = round(score.volume_score   * _regime_weights.volume_mult, 1)
                # Clamp after regime adjustment
                score.trend_score    = max(-100, min(100, score.trend_score))
                score.momentum_score = max(0, min(100, score.momentum_score))
                score.volume_score   = max(0, min(100, score.volume_score))
            else:
                _core_w = 0.60
                _ta29_w = 0.40

            score.trend_score    = round(score.trend_score    * _core_w + _ta29_trend    * _ta29_w, 1)
            score.momentum_score = round(score.momentum_score * _core_w + _ta29_momentum * _ta29_w, 1)
            score.volume_score   = round(score.volume_score   * _core_w + _ta29_volume   * _ta29_w, 1)
            logger.info(
                f"TA-29 blended for {token_symbol}: "
                f"trend={score.trend_score:.0f} momentum={score.momentum_score:.0f} "
                f"volume={score.volume_score:.0f}"
                f"{f' [regime={_regime_weights.regime_name}]' if _regime_weights else ''}"
            )

        # ── Multi-Timeframe Confirmation (Freqtrade informative_pairs) ────────
        # Confirms 1h signal with 15m and 4h trend alignment.
        # All three aligned = dramatically higher win rate.
        try:
            from strategies.mtf_confirmer import get_mtf_alignment, MTF_CONFIRM_ENABLED
            if MTF_CONFIRM_ENABLED and pair_address:
                _mtf = get_mtf_alignment(pair_address, chain, closes_1h=closes)
                if _mtf.alignment_score != 50.0:
                    # Blend MTF alignment into trend_score at 25% weight
                    score.trend_score = round(
                        score.trend_score * 0.75 + _mtf.alignment_score * 0.25, 1
                    )
                    score.trend_score = max(-100, min(100, score.trend_score))
                    logger.info(
                        f"🕐 MTF blended for {token_symbol}: "
                        f"alignment={_mtf.alignment_score:.0f} → "
                        f"trend={score.trend_score:.0f} ({_mtf.detail})"
                    )
        except Exception as _mtf_err:
            logger.debug(f"MTF confirmation skipped for {token_symbol}: {_mtf_err}")

        return score

    def _microcap_signals(
        self,
        score: SignalScore,
        token_symbol: str,
        gem_score: float,
        price_change_1h: float,
        price_change_24h: float,
        volume_1h: float,
        volume_24h: float,
        buys_1h: int,
        sells_1h: int,
        holder_concentration_score: float = 0.0,
        smart_money_score: float = 0.0,
        unlock_risk_score: float = 0.0,
        grok_sentiment_score: float = 0.0,
        age_hours: float = None,
        safety_passed: bool = False,
    ) -> SignalScore:
        """
        Micro-cap gem signal scoring when OHLCV candle data is unavailable.

        This is THE critical path for new gem sniping. Most micro-cap tokens
        are < 24h old and have no candle history on GeckoTerminal. Instead of
        blocking these (which defeats the bot's purpose), we build a composite
        from:

        1. Gem score (14-signal pipeline: Moralis, holder analysis, smart money,
           unlock risk, social sentiment, contract verification, etc.)
        2. Price momentum from DexScreener (1h + 24h changes)
        3. Volume spike detection
        4. On-chain buy/sell pressure
        5. Enrichment signals (holder concentration, smart money, safety)

        A gem scoring 60+ on the 14-signal pipeline with positive momentum
        should produce a composite of ~55-70, clearing the MIN_SIGNAL_SCORE gate.
        """
        # ── Trend from price action ────────────────────────────────────────
        if price_change_1h > 100:
            score.trend_score = 90
        elif price_change_1h > 50:
            score.trend_score = 80
        elif price_change_1h > 20:
            score.trend_score = 70
        elif price_change_1h > 10:
            score.trend_score = 55
        elif price_change_1h > 0:
            score.trend_score = 50
        elif price_change_1h > -10:
            score.trend_score = 40
        else:
            score.trend_score = 20

        # ── Momentum from combined price action + gem quality ──────────────
        # Instead of RSI/BB, we derive momentum from price changes
        # AND the gem_score (which already incorporates 14 quality signals)
        momentum = 40  # baseline

        # Price momentum
        if price_change_1h > 50:
            momentum += 30
        elif price_change_1h > 20:
            momentum += 20
        elif price_change_1h > 5:
            momentum += 10
        elif price_change_1h < -15:
            momentum -= 25

        # 24h context
        if price_change_24h > 100:
            momentum += 15
        elif price_change_24h > 50:
            momentum += 10
        elif price_change_24h > 0:
            momentum += 5
        elif price_change_24h < -30:
            momentum -= 15

        # Gem score quality boost — the 14-signal pipeline already validated
        # token quality (holders, liquidity, safety, social, contract, etc.)
        # A gem_score ≥ 65 means strong fundamentals across multiple signals
        if gem_score >= 70:
            momentum += 15
        elif gem_score >= 60:
            momentum += 10
        elif gem_score >= 55:
            momentum += 5

        score.momentum_score = max(0, min(100, momentum))

        # ── Volume analysis ────────────────────────────────────────────────
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
        elif volume_1h > 0:
            score.volume_score = 55  # New token — neutral credit
        else:
            score.volume_score = 30

        # ── On-chain scoring (buy/sell + enrichment data) ──────────────────
        # This replaces pure buy/sell ratio with a richer composite that
        # includes holder concentration, smart money, and unlock risk data
        # already collected by the gem scanner.
        onchain = 40  # baseline

        # Buy/sell pressure
        total_txns = buys_1h + sells_1h
        if total_txns > 0:
            buy_ratio = buys_1h / total_txns
            if buy_ratio >= 0.70:
                onchain += 30
            elif buy_ratio >= 0.60:
                onchain += 20
            elif buy_ratio >= 0.50:
                onchain += 10
            elif buy_ratio < 0.40:
                onchain -= 15

        # Holder concentration (from gem scanner — already on-chain verified)
        if holder_concentration_score >= 80:
            onchain += 15  # Well distributed, not whale-dominated
        elif holder_concentration_score >= 60:
            onchain += 8
        elif holder_concentration_score < 30:
            onchain -= 10  # Whale-dominated = rug risk

        # Smart money overlap (known profitable wallets hold this token)
        if smart_money_score >= 80:
            onchain += 15  # Strong smart money signal
        elif smart_money_score >= 50:
            onchain += 8
        elif smart_money_score >= 25:
            onchain += 3

        # Unlock/dilution risk (low risk = safer to hold)
        if unlock_risk_score >= 80:
            onchain += 5  # Minimal dilution risk
        elif unlock_risk_score < 30:
            onchain -= 10  # High dilution risk

        # Safety passed bonus — token cleared GoPlus + Honeypot + TokenSniffer
        if safety_passed:
            onchain += 5

        score.onchain_score = max(0, min(100, onchain))

        # ── Sentiment indicator (Grok X/Twitter analysis) ──────────────────
        # Use Grok sentiment as a proxy for social/market buzz
        if grok_sentiment_score >= 75:
            score.trend_score = min(100, score.trend_score + 10)
        elif grok_sentiment_score >= 60:
            score.trend_score = min(100, score.trend_score + 5)
        elif grok_sentiment_score < 25:
            score.trend_score = max(-100, score.trend_score - 10)

        logger.info(
            f"🔬 Micro-cap signal [{token_symbol}]: "
            f"gem={gem_score:.0f} → "
            f"trend={score.trend_score:.0f} "
            f"momentum={score.momentum_score:.0f} "
            f"volume={score.volume_score:.0f} "
            f"onchain={score.onchain_score:.0f} "
            f"→ composite={score.composite:.1f} "
            f"(need ≥{settings.MIN_SIGNAL_SCORE})"
        )

        return score
