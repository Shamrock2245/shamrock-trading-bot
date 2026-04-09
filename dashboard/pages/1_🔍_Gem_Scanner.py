"""
Page 1 — 🔍 Gem Scanner (GemSeeker v4.0)

Live gem candidate feed with:
  - Force Scan (GemSeeker) button
  - De-duplicated token cards (one per address, highest score wins)
  - Full Moralis intelligence display per gem
  - Timing signal badges
  - Score radar chart
  - DexScreener deep links
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime, timezone

from styles import PREMIUM_CSS, PLOTLY_LAYOUT, ACCENT, CHAIN_COLORS, CHAIN_EMOJI, DANGER, WARNING
from state import (
    get_latest_gems,
    get_gem_history,
    request_force_scan,
    get_force_scan_request,
    request_manual_buy,
    get_pending_manual_commands,
)

st.set_page_config(page_title="Gem Scanner | Shamrock", page_icon="🔍", layout="wide")
st.markdown(PREMIUM_CSS, unsafe_allow_html=True)

# ── GemSeeker-specific CSS ────────────────────────────────────────────────────
st.markdown("""
<style>
.gemseeker-btn-wrap { margin-bottom: 20px; }
.intel-row { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 8px; }
.intel-pill {
    display: inline-flex; align-items: center; gap: 4px;
    padding: 3px 9px; border-radius: 20px;
    font-size: 0.67rem; font-weight: 700; letter-spacing: 0.03em;
}
.pill-green  { background: rgba(0,208,156,0.12);  color: #00D09C; border: 1px solid rgba(0,208,156,0.2); }
.pill-red    { background: rgba(255,71,87,0.12);   color: #FF4757; border: 1px solid rgba(255,71,87,0.2); }
.pill-yellow { background: rgba(255,184,77,0.12);  color: #FFB84D; border: 1px solid rgba(255,184,77,0.2); }
.pill-blue   { background: rgba(88,166,255,0.12);  color: #58A6FF; border: 1px solid rgba(88,166,255,0.2); }
.pill-purple { background: rgba(188,140,255,0.12); color: #BC8CFF; border: 1px solid rgba(188,140,255,0.2); }
.pill-gray   { background: rgba(139,148,158,0.10); color: #8B949E; border: 1px solid rgba(139,148,158,0.15); }
.score-bar-wrap { margin: 6px 0; }
.score-bar-label { display: flex; justify-content: space-between; margin-bottom: 2px; }
.score-bar-label span { font-size: 0.65rem; color: #484F58; }
.score-bar-label strong { font-size: 0.65rem; color: #8B949E; }
.score-bar-track { height: 5px; background: rgba(48,54,61,0.5); border-radius: 3px; }
.score-bar-fill { height: 100%; border-radius: 3px; }
.gem-header-row {
    display: flex; align-items: center; gap: 10px;
    padding: 10px 0 6px;
}
.gem-score-badge {
    display: inline-flex; align-items: center; justify-content: center;
    width: 48px; height: 48px; border-radius: 12px;
    font-size: 1rem; font-weight: 800;
    font-family: 'JetBrains Mono', monospace;
    flex-shrink: 0;
}
.gem-score-high  { background: rgba(0,208,156,0.15);  color: #00D09C; border: 1px solid rgba(0,208,156,0.3); }
.gem-score-mid   { background: rgba(255,184,77,0.15);  color: #FFB84D; border: 1px solid rgba(255,184,77,0.3); }
.gem-score-low   { background: rgba(255,71,87,0.15);   color: #FF4757; border: 1px solid rgba(255,71,87,0.3); }
</style>
""", unsafe_allow_html=True)

# ── Header ────────────────────────────────────────────────────────────────────
hdr_c1, hdr_c2 = st.columns([3, 1])
with hdr_c1:
    st.markdown(
        '<div class="page-header" style="margin-bottom:0;">'
        '<div style="display:flex;align-items:center;gap:10px;">'
        '<span style="font-size:1.6rem;">🔍</span>'
        '<div>'
        '<h1>GEM SCANNER</h1>'
        '<div class="subtitle">Discover · Score · Analyze · Execute</div>'
        '</div>'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )

with hdr_c2:
    st.markdown('<div style="height:12px;"></div>', unsafe_allow_html=True)
    pending = get_force_scan_request()
    if pending:
        st.markdown(
            '<div style="background:rgba(255,184,77,0.10);border:1px solid rgba(255,184,77,0.3);'
            'border-radius:10px;padding:10px 14px;text-align:center;">'
            '<div style="color:#FFB84D;font-size:0.8rem;font-weight:700;">⏳ Scan Queued</div>'
            '<div style="color:#484F58;font-size:0.68rem;margin-top:2px;">Bot picks up next cycle</div>'
            '</div>',
            unsafe_allow_html=True,
        )
    else:
        if st.button(
            "🔍  GemSeeker — Force Scan",
            key="gs_force_scan",
            use_container_width=True,
            type="primary",
            help="Trigger an immediate full gem scan across all 6 chains and 9 discovery sources",
        ):
            request_force_scan(reason="gemseeker_button")
            st.success("✅ GemSeeker scan launched! Results appear in the next cycle.")
            st.rerun()

st.markdown('<div style="height:16px;"></div>', unsafe_allow_html=True)

# ── Filters ───────────────────────────────────────────────────────────────────
fc1, fc2, fc3, fc4, fc5 = st.columns([1.2, 1, 0.8, 0.8, 0.8])
with fc1:
    chain_filter = st.selectbox("Chain", ["All", "Ethereum", "Base", "Arbitrum", "Polygon", "BSC", "Solana"])
with fc2:
    min_score = st.slider("Min Score", 0, 100, 60)
with fc3:
    boosted_only = st.toggle("Boosted Only", value=False)
with fc4:
    safe_only = st.toggle("Safe Only", value=False)
with fc5:
    express_only = st.toggle("Express Only", value=False)

# ── Data + De-duplication ─────────────────────────────────────────────────────
raw_gems = get_latest_gems()
history = get_gem_history()

# De-duplicate: one entry per token address, keep highest gem_score
seen_addr: dict = {}
for g in raw_gems:
    addr = (g.get("address") or g.get("symbol", "")).lower().strip()
    if not addr:
        continue
    if addr not in seen_addr or g.get("gem_score", 0) > seen_addr[addr].get("gem_score", 0):
        seen_addr[addr] = g
gems = list(seen_addr.values())

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
if express_only:
    filtered = [g for g in filtered if g.get("express_lane", False)]

filtered.sort(key=lambda x: x.get("gem_score", 0), reverse=True)

# ── Stats Row ─────────────────────────────────────────────────────────────────
st1, st2, st3, st4, st5 = st.columns(5)
with st1:
    st.metric("Raw Candidates", len(raw_gems))
with st2:
    st.metric("De-duplicated", len(gems))
with st3:
    st.metric("After Filters", len(filtered))
with st4:
    boosted_c = len([g for g in gems if g.get("is_boosted")])
    st.metric("Boosted", f"🚀 {boosted_c}")
with st5:
    avg_score = sum(g.get("gem_score", 0) for g in gems) / max(len(gems), 1)
    st.metric("Avg Score", f"{avg_score:.1f}")

st.markdown('<div style="height:12px;"></div>', unsafe_allow_html=True)

# ── Gem Cards ─────────────────────────────────────────────────────────────────
if filtered:
    for i, gem in enumerate(filtered[:30]):
        score = gem.get("gem_score", 0)
        chain = gem.get("chain", "unknown")
        chain_color = CHAIN_COLORS.get(chain, "#8B949E")
        chain_emoji = CHAIN_EMOJI.get(chain, "⬡")
        score_cls = "gem-score-high" if score >= 75 else ("gem-score-mid" if score >= 65 else "gem-score-low")

        # Build expander label
        express_tag = "⚡ " if gem.get("express_lane") else ""
        boosted_tag = "🚀 " if gem.get("is_boosted") else ""
        cto_tag = "🔄 CTO " if gem.get("is_cto") else ""
        safe_tag = "✅" if gem.get("is_safe") else "⚠️"
        timing = gem.get("timing_bp_trend", "flat")
        t_icon = {"accelerating": "🚀", "decelerating": "📉", "flat": "➡️"}.get(timing, "➡️")

        expander_label = (
            f"{express_tag}{boosted_tag}{cto_tag}"
            f"{gem.get('symbol', '???')}  ·  "
            f"Score {score:.1f}  ·  "
            f"{chain_emoji} {chain.capitalize()}  ·  "
            f"{t_icon} {timing.capitalize()}  ·  "
            f"{safe_tag}"
        )

        with st.expander(expander_label, expanded=(i == 0)):
            d1, d2, d3 = st.columns([1, 1, 1])

            # ── Column 1: Market Data ─────────────────────────────────────────
            with d1:
                st.markdown("##### 📊 Market Data")
                price = gem.get("price_usd", 0)
                price_str = f"${price:.8f}" if price < 0.001 else (f"${price:.4f}" if price < 1 else f"${price:,.2f}")
                st.markdown(f"**Price:** {price_str}")
                st.markdown(f"**Market Cap:** ${gem.get('market_cap', 0):,.0f}")
                st.markdown(f"**Liquidity:** ${gem.get('liquidity_usd', 0):,.0f}")
                st.markdown(f"**Volume 24h:** ${gem.get('volume_24h', 0):,.0f}")
                st.markdown(f"**Volume 1h:** ${gem.get('volume_1h', 0):,.0f}")
                st.markdown(f"**Buy/Sell Ratio:** {gem.get('buy_sell_ratio', 0):.2f}")
                st.markdown(f"**Δ 1h:** {gem.get('price_change_1h', 0):+.1f}%")
                st.markdown(f"**Δ 24h:** {gem.get('price_change_24h', 0):+.1f}%")

                age = gem.get("age_hours")
                age_str = f"{age:.1f}h" if age else "Unknown"
                st.markdown(f"**Age:** {age_str}")

                if gem.get("dex_url"):
                    st.markdown(f"[🔗 View on DexScreener]({gem['dex_url']})")

            # ── Column 2: Intelligence Signals ───────────────────────────────
            with d2:
                st.markdown("##### 🧠 Intelligence Signals")

                # Timing
                timing_color = ACCENT if timing == "accelerating" else (DANGER if timing == "decelerating" else "#8B949E")
                timing_label = {"accelerating": "ACCELERATING ▲", "decelerating": "DECELERATING ▼", "flat": "FLAT →"}.get(timing, timing.upper())
                st.markdown(
                    f'<div style="margin-bottom:10px;">'
                    f'<div style="color:#484F58;font-size:0.65rem;font-weight:700;'
                    f'text-transform:uppercase;letter-spacing:0.08em;margin-bottom:4px;">Entry Timing</div>'
                    f'<div style="color:{timing_color};font-size:0.85rem;font-weight:700;">'
                    f'{t_icon} {timing_label}</div>'
                    f'<div style="color:#484F58;font-size:0.68rem;">'
                    f'Timing Score: {gem.get("timing_score", 0):.0f}/100</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

                # Intelligence pills
                pills_html = '<div class="intel-row">'
                intel_map = [
                    ("intel_smart_money_buying", "🧠 Smart Money", "pill-green"),
                    ("intel_whale_buying", "🐋 Whale Buying", "pill-blue"),
                    ("intel_top_trader_active", "🏆 Top Traders", "pill-purple"),
                    ("intel_snipers_detected", "🎯 Snipers", "pill-red"),
                    ("intel_holder_growth", "📈 Holder Growth", "pill-green"),
                    ("intel_score_improving", "⬆️ Score Rising", "pill-green"),
                    ("intel_volume_accelerating", "⚡ Vol Accel", "pill-yellow"),
                    ("is_boosted", "🚀 Boosted", "pill-yellow"),
                    ("is_cto", "🔄 CTO", "pill-purple"),
                    ("express_lane", "⚡ Express", "pill-green"),
                ]
                has_pills = False
                for key, label, cls in intel_map:
                    if gem.get(key):
                        pills_html += f'<span class="intel-pill {cls}">{label}</span>'
                        has_pills = True
                if not has_pills:
                    pills_html += '<span class="intel-pill pill-gray">No signals</span>'
                pills_html += '</div>'
                st.markdown(pills_html, unsafe_allow_html=True)

                st.markdown('<div style="height:8px;"></div>', unsafe_allow_html=True)

                # Score bars
                st.markdown("**Score Breakdown**")
                score_cats = [
                    ("Volume", gem.get("volume_score", 0)),
                    ("Whale/Holder", gem.get("holder_score", 0)),
                    ("Liquidity", gem.get("liquidity_score", 0)),
                    ("Safety", gem.get("contract_score", 0)),
                    ("TA/Momentum", gem.get("smart_money_score", 0)),
                    ("Boost/CTO", gem.get("boost_score", 0)),
                    ("Fibonacci", gem.get("tvl_score", 0)),
                    ("Sentiment", gem.get("social_sentiment_score", 0)),
                    ("Age", gem.get("age_score", 0)),
                    ("Social", gem.get("social_score", 0)),
                ]
                bars_html = ""
                for cat_name, cat_val in score_cats:
                    if cat_val > 0:
                        bar_color = ACCENT if cat_val >= 70 else (WARNING if cat_val >= 40 else DANGER)
                        bars_html += (
                            f'<div class="score-bar-wrap">'
                            f'<div class="score-bar-label">'
                            f'<span>{cat_name}</span><strong>{cat_val:.0f}</strong>'
                            f'</div>'
                            f'<div class="score-bar-track">'
                            f'<div class="score-bar-fill" style="width:{min(cat_val,100):.0f}%;'
                            f'background:{bar_color};"></div>'
                            f'</div>'
                            f'</div>'
                        )
                if bars_html:
                    st.markdown(bars_html, unsafe_allow_html=True)

            # ── Column 3: Radar Chart + Holder Stats ──────────────────────────
            with d3:
                st.markdown("##### 🎯 Score Radar")
                scores_dict = gem.get("scores", {})
                if scores_dict and any(v > 0 for v in scores_dict.values()):
                    cats = list(scores_dict.keys())
                    vals = [scores_dict.get(c, 0) for c in cats]
                    fig_r = go.Figure()
                    fig_r.add_trace(go.Scatterpolar(
                        r=vals + [vals[0]],
                        theta=[c.capitalize() for c in cats] + [cats[0].capitalize()],
                        fill="toself",
                        fillcolor="rgba(0,208,156,0.10)",
                        line=dict(color=ACCENT, width=2),
                        marker=dict(size=4, color=ACCENT),
                    ))
                    fig_r.update_layout(
                        polar=dict(
                            bgcolor="rgba(0,0,0,0)",
                            radialaxis=dict(
                                visible=True, range=[0, 100],
                                gridcolor="rgba(255,255,255,0.05)",
                                tickfont=dict(size=8, color="#30363D"),
                            ),
                            angularaxis=dict(
                                gridcolor="rgba(255,255,255,0.05)",
                                tickfont=dict(size=9, color="#8B949E"),
                            ),
                        ),
                        showlegend=False, height=220,
                        margin=dict(l=30, r=30, t=15, b=15),
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                        font=dict(family="Inter, sans-serif", color="#E6EDF3"),
                    )
                    st.plotly_chart(fig_r, use_container_width=True, config={"displayModeBar": False}, key=f"radar_{i}")
                else:
                    st.markdown(
                        '<div style="text-align:center;padding:2rem;color:#484F58;font-size:0.8rem;">'
                        'Score breakdown pending next scan</div>',
                        unsafe_allow_html=True,
                    )

                # Holder stats
                exp_buyers = gem.get("experienced_buyers_count", 0)
                holder_count = gem.get("holder_count", 0)
                top10_pct = gem.get("intel_top10_holder_pct", 0)
                if any([exp_buyers, holder_count, top10_pct]):
                    st.markdown("**Holder Intelligence**")
                    if exp_buyers:
                        st.markdown(f"🧠 Exp. Buyers: **{exp_buyers}**")
                    if holder_count:
                        st.markdown(f"👥 Total Holders: **{holder_count:,}**")
                    if top10_pct:
                        conc_color = DANGER if top10_pct > 60 else (WARNING if top10_pct > 40 else ACCENT)
                        st.markdown(
                            f'<span style="color:{conc_color};font-size:0.8rem;">'
                            f'🏦 Top 10 Hold: <strong>{top10_pct:.1f}%</strong></span>',
                            unsafe_allow_html=True,
                        )

            # ── Signal Row ────────────────────────────────────────────────────
            signal = gem.get("signal")
            if signal:
                st.markdown("---")
                sg1, sg2, sg3, sg4, sg5 = st.columns(5)
                with sg1:
                    st.metric("Trend", f"{signal.get('trend', 0):.0f}")
                with sg2:
                    st.metric("Momentum", f"{signal.get('momentum', 0):.0f}")
                with sg3:
                    st.metric("Volume", f"{signal.get('volume', 0):.0f}")
                with sg4:
                    st.metric("Fib Score", f"{signal.get('fib_score', 0):.0f}")
                with sg5:
                    sig_str = signal.get("signal", "N/A")
                    sig_emoji = {"BUY": "🟢", "SELL": "🔴", "NEUTRAL": "🟡"}.get(sig_str, "⚪")
                    st.metric("Signal", f"{sig_emoji} {sig_str}")

            # ── Manual Force Buy + Research Report ───────────────────────────
            gem_addr = gem.get("address", "")
            gem_sym = gem.get("symbol", "?")
            gem_chain = gem.get("chain", "base")
            if gem_addr:
                st.markdown("---")
                fb_c1, fb_c2, fb_c3, fb_c4, fb_c5 = st.columns([1, 1, 1, 1, 1])
                with fb_c1:
                    if st.button(
                        "🛒 Buy $50",
                        key=f"buy50_{i}_{gem_addr[:8]}",
                        use_container_width=True,
                        help=f"Force-buy {gem_sym} with $50 via primary wallet",
                    ):
                        request_manual_buy(
                            token_address=gem_addr,
                            chain=gem_chain,
                            symbol=gem_sym,
                            usd_amount=50.0,
                            wallet="primary",
                            reason="gemscanner_force_buy_50",
                        )
                        st.success(f"✅ Queued: buy ${50} of {gem_sym} on {gem_chain}")
                        st.rerun()
                with fb_c2:
                    if st.button(
                        "🛒 Buy $100",
                        key=f"buy100_{i}_{gem_addr[:8]}",
                        use_container_width=True,
                        help=f"Force-buy {gem_sym} with $100 via primary wallet",
                    ):
                        request_manual_buy(
                            token_address=gem_addr,
                            chain=gem_chain,
                            symbol=gem_sym,
                            usd_amount=100.0,
                            wallet="primary",
                            reason="gemscanner_force_buy_100",
                        )
                        st.success(f"✅ Queued: buy $100 of {gem_sym} on {gem_chain}")
                        st.rerun()
                with fb_c3:
                    if st.button(
                        "🛒 Buy $250",
                        key=f"buy250_{i}_{gem_addr[:8]}",
                        use_container_width=True,
                        help=f"Force-buy {gem_sym} with $250 via primary wallet",
                    ):
                        request_manual_buy(
                            token_address=gem_addr,
                            chain=gem_chain,
                            symbol=gem_sym,
                            usd_amount=250.0,
                            wallet="primary",
                            reason="gemscanner_force_buy_250",
                        )
                        st.success(f"✅ Queued: buy $250 of {gem_sym} on {gem_chain}")
                        st.rerun()
                with fb_c4:
                    if st.button(
                        "📄 Research Report",
                        key=f"report_{i}_{gem_addr[:8]}",
                        use_container_width=True,
                        help=f"Generate a full PDF research report for {gem_sym}",
                    ):
                        with st.spinner(f"Generating report for {gem_sym}..."):
                            try:
                                from core.research_report import generate_token_report
                                result = generate_token_report(
                                    token_address=gem_addr,
                                    chain=gem_chain,
                                    capital_usd=5000.0,
                                )
                                if result.get("success") and result.get("pdf_path"):
                                    with open(result["pdf_path"], "rb") as _pdf:
                                        st.download_button(
                                            label=f"⬇️ Download {gem_sym} Report",
                                            data=_pdf.read(),
                                            file_name=os.path.basename(result["pdf_path"]),
                                            mime="application/pdf",
                                            key=f"dl_report_{i}_{gem_addr[:8]}",
                                        )
                                    st.success(f"✅ Report ready: {result.get('verdict')} ({result.get('gem_score', 0):.0f}/100)")
                                else:
                                    st.error(f"Report failed: {result.get('error', 'Unknown error')}")
                            except Exception as _re:
                                st.error(f"Report error: {_re}")
                with fb_c5:
                    st.markdown(
                        f'<div style="color:#484F58;font-size:0.65rem;padding-top:8px;">'
                        f'⚠️ Safety checks always run. Score gate bypassed. '
                        f'Chain: <b style="color:#8B949E;">{gem_chain}</b> · '
                        f'Addr: <span style="font-family:monospace;">{gem_addr[:12]}...</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

else:
    st.markdown(
        '<div class="glass-card" style="text-align:center;padding:3rem;">'
        '<div style="font-size:2.2rem;margin-bottom:10px;">🔍</div>'
        '<div style="color:#8B949E;font-size:1rem;font-weight:600;">No gems match your filters</div>'
        '<div style="color:#484F58;font-size:0.8rem;margin-top:6px;">'
        'Try lowering the minimum score, removing filters, or triggering a Force Scan above</div>'
        '</div>',
        unsafe_allow_html=True,
    )

# ── Historical Score Distribution ─────────────────────────────────────────────
if history:
    st.markdown('<div style="height:20px;"></div>', unsafe_allow_html=True)
    st.markdown("#### 📊 Score Distribution (All-Time)")
    all_scores = [g.get("gem_score", 0) for g in history if g.get("gem_score", 0) > 0]
    if all_scores:
        fig_hist = go.Figure()
        fig_hist.add_trace(go.Histogram(
            x=all_scores, nbinsx=30,
            marker_color=ACCENT,
            marker_line=dict(color="#0A0E14", width=1),
            opacity=0.85,
            hovertemplate="Score %{x:.0f}–%{x:.0f}: %{y} gems<extra></extra>",
        ))
        fig_hist.update_layout(
            **PLOTLY_LAYOUT, height=240,
            xaxis_title="Gem Score", yaxis_title="Count", bargap=0.05,
        )
        st.plotly_chart(fig_hist, use_container_width=True, config={"displayModeBar": False}, key="score_histogram")
