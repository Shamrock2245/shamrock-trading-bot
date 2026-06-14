"""
ml/hl_backtest.py — Hyperliquid Perps Strategy Backtester

Fetches real historical OHLCV data from the Hyperliquid API and simulates
the HLPerpsScanner strategy to validate the $500/day profit target before
going live.

Usage:
    python3 -m ml.hl_backtest                    # Run full backtest (30d)
    python3 -m ml.hl_backtest --days 7           # 7-day backtest
    python3 -m ml.hl_backtest --coin BTC ETH SOL # Specific coins only
    python3 -m ml.hl_backtest --report           # Save HTML report

Output:
    - Console summary with per-coin and aggregate stats
    - data/backtest/hl_perps_backtest_YYYYMMDD.json
    - data/backtest/hl_perps_backtest_YYYYMMDD.html (if --report)
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Allow running as a module from repo root
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.hl_perps_scanner import (
    _rsi, _ema, _macd, _bollinger, _volume_spike, _score_signal,
    HL_PERPS_WATCHLIST, HL_PERPS_MIN_SCORE,
    HL_PERPS_STOP_LOSS_PCT, HL_PERPS_TAKE_PROFIT_PCT,
    HL_PERPS_LEVERAGE, HL_PERPS_MAX_POSITION_USD,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────
BACKTEST_LOOKBACK_DAYS: int = int(os.getenv("HL_BACKTEST_DAYS", "30"))
BACKTEST_INTERVAL: str = "1h"
BACKTEST_OUTPUT_DIR = Path("data/backtest")
# Hyperliquid taker fee: 0.035% per side
TAKER_FEE_PCT: float = 0.00035
# Slippage estimate: 0.05% per side
SLIPPAGE_PCT: float = 0.0005
# Round-trip cost per trade (both sides)
ROUND_TRIP_COST_PCT: float = (TAKER_FEE_PCT + SLIPPAGE_PCT) * 2


# ─────────────────────────────────────────────────────────────────────────────
# Data models
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class BacktestTrade:
    """A single simulated trade."""
    coin: str
    direction: str          # "long" or "short"
    entry_time: str
    exit_time: str
    entry_price: float
    exit_price: float
    exit_reason: str        # "take_profit", "stop_loss", "end_of_data"
    pnl_pct: float          # Net PnL % (after fees, before leverage)
    pnl_usd: float          # Net PnL in USD (with leverage applied)
    position_size_usd: float
    leverage: int
    score: float
    rsi: Optional[float] = None
    funding_rate: Optional[float] = None


@dataclass
class CoinBacktestResult:
    """Backtest results for a single coin."""
    coin: str
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    total_pnl_usd: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    max_drawdown_usd: float = 0.0
    avg_win_usd: float = 0.0
    avg_loss_usd: float = 0.0
    win_rate_pct: float = 0.0
    profit_factor: float = 0.0
    sharpe_ratio: float = 0.0
    trades: list[BacktestTrade] = field(default_factory=list)


@dataclass
class BacktestReport:
    """Aggregate backtest report across all coins."""
    run_date: str
    lookback_days: int
    coins_tested: int
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    total_pnl_usd: float = 0.0
    win_rate_pct: float = 0.0
    profit_factor: float = 0.0
    sharpe_ratio: float = 0.0
    avg_daily_pnl_usd: float = 0.0
    max_drawdown_usd: float = 0.0
    projected_monthly_usd: float = 0.0
    hits_500_daily_target: bool = False
    coin_results: list[CoinBacktestResult] = field(default_factory=list)
    config: dict = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# Data fetching
# ─────────────────────────────────────────────────────────────────────────────

def fetch_candles(info, coin: str, interval: str, lookback_days: int) -> list[dict]:
    """Fetch historical candles from Hyperliquid."""
    now_ms = int(time.time() * 1000)
    start_ms = now_ms - lookback_days * 24 * 3600 * 1000
    try:
        candles = info.candles_snapshot(coin, interval, start_ms, now_ms)
        return candles or []
    except Exception as e:
        logger.warning(f"Backtest: candle fetch failed for {coin}: {e}")
        return []


def fetch_funding_history(info, coin: str, lookback_days: int) -> dict[int, float]:
    """
    Fetch funding rate history and return a dict of {timestamp_ms: rate}.
    Funding is paid every 8 hours on HL.
    """
    now_ms = int(time.time() * 1000)
    start_ms = now_ms - lookback_days * 24 * 3600 * 1000
    try:
        records = info.funding_history(coin, start_ms, now_ms)
        return {int(r["time"]): float(r["fundingRate"]) for r in records}
    except Exception as e:
        logger.debug(f"Backtest: funding history failed for {coin}: {e}")
        return {}


def get_funding_at_time(funding_history: dict[int, float], timestamp_ms: int) -> float:
    """Get the most recent funding rate at or before a given timestamp."""
    if not funding_history:
        return 0.0
    # Find the closest funding rate <= timestamp
    candidates = [(t, r) for t, r in funding_history.items() if t <= timestamp_ms]
    if not candidates:
        return 0.0
    return max(candidates, key=lambda x: x[0])[1]


# ─────────────────────────────────────────────────────────────────────────────
# Simulation engine
# ─────────────────────────────────────────────────────────────────────────────

def simulate_coin(
    coin: str,
    candles: list[dict],
    funding_history: dict[int, float],
    warmup_bars: int = 35,
) -> CoinBacktestResult:
    """
    Walk-forward simulation of the HLPerpsScanner strategy on historical data.

    For each bar (after warmup):
      1. Score the market using the same _score_signal() function used live
      2. If score >= threshold and direction != "none": enter trade
      3. On subsequent bars: check TP/SL exit conditions
      4. Track PnL, win/loss, drawdown

    This uses the EXACT same scoring logic as the live scanner — no lookahead.
    """
    result = CoinBacktestResult(coin=coin)

    if len(candles) < warmup_bars + 5:
        logger.warning(f"Backtest: insufficient candles for {coin} ({len(candles)})")
        return result

    closes = [float(c["c"]) for c in candles]
    highs = [float(c["h"]) for c in candles]
    lows = [float(c["l"]) for c in candles]
    volumes = [float(c["v"]) for c in candles]
    timestamps = [int(c["t"]) for c in candles]

    in_trade = False
    trade_direction = ""
    entry_price = 0.0
    entry_bar = 0
    entry_time = ""
    entry_score = 0.0
    entry_rsi = None
    entry_funding = 0.0
    stop_loss = 0.0
    take_profit = 0.0

    sl_pct = HL_PERPS_STOP_LOSS_PCT / 100
    tp_pct = HL_PERPS_TAKE_PROFIT_PCT / 100

    # Running equity curve for drawdown calculation
    equity = 0.0
    peak_equity = 0.0
    max_drawdown = 0.0

    pnl_series: list[float] = []

    for i in range(warmup_bars, len(candles)):
        current_price = closes[i]
        current_time = datetime.fromtimestamp(timestamps[i] / 1000, tz=timezone.utc).isoformat()
        funding_rate = get_funding_at_time(funding_history, timestamps[i])

        # ── Exit check (must come before entry to avoid same-bar entry+exit) ──
        if in_trade:
            high = highs[i]
            low = lows[i]

            hit_tp = False
            hit_sl = False

            if trade_direction == "long":
                if high >= take_profit:
                    hit_tp = True
                    exit_price = take_profit
                elif low <= stop_loss:
                    hit_sl = True
                    exit_price = stop_loss
            else:  # short
                if low <= take_profit:
                    hit_tp = True
                    exit_price = take_profit
                elif high >= stop_loss:
                    hit_sl = True
                    exit_price = stop_loss

            if hit_tp or hit_sl:
                # Calculate PnL
                if trade_direction == "long":
                    raw_pnl_pct = (exit_price - entry_price) / entry_price
                else:
                    raw_pnl_pct = (entry_price - exit_price) / entry_price

                # Apply leverage, subtract round-trip costs
                leveraged_pnl_pct = raw_pnl_pct * HL_PERPS_LEVERAGE - ROUND_TRIP_COST_PCT
                pnl_usd = leveraged_pnl_pct * HL_PERPS_MAX_POSITION_USD

                trade = BacktestTrade(
                    coin=coin,
                    direction=trade_direction,
                    entry_time=entry_time,
                    exit_time=current_time,
                    entry_price=entry_price,
                    exit_price=exit_price,
                    exit_reason="take_profit" if hit_tp else "stop_loss",
                    pnl_pct=round(leveraged_pnl_pct * 100, 3),
                    pnl_usd=round(pnl_usd, 2),
                    position_size_usd=HL_PERPS_MAX_POSITION_USD,
                    leverage=HL_PERPS_LEVERAGE,
                    score=entry_score,
                    rsi=entry_rsi,
                    funding_rate=entry_funding,
                )
                result.trades.append(trade)
                result.total_trades += 1
                result.total_pnl_usd += pnl_usd
                pnl_series.append(pnl_usd)

                if pnl_usd > 0:
                    result.wins += 1
                    result.gross_profit += pnl_usd
                else:
                    result.losses += 1
                    result.gross_loss += abs(pnl_usd)

                # Update equity curve
                equity += pnl_usd
                peak_equity = max(peak_equity, equity)
                drawdown = peak_equity - equity
                max_drawdown = max(max_drawdown, drawdown)

                in_trade = False
                trade_direction = ""

        # ── Entry check (only if not in a trade) ─────────────────────────────
        if not in_trade:
            # Use only data available up to bar i (no lookahead)
            hist_closes = closes[:i + 1]
            hist_volumes = volumes[:i + 1]

            score, direction, components = _score_signal(hist_closes, hist_volumes, funding_rate)

            if direction != "none" and score >= HL_PERPS_MIN_SCORE:
                in_trade = True
                trade_direction = direction
                entry_price = current_price
                entry_bar = i
                entry_time = current_time
                entry_score = score
                entry_rsi = components.get("rsi")
                entry_funding = funding_rate

                if direction == "long":
                    stop_loss = entry_price * (1 - sl_pct)
                    take_profit = entry_price * (1 + tp_pct)
                else:
                    stop_loss = entry_price * (1 + sl_pct)
                    take_profit = entry_price * (1 - tp_pct)

    # Close any open trade at end of data
    if in_trade:
        exit_price = closes[-1]
        if trade_direction == "long":
            raw_pnl_pct = (exit_price - entry_price) / entry_price
        else:
            raw_pnl_pct = (entry_price - exit_price) / entry_price
        leveraged_pnl_pct = raw_pnl_pct * HL_PERPS_LEVERAGE - ROUND_TRIP_COST_PCT
        pnl_usd = leveraged_pnl_pct * HL_PERPS_MAX_POSITION_USD
        result.trades.append(BacktestTrade(
            coin=coin,
            direction=trade_direction,
            entry_time=entry_time,
            exit_time=datetime.fromtimestamp(timestamps[-1] / 1000, tz=timezone.utc).isoformat(),
            entry_price=entry_price,
            exit_price=exit_price,
            exit_reason="end_of_data",
            pnl_pct=round(leveraged_pnl_pct * 100, 3),
            pnl_usd=round(pnl_usd, 2),
            position_size_usd=HL_PERPS_MAX_POSITION_USD,
            leverage=HL_PERPS_LEVERAGE,
            score=entry_score,
            rsi=entry_rsi,
            funding_rate=entry_funding,
        ))
        result.total_trades += 1
        result.total_pnl_usd += pnl_usd
        pnl_series.append(pnl_usd)
        if pnl_usd > 0:
            result.wins += 1
            result.gross_profit += pnl_usd
        else:
            result.losses += 1
            result.gross_loss += abs(pnl_usd)

    result.max_drawdown_usd = round(max_drawdown, 2)
    result.total_pnl_usd = round(result.total_pnl_usd, 2)

    if result.total_trades > 0:
        result.win_rate_pct = round(result.wins / result.total_trades * 100, 1)
        result.avg_win_usd = round(result.gross_profit / result.wins, 2) if result.wins else 0
        result.avg_loss_usd = round(result.gross_loss / result.losses, 2) if result.losses else 0
        result.profit_factor = round(result.gross_profit / result.gross_loss, 2) if result.gross_loss > 0 else 10.0

    # Sharpe ratio (annualized, using hourly PnL series)
    if len(pnl_series) > 1:
        mean_pnl = sum(pnl_series) / len(pnl_series)
        variance = sum((p - mean_pnl) ** 2 for p in pnl_series) / len(pnl_series)
        std_pnl = math.sqrt(variance)
        if std_pnl > 0:
            # Annualize: 24 bars/day * 365 days
            result.sharpe_ratio = round((mean_pnl / std_pnl) * math.sqrt(24 * 365), 2)

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Main backtest runner
# ─────────────────────────────────────────────────────────────────────────────

def run_backtest(
    coins: Optional[list[str]] = None,
    lookback_days: int = BACKTEST_LOOKBACK_DAYS,
    save_report: bool = True,
) -> BacktestReport:
    """
    Run the full backtest across the watchlist.

    Args:
        coins: Specific coins to test (defaults to full HL_PERPS_WATCHLIST)
        lookback_days: How many days of history to use
        save_report: Whether to save JSON + HTML report

    Returns:
        BacktestReport with aggregate and per-coin results
    """
    try:
        from hyperliquid.info import Info
    except ImportError:
        logger.error("hyperliquid-python-sdk not installed — pip install hyperliquid-python-sdk")
        sys.exit(1)

    info = Info("https://api.hyperliquid.xyz", skip_ws=True)
    test_coins = coins or HL_PERPS_WATCHLIST

    logger.info(
        f"🔬 Starting HL Perps Backtest | {len(test_coins)} coins | "
        f"{lookback_days}d lookback | leverage={HL_PERPS_LEVERAGE}x | "
        f"TP={HL_PERPS_TAKE_PROFIT_PCT}% | SL={HL_PERPS_STOP_LOSS_PCT}%"
    )

    report = BacktestReport(
        run_date=datetime.now(timezone.utc).isoformat(),
        lookback_days=lookback_days,
        coins_tested=len(test_coins),
        config={
            "leverage": HL_PERPS_LEVERAGE,
            "take_profit_pct": HL_PERPS_TAKE_PROFIT_PCT,
            "stop_loss_pct": HL_PERPS_STOP_LOSS_PCT,
            "min_score": HL_PERPS_MIN_SCORE,
            "position_size_usd": HL_PERPS_MAX_POSITION_USD,
            "taker_fee_pct": TAKER_FEE_PCT * 100,
            "slippage_pct": SLIPPAGE_PCT * 100,
            "round_trip_cost_pct": ROUND_TRIP_COST_PCT * 100,
        }
    )

    all_pnl_series: list[float] = []

    for i, coin in enumerate(test_coins):
        logger.info(f"  [{i+1}/{len(test_coins)}] Backtesting {coin}...")

        candles = fetch_candles(info, coin, BACKTEST_INTERVAL, lookback_days)
        if not candles:
            logger.warning(f"  Skipping {coin} — no candle data")
            continue

        funding_history = fetch_funding_history(info, coin, lookback_days)
        coin_result = simulate_coin(coin, candles, funding_history)

        if coin_result.total_trades == 0:
            logger.info(f"  {coin}: 0 trades (no signals above threshold)")
            continue

        report.coin_results.append(coin_result)
        report.total_trades += coin_result.total_trades
        report.wins += coin_result.wins
        report.losses += coin_result.losses
        report.total_pnl_usd += coin_result.total_pnl_usd

        all_pnl_series.extend([t.pnl_usd for t in coin_result.trades])

        logger.info(
            f"  {coin}: {coin_result.total_trades} trades | "
            f"WR={coin_result.win_rate_pct:.0f}% | "
            f"PF={coin_result.profit_factor:.2f} | "
            f"PnL=${coin_result.total_pnl_usd:+.2f} | "
            f"Sharpe={coin_result.sharpe_ratio:.2f}"
        )

        # Rate limit: be polite to the API
        time.sleep(0.3)

    # Aggregate stats
    if report.total_trades > 0:
        report.win_rate_pct = round(report.wins / report.total_trades * 100, 1)
        gross_profit = sum(r.gross_profit for r in report.coin_results)
        gross_loss = sum(r.gross_loss for r in report.coin_results)
        report.profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else 10.0
        report.max_drawdown_usd = round(max((r.max_drawdown_usd for r in report.coin_results), default=0), 2)
        report.avg_daily_pnl_usd = round(report.total_pnl_usd / lookback_days, 2)
        report.projected_monthly_usd = round(report.avg_daily_pnl_usd * 30, 2)
        report.hits_500_daily_target = report.avg_daily_pnl_usd >= 500.0

    # Aggregate Sharpe
    if len(all_pnl_series) > 1:
        mean_pnl = sum(all_pnl_series) / len(all_pnl_series)
        variance = sum((p - mean_pnl) ** 2 for p in all_pnl_series) / len(all_pnl_series)
        std_pnl = math.sqrt(variance)
        if std_pnl > 0:
            report.sharpe_ratio = round((mean_pnl / std_pnl) * math.sqrt(24 * 365), 2)

    # Print summary
    _print_summary(report)

    # Save outputs
    if save_report:
        BACKTEST_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
        json_path = BACKTEST_OUTPUT_DIR / f"hl_perps_backtest_{date_str}.json"

        # Convert to JSON-serializable dict
        report_dict = asdict(report)
        json_path.write_text(json.dumps(report_dict, indent=2))
        logger.info(f"📄 Backtest report saved: {json_path}")

        # HTML report
        html_path = BACKTEST_OUTPUT_DIR / f"hl_perps_backtest_{date_str}.html"
        _save_html_report(report, html_path)
        logger.info(f"📊 HTML report saved: {html_path}")

    return report


def _print_summary(report: BacktestReport) -> None:
    """Print a clean console summary."""
    print("\n" + "=" * 70)
    print("  HYPERLIQUID PERPS BACKTEST RESULTS")
    print("=" * 70)
    print(f"  Period:          {report.lookback_days} days")
    print(f"  Coins tested:    {report.coins_tested}")
    print(f"  Total trades:    {report.total_trades}")
    print(f"  Win rate:        {report.win_rate_pct:.1f}%")
    print(f"  Profit factor:   {report.profit_factor:.2f}")
    print(f"  Sharpe ratio:    {report.sharpe_ratio:.2f}")
    print(f"  Total PnL:       ${report.total_pnl_usd:+,.2f}")
    print(f"  Avg daily PnL:   ${report.avg_daily_pnl_usd:+,.2f}")
    print(f"  Projected/month: ${report.projected_monthly_usd:+,.2f}")
    print(f"  Max drawdown:    ${report.max_drawdown_usd:.2f}")
    target_icon = "✅" if report.hits_500_daily_target else "❌"
    print(f"  $500/day target: {target_icon} {'HIT' if report.hits_500_daily_target else 'MISS'}")
    print("-" * 70)
    print(f"  {'Coin':<12} {'Trades':>6} {'WR%':>6} {'PF':>6} {'PnL':>10} {'Sharpe':>8}")
    print("-" * 70)

    sorted_results = sorted(report.coin_results, key=lambda r: r.total_pnl_usd, reverse=True)
    for r in sorted_results[:20]:  # Top 20 by PnL
        print(
            f"  {r.coin:<12} {r.total_trades:>6} {r.win_rate_pct:>6.1f} "
            f"{r.profit_factor:>6.2f} {r.total_pnl_usd:>+10.2f} {r.sharpe_ratio:>8.2f}"
        )
    print("=" * 70 + "\n")


def _save_html_report(report: BacktestReport, path: Path) -> None:
    """Generate a simple HTML report."""
    rows = ""
    sorted_results = sorted(report.coin_results, key=lambda r: r.total_pnl_usd, reverse=True)
    for r in sorted_results:
        color = "#22c55e" if r.total_pnl_usd >= 0 else "#ef4444"
        rows += (
            f"<tr><td>{r.coin}</td><td>{r.total_trades}</td>"
            f"<td>{r.win_rate_pct:.1f}%</td><td>{r.profit_factor:.2f}</td>"
            f"<td style='color:{color}'>${r.total_pnl_usd:+.2f}</td>"
            f"<td>{r.sharpe_ratio:.2f}</td><td>${r.max_drawdown_usd:.2f}</td></tr>\n"
        )

    target_color = "#22c55e" if report.hits_500_daily_target else "#ef4444"
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>HL Perps Backtest — {report.run_date[:10]}</title>
<style>
body{{font-family:monospace;background:#0f172a;color:#e2e8f0;padding:2rem}}
h1{{color:#38bdf8}}h2{{color:#7dd3fc}}
table{{border-collapse:collapse;width:100%}}
th,td{{padding:8px 12px;text-align:right;border-bottom:1px solid #1e293b}}
th{{background:#1e293b;color:#94a3b8}}
td:first-child{{text-align:left;font-weight:bold}}
.stat{{display:inline-block;margin:8px 16px 8px 0;padding:12px 20px;
       background:#1e293b;border-radius:8px;min-width:140px}}
.stat-label{{font-size:0.75rem;color:#64748b}}
.stat-value{{font-size:1.4rem;font-weight:bold;color:#38bdf8}}
.hit{{color:#22c55e}}.miss{{color:#ef4444}}
</style></head><body>
<h1>🔬 Hyperliquid Perps Backtest</h1>
<p style="color:#64748b">{report.run_date} | {report.lookback_days}d lookback | 
{HL_PERPS_LEVERAGE}x leverage | TP={HL_PERPS_TAKE_PROFIT_PCT}% | SL={HL_PERPS_STOP_LOSS_PCT}%</p>

<div>
<div class="stat"><div class="stat-label">Total PnL</div>
<div class="stat-value" style="color:{'#22c55e' if report.total_pnl_usd>=0 else '#ef4444'}">${report.total_pnl_usd:+,.2f}</div></div>
<div class="stat"><div class="stat-label">Avg Daily PnL</div>
<div class="stat-value" style="color:{target_color}">${report.avg_daily_pnl_usd:+,.2f}</div></div>
<div class="stat"><div class="stat-label">Projected/Month</div>
<div class="stat-value">${report.projected_monthly_usd:+,.2f}</div></div>
<div class="stat"><div class="stat-label">Win Rate</div>
<div class="stat-value">{report.win_rate_pct:.1f}%</div></div>
<div class="stat"><div class="stat-label">Profit Factor</div>
<div class="stat-value">{report.profit_factor:.2f}</div></div>
<div class="stat"><div class="stat-label">Sharpe Ratio</div>
<div class="stat-value">{report.sharpe_ratio:.2f}</div></div>
<div class="stat"><div class="stat-label">Total Trades</div>
<div class="stat-value">{report.total_trades}</div></div>
<div class="stat"><div class="stat-label">Max Drawdown</div>
<div class="stat-value" style="color:#ef4444">${report.max_drawdown_usd:.2f}</div></div>
<div class="stat"><div class="stat-label">$500/Day Target</div>
<div class="stat-value {'hit' if report.hits_500_daily_target else 'miss'}">
{'✅ HIT' if report.hits_500_daily_target else '❌ MISS'}</div></div>
</div>

<h2>Per-Coin Results</h2>
<table>
<tr><th>Coin</th><th>Trades</th><th>Win Rate</th><th>Profit Factor</th>
<th>Total PnL</th><th>Sharpe</th><th>Max DD</th></tr>
{rows}
</table>
</body></html>"""
    path.write_text(html)


# ─────────────────────────────────────────────────────────────────────────────
# CLI entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HL Perps Strategy Backtester")
    parser.add_argument("--days", type=int, default=BACKTEST_LOOKBACK_DAYS, help="Lookback days")
    parser.add_argument("--coin", nargs="+", help="Specific coins to test")
    parser.add_argument("--report", action="store_true", default=True, help="Save HTML report")
    parser.add_argument("--no-report", dest="report", action="store_false")
    args = parser.parse_args()

    run_backtest(
        coins=args.coin,
        lookback_days=args.days,
        save_report=args.report,
    )
