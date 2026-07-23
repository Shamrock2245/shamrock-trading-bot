"""
core/hl_perps_scanner.py — Hyperliquid Perpetuals Scanner & Signal Engine

Scans all 230 Hyperliquid perp markets every cycle for high-conviction
directional setups. Generates LONG and SHORT signals using a composite
score built from:

  1. RSI (14)           — oversold <30 = long bias, overbought >70 = short bias
  2. EMA Cross          — 9 EMA > 21 EMA = bullish, 9 < 21 = bearish
  3. MACD               — histogram direction and zero-cross
  4. Volume Spike       — volume > 2× 24h average = momentum confirmation
  5. Funding Rate       — extreme positive funding = short fade candidate
                          extreme negative funding = long fade candidate
  6. Bollinger Band     — price near lower band = long, near upper = short
  7. Price Momentum     — 1h return vs 4h return (acceleration)
  8. Open Interest Δ    — rising OI + price rise = trend confirmation

Signal Score: 0–100. Entry gate: ≥ EXEC_SCORE (default 55, goal-adaptive).
Direction: LONG primary (LONG_ONLY=true by default — short WR ~17% in live book).
Leverage: 3× default (configurable via HL_PERPS_LEVERAGE env var).
Position size: Kelly + vol sizer + daily-goal multiplier toward $500+/day ladder.

Scan universe: Watchlist + momentum-ranked discovery (up to 150 coins) + funding anomalies.

Integration: main.py → _hl_perps_daemon() → HLPerpsScanner.run_cycle()
Executor: core/hyperliquid_executor.py (open_long / open_short)

Safety guardrails:
  - Daily loss limit: $30 floor or 33% equity (HL_PERPS_DAILY_LOSS_LIMIT)
  - Max concurrent positions: 10 (goal-adaptive down to 3 in bank_it)
  - Max position margin: $150 (HL_PERPS_MAX_POSITION_USD)
  - Hard notional cap: $400 (HL_PERPS_MAX_NOTIONAL_USD)
  - Re-entry cooldown: 8 min base (goal-adaptive 6–30)
  - Loss cooldown: 10 min base; emergency: 60 min
"""

from __future__ import annotations

import logging
import math
import os
import time
import threading
import json
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Configuration (all overridable via .env)
# ─────────────────────────────────────────────────────────────────────────────
HL_PERPS_ENABLED: bool = os.getenv("HL_PERPS_ENABLED", "true").lower() == "true"
HL_PERPS_SCAN_INTERVAL: float = float(os.getenv("HL_PERPS_SCAN_INTERVAL_SECONDS", "30.0"))
HL_PERPS_MIN_SCORE: float = float(os.getenv("HL_PERPS_MIN_SCORE", "20.0"))  # Initial filter (lets coins reach Fib analysis)
# 2026-07-17 trade_history (26): post-fix edge is +EV (41% WR, 3.26x R:R) but volume
# starved at ~3.5 opens/day (Jul 16 = 1). Drop bar 58→55; floor still 52 via goal engine.
HL_PERPS_EXEC_SCORE: float = float(os.getenv("HL_PERPS_EXEC_SCORE", "55.0"))
HL_PERPS_LEVERAGE: int = int(os.getenv("HL_PERPS_LEVERAGE", "3"))
HL_PERPS_MAX_POSITION_USD: float = float(os.getenv("HL_PERPS_MAX_POSITION_USD", "150.0"))
HL_PERPS_MAX_POSITIONS: int = int(os.getenv("HL_PERPS_MAX_POSITIONS", "10"))  # 10 slots for $500/day rotation
# Align with executor HYPERLIQUID_MAX_TOTAL_EXPOSURE (notional, margin×lev). 1200 was too tight at 10×$400.
HL_PERPS_MAX_TOTAL_EXPOSURE: float = float(os.getenv("HL_PERPS_MAX_TOTAL_EXPOSURE", "5000.0"))
HL_PERPS_DAILY_LOSS_LIMIT: float = float(os.getenv("HL_PERPS_DAILY_LOSS_LIMIT", "100.0"))
HL_PERPS_STOP_LOSS_PCT: float = float(os.getenv("HL_PERPS_STOP_LOSS_PCT", "2.5"))
HL_PERPS_TAKE_PROFIT_PCT: float = float(os.getenv("HL_PERPS_TAKE_PROFIT_PCT", "6.0"))
# Extreme funding rate = fade opportunity (short when funding very positive, long when very negative)
HL_PERPS_FUNDING_FADE_THRESHOLD: float = float(os.getenv("HL_PERPS_FUNDING_FADE_THRESHOLD", "0.03"))
# Cooldown after a loss on a coin (minutes)
# 2026-07-17: 15m was stacking with reentry and starving volume; RSI veto + autoban still block churn
HL_PERPS_LOSS_COOLDOWN_MIN: int = int(os.getenv("HL_PERPS_LOSS_COOLDOWN_MIN", "10"))
# Re-entry throttle: 8m (was 12) — autoban handles toxic names; 5m was too short for AAVE era
HL_PERPS_REENTRY_COOLDOWN_MIN: int = int(os.getenv("HL_PERPS_REENTRY_COOLDOWN_MIN", "8"))
# After emergency close (SL place fail), block the coin longer than normal reentry
HL_PERPS_EMERGENCY_COOLDOWN_MIN: int = int(os.getenv("HL_PERPS_EMERGENCY_COOLDOWN_MIN", "60"))
# Hard notional cap (margin × leverage)
HL_PERPS_MAX_NOTIONAL_USD: float = float(os.getenv("HL_PERPS_MAX_NOTIONAL_USD", "400.0"))
# Minimum R/R at signal generation (executor re-checks post-fill) — KEEP 1.2 (post-fix R:R 3.26x)
HL_PERPS_MIN_RR: float = float(os.getenv("HL_PERPS_MIN_RR", "1.2"))
# Shorts: live book ~17% short WR — stay long-only until short edge is proven
HL_PERPS_LONG_ONLY: bool = os.getenv("HL_PERPS_LONG_ONLY", "true").lower() == "true"
# ── Hard ban (trade_history 31): NEVER open these — score+20 was not enough ──
# Soft toxic (score bonus) still let KAITO/APE EXECUTING live on 2026-07-22.
# Confirmed multi-trade losers from v26–v31 (AAVE kept off hard-ban: net +$68).
_HARD_BAN_RAW = os.getenv(
    "HL_PERPS_HARD_BAN_COINS",
    "KAITO,APE,HEMI,ONDO,GRASS,TRB,HMSTR,FARTCOIN,MET,EIGEN,MORPHO,LIT,HYPE,BRETT,POPCAT,MEME,JTO",
)
HL_PERPS_HARD_BAN_COINS: set[str] = {
    c.strip().upper() for c in _HARD_BAN_RAW.split(",") if c.strip()
}
# Soft toxic: higher score bar only (not a hard skip). Borderline / noisy names.
# HYPE added 2026-07-17; KAITO/HEMI/ONDO moved to hard-ban after v29–v31.
_TOXIC_RAW = os.getenv(
    "HL_PERPS_TOXIC_COINS",
    "AAVE",
)
HL_PERPS_TOXIC_COINS: set[str] = {c.strip().upper() for c in _TOXIC_RAW.split(",") if c.strip()}
# Higher bar for soft-toxic names
HL_PERPS_TOXIC_SCORE_BONUS: float = float(os.getenv("HL_PERPS_TOXIC_SCORE_BONUS", "20.0"))
# Cap new opens per scan cycle — trade_history 31 / live 2026-07-22 sprayed 6–9
# entries in one minute when behind_pace. Rank full universe, take top-N only.
# v32: 3 → 2 (trade_history 34: 67 opens on 7/22, fees ~4x the gross edge).
HL_PERPS_MAX_NEW_PER_SCAN: int = int(os.getenv("HL_PERPS_MAX_NEW_PER_SCAN", "2"))
# v32: hard daily churn cap — new opens per UTC day across all coins. The edge
# shape (7/14–7/21: 42% WR, >2% winners = all the profit) supports ~15–25
# quality trades/day; 67/day is pure fee bleed. Resets at midnight UTC.
HL_PERPS_MAX_OPENS_PER_DAY: int = int(os.getenv("HL_PERPS_MAX_OPENS_PER_DAY", "24"))
# v32: per-coin edge sizing — scale size by realized per-coin expectancy from
# hl_coin_perf.json (already persisted for autoban). Proven winners get up to
# EDGE_SIZE_MAX, chronic underperformers get EDGE_SIZE_MIN. Neutral → 1.0.
HL_PERPS_EDGE_SIZING_ENABLED: bool = os.getenv(
    "HL_PERPS_EDGE_SIZING_ENABLED", "true"
).lower() in ("1", "true", "yes", "on")
HL_PERPS_EDGE_SIZE_MIN: float = float(os.getenv("HL_PERPS_EDGE_SIZE_MIN", "0.6"))
HL_PERPS_EDGE_SIZE_MAX: float = float(os.getenv("HL_PERPS_EDGE_SIZE_MAX", "1.3"))
HL_PERPS_EDGE_MIN_TRADES: int = int(os.getenv("HL_PERPS_EDGE_MIN_TRADES", "4"))
# Optional hour block (local America/New_York). trade_history(27): hour 10/17/22 worst PnL.
# Empty string disables. Example: "10,17,22"
_BLOCKED_HOURS_RAW = os.getenv("HL_PERPS_BLOCKED_HOURS_ET", "10,17,22")
HL_PERPS_BLOCKED_HOURS_ET: set[int] = {
    int(h.strip()) for h in _BLOCKED_HOURS_RAW.split(",") if h.strip().isdigit()
}
# Winning entry filter (trade_history 29) — volume floor + toxic-hour size cut
WINNING_ENTRY_FILTER_ENABLED: bool = os.getenv(
    "WINNING_ENTRY_FILTER_ENABLED", "true"
).lower() in ("1", "true", "yes", "on")
# ── Auto-Blacklist: performance-based dynamic coin banning ───────────────────
# A coin is auto-banned for HL_PERPS_AUTOBAN_HOURS when it has
# >= HL_PERPS_AUTOBAN_MIN_TRADES AND a win rate below HL_PERPS_AUTOBAN_WR_THRESHOLD.
# State persists to data/dashboard/hl_coin_perf.json so bans survive restarts.
HL_PERPS_AUTOBAN_ENABLED: bool = os.getenv("HL_PERPS_AUTOBAN_ENABLED", "true").lower() == "true"
HL_PERPS_AUTOBAN_MIN_TRADES: int = int(os.getenv("HL_PERPS_AUTOBAN_MIN_TRADES", "5"))  # Min trades before ban eligible
HL_PERPS_AUTOBAN_WR_THRESHOLD: float = float(os.getenv("HL_PERPS_AUTOBAN_WR_THRESHOLD", "0.30"))  # Ban if WR < 30%
HL_PERPS_AUTOBAN_HOURS: float = float(os.getenv("HL_PERPS_AUTOBAN_HOURS", "48.0"))  # Ban duration in hours

# Profit withdrawal automation
HL_PERPS_BASE_CAPITAL: float = float(os.getenv("HL_PERPS_BASE_CAPITAL", "150.0"))
HL_PERPS_PROFIT_SWEEP_USD: float = float(os.getenv("HL_PERPS_PROFIT_SWEEP_USD", "500.0"))

# State persistence
_STATE_DIR = Path(os.getenv("DASHBOARD_STATE_DIR", "./data/dashboard"))
_STATE_FILE = _STATE_DIR / "hl_perps_state.json"
_COIN_PERF_FILE = _STATE_DIR / "hl_coin_perf.json"  # Auto-blacklist win/loss stats

# Global registry for cross-module cooldown access
_global_scanner = None

