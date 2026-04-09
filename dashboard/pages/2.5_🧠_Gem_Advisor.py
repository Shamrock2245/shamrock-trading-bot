"""
Page 2.5 — 🧠 Gem Advisor — Decision Cockpit

The page you look at to make a trading decision. No cross-referencing
needed — everything actionable is right here:
  1. "Action Now" — Top 3 gems above threshold, ranked by conviction
  2. Watchlist Momentum — Tokens trending UP (improving each scan)
  3. Macro Briefing — Market regime + Fear & Greed at a glance
  4. Recent Reports — Quick access to generated research PDFs
"""

import sys
import os
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import streamlit as st
from datetime import datetime, timezone

from styles import PREMIUM_CSS, ACCENT, CHAIN_COLORS, CHAIN_EMOJI, DANGER, WARNING
from state import (
    get_latest_gems,
    get_positions,
    get_bot_status,
    request_force_scan,
    get_force_scan_request,
    request_manual_buy,
)

st.set_page_config(page_title="Gem Advisor | Shamrock", page_icon="🧠", layout="wide")
st.markdown(PREMIUM_CSS, unsafe_allow_html=True)

# ── Extra CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.advisor-action-card {
    background: linear-gradient(145deg, rgba(0,208,156,0.04), rgba(13,17,23,0.98));
    border: 1px solid rgba(0,208,156,0.25);
    border-radius: 14px;
    padding: 22px 24px;
    margin-bottom: 16px;
    transition: border-color 0.3s, transform 0.2s;
}
.advisor-action-card:hover {
    border-color: rgba(0,208,156,0.5);
    transform: translateY(-1px);
}
.momentum-rising { border-left: 4px solid #00D09C; }
.momentum-falling { border-left: 4px solid #FF4757; }
.momentum-stable { border-left: 4px solid #484F58; }
.momentum-new { border-left: 4px solid #58A6FF; }
.macro-regime-card {
    border-radius: 14px;
    padding: 22px 26px;
    margin-bottom: 18px;
}
.macro-bull { background: linear-gradient(145deg, rgba(0,208,156,0.06), rgba(13,17,23,0.98)); border: 1px solid rgba(0,208,156,0.25); }
.macro-neutral { background: linear-gradient(145deg, rgba(255,184,77,0.06), rgba(13,17,23,0.98)); border: 1px solid rgba(255,184,77,0.25); }
.macro-bear { background: linear-gradient(145deg, rgba(255,71,87,0.06), rgba(13,17,23,0.98)); border: 1px solid rgba(255,71,87,0.25); }
</style>
""", unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        '<div style="display:flex;align-items:center;gap:10px;padding:4px 0 12px;">'
        '<span style="font-size:1.6rem;">☘️</span>'
        '<div>'
        '<div style="color:#E6EDF3;font-size:1.05rem;font-weight:800;letter-spacing:0.04em;">SHAMROCK</div>'
        '<div style="color:#30363D;font-size:0.65rem;font-weight:600;letter-spacing:0.08em;'
        'text-transform:uppercase;">Gem Advisor</div>'
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
        if st.button("🔍 Force Scan Now", key="adv_force_scan", use_container_width=True):
            request_force_scan(reason="gem_advisor_page")
            st.success("✅ Scan queued!")
            st.rerun()

    st.markdown('<hr style="border-color:rgba(48,54,61,0.5);margin:14px 0;">', unsafe_allow_html=True)
    auto_refresh = st.toggle("Auto-refresh", value=True, key="adv_ar")
    refresh_rate = st.select_slider("Interval", options=[10, 15, 30, 60], value=15, key="adv_rate", format_func=lambda x: f"{x}s")

# ── Data ──────────────────────────────────────────────────────────────────────
_BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def _load_json(path, default=None):
    try:
        full = os.path.join(_BASE, path)
        if os.path.exists(full):
            return json.loads(open(full).read())
    except Exception:
        pass
    return default if default is not None else {}

gems = get_latest_gems()
positions = get_positions()
watchlist_data = _load_json("output/watchlist.json", {})
macro_data = _load_json("output/macro_regime.json", {})
adaptive_state = _load_json("output/adaptive_mode_state.json", {})

# De-duplicate gems
seen: dict = {}
for g in gems:
    addr = (g.get("address") or g.get("symbol", "")).lower().strip()
    if not addr:
        continue
    if addr not in seen or g.get("gem_score", 0) > seen[addr].get("gem_score", 0):
        seen[addr] = g
all_gems = sorted(seen.values(), key=lambda x: x.get("gem_score", 0), reverse=True)

# Open position addresses for "already holding" detection
held_addresses = {
    (p.get("address") or p.get("token_address", "")).lower()
    for p in positions if p.get("is_open", False)
}

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown(
    '<div class="page-header">'
    '<div style="display:flex;align-items:center;gap:12px;">'
    '<span style="font-size:1.7rem;">🧠</span>'
    '<div>'
    '<h1>GEM ADVISOR</h1>'
    '<div class="subtitle">Your decision cockpit — what to buy, what to watch, what the market is doing</div>'
    '</div>'
    '</div>'
    '</div>',
    unsafe_allow_html=True,
)

# ═════════════════════════════════════════════════════════════════════════════
# SECTION 1: MACRO BRIEFING
# ═════════════════════════════════════════════════════════════════════════════
st.markdown("### 🌍 Macro Briefing")

regime = macro_data.get("regime", adaptive_state.get("macro_regime", "NEUTRAL"))
multiplier = macro_data.get("score_multiplier", 1.0)
fg_value = macro_data.get("fear_greed_value", 50)
fg_label = macro_data.get("fear_greed_label", "Neutral")
btc_dom = macro_data.get("btc_dominance_signal", "NEUTRAL")
coins = macro_data.get("coins", {})

regime_class = {"BULL": "macro-bull", "BEAR": "macro-bear", "EXTREME_FEAR": "macro-bear"}.get(regime, "macro-neutral")
regime_emoji = {"BULL": "🟢", "BEAR": "🔴", "EXTREME_FEAR": "🔴", "NEUTRAL": "🟡"}.get(regime, "🟡")
regime_color = {"BULL": "#00D09C", "BEAR": "#FF4757", "EXTREME_FEAR": "#FF4757", "NEUTRAL": "#FFB84D"}.get(regime, "#FFB84D")

# FG gauge color
fg_color = "#FF4757" if fg_value < 25 else ("#FFB84D" if fg_value < 45 else ("#00D09C" if fg_value < 75 else "#58A6FF"))

macro_html = (
    f'<div class="{regime_class} macro-regime-card">'
    f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;">'
    f'<div>'
    f'<div style="color:{regime_color};font-size:1.2rem;font-weight:800;">'
    f'{regime_emoji} MARKET REGIME: {regime}</div>'
    f'<div style="color:#484F58;font-size:0.72rem;margin-top:4px;">'
    f'Score multiplier: {multiplier:.2f}× · BTC dominance: {btc_dom}</div>'
    f'</div>'
    f'<div style="text-align:center;">'
    f'<div style="color:{fg_color};font-size:2rem;font-weight:800;font-family:monospace;">{fg_value}</div>'
    f'<div style="color:#484F58;font-size:0.62rem;font-weight:700;text-transform:uppercase;">Fear & Greed</div>'
    f'<div style="color:{fg_color};font-size:0.7rem;font-weight:600;">{fg_label}</div>'
    f'</div>'
    f'</div>'
    f'<div style="display:flex;gap:12px;flex-wrap:wrap;">'
)
for sym, cd in coins.items():
    cr = cd.get("regime", "NEUTRAL")
    chg = cd.get("chg_7d_pct", 0)
    above200 = cd.get("above_ema200", False)
    _sc = "#00D09C" if cr == "BULL" else ("#FF4757" if cr in ("BEAR", "EXTREME_FEAR") else "#FFB84D")
    macro_html += (
        f'<div style="background:rgba(48,54,61,0.3);border-radius:10px;padding:10px 14px;min-width:110px;">'
        f'<div style="color:#E6EDF3;font-size:0.85rem;font-weight:700;">{sym}</div>'
        f'<div style="color:{_sc};font-size:0.92rem;font-weight:700;font-family:monospace;">{chg:+.1f}%</div>'
        f'<div style="color:#8B949E;font-size:0.7rem;">{"✅ Above" if above200 else "❌ Below"} EMA200</div>'
        f'</div>'
    )
macro_html += '</div></div>'
st.markdown(macro_html, unsafe_allow_html=True)

# ═════════════════════════════════════════════════════════════════════════════
# SECTION 2: ACTION NOW — Top Actionable Gems
# ═════════════════════════════════════════════════════════════════════════════
st.markdown("### ⚡ Action Now — Top Gems Ready to Enter")

actionable = [g for g in all_gems if g.get("gem_score", 0) >= 62]

if actionable:
    for i, gem in enumerate(actionable[:5]):
        score = gem.get("gem_score", 0)
        chain = gem.get("chain", "unknown")
        symbol = gem.get("symbol", "???")
        addr = gem.get("address", "")
        price = gem.get("price_usd", 0)
        mcap = gem.get("market_cap", 0)
        liq = gem.get("liquidity_usd", 0)
        vol1h = gem.get("volume_1h", 0)
        vol24h = gem.get("volume_24h", 0)
        timing = gem.get("timing_bp_trend", "flat")
        express = gem.get("express_lane", False)
        is_safe = gem.get("is_safe", False)

        already_held = addr.lower() in held_addresses
        chain_emoji = CHAIN_EMOJI.get(chain, "⬡")
        chain_color = CHAIN_COLORS.get(chain, "#8B949E")
        score_color = "#00D09C" if score >= 75 else ("#FFB84D" if score >= 65 else "#FF4757")
        timing_icon = {"accelerating": "🚀", "decelerating": "📉", "flat": "➡️"}.get(timing, "➡️")
        price_str = f"${price:.8f}" if price < 0.001 else (f"${price:.4f}" if price < 1 else f"${price:,.2f}")

        badge_html = ""
        if express:
            badge_html += '<span style="background:rgba(88,166,255,0.12);color:#58A6FF;font-size:0.6rem;font-weight:700;padding:2px 8px;border-radius:20px;margin-left:6px;">⚡ EXPRESS</span>'
        if gem.get("is_boosted"):
            badge_html += '<span style="background:rgba(255,184,77,0.12);color:#FFB84D;font-size:0.6rem;font-weight:700;padding:2px 8px;border-radius:20px;margin-left:6px;">🚀 BOOSTED</span>'
        if already_held:
            badge_html += '<span style="background:rgba(139,148,158,0.12);color:#8B949E;font-size:0.6rem;font-weight:700;padding:2px 8px;border-radius:20px;margin-left:6px;">📦 HOLDING</span>'

        st.markdown(
            f'<div class="advisor-action-card">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">'
            f'<div style="display:flex;align-items:center;gap:12px;">'
            f'<div style="background:rgba(0,208,156,0.1);color:{score_color};font-size:1.3rem;font-weight:800;'
            f'width:58px;height:58px;border-radius:14px;display:flex;align-items:center;justify-content:center;'
            f'font-family:monospace;border:1px solid {score_color}44;">{score:.0f}</div>'
            f'<div>'
            f'<div style="color:#E6EDF3;font-size:1.15rem;font-weight:800;">${symbol}'
            f'<span style="color:{chain_color};font-size:0.82rem;margin-left:10px;">{chain_emoji} {chain.capitalize()}</span>'
            f'{badge_html}</div>'
            f'<div style="color:#8B949E;font-size:0.78rem;margin-top:4px;">'
            f'{timing_icon} {timing.capitalize()} · {"✅ Safe" if is_safe else "⚠️ Check safety"} · '
            f'{"Score ≥82 → Express Lane" if express else f"Score {score:.0f}/100"}</div>'
            f'</div>'
            f'</div>'
            f'<div style="text-align:right;">'
            f'<div style="color:#E6EDF3;font-size:1.05rem;font-weight:700;font-family:monospace;">{price_str}</div>'
            f'<div style="color:#8B949E;font-size:0.75rem;">MCap ${mcap:,.0f}</div>'
            f'</div>'
            f'</div>'
            f'<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;">'
            f'<div><div style="color:#8B949E;font-size:0.65rem;font-weight:700;text-transform:uppercase;">Liquidity</div>'
            f'<div style="color:#E6EDF3;font-size:0.88rem;font-family:monospace;">${liq:,.0f}</div></div>'
            f'<div><div style="color:#8B949E;font-size:0.65rem;font-weight:700;text-transform:uppercase;">Vol 1h</div>'
            f'<div style="color:#E6EDF3;font-size:0.88rem;font-family:monospace;">${vol1h:,.0f}</div></div>'
            f'<div><div style="color:#8B949E;font-size:0.65rem;font-weight:700;text-transform:uppercase;">Vol 24h</div>'
            f'<div style="color:#E6EDF3;font-size:0.88rem;font-family:monospace;">${vol24h:,.0f}</div></div>'
            f'<div><div style="color:#8B949E;font-size:0.65rem;font-weight:700;text-transform:uppercase;">Δ 1h</div>'
            f'<div style="color:{"#00D09C" if gem.get("price_change_1h",0)>=0 else "#FF4757"};font-size:0.88rem;font-family:monospace;">'
            f'{gem.get("price_change_1h",0):+.1f}%</div></div>'
            f'</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # Quick buy buttons
        if addr and not already_held:
            _bc1, _bc2, _bc3, _bc4 = st.columns([1, 1, 1, 2])
            with _bc1:
                if st.button("🛒 $50", key=f"adv_b50_{i}_{addr[:8]}", use_container_width=True):
                    request_manual_buy(token_address=addr, chain=chain, symbol=symbol,
                                       usd_amount=50.0, wallet="primary", reason="gem_advisor_buy_50")
                    st.success(f"✅ Queued: buy $50 of {symbol}")
                    st.rerun()
            with _bc2:
                if st.button("🛒 $100", key=f"adv_b100_{i}_{addr[:8]}", use_container_width=True):
                    request_manual_buy(token_address=addr, chain=chain, symbol=symbol,
                                       usd_amount=100.0, wallet="primary", reason="gem_advisor_buy_100")
                    st.success(f"✅ Queued: buy $100 of {symbol}")
                    st.rerun()
            with _bc3:
                if st.button("🛒 $250", key=f"adv_b250_{i}_{addr[:8]}", use_container_width=True):
                    request_manual_buy(token_address=addr, chain=chain, symbol=symbol,
                                       usd_amount=250.0, wallet="primary", reason="gem_advisor_buy_250")
                    st.success(f"✅ Queued: buy $250 of {symbol}")
                    st.rerun()
            with _bc4:
                dex_url = gem.get("dex_url", f"https://dexscreener.com/{chain}/{addr}")
                st.markdown(
                    f'<div style="padding-top:6px;">'
                    f'<a href="{dex_url}" target="_blank" style="color:#58A6FF;font-size:0.72rem;text-decoration:none;">'
                    f'🔗 DexScreener →</a> · '
                    f'<span style="color:#484F58;font-size:0.65rem;font-family:monospace;">{addr[:16]}...</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
        st.markdown('<div style="height:4px;"></div>', unsafe_allow_html=True)
else:
    st.markdown(
        '<div class="glass-card" style="text-align:center;padding:2.5rem;">'
        '<div style="font-size:2rem;margin-bottom:8px;">🔍</div>'
        '<div style="color:#8B949E;font-size:1rem;font-weight:600;">No actionable gems right now</div>'
        '<div style="color:#484F58;font-size:0.8rem;margin-top:6px;">'
        'Hit "Force Scan" in the sidebar to trigger a fresh scan, or wait for the next cycle</div>'
        '</div>',
        unsafe_allow_html=True,
    )

# ═════════════════════════════════════════════════════════════════════════════
# SECTION 3: WATCHLIST MOMENTUM
# ═════════════════════════════════════════════════════════════════════════════
st.markdown("### 📈 Watchlist Momentum")
st.markdown(
    '<div style="color:#8B949E;font-size:0.78rem;margin-bottom:12px;">'
    'Tokens being watched for threshold breakthrough. Rising = improving each scan cycle.</div>',
    unsafe_allow_html=True,
)

if watchlist_data:
    wl_entries = []
    for key, entry in watchlist_data.items():
        wl_entries.append(entry)
    wl_entries.sort(key=lambda x: x.get("current_score", 0), reverse=True)

    _wl_c1, _wl_c2, _wl_c3 = st.columns(3)
    with _wl_c1:
        st.metric("Watched", len(wl_entries))
    with _wl_c2:
        rising = sum(1 for e in wl_entries if len(e.get("score_history", [])) >= 2
                     and e.get("score_history", [])[-1][1] > e.get("score_history", [])[-2][1])
        st.metric("📈 Rising", rising)
    with _wl_c3:
        avg_score = sum(e.get("current_score", 0) for e in wl_entries) / max(len(wl_entries), 1)
        st.metric("Avg Score", f"{avg_score:.1f}")

    st.markdown('<div style="height:8px;"></div>', unsafe_allow_html=True)

    for entry in wl_entries[:12]:
        sym = entry.get("symbol", "?")
        chain = entry.get("chain", "")
        curr_score = entry.get("current_score", 0)
        init_score = entry.get("initial_score", 0)
        peak_score = entry.get("peak_score", 0)
        checks = entry.get("check_count", 0)
        age_h = (datetime.now(timezone.utc).timestamp() - entry.get("added_at", 0)) / 3600

        # Determine momentum
        history = entry.get("score_history", [])
        if len(history) >= 2:
            recent = history[-1][1]
            prev = history[-2][1]
            diff = recent - prev
            if diff >= 5:
                momentum = "rising"
            elif diff <= -5:
                momentum = "falling"
            else:
                momentum = "stable"
        else:
            momentum = "new"

        mom_class = f"momentum-{momentum}"
        mom_icon = {"rising": "📈", "falling": "📉", "stable": "➡️", "new": "🆕"}.get(momentum, "")
        score_color = "#00D09C" if curr_score >= 55 else ("#FFB84D" if curr_score >= 40 else "#484F58")
        chain_emoji = CHAIN_EMOJI.get(chain, "⬡")
        delta = curr_score - init_score

        st.markdown(
            f'<div class="glass-card {mom_class}" style="padding:12px 18px;margin-bottom:8px;'
            f'display:flex;justify-content:space-between;align-items:center;">'
            f'<div>'
            f'<span style="color:#E6EDF3;font-size:0.92rem;font-weight:700;">{sym}</span>'
            f'<span style="color:#8B949E;font-size:0.78rem;margin-left:10px;">'
            f'{chain_emoji} {chain.capitalize()} · {checks} checks · {age_h:.1f}h</span>'
            f'</div>'
            f'<div style="display:flex;align-items:center;gap:14px;">'
            f'<span style="color:{score_color};font-size:0.95rem;font-weight:800;font-family:monospace;">'
            f'{curr_score:.0f}</span>'
            f'<span style="color:{"#00D09C" if delta >= 0 else "#FF4757"};font-size:0.8rem;font-family:monospace;">'
            f'{delta:+.0f}</span>'
            f'<span style="font-size:0.82rem;">{mom_icon}</span>'
            f'</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
else:
    st.markdown(
        '<div class="glass-card" style="text-align:center;padding:2rem;">'
        '<div style="font-size:1.5rem;margin-bottom:6px;">👁️</div>'
        '<div style="color:#8B949E;">No tokens on watchlist — near-miss gems will appear here</div>'
        '</div>',
        unsafe_allow_html=True,
    )

# ═════════════════════════════════════════════════════════════════════════════
# SECTION 4: RECENT RESEARCH REPORTS
# ═════════════════════════════════════════════════════════════════════════════
st.markdown("### 📄 Recent Research Reports")

reports_dir = os.path.join(_BASE, "output", "reports")
reports = []
if os.path.exists(reports_dir):
    for fname in sorted(os.listdir(reports_dir), reverse=True):
        if fname.endswith(".json"):
            try:
                with open(os.path.join(reports_dir, fname)) as f:
                    data = json.load(f)
                pdf_name = fname.replace(".json", ".pdf")
                pdf_path = os.path.join(reports_dir, pdf_name)
                reports.append({
                    "symbol": data.get("symbol", "?"),
                    "chain": data.get("chain", "?"),
                    "score": data.get("gem_score", 0),
                    "verdict": data.get("verdict", "?"),
                    "generated_at": data.get("generated_at", ""),
                    "pdf_path": pdf_path if os.path.exists(pdf_path) else None,
                })
                if len(reports) >= 10:
                    break
            except Exception:
                continue

if reports:
    for idx, rpt in enumerate(reports):
        _v_color = {"STRONG BUY": "#00D09C", "BUY": "#00D09C", "WATCHLIST": "#FFB84D",
                     "AVOID": "#FF4757", "UNSCORED": "#484F58"}.get(rpt["verdict"], "#8B949E")
        st.markdown(
            f'<div class="glass-card" style="padding:10px 14px;margin-bottom:6px;'
            f'display:flex;justify-content:space-between;align-items:center;">'
            f'<div>'
            f'<span style="color:#E6EDF3;font-size:0.82rem;font-weight:700;">{rpt["symbol"]}</span>'
            f'<span style="color:#484F58;font-size:0.68rem;margin-left:8px;">'
            f'{CHAIN_EMOJI.get(rpt["chain"], "⬡")} {rpt["chain"].capitalize()}</span>'
            f'</div>'
            f'<div style="display:flex;align-items:center;gap:12px;">'
            f'<span style="color:#8B949E;font-size:0.68rem;">{rpt["generated_at"]}</span>'
            f'<span style="background:{_v_color}22;color:{_v_color};font-size:0.62rem;font-weight:700;'
            f'padding:2px 10px;border-radius:20px;border:1px solid {_v_color}44;">{rpt["verdict"]}</span>'
            f'<span style="color:#58A6FF;font-size:0.75rem;font-weight:800;font-family:monospace;">'
            f'{rpt["score"]:.0f}</span>'
            f'</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        if rpt["pdf_path"]:
            with open(rpt["pdf_path"], "rb") as pdf_f:
                st.download_button(
                    f"⬇️ Download {rpt['symbol']} Report",
                    data=pdf_f.read(),
                    file_name=os.path.basename(rpt["pdf_path"]),
                    mime="application/pdf",
                    key=f"adv_dl_{idx}_{rpt['symbol']}",
                )
else:
    st.markdown(
        '<div class="glass-card" style="text-align:center;padding:2rem;">'
        '<div style="font-size:1.5rem;margin-bottom:6px;">📄</div>'
        '<div style="color:#8B949E;">No reports generated yet — use the "📄 Research Report" '
        'button on the Gem Scanner page</div>'
        '</div>',
        unsafe_allow_html=True,
    )

# ── Auto-refresh ──────────────────────────────────────────────────────────────
if auto_refresh:
    st.markdown(
        f'<script>setTimeout(()=>window.location.reload(),{refresh_rate*1000});</script>',
        unsafe_allow_html=True,
    )
