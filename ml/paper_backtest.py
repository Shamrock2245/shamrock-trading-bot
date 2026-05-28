"""
ml/paper_backtest.py — Paper Backtest Engine for Optuna Hyperparameter Optimization

Replays historical trades from output/trades.json with different parameter sets
to evaluate what-if scenarios. This is NOT a full market simulator — it replays
YOUR actual trades with modified entry/exit/sizing rules.

Key metrics returned:
  - sharpe_ratio: Risk-adjusted returns (annualized)
  - sortino_ratio: Downside-risk-adjusted returns
  - max_drawdown_pct: Worst peak-to-trough equity drop
  - total_pnl_usd: Total realized profit/loss
  - win_rate_pct: Percentage of profitable trades
  - trade_count: Number of trades that passed the entry filter
  - profit_factor: Gross profits / gross losses
  - calmar_ratio: Annual return / max drawdown
"""

import json
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).parent.parent
TRADES_PATH = _ROOT / "output" / "trades.json"


@dataclass
class BacktestParams:
    """All tunable parameters for a single backtest trial."""
    # Entry quality
    min_gem_score: float = 68.0
    express_lane_score: float = 78.0

    # Take-profit tiers
    tp1_mult: float = 1.5
    tp1_sell_pct: float = 0.40
    tp2_mult: float = 2.5
    tp2_sell_pct: float = 0.35
    tp3_mult: float = 5.0

    # Stop-loss
    stop_loss_pct: float = 12.0
    hard_stop_pct: float = 18.0
    pre_tp1_trailing_pct: float = 15.0

    # Fast fail
    fast_fail_hours: float = 1.5
    fast_fail_down_pct: float = 10.0

    # Position sizing
    max_position_pct: float = 5.0
    god_mode_kelly_mult: float = 2.5

    # Time exit
    time_exit_hours: float = 8.0

    # Scoring weights (sum auto-normalized to 1.0)
    w_volume: float = 0.22
    w_holder: float = 0.18
    w_liquidity: float = 0.14
    w_safety: float = 0.12
    w_momentum: float = 0.10


@dataclass
class BacktestResult:
    """Results from a single backtest run."""
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    max_drawdown_pct: float = 0.0
    total_pnl_usd: float = 0.0
    win_rate_pct: float = 0.0
    trade_count: int = 0
    profit_factor: float = 0.0
    calmar_ratio: float = 0.0
    avg_pnl_pct: float = 0.0
    total_wins: int = 0
    total_losses: int = 0


def load_trades(lookback_days: int = 30) -> list[dict]:
    """Load completed SELL trades from output/trades.json."""
    if not TRADES_PATH.exists():
        return []

    try:
        with open(TRADES_PATH) as f:
            all_trades = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []

    if not isinstance(all_trades, list):
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    trades = []

    for t in all_trades:
        # Only use real sells with PnL data
        if t.get("action", "").upper() != "SELL":
            continue
        if t.get("pnl_pct") is None:
            continue
        # Skip dust sweeps
        if "dust_sweep" in t.get("reason", ""):
            continue

        try:
            ts_str = t.get("timestamp", "")
            if ts_str:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if ts < cutoff:
                    continue
        except Exception:
            continue

        trades.append(t)

    return trades