# ─────────────────────────────────────────────────────────────────────────────
# Scan universe — top 40 liquid perps + dynamic funding anomaly additions
# ─────────────────────────────────────────────────────────────────────────────
HL_PERPS_WATCHLIST: list[str] = [
    # Tier 1 — highest liquidity, tightest spreads
    "BTC", "ETH", "SOL", "XRP", "BNB", "DOGE", "ADA", "AVAX", "SUI", "TON",
    # Tier 2 — high-volume altcoins
    "LINK", "DOT", "NEAR", "ARB", "OP", "INJ", "APT", "TRX", "LTC", "BCH",
    "ATOM", "UNI", "AAVE", "MKR", "CRV", "LDO", "STX", "ONDO", "ENA", "JUP",
    # Tier 3 — high-beta momentum plays
    "kPEPE", "kSHIB", "kBONK", "WLD", "HYPE", "TRUMP", "FARTCOIN",
    "RNDR", "FTM", "APE", "DYDX",
]


# ─────────────────────────────────────────────────────────────────────────────
# Data models
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PerpSignal:
    """A scored directional signal for a single perp market."""
    coin: str
    direction: str          # "long" or "short"
    score: float            # 0–100
    entry_price: float
    stop_loss_price: float
    take_profit_price: float
    leverage: int
    position_size_usd: float
    # Signal components
    rsi: Optional[float] = None
    ema_cross: Optional[str] = None     # "bullish", "bearish", "neutral"
    macd_signal: Optional[str] = None   # "buy", "sell", "neutral"
    volume_spike: Optional[float] = None  # ratio vs 24h avg
    funding_rate: Optional[float] = None  # per 8h
    bb_position: Optional[str] = None   # "lower", "upper", "middle"
    momentum_1h: Optional[float] = None  # 1h price change %
    ema_support_px: Optional[float] = None # EMA 21 value for retracement limit entries
    fib_zone: str = "none"                 # Fibonacci zone name (golden_pocket, fib_618, etc.)
    fib_confidence: float = 0.0            # Fibonacci alignment confidence (0-100)
    components: Optional[dict] = field(default_factory=dict)  # Full scoring components for audit trail
    reasoning: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def r_r_ratio(self) -> float:
        """Risk/reward ratio."""
        if self.direction == "long":
            reward = (self.take_profit_price - self.entry_price) / self.entry_price
            risk = (self.entry_price - self.stop_loss_price) / self.entry_price
        else:
            reward = (self.entry_price - self.take_profit_price) / self.entry_price
            risk = (self.stop_loss_price - self.entry_price) / self.entry_price
        return reward / risk if risk > 0 else 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Technical indicator calculations (pure Python, no pandas dependency)
# ─────────────────────────────────────────────────────────────────────────────

def _rsi(closes: list[float], period: int = 14) -> Optional[float]:
    """Wilder's RSI."""
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0))
        losses.append(max(-delta, 0))
    # Initial averages
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _ema(values: list[float], period: int) -> Optional[float]:
    """Exponential moving average — returns most recent value."""
    if len(values) < period:
        return None
    k = 2 / (period + 1)
    ema = sum(values[:period]) / period
    for v in values[period:]:
        ema = v * k + ema * (1 - k)
    return ema


def _ema_series(values: list[float], period: int) -> list[float]:
    """Full EMA series."""
    if len(values) < period:
        return []
    k = 2 / (period + 1)
    ema = sum(values[:period]) / period
    result = [ema]
    for v in values[period:]:
        ema = v * k + ema * (1 - k)
        result.append(ema)
    return result


def _macd(closes: list[float]) -> tuple[Optional[float], Optional[float], Optional[float]]:
    """MACD(12,26,9). Returns (macd_line, signal_line, histogram)."""
    if len(closes) < 35:
        return None, None, None
    ema12 = _ema_series(closes, 12)
    ema26 = _ema_series(closes, 26)
    # Align lengths
    min_len = min(len(ema12), len(ema26))
    macd_line = [ema12[-(min_len - i)] - ema26[-(min_len - i)] for i in range(min_len)]
    if len(macd_line) < 9:
        return None, None, None
    signal = _ema(macd_line, 9)
    if signal is None:
        return None, None, None
    hist = macd_line[-1] - signal
    return macd_line[-1], signal, hist


def _bollinger(closes: list[float], period: int = 20, std_mult: float = 2.0) -> tuple[float, float, float]:
    """Bollinger Bands. Returns (upper, middle, lower)."""
    if len(closes) < period:
        mid = closes[-1]
        return mid, mid, mid
    recent = closes[-period:]
    mid = sum(recent) / period
    variance = sum((p - mid) ** 2 for p in recent) / period
    std = math.sqrt(variance)
    return mid + std_mult * std, mid, mid - std_mult * std


def _volume_spike(volumes: list[float], window: int = 24) -> Optional[float]:
    """Volume spike ratio vs rolling average."""
    if len(volumes) < window + 1:
        return None
    avg = sum(volumes[-window - 1:-1]) / window
    if avg <= 0:
        return None
    return volumes[-1] / avg


# ─────────────────────────────────────────────────────────────────────────────
# Signal scoring
# ─────────────────────────────────────────────────────────────────────────────

def _score_signal(
    closes: list[float],
    volumes: list[float],
    funding_rate: float,
) -> tuple[float, str, dict]:
    """
    Score a perp market and determine direction.

    Returns:
        (score 0–100, direction "long"/"short"/"none", components dict)
    """
    if len(closes) < 35:
        return 0.0, "none", {}

    components = {}
    long_score = 0.0
    short_score = 0.0

    # ── EMA 50 Trend Filter (Block counter-trend trades) ─────────────────────
    ema50 = _ema(closes, 50)
    current_price = closes[-1]
    trend = "neutral"
    if ema50 is not None:
        if current_price > ema50:
            trend = "bullish"
        elif current_price < ema50:
            trend = "bearish"

    # ── RSI (weight: 25%) ────────────────────────────────────────────────────
    # Shifting from Mean Reversion to Trend Continuation
    rsi = _rsi(closes)
    components["rsi"] = rsi
    # Sticky veto flags — once set, no downstream indicator can override them.
    # This is the critical fix: without these flags, EMA/MACD/volume/BB can
    # add points back after the veto, allowing a deeply oversold coin to still
    # reach the 65-point entry threshold and trigger a knife-catching long.
    _rsi_long_vetoed = False
    _rsi_short_vetoed = False
    if rsi is not None:
        if rsi < 35:
            # Deeply oversold = market is dumping. Catching knives is deadly.
            long_score = 0.0  # VETO long
            short_score += 15.0
            _rsi_long_vetoed = True
            components["rsi_veto"] = "long_vetoed"
        elif rsi > 65:
            # Deeply overbought = market is rocketing. Shorting is deadly.
            short_score = 0.0  # VETO short
            long_score += 15.0
            _rsi_short_vetoed = True
            components["rsi_veto"] = "short_vetoed"
        elif 40 <= rsi <= 60:
            # Mid-range: perfect for trend continuation pullbacks
            long_score += 25.0
            short_score += 25.0
        elif 35 <= rsi < 40:
            # Transitional zone: oversold recovery — proportional RSI points.
            # Fixes dead zone: RSI=38 was giving 0 points, blocking valid recovery longs.
            _frac = (rsi - 35) / 5.0  # 0.0 at RSI=35, 1.0 at RSI=40
            long_score += round(25.0 * _frac * 0.6, 1)   # max +15 at boundary
            short_score += round(15.0 * (1 - _frac), 1)  # fades as RSI recovers
            components["rsi_zone"] = f"recovery_{rsi:.0f}"
        elif 60 < rsi <= 65:
            # Transitional zone: overbought approach — proportional points.
            # Fixes dead zone: RSI=62 (healthy bull trend) was giving 0 points.
            _frac = (65 - rsi) / 5.0  # 1.0 at RSI=60, 0.0 at RSI=65
            long_score += round(25.0 * _frac * 0.6, 1)   # fades as RSI approaches veto
            short_score += round(15.0 * (1 - _frac), 1)  # builds as RSI approaches veto
            components["rsi_zone"] = f"extended_{rsi:.0f}"

    # ── EMA Cross 9/21 (weight: 20%) ─────────────────────────────────────────
    ema9 = _ema(closes, 9)
    ema21 = _ema(closes, 21)
    if ema9 is not None and ema21 is not None:
        components["ema21"] = ema21
        spread_pct = (ema9 - ema21) / ema21 * 100
        if ema9 > ema21:
            components["ema_cross"] = "bullish"
            long_score += min(20.0, 10.0 + abs(spread_pct) * 2)
        else:
            components["ema_cross"] = "bearish"
            short_score += min(20.0, 10.0 + abs(spread_pct) * 2)

    # ── MACD (weight: 20%) ───────────────────────────────────────────────────
    macd_line, signal_line, histogram = _macd(closes)
    components["macd_hist"] = histogram
    if histogram is not None and macd_line is not None:
        if histogram > 0 and macd_line > 0:
            long_score += 20.0          # MACD positive and above zero
        elif histogram > 0:
            long_score += 12.0          # MACD turning positive
        elif histogram < 0 and macd_line < 0:
            short_score += 20.0         # MACD negative and below zero
        elif histogram < 0:
            short_score += 12.0         # MACD turning negative

    # ── Volume Spike (weight: 15%) ───────────────────────────────────────────
    vol_ratio = _volume_spike(volumes)
    components["volume_spike"] = vol_ratio
    if vol_ratio is not None:
        if vol_ratio >= 3.0:
            # High volume spike — amplifies whichever direction is leading
            bonus = 15.0
        elif vol_ratio >= 2.0:
            bonus = 10.0
        elif vol_ratio >= 1.5:
            bonus = 5.0
        else:
            bonus = 0.0
        # Apply to the leading direction
        if long_score >= short_score:
            long_score += bonus
        else:
            short_score += bonus

    # ── Bollinger Band Position (weight: 10%) ────────────────────────────────
    bb_upper, bb_mid, bb_lower = _bollinger(closes)
    price = closes[-1]
    bb_range = bb_upper - bb_lower
    if bb_range > 0:
        bb_pos = (price - bb_lower) / bb_range  # 0 = at lower, 1 = at upper
        components["bb_position"] = bb_pos
        if bb_pos < 0.15:
            long_score += 10.0          # Near lower band — oversold
            components["bb_zone"] = "lower"
        elif bb_pos > 0.85:
            short_score += 10.0         # Near upper band — overbought
            components["bb_zone"] = "upper"
        else:
            components["bb_zone"] = "middle"

    # ── Funding Rate Fade (weight: 10%) ──────────────────────────────────────
    # Extreme positive funding = longs paying shorts = fade long, go short
    # Extreme negative funding = shorts paying longs = fade short, go long
    components["funding_rate"] = funding_rate
    funding_pct = funding_rate * 100  # Convert to percentage
    if funding_pct > HL_PERPS_FUNDING_FADE_THRESHOLD:
        short_score += min(10.0, funding_pct * 100)  # Fade the longs
        components["funding_signal"] = "short_fade"
    elif funding_pct < -HL_PERPS_FUNDING_FADE_THRESHOLD:
        long_score += min(10.0, abs(funding_pct) * 100)  # Fade the shorts
        components["funding_signal"] = "long_fade"

    # ── 1h Price Momentum (weight: 5%) ───────────────────────────────────────
    if len(closes) >= 2:
        mom_1h = (closes[-1] - closes[-2]) / closes[-2] * 100
        components["momentum_1h"] = mom_1h
        if mom_1h > 1.5:
            long_score += 5.0
        elif mom_1h < -1.5:
            short_score += 5.0

    # ── Momentum Acceleration (2nd derivative — OpenAlice) ────────────────────
    # Detects when momentum is DECELERATING — a warning that the trend is
    # exhausting.  Formula: accel = mom_recent - mom_prior.  If momentum is
    # decelerating in the signal direction, apply a penalty.  If accelerating,
    # apply a small bonus.  Uses 4-candle lookback to compare mom_now vs
    # mom_4_candles_ago.  Safely degrades if not enough data.
    if len(closes) >= 6:
        mom_now = (closes[-1] - closes[-2]) / closes[-2] * 100
        mom_prior = (closes[-5] - closes[-6]) / closes[-6] * 100 if closes[-6] != 0 else 0
        accel = mom_now - mom_prior  # positive = accelerating, negative = decelerating
        components["momentum_accel"] = round(accel, 3)

        # Deceleration penalty: momentum was moving in signal direction but is now fading
        if accel < -0.5 and mom_now > 0:  # Was bullish, now decelerating
            long_score -= min(5.0, abs(accel) * 1.5)  # Penalize long entries
            components["accel_signal"] = f"long_decel-{min(5.0, abs(accel) * 1.5):.1f}"
        elif accel > 0.5 and mom_now < 0:  # Was bearish, now decelerating (from short perspective)
            short_score -= min(5.0, abs(accel) * 1.5)  # Penalize short entries
            components["accel_signal"] = f"short_decel-{min(5.0, abs(accel) * 1.5):.1f}"

        # Acceleration bonus: momentum is building
        if accel > 0.5 and mom_now > 0:  # Bullish and accelerating
            long_score += min(3.0, accel * 0.8)
            components["accel_signal"] = f"long_accel+{min(3.0, accel * 0.8):.1f}"
        elif accel < -0.5 and mom_now < 0:  # Bearish and accelerating
            short_score += min(3.0, abs(accel) * 0.8)
            components["accel_signal"] = f"short_accel+{min(3.0, abs(accel) * 0.8):.1f}"

    # ── Determine direction and final score ──────────────────────────────────
    # Enforce RSI sticky vetoes BEFORE trend filter — downstream indicators
    # (EMA cross, MACD, volume, BB) may have added points back after the veto.
    # This clamp ensures the veto is absolute regardless of other signals.
    if _rsi_long_vetoed:
        long_score = 0.0
    if _rsi_short_vetoed:
        short_score = 0.0

    # Apply Trend Filter Constraints
    if trend == "bearish":
        long_score = 0.0  # Do not long below EMA 50
    elif trend == "bullish":
        short_score = 0.0 # Do not short above EMA 50

    if long_score > short_score and long_score >= HL_PERPS_MIN_SCORE:
        # Normalize to 0–100
        final_score = min(100.0, long_score)
        return final_score, "long", components
    elif short_score > long_score and short_score >= HL_PERPS_MIN_SCORE:
        final_score = min(100.0, short_score)
        return final_score, "short", components
    else:
        return max(long_score, short_score), "none", components


