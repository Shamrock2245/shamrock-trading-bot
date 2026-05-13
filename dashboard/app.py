"""
dashboard/app.py — ☘️ Shamrock Trading Bot — Command Center v4.5

Fortune 50-grade dark-mode dashboard.
Navigation card grid · Force Scan IPC · Daily Floor Guardian status ·
Blue-Chip Anchor status · Full Moralis intelligence display.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import time as _time
from datetime import datetime, timezone

from styles import (
    PREMIUM_CSS, PLOTLY_LAYOUT, ACCENT, CHAIN_COLORS, CHAIN_EMOJI,
    DANGER, WARNING,
)
from nav import render_nav
from state import (
    get_bot_status,
    get_scan_history,
    get_latest_gems,
    get_gem_history,
    get_trades,
    get_positions,
    get_errors,
    request_force_scan,
    get_force_scan_request,
    get_pending_manual_commands,
    request_manual_sell,
    request_manual_close,
    request_manual_buy,
)

# ─────────────────────────────────────────────────────────────────────────────
# Page Config
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Shamrock | Command Center",
    page_icon="☘️",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(PREMIUM_CSS, unsafe_allow_html=True)
render_nav("Command Center")

# ── Brand-specific CSS additions ──────────────────────────────────────────────
st.markdown("""
<style>
/* ── Navigation Cards ─────────────────────────────────────────────────────── */
.nav-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin-bottom: 24px; }
.nav-card {
    background: linear-gradient(145deg, rgba(13,17,23,0.98), rgba(22,27,34,0.95));
    border: 1px solid rgba(48,54,61,0.7);
    border-radius: 14px;
    padding: 18px 14px 14px;
    text-align: center;
    text-decoration: none !important;
    display: block;
    transition: all 0.22s cubic-bezier(.4,0,.2,1);
    position: relative;
    overflow: hidden;
}
.nav-card::before {
    content: '';
    position: absolute; inset: 0;
    background: linear-gradient(135deg, rgba(0,208,156,0.04), transparent);
    opacity: 0; transition: opacity 0.22s;
}
.nav-card:hover { border-color: rgba(0,208,156,0.45); transform: translateY(-3px);
    box-shadow: 0 8px 32px rgba(0,208,156,0.10); }
