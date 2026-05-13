"""
Page 9 — 📈 Paper P&L Tracker

Purpose: Validate trading strategy profitability during paper trading phase.
Shows cumulative P&L, win rate, drawdown, per-chain performance, trade log,
and Grok API usage stats — everything needed to decide when to go live.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import json
from datetime import datetime, timezone, timedelta

from styles import (
    PREMIUM_CSS, PLOTLY_LAYOUT, PLOTLY_LAYOUT_HLEGEND,
    ACCENT, CHAIN_COLORS, DANGER, WARNING, INFO, PURPLE,
)
from state import get_trades, get_positions, get_bot_status
from nav import render_nav

st.set_page_config(page_title="Paper P&L | Shamrock", page_icon="📈", layout="wide")
st.markdown(PREMIUM_CSS, unsafe_allow_html=True)
render_nav("Paper P&L")

# ── Extra CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.pnl-kpi { background: var(--bg-card); border: 1px solid var(--border-subtle);
    border-radius: 14px; padding: 16px 18px; position: relative; overflow: hidden; }
.pnl-kpi::before { content: ''; position: absolute; top: 0; left: 0; right: 0;
    height: 2px; background: linear-gradient(90deg, transparent, var(--accent), transparent); }
.kpi-label { color: #484F58; font-size: 0.6rem; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 4px; }
.kpi-value { color: #E6EDF3; font-size: 1.4rem; font-weight: 800;
    font-family: 'JetBrains Mono', monospace; }
.kpi-sub { color: #8B949E; font-size: 0.68rem; margin-top: 4px; }
.kpi-value.green { color: #00D09C; }
.kpi-value.red { color: #FF4757; }
.kpi-value.amber { color: #FFB84D; }
.trade-row { display: flex; align-items: center; gap: 12px; padding: 10px 14px;
    background: var(--bg-card); border: 1px solid var(--border-subtle);
    border-radius: 10px; margin-bottom: 4px; transition: all 0.2s ease; }
.trade-row:hover { border-color: rgba(0,208,156,0.3); }
.paper-badge { display: inline-flex; align-items: center; gap: 6px;
    background: rgba(255,184,77,0.1); border: 1px solid rgba(255,184,77,0.25);
    border-radius: 20px; padding: 4px 14px; font-size: 0.72rem; font-weight: 700;
    color: #FFB84D; text-transform: uppercase; letter-spacing: 0.08em; }
</style>
""", unsafe_allow_html=True)

# ── Header ───────────────────────────────────────────────────────────────────
status = get_bot_status()
mode = status.get("mode", "unknown").upper()

st.markdown(
    '<div style="display:flex;align-items:center;gap:12px;margin-bottom:1rem;">'
    '<span style="font-size:2rem;">📈</span>'
    '<div>'
    '<h1 style="margin:0;padding:0;font-size:1.5rem;font-weight:800;'
    'background:linear-gradient(135deg,#00D09C,#00E6AC);'
    '-webkit-background-clip:text;-webkit-text-fill-color:transparent;">PAPER P&L TRACKER</h1>'
    '<span style="color:#8B949E;font-size:0.8rem;">Strategy validation · Go-live readiness assessment</span>'
    '</div>'
    f'<div style="margin-left:auto;"><span class="paper-badge">📝 {mode} MODE</span></div>'
    '</div>',
    unsafe_allow_html=True,
)

# ── Load Data ────────────────────────────────────────────────────────────────
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

trades_raw = get_trades()
positions = get_positions()

# Filter to sells only for P&L (buys have no realized P&L)
sells = [t for t in trades_raw if t.get("direction") == "sell" or
         str(t.get("action", "")).upper() == "SELL"]
buys = [t for t in trades_raw if t.get("direction") == "buy" or
        str(t.get("action", "")).upper() == "BUY"]

