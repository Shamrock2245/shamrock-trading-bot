"""
Page 8 — 🏦 Paycheck Wallet

Tracks automated profit sweeps from trading capital to cold storage.
Shows accumulator progress, sweep history, and lifetime income.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import json
import plotly.graph_objects as go
import pandas as pd
from pathlib import Path
from datetime import datetime

from styles import PREMIUM_CSS, PLOTLY_LAYOUT, ACCENT, DANGER, WARNING

st.set_page_config(page_title="Paycheck Wallet | Shamrock", page_icon="🏦", layout="wide")
st.markdown(PREMIUM_CSS, unsafe_allow_html=True)

# ── Header ───────────────────────────────────────────────────────────────────
st.markdown(
    '<div style="display:flex;align-items:center;gap:12px;margin-bottom:1.5rem;">'
    '<span style="font-size:2rem;">🏦</span>'
    '<div>'
    '<h1 style="margin:0;padding:0;font-size:1.5rem;font-weight:800;'
    'background:linear-gradient(135deg,#00D09C,#00E6AC);'
    '-webkit-background-clip:text;-webkit-text-fill-color:transparent;">PAYCHECK WALLET</h1>'
    '<span style="color:#8B949E;font-size:0.8rem;">Automated profit sweeps · Cold storage income</span>'
    '</div></div>',
    unsafe_allow_html=True,
)

# ── Load State ───────────────────────────────────────────────────────────────
state_path = Path("output/compound_state.json")
if not state_path.exists():
    st.markdown(
        '<div class="glass-card" style="text-align:center;padding:3rem;">'
        '<div style="font-size:2.5rem;margin-bottom:10px;">🏦</div>'
        '<div style="color:#E6EDF3;font-size:1.1rem;font-weight:600;">Paycheck System</div>'
        '<div style="color:#8B949E;font-size:0.85rem;margin-top:6px;">'
        'No compound state yet — the bot needs to run and log profitable trades first.</div>'
        '</div>',
        unsafe_allow_html=True,
    )
    st.stop()

try:
    state = json.loads(state_path.read_text())
except Exception as e:
    st.error(f"Failed to load compound state: {e}")
    st.stop()

# ── Derived Data ─────────────────────────────────────────────────────────────
accumulator = state.get("paycheck_accumulator_usd", 0.0)
total_swept = state.get("total_swept_usd", 0.0)
threshold = 500.0
progress_pct = min(100.0, (accumulator / threshold) * 100) if threshold > 0 else 0

# ── KPI Row ──────────────────────────────────────────────────────────────────
with st.container(horizontal=True):
    st.metric("💰 Total Swept", f"${total_swept:,.2f}", "Lifetime income to cold storage", border=True)
    st.metric("📊 Accumulator", f"${accumulator:,.2f}", f"{progress_pct:.0f}% to next paycheck", border=True)
    st.metric("🎯 Threshold", f"${threshold:,.2f}", "Triggers 50% sweep ($250)", border=True)
    sweep_count = len([t for t in json.loads(Path("output/trades.json").read_text()) if t.get("sweep_triggered")]) if Path("output/trades.json").exists() else 0
    st.metric("📦 Sweeps", str(sweep_count), "Total paycheck events", border=True)

st.markdown('<div style="height:12px;"></div>', unsafe_allow_html=True)

# ── Progress Gauge ───────────────────────────────────────────────────────────
gauge_color = ACCENT if progress_pct >= 80 else (WARNING if progress_pct >= 50 else "#58A6FF")
st.markdown(
    f'<div class="glass-card">'
    f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">'
    f'<span style="color:#484F58;font-size:0.62rem;font-weight:700;text-transform:uppercase;'
    f'letter-spacing:0.1em;">Next Paycheck Progress</span>'
    f'<span style="color:{gauge_color};font-size:0.85rem;font-weight:800;'
    f'font-family:\'JetBrains Mono\',monospace;">{progress_pct:.1f}%</span>'
    f'</div>'
    f'<div style="height:10px;background:rgba(48,54,61,0.5);border-radius:5px;overflow:hidden;">'
    f'<div style="height:100%;width:{progress_pct:.1f}%;background:linear-gradient(90deg,{gauge_color},'
    f'{gauge_color}90);border-radius:5px;transition:width 0.6s ease;"></div>'
    f'</div>'
    f'<div style="display:flex;justify-content:space-between;margin-top:6px;">'
    f'<span style="color:#484F58;font-size:0.6rem;">$0</span>'
    f'<span style="color:#484F58;font-size:0.6rem;">${accumulator:,.2f} / ${threshold:,.2f}</span>'
    f'<span style="color:#484F58;font-size:0.6rem;">${threshold:,.2f}</span>'
    f'</div></div>',
    unsafe_allow_html=True,
)

st.markdown('<div style="height:12px;"></div>', unsafe_allow_html=True)

# ── Sweep History ────────────────────────────────────────────────────────────
trades_path = Path("output/trades.json")
if trades_path.exists():
    try:
        trades = json.loads(trades_path.read_text())
        sweeps = [t for t in trades if t.get("sweep_triggered", False)]

        if sweeps:
            st.markdown("#### 📋 Sweep History")
            rows = []
            for s in reversed(sweeps[-20:]):
                ts = s.get("exit_time", s.get("timestamp", ""))
                if isinstance(ts, (int, float)):
                    ts = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
                else:
                    ts = str(ts)[:16]
                pnl = float(s.get("pnl_usd", 0))
                swept = pnl * 0.5
                rows.append({
                    "Time": ts,
                    "Token": s.get("token_symbol", s.get("symbol", "?")),
                    "Chain": s.get("chain", "").capitalize(),
                    "Trade P&L": f"${pnl:,.2f}",
                    "Swept": f"${swept:,.2f}",
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.markdown(
                '<div class="glass-card" style="text-align:center;padding:2rem;">'
                '<div style="font-size:1.5rem;">📭</div>'
                '<div style="color:#8B949E;font-size:0.85rem;">No sweeps recorded yet</div>'
                '<div style="color:#484F58;font-size:0.72rem;margin-top:4px;">'
                'Sweeps trigger when accumulator reaches $500 from profitable trades</div>'
                '</div>',
                unsafe_allow_html=True,
            )
    except Exception as e:
        st.warning(f"Could not load trades: {e}")
else:
    st.info("No trades recorded yet.")

# ── How It Works ─────────────────────────────────────────────────────────────
with st.expander("ℹ️ How Paycheck Sweeps Work", expanded=False):
    st.markdown("""
**Automated Profit Protection:**

1. Every profitable trade contributes to the **accumulator** pool
2. When the accumulator reaches **$500**, a sweep is triggered
3. **50% ($250)** is moved to Wallet C (cold storage / paycheck)
4. The remaining 50% stays in the trading capital for compounding
5. This ensures consistent income while maintaining growth potential

**Why this matters:** It removes emotion from profit-taking and systematically locks in gains.
""")