.nav-card:hover::before { opacity: 1; }
.nav-icon { font-size: 1.9rem; margin-bottom: 8px; display: block; }
.nav-title {
    color: #E6EDF3; font-size: 0.78rem; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.09em; margin-bottom: 5px;
}
.nav-desc { color: #484F58; font-size: 0.68rem; line-height: 1.45; }
.nav-badge {
    position: absolute; top: 9px; right: 9px;
    background: rgba(0,208,156,0.15); color: #00D09C;
    border-radius: 20px; padding: 2px 7px;
    font-size: 0.62rem; font-weight: 700; letter-spacing: 0.04em;
}
/* ── Floor/Anchor Status Cards ────────────────────────────────────────────── */
.guardian-card {
    background: linear-gradient(145deg, rgba(13,17,23,0.98), rgba(22,27,34,0.95));
    border: 1px solid rgba(48,54,61,0.7);
    border-radius: 14px;
    padding: 16px 18px;
    position: relative;
    overflow: hidden;
}
.guardian-card.preservation {
    border-color: rgba(255,71,87,0.5);
    background: linear-gradient(145deg, rgba(255,71,87,0.05), rgba(13,17,23,0.98));
}
.guardian-card.healthy {
    border-color: rgba(0,208,156,0.3);
    background: linear-gradient(145deg, rgba(0,208,156,0.04), rgba(13,17,23,0.98));
}
.guardian-label {
    color: #484F58; font-size: 0.62rem; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 6px;
}
.guardian-value {
    color: #E6EDF3; font-size: 1.25rem; font-weight: 700;
    font-family: 'JetBrains Mono', monospace; margin-bottom: 3px;
}
.guardian-sub { color: #8B949E; font-size: 0.72rem; }
/* ── Force Scan Button ────────────────────────────────────────────────────── */
.scan-pending-pill {
    background: rgba(255,184,77,0.12);
    border: 1px solid rgba(255,184,77,0.3);
    border-radius: 20px; padding: 6px 12px;
    color: #FFB84D; font-size: 0.72rem; font-weight: 600;
    text-align: center; margin-top: 6px;
}
/* ── Sidebar meta ─────────────────────────────────────────────────────────── */
.sidebar-stat-row { display: flex; flex-direction: column; gap: 10px; }
.sidebar-stat { }
.sidebar-stat-label {
    color: #30363D; font-size: 0.6rem; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.09em;
}
.sidebar-stat-value {
    color: #E6EDF3; font-size: 0.92rem; font-weight: 600;
    font-family: 'JetBrains Mono', monospace;
}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    # Brand header
    st.markdown(
        '<div style="display:flex;align-items:center;gap:10px;padding:4px 0 12px;">'
        '<span style="font-size:1.6rem;">☘️</span>'
        '<div>'
        '<div style="color:#E6EDF3;font-size:1.05rem;font-weight:800;letter-spacing:0.04em;">SHAMROCK</div>'
        '<div style="color:#30363D;font-size:0.65rem;font-weight:600;letter-spacing:0.08em;'
        'text-transform:uppercase;">Multi-Chain AI Trading Engine</div>'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )
    st.markdown('<hr style="border-color:rgba(48,54,61,0.5);margin:0 0 14px;">', unsafe_allow_html=True)

    # Bot status badge
    @st.cache_data(ttl=15)
    def _get_status():
        return get_bot_status()
    status = _get_status()
    mode = status.get("mode", "unknown").upper()
    is_running = status.get("is_running", False)

    if is_running:
        st.markdown(
            f'<div style="display:flex;align-items:center;gap:7px;padding:6px 10px;'
            f'background:rgba(0,208,156,0.06);border:1px solid rgba(0,208,156,0.2);'
            f'border-radius:8px;">'
            f'<span class="pulse-dot" style="background:#00D09C;"></span>'
            f'<span style="color:#00D09C;font-weight:700;font-size:0.78rem;">'
            f'RUNNING · {mode}</span></div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div style="display:flex;align-items:center;gap:7px;padding:6px 10px;'
            'background:rgba(255,71,87,0.06);border:1px solid rgba(255,71,87,0.2);'
            'border-radius:8px;">'
            '<span class="pulse-dot" style="background:#FF4757;"></span>'
            '<span style="color:#FF4757;font-weight:700;font-size:0.78rem;">OFFLINE</span>'
            '</div>',
            unsafe_allow_html=True,
        )

    st.markdown('<div class="section-label" style="margin-top:14px;">Controls</div>',
                unsafe_allow_html=True)

    pending = get_force_scan_request()
    if pending:
        st.markdown(
            '<div class="scan-pending-pill">⏳ Scan queued — picks up next cycle</div>',
            unsafe_allow_html=True,
        )
    else:
        if st.button("⚡ Force scan", key="sb_force_scan", use_container_width=True,
                      help="Trigger an immediate gem scan"):
            request_force_scan(reason="sidebar_button")
            st.toast("Scan request sent!", icon="✅")
            st.rerun()

    # Pending manual commands
    _pending_cmds = get_pending_manual_commands()
    if _pending_cmds:
        st.markdown(
            f'<div style="background:rgba(255,184,77,0.06);border:1px solid rgba(255,184,77,0.2);'
            f'border-radius:8px;padding:7px 10px;margin-top:8px;">'
            f'<div style="color:#FFB84D;font-size:0.68rem;font-weight:700;margin-bottom:4px;">'
            f'🎮 {len(_pending_cmds)} command(s) queued</div>'
            + "".join(
                f'<div style="color:#8B949E;font-size:0.62rem;padding:1px 0;">'
                f'• {c.get("type","").upper().replace("_"," ")}: '
                f'<b style="color:#E6EDF3;">{c.get("symbol","?")}</b>'
                f' on {c.get("chain","?")}</div>'
                for c in _pending_cmds[:5]
            )
            + '</div>',
            unsafe_allow_html=True,
        )

    # Active chains
    chains = status.get("chains_scanned", [])
    if chains:
        st.markdown('<div class="section-label">Chains</div>', unsafe_allow_html=True)
        chain_pills = " ".join(
            f'<span class="info-pill" style="border-color:{CHAIN_COLORS.get(c,"#484F58")}44;">'
            f'{CHAIN_EMOJI.get(c,"⬡")} {c[:3].upper()}</span>'
            for c in chains
        )
        st.markdown(f'<div style="display:flex;gap:4px;flex-wrap:wrap;">{chain_pills}</div>',
                    unsafe_allow_html=True)

    # Uptime + cycles — native metrics
    uptime = status.get("uptime_seconds", 0)
    days = uptime // 86400
    hours = (uptime % 86400) // 3600
    minutes = (uptime % 3600) // 60
    uptime_str = (
        f"{days}d {hours}h {minutes}m" if days > 0
        else f"{hours}h {minutes}m" if hours > 0
        else f"{minutes}m"
    )
    cycle = status.get("cycle_count", 0)

    st.markdown('<div class="section-label">Runtime</div>', unsafe_allow_html=True)
    _sb1, _sb2 = st.columns(2)
    with _sb1:
        st.metric("Uptime", uptime_str, border=True)
    with _sb2:
        st.metric("Cycles", f"{cycle:,}", border=True)

    last_cycle = status.get("last_cycle_at", "")
    if last_cycle:
        try:
            dt = datetime.fromisoformat(last_cycle.replace("Z", "+00:00"))
            ago = (datetime.now(timezone.utc) - dt).total_seconds()
            ago_str = (
                f"{int(ago)}s ago" if ago < 120
                else f"{int(ago/60)}m ago" if ago < 7200
                else f"{int(ago/3600)}h ago"
            )
            st.caption(f"Last scan: {ago_str}")
        except (ValueError, TypeError):
            pass

    st.markdown('<div class="section-label">Refresh</div>', unsafe_allow_html=True)
    auto_refresh = st.toggle("Auto-refresh", value=True)
    refresh_rate = st.select_slider(
        "Interval", options=[5, 10, 15, 30, 60], value=15,
        format_func=lambda x: f"{x}s",
    )

    st.caption("v4.5 · Moralis Intelligence Suite")

# ─────────────────────────────────────────────────────────────────────────────
# Main Content
# ─────────────────────────────────────────────────────────────────────────────
# Mode badge for header
_mode_badge = (
    f'<span style="margin-left:auto;display:inline-flex;align-items:center;gap:6px;'
    f'background:rgba(0,208,156,0.06);border:1px solid rgba(0,208,156,0.2);'
    f'border-radius:20px;padding:4px 14px;font-size:0.72rem;font-weight:700;'
    f'color:#00D09C;text-transform:uppercase;letter-spacing:0.08em;">'
    f'<span class="pulse-dot" style="background:#00D09C;width:6px;height:6px;"></span>'
    f'{mode}</span>'
) if is_running else ''

st.markdown(
    '<div style="display:flex;align-items:center;gap:12px;margin-bottom:0.5rem;">'
    '<span style="font-size:2rem;">☘️</span>'
    '<div>'
    '<h1 style="margin:0;padding:0;font-size:1.6rem;font-weight:800;'
    'background:linear-gradient(135deg,#00D09C,#00E6AC);'
    '-webkit-background-clip:text;-webkit-text-fill-color:transparent;">'
    'Command center</h1>'
    '<span style="color:#484F58;font-size:0.75rem;">'
    'Moralis Intelligence · Cortex AI · Copy-Trade · Sniper Defense</span>'
    '</div>'
    f'{_mode_badge}'
    '</div>',
    unsafe_allow_html=True,
)

# ── Data Loading (cached — Streamlit performance optimization) ───────────────
# Using @st.cache_data(ttl=15) so data refreshes every 15s but widget
# interactions don't trigger expensive re-reads of every JSON file.
import json as _json

@st.cache_data(ttl=15)
def _cached_bot_status():
    return get_bot_status()

@st.cache_data(ttl=15)
def _cached_scan_history():
    return get_scan_history()

@st.cache_data(ttl=15)
def _cached_gem_history():
    return get_gem_history()

@st.cache_data(ttl=15)
def _cached_trades():
    return get_trades()

@st.cache_data(ttl=15)
def _cached_positions():
    return get_positions()

@st.cache_data(ttl=15)
def _cached_latest_gems():
    return get_latest_gems()

history = _cached_scan_history()
gems = _cached_gem_history()
trades_data = _cached_trades()
positions_data = _cached_positions()
latest_gems = _cached_latest_gems()

# Load extra state files
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

@st.cache_data(ttl=15)
def _load_json(path, default=None):
    try:
        full = os.path.join(_BASE, path)
        if os.path.exists(full):
            return _json.loads(open(full).read())
    except Exception:
        pass
    return default or {}

adaptive_state   = _load_json("output/adaptive_mode_state.json")
offensive_state  = _load_json("output/offensive_state.json")
rebalance_state  = _load_json("output/rebalance_state.json")
watchlist_data   = _load_json("output/watchlist.json", default=[])
if isinstance(watchlist_data, dict):
    watchlist_data = list(watchlist_data.values())

# Load rebalance plans for all wallets/chains
_rebalance_plans = {}
for _wc in ["primary_base", "primary_bsc", "primary_ethereum", "primary_solana",
            "wallet_b_base", "wallet_b_bsc", "wallet_b_arbitrum", "wallet_b_ethereum"]:
    _plan = _load_json(f"output/rebalance_plan_{_wc}.json")
    if _plan:
        _rebalance_plans[_wc] = _plan

active_positions = len([p for p in positions_data if p.get("status") == "open" or p.get("is_open", False)])
realized_pnl = sum(t.get("pnl_usd", 0) for t in trades_data)
total_trades = len(trades_data)
sells = [t for t in trades_data if t.get("action", "").upper() == "SELL" or t.get("direction") == "sell"]
wins = [t for t in sells if t.get("pnl_usd", 0) > 0]
win_rate = (len(wins) / max(len(sells), 1)) * 100

# Derived counts for nav badges & KPI row
latest_count = len(history[-1].get("candidates", [])) if history and isinstance(history[-1], dict) else len(gems)
express_count = sum(1 for g in gems if g.get("express_lane", False))

# ── Guardian + Anchor Status (read from output files) ─────────────────────────
guardian_status = {}
anchor_status = {}
try:
    import json as _json
    _gf = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output", "daily_floor.json")
    if os.path.exists(_gf):
        guardian_status = _json.loads(open(_gf).read())
except Exception:
    pass
try:
    import json as _json2
    _af = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output", "bluechip_anchor.json")
    if os.path.exists(_af):
        anchor_status = _json2.loads(open(_af).read())
except Exception:
    pass

# ── P&L Hero ──────────────────────────────────────────────────────────────────
pnl_class = "positive" if realized_pnl > 0 else ("negative" if realized_pnl < 0 else "zero")
pnl_sign = "+" if realized_pnl > 0 else ""
pnl_subtitle = (
    f"{total_trades} trades · {win_rate:.0f}% win rate"
    if total_trades > 0 else "Awaiting first trade"
)

# Calculate unrealized P&L from open positions
_open_pos = [p for p in positions_data if p.get("status") == "open" or p.get("is_open", False)]
_unr_pnl_pct = (
    sum(float(p.get("unrealized_pnl_pct", 0)) for p in _open_pos) / max(len(_open_pos), 1)
) if _open_pos else 0
_unr_sign = "+" if _unr_pnl_pct >= 0 else ""
_unr_color = "#00D09C" if _unr_pnl_pct >= 0 else "#FF4757"

_unr_html = ""
if _open_pos:
    _unr_html = (
        f'<div style="display:flex;justify-content:center;gap:28px;margin-top:12px;'
        f'padding-top:12px;border-top:1px solid rgba(48,54,61,0.3);">'
        f'<div style="text-align:center;">'
        f'<div style="color:#484F58;font-size:0.58rem;font-weight:700;'
        f'text-transform:uppercase;letter-spacing:0.1em;">Unrealized Avg</div>'
        f'<div style="color:{_unr_color};font-size:1.05rem;font-weight:700;'
        f'font-family:JetBrains Mono,monospace;">{_unr_sign}{_unr_pnl_pct:.1f}%</div>'
        f'</div>'
        f'<div style="text-align:center;">'
        f'<div style="color:#484F58;font-size:0.58rem;font-weight:700;'
        f'text-transform:uppercase;letter-spacing:0.1em;">Open</div>'
        f'<div style="color:#E6EDF3;font-size:1.05rem;font-weight:700;'
        f'font-family:JetBrains Mono,monospace;">{len(_open_pos)}</div>'
        f'</div></div>'
    )

_hc1, _hc2, _hc3 = st.columns([1, 2, 1])
with _hc2:
    st.markdown(
        f'<div class="pnl-hero">'
        f'<div class="pnl-label">Realized P&L</div>'
        f'<div class="pnl-value {pnl_class}">{pnl_sign}${abs(realized_pnl):,.2f}</div>'
        f'<div class="pnl-subtitle">{pnl_subtitle}</div>'
        f'{_unr_html}'
        f'</div>',
        unsafe_allow_html=True,
    )

st.markdown('<div style="height:12px;"></div>', unsafe_allow_html=True)

# ── Guardian + Anchor Status Row ──────────────────────────────────────────────
if guardian_status or anchor_status:
    ga_col1, ga_col2, ga_col3, ga_col4 = st.columns(4)

    with ga_col1:
        floor_usd = guardian_status.get("floor_usd", 0)
        current_usd = guardian_status.get("current_portfolio_usd", 0)
        is_pres = guardian_status.get("is_preservation_mode", False)
        daily_gain_pct = guardian_status.get("daily_gain_pct", 0)
        card_class = "preservation" if is_pres else "healthy"
        status_icon = "🛡️ PRESERVATION" if is_pres else "✅ HEALTHY"
        status_color = DANGER if is_pres else ACCENT
        st.markdown(
            f'<div class="guardian-card {card_class}">'
            f'<div class="guardian-label">Daily Floor Guardian</div>'
            f'<div class="guardian-value">${floor_usd:,.2f}</div>'
            f'<div class="guardian-sub">Floor · Current: ${current_usd:,.2f}</div>'
            f'<div style="margin-top:6px;font-size:0.7rem;font-weight:700;color:{status_color};">'
            f'{status_icon}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    with ga_col2:
        daily_gain = guardian_status.get("daily_gain_usd", 0)
        peak = guardian_status.get("peak_usd_today", 0)
        gain_class = "positive" if daily_gain >= 0 else "negative"
        gain_sign = "+" if daily_gain >= 0 else ""
        st.markdown(
            f'<div class="guardian-card healthy">'
            f'<div class="guardian-label">24h P&L vs Floor</div>'
            f'<div class="guardian-value {gain_class}">{gain_sign}${abs(daily_gain):,.2f}</div>'
            f'<div class="guardian-sub">{gain_sign}{daily_gain_pct:+.2f}% · Peak: ${peak:,.2f}</div>'
            f'<div style="margin-top:6px;font-size:0.7rem;color:#484F58;">'
            f'Floor date: {guardian_status.get("floor_date", "—")}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    with ga_col3:
        anchor_sym = anchor_status.get("anchor_symbol", "ETH")
        anchor_usd = anchor_status.get("anchor_current_usd", 0)
        anchor_pct = anchor_status.get("anchor_current_pct", 0)
        anchor_target = anchor_status.get("anchor_target_pct", 20)
        scores = anchor_status.get("last_scores", {})
        best_score = max(scores.values()) if scores else 0
        st.markdown(
            f'<div class="guardian-card healthy">'
            f'<div class="guardian-label">Blue-Chip Anchor</div>'
            f'<div class="guardian-value">⚓ {anchor_sym}</div>'
            f'<div class="guardian-sub">${anchor_usd:,.2f} · {anchor_pct:.1f}% of portfolio</div>'
            f'<div style="margin-top:6px;font-size:0.7rem;color:#484F58;">'
            f'Target: {anchor_target:.0f}% · Momentum: {best_score:.0f}/100</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    with ga_col4:
        rebalances = anchor_status.get("rebalance_count", 0)
        switches = anchor_status.get("switches", 0)
        last_rb = anchor_status.get("last_rebalance_at", "")
        last_rb_str = last_rb[:10] if last_rb else "Never"
        scores_html = ""
        if scores:
            for sym, sc in sorted(scores.items(), key=lambda x: -x[1])[:4]:
                bar_w = int(sc)
                color = ACCENT if sc >= 60 else (WARNING if sc >= 40 else DANGER)
                scores_html += (
                    f'<div style="display:flex;align-items:center;gap:6px;margin-bottom:3px;">'
                    f'<span style="color:#8B949E;font-size:0.65rem;width:32px;">{sym}</span>'
                    f'<div style="flex:1;height:4px;background:rgba(48,54,61,0.5);border-radius:2px;">'
                    f'<div style="width:{bar_w}%;height:100%;background:{color};border-radius:2px;"></div>'
                    f'</div>'
                    f'<span style="color:{color};font-size:0.62rem;width:24px;text-align:right;">{sc:.0f}</span>'
                    f'</div>'
                )
        st.markdown(
            f'<div class="guardian-card healthy">'
            f'<div class="guardian-label">Anchor Momentum Scores</div>'
            f'{scores_html if scores_html else "<div class=guardian-sub>Awaiting first evaluation</div>"}'
            f'<div style="margin-top:6px;font-size:0.65rem;color:#30363D;">'
            f'Rebalances: {rebalances} · Switches: {switches} · Last: {last_rb_str}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.markdown('<div style="height:16px;"></div>', unsafe_allow_html=True)

# ── Quick Nav (compact pill bar) ─────────────────────────────────────────────
_nav_links = [
    ("🔍 Scanner", "/Gem_Scanner", latest_count),
    ("💰 Positions", "/Positions", active_positions),
    ("📊 Analytics", "/Analytics", 0),
    ("🏥 Health", "/System_Health", 0),
    ("👛 Wallets", "/Wallet_Overview", 0),
    ("🤝 Alpha", "/Alpha_Wallets", 0),
    ("🎯 Sniper", "/Sniper_Wallets", 0),
]
_nav_html = '<div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:16px;">'
for _label, _href, _count in _nav_links:
    _badge = (f'<span style="background:rgba(0,208,156,0.15);color:#00D09C;'
              f'font-size:0.6rem;font-weight:800;padding:1px 6px;border-radius:8px;'
              f'margin-left:5px;">{_count}</span>') if _count > 0 else ""
    _nav_html += (
        f'<a href="{_href}" target="_self" style="text-decoration:none;display:inline-flex;'
        f'align-items:center;gap:3px;background:rgba(255,255,255,0.03);'
        f'border:1px solid rgba(48,54,61,0.5);border-radius:20px;padding:5px 14px;'
        f'color:#8B949E;font-size:0.72rem;font-weight:600;transition:all 0.2s;">'
        f'{_label}{_badge}</a>'
    )
_nav_html += '</div>'
st.markdown(_nav_html, unsafe_allow_html=True)

# ── Live Data Panels (replaced nav cards) ────────────────────────────────────
_dp_left, _dp_right = st.columns([3, 2])

with _dp_left:
    # ── Open Positions Table ─────────────────────────────────────────────────
    st.markdown(
        '<div style="color:#484F58;font-size:0.62rem;font-weight:700;text-transform:uppercase;'
        'letter-spacing:0.12em;margin-bottom:8px;">Open positions</div>',
        unsafe_allow_html=True,
    )
    _open = [p for p in positions_data if p.get("status") == "open" or p.get("is_open", False)]
    if _open:
        _rows_html = ""
        for _p in sorted(_open, key=lambda x: float(x.get("unrealized_pnl_pct", 0)), reverse=True)[:8]:
            _sym = _p.get("symbol", "???")
            _chain = _p.get("chain", "?")
            _entry = float(_p.get("entry_price", 0))
            _curr = float(_p.get("current_price", _entry))
            _pnl_pct = float(_p.get("unrealized_pnl_pct", 0))
            _pnl_color = "#00D09C" if _pnl_pct >= 0 else "#FF4757"
            _pnl_sign = "+" if _pnl_pct >= 0 else ""
            _chain_emoji = CHAIN_EMOJI.get(_chain, "⬡")
            _size = float(_p.get("position_size_usd", 0))
            _rows_html += (
                f'<div style="display:flex;align-items:center;padding:8px 12px;'
                f'border-bottom:1px solid rgba(48,54,61,0.3);gap:10px;">'
                f'<span style="font-size:0.75rem;">{_chain_emoji}</span>'
                f'<div style="flex:1;min-width:0;">'
                f'<div style="color:#E6EDF3;font-size:0.78rem;font-weight:700;'
                f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{_sym}</div>'
                f'<div style="color:#484F58;font-size:0.6rem;">{_chain} · ${_size:.2f}</div>'
                f'</div>'
                f'<div style="text-align:right;">'
                f'<div style="color:{_pnl_color};font-size:0.82rem;font-weight:800;'
                f'font-family:\'JetBrains Mono\',monospace;">{_pnl_sign}{_pnl_pct:.1f}%</div>'
                f'<div style="color:#30363D;font-size:0.58rem;">'
                f'${_entry:.6f} → ${_curr:.6f}</div>'
                f'</div>'
                f'</div>'
            )
        st.markdown(
            f'<div class="glass-card" style="padding:0;overflow:hidden;">'
            f'{_rows_html}'
            f'</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="glass-card" style="padding:24px;text-align:center;">'
            '<div style="color:#30363D;font-size:1.4rem;">📭</div>'
            '<div style="color:#484F58;font-size:0.78rem;font-weight:600;">No open positions</div>'
            '<div style="color:#30363D;font-size:0.68rem;">Scanner is searching for gems...</div>'
            '</div>',
            unsafe_allow_html=True,
        )

with _dp_right:
    # ── Recent Trades Feed ───────────────────────────────────────────────────
    st.markdown(
        '<div style="color:#484F58;font-size:0.62rem;font-weight:700;text-transform:uppercase;'
        'letter-spacing:0.12em;margin-bottom:8px;">Recent trades</div>',
        unsafe_allow_html=True,
    )
    _recent = sorted(trades_data, key=lambda t: t.get("timestamp", ""), reverse=True)[:8] if trades_data else []
    if _recent:
        _trades_html = ""
        for _t in _recent:
            _t_sym = _t.get("symbol", "???")
            _t_side = _t.get("side", "buy").upper()
            _t_pnl = float(_t.get("realized_pnl_usd", 0))
            _t_pnl_pct = float(_t.get("pnl_pct", 0))
            _is_buy = _t_side == "BUY"
            _side_color = "#00D09C" if _is_buy else "#FF4757"
            _side_icon = "▲" if _is_buy else "▼"
            _pnl_str = ""
            if not _is_buy and _t_pnl != 0:
                _pc = "#00D09C" if _t_pnl > 0 else "#FF4757"
                _ps = "+" if _t_pnl > 0 else ""
                _pnl_str = (
                    f'<span style="color:{_pc};font-weight:700;font-family:\'JetBrains Mono\',monospace;'
                    f'font-size:0.72rem;">{_ps}${abs(_t_pnl):.4f}</span>'
                )
            _t_time = _t.get("timestamp", "")[:16].replace("T", " ")
            _t_chain = _t.get("chain", "")
            _trades_html += (
                f'<div style="display:flex;align-items:center;padding:7px 12px;'
                f'border-bottom:1px solid rgba(48,54,61,0.3);gap:8px;">'
                f'<span style="color:{_side_color};font-weight:900;font-size:0.72rem;">{_side_icon}</span>'
                f'<div style="flex:1;min-width:0;">'
                f'<div style="color:#E6EDF3;font-size:0.72rem;font-weight:600;'
                f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">'
                f'{_t_sym}</div>'
                f'<div style="color:#30363D;font-size:0.56rem;">{_t_time} · {_t_chain}</div>'
                f'</div>'
                f'{_pnl_str}'
                f'</div>'
            )
        st.markdown(
            f'<div class="glass-card" style="padding:0;overflow:hidden;">'
            f'{_trades_html}'
            f'</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="glass-card" style="padding:24px;text-align:center;">'
            '<div style="color:#30363D;font-size:1.4rem;">📊</div>'
            '<div style="color:#484F58;font-size:0.78rem;font-weight:600;">No trades yet</div>'
            '<div style="color:#30363D;font-size:0.68rem;">Waiting for first execution...</div>'
            '</div>',
            unsafe_allow_html=True,
        )

    # ── Chain Allocation Mini ────────────────────────────────────────────────
    _chain_counts = {}
    for _g in gems:
        _c = _g.get("chain", "unknown")
        _chain_counts[_c] = _chain_counts.get(_c, 0) + 1
    _total_gems_c = max(sum(_chain_counts.values()), 1)
    if _chain_counts:
        st.markdown(
            '<div style="color:#484F58;font-size:0.62rem;font-weight:700;text-transform:uppercase;'
            'letter-spacing:0.12em;margin:12px 0 8px;">Chain distribution</div>',
            unsafe_allow_html=True,
        )
        _alloc_html = ""
        for _c, _cnt in sorted(_chain_counts.items(), key=lambda x: -x[1])[:6]:
            _pct = (_cnt / _total_gems_c) * 100
            _cc = CHAIN_COLORS.get(_c, "#8B949E")
            _ce = CHAIN_EMOJI.get(_c, "⬡")
            _alloc_html += (
                f'<div style="display:flex;align-items:center;gap:8px;padding:4px 0;">'
                f'<span style="font-size:0.72rem;">{_ce}</span>'
                f'<span style="color:#8B949E;font-size:0.68rem;font-weight:600;width:50px;">'
                f'{_c[:8]}</span>'
                f'<div style="flex:1;height:4px;background:rgba(48,54,61,0.5);border-radius:2px;">'
                f'<div style="width:{_pct:.0f}%;height:100%;background:{_cc};border-radius:2px;'
                f'transition:width 0.6s ease;"></div></div>'
                f'<span style="color:{_cc};font-size:0.65rem;font-weight:700;width:36px;'
                f'text-align:right;">{_cnt}</span>'
                f'</div>'
            )
        st.markdown(
            f'<div class="glass-card" style="padding:10px 14px;">{_alloc_html}</div>',
            unsafe_allow_html=True,
        )

st.markdown('<div style="height:12px;"></div>', unsafe_allow_html=True)

# ── Bot Activity Ticker ──────────────────────────────────────────────────────
bot_mode = adaptive_state.get("mode", "unknown").upper()
consec_wins = offensive_state.get("consecutive_wins", 0)
consec_losses = offensive_state.get("consecutive_losses", 0)
god_mode = offensive_state.get("god_mode_active", False)
hwm = adaptive_state.get("high_water_mark_usd", 0)
current_cap = adaptive_state.get("current_capital_usd", 0)
drawdown = adaptive_state.get("drawdown_pct", 0)
house_pool = offensive_state.get("house_money_pool_usd", 0)
session_pnl = offensive_state.get("session_realized_pnl_usd", 0)

# Mode color
_mode_colors = {
    "LIVE": ("#00D09C", "rgba(0,208,156,0.08)"),
    "GOD MODE": ("#FFD700", "rgba(255,215,0,0.10)"),
    "RECOVERY": ("#FF4757", "rgba(255,71,87,0.08)"),
    "EXPANSION": ("#58A6FF", "rgba(88,166,255,0.08)"),
    "CONSERVATIVE": ("#FFB84D", "rgba(255,184,77,0.08)"),
}
_mc, _mbg = _mode_colors.get(bot_mode, ("#8B949E", "rgba(139,148,158,0.08)"))

ticker_items = []
if god_mode:
    ticker_items.append(f'<span style="color:#FFD700;font-weight:800;">⚡ GOD MODE ACTIVE</span>')
if consec_wins >= 2:
    ticker_items.append(f'<span style="color:#00D09C;">🔥 {consec_wins}-WIN STREAK</span>')
if consec_losses >= 2:
    ticker_items.append(f'<span style="color:#FF4757;">⚠️ {consec_losses} CONSECUTIVE LOSSES</span>')
if house_pool > 1:
    ticker_items.append(f'<span style="color:#58A6FF;">🏦 House Pool: ${house_pool:.2f}</span>')
if drawdown > 50:
    ticker_items.append(f'<span style="color:#FF4757;">📉 Drawdown: {drawdown:.1f}% from HWM ${hwm:.0f}</span>')
ticker_items.append(f'<span style="color:#484F58;">Capital: ${current_cap:.2f} · HWM: ${hwm:.2f}</span>')
ticker_items.append(f'<span style="color:#484F58;">Session P&L: {"+ " if session_pnl>=0 else ""}${session_pnl:.4f}</span>')

st.markdown(
    f'<div style="background:{_mbg};border:1px solid {_mc}33;border-radius:10px;'
    f'padding:10px 16px;margin-bottom:18px;display:flex;align-items:center;gap:16px;flex-wrap:wrap;">'
    f'<span style="background:{_mc}22;color:{_mc};font-size:0.68rem;font-weight:800;'
    f'text-transform:uppercase;letter-spacing:0.1em;padding:3px 10px;border-radius:20px;'
    f'border:1px solid {_mc}44;white-space:nowrap;">'
    f'● {bot_mode}</span>'
    + " &nbsp;·&nbsp; ".join(ticker_items)
    + '</div>',
    unsafe_allow_html=True,
)

# ── Macro Market Regime Widget ───────────────────────────────────────────────
try:
    import sys as _sys
    _sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from core.macro_filter import get_macro_regime
    _macro = get_macro_regime()
    _mr_regime = _macro.regime
    _mr_mult = _macro.score_multiplier
    _mr_min = _macro.min_score_override
    _mr_fg = _macro.fear_greed_value
    _mr_fg_label = _macro.fear_greed_label
    _mr_dom = _macro.btc_dominance_signal
    _mr_coins = _macro.coins
    _mr_cached = _macro.cached
    _mr_ok = True
except Exception:
    _mr_ok = False
    _mr_regime = "NEUTRAL"
    _mr_mult = 1.0
    _mr_min = 65.0
    _mr_fg = 50
    _mr_fg_label = "Neutral"
    _mr_dom = "NEUTRAL"
    _mr_coins = {}
    _mr_cached = False

_regime_colors = {
    "BULL": ("#00D09C", "rgba(0,208,156,0.08)", "rgba(0,208,156,0.3)"),
    "NEUTRAL": ("#8B949E", "rgba(139,148,158,0.06)", "rgba(139,148,158,0.2)"),
    "BEAR": ("#FF4757", "rgba(255,71,87,0.08)", "rgba(255,71,87,0.3)"),
    "EXTREME_FEAR": ("#FF4757", "rgba(255,71,87,0.12)", "rgba(255,71,87,0.5)"),
}
_rc, _rbg, _rborder = _regime_colors.get(_mr_regime, _regime_colors["NEUTRAL"])

_regime_icons = {"BULL": "🟢", "NEUTRAL": "🟡", "BEAR": "🔴", "EXTREME_FEAR": "🚨"}
_regime_icon = _regime_icons.get(_mr_regime, "🟡")

# F&G color
_fg_color = (
    "#FF4757" if _mr_fg <= 25
    else "#FFB84D" if _mr_fg <= 45
    else "#8B949E" if _mr_fg <= 55
    else "#58A6FF" if _mr_fg <= 75
    else "#00D09C"
)

# Build coin pills
_coin_pills = ""
for _sym, _cr in _mr_coins.items():
    _cc = "#00D09C" if _cr.regime == "BULL" else ("#FF4757" if _cr.regime == "BEAR" else "#8B949E")
    _ema_icon = "▲" if _cr.above_ema200 else "▼"
    _coin_pills += (
        f'<div style="background:rgba(255,255,255,0.03);border:1px solid {_cc}33;'
        f'border-radius:8px;padding:6px 10px;min-width:90px;">'
        f'<div style="color:#484F58;font-size:0.58rem;font-weight:700;text-transform:uppercase;">'
        f'{_sym}</div>'
        f'<div style="color:{_cc};font-size:0.82rem;font-weight:700;font-family:monospace;">'
        f'{_ema_icon} {_cr.chg_7d_pct:+.1f}%</div>'
        f'<div style="color:#30363D;font-size:0.58rem;">7d · EMA200 {"above" if _cr.above_ema200 else "below"}</div>'
        f'</div>'
    )

# Multiplier display
_mult_color = "#00D09C" if _mr_mult >= 1.0 else ("#FF4757" if _mr_mult < 0.85 else "#FFB84D")
_mult_str = f"{_mr_mult:.2f}×"
_cached_str = ' <span style="color:#30363D;font-size:0.6rem;">(cached)</span>' if _mr_cached else ''

st.markdown(
    f'<div style="background:{_rbg};border:1px solid {_rborder};border-radius:12px;'
    f'padding:12px 18px;margin-bottom:18px;">'
    f'<div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px;">'
    f'<div style="display:flex;align-items:center;gap:10px;">'
    f'<span style="font-size:1.2rem;">{_regime_icon}</span>'
    f'<div>'
    f'<div style="color:#484F58;font-size:0.6rem;font-weight:700;text-transform:uppercase;'
    f'letter-spacing:0.1em;">Macro Market Regime{_cached_str}</div>'
    f'<div style="color:{_rc};font-size:1.05rem;font-weight:800;letter-spacing:0.05em;">{_mr_regime}</div>'
    f'</div>'
    f'</div>'
    f'<div style="display:flex;align-items:center;gap:16px;flex-wrap:wrap;">'
    f'<div style="text-align:center;">'
    f'<div style="color:#484F58;font-size:0.58rem;font-weight:700;text-transform:uppercase;">Gem Multiplier</div>'
    f'<div style="color:{_mult_color};font-size:1.0rem;font-weight:800;font-family:monospace;">{_mult_str}</div>'
    f'</div>'
    f'<div style="text-align:center;">'
    f'<div style="color:#484F58;font-size:0.58rem;font-weight:700;text-transform:uppercase;">Min Score</div>'
    f'<div style="color:#E6EDF3;font-size:1.0rem;font-weight:800;font-family:monospace;">{_mr_min:.0f}</div>'
    f'</div>'
    f'<div style="text-align:center;">'
    f'<div style="color:#484F58;font-size:0.58rem;font-weight:700;text-transform:uppercase;">Fear & Greed</div>'
    f'<div style="color:{_fg_color};font-size:1.0rem;font-weight:800;font-family:monospace;">{_mr_fg} <span style="font-size:0.7rem;">{_mr_fg_label}</span></div>'
    f'</div>'
    f'<div style="text-align:center;">'
    f'<div style="color:#484F58;font-size:0.58rem;font-weight:700;text-transform:uppercase;">BTC Dom Signal</div>'
    f'<div style="color:#8B949E;font-size:0.78rem;font-weight:700;">{_mr_dom.replace("_"," ")}</div>'
    f'</div>'
    f'</div>'
    f'</div>'
    f'<div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:10px;">'
    + _coin_pills
    + f'</div>'
    f'</div>',
    unsafe_allow_html=True,
)

# ── KPI Stats Row (native st.metric) ─────────────────────────────────────────
with st.container(horizontal=True):
    st.metric("Total scans", f"{len(history):,}", f"~{avg_gems:.1f} gems/scan", border=True)
    st.metric("Gems found", f"{len(gems):,}", "All chains", border=True)
    exp_delta = f"⚡ {express_count} express" if express_count > 0 else "No express"
    st.metric("Live candidates", str(latest_count), exp_delta, border=True)
    st.metric("Positions", str(active_positions), f"{len(positions_data)} total", border=True)
    st.metric("Trades", str(total_trades), "Executed", border=True)
    pnl_s = "+" if realized_pnl > 0 else ""
    st.metric("Realized P&L", f"{pnl_s}${abs(realized_pnl):,.0f}",
              f"{win_rate:.0f}% win rate",
              delta_color="normal" if realized_pnl >= 0 else "inverse",
              border=True)

st.markdown('<div style="height:12px;"></div>', unsafe_allow_html=True)

# ── Copy-Trade & Rebalance Live Feed ─────────────────────────────────────────
ct_col, rb_col = st.columns([1, 1])

with ct_col:
    st.markdown("#### 🤝 Copy-Trade Monitor")
    # Show alpha wallet tracking status
    _alpha_evm = [
        "0x6b75d8af000000e20b7a7ddf000ba900b4009a80",
        "0xd8da6bf26964af9d7eed9e03e53415d37aa96045",
        "0x28c6c06298d514db089934071355e5743bf21d60",
        "0x21a31ee1afc51d94c2efccaa2092ad1028285549",
        "0x47ac0fb4f2d84898e4d9e7b4dab3c24507a6d503",
        "0xf977814e90da44bfa03b6295a0616a897441acec",
        "0x95222290dd7278aa3ddd389cc1e1d165cc4bafe5",
        "0x4838b106fce9647bdf1e7877bf73ce8b0bad5f97",
        "0x3f5ce5fbfe3e9af3971dd833d26ba9b5c936f0be",
        "0x9696f59e4d72e237be84ffd425dcad154bf96976",
    ]
    _alpha_labels = [
        "Lookonchain Alpha", "Vitalik (Signal)", "Binance 14", "Binance 15",
        "Binance Cold", "Binance 8", "Base Ecosystem Whale", "Base Gem Sniper",
        "Binance Hot", "Known Accumulator",
    ]
    # Find copy trades from trade history
    _copy_trades = [t for t in trades_data if t.get("strategy_tag") == "copy_trade"
                    or "copy" in str(t.get("reason", "")).lower()]
    _last_copy = _copy_trades[-1] if _copy_trades else None

    st.markdown(
        f'<div class="glass-card" style="padding:14px 16px;">'
        f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">'
        f'<span style="color:#E6EDF3;font-size:0.8rem;font-weight:700;">Alpha Wallets Tracked</span>'
        f'<span style="background:rgba(0,208,156,0.12);color:#00D09C;font-size:0.68rem;'
        f'font-weight:700;padding:2px 10px;border-radius:20px;border:1px solid rgba(0,208,156,0.25);">'
        f'● ACTIVE · {len(_alpha_evm)} wallets</span>'
        f'</div>'
        f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:4px;">',
        unsafe_allow_html=True,
    )
    for _addr, _lbl in zip(_alpha_evm[:8], _alpha_labels[:8]):
        _short = _addr[:6] + "..." + _addr[-4:]
        st.markdown(
            f'<div style="display:flex;align-items:center;gap:8px;padding:4px 0;'
            f'border-bottom:1px solid rgba(48,54,61,0.3);">'
            f'<span style="width:6px;height:6px;border-radius:50%;background:#00D09C;'
            f'display:inline-block;flex-shrink:0;"></span>'
            f'<span style="color:#8B949E;font-size:0.68rem;font-family:monospace;">{_short}</span>'
            f'<span style="color:#484F58;font-size:0.65rem;">{_lbl}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
    st.markdown(
        f'</div>'
        f'<div style="margin-top:10px;padding-top:10px;border-top:1px solid rgba(48,54,61,0.5);">'
        f'<div style="color:#484F58;font-size:0.65rem;font-weight:700;'
        f'text-transform:uppercase;letter-spacing:0.08em;margin-bottom:6px;">Copy-Trade Settings</div>'
        f'<div style="display:flex;gap:12px;flex-wrap:wrap;">'
        f'<span style="color:#8B949E;font-size:0.72rem;">Min Buy: <b style="color:#E6EDF3;">$50</b></span>'
        f'<span style="color:#8B949E;font-size:0.72rem;">Tier 1: <b style="color:#E6EDF3;">2 wallets</b></span>'
        f'<span style="color:#8B949E;font-size:0.72rem;">Tier 2: <b style="color:#E6EDF3;">1 wallet</b></span>'
        f'<span style="color:#8B949E;font-size:0.72rem;">Max Copy: <b style="color:#E6EDF3;">$100</b></span>'
        f'<span style="color:#8B949E;font-size:0.72rem;">Age Window: <b style="color:#E6EDF3;">5 min</b></span>'
        f'</div>'
        + (f'<div style="margin-top:8px;padding:6px 10px;background:rgba(0,208,156,0.06);'
           f'border-radius:6px;border-left:3px solid #00D09C;">'
           f'<span style="color:#00D09C;font-size:0.7rem;font-weight:700;">Last Copy Trade: </span>'
           f'<span style="color:#8B949E;font-size:0.7rem;">{_last_copy.get("token_symbol","?")}</span>'
           f'<span style="color:#484F58;font-size:0.68rem;"> · {_last_copy.get("timestamp","")[:19]}</span>'
           f'</div>' if _last_copy else
           f'<div style="margin-top:8px;padding:6px 10px;background:rgba(255,184,77,0.06);'
           f'border-radius:6px;border-left:3px solid #FFB84D;">'
           f'<span style="color:#FFB84D;font-size:0.7rem;">⏳ Monitoring — no copy trades yet. '
           f'Waiting for alpha wallet buy ≥ $50</span>'
           f'</div>')
        + '</div></div>',
        unsafe_allow_html=True,
    )

with rb_col:
    st.markdown("#### ⚖️ Capital Rebalance Status")
    _total_hold = sum(
        sum(t.get("value_usd", 0) for t in p.get("hold", []))
        for p in _rebalance_plans.values()
    )
    _total_liq = sum(
        sum(t.get("value_usd", 0) for t in p.get("liquidate", []))
        for p in _rebalance_plans.values()
    )
    _total_dust = sum(
        sum(t.get("value_usd", 0) for t in p.get("dust", []))
        for p in _rebalance_plans.values()
    )
    st.markdown(
        f'<div class="glass-card" style="padding:14px 16px;">'
        f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">'
        f'<span style="color:#E6EDF3;font-size:0.8rem;font-weight:700;">Rebalance Planner</span>'
        f'<span style="background:rgba(88,166,255,0.12);color:#58A6FF;font-size:0.68rem;'
        f'font-weight:700;padding:2px 10px;border-radius:20px;border:1px solid rgba(88,166,255,0.25);">'
        f'{len(_rebalance_plans)} plans active</span>'
        f'</div>',
        unsafe_allow_html=True,
    )
    # Summary bars
    _rb_items = [
        ("Hold", _total_hold, "#00D09C"),
        ("Liquidate", _total_liq, "#FF4757"),
        ("Dust", _total_dust, "#484F58"),
    ]
    _rb_total = max(_total_hold + _total_liq + _total_dust, 1)
    for _label, _val, _color in _rb_items:
        _pct = (_val / _rb_total) * 100
        st.markdown(
            f'<div style="margin-bottom:8px;">'
            f'<div style="display:flex;justify-content:space-between;margin-bottom:3px;">'
            f'<span style="color:#8B949E;font-size:0.72rem;">{_label}</span>'
            f'<span style="color:{_color};font-size:0.72rem;font-weight:700;">${_val:,.2f}</span>'
            f'</div>'
            f'<div style="height:5px;background:rgba(48,54,61,0.5);border-radius:3px;">'
            f'<div style="width:{_pct:.1f}%;height:100%;background:{_color};border-radius:3px;"></div>'
            f'</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    # Show top liquidation candidates
    _all_liq = []
    for _p in _rebalance_plans.values():
        _all_liq.extend(_p.get("liquidate", []))
    if _all_liq:
        st.markdown(
            '<div style="margin-top:10px;padding-top:10px;border-top:1px solid rgba(48,54,61,0.5);">'
            '<div style="color:#484F58;font-size:0.65rem;font-weight:700;'
            'text-transform:uppercase;letter-spacing:0.08em;margin-bottom:6px;">Liquidation Queue</div>',
            unsafe_allow_html=True,
        )
        for _t in _all_liq[:4]:
            st.markdown(
                f'<div style="display:flex;justify-content:space-between;padding:3px 0;'
                f'border-bottom:1px solid rgba(48,54,61,0.2);">'
                f'<span style="color:#FF4757;font-size:0.72rem;font-weight:600;">{_t.get("symbol","?")}</span>'
                f'<span style="color:#8B949E;font-size:0.68rem;">${_t.get("value_usd",0):,.2f}</span>'
                f'<span style="color:#484F58;font-size:0.65rem;">{_t.get("reason","")[:30]}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
        st.markdown('</div>', unsafe_allow_html=True)
    else:
        st.markdown(
            '<div style="margin-top:10px;padding:8px;text-align:center;color:#484F58;font-size:0.72rem;">'
            'No liquidation candidates — portfolio is clean</div>',
            unsafe_allow_html=True,
        )
    st.markdown('</div>', unsafe_allow_html=True)

st.markdown('<div style="height:8px;"></div>', unsafe_allow_html=True)

# ── Charts Row ────────────────────────────────────────────────────────────────
chart_c1, chart_c2 = st.columns([2, 1])

with chart_c1:
    st.markdown("#### 📈 Scan Activity")
    if history:
        df_h = pd.DataFrame(history)
        df_h["timestamp"] = pd.to_datetime(df_h["timestamp"])
        df_h = df_h.sort_values("timestamp")
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df_h["timestamp"], y=df_h["candidates_found"],
            mode="lines", name="Candidates",
            line=dict(color=ACCENT, width=2),
            fill="tozeroy", fillcolor="rgba(0,208,156,0.06)",
            hovertemplate="<b>%{y} candidates</b><br>%{x|%H:%M:%S}<extra></extra>",
        ))
        if "trades_attempted" in df_h.columns:
            fig.add_trace(go.Bar(
                x=df_h["timestamp"], y=df_h["trades_attempted"],
                name="Trades", marker_color="rgba(88,166,255,0.45)",
                hovertemplate="<b>%{y} trades</b><br>%{x|%H:%M:%S}<extra></extra>",
            ))
        fig.update_layout(**PLOTLY_LAYOUT, height=280, xaxis_title=None, yaxis_title=None)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    else:
        st.markdown(
            '<div class="glass-card" style="text-align:center;padding:2.5rem;">'
            '<div style="font-size:1.8rem;margin-bottom:8px;">📡</div>'
            '<div style="color:#8B949E;">Waiting for scan data...</div>'
            '<div style="color:#484F58;font-size:0.75rem;margin-top:4px;">'
            'Appears after the first scan cycle</div>'
            '</div>',
            unsafe_allow_html=True,
        )

with chart_c2:
    st.markdown("#### 🔗 Chain Distribution")
    if gems:
        chain_counts = {}
        for g in gems:
            c = g.get("chain", "unknown")
            chain_counts[c] = chain_counts.get(c, 0) + 1
        chains_list = list(chain_counts.keys())
        counts = list(chain_counts.values())
        colors = [CHAIN_COLORS.get(c, "#8B949E") for c in chains_list]
        fig_d = go.Figure(data=[go.Pie(
            labels=[c.capitalize() for c in chains_list], values=counts, hole=0.70,
            marker=dict(colors=colors, line=dict(color="#06090F", width=2)),
            textinfo="percent", textfont=dict(size=10, color="#E6EDF3"),
            hovertemplate="<b>%{label}</b><br>%{value} gems (%{percent})<extra></extra>",
        )])
        fig_d.update_layout(
            **PLOTLY_LAYOUT, height=280,
            annotations=[dict(
                text=f"<b>{sum(counts)}</b><br><span style='font-size:11px;'>gems</span>",
                x=0.5, y=0.5, font_size=14,
                font=dict(color="#E6EDF3", family="JetBrains Mono, Inter"),
                showarrow=False,
            )],
        )
        st.plotly_chart(fig_d, use_container_width=True, config={"displayModeBar": False})
    else:
        st.markdown(
            '<div class="glass-card" style="text-align:center;padding:2.5rem;">'
            '<div style="font-size:1.8rem;margin-bottom:8px;">🔗</div>'
            '<div style="color:#8B949E;">No chain data yet</div>'
            '</div>',
            unsafe_allow_html=True,
        )

# ── Recent Trades Feed + Gem Candidates Row ───────────────────────────────────
st.markdown('<div style="height:14px;"></div>', unsafe_allow_html=True)
trades_col, gems_col = st.columns([1, 2])

with trades_col:
    st.markdown("#### 📜 Recent Trades")
    if trades_data:
        _recent = sorted(trades_data, key=lambda t: t.get("timestamp", ""), reverse=True)[:12]
        for _t in _recent:
            _dir = _t.get("direction", "buy")
            _sym = _t.get("symbol", "???")
            _chain = _t.get("chain", "")
            _pnl = _t.get("pnl_usd", 0)
            _ts = _t.get("timestamp", "")[:16]
            _price = _t.get("price_usd", 0)
            _emoji = CHAIN_EMOJI.get(_chain, "⬡")

            if _dir == "buy":
                _dir_badge = ('<span style="background:rgba(0,208,156,0.12);color:#00D09C;'
                              'font-size:0.62rem;font-weight:800;padding:1px 6px;'
                              'border-radius:4px;">BUY</span>')
                _pnl_html = ""
            else:
                _dir_badge = ('<span style="background:rgba(255,71,87,0.12);color:#FF4757;'
                              'font-size:0.62rem;font-weight:800;padding:1px 6px;'
                              'border-radius:4px;">SELL</span>')
                _pnl_color = "#00D09C" if _pnl >= 0 else "#FF4757"
                _pnl_sign = "+" if _pnl >= 0 else ""
                _pnl_html = (f'<span style="color:{_pnl_color};font-size:0.72rem;'
                             f'font-weight:700;font-family:monospace;">'
                             f'{_pnl_sign}${abs(_pnl):,.2f}</span>')

            st.markdown(
                f'<div style="display:flex;align-items:center;gap:8px;padding:6px 0;'
                f'border-bottom:1px solid rgba(48,54,61,0.3);">'
                f'{_dir_badge}'
                f'<span style="color:#E6EDF3;font-size:0.78rem;font-weight:600;">{_sym}</span>'
                f'<span style="color:#484F58;font-size:0.65rem;">{_emoji} {_chain[:3]}</span>'
                f'<span style="flex:1;"></span>'
                f'{_pnl_html}'
                f'<span style="color:#30363D;font-size:0.6rem;font-family:monospace;">{_ts[11:]}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

        # Win/Loss summary bar
        _buys = len([t for t in trades_data if t.get("direction") == "buy"])
        _sells_w = len([t for t in sells if t.get("pnl_usd", 0) > 0])
        _sells_l = len(sells) - _sells_w
        _total_bar = max(_sells_w + _sells_l, 1)
        _w_pct = (_sells_w / _total_bar) * 100
        st.markdown(
            f'<div style="margin-top:10px;">'
            f'<div style="display:flex;justify-content:space-between;margin-bottom:4px;">'
            f'<span style="color:#00D09C;font-size:0.68rem;font-weight:700;">'
            f'✅ {_sells_w} wins</span>'
            f'<span style="color:#FF4757;font-size:0.68rem;font-weight:700;">'
            f'❌ {_sells_l} losses</span>'
            f'</div>'
            f'<div style="height:6px;background:rgba(255,71,87,0.3);border-radius:3px;overflow:hidden;">'
            f'<div style="width:{_w_pct:.0f}%;height:100%;background:#00D09C;border-radius:3px;"></div>'
            f'</div>'
            f'<div style="color:#484F58;font-size:0.62rem;text-align:center;margin-top:4px;">'
            f'{_buys} buys · {len(sells)} sells · {win_rate:.0f}% win rate</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="glass-card" style="text-align:center;padding:2rem;">'
            '<div style="font-size:1.4rem;margin-bottom:6px;">📜</div>'
            '<div style="color:#8B949E;">No trades yet</div>'
            '<div style="color:#484F58;font-size:0.72rem;margin-top:4px;">'
            'Trades appear after the bot executes a buy or sell</div>'
            '</div>',
            unsafe_allow_html=True,
        )

with gems_col:
    st.markdown("#### 💎 Latest Gem Candidates")
    if latest_gems:
        seen = {}
        for g in latest_gems:
            addr = g.get("address", g.get("symbol", ""))
            if addr not in seen or g.get("gem_score", 0) > seen[addr].get("gem_score", 0):
                seen[addr] = g
        deduped = sorted(seen.values(), key=lambda x: x.get("gem_score", 0), reverse=True)[:20]

        _gem_df = pd.DataFrame([
            {
                "Score": g.get("gem_score", 0),
                "Token": g.get("symbol", "???"),
                "Chain": f"{CHAIN_EMOJI.get(g.get('chain',''), '⬡')} {g.get('chain','').capitalize()}",
                "Price": g.get("price_usd", 0),
                "Liquidity": g.get("liquidity_usd", 0),
                "Vol 1h": g.get("volume_1h", 0),
                "Age (h)": g.get("age_hours", 0) or 0,
                "Express": "⚡" if g.get("express_lane") else "",
                "Safe": "✅" if g.get("is_safe") else "⚠️",
            }
            for g in deduped
        ])

        st.dataframe(
            _gem_df,
            use_container_width=True,
            hide_index=True,
            height=min(460, len(deduped) * 38 + 40),
            column_config={
                "Score": st.column_config.ProgressColumn(
                    "Score",
                    min_value=0,
                    max_value=100,
                    format="%.0f",
                ),
                "Price": st.column_config.NumberColumn(
                    "Price",
                    format="$%.6f",
                ),
                "Liquidity": st.column_config.NumberColumn(
                    "Liquidity",
                    format="$%,.0f",
                ),
                "Vol 1h": st.column_config.NumberColumn(
                    "Vol 1h",
                    format="$%,.0f",
                ),
                "Age (h)": st.column_config.NumberColumn(
                    "Age (h)",
                    format="%.1f",
                ),
            },
        )
    else:
        st.markdown(
            '<div class="glass-card" style="text-align:center;padding:2rem;">'
            '<div style="font-size:1.4rem;margin-bottom:6px;">💎</div>'
            '<div style="color:#8B949E;">No gem candidates yet — scanner is running</div>'
            '<div style="color:#484F58;font-size:0.75rem;margin-top:4px;">'
            'Use Force Scan in the sidebar to trigger immediately</div>'
            '</div>',
            unsafe_allow_html=True,
        )

# ── Watchlist ─────────────────────────────────────────────────────────────────
if watchlist_data:
    st.markdown('<div style="height:14px;"></div>', unsafe_allow_html=True)
    with st.expander(f"👁️ Watchlist ({len(watchlist_data)} tokens)", expanded=False):
        _wl_rows = []
        for w in watchlist_data[:30]:
            if isinstance(w, dict):
                _wl_rows.append({
                    "Token": w.get("symbol", w.get("token_symbol", "???")),
                    "Chain": w.get("chain", "").capitalize(),
                    "Score": w.get("score", w.get("gem_score", 0)),
                    "Added": str(w.get("added_at", w.get("discovered_at", "")))[:16],
                    "Reason": w.get("reason", w.get("strategy_tag", "")),
                })
        if _wl_rows:
            st.dataframe(
                pd.DataFrame(_wl_rows),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Score": st.column_config.ProgressColumn(
                        "Score", min_value=0, max_value=100, format="%.0f",
                    ),
                },
            )

# ── Error Feed (cached) ───────────────────────────────────────────────────────
@st.cache_data(ttl=15)
def _cached_errors():
    return get_errors()

errors = _cached_errors()
if errors:
    with st.expander(f"⚠️ Recent Errors ({len(errors[-10:])})", expanded=False):
        for err in reversed(errors[-10:]):
            st.markdown(
                f'<div style="padding:5px 10px;margin:3px 0;border-radius:6px;'
                f'background:rgba(255,71,87,0.05);border-left:3px solid #FF4757;'
                f'font-size:0.75rem;">'
                f'<span style="color:#30363D;">{err.get("timestamp","")[:19]}</span> · '
                f'<span style="color:#FF4757;">{err.get("error","Unknown error")}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

# ── Auto-refresh (proper Streamlit pattern — no script injection) ─────────────
if auto_refresh:
    try:
        # Use st.fragment with run_every for clean auto-refresh (Streamlit ≥1.33)
        @st.fragment(run_every=f"{refresh_rate}s")
        def _auto_refresh_trigger():
            """Fragment that triggers a full rerun on its refresh cycle."""
            pass  # The fragment rerun triggers data-reload via the cached functions
        _auto_refresh_trigger()
    except (TypeError, AttributeError):
        # Fallback for older Streamlit versions without run_every
        st.markdown(
            f'<meta http-equiv="refresh" content="{refresh_rate}">',
            unsafe_allow_html=True,
        )