# ── Empty State ──────────────────────────────────────────────────────────────
if not trades_raw:
    st.markdown(
        '<div class="glass-card" style="text-align:center;padding:4rem;">'
        '<div style="font-size:3.5rem;margin-bottom:1rem;">📈</div>'
        '<div style="color:#E6EDF3;font-size:1.3rem;font-weight:700;">Paper Trading Active</div>'
        '<div style="color:#8B949E;font-size:0.9rem;margin-top:8px;max-width:500px;margin-left:auto;margin-right:auto;">'
        'The bot is scanning and evaluating gems in paper mode. Once it starts '
        'executing paper trades, P&L data will populate here automatically.</div>'
        '<div style="margin-top:24px;display:flex;justify-content:center;gap:16px;">'
        '<div class="pnl-kpi" style="min-width:140px;">'
        '<div class="kpi-label">Mode</div>'
        f'<div class="kpi-value amber">{mode}</div>'
        '</div>'
        '<div class="pnl-kpi" style="min-width:140px;">'
        '<div class="kpi-label">Trades</div>'
        '<div class="kpi-value">0</div>'
        '</div>'
        '<div class="pnl-kpi" style="min-width:140px;">'
        '<div class="kpi-label">Positions</div>'
        f'<div class="kpi-value">{len([p for p in positions if p.get("is_open")])}</div>'
        '</div>'
        '</div></div>',
        unsafe_allow_html=True,
    )
    st.stop()

# ── Compute Metrics ──────────────────────────────────────────────────────────
total_realized = sum(float(t.get("pnl_usd", 0)) for t in sells)
total_trades = len(trades_raw)
total_sells = len(sells)
wins = [t for t in sells if float(t.get("pnl_usd", 0)) > 0]
losses = [t for t in sells if float(t.get("pnl_usd", 0)) < 0]
win_rate = (len(wins) / max(total_sells, 1)) * 100
avg_win = sum(float(t.get("pnl_usd", 0)) for t in wins) / max(len(wins), 1)
avg_loss = sum(float(t.get("pnl_usd", 0)) for t in losses) / max(len(losses), 1)
profit_factor = abs(sum(float(t.get("pnl_usd", 0)) for t in wins)) / max(
    abs(sum(float(t.get("pnl_usd", 0)) for t in losses)), 0.01)
open_positions = [p for p in positions if p.get("is_open")]
unrealized = sum(float(p.get("unrealized_pnl_pct", 0)) for p in open_positions)

# Expectancy = (win_rate% × avg_win) + (loss_rate% × avg_loss)
expectancy = (win_rate / 100 * avg_win) + ((100 - win_rate) / 100 * avg_loss)

# Streaks
current_streak = 0
streak_type = ""
for t in reversed(sells):
    pnl = float(t.get("pnl_usd", 0))
    if not streak_type:
        streak_type = "W" if pnl > 0 else "L"
        current_streak = 1
    elif (pnl > 0 and streak_type == "W") or (pnl <= 0 and streak_type == "L"):
        current_streak += 1
    else:
        break

# Max drawdown from cumulative P&L
cumulative = []
running = 0
peak = 0
max_dd = 0
for t in sells:
    running += float(t.get("pnl_usd", 0))
    cumulative.append(running)
    if running > peak:
        peak = running
    dd = peak - running
    if dd > max_dd:
        max_dd = dd

# ── KPI Row ──────────────────────────────────────────────────────────────────
pnl_class = "green" if total_realized > 0 else ("red" if total_realized < 0 else "")
pnl_sign = "+" if total_realized > 0 else ""
wr_class = "green" if win_rate >= 50 else ("amber" if win_rate >= 40 else "red")
pf_class = "green" if profit_factor >= 1.5 else ("amber" if profit_factor >= 1.0 else "red")
exp_class = "green" if expectancy > 0 else "red"

k1, k2, k3, k4, k5, k6 = st.columns(6)

def _kpi(label, value, sub="", css_class=""):
    return (
        f'<div class="pnl-kpi">'
        f'<div class="kpi-label">{label}</div>'
        f'<div class="kpi-value {css_class}">{value}</div>'
        f'<div class="kpi-sub">{sub}</div>'
        f'</div>'
    )

with k1:
    st.markdown(_kpi("Realized P&L", f"{pnl_sign}${abs(total_realized):,.2f}",
                      f"{total_sells} closed trades", pnl_class), unsafe_allow_html=True)
with k2:
    st.markdown(_kpi("Win Rate", f"{win_rate:.1f}%",
                      f"{len(wins)}W / {len(losses)}L", wr_class), unsafe_allow_html=True)
with k3:
    st.markdown(_kpi("Profit Factor", f"{profit_factor:.2f}",
                      f"Avg W: ${avg_win:.2f} / L: ${avg_loss:.2f}", pf_class), unsafe_allow_html=True)
with k4:
    st.markdown(_kpi("Expectancy", f"${expectancy:+.2f}",
                      "Per trade expected value", exp_class), unsafe_allow_html=True)
