"""
Page 3 — 💰 Positions & Trades

Open positions with unrealized P&L, trade history log,
portfolio performance visualization, and MANUAL INTERVENTION controls.

Manual Controls (new):
  • Force Sell % — sell a custom percentage of any open position immediately
  • Force Close  — close 100% of a position at market price
  • Manual Buy   — buy any token by address with a custom USD amount
  • Partial Sell — quick 25/50/75% sell buttons per position
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime, timezone

from styles import PREMIUM_CSS, PLOTLY_LAYOUT, ACCENT, CHAIN_COLORS, DANGER, WARNING
from state import (
    get_positions,
    get_trades,
    get_pending_manual_commands,
    request_manual_sell,
    request_manual_close,
    request_manual_buy,
)

st.set_page_config(page_title="Positions | Shamrock", page_icon="💰", layout="wide")
st.markdown(PREMIUM_CSS, unsafe_allow_html=True)

# ── Extra CSS for intervention controls ──────────────────────────────────────
st.markdown("""
<style>
.intervention-card {
    background: linear-gradient(145deg, rgba(13,17,23,0.98), rgba(22,27,34,0.95));
    border: 1px solid rgba(255,184,77,0.35);
    border-radius: 14px;
    padding: 18px 20px;
    margin-bottom: 14px;
    position: relative;
}
.intervention-card.buy-card {
    border-color: rgba(0,208,156,0.35);
}
.intervention-label {
    color: #FFB84D; font-size: 0.62rem; font-weight: 800;
    text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 10px;
}
.intervention-label.buy-label { color: #00D09C; }
.pos-card {
    background: linear-gradient(145deg, rgba(13,17,23,0.98), rgba(22,27,34,0.95));
    border: 1px solid rgba(48,54,61,0.7);
    border-radius: 12px;
    padding: 16px 18px;
    margin-bottom: 12px;
}
.pos-card.profitable { border-color: rgba(0,208,156,0.3); }
.pos-card.losing { border-color: rgba(255,71,87,0.3); }
.pos-header {
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 10px;
}
.pos-symbol {
    color: #E6EDF3; font-size: 1.05rem; font-weight: 800;
    font-family: 'JetBrains Mono', monospace;
}
.pos-chain {
    color: #8B949E; font-size: 0.75rem; margin-left: 8px;
}
.pos-pnl-positive { color: #00D09C; font-size: 1.1rem; font-weight: 700; }
.pos-pnl-negative { color: #FF4757; font-size: 1.1rem; font-weight: 700; }
.pos-meta { color: #484F58; font-size: 0.7rem; margin-top: 4px; }
.tp-badge {
    display: inline-block; padding: 2px 8px; border-radius: 20px;
    font-size: 0.62rem; font-weight: 700; margin-right: 4px;
}
.tp-hit { background: rgba(0,208,156,0.15); color: #00D09C; border: 1px solid rgba(0,208,156,0.3); }
.tp-pending { background: rgba(48,54,61,0.4); color: #484F58; border: 1px solid rgba(48,54,61,0.5); }
.cmd-queue-item {
    background: rgba(255,184,77,0.06);
    border: 1px solid rgba(255,184,77,0.2);
    border-radius: 8px;
    padding: 8px 12px;
    margin-bottom: 6px;
    font-size: 0.72rem;
    color: #8B949E;
}
.cmd-queue-item .cmd-type { color: #FFB84D; font-weight: 700; margin-right: 6px; }
</style>
""", unsafe_allow_html=True)

# ── Header ───────────────────────────────────────────────────────────────────
st.markdown(
    '<div style="display:flex;align-items:center;gap:12px;margin-bottom:1.5rem;">'
    '<span style="font-size:2rem;">💰</span>'
    '<div>'
    '<h1 style="margin:0;padding:0;font-size:1.5rem;font-weight:800;'
    'background:linear-gradient(135deg,#00D09C,#00E6AC);'
    '-webkit-background-clip:text;-webkit-text-fill-color:transparent;">POSITIONS & TRADES</h1>'
    '<span style="color:#8B949E;font-size:0.8rem;">Portfolio management · Trade history · Manual intervention controls</span>'
    '</div></div>',
    unsafe_allow_html=True,
)

positions = get_positions()
trades = get_trades()

# ── Portfolio Summary ────────────────────────────────────────────────────────
open_positions = [p for p in positions if p.get("is_open", False)]
closed_positions = [p for p in positions if not p.get("is_open", True)]

total_invested = sum(p.get("amount_eth_spent", 0) or p.get("amount_sol_spent", 0) for p in open_positions)
total_unrealized = sum(p.get("unrealized_pnl_pct", 0) for p in open_positions)
avg_unrealized = total_unrealized / max(len(open_positions), 1)

buy_trades = [t for t in trades if t.get("direction") == "buy"]
sell_trades = [t for t in trades if t.get("direction") == "sell"]
total_pnl_eth = sum(t.get("amount_out", 0) - t.get("amount_in", 0) for t in sell_trades)

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Open Positions", len(open_positions))
with col2:
    st.metric("Total Invested", f"{total_invested:.4f} ETH")
with col3:
    pnl_color = "normal" if total_pnl_eth >= 0 else "inverse"
    st.metric("Realized P&L", f"{total_pnl_eth:+.4f} ETH", delta=f"{len(sell_trades)} sells")
with col4:
    st.metric("Avg Unrealized", f"{avg_unrealized:+.1f}%")

st.markdown("<div style='height:24px;'></div>", unsafe_allow_html=True)

# ── Tabs ─────────────────────────────────────────────────────────────────────
tab_pos, tab_buy, tab_trades_tab, tab_perf = st.tabs([
    "📍 Open Positions",
    "🛒 Manual Buy",
    "📝 Trade Log",
    "📈 Performance",
])

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — OPEN POSITIONS with per-position sell controls
# ═══════════════════════════════════════════════════════════════════════════════
with tab_pos:
    # ── Pending command queue display ────────────────────────────────────────
    pending_cmds = get_pending_manual_commands()
    if pending_cmds:
        st.markdown(
            f'<div style="background:rgba(255,184,77,0.06);border:1px solid rgba(255,184,77,0.25);'
            f'border-radius:10px;padding:12px 16px;margin-bottom:16px;">'
            f'<div style="color:#FFB84D;font-size:0.72rem;font-weight:800;'
            f'text-transform:uppercase;letter-spacing:0.08em;margin-bottom:8px;">'
            f'⏳ {len(pending_cmds)} Command(s) Queued — Executing Next Cycle</div>',
            unsafe_allow_html=True,
        )
        for cmd in pending_cmds:
            cmd_type = cmd.get("type", "").upper().replace("_", " ")
            sym = cmd.get("symbol", "?")
            chain = cmd.get("chain", "")
            ts = cmd.get("requested_at", "")[:19]
            extra = ""
            if cmd.get("type") == "manual_sell":
                extra = f" · {cmd.get('sell_pct', 100):.0f}%"
            elif cmd.get("type") == "manual_buy":
                extra = f" · ${cmd.get('usd_amount', 0):.2f}"
            st.markdown(
                f'<div class="cmd-queue-item">'
                f'<span class="cmd-type">{cmd_type}</span>'
                f'<span style="color:#E6EDF3;font-weight:600;">{sym}</span>'
                f'<span style="color:#484F58;"> on {chain}{extra} · queued {ts}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
        st.markdown('</div>', unsafe_allow_html=True)

    if open_positions:
        st.markdown("### 📍 Open Positions")

        # ── Position cards with sell buttons ─────────────────────────────────
        for idx, p in enumerate(open_positions):
            pnl = p.get("unrealized_pnl_pct", 0)
            symbol = p.get("symbol", "???")
            chain = p.get("chain", "")
            token_addr = p.get("address", p.get("token_address", ""))
            entry_price = p.get("entry_price", 0)
            current_price = p.get("current_price", 0)
            tp1 = p.get("tp1_hit", False)
            tp2 = p.get("tp2_hit", False)
            tp3 = p.get("tp3_hit", False)
            express = p.get("express_lane", False)
            fib_zone = p.get("fib_zone", "")
            wallet = p.get("wallet", "primary")
            opened_at = p.get("opened_at", "")[:16]
            is_paper = p.get("is_paper", True)

            card_class = "profitable" if pnl > 0 else ("losing" if pnl < 0 else "")
            pnl_class = "pos-pnl-positive" if pnl > 0 else "pos-pnl-negative"
            chain_emoji = {
                "ethereum": "⟠", "base": "🔵", "arbitrum": "🔷",
                "polygon": "🟣", "bsc": "🟡", "solana": "◎", "avalanche": "🔺",
            }.get(chain, "⬡")

            tp1_cls = "tp-hit" if tp1 else "tp-pending"
            tp2_cls = "tp-hit" if tp2 else "tp-pending"
            tp3_cls = "tp-hit" if tp3 else "tp-pending"

            express_badge = (
                '<span style="background:rgba(88,166,255,0.12);color:#58A6FF;font-size:0.62rem;'
                'font-weight:700;padding:2px 8px;border-radius:20px;margin-left:8px;">\u26a1 EXPRESS</span>'
                if express else ""
            )
            mode_badge = (
                '<span style="background:rgba(255,184,77,0.12);color:#FFB84D;font-size:0.62rem;'
                'font-weight:700;padding:2px 8px;border-radius:20px;margin-left:4px;">\ud83d\udcc4 PAPER</span>'
                if is_paper else
                '<span style="background:rgba(0,208,156,0.12);color:#00D09C;font-size:0.62rem;'
                'font-weight:700;padding:2px 8px;border-radius:20px;margin-left:4px;">\ud83d\udd34 LIVE</span>'
            )
            fib_badge = (
                f'<span class="tp-badge tp-hit">\ud83d\udcd0 {fib_zone}</span>' if fib_zone else ""
            )
            pos_html = (
                f'<div class="pos-card {card_class}">'
                f'<div class="pos-header">'
                f'<div>'
                f'<span class="pos-symbol">{symbol}</span>'
                f'<span class="pos-chain">{chain_emoji} {chain.capitalize()}</span>'
                f'{express_badge}{mode_badge}'
                f'</div>'
                f'<div class="{pnl_class}">{pnl:+.2f}%</div>'
                f'</div>'
                f'<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:10px;">'
                f'<div><div style="color:#484F58;font-size:0.6rem;font-weight:700;text-transform:uppercase;">Entry</div>'
                f'<div style="color:#E6EDF3;font-size:0.78rem;font-family:monospace;">${entry_price:.8f}</div></div>'
                f'<div><div style="color:#484F58;font-size:0.6rem;font-weight:700;text-transform:uppercase;">Current</div>'
                f'<div style="color:#E6EDF3;font-size:0.78rem;font-family:monospace;">${current_price:.8f}</div></div>'
                f'<div><div style="color:#484F58;font-size:0.6rem;font-weight:700;text-transform:uppercase;">Wallet</div>'
                f'<div style="color:#8B949E;font-size:0.78rem;">{wallet}</div></div>'
                f'<div><div style="color:#484F58;font-size:0.6rem;font-weight:700;text-transform:uppercase;">Opened</div>'
                f'<div style="color:#8B949E;font-size:0.78rem;">{opened_at}</div></div>'
                f'</div>'
                f'<div style="margin-bottom:10px;">'
                f'<span class="tp-badge {tp1_cls}">TP1 1.5\u00d7</span>'
                f'<span class="tp-badge {tp2_cls}">TP2 2.5\u00d7</span>'
                f'<span class="tp-badge {tp3_cls}">TP3 5.0\u00d7</span>'
                + fib_badge +
                f'</div>'
                f'<div style="color:#484F58;font-size:0.65rem;font-family:monospace;'
                f'word-break:break-all;margin-bottom:10px;">{token_addr}</div>'
                f'</div>'
            )
            st.markdown(pos_html, unsafe_allow_html=True)

            # ── Sell control buttons ──────────────────────────────────────────
            if token_addr:
                btn_col1, btn_col2, btn_col3, btn_col4, btn_col5 = st.columns([1, 1, 1, 1, 2])

                with btn_col1:
                    if st.button(
                        "🔴 Sell 25%",
                        key=f"sell25_{idx}_{token_addr[:8]}",
                        use_container_width=True,
                        help=f"Sell 25% of {symbol} position immediately",
                    ):
                        request_manual_sell(
                            token_address=token_addr,
                            chain=chain,
                            symbol=symbol,
                            sell_pct=25.0,
                            reason="dashboard_sell_25pct",
                        )
                        st.success(f"✅ Queued: sell 25% of {symbol}")
                        st.rerun()

                with btn_col2:
                    if st.button(
                        "🟠 Sell 50%",
                        key=f"sell50_{idx}_{token_addr[:8]}",
                        use_container_width=True,
                        help=f"Sell 50% of {symbol} position immediately",
                    ):
                        request_manual_sell(
                            token_address=token_addr,
                            chain=chain,
                            symbol=symbol,
                            sell_pct=50.0,
                            reason="dashboard_sell_50pct",
                        )
                        st.success(f"✅ Queued: sell 50% of {symbol}")
                        st.rerun()

                with btn_col3:
                    if st.button(
                        "🟡 Sell 75%",
                        key=f"sell75_{idx}_{token_addr[:8]}",
                        use_container_width=True,
                        help=f"Sell 75% of {symbol} position immediately",
                    ):
                        request_manual_sell(
                            token_address=token_addr,
                            chain=chain,
                            symbol=symbol,
                            sell_pct=75.0,
                            reason="dashboard_sell_75pct",
                        )
                        st.success(f"✅ Queued: sell 75% of {symbol}")
                        st.rerun()

                with btn_col4:
                    if st.button(
                        "⛔ CLOSE ALL",
                        key=f"close_{idx}_{token_addr[:8]}",
                        use_container_width=True,
                        type="primary",
                        help=f"Force-close 100% of {symbol} at market price",
                    ):
                        request_manual_close(
                            token_address=token_addr,
                            chain=chain,
                            symbol=symbol,
                            reason="dashboard_force_close",
                        )
                        st.success(f"✅ Queued: FORCE CLOSE {symbol} (100%)")
                        st.rerun()

                with btn_col5:
                    # Custom % sell
                    with st.expander(f"🎯 Custom % Sell — {symbol}", expanded=False):
                        custom_pct = st.slider(
                            "Sell percentage",
                            min_value=1,
                            max_value=100,
                            value=50,
                            step=1,
                            key=f"custom_pct_{idx}_{token_addr[:8]}",
                            label_visibility="collapsed",
                        )
                        if st.button(
                            f"Execute {custom_pct}% Sell",
                            key=f"custom_sell_{idx}_{token_addr[:8]}",
                            use_container_width=True,
                        ):
                            request_manual_sell(
                                token_address=token_addr,
                                chain=chain,
                                symbol=symbol,
                                sell_pct=float(custom_pct),
                                reason=f"dashboard_custom_sell_{custom_pct}pct",
                            )
                            st.success(f"✅ Queued: sell {custom_pct}% of {symbol}")
                            st.rerun()

            st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)

        # ── P&L Waterfall ─────────────────────────────────────────────────────
        if len(open_positions) > 1:
            st.markdown("### 📊 Position P&L Distribution")
            fig_waterfall = go.Figure()
            symbols = [p.get("symbol", "?") for p in open_positions]
            pnls = [p.get("unrealized_pnl_pct", 0) for p in open_positions]
            colors = [ACCENT if pnl >= 0 else DANGER for pnl in pnls]
            fig_waterfall.add_trace(go.Bar(
                x=symbols, y=pnls,
                marker=dict(color=colors, line=dict(color="#0A0E14", width=1)),
                hovertemplate="<b>%{x}</b><br>P&L: %{y:+.2f}%<extra></extra>",
            ))
            fig_waterfall.update_layout(
                **{**PLOTLY_LAYOUT, "showlegend": False},
                height=300, yaxis_title="Unrealized P&L %",
            )
            st.plotly_chart(fig_waterfall, use_container_width=True, config={"displayModeBar": False})

    else:
        st.markdown(
            '<div class="glass-card" style="text-align:center;padding:3rem;">'
            '<div style="font-size:2.5rem;margin-bottom:0.75rem;">📍</div>'
            '<div style="color:#E6EDF3;font-size:1.1rem;font-weight:600;">No Open Positions</div>'
            '<div style="color:#8B949E;font-size:0.85rem;margin-top:6px;">'
            'Positions will appear when the bot executes trades</div>'
            '</div>',
            unsafe_allow_html=True,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — MANUAL BUY
# ═══════════════════════════════════════════════════════════════════════════════
with tab_buy:
    st.markdown("### 🛒 Manual Buy — Force Entry")
    st.markdown(
        '<div style="background:rgba(255,71,87,0.06);border:1px solid rgba(255,71,87,0.2);'
        'border-radius:10px;padding:12px 16px;margin-bottom:20px;">'
        '<span style="color:#FF4757;font-size:0.75rem;font-weight:700;">⚠️ SAFETY NOTE: </span>'
        '<span style="color:#8B949E;font-size:0.75rem;">Manual buys bypass the score gate but '
        '<b style="color:#E6EDF3;">NEVER bypass safety/honeypot checks</b>. '
        'GoPlus + Honeypot.is checks always run. Honeypots and high-tax tokens will be blocked.</span>'
        '</div>',
        unsafe_allow_html=True,
    )

    buy_col1, buy_col2 = st.columns([3, 2])

    with buy_col1:
        st.markdown('<div class="intervention-card buy-card">', unsafe_allow_html=True)
        st.markdown('<div class="intervention-label buy-label">🛒 Manual Buy Order</div>', unsafe_allow_html=True)

        mb_chain = st.selectbox(
            "Chain",
            options=["base", "ethereum", "arbitrum", "polygon", "bsc", "solana"],
            key="mb_chain",
        )
        mb_token = st.text_input(
            "Token Contract Address",
            placeholder="0x... or Solana mint address",
            key="mb_token",
        )
        mb_symbol = st.text_input(
            "Token Symbol (for logging)",
            placeholder="e.g. PEPE",
            key="mb_symbol",
        )
        mb_usd = st.number_input(
            "USD Amount to Buy",
            min_value=1.0,
            max_value=10000.0,
            value=50.0,
            step=10.0,
            key="mb_usd",
            help="Will be converted to native token (ETH/SOL) at execution time",
        )
        mb_wallet = st.selectbox(
            "Wallet",
            options=["primary", "wallet_b", "wallet_c"],
            key="mb_wallet",
            help="primary=gem sniping, wallet_b=DCA/mean-reversion, wallet_c=long-term holds",
        )
        mb_reason = st.text_input(
            "Reason / Note (optional)",
            placeholder="e.g. manual_degen_play",
            value="dashboard_manual_buy",
            key="mb_reason",
        )

        st.markdown('</div>', unsafe_allow_html=True)

        if st.button(
            f"🛒 Queue Manual Buy — ${mb_usd:.0f} of {mb_symbol or '?'} on {mb_chain}",
            key="execute_manual_buy",
            use_container_width=True,
            type="primary",
        ):
            if not mb_token or len(mb_token) < 10:
                st.error("❌ Please enter a valid token contract address.")
            elif mb_usd <= 0:
                st.error("❌ USD amount must be greater than 0.")
            else:
                request_manual_buy(
                    token_address=mb_token.strip(),
                    chain=mb_chain,
                    symbol=(mb_symbol.strip().upper() or mb_token[:8]),
                    usd_amount=mb_usd,
                    wallet=mb_wallet,
                    reason=mb_reason.strip() or "dashboard_manual_buy",
                )
                st.success(
                    f"✅ Manual buy queued: ${mb_usd:.2f} of {mb_symbol or mb_token[:10]} "
                    f"on {mb_chain} via {mb_wallet} wallet. "
                    f"Will execute next cycle (safety checks will run first)."
                )
                st.rerun()

    with buy_col2:
        st.markdown(
            '<div style="background:rgba(13,17,23,0.98);border:1px solid rgba(48,54,61,0.5);'
            'border-radius:12px;padding:16px;">'
            '<div style="color:#E6EDF3;font-size:0.8rem;font-weight:700;margin-bottom:12px;">'
            '📋 Manual Buy Checklist</div>'
            '<div style="color:#8B949E;font-size:0.72rem;line-height:1.8;">'
            '✅ Safety checks always run (GoPlus + Honeypot.is)<br>'
            '✅ Score gate bypassed — you are overriding the AI<br>'
            '⚠️ Dedup guard still active — no double-buys<br>'
            '⚠️ Risk manager still applies position sizing<br>'
            '⚠️ Paper mode: no real funds spent if MODE=paper<br>'
            '🔴 Live mode: real funds at risk — confirm chain/address<br>'
            '</div>'
            '<hr style="border-color:rgba(48,54,61,0.5);margin:12px 0;">'
            '<div style="color:#484F58;font-size:0.65rem;font-weight:700;'
            'text-transform:uppercase;letter-spacing:0.08em;margin-bottom:6px;">Wallet Roles</div>'
            '<div style="color:#8B949E;font-size:0.7rem;line-height:1.7;">'
            '<b style="color:#E6EDF3;">primary</b> — gem sniping, active plays<br>'
            '<b style="color:#E6EDF3;">wallet_b</b> — DCA &amp; mean-reversion<br>'
            '<b style="color:#E6EDF3;">wallet_c</b> — long-term holds &amp; sweeps<br>'
            '</div>'
            '</div>',
            unsafe_allow_html=True,
        )

        # Show pending buy commands
        pending_buys = [c for c in get_pending_manual_commands() if c.get("type") == "manual_buy"]
        if pending_buys:
            st.markdown(
                f'<div style="margin-top:12px;background:rgba(0,208,156,0.05);'
                f'border:1px solid rgba(0,208,156,0.2);border-radius:8px;padding:10px 12px;">'
                f'<div style="color:#00D09C;font-size:0.68rem;font-weight:700;margin-bottom:6px;">'
                f'⏳ {len(pending_buys)} Buy(s) Queued</div>',
                unsafe_allow_html=True,
            )
            for pb in pending_buys:
                st.markdown(
                    f'<div style="color:#8B949E;font-size:0.68rem;padding:3px 0;">'
                    f'<b style="color:#E6EDF3;">{pb.get("symbol","?")}</b> '
                    f'${pb.get("usd_amount",0):.2f} on {pb.get("chain","?")} '
                    f'via {pb.get("wallet","?")}</div>',
                    unsafe_allow_html=True,
                )
            st.markdown('</div>', unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3 — TRADE LOG
# ═══════════════════════════════════════════════════════════════════════════════
with tab_trades_tab:
    if trades:
        trade_rows = []
        for t in sorted(trades, key=lambda x: x.get("timestamp", ""), reverse=True)[:100]:
            direction = t.get("direction", "")
            dir_emoji = "🟢 BUY" if direction == "buy" else "🔴 SELL"
            status = t.get("status", "")
            status_emoji = {"success": "✅", "failed": "❌", "pending": "⏳"}.get(status, "❓")
            reason = t.get("execution_path", "")
            is_manual = "manual" in reason.lower() or "dashboard" in reason.lower()
            manual_tag = " 🎮" if is_manual else ""

            trade_rows.append({
                "Time": t.get("timestamp", "")[:19],
                "Dir": dir_emoji,
                "Token": t.get("symbol", "???"),
                "Chain": t.get("chain", "").capitalize(),
                "Price": f"${t.get('price_usd', 0):.6f}",
                "In": f"{t.get('amount_in', 0):.4f}",
                "Out": f"{t.get('amount_out', 0):.4f}",
                "P&L": f"{t.get('pnl_pct', 0):+.2f}%" if t.get("pnl_pct") else "—",
                "Gas (ETH)": f"{t.get('gas_cost_eth', 0):.6f}",
                "Path": (t.get("execution_path", "").upper() + manual_tag),
                "Score": f"{t.get('gem_score', 0):.1f}",
                "Status": status_emoji,
            })

        df_trades = pd.DataFrame(trade_rows)
        st.dataframe(df_trades, use_container_width=True, hide_index=True, height=500)

        # Trade volume over time
        st.markdown("### 📊 Trade Volume Over Time")
        df_t = pd.DataFrame(trades)
        df_t["timestamp"] = pd.to_datetime(df_t["timestamp"], errors="coerce")
        df_t = df_t.dropna(subset=["timestamp"]).sort_values("timestamp")

        fig_vol = go.Figure()
        buys = df_t[df_t["direction"] == "buy"]
        sells = df_t[df_t["direction"] == "sell"]

        if not buys.empty:
            fig_vol.add_trace(go.Scatter(
                x=buys["timestamp"], y=buys["amount_in"],
                mode="markers", name="Buys",
                marker=dict(color=ACCENT, size=8, symbol="triangle-up"),
                hovertemplate="<b>BUY</b><br>%{y:.4f} ETH<br>%{x|%b %d %H:%M}<extra></extra>",
            ))
        if not sells.empty:
            fig_vol.add_trace(go.Scatter(
                x=sells["timestamp"], y=sells["amount_out"],
                mode="markers", name="Sells",
                marker=dict(color=DANGER, size=8, symbol="triangle-down"),
                hovertemplate="<b>SELL</b><br>%{y:.4f} ETH<br>%{x|%b %d %H:%M}<extra></extra>",
            ))

        fig_vol.update_layout(**PLOTLY_LAYOUT, height=300)
        st.plotly_chart(fig_vol, use_container_width=True, config={"displayModeBar": False})
    else:
        st.markdown(
            '<div class="glass-card" style="text-align:center;padding:3rem;">'
            '<div style="font-size:2.5rem;margin-bottom:0.75rem;">📝</div>'
            '<div style="color:#E6EDF3;font-size:1.1rem;font-weight:600;">No Trades Yet</div>'
            '<div style="color:#8B949E;font-size:0.85rem;margin-top:6px;">'
            'Bot is running — trades will appear here</div>'
            '</div>',
            unsafe_allow_html=True,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 4 — PERFORMANCE
# ═══════════════════════════════════════════════════════════════════════════════
with tab_perf:
    if trades:
        st.markdown("### 📈 Cumulative P&L")

        df_perf = pd.DataFrame(trades)
        df_perf["timestamp"] = pd.to_datetime(df_perf["timestamp"], errors="coerce")
        df_perf = df_perf.dropna(subset=["timestamp"]).sort_values("timestamp")
        df_perf["pnl"] = df_perf.apply(
            lambda r: (r.get("amount_out", 0) - r.get("amount_in", 0)) if r.get("direction") == "sell" else 0,
            axis=1,
        )
        df_perf["cumulative_pnl"] = df_perf["pnl"].cumsum()

        fig_pnl = go.Figure()
        fig_pnl.add_trace(go.Scatter(
            x=df_perf["timestamp"],
            y=df_perf["cumulative_pnl"],
            mode="lines",
            line=dict(color=ACCENT, width=2.5),
            fill="tozeroy",
            fillcolor="rgba(0, 208, 156, 0.1)",
            hovertemplate="<b>P&L: %{y:.4f} ETH</b><br>%{x|%b %d %H:%M}<extra></extra>",
        ))
        fig_pnl.add_hline(y=0, line_dash="dash", line_color="rgba(255,255,255,0.1)")
        fig_pnl.update_layout(**PLOTLY_LAYOUT, height=350, yaxis_title="Cumulative P&L (ETH)")
        st.plotly_chart(fig_pnl, use_container_width=True, config={"displayModeBar": False})

        # Win rate
        st.markdown("### 🎯 Trade Statistics")
        wins = len([t for t in sell_trades if (t.get("amount_out", 0) - t.get("amount_in", 0)) > 0])
        total_sells = len(sell_trades)
        win_rate = (wins / max(total_sells, 1)) * 100

        # Manual vs auto breakdown
        manual_trades = [t for t in trades if "manual" in str(t.get("execution_path", "")).lower()
                         or "dashboard" in str(t.get("execution_path", "")).lower()]

        stat_col1, stat_col2, stat_col3, stat_col4 = st.columns(4)
        with stat_col1:
            st.metric("Win Rate", f"{win_rate:.1f}%")
        with stat_col2:
            st.metric("Total Buys", len(buy_trades))
        with stat_col3:
            st.metric("Total Sells", len(sell_trades))
        with stat_col4:
            st.metric("Manual Interventions", len(manual_trades), help="Trades triggered from dashboard")
    else:
        st.markdown(
            '<div class="glass-card" style="text-align:center;padding:3rem;">'
            '<div style="font-size:2.5rem;margin-bottom:0.75rem;">📈</div>'
            '<div style="color:#E6EDF3;font-size:1.1rem;font-weight:600;">Performance Tracking</div>'
            '<div style="color:#8B949E;font-size:0.85rem;margin-top:6px;">'
            'P&L charts and win rate will appear after trades execute</div>'
            '</div>',
            unsafe_allow_html=True,
        )
