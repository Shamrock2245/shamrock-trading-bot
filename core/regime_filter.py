"""
core/regime_filter.py — Global market regime detector.

Uses ADX (Average Directional Index) + volume breakout to classify the
current market regime as EXPANSION, NORMAL, or CHOP.

The regime affects BOTH wallets (global scope):
  - EXPANSION (ADX > 35 + volume breakout): Full aggression
  - NORMAL (ADX 20-35): Standard sizing
  - CHOP (ADX < 20): Reduce size 70% on both wallets — no dead money

Data source: DexScreener OHLCV for SOL/USD and ETH/USD (the two chains
we care about most). Checked once per scan cycle, cached for 5 minutes.
"""

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import requests

logger = logging.getLogger(__name__)


class Regime(Enum):
    EXPANSION = "expansion"   # ADX > 35, volume breakout → full nuclear
    NORMAL = "normal"         # ADX 20-35 → standard sizing
    CHOP = "chop"             # ADX < 20 → reduce size 70%, protect capital


@dataclass
class RegimeState:
    """Cached regime state."""
    regime: Regime
    adx: float
    volume_ratio: float       # Current volume / 20-period avg volume
    timestamp: float
    details: str


# ─────────────────────────────────────────────────────────────────────────────
# Cache
# ─────────────────────────────────────────────────────────────────────────────
_regime_cache: Optional[RegimeState] = None
_CACHE_TTL_SECONDS = 300  # 5 minutes


# ─────────────────────────────────────────────────────────────────────────────
# ADX Calculation (Wilder's smoothing)
# ─────────────────────────────────────────────────────────────────────────────

def _calculate_adx(highs: list[float], lows: list[float], closes: list[float],
                   period: int = 14) -> float:
    """
    Calculate ADX using Wilder's smoothing method.
    Returns ADX value (0-100). Higher = stronger trend.
    """
    if len(highs) < period + 1:
        return 25.0  # Default to NORMAL if insufficient data

    # True Range, +DM, -DM
    tr_list = []
    plus_dm_list = []
    minus_dm_list = []

    for i in range(1, len(highs)):
        high_diff = highs[i] - highs[i - 1]
        low_diff = lows[i - 1] - lows[i]

        plus_dm = max(high_diff, 0) if high_diff > low_diff else 0
        minus_dm = max(low_diff, 0) if low_diff > high_diff else 0

        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        tr_list.append(tr)
        plus_dm_list.append(plus_dm)
        minus_dm_list.append(minus_dm)

    if len(tr_list) < period:
        return 25.0

    # Wilder's smoothing for ATR, +DM14, -DM14
    atr = sum(tr_list[:period])
    plus_dm14 = sum(plus_dm_list[:period])
    minus_dm14 = sum(minus_dm_list[:period])

    dx_values = []
    for i in range(period, len(tr_list)):
        atr = atr - (atr / period) + tr_list[i]
        plus_dm14 = plus_dm14 - (plus_dm14 / period) + plus_dm_list[i]
        minus_dm14 = minus_dm14 - (minus_dm14 / period) + minus_dm_list[i]

        if atr == 0:
            continue

        plus_di = (plus_dm14 / atr) * 100
        minus_di = (minus_dm14 / atr) * 100

        di_sum = plus_di + minus_di
        if di_sum == 0:
            continue

        dx = abs(plus_di - minus_di) / di_sum * 100
        dx_values.append(dx)

    if len(dx_values) < period:
        return 25.0

    # ADX = Wilder's smoothed average of DX
    adx = sum(dx_values[:period]) / period
    for i in range(period, len(dx_values)):
        adx = (adx * (period - 1) + dx_values[i]) / period

    return adx


def _fetch_ohlcv(pair_address: str, resolution: str = "1h",
                 limit: int = 50) -> Optional[list[dict]]:
    """
    Fetch OHLCV candles from DexScreener for a specific pair.
    Returns list of {open, high, low, close, volume} dicts.
    """
    try:
        # DexScreener OHLCV endpoint (free, no key needed)
        url = f"https://api.dexscreener.com/latest/dex/pairs/solana/{pair_address}"
        resp = requests.get(url, timeout=10)
        data = resp.json()
        pair = data.get("pair") or data.get("pairs", [{}])[0]

        if not pair or not pair.get("priceUsd"):
            return None

        # DexScreener doesn't have a full OHLCV endpoint, so we use
        # the price history from the pair data. For a proper ADX we'd
        # need candle data — fall back to volume-based heuristic.
        return None  # Signal to use volume-only regime detection

    except Exception as e:
        logger.debug(f"OHLCV fetch failed: {e}")
        return None


def _fetch_market_metrics() -> dict:
    """
    Fetch volume and price metrics for regime detection.
    Uses CoinGecko for ETH + SOL market data.
    """
    try:
        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {
            "vs_currency": "usd",
            "ids": "solana,ethereum",
            "order": "market_cap_desc",
            "sparkline": "false",
        }
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()

        metrics = {}
        for coin in data:
            cid = coin.get("id", "")
            metrics[cid] = {
                "price_change_24h": coin.get("price_change_percentage_24h", 0) or 0,
                "total_volume": coin.get("total_volume", 0) or 0,
                "market_cap": coin.get("market_cap", 0) or 0,
                "high_24h": coin.get("high_24h", 0) or 0,
                "low_24h": coin.get("low_24h", 0) or 0,
                "current_price": coin.get("current_price", 0) or 0,
            }
        return metrics

    except Exception as e:
        logger.warning(f"Market metrics fetch failed: {e}")
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# Main Regime Detection
# ─────────────────────────────────────────────────────────────────────────────

