"""
dashboard/app.py — ☘️ Shamrock Trading Bot — Command Center

Premium dark-mode dashboard: Fortune 50-grade aesthetics.
This is the main entry point for the Streamlit multi-page app.
"""

import sys
import os

# Add parent dir to path so we can import dashboard modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from datetime import datetime, timezone, timedelta

from styles import PREMIUM_CSS, PLOTLY_LAYOUT, ACCENT, CHAIN_COLORS, DANGER, WARNING, INFO
from state import (
    get_bot_status,
    get_scan_history,
    get_latest_gems,
    get_gem_history,
    get_trades,
    get_positions,
    get_errors,
)

# ─────────────────────────────────────────────────────────────────────────────
# Page Config
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Shamrock Trading Bot",
    page_icon="☘️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Inject premium CSS
st.markdown(PREMIUM_CSS, unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("# ☘️ SHAMROCK")
    st.markdown("**Trading Bot**")
    st.markdown("---")

    status = get_bot_status()
    mode = status.get("mode", "unknown").upper()
    is_running = status.get("is_running", False)

    # Live status indicator
    if is_running:
        st.markdown(
            '<div style="display:flex;align-items:center;gap:8px;">'
            '<span class="live-dot"></span>'
            f'<span style="color:#00D09C;font-weight:600;font-size:0.85rem;">RUNNING • {mode}</span>'
            '</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div style="display:flex;align-items:center;gap:8px;">'
            '<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#FF4757;margin-right:6px;"></span>'
            '<span style="color:#FF4757;font-weight:600;font-size:0.85rem;">OFFLINE</span>'
            '</div>',
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # Chains
    chains = status.get("chains_scanned", [])
    if chains:
        st.markdown("### Active Chains")
        for chain in chains:
            color = CHAIN_COLORS.get(chain, "#8B949E")
            emoji_map = {
                "ethereum": "⟠", "base": "🔵", "arbitrum": "🔷",
                "polygon": "🟣", "bsc": "🟡"
            }
            emoji = emoji_map.get(chain, "⬡")
            st.markdown(
                f'<span style="color:{color};font-weight:500;">'
                f'{emoji} {chain.capitalize()}</span>',
                unsafe_allow_html=True,
            )

    st.markdown("---")

    # Uptime
    uptime = status.get("uptime_seconds", 0)
    hours = uptime // 3600
    minutes = (uptime % 3600) // 60
    st.markdown(
        f'<div style="color:#8B949E;font-size:0.8rem;">'
        f'⏱ Uptime: <strong style="color:#E6EDF3;">{hours}h {minutes}m</strong></div>',
        unsafe_allow_html=True,
    )

    cycle = status.get("cycle_count", 0)
    st.markdown(
        f'<div style="color:#8B949E;font-size:0.8rem;">'
        f'🔄 Cycles: <strong style="color:#E6EDF3;">{cycle:,}</strong></div>',
        unsafe_allow_html=True,
    )

    last_cycle = status.get("last_cycle_at", "")
    if last_cycle:
        try:
            dt = datetime.fromisoformat(last_cycle.replace("Z", "+00:00"))
            ago = (datetime.now(timezone.utc) - dt).total_seconds()
            if ago < 120:
                ago_str = f"{int(ago)}s ago"
            elif ago < 7200:
                ago_str = f"{int(ago/60)}m ago"
            else:
                ago_str = f"{int(ago/3600)}h ago"
            st.markdown(
                f'<div style="color:#8B949E;font-size:0.8rem;">'
                f'📡 Last scan: <strong style="color:#E6EDF3;">{ago_str}</strong></div>',
                unsafe_allow_html=True,
            )
        except (ValueError, TypeError):
            pass

    # Auto-refresh
    st.markdown("---")
    auto_refresh = st.toggle("Auto-refresh", value=True)
    refresh_rate = st.select_slider(
        "Interval",
        options=[5, 10, 15, 30, 60],
        value=15,
        format_func=lambda x: f"{x}s",
    )

    if auto_refresh:
        import time
        st.markdown(
            f'<div style="color:#8B949E;font-size:0.75rem;margin-top:4px;">'
            f'Refreshing every {refresh_rate}s</div>',
            unsafe_allow_html=True,
        )

# ─────────────────────────────────────────────────────────────────────────────
# Main Content — Command Center
# ─────────────────────────────────────────────────────────────────────────────

# Title bar
st.markdown(
    '<div style="display:flex;align-items:center;gap:12px;margin-bottom:1.5rem;">'
    '<span style="font-size:2rem;">☘️</span>'
    '<div>'
    '<h1 style="margin:0;padding:0;font-size:1.5rem;font-weight:800;'
    'background:linear-gradient(135deg,#00D09C,#00E6AC);'
    '-webkit-background-clip:text;-webkit-text-fill-color:transparent;'
    'letter-spacing:-0.02em;">COMMAND CENTER</h1>'
    '<span style="color:#8B949E;font-size:0.8rem;">Real-time trading intelligence</span>'
    '</div></div>',
    unsafe_allow_html=True,
)

# ── Hero Stats Row ───────────────────────────────────────────────────────────
history = get_scan_history()
gems = get_gem_history()
trades_data = get_trades()
positions_data = get_positions()

total_scans = len(history)
total_gems = len(gems)
active_positions = len([p for p in positions_data if p.get("is_open", False)])

# Calculate P&L
total_pnl = sum(t.get("amount_out", 0) - t.get("amount_in", 0) for t in trades_data if t.get("direction") == "sell")

# Delta calculations
recent_scans = [h for h in history[-10:] if h.get("candidates_found", 0) > 0]
avg_gems_per_scan = sum(h.get("candidates_found", 0) for h in history[-50:]) / max(len(history[-50:]), 1) if history else 0

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        label="TOTAL SCANS",
        value=f"{total_scans:,}",
        delta=f"+{len(history[-10:])} last 10 cycles" if history else None,
    )

with col2:
    st.metric(
        label="GEMS DISCOVERED",
        value=f"{total_gems:,}",
        delta=f"~{avg_gems_per_scan:.1f}/scan avg" if history else None,
    )

with col3:
    st.metric(
        label="ACTIVE POSITIONS",
        value=str(active_positions),
        delta=f"{len(positions_data)} total" if positions_data else "0",
    )

with col4:
    pnl_str = f"${total_pnl:,.2f}" if total_pnl != 0 else "$0.00"
    st.metric(
        label="PORTFOLIO P&L",
        value=pnl_str,
        delta=f"{len(trades_data)} trades" if trades_data else "Paper mode",
    )

st.markdown("<div style='height:24px;'></div>", unsafe_allow_html=True)

# ── Charts Row ───────────────────────────────────────────────────────────────
chart_col1, chart_col2 = st.columns([2, 1])

with chart_col1:
    st.markdown("## 📈 Scan Activity")

    if history:
        df_hist = pd.DataFrame(history)
        df_hist["timestamp"] = pd.to_datetime(df_hist["timestamp"])
        df_hist = df_hist.sort_values("timestamp")

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df_hist["timestamp"],
            y=df_hist["candidates_found"],
            mode="lines",
            name="Candidates",
            line=dict(color=ACCENT, width=2),
            fill="tozeroy",
            fillcolor="rgba(0, 208, 156, 0.08)",
            hovertemplate="<b>%{y} candidates</b><br>%{x|%H:%M:%S}<extra></extra>",
        ))

        if "trades_attempted" in df_hist.columns:
            fig.add_trace(go.Bar(
                x=df_hist["timestamp"],
                y=df_hist["trades_attempted"],
                name="Trades",
                marker_color="rgba(88, 166, 255, 0.6)",
                hovertemplate="<b>%{y} trades</b><br>%{x|%H:%M:%S}<extra></extra>",
            ))

        fig.update_layout(
            **PLOTLY_LAYOUT,
            height=320,
            showlegend=True,
            xaxis_title=None,
            yaxis_title=None,
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    else:
        st.markdown(
            '<div class="glass-card" style="text-align:center;padding:3rem;">'
            '<div style="font-size:2rem;margin-bottom:0.5rem;">📡</div>'
            '<div style="color:#8B949E;">Waiting for scan data...</div>'
            '<div style="color:#484F58;font-size:0.8rem;">Data will appear after the first scan cycle</div>'
            '</div>',
            unsafe_allow_html=True,
        )

with chart_col2:
    st.markdown("## 🔗 Chain Distribution")

    if gems:
        chain_counts = {}
        for g in gems:
            chain = g.get("chain", "unknown")
            chain_counts[chain] = chain_counts.get(chain, 0) + 1

        chains_list = list(chain_counts.keys())
        counts = list(chain_counts.values())
        colors = [CHAIN_COLORS.get(c, "#8B949E") for c in chains_list]

        fig_donut = go.Figure(data=[go.Pie(
            labels=[c.capitalize() for c in chains_list],
            values=counts,
            hole=0.7,
            marker=dict(colors=colors, line=dict(color="#0A0E14", width=2)),
            textinfo="percent",
            textfont=dict(size=11, color="#E6EDF3"),
            hovertemplate="<b>%{label}</b><br>%{value} gems (%{percent})<extra></extra>",
        )])

        fig_donut.update_layout(
            **PLOTLY_LAYOUT,
            height=320,
            showlegend=True,
            annotations=[dict(
                text=f"<b>{sum(counts)}</b><br>gems",
                x=0.5, y=0.5, font_size=16,
                font=dict(color="#E6EDF3", family="Inter"),
                showarrow=False,
            )],
        )
        st.plotly_chart(fig_donut, use_container_width=True, config={"displayModeBar": False})
    else:
        st.markdown(
            '<div class="glass-card" style="text-align:center;padding:3rem;">'
            '<div style="font-size:2rem;margin-bottom:0.5rem;">🔗</div>'
            '<div style="color:#8B949E;">No chain data yet</div>'
            '</div>',
            unsafe_allow_html=True,
        )

# ── Recent Gems Table ────────────────────────────────────────────────────────
st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)
st.markdown("## 💎 Recent Gem Candidates")

