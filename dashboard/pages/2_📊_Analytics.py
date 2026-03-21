"""
Page 2 — 📊 Analytics

Scan frequency charts, chain heatmap, Fibonacci zone distribution,
and performance metrics over time.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from datetime import datetime, timezone

from styles import PREMIUM_CSS, PLOTLY_LAYOUT, ACCENT, CHAIN_COLORS, DANGER, WARNING, INFO
from state import get_scan_history, get_gem_history, get_trades

st.set_page_config(page_title="Analytics | Shamrock", page_icon="📊", layout="wide")
st.markdown(PREMIUM_CSS, unsafe_allow_html=True)

# ── Header ───────────────────────────────────────────────────────────────────
st.markdown(
    '<div style="display:flex;align-items:center;gap:12px;margin-bottom:1.5rem;">'
    '<span style="font-size:2rem;">📊</span>'
    '<div>'
    '<h1 style="margin:0;padding:0;font-size:1.5rem;font-weight:800;'
    'background:linear-gradient(135deg,#00D09C,#00E6AC);'
    '-webkit-background-clip:text;-webkit-text-fill-color:transparent;">ANALYTICS</h1>'
    '<span style="color:#8B949E;font-size:0.8rem;">Performance metrics and market intelligence</span>'
    '</div></div>',
    unsafe_allow_html=True,
)

history = get_scan_history()
gems = get_gem_history()
trades = get_trades()

if not history:
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

# ── Scan Frequency Over Time ────────────────────────────────────────────────
st.markdown("## 📈 Scan Frequency")

df_hist = pd.DataFrame(history)
df_hist["timestamp"] = pd.to_datetime(df_hist["timestamp"])

tab1, tab2 = st.tabs(["Candidates Over Time", "Cumulative Gems"])

with tab1:
    fig_freq = go.Figure()
    fig_freq.add_trace(go.Scatter(
        x=df_hist["timestamp"],
        y=df_hist["candidates_found"],
        mode="lines+markers",
        name="Candidates / Cycle",
        line=dict(color=ACCENT, width=2),
        marker=dict(size=4, color=ACCENT),
        fill="tozeroy",
        fillcolor="rgba(0, 208, 156, 0.06)",
        hovertemplate="<b>%{y} candidates</b><br>%{x|%b %d, %H:%M}<extra></extra>",
    ))

    # Rolling average
    if len(df_hist) > 10:
        df_hist["rolling_avg"] = df_hist["candidates_found"].rolling(window=10, min_periods=1).mean()
        fig_freq.add_trace(go.Scatter(
            x=df_hist["timestamp"],
            y=df_hist["rolling_avg"],
            mode="lines",
            name="10-cycle avg",
            line=dict(color="#FFB84D", width=2, dash="dot"),
            hovertemplate="<b>Avg: %{y:.1f}</b><br>%{x|%b %d, %H:%M}<extra></extra>",
        ))

    fig_freq.update_layout(**PLOTLY_LAYOUT, height=350)
    fig_freq.update_layout(
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    st.plotly_chart(fig_freq, use_container_width=True, config={"displayModeBar": False})

with tab2:
    # Cumulative gem count
    if gems:
        df_gems = pd.DataFrame(gems)
        df_gems["discovered_at"] = pd.to_datetime(df_gems["discovered_at"])
        df_gems = df_gems.sort_values("discovered_at")
        df_gems["cumulative"] = range(1, len(df_gems) + 1)

        fig_cum = go.Figure()
        fig_cum.add_trace(go.Scatter(
            x=df_gems["discovered_at"],
            y=df_gems["cumulative"],
            mode="lines",
            line=dict(color=ACCENT, width=2.5),
            fill="tozeroy",
            fillcolor="rgba(0, 208, 156, 0.08)",
            hovertemplate="<b>%{y:,} total gems</b><br>%{x|%b %d, %H:%M}<extra></extra>",
        ))

        fig_cum.update_layout(
            **PLOTLY_LAYOUT, height=350,
            yaxis_title="Total Gems Discovered",
        )
        st.plotly_chart(fig_cum, use_container_width=True, config={"displayModeBar": False})

# ── Chain & Score Analysis ───────────────────────────────────────────────────
st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)

analysis_col1, analysis_col2 = st.columns(2)

with analysis_col1:
    st.markdown("## 🔗 Gems by Chain")

    if gems:
        chain_data = {}
        for g in gems:
            chain = g.get("chain", "unknown")
            chain_data[chain] = chain_data.get(chain, 0) + 1

        fig_bar = go.Figure()
        chains_sorted = sorted(chain_data.items(), key=lambda x: x[1], reverse=True)

        fig_bar.add_trace(go.Bar(
            x=[c[0].capitalize() for c in chains_sorted],
            y=[c[1] for c in chains_sorted],
            marker=dict(
                color=[CHAIN_COLORS.get(c[0], "#8B949E") for c in chains_sorted],
                line=dict(color="#0A0E14", width=1),
            ),
            hovertemplate="<b>%{x}</b><br>%{y:,} gems<extra></extra>",
        ))

        fig_bar.update_layout(**PLOTLY_LAYOUT, height=300, showlegend=False)
        st.plotly_chart(fig_bar, use_container_width=True, config={"displayModeBar": False})

with analysis_col2:
    st.markdown("## 🎯 Score Heatmap")

    if gems:
        score_ranges = {"0-20": 0, "20-40": 0, "40-60": 0, "60-80": 0, "80-100": 0}
        for g in gems:
            s = g.get("gem_score", 0)
            if s < 20: score_ranges["0-20"] += 1
            elif s < 40: score_ranges["20-40"] += 1
            elif s < 60: score_ranges["40-60"] += 1
            elif s < 80: score_ranges["60-80"] += 1
            else: score_ranges["80-100"] += 1

        fig_scores = go.Figure()
        colors_gradient = ["#FF4757", "#FF6B7A", "#FFB84D", "#00D09C", "#00FFB8"]
        fig_scores.add_trace(go.Bar(
            x=list(score_ranges.keys()),
            y=list(score_ranges.values()),
            marker=dict(color=colors_gradient, line=dict(color="#0A0E14", width=1)),
            hovertemplate="<b>Score %{x}</b><br>%{y:,} gems<extra></extra>",
        ))

        fig_scores.update_layout(**PLOTLY_LAYOUT, height=300, showlegend=False)
        st.plotly_chart(fig_scores, use_container_width=True, config={"displayModeBar": False})

# ── Fibonacci Zone Distribution ──────────────────────────────────────────────
fib_zones = [g.get("signal", {}).get("fib_zone", "") for g in gems if g.get("signal")]
fib_zones = [z for z in fib_zones if z and z != "unknown"]

if fib_zones:
    st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)
    st.markdown("## 📐 Fibonacci Zone Distribution")

    zone_counts = {}
    for z in fib_zones:
        zone_counts[z] = zone_counts.get(z, 0) + 1

    zone_colors = {
        "golden_pocket": "#FFD700",
        "fib_618": "#00D09C",
        "fib_382": "#58A6FF",
        "fib_236": "#8247E5",
        "no_mans_land": "#484F58",
        "above_high": "#FF4757",
        "below_low": "#FF6B7A",
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
        **PLOTLY_LAYOUT, height=350,
        annotations=[dict(
            text="<b>Fib<br>Zones</b>",
            x=0.5, y=0.5, font_size=14,
            font=dict(color="#E6EDF3", family="Inter"),
            showarrow=False,
        )],
    )
    st.plotly_chart(fig_fib, use_container_width=True, config={"displayModeBar": False})

# ── Key Metrics Summary ─────────────────────────────────────────────────────
st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)
st.markdown("## 📋 Session Summary")

summary_col1, summary_col2, summary_col3, summary_col4 = st.columns(4)

with summary_col1:
    st.metric("Total Cycles", f"{len(history):,}")
with summary_col2:
    total_candidates = sum(h.get("candidates_found", 0) for h in history)
    st.metric("Total Candidates", f"{total_candidates:,}")
with summary_col3:
    st.metric("Unique Gems", f"{len(gems):,}")
with summary_col4:
    error_cycles = sum(1 for h in history if h.get("errors", 0) > 0)
    success_rate = ((len(history) - error_cycles) / max(len(history), 1)) * 100
    st.metric("Success Rate", f"{success_rate:.1f}%")
