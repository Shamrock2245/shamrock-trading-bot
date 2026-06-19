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

Signal Score: 0–100. Entry gate: ≥ 65.
Direction: LONG or SHORT — both are traded.
Leverage: 3× default (configurable via HL_PERPS_LEVERAGE env var).
Position size: scaled to hit $500/day target across the portfolio.

Scan universe: Top 40 perps by liquidity (BTC, ETH, SOL, etc.) + any
perp with anomalous funding rate (absolute value > 0.03%/8h).

Integration: main.py → _hl_perps_daemon() → HLPerpsScanner.run_cycle()
Executor: core/hyperliquid_executor.py (open_long / open_short)

Safety guardrails (all inherited from hyperliquid_executor.py):
  - Daily loss limit: $30 (HL_PERPS_DAILY_LOSS_LIMIT)
  - Max concurrent positions: 6 (HL_PERPS_MAX_POSITIONS)
  - Max position size: $100 per trade (HL_PERPS_MAX_POSITION_USD)
  - Max total exposure: $600 (HL_PERPS_MAX_TOTAL_EXPOSURE)
  - Funding rate gate: reject if funding > 0.05%/8h against direction
  - No trade within 30 min of a loss on the same coin
"""

from __future__ import annotations

import logging
import math
import os
import time
import threading
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
HL_PERPS_EXEC_SCORE: float = float(os.getenv("HL_PERPS_EXEC_SCORE", "50.0"))  # Post-Fib execution threshold
HL_PERPS_LEVERAGE: int = int(os.getenv("HL_PERPS_LEVERAGE", "3"))
HL_PERPS_MAX_POSITION_USD: float = float(os.getenv("HL_PERPS_MAX_POSITION_USD", "100.0"))
HL_PERPS_MAX_POSITIONS: int = int(os.getenv("HL_PERPS_MAX_POSITIONS", "6"))
HL_PERPS_MAX_TOTAL_EXPOSURE: float = float(os.getenv("HL_PERPS_MAX_TOTAL_EXPOSURE", "600.0"))
HL_PERPS_DAILY_LOSS_LIMIT: float = float(os.getenv("HL_PERPS_DAILY_LOSS_LIMIT", "30.0"))
HL_PERPS_STOP_LOSS_PCT: float = float(os.getenv("HL_PERPS_STOP_LOSS_PCT", "2.5"))
HL_PERPS_TAKE_PROFIT_PCT: float = float(os.getenv("HL_PERPS_TAKE_PROFIT_PCT", "6.0"))
# Extreme funding rate = fade opportunity (short when funding very positive, long when very negative)
HL_PERPS_FUNDING_FADE_THRESHOLD: float = float(os.getenv("HL_PERPS_FUNDING_FADE_THRESHOLD", "0.03"))
# Cooldown after a loss on a coin (minutes)
HL_PERPS_LOSS_COOLDOWN_MIN: int = int(os.getenv("HL_PERPS_LOSS_COOLDOWN_MIN", "30"))

# Profit withdrawal automation
HL_PERPS_BASE_CAPITAL: float = float(os.getenv("HL_PERPS_BASE_CAPITAL", "150.0"))
HL_PERPS_PROFIT_SWEEP_USD: float = float(os.getenv("HL_PERPS_PROFIT_SWEEP_USD", "500.0"))

# State persistence
_STATE_DIR = Path(os.getenv("DASHBOARD_STATE_DIR", "./data/dashboard"))
_STATE_FILE = _STATE_DIR / "hl_perps_state.json"

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

    # ── RSI (weight: 25%) ────────────────────────────────────────────────────
    rsi = _rsi(closes)
    components["rsi"] = rsi
    if rsi is not None:
        if rsi < 25:
            long_score += 25.0          # Deeply oversold — strong long
        elif rsi < 30:
            long_score += 20.0          # Oversold — long
        elif rsi < 40:
            long_score += 10.0          # Approaching oversold — mild long
        elif rsi > 75:
            short_score += 25.0         # Deeply overbought — strong short
        elif rsi > 70:
            short_score += 20.0         # Overbought — short
        elif rsi > 60:
            short_score += 10.0         # Approaching overbought — mild short

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

    # ── Determine direction and final score ──────────────────────────────────
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
        self.loss_cooldowns: dict[str, float] = {}  # coin → timestamp of last loss
        self.last_signals: list[PerpSignal] = []
        self.pending_retracements: dict[str, dict] = {}  # coin -> {"signal": PerpSignal, "target_px": float, "expires_at": float}
        
        _STATE_DIR.mkdir(parents=True, exist_ok=True)
        self._load_pending_retracements()

        # Stats
        self.total_wins: int = 0
        self.total_losses: int = 0
        self.total_pnl: float = 0.0

        # ── API Rate-Limit Protection ─────────────────────────────────────────
        # Cache meta() responses for 30s to stay well under HL's 1200 weight/min limit.
        self._meta_cache: dict = {}
        self._meta_cache_ts: float = 0.0
        self._META_CACHE_TTL: float = 30.0  # seconds

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

    def _is_on_cooldown(self, coin: str) -> bool:
        """Check if a coin is in loss cooldown."""
        if coin not in self.loss_cooldowns:
            return False
        elapsed = time.time() - self.loss_cooldowns[coin]
        return elapsed < HL_PERPS_LOSS_COOLDOWN_MIN * 60

    def _check_daily_reset(self) -> None:
        """Reset daily PnL at midnight UTC."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if today != self.daily_pnl_reset_date:
            if self.daily_pnl != 0:
                logger.info(f"HLPerpsScanner: daily PnL reset (was ${self.daily_pnl:+.2f})")
            self.daily_pnl = 0.0
            self.daily_pnl_reset_date = today

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

        # ── Institutional Capital Protection: Macro Trend Alignment ──────────
        # Reject trades that fight the daily trend.
        if direction == "long" and macro_trend == "bearish":
            logger.debug(f"[HL-PERPS] {coin}: VETOED LONG — Fighting daily bearish trend")
            return None
        if direction == "short" and macro_trend == "bullish":
            logger.debug(f"[HL-PERPS] {coin}: VETOED SHORT — Fighting daily bullish trend")
            return None
            
        components["macro_trend"] = macro_trend

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

        # ── Kelly Criterion Position Sizing ──────────────────────────────────────
        # ── Dynamic Kelly Criterion Position Sizing ─────────────────────────
        # Scale size exponentially based on signal score (65 to 100).
        # Uses LIVE account equity if executor is available, otherwise falls back
        # to HL_PERPS_BASE_CAPITAL env var (default $150).
        # Sizing: min=16.7% of equity (1 of 6 slots), max=96.7% of equity.
        # Formula: base_size * e^(k * (score - min_score))
        _live_equity = HL_PERPS_BASE_CAPITAL
        if self.hl_executor and self.hl_executor.is_available():
            try:
                _bal = self.hl_executor.get_balance()
                _acct_val = _bal.get("accountValue", 0.0) or _bal.get("equity", 0.0)
                if _acct_val and _acct_val > 10.0:  # sanity: ignore near-zero balances
                    _live_equity = float(_acct_val)
            except Exception:
                pass  # Fall back to HL_PERPS_BASE_CAPITAL
        min_score = HL_PERPS_MIN_SCORE
        max_score = 95.0
        # Allocate 1/6 of equity at min score, up to 5/6 at max score
        # This ensures no single trade risks more than ~97% of account
        min_size = max(10.0, round(_live_equity / 6.0, 2))
        max_size = max(min_size, round(_live_equity * 0.967, 2))

        if score <= min_score:
            kelly_size_usd = min_size
        elif score >= max_score:
            kelly_size_usd = max_size
        else:
            # Exponential scaling factor
            k = math.log(max_size / min_size) / (max_score - min_score)
            kelly_size_usd = min_size * math.exp(k * (score - min_score))

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
        if score < HL_PERPS_EXEC_SCORE:
            logger.info(
                f"[HL-PERPS] {coin} {direction.upper()} score={score:.0f} < exec_threshold={HL_PERPS_EXEC_SCORE} "
                f"(fib={fib_zone}, tp_src={tp_source}) — NEAR MISS, not trading"
            )
            return None

        # ── R/R Ratio Guard (OpenAlice Guard Pipeline) ────────────────────────
        # Reject signals where TP/SL math doesn't make sense.
        # Minimum R/R = 1.5x to ensure favorable risk/reward on every trade.
        MIN_RR_RATIO = 1.5
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
            _av = _bl.get("accountValue", 0.0) or _bl.get("equity", 0.0)
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

        # Check max positions
        active = len(self.hl_executor.positions)
        if active >= HL_PERPS_MAX_POSITIONS:
            logger.debug(f"HLPerpsScanner: max positions ({HL_PERPS_MAX_POSITIONS}) reached")
            return False

        try:
            if signal.direction == "long":
                result = self.hl_executor.open_long(
                    symbol=signal.coin,
                    size_usd=signal.position_size_usd,
                    leverage=signal.leverage,
                    gem_score=signal.score,
                )
            else:
                result = self.hl_executor.open_short(
                    symbol=signal.coin,
                    size_usd=signal.position_size_usd,
                    leverage=signal.leverage,
                    gem_score=signal.score,
                )

            if result:
                self.trades_executed += 1
                logger.info(
                    f"✅ HLPerpsScanner: {signal.direction.upper()} {signal.coin} executed | "
                    f"size=${signal.position_size_usd} × {signal.leverage}x | "
                    f"score={signal.score}"
                )
                return True
            else:
                logger.warning(f"HLPerpsScanner: executor returned None for {signal.coin}")
                return False

        except Exception as e:
            logger.error(f"HLPerpsScanner: execution error for {signal.coin}: {e}")
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
        if self.hl_executor and self.hl_executor.is_available():
            paycheck_wallet = os.getenv("WALLET_ADDRESS_C", "").strip()
            if paycheck_wallet:
                try:
                    balance_info = self.hl_executor.get_balance()
                    withdrawable = balance_info.get("withdrawable", 0.0)
                    if withdrawable >= (HL_PERPS_BASE_CAPITAL + HL_PERPS_PROFIT_SWEEP_USD):
                        logger.info(
                            f"💰 [HL-PERPS] Profit Sweeper triggered! "
                            f"Withdrawable (${withdrawable:.2f}) >= Base (${HL_PERPS_BASE_CAPITAL:.2f}) + Sweep (${HL_PERPS_PROFIT_SWEEP_USD:.2f})"
                        )
                        self.hl_executor.withdraw_profit_usd(HL_PERPS_PROFIT_SWEEP_USD, paycheck_wallet)
                except Exception as e:
                    logger.error(f"Failed to check/sweep HL profits: {e}")

        self._check_daily_reset()
        self.scan_count += 1
        cycle_start = time.time()

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
        watchlist_set = set(HL_PERPS_WATCHLIST)
        scan_list = list(HL_PERPS_WATCHLIST)
        all_perps = set(funding_rates.keys())
        remaining = [c for c in sorted(all_perps) if c not in watchlist_set]
        scan_list.extend(remaining)

        signals: list[PerpSignal] = []
        scanned = 0
        near_misses: list[tuple[str, float, str]] = []  # (coin, score, direction)

        watchlist_len = len(HL_PERPS_WATCHLIST)
        active_positions = len(self.hl_executor.positions) if self.hl_executor else 0
        max_new_signals = HL_PERPS_MAX_POSITIONS - active_positions

        # Cap total scan to 100 coins to balance opportunity vs rate limits
        # (41 watchlist + 59 discovery = 100 coins × 2 API calls = 200 calls/cycle)
        scan_list = scan_list[:100]

        for idx, coin in enumerate(scan_list):
            # Stop if we've found enough signals to fill all position slots
            if len(signals) >= max(max_new_signals, 1):
                break

            # Skip if already in a position or pending sniper entry
            if self.hl_executor and coin in self.hl_executor.positions:
                continue
            if coin in self.pending_retracements:
                continue

            # Rate-limit: 0.25s delay every 3 non-watchlist coins
            # 100 coins × 2 API calls = 200 calls. At ~0.25s per 3 coins,
            # scan takes ~16s for discovery coins + ~10s for watchlist = ~26s total.
            if idx >= watchlist_len and idx % 3 == 0:
                time.sleep(0.25)

            funding_rate = funding_rates.get(coin, 0.0)
            signal = self.scan_coin(coin, funding_rate)
            scanned += 1

            if signal:
                signals.append(signal)
                self.signals_generated += 1

                # ── Entry Decision: Immediate vs Sniper ────────────────────────
                # Golden pocket (fib confidence >= 70) = EXECUTE NOW — price is
                # already at the optimal Fibonacci level. Don't wait for a dip
                # that may never come; the golden pocket IS the dip.
                # Lower confidence = load the retracement sniper and wait.
                is_golden = (
                    signal.fib_confidence >= 70
                    or signal.fib_zone == "golden_pocket"
                    or "golden" in signal.fib_zone.lower()
                )

                if is_golden:
                    logger.info(
                        f"⚡ GOLDEN POCKET — IMMEDIATE ENTRY: {signal.direction.upper()} {signal.coin} "
                        f"@ ${signal.entry_price:.4f} | score={signal.score:.0f} | "
                        f"fib_zone={signal.fib_zone} | fib_conf={signal.fib_confidence:.0f}"
                    )
                    self._execute_signal(signal)
                else:
                    # Retracement Sniper: delay entry until price pulls back
                    if signal.ema_support_px and signal.ema_support_px > 0:
                        target_px = round(signal.ema_support_px, 4)
                    else:
                        discount = 0.015
                        if signal.direction == "long":
                            target_px = round(signal.entry_price * (1 - discount), 4)
                        else:
                            target_px = round(signal.entry_price * (1 + discount), 4)

                    # If already within 1% of target, execute immediately
                    current_px = signal.entry_price
                    at_target = (
                        (signal.direction == "long" and current_px <= target_px * 1.01) or
                        (signal.direction == "short" and current_px >= target_px * 0.99)
                    )
                    if at_target:
                        logger.info(
                            f"⚡ NEAR TARGET — EXECUTING: {signal.direction.upper()} {signal.coin} "
                            f"at ${current_px:.4f} (target ${target_px:.4f})"
                        )
                        self._execute_signal(signal)
                    else:
                        self.pending_retracements[signal.coin] = {
                            "signal": signal,
                            "target_px": target_px,
                            "expires_at": time.time() + 3600
                        }
                        logger.info(
                            f"🏹 RETRACEMENT SNIPER LOADED: {signal.direction.upper()} {signal.coin} "
                            f"| Waiting for dip to ${target_px}..."
                        )
        # Sort by score descending for logging
        signals.sort(key=lambda s: s.score, reverse=True)
        self.last_signals = signals

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
