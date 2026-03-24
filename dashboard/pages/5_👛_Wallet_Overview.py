"""
Page 5 — 👛 Wallet Overview

Real-time multi-wallet, multi-chain portfolio dashboard.
Pulls live data from Moralis Pro API and wallet config.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime, timezone

from styles import PREMIUM_CSS, PLOTLY_LAYOUT, ACCENT, CHAIN_COLORS, CHAIN_EMOJI, DANGER, WARNING


# ── Helper ───────────────────────────────────────────────────────────────────
def _hex_to_rgb(hex_color: str) -> str:
    """Convert #RRGGBB to 'R,G,B' for use in rgba()."""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 6:
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        return f"{r},{g},{b}"
    return "139,148,158"


st.set_page_config(page_title="Wallet Overview | Shamrock", page_icon="👛", layout="wide")
st.markdown(PREMIUM_CSS, unsafe_allow_html=True)

# ── Header ───────────────────────────────────────────────────────────────────
st.markdown(
    '<div style="display:flex;align-items:center;gap:12px;margin-bottom:1.5rem;">'
    '<span style="font-size:2rem;">👛</span>'
    '<div>'
    '<h1 style="margin:0;padding:0;font-size:1.5rem;font-weight:800;'
    'background:linear-gradient(135deg,#00D09C,#00E6AC);'
    '-webkit-background-clip:text;-webkit-text-fill-color:transparent;">WALLET OVERVIEW</h1>'
    '<span style="color:#8B949E;font-size:0.8rem;">Real-time portfolio across all wallets & chains</span>'
    '</div></div>',
    unsafe_allow_html=True,
)

# ── Load wallet config ───────────────────────────────────────────────────────
try:
    from config.wallets import WALLETS, get_active_trading_wallets
    wallets_available = True
except ImportError:
    wallets_available = False
    WALLETS = {}

# ── Load Moralis data (graceful degradation) ─────────────────────────────────
moralis_available = False
try:
    from data.providers.moralis_wallet import (
        get_wallet_net_worth,
        get_wallet_token_balances,
        get_wallet_pnl,
        get_usage_stats,
    )
    moralis_available = True
except ImportError:
    pass


def safe_net_worth(address: str) -> dict:
    """Fetch net worth with error handling."""
    if not moralis_available or not address:
        return {"total_networth_usd": 0.0, "chains": []}
    try:
        return get_wallet_net_worth(address)
    except Exception:
        return {"total_networth_usd": 0.0, "chains": []}


def safe_token_balances(address: str, chain: str) -> list:
    """Fetch token balances with error handling."""
    if not moralis_available or not address:
        return []
    try:
        return get_wallet_token_balances(address, chain)
    except Exception:
        return []


# ── Aggregate portfolio data ─────────────────────────────────────────────────
total_portfolio_usd = 0.0
wallet_data = {}

if wallets_available:
    for key, wallet in WALLETS.items():
        nw = safe_net_worth(wallet.address)
        total_portfolio_usd += nw.get("total_networth_usd", 0.0)
        wallet_data[key] = {
            "config": wallet,
            "net_worth": nw,
        }