latest = get_latest_gems()
if latest:
    gem_rows = []
    for g in sorted(latest, key=lambda x: x.get("gem_score", 0), reverse=True)[:20]:
        score = g.get("gem_score", 0)
        score_color = "#00D09C" if score >= 75 else ("#FFB84D" if score >= 65 else "#FF4757")
        chain_emoji = {
            "ethereum": "⟠", "base": "🔵", "arbitrum": "🔷",
            "polygon": "🟣", "bsc": "🟡"
        }.get(g.get("chain", ""), "⬡")

        gem_rows.append({
            "Score": f"{score:.1f}",
            "Token": g.get("symbol", "???"),
            "Chain": f"{chain_emoji} {g.get('chain', '').capitalize()}",
            "Price": f"${g.get('price_usd', 0):.6f}" if g.get("price_usd", 0) < 1 else f"${g.get('price_usd', 0):,.2f}",
            "Liquidity": f"${g.get('liquidity_usd', 0):,.0f}",
            "Vol 1h": f"${g.get('volume_1h', 0):,.0f}",
            "MCap": f"${g.get('market_cap', 0):,.0f}",
            "Age": f"{g.get('age_hours', 0):.1f}h" if g.get("age_hours") else "N/A",
            "Boosted": "🚀" if g.get("is_boosted") else "",
            "Safe": "✅" if g.get("is_safe") else "❌",
        })

    df_gems = pd.DataFrame(gem_rows)
    st.dataframe(
        df_gems,
        use_container_width=True,
        hide_index=True,
        height=min(400, len(gem_rows) * 40 + 40),
    )
