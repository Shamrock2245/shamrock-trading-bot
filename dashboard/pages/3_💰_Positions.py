"""
Page 3 — 💰 Positions & Trades

Open positions with unrealized P&L, trade history log,
and portfolio performance visualization.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime, timezone

from styles import PREMIUM_CSS, PLOTLY_LAYOUT, ACCENT, CHAIN_COLORS, DANGER, WARNING
from state import get_positions, get_trades

st.set_page_config(page_title="Positions | Shamrock", page_icon="💰", layout="wide")
st.markdown(PREMIUM_CSS, unsafe_allow_html=True)

# ── Header ───────────────────────────────────────────────────────────────────
st.markdown(
    '<div style="display:flex;align-items:center;gap:12px;margin-bottom:1.5rem;">'
    '<span style="font-size:2rem;">💰</span>'
    '<div>'
    '<h1 style="margin:0;padding:0;font-size:1.5rem;font-weight:800;'
    'background:linear-gradient(135deg,#00D09C,#00E6AC);'
    '-webkit-background-clip:text;-webkit-text-fill-color:transparent;">POSITIONS & TRADES</h1>'
    '<span style="color:#8B949E;font-size:0.8rem;">Portfolio management and trade history</span>'
    '</div></div>',
    unsafe_allow_html=True,
)

positions = get_positions()
trades = get_trades()

# ── Portfolio Summary ────────────────────────────────────────────────────────
open_positions = [p for p in positions if p.get("is_open", False)]
closed_positions = [p for p in positions if not p.get("is_open", True)]

total_invested = sum(p.get("amount_eth_spent", 0) for p in open_positions)
total_unrealized = sum(p.get("unrealized_pnl_pct", 0) for p in open_positions)
avg_unrealized = total_unrealized / max(len(open_positions), 1)

buy_trades = [t for t in trades if t.get("direction") == "buy"]
sell_trades = [t for t in trades if t.get("direction") == "sell"]
total_pnl_eth = sum(t.get("amount_out", 0) - t.get("amount_in", 0) for t in sell_trades)

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("Open Positions", len(open_positions))
with col2:
    st.metric("Total Invested", f"{total_invested:.4f} ETH")
with col3:
    pnl_color = "normal" if total_pnl_eth >= 0 else "inverse"
    st.metric("Realized P&L", f"{total_pnl_eth:+.4f} ETH", delta=f"{len(sell_trades)} sells")
with col4:
    st.metric("Avg Unrealized", f"{avg_unrealized:+.1f}%")

st.markdown("<div style='height:24px;'></div>", unsafe_allow_html=True)

# ── Tabs ─────────────────────────────────────────────────────────────────────
tab_pos, tab_trades, tab_perf = st.tabs(["📍 Open Positions", "📝 Trade Log", "📈 Performance"])

# ── Open Positions Tab ───────────────────────────────────────────────────────
with tab_pos:
    if open_positions:
        pos_rows = []
        for p in open_positions:
            pnl = p.get("unrealized_pnl_pct", 0)
            pnl_emoji = "🟢" if pnl > 0 else ("🔴" if pnl < 0 else "⚪")
            chain = p.get("chain", "")
            chain_emoji = {"ethereum": "⟠", "base": "🔵", "arbitrum": "🔷", "polygon": "🟣", "bsc": "🟡"}.get(chain, "⬡")

            pos_rows.append({
                "": pnl_emoji,
                "Token": p.get("symbol", "???"),
                "Chain": f"{chain_emoji} {chain.capitalize()}",
                "Entry Price": f"${p.get('entry_price', 0):.8f}",
                "Current Price": f"${p.get('current_price', 0):.8f}",
                "P&L": f"{pnl:+.2f}%",
                "ETH Spent": f"{p.get('amount_eth_spent', 0):.4f}",
                "Fib Zone": p.get("fib_zone", "N/A"),
                "Fib Support": f"${p.get('fib_support', 0):.8f}" if p.get("fib_support") else "—",
                "Fib Resistance": f"${p.get('fib_resistance', 0):.8f}" if p.get("fib_resistance") else "—",
                "Opened": p.get("opened_at", "")[:16],
            })

        df_pos = pd.DataFrame(pos_rows)
        st.dataframe(df_pos, use_container_width=True, hide_index=True)

        # P&L Waterfall
        if len(open_positions) > 1:
            st.markdown("### 📊 Position P&L Distribution")
            fig_waterfall = go.Figure()
            symbols = [p.get("symbol", "?") for p in open_positions]
            pnls = [p.get("unrealized_pnl_pct", 0) for p in open_positions]
            colors = [ACCENT if pnl >= 0 else DANGER for pnl in pnls]

            fig_waterfall.add_trace(go.Bar(
                x=symbols,
                y=pnls,
                marker=dict(color=colors, line=dict(color="#0A0E14", width=1)),
                hovertemplate="<b>%{x}</b><br>P&L: %{y:+.2f}%<extra></extra>",
            ))

            fig_waterfall.update_layout(
                **PLOTLY_LAYOUT, height=300,
                yaxis_title="Unrealized P&L %",
                showlegend=False,
            )
            st.plotly_chart(fig_waterfall, use_container_width=True, config={"displayModeBar": False})
    else:
        st.markdown(
            '<div class="glass-card" style="text-align:center;padding:3rem;">'
            '<div style="font-size:2.5rem;margin-bottom:0.75rem;">📍</div>'
            '<div style="color:#E6EDF3;font-size:1.1rem;font-weight:600;">No Open Positions</div>'
            '<div style="color:#8B949E;font-size:0.85rem;margin-top:6px;">'
            'Positions will appear when the bot executes trades</div>'
            '</div>',
            unsafe_allow_html=True,
        )

# ── Trade Log Tab ────────────────────────────────────────────────────────────
with tab_trades:
    if trades:
        trade_rows = []
        for t in sorted(trades, key=lambda x: x.get("timestamp", ""), reverse=True)[:100]:
            direction = t.get("direction", "")
            dir_emoji = "🟢 BUY" if direction == "buy" else "🔴 SELL"
            status = t.get("status", "")
            status_emoji = {"success": "✅", "failed": "❌", "pending": "⏳"}.get(status, "❓")

            trade_rows.append({
                "Time": t.get("timestamp", "")[:19],
                "Dir": dir_emoji,
                "Token": t.get("symbol", "???"),
                "Chain": t.get("chain", "").capitalize(),
                "Price": f"${t.get('price_usd', 0):.6f}",
                "In": f"{t.get('amount_in', 0):.4f}",
                "Out": f"{t.get('amount_out', 0):.4f}",
                "Gas (ETH)": f"{t.get('gas_cost_eth', 0):.6f}",
                "Path": t.get("execution_path", "").upper(),
                "Score": f"{t.get('gem_score', 0):.1f}",
                "Status": status_emoji,
            })

        df_trades = pd.DataFrame(trade_rows)
        st.dataframe(df_trades, use_container_width=True, hide_index=True, height=500)

        # Trade volume over time
        st.markdown("### 📊 Trade Volume Over Time")
        df_t = pd.DataFrame(trades)
        df_t["timestamp"] = pd.to_datetime(df_t["timestamp"])
        df_t = df_t.sort_values("timestamp")

        fig_vol = go.Figure()
        buys = df_t[df_t["direction"] == "buy"]
        sells = df_t[df_t["direction"] == "sell"]

        if not buys.empty:
            fig_vol.add_trace(go.Scatter(
                x=buys["timestamp"], y=buys["amount_in"],
                mode="markers", name="Buys",
                marker=dict(color=ACCENT, size=8, symbol="triangle-up"),
                hovertemplate="<b>BUY</b><br>%{y:.4f} ETH<br>%{x|%b %d %H:%M}<extra></extra>",
            ))
        if not sells.empty:
            fig_vol.add_trace(go.Scatter(
                x=sells["timestamp"], y=sells["amount_out"],
                mode="markers", name="Sells",
                marker=dict(color=DANGER, size=8, symbol="triangle-down"),
                hovertemplate="<b>SELL</b><br>%{y:.4f} ETH<br>%{x|%b %d %H:%M}<extra></extra>",
            ))

        fig_vol.update_layout(
            **PLOTLY_LAYOUT, height=300,
        )
        st.plotly_chart(fig_vol, use_container_width=True, config={"displayModeBar": False})
    else:
        st.markdown(
            '<div class="glass-card" style="text-align:center;padding:3rem;">'
            '<div style="font-size:2.5rem;margin-bottom:0.75rem;">📝</div>'
            '<div style="color:#E6EDF3;font-size:1.1rem;font-weight:600;">No Trades Yet</div>'
            '<div style="color:#8B949E;font-size:0.85rem;margin-top:6px;">'
            f'Bot is running in PAPER mode — simulated trades will appear here</div>'
            '</div>',
            unsafe_allow_html=True,
        )

# ── Performance Tab ──────────────────────────────────────────────────────────
with tab_perf:
    if trades:
        st.markdown("### 📈 Cumulative P&L")

        df_perf = pd.DataFrame(trades)
        df_perf["timestamp"] = pd.to_datetime(df_perf["timestamp"])
        df_perf = df_perf.sort_values("timestamp")
        df_perf["pnl"] = df_perf.apply(
            lambda r: (r.get("amount_out", 0) - r.get("amount_in", 0)) if r.get("direction") == "sell" else 0,
            axis=1
        )
        df_perf["cumulative_pnl"] = df_perf["pnl"].cumsum()

        fig_pnl = go.Figure()
        fig_pnl.add_trace(go.Scatter(
            x=df_perf["timestamp"],
            y=df_perf["cumulative_pnl"],
            mode="lines",
            line=dict(color=ACCENT, width=2.5),
            fill="tozeroy",
            fillcolor="rgba(0, 208, 156, 0.1)",
            hovertemplate="<b>P&L: %{y:.4f} ETH</b><br>%{x|%b %d %H:%M}<extra></extra>",
        ))

        fig_pnl.add_hline(y=0, line_dash="dash", line_color="rgba(255,255,255,0.1)")

        fig_pnl.update_layout(
            **PLOTLY_LAYOUT, height=350,
            yaxis_title="Cumulative P&L (ETH)",
        )
        st.plotly_chart(fig_pnl, use_container_width=True, config={"displayModeBar": False})

        # Win rate
        st.markdown("### 🎯 Trade Statistics")
        wins = len([t for t in sell_trades if (t.get("amount_out", 0) - t.get("amount_in", 0)) > 0])
        total_sells = len(sell_trades)
        win_rate = (wins / max(total_sells, 1)) * 100

        stat_col1, stat_col2, stat_col3 = st.columns(3)
        with stat_col1:
            st.metric("Win Rate", f"{win_rate:.1f}%")
        with stat_col2:
            st.metric("Total Buys", len(buy_trades))
        with stat_col3:
            st.metric("Total Sells", len(sell_trades))
    else:
        st.markdown(
            '<div class="glass-card" style="text-align:center;padding:3rem;">'
            '<div style="font-size:2.5rem;margin-bottom:0.75rem;">📈</div>'
            '<div style="color:#E6EDF3;font-size:1.1rem;font-weight:600;">Performance Tracking</div>'
            '<div style="color:#8B949E;font-size:0.85rem;margin-top:6px;">'
            'P&L charts and win rate will appear after trades execute</div>'
            '</div>',
            unsafe_allow_html=True,
        )