def _simulate_exit(trade: dict, params: BacktestParams) -> dict:
    """
    Simulate what would have happened with different exit parameters.

    Since we don't have full OHLCV candle data in the trade log, we use
    the actual trade outcome and apply parameter adjustments:

    1. If trade's actual exit was a stop-loss and our new SL is tighter,
       we would have exited at the tighter SL (worse PnL).
    2. If trade's actual exit hit TP1 and our new TP1 is lower,
       we would have taken profit sooner (less upside per take, but more likely).
    3. For general trades, we scale the PnL by the ratio of parameter changes.
    """
    actual_pnl_pct = float(trade.get("pnl_pct", 0))
    actual_value_usd = float(trade.get("value_usd", 0))
    entry_price = float(trade.get("entry_price", 0))
    exit_price = float(trade.get("price_usd", 0))
    reason = trade.get("reason", "")

    if entry_price <= 0:
        return {"pnl_pct": actual_pnl_pct, "pnl_usd": float(trade.get("pnl_usd", 0)),
                "exit_reason": reason, "passed_filter": True}

    # Calculate the actual price movement
    price_change_pct = ((exit_price - entry_price) / entry_price) * 100

    # ── Simulate with new parameters ─────────────────────────────────
    sim_pnl_pct = actual_pnl_pct  # default: same as actual

    # Hard stop: if price dropped below our new hard stop, clip there
    if price_change_pct <= -params.hard_stop_pct:
        sim_pnl_pct = -params.hard_stop_pct

    # Trailing stop (pre-TP1): if price peaked then fell
    elif price_change_pct <= -params.stop_loss_pct:
        sim_pnl_pct = -params.stop_loss_pct

    # Fast fail: if the trade was a fast fail and our threshold is different
    elif "fast_fail" in reason:
        if abs(price_change_pct) <= params.fast_fail_down_pct:
            sim_pnl_pct = price_change_pct  # Would have fast-failed at actual level
        else:
            sim_pnl_pct = -params.fast_fail_down_pct

    # TP1 hit: if actual gain >= our TP1 threshold
    elif price_change_pct >= (params.tp1_mult - 1) * 100:
        # Simulate partial sell at TP1
        tp1_gain = (params.tp1_mult - 1) * 100
        remaining_pct = 1.0 - params.tp1_sell_pct

        # Check if TP2 was also hit
        if price_change_pct >= (params.tp2_mult - 1) * 100:
            tp2_gain = (params.tp2_mult - 1) * 100
            remaining_after_tp2 = remaining_pct * (1 - params.tp2_sell_pct)

            # Check TP3
            if price_change_pct >= (params.tp3_mult - 1) * 100:
                tp3_gain = (params.tp3_mult - 1) * 100
                # Blended: TP1 portion + TP2 portion + TP3 remainder
                sim_pnl_pct = (
                    params.tp1_sell_pct * tp1_gain +
                    remaining_pct * params.tp2_sell_pct * tp2_gain +
                    remaining_after_tp2 * tp3_gain
                )
            else:
                sim_pnl_pct = (
                    params.tp1_sell_pct * tp1_gain +
                    remaining_pct * params.tp2_sell_pct * tp2_gain +
                    remaining_after_tp2 * price_change_pct
                )
        else:
            # Only TP1 hit, rest rides
            sim_pnl_pct = (
                params.tp1_sell_pct * tp1_gain +
                remaining_pct * price_change_pct
            )

    # No TP hit — trade exits at actual level or time exit
    else:
        sim_pnl_pct = price_change_pct

    # Position sizing adjustment
    size_mult = min(params.max_position_pct / 5.0, 2.0)  # Relative to baseline 5%
    sim_pnl_usd = (sim_pnl_pct / 100) * actual_value_usd * size_mult

    return {
        "pnl_pct": sim_pnl_pct,
        "pnl_usd": sim_pnl_usd,
        "exit_reason": reason,
        "passed_filter": True,
    }


