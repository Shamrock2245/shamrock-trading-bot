"""
Page 2 — 📊 Analytics

Comprehensive trading analytics: P&L curves, win rate trends,
chain performance, strategy breakdown, hourly activity heatmap,
drawdown tracking, and session intelligence.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from collections import defaultdict

from styles import (
    PREMIUM_CSS, PLOTLY_LAYOUT, PLOTLY_LAYOUT_HLEGEND,
    ACCENT, CHAIN_COLORS, CHAIN_EMOJI, DANGER, WARNING, INFO,
)
from state import get_scan_history, get_gem_history, get_trades, get_positions, get_bot_status
from nav import render_nav

st.set_page_config(page_title="Analytics | Shamrock", page_icon="📊", layout="wide")
st.markdown(PREMIUM_CSS, unsafe_allow_html=True)
render_nav("Analytics")

# ── Header ───────────────────────────────────────────────────────────────────
st.markdown(
    '<div style="display:flex;align-items:center;gap:12px;margin-bottom:1.5rem;">'
    '<span style="font-size:2rem;">📊</span>'
    '<div>'
    '<h1 style="margin:0;padding:0;font-size:1.5rem;font-weight:800;'
    'background:linear-gradient(135deg,#00D09C,#00E6AC);'
    '-webkit-background-clip:text;-webkit-text-fill-color:transparent;">ANALYTICS</h1>'
    '<span style="color:#8B949E;font-size:0.8rem;">Performance · Strategy · Market intelligence</span>'
    '</div></div>',
    unsafe_allow_html=True,
)

history = get_scan_history()
gems = get_gem_history()
trades = get_trades()
positions = get_positions()
status = get_bot_status()

if not history and not trades:
    st.markdown(
        '<div class="glass-card" style="text-align:center;padding:4rem;">'
        '<div style="font-size:3rem;margin-bottom:1rem;">📊</div>'
        '<div style="color:#E6EDF3;font-size:1.2rem;font-weight:600;">Analytics Dashboard</div>'
        '<div style="color:#8B949E;font-size:0.9rem;margin-top:8px;">'
        'Data will populate as the bot completes scan cycles</div>'
        '</div>',
        unsafe_allow_html=True,
    )
    st.stop()

# ── Derived data ─────────────────────────────────────────────────────────────
sells = [t for t in trades if t.get("direction") == "sell"]
buys = [t for t in trades if t.get("direction") == "buy"]
open_pos = [p for p in positions if p.get("is_open", False)]

wins = [s for s in sells if (s.get("amount_out", 0) - s.get("amount_in", 0)) > 0]
losses = [s for s in sells if (s.get("amount_out", 0) - s.get("amount_in", 0)) <= 0]
win_rate = (len(wins) / max(len(sells), 1)) * 100

total_gains = sum((s.get("amount_out", 0) - s.get("amount_in", 0)) for s in wins)
total_losses_v = sum(abs(s.get("amount_out", 0) - s.get("amount_in", 0)) for s in losses)
profit_factor = total_gains / max(total_losses_v, 0.0001)
avg_win = total_gains / max(len(wins), 1)
avg_loss = total_losses_v / max(len(losses), 1)
expectancy = (win_rate / 100 * avg_win) - ((1 - win_rate / 100) * avg_loss)

# ── KPI Row ──────────────────────────────────────────────────────────────────
with st.container(horizontal=True):
    st.metric("Total Trades", f"{len(trades):,}", f"{len(buys)} buys · {len(sells)} sells", border=True)
    wr_delta = "System profitable" if win_rate >= 50 else "Needs work"
    st.metric("Win Rate", f"{win_rate:.1f}%", f"{len(wins)}W / {len(losses)}L", border=True)
    pf_delta = "Edge confirmed" if profit_factor >= 1.0 else "Negative edge"
    st.metric("Profit Factor", f"{profit_factor:.2f}×", pf_delta, border=True)
    st.metric("Avg Win", f"+{avg_win:.4f}", "ETH per winner", border=True)
    st.metric("Avg Loss", f"-{avg_loss:.4f}", "ETH per loser", border=True)
    exp_sign = "+" if expectancy >= 0 else ""
    st.metric("Expectancy", f"{exp_sign}{expectancy:.4f}", "ETH per trade", border=True)

st.markdown('<div style="height:12px;"></div>', unsafe_allow_html=True)

# ── Row 1: P&L Curve + Drawdown ─────────────────────────────────────────────
r1c1, r1c2 = st.columns([3, 2])

with r1c1:
    st.markdown("#### 📈 Cumulative P&L Curve")
    if sells:
        df_pnl = pd.DataFrame(sells)
        df_pnl["timestamp"] = pd.to_datetime(df_pnl["timestamp"], errors="coerce")
        df_pnl = df_pnl.dropna(subset=["timestamp"]).sort_values("timestamp")
        df_pnl["pnl"] = df_pnl.apply(
            lambda r: r.get("amount_out", 0) - r.get("amount_in", 0), axis=1
        )
        df_pnl["cum_pnl"] = df_pnl["pnl"].cumsum()
        df_pnl["hwm"] = df_pnl["cum_pnl"].cummax()
        df_pnl["drawdown"] = df_pnl["cum_pnl"] - df_pnl["hwm"]

        fig_pnl = go.Figure()
        fig_pnl.add_trace(go.Scatter(
            x=df_pnl["timestamp"], y=df_pnl["cum_pnl"],
            mode="lines", name="Cumulative P&L",
            line=dict(color=ACCENT, width=2.5),
            fill="tozeroy", fillcolor="rgba(0,208,156,0.08)",
            hovertemplate="<b>P&L: %{y:.4f} ETH</b><br>%{x|%b %d %H:%M}<extra></extra>",
        ))
        fig_pnl.add_hline(y=0, line_dash="dash", line_color="rgba(255,255,255,0.08)")
        fig_pnl.update_layout(**{**PLOTLY_LAYOUT, "showlegend": False}, height=300, yaxis_title="P&L (ETH)")
        st.plotly_chart(fig_pnl, use_container_width=True, config={"displayModeBar": False}, key="a_pnl")
    else:
        st.info("P&L curve appears after first sell trade.")

with r1c2:
    st.markdown("#### 📉 Drawdown from HWM")
    if sells and len(df_pnl) > 1:
        fig_dd = go.Figure()
        fig_dd.add_trace(go.Scatter(
            x=df_pnl["timestamp"], y=df_pnl["drawdown"],
            mode="lines", line=dict(color=DANGER, width=2),
            fill="tozeroy", fillcolor="rgba(255,71,87,0.08)",
            hovertemplate="<b>DD: %{y:.4f} ETH</b><br>%{x|%b %d %H:%M}<extra></extra>",
        ))
        max_dd = df_pnl["drawdown"].min()
        fig_dd.update_layout(**{**PLOTLY_LAYOUT, "showlegend": False}, height=300, yaxis_title="Drawdown (ETH)")
        st.plotly_chart(fig_dd, use_container_width=True, config={"displayModeBar": False}, key="a_dd")
        st.markdown(
            f'<div style="color:#FF4757;font-size:0.72rem;font-weight:700;text-align:center;">'
            f'Max Drawdown: {max_dd:.4f} ETH</div>',
            unsafe_allow_html=True,
        )
    else:
        st.info("Drawdown chart appears after sell trades.")

# ── Row 2: Chain Performance + Rolling Win Rate ─────────────────────────────
r2c1, r2c2 = st.columns(2)

with r2c1:
    st.markdown("#### 🔗 Performance by Chain")
    if sells:
        chain_perf = {}
        for t in sells:
            ch = t.get("chain", "unknown")
            pnl = t.get("amount_out", 0) - t.get("amount_in", 0)
            if ch not in chain_perf:
                chain_perf[ch] = {"pnl": 0, "wins": 0, "total": 0, "volume": 0}
            chain_perf[ch]["pnl"] += pnl
            chain_perf[ch]["total"] += 1
            chain_perf[ch]["volume"] += t.get("amount_in", 0)
            if pnl > 0:
                chain_perf[ch]["wins"] += 1

        _cp_html = ""
        for ch, cp in sorted(chain_perf.items(), key=lambda x: x[1]["pnl"], reverse=True):
            _ce = CHAIN_EMOJI.get(ch, "⬡")
            _cc = CHAIN_COLORS.get(ch, "#8B949E")
            _wr = (cp["wins"] / max(cp["total"], 1)) * 100
            _pc = "#00D09C" if cp["pnl"] >= 0 else "#FF4757"
            _ps = "+" if cp["pnl"] >= 0 else ""
            _cp_html += (
                f'<div style="display:flex;align-items:center;gap:10px;padding:10px 14px;'
                f'border-bottom:1px solid rgba(48,54,61,0.3);">'
                f'<span style="font-size:0.9rem;">{_ce}</span>'
                f'<div style="flex:1;min-width:0;">'
                f'<div style="color:#E6EDF3;font-size:0.82rem;font-weight:700;">{ch.capitalize()}</div>'
                f'<div style="color:#484F58;font-size:0.62rem;">{cp["total"]} trades · {_wr:.0f}% WR</div>'
                f'</div>'
                f'<div style="text-align:right;">'
                f'<div style="color:{_pc};font-size:0.88rem;font-weight:800;'
                f'font-family:\'JetBrains Mono\',monospace;">{_ps}{cp["pnl"]:.4f}</div>'
                f'<div style="color:#484F58;font-size:0.58rem;">ETH</div>'
                f'</div></div>'
            )
        st.markdown(
            f'<div class="glass-card" style="padding:0;overflow:hidden;">{_cp_html}</div>',
            unsafe_allow_html=True,
        )
    else:
        st.info("Chain performance appears after sell trades.")

with r2c2:
    st.markdown("#### 🎯 Rolling Win Rate (10-trade window)")
    if len(sells) >= 5:
        df_wr = pd.DataFrame(sells)
        df_wr["timestamp"] = pd.to_datetime(df_wr["timestamp"], errors="coerce")
        df_wr = df_wr.dropna(subset=["timestamp"]).sort_values("timestamp")
        df_wr["is_win"] = df_wr.apply(lambda r: 1 if (r.get("amount_out", 0) - r.get("amount_in", 0)) > 0 else 0, axis=1)
        window = min(10, len(df_wr))
        df_wr["rolling_wr"] = df_wr["is_win"].rolling(window=window, min_periods=1).mean() * 100

        fig_wr = go.Figure()
        fig_wr.add_trace(go.Scatter(
            x=df_wr["timestamp"], y=df_wr["rolling_wr"],
            mode="lines", line=dict(color="#58A6FF", width=2.5),
            fill="tozeroy", fillcolor="rgba(88,166,255,0.06)",
            hovertemplate="<b>WR: %{y:.0f}%</b><br>%{x|%b %d %H:%M}<extra></extra>",
        ))
        fig_wr.add_hline(y=50, line_dash="dash", line_color="rgba(255,184,77,0.3)")
        fig_wr.update_layout(**{**PLOTLY_LAYOUT, "showlegend": False}, height=300, yaxis_title="Win Rate %")
        st.plotly_chart(fig_wr, use_container_width=True, config={"displayModeBar": False}, key="a_wr")
    else:
        st.info("Rolling win rate appears after 5+ sell trades.")

# ── Row 3: Scan Frequency + Gem Discovery ────────────────────────────────────
st.markdown('<div style="height:8px;"></div>', unsafe_allow_html=True)
r3c1, r3c2 = st.columns(2)

with r3c1:
    st.markdown("#### 🔍 Scan Frequency")
    if history:
        df_hist = pd.DataFrame(history)
        df_hist["timestamp"] = pd.to_datetime(df_hist["timestamp"])
        fig_freq = go.Figure()
        fig_freq.add_trace(go.Scatter(
            x=df_hist["timestamp"], y=df_hist["candidates_found"],
            mode="lines+markers", name="Candidates",
            line=dict(color=ACCENT, width=2), marker=dict(size=3, color=ACCENT),
            fill="tozeroy", fillcolor="rgba(0,208,156,0.06)",
            hovertemplate="<b>%{y} candidates</b><br>%{x|%b %d, %H:%M}<extra></extra>",
        ))
        if len(df_hist) > 10:
            df_hist["rolling_avg"] = df_hist["candidates_found"].rolling(window=10, min_periods=1).mean()
            fig_freq.add_trace(go.Scatter(
                x=df_hist["timestamp"], y=df_hist["rolling_avg"],
                mode="lines", name="10-cycle avg",
                line=dict(color="#FFB84D", width=2, dash="dot"),
            ))
        fig_freq.update_layout(**PLOTLY_LAYOUT_HLEGEND, height=280)
        st.plotly_chart(fig_freq, use_container_width=True, config={"displayModeBar": False}, key="a_freq")

with r3c2:
    st.markdown("#### 💎 Cumulative Gems Discovered")
    if gems:
        df_gems = pd.DataFrame(gems)
        df_gems["discovered_at"] = pd.to_datetime(df_gems["discovered_at"])
        df_gems = df_gems.sort_values("discovered_at")
        df_gems["cumulative"] = range(1, len(df_gems) + 1)
        fig_cum = go.Figure()
        fig_cum.add_trace(go.Scatter(
            x=df_gems["discovered_at"], y=df_gems["cumulative"],
            mode="lines", line=dict(color=ACCENT, width=2.5),
            fill="tozeroy", fillcolor="rgba(0,208,156,0.08)",
            hovertemplate="<b>%{y:,} total gems</b><br>%{x|%b %d, %H:%M}<extra></extra>",
        ))
        fig_cum.update_layout(**{**PLOTLY_LAYOUT, "showlegend": False}, height=280, yaxis_title="Total Gems")
        st.plotly_chart(fig_cum, use_container_width=True, config={"displayModeBar": False}, key="a_cum")

# ── Row 4: Chain Distribution + Score Heatmap ────────────────────────────────
r4c1, r4c2 = st.columns(2)

with r4c1:
    st.markdown("#### 🔗 Gems by Chain")
    if gems:
        chain_data = {}
        for g in gems:
            chain = g.get("chain", "unknown")
            chain_data[chain] = chain_data.get(chain, 0) + 1
        chains_sorted = sorted(chain_data.items(), key=lambda x: x[1], reverse=True)
        fig_bar = go.Figure()
        fig_bar.add_trace(go.Bar(
            x=[c[0].capitalize() for c in chains_sorted],
            y=[c[1] for c in chains_sorted],
            marker=dict(
                color=[CHAIN_COLORS.get(c[0], "#8B949E") for c in chains_sorted],
                line=dict(color="#0A0E14", width=1),
            ),
            hovertemplate="<b>%{x}</b><br>%{y:,} gems<extra></extra>",
        ))
        fig_bar.update_layout(**{**PLOTLY_LAYOUT, "showlegend": False}, height=280)
        st.plotly_chart(fig_bar, use_container_width=True, config={"displayModeBar": False}, key="a_chain_bar")

with r4c2:
    st.markdown("#### 🎯 Score Distribution")
    if gems:
        score_ranges = {"0-20": 0, "20-40": 0, "40-60": 0, "60-80": 0, "80-100": 0}
        for g in gems:
            s = g.get("gem_score", 0)
            if s < 20: score_ranges["0-20"] += 1
            elif s < 40: score_ranges["20-40"] += 1
            elif s < 60: score_ranges["40-60"] += 1
            elif s < 80: score_ranges["60-80"] += 1
            else: score_ranges["80-100"] += 1
        colors_gradient = ["#FF4757", "#FF6B7A", "#FFB84D", "#00D09C", "#00FFB8"]
        fig_scores = go.Figure()
        fig_scores.add_trace(go.Bar(
            x=list(score_ranges.keys()), y=list(score_ranges.values()),
            marker=dict(color=colors_gradient, line=dict(color="#0A0E14", width=1)),
            hovertemplate="<b>Score %{x}</b><br>%{y:,} gems<extra></extra>",
        ))
        fig_scores.update_layout(**{**PLOTLY_LAYOUT, "showlegend": False}, height=280)
        st.plotly_chart(fig_scores, use_container_width=True, config={"displayModeBar": False}, key="a_scores")

# ── Row 5: Hourly Activity Heatmap ───────────────────────────────────────────
if trades and len(trades) >= 3:
    st.markdown("#### 🕐 Trading Activity by Hour")
    df_activity = pd.DataFrame(trades)
    df_activity["timestamp"] = pd.to_datetime(df_activity["timestamp"], errors="coerce")
    df_activity = df_activity.dropna(subset=["timestamp"])
    df_activity["hour"] = df_activity["timestamp"].dt.hour
    df_activity["day"] = df_activity["timestamp"].dt.day_name()

    heatmap_data = df_activity.groupby(["day", "hour"]).size().reset_index(name="count")
    day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    heatmap_pivot = heatmap_data.pivot_table(index="day", columns="hour", values="count", fill_value=0)
    heatmap_pivot = heatmap_pivot.reindex(day_order, fill_value=0)

    fig_heat = go.Figure(data=go.Heatmap(
        z=heatmap_pivot.values,
        x=[f"{h:02d}:00" for h in range(24)],
        y=heatmap_pivot.index,
        colorscale=[[0, "#0D1117"], [0.5, "#1a4731"], [1, "#00D09C"]],
        showscale=False,
        hovertemplate="<b>%{y} %{x}</b><br>%{z} trades<extra></extra>",
    ))
    fig_heat.update_layout(**{**PLOTLY_LAYOUT, "showlegend": False}, height=220)
    st.plotly_chart(fig_heat, use_container_width=True, config={"displayModeBar": False}, key="a_heat")

# ── Fibonacci Zone Distribution ──────────────────────────────────────────────
fib_zones = [g.get("signal", {}).get("fib_zone", "") for g in gems if g.get("signal")]
fib_zones = [z for z in fib_zones if z and z != "unknown"]

if fib_zones:
    st.markdown("#### 📐 Fibonacci Zone Distribution")
    zone_counts = {}
    for z in fib_zones:
        zone_counts[z] = zone_counts.get(z, 0) + 1
    zone_colors = {
        "golden_pocket": "#FFD700", "fib_618": "#00D09C", "fib_382": "#58A6FF",
        "fib_236": "#8247E5", "no_mans_land": "#484F58",
        "above_high": "#FF4757", "below_low": "#FF6B7A",
    }
    fig_fib = go.Figure(data=[go.Pie(
        labels=[z.replace("_", " ").title() for z in zone_counts.keys()],
        values=list(zone_counts.values()),
        hole=0.6,
        marker=dict(
            colors=[zone_colors.get(z, "#8B949E") for z in zone_counts.keys()],
            line=dict(color="#0A0E14", width=2),
        ),
        textinfo="label+percent",
        textfont=dict(size=11, color="#E6EDF3"),
    )])
    fig_fib.update_layout(
        **PLOTLY_LAYOUT, height=300,
        annotations=[dict(
            text="<b>Fib<br>Zones</b>", x=0.5, y=0.5, font_size=14,
            font=dict(color="#E6EDF3", family="Inter"), showarrow=False,
        )],
    )
    st.plotly_chart(fig_fib, use_container_width=True, config={"displayModeBar": False}, key="a_fib")

# ── Strategy Performance Table ────────────────────────────────────────────
if sells:
    st.markdown("#### 🧠 Strategy Performance")
    strat_data = defaultdict(lambda: {"wins": 0, "losses": 0, "pnl": 0.0, "count": 0, "hold_times": []})
    for t in sells:
        strat = t.get("strategy_tag", t.get("execution_path", "unknown"))
        if not strat or strat == "":
            strat = "unknown"
        pnl = float(t.get("pnl_usd", t.get("amount_out", 0) - t.get("amount_in", 0)))
        strat_data[strat]["count"] += 1
        strat_data[strat]["pnl"] += pnl
        if pnl > 0:
            strat_data[strat]["wins"] += 1
        else:
            strat_data[strat]["losses"] += 1
        # Hold time
        entry_ts = t.get("entry_time") or t.get("buy_timestamp")
        exit_ts = t.get("exit_time") or t.get("timestamp")
        if entry_ts and exit_ts:
            try:
                if isinstance(entry_ts, (int, float)):
                    et = datetime.fromtimestamp(entry_ts, tz=timezone.utc)
                else:
                    et = pd.to_datetime(entry_ts, utc=True)
                if isinstance(exit_ts, (int, float)):
                    xt = datetime.fromtimestamp(exit_ts, tz=timezone.utc)
                else:
                    xt = pd.to_datetime(exit_ts, utc=True)
                hold_min = (xt - et).total_seconds() / 60
                if 0 < hold_min < 10080:  # <7 days
                    strat_data[strat]["hold_times"].append(hold_min)
            except Exception:
                pass

    strat_sorted = sorted(strat_data.items(), key=lambda x: x[1]["pnl"], reverse=True)
    _strat_html = ""
    for sname, sd in strat_sorted:
        wr = (sd["wins"] / max(sd["count"], 1)) * 100
        _pc = ACCENT if sd["pnl"] >= 0 else DANGER
        _ps = "+" if sd["pnl"] >= 0 else ""
        _wr_color = ACCENT if wr >= 50 else (WARNING if wr >= 35 else DANGER)
        avg_hold = sum(sd["hold_times"]) / max(len(sd["hold_times"]), 1)
        hold_str = f"{avg_hold:.0f}m" if avg_hold < 60 else f"{avg_hold/60:.1f}h"
        _strat_html += (
            f'<div style="display:flex;align-items:center;padding:10px 14px;'
            f'border-bottom:1px solid rgba(48,54,61,0.3);gap:12px;">'
            f'<div style="flex:1;min-width:0;">'
            f'<div style="color:#E6EDF3;font-size:0.82rem;font-weight:700;">'
            f'{sname.replace("_"," ").title()}</div>'
            f'<div style="color:#484F58;font-size:0.62rem;">'
            f'{sd["count"]} trades · {sd["wins"]}W/{sd["losses"]}L · avg hold {hold_str}</div>'
            f'</div>'
            f'<div style="text-align:center;min-width:60px;">'
            f'<div style="color:{_wr_color};font-size:0.85rem;font-weight:800;'
            f'font-family:\'JetBrains Mono\',monospace;">{wr:.0f}%</div>'
            f'<div style="color:#30363D;font-size:0.52rem;">WIN RATE</div>'
            f'</div>'
            f'<div style="text-align:right;min-width:80px;">'
            f'<div style="color:{_pc};font-size:0.88rem;font-weight:800;'
            f'font-family:\'JetBrains Mono\',monospace;">{_ps}${abs(sd["pnl"]):.4f}</div>'
            f'<div style="color:#30363D;font-size:0.52rem;">P&L</div>'
            f'</div></div>'
        )
    st.markdown(
        f'<div class="glass-card" style="padding:0;overflow:hidden;">{_strat_html}</div>',
        unsafe_allow_html=True,
    )

st.markdown('<div style="height:8px;"></div>', unsafe_allow_html=True)

# ── Best / Worst Trades ─────────────────────────────────────────────────
if sells and len(sells) >= 3:
    st.markdown("#### 🏆 Best & Worst Trades")
    bw_c1, bw_c2 = st.columns(2)
    sells_sorted = sorted(sells, key=lambda t: float(t.get("pnl_usd", t.get("amount_out", 0) - t.get("amount_in", 0))), reverse=True)

    with bw_c1:
        _best_html = ""
        for t in sells_sorted[:5]:
            pnl = float(t.get("pnl_usd", t.get("amount_out", 0) - t.get("amount_in", 0)))
            sym = t.get("symbol", t.get("token_symbol", "???"))
            chain = t.get("chain", "?")
            ce = CHAIN_EMOJI.get(chain, "⬡")
            _best_html += (
                f'<div style="display:flex;align-items:center;padding:6px 12px;'
                f'border-bottom:1px solid rgba(48,54,61,0.3);gap:8px;">'
                f'<span style="font-size:0.72rem;">{ce}</span>'
                f'<span style="color:#E6EDF3;font-size:0.78rem;font-weight:600;flex:1;">{sym}</span>'
                f'<span style="color:{ACCENT};font-size:0.82rem;font-weight:800;'
                f'font-family:\'JetBrains Mono\',monospace;">+${pnl:.4f}</span>'
                f'</div>'
            )
        st.markdown(
            f'<div style="color:#00D09C;font-size:0.62rem;font-weight:700;text-transform:uppercase;'
            f'letter-spacing:0.1em;margin-bottom:6px;">🟢 Best Trades</div>'
            f'<div class="glass-card" style="padding:0;overflow:hidden;">{_best_html}</div>',
            unsafe_allow_html=True,
        )

    with bw_c2:
        _worst_html = ""
        for t in sells_sorted[-5:]:
            pnl = float(t.get("pnl_usd", t.get("amount_out", 0) - t.get("amount_in", 0)))
            sym = t.get("symbol", t.get("token_symbol", "???"))
            chain = t.get("chain", "?")
            ce = CHAIN_EMOJI.get(chain, "⬡")
            _worst_html += (
                f'<div style="display:flex;align-items:center;padding:6px 12px;'
                f'border-bottom:1px solid rgba(48,54,61,0.3);gap:8px;">'
                f'<span style="font-size:0.72rem;">{ce}</span>'
                f'<span style="color:#E6EDF3;font-size:0.78rem;font-weight:600;flex:1;">{sym}</span>'
                f'<span style="color:{DANGER};font-size:0.82rem;font-weight:800;'
                f'font-family:\'JetBrains Mono\',monospace;">${pnl:.4f}</span>'
                f'</div>'
            )
        st.markdown(
            f'<div style="color:#FF4757;font-size:0.62rem;font-weight:700;text-transform:uppercase;'
            f'letter-spacing:0.1em;margin-bottom:6px;">🔴 Worst Trades</div>'
            f'<div class="glass-card" style="padding:0;overflow:hidden;">{_worst_html}</div>',
            unsafe_allow_html=True,
        )

# ── Session Summary ──────────────────────────────────────────────────────────
st.markdown('<div style="height:8px;"></div>', unsafe_allow_html=True)
st.markdown("#### 📋 Session Summary")
with st.container(horizontal=True):
    st.metric("Total Cycles", f"{len(history):,}", border=True)
    total_candidates = sum(h.get("candidates_found", 0) for h in history)
    st.metric("Total Candidates", f"{total_candidates:,}", border=True)
    st.metric("Unique Gems", f"{len(gems):,}", border=True)
    error_cycles = sum(1 for h in history if h.get("errors", 0) > 0)
    success_rate = ((len(history) - error_cycles) / max(len(history), 1)) * 100
    st.metric("Success Rate", f"{success_rate:.1f}%", border=True)
    st.metric("Open Positions", str(len(open_pos)), border=True)
