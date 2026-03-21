"""
Page 1 — 🔍 Gem Scanner

Real-time gem candidate feed with full score breakdowns,
filtering, and DexScreener deep links.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import plotly.graph_objects as go
import pandas as pd

from styles import PREMIUM_CSS, PLOTLY_LAYOUT, ACCENT, CHAIN_COLORS
from state import get_latest_gems, get_gem_history

st.set_page_config(page_title="Gem Scanner | Shamrock", page_icon="🔍", layout="wide")
st.markdown(PREMIUM_CSS, unsafe_allow_html=True)

# ── Header ───────────────────────────────────────────────────────────────────
st.markdown(
    '<div style="display:flex;align-items:center;gap:12px;margin-bottom:1.5rem;">'
    '<span style="font-size:2rem;">🔍</span>'
    '<div>'
    '<h1 style="margin:0;padding:0;font-size:1.5rem;font-weight:800;'
    'background:linear-gradient(135deg,#00D09C,#00E6AC);'
    '-webkit-background-clip:text;-webkit-text-fill-color:transparent;">GEM SCANNER</h1>'
    '<span style="color:#8B949E;font-size:0.8rem;">Discover, score, and analyze token opportunities</span>'
    '</div></div>',
    unsafe_allow_html=True,
)

# ── Filters ──────────────────────────────────────────────────────────────────
filter_col1, filter_col2, filter_col3, filter_col4 = st.columns([1, 1, 1, 1])

with filter_col1:
    chain_filter = st.selectbox("Chain", ["All", "Ethereum", "Base", "Arbitrum", "Polygon", "BSC"])

with filter_col2:
    min_score = st.slider("Min Score", 0, 100, 50)

with filter_col3:
    boosted_only = st.toggle("Boosted Only", value=False)

with filter_col4:
    safe_only = st.toggle("Safe Only", value=False)

# ── Data ─────────────────────────────────────────────────────────────────────
gems = get_latest_gems()
history = get_gem_history()

# Apply filters
filtered = gems
if chain_filter != "All":
    filtered = [g for g in filtered if g.get("chain", "").lower() == chain_filter.lower()]
if min_score > 0:
    filtered = [g for g in filtered if g.get("gem_score", 0) >= min_score]
if boosted_only:
    filtered = [g for g in filtered if g.get("is_boosted", False)]
if safe_only:
    filtered = [g for g in filtered if g.get("is_safe", False)]

# Sort by score
filtered.sort(key=lambda x: x.get("gem_score", 0), reverse=True)

# ── Stats Row ────────────────────────────────────────────────────────────────
stat_col1, stat_col2, stat_col3, stat_col4 = st.columns(4)

with stat_col1:
    st.metric("Latest Batch", len(gems))
with stat_col2:
    st.metric("After Filters", len(filtered))
with stat_col3:
    boosted_count = len([g for g in gems if g.get("is_boosted")])
    st.metric("Boosted", f"🚀 {boosted_count}")
with stat_col4:
    avg_score = sum(g.get("gem_score", 0) for g in gems) / max(len(gems), 1)
    st.metric("Avg Score", f"{avg_score:.1f}")

st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)

# ── Gem Cards ────────────────────────────────────────────────────────────────
if filtered:
    for i, gem in enumerate(filtered[:30]):
        score = gem.get("gem_score", 0)
        score_color = "#00D09C" if score >= 75 else ("#FFB84D" if score >= 65 else "#FF4757")
        chain = gem.get("chain", "unknown")
        chain_color = CHAIN_COLORS.get(chain, "#8B949E")

        with st.expander(
            f"{'🚀 ' if gem.get('is_boosted') else ''}"
            f"**{gem.get('symbol', '???')}** — "
            f"Score: {score:.1f} — "
            f"{chain.capitalize()} — "
            f"{'✅ Safe' if gem.get('is_safe') else '⚠️ Unverified'}",
            expanded=(i == 0),
        ):
            detail_col1, detail_col2, detail_col3 = st.columns([1, 1, 1])

            with detail_col1:
                st.markdown("### Market Data")
                st.markdown(f"**Price:** ${gem.get('price_usd', 0):.8f}")
                st.markdown(f"**Market Cap:** ${gem.get('market_cap', 0):,.0f}")
                st.markdown(f"**Liquidity:** ${gem.get('liquidity_usd', 0):,.0f}")
                st.markdown(f"**Volume 24h:** ${gem.get('volume_24h', 0):,.0f}")
                st.markdown(f"**Volume 1h:** ${gem.get('volume_1h', 0):,.0f}")

            with detail_col2:
                st.markdown("### Token Info")
                st.markdown(f"**Name:** {gem.get('name', 'N/A')}")
                st.markdown(f"**Chain:** {chain.capitalize()}")
                age = gem.get("age_hours")
                st.markdown(f"**Age:** {f'{age:.1f} hours' if age else 'Unknown'}")
                st.markdown(f"**Δ 1h:** {gem.get('price_change_1h', 0):+.1f}%")
                if gem.get("dex_url"):
                    st.markdown(f"[🔗 DexScreener]({gem['dex_url']})")

            with detail_col3:
                # Radar chart of score components
                scores = gem.get("scores", {})
                if scores and any(v > 0 for v in scores.values()):
                    categories = list(scores.keys())
                    values = [scores.get(c, 0) for c in categories]

                    fig_radar = go.Figure()
                    fig_radar.add_trace(go.Scatterpolar(
                        r=values + [values[0]],
                        theta=[c.capitalize() for c in categories] + [categories[0].capitalize()],
                        fill="toself",
                        fillcolor="rgba(0, 208, 156, 0.12)",
                        line=dict(color=ACCENT, width=2),
                        marker=dict(size=4, color=ACCENT),
                    ))

                    fig_radar.update_layout(
                        polar=dict(
                            bgcolor="rgba(0,0,0,0)",
                            radialaxis=dict(
                                visible=True, range=[0, 100],
                                gridcolor="rgba(255,255,255,0.06)",
                                tickfont=dict(size=9, color="#484F58"),
                            ),
                            angularaxis=dict(
                                gridcolor="rgba(255,255,255,0.06)",
                                tickfont=dict(size=10, color="#8B949E"),
                            ),
                        ),
                        showlegend=False,
                        height=250,
                        margin=dict(l=40, r=40, t=20, b=20),
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                        font=dict(family="Inter, sans-serif", color="#E6EDF3"),
                    )
                    st.plotly_chart(fig_radar, use_container_width=True, config={"displayModeBar": False})
                else:
                    st.markdown("*No score breakdown available*")

            # Signal data if available
            signal = gem.get("signal")
            if signal:
                st.markdown("---")
                sig_col1, sig_col2, sig_col3, sig_col4, sig_col5 = st.columns(5)
                with sig_col1:
                    st.metric("Trend", f"{signal.get('trend', 0):.0f}")
                with sig_col2:
                    st.metric("Momentum", f"{signal.get('momentum', 0):.0f}")
                with sig_col3:
                    st.metric("Volume", f"{signal.get('volume', 0):.0f}")
                with sig_col4:
                    st.metric("Fib Score", f"{signal.get('fib_score', 0):.0f}")
                with sig_col5:
                    sig_str = signal.get("signal", "N/A")
                    sig_emoji = {"BUY": "🟢", "SELL": "🔴", "NEUTRAL": "🟡"}.get(sig_str, "⚪")
                    st.metric("Signal", f"{sig_emoji} {sig_str}")
else:
    st.markdown(
        '<div class="glass-card" style="text-align:center;padding:3rem;">'
        '<div style="font-size:2.5rem;margin-bottom:0.5rem;">🔍</div>'
        '<div style="color:#8B949E;font-size:1.1rem;">No gems match your filters</div>'
        '<div style="color:#484F58;font-size:0.85rem;margin-top:6px;">'
        'Try lowering the minimum score or removing filters</div>'
        '</div>',
        unsafe_allow_html=True,
    )

# ── Historical Score Distribution ────────────────────────────────────────────
if history:
    st.markdown("<div style='height:24px;'></div>", unsafe_allow_html=True)
    st.markdown("## 📊 Score Distribution (All Time)")

    scores = [g.get("gem_score", 0) for g in history if g.get("gem_score", 0) > 0]
    if scores:
        fig_hist = go.Figure()
        fig_hist.add_trace(go.Histogram(
            x=scores,
            nbinsx=30,
            marker_color=ACCENT,
            marker_line=dict(color="#0A0E14", width=1),
            opacity=0.85,
            hovertemplate="Score range: %{x}<br>Count: %{y}<extra></extra>",
        ))

        fig_hist.update_layout(
            **PLOTLY_LAYOUT,
            height=260,
            xaxis_title="Gem Score",
            yaxis_title="Count",
            bargap=0.05,
        )
        st.plotly_chart(fig_hist, use_container_width=True, config={"displayModeBar": False})
