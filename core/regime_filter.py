"""
core/regime_filter.py — Global market regime detector (v3 — Deep RL Regime Filter).

Analyzes the last 100 candles of BTC and SOL to classify the current market regime
into one of three states: 'Trending', 'Choppy', or 'Nuke'.

The regime affects BOTH wallets (global scope):
  - Trending: Tell position_monitor to loosen trailing stops and let winners run for massive multipliers.
  - Choppy: Tell position_monitor to switch to Mean-Reversion mode (take fast 3-5% scalps and get out).
  - Nuke: Trigger an immediate 'Risk-Off' protocol, halting new buys and tightening all stop-losses to 1% to protect capital.

Data sources (cascading):
  1. Binance API (primary) — BTC + SOL 1h candle data
  2. DexScreener (fallback) — when Binance API is unavailable
"""

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from data.http_session import get_session

logger = logging.getLogger(__name__)


class Regime(Enum):
    TRENDING = "Trending"
    CHOPPY = "Choppy"
    NUKE = "Nuke"


# Backward-compatible aliases for other modules
Regime.EXPANSION = Regime.TRENDING
Regime.CHOP = Regime.CHOPPY
Regime.NORMAL = Regime.TRENDING


@dataclass
class RegimeState:
    """Cached regime state."""
    regime: Regime
    adx: float
    volume_ratio: float       # Current volume / 20-period avg volume
    timestamp: float
    details: str
    funding_rate: float = 0.0       # Binance perp funding rate (positive = longs paying)
    data_source: str = "binance"    # Which data source was used


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
        return 25.0  # Default to TRENDING/NORMAL if insufficient data

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


