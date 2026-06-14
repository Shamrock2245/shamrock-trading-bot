"""
dashboard/pages/7_🎯_Sniper_Wallets.py — Shamrock Trading Bot
Microcap Sniper Wallet Leaderboard & Capital Compounding Dashboard

Shows:
  - Discovered high-PnL sniper wallets ranked by composite score
  - Live copy-trade signal feed from tracked snipers
  - Manual add/remove wallet controls
  - Capital compounding loop status (phases, milestones, sweeps)
  - Moralis endpoint utilization summary
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Path setup (must precede dashboard-level imports)
# ─────────────────────────────────────────────────────────────────────────────
_DASHBOARD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ROOT = str(Path(__file__).resolve().parent.parent.parent)
for _p in [_DASHBOARD_DIR, _ROOT]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import streamlit as st

from styles import PREMIUM_CSS
from nav import render_nav

st.set_page_config(
    page_title="🎯 Sniper Wallets — Shamrock",
    page_icon="🎯",
    layout="wide",
)

# ─────────────────────────────────────────────────────────────────────────────
# Imports
# ─────────────────────────────────────────────────────────────────────────────
try:
    from core.sniper_discovery import (
        load_leaderboard,
        add_wallet_manually,
        remove_wallet,
        get_leaderboard_stats,
        get_daemon,
        LEADERBOARD_FILE,
        DISCOVERY_LOG_FILE,
        ACTIVE_SNIPERS_FILE,
    )
    _SNIPER_AVAILABLE = True
except Exception as _e:
    _SNIPER_AVAILABLE = False
    _SNIPER_ERR = str(_e)

try:
    from core.capital_compounder import get_compound_summary, COMPOUND_PHASES
    _COMPOUNDER_AVAILABLE = True
except Exception as _ce:
    _COMPOUNDER_AVAILABLE = False

try:
    from core.moralis_streams import MoralisStreamsServer
    from core.moralis_streams_manager import MoralisStreamsManager
    _STREAMS_AVAILABLE = True
except Exception:
    _STREAMS_AVAILABLE = False

# ─────────────────────────────────────────────────────────────────────────────
# Styles
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.sniper-card {
    background: linear-gradient(135deg, #0f2027, #203a43, #2c5364);
    border: 1px solid #00ff88;
    border-radius: 10px;
    padding: 16px;
    margin-bottom: 10px;
}
.sniper-score-high { color: #00ff88; font-weight: bold; font-size: 1.3em; }
.sniper-score-med  { color: #ffd700; font-weight: bold; font-size: 1.3em; }
.sniper-score-low  { color: #ff6b6b; font-weight: bold; font-size: 1.3em; }
.phase-badge {
    display: inline-block;
    padding: 4px 12px;
    border-radius: 20px;
    font-weight: bold;
    font-size: 0.9em;
}
.phase-seed       { background: #2c3e50; color: #bdc3c7; }
.phase-growth     { background: #1a5276; color: #85c1e9; }
.phase-aggressive { background: #1e8449; color: #a9dfbf; }
.phase-predator   { background: #7d3c98; color: #d7bde2; }
.phase-apex       { background: #b7950b; color: #f9e79f; }
.milestone-hit    { color: #00ff88; }
.milestone-next   { color: #ffd700; }
.stat-box {
    background: rgba(0,255,136,0.08);
    border: 1px solid rgba(0,255,136,0.3);
    border-radius: 8px;
    padding: 12px;
    text-align: center;
}
</style>
""", unsafe_allow_html=True)
st.markdown(PREMIUM_CSS, unsafe_allow_html=True)
render_nav("Sniper")

# ─────────────────────────────────────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("# 🎯 Microcap Sniper Wallets")
st.markdown(
    "Proactively discovered high-PnL wallets that consistently snipe microcap gems early. "
    "Powered by **Moralis profitability/summary**, **wallet stats**, and **top-traders** endpoints."
)

if not _SNIPER_AVAILABLE:
    st.error(f"Sniper Discovery module not available: {_SNIPER_ERR}")
    st.stop()

