"""
strategies/gem_snipe.py — Gem Snipe Strategy with TA Confirmation.

The first concrete trading strategy. Orchestrates the full flow:

  Gem Candidate → Fetch OHLCV → Run TA Indicators → Fibonacci Gate
  → Signal Score → Risk Check → Execute or Skip

This replaces the bare safety→risk→execute flow in main.py's bot loop,
adding the Phase 2 TA layer as a mandatory gate between gem discovery
and trade execution.

Requirements:
  - Gem score ≥ MIN_GEM_SCORE (from scanner)
  - Safety check passed (from core/safety.py)
  - Signal score ≥ MIN_SIGNAL_SCORE
  - Fibonacci alignment = True (hard gate)
  - Risk check approved (from core/risk.py)
"""

import logging
from dataclasses import dataclass
from typing import Optional

from config import settings
from data.models import Token, GemCandidate, SignalScore
from data.providers.ohlcv_provider import fetch_ohlcv, get_current_price
from strategies.fibonacci import FibResult
from strategies.signal_scorer import analyze_token, format_analysis_report
from strategies.indicators import TAResult

logger = logging.getLogger(__name__)


@dataclass
class StrategyDecision:
    """Result of strategy evaluation for a gem candidate."""
    action: str = "skip"           # "buy", "sell", "skip"
    reason: str = ""
    signal_score: Optional[SignalScore] = None
    ta_result: Optional[TAResult] = None
    fib_result: Optional[FibResult] = None
    gem_score: float = 0.0
    confidence: float = 0.0        # 0–100 overall confidence
    take_profit_targets: list = None
    stop_loss_price: float = 0.0

    def __post_init__(self):
        if self.take_profit_targets is None:
            self.take_profit_targets = []

    def __str__(self) -> str:
        if self.action == "buy":
            return (
                f"StrategyDecision(✅ BUY | confidence={self.confidence:.0f} | "
                f"signal={self.signal_score.composite:.1f} | gem={self.gem_score:.1f} | "
                f"fib={self.fib_result.current_zone if self.fib_result else 'N/A'})"
            )
        return f"StrategyDecision(⏭ SKIP | {self.reason})"


