"""
strategies/mtf_confirmer.py — Multi-Timeframe Confirmation Engine

Inspired by Freqtrade's informative_pairs() pattern: the most profitable
strategies always confirm entries on multiple timeframes. A 1h signal
confirmed by 4h trend alignment has a dramatically higher win rate.

How it works:
  1. Fetches 15m and 4h candles from GeckoTerminal (same API, different timeframe)
  2. Calculates EMA9/EMA21 trend direction on each timeframe
  3. Checks 4h RSI to filter overbought entries
  4. Returns a timeframe_alignment_score (0–100):
     - All three TFs aligned bullish → 100
     - 1h + 4h aligned → 80
     - 1h + 15m aligned → 65
     - Only 1h bullish → 50 (baseline)
     - 15m or 4h contradicts → penalty
  5. Result is blended into trend_score at 25% weight

Caching: 5-minute TTL per token, same as OHLCV cache.

Feature flag: MTF_CONFIRM_ENABLED (default: false)
"""

from __future__ import annotations


import logging
import os
import time
from dataclasses import dataclass
from typing import Optional

from data.http_session import get_session

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────
MTF_CONFIRM_ENABLED = os.getenv("MTF_CONFIRM_ENABLED", "false").lower() == "true"

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

# Cache
_CACHE_TTL = 300  # 5 minutes
_cache: dict[str, tuple[float, dict]] = {}  # key → (timestamp, result_dict)


# ─────────────────────────────────────────────────────────────────────────────
# Data model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class MTFResult:
    """Multi-timeframe confirmation result."""
    alignment_score: float = 50.0   # 0–100 (50 = neutral/no data)

    # Per-timeframe signals
    tf_15m_trend: str = "unknown"   # "bullish", "bearish", "neutral"
    tf_1h_trend: str = "unknown"
    tf_4h_trend: str = "unknown"

    # 4h RSI (overbought filter)
    tf_4h_rsi: Optional[float] = None

    # Alignment detail
    all_aligned: bool = False       # All 3 TFs agree
    detail: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# EMA helpers
# ─────────────────────────────────────────────────────────────────────────────

def _ema(data: list[float], period: int) -> list[float]:
    """Calculate EMA series."""
    if not data or len(data) < period:
        return []
    k = 2.0 / (period + 1)
    ema = [data[0]]
    for val in data[1:]:
        ema.append(val * k + ema[-1] * (1 - k))
    return ema


def _rsi(closes: list[float], period: int = 14) -> Optional[float]:
    """Calculate RSI from closes."""
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


def _get_trend(closes: list[float]) -> str:
    """Determine trend from EMA9/EMA21 crossover."""
    if len(closes) < 21:
        return "neutral"
    ema9 = _ema(closes, 9)
    ema21 = _ema(closes, 21)
    if not ema9 or not ema21:
        return "neutral"
    if ema9[-1] > ema21[-1]:
        return "bullish"
    elif ema9[-1] < ema21[-1]:
        return "bearish"
    return "neutral"


