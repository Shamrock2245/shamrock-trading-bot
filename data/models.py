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

    # Signals
    signal_score: Optional["SignalScore"] = None
    block_reason: Optional[str] = None

    @property
    def is_actionable(self) -> bool:
        """True if this gem is ready for trade consideration."""
        return self.is_safe and self.gem_score >= 65.0

    def __str__(self) -> str:
        return (
            f"GemCandidate({self.token.symbol} | {self.token.chain} | "
            f"score={self.gem_score:.1f} | safe={self.is_safe})"
        )


@dataclass
class SignalScore:
    """Technical analysis signal composite score."""
    trend_score: float = 0.0       # -100 to +100 (bearish to bullish)
    momentum_score: float = 0.0    # 0 to 100
    volume_score: float = 0.0      # 0 to 100
    onchain_score: float = 0.0     # 0 to 100

    # Individual indicators
    rsi: Optional[float] = None
    macd_signal: Optional[str] = None    # "bullish", "bearish", "neutral"
    ema_signal: Optional[str] = None     # "golden_cross", "death_cross", "neutral"
    bb_signal: Optional[str] = None      # "squeeze", "breakout", "normal"
    volume_spike: bool = False

    @property
    def composite(self) -> float:
        """
        Weighted composite score.
        >70 = BUY signal, <30 = SELL signal, 30–70 = HOLD/NEUTRAL
        """
        # Normalize trend_score from -100/+100 to 0/100
        trend_normalized = (self.trend_score + 100) / 2
        return (
            trend_normalized * 0.30
            + self.momentum_score * 0.25
            + self.volume_score * 0.20
            + self.onchain_score * 0.25
        )

    @property
    def signal(self) -> str:
        score = self.composite
        if score >= 70:
            return "BUY"
        elif score <= 30:
            return "SELL"
        return "NEUTRAL"


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