with k5:
    dd_class = "green" if max_dd < 20 else ("amber" if max_dd < 50 else "red")
    st.markdown(_kpi("Max Drawdown", f"${max_dd:.2f}",
                      f"Peak: ${peak:.2f}", dd_class), unsafe_allow_html=True)
with k6:
    streak_icon = "🔥" if streak_type == "W" else "❄️"
    s_class = "green" if streak_type == "W" else "red"
    st.markdown(_kpi("Current Streak", f"{streak_icon} {current_streak}{streak_type}",
                      f"{len(open_positions)} open positions", s_class), unsafe_allow_html=True)

st.markdown('<div style="height:20px;"></div>', unsafe_allow_html=True)

# ── Cumulative P&L Curve ─────────────────────────────────────────────────────
st.markdown("## 📈 Cumulative P&L")

if sells:
    df_sells = pd.DataFrame(sells)
    df_sells["timestamp"] = pd.to_datetime(df_sells["timestamp"], errors="coerce")
    df_sells = df_sells.sort_values("timestamp")
    df_sells["cumulative_pnl"] = df_sells["pnl_usd"].astype(float).cumsum()
    df_sells["peak"] = df_sells["cumulative_pnl"].cummax()
    df_sells["drawdown"] = df_sells["peak"] - df_sells["cumulative_pnl"]

    fig_pnl = go.Figure()

    # Fill green/red based on whether cumulative is positive
    fig_pnl.add_trace(go.Scatter(
        x=df_sells["timestamp"], y=df_sells["cumulative_pnl"],
        mode="lines", name="Cumulative P&L",
        line=dict(color=ACCENT, width=2.5),
        fill="tozeroy",
        fillcolor="rgba(0,208,156,0.06)" if total_realized >= 0 else "rgba(255,71,87,0.06)",
        hovertemplate="<b>$%{y:,.2f}</b><br>%{x|%b %d, %H:%M}<extra></extra>",
    ))

    # Peak line
    fig_pnl.add_trace(go.Scatter(
        x=df_sells["timestamp"], y=df_sells["peak"],
        mode="lines", name="High Water Mark",
        line=dict(color="#484F58", width=1, dash="dot"),
        hovertemplate="HWM: $%{y:,.2f}<extra></extra>",
    ))

    # Zero line
    fig_pnl.add_hline(y=0, line_dash="dash", line_color="#30363D", line_width=1)

    fig_pnl.update_layout(**PLOTLY_LAYOUT_HLEGEND, height=380,
                          yaxis_title="Cumulative P&L ($)")
    st.plotly_chart(fig_pnl, use_container_width=True, config={"displayModeBar": False},
                    key="paper_pnl_curve")

st.markdown('<div style="height:12px;"></div>', unsafe_allow_html=True)

# ── Two Column: Chain Performance + Win/Loss Distribution ────────────────────
col_chain, col_dist = st.columns(2)

with col_chain:
    st.markdown("## 🔗 P&L by Chain")
    if sells:
        chain_pnl = {}
        chain_count = {}
        for t in sells:
            c = t.get("chain", "unknown")
            chain_pnl[c] = chain_pnl.get(c, 0) + float(t.get("pnl_usd", 0))
            chain_count[c] = chain_count.get(c, 0) + 1

        chains_sorted = sorted(chain_pnl.items(), key=lambda x: x[1], reverse=True)
        fig_chain = go.Figure()
        fig_chain.add_trace(go.Bar(
            x=[c[0].capitalize() for c in chains_sorted],
            y=[c[1] for c in chains_sorted],
            marker=dict(
                color=[ACCENT if c[1] >= 0 else DANGER for c in chains_sorted],
                line=dict(color="#0A0E14", width=1),
            ),
            text=[f"${c[1]:+.2f}" for c in chains_sorted],
            textposition="outside",
            textfont=dict(size=11, color="#E6EDF3"),
            hovertemplate="<b>%{x}</b><br>P&L: $%{y:,.2f}<extra></extra>",
        ))
        fig_chain.update_layout(**{**PLOTLY_LAYOUT, "showlegend": False}, height=300)
        st.plotly_chart(fig_chain, use_container_width=True,
                        config={"displayModeBar": False}, key="paper_chain_pnl")

