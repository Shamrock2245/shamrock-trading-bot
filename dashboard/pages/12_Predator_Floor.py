"""Page — Predator Floor. One arcade screen. Sit chop. Hunt expansion."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st

from styles import PREMIUM_CSS, DANGER
from nav import render_nav
from state import (
    get_bot_status,
    get_hl_scanner_state,
    get_positions,
    get_trades,
)

try:
    from state import get_predator_state
except ImportError:
    def get_predator_state():
        return {}

st.set_page_config(page_title="Predator Floor | Shamrock", page_icon="\U0001F3AE", layout="wide")
st.markdown(PREMIUM_CSS, unsafe_allow_html=True)
render_nav("Predator Floor")

pred = get_predator_state() or {}
hl = get_hl_scanner_state() or {}
status = get_bot_status() or {}
trades = get_trades() or []
positions = get_positions() or []

enabled = bool(pred.get("enabled"))
last = pred.get("last") or {}
regime = (last.get("regime") or hl.get("regime") or status.get("regime") or "UNKNOWN")
regime_u = str(regime).upper()
if regime_u in ("TRENDING", "EXPANSION", "TREND", "BULL", "NORMAL"):
    regime_color, regime_label, vibe = "#00FFB8", "EXPANSION", "HUNT"
elif regime_u in ("CHOPPY", "CHOP", "RANGE", "DEAD"):
    regime_color, regime_label, vibe = "#FFB84D", "CHOP", "SIT ON HANDS"
elif regime_u in ("NUKE", "CRASH", "BEAR"):
    regime_color, regime_label, vibe = "#FF4757", "NUKE", "NO KNIVES"
else:
    regime_color, regime_label, vibe = "#8B949E", regime_u, "NO EDGE"

recent = trades[-20:]
hits = misses = 0
pnl_sum = 0.0
for t in recent:
    try:
        pnl = float(t.get("pnl") or t.get("pnl_usd") or t.get("realized_pnl") or 0)
    except (TypeError, ValueError):
        pnl = 0.0
    pnl_sum += pnl
    if pnl > 0:
        hits += 1
    elif pnl < 0:
        misses += 1

combo = 0
for t in reversed(recent):
    try:
        pnl = float(t.get("pnl") or t.get("pnl_usd") or t.get("realized_pnl") or 0)
    except (TypeError, ValueError):
        pnl = 0.0
    if pnl > 0:
        combo += 1
    else:
        break

st.markdown(
    f"""
<div class='section-header'>
    <span class='section-icon'>\U0001F3AE</span>
    <h2>Predator Floor</h2>
    <div class='pulse-indicator'>{'ARMED' if enabled else 'FLAG OFF'}</div>
</div>
<p style="color:#8B949E; font-size:0.8rem; margin-top:-10px; margin-bottom:18px;">
    Expansion only. Allowlist only. Chop is not a trade.
</p>
""",
    unsafe_allow_html=True,
)
st.markdown(
    f"""
<div style="border:1px solid {regime_color}55; background:linear-gradient(180deg, {regime_color}14, #0D1117);
            border-radius:18px; padding:28px 24px; margin-bottom:18px; text-align:center;">
  <div style="font-size:0.72rem; letter-spacing:0.22em; color:#8B949E; font-weight:700;">REGIME</div>
  <div style="font-size:3.2rem; font-weight:900; color:{regime_color};">{regime_label}</div>
  <div style="font-size:1.05rem; color:#E6EDF3; font-weight:700;">{vibe}</div>
</div>
""",
    unsafe_allow_html=True,
)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Flag", "ON" if enabled else "OFF")
c2.metric("Last 20 heat", f"${pnl_sum:,.2f}", f"{hits}W / {misses}L")
c3.metric("Combo", f"{combo} clean hits")
c4.metric("Open risk slots", f"{len(positions)}")
blocked = pred.get("last_block") or {}
st.write(f"Last call: {last.get('coin') or '—'} · {last.get('reason') or '—'}")
st.write(f"Last hammer: {blocked.get('coin') or '—'} · {blocked.get('reason') or 'quiet'}")
"}, {