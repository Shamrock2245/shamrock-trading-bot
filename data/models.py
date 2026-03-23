"""
data/models.py — Core data models for Shamrock Trading Bot.

Defines dataclasses for Token, GemCandidate, Trade, Position, and SignalScore.
These are used throughout the codebase for type-safe data passing.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class Token:
    """Represents a token discovered by the scanner."""
    address: str
    symbol: str
    name: str
    chain: str
    pair_address: str = ""
    price_usd: float = 0.0
    market_cap: float = 0.0
    liquidity_usd: float = 0.0
    volume_24h: float = 0.0
    volume_1h: float = 0.0
    price_change_1h: float = 0.0
    price_change_24h: float = 0.0
    age_hours: Optional[float] = None
    holder_count: int = 0
    buy_tax: float = 0.0
    sell_tax: float = 0.0
    is_boosted: bool = False
    boost_amount: int = 0
    is_cto: bool = False               # Community takeover flag
    dex_url: str = ""
    discovered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_new(self) -> bool:
        """Token is less than 24 hours old."""
        return self.age_hours is not None and self.age_hours < 24

    @property
    def volume_to_mcap_ratio(self) -> float:
        """High ratio (>10%) indicates strong trading activity."""
        if self.market_cap > 0:
            return self.volume_24h / self.market_cap
        return 0.0


@dataclass
class GemCandidate:
    """A token that has passed initial screening with a composite score."""
    token: Token
    gem_score: float = 0.0          # 0–100 composite score
    safety_passed: bool = False
    is_safe: bool = False

    # Score components
    age_score: float = 0.0
    volume_score: float = 0.0
    liquidity_score: float = 0.0
    contract_score: float = 0.0
    holder_score: float = 0.0
    tax_score: float = 0.0
    social_score: float = 0.0
    boost_score: float = 0.0
    smart_money_score: float = 0.0

    # Enhanced signals (Phase 3)
    tvl_score: float = 0.0              # DefiLlama TVL
    social_sentiment_score: float = 0.0  # LunarCrush Galaxy Score
    holder_concentration_score: float = 0.0  # On-chain holder analysis
    unlock_risk_score: float = 0.0      # FDV/mcap dilution risk

    # Signals
    signal_score: Optional["SignalScore"] = None
    block_reason: Optional[str] = None

    # Strategy and routing metadata
    strategy_tag: str = "gem_snipe"   # "gem_snipe", "cto_revival", "boost_momentum"
    express_lane: bool = False         # True = skip full TA, execute immediately
    is_cto: bool = False               # True = community takeover token

    @property
    def is_actionable(self) -> bool:
        """True if this gem is ready for trade consideration."""
        from config import settings
        return self.is_safe and self.gem_score >= settings.MIN_GEM_SCORE

    def __str__(self) -> str:
        return (
            f"GemCandidate({self.token.symbol} | {self.token.chain} | "
            f"score={self.gem_score:.1f} | safe={self.is_safe})"
        )


@dataclass
class SignalScore:
    """
    Unified technical analysis signal composite score.

    Used by both:
      - core/signal_engine.py (Phase 1 lightweight scoring)
      - strategies/signal_scorer.py (Phase 2 full TA + Fibonacci)
    """
    trend_score: float = 0.0       # -100 to +100 (bearish to bullish)
    momentum_score: float = 0.0    # 0 to 100
    volume_score: float = 0.0      # 0 to 100
    onchain_score: float = 0.0     # 0 to 100

    # Fibonacci analysis (Phase 2)
    fib_score: float = 0.0         # 0 to 100 (Fibonacci zone alignment)
    fib_zone: str = "unknown"      # "golden_pocket", "fib_618", "no_mans_land", etc.
    fib_aligned: bool = False      # True = price is in a valid Fibonacci zone

    # Individual indicators
    rsi: Optional[float] = None
    macd_signal: Optional[str] = None    # "bullish", "bearish", "neutral"
    ema_signal: Optional[str] = None     # "golden_cross", "death_cross", "neutral"
    bb_signal: Optional[str] = None      # "squeeze", "breakout", "normal"
    adx: Optional[float] = None
    volume_spike: bool = False
    volume_spike_ratio: Optional[float] = None

    # Express lane bypass (Phase 1 — gem_score ≥ 82 skips full TA)
    express_lane: bool = False

    @property
    def composite(self) -> float:
        """
        Weighted composite score.

        If fib_score is populated (Phase 2):
          trend=25%, momentum=20%, volume=15%, onchain=15%, fibonacci=25%
        Otherwise (Phase 1 fallback):
          trend=30%, momentum=25%, volume=20%, onchain=25%
        """
        trend_normalized = (self.trend_score + 100) / 2
        if self.fib_score > 0 or self.fib_aligned:
            return (
                trend_normalized * 0.25
                + self.momentum_score * 0.20
                + self.volume_score * 0.15
                + self.onchain_score * 0.15
                + self.fib_score * 0.25
            )
        # Phase 1 fallback (no Fibonacci data)
        return (
            trend_normalized * 0.30
            + self.momentum_score * 0.25
            + self.volume_score * 0.20
            + self.onchain_score * 0.25
        )

    @property
    def signal(self) -> str:
        score = self.composite
        if self.fib_score > 0 or self.fib_aligned:
            if score >= 70 and self.fib_aligned:
                return "BUY"
            elif score <= 30 or not self.fib_aligned:
                return "SELL"
        else:
            if score >= 70:
                return "BUY"
            elif score <= 30:
                return "SELL"
        return "NEUTRAL"

    @property
    def is_buy_signal(self) -> bool:
        from config import settings
        return self.composite >= settings.MIN_SIGNAL_SCORE

    @property
    def is_sell_signal(self) -> bool:
        return self.composite < 30.0


@dataclass
class Trade:
    """Record of a completed or attempted trade."""
    id: Optional[str] = None
    wallet_alias: str = ""
    wallet_address: str = ""
    chain: str = ""
    token_address: str = ""
    token_symbol: str = ""
    direction: str = ""             # "buy" or "sell"
    amount_in: float = 0.0
    amount_out: float = 0.0
    price_usd: float = 0.0
    gas_used: int = 0
    gas_price_gwei: float = 0.0
    gas_cost_eth: float = 0.0
    tx_hash: Optional[str] = None
    execution_path: str = ""        # "cow", "1inch", "paper"
    status: str = "pending"         # "pending", "success", "failed"
    error: Optional[str] = None
    gem_score: float = 0.0
    signal_score: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def pnl_eth(self) -> float:
        """P&L in ETH (positive = profit, negative = loss)."""
        if self.direction == "sell":
            return self.amount_out - self.amount_in
        return 0.0


@dataclass
class Position:
    """An open trading position."""
    wallet_alias: str
    chain: str
    token_address: str
    token_symbol: str
    entry_price_usd: float
    amount_tokens: float
    amount_eth_spent: float
    entry_tx_hash: str
    opened_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    peak_price_usd: float = 0.0
    current_price_usd: float = 0.0
    is_open: bool = True

    # Fibonacci-derived levels
    fib_support: float = 0.0       # Nearest Fib support for stop-loss reference
    fib_resistance: float = 0.0    # Nearest Fib resistance for take-profit reference
    fib_zone: str = ""             # Zone at time of entry
    take_profit_targets: list = field(default_factory=list)  # Staged TP from Fib extensions

    @property
    def unrealized_pnl_pct(self) -> float:
        """Current unrealized P&L as percentage."""
        if self.entry_price_usd > 0 and self.current_price_usd > 0:
            return (self.current_price_usd - self.entry_price_usd) / self.entry_price_usd * 100
        return 0.0

    @property
    def should_trailing_stop(self) -> bool:
        """True if price has dropped >10% from peak."""
        from config import settings
        if self.peak_price_usd > 0 and self.current_price_usd > 0:
            drop_from_peak = (self.peak_price_usd - self.current_price_usd) / self.peak_price_usd * 100
            return drop_from_peak >= settings.STOP_LOSS_PERCENT
        return False

    @property
    def should_hard_stop(self) -> bool:
        """True if price has dropped >25% from entry."""
        from config import settings
        return self.unrealized_pnl_pct <= -settings.HARD_STOP_LOSS_PERCENT