with col_dist:
    st.markdown("## 📊 Trade Distribution")
    if sells:
        pnl_values = [float(t.get("pnl_usd", 0)) for t in sells]
        fig_dist = go.Figure()
        fig_dist.add_trace(go.Histogram(
            x=pnl_values, nbinsx=30, name="Trade P&L",
            marker=dict(color=ACCENT, line=dict(color="#0A0E14", width=1)),
            hovertemplate="P&L: $%{x:.2f}<br>Count: %{y}<extra></extra>",
        ))
        fig_dist.add_vline(x=0, line_dash="dash", line_color=DANGER, line_width=1)
        fig_dist.update_layout(**{**PLOTLY_LAYOUT, "showlegend": False}, height=300,
                               xaxis_title="P&L per Trade ($)")
        st.plotly_chart(fig_dist, use_container_width=True,
                        config={"displayModeBar": False}, key="paper_dist")

# ── Drawdown Chart ───────────────────────────────────────────────────────────
if sells and len(sells) > 3:
    st.markdown("## 📉 Drawdown Analysis")
    fig_dd = go.Figure()
    fig_dd.add_trace(go.Scatter(
        x=df_sells["timestamp"], y=-df_sells["drawdown"],
        mode="lines", name="Drawdown",
        line=dict(color=DANGER, width=2),
        fill="tozeroy", fillcolor="rgba(255,71,87,0.08)",
        hovertemplate="Drawdown: -$%{customdata:,.2f}<br>%{x|%b %d, %H:%M}<extra></extra>",
        customdata=df_sells["drawdown"],
    ))
    fig_dd.update_layout(**{**PLOTLY_LAYOUT, "showlegend": False}, height=250,
                         yaxis_title="Drawdown ($)")
    st.plotly_chart(fig_dd, use_container_width=True,
                    config={"displayModeBar": False}, key="paper_drawdown")

# ── Go-Live Readiness ────────────────────────────────────────────────────────
st.markdown('<div style="height:12px;"></div>', unsafe_allow_html=True)
st.markdown("## 🚦 Go-Live Readiness")

checks = []
checks.append(("30+ Closed Trades", total_sells >= 30, f"{total_sells}/30"))
checks.append(("Win Rate ≥ 45%", win_rate >= 45, f"{win_rate:.1f}%"))
checks.append(("Profit Factor ≥ 1.2", profit_factor >= 1.2, f"{profit_factor:.2f}"))
checks.append(("Positive Expectancy", expectancy > 0, f"${expectancy:+.2f}"))
checks.append(("Max DD < $100", max_dd < 100, f"${max_dd:.2f}"))
checks.append(("Net Profitable", total_realized > 0, f"${total_realized:+.2f}"))

passed = sum(1 for _, ok, _ in checks if ok)
all_pass = passed == len(checks)

ready_color = ACCENT if all_pass else (WARNING if passed >= 4 else DANGER)
ready_text = "READY FOR LIVE" if all_pass else f"{passed}/{len(checks)} PASSED"

checks_html = ""
for label, ok, val in checks:
    icon = "✅" if ok else "❌"
    color = ACCENT if ok else DANGER
    checks_html += (
        f'<div style="display:flex;align-items:center;gap:10px;padding:8px 14px;'
        f'background:rgba({"0,208,156" if ok else "255,71,87"},0.04);'
        f'border:1px solid rgba({"0,208,156" if ok else "255,71,87"},0.15);'
        f'border-radius:8px;margin-bottom:4px;">'
        f'<span style="font-size:1rem;">{icon}</span>'
        f'<span style="color:#E6EDF3;font-size:0.82rem;font-weight:600;flex:1;">{label}</span>'
        f'<span style="color:{color};font-size:0.82rem;font-weight:700;'
        f'font-family:JetBrains Mono,monospace;">{val}</span>'
        f'</div>'
    )

rc1, rc2 = st.columns([1, 2])
with rc1:
    st.markdown(
        f'<div class="pnl-kpi" style="text-align:center;padding:24px;">'
        f'<div class="kpi-label">Go-Live Status</div>'
        f'<div style="font-size:2.5rem;margin:8px 0;">{"🟢" if all_pass else "🟡" if passed >= 4 else "🔴"}</div>'
        f'<div style="color:{ready_color};font-size:1rem;font-weight:800;'
        f'letter-spacing:0.06em;">{ready_text}</div>'
        f'<div class="kpi-sub" style="margin-top:8px;">'
        f'{"Switch .env MODE=live when ready" if all_pass else "Keep paper trading to collect more data"}'
        f'</div></div>',
        unsafe_allow_html=True,
    )
