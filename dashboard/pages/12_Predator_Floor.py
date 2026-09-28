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

# ── Paper Campaign Promotion Progress (Gate: >=50 closes, WR>=50%, PF>=1.30) ──
pm = pred.get("paper_metrics") or {}
if pm:
    st.markdown("### 🎯 Paper Promote Gate Progress (≥50 closes, WR ≥50%, PF ≥1.30)")
    pg1, pg2, pg3, pg4 = st.columns(4)
    closes_cnt = pm.get("closed_trades", 0)
    wr_val = pm.get("win_rate", 0.0) * 100.0
    pf_val = pm.get("profit_factor", 0.0)
    mfe_cap = pm.get("mfe_capture_ratio_pct")

    pg1.metric("Paper Closes", f"{closes_cnt} / 50", f"{'✅ Ready' if closes_cnt >= 50 else f'{50 - closes_cnt} to go'}")
    pg2.metric("Paper Win Rate", f"{wr_val:.1f}%", f"{'✅ Passed' if wr_val >= 50.0 else 'Under 50%'}")
    pg3.metric("Profit Factor", f"{pf_val:.2f}", f"{'✅ Passed' if pf_val >= 1.30 else 'Under 1.30'}")
    pg4.metric("MFE Capture Rate", f"{mfe_cap:.1f}%" if mfe_cap is not None else "—", "Realized / Peak MFE")

# ── Predator Sniper Deny Telemetry ──────────────────────────────────────────
deny = pred.get("deny_stats") or {}
if deny and deny.get("evaluations", 0) > 0:
    st.markdown("### 🛡️ Predator Guard Telemetry")
    d1, d2, d3 = st.columns(3)
    d1.metric("Evaluations", f"{deny.get('evaluations', 0)}")
    d2.metric("Denied Entries", f"{deny.get('denied', 0)}", f"{deny.get('deny_rate_pct', 0):.1f}% rate")
    d3.metric("Allowed Entries", f"{deny.get('allowed', 0)}")
    reasons = deny.get("reasons") or {}
    if reasons:
        st.caption("Deny breakdown: " + " · ".join(f"**{k}**: {v}" for k, v in sorted(reasons.items(), key=lambda x: -x[1])))

# Paper lock banner — Predator never unlocks live.
if os.getenv("PAPER_MODE_LOCKED", "true").lower() == "true":
    st.info("PAPER_MODE_LOCKED=true — Predator v1 is running in paper only.")

h1, h2 = st.columns(2)
with h1:
    st.markdown("**Allowlist (hunt)**")
    st.write(", ".join(pred.get("allowlist") or []) or "—")
with h2:
    st.markdown("**Ban hammer**")
    st.write(", ".join(pred.get("hard_ban") or []) or "—")

st.markdown("**Last 20 sprites**")
sprites = []
for t in recent:
    try:
        pnl = float(t.get("pnl") or t.get("pnl_usd") or t.get("realized_pnl") or 0)
    except (TypeError, ValueError):
        pnl = 0.0
    sprites.append("\U0001F7E9" if pnl > 0 else ("\U0001F7E5" if pnl < 0 else "\u2B1C"))
st.write(" ".join(sprites) or "—")