class GemSnipeStrategy:
    """
    Gem Snipe Strategy — the primary trading strategy.

    Combines Phase 1 (Gem Discovery) with Phase 2 (TA & Fibonacci)
    to make high-confidence entry decisions.
    """

    def __init__(
        self,
        min_signal_score: float = None,
        require_fib_alignment: bool = None,
        ohlcv_days: int = 7,
    ):
        self.min_signal_score = min_signal_score or getattr(settings, "MIN_SIGNAL_SCORE", 55.0)
        self.require_fib_alignment = require_fib_alignment if require_fib_alignment is not None else getattr(settings, "REQUIRE_FIB_ALIGNMENT", True)
        self.ohlcv_days = ohlcv_days

    def evaluate(self, candidate: GemCandidate) -> StrategyDecision:
        """
        Evaluate a gem candidate for trade entry.

        Full pipeline:
          1. Validate gem score meets threshold
          2. Fetch OHLCV data
          3. Get current price
          4. Run TA indicators + Fibonacci analysis
          5. Calculate composite signal score
          6. Apply decision rules

        Args:
            candidate: GemCandidate from the scanner (must have passed safety)

        Returns:
            StrategyDecision with action, confidence, TP/SL levels
        """
        token = candidate.token
        logger.info(f"Evaluating {token.symbol} ({token.chain}) — gem score: {candidate.gem_score:.1f}")

        # ── Gate 1: Gem Score ─────────────────────────────────────────────
        if candidate.gem_score < settings.MIN_GEM_SCORE:
            return StrategyDecision(
                action="skip",
                reason=f"Gem score {candidate.gem_score:.1f} below threshold {settings.MIN_GEM_SCORE}",
                gem_score=candidate.gem_score,
            )

        # ── Gate 2: Safety (should already be checked, but enforce) ───────
        if not candidate.is_safe:
            return StrategyDecision(
                action="skip",
                reason=f"Safety check failed: {candidate.safety_details.get('block_reason', 'unknown')}",
                gem_score=candidate.gem_score,
            )

        # ── Step 1: Fetch OHLCV ──────────────────────────────────────────
        df = fetch_ohlcv(token.address, token.chain, days=self.ohlcv_days)

        # ── Step 2: Get current price ─────────────────────────────────────
        current_price = token.price_usd
        if not current_price or current_price <= 0:
            current_price = get_current_price(token.address, token.chain)
        if not current_price or current_price <= 0:
            return StrategyDecision(
                action="skip",
                reason="Unable to fetch current price",
                gem_score=candidate.gem_score,
            )

        # ── Step 3: Run TA + Fibonacci Analysis ──────────────────────────
        # Calculate on-chain score from gem scanner data
        onchain_score = self._calculate_onchain_score(candidate)

        if df is not None and len(df) >= 3:
            signal_score, ta_result, fib_result = analyze_token(
                df=df,
                current_price=current_price,
                onchain_score=onchain_score,
                direction="buy",
                chain=token.chain,
            )
        else:
            # Insufficient OHLCV data — use signal engine's micro-cap score if available
            from strategies.fibonacci import FibResult as FR
            from strategies.indicators import TAResult as TA

            if candidate.signal_score is not None:
                # Reuse the signal engine's score (it already used gem_score + enrichment)
                signal_score = candidate.signal_score
                logger.info(
                    f"Reusing signal engine score for {token.symbol}: "
                    f"composite={signal_score.composite:.1f}"
                )
            else:
                logger.warning(f"Limited OHLCV data for {token.symbol} — using gem score only")
                signal_score = SignalScore(onchain_score=onchain_score)

            ta_result = TAResult()
            fib_result = FR(
                aligned=True,  # Permissive when no data
                current_zone="insufficient_data",
                confidence=10.0,
                current_price=current_price,
            )
            # Ensure fib fields are set
            signal_score.fib_score = 50.0
            signal_score.fib_zone = "insufficient_data"
            signal_score.fib_aligned = True

        # ── Gate 3: Fibonacci Alignment (SOFT PENALTY) ───────────────────
        # Instead of hard-blocking, apply a score penalty for misaligned fib
        fib_penalty = 0.0
        if self.require_fib_alignment and not fib_result.aligned:
            fib_penalty = 15.0
            logger.info(
                f"Fibonacci penalty applied to {token.symbol}: "
                f"-{fib_penalty} pts (price in '{fib_result.current_zone}' zone)"
            )

        # ── Gate 4: Minimum Signal Score (with fib penalty) ───────────────
        composite = signal_score.composite - fib_penalty
        if composite < self.min_signal_score:
            report = format_analysis_report(signal_score, ta_result, fib_result, token.symbol)
            logger.info(f"Signal score too low for {token.symbol} ({composite:.1f} after fib penalty):\n{report}")
            return StrategyDecision(
                action="skip",
                reason=f"Signal score {composite:.1f} below threshold {self.min_signal_score}" +
                       (f" (includes -{fib_penalty:.0f} fib penalty)" if fib_penalty > 0 else ""),
                signal_score=signal_score,
                ta_result=ta_result,
                fib_result=fib_result,
                gem_score=candidate.gem_score,
            )

        # ── Gate 5: Hard DECELERATING Block (worst entry timing) ───────────────────
        # If buy pressure is actively decelerating AND timing_score is critically
        # low (<30), this is a dying move. Reject to avoid buying the top.
        # Express lane tokens bypass this gate (they scored ≥82 for a reason).
        _hard_timing_bp = getattr(candidate, 'timing_bp_trend', 'flat')
        _hard_timing_score = getattr(candidate, 'timing_score', 50.0)
        _is_express = getattr(candidate, 'express_lane', False)
        if (
            not _is_express
            and _hard_timing_bp == 'decelerating'
            and _hard_timing_score < 30.0
        ):
            logger.info(
                f"⛔ TIMING HARD BLOCK: {token.symbol} — decelerating BP + timing_score={_hard_timing_score:.0f} < 30 "
                f"(buying a dying move — rejected)"
            )
            return StrategyDecision(
                action="skip",
                reason=f"Timing hard block: decelerating BP trend + timing_score={_hard_timing_score:.0f} (late entry risk)",
                signal_score=signal_score,
                ta_result=ta_result,
                fib_result=fib_result,
                gem_score=candidate.gem_score,
            )

        # ── Decision: BUY ───────────────────────────────────────────────────────────────────
        # All gates passed — this is a high-confidence entry
        # timing_score (0–100) from Moralis multi-timeframe entry intelligence:
        #   accelerating BP trend → +5 confidence bonus (momentum building)
        #   decelerating BP trend → -8 confidence penalty (late entry risk)
        timing_bp_trend = getattr(candidate, 'timing_bp_trend', 'flat')
        timing_adj = 0.0
        if timing_bp_trend == 'accelerating':
            timing_adj = +5.0
            logger.info(f"⏱️ TIMING BONUS: {token.symbol} — accelerating BP trend → +5 confidence")
        elif timing_bp_trend == 'decelerating':
            timing_adj = -8.0
            logger.info(f"⏱️ TIMING PENALTY: {token.symbol} — decelerating BP trend → -8 confidence (late entry risk)")

        confidence = max(0.0, min(100.0, (
            composite * 0.5 +
            candidate.gem_score * 0.3 +
            fib_result.confidence * 0.2
        ) + timing_adj))

        timing_note = f" | timing={timing_bp_trend}({timing_adj:+.0f})" if timing_adj != 0 else ""
        report = format_analysis_report(signal_score, ta_result, fib_result, token.symbol)
        logger.info(f"✅ BUY SIGNAL for {token.symbol} (confidence: {confidence:.0f}{timing_note}):\n{report}")

        return StrategyDecision(
            action="buy",
            reason=f"All gates passed — composite={composite:.1f}, gem={candidate.gem_score:.1f}, fib={fib_result.current_zone}{timing_note}",
            signal_score=signal_score,
            ta_result=ta_result,
            fib_result=fib_result,
            gem_score=candidate.gem_score,
            confidence=confidence,
            take_profit_targets=fib_result.take_profit_targets,
            stop_loss_price=fib_result.stop_loss_level,
        )

    def _calculate_onchain_score(self, candidate: GemCandidate) -> float:
        """
        Derive an on-chain score from the gem candidate's existing data.

        Maps the gem scanner's individual scores to a 0–100 on-chain score.
        """
        # Read scores directly from GemCandidate attributes
        onchain = (
            getattr(candidate, "volume_score", 0) * 0.25 +
            getattr(candidate, "liquidity_score", 0) * 0.20 +
            getattr(candidate, "holder_score", 0) * 0.20 +
            getattr(candidate, "age_score", 0) * 0.15 +
            getattr(candidate, "tax_score", 0) * 0.10 +
            getattr(candidate, "social_score", 0) * 0.10
        )

        return max(0, min(100, onchain))

    def evaluate_batch(self, candidates: list[GemCandidate]) -> list[StrategyDecision]:
        """Evaluate multiple candidates and return sorted by confidence."""
        decisions = []
        for candidate in candidates:
            try:
                decision = self.evaluate(candidate)
                decisions.append(decision)
            except Exception as e:
                logger.error(f"Error evaluating {candidate.token.symbol}: {e}", exc_info=True)
                decisions.append(StrategyDecision(
                    action="skip",
                    reason=f"Evaluation error: {str(e)}",
                    gem_score=candidate.gem_score,
                ))

        # Sort: buys first (by confidence), then skips
        buy_decisions = sorted(
            [d for d in decisions if d.action == "buy"],
            key=lambda d: d.confidence,
            reverse=True,
        )
        skip_decisions = [d for d in decisions if d.action != "buy"]

        return buy_decisions + skip_decisions
