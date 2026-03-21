"""
strategies/signal_scorer.py — Composite Signal Scoring Engine.

Combines all TA indicators + Fibonacci alignment into a single
weighted composite score that drives trade decisions.

Scoring formula:
  Composite = (
    trend_score    × 0.25  +  # EMA + MACD + ADX
    momentum_score × 0.20  +  # RSI + StochRSI + BB + VWAP
    volume_score   × 0.15  +  # OBV + Volume Spike + A/D
    onchain_score  × 0.15  +  # From gem scanner (existing)
    fib_score      × 0.25     # Fibonacci zone alignment
  )

Decision thresholds:
  ≥ 70 + Fib aligned → BUY
  ≤ 30 or Fib misaligned → SELL / NO TRADE
  30-70 → HOLD / NEUTRAL
"""

import logging
from typing import Optional

import pandas as pd

from strategies.fibonacci import FibResult, check_fibonacci_alignment
from strategies.indicators import TAResult, run_all_indicators
from data.models import SignalScore

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Weight Configuration
# ─────────────────────────────────────────────────────────────────────────────

WEIGHTS = {
    "trend": 0.25,
    "momentum": 0.20,
    "volume": 0.15,
    "onchain": 0.15,
    "fibonacci": 0.25,
}

# Verify weights sum to 1.0
assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-6, f"Weights must sum to 1.0, got {sum(WEIGHTS.values())}"


# ─────────────────────────────────────────────────────────────────────────────
# Scoring Functions
# ─────────────────────────────────────────────────────────────────────────────

def _fib_to_score(fib: FibResult) -> float:
    """Convert Fibonacci analysis result to a 0–100 score."""
    if fib.error:
        return 50.0  # Neutral on error — don't penalize for missing data

    if not fib.aligned:
        return 15.0  # Misaligned = strong negative signal

    # Base score from confidence
    base = fib.confidence

    # Zone-specific bonuses
    zone_bonuses = {
        "golden_pocket": 30,
        "fib_618": 25,
        "fib_500": 20,
        "fib_786": 15,
        "fib_382": 10,
        "fib_236": 5,
        "insufficient_data": 0,  # Permissive but no bonus
    }
    bonus = zone_bonuses.get(fib.current_zone, 0)

    # Trend bonus — uptrend Fib retrace is stronger signal than downtrend
    if fib.trend == "uptrend":
        bonus += 10

    score = min(100, base + bonus)
    return max(0, score)


def calculate_composite_score(
    ta_result: TAResult,
    fib_result: FibResult,
    onchain_score: float = 50.0,
) -> SignalScore:
    """
    Calculate the final composite signal score from all analysis components.

    Args:
        ta_result: Results from all TA indicators
        fib_result: Fibonacci alignment analysis
        onchain_score: On-chain score from gem scanner (0–100)

    Returns:
        SignalScore with all fields populated
    """
    fib_score = _fib_to_score(fib_result)

    # Build the composite
    trend_normalized = ta_result.trend_score
    momentum_normalized = ta_result.momentum_score
    volume_normalized = ta_result.volume_score

    composite = (
        trend_normalized * WEIGHTS["trend"]
        + momentum_normalized * WEIGHTS["momentum"]
        + volume_normalized * WEIGHTS["volume"]
        + onchain_score * WEIGHTS["onchain"]
        + fib_score * WEIGHTS["fibonacci"]
    )

    # Convert trend score to -100/+100 range for the SignalScore model
    trend_directional = (trend_normalized - 50) * 2  # 0→-100, 50→0, 100→+100

    signal_score = SignalScore(
        trend_score=trend_directional,
        momentum_score=momentum_normalized,
        volume_score=volume_normalized,
        onchain_score=onchain_score,
        fib_score=fib_score,
        fib_zone=fib_result.current_zone,
        fib_aligned=fib_result.aligned,
        rsi=ta_result.rsi,
        macd_signal=ta_result.macd_signal,
        ema_signal=ta_result.ema_signal,
        bb_signal=ta_result.bb_signal,
        volume_spike=ta_result.volume_spike,
    )

    logger.info(
        f"Signal score: composite={signal_score.composite:.1f} | "
        f"signal={signal_score.signal} | "
        f"trend={trend_directional:.0f} | momentum={momentum_normalized:.0f} | "
        f"volume={volume_normalized:.0f} | onchain={onchain_score:.0f} | "
        f"fib={fib_score:.0f} ({fib_result.current_zone})"
    )

    return signal_score