# ── Total Portfolio Value — Hero ─────────────────────────────────────────────
hero_col1, hero_col2, hero_col3 = st.columns([1, 2, 1])
with hero_col2:
    wallet_count = len(WALLETS)
    chain_count = len(set(c for w in WALLETS.values() for c in w.chains)) if wallets_available else 0

    st.markdown(
        f'<div class="pnl-hero">'
        f'<div class="pnl-label">Total Portfolio Value</div>'
        f'<div class="pnl-value positive" style="font-size:2.8rem;">'
        f'${total_portfolio_usd:,.2f}</div>'
        f'<div class="pnl-subtitle">{wallet_count} wallets · {chain_count} chains</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

st.markdown("<div style='height:20px;'></div>", unsafe_allow_html=True)

# ── Wallet Cards ─────────────────────────────────────────────────────────────
if wallet_data:
    cols = st.columns(len(wallet_data))

    for i, (key, data) in enumerate(wallet_data.items()):
        wallet = data["config"]
        nw = data["net_worth"]
        wallet_usd = nw.get("total_networth_usd", 0.0)

        # Determine status
        has_key = wallet.has_private_key
        is_cold = wallet.is_cold_storage
        if is_cold:
            status_html = '<span style="color:#58A6FF;font-size:0.72rem;font-weight:600;">🧊 COLD STORAGE</span>'
        elif has_key:
            status_html = '<span style="color:#00D09C;font-size:0.72rem;font-weight:600;">🟢 ACTIVE</span>'
        else:
            status_html = '<span style="color:#FFB84D;font-size:0.72rem;font-weight:600;">🟡 PAPER</span>'

        # Chain pills
        chain_pills = ""
        for chain in wallet.chains:
            emoji = CHAIN_EMOJI.get(chain, "⬡")
            color = CHAIN_COLORS.get(chain, "#8B949E")
            chain_pills += (
                f'<span style="display:inline-flex;align-items:center;gap:3px;'
                f'padding:2px 8px;border-radius:12px;font-size:0.65rem;font-weight:600;'
                f'background:rgba({_hex_to_rgb(color)},0.1);color:{color};'
                f'border:1px solid rgba({_hex_to_rgb(color)},0.2);margin:2px 2px;">'
                f'{emoji} {chain[:3].upper()}</span>'
            )

        # Address display
        addr_short = f"{wallet.address[:6]}...{wallet.address[-4:]}"
        sol_addr = getattr(wallet, "solana_address", "")
        sol_display = f"{sol_addr[:4]}...{sol_addr[-4:]}" if sol_addr else ""

        with cols[i]:
            st.markdown(
                f'<div class="glass-card" style="height:100%;">'
                # Header
                f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">'
                f'<div>'
                f'<div style="font-size:1.1rem;font-weight:800;color:#E6EDF3;">{wallet.alias}</div>'
                f'<div style="color:#484F58;font-size:0.7rem;font-family:\'JetBrains Mono\',monospace;">'
                f'{addr_short}</div>'
                f'</div>'
                f'{status_html}'
                f'</div>'
                # Value
                f'<div style="margin:16px 0;">'
                f'<div style="color:#484F58;font-size:0.65rem;font-weight:700;text-transform:uppercase;'
                f'letter-spacing:0.1em;">Net Worth</div>'
                f'<div style="color:#E6EDF3;font-size:1.8rem;font-weight:700;'
                f'font-family:\'JetBrains Mono\',monospace;">${wallet_usd:,.2f}</div>'
                f'</div>'
                # Role
                f'<div style="color:#8B949E;font-size:0.75rem;margin-bottom:12px;'
                f'line-height:1.4;">{wallet.role}</div>'
                # Strategies
                f'<div style="color:#484F58;font-size:0.62rem;font-weight:700;text-transform:uppercase;'
                f'letter-spacing:0.08em;margin-bottom:4px;">Strategies</div>'
                f'<div style="color:#A371F7;font-size:0.75rem;font-weight:500;">'
                f'{" · ".join(s.replace("_", " ").title() for s in wallet.strategies)}</div>'
                # Chains
                f'<div style="margin-top:12px;">'
                f'<div style="color:#484F58;font-size:0.62rem;font-weight:700;text-transform:uppercase;'
                f'letter-spacing:0.08em;margin-bottom:4px;">Chains</div>'
                f'<div style="display:flex;flex-wrap:wrap;">{chain_pills}</div>'
                f'</div>'
                # Guardrails
                f'<div style="margin-top:12px;padding-top:12px;border-top:1px solid rgba(48,54,61,0.3);">'
                f'<div style="display:flex;gap:16px;">'
                f'<div>'
                f'<div style="color:#484F58;font-size:0.58rem;font-weight:600;text-transform:uppercase;">Max Positions</div>'
                f'<div style="color:#E6EDF3;font-size:0.85rem;font-weight:600;">{wallet.max_concurrent_positions}</div>'
                f'</div>'
                f'<div>'
                f'<div style="color:#484F58;font-size:0.58rem;font-weight:600;text-transform:uppercase;">Daily Loss Limit</div>'
                f'<div style="color:#E6EDF3;font-size:0.85rem;font-weight:600;">{wallet.daily_loss_limit_eth} ETH</div>'
                f'</div>'
                f'<div>'
                f'<div style="color:#484F58;font-size:0.58rem;font-weight:600;text-transform:uppercase;">Max Size</div>'
                f'<div style="color:#E6EDF3;font-size:0.85rem;font-weight:600;">{wallet.max_position_size_pct}%</div>'
                f'</div>'
                f'</div>'
                f'</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

st.markdown("<div style='height:24px;'></div>", unsafe_allow_html=True)

# ── Chain Breakdown (from Moralis net-worth data) ────────────────────────────
st.markdown("#### 🔗 Value by Chain")

chain_totals = {}
for key, data in wallet_data.items():
    for chain_entry in data["net_worth"].get("chains", []):
        chain_name = chain_entry.get("chain", "unknown")
        chain_val = chain_entry.get("networth_usd", 0.0)
        if chain_val > 0.01:
            chain_totals[chain_name] = chain_totals.get(chain_name, 0.0) + chain_val

if chain_totals:
    chain_col1, chain_col2 = st.columns([2, 1])

    with chain_col1:
        # Horizontal bar chart
        sorted_chains = sorted(chain_totals.items(), key=lambda x: x[1], reverse=True)
        chain_names = [c[0].capitalize() for c in sorted_chains]
        chain_values = [c[1] for c in sorted_chains]
        bar_colors = [CHAIN_COLORS.get(c[0], "#8B949E") for c in sorted_chains]

        fig_bar = go.Figure()
        fig_bar.add_trace(go.Bar(
            y=chain_names,
            x=chain_values,
            orientation="h",
            marker_color=bar_colors,
            marker_line=dict(color="#06090F", width=1),
            text=[f"${v:,.2f}" for v in chain_values],
            textposition="auto",
            textfont=dict(color="#E6EDF3", size=11, family="JetBrains Mono, Inter"),
            hovertemplate="<b>%{y}</b><br>$%{x:,.2f}<extra></extra>",
        ))
        bar_layout = {**PLOTLY_LAYOUT, "showlegend": False}
        fig_bar.update_layout(
            **bar_layout,
            height=max(180, len(sorted_chains) * 50),
            yaxis=dict(
                autorange="reversed",
                gridcolor="rgba(255,255,255,0.03)",
                tickfont=dict(size=12, color="#E6EDF3", family="Inter"),
            ),
            xaxis=dict(
                gridcolor="rgba(255,255,255,0.03)",
                tickfont=dict(size=10, color="#484F58"),
                tickprefix="$",
            ),
        )
        st.plotly_chart(fig_bar, use_container_width=True, config={"displayModeBar": False})

    with chain_col2:
        # Donut chart
        fig_donut = go.Figure(data=[go.Pie(
            labels=chain_names,
            values=chain_values,
            hole=0.72,
            marker=dict(colors=bar_colors, line=dict(color="#06090F", width=2)),
            textinfo="percent",
            textfont=dict(size=11, color="#E6EDF3"),
            hovertemplate="<b>%{label}</b><br>$%{value:,.2f} (%{percent})<extra></extra>",
        )])
        fig_donut.update_layout(
            **PLOTLY_LAYOUT,
            height=max(180, len(sorted_chains) * 50),
            annotations=[dict(
                text=f"<b>${sum(chain_values):,.0f}</b><br>total",
                x=0.5, y=0.5, font_size=14,
                font=dict(color="#E6EDF3", family="JetBrains Mono, Inter"),
                showarrow=False,
            )],
        )
        st.plotly_chart(fig_donut, use_container_width=True, config={"displayModeBar": False})
else:
    st.markdown(
        '<div class="glass-card" style="text-align:center;padding:2.5rem;">'
        '<div style="font-size:1.5rem;margin-bottom:0.5rem;">🔗</div>'
        '<div style="color:#8B949E;">No chain data available</div>'
        '<div style="color:#484F58;font-size:0.78rem;margin-top:4px;">'
        'Moralis API key may not be configured</div>'
        '</div>',
        unsafe_allow_html=True,
    )

st.markdown("<div style='height:24px;'></div>", unsafe_allow_html=True)

# ── Token Holdings Table ─────────────────────────────────────────────────────
st.markdown("#### 💰 Token Holdings")

wallet_filter = st.selectbox(
    "Wallet",
    ["All Wallets"] + [w.alias for w in WALLETS.values()] if wallets_available else ["All Wallets"],
)

# Collect tokens across wallets & chains
all_tokens = []
target_wallets = WALLETS.items() if wallet_filter == "All Wallets" else [
    (k, v) for k, v in WALLETS.items() if v.alias == wallet_filter
]

for key, wallet in target_wallets:
    for chain in wallet.chains:
        if chain == "solana":
            continue  # Moralis doesn't support Solana ERC20 balances
        tokens = safe_token_balances(wallet.address, chain)
        for t in tokens:
            t["wallet"] = wallet.alias
        all_tokens.extend(tokens)

if all_tokens:
    # Sort by USD value descending
    all_tokens.sort(key=lambda t: t.get("usd_value", 0), reverse=True)

    # Build clean dataframe
    token_rows = []
    for t in all_tokens[:50]:
        usd_val = t.get("usd_value", 0)
        if usd_val < 0.01:
            continue
        emoji = CHAIN_EMOJI.get(t.get("chain", ""), "⬡")
        token_rows.append({
            "Wallet": t.get("wallet", ""),
            "Token": t.get("symbol", "???"),
            "Chain": f"{emoji} {t.get('chain', '').capitalize()}",
            "Balance": f"{t.get('balance', 0):,.4f}" if t.get("balance", 0) < 1e6 else f"{t.get('balance', 0):,.0f}",
            "Price": f"${t.get('usd_price', 0):,.6f}" if t.get("usd_price", 0) < 1 else f"${t.get('usd_price', 0):,.2f}",
            "Value": f"${usd_val:,.2f}",
            "Verified": "✅" if t.get("verified_contract") else "⚠️",
        })

    if token_rows:
        df_tokens = pd.DataFrame(token_rows)
        st.dataframe(
            df_tokens,
            use_container_width=True,
            hide_index=True,
            height=min(600, len(token_rows) * 40 + 40),
        )
    else:
        st.markdown(
            '<div class="glass-card" style="text-align:center;padding:2rem;">'
            '<div style="color:#8B949E;">No token holdings above $0.01</div>'
            '</div>',
            unsafe_allow_html=True,
        )
else:
    st.markdown(
        '<div class="glass-card" style="text-align:center;padding:2.5rem;">'
        '<div style="font-size:1.5rem;margin-bottom:0.5rem;">💰</div>'
        '<div style="color:#8B949E;">No token balances found</div>'
        '<div style="color:#484F58;font-size:0.78rem;margin-top:4px;">'
        'Token data will appear as the Moralis API responds</div>'
        '</div>',
        unsafe_allow_html=True,
    )

st.markdown("<div style='height:24px;'></div>", unsafe_allow_html=True)

# ── Moralis API Status ───────────────────────────────────────────────────────
if moralis_available:
    with st.expander("🔌 Moralis API Status", expanded=False):
        stats = get_usage_stats()
        api_col1, api_col2, api_col3 = st.columns(3)
        with api_col1:
            configured = stats.get("api_key_configured", False)
            status_text = "🟢 Connected" if configured else "🔴 Not Configured"
            st.metric("API Key", status_text)
        with api_col2:
            st.metric("Cached Queries", stats.get("cached_keys", 0))
        with api_col3:
            st.metric("Calls This Minute", stats.get("rate_calls_in_window", 0))