def get_regime(force_refresh: bool = False) -> RegimeState:
    """
    Get the current market regime. Cached for 5 minutes.

    Uses a volume + volatility heuristic since we don't have proper
    intraday OHLCV for ADX:
      - High volume + strong price movement → EXPANSION
      - Normal volume + moderate movement → NORMAL
      - Low volume + flat price → CHOP

    Returns:
        RegimeState with regime classification, metrics, and details.
    """
    global _regime_cache

    if not force_refresh and _regime_cache and (time.time() - _regime_cache.timestamp) < _CACHE_TTL_SECONDS:
        return _regime_cache

    metrics = _fetch_market_metrics()
    if not metrics:
        # Default to NORMAL if we can't fetch data — don't block trading
        state = RegimeState(
            regime=Regime.NORMAL,
            adx=25.0,
            volume_ratio=1.0,
            timestamp=time.time(),
            details="Unable to fetch market data — defaulting to NORMAL",
        )
        _regime_cache = state
        return state

    # ── Heuristic regime detection ────────────────────────────────────────
    # Combine ETH + SOL signals for an aggregate regime
    sol = metrics.get("solana", {})
    eth = metrics.get("ethereum", {})

    # Price volatility (absolute 24h change as proxy for trend strength)
    sol_vol = abs(sol.get("price_change_24h", 0))
    eth_vol = abs(eth.get("price_change_24h", 0))
    avg_volatility = (sol_vol + eth_vol) / 2

    # Volume signal: compare 24h volume to market cap (proxy volume ratio)
    sol_vol_ratio = sol.get("total_volume", 0) / max(sol.get("market_cap", 1), 1)
    eth_vol_ratio = eth.get("total_volume", 0) / max(eth.get("market_cap", 1), 1)
    avg_vol_ratio = (sol_vol_ratio + eth_vol_ratio) / 2

    # 24h range as % of price (proxy for ADX)
    sol_range = 0.0
    if sol.get("current_price", 0) > 0:
        sol_range = (sol.get("high_24h", 0) - sol.get("low_24h", 0)) / sol["current_price"] * 100
    eth_range = 0.0
    if eth.get("current_price", 0) > 0:
        eth_range = (eth.get("high_24h", 0) - eth.get("low_24h", 0)) / eth["current_price"] * 100
    avg_range = (sol_range + eth_range) / 2

    # Synthesize into pseudo-ADX
    # Range > 5% + vol ratio > 5% → strong trend (ADX equivalent > 35)
    # Range 2-5% + moderate vol → normal trend (ADX 20-35)
    # Range < 2% + low vol → chop (ADX < 20)
    pseudo_adx = (avg_range * 4) + (avg_volatility * 1.5) + (avg_vol_ratio * 200)
    pseudo_adx = min(pseudo_adx, 80.0)  # Cap at 80

    if pseudo_adx >= 35 and avg_vol_ratio >= 0.04:
        regime = Regime.EXPANSION
        details = (
            f"🚀 EXPANSION — pseudo_ADX={pseudo_adx:.1f}, "
            f"vol_ratio={avg_vol_ratio:.3f}, range={avg_range:.1f}%, "
            f"SOL Δ{sol.get('price_change_24h', 0):+.1f}%, "
            f"ETH Δ{eth.get('price_change_24h', 0):+.1f}%"
        )
    elif pseudo_adx < 20 and avg_vol_ratio < 0.03:
        regime = Regime.CHOP
        details = (
            f"😴 CHOP — pseudo_ADX={pseudo_adx:.1f}, "
            f"vol_ratio={avg_vol_ratio:.3f}, range={avg_range:.1f}%, "
            f"SOL Δ{sol.get('price_change_24h', 0):+.1f}%, "
            f"ETH Δ{eth.get('price_change_24h', 0):+.1f}%"
        )
    else:
        regime = Regime.NORMAL
        details = (
            f"📊 NORMAL — pseudo_ADX={pseudo_adx:.1f}, "
            f"vol_ratio={avg_vol_ratio:.3f}, range={avg_range:.1f}%, "
            f"SOL Δ{sol.get('price_change_24h', 0):+.1f}%, "
            f"ETH Δ{eth.get('price_change_24h', 0):+.1f}%"
        )

    state = RegimeState(
        regime=regime,
        adx=pseudo_adx,
        volume_ratio=avg_vol_ratio,
        timestamp=time.time(),
        details=details,
    )

    _regime_cache = state
    logger.info(f"Regime: {details}")
    return state


def get_sizing_multiplier(regime: Regime, profile_name: str = "conservative") -> float:
    """
    Return a sizing multiplier based on regime and strategy profile.

    Global scope — affects both wallets:
      EXPANSION: conservative=1.0, nuclear=1.5 (full nuclear + bonus)
      NORMAL:    conservative=1.0, nuclear=1.0
      CHOP:      conservative=0.3, nuclear=0.3 (both reduce 70%)
    """
    if regime == Regime.EXPANSION:
        return 1.5 if profile_name == "nuclear" else 1.0
    elif regime == Regime.CHOP:
        return 0.3  # Both wallets reduce 70%
    else:
        return 1.0  # NORMAL — standard sizing