def analyze_token(
    df: pd.DataFrame,
    current_price: float,
    onchain_score: float = 50.0,
    direction: str = "buy",
) -> tuple[SignalScore, TAResult, FibResult]:
    """
    Run complete analysis pipeline on a token.

    This is the main entry point for Phase 2 signal generation.

    Args:
        df: OHLCV DataFrame
        current_price: Current token price in USD
        onchain_score: Score from the gem scanner (0–100)
        direction: "buy" or "sell"

    Returns:
        (SignalScore, TAResult, FibResult)
    """
    # Step 1: Run all TA indicators
    ta_result = run_all_indicators(df)

    # Step 2: Fibonacci analysis (hard gate)
    fib_result = check_fibonacci_alignment(df, current_price, direction=direction)

    # Step 3: Composite scoring
    signal_score = calculate_composite_score(ta_result, fib_result, onchain_score)

    return signal_score, ta_result, fib_result


def format_analysis_report(
    signal: SignalScore,
    ta: TAResult,
    fib: FibResult,
    token_symbol: str = "???",
) -> str:
    """Format a human-readable analysis report for console/logging."""
    lines = [
        f"",
        f"{'═' * 60}",
        f"  ☘️  SIGNAL ANALYSIS — {token_symbol}",
        f"{'═' * 60}",
        f"",
        f"  COMPOSITE SCORE:  {signal.composite:.1f} / 100  →  {signal.signal}",
        f"  Fibonacci Zone:   {fib.current_zone} ({'✅ ALIGNED' if fib.aligned else '❌ NOT ALIGNED'})",
        f"  Fibonacci Conf:   {fib.confidence:.0f}%",
        f"",
        f"  ── Category Scores ──",
        f"  Trend:     {ta.trend_score:5.1f}  (EMA={ta.ema_signal}, MACD={ta.macd_signal})",
        f"  Momentum:  {ta.momentum_score:5.1f}  (RSI={ta.rsi:.1f})" if ta.rsi else f"  Momentum:  {ta.momentum_score:5.1f}",
        f"  Volume:    {ta.volume_score:5.1f}  ({'🔥 SPIKE' if ta.volume_spike else 'normal'})",
        f"  On-chain:  {signal.onchain_score:5.1f}",
        f"  Fibonacci: {signal.fib_score:5.1f}  ({fib.current_zone})",
        f"",
    ]

    # Fibonacci levels
    if fib.retracement_levels:
        lines.append(f"  ── Fibonacci Levels ──")
        lines.append(f"  Swing High:  {fib.swing_high:.8f}")
        lines.append(f"  Swing Low:   {fib.swing_low:.8f}")
        lines.append(f"  Current:     {fib.current_price:.8f}")
        lines.append(f"  Trend:       {fib.trend}")
        lines.append(f"  Support:     {fib.nearest_support:.8f}")
        lines.append(f"  Resistance:  {fib.nearest_resistance:.8f}")
        lines.append(f"  Stop-Loss:   {fib.stop_loss_level:.8f}")
        lines.append(f"")
        lines.append(f"  Retracements:")
        for ratio, price in sorted(fib.retracement_levels.items()):
            marker = " ◄── PRICE" if abs(price - fib.current_price) / max(price, 1e-10) < 0.03 else ""
            gp = " [GOLDEN POCKET]" if 0.618 <= ratio <= 0.65 else ""
            lines.append(f"    {ratio:.3f}:  {price:.8f}{gp}{marker}")
        lines.append(f"")

    # Take-profit targets
    if fib.take_profit_targets:
        lines.append(f"  ── Take-Profit Targets ──")
        for tp in fib.take_profit_targets:
            lines.append(
                f"    {tp['label']}:  {tp['price']:.8f} "
                f"(Fib {tp['ratio']}) — sell {tp['sell_portion']:.0%}"
            )
        lines.append(f"")

    # Individual indicators
    lines.append(f"  ── Indicator Details ──")
    for ind in ta.trend_indicators + ta.momentum_indicators + ta.volume_indicators:
        emoji = "🟢" if ind.signal == "bullish" else "🔴" if ind.signal == "bearish" else "⚪"
        lines.append(f"    {emoji} {ind}")
    lines.append(f"")
    lines.append(f"{'═' * 60}")

    return "\n".join(lines)