# ─────────────────────────────────────────────────────────────────────────────
# Data Sources (cascading fallback)
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_kraken_candles(symbol: str, limit: int = 100) -> Optional[list]:
    """Fetch OHLCV candles from Kraken API and format like Binance for compatibility."""
    try:
        url = "https://api.kraken.com/0/public/OHLC"
        # XBTUSD for BTC, SOLUSD for SOL
        kraken_symbol = "XBTUSD" if "BTC" in symbol else "SOLUSD"
        params = {"pair": kraken_symbol, "interval": 60}
        resp = get_session().get(url, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if not data.get("error"):
                pair_key = [k for k in data["result"].keys() if k != "last"][0]
                candles = data["result"][pair_key][-limit:]
                # Convert Kraken to Binance format: [0:time, 1:open, 2:high, 3:low, 4:close, 5:volume]
                formatted = [
                    [
                        c[0], # time
                        c[1], # open
                        c[2], # high
                        c[3], # low
                        c[4], # close
                        c[6]  # volume
                    ] for c in candles
                ]
                return formatted
        logger.warning(f"Kraken API returned status code {resp.status_code} for {symbol}")
        return None
    except Exception as e:
        logger.warning(f"Failed to fetch Kraken candles for {symbol}: {e}")
        return None


def _fetch_dexscreener_fallback() -> dict:
    """
    DexScreener fallback: fetch SOL/USDC and ETH/USDC 5m pair data
    when Binance API is unavailable.
    """
    metrics = {}
    pairs = {
        "solana": {
            "url": "https://api.dexscreener.com/latest/dex/tokens/solana/So11111111111111111111111111111111111111112",
        },
        "ethereum": {
            "url": "https://api.dexscreener.com/latest/dex/tokens/ethereum/0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
        },
    }

    for asset_id, pair_info in pairs.items():
        try:
            resp = get_session().get(pair_info["url"], timeout=10)
            if resp.status_code != 200:
                continue

            data = resp.json()
            pair_list = data.get("pairs", []) if isinstance(data, dict) else data
            if not pair_list:
                continue

            valid_pairs = [p for p in pair_list if isinstance(p, dict) and p.get("priceUsd")]
            if not valid_pairs:
                continue
            valid_pairs.sort(
                key=lambda p: float(p.get("liquidity", {}).get("usd", 0) or 0),
                reverse=True,
            )
            p = valid_pairs[0]

            price = float(p.get("priceUsd", 0))
            h24_change = float(p.get("priceChange", {}).get("h24", 0) or 0)
            vol_24h = float(p.get("volume", {}).get("h24", 0) or 0)
            mcap = float(p.get("marketCap", 0) or p.get("fdv", 0) or 0)

            if h24_change != 0:
                est_prev_price = price / (1 + h24_change / 100)
                high_24h = max(price, est_prev_price) * 1.01
                low_24h = min(price, est_prev_price) * 0.99
            else:
                high_24h = price * 1.005
                low_24h = price * 0.995

            metrics[asset_id] = {
                "price_change_24h": h24_change,
                "total_volume": vol_24h,
                "market_cap": mcap if mcap > 0 else vol_24h * 10,
                "high_24h": high_24h,
                "low_24h": low_24h,
                "current_price": price,
            }

        except Exception as e:
            logger.debug(f"DexScreener fallback failed for {asset_id}: {e}")

    if metrics:
        logger.info(f"📡 DexScreener fallback loaded: {list(metrics.keys())}")
    return metrics


def _fetch_funding_rate() -> float:
    """Fetch Binance perpetual funding rate for ETHUSDT as supplemental signal."""
    try:
        url = "https://fapi.binance.com/fapi/v1/premiumIndex"
        params = {"symbol": "ETHUSDT"}
        resp = get_session().get(url, params=params, timeout=5)
        if resp.status_code != 200:
            return 0.0
        data = resp.json()
        rate = float(data.get("lastFundingRate", 0))
        return rate
    except Exception as e:
        logger.debug(f"Funding rate fetch failed: {e}")
        return 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Main Regime Detection
# ─────────────────────────────────────────────────────────────────────────────

def get_regime(force_refresh: bool = False) -> RegimeState:
    """
    Get the current market regime. Cached for 5 minutes.
    Analyzes the last 100 candles of BTC and SOL to classify the current market regime
    into 'Trending', 'Choppy', or 'Nuke'.
    """
    global _regime_cache

    if not force_refresh and _regime_cache and (time.time() - _regime_cache.timestamp) < _CACHE_TTL_SECONDS:
        return _regime_cache

    # 1. Fetch candles from Kraken API (Binance geo-blocked)
    btc_candles = _fetch_kraken_candles("BTCUSDT", 100)
    sol_candles = _fetch_kraken_candles("SOLUSDT", 100)

    funding_rate = _fetch_funding_rate()

    if btc_candles and sol_candles:
        # Extract candle metrics
        btc_closes = [float(c[4]) for c in btc_candles]
        btc_highs = [float(c[2]) for c in btc_candles]
        btc_lows = [float(c[3]) for c in btc_candles]
        btc_opens = [float(c[1]) for c in btc_candles]
        btc_vols = [float(c[5]) for c in btc_candles]

        sol_closes = [float(c[4]) for c in sol_candles]
        sol_highs = [float(c[2]) for c in sol_candles]
        sol_lows = [float(c[3]) for c in sol_candles]
        sol_opens = [float(c[1]) for c in sol_candles]
        sol_vols = [float(c[5]) for c in sol_candles]

        # Calculate ADX (Wilder's smoothing)
        btc_adx = _calculate_adx(btc_highs, btc_lows, btc_closes)
        sol_adx = _calculate_adx(sol_highs, sol_lows, sol_closes)
        avg_adx = (btc_adx + sol_adx) / 2

        # Price changes over different horizons
        btc_change_1h = (btc_closes[-1] - btc_opens[-1]) / btc_opens[-1] * 100
        sol_change_1h = (sol_closes[-1] - sol_opens[-1]) / sol_opens[-1] * 100

        # Last 4 hours price change
        btc_change_4h = (btc_closes[-1] - btc_closes[-5]) / btc_closes[-5] * 100
        sol_change_4h = (sol_closes[-1] - sol_closes[-5]) / sol_closes[-5] * 100

        # Last 24 hours price change
        btc_change_24h = (btc_closes[-1] - btc_closes[-25]) / btc_closes[-25] * 100
        sol_change_24h = (sol_closes[-1] - sol_closes[-25]) / sol_closes[-25] * 100

        # Volume ratio: current 20-period avg volume vs 100-period avg volume
        btc_vol_ratio = sum(btc_vols[-20:]) / max(sum(btc_vols) / 5, 1)
        sol_vol_ratio = sum(sol_vols[-20:]) / max(sum(sol_vols) / 5, 1)
        avg_vol_ratio = (btc_vol_ratio + sol_vol_ratio) / 2

        # ── Regime Classification ──
        # A. NUKE: sudden sharp drop in last 4 hours or extreme 1h drop
        is_btc_nuke = btc_change_4h <= -3.0 or btc_change_1h <= -2.0
        is_sol_nuke = sol_change_4h <= -4.0 or sol_change_1h <= -2.5

        if is_btc_nuke or is_sol_nuke:
            regime = Regime.NUKE
            details = (
                f"🚨 NUKE — BTC 1h:{btc_change_1h:+.1f}% 4h:{btc_change_4h:+.1f}%, "
                f"SOL 1h:{sol_change_1h:+.1f}% 4h:{sol_change_4h:+.1f}%, "
                f"ADX={avg_adx:.1f}, vol_ratio={avg_vol_ratio:.2f}"
            )
        # B. TRENDING: strong trend confirmed by ADX > 25, or high 24h absolute price change
        elif avg_adx >= 25.0 or abs(btc_change_24h) >= 4.0 or abs(sol_change_24h) >= 6.0:
            regime = Regime.TRENDING
            details = (
                f"🚀 TRENDING — ADX={avg_adx:.1f} (BTC:{btc_adx:.1f}/SOL:{sol_adx:.1f}), "
                f"BTC 24h:{btc_change_24h:+.1f}%, SOL 24h:{sol_change_24h:+.1f}%, "
                f"vol_ratio={avg_vol_ratio:.2f}"
            )
        # C. CHOPPY: range-bound, low ADX, flat price action
        else:
            regime = Regime.CHOPPY
            details = (
                f"😴 CHOPPY — ADX={avg_adx:.1f} (BTC:{btc_adx:.1f}/SOL:{sol_adx:.1f}), "
                f"BTC 24h:{btc_change_24h:+.1f}%, SOL 24h:{sol_change_24h:+.1f}%, "
                f"vol_ratio={avg_vol_ratio:.2f}"
            )

        state = RegimeState(
            regime=regime,
            adx=avg_adx,
            volume_ratio=avg_vol_ratio,
            timestamp=time.time(),
            details=details,
            funding_rate=funding_rate,
            data_source="binance",
        )
        _regime_cache = state
        logger.info(f"Regime: {details}")
        return state

    # Fallback to DexScreener if Binance is down
    logger.warning("Binance API down or rate-limited — falling back to DexScreener")
    metrics = _fetch_dexscreener_fallback()
    if not metrics:
        state = RegimeState(
            regime=Regime.CHOPPY,
            adx=20.0,
            volume_ratio=1.0,
            timestamp=time.time(),
            details="Unable to fetch market data — defaulting to CHOPPY",
            data_source="none",
        )
        _regime_cache = state
        return state

    sol = metrics.get("solana", {})
    eth = metrics.get("ethereum", {})

    sol_vol = abs(sol.get("price_change_24h", 0))
    eth_vol = abs(eth.get("price_change_24h", 0))
    avg_volatility = (sol_vol + eth_vol) / 2

    # If fallback volatility is extremely negative, classify as NUKE
    if sol.get("price_change_24h", 0) <= -8.0 or eth.get("price_change_24h", 0) <= -6.0:
        regime = Regime.NUKE
        details = f"🚨 NUKE (DexScreener Fallback) — SOL 24h:{sol.get('price_change_24h'):+.1f}%, ETH 24h:{eth.get('price_change_24h'):+.1f}%"
    elif avg_volatility >= 5.0:
        regime = Regime.TRENDING
        details = f"🚀 TRENDING (DexScreener Fallback) — SOL 24h:{sol.get('price_change_24h'):+.1f}%, ETH 24h:{eth.get('price_change_24h'):+.1f}%"
    else:
        regime = Regime.CHOPPY
        details = f"😴 CHOPPY (DexScreener Fallback) — SOL 24h:{sol.get('price_change_24h'):+.1f}%, ETH 24h:{eth.get('price_change_24h'):+.1f}%"

    state = RegimeState(
        regime=regime,
        adx=22.0 if regime == Regime.CHOPPY else 35.0,
        volume_ratio=1.0,
        timestamp=time.time(),
        details=details,
        funding_rate=funding_rate,
        data_source="dexscreener",
    )
    _regime_cache = state
    logger.info(f"Regime: {details}")
    return state


def get_sizing_multiplier(regime: Regime, profile_name: str = "conservative") -> float:
    """
    Return a sizing multiplier based on regime and strategy profile.
    """
    if regime == Regime.TRENDING:
        return 2.3 if profile_name == "nuclear" else 1.0
    elif regime == Regime.CHOPPY:
        return 0.07  # Both wallets reduce 93% — no dead money
    else:  # Regime.NUKE
        return 0.0   # Halts new buys completely


def get_regime_with_sweep() -> dict:
    """Get regime state enriched with sweep detection context."""
    state = get_regime()

    sweep_active = False
    try:
        from strategies.indicators import detect_liquidity_sweep_from_dexscreener
        sol_sweep = detect_liquidity_sweep_from_dexscreener(
            token_address="So11111111111111111111111111111111111111112",
            chain="solana",
        )
        if sol_sweep.get("sweep_detected"):
            sweep_active = True
            logger.info(f"🔥 SOL sweep detected: {sol_sweep['details']}")
    except Exception as e:
        logger.debug(f"Sweep check in regime context failed: {e}")

    return {
        "regime": state.regime,
        "is_expansion": state.regime == Regime.TRENDING,
        "is_chop": state.regime == Regime.CHOPPY,
        "is_nuke": state.regime == Regime.NUKE,
        "adx": state.adx,
        "funding_rate": state.funding_rate,
        "sweep_active": sweep_active,
        "should_rebalance": (
            state.regime == Regime.TRENDING and sweep_active
        ),
        "details": state.details,
    }