# ─────────────────────────────────────────────────────────────────────────────
# Auto-refresh
# ─────────────────────────────────────────────────────────────────────────────
auto_refresh = st.sidebar.checkbox("Auto-refresh (30s)", value=True)
if auto_refresh:
    time.sleep(0.1)
    st.rerun() if st.session_state.get("_sniper_refresh_counter", 0) % 60 == 0 else None
    st.session_state["_sniper_refresh_counter"] = (
        st.session_state.get("_sniper_refresh_counter", 0) + 1
    )

# ─────────────────────────────────────────────────────────────────────────────
# Tab layout
# ─────────────────────────────────────────────────────────────────────────────
tab_leaderboard, tab_compounder, tab_add, tab_moralis, tab_streams = st.tabs([
    "🏆 Leaderboard",
    "💰 Capital Compounder",
    "➕ Add / Remove Wallets",
    "📡 Moralis Utilization",
    "⚡ Streams Health",
])

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1: LEADERBOARD
# ═══════════════════════════════════════════════════════════════════════════════
with tab_leaderboard:
    stats = get_leaderboard_stats()
    wallets = load_leaderboard()

    # Summary row
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.markdown(
            f'<div class="stat-box"><div style="font-size:1.8em;font-weight:bold;">'
            f'{stats["total_tracked"]}</div><div>Tracked Wallets</div></div>',
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            f'<div class="stat-box"><div style="font-size:1.8em;font-weight:bold;color:#00ff88;">'
            f'{stats["active"]}</div><div>Active (Copy-Trade)</div></div>',
            unsafe_allow_html=True,
        )
    with col3:
        st.markdown(
            f'<div class="stat-box"><div style="font-size:1.8em;font-weight:bold;">'
            f'{stats["avg_win_rate"]:.1f}%</div><div>Avg Win Rate</div></div>',
            unsafe_allow_html=True,
        )
    with col4:
        st.markdown(
            f'<div class="stat-box"><div style="font-size:1.8em;font-weight:bold;">'
            f'${stats["total_pnl_tracked"]:,.0f}</div><div>Total PnL Tracked</div></div>',
            unsafe_allow_html=True,
        )
    with col5:
        copy_win_rate = (
            stats["copy_signals_profitable"] / max(stats["copy_signals_total"], 1) * 100
        )
        st.markdown(
            f'<div class="stat-box"><div style="font-size:1.8em;font-weight:bold;">'
            f'{copy_win_rate:.0f}%</div><div>Copy Signal Win Rate</div></div>',
            unsafe_allow_html=True,
        )

    st.divider()

    if not wallets:
        st.info(
            "No snipers discovered yet. The discovery daemon runs every 6 hours, "
            "harvesting top traders from your best recent gems. "
            "You can also manually add known whale wallets using the **Add / Remove** tab."
        )
    else:
        # Filter controls
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            show_active_only = st.checkbox("Active only", value=False)
        with col_f2:
            min_score = st.slider("Min sniper score", 0, 100, 0)
        with col_f3:
            chain_filter = st.selectbox(
                "Chain", ["All"] + list({w.chain for w in wallets})
            )

        filtered = wallets
        if show_active_only:
            filtered = [w for w in filtered if w.is_active]
        if min_score > 0:
            filtered = [w for w in filtered if w.sniper_score >= min_score]
        if chain_filter != "All":
            filtered = [w for w in filtered if w.chain == chain_filter]

        st.markdown(f"**{len(filtered)} wallets** matching filters")

        for i, wallet in enumerate(filtered, 1):
            score = wallet.sniper_score
            score_class = (
                "sniper-score-high" if score >= 70
                else "sniper-score-med" if score >= 50
                else "sniper-score-low"
            )
            active_badge = "🟢 ACTIVE" if wallet.is_active else "⚪ INACTIVE"
            chain_emoji = {
                "solana": "◎", "ethereum": "Ξ", "base": "🔵",
                "bsc": "🟡", "arbitrum": "🔷",
            }.get(wallet.chain, "⛓")

            with st.expander(
                f"#{i} {chain_emoji} {wallet.alias or wallet.address[:12]}...  "
                f"Score: {score:.1f}  |  Win Rate: {wallet.win_rate*100:.0f}%  "
                f"|  PnL: ${wallet.total_realized_pnl_usd:,.0f}  |  {active_badge}",
                expanded=(i <= 3),
            ):
                col_a, col_b, col_c = st.columns(3)
                with col_a:
                    st.markdown(f"**Address:** `{wallet.address}`")
                    st.markdown(f"**Chain:** {wallet.chain.upper()}")
                    st.markdown(f"**Discovery:** {wallet.discovery_source}")
                    st.markdown(f"**First Seen:** {wallet.first_seen[:10] if wallet.first_seen else 'N/A'}")
                with col_b:
                    st.markdown(f"**Win Rate:** {wallet.win_rate*100:.1f}%")
                    st.markdown(f"**Avg ROI:** {wallet.avg_roi_pct:.1f}%")
                    st.markdown(f"**Total PnL:** ${wallet.total_realized_pnl_usd:,.2f}")
                    st.markdown(f"**Total Trades:** {wallet.total_trades}")
                with col_c:
                    st.markdown(f"**Microcap Focus:** {wallet.microcap_focus_score:.0f}/100")
                    st.markdown(f"**Active Chains:** {', '.join(wallet.active_chains) or wallet.chain}")
                    st.markdown(f"**Copy Signals:** {wallet.copy_signals_generated}")
                    st.markdown(f"**Copy Win Rate:** "
                        f"{wallet.copy_signals_profitable}/{wallet.copy_signals_generated}")
                if wallet.top_tokens:
                    st.markdown(f"**Top Tokens:** {', '.join(wallet.top_tokens)}")

                # Action buttons
                btn_col1, btn_col2, btn_col3 = st.columns([1, 1, 3])
                with btn_col1:
                    toggle_label = "⏸ Deactivate" if wallet.is_active else "▶ Activate"
                    if st.button(toggle_label, key=f"toggle_{wallet.address}"):
                        all_wallets = load_leaderboard()
                        for w in all_wallets:
                            if w.address == wallet.address:
                                w.is_active = not w.is_active
                        from core.sniper_discovery import save_leaderboard, save_active_snipers
                        save_leaderboard(all_wallets)
                        save_active_snipers(all_wallets)
                        st.success(f"{'Activated' if not wallet.is_active else 'Deactivated'} {wallet.address[:10]}...")
                        st.rerun()
                with btn_col2:
                    if st.button("🗑 Remove", key=f"remove_{wallet.address}"):
                        result = remove_wallet(wallet.address)
                        if result["success"]:
                            st.success(result["message"])
                            st.rerun()
                        else:
                            st.error(result["error"])

    # Discovery log
    st.divider()
    st.markdown("### 📋 Discovery Log")
    if DISCOVERY_LOG_FILE.exists():
        try:
            with open(DISCOVERY_LOG_FILE) as f:
                log = json.load(f)
            log_reversed = list(reversed(log[-20:]))
            for entry in log_reversed:
                ts = entry.get("timestamp", "")[:16]
                etype = entry.get("type", "")
                if etype == "cycle_complete":
                    st.markdown(
                        f"`{ts}` — Cycle complete: "
                        f"{entry.get('candidates_harvested', 0)} candidates → "
                        f"{entry.get('new_snipers_found', 0)} new snipers "
                        f"({entry.get('new_snipers_promoted', 0)} promoted) | "
                        f"{entry.get('elapsed_seconds', 0):.0f}s"
                    )
                elif etype == "manual_add":
                    st.markdown(
                        f"`{ts}` — Manual add: `{entry.get('address', '')[:12]}...` "
                        f"on {entry.get('chain', '')} | score={entry.get('score', 0):.1f}"
                    )
        except Exception:
            st.info("No discovery log yet.")
    else:
        st.info("Discovery log will appear after the first cycle completes.")

    # Manual trigger
    col_t1, col_t2 = st.columns([1, 4])
    with col_t1:
        if st.button("🔄 Trigger Discovery Now", type="primary"):
            with st.spinner("Running discovery cycle... (may take 1-2 minutes)"):
                try:
                    daemon = get_daemon()
                    result = daemon.trigger_now()
                    st.success(
                        f"Discovery complete: {result.get('new_snipers_found', 0)} new snipers found, "
                        f"{result.get('new_snipers_promoted', 0)} promoted to active tracking"
                    )
                    st.rerun()
                except Exception as e:
                    st.error(f"Discovery error: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2: CAPITAL COMPOUNDER
# ═══════════════════════════════════════════════════════════════════════════════
with tab_compounder:
    if not _COMPOUNDER_AVAILABLE:
        st.warning("Capital Compounder module not available.")
    else:
        summary = get_compound_summary()

        # Phase badge
        phase_name = summary["current_phase"]
        phase_class = f"phase-{phase_name.lower()}"
        st.markdown(
            f'<div style="margin-bottom:16px;">'
            f'<span class="phase-badge {phase_class}">⚡ {phase_name.upper()} PHASE</span>'
            f'&nbsp;&nbsp;<span style="color:#aaa;">{summary["phase_description"]}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # Capital overview
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric(
                "Current Capital",
                f"${summary['current_capital_usd']:,.2f}",
                delta=f"+${summary['total_realized_pnl_usd']:,.2f} total PnL",
            )
        with col2:
            st.metric(
                "Total Return",
                f"{summary['total_return_pct']:+.1f}%",
                delta=f"Peak: ${summary['peak_capital_usd']:,.0f}",
            )
        with col3:
            st.metric(
                "Swept to Cold (Wallet C)",
                f"${summary['total_swept_to_cold_usd']:,.2f}",
                delta="Locked profits",
            )
        with col4:
            st.metric(
                "Today's PnL",
                f"${summary['daily_pnl_usd']:+,.2f}",
                delta=f"{summary['daily_win_rate_pct']:.0f}% win rate ({summary['daily_trades']} trades)",
            )

        st.divider()

        # Phase progression
        st.markdown("### 📈 Compounding Phases")
        for phase in COMPOUND_PHASES:
            is_current = phase.name == phase_name
            is_completed = summary["current_capital_usd"] >= phase.max_capital_usd
            icon = "✅" if is_completed else ("▶" if is_current else "○")
            color = "#00ff88" if is_current else ("#888" if not is_completed else "#ffd700")
            st.markdown(
                f'<div style="color:{color};margin:4px 0;">'
                f'{icon} <b>{phase.name}</b> — '
                f'${phase.min_capital_usd:,.0f}–{"∞" if phase.max_capital_usd == float("inf") else f"${phase.max_capital_usd:,.0f}"} | '
                f'Max position: ${phase.max_position_usd:,.0f} | '
                f'Base size: {phase.base_position_pct:.0f}% | '
                f'Sweep: {phase.sweep_pct:.0f}%'
                f'</div>',
                unsafe_allow_html=True,
            )

        st.divider()

        # Milestone tracker
        st.markdown("### 🏆 Milestone Tracker")
        milestones_hit = summary.get("milestones_hit", [])
        next_milestone = summary.get("next_milestone_usd")
        progress = summary.get("progress_to_next_milestone_pct", 0)

        milestone_targets = [10_000, 25_000, 50_000, 100_000, 250_000,
                             500_000, 1_000_000, 2_500_000, 5_000_000, 10_000_000]
        cols = st.columns(5)
        for i, m in enumerate(milestone_targets):
            with cols[i % 5]:
                hit = m in milestones_hit
                is_next = m == next_milestone
                icon = "🏆" if hit else ("🎯" if is_next else "○")
                color = "#00ff88" if hit else ("#ffd700" if is_next else "#555")
                label = f"${m/1000:.0f}k" if m < 1_000_000 else f"${m/1_000_000:.1f}M"
                st.markdown(
                    f'<div style="text-align:center;color:{color};">'
                    f'{icon}<br><b>{label}</b></div>',
                    unsafe_allow_html=True,
                )

        if next_milestone:
            # Ensure progress is between 0 and 100
            safe_progress = max(0, min(100, int(progress)))
            st.progress(
                safe_progress,
                text=f"Progress to next milestone (${next_milestone:,.0f}): {progress:.1f}%",
            )

        st.divider()

        # Current phase settings
        st.markdown("### ⚙️ Current Phase Settings")
        col_s1, col_s2, col_s3 = st.columns(3)
        with col_s1:
            st.info(f"**Max Position Size**\n\n${summary['current_max_position_usd']:,.0f} per trade")
        with col_s2:
            st.info(f"**Offensive Max**\n\n${summary['current_offensive_max_usd']:,.0f} (win-streak boost)")
        with col_s3:
            st.info(f"**Base Position %**\n\n{summary['current_base_position_pct']:.0f}% of capital")

        # Recent sweeps
        st.divider()
        st.markdown("### 💰 Recent Profit Sweeps → Wallet C")
        sweep_log = summary.get("sweep_log", [])
        if sweep_log:
            for sweep in reversed(sweep_log[-10:]):
                ts = sweep.get("timestamp", "")[:16]
                st.markdown(
                    f"`{ts}` — **${sweep['amount_usd']:,.2f}** swept | "
                    f"Reason: {sweep['reason']} | "
                    f"Capital at sweep: ${sweep['capital_at_sweep']:,.0f}"
                )
        else:
            st.info(
                "No sweeps yet. Sweeps trigger when daily PnL exceeds $500 "
                "or a capital milestone is crossed."
            )


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3: ADD / REMOVE WALLETS
# ═══════════════════════════════════════════════════════════════════════════════
with tab_add:
    st.markdown("### ➕ Add a Wallet to Sniper Tracking")
    st.markdown(
        "Manually add a known high-PnL wallet. The system will immediately score it "
        "using Moralis profitability endpoints and add it to the live copy-trade pool."
    )

    with st.form("add_wallet_form"):
        wallet_address = st.text_input(
            "Wallet Address",
            placeholder="0x... or Solana base58 address",
        )
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            wallet_chain = st.selectbox(
                "Chain",
                ["ethereum", "base", "bsc", "arbitrum", "polygon", "solana"],
            )
        with col_f2:
            wallet_alias = st.text_input(
                "Alias (optional)",
                placeholder="e.g. Dragon Wallet #1",
            )
        submitted = st.form_submit_button("Add Wallet", type="primary")

    if submitted and wallet_address:
        with st.spinner(f"Scoring {wallet_address[:12]}... via Moralis..."):
            result = add_wallet_manually(
                address=wallet_address,
                chain=wallet_chain,
                alias=wallet_alias,
            )
        if result["success"]:
            w = result["wallet"]
            st.success(result["message"])
            st.json({
                "sniper_score": w["sniper_score"],
                "win_rate": f"{w['win_rate']*100:.1f}%",
                "total_pnl_usd": f"${w['total_realized_pnl_usd']:,.2f}",
                "avg_roi_pct": f"{w['avg_roi_pct']:.1f}%",
                "total_trades": w["total_trades"],
                "microcap_focus": w["microcap_focus_score"],
                "is_active": w["is_active"],
            })
        else:
            st.error(result["error"])

    st.divider()
    st.markdown("### 🗑 Remove a Wallet")
    wallets_for_remove = load_leaderboard()
    if wallets_for_remove:
        remove_options = {
            f"{w.alias or w.address[:12]}... ({w.chain}) — score {w.sniper_score:.1f}": w.address
            for w in wallets_for_remove
        }
        selected_label = st.selectbox("Select wallet to remove", list(remove_options.keys()))
        if st.button("Remove Selected Wallet", type="secondary"):
            addr = remove_options[selected_label]
            result = remove_wallet(addr)
            if result["success"]:
                st.success(result["message"])
                st.rerun()
            else:
                st.error(result["error"])
    else:
        st.info("No wallets tracked yet.")

    st.divider()
    st.markdown("### 🔄 Refresh All Wallet Scores")
    st.markdown(
        "Re-score all tracked wallets with fresh Moralis data. "
        "Useful after a few days to update win rates and PnL."
    )
    if st.button("Refresh All Scores"):
        with st.spinner("Refreshing scores via Moralis..."):
            try:
                from core.sniper_discovery import refresh_wallet_scores
                count = refresh_wallet_scores()
                st.success(f"Refreshed {count} wallet scores")
                st.rerun()
            except Exception as e:
                st.error(f"Refresh error: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 4: MORALIS UTILIZATION
# ═══════════════════════════════════════════════════════════════════════════════
with tab_moralis:
    st.markdown("### 📡 Moralis Subscription Utilization")
    st.markdown(
        "Full inventory of Moralis endpoints used across the bot. "
        "Green = actively used. Yellow = used but could be expanded. "
        "Red = paid for but not yet used."
    )

    endpoint_table = [
        # (Endpoint, Module, Status, Purpose)
        ("GET /erc20/{token}/top-traders", "moralis_intelligence.py + sniper_discovery.py", "🟢 ACTIVE", "Harvest sniper candidates from gems + per-token scoring"),
        ("GET /token/{network}/{token}/top-holders", "moralis_solana.py + sniper_discovery.py", "🟢 ACTIVE", "Solana sniper candidate harvest"),
        ("GET /wallets/{addr}/profitability/summary", "sniper_discovery.py", "🟢 ACTIVE", "Win rate, total PnL, avg ROI for sniper scoring"),
        ("GET /wallets/{addr}/profitability", "sniper_discovery.py", "🟢 ACTIVE", "Per-token PnL breakdown, microcap focus detection"),
        ("GET /wallets/{addr}/stats", "sniper_discovery.py + moralis_wallet.py", "🟢 ACTIVE", "Trade count, token transfers, activity level"),
        ("GET /wallets/{addr}/chains", "sniper_discovery.py", "🟢 ACTIVE", "Multi-chain activity detection"),
        ("GET /wallets/{addr}/history", "sniper_discovery.py", "🟢 ACTIVE", "Early-entry pattern analysis"),
        ("GET /wallets/{addr}/net-worth", "moralis_wallet.py", "🟢 ACTIVE", "Our own wallet net worth tracking"),
        ("GET /wallets/{addr}/tokens", "moralis_wallet.py", "🟢 ACTIVE", "Our own wallet token balances"),
        ("GET /wallets/{addr}/swaps", "wallet_monitor.py", "🟢 ACTIVE", "Real-time swap detection for copy-trading"),
        ("GET /tokens/trending", "moralis_money.py", "🟢 ACTIVE", "Trending token discovery"),
        ("GET /tokens/top-gainers", "moralis_money.py", "🔄 MIGRATED", "Removed Jun 4 2026 — now /tokens/trending sorted by 1h price change"),
        ("GET /tokens/top-losers", "moralis_money.py", "🔄 MIGRATED", "Removed Jun 4 2026 — now /tokens/trending sorted ascending by 1h change"),
        ("GET /tokens/buying-pressure", "moralis_money.py", "🟢 ACTIVE", "Rising buy:sell ratio detection"),
        ("POST /tokens/search", "moralis_money.py", "🟢 ACTIVE", "Smart money filtered tokens ($75k+ liq, 15+ exp buyers)"),
        ("POST /tokens/search (whale)", "moralis_money.py", "🟢 ACTIVE", "Net experienced buyers — strongest whale signal"),
        ("Moralis Streams Webhook", "moralis_streams.py", "🟢 ACTIVE", "Push-based real-time swap events (no polling lag)"),
        ("GET /token/{addr}/price", "moralis_intelligence.py", "🟢 ACTIVE", "Token price enrichment"),
        ("GET /token/{addr}/analytics", "moralis_intelligence.py", "🟢 ACTIVE", "Holder growth, whale score"),
        ("GET /token/{addr}/snipers", "moralis_solana.py", "🔄 MIGRATED", "Removed Jun 4 2026 — now uses /wallets/{addr}/swaps convergence detection"),
        ("GET /token/{addr}/top-holders", "moralis_solana.py", "🟢 ACTIVE", "Holder concentration analysis"),
        ("GET /wallets/{addr}/profitability (Solana)", "moralis_solana.py", "🟡 PARTIAL", "Solana wallet PnL — used for top holders only"),
        ("GET /nft/{addr}/trades", "—", "🔴 UNUSED", "NFT trade history — not relevant to our strategy"),
        ("GET /blocks/{block}/stats", "—", "🔴 UNUSED", "Block statistics — not needed"),
    ]

    # Color-coded table
    for endpoint, module, status, purpose in endpoint_table:
        color = "#00ff88" if "🟢" in status else ("#ffd700" if "🟡" in status else "#ff6b6b")
        st.markdown(
            f'<div style="border-left:3px solid {color};padding:6px 12px;margin:3px 0;">'
            f'<code style="color:{color};">{endpoint}</code> — {purpose}'
            f'<br><small style="color:#888;">{module} | {status}</small>'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.divider()
    st.markdown("### 📊 Discovery Daemon Status")
    try:
        daemon = get_daemon()
        status_data = daemon.get_status()
        col1, col2, col3 = st.columns(3)
        with col1:
            running_icon = "🟢" if status_data["running"] else "🔴"
            st.metric("Daemon Status", f"{running_icon} {'Running' if status_data['running'] else 'Stopped'}")
        with col2:
            st.metric("Cycles Completed", status_data["cycle_count"])
        with col3:
            st.metric("Interval", f"{status_data['interval_hours']}h")

        if status_data.get("last_cycle"):
            lc = status_data["last_cycle"]
            st.markdown("**Last Cycle:**")
            st.json({
                "candidates_harvested": lc.get("candidates_harvested", 0),
                "candidates_scored": lc.get("candidates_scored", 0),
                "new_snipers_found": lc.get("new_snipers_found", 0),
                "new_snipers_promoted": lc.get("new_snipers_promoted", 0),
                "total_tracked": lc.get("total_tracked", 0),
                "elapsed_seconds": lc.get("elapsed_seconds", 0),
            })
    except Exception as e:
        st.warning(f"Could not get daemon status: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 5: STREAMS HEALTH
# ═══════════════════════════════════════════════════════════════════════════════
with tab_streams:
    st.markdown("### ⚡ Moralis Streams Health Monitor")
    st.markdown(
        "Real-time status of the push-based event pipeline. "
        "Streams provide **sub-second** copy-trade detection vs. 30s polling."
    )

    if not _STREAMS_AVAILABLE:
        st.warning(
            "Moralis Streams modules not loaded. "
            "Set `MORALIS_STREAMS_ENABLED=true` in your `.env` to activate."
        )
    else:
        # Get wallet monitor stats for hybrid mode info
        try:
            from core.wallet_monitor import get_monitor as _get_wm
            wm_stats = _get_wm().get_stats()
        except Exception:
            wm_stats = {}

        # Hybrid mode status
        streams_active = wm_stats.get("streams_active", False)
        poll_interval = wm_stats.get("poll_interval", 30)

        st.markdown("#### 🔄 Detection Mode")
        col_m1, col_m2, col_m3 = st.columns(3)
        with col_m1:
            mode_icon = "⚡" if streams_active else "🔄"
            mode_label = "HYBRID (Streams Primary)" if streams_active else "POLLING ONLY"
            mode_color = "#00ff88" if streams_active else "#ffd700"
            st.markdown(
                f'<div class="stat-box"><div style="font-size:1.5em;font-weight:bold;color:{mode_color};">{mode_icon} {mode_label}</div></div>',
                unsafe_allow_html=True,
            )
        with col_m2:
            st.markdown(
                f'<div class="stat-box"><div style="font-size:1.8em;font-weight:bold;">{poll_interval}s</div><div>Poll Interval (fallback)</div></div>',
                unsafe_allow_html=True,
            )
        with col_m3:
            latency_label = "<1s" if streams_active else f"{poll_interval}s"
            latency_color = "#00ff88" if streams_active else "#ff6b6b"
            st.markdown(
                f'<div class="stat-box"><div style="font-size:1.8em;font-weight:bold;color:{latency_color};">{latency_label}</div><div>Signal Latency</div></div>',
                unsafe_allow_html=True,
            )

        st.divider()

        # Webhook metrics from file
        st.markdown("#### 📊 Webhook Metrics")
        metrics_file = _ROOT / "output" / "streams_metrics.json"
        if metrics_file.exists():
            try:
                with open(metrics_file) as f:
                    metrics = json.load(f)

                col_w1, col_w2, col_w3, col_w4 = st.columns(4)
                with col_w1:
                    st.metric("Total Webhooks", metrics.get("total_webhooks", 0))
                with col_w2:
                    st.metric("Alpha Swap Events", metrics.get("alpha_events", 0))
                with col_w3:
                    st.metric("Whale Events", metrics.get("whale_events", 0))
                with col_w4:
                    avg_latency = metrics.get("avg_latency_ms", 0)
                    st.metric("Avg Latency", f"{avg_latency:.0f}ms")

                # Error rate
                errors = metrics.get("errors", 0)
                total = max(metrics.get("total_webhooks", 1), 1)
                error_rate = errors / total * 100
                if error_rate > 5:
                    st.error(f"⚠️ High webhook error rate: {error_rate:.1f}% ({errors}/{total})")
                elif error_rate > 0:
                    st.warning(f"Webhook error rate: {error_rate:.1f}% ({errors}/{total})")
                else:
                    st.success("✅ Zero webhook errors")

                # Recent events
                recent = metrics.get("recent_events", [])
                if recent:
                    st.markdown("**Recent Events:**")
                    for evt in reversed(recent[-10:]):
                        ts = evt.get("timestamp", "")[:19]
                        etype = evt.get("type", "unknown")
                        badge_color = {
                            "alpha_swap": "#00ff88",
                            "whale_transfer": "#ffd700",
                            "liquidity": "#85c1e9",
                        }.get(etype, "#aaa")
                        st.markdown(
                            f'<div style="border-left:3px solid {badge_color}; padding:4px 12px; margin:2px 0;">'
                            f'<code>{ts}</code> — <b style="color:{badge_color};">{etype}</b> | '
                            f'{evt.get("summary", "")}'
                            f'</div>',
                            unsafe_allow_html=True,
                        )

            except Exception as e:
                st.warning(f"Could not read metrics: {e}")
        else:
            st.info(
                "No webhook metrics yet. Metrics will appear once the Streams server "
                "starts receiving events from Moralis."
            )

        st.divider()

        # Stream configuration info
        st.markdown("#### ⚙️ Stream Configuration")
        try:
            from config import settings as _s
            config_items = {
                "Webhook Port": getattr(_s, "MORALIS_STREAMS_PORT", 8787),
                "Webhook URL": getattr(_s, "MORALIS_STREAMS_WEBHOOK_URL", "Not set"),
                "Streams Enabled": getattr(_s, "MORALIS_STREAMS_ENABLED", False),
                "Whale Detection": getattr(_s, "MORALIS_STREAMS_WHALE_ENABLED", False),
                "Liquidity Detection": getattr(_s, "MORALIS_STREAMS_LIQUIDITY_ENABLED", False),
                "Auto-Sync Wallets": getattr(_s, "MORALIS_STREAMS_AUTO_SYNC", True),
                "Health Check Interval": f"{getattr(_s, 'MORALIS_STREAMS_HEALTH_CHECK_INTERVAL', 300)}s",
                "Fallback Poll Interval": f"{getattr(_s, 'MORALIS_STREAMS_FALLBACK_POLL_INTERVAL', 120)}s",
            }
            for key, val in config_items.items():
                is_bool = isinstance(val, bool)
                color = "#00ff88" if val else "#ff6b6b" if is_bool else "#ccc"
                display = ("✅ Enabled" if val else "❌ Disabled") if is_bool else str(val)
                st.markdown(
                    f'<div style="border-left:3px solid {color}; padding:4px 12px; margin:2px 0;">'
                    f'<b>{key}:</b> <span style="color:{color};">{display}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
        except Exception as e:
            st.warning(f"Could not load streams config: {e}")

        st.divider()

        # Pro plan note
        st.markdown("#### 💳 Moralis Plan")
        st.info(
            "**Pro Plan** — Streams supports custom streams for tracked wallets. "
            "Whale detection (`allAddresses: true`) may require **Business plan**. "
            "Verify your plan tier before enabling `MORALIS_STREAMS_WHALE_ENABLED`.\n\n"
            "CU Budget: Check [admin.moralis.com](https://admin.moralis.com) for current usage."
        )