# ─────────────────────────────────────────────────────────────────────────────
# Main Scanner
# ─────────────────────────────────────────────────────────────────────────────

class HLPerpsScanner:
    """
    Scans Hyperliquid perp markets for directional trading opportunities.
    Runs as a background daemon thread in main.py.

    Target: $500/day net profit from perps trading.
    Strategy: High-frequency directional scalps (3× leverage, 6% TP, 2.5% SL)
              + funding rate fade trades on extreme funding coins.
    """

    def __init__(self, hl_executor=None):
        global _global_scanner
        _global_scanner = self
        
        self.enabled = HL_PERPS_ENABLED
        self.hl_executor = hl_executor  # HyperliquidExecutor instance
        self._info = None
        self._initialized = False
        self._lock = threading.Lock()

        # State
        self.scan_count: int = 0
        self.signals_generated: int = 0
        self.trades_executed: int = 0
        self.daily_pnl: float = 0.0
        self.daily_pnl_reset_date: str = ""
        self.opens_today: int = 0  # v32: daily churn cap counter (resets midnight UTC)
        self.loss_cooldowns: dict[str, float] = {}  # coin → timestamp of last loss
        self.reentry_cooldowns: dict[str, float] = {} # coin → timestamp of last close
        self.emergency_cooldowns: dict[str, float] = {}  # coin → timestamp of emergency SL-fail close
        self.last_signals: list[PerpSignal] = []
        self.pending_retracements: dict[str, dict] = {}  # coin -> {"signal": PerpSignal, "target_px": float, "expires_at": float}
        
        _STATE_DIR.mkdir(parents=True, exist_ok=True)
        self._load_pending_retracements()

        # Stats
        self.total_wins: int = 0
        self.total_losses: int = 0
        self.total_pnl: float = 0.0
        # ── Auto-Blacklist state ───────────────────────────────────────────────
        # coin → {"wins": int, "losses": int, "last_updated": float}
        self._coin_perf: dict[str, dict] = {}
        # coin → unix timestamp when the ban expires
        self._autoban_until: dict[str, float] = {}
        self._load_coin_perf()

        # ── API Rate-Limit Protection ─────────────────────────────────────────
        # Cache meta() responses for 30s to stay well under HL's 1200 weight/min limit.
        self._meta_cache: dict = {}
        self._meta_cache_ts: float = 0.0
        self._META_CACHE_TTL: float = 30.0  # seconds
        # Cache meta_and_asset_ctxs() for momentum pre-filter (60s TTL)
        # Provides dayNtlVlm, openInterest, markPx, prevDayPx per coin in one call.
        self._asset_ctxs_cache: dict[str, dict] = {}
        self._asset_ctxs_cache_ts: float = 0.0
        self._ASSET_CTXS_TTL: float = 60.0  # seconds

        # ── Correlation Guard: 1h close price history per coin ───────────────
        # Stores last 30 close prices per coin for Pearson correlation.
        # Only used pre-execution to block correlated positions.
        self._price_history: dict[str, deque] = {}  # coin → deque(maxlen=30)
        self._CORR_THRESHOLD: float = float(os.getenv("HL_PERPS_CORR_THRESHOLD", "0.85"))

        # ── Dollar-Volume Share Change tracking ─────────────────────────────
        # Stores prior-cycle dollar volume share per coin to detect change.
        self._prior_dvol_share: dict[str, float] = {}

        _STATE_DIR.mkdir(parents=True, exist_ok=True)

        if self.enabled:
            self._init_api()

    def _api_call(self, func, *args, **kwargs):
        """Execute an HL Info API call with exponential backoff on 429."""
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                err = str(e).lower()
                if any(k in err for k in ("429", "rate limit", "too many")) and attempt < max_retries:
                    sleep_t = 2 ** attempt
                    logger.warning(f"HLPerpsScanner API rate limit (attempt {attempt}/{max_retries}), retrying in {sleep_t}s")
                    time.sleep(sleep_t)
                else:
                    raise

    @staticmethod
    def _pearson_correlation(a: list[float], b: list[float]) -> Optional[float]:
        """Compute Pearson correlation between two price series.

        Returns None if series are too short or have zero variance.
        Pure Python — no numpy dependency.
        """
        n = min(len(a), len(b))
        if n < 10:
            return None
        a, b = a[-n:], b[-n:]
        mean_a = sum(a) / n
        mean_b = sum(b) / n
        cov = sum((a[i] - mean_a) * (b[i] - mean_b) for i in range(n)) / n
        std_a = math.sqrt(sum((x - mean_a) ** 2 for x in a) / n)
        std_b = math.sqrt(sum((x - mean_b) ** 2 for x in b) / n)
        if std_a == 0 or std_b == 0:
            return None
        return cov / (std_a * std_b)

    def _record_price_history(self, coin: str, close_price: float) -> None:
        """Append the latest 1h close to the price history ring buffer.

        Used by the Correlation Guard to compute inter-asset correlations.
        """
        if coin not in self._price_history:
            self._price_history[coin] = deque(maxlen=30)
        self._price_history[coin].append(close_price)

    def _get_meta_cached(self) -> dict:
        """Return cached meta() response, refreshing every 30 seconds."""
        now = time.monotonic()
        if now - self._meta_cache_ts > self._META_CACHE_TTL or not self._meta_cache:
            try:
                meta = self._api_call(self._info.meta)
                if meta:
                    self._meta_cache = meta
                    self._meta_cache_ts = now
            except Exception as e:
                logger.warning(f"HLPerpsScanner: meta() refresh failed (using stale cache): {e}")
        return self._meta_cache

    def _init_api(self) -> None:
        """Initialize the Hyperliquid Info API (read-only, no keys needed)."""
        try:
            from hyperliquid.info import Info
            self._info = Info("https://api.hyperliquid.xyz", skip_ws=True)
            # Quick connectivity test (also primes the cache)
            meta = self._api_call(self._info.meta)
            self._meta_cache = meta
            self._meta_cache_ts = time.monotonic()
            n_perps = len(meta.get("universe", []))
            self._initialized = True
            logger.info(
                f"✅ HLPerpsScanner initialized | {n_perps} perps available | "
                f"scan_interval={HL_PERPS_SCAN_INTERVAL}s | "
                f"filter={HL_PERPS_MIN_SCORE} → exec={HL_PERPS_EXEC_SCORE} | leverage={HL_PERPS_LEVERAGE}x"
            )
        except ImportError:
            logger.error("❌ hyperliquid-python-sdk not installed — pip install hyperliquid-python-sdk")
            self.enabled = False
        except Exception as e:
            logger.error(f"❌ HLPerpsScanner init failed: {e}")
            self.enabled = False

    def _get_candles(self, coin: str, interval: str = "1h", lookback_hours: int = 72) -> list[dict]:
        """Fetch OHLCV candles for a coin (with retry wrapper)."""
        try:
            now_ms = int(time.time() * 1000)
            start_ms = now_ms - lookback_hours * 3600 * 1000
            candles = self._api_call(self._info.candles_snapshot, coin, interval, start_ms, now_ms)
            return candles or []
        except Exception as e:
            logger.debug(f"HLPerpsScanner: candle fetch failed for {coin}: {e}")
            return []

    def _get_funding_rate(self, coin: str) -> float:
        """Get current funding rate for a coin (per 8h) from cached meta."""
        try:
            meta = self._get_meta_cached()
            for asset in meta.get("universe", []):
                if asset.get("name", "").upper() == coin.upper():
                    return float(asset.get("funding", 0))
            return 0.0
        except Exception:
            return 0.0

    def _get_all_funding_rates(self) -> dict[str, float]:
        """Fetch all funding rates from a single cached meta() call."""
        try:
            meta = self._get_meta_cached()
            return {
                asset["name"].upper(): float(asset.get("funding", 0))
                for asset in meta.get("universe", [])
                if asset.get("name")
            }
        except Exception as e:
            logger.debug(f"HLPerpsScanner: funding rate fetch failed: {e}")
            return {}

    def _get_asset_ctxs_cached(self) -> dict[str, dict]:
        """
        Return a coin->ctx dict from meta_and_asset_ctxs(), refreshed every 60s.
        Each ctx contains: funding, openInterest, prevDayPx, dayNtlVlm,
        markPx, midPx, dayBaseVlm.
        Used for momentum pre-filter: rank all 230 coins by 24h price change
        before running the expensive per-coin candle + indicator pipeline.
        Single API call replaces N individual price lookups.
        """
        now = time.monotonic()
        if now - self._asset_ctxs_cache_ts > self._ASSET_CTXS_TTL or not self._asset_ctxs_cache:
            try:
                result = self._api_call(self._info.meta_and_asset_ctxs)
                if result and len(result) >= 2:
                    meta, ctxs = result[0], result[1]
                    new_cache: dict[str, dict] = {}
                    for asset, ctx in zip(meta.get("universe", []), ctxs):
                        name = asset.get("name", "").upper()
                        if name and ctx:
                            new_cache[name] = ctx
                    self._asset_ctxs_cache = new_cache
                    self._asset_ctxs_cache_ts = now
            except Exception as e:
                logger.debug(f"HLPerpsScanner: asset_ctxs refresh failed (using stale): {e}")
        return self._asset_ctxs_cache

    def _rank_coins_by_momentum(self, coins: list[str]) -> list[str]:
        """
        Re-order coins by absolute 24h price change blended with log-volume.
        Inspired by OpenAlice cross-sectional momentum ranking: scan the most
        active, trending coins first each cycle so the best setups are found
        even when the 100-coin cap truncates the tail.
        Coins with zero volume (delisted/illiquid) are pushed to the end.
        Falls back to original order if ctxs unavailable.
        """
        ctxs = self._get_asset_ctxs_cached()
        if not ctxs:
            return coins
        scored: list[tuple[str, float]] = []
        for coin in coins:
            ctx = ctxs.get(coin)
            if not ctx:
                scored.append((coin, 0.0))
                continue
            try:
                mark = float(ctx.get("markPx") or 0)
                prev = float(ctx.get("prevDayPx") or 0)
                ntl_vlm = float(ctx.get("dayNtlVlm") or 0)
                if prev > 0 and ntl_vlm > 10_000:  # min $10k volume to qualify
                    chg_pct = abs((mark - prev) / prev * 100)
                    # 70% price momentum + 30% log-volume rank
                    vol_score = math.log10(max(ntl_vlm, 1))
                    momentum = 0.7 * chg_pct + 0.3 * vol_score
                else:
                    momentum = 0.0
            except (TypeError, ValueError, ZeroDivisionError):
                momentum = 0.0
            scored.append((coin, momentum))
        scored.sort(key=lambda x: x[1], reverse=True)
        return [c for c, _ in scored]

    def _goal_frequency_params(self) -> dict:
        """
        Merge env defaults with daily-goal adaptive overrides.

        Goal ladder (README): Phase 1 $500/day → Phase 4 $10k+/day.
        Behind pace → slightly lower exec bar + shorter cooldowns + more size.
        Goal hit → protect/bank-it (higher bar, fewer slots).
        """
        params = {
            "exec_score": HL_PERPS_EXEC_SCORE,
            "reentry_cooldown_min": HL_PERPS_REENTRY_COOLDOWN_MIN,
            "loss_cooldown_min": HL_PERPS_LOSS_COOLDOWN_MIN,
            "max_positions": HL_PERPS_MAX_POSITIONS,
            "size_multiplier": 1.0,
            "mode": "normal",
            "progress_pct": 0.0,
            "remaining_usd": 0.0,
            "behind_pace": False,
        }
        try:
            from core.daily_goal_engine import get_daily_goal_engine
            ov = get_daily_goal_engine().get_hl_perps_config_overrides()
            params["exec_score"] = max(
                52.0, HL_PERPS_EXEC_SCORE + float(ov.get("exec_score_delta") or 0.0)
            )
            if ov.get("reentry_cooldown_min") is not None:
                params["reentry_cooldown_min"] = int(ov["reentry_cooldown_min"])
            if ov.get("loss_cooldown_min") is not None:
                params["loss_cooldown_min"] = int(ov["loss_cooldown_min"])
            if ov.get("max_positions") is not None:
                params["max_positions"] = max(1, int(ov["max_positions"]))
            params["size_multiplier"] = float(ov.get("size_multiplier") or 1.0)
            params["mode"] = str(ov.get("mode") or "normal")
            params["progress_pct"] = float(ov.get("progress_pct") or 0.0)
            params["remaining_usd"] = float(ov.get("remaining_usd") or 0.0)
            params["behind_pace"] = bool(ov.get("behind_pace"))
        except Exception as e:
            logger.debug(f"[HL-PERPS] goal frequency params unavailable: {e}")
        return params

    def _is_on_cooldown(self, coin: str) -> bool:
        """Check if a coin is in loss / re-entry / emergency cooldown."""
        now = time.time()
        freq = self._goal_frequency_params()
        reentry_min = int(freq["reentry_cooldown_min"])
        loss_min = int(freq["loss_cooldown_min"])

        # 0. Auto-blacklist (performance-based dynamic ban)
        if HL_PERPS_AUTOBAN_ENABLED and coin in self._autoban_until:
            if now < self._autoban_until[coin]:
                remaining_h = (self._autoban_until[coin] - now) / 3600
                logger.debug(
                    f"[AUTO-BAN] {coin} banned for {remaining_h:.1f}h more "
                    f"(low WR) — skip"
                )
                return True
            else:
                # Ban expired — remove and allow re-evaluation
                del self._autoban_until[coin]
                logger.info(f"[AUTO-BAN] {coin} ban expired — re-entering watchlist")
        # 1. Emergency cooldown (SL place-fail micro-loop — was 3–5s AAVE spam)
        if coin in getattr(self, "emergency_cooldowns", {}):
            elapsed = now - self.emergency_cooldowns[coin]
            if elapsed < HL_PERPS_EMERGENCY_COOLDOWN_MIN * 60:
                return True

        # 2. Universal re-entry throttle (goal-adaptive; base ~12 min)
        if coin in getattr(self, "reentry_cooldowns", {}):
            elapsed_reentry = now - self.reentry_cooldowns[coin]
            if elapsed_reentry < reentry_min * 60:
                return True

        # 3. Loss cooldown (goal-adaptive)
        if coin in self.loss_cooldowns:
            elapsed_loss = now - self.loss_cooldowns[coin]
            if elapsed_loss < loss_min * 60:
                return True

        return False

    def record_trade_outcome(self, coin: str, won: bool) -> None:
        """
        Record a closed trade outcome for a coin and auto-ban it if its
        rolling win rate falls below the threshold.

        Called by hyperliquid_executor._inject_scanner_cooldown() after every close.
        """
        if not HL_PERPS_AUTOBAN_ENABLED:
            return
        coin = coin.upper()
        perf = self._coin_perf.setdefault(coin, {"wins": 0, "losses": 0, "last_updated": time.time()})
        if won:
            perf["wins"] += 1
        else:
            perf["losses"] += 1
        perf["last_updated"] = time.time()
        total = perf["wins"] + perf["losses"]
        wr = perf["wins"] / total if total > 0 else 1.0
        # Evaluate ban eligibility
        if (
            total >= HL_PERPS_AUTOBAN_MIN_TRADES
            and wr < HL_PERPS_AUTOBAN_WR_THRESHOLD
            and coin not in self._autoban_until
        ):
            ban_expires = time.time() + HL_PERPS_AUTOBAN_HOURS * 3600
            self._autoban_until[coin] = ban_expires
            logger.warning(
                f"🚫 [AUTO-BAN] {coin} auto-banned for {HL_PERPS_AUTOBAN_HOURS:.0f}h "
                f"| trades={total} | WR={wr*100:.0f}% < {HL_PERPS_AUTOBAN_WR_THRESHOLD*100:.0f}% threshold"
            )
        self._save_coin_perf()

    def _load_coin_perf(self) -> None:
        """Load coin performance stats and active bans from disk on startup."""
        try:
            _STATE_DIR.mkdir(parents=True, exist_ok=True)
            if not _COIN_PERF_FILE.exists():
                return
            raw = json.loads(_COIN_PERF_FILE.read_text(encoding="utf-8"))
            self._coin_perf = raw.get("coin_perf", {})
            # Restore active bans (skip expired ones)
            now = time.time()
            for coin, expires in raw.get("autoban_until", {}).items():
                if expires > now:
                    self._autoban_until[coin] = expires
                    remaining_h = (expires - now) / 3600
                    logger.info(
                        f"[AUTO-BAN] {coin} ban restored from disk — {remaining_h:.1f}h remaining"
                    )
            if self._autoban_until:
                logger.info(
                    f"[AUTO-BAN] {len(self._autoban_until)} active bans loaded: "
                    f"{', '.join(self._autoban_until.keys())}"
                )
        except Exception as e:
            logger.warning(f"[AUTO-BAN] Failed to load coin perf state: {e}")

    def _save_coin_perf(self) -> None:
        """Persist coin performance stats and active bans to disk."""
        try:
            _STATE_DIR.mkdir(parents=True, exist_ok=True)
            _COIN_PERF_FILE.write_text(
                json.dumps(
                    {"coin_perf": self._coin_perf, "autoban_until": self._autoban_until},
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning(f"[AUTO-BAN] Failed to save coin perf state: {e}")

    def _check_daily_reset(self) -> None:
        """Reset daily PnL and the opens-per-day counter at midnight UTC."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if today != self.daily_pnl_reset_date:
            if self.daily_pnl != 0:
                logger.info(f"HLPerpsScanner: daily PnL reset (was ${self.daily_pnl:+.2f})")
            if self.opens_today:
                logger.info(f"HLPerpsScanner: opens/day reset (was {self.opens_today})")
            self.daily_pnl = 0.0
            self.opens_today = 0
            self.daily_pnl_reset_date = today

    def get_edge_size_multiplier(self, coin: str) -> float:
        """v32 per-coin edge sizing — scale size by realized expectancy.

        Uses the win/loss record already persisted in hl_coin_perf.json (autoban
        state). Coins with a proven positive record scale up toward
        HL_PERPS_EDGE_SIZE_MAX; chronic underperformers scale down toward
        HL_PERPS_EDGE_SIZE_MIN. Below HL_PERPS_EDGE_MIN_TRADES → neutral 1.0.

        Mapping: wr 0.30 → EDGE_SIZE_MIN, wr 0.50 → 1.0, wr 0.70+ → EDGE_SIZE_MAX
        (linear in between). The 30% floor aligns with the autoban threshold —
        anything below it gets banned outright, so sizing only shades the middle.
        """
        if not HL_PERPS_EDGE_SIZING_ENABLED:
            return 1.0
        perf = self._coin_perf.get(coin.upper())
        if not perf:
            return 1.0
        wins = int(perf.get("wins", 0))
        losses = int(perf.get("losses", 0))
        total = wins + losses
        if total < HL_PERPS_EDGE_MIN_TRADES:
            return 1.0
        wr = wins / total
        lo, hi = HL_PERPS_EDGE_SIZE_MIN, HL_PERPS_EDGE_SIZE_MAX
        if wr <= 0.30:
            mult = lo
        elif wr >= 0.70:
            mult = hi
        elif wr < 0.50:
            # 0.30→0.50 maps lo→1.0
            mult = lo + (wr - 0.30) / 0.20 * (1.0 - lo)
        else:
            # 0.50→0.70 maps 1.0→hi
            mult = 1.0 + (wr - 0.50) / 0.20 * (hi - 1.0)
        return round(mult, 3)

    def scan_coin(self, coin: str, funding_rate: float) -> Optional[PerpSignal]:
        """
        Scan a single perp market and return a signal if one exists.
        Upgraded to Hourly/Daily Multi-Timeframe (MTF) logic for institutional safety.

        Args:
            coin: Coin symbol (e.g., "BTC")
            funding_rate: Current funding rate per 8h (pre-fetched for efficiency)

        Returns:
            PerpSignal if a trade setup is found, None otherwise.
        """
        if not self._initialized:
            return None

        # Cooldown check
        if self._is_on_cooldown(coin):
            return None

        # Fetch MTF candles: 1h for precise entry, 1d for macro trend confirmation
        candles_1h = self._get_candles(coin, "1h", 120)  # 5 days of 1h
        candles_1d = self._get_candles(coin, "1d", 1440) # 60 days of 1d

        if len(candles_1h) < 35 or len(candles_1d) < 10:
            return None

        closes_1h = [float(c["c"]) for c in candles_1h]
        volumes_1h = [float(c["v"]) for c in candles_1h]
        closes_1d = [float(c["c"]) for c in candles_1d]
        
        current_price = closes_1h[-1]

        # Record close for Correlation Guard (OpenAlice)
        self._record_price_history(coin, current_price)

        if current_price <= 0:
            return None

        # ── Macro Trend Filter (1d EMA) ──────────────────────────────────────
        # We only trade IN THE DIRECTION of the daily trend to protect capital.
        ema9_1d = _ema(closes_1d, 9)
        ema21_1d = _ema(closes_1d, 21)
        macro_trend = "neutral"
        if ema9_1d and ema21_1d:
            if ema9_1d > ema21_1d:
                macro_trend = "bullish"
            elif ema9_1d < ema21_1d:
                macro_trend = "bearish"

        # Score the market on the 1h timeframe
        score, direction, components = _score_signal(closes_1h, volumes_1h, funding_rate)

        if direction == "none" or score < HL_PERPS_MIN_SCORE:
            return None

        # Shorts disabled until short WR recovers (live CSV: 12.5%)
        if HL_PERPS_LONG_ONLY and direction == "short":
            return None

        # ── Institutional Capital Protection: Macro Trend Alignment ──────────
        # Reject trades that fight the daily trend.
        if direction == "long" and macro_trend == "bearish":
            logger.debug(f"[HL-PERPS] {coin}: VETOED LONG — Fighting daily bearish trend")
            return None
        if direction == "short" and macro_trend == "bullish":
            logger.debug(f"[HL-PERPS] {coin}: VETOED SHORT — Fighting daily bullish trend")
            return None
        components["macro_trend"] = macro_trend

        # ── Open Interest Confirmation (from cached asset_ctxs) ────────────────
        # Rising OI + price rise = real trend (new money entering).
        # Rising OI + price fall = real downtrend.
        # Falling OI + price move = short-covering / profit-taking (weaker signal).
        # Uses the already-fetched asset_ctxs cache — zero extra API calls.
        try:
            ctxs = self._get_asset_ctxs_cached()
            ctx = ctxs.get(coin)
            if ctx:
                oi = float(ctx.get("openInterest") or 0)
                prev_px = float(ctx.get("prevDayPx") or 0)
                mark_px = float(ctx.get("markPx") or current_price)
                ntl_vlm = float(ctx.get("dayNtlVlm") or 0)
                # OI confirmation: high OI + price moving in signal direction
                if oi > 0 and prev_px > 0:
                    px_chg = (mark_px - prev_px) / prev_px  # 24h price change
                    # Normalize OI by 24h volume to get OI/Volume ratio
                    oi_vol_ratio = oi * mark_px / max(ntl_vlm, 1) if ntl_vlm > 0 else 0
                    if direction == "long" and px_chg > 0.01:  # Price up >1% with OI
                        oi_boost = min(8.0, px_chg * 100 * 0.5)  # Up to +8 pts
                        score += oi_boost
                        components["oi_confirmation"] = f"bullish+{oi_boost:.1f}"
                    elif direction == "short" and px_chg < -0.01:  # Price down >1% with OI
                        oi_boost = min(8.0, abs(px_chg) * 100 * 0.5)
                        score += oi_boost
                        components["oi_confirmation"] = f"bearish+{oi_boost:.1f}"
                    elif oi_vol_ratio < 0.1:  # Very low OI vs volume = thin market
                        score -= 5.0  # Penalise illiquid setups
                        components["oi_confirmation"] = "thin_market-5"
                    else:
                        components["oi_confirmation"] = "neutral"
        except Exception as _oi_err:
            logger.debug(f"[HL-PERPS] {coin}: OI confirmation failed: {_oi_err}")

        # ── Dollar-Volume Share Change (OpenAlice institutional signal) ──────
        # Detects coins gaining an outsized share of total market volume.
        # A coin going from 0.5% to 2% of total volume = institutional
        # accumulation, even if price hasn't moved yet.  Uses the same
        # asset_ctxs cache — zero extra API calls.
        try:
            ctxs = self._get_asset_ctxs_cached()
            ctx = ctxs.get(coin)
            if ctx:
                coin_dvol = float(ctx.get("dayNtlVlm") or 0)
                total_dvol = sum(float(c.get("dayNtlVlm") or 0) for c in ctxs.values())
                if total_dvol > 0 and coin_dvol > 0:
                    current_share = coin_dvol / total_dvol
                    prior_share = self._prior_dvol_share.get(coin, current_share)
                    share_change = current_share - prior_share
                    self._prior_dvol_share[coin] = current_share
                    components["dvol_share"] = round(current_share * 100, 3)  # % of total
                    components["dvol_share_change"] = round(share_change * 100, 4)  # pp change

                    # Significant share gain = institutional accumulation signal
                    if share_change > 0.002:  # Gained >0.2 percentage points
                        dvol_boost = min(5.0, share_change * 1000)  # Up to +5 pts
                        score += dvol_boost
                        components["dvol_signal"] = f"accumulation+{dvol_boost:.1f}"
                    elif share_change < -0.003:  # Lost >0.3 pp = distribution
                        score -= 2.0
                        components["dvol_signal"] = "distribution-2"
        except Exception as _dvol_err:
            logger.debug(f"[HL-PERPS] {coin}: DVolShare calculation failed: {_dvol_err}")

        # ── Elliott Wave / ECC Pattern Recognition ───────────────────────────
        # ECC (Elliott Crypto Cycle) relies on 5-wave impulse and 3-wave correction.
        # We use RSI divergence and MACD histogram to identify wave 3/5 tops and wave C bottoms.
        # If we are in a bullish macro trend, we look for wave C bottoms (oversold RSI + bullish divergence) to enter Longs.
        ecc_wave_boost = 0.0
        ecc_wave_detected = "none"

        try:
            import pandas as pd
            from strategies.indicators import run_all_indicators, detect_divergence, _manual_rsi
            
            # Detect ECC Wave C Bottom (Bullish) or Wave 5 Top (Bearish)
            rsi_1h = _rsi(closes_1h, 14)
            macd_line, sig_line, hist = _macd(closes_1h)
            
            if direction == "long" and rsi_1h and rsi_1h < 40 and hist and hist > 0:
                # Potential Wave C bottom turning into Wave 1
                ecc_wave_detected = "wave_c_bottom"
                ecc_wave_boost = 15.0
            elif direction == "short" and rsi_1h and rsi_1h > 60 and hist and hist < 0:
                # Potential Wave 5 top turning into Wave A
                ecc_wave_detected = "wave_5_top"
                ecc_wave_boost = 15.0
                
            components["ecc_wave"] = ecc_wave_detected
            score += ecc_wave_boost

        except Exception as e:
            logger.debug(f"[HL-PERPS] {coin}: ECC Wave analysis failed: {e}")

        # ── 29-Indicator TA Confirmation Gate (1h) ───────────────────────────
        # Blend the full 29-indicator engine from strategies/indicators.py
        # with the built-in 8-indicator HL score for higher-quality entries.
        # Final score = 60% HL score + 40% TA29 average
        # Direction must AGREE — both systems must confirm LONG or SHORT.
        try:
            # import already done above if ECC succeeded, but just in case
            import pandas as pd
            from strategies.indicators import run_all_indicators, detect_divergence, _manual_rsi

            # Build DataFrame from candle data
            highs_1h = [float(c["h"]) for c in candles_1h]
            lows_1h = [float(c["l"]) for c in candles_1h]
            opens_1h = [float(c["o"]) for c in candles_1h]
            df = pd.DataFrame({
                "open": opens_1h, "high": highs_1h, "low": lows_1h,
                "close": closes_1h, "volume": volumes_1h,
            })

            ta29 = run_all_indicators(df)
            ta29_avg = (ta29.trend_score + ta29.momentum_score + ta29.volume_score) / 3.0

            # Directional agreement check
            if direction == "long" and ta29.trend_score < 35:
                logger.debug(
                    f"[HL-PERPS] {coin}: HL says LONG (score={score:.0f}) but "
                    f"TA29 trend={ta29.trend_score:.0f} < 35 — VETOED"
                )
                return None
            elif direction == "short" and ta29.trend_score > 65:
                logger.debug(
                    f"[HL-PERPS] {coin}: HL says SHORT (score={score:.0f}) but "
                    f"TA29 trend={ta29.trend_score:.0f} > 65 — VETOED"
                )
                return None

            # Blend scores: 60% HL built-in + 40% TA29
            original_score = score
            score = 0.6 * score + 0.4 * ta29_avg

            # Divergence bonus
            try:
                rsi_series = [_manual_rsi(closes_1h[:i+1]) for i in range(len(closes_1h)-1, max(len(closes_1h)-15, 13), -1)]
                rsi_series = [r for r in rsi_series if r is not None]
                if len(rsi_series) >= 5 and len(closes_1h) >= 15:
                    div = detect_divergence(closes_1h[-15:], rsi_series[-15:] if len(rsi_series) >= 15 else rsi_series)
                    if div == "bullish" and direction == "long":
                        score += 10.0
                        components["divergence"] = "bullish"
                    elif div == "bearish" and direction == "short":
                        score += 10.0
                        components["divergence"] = "bearish"
            except Exception:
                pass  # Divergence is a bonus, not required

            logger.info(
                f"[HL-PERPS] {coin} TA29 gate: HL={original_score:.0f} + TA29="
                f"(trend={ta29.trend_score:.0f}, mom={ta29.momentum_score:.0f}, "
                f"vol={ta29.volume_score:.0f}, avg={ta29_avg:.0f}) → blended={score:.0f}"
            )
            components["ta29_trend"] = ta29.trend_score
            components["ta29_momentum"] = ta29.momentum_score
            components["ta29_volume"] = ta29.volume_score
            components["ta29_avg"] = ta29_avg

            # Re-check minimum score after blending
            if score < HL_PERPS_MIN_SCORE:
                logger.debug(f"[HL-PERPS] {coin}: blended score {score:.0f} < {HL_PERPS_MIN_SCORE} — filtered")
                return None

        except Exception as _ta29_err:
            # Graceful degradation — use 8-indicator score only
            logger.debug(f"[HL-PERPS] {coin}: TA29 gate unavailable ({_ta29_err}) — using HL score only")

        # ── Fibonacci Precision Entry Gate ────────────────────────────────────
        # Use Fibonacci retracement levels for mathematically sound entries.
        # For LONG: price should be near a Fib support (0.618, 0.5, 0.382)
        # For SHORT: price should be near a Fib resistance (0.236, 0.382)
        # Golden pocket (0.618-0.65) entries get the highest score boost.
        # Fib extensions set take-profit targets instead of fixed percentages.
        fib_tp = None
        fib_sl = None
        fib_zone = "none"
        fib_confidence = 0.0
        try:
            import pandas as pd
            from strategies.fibonacci import check_fibonacci_alignment, FibResult

            # Build DataFrame if not already built (may exist from TA29 gate)
            if 'df' not in dir():
                highs_1h = [float(c["h"]) for c in candles_1h]
                lows_1h = [float(c["l"]) for c in candles_1h]
                opens_1h = [float(c["o"]) for c in candles_1h]
                df = pd.DataFrame({
                    "open": opens_1h, "high": highs_1h, "low": lows_1h,
                    "close": closes_1h, "volume": volumes_1h,
                })

            fib_direction = "buy" if direction == "long" else "sell"
            fib_result = check_fibonacci_alignment(df, current_price, direction=fib_direction)

            fib_zone = fib_result.current_zone
            fib_confidence = fib_result.confidence
            components["fib_zone"] = fib_zone
            components["fib_confidence"] = fib_confidence

            # Score boost based on Fib zone
            if fib_result.aligned:
                if fib_zone == "golden_pocket":
                    score += 20.0  # Strongest mathematical edge
                    components["fib_boost"] = 20
                elif fib_zone in ("fib_618", "fib_500"):
                    score += 15.0
                    components["fib_boost"] = 15
                elif fib_zone in ("fib_382", "fib_786"):
                    score += 10.0
                    components["fib_boost"] = 10
                else:
                    score += 5.0
                    components["fib_boost"] = 5

                logger.info(
                    f"[HL-PERPS] {coin} FIB ALIGNED: zone={fib_zone} | "
                    f"confidence={fib_confidence:.0f} | boost=+{components.get('fib_boost', 0)} | "
                    f"support=${fib_result.nearest_support:.4f} | "
                    f"resistance=${fib_result.nearest_resistance:.4f}"
                )

            # Use Fib levels for mathematically precise TP/SL
            if fib_result.nearest_support > 0 and fib_result.nearest_resistance > 0:
                if direction == "long":
                    # SL just below nearest Fib support, TP at nearest resistance/extension
                    fib_sl = fib_result.nearest_support * 0.995  # 0.5% below support
                    # Use first extension target if available, else resistance
                    if fib_result.take_profit_targets:
                        fib_tp = fib_result.take_profit_targets[0]["price"]
                    else:
                        fib_tp = fib_result.nearest_resistance
                else:
                    # SL just above nearest Fib resistance, TP at nearest support
                    fib_sl = fib_result.nearest_resistance * 1.005  # 0.5% above resistance
                    fib_tp = fib_result.nearest_support

        except Exception as _fib_err:
            logger.debug(f"[HL-PERPS] {coin}: Fibonacci analysis failed ({_fib_err})")

        # Calculate TP/SL prices — prefer Fib-based if available, else fixed %
        if fib_tp and fib_sl and fib_tp > 0 and fib_sl > 0:
            take_profit = fib_tp
            stop_loss = fib_sl
            tp_source = "fib"
        else:
            sl_pct = HL_PERPS_STOP_LOSS_PCT / 100
            tp_pct = HL_PERPS_TAKE_PROFIT_PCT / 100
            if direction == "long":
                stop_loss = current_price * (1 - sl_pct)
                take_profit = current_price * (1 + tp_pct)
            else:
                stop_loss = current_price * (1 + sl_pct)
                take_profit = current_price * (1 - tp_pct)
            tp_source = "fixed"

        # Build reasoning string
        rsi_val = components.get("rsi")
        vol_spike = components.get("volume_spike")
        fund_sig = components.get("funding_signal", "")
        reasoning_parts = [
            f"Macro={components.get('macro_trend', '?')}",
            f"ECC={components.get('ecc_wave', 'none')}",
            f"RSI={rsi_val:.1f}" if rsi_val else "",
            f"EMA={components.get('ema_cross', '?')}",
            f"MACD_hist={components.get('macd_hist', 0):.4f}" if components.get("macd_hist") else "",
            f"vol_spike={vol_spike:.1f}x" if vol_spike else "",
            f"BB={components.get('bb_zone', '?')}",
            f"funding={funding_rate*100:.4f}%/8h",
            f"fade={fund_sig}" if fund_sig else "",
            f"mom_1h={components.get('momentum_1h', 0):.2f}%" if components.get("momentum_1h") else "",
            f"fib={fib_zone}" if fib_zone != "none" else "",
            f"tp_src={tp_source}",
        ]
        reasoning = " | ".join(p for p in reasoning_parts if p)

        # ── Dynamic Volatility Sizing (ATR) ─────────────────────────────────────
        # RED TEAM PATCH: High-beta coins (GRASS, EIGEN) bleed too much if given full size.
        # We now scale position size DOWN and SL/TP bounds UP based on ATR percentage.
        vol_multiplier = 1.0
        try:
            from strategies.volatility_sizer import analyze_volatility
            # analyze_volatility takes ohlcv list
            vol_result = analyze_volatility(ohlcv=candles_1h)
            vol_multiplier = vol_result.multiplier
            
            # If volatility is ultra-high, widen the stop loss so we don't get chopped out
            if vol_result.volatility_zone in ["high", "ultra_high"]:
                if tp_source == "fixed":
                    # Widen the fixed SL/TP for high-beta tokens
                    widen_factor = 1.5 if vol_result.volatility_zone == "ultra_high" else 1.25
                    sl_pct = (HL_PERPS_STOP_LOSS_PCT / 100) * widen_factor
                    tp_pct = (HL_PERPS_TAKE_PROFIT_PCT / 100) * widen_factor
                    
                    if direction == "long":
                        stop_loss = current_price * (1 - sl_pct)
                        take_profit = current_price * (1 + tp_pct)
                    else:
                        stop_loss = current_price * (1 + sl_pct)
                        take_profit = current_price * (1 - tp_pct)
                    tp_source = f"fixed_widened_{widen_factor}x"
        except Exception as e:
            logger.debug(f"[HL-PERPS] {coin} Volatility sizing failed: {e}")

        # ── EV-Aware Kelly Criterion Position Sizing ────────────────────────────
        # RED TEAM PATCH: Kelly sizing now incorporates R/R and estimated win-rate.
        # Formula: f* = (W * R - (1-W)) / R  where R = reward/risk ratio
        # Win-rate estimated from score: score 50 -> 50% WR, score 95 -> 75% WR (linear)
        # If estimated WR < break-even WR, position is capped to 1/max_positions of equity.
        _live_equity = HL_PERPS_BASE_CAPITAL
        if self.hl_executor and self.hl_executor.is_available():
            try:
                _bal = self.hl_executor.get_balance()
                _acct_val = _bal.get("account_value", 0.0) or _bal.get("equity", 0.0)
                if _acct_val and _acct_val > 10.0:
                    _live_equity = float(_acct_val)
            except Exception:
                pass  # Fall back to HL_PERPS_BASE_CAPITAL

        # Compute R/R for this specific signal (using Fib-computed TP/SL)
        _risk = abs(current_price - stop_loss) if stop_loss and current_price else None
        _reward = abs(take_profit - current_price) if take_profit and current_price else None
        _rr = (_reward / _risk) if (_risk and _risk > 0 and _reward) else 1.0

        # Estimate win-rate from score (linear: 50->50%, 95->75%)
        _score_norm = max(0.0, min(1.0, (score - 50.0) / 45.0))
        _est_win_rate = 0.50 + _score_norm * 0.25  # 50% to 75%

        # Break-even win-rate for this R/R
        _breakeven_wr = 1.0 / (_rr + 1.0) if _rr > 0 else 1.0

        # True fractional Kelly: f* = (W*R - (1-W)) / R
        _kelly_fraction = (_est_win_rate * _rr - (1.0 - _est_win_rate)) / _rr if _rr > 0 else 0.0

        # Slot-based minimum (1 slot = 1/max_positions of equity)
        _max_positions_kelly = HL_PERPS_MAX_POSITIONS if HL_PERPS_MAX_POSITIONS > 0 else 6
        min_size = max(10.0, round(_live_equity / _max_positions_kelly, 2))
        max_size = max(min_size, round(_live_equity * 0.40, 2))  # Hard cap: 40% per position

        if _kelly_fraction <= 0:
            # Negative or zero EV -- use minimum slot size only
            kelly_size_usd = min_size
            logger.info(
                f"[HL-PERPS] {coin} EV-KELLY: est_WR={_est_win_rate*100:.1f}% < "
                f"breakeven={_breakeven_wr*100:.1f}% at R/R={_rr:.2f}x -- "
                f"capped to min_size="
            )
        else:
            # Positive EV -- scale by Kelly fraction, bounded by [min_size, max_size]
            kelly_size_usd = _live_equity * _kelly_fraction
            kelly_size_usd = max(min_size, min(kelly_size_usd, max_size))
            logger.debug(
                f"[HL-PERPS] {coin} EV-KELLY: est_WR={_est_win_rate*100:.1f}% "
                f"R/R={_rr:.2f}x f*={_kelly_fraction*100:.1f}% "
                f"-> size="
            )

        # Apply Volatility Multiplier (scales down size for high-beta coins like GRASS)
        kelly_size_usd = kelly_size_usd * vol_multiplier

        # Goal-adaptive size: catch-up / behind pace scales up; protect/bank-it scales down
        try:
            _goal_sz = float(self._goal_frequency_params().get("size_multiplier") or 1.0)
            if _goal_sz != 1.0:
                kelly_size_usd = kelly_size_usd * _goal_sz
        except Exception:
            pass

        # Hard cap: never risk more than max_size in a single position
        kelly_size_usd = min(kelly_size_usd, max_size)

        signal = PerpSignal(
            coin=coin,
            direction=direction,
            score=round(score, 1),
            entry_price=current_price,
            stop_loss_price=round(stop_loss, 6),
            take_profit_price=round(take_profit, 6),
            leverage=HL_PERPS_LEVERAGE,
            position_size_usd=round(kelly_size_usd, 2),
            rsi=rsi_val,
            ema_cross=components.get("ema_cross"),
            macd_signal="buy" if (components.get("macd_hist") or 0) > 0 else "sell",
            volume_spike=vol_spike,
            funding_rate=funding_rate,
            bb_position=components.get("bb_zone"),
            momentum_1h=components.get("momentum_1h"),
            ema_support_px=components.get("ema21"),
            fib_zone=fib_zone,
            fib_confidence=fib_confidence,
            components=components,
            reasoning=reasoning,
        )

        # ── Final execution threshold (post Fib + TA29) ─────────────────────
        # MIN_SCORE is the initial filter to let coins REACH the analysis.
        # EXEC_SCORE is the real bar — only Fib-boosted, TA29-confirmed signals trade.
        # Goal-adaptive: behind $500/day pace lowers bar slightly; protect raises it.
        _exec_threshold = float(self._goal_frequency_params()["exec_score"])
        if score < _exec_threshold:
            logger.info(
                f"[HL-PERPS] {coin} {direction.upper()} score={score:.0f} < exec_threshold={_exec_threshold:.0f} "
                f"(base={HL_PERPS_EXEC_SCORE}, fib={fib_zone}, tp_src={tp_source}) — NEAR MISS, not trading"
            )
            return None

        # ── R/R Ratio Guard (OpenAlice Guard Pipeline) ────────────────────────
        # Reject signals where TP/SL math doesn't make sense.
        # Raised to 1.5x (2026-07-09) — live book had ~28% WR; need higher R/R for +EV.
        MIN_RR_RATIO = HL_PERPS_MIN_RR
        rr = signal.r_r_ratio

        # Sanity: TP must be on the correct side of entry
        if direction == "long" and take_profit <= current_price:
            logger.warning(
                f"[HL-PERPS] {coin} LONG rejected: TP=${take_profit:.4f} ≤ entry=${current_price:.4f} — invalid Fib target"
            )
            return None
        if direction == "short" and take_profit >= current_price:
            logger.warning(
                f"[HL-PERPS] {coin} SHORT rejected: TP=${take_profit:.4f} ≥ entry=${current_price:.4f} — invalid Fib target"
            )
            return None

        if rr < MIN_RR_RATIO:
            logger.info(
                f"[HL-PERPS] {coin} {direction.upper()} R/R={rr:.1f}x < {MIN_RR_RATIO}x — "
                f"rejected (score={score:.0f}, fib={fib_zone})"
            )
            return None

        # ── Correlation Guard (OpenAlice Guard Pipeline) ──────────────────────
        # Prevent concentrated risk: reject a new position if it's >85%
        # correlated with any existing open position.  Uses Pearson correlation
        # on the last 30 close prices.  Only blocks — never overrides other guards.
        if self.hl_executor and hasattr(self.hl_executor, 'positions') and self.hl_executor.positions:
            try:
                coin_hist = self._price_history.get(coin)
                if coin_hist and len(coin_hist) >= 15:
                    for pos_coin in self.hl_executor.positions:
                        if pos_coin == coin:
                            continue
                        pos_hist = self._price_history.get(pos_coin)
                        if pos_hist and len(pos_hist) >= 15:
                            # Pearson correlation on overlapping history
                            n = min(len(coin_hist), len(pos_hist))
                            a = list(coin_hist)[-n:]
                            b = list(pos_hist)[-n:]
                            corr = self._pearson_correlation(a, b)
                            if corr is not None and corr > self._CORR_THRESHOLD:
                                logger.info(
                                    f"[HL-PERPS] {coin} {direction.upper()} REJECTED by "
                                    f"Correlation Guard: corr({coin},{pos_coin})={corr:.2f} "
                                    f"> {self._CORR_THRESHOLD} — too concentrated"
                                )
                                return None
            except Exception as _corr_err:
                logger.debug(f"[HL-PERPS] {coin}: Correlation guard error: {_corr_err}")

        logger.info(
            f"📡 HL PERPS SIGNAL | {direction.upper()} {coin} @ ${current_price:.4f} | "
            f"score={score:.0f} | TP=${take_profit:.4f} ({tp_source}) | SL=${stop_loss:.4f} | "
            f"R/R={rr:.1f}x | fib={fib_zone} | {reasoning}"
        )

        return signal

    def _execute_signal(self, signal: PerpSignal) -> bool:
        """
        Execute a signal via the HyperliquidExecutor.

        Returns True if the trade was placed successfully.
        """
        if self.hl_executor is None:
            logger.debug(f"HLPerpsScanner: no executor — signal for {signal.coin} not executed")
            return False

        if not self.hl_executor.is_available():
            logger.warning("HLPerpsScanner: HL executor not available")
            return False

        # Check daily loss limit — dynamic: 33% of live equity or env var floor
        self._check_daily_reset()
        _eq_for_limit = HL_PERPS_BASE_CAPITAL
        try:
            _bl = self.hl_executor.get_balance()
            _av = _bl.get("account_value", 0.0) or _bl.get("equity", 0.0)
            if _av and _av > 10.0:
                _eq_for_limit = float(_av)
        except Exception:
            pass
        daily_limit = max(HL_PERPS_DAILY_LOSS_LIMIT, round(_eq_for_limit * 0.33, 2))
        if self.daily_pnl <= -daily_limit:
            logger.warning(
                f"🛑 HLPerpsScanner CIRCUIT BREAKER: daily PnL ${self.daily_pnl:.2f} "
                f"hit limit -${daily_limit:.2f} (33% of ${_eq_for_limit:.2f} equity) — halting perps trading"
            )
            return False
        # v32: daily churn cap — 67 opens on 7/22 bled ~$43 of fees against a
        # −$11 gross edge. Quality over quantity, hard stop at N opens/day.
        if HL_PERPS_MAX_OPENS_PER_DAY > 0 and self.opens_today >= HL_PERPS_MAX_OPENS_PER_DAY:
            if self.opens_today == HL_PERPS_MAX_OPENS_PER_DAY:
                logger.warning(
                    f"🚫 HLPerpsScanner DAILY OPEN CAP: {self.opens_today}/"
                    f"{HL_PERPS_MAX_OPENS_PER_DAY} opens used — no new entries until midnight UTC"
                )
            return False

        # Check max positions (goal-adaptive: protect/bank_it reduce slots)
        freq = self._goal_frequency_params()
        max_pos = int(freq["max_positions"])
        active = len(self.hl_executor.positions)
        if active >= max_pos:
            logger.debug(f"HLPerpsScanner: max positions ({max_pos}) reached")
            return False

        # Long-only mode (CSV: shorts ~17% WR)
        if HL_PERPS_LONG_ONLY and signal.direction == "short":
            logger.info(
                f"[HL-PERPS] {signal.coin} SHORT blocked — HL_PERPS_LONG_ONLY=true"
            )
            return False

        coin_u = signal.coin.upper()
        # Hard ban — never open (v31: score+20 soft toxic still let KAITO/APE through)
        if coin_u in HL_PERPS_HARD_BAN_COINS:
            logger.info(
                f"[HL-PERPS] {signal.coin} HARD-BANNED (HL_PERPS_HARD_BAN_COINS) — skip"
            )
            return False

        # Soft toxic: higher score bar only (repeat losers / noisy names)
        exec_floor = float(freq["exec_score"])
        if coin_u in HL_PERPS_TOXIC_COINS and coin_u not in HL_PERPS_HARD_BAN_COINS:
            exec_floor = exec_floor + HL_PERPS_TOXIC_SCORE_BONUS
            if signal.score < exec_floor:
                logger.info(
                    f"[HL-PERPS] {signal.coin} toxic-list: score={signal.score:.0f} "
                    f"< required {exec_floor:.0f} — skip"
                )
                return False

        # Cap margin so notional (margin × lev) stays under hard cap
        lev = max(1, int(signal.leverage or HL_PERPS_LEVERAGE))
        size_usd = min(signal.position_size_usd, HL_PERPS_MAX_POSITION_USD)
        max_margin_for_notional = HL_PERPS_MAX_NOTIONAL_USD / lev
        if size_usd > max_margin_for_notional:
            logger.info(
                f"[HL-PERPS] {signal.coin} size ${size_usd:.2f} → "
                f"${max_margin_for_notional:.2f} (notional cap ${HL_PERPS_MAX_NOTIONAL_USD:.0f})"
            )
            size_usd = round(max_margin_for_notional, 2)

        # ── Winning entry filter (volume floor, blacklist, ATR size cut, toxic zone) ──
        if WINNING_ENTRY_FILTER_ENABLED:
            try:
                from core.hl_scanner_winning_tuning import winning_entry_filter
                from core.winning_risk_manager import get_position_size_multiplier

                day_vol = 0.0
                atr_pct = 0.0
                try:
                    ctxs = self._get_asset_ctxs_cached()
                    ctx = ctxs.get(coin_u) or ctxs.get(signal.coin)
                    if ctx:
                        day_vol = float(ctx.get("dayNtlVlm") or 0)
                except Exception:
                    pass
                try:
                    comps = signal.components or {}
                    # Prefer explicit atr if present; else rough from vol_multiplier inverse
                    if comps.get("atr_pct") is not None:
                        atr_pct = float(comps["atr_pct"])
                except Exception:
                    pass

                validation = winning_entry_filter.validate_entry({
                    "symbol": signal.coin,
                    "current_price": signal.entry_price,
                    "volume_24h_usd": day_vol,
                    "vwap_15m": 0.0,  # optional; 0 = skip VWAP gate
                    "atr_pct": atr_pct,
                    "narrative_score": 0.0,
                    "sl_count_24h": 0,
                    "side": signal.direction,
                })
                if not validation.get("approved"):
                    logger.info(
                        f"[HL-PERPS] {signal.coin} Winning entry blocked: "
                        f"{validation.get('reason')}"
                    )
                    return False
                size_mult = float(validation.get("position_size_multiplier") or 1.0)
                # Toxic-hour size cut (08–14 ET): trade_history 29 −$326 vs +$28 elsewhere
                size_mult *= float(get_position_size_multiplier())
                if size_mult != 1.0:
                    new_size = round(max(10.0, size_usd * size_mult), 2)
                    logger.info(
                        f"[HL-PERPS] {signal.coin} Winning size ×{size_mult:.2f}: "
                        f"${size_usd:.2f} → ${new_size:.2f}"
                    )
                    size_usd = new_size
            except Exception as _win_err:
                logger.debug(f"[HL-PERPS] Winning entry filter error (allowing): {_win_err}")
        # ── v32: per-coin edge sizing — feed proven winners, starve marginal names ──
        try:
            edge_mult = self.get_edge_size_multiplier(coin_u)
            if edge_mult != 1.0:
                new_size = round(max(10.0, size_usd * edge_mult), 2)
                logger.info(
                    f"[HL-PERPS] {signal.coin} Edge size ×{edge_mult:.2f} "
                    f"(realized WR-based): ${size_usd:.2f} → ${new_size:.2f}"
                )
                size_usd = new_size
        except Exception as _edge_err:
            logger.debug(f"[HL-PERPS] Edge sizing error (neutral): {_edge_err}")

        try:
            open_kwargs = dict(
                symbol=signal.coin,
                size_usd=size_usd,
                leverage=signal.leverage,
                gem_score=signal.score,
                stop_loss_price=signal.stop_loss_price,
                take_profit_price=signal.take_profit_price,
            )
            if signal.direction == "long":
                result = self.hl_executor.open_long(**open_kwargs)
            else:
                result = self.hl_executor.open_short(**open_kwargs)

            if result:
                self.trades_executed += 1
                self.opens_today += 1  # v32 daily churn cap counter
                logger.info(
                    f"✅ HLPerpsScanner: {signal.direction.upper()} {signal.coin} executed | "
                    f"size=${size_usd} × {signal.leverage}x | "
                    f"score={signal.score} | "
                    f"SL=${signal.stop_loss_price} TP=${signal.take_profit_price} | "
                    f"opens_today={self.opens_today}/{HL_PERPS_MAX_OPENS_PER_DAY}"
                )
                return True
            else:
                logger.warning(f"HLPerpsScanner: executor returned None for {signal.coin}")
                return False

        except Exception as e:
            logger.warning(f"HLPerpsScanner: execution error for {signal.coin}: {e}")
            return False

    def _add_funding_anomaly_coins(self, funding_rates: dict[str, float]) -> list[str]:
        """
        Add any coin with extreme funding rate to the scan list.
        Extreme funding = fade opportunity regardless of watchlist membership.
        """
        extra = []
        threshold = HL_PERPS_FUNDING_FADE_THRESHOLD / 100  # Convert pct to decimal
        for coin, rate in funding_rates.items():
            if abs(rate) > threshold and coin not in HL_PERPS_WATCHLIST:
                extra.append(coin)
                logger.debug(f"HLPerpsScanner: adding {coin} for funding anomaly ({rate*100:.4f}%/8h)")
        return extra

    def run_cycle(self) -> list[PerpSignal]:
        """
        Run one full scan cycle across the watchlist.

        Returns:
            List of PerpSignal objects that met the entry threshold.
        """
        if not self.enabled or not self._initialized:
            return []

        # ── Autonomous Profit Sweep ──
        # Triggers once the base capital reaches $25k. Sweeps $500 incrementally.
        if self.hl_executor and self.hl_executor.is_available():
            paycheck_wallet = os.getenv("WALLET_ADDRESS_C", "").strip()
            if paycheck_wallet:
                try:
                    balance_info = self.hl_executor.get_balance()
                    withdrawable = balance_info.get("withdrawable", 0.0)
                    if withdrawable >= 25000.0 + HL_PERPS_PROFIT_SWEEP_USD:
                        logger.info(
                            f"💰 [HL-PERPS] Profit Sweeper triggered! "
                            f"Withdrawable (${withdrawable:.2f}) >= $25,000 + Sweep (${HL_PERPS_PROFIT_SWEEP_USD:.2f})"
                        )
                        self.hl_executor.withdraw_profit_usd(HL_PERPS_PROFIT_SWEEP_USD, paycheck_wallet)
                except Exception as e:
                    logger.warning(f"Failed to check/sweep HL profits: {e}")

        self._check_daily_reset()
        self.scan_count += 1
        cycle_start = time.time()

        # ── Time gate (America/New_York) — trade_history(27) worst hours ──
        # Blocks NEW entries only; open positions still managed by executor/trailing.
        if HL_PERPS_BLOCKED_HOURS_ET:
            try:
                from zoneinfo import ZoneInfo
                et_hour = datetime.now(ZoneInfo("America/New_York")).hour
            except Exception:
                et_hour = datetime.now(timezone.utc).hour  # fallback UTC
            if et_hour in HL_PERPS_BLOCKED_HOURS_ET:
                if self.scan_count % 10 == 1:
                    logger.info(
                        f"[HL-PERPS] Time gate: hour={et_hour} ET in blocked set "
                        f"{sorted(HL_PERPS_BLOCKED_HOURS_ET)} — skipping new entries this cycle"
                    )
                self._save_state([])
                return []

        # ── Retracement Sniper: Check pending entries ──
        if self.pending_retracements and self.hl_executor and self.hl_executor.is_available():
            current_time = time.time()
            for coin in list(self.pending_retracements.keys()):
                pending = self.pending_retracements[coin]
                if current_time > pending["expires_at"]:
                    logger.debug(f"Retracement sniper expired for {coin} (no dip detected)")
                    del self.pending_retracements[coin]
                    continue
                
                try:
                    current_px = self.hl_executor.get_price(coin)
                    if not current_px: continue

                    signal = pending["signal"]
                    trigger = False
                    if signal.direction == "long" and current_px <= pending["target_px"]:
                        trigger = True
                    elif signal.direction == "short" and current_px >= pending["target_px"]:
                        trigger = True
                        
                    if trigger:
                        logger.info(f"🎯 RETRACEMENT SNIPER TRIGGERED for {coin}! Target {pending['target_px']} hit at {current_px}.")
                        self._execute_signal(signal)
                        del self.pending_retracements[coin]
                except Exception as e:
                    logger.warning(f"Retracement sniper check failed for {coin}: {e}")

        # Fetch all funding rates in one call (efficiency)
        funding_rates = self._get_all_funding_rates()

        # Build scan list: ALL perps from HL universe (not just watchlist)
        # This dramatically expands opportunity surface from 41 to 230+ coins.
        # Watchlist coins are scanned first (priority), then all remaining perps.
        # Discovery coins are ranked by cross-sectional momentum (OpenAlice pattern):
        # absolute 24h price change × log-volume ensures the most active movers
        # are scanned first, maximising signal quality within the 100-coin cap.
        watchlist_set = set(HL_PERPS_WATCHLIST)
        scan_list = list(HL_PERPS_WATCHLIST)
        all_perps = set(funding_rates.keys())
        remaining = [c for c in sorted(all_perps) if c not in watchlist_set]
        # Rank discovery coins by momentum before appending
        remaining = self._rank_coins_by_momentum(remaining)
        scan_list.extend(remaining)

        signals: list[PerpSignal] = []
        scanned = 0
        near_misses: list[tuple[str, float, str]] = []  # (coin, score, direction)

        watchlist_len = len(HL_PERPS_WATCHLIST)
        active_positions = len(self.hl_executor.positions) if self.hl_executor else 0
        freq = self._goal_frequency_params()
        max_pos = int(freq["max_positions"])
        free_slots = max(0, max_pos - active_positions)
        # Cap spray: free slots AND max-new-per-scan (v31 behind_pace spray fix)
        max_new_per_scan = max(1, int(HL_PERPS_MAX_NEW_PER_SCAN))
        max_new_signals = min(free_slots, max_new_per_scan)
        if self.scan_count % 10 == 1:
            logger.info(
                f"[HL-PERPS] Goal frequency | mode={freq['mode']} | "
                f"progress={freq['progress_pct']:.0f}% | remaining=${freq['remaining_usd']:.0f} | "
                f"behind_pace={freq['behind_pace']} | exec≥{freq['exec_score']:.0f} | "
                f"reentry={freq['reentry_cooldown_min']}m | max_pos={max_pos} | "
                f"max_new/scan={max_new_per_scan} | size_mult={freq['size_multiplier']:.2f}"
            )

        # Cap total scan to 150 coins to balance opportunity vs rate limits
        scan_list = scan_list[:150]

        # ── CRITICAL FIX (trade_history 27 / live 2026-07-17): ────────────────
        # Old logic broke after first signal when max_new_signals<=1:
        #   if len(signals) >= max(max_new_signals, 1): break
        # With full/near-full books that meant ONLY BTC (first watchlist coin)
        # was ever scored — 230+ scans of "1 coins" and zero multi-coin alpha.
        # Correct approach: scan full universe, rank by score, execute top-N only.
        for idx, coin in enumerate(scan_list):
            # Skip if already in a position or pending sniper entry
            if self.hl_executor and coin in self.hl_executor.positions:
                continue
            if coin in self.pending_retracements:
                continue
            # Hard-ban early — no TA / no EXECUTING log noise
            if coin.upper() in HL_PERPS_HARD_BAN_COINS:
                continue

            # Rate-limit: 0.25s delay every 3 non-watchlist coins
            if idx >= watchlist_len and idx % 3 == 0:
                time.sleep(0.25)

            funding_rate = funding_rates.get(coin, 0.0)
            signal = self.scan_coin(coin, funding_rate)
            scanned += 1

            if signal:
                if signal.coin.upper() in HL_PERPS_HARD_BAN_COINS:
                    continue
                signals.append(signal)
                self.signals_generated += 1

        # Sort by score descending — best setups first
        signals.sort(key=lambda s: s.score, reverse=True)
        self.last_signals = signals

        # Execute only what we have room for (0 when full — still scanned above)
        to_execute = signals[: max(0, max_new_signals)]
        if signals and free_slots <= 0:
            logger.warning(
                f"[HL-PERPS] {len(signals)} signals ready but 0 free slots "
                f"(local_positions={active_positions}/{max_pos}). "
                f"If exchange is flat, ghosts are blocking — sync/purge required. "
                f"coins={sorted(list(self.hl_executor.positions.keys())[:12]) if self.hl_executor else []}"
            )
        elif signals and max_new_signals < free_slots and len(signals) > max_new_signals:
            logger.info(
                f"[HL-PERPS] Entry cap: executing top {max_new_signals}/{len(signals)} "
                f"signals (max_new_per_scan={max_new_per_scan}, free_slots={free_slots})"
            )
        for signal in to_execute:
            is_golden = (
                signal.fib_confidence >= 70
                or signal.fib_zone == "golden_pocket"
                or "golden" in (signal.fib_zone or "").lower()
            )
            entry_label = "⚡ GOLDEN POCKET" if is_golden else "✅ SIGNAL"
            logger.info(
                f"{entry_label} — EXECUTING: {signal.direction.upper()} {signal.coin} "
                f"@ ${signal.entry_price:.4f} | score={signal.score:.0f} | "
                f"fib_zone={signal.fib_zone} | fib_conf={signal.fib_confidence:.0f}"
            )
            self._execute_signal(signal)

        elapsed = time.time() - cycle_start
        if signals:
            logger.info(
                f"🔍 HL PERPS SCAN #{self.scan_count}: {scanned} coins | "
                f"{len(signals)} signals | best={signals[0].coin} {signals[0].direction.upper()} "
                f"score={signals[0].score:.0f} | elapsed={elapsed:.1f}s | "
                f"daily_pnl=${self.daily_pnl:+.2f}"
            )
        else:
            logger.info(
                f"🔍 HL PERPS SCAN #{self.scan_count}: {scanned} coins | "
                f"0 signals (min_score={HL_PERPS_MIN_SCORE}) | {elapsed:.1f}s | "
                f"Fib + TA29 gate active"
            )

        self._save_state(signals)
        return signals

    def _save_state(self, signals: list[PerpSignal]) -> None:
        """Persist scanner state for dashboard display."""
        try:
            import json
            
            # Serialize pending retracements
            pending_serializable = {}
            for coin, data in self.pending_retracements.items():
                s = data["signal"]
                pending_serializable[coin] = {
                    "target_px": data["target_px"],
                    "expires_at": data["expires_at"],
                    "signal": {
                        "coin": s.coin,
                        "direction": s.direction,
                        "score": s.score,
                        "entry_price": s.entry_price,
                        "stop_loss_price": s.stop_loss_price,
                        "take_profit_price": s.take_profit_price,
                        "leverage": s.leverage,
                        "position_size_usd": s.position_size_usd,
                        "rsi": s.rsi,
                        "ema_cross": s.ema_cross,
                        "macd_signal": s.macd_signal,
                        "volume_spike": s.volume_spike,
                        "funding_rate": s.funding_rate,
                        "bb_position": s.bb_position,
                        "momentum_1h": s.momentum_1h,
                        "ema_support_px": s.ema_support_px,
                        "fib_zone": s.fib_zone,
                        "fib_confidence": s.fib_confidence,
                        "reasoning": s.reasoning,
                    }
                }
                
            state = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "scan_count": self.scan_count,
                "signals_generated": self.signals_generated,
                "trades_executed": self.trades_executed,
                "daily_pnl": round(self.daily_pnl, 2),
                "opens_today": self.opens_today,
                "opens_today_date": self.daily_pnl_reset_date,
                "max_opens_per_day": HL_PERPS_MAX_OPENS_PER_DAY,
                "daily_loss_limit": max(HL_PERPS_DAILY_LOSS_LIMIT, 50.0),
                "enabled": self.enabled,
                "pending_retracements": pending_serializable,
                "last_signals": [
                    {
                        "coin": s.coin,
                        "direction": s.direction,
                        "score": s.score,
                        "entry_price": s.entry_price,
                        "take_profit": s.take_profit_price,
                        "stop_loss": s.stop_loss_price,
                        "leverage": s.leverage,
                        "rsi": s.rsi,
                        "funding_rate": s.funding_rate,
                        "reasoning": s.reasoning,
                        "r_r_ratio": round(s.r_r_ratio, 2),
                    }
                    for s in signals[:10]
                ],
            }
            _STATE_FILE.write_text(json.dumps(state, indent=2))
        except Exception as e:
            logger.debug(f"HLPerpsScanner: state save failed: {e}")

    def _load_pending_retracements(self) -> None:
        """Load pending retracements from state file on startup."""
        if not _STATE_FILE.exists():
            return
        try:
            import json
            raw = json.loads(_STATE_FILE.read_text())
            # v32: restore opens_today so a restart cannot bypass the daily cap
            try:
                saved_date = str(raw.get("opens_today_date") or "")
                today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                if saved_date == today:
                    self.opens_today = int(raw.get("opens_today") or 0)
                    self.daily_pnl_reset_date = saved_date
                    if self.opens_today:
                        logger.info(
                            f"HLPerpsScanner: restored opens_today={self.opens_today} from state"
                        )
            except Exception:
                pass
            pending_raw = raw.get("pending_retracements", {})
            current_time = time.time()
            
            for coin, data in pending_raw.items():
                if current_time > data.get("expires_at", 0):
                    continue
                    
                s_dict = data.get("signal", {})
                if not s_dict:
                    continue
                    
                signal = PerpSignal(
                    coin=s_dict.get("coin", coin),
                    direction=s_dict.get("direction", "long"),
                    score=s_dict.get("score", 0.0),
                    entry_price=s_dict.get("entry_price", 0.0),
                    stop_loss_price=s_dict.get("stop_loss_price", 0.0),
                    take_profit_price=s_dict.get("take_profit_price", 0.0),
                    leverage=s_dict.get("leverage", HL_PERPS_LEVERAGE),
                    position_size_usd=s_dict.get("position_size_usd", HL_PERPS_MAX_POSITION_USD),
                    rsi=s_dict.get("rsi"),
                    ema_cross=s_dict.get("ema_cross"),
                    macd_signal=s_dict.get("macd_signal"),
                    volume_spike=s_dict.get("volume_spike"),
                    funding_rate=s_dict.get("funding_rate"),
                    bb_position=s_dict.get("bb_position"),
                    momentum_1h=s_dict.get("momentum_1h"),
                    ema_support_px=s_dict.get("ema_support_px"),
                    fib_zone=s_dict.get("fib_zone", "none"),
                    fib_confidence=s_dict.get("fib_confidence", 0.0),
                    reasoning=s_dict.get("reasoning", "")
                )
                
                self.pending_retracements[coin] = {
                    "signal": signal,
                    "target_px": data.get("target_px", 0.0),
                    "expires_at": data.get("expires_at", 0)
                }
            logger.info(f"HLPerpsScanner: loaded {len(self.pending_retracements)} pending retracements from state")
        except Exception as e:
            logger.warning(f"HLPerpsScanner: failed to load pending retracements: {e}")

    def get_status(self) -> dict:
        """Status dict for dashboard/logging."""
        return {
            "enabled": self.enabled,
            "initialized": self._initialized,
            "scan_count": self.scan_count,
            "signals_generated": self.signals_generated,
            "trades_executed": self.trades_executed,
            "daily_pnl": round(self.daily_pnl, 2),
            "opens_today": self.opens_today,
            "max_opens_per_day": HL_PERPS_MAX_OPENS_PER_DAY,
            "daily_loss_limit": max(HL_PERPS_DAILY_LOSS_LIMIT, 50.0),
            "watchlist_size": len(HL_PERPS_WATCHLIST),
            "scan_interval_seconds": HL_PERPS_SCAN_INTERVAL,
            "min_score": HL_PERPS_MIN_SCORE,
            "leverage": HL_PERPS_LEVERAGE,
            "max_position_usd": HL_PERPS_MAX_POSITION_USD,
            "max_positions": HL_PERPS_MAX_POSITIONS,
            "stop_loss_pct": HL_PERPS_STOP_LOSS_PCT,
            "take_profit_pct": HL_PERPS_TAKE_PROFIT_PCT,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Singleton
# ─────────────────────────────────────────────────────────────────────────────
_scanner_instance: Optional[HLPerpsScanner] = None
_scanner_lock = threading.Lock()


def get_hl_perps_scanner(hl_executor=None) -> HLPerpsScanner:
    """Get or create the singleton HLPerpsScanner."""
    global _scanner_instance
    with _scanner_lock:
        if _scanner_instance is None:
            _scanner_instance = HLPerpsScanner(hl_executor=hl_executor)
        elif hl_executor is not None and _scanner_instance.hl_executor is None:
            _scanner_instance.hl_executor = hl_executor
    return _scanner_instance