# ─────────────────────────────────────────────────────────────────────────────
# GeckoTerminal OHLCV fetcher
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_candles(pair_address: str, chain: str, timeframe: str,
                   limit: int = 50) -> list[dict]:
    """
    Fetch OHLCV candles from GeckoTerminal.

    Args:
        pair_address: DEX pair address
        chain: chain name (e.g., "base", "solana")
        timeframe: "minute" (15m), "hour" (1h), or "day" (4h uses hour with aggregate)
        limit: number of candles
    """
    network = _CHAIN_MAP.get(chain.lower(), chain.lower())

    # GeckoTerminal timeframe mapping
    tf_map = {
        "15m": ("minute", 15),
        "1h": ("hour", 1),
        "4h": ("hour", 4),
    }

    aggregate, period = tf_map.get(timeframe, ("hour", 1))

    url = f"{_GT_BASE}/networks/{network}/pools/{pair_address}/ohlcv/{aggregate}"
    params = {
        "aggregate": str(period),
        "limit": str(limit),
        "currency": "usd",
    }

    try:
        resp = get_session().get(url, params=params, timeout=10, headers={
            "Accept": "application/json;version=20230302"
        })
        resp.raise_for_status()
        data = resp.json()

        candles = []
        for attr in data.get("data", {}).get("attributes", {}).get("ohlcv_list", []):
            if len(attr) >= 6:
                candles.append({
                    "timestamp": attr[0],
                    "open": float(attr[1]),
                    "high": float(attr[2]),
                    "low": float(attr[3]),
                    "close": float(attr[4]),
                    "volume": float(attr[5]),
                })
        return candles

    except Exception as e:
        logger.debug(f"MTF: Failed to fetch {timeframe} candles for {pair_address} on {chain}: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Main API
# ─────────────────────────────────────────────────────────────────────────────

def get_mtf_alignment(
    pair_address: str,
    chain: str,
    closes_1h: list[float] | None = None,
) -> MTFResult:
    """
    Analyze multi-timeframe alignment for a token.

    Args:
        pair_address: DEX pair address (for fetching 15m/4h candles)
        chain: blockchain name
        closes_1h: pre-fetched 1h closes (avoids redundant API call)

    Returns:
        MTFResult with alignment_score and per-TF signals.
    """
    if not MTF_CONFIRM_ENABLED:
        return MTFResult()

    if not pair_address:
        return MTFResult(detail="no pair address")

    # Check cache
    cache_key = f"mtf:{chain}:{pair_address}"
    now = time.monotonic()
    if cache_key in _cache:
        cached_at, cached_result = _cache[cache_key]
        if now - cached_at < _CACHE_TTL:
            return MTFResult(**cached_result)

    result = MTFResult()

    # 1h trend (from pre-fetched data or separate fetch)
    if closes_1h and len(closes_1h) >= 21:
        result.tf_1h_trend = _get_trend(closes_1h)
    else:
        candles_1h = _fetch_candles(pair_address, chain, "1h", limit=30)
        if candles_1h:
            c1h = [c["close"] for c in candles_1h]
            result.tf_1h_trend = _get_trend(c1h)

    # 15m trend
    candles_15m = _fetch_candles(pair_address, chain, "15m", limit=50)
    if candles_15m:
        c15m = [c["close"] for c in candles_15m]
        result.tf_15m_trend = _get_trend(c15m)

    # 4h trend + RSI
    candles_4h = _fetch_candles(pair_address, chain, "4h", limit=50)
    if candles_4h:
        c4h = [c["close"] for c in candles_4h]
        result.tf_4h_trend = _get_trend(c4h)
        result.tf_4h_rsi = _rsi(c4h, period=14)

    # ── Calculate alignment score ────────────────────────────────────────────
    score = 50.0  # baseline

    # All three aligned = max conviction
    if (result.tf_15m_trend == "bullish" and
            result.tf_1h_trend == "bullish" and
            result.tf_4h_trend == "bullish"):
        score = 100.0
        result.all_aligned = True
        result.detail = "all_bullish_aligned"

    elif (result.tf_15m_trend == "bearish" and
          result.tf_1h_trend == "bearish" and
          result.tf_4h_trend == "bearish"):
        score = 0.0
        result.all_aligned = True
        result.detail = "all_bearish_aligned"

    else:
        # Partial alignment scoring
        if result.tf_1h_trend == "bullish":
            score += 10  # 1h is our primary TF, bullish is good

        # 4h carries more weight (longer trend is more reliable)
        if result.tf_4h_trend == "bullish":
            score += 25
        elif result.tf_4h_trend == "bearish":
            score -= 20  # 4h bearish = significant headwind

        # 15m confirms immediate momentum
        if result.tf_15m_trend == "bullish":
            score += 15
        elif result.tf_15m_trend == "bearish":
            score -= 10  # Short-term weakness

        # 4h RSI overbought filter
        if result.tf_4h_rsi is not None:
            if result.tf_4h_rsi > 75:
                score -= 15  # Overbought on 4h = risky entry
                result.detail = f"overbought_4h_rsi_{result.tf_4h_rsi:.0f}"
            elif result.tf_4h_rsi < 30:
                score += 10  # Oversold on 4h = reversal opportunity
                result.detail = f"oversold_4h_rsi_{result.tf_4h_rsi:.0f}"

        if not result.detail:
            parts = []
            if result.tf_15m_trend != "unknown":
                parts.append(f"15m={result.tf_15m_trend}")
            if result.tf_1h_trend != "unknown":
                parts.append(f"1h={result.tf_1h_trend}")
            if result.tf_4h_trend != "unknown":
                parts.append(f"4h={result.tf_4h_trend}")
            result.detail = " | ".join(parts) if parts else "partial"

    result.alignment_score = max(0.0, min(100.0, score))

    # Cache
    _cache[cache_key] = (now, {
        "alignment_score": result.alignment_score,
        "tf_15m_trend": result.tf_15m_trend,
        "tf_1h_trend": result.tf_1h_trend,
        "tf_4h_trend": result.tf_4h_trend,
        "tf_4h_rsi": result.tf_4h_rsi,
        "all_aligned": result.all_aligned,
        "detail": result.detail,
    })

    if result.alignment_score != 50.0:
        logger.info(
            f"🕐 MTF Confirmation: score={result.alignment_score:.0f} "
            f"({result.detail}) "
            f"[15m={result.tf_15m_trend} 1h={result.tf_1h_trend} 4h={result.tf_4h_trend}"
            f"{f' RSI4h={result.tf_4h_rsi:.0f}' if result.tf_4h_rsi else ''}]"
        )

    return result
