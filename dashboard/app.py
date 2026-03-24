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

from styles import (
    PREMIUM_CSS, PLOTLY_LAYOUT, ACCENT, CHAIN_COLORS, CHAIN_EMOJI,
    DANGER, WARNING, INFO,
)
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
    st.markdown(
        '<span style="color:#8B949E;font-size:0.82rem;font-weight:500;">'
        'Multi-Chain Trading Engine</span>',
        unsafe_allow_html=True,
    )
    st.markdown("---")

    status = get_bot_status()
    mode = status.get("mode", "unknown").upper()
    is_running = status.get("is_running", False)

    # Live status indicator
    if is_running:
        badge_class = "status-live" if mode == "LIVE" else "status-paper"
        st.markdown(
            f'<div class="{badge_class}">'
            f'<span class="live-dot"></span> RUNNING • {mode}'
            f'</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div style="display:flex;align-items:center;gap:8px;">'
            '<span style="display:inline-block;width:8px;height:8px;border-radius:50%;'
            'background:#FF4757;"></span>'
            '<span style="color:#FF4757;font-weight:600;font-size:0.82rem;">OFFLINE</span>'
            '</div>',
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # Chains
    chains = status.get("chains_scanned", [])
    if chains:
        st.markdown(
            '<div style="color:#8B949E;font-size:0.68rem;font-weight:700;'
            'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:8px;">'
            'Active Chains</div>',
            unsafe_allow_html=True,
        )
        chain_html = ""
        for chain in chains:
            color = CHAIN_COLORS.get(chain, "#8B949E")
            emoji = CHAIN_EMOJI.get(chain, "⬡")
            chain_html += (
                f'<div style="display:flex;align-items:center;gap:8px;'
                f'padding:4px 0;font-size:0.82rem;">'
                f'<span>{emoji}</span>'
                f'<span style="color:{color};font-weight:500;">{chain.capitalize()}</span>'
                f'</div>'
            )
        st.markdown(chain_html, unsafe_allow_html=True)

    st.markdown("---")

    # Uptime & Cycles
    uptime = status.get("uptime_seconds", 0)
    days = uptime // 86400
    hours = (uptime % 86400) // 3600
    minutes = (uptime % 3600) // 60

    if days > 0:
        uptime_str = f"{days}d {hours}h {minutes}m"
    elif hours > 0:
        uptime_str = f"{hours}h {minutes}m"
    else:
        uptime_str = f"{minutes}m"

    cycle = status.get("cycle_count", 0)

    sidebar_stats = f"""
    <div style="display:flex;flex-direction:column;gap:10px;">
        <div>
            <div style="color:#484F58;font-size:0.65rem;font-weight:600;text-transform:uppercase;
                letter-spacing:0.08em;">Uptime</div>
            <div style="color:#E6EDF3;font-size:0.95rem;font-weight:600;
                font-family:'JetBrains Mono',monospace;">{uptime_str}</div>
        </div>
        <div>
            <div style="color:#484F58;font-size:0.65rem;font-weight:600;text-transform:uppercase;
                letter-spacing:0.08em;">Scan Cycles</div>
            <div style="color:#E6EDF3;font-size:0.95rem;font-weight:600;
                font-family:'JetBrains Mono',monospace;">{cycle:,}</div>
        </div>
    </div>
    """
    st.markdown(sidebar_stats, unsafe_allow_html=True)

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
                f'<div style="color:#484F58;font-size:0.72rem;margin-top:8px;">'
                f'Last scan: <span style="color:#8B949E;">{ago_str}</span></div>',
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
        st.markdown(
            f'<div style="color:#484F58;font-size:0.7rem;margin-top:4px;">'
            f'↻ Every {refresh_rate}s</div>',
            unsafe_allow_html=True,
        )

    # Version footer
    st.markdown("---")
    st.markdown(
        '<div style="color:#30363D;font-size:0.65rem;text-align:center;">'
        'v3.0 · 18-Signal Engine<br>Moralis Pro · Rug Protection</div>',
        unsafe_allow_html=True,
    )

# ─────────────────────────────────────────────────────────────────────────────
# Main Content — Command Center
# ─────────────────────────────────────────────────────────────────────────────

# ── Page Header ──────────────────────────────────────────────────────────────
st.markdown(
    '<div class="page-header">'
    '<div style="display:flex;align-items:center;gap:12px;">'
    '<span style="font-size:1.8rem;">☘️</span>'
    '<div>'
    '<h1>COMMAND CENTER</h1>'
    '<div class="subtitle">Real-time trading intelligence · 18-signal pipeline</div>'
    '</div>'
    '</div>'
    '</div>',
    unsafe_allow_html=True,
)

# ── Data Loading ─────────────────────────────────────────────────────────────
history = get_scan_history()
gems = get_gem_history()
trades_data = get_trades()
positions_data = get_positions()

total_scans = len(history)
total_gems = len(gems)
active_positions = len([p for p in positions_data if p.get("is_open", False)])

# Calculate P&L
buy_total = sum(
    t.get("amount_in", 0) * t.get("price_usd", 1)
    for t in trades_data if t.get("direction") == "buy"
)
sell_total = sum(
    t.get("amount_out", 0) * t.get("price_usd", 1)
    for t in trades_data if t.get("direction") == "sell"
)
# Also consider realized PnL from position monitor
realized_pnl = sum(t.get("pnl_usd", 0) for t in trades_data if t.get("direction") == "sell")
# Unrealized from open positions
unrealized_pnl = sum(
    p.get("realized_pnl_usd", 0) for p in positions_data if p.get("is_open", False)
)
total_pnl = realized_pnl + unrealized_pnl
total_trades = len(trades_data)

# ── Moralis Wallet Intelligence ──────────────────────────────────────────
# Fetch real-time portfolio value and on-chain P&L from Moralis Pro API
moralis_net_worth = 0.0
moralis_pnl_data = {}
try:
    from data.providers.moralis_wallet import get_wallet_net_worth, get_aggregate_pnl
    import os as _os
    _wallets = {
        "evm": _os.getenv("EVM_WALLET_ADDRESS", ""),
    }
    for _wkey, _waddr in _wallets.items():
        if _waddr:
            nw = get_wallet_net_worth(_waddr)
            moralis_net_worth += nw.get("total_networth_usd", 0)
    if moralis_net_worth > 0:
        moralis_pnl_data = get_aggregate_pnl(days=30)
except Exception:
    pass  # Graceful degradation — dashboard still works without Moralis

# ── P&L Hero Display ────────────────────────────────────────────────────────
pnl_class = "positive" if total_pnl > 0 else ("negative" if total_pnl < 0 else "zero")
pnl_sign = "+" if total_pnl > 0 else ""
pnl_display = f"{pnl_sign}${abs(total_pnl):,.2f}"

# Build subtitle
if total_trades > 0:
    wins = len([t for t in trades_data if t.get("direction") == "sell" and t.get("pnl_usd", 0) > 0])
    sells = len([t for t in trades_data if t.get("direction") == "sell"])
    win_rate = (wins / max(sells, 1)) * 100
    pnl_subtitle = f"{total_trades} trades · {win_rate:.0f}% win rate"
else:
    pnl_subtitle = "Awaiting first trade"

hero_col1, hero_col2, hero_col3 = st.columns([1, 2, 1])

with hero_col2:
    st.markdown(
        f'<div class="pnl-hero">'
        f'<div class="pnl-label">Total Portfolio P&L</div>'
        f'<div class="pnl-value {pnl_class}">{pnl_display}</div>'
        f'<div class="pnl-subtitle">{pnl_subtitle}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

# ── Moralis Net Worth Row ────────────────────────────────────────────────
if moralis_net_worth > 0:
    nw_col1, nw_col2, nw_col3 = st.columns([1, 2, 1])
    with nw_col2:
        moralis_pnl_total = moralis_pnl_data.get("total_profit_usd", 0)
        mpnl_class = "positive" if moralis_pnl_total > 0 else ("negative" if moralis_pnl_total < 0 else "zero")
        mpnl_sign = "+" if moralis_pnl_total > 0 else ""
        st.markdown(
            f'<div style="text-align:center;padding:12px 0;margin:-10px 0 6px 0;">'
            f'<div style="display:flex;justify-content:center;gap:32px;">'
            f'<div>'
            f'<div style="color:#484F58;font-size:0.65rem;font-weight:700;'
            f'text-transform:uppercase;letter-spacing:0.1em;">On-Chain Net Worth</div>'
            f'<div style="color:#E6EDF3;font-size:1.3rem;font-weight:700;'
            f'font-family:\'JetBrains Mono\',monospace;">${moralis_net_worth:,.2f}</div>'
            f'</div>'
            f'<div>'
            f'<div style="color:#484F58;font-size:0.65rem;font-weight:700;'
            f'text-transform:uppercase;letter-spacing:0.1em;">30d Realized P&L</div>'
            f'<div class="pnl-value {mpnl_class}" style="font-size:1.3rem;">'
            f'{mpnl_sign}${abs(moralis_pnl_total):,.2f}</div>'
            f'</div>'
            f'</div>'
            f'<div style="color:#30363D;font-size:0.6rem;margin-top:4px;">'
            f'Powered by Moralis Pro API</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

st.markdown("<div style='height:20px;'></div>", unsafe_allow_html=True)

# ── Stats Row ────────────────────────────────────────────────────────────────
avg_gems_per_scan = (
    sum(h.get("candidates_found", 0) for h in history[-50:]) / max(len(history[-50:]), 1)
    if history else 0
)

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.markdown(
        '<div class="stat-card">'
        '<div class="stat-icon">📡</div>'
        '<div class="stat-label">Total Scans</div>'
        f'<div class="stat-value">{total_scans:,}</div>'
        f'<div class="stat-delta neutral">~{avg_gems_per_scan:.1f} gems/scan</div>'
        '</div>',
        unsafe_allow_html=True,
    )

with col2:
    st.markdown(
        '<div class="stat-card">'
        '<div class="stat-icon">💎</div>'
        '<div class="stat-label">Gems Discovered</div>'
        f'<div class="stat-value">{total_gems:,}</div>'
        f'<div class="stat-delta neutral">Across all chains</div>'
        '</div>',
        unsafe_allow_html=True,
    )

with col3:
    pos_delta_class = "positive" if active_positions > 0 else "neutral"
    st.markdown(
        '<div class="stat-card">'
        '<div class="stat-icon">📍</div>'
        '<div class="stat-label">Active Positions</div>'
        f'<div class="stat-value">{active_positions}</div>'
        f'<div class="stat-delta {pos_delta_class}">'
        f'{len(positions_data)} total tracked</div>'
        '</div>',
        unsafe_allow_html=True,
    )

with col4:
    trade_delta = f"{total_trades} executed" if total_trades > 0 else "Scanning..."
    st.markdown(
        '<div class="stat-card">'
        '<div class="stat-icon">⚡</div>'
        '<div class="stat-label">Trades</div>'
        f'<div class="stat-value">{total_trades}</div>'
        f'<div class="stat-delta neutral">{trade_delta}</div>'
        '</div>',
        unsafe_allow_html=True,
    )

st.markdown("<div style='height:20px;'></div>", unsafe_allow_html=True)

# ── Charts Row ───────────────────────────────────────────────────────────────
chart_col1, chart_col2 = st.columns([2, 1])

with chart_col1:
    st.markdown("#### 📈 Scan Activity")

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
            fillcolor="rgba(0, 208, 156, 0.06)",
            hovertemplate="<b>%{y} candidates</b><br>%{x|%H:%M:%S}<extra></extra>",
        ))

        if "trades_attempted" in df_hist.columns:
            fig.add_trace(go.Bar(
                x=df_hist["timestamp"],
                y=df_hist["trades_attempted"],
                name="Trades",
                marker_color="rgba(88, 166, 255, 0.5)",
                hovertemplate="<b>%{y} trades</b><br>%{x|%H:%M:%S}<extra></extra>",
            ))

        fig.update_layout(
            **PLOTLY_LAYOUT,
            height=300,
            xaxis_title=None,
            yaxis_title=None,
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    else:
        st.markdown(
            '<div class="glass-card" style="text-align:center;padding:3rem;">'
            '<div style="font-size:2rem;margin-bottom:0.5rem;">📡</div>'
            '<div style="color:#8B949E;">Waiting for scan data...</div>'
            '<div style="color:#484F58;font-size:0.78rem;">Data appears after the first cycle</div>'
            '</div>',
            unsafe_allow_html=True,
        )

with chart_col2:
    st.markdown("#### 🔗 Chain Distribution")

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
            hole=0.72,
            marker=dict(colors=colors, line=dict(color="#06090F", width=2)),
            textinfo="percent",
            textfont=dict(size=11, color="#E6EDF3"),
            hovertemplate="<b>%{label}</b><br>%{value} gems (%{percent})<extra></extra>",
        )])

        fig_donut.update_layout(
            **PLOTLY_LAYOUT,
            height=300,
            annotations=[dict(
                text=f"<b>{sum(counts)}</b><br>gems",
                x=0.5, y=0.5, font_size=15,
                font=dict(color="#E6EDF3", family="JetBrains Mono, Inter"),
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
st.markdown("#### 💎 Recent Gem Candidates")

latest = get_latest_gems()
if latest:
    gem_rows = []
    for g in sorted(latest, key=lambda x: x.get("gem_score", 0), reverse=True)[:20]:
        score = g.get("gem_score", 0)
        chain = g.get("chain", "")
        emoji = CHAIN_EMOJI.get(chain, "⬡")

        gem_rows.append({
            "Score": f"{score:.1f}",
            "Token": g.get("symbol", "???"),
            "Chain": f"{emoji} {chain.capitalize()}",
            "Price": f"${g.get('price_usd', 0):.6f}" if g.get("price_usd", 0) < 1 else f"${g.get('price_usd', 0):,.2f}",
            "Liquidity": f"${g.get('liquidity_usd', 0):,.0f}",
            "Vol 1h": f"${g.get('volume_1h', 0):,.0f}",
            "MCap": f"${g.get('market_cap', 0):,.0f}",
            "Age": f"{g.get('age_hours', 0):.1f}h" if g.get("age_hours") else "N/A",
            "Boost": "🚀" if g.get("is_boosted") else "",
            "Safe": "✅" if g.get("is_safe") else "⚠️",
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
        '<div class="glass-card" style="text-align:center;padding:2.5rem;">'
        '<div style="font-size:1.5rem;margin-bottom:0.5rem;">💎</div>'
        '<div style="color:#8B949E;">No gem candidates discovered yet</div>'
        '<div style="color:#484F58;font-size:0.78rem;margin-top:4px;">'
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
                f'background:rgba(255,71,87,0.05);border-left:3px solid #FF4757;'
                f'font-size:0.78rem;">'
                f'<span style="color:#484F58;">{err.get("timestamp", "")[:19]}</span> · '
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
