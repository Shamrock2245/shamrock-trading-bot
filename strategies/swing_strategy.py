"""
strategies/swing_strategy.py — Swing Trade Strategy for Capital Recovery.

Evaluates SwingCandidates from the swing scanner and produces trade decisions
with tight scalp-oriented TP/SL levels.

Key differences from GemSnipeStrategy:
  - No gem score gate (tokens are pre-vetted blue chips)
  - No safety check (established tokens don't rug)
  - No Fibonacci hard gate
  - Tight TP (3%/6%) and tight SL (2.5%)
  - Designed for 15m-4h hold times
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Swing Strategy Profile — tight scalp parameters
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SwingProfile:
    """Risk/reward profile for swing trades."""
    name: str = "swing_scalp"
    # Take-profit tiers
    tp1_pct: float = 3.0        # +3% → sell 50%
    tp1_sell_pct: float = 0.50
    tp2_pct: float = 6.0        # +6% → sell remaining
    tp2_sell_pct: float = 1.0   # Sell all remaining
    # Stop loss
    hard_stop_pct: float = 2.5  # −2.5% hard stop
    trailing_stop_pct: float = 1.5  # Trailing stop after TP1
    # Position sizing
    max_position_pct: float = 5.0   # Max 5% of wallet per swing trade
    max_position_usd: float = 100.0  # Hard cap $100 per trade
    min_position_usd: float = 10.0   # Minimum trade size
    max_concurrent: int = 5         # Max open swing positions
    # Score thresholds
    min_composite_score: float = 60.0  # Minimum TA composite to enter


SWING_SCALP_PROFILE = SwingProfile()


# ─────────────────────────────────────────────────────────────────────────────
# Swing Decision
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SwingDecision:
    """Result of swing strategy evaluation."""
    action: str = "skip"           # "buy" or "skip"
    symbol: str = ""
    chain: str = ""
    token_address: str = ""
    reason: str = ""
    ta_composite: float = 0.0
    confidence: float = 0.0
    # Trade parameters
    entry_price: float = 0.0
    tp1_price: float = 0.0
    tp2_price: float = 0.0
    stop_loss_price: float = 0.0
    position_size_usd: float = 0.0

    def __str__(self) -> str:
        if self.action == "buy":
            return (
                f"SwingDecision(✅ BUY {self.symbol}/{self.chain} | "
                f"composite={self.ta_composite:.1f} | "
                f"TP1=${self.tp1_price:.4f} (+3%) | "
                f"TP2=${self.tp2_price:.4f} (+6%) | "
                f"SL=${self.stop_loss_price:.4f} (−2.5%))"
            )
        return f"SwingDecision(⏭ SKIP {self.symbol} | {self.reason})"


# ─────────────────────────────────────────────────────────────────────────────
# Swing Strategy
# ─────────────────────────────────────────────────────────────────────────────

class SwingStrategy:
    """
    Evaluates swing candidates and produces buy decisions with
    tight scalp TP/SL levels.
    """

    def __init__(self, profile: SwingProfile = None):
        self.profile = profile or SWING_SCALP_PROFILE

    def evaluate(self, candidate) -> SwingDecision:
        """
        Evaluate a SwingCandidate for trade entry.

        Args:
            candidate: SwingCandidate from swing_scanner

        Returns:
            SwingDecision with action, TP/SL levels
        """
        decision = SwingDecision(
            symbol=candidate.symbol,
            chain=candidate.chain,
            token_address=candidate.address,
            ta_composite=candidate.ta_composite,
        )

        # ── Gate: Entry signal must be True ────────────────────────────────
        if not candidate.entry_signal:
            decision.reason = f"No entry signal (composite={candidate.ta_composite:.1f})"
            return decision

        # ── Gate: Minimum composite score ──────────────────────────────────
        if candidate.ta_composite < self.profile.min_composite_score:
            decision.reason = (
                f"Composite {candidate.ta_composite:.1f} below "
                f"threshold {self.profile.min_composite_score}"
            )
            return decision

        # ── Calculate TP/SL levels ─────────────────────────────────────────
        entry_price = candidate.price_usd
        if entry_price <= 0:
            decision.reason = "No valid price"
            return decision

        tp1_price = entry_price * (1 + self.profile.tp1_pct / 100)
        tp2_price = entry_price * (1 + self.profile.tp2_pct / 100)
        stop_loss_price = entry_price * (1 - self.profile.hard_stop_pct / 100)

        # ── Confidence score ──────────────────────────────────────────────
        # Higher RSI oversold + more confirms = higher confidence
        confidence = min(100, candidate.ta_composite * 1.2)

        # ── BUY ───────────────────────────────────────────────────────────
        decision.action = "buy"
        decision.reason = candidate.entry_reason
        decision.confidence = confidence
        decision.entry_price = entry_price
        decision.tp1_price = tp1_price
        decision.tp2_price = tp2_price
        decision.stop_loss_price = stop_loss_price

        logger.info(
            f"✅ SWING BUY: {candidate.symbol}/{candidate.chain} @ ${entry_price:.4f} | "
            f"TP1=${tp1_price:.4f} (+{self.profile.tp1_pct}%) | "
            f"TP2=${tp2_price:.4f} (+{self.profile.tp2_pct}%) | "
            f"SL=${stop_loss_price:.4f} (−{self.profile.hard_stop_pct}%) | "
            f"composite={candidate.ta_composite:.1f}"
        )

        return decision

    def calculate_position_size(
        self,
        wallet_balance_usd: float,
        decision: SwingDecision,
    ) -> float:
        """
        Calculate position size for a swing trade.

        Uses profile limits to cap exposure.
        """
        # Base size: % of wallet
        size = wallet_balance_usd * (self.profile.max_position_pct / 100)

        # Hard cap
        size = min(size, self.profile.max_position_usd)

        # Minimum check
        if size < self.profile.min_position_usd:
            return 0.0

        return round(size, 2)
