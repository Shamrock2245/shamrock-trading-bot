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
HL_PERPS_MIN_SCORE: float = float(os.getenv("HL_PERPS_MIN_SCORE", "65.0"))
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

        # Stats
        self.total_wins: int = 0
        self.total_losses: int = 0
        self.total_pnl: float = 0.0

        _STATE_DIR.mkdir(parents=True, exist_ok=True)

        if self.enabled:
            self._init_api()

    def _init_api(self) -> None:
        """Initialize the Hyperliquid Info API (read-only, no keys needed)."""
        try:
            from hyperliquid.info import Info
            self._info = Info("https://api.hyperliquid.xyz", skip_ws=True)
            # Quick connectivity test
            meta = self._info.meta()
            n_perps = len(meta.get("universe", []))
            self._initialized = True
            logger.info(
                f"✅ HLPerpsScanner initialized | {n_perps} perps available | "
                f"scan_interval={HL_PERPS_SCAN_INTERVAL}s | "
                f"min_score={HL_PERPS_MIN_SCORE} | leverage={HL_PERPS_LEVERAGE}x"
            )
        except ImportError:
            logger.error("❌ hyperliquid-python-sdk not installed — pip install hyperliquid-python-sdk")
            self.enabled = False
        except Exception as e:
            logger.error(f"❌ HLPerpsScanner init failed: {e}")
            self.enabled = False

    def _get_candles(self, coin: str, interval: str = "1h", lookback_hours: int = 72) -> list[dict]:
        """Fetch OHLCV candles for a coin."""
        try:
            now_ms = int(time.time() * 1000)
            start_ms = now_ms - lookback_hours * 3600 * 1000
            candles = self._info.candles_snapshot(coin, interval, start_ms, now_ms)
            return candles or []
        except Exception as e:
            logger.debug(f"HLPerpsScanner: candle fetch failed for {coin}: {e}")
            return []

    def _get_funding_rate(self, coin: str) -> float:
        """Get current funding rate for a coin (per 8h)."""
        try:
            meta = self._info.meta()
            for asset in meta.get("universe", []):
                if asset.get("name", "").upper() == coin.upper():
                    return float(asset.get("funding", 0))
            return 0.0
        except Exception:
            return 0.0

    def _get_all_funding_rates(self) -> dict[str, float]:
        """Fetch all funding rates in one API call."""
        try:
            meta = self._info.meta()
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

        # Fetch candles
        candles = self._get_candles(coin, "1h", 72)
        if len(candles) < 35:
            return None

        closes = [float(c["c"]) for c in candles]
        volumes = [float(c["v"]) for c in candles]
        current_price = closes[-1]

        if current_price <= 0:
            return None

        # Score the market
        score, direction, components = _score_signal(closes, volumes, funding_rate)

        if direction == "none" or score < HL_PERPS_MIN_SCORE:
            return None

        # Calculate TP/SL prices
        sl_pct = HL_PERPS_STOP_LOSS_PCT / 100
        tp_pct = HL_PERPS_TAKE_PROFIT_PCT / 100

        if direction == "long":
            stop_loss = current_price * (1 - sl_pct)
            take_profit = current_price * (1 + tp_pct)
        else:
            stop_loss = current_price * (1 + sl_pct)
            take_profit = current_price * (1 - tp_pct)

        # Build reasoning string
        rsi_val = components.get("rsi")
        vol_spike = components.get("volume_spike")
        fund_sig = components.get("funding_signal", "")
        reasoning_parts = [
            f"RSI={rsi_val:.1f}" if rsi_val else "",
            f"EMA={components.get('ema_cross', '?')}",
            f"MACD_hist={components.get('macd_hist', 0):.4f}" if components.get("macd_hist") else "",
            f"vol_spike={vol_spike:.1f}x" if vol_spike else "",
            f"BB={components.get('bb_zone', '?')}",
            f"funding={funding_rate*100:.4f}%/8h",
            f"fade={fund_sig}" if fund_sig else "",
            f"mom_1h={components.get('momentum_1h', 0):.2f}%" if components.get("momentum_1h") else "",
        ]
        reasoning = " | ".join(p for p in reasoning_parts if p)

        signal = PerpSignal(
            coin=coin,
            direction=direction,
            score=round(score, 1),
            entry_price=current_price,
            stop_loss_price=round(stop_loss, 6),
            take_profit_price=round(take_profit, 6),
            leverage=HL_PERPS_LEVERAGE,
            position_size_usd=HL_PERPS_MAX_POSITION_USD,
            rsi=rsi_val,
            ema_cross=components.get("ema_cross"),
            macd_signal="buy" if (components.get("macd_hist") or 0) > 0 else "sell",
            volume_spike=vol_spike,
            funding_rate=funding_rate,
            bb_position=components.get("bb_zone"),
            momentum_1h=components.get("momentum_1h"),
            reasoning=reasoning,
        )

        logger.info(
            f"📡 HL PERPS SIGNAL | {direction.upper()} {coin} @ ${current_price:.4f} | "
            f"score={score:.0f} | TP=${take_profit:.4f} | SL=${stop_loss:.4f} | "
            f"R/R={signal.r_r_ratio:.1f}x | {reasoning}"
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

        # Check daily loss limit
        self._check_daily_reset()
        if self.daily_pnl <= -HL_PERPS_DAILY_LOSS_LIMIT:
            logger.warning(
                f"🛑 HLPerpsScanner CIRCUIT BREAKER: daily PnL ${self.daily_pnl:.2f} "
                f"hit limit -${HL_PERPS_DAILY_LOSS_LIMIT:.2f} — halting perps trading"
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

        self._check_daily_reset()
        self.scan_count += 1
        cycle_start = time.time()

        # Fetch all funding rates in one call (efficiency)
        funding_rates = self._get_all_funding_rates()

        # Build scan list: watchlist + funding anomaly coins
        scan_list = list(HL_PERPS_WATCHLIST)
        anomaly_coins = self._add_funding_anomaly_coins(funding_rates)
        scan_list.extend(anomaly_coins)

        signals: list[PerpSignal] = []
        scanned = 0

        for coin in scan_list:
            # Skip if already in a position
            if self.hl_executor and coin in self.hl_executor.positions:
                continue

            funding_rate = funding_rates.get(coin, 0.0)
            signal = self.scan_coin(coin, funding_rate)
            scanned += 1

            if signal:
                signals.append(signal)
                self.signals_generated += 1

                # Execute immediately
                self._execute_signal(signal)

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
            logger.debug(
                f"HLPerpsScanner scan #{self.scan_count}: {scanned} coins scanned | "
                f"0 signals | {elapsed:.1f}s"
            )

        self._save_state(signals)
        return signals

    def _save_state(self, signals: list[PerpSignal]) -> None:
        """Persist scanner state for dashboard display."""
        try:
            import json
            state = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "scan_count": self.scan_count,
                "signals_generated": self.signals_generated,
                "trades_executed": self.trades_executed,
                "daily_pnl": round(self.daily_pnl, 2),
                "daily_loss_limit": HL_PERPS_DAILY_LOSS_LIMIT,
                "enabled": self.enabled,
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

    def get_status(self) -> dict:
        """Status dict for dashboard/logging."""
        return {
            "enabled": self.enabled,
            "initialized": self._initialized,
            "scan_count": self.scan_count,
            "signals_generated": self.signals_generated,
            "trades_executed": self.trades_executed,
            "daily_pnl": round(self.daily_pnl, 2),
            "daily_loss_limit": HL_PERPS_DAILY_LOSS_LIMIT,
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
