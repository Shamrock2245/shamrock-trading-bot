"""
ml/trade_analytics.py — Post-Trade Journal Analytics Engine

Inspired by Freqtrade's hyperopt system and the quant-trading repo's
backtesting approaches. Core insight: learning from your OWN trade
history beats any static strategy optimization.

Analyzes output/trades.json to produce actionable insights:

1. Win Rate by Exit Reason
   - Which exit strategies actually produce profits?
   - e.g., "trailing_stop wins 55%, avg +12%" vs "time_exit wins 20%, avg +8%"

2. Win Rate by Entry Source
   - Which discovery channels find winners?
   - e.g., "pumpfun_graduate: 45% WR, avg +38%" vs "grok_trending: 25% WR"

3. Optimal Hold Time
   - Median/P75 time to TP1 by entry source
   - Used to calibrate TIME_EXIT_HOURS dynamically

4. Signal Decay Analysis
   - Win rate by position age bucket (0-2h, 2-6h, 6-12h, 12-24h)
   - At what age does a signal's edge disappear?

5. Risk-Adjusted Returns
   - Rolling Sharpe and Sortino ratios (7d/30d windows)
   - Identifies when the strategy's edge is strong vs decaying

Output: data/dashboard/trade_analytics.json (for ops dashboard)
Runs every 6 hours (same schedule as weight_optimizer.py)
"""

import json
import logging
import math
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────
_ROOT = Path(__file__).parent.parent
TRADES_PATH = _ROOT / "output" / "trades.json"
ANALYTICS_OUTPUT_PATH = _ROOT / "data" / "dashboard" / "trade_analytics.json"
ANALYTICS_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

ANALYTICS_LOOKBACK_DAYS = int(os.getenv("ANALYTICS_LOOKBACK_DAYS", "30"))
ANALYTICS_MIN_TRADES = int(os.getenv("ANALYTICS_MIN_TRADES", "5"))  # Min trades for any stat

# Age buckets for signal decay analysis
AGE_BUCKETS = [
    (0, 2, "0-2h"),
    (2, 6, "2-6h"),
    (6, 12, "6-12h"),
    (12, 24, "12-24h"),
    (24, 72, "24-72h"),
    (72, float("inf"), "72h+"),
]


# ─────────────────────────────────────────────────────────────────────────────
# Data Loading
# ─────────────────────────────────────────────────────────────────────────────

def _load_trades(lookback_days: int = ANALYTICS_LOOKBACK_DAYS) -> list[dict]:
    """Load closed trades from output/trades.json within the lookback window."""
    if not TRADES_PATH.exists():
        logger.warning(f"Trade analytics: {TRADES_PATH} not found")
        return []

    try:
        with open(TRADES_PATH) as f:
            all_trades = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"Trade analytics: Failed to load trades: {e}")
        return []

    if not isinstance(all_trades, list):
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    sells = []

    for trade in all_trades:
        if trade.get("action", "").upper() != "SELL":
            continue
        try:
            ts_str = trade.get("timestamp", "")
            if ts_str:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if ts < cutoff:
                    continue
        except Exception:
            continue
        if trade.get("pnl_pct") is None:
            continue
        sells.append(trade)

    return sells


# ─────────────────────────────────────────────────────────────────────────────
# Analysis Functions
# ─────────────────────────────────────────────────────────────────────────────