else:
    st.markdown(
        '<div class="glass-card" style="text-align:center;padding:2rem;">'
        '<div style="font-size:1.5rem;margin-bottom:0.5rem;">💎</div>'
        '<div style="color:#8B949E;">No gem candidates discovered yet</div>'
        '<div style="color:#484F58;font-size:0.8rem;margin-top:4px;">'
        'The scanner is searching across all chains</div>'
        '</div>',
        unsafe_allow_html=True,
    )

# ── Error Feed (if any) ─────────────────────────────────────────────────────
errors = get_errors()
if errors:
    with st.expander(f"⚠️ Recent Errors ({len(errors[-10:])})", expanded=False):
        for err in reversed(errors[-10:]):
            st.markdown(
                f'<div style="padding:6px 12px;margin:4px 0;border-radius:8px;'
                f'background:rgba(255,71,87,0.06);border-left:3px solid #FF4757;'
                f'font-size:0.82rem;">'
                f'<span style="color:#8B949E;">{err.get("timestamp", "")[:19]}</span> • '
                f'<span style="color:#FF4757;">{err.get("error", "Unknown error")}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

# ── Auto-refresh Script ─────────────────────────────────────────────────────
if auto_refresh:
    st.markdown(
        f"""
        <script>
            setTimeout(function() {{
                window.location.reload();
            }}, {refresh_rate * 1000});
        </script>
        """,
        unsafe_allow_html=True,
    )
