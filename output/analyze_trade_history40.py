#!/usr/bin/env python3
"""
HL Perps Trade History Analysis — CSV 40 (downloaded 2026-07-26)

Methodology stack (aligned with README reference repos + in-repo analytics):
  - Freqtrade: win rate, profit factor, expectancy, drawdown, exit buckets
  - Jesse: clean R-multiple / payoff framing, long vs short split
  - Hummingbot: fee drag, notional sizing, inventory-style coin concentration
  - OpenAlice / ml/trade_analytics.py: hold-duration edge decay, self-history learning
  - docs/HL_PERPS_RAPID_CLOSE_POSTMORTEM.md: <10s / <1m rapid-close fingerprint

Source: /Users/brendan/Downloads/trade_history (40).csv
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

CSV_PATH = Path("/Users/brendan/Downloads/trade_history (40).csv")
# "Today" relative to download: 2026-07-26
AS_OF = pd.Timestamp("2026-07-26")


def load_fills(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["dt"] = pd.to_datetime(df["time"], format="%m/%d/%Y - %H:%M:%S")
    df = df.sort_values("dt").reset_index(drop=True)
    df["is_open"] = df["dir"].str.startswith("Open")
    df["is_close"] = df["dir"].str.startswith("Close")
    df["side"] = np.where(df["dir"].str.contains("Long"), "Long", "Short")
    return df


def pair_trades(df: pd.DataFrame) -> pd.DataFrame:
    """FIFO open→close pairing per coin (same approach as analyze_trade_history39_paired)."""
    trades = []
    for coin, group in df.groupby("coin"):
        open_stack: list = []
        for _, row in group.iterrows():
            if row["is_open"]:
                open_stack.append(row)
            elif row["is_close"]:
                if open_stack:
                    o = open_stack.pop(0)
                    duration_min = (row["dt"] - o["dt"]).total_seconds() / 60.0
                    duration_sec = (row["dt"] - o["dt"]).total_seconds()
                    trades.append(
                        {
                            "coin": coin,
                            "direction": row["side"],
                            "open_time": o["dt"],
                            "close_time": row["dt"],
                            "duration_min": duration_min,
                            "duration_sec": duration_sec,
                            "open_px": float(o["px"]),
                            "close_px": float(row["px"]),
                            "size": float(row["sz"]),
                            "ntl": float(row["ntl"]),
                            "open_ntl": float(o["ntl"]),
                            "pnl": float(row["closedPnl"]),
                            "fee": float(o["fee"]) + float(row["fee"]),
                            "close_fee": float(row["fee"]),
                        }
                    )
                else:
                    trades.append(
                        {
                            "coin": coin,
                            "direction": row["side"],
                            "open_time": row["dt"],
                            "close_time": row["dt"],
                            "duration_min": 0.0,
                            "duration_sec": 0.0,
                            "open_px": float(row["px"]),
                            "close_px": float(row["px"]),
                            "size": float(row["sz"]),
                            "ntl": float(row["ntl"]),
                            "open_ntl": float(row["ntl"]),
                            "pnl": float(row["closedPnl"]),
                            "fee": float(row["fee"]),
                            "close_fee": float(row["fee"]),
                        }
                    )
    return pd.DataFrame(trades)


def dur_bucket(m: float) -> str:
    if m <= 1 / 60:  # <= 1 second treated with sub-bucket below
        return "< 1s*"
    if m * 60 <= 10:
        return "≤10s rapid"
    if m <= 1:
        return "10s–1m"
    if m <= 5:
        return "1m–5m"
    if m <= 30:
        return "5m–30m"
    if m <= 90:
        return "30m–1.5h"
    if m <= 240:
        return "1.5h–4h"
    return ">4h"


def dur_bucket_simple(m: float) -> str:
    if m <= 1:
        return "< 1m"
    if m <= 5:
        return "1m–5m"
    if m <= 30:
        return "5m–30m"
    if m <= 90:
        return "30m–1.5h"
    if m <= 240:
        return "1.5h–4h"
    return ">4h"


def metrics_block(closes_or_trades: pd.DataFrame, pnl_col: str = "closedPnl") -> dict:
    s = closes_or_trades[pnl_col]
    n = len(s)
    if n == 0:
        return {
            "n": 0,
            "wins": 0,
            "losses": 0,
            "wr": 0.0,
            "net": 0.0,
            "gp": 0.0,
            "gl": 0.0,
            "pf": 0.0,
            "avg_w": 0.0,
            "avg_l": 0.0,
            "payoff": 0.0,
            "expectancy": 0.0,
            "avg": 0.0,
            "median": 0.0,
        }
    wins = s[s > 0]
    losses = s[s <= 0]
    gp = float(wins.sum()) if len(wins) else 0.0
    gl = float(abs(losses.sum())) if len(losses) else 0.0
    avg_w = float(wins.mean()) if len(wins) else 0.0
    avg_l = float(losses.mean()) if len(losses) else 0.0
    wr = len(wins) / n
    payoff = abs(avg_w / avg_l) if avg_l != 0 else 0.0
    # Freqtrade-style expectancy = (WR * avg_win) + ((1-WR) * avg_loss)
    expectancy = wr * avg_w + (1 - wr) * avg_l
    return {
        "n": n,
        "wins": len(wins),
        "losses": len(losses),
        "wr": wr * 100,
        "net": float(s.sum()),
        "gp": gp,
        "gl": gl,
        "pf": (gp / gl) if gl > 0 else (float("inf") if gp > 0 else 0.0),
        "avg_w": avg_w,
        "avg_l": avg_l,
        "payoff": payoff,
        "expectancy": expectancy,
        "avg": float(s.mean()),
        "median": float(s.median()),
    }


def print_m(label: str, m: dict) -> None:
    pf = m["pf"]
    pf_s = f"{pf:.3f}" if pf != float("inf") else "∞"
    print(f"\n--- {label} ---")
    print(
        f"Trades/Closes: {m['n']} | W/L: {m['wins']}/{m['losses']} | "
        f"Win Rate: {m['wr']:.2f}%"
    )
    print(
        f"Net PnL: ${m['net']:.2f} | Gross +${m['gp']:.2f} / -${m['gl']:.2f} | "
        f"Profit Factor: {pf_s}"
    )
    print(
        f"Avg Win: ${m['avg_w']:.2f} | Avg Loss: ${m['avg_l']:.2f} | "
        f"Payoff: {m['payoff']:.2f}x | Expectancy: ${m['expectancy']:.2f}/trade"
    )
    print(f"Mean: ${m['avg']:.2f} | Median: ${m['median']:.2f}")


def equity_drawdown(pnl_series: pd.Series) -> dict:
    """Jesse/Freqtrade-style equity curve max drawdown from realized close PnL."""
    eq = pnl_series.cumsum()
    peak = eq.cummax()
    dd = eq - peak
    max_dd = float(dd.min()) if len(dd) else 0.0
    end_eq = float(eq.iloc[-1]) if len(eq) else 0.0
    return {
        "final_equity": end_eq,
        "max_dd": max_dd,
        "peak": float(peak.max()) if len(peak) else 0.0,
        "trough_after_peak": float(eq.min()) if len(eq) else 0.0,
    }


def streak_stats(pnl: pd.Series) -> dict:
    signs = (pnl > 0).astype(int)
    max_w = max_l = cur_w = cur_l = 0
    for v in signs:
        if v == 1:
            cur_w += 1
            cur_l = 0
            max_w = max(max_w, cur_w)
        else:
            cur_l += 1
            cur_w = 0
            max_l = max(max_l, cur_l)
    return {"max_win_streak": max_w, "max_loss_streak": max_l}


def main() -> int:
    if not CSV_PATH.exists():
        print(f"ERROR: missing {CSV_PATH}", file=sys.stderr)
        return 1

    df = load_fills(CSV_PATH)
    closes = df[df["is_close"]].copy()
    opens = df[df["is_open"]].copy()
    tdf = pair_trades(df)

    print("=" * 62)
    print("  SHAMROCK HL PERPS — TRADE HISTORY CSV 40 AUDIT")
    print("  Framework: Freqtrade · Jesse · Hummingbot · OpenAlice")
    print("=" * 62)
    print(f"File: {CSV_PATH}")
    print(f"Date Range: {df['dt'].min()} → {df['dt'].max()}")
    print(
        f"Total Fills: {len(df)} "
        f"({len(opens)} Opens, {len(closes)} Closes)"
    )
    print(f"Unique Coins: {df['coin'].nunique()}")
    print(f"Total Fees Paid: ${df['fee'].sum():.2f}")
    print(f"Net Realized PnL (sum of close closedPnl): ${closes['closedPnl'].sum():.2f}")
    print(f"Paired Trades (FIFO): {len(tdf)}")

    # ── Overall (Freqtrade core stats) ──────────────────────────────────────
    m_all = metrics_block(closes, "closedPnl")
    print_m("OVERALL CLOSE STATISTICS (Freqtrade-style)", m_all)

    eq = equity_drawdown(closes.sort_values("dt")["closedPnl"])
    st = streak_stats(closes.sort_values("dt")["closedPnl"])
    print(
        f"Equity curve (realized closes): final ${eq['final_equity']:.2f} | "
        f"peak ${eq['peak']:.2f} | max DD ${eq['max_dd']:.2f}"
    )
    print(
        f"Streaks: max win streak {st['max_win_streak']} | "
        f"max loss streak {st['max_loss_streak']}"
    )

    # Fee drag (Hummingbot)
    total_fees = float(df["fee"].sum())
    gross_before_fees_approx = float(closes["closedPnl"].sum()) + total_fees
    print(
        f"Fee drag: ${total_fees:.2f} total fees "
        f"(~{100 * total_fees / max(1, abs(closes['closedPnl'].sum())):.1f}% of |net PnL|)"
    )
    print(
        f"Rough PnL if fees=0 (approx): ${gross_before_fees_approx:.2f} "
        f"(adds back all fill fees; HL closedPnl already net of close fee on closes)"
    )

    # ── Direction (Jesse) ───────────────────────────────────────────────────
    print("\n--- LONG vs SHORT (Jesse split) ---")
    for side in ["Long", "Short"]:
        sub = closes[closes["side"] == side]
        m = metrics_block(sub, "closedPnl")
        print(
            f"{side:5s}: n={m['n']:3d} WR={m['wr']:5.1f}% "
            f"Net=${m['net']:8.2f} PF={m['pf']:.3f} Exp=${m['expectancy']:.2f}"
        )

    # ── By coin ─────────────────────────────────────────────────────────────
    coin_summary = (
        closes.groupby("coin")
        .agg(
            count=("closedPnl", "count"),
            net_pnl=("closedPnl", "sum"),
            wins=("closedPnl", lambda s: int((s > 0).sum())),
            losses=("closedPnl", lambda s: int((s <= 0).sum())),
            avg_pnl=("closedPnl", "mean"),
            fees=("fee", "sum"),
            notional=("ntl", "sum"),
        )
        .reset_index()
    )
    coin_summary["win_rate"] = coin_summary["wins"] / coin_summary["count"] * 100
    coin_summary = coin_summary.sort_values("net_pnl", ascending=False)

    print("\n--- TOP 12 WINNING COINS ---")
    print(
        coin_summary.head(12)[
            ["coin", "count", "wins", "losses", "win_rate", "net_pnl", "avg_pnl"]
        ].to_string(index=False, float_format=lambda x: f"{x:.2f}")
    )
    print("\n--- BOTTOM 12 LOSING COINS ---")
    print(
        coin_summary.tail(12)[
            ["coin", "count", "wins", "losses", "win_rate", "net_pnl", "avg_pnl"]
        ].to_string(index=False, float_format=lambda x: f"{x:.2f}")
    )

    # Concentration: how much loss from top N losers
    losers = coin_summary[coin_summary["net_pnl"] < 0].sort_values("net_pnl")
    top5_loss = losers.head(5)["net_pnl"].sum()
    print(
        f"\nLoss concentration: top-5 losing coins = ${top5_loss:.2f} "
        f"({100 * abs(top5_loss) / max(1e-9, abs(losers['net_pnl'].sum())):.1f}% of all coin losses)"
    )
    print("Top-5 bleeders:", ", ".join(f"{r.coin} ${r.net_pnl:.2f}" for r in losers.head(5).itertuples()))

    # ── Hold duration (OpenAlice / trade_analytics signal decay) ─────────────
    if len(tdf):
        tdf = tdf.copy()
        tdf["dur_bucket"] = tdf["duration_min"].apply(dur_bucket_simple)
        tdf["dur_detail"] = tdf["duration_min"].apply(
            lambda m: (
                "≤10s rapid"
                if m * 60 <= 10
                else ("10s–1m" if m <= 1 else dur_bucket_simple(m))
            )
        )
        dur_order = ["< 1m", "1m–5m", "5m–30m", "30m–1.5h", "1.5h–4h", ">4h"]
        detail_order = ["≤10s rapid", "10s–1m", "1m–5m", "5m–30m", "30m–1.5h", "1.5h–4h", ">4h"]

        print("\n--- PERFORMANCE BY HOLD DURATION (paired FIFO) ---")
        dur = (
            tdf.groupby("dur_bucket")
            .agg(
                count=("pnl", "count"),
                net_pnl=("pnl", "sum"),
                wins=("pnl", lambda s: int((s > 0).sum())),
                avg_pnl=("pnl", "mean"),
            )
            .reindex(dur_order)
            .reset_index()
        )
        dur["win_rate"] = dur["wins"] / dur["count"] * 100
        print(dur.to_string(index=False, float_format=lambda x: f"{x:.2f}"))

        print("\n--- RAPID-CLOSE FINGERPRINT (postmortem: ≤10s + <1m) ---")
        det = (
            tdf.groupby("dur_detail")
            .agg(
                count=("pnl", "count"),
                net_pnl=("pnl", "sum"),
                wins=("pnl", lambda s: int((s > 0).sum())),
                avg_pnl=("pnl", "mean"),
                avg_fee=("fee", "mean"),
            )
            .reindex(detail_order)
            .dropna(how="all")
            .reset_index()
        )
        det["win_rate"] = det["wins"] / det["count"] * 100
        print(det.to_string(index=False, float_format=lambda x: f"{x:.2f}"))

        rapid = tdf[tdf["duration_sec"] <= 10]
        sub1m = tdf[tdf["duration_min"] <= 1]
        print(
            f"\nRapid closes ≤10s: {len(rapid)} trades | Net ${rapid['pnl'].sum():.2f} | "
            f"Avg ${rapid['pnl'].mean():.2f} if any"
            if len(rapid)
            else "\nRapid closes ≤10s: 0"
        )
        if len(rapid):
            print(
                f"  Coins in ≤10s closes: "
                + ", ".join(
                    f"{c}({n})"
                    for c, n in rapid["coin"].value_counts().head(12).items()
                )
            )
        print(
            f"Sub-1m closes: {len(sub1m)} | Net ${sub1m['pnl'].sum():.2f} | "
            f"share of all paired: {100*len(sub1m)/len(tdf):.1f}%"
        )

        # Direction on paired
        print("\n--- PAIRED: LONG vs SHORT ---")
        for side in ["Long", "Short"]:
            sub = tdf[tdf["direction"] == side]
            m = metrics_block(sub, "pnl")
            print(
                f"{side:5s}: n={m['n']:3d} WR={m['wr']:5.1f}% "
                f"Net=${m['net']:8.2f} PF={m['pf']:.3f} med hold={sub['duration_min'].median():.1f}m"
            )

        # Loss size buckets (prior script)
        losses = tdf[tdf["pnl"] < 0]
        small = losses[losses["pnl"] >= -2.0]
        mid = losses[(losses["pnl"] < -2.0) & (losses["pnl"] >= -10.0)]
        huge = losses[losses["pnl"] < -10.0]
        print("\n--- LOSS SIZE BREAKDOWN (paired) ---")
        for name, g in [
            ("Small ($-0.01 to $-2)", small),
            ("Medium ($-2 to $-10)", mid),
            ("Huge (< $-10)", huge),
        ]:
            if len(g):
                print(
                    f"{name}: {len(g)} trades | Total ${g['pnl'].sum():.2f} | "
                    f"Avg ${g['pnl'].mean():.2f}"
                )
            else:
                print(f"{name}: 0")
        if len(huge):
            print("\n--- HUGE BLEEDERS (< $-10) ---")
            cols = [
                "coin",
                "direction",
                "open_time",
                "close_time",
                "duration_min",
                "open_ntl",
                "pnl",
            ]
            print(
                huge.sort_values("pnl")[cols].to_string(
                    index=False, float_format=lambda x: f"{x:.2f}"
                )
            )

        # Notional sizing (oversized position risk — postmortem GRASS/TRB)
        print("\n--- NOTIONAL SIZE BUCKETS (open notional) ---")
        tdf["ntl_bucket"] = pd.cut(
            tdf["open_ntl"],
            bins=[0, 50, 150, 300, 500, 1000, 1e9],
            labels=["<$50", "$50-150", "$150-300", "$300-500", "$500-1k", ">$1k"],
        )
        ntl_sum = (
            tdf.groupby("ntl_bucket", observed=False)
            .agg(
                count=("pnl", "count"),
                net_pnl=("pnl", "sum"),
                avg_pnl=("pnl", "mean"),
                wins=("pnl", lambda s: int((s > 0).sum())),
            )
            .reset_index()
        )
        ntl_sum["win_rate"] = ntl_sum["wins"] / ntl_sum["count"].replace(0, np.nan) * 100
        print(ntl_sum.to_string(index=False, float_format=lambda x: f"{x:.2f}"))
        big = tdf[tdf["open_ntl"] >= 500].sort_values("pnl")
        if len(big):
            print(f"\nPositions with open ntl ≥ $500: {len(big)} | Net ${big['pnl'].sum():.2f}")
            print(
                big[["coin", "open_time", "open_ntl", "duration_min", "pnl"]]
                .head(15)
                .to_string(index=False, float_format=lambda x: f"{x:.2f}")
            )

    # ── Hour of day (EST) ───────────────────────────────────────────────────
    closes = closes.copy()
    closes["hour_est"] = (closes["dt"] - pd.Timedelta(hours=4)).dt.hour  # UTC-4 approx
    hour = (
        closes.groupby("hour_est")
        .agg(
            count=("closedPnl", "count"),
            net_pnl=("closedPnl", "sum"),
            win_rate=("closedPnl", lambda s: (s > 0).mean() * 100),
        )
        .reset_index()
    )
    print("\n--- PERFORMANCE BY HOUR (EST approx UTC-4) ---")
    print(hour.to_string(index=False, float_format=lambda x: f"{x:.2f}"))
    best_h = hour.loc[hour["net_pnl"].idxmax()]
    worst_h = hour.loc[hour["net_pnl"].idxmin()]
    print(
        f"Best hour: {int(best_h['hour_est']):02d}:00 EST (${best_h['net_pnl']:.2f}) | "
        f"Worst: {int(worst_h['hour_est']):02d}:00 EST (${worst_h['net_pnl']:.2f})"
    )

    # ── Calendar periods ────────────────────────────────────────────────────
    print("\n" + "=" * 62)
    print("  PERIOD BREAKDOWNS (as of 2026-07-26 download)")
    print("=" * 62)

    periods = [
        ("All history", closes["dt"].min(), closes["dt"].max()),
        ("Since Jul 1", pd.Timestamp("2026-07-01"), AS_OF + pd.Timedelta(days=1)),
        ("Last 14d (Jul 12–26)", pd.Timestamp("2026-07-12"), AS_OF + pd.Timedelta(days=1)),
        ("Last 7d (Jul 19–26)", pd.Timestamp("2026-07-19"), AS_OF + pd.Timedelta(days=1)),
        ("Post-CSV39 window (Jul 24–26)", pd.Timestamp("2026-07-24 21:17"), AS_OF + pd.Timedelta(days=1)),
        ("Last 3d (Jul 23–26)", pd.Timestamp("2026-07-23"), AS_OF + pd.Timedelta(days=1)),
        ("Jul 25 only", pd.Timestamp("2026-07-25"), pd.Timestamp("2026-07-26")),
        ("Jul 26 (partial)", pd.Timestamp("2026-07-26"), AS_OF + pd.Timedelta(days=1)),
    ]
    for name, start, end in periods:
        sub = closes[(closes["dt"] >= start) & (closes["dt"] <= end)]
        m = metrics_block(sub, "closedPnl")
        print_m(name, m)

    # ── Daily PnL series (recent) ───────────────────────────────────────────
    closes["day"] = closes["dt"].dt.date
    daily = (
        closes.groupby("day")
        .agg(
            closes=("closedPnl", "count"),
            net_pnl=("closedPnl", "sum"),
            wins=("closedPnl", lambda s: int((s > 0).sum())),
            fees=("fee", "sum"),
        )
        .reset_index()
    )
    daily["wr"] = daily["wins"] / daily["closes"] * 100
    print("\n--- DAILY PnL (last 21 trading days with closes) ---")
    print(daily.tail(21).to_string(index=False, float_format=lambda x: f"{x:.2f}"))
    green = (daily["net_pnl"] > 0).sum()
    red = (daily["net_pnl"] <= 0).sum()
    print(f"Green days: {green} | Red days: {red} | Green rate: {100*green/len(daily):.1f}%")

    # ── What's new since CSV 39 (approx by mtime window) ────────────────────
    new = closes[closes["dt"] >= "2026-07-24 21:17"]
    if len(new):
        print("\n" + "=" * 62)
        print("  NEW FILLS SINCE CSV 39 (~Jul 24 21:17 → Jul 26)")
        print("=" * 62)
        print_m("New closes only", metrics_block(new, "closedPnl"))
        nc = (
            new.groupby("coin")
            .agg(count=("closedPnl", "count"), net_pnl=("closedPnl", "sum"))
            .sort_values("net_pnl")
        )
        print("\nBy coin (new window):")
        print(nc.to_string(float_format=lambda x: f"{x:.2f}"))
        if len(tdf):
            nt = tdf[tdf["close_time"] >= "2026-07-24 21:17"]
            if len(nt):
                print("\nNew paired hold durations:")
                nt = nt.copy()
                nt["b"] = nt["duration_min"].apply(dur_bucket_simple)
                print(
                    nt.groupby("b")
                    .agg(n=("pnl", "count"), net=("pnl", "sum"), avg=("pnl", "mean"))
                    .reindex(dur_order)
                    .dropna(how="all")
                    .to_string(float_format=lambda x: f"{x:.2f}")
                )
                print("\nSample new trades (worst 10):")
                print(
                    nt.nsmallest(10, "pnl")[
                        ["coin", "direction", "open_time", "close_time", "duration_min", "pnl", "open_ntl"]
                    ].to_string(index=False, float_format=lambda x: f"{x:.2f}")
                )
                print("\nSample new trades (best 10):")
                print(
                    nt.nlargest(10, "pnl")[
                        ["coin", "direction", "open_time", "close_time", "duration_min", "pnl", "open_ntl"]
                    ].to_string(index=False, float_format=lambda x: f"{x:.2f}")
                )

    # ── Actionable synthesis (OpenAlice self-improve style) ──────────────────
    print("\n" + "=" * 62)
    print("  ACTIONABLE INSIGHTS (OpenAlice / self-improving style)")
    print("=" * 62)

    insights = []
    if m_all["pf"] < 1.0:
        insights.append(
            f"1. EDGE NEGATIVE: Profit factor {m_all['pf']:.3f} < 1.0 — "
            f"expectancy ${m_all['expectancy']:.2f}/close. System is fee+loss bleeding overall."
        )
    if len(tdf):
        sub1 = tdf[tdf["duration_min"] <= 1]
        long_hold = tdf[tdf["duration_min"] > 30]
        if len(sub1) and sub1["pnl"].sum() < 0:
            insights.append(
                f"2. RAPID EXITS HURT: {len(sub1)} sub-1m trades net ${sub1['pnl'].sum():.2f} "
                f"(avg ${sub1['pnl'].mean():.2f}) — still echoes rapid-close / guard / fee-churn mode."
            )
        if len(long_hold) and long_hold["pnl"].sum() > sub1["pnl"].sum():
            insights.append(
                f"3. HOLD TIME EDGE: trades >30m net ${long_hold['pnl'].sum():.2f} "
                f"(n={len(long_hold)}, WR={100*(long_hold['pnl']>0).mean():.1f}%) vs sub-1m "
                f"${sub1['pnl'].sum():.2f}. Prefer fewer, longer holds if signal quality allows."
            )
        short_m = metrics_block(tdf[tdf["direction"] == "Short"], "pnl")
        long_m = metrics_block(tdf[tdf["direction"] == "Long"], "pnl")
        if short_m["n"] >= 5:
            insights.append(
                f"4. DIRECTION: Long n={long_m['n']} net ${long_m['net']:.2f} PF={long_m['pf']:.2f}; "
                f"Short n={short_m['n']} net ${short_m['net']:.2f} PF={short_m['pf']:.2f}."
            )
        if len(huge):
            insights.append(
                f"5. TAIL RISK: {len(huge)} trades < -$10 account for ${huge['pnl'].sum():.2f}. "
                f"Cap notional / tighten SL on: {', '.join(huge.sort_values('pnl')['coin'].unique()[:8])}."
            )
        if len(big) and big["pnl"].sum() < 0:
            insights.append(
                f"6. SIZE: open ntl≥$500 trades net ${big['pnl'].sum():.2f} — "
                f"oversized entries still a failure mode (see GRASS postmortem)."
            )
    # Worst hours
    bad_hours = hour[hour["net_pnl"] < -20].sort_values("net_pnl")
    if len(bad_hours):
        insights.append(
            "7. TIME FILTER: avoid or reduce size in EST hours "
            + ", ".join(f"{int(r.hour_est):02d}:00 (${r.net_pnl:.0f})" for r in bad_hours.itertuples())
        )
    recent7 = metrics_block(closes[closes["dt"] >= "2026-07-19"], "closedPnl")
    insights.append(
        f"8. RECENT 7D: n={recent7['n']} WR={recent7['wr']:.1f}% net ${recent7['net']:.2f} "
        f"PF={recent7['pf']:.3f} exp=${recent7['expectancy']:.2f} — "
        + ("still underwater; do not scale size." if recent7["net"] < 0 else "improving; scale carefully.")
    )
    for line in insights:
        print(line)

    print("\n" + "=" * 62)
    print("  END CSV 40 AUDIT")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