def _analyze_by_exit_reason(trades: list[dict]) -> dict:
    """
    Win rate and average PnL by exit reason.
    Groups by the 'reason' field (e.g., trailing_stop, hard_stop, tp1, time_exit).
    """
    by_reason: dict[str, list[dict]] = {}

    for t in trades:
        reason = t.get("reason", "unknown")
        # Normalize reason (strip profile tags and specific numbers)
        if "trailing_stop" in reason:
            key = "trailing_stop"
        elif "hard_stop" in reason:
            key = "hard_stop"
        elif "pre_tp1_peak" in reason:
            key = "pre_tp1_peak_protection"
        elif "fast_fail" in reason:
            key = "fast_fail"
        elif "tp1" in reason.lower() or "take_profit_1" in reason:
            key = "tp1"
        elif "tp2" in reason.lower() or "take_profit_2" in reason:
            key = "tp2"
        elif "tp3" in reason.lower() or "take_profit_3" in reason:
            key = "tp3"
        elif "time_exit" in reason:
            key = "time_exit"
        elif "emergency" in reason or "analytics_emergency" in reason:
            key = "emergency_exit"
        elif "volume_collapse" in reason or "liquidity_drain" in reason:
            key = "volume_collapse"
        elif "manual" in reason:
            key = "manual"
        else:
            key = reason[:30]  # Truncate unknown reasons

        by_reason.setdefault(key, []).append(t)

    results = {}
    for reason, group in sorted(by_reason.items(), key=lambda x: -len(x[1])):
        if len(group) < 2:
            continue
        pnls = [float(t.get("pnl_pct", 0)) for t in group]
        wins = sum(1 for p in pnls if p > 0)
        results[reason] = {
            "count": len(group),
            "win_rate_pct": round(wins / len(group) * 100, 1),
            "avg_pnl_pct": round(sum(pnls) / len(pnls), 2),
            "median_pnl_pct": round(sorted(pnls)[len(pnls) // 2], 2),
            "best_pnl_pct": round(max(pnls), 2),
            "worst_pnl_pct": round(min(pnls), 2),
        }

    return results


def _analyze_by_entry_source(trades: list[dict]) -> dict:
    """Win rate and average PnL by entry source / discovery channel."""
    by_source: dict[str, list[dict]] = {}

    for t in trades:
        source = t.get("source", t.get("entry_source", "unknown"))
        by_source.setdefault(source, []).append(t)

    results = {}
    for source, group in sorted(by_source.items(), key=lambda x: -len(x[1])):
        if len(group) < ANALYTICS_MIN_TRADES:
            continue
        pnls = [float(t.get("pnl_pct", 0)) for t in group]
        wins = sum(1 for p in pnls if p > 0)
        results[source] = {
            "count": len(group),
            "win_rate_pct": round(wins / len(group) * 100, 1),
            "avg_pnl_pct": round(sum(pnls) / len(pnls), 2),
            "total_pnl_usd": round(sum(float(t.get("pnl_usd", 0)) for t in group), 2),
        }

    return results


def _analyze_hold_times(trades: list[dict]) -> dict:
    """
    Optimal hold time analysis.
    Measures median and P75 time to exit for winners vs losers.
    """
    hold_times_winners = []
    hold_times_losers = []

    for t in trades:
        try:
            entry_ts = t.get("entry_time", t.get("entry_timestamp", ""))
            exit_ts = t.get("timestamp", "")
            if not entry_ts or not exit_ts:
                continue
            entry_dt = datetime.fromisoformat(str(entry_ts).replace("Z", "+00:00"))
            exit_dt = datetime.fromisoformat(str(exit_ts).replace("Z", "+00:00"))
            hold_hours = (exit_dt - entry_dt).total_seconds() / 3600

            if hold_hours <= 0 or hold_hours > 168:  # Sanity: 0–7 days
                continue

            pnl = float(t.get("pnl_pct", 0))
            if pnl > 0:
                hold_times_winners.append(hold_hours)
            else:
                hold_times_losers.append(hold_hours)
        except Exception:
            continue

    def _stats(times: list[float]) -> dict:
        if not times:
            return {"count": 0}
        times.sort()
        return {
            "count": len(times),
            "median_hours": round(times[len(times) // 2], 2),
            "p75_hours": round(times[int(len(times) * 0.75)] if len(times) > 3 else times[-1], 2),
            "avg_hours": round(sum(times) / len(times), 2),
            "min_hours": round(times[0], 2),
            "max_hours": round(times[-1], 2),
        }

    return {
        "winners": _stats(hold_times_winners),
        "losers": _stats(hold_times_losers),
        "recommendation": _hold_time_recommendation(hold_times_winners, hold_times_losers),
    }


def _hold_time_recommendation(winners: list[float], losers: list[float]) -> str:
    """Generate a recommendation for TIME_EXIT_HOURS based on hold time data."""
    if not winners or not losers:
        return "Insufficient data for recommendation"

    winner_median = sorted(winners)[len(winners) // 2]
    loser_median = sorted(losers)[len(losers) // 2]

    if loser_median < 4 and winner_median > 8:
        return f"Losers die fast (median {loser_median:.1f}h), winners take time (median {winner_median:.1f}h). Consider FAST_FAIL_HOURS={loser_median:.0f}h"
    elif winner_median < 6:
        return f"Winners resolve quickly (median {winner_median:.1f}h). Consider TIME_EXIT_HOURS={winner_median * 2:.0f}h"
    else:
        return f"Winner median: {winner_median:.1f}h, Loser median: {loser_median:.1f}h — current settings look reasonable"


def _analyze_signal_decay(trades: list[dict]) -> dict:
    """
    Signal decay analysis — win rate by position age bucket.
    Reveals at what point the entry signal's edge disappears.
    """
    buckets: dict[str, list[float]] = {label: [] for _, _, label in AGE_BUCKETS}

    for t in trades:
        try:
            entry_ts = t.get("entry_time", t.get("entry_timestamp", ""))
            exit_ts = t.get("timestamp", "")
            if not entry_ts or not exit_ts:
                continue
            entry_dt = datetime.fromisoformat(str(entry_ts).replace("Z", "+00:00"))
            exit_dt = datetime.fromisoformat(str(exit_ts).replace("Z", "+00:00"))
            hold_hours = (exit_dt - entry_dt).total_seconds() / 3600
            pnl = float(t.get("pnl_pct", 0))

            for lo, hi, label in AGE_BUCKETS:
                if lo <= hold_hours < hi:
                    buckets[label].append(pnl)
                    break
        except Exception:
            continue

    results = {}
    for label, pnls in buckets.items():
        if len(pnls) < 2:
            results[label] = {"count": len(pnls), "win_rate_pct": None}
            continue
        wins = sum(1 for p in pnls if p > 0)
        results[label] = {
            "count": len(pnls),
            "win_rate_pct": round(wins / len(pnls) * 100, 1),
            "avg_pnl_pct": round(sum(pnls) / len(pnls), 2),
        }

    return results


def _calculate_risk_metrics(trades: list[dict]) -> dict:
    """
    Rolling Sharpe and Sortino ratios.
    Uses PnL percentage as returns series.
    """
    pnls = [float(t.get("pnl_pct", 0)) for t in trades]
    if len(pnls) < 5:
        return {"sharpe_7d": None, "sortino_7d": None, "sharpe_30d": None}

    def _sharpe(returns: list[float]) -> Optional[float]:
        if len(returns) < 3:
            return None
        mean = sum(returns) / len(returns)
        variance = sum((r - mean) ** 2 for r in returns) / len(returns)
        std = math.sqrt(variance) if variance > 0 else 0.001
        return round(mean / std, 3)

    def _sortino(returns: list[float]) -> Optional[float]:
        if len(returns) < 3:
            return None
        mean = sum(returns) / len(returns)
        downside = [r for r in returns if r < 0]
        if not downside:
            return round(mean / 0.001, 3)  # No downside = excellent
        downside_var = sum(r ** 2 for r in downside) / len(downside)
        downside_std = math.sqrt(downside_var) if downside_var > 0 else 0.001
        return round(mean / downside_std, 3)

    # Get trades by recency for rolling windows
    # Last 7 days
    now = datetime.now(timezone.utc)
    pnls_7d = []
    pnls_30d = []
    for t in trades:
        try:
            ts = datetime.fromisoformat(str(t.get("timestamp", "")).replace("Z", "+00:00"))
            age_days = (now - ts).total_seconds() / 86400
            if age_days <= 7:
                pnls_7d.append(float(t.get("pnl_pct", 0)))
            if age_days <= 30:
                pnls_30d.append(float(t.get("pnl_pct", 0)))
        except Exception:
            continue

    return {
        "sharpe_7d": _sharpe(pnls_7d),
        "sortino_7d": _sortino(pnls_7d),
        "sharpe_30d": _sharpe(pnls_30d),
        "sortino_30d": _sortino(pnls_30d),
        "total_trades_7d": len(pnls_7d),
        "total_trades_30d": len(pnls_30d),
        "win_rate_7d": round(sum(1 for p in pnls_7d if p > 0) / max(len(pnls_7d), 1) * 100, 1),
        "win_rate_30d": round(sum(1 for p in pnls_30d if p > 0) / max(len(pnls_30d), 1) * 100, 1),
        "avg_win_pct": round(
            sum(p for p in pnls_30d if p > 0) / max(sum(1 for p in pnls_30d if p > 0), 1), 2
        ),
        "avg_loss_pct": round(
            sum(p for p in pnls_30d if p < 0) / max(sum(1 for p in pnls_30d if p < 0), 1), 2
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main API
# ─────────────────────────────────────────────────────────────────────────────

def _analyze_ml_performance(trades: list[dict]) -> dict:
    """
    Measure ML model accuracy by comparing predictions to actual outcomes.
    
    TimesFM: Did UP forecasts actually produce winning trades?
    RL Sizer: Did position sizes correlate with trade outcomes?
    """
    # ── TimesFM Forecast Accuracy ──────────────────────────────────────────
    tf_correct = 0
    tf_total = 0
    tf_by_direction: dict[str, list[float]] = {"UP": [], "DOWN": [], "FLAT": []}
    
    for t in trades:
        tf_dir = t.get("timesfm_direction", t.get("forecast_direction", ""))
        if not tf_dir or tf_dir not in ("UP", "DOWN", "FLAT"):
            continue
        pnl = float(t.get("pnl_pct", 0))
        tf_by_direction[tf_dir].append(pnl)
        tf_total += 1
        
        # Correct if: UP and pnl > 0, DOWN and pnl < 0, FLAT is always neutral
        if (tf_dir == "UP" and pnl > 0) or (tf_dir == "DOWN" and pnl < 0):
            tf_correct += 1
    
    timesfm_metrics = {
        "total_forecasted_trades": tf_total,
        "accuracy_pct": round(tf_correct / tf_total * 100, 1) if tf_total > 0 else None,
    }
    for direction, pnls in tf_by_direction.items():
        if pnls:
            wins = sum(1 for p in pnls if p > 0)
            timesfm_metrics[f"{direction.lower()}_count"] = len(pnls)
            timesfm_metrics[f"{direction.lower()}_win_rate_pct"] = round(wins / len(pnls) * 100, 1)
            timesfm_metrics[f"{direction.lower()}_avg_pnl_pct"] = round(sum(pnls) / len(pnls), 2)

    # ── RL Sizer Correlation ────────────────────────────────────────────────
    sized_trades = [(float(t.get("position_size_multiplier", 1.0)), float(t.get("pnl_pct", 0)))
                    for t in trades if t.get("position_size_multiplier")]
    
    rl_metrics: dict = {"total_sized_trades": len(sized_trades)}
    if len(sized_trades) >= 5:
        # Compare high-conviction (multiplier >= 0.8) vs low-conviction (< 0.6)
        high_conv = [pnl for mult, pnl in sized_trades if mult >= 0.8]
        low_conv = [pnl for mult, pnl in sized_trades if mult < 0.6]
        if high_conv:
            rl_metrics["high_conviction_count"] = len(high_conv)
            rl_metrics["high_conviction_avg_pnl_pct"] = round(sum(high_conv) / len(high_conv), 2)
            rl_metrics["high_conviction_win_rate_pct"] = round(
                sum(1 for p in high_conv if p > 0) / len(high_conv) * 100, 1
            )
        if low_conv:
            rl_metrics["low_conviction_count"] = len(low_conv)
            rl_metrics["low_conviction_avg_pnl_pct"] = round(sum(low_conv) / len(low_conv), 2)
            rl_metrics["low_conviction_win_rate_pct"] = round(
                sum(1 for p in low_conv if p > 0) / len(low_conv) * 100, 1
            )

    return {
        "timesfm": timesfm_metrics,
        "rl_sizer": rl_metrics,
    }


def run_analytics(lookback_days: int = ANALYTICS_LOOKBACK_DAYS) -> dict:
    """
    Run full trade analytics and save results to disk.

    Returns dict with all analysis results.
    """
    logger.info(f"📊 Trade analytics: loading trades (last {lookback_days} days)...")
    trades = _load_trades(lookback_days)

    if len(trades) < ANALYTICS_MIN_TRADES:
        logger.info(
            f"Trade analytics: insufficient trades ({len(trades)} < {ANALYTICS_MIN_TRADES}) — skipping"
        )
        return {"status": "insufficient_data", "trade_count": len(trades)}

    logger.info(f"📊 Trade analytics: analyzing {len(trades)} closed trades...")

    results = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lookback_days": lookback_days,
        "total_trades": len(trades),

        # Core analyses
        "by_exit_reason": _analyze_by_exit_reason(trades),
        "by_entry_source": _analyze_by_entry_source(trades),
        "hold_times": _analyze_hold_times(trades),
        "signal_decay": _analyze_signal_decay(trades),
        "risk_metrics": _calculate_risk_metrics(trades),

        # Summary stats
        "overall_win_rate_pct": round(
            sum(1 for t in trades if float(t.get("pnl_pct", 0)) > 0) / len(trades) * 100, 1
        ),
        "overall_avg_pnl_pct": round(
            sum(float(t.get("pnl_pct", 0)) for t in trades) / len(trades), 2
        ),
        "total_realized_pnl_usd": round(
            sum(float(t.get("pnl_usd", 0)) for t in trades), 2
        ),

        # Fix 8: ML model performance metrics
        "ml_performance": _analyze_ml_performance(trades),
    }

    # Save to disk
    try:
        with open(ANALYTICS_OUTPUT_PATH, "w") as f:
            json.dump(results, f, indent=2)
        logger.info(f"📊 Trade analytics saved to {ANALYTICS_OUTPUT_PATH}")
    except Exception as e:
        logger.error(f"Trade analytics: failed to save results: {e}")

    # Log key insights
    logger.info(
        f"📊 Analytics Summary: "
        f"{results['total_trades']} trades | "
        f"WR={results['overall_win_rate_pct']}% | "
        f"avg PnL={results['overall_avg_pnl_pct']:+.1f}% | "
        f"total PnL=${results['total_realized_pnl_usd']:+,.2f}"
    )

    risk = results.get("risk_metrics", {})
    if risk.get("sharpe_7d") is not None:
        logger.info(
            f"📊 Risk metrics: "
            f"Sharpe7d={risk['sharpe_7d']:.3f} "
            f"Sortino7d={risk.get('sortino_7d', 'N/A')} | "
            f"Sharpe30d={risk.get('sharpe_30d', 'N/A')}"
        )

    # Log best and worst exit reasons
    by_exit = results.get("by_exit_reason", {})
    if by_exit:
        best = max(by_exit.items(), key=lambda x: x[1].get("avg_pnl_pct", -999))
        worst = min(by_exit.items(), key=lambda x: x[1].get("avg_pnl_pct", 999))
        logger.info(
            f"📊 Best exit: {best[0]} (WR={best[1]['win_rate_pct']}%, avg={best[1]['avg_pnl_pct']:+.1f}%) | "
            f"Worst exit: {worst[0]} (WR={worst[1]['win_rate_pct']}%, avg={worst[1]['avg_pnl_pct']:+.1f}%)"
        )

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Standalone execution
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    results = run_analytics()
    if results.get("status") != "insufficient_data":
        print("\n=== Trade Analytics ===")
        print(json.dumps(results, indent=2))