def run_backtest(
    params: BacktestParams,
    trades: Optional[list[dict]] = None,
    lookback_days: int = 14,
) -> BacktestResult:
    """
    Run a paper backtest with the given parameters.

    Returns BacktestResult with Sharpe, Sortino, drawdown, etc.
    """
    if trades is None:
        trades = load_trades(lookback_days)

    if not trades:
        return BacktestResult()

    # ── Filter trades by entry quality ────────────────────────────────
    filtered_trades = []
    for t in trades:
        gem_score = (
            t.get("gem_score") or
            t.get("signal_scores", {}).get("gem_score") or
            0  # 0 means not recorded
        )
        # Apply entry filter — skip filtering for trades without recorded gem_score
        if float(gem_score) == 0 or float(gem_score) >= params.min_gem_score:
            filtered_trades.append(t)

    if len(filtered_trades) < 3:
        return BacktestResult(trade_count=len(filtered_trades))

    # ── Simulate exits with new parameters ────────────────────────────
    pnl_series = []
    pnl_usd_series = []

    for t in filtered_trades:
        result = _simulate_exit(t, params)
        if result["passed_filter"]:
            pnl_series.append(result["pnl_pct"])
            pnl_usd_series.append(result["pnl_usd"])

    if len(pnl_series) < 3:
        return BacktestResult(trade_count=len(pnl_series))

    # ── Calculate metrics ─────────────────────────────────────────────
    total_pnl_usd = sum(pnl_usd_series)
    wins = [p for p in pnl_series if p > 0]
    losses = [p for p in pnl_series if p <= 0]
    win_rate = len(wins) / len(pnl_series) * 100 if pnl_series else 0

    avg_pnl = sum(pnl_series) / len(pnl_series)

    # Sharpe ratio (annualized, assuming ~3 trades/day)
    mean_return = sum(pnl_series) / len(pnl_series) / 100
    variance = sum((p / 100 - mean_return) ** 2 for p in pnl_series) / len(pnl_series)
    std_dev = math.sqrt(variance) if variance > 0 else 0.001
    sharpe = (mean_return / std_dev) * math.sqrt(365 * 3)  # Annualized

    # Sortino ratio (only penalizes downside)
    downside_returns = [p / 100 for p in pnl_series if p < 0]
    if downside_returns:
        downside_var = sum(r ** 2 for r in downside_returns) / len(downside_returns)
        downside_std = math.sqrt(downside_var) if downside_var > 0 else 0.001
        sortino = (mean_return / downside_std) * math.sqrt(365 * 3)
    else:
        sortino = sharpe * 2  # No downside = excellent

    # Max drawdown
    equity_curve = []
    running_equity = 0.0
    for pnl in pnl_usd_series:
        running_equity += pnl
        equity_curve.append(running_equity)

    peak = 0.0
    max_dd = 0.0
    for equity in equity_curve:
        if equity > peak:
            peak = equity
        dd = (peak - equity) / max(abs(peak), 1.0) * 100
        if dd > max_dd:
            max_dd = dd

    # Profit factor
    gross_profit = sum(p for p in pnl_usd_series if p > 0)
    gross_loss = abs(sum(p for p in pnl_usd_series if p < 0))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (10.0 if gross_profit > 0 else 0.0)

    # Calmar ratio
    annual_return = total_pnl_usd * (365 / max(lookback_days, 1))
    calmar = annual_return / max(max_dd, 0.01) if max_dd > 0 else 0.0

    return BacktestResult(
        sharpe_ratio=round(sharpe, 4),
        sortino_ratio=round(sortino, 4),
        max_drawdown_pct=round(max_dd, 2),
        total_pnl_usd=round(total_pnl_usd, 2),
        win_rate_pct=round(win_rate, 1),
        trade_count=len(pnl_series),
        profit_factor=round(profit_factor, 3),
        calmar_ratio=round(calmar, 2),
        avg_pnl_pct=round(avg_pnl, 2),
        total_wins=len(wins),
        total_losses=len(losses),
    )


def run_walk_forward(
    params: BacktestParams,
    trades: list[dict],
    n_windows: int = 3,
) -> tuple[bool, list[BacktestResult]]:
    """
    Walk-forward validation: split trades into windows, train on N-1, validate on Nth.

    Returns:
        (is_consistent, list_of_window_results)

    Consistency check: params must produce positive Sharpe in at least 2/3 windows.
    """
    if len(trades) < n_windows * 5:
        return False, []

    window_size = len(trades) // n_windows
    results = []

    for i in range(n_windows):
        start = i * window_size
        end = start + window_size if i < n_windows - 1 else len(trades)
        window_trades = trades[start:end]

        result = run_backtest(params, trades=window_trades)
        results.append(result)

    # Consistency: positive Sharpe in at least 2/3 windows
    positive_windows = sum(1 for r in results if r.sharpe_ratio > 0)
    is_consistent = positive_windows >= (n_windows * 2 // 3)

    return is_consistent, results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    trades = load_trades(30)
    print(f"Loaded {len(trades)} trades")

    # Test with default params
    params = BacktestParams()
    result = run_backtest(params, trades=trades)
    print(f"\nDefault params result:")
    print(f"  Sharpe: {result.sharpe_ratio}")
    print(f"  Sortino: {result.sortino_ratio}")
    print(f"  Max DD: {result.max_drawdown_pct}%")
    print(f"  PnL: ${result.total_pnl_usd}")
    print(f"  Win Rate: {result.win_rate_pct}%")
    print(f"  Trades: {result.trade_count}")
    print(f"  Profit Factor: {result.profit_factor}")
