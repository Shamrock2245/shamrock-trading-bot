"""
Page 4 — 🏥 System Health

Infrastructure monitoring: bot vitals, API service matrix,
error rate trends, cycle throughput, manual command audit trail,
and live log viewer.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

from styles import PREMIUM_CSS, PLOTLY_LAYOUT, ACCENT, DANGER, WARNING, INFO
from nav import render_nav
from state import get_bot_status, get_scan_history, get_errors, get_pending_manual_commands, STATE_DIR

st.set_page_config(page_title="System Health | Shamrock", page_icon="🏥", layout="wide")
st.markdown(PREMIUM_CSS, unsafe_allow_html=True)
render_nav("Health")

# ── Header ───────────────────────────────────────────────────────────────────
st.markdown(
    '<div style="display:flex;align-items:center;gap:12px;margin-bottom:1.5rem;">'
    '<span style="font-size:2rem;">🏥</span>'
    '<div>'
    '<h1 style="margin:0;padding:0;font-size:1.5rem;font-weight:800;'
    'background:linear-gradient(135deg,#00D09C,#00E6AC);'
    '-webkit-background-clip:text;-webkit-text-fill-color:transparent;">SYSTEM HEALTH</h1>'
    '<span style="color:#8B949E;font-size:0.8rem;">Infrastructure · APIs · Diagnostics</span>'
    '</div></div>',
    unsafe_allow_html=True,
)

status = get_bot_status()
history = get_scan_history()
errors = get_errors()

# ── Top: System Vitals ───────────────────────────────────────────────────────
is_running = status.get("is_running", False)
uptime = status.get("uptime_seconds", 0)
days = uptime // 86400
hours = (uptime % 86400) // 3600
minutes = (uptime % 3600) // 60
uptime_str = f"{days}d {hours}h {minutes}m" if days > 0 else (f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m")
mode = status.get("mode", "unknown").upper()
last_cycle = status.get("last_cycle_at", "")

# Staleness check
stale = False
if last_cycle:
    try:
        lc_dt = datetime.fromisoformat(last_cycle.replace("Z", "+00:00"))
        staleness = (datetime.now(timezone.utc) - lc_dt).total_seconds()
        stale = staleness > 600  # >10 min = stale
    except Exception:
        staleness = 0

status_color = "#00D09C" if is_running and not stale else ("#FFB84D" if is_running else "#FF4757")
status_label = "OPERATIONAL" if is_running and not stale else ("STALE" if is_running else "OFFLINE")
status_icon = "🟢" if is_running and not stale else ("🟡" if is_running else "🔴")

# Calculate error rate from recent history
recent_history = history[-50:] if history else []
error_cycles = sum(1 for h in recent_history if h.get("errors", 0) > 0)
success_rate = ((len(recent_history) - error_cycles) / max(len(recent_history), 1)) * 100

# Avg cycle time
if len(history) >= 2:
    try:
        ts_list = [datetime.fromisoformat(h["timestamp"].replace("Z", "+00:00")) for h in history[-20:]]
        deltas = [(ts_list[i+1] - ts_list[i]).total_seconds() for i in range(len(ts_list)-1)]
        avg_cycle = sum(deltas) / len(deltas)
    except Exception:
        avg_cycle = 0
else:
    avg_cycle = 0

# Big status banner + KPIs
st.markdown(
    f'<div style="display:flex;align-items:center;gap:16px;padding:16px 20px;'
    f'background:rgba(13,17,23,0.6);border:1px solid {status_color}40;border-radius:14px;'
    f'margin-bottom:1rem;">'
    f'<div style="font-size:2.8rem;line-height:1;">{status_icon}</div>'
    f'<div style="flex:1;">'
    f'<div style="color:{status_color};font-size:1.1rem;font-weight:800;letter-spacing:0.06em;">'
    f'{status_label}</div>'
    f'<div style="color:#8B949E;font-size:0.72rem;">Mode: {mode} · Uptime: {uptime_str}</div>'
    f'</div>'
    f'<div style="display:flex;gap:24px;">'
    f'<div style="text-align:center;"><div style="color:#484F58;font-size:0.55rem;font-weight:700;'
    f'text-transform:uppercase;letter-spacing:0.1em;">Cycles</div>'
    f'<div style="color:#E6EDF3;font-size:1.3rem;font-weight:800;'
    f'font-family:\'JetBrains Mono\',monospace;">{status.get("cycle_count",0):,}</div></div>'
    f'<div style="text-align:center;"><div style="color:#484F58;font-size:0.55rem;font-weight:700;'
    f'text-transform:uppercase;letter-spacing:0.1em;">Success</div>'
    f'<div style="color:{"#00D09C" if success_rate >= 90 else "#FFB84D"};font-size:1.3rem;'
    f'font-weight:800;font-family:\'JetBrains Mono\',monospace;">{success_rate:.0f}%</div></div>'
    f'<div style="text-align:center;"><div style="color:#484F58;font-size:0.55rem;font-weight:700;'
    f'text-transform:uppercase;letter-spacing:0.1em;">Avg Cycle</div>'
    f'<div style="color:#58A6FF;font-size:1.3rem;font-weight:800;'
    f'font-family:\'JetBrains Mono\',monospace;">{avg_cycle:.0f}s</div></div>'
    f'<div style="text-align:center;"><div style="color:#484F58;font-size:0.55rem;font-weight:700;'
    f'text-transform:uppercase;letter-spacing:0.1em;">Errors</div>'
    f'<div style="color:{"#FF4757" if len(errors) > 10 else "#00D09C"};font-size:1.3rem;'
    f'font-weight:800;font-family:\'JetBrains Mono\',monospace;">{len(errors)}</div></div>'
    f'</div></div>',
    unsafe_allow_html=True,
)

# ── API Service Matrix ───────────────────────────────────────────────────────
st.markdown("#### 📡 Service Matrix")

recent_errors = errors[-100:] if errors else []
error_sources = {}
for e in recent_errors:
    msg = str(e.get("error", "")).lower()
    for kw, name in [
        ("dexscreener", "DexScreener"), ("coingecko", "CoinGecko"),
        ("goplus", "GoPlus"), ("honeypot", "Honeypot.is"),
        ("1inch", "1inch"), ("oneinch", "1inch"),
        ("tokensniffer", "TokenSniffer"), ("moralis", "Moralis"),
        ("jupiter", "Jupiter"), ("grok", "Grok/X"), ("x.com", "Grok/X"),
    ]:
        if kw in msg:
            error_sources[name] = error_sources.get(name, 0) + 1

apis = [
    ("DexScreener", "Profiles, boosts, pairs"),
    ("Moralis", "Pro discovery + enrichment"),
    ("CoinGecko", "OHLCV, market data"),
    ("GoPlus", "Contract safety"),
    ("Honeypot.is", "Honeypot detection"),
    ("1inch", "EVM DEX routing"),
    ("Jupiter", "Solana DEX swaps"),
    ("Grok/X", "Sentiment analysis"),
    ("TokenSniffer", "Token audits"),
    ("Copy-Trade", "Alpha wallet execution"),
    ("Manual IPC", "Dashboard → Bot commands"),
    ("Position Monitor", "P&L tracking engine"),
]

_api_html = '<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:6px;">'
for name, desc in apis:
    ec = error_sources.get(name, 0)
    if ec == 0:
        _hc, _hi, _hl = "#00D09C", "●", "OK"
    elif ec < 5:
        _hc, _hi, _hl = "#FFB84D", "●", f"{ec} err"
    else:
        _hc, _hi, _hl = "#FF4757", "●", f"{ec} err"

    _api_html += (
        f'<div style="padding:10px 12px;background:rgba(13,17,23,0.5);'
        f'border:1px solid rgba(48,54,61,0.3);border-radius:10px;">'
        f'<div style="display:flex;align-items:center;gap:6px;margin-bottom:2px;">'
        f'<span style="color:{_hc};font-size:0.65rem;">{_hi}</span>'
        f'<span style="color:#E6EDF3;font-size:0.78rem;font-weight:600;">{name}</span></div>'
        f'<div style="color:#484F58;font-size:0.6rem;">{desc}</div>'
        f'</div>'
    )
_api_html += '</div>'
st.markdown(_api_html, unsafe_allow_html=True)

st.markdown('<div style="height:12px;"></div>', unsafe_allow_html=True)

# ── Error Rate + Cycle Throughput Charts ─────────────────────────────────────
r2c1, r2c2 = st.columns(2)

with r2c1:
    st.markdown("#### ⚠️ Error Rate per Cycle")
    if history:
        df_h = pd.DataFrame(history)
        df_h["timestamp"] = pd.to_datetime(df_h["timestamp"])
        fig_err = go.Figure()
        fig_err.add_trace(go.Scatter(
            x=df_h["timestamp"], y=df_h.get("errors", 0),
            mode="lines+markers", line=dict(color=DANGER, width=2),
            marker=dict(size=3), fill="tozeroy", fillcolor="rgba(255,71,87,0.06)",
            hovertemplate="<b>%{y} errors</b><br>%{x|%b %d %H:%M}<extra></extra>",
        ))
        fig_err.update_layout(**{**PLOTLY_LAYOUT, "showlegend": False}, height=260, yaxis_title="Errors")
        st.plotly_chart(fig_err, use_container_width=True, config={"displayModeBar": False}, key="h_err")
    else:
        st.info("Error rate chart appears after scan cycles.")

with r2c2:
    st.markdown("#### 📈 Candidates per Cycle")
    if history:
        fig_cand = go.Figure()
        fig_cand.add_trace(go.Scatter(
            x=df_h["timestamp"], y=df_h["candidates_found"],
            mode="lines", line=dict(color=ACCENT, width=2),
            fill="tozeroy", fillcolor="rgba(0,208,156,0.06)",
            hovertemplate="<b>%{y} candidates</b><br>%{x|%b %d %H:%M}<extra></extra>",
        ))
        fig_cand.update_layout(**{**PLOTLY_LAYOUT, "showlegend": False}, height=260, yaxis_title="Candidates")
        st.plotly_chart(fig_cand, use_container_width=True, config={"displayModeBar": False}, key="h_cand")

# ── Recent Errors ────────────────────────────────────────────────────────────
st.markdown("#### 🔴 Recent Errors")
if errors:
    for err in reversed(errors[-12:]):
        ts_str = err.get("timestamp", "")[:19]
        cycle_n = err.get("cycle", "?")
        err_msg = str(err.get("error", "Unknown"))[:200]
        st.markdown(
            f'<div style="padding:8px 12px;margin:3px 0;border-radius:8px;'
            f'background:rgba(255,71,87,0.04);border-left:3px solid #FF4757;font-size:0.75rem;">'
            f'<div style="display:flex;justify-content:space-between;">'
            f'<span style="color:#8B949E;font-size:0.65rem;">Cycle {cycle_n}</span>'
            f'<span style="color:#484F58;font-size:0.65rem;">{ts_str}</span></div>'
            f'<div style="color:#FF4757;margin-top:2px;">{err_msg}</div></div>',
            unsafe_allow_html=True,
        )
else:
    st.markdown(
        '<div class="glass-card" style="text-align:center;padding:2rem;">'
        '<div style="font-size:1.5rem;">✨</div>'
        '<div style="color:#00D09C;font-weight:600;">Zero Errors</div>'
        '<div style="color:#8B949E;font-size:0.78rem;">System running clean</div></div>',
        unsafe_allow_html=True,
    )

# ── Manual Intervention Log ──────────────────────────────────────────────────
st.markdown('<div style="height:8px;"></div>', unsafe_allow_html=True)
st.markdown("#### 🎮 Manual Commands")

try:
    _cmds_path = os.path.join(STATE_DIR, "manual_commands.json")
    _all_cmds = json.load(open(_cmds_path)) if os.path.exists(_cmds_path) else []
except Exception:
    _all_cmds = []

if _all_cmds:
    rows = []
    for c in reversed(_all_cmds[-30:]):
        status_str = (
            "✅ Executed" if c.get("processed") and c.get("result") == "executed"
            else "⏳ Pending" if not c.get("processed")
            else f"⚠️ {c.get('result','')[:25]}"
        )
        rows.append({
            "Time": c.get("requested_at", "")[:19],
            "Type": c.get("type", "").replace("_", " ").title(),
            "Symbol": c.get("symbol", "?"),
            "Chain": c.get("chain", "").capitalize(),
            "Detail": (
                f"{c.get('sell_pct',100):.0f}%" if "sell" in c.get("type", "")
                else f"${c.get('usd_amount',0):.0f}" if c.get("type") == "manual_buy"
                else ""
            ),
            "Status": status_str,
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
else:
    st.markdown(
        '<div class="glass-card" style="text-align:center;padding:1.5rem;">'
        '<div style="color:#8B949E;font-size:0.85rem;">No manual commands queued</div></div>',
        unsafe_allow_html=True,
    )

# ── Live Logs ────────────────────────────────────────────────────────────────
st.markdown('<div style="height:8px;"></div>', unsafe_allow_html=True)
with st.expander("📄 Live Bot Logs", expanded=False):
    log_path = Path("/app/logs/bot.log")
    if not log_path.exists():
        log_path = Path("./logs/bot.log")

    if log_path.exists():
        num_lines = st.slider("Lines", 20, 200, 50, step=10)
        try:
            lines = log_path.read_text().splitlines()
            st.code("\n".join(lines[-num_lines:]), language="log")
        except Exception as e:
            st.warning(f"Could not read logs: {e}")
    else:
        st.info(f"Log file not found: {log_path}")

# ── System Info ──────────────────────────────────────────────────────────────
with st.expander("🖥️ System Info", expanded=False):
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"**Mode:** `{status.get('mode', 'unknown')}`")
        st.markdown(f"**Started:** `{status.get('started_at', 'N/A')[:19]}`")
        st.markdown(f"**Last Cycle:** `{status.get('last_cycle_at', 'N/A')[:19]}`")
    with c2:
        chains = status.get("chains_scanned", [])
        st.markdown(f"**Chains:** `{', '.join(chains) if chains else 'N/A'}`")
        st.markdown(f"**Cycles:** `{status.get('cycle_count', 0):,}`")
        st.markdown(f"**Uptime:** `{uptime_str}`")