with rc2:
    st.markdown(checks_html, unsafe_allow_html=True)

# ── Grok API Usage ───────────────────────────────────────────────────────────
st.markdown('<div style="height:16px;"></div>', unsafe_allow_html=True)
st.markdown("## 🤖 Grok API Usage")

try:
    from data.providers.grok_client import get_usage_stats
    grok = get_usage_stats()

    g1, g2, g3, g4 = st.columns(4)
    with g1:
        st.markdown(_kpi("Total Requests", f"{grok['total_requests']:,}",
                          f"RPM: {grok['requests_last_minute']}/{grok['rpm_limit']}"), unsafe_allow_html=True)
    with g2:
        st.markdown(_kpi("Input Tokens", f"{grok['total_input_tokens']:,}",
                          f"Output: {grok['total_output_tokens']:,}"), unsafe_allow_html=True)
    with g3:
        st.markdown(_kpi("Cached Tokens", f"{grok['total_cached_tokens']:,}",
                          f"Cache hit rate: {grok['cache_hit_rate']}",
                          "green" if float(grok['cache_hit_rate'].rstrip('%')) > 30 else "amber"),
                    unsafe_allow_html=True)
    with g4:
        top_mod = max(grok.get("per_module", {}).items(), key=lambda x: x[1], default=("—", 0))
        st.markdown(_kpi("Top Module", f"{top_mod[0]}",
                          f"{top_mod[1]} calls"), unsafe_allow_html=True)
except Exception:
    st.markdown(
        '<div class="pnl-kpi"><div class="kpi-label">Grok API</div>'
        '<div class="kpi-value" style="font-size:0.9rem;">Stats available after first API call</div></div>',
        unsafe_allow_html=True,
    )

# ── Recent Trades Log ────────────────────────────────────────────────────────
st.markdown('<div style="height:16px;"></div>', unsafe_allow_html=True)
st.markdown("## 📋 Recent Trades")

recent = sorted(trades_raw, key=lambda t: t.get("timestamp", ""), reverse=True)[:50]

if recent:
    for t in recent:
        direction = t.get("direction", "?")
        symbol = t.get("symbol", "???")
        chain = t.get("chain", "?")
        pnl = float(t.get("pnl_usd", 0))
        price = float(t.get("price_usd", 0))
        ts = t.get("timestamp", "")[:16].replace("T", " ")
        reason = t.get("execution_path", t.get("reason", ""))

        dir_icon = "🟢" if direction == "buy" else "🔴"
        dir_color = ACCENT if direction == "buy" else DANGER
        pnl_str = f"${pnl:+.4f}" if direction == "sell" else "—"
        pnl_color = ACCENT if pnl > 0 else (DANGER if pnl < 0 else "#484F58")
        chain_color = CHAIN_COLORS.get(chain, "#8B949E")

        st.markdown(
            f'<div class="trade-row">'
            f'<span style="font-size:1.1rem;">{dir_icon}</span>'
            f'<span style="color:{dir_color};font-size:0.75rem;font-weight:700;'
            f'text-transform:uppercase;width:32px;">{direction}</span>'
            f'<span style="color:#E6EDF3;font-weight:700;font-size:0.88rem;min-width:70px;">{symbol}</span>'
            f'<span style="color:{chain_color};font-size:0.7rem;font-weight:600;'
            f'background:{chain_color}15;padding:2px 8px;border-radius:12px;'
            f'border:1px solid {chain_color}33;">{chain}</span>'
            f'<span style="color:#8B949E;font-size:0.72rem;font-family:JetBrains Mono,monospace;'
            f'flex:1;">${price:,.8f}</span>'
            f'<span style="color:{pnl_color};font-size:0.82rem;font-weight:700;'
            f'font-family:JetBrains Mono,monospace;min-width:80px;text-align:right;">{pnl_str}</span>'
            f'<span style="color:#30363D;font-size:0.65rem;min-width:100px;text-align:right;">{ts}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
else:
    st.info("No trades recorded yet.")

# ── Auto-refresh ─────────────────────────────────────────────────────────────
st.markdown('<div style="height:24px;"></div>', unsafe_allow_html=True)
st.markdown(
    '<div style="text-align:center;color:#30363D;font-size:0.6rem;">'
    'Auto-refreshes every 15 seconds when enabled on sidebar · '
    'Paper trades are simulated — no real capital at risk</div>',
    unsafe_allow_html=True,
)
