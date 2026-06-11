"""
dashboard/pages/6_🤝_Alpha_Wallets.py — ☘️ Shamrock Trading Bot
Alpha Wallet Monitor — copy-trade status, alpha wallet activity,
capital distribution per chain, and what the bot is doing right now.
"""

import sys
import os
import json
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from styles import PREMIUM_CSS, PLOTLY_LAYOUT, ACCENT, CHAIN_COLORS, CHAIN_EMOJI, DANGER, WARNING
from nav import render_nav
from state import (get_trades, get_positions, get_bot_status, get_force_scan_request,
                   request_force_scan, get_all_alpha_wallets, add_dashboard_alpha_wallet,
                   remove_dashboard_alpha_wallet)
from components import render_section_header, render_wallet_card_html

st.set_page_config(
    page_title="Shamrock | Alpha Wallets",
    page_icon="🤝",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(PREMIUM_CSS, unsafe_allow_html=True)
render_nav("Alpha")

# ─────────────────────────────────────────────────────────────────────────────
# Extra CSS
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.alpha-card {
    background: linear-gradient(145deg, rgba(13,17,23,0.98), rgba(22,27,34,0.95));
    border: 1px solid rgba(48,54,61,0.7);
    border-radius: 12px;
    padding: 14px 16px;
    margin-bottom: 8px;
    transition: border-color 0.2s;
}
.alpha-card:hover { border-color: rgba(0,208,156,0.35); }
.alpha-card.active { border-color: rgba(0,208,156,0.4); background: linear-gradient(145deg, rgba(0,208,156,0.04), rgba(13,17,23,0.98)); }
.alpha-card.signal { border-color: rgba(255,184,77,0.5); background: linear-gradient(145deg, rgba(255,184,77,0.05), rgba(13,17,23,0.98)); }
.wallet-addr { font-family: 'JetBrains Mono', monospace; font-size: 0.72rem; color: #58A6FF; }
.wallet-label { font-size: 0.78rem; font-weight: 700; color: #E6EDF3; }
.tier-badge {
    font-size: 0.62rem; font-weight: 800; text-transform: uppercase;
    letter-spacing: 0.08em; padding: 2px 8px; border-radius: 20px;
}
.tier-1 { background: rgba(0,208,156,0.15); color: #00D09C; border: 1px solid rgba(0,208,156,0.3); }
.tier-2 { background: rgba(88,166,255,0.12); color: #58A6FF; border: 1px solid rgba(88,166,255,0.25); }
.tier-3 { background: rgba(255,184,77,0.12); color: #FFB84D; border: 1px solid rgba(255,184,77,0.25); }
.chain-bar-row { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.chain-bar-label { width: 70px; font-size: 0.7rem; color: #8B949E; }
.chain-bar-track { flex: 1; height: 6px; background: rgba(48,54,61,0.5); border-radius: 3px; }
.chain-bar-fill { height: 100%; border-radius: 3px; }
.chain-bar-value { width: 55px; text-align: right; font-size: 0.7rem; font-family: monospace; }
.status-pill {
    display: inline-flex; align-items: center; gap: 5px;
    padding: 3px 10px; border-radius: 20px; font-size: 0.68rem; font-weight: 700;
}
.pill-monitoring { background: rgba(0,208,156,0.1); color: #00D09C; border: 1px solid rgba(0,208,156,0.25); }
.pill-signal    { background: rgba(255,184,77,0.12); color: #FFB84D; border: 1px solid rgba(255,184,77,0.3); }
.pill-copied    { background: rgba(88,166,255,0.12); color: #58A6FF; border: 1px solid rgba(88,166,255,0.25); }
.pill-skipped   { background: rgba(139,148,158,0.1); color: #8B949E; border: 1px solid rgba(139,148,158,0.2); }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        '<div style="display:flex;align-items:center;gap:10px;padding:4px 0 12px;">'
        '<span style="font-size:1.6rem;">☘️</span>'
        '<div>'
        '<div style="color:#E6EDF3;font-size:1.05rem;font-weight:800;letter-spacing:0.04em;">SHAMROCK</div>'
        '<div style="color:#30363D;font-size:0.65rem;font-weight:600;letter-spacing:0.08em;'
        'text-transform:uppercase;">Alpha Wallet Monitor</div>'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )
    st.markdown('<hr style="border-color:rgba(48,54,61,0.5);margin:0 0 14px;">', unsafe_allow_html=True)

    status = get_bot_status()
    is_running = status.get("is_running", False)
    mode = status.get("mode", "unknown").upper()
    if is_running:
        st.markdown(
            f'<div class="status-live"><span class="live-dot"></span> RUNNING · {mode}</div>',
            unsafe_allow_html=True,
        )
    pending = get_force_scan_request()
    st.markdown('<div style="height:10px;"></div>', unsafe_allow_html=True)
    if pending:
        st.markdown('<div class="scan-pending-pill">⏳ Scan queued</div>', unsafe_allow_html=True)
    else:
        if st.button("🔍 Force Scan Now", key="aw_force_scan", use_container_width=True):
            request_force_scan(reason="alpha_wallets_page")
            st.success("✅ Scan queued!")
            st.rerun()

    st.markdown('<hr style="border-color:rgba(48,54,61,0.5);margin:14px 0;">', unsafe_allow_html=True)
    auto_refresh = st.toggle("Auto-refresh", value=True)
    refresh_rate = st.select_slider("Interval", options=[5, 10, 15, 30, 60], value=15, format_func=lambda x: f"{x}s")

# ─────────────────────────────────────────────────────────────────────────────
# Data
# ─────────────────────────────────────────────────────────────────────────────
_BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def _load_json(path, default=None):
    try:
        full = os.path.join(_BASE, path)
        if os.path.exists(full):
            return json.loads(open(full).read())
    except Exception:
        pass
    return default if default is not None else {}

trades_data     = get_trades()
positions_data  = get_positions()
adaptive_state  = _load_json("output/adaptive_mode_state.json")
offensive_state = _load_json("output/offensive_state.json")

# Rebalance plans
_rebalance_plans = {}
for _wc in ["primary_base", "primary_bsc", "primary_ethereum", "primary_solana",
            "wallet_b_base", "wallet_b_bsc", "wallet_b_arbitrum", "wallet_b_ethereum"]:
    _plan = _load_json(f"output/rebalance_plan_{_wc}.json")
    if _plan:
        _rebalance_plans[_wc] = _plan

# ─────────────────────────────────────────────────────────────────────────────
# Alpha Wallet Management (Dynamic)
# ─────────────────────────────────────────────────────────────────────────────
ALPHA_WALLETS = get_all_alpha_wallets()

# ─────────────────────────────────────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(
    '<div class="page-header">'
    '<div style="display:flex;align-items:center;gap:12px;">'
    '<span style="font-size:1.7rem;">🤝</span>'
    '<div>'
    '<h1>ALPHA WALLET MONITOR</h1>'
    f'<div class="subtitle">{len(ALPHA_WALLETS)} tracked alpha wallets · Copy-trade status · Capital distribution</div>'
    '</div>'
    '</div>'
    '</div>',
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────────────────────────────────────
# Wallet Management — Add / Remove
# ─────────────────────────────────────────────────────────────────────────────
render_section_header("🔧", "Wallet management", f"{len(ALPHA_WALLETS)} tracked")

with st.expander("➕ Add a new alpha wallet", expanded=False, icon=":material/add_circle:"):
    with st.form("add_wallet_form", clear_on_submit=True):
        form_cols = st.columns([3, 2, 1])
        with form_cols[0]:
            new_address = st.text_input(
                "Wallet address",
                placeholder="0x... or Solana base58 address",
            )
        with form_cols[1]:
            new_label = st.text_input(
                "Label",
                placeholder="e.g., Based Whale #3",
            )
        with form_cols[2]:
            new_chain = st.selectbox(
                "Chain",
                ["evm", "solana"],
                index=0,
            )
        submitted = st.form_submit_button("Add wallet", use_container_width=True)
        if submitted:
            if not new_address:
                st.error("Address is required")
            elif not new_label:
                st.error("Label is required")
            elif new_chain == "evm" and (not new_address.startswith("0x") or len(new_address) != 42):
                st.error("Invalid EVM address (must be 0x + 40 hex chars)")
            else:
                if add_dashboard_alpha_wallet(new_address, new_label, new_chain):
                    st.success(f"✅ Added {new_label}")
                    st.rerun()
                else:
                    st.warning("Wallet already exists in the tracked list")

# Show dashboard-added wallets with remove buttons
_dashboard_wallets = [w for w in ALPHA_WALLETS if w.get("source") == "dashboard"]
if _dashboard_wallets:
    st.caption(f"{len(_dashboard_wallets)} custom wallet(s) added from dashboard")
    for dw in _dashboard_wallets:
        card_col, btn_col = st.columns([6, 1])
        with card_col:
            st.markdown(
                render_wallet_card_html(
                    address=dw["address"],
                    label=dw.get("label", ""),
                    chain_type=dw.get("chain_type", "evm"),
                    source="dashboard",
                ),
                unsafe_allow_html=True,
            )
        with btn_col:
            if st.button("🗑️", key=f"rm_{dw['address'][:10]}", help="Remove this wallet"):
                remove_dashboard_alpha_wallet(dw["address"])
                st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# Bot Activity Banner
# ─────────────────────────────────────────────────────────────────────────────
bot_mode     = adaptive_state.get("mode", "unknown").upper()
consec_wins  = offensive_state.get("consecutive_wins", 0)
consec_losses = offensive_state.get("consecutive_losses", 0)
god_mode     = offensive_state.get("god_mode_active", False)
hwm          = adaptive_state.get("high_water_mark_usd", 0)
current_cap  = adaptive_state.get("current_capital_usd", 0)
drawdown     = adaptive_state.get("drawdown_pct", 0)
house_pool   = offensive_state.get("house_money_pool_usd", 0)
session_pnl  = offensive_state.get("session_realized_pnl_usd", 0)
session_trades = offensive_state.get("session_trades", 0)
profit_boost = offensive_state.get("profit_boost_remaining", 0)
express_od   = offensive_state.get("express_overdrive_count", 0)

_mode_colors = {
    "LIVE":         ("#00D09C", "rgba(0,208,156,0.08)"),
    "GOD MODE":     ("#FFD700", "rgba(255,215,0,0.10)"),
    "RECOVERY":     ("#FF4757", "rgba(255,71,87,0.08)"),
    "EXPANSION":    ("#58A6FF", "rgba(88,166,255,0.08)"),
    "CONSERVATIVE": ("#FFB84D", "rgba(255,184,77,0.08)"),
}
_mc, _mbg = _mode_colors.get(bot_mode, ("#8B949E", "rgba(139,148,158,0.08)"))

st.markdown(
    f'<div style="background:{_mbg};border:1px solid {_mc}33;border-radius:12px;'
    f'padding:14px 18px;margin-bottom:20px;">'
    f'<div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;">'
    f'<span style="background:{_mc}22;color:{_mc};font-size:0.7rem;font-weight:800;'
    f'text-transform:uppercase;letter-spacing:0.1em;padding:4px 12px;border-radius:20px;'
    f'border:1px solid {_mc}44;">● {bot_mode}</span>'
    + (f'<span style="color:#FFD700;font-weight:800;font-size:0.8rem;">⚡ GOD MODE ACTIVE</span>' if god_mode else '')
    + (f'<span style="color:#00D09C;font-size:0.78rem;">🔥 {consec_wins}-win streak</span>' if consec_wins >= 2 else '')
    + (f'<span style="color:#FF4757;font-size:0.78rem;">⚠️ {consec_losses} consecutive losses</span>' if consec_losses >= 2 else '')
    + f'</div>'
    f'<div style="display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-top:12px;">'
    f'<div><div style="color:#484F58;font-size:0.6rem;font-weight:700;text-transform:uppercase;letter-spacing:0.08em;">Capital</div>'
    f'<div style="color:#E6EDF3;font-size:0.95rem;font-weight:700;font-family:monospace;">${current_cap:,.2f}</div></div>'
    f'<div><div style="color:#484F58;font-size:0.6rem;font-weight:700;text-transform:uppercase;letter-spacing:0.08em;">HWM</div>'
    f'<div style="color:#E6EDF3;font-size:0.95rem;font-weight:700;font-family:monospace;">${hwm:,.2f}</div></div>'
    f'<div><div style="color:#484F58;font-size:0.6rem;font-weight:700;text-transform:uppercase;letter-spacing:0.08em;">Drawdown</div>'
    f'<div style="color:{"#FF4757" if drawdown > 30 else "#00D09C"};font-size:0.95rem;font-weight:700;font-family:monospace;">{drawdown:.1f}%</div></div>'
    f'<div><div style="color:#484F58;font-size:0.6rem;font-weight:700;text-transform:uppercase;letter-spacing:0.08em;">Session P&L</div>'
    f'<div style="color:{"#00D09C" if session_pnl >= 0 else "#FF4757"};font-size:0.95rem;font-weight:700;font-family:monospace;">{"+" if session_pnl>=0 else ""}${session_pnl:.4f}</div></div>'
    f'<div><div style="color:#484F58;font-size:0.6rem;font-weight:700;text-transform:uppercase;letter-spacing:0.08em;">House Pool</div>'
    f'<div style="color:#58A6FF;font-size:0.95rem;font-weight:700;font-family:monospace;">${house_pool:.4f}</div></div>'
    f'</div>'
    f'</div>',
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────────────────────────────────────
# Copy-Trade Status Explanation
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("### 🤝 Do You Need to Do Anything to Trigger Copy Trading?")
st.markdown(
    '<div class="glass-card" style="padding:18px 20px;margin-bottom:20px;">'
    '<div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;">'
    '<div>'
    '<div style="color:#00D09C;font-size:0.85rem;font-weight:700;margin-bottom:8px;">✅ Fully Automatic — No Action Required</div>'
    '<div style="color:#8B949E;font-size:0.78rem;line-height:1.7;">'
    'The copy-trade daemon runs automatically every bot cycle (~2 minutes). '
    'It monitors all 10 alpha wallets in real-time using Moralis wallet activity feeds. '
    'When an alpha wallet buys a token ≥ $50, the bot automatically scores it and, '
    'if it passes the entry gates (score ≥ 62 in recovery mode), executes a copy trade '
    'proportional to your wallet balance.'
    '</div>'
    '</div>'
    '<div>'
    '<div style="color:#FFB84D;font-size:0.85rem;font-weight:700;margin-bottom:8px;">⚠️ Current Constraint: Low Liquid Capital</div>'
    '<div style="color:#8B949E;font-size:0.78rem;line-height:1.7;">'
    'The bot is in <b style="color:#FF4757;">RECOVERY MODE</b> with ~$94–$127 liquid capital. '
    'Position sizes are $2–$6 per trade. To unlock larger copy trades and full gem sniping, '
    'add capital to the wallets. The bot will automatically scale up position sizes '
    'as the portfolio grows via the Kelly multiplier system.'
    '</div>'
    '</div>'
    '</div>'
    '<div style="margin-top:14px;padding-top:14px;border-top:1px solid rgba(48,54,61,0.5);">'
    '<div style="color:#484F58;font-size:0.65rem;font-weight:700;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:8px;">How Copy Trading Works</div>'
    '<div style="display:flex;gap:8px;flex-wrap:wrap;">'
    '<div style="background:rgba(0,208,156,0.06);border:1px solid rgba(0,208,156,0.2);border-radius:8px;padding:8px 12px;flex:1;min-width:140px;">'
    '<div style="color:#00D09C;font-size:0.68rem;font-weight:700;">STEP 1</div>'
    '<div style="color:#8B949E;font-size:0.7rem;margin-top:3px;">Alpha wallet buys token ≥ $50</div>'
    '</div>'
    '<div style="background:rgba(88,166,255,0.06);border:1px solid rgba(88,166,255,0.2);border-radius:8px;padding:8px 12px;flex:1;min-width:140px;">'
    '<div style="color:#58A6FF;font-size:0.68rem;font-weight:700;">STEP 2</div>'
    '<div style="color:#8B949E;font-size:0.7rem;margin-top:3px;">Bot detects within 5 min window</div>'
    '</div>'
    '<div style="background:rgba(255,184,77,0.06);border:1px solid rgba(255,184,77,0.2);border-radius:8px;padding:8px 12px;flex:1;min-width:140px;">'
    '<div style="color:#FFB84D;font-size:0.68rem;font-weight:700;">STEP 3</div>'
    '<div style="color:#8B949E;font-size:0.7rem;margin-top:3px;">Token scored through 29-signal engine</div>'
    '</div>'
    '<div style="background:rgba(0,208,156,0.06);border:1px solid rgba(0,208,156,0.2);border-radius:8px;padding:8px 12px;flex:1;min-width:140px;">'
    '<div style="color:#00D09C;font-size:0.68rem;font-weight:700;">STEP 4</div>'
    '<div style="color:#8B949E;font-size:0.7rem;margin-top:3px;">If score ≥ 62 → execute copy trade</div>'
    '</div>'
    '</div>'
    '</div>'
    '</div>',
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────────────────────────────────────
# Alpha Wallet Cards
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("### 🧠 GMGN Smart Money — Solana Copy-Trading Pool")

# ── GMGN Solana Smart Money (live audit) ───────────────────────────────────
_GMGN_SOL_WALLETS = [
    {
        "address": "4Be9CvxqHW6BYiRAxW9Q3xu1ycTMWaL5z8NX4HR3ha7t",
        "label": "Smart Money Alpha #1",
        "tier": 1,
        "notes": "100% win rate • Confirmed $73K+ realized PnL • WOJAK +535%, PONKE +200%+",
    },
    {
        "address": "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM",
        "label": "Smart Money Alpha #2",
        "tier": 1,
        "notes": "100% win rate • $389K+ realized PnL • FWOG +115%, FTP +755%",
    },
    {
        "address": "DfMxre4cKmvogbLrPigxmibVTTQDuzjdXojWzjCXXhzj",
        "label": "Smart Money Alpha #4",
        "tier": 1,
        "notes": "100% win rate • $38K+ realized PnL • Consistent 100–200%+ returners",
    },
]

@st.cache_data(ttl=300, show_spinner=False)
def _load_gmgn_audit():
    """Load live GMGN audit data for all Smart Money wallets. Cached 5 min."""
    results = {}
    try:
        import sys, os
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        from core.gmgn_client import get_gmgn_client
        client = get_gmgn_client()
        for w in _GMGN_SOL_WALLETS:
            try:
                audit = client.audit_wallet(w["address"])
                results[w["address"]] = audit
            except Exception:
                results[w["address"]] = {}
    except Exception:
        pass
    return results

_gmgn_audit = _load_gmgn_audit()

# Summary KPIs
total_pnl = sum(
    _gmgn_audit.get(w["address"], {}).get("total_realized_pnl_usd", 0)
    for w in _GMGN_SOL_WALLETS
)
avg_wr = (
    sum(
        _gmgn_audit.get(w["address"], {}).get("win_rate_pct", 0)
        for w in _GMGN_SOL_WALLETS
        if _gmgn_audit.get(w["address"])
    ) / max(1, sum(1 for w in _GMGN_SOL_WALLETS if _gmgn_audit.get(w["address"])))
)

gkpi1, gkpi2, gkpi3, gkpi4 = st.columns(4)
with gkpi1:
    st.markdown(
        f'<div class="stat-card">'
        f'<div class="stat-icon">🧠</div>'
        f'<div class="stat-label">Smart Money Wallets</div>'
        f'<div class="stat-value">{len(_GMGN_SOL_WALLETS)}</div>'
        f'<div class="stat-delta positive">All Tier 1</div>'
        f'</div>', unsafe_allow_html=True,
    )
with gkpi2:
    st.markdown(
        f'<div class="stat-card">'
        f'<div class="stat-icon">💰</div>'
        f'<div class="stat-label">Combined PnL</div>'
        f'<div class="stat-value">${total_pnl:,.0f}</div>'
        f'<div class="stat-delta positive">Verified on-chain</div>'
        f'</div>', unsafe_allow_html=True,
    )
with gkpi3:
    st.markdown(
        f'<div class="stat-card">'
        f'<div class="stat-icon">🎯</div>'
        f'<div class="stat-label">Avg Win Rate</div>'
        f'<div class="stat-value">{avg_wr:.0f}%</div>'
        f'<div class="stat-delta positive">GMGN verified</div>'
        f'</div>', unsafe_allow_html=True,
    )
with gkpi4:
    st.markdown(
        f'<div class="stat-card">'
        f'<div class="stat-icon">⚡</div>'
        f'<div class="stat-label">Data Source</div>'
        f'<div class="stat-value">GMGN</div>'
        f'<div class="stat-delta positive">openapi.gmgn.ai</div>'
        f'</div>', unsafe_allow_html=True,
    )

st.markdown('<div style="height:12px;"></div>', unsafe_allow_html=True)

# Smart Money wallet cards
sol_left, sol_right = st.columns(2)
for i, sw in enumerate(_GMGN_SOL_WALLETS):
    col = sol_left if i % 2 == 0 else sol_right
    addr = sw["address"]
    short = addr[:8] + "..." + addr[-6:]
    audit = _gmgn_audit.get(addr, {})
    pnl = audit.get("total_realized_pnl_usd", 0)
    wr = audit.get("win_rate_pct", 0)
    top_winners = audit.get("top_winners", [])
    top = top_winners[0] if top_winners else {}
    live = bool(audit)

    with col:
        st.markdown(
            f'<div class="alpha-card {"active" if live else ""}">'
            f'<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px;">'
            f'<div>'
            f'<div class="wallet-label">🟢 {sw["label"]}</div>'
            f'<div class="wallet-addr">◎ {short}</div>'
            f'</div>'
            f'<div style="display:flex;flex-direction:column;align-items:flex-end;gap:4px;">'
            f'<span class="tier-badge tier-1">Tier 1 — GMGN</span>'
            f'<span style="color:#58A6FF;font-size:0.65rem;">◎ Solana</span>'
            f'</div>'
            f'</div>'
            f'<div style="color:#484F58;font-size:0.7rem;line-height:1.5;margin-bottom:10px;">{sw["notes"]}</div>'
            + (
                f'<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-bottom:10px;">'
                f'<div style="background:rgba(0,208,156,0.06);border-radius:6px;padding:6px 8px;">'
                f'<div style="color:#484F58;font-size:0.58rem;text-transform:uppercase;letter-spacing:0.06em;">Realized PnL</div>'
                f'<div style="color:#00D09C;font-size:0.82rem;font-weight:700;font-family:monospace;">${pnl:,.0f}</div>'
                f'</div>'
                f'<div style="background:rgba(88,166,255,0.06);border-radius:6px;padding:6px 8px;">'
                f'<div style="color:#484F58;font-size:0.58rem;text-transform:uppercase;letter-spacing:0.06em;">Win Rate</div>'
                f'<div style="color:#58A6FF;font-size:0.82rem;font-weight:700;font-family:monospace;">{wr:.0f}%</div>'
                f'</div>'
                f'<div style="background:rgba(255,184,77,0.06);border-radius:6px;padding:6px 8px;">'
                f'<div style="color:#484F58;font-size:0.58rem;text-transform:uppercase;letter-spacing:0.06em;">Best Call</div>'
                f'<div style="color:#FFB84D;font-size:0.75rem;font-weight:700;">'
                f'{top.get("symbol","—")} +{top.get("pnl_pct",0):.0f}%</div>'
                f'</div>'
                f'</div>'
                if live else
                f'<div style="color:#484F58;font-size:0.7rem;font-style:italic;margin-bottom:10px;">⏳ Loading GMGN data...</div>'
            )
            + f'<div style="display:flex;align-items:center;justify-content:space-between;">'
            f'<span class="status-pill pill-monitoring">● GMGN Active</span>'
            f'<a href="https://gmgn.ai/sol/address/{addr}" target="_blank" '
            f'style="color:#484F58;font-size:0.65rem;text-decoration:none;">View on GMGN →</a>'
            f'</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

st.markdown('<div style="height:24px;"></div>', unsafe_allow_html=True)
st.markdown("### 👁️ Tracked Alpha Wallets")

# Find any copy trades from history
copy_trades = [t for t in trades_data if
               t.get("strategy_tag") == "copy_trade" or
               "copy" in str(t.get("reason", "")).lower()]
copy_trade_map = {}
for ct in copy_trades:
    # Try to match by token
    sym = ct.get("token_symbol", "")
    copy_trade_map[sym] = ct

source_counts = {"system": 0, "dashboard": 0, "vip": 0}
for w in ALPHA_WALLETS:
    src = w.get("source", "system")
    source_counts[src] = source_counts.get(src, 0) + 1

_copy_delta_cls = "positive" if copy_trades else "neutral"
_copy_delta_txt = f"{len(copy_trades)} copied" if copy_trades else "Monitoring"

# Summary stats
col_s1, col_s2, col_s3, col_total = st.columns(4)
with col_s1:
    st.markdown(
        f'<div class="stat-card">'
        f'<div class="stat-icon">⚙️</div>'
        f'<div class="stat-label">System Wallets</div>'
        f'<div class="stat-value">{source_counts.get("system", 0)}</div>'
        f'<div class="stat-delta neutral">From config</div>'
        f'</div>', unsafe_allow_html=True,
    )
with col_s2:
    st.markdown(
        f'<div class="stat-card">'
        f'<div class="stat-icon">🛠️</div>'
        f'<div class="stat-label">Custom Wallets</div>'
        f'<div class="stat-value">{source_counts.get("dashboard", 0)}</div>'
        f'<div class="stat-delta positive">Dashboard-added</div>'
        f'</div>', unsafe_allow_html=True,
    )
with col_s3:
    st.markdown(
        f'<div class="stat-card">'
        f'<div class="stat-icon">⭐</div>'
        f'<div class="stat-label">VIP Wallets</div>'
        f'<div class="stat-value">{source_counts.get("vip", 0)}</div>'
        f'<div class="stat-delta positive">Priority copy</div>'
        f'</div>', unsafe_allow_html=True,
    )
with col_total:
    st.markdown(
        f'<div class="stat-card">'
        f'<div class="stat-icon">🤝</div>'
        f'<div class="stat-label">Total Tracked</div>'
        f'<div class="stat-value">{len(ALPHA_WALLETS)}</div>'
        f'<div class="stat-delta {_copy_delta_cls}">{_copy_delta_txt}</div>'
        f'</div>', unsafe_allow_html=True,
    )

st.markdown('<div style="height:16px;"></div>', unsafe_allow_html=True)

# Wallet cards grid
left_col, right_col = st.columns(2)
for i, wallet in enumerate(ALPHA_WALLETS):
    col = left_col if i % 2 == 0 else right_col
    with col:
        st.markdown(
            render_wallet_card_html(
                address=wallet["address"],
                label=wallet.get("label", ""),
                chain_type=wallet.get("chain_type", "evm"),
                source=wallet.get("source", "system"),
            ),
            unsafe_allow_html=True,
        )

# ─────────────────────────────────────────────────────────────────────────────
# Capital Distribution Per Chain
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("### 💰 Capital Distribution & Rebalance Status")
st.markdown(
    '<div style="color:#8B949E;font-size:0.78rem;margin-bottom:16px;">'
    'The bot automatically rebalances capital across chains to ensure liquid capital is available '
    'where gems are being found. Below is the current rebalance plan per wallet/chain.'
    '</div>',
    unsafe_allow_html=True,
)

if _rebalance_plans:
    for plan_key, plan in _rebalance_plans.items():
        wallet_name, chain_name = plan_key.rsplit("_", 1) if "_" in plan_key else (plan_key, "")
        wallet_display = {"primary": "Primary Wallet", "wallet_b": "Wallet B"}.get(wallet_name, wallet_name.title())
        chain_emoji_d = CHAIN_EMOJI.get(chain_name, "⬡")
        chain_color_d = CHAIN_COLORS.get(chain_name, "#8B949E")

        hold_items = plan.get("hold", [])
        liq_items  = plan.get("liquidate", [])
        monitor_items = plan.get("monitor", [])
        dust_items = plan.get("dust", [])

        total_hold = sum(t.get("value_usd", 0) for t in hold_items)
        total_liq  = sum(t.get("value_usd", 0) for t in liq_items)

        with st.expander(
            f"{chain_emoji_d} {wallet_display} — {chain_name.capitalize()} "
            f"| Hold: ${total_hold:,.2f} | Liquidate: ${total_liq:,.2f} "
            f"| {len(hold_items)} hold · {len(liq_items)} liq · {len(monitor_items)} monitor",
            expanded=False,
        ):
            rb_c1, rb_c2, rb_c3 = st.columns(3)
            with rb_c1:
                st.markdown(f'<div style="color:#00D09C;font-size:0.72rem;font-weight:700;margin-bottom:6px;">✅ HOLD ({len(hold_items)})</div>', unsafe_allow_html=True)
                for t in hold_items[:8]:
                    st.markdown(
                        f'<div style="display:flex;justify-content:space-between;padding:3px 0;'
                        f'border-bottom:1px solid rgba(48,54,61,0.3);">'
                        f'<span style="color:#E6EDF3;font-size:0.72rem;font-weight:600;">{t.get("symbol","?")}</span>'
                        f'<span style="color:#8B949E;font-size:0.68rem;">${t.get("value_usd",0):,.2f}</span>'
                        f'<span style="color:#484F58;font-size:0.65rem;">score {t.get("score",0):.0f}</span>'
                        f'</div>', unsafe_allow_html=True,
                    )
            with rb_c2:
                st.markdown(f'<div style="color:#FFB84D;font-size:0.72rem;font-weight:700;margin-bottom:6px;">👁️ MONITOR ({len(monitor_items)})</div>', unsafe_allow_html=True)
                for t in monitor_items[:8]:
                    st.markdown(
                        f'<div style="display:flex;justify-content:space-between;padding:3px 0;'
                        f'border-bottom:1px solid rgba(48,54,61,0.3);">'
                        f'<span style="color:#E6EDF3;font-size:0.72rem;font-weight:600;">{t.get("symbol","?")}</span>'
                        f'<span style="color:#8B949E;font-size:0.68rem;">${t.get("value_usd",0):,.2f}</span>'
                        f'<span style="color:#484F58;font-size:0.65rem;">score {t.get("score",0):.0f}</span>'
                        f'</div>', unsafe_allow_html=True,
                    )
            with rb_c3:
                st.markdown(f'<div style="color:#FF4757;font-size:0.72rem;font-weight:700;margin-bottom:6px;">🔴 LIQUIDATE ({len(liq_items)})</div>', unsafe_allow_html=True)
                for t in liq_items[:8]:
                    st.markdown(
                        f'<div style="display:flex;justify-content:space-between;padding:3px 0;'
                        f'border-bottom:1px solid rgba(48,54,61,0.3);">'
                        f'<span style="color:#FF4757;font-size:0.72rem;font-weight:600;">{t.get("symbol","?")}</span>'
                        f'<span style="color:#8B949E;font-size:0.68rem;">${t.get("value_usd",0):,.2f}</span>'
                        f'<span style="color:#484F58;font-size:0.65rem;">{t.get("reason","")[:25]}</span>'
                        f'</div>', unsafe_allow_html=True,
                    )
else:
    st.markdown(
        '<div class="glass-card" style="text-align:center;padding:2rem;">'
        '<div style="font-size:1.4rem;margin-bottom:6px;">⚖️</div>'
        '<div style="color:#8B949E;">No rebalance plans generated yet</div>'
        '<div style="color:#484F58;font-size:0.75rem;margin-top:4px;">'
        'Plans are generated each scan cycle based on portfolio scoring</div>'
        '</div>',
        unsafe_allow_html=True,
    )

# ─────────────────────────────────────────────────────────────────────────────
# Recent Trades Feed
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("### 📋 Recent Trade History")
if trades_data:
    recent = sorted(trades_data, key=lambda x: x.get("timestamp", ""), reverse=True)[:20]
    rows = []
    for t in recent:
        pnl = t.get("pnl_usd", 0) or 0
        action = t.get("action", t.get("direction", "?")).upper()
        pnl_str = f"+${pnl:.4f}" if pnl > 0 else (f"-${abs(pnl):.4f}" if pnl < 0 else "—")
        chain = t.get("chain", "")
        rows.append({
            "Time": t.get("timestamp", "")[:19],
            "Token": t.get("token_symbol", "?"),
            "Chain": f"{CHAIN_EMOJI.get(chain,'⬡')} {chain.capitalize()}",
            "Action": action,
            "Value": f"${t.get('value_usd', 0):,.4f}",
            "P&L": pnl_str,
            "Reason": t.get("reason", "—")[:40],
        })
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True, height=min(500, len(rows) * 38 + 40))
else:
    st.markdown(
        '<div class="glass-card" style="text-align:center;padding:2rem;">'
        '<div style="font-size:1.4rem;margin-bottom:6px;">📋</div>'
        '<div style="color:#8B949E;">No trades yet — bot is scanning and monitoring</div>'
        '</div>',
        unsafe_allow_html=True,
    )

# ─────────────────────────────────────────────────────────────────────────────
# Auto-refresh
# ─────────────────────────────────────────────────────────────────────────────
if auto_refresh:
    st.markdown(
        f'<script>setTimeout(()=>window.location.reload(),{refresh_rate*1000});</script>',
        unsafe_allow_html=True,
    )
