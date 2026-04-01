"""
Page 4 — 🏥 System Health

Bot uptime, API health monitoring, error tracking,
and live log viewer.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path

from styles import PREMIUM_CSS, PLOTLY_LAYOUT, ACCENT, DANGER, WARNING, INFO
from state import get_bot_status, get_scan_history, get_errors

st.set_page_config(page_title="System Health | Shamrock", page_icon="🏥", layout="wide")
st.markdown(PREMIUM_CSS, unsafe_allow_html=True)

# ── Header ───────────────────────────────────────────────────────────────────
st.markdown(
    '<div style="display:flex;align-items:center;gap:12px;margin-bottom:1.5rem;">'
    '<span style="font-size:2rem;">🏥</span>'
    '<div>'
    '<h1 style="margin:0;padding:0;font-size:1.5rem;font-weight:800;'
    'background:linear-gradient(135deg,#00D09C,#00E6AC);'
    '-webkit-background-clip:text;-webkit-text-fill-color:transparent;">SYSTEM HEALTH</h1>'
    '<span style="color:#8B949E;font-size:0.8rem;">Infrastructure monitoring and diagnostics</span>'
    '</div></div>',
    unsafe_allow_html=True,
)

status = get_bot_status()
history = get_scan_history()
errors = get_errors()

# ── Status Overview ──────────────────────────────────────────────────────────
col1, col2, col3, col4 = st.columns(4)

with col1:
    is_running = status.get("is_running", False)
    if is_running:
        st.markdown(
            '<div style="text-align:center;">'
            '<div style="font-size:2.5rem;margin-bottom:0.25rem;">🟢</div>'
            '<div style="color:#00D09C;font-weight:700;font-size:1.1rem;">HEALTHY</div>'
            '<div style="color:#8B949E;font-size:0.78rem;">All systems operational</div>'
            '</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div style="text-align:center;">'
            '<div style="font-size:2.5rem;margin-bottom:0.25rem;">🔴</div>'
            '<div style="color:#FF4757;font-weight:700;font-size:1.1rem;">OFFLINE</div>'
            '<div style="color:#8B949E;font-size:0.78rem;">Bot is not running</div>'
            '</div>',
            unsafe_allow_html=True,
        )

with col2:
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
    st.metric("Uptime", uptime_str)

with col3:
    st.metric("Total Cycles", f"{status.get('cycle_count', 0):,}")

with col4:
    mode = status.get("mode", "unknown").upper()
    mode_emoji = "🟢" if mode == "PAPER" else "🔴"
    st.metric("Mode", f"{mode_emoji} {mode}")

st.markdown("<div style='height:24px;'></div>", unsafe_allow_html=True)

# ── API Health Grid ──────────────────────────────────────────────────────────
st.markdown("## 📡 API Health Status")

# Calculate health from recent errors
recent_errors = errors[-50:] if errors else []
error_sources = {}
for e in recent_errors:
    msg = str(e.get("error", ""))
    if "dexscreener" in msg.lower():
        error_sources["DexScreener"] = error_sources.get("DexScreener", 0) + 1
    elif "coingecko" in msg.lower():
        error_sources["CoinGecko"] = error_sources.get("CoinGecko", 0) + 1
    elif "goplus" in msg.lower():
        error_sources["GoPlus"] = error_sources.get("GoPlus", 0) + 1
    elif "honeypot" in msg.lower():
        error_sources["Honeypot.is"] = error_sources.get("Honeypot.is", 0) + 1
    elif "1inch" in msg.lower() or "oneinch" in msg.lower():
        error_sources["1inch"] = error_sources.get("1inch", 0) + 1
    elif "tokensniffer" in msg.lower():
        error_sources["TokenSniffer"] = error_sources.get("TokenSniffer", 0) + 1
    elif "moralis" in msg.lower():
        error_sources["Moralis"] = error_sources.get("Moralis", 0) + 1
    elif "jupiter" in msg.lower():
        error_sources["Jupiter"] = error_sources.get("Jupiter", 0) + 1
    elif "grok" in msg.lower() or "x.com" in msg.lower():
        error_sources["Grok/X"] = error_sources.get("Grok/X", 0) + 1

apis = [
    ("DexScreener", "Token profiles, boosts, pair data", "dexscreener.com"),
    ("Moralis Money", "Pro discovery + enrichment (10 endpoints)", "moralis.io"),
    ("Moralis Streams", "Real-time push webhooks — Codex addition", "moralis.io"),
    ("CoinGecko", "OHLCV data, market data", "coingecko.com"),
    ("GoPlus", "Contract safety analysis", "gopluslabs.io"),
    ("Honeypot.is", "Honeypot detection", "honeypot.is"),
    ("1inch", "DEX aggregation & routing (EVM)", "1inch.dev"),
    ("Jupiter", "Solana DEX aggregation & swap", "jup.ag"),
    ("Grok/X", "Sentiment analysis via X API", "x.com"),
    ("TokenSniffer", "Token audits & scores", "tokensniffer.com"),
    ("Copy-Trade Fastlane", "Alpha wallet copy-trade execution", "internal"),
    ("Manual Intervention IPC", "Dashboard → bot command pipeline", "internal"),
]

api_cols = st.columns(3)
for i, (name, desc, domain) in enumerate(apis):
    with api_cols[i % 3]:
        error_count = error_sources.get(name, 0)
        if error_count == 0:
            health_color = "#00D09C"
            health_icon = "🟢"
            health_label = "Healthy"
        elif error_count < 5:
            health_color = "#FFB84D"
            health_icon = "🟡"
            health_label = f"{error_count} errors"
        else:
            health_color = "#FF4757"
            health_icon = "🔴"
            health_label = f"{error_count} errors"

        st.markdown(
            f'<div class="glass-card" style="margin-bottom:12px;">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;">'
            f'<div>'
            f'<div style="font-weight:600;color:#E6EDF3;font-size:0.95rem;">{name}</div>'
            f'<div style="color:#8B949E;font-size:0.78rem;">{desc}</div>'
            f'</div>'
            f'<div style="text-align:right;">'
            f'<span style="font-size:1.2rem;">{health_icon}</span>'
            f'<div style="color:{health_color};font-size:0.75rem;font-weight:600;">{health_label}</div>'
            f'</div>'
            f'</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

# ── Error Rate Over Time ────────────────────────────────────────────────────
st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)
st.markdown("## ⚠️ Error Tracking")

error_col1, error_col2 = st.columns([2, 1])

with error_col1:
    if history:
        df_hist = pd.DataFrame(history)
        df_hist["timestamp"] = pd.to_datetime(df_hist["timestamp"])

        fig_errors = go.Figure()

        if "errors" in df_hist.columns:
            fig_errors.add_trace(go.Scatter(
                x=df_hist["timestamp"],
                y=df_hist["errors"],
                mode="lines+markers",
                name="Errors per cycle",
                line=dict(color=DANGER, width=2),
                marker=dict(size=4, color=DANGER),
                fill="tozeroy",
                fillcolor="rgba(255, 71, 87, 0.06)",
                hovertemplate="<b>%{y} errors</b><br>%{x|%H:%M:%S}<extra></extra>",
            ))

        fig_errors.update_layout(
            **{**PLOTLY_LAYOUT, "showlegend": False},
            height=280,
            yaxis_title="Errors",
        )
        st.plotly_chart(fig_errors, use_container_width=True, config={"displayModeBar": False})
    else:
        st.markdown(
            '<div class="glass-card" style="text-align:center;padding:2rem;">'
            '<div style="color:#8B949E;">No scan history yet</div></div>',
            unsafe_allow_html=True,
        )

with error_col2:
    st.markdown("### Recent Errors")
    if errors:
        for err in reversed(errors[-8:]):
            st.markdown(
                f'<div style="padding:8px 12px;margin:4px 0;border-radius:8px;'
                f'background:rgba(255,71,87,0.06);border-left:3px solid #FF4757;'
                f'font-size:0.78rem;">'
                f'<div style="color:#8B949E;font-size:0.7rem;">'
                f'{err.get("timestamp", "")[:19]} • Cycle {err.get("cycle", "?")}</div>'
                f'<div style="color:#FF4757;margin-top:2px;">'
                f'{str(err.get("error", "Unknown"))[:120]}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
    else:
        st.markdown(
            '<div class="glass-card" style="text-align:center;padding:2rem;">'
            '<div style="font-size:1.5rem;">✨</div>'
            '<div style="color:#00D09C;font-weight:600;font-size:0.9rem;">Zero Errors</div>'
            '<div style="color:#8B949E;font-size:0.78rem;">System running clean</div>'
            '</div>',
            unsafe_allow_html=True,
        )

# ── Manual Intervention Log ─────────────────────────────────────────────────────────────────────────────
st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)
st.markdown("## 🎮 Manual Intervention Log")

try:
    from state import get_pending_manual_commands, STATE_DIR
    import os
    _all_cmds_path = os.path.join(STATE_DIR, "manual_commands.json")
    import json as _json_h
    if os.path.exists(_all_cmds_path):
        with open(_all_cmds_path) as _f:
            _all_cmds = _json_h.load(_f)
    else:
        _all_cmds = []
except Exception:
    _all_cmds = []

if _all_cmds:
    mi_col1, mi_col2 = st.columns([3, 1])
    with mi_col1:
        mi_rows = []
        for _c in reversed(_all_cmds[-50:]):
            mi_rows.append({
                "Time": _c.get("requested_at", "")[:19],
                "Type": _c.get("type", "").upper().replace("_", " "),
                "Symbol": _c.get("symbol", "?"),
                "Chain": _c.get("chain", "").capitalize(),
                "Detail": (
                    f"{_c.get('sell_pct',100):.0f}%" if _c.get("type") in ("manual_sell","manual_close")
                    else f"${_c.get('usd_amount',0):.2f}" if _c.get("type") == "manual_buy"
                    else ""
                ),
                "Wallet": _c.get("wallet", ""),
                "Reason": _c.get("reason", ""),
                "Status": (
                    "✅ Done" if _c.get("processed") and _c.get("result") == "executed"
                    else "⏳ Pending" if not _c.get("processed")
                    else f"⚠️ {_c.get('result','')[:30]}"
                ),
            })
        import pandas as _pd_mi
        st.dataframe(_pd_mi.DataFrame(mi_rows), use_container_width=True, hide_index=True)
    with mi_col2:
        pending_n = len([c for c in _all_cmds if not c.get("processed")])
        done_n = len([c for c in _all_cmds if c.get("processed") and c.get("result") == "executed"])
        st.metric("Pending", pending_n)
        st.metric("Executed", done_n)
else:
    st.markdown(
        '<div class="glass-card" style="text-align:center;padding:1.5rem;">'
        '<div style="color:#8B949E;font-size:0.85rem;">No manual commands yet</div>'
        '<div style="color:#484F58;font-size:0.72rem;margin-top:4px;">'
        'Use the Positions or Gem Scanner pages to queue buy/sell commands</div>'
        '</div>',
        unsafe_allow_html=True,
    )

# ── Log Viewer ─────────────────────────────────────────────────────────────────────────────
st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)
st.markdown("## 📄 Live Logs")

log_path = Path("/app/logs/bot.log")
# Fallback for local development
if not log_path.exists():
    log_path = Path("./logs/bot.log")

if log_path.exists():
    num_lines = st.slider("Lines to show", 10, 200, 50, step=10)
    try:
        with open(log_path, "r") as f:
            lines = f.readlines()
        recent_lines = lines[-num_lines:]

        log_text = "".join(recent_lines)
        st.code(log_text, language="log")
    except Exception as e:
        st.warning(f"Could not read log file: {e}")
else:
    st.markdown(
        '<div class="glass-card" style="text-align:center;padding:2rem;">'
        '<div style="color:#8B949E;">Log file not found at expected path</div>'
        '<div style="color:#484F58;font-size:0.78rem;margin-top:4px;">'
        f'Expected: {log_path}</div>'
        '</div>',
        unsafe_allow_html=True,
    )

# ── System Info ──────────────────────────────────────────────────────────────
st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)

with st.expander("🖥️ System Info", expanded=False):
    info_col1, info_col2 = st.columns(2)

    with info_col1:
        st.markdown(f"**Mode:** `{status.get('mode', 'unknown')}`")
        st.markdown(f"**Started:** `{status.get('started_at', 'N/A')[:19]}`")
        st.markdown(f"**Last Cycle:** `{status.get('last_cycle_at', 'N/A')[:19]}`")

    with info_col2:
        chains = status.get("chains_scanned", [])
        st.markdown(f"**Chains:** `{', '.join(chains) if chains else 'N/A'}`")
        st.markdown(f"**Cycles:** `{status.get('cycle_count', 0):,}`")
        st.markdown(f"**Uptime:** `{uptime_str}`")
