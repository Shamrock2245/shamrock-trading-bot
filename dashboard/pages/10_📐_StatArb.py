"""
dashboard/pages/10_📐_StatArb.py — CEX/DEX Statistical Arbitrage Dashboard

Displays:
  • Live engine status (enabled, thresholds, trade size)
  • Active delta-neutral positions with real-time spread tracking
  • Completed trade history with PnL breakdown
  • Cumulative profit chart
  • Spread distribution across watchlist
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st
import pandas as pd

# ─────────────────────────────────────────────────────────────────────────────
# Page config
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="StatArb | Shamrock Bot",
    page_icon="📐",
    layout="wide",
)

# ─────────────────────────────────────────────────────────────────────────────
# State file path
# ─────────────────────────────────────────────────────────────────────────────
_STATE_DIR = Path(os.getenv("DASHBOARD_STATE_DIR", "./data/dashboard"))
_STATE_FILE = _STATE_DIR / "stat_arb_state.json"


def load_state() -> dict:
    """Load the stat arb state JSON written by StatArbEngine._save_state()."""
    try:
        if _STATE_FILE.exists():
            with open(_STATE_FILE) as f:
                return json.load(f)
    except Exception:
        pass
    return {}


# ─────────────────────────────────────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────────────────────────────────────
st.title("📐 CEX/DEX Statistical Arbitrage")
st.caption(
    "Delta-neutral basis trades: **Spot BUY on Raydium/Aerodrome** + "
    "**1× Short on Hyperliquid**. Entry when spread > 2.5%, exit when < 0.5%."
)

state = load_state()

if not state:
    st.info(
        "StatArb engine has not run yet. The daemon starts 45 seconds after bot launch. "
        "Refresh this page after the bot is running."
    )
    st.stop()

# ─────────────────────────────────────────────────────────────────────────────
# Engine Status Row
# ─────────────────────────────────────────────────────────────────────────────
st.subheader("Engine Status")

col1, col2, col3, col4, col5, col6 = st.columns(6)

enabled = state.get("enabled", False)
col1.metric(
    "Status",
    "🟢 ACTIVE" if enabled else "🔴 DISABLED",
)
col2.metric("Entry Threshold", f"{state.get('entry_threshold_pct', 2.5):.1f}%")
col3.metric("Exit Threshold",  f"{state.get('exit_threshold_pct', 0.5):.1f}%")
col4.metric("Trade Size",      f"${state.get('trade_size_usd', 50):.0f}/leg")
col5.metric("Active Positions", state.get("active_positions", 0))
col6.metric(
    "Total Net PnL",
    f"${state.get('total_net_profit_usd', 0):+.2f}",
    delta=None,
)

st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# Active Positions
# ─────────────────────────────────────────────────────────────────────────────
st.subheader("Active Delta-Neutral Positions")

active = state.get("active_positions", {})
if not active:
    st.info("No active StatArb positions. Waiting for a spread > entry threshold.")
else:
    rows = []
    for sym, pos in active.items():
        opened_at = pos.get("opened_at", "")
        hold_h = 0.0
        try:
            opened_dt = datetime.fromisoformat(opened_at.replace("Z", "+00:00"))
            hold_h = (datetime.now(timezone.utc) - opened_dt).total_seconds() / 3600.0
        except Exception:
            pass

        entry_spread = pos.get("entry_spread_pct", 0)
        current_spread = pos.get("current_spread_pct", 0)
        spread_captured = entry_spread - current_spread
        unrealized_pct = spread_captured / entry_spread * 100 if entry_spread else 0

        rows.append({
            "Symbol": sym,
            "Chain": pos.get("chain", ""),
            "DEX": pos.get("dex_name", ""),
            "Entry Spread": f"{entry_spread:+.3f}%",
            "Current Spread": f"{current_spread:+.3f}%",
            "Captured": f"{spread_captured:+.3f}%",
            "Progress": f"{unrealized_pct:.0f}%",
            "Size (USD)": f"${pos.get('size_usd', 0):.0f}",
            "Hold Time": f"{hold_h:.1f}h",
            "Status": pos.get("status", "open").upper(),
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# Completed Trades
# ─────────────────────────────────────────────────────────────────────────────
st.subheader("Completed Trades")

recent = state.get("recent_trades", [])
if not recent:
    st.info("No completed StatArb trades yet.")
else:
    rows = []
    cumulative = 0.0
    for t in recent:
        cumulative += t.get("net_profit_usd", 0)
        rows.append({
            "Symbol": t.get("symbol", ""),
            "Entry Spread": f"{t.get('entry_spread_pct', 0):+.3f}%",
            "Exit Spread": f"{t.get('exit_spread_pct', 0):+.3f}%",
            "Captured": f"{t.get('entry_spread_pct', 0) - t.get('exit_spread_pct', 0):+.3f}%",
            "Net PnL": f"${t.get('net_profit_usd', 0):+.4f}",
            "Hold (h)": f"{t.get('hold_hours', 0):.1f}",
            "Closed At": t.get("closed_at", "")[:19].replace("T", " "),
            "Cumulative": f"${cumulative:+.2f}",
        })

    df_trades = pd.DataFrame(rows)
    st.dataframe(df_trades, use_container_width=True, hide_index=True)

    # Cumulative PnL chart
    if len(recent) > 1:
        st.subheader("Cumulative Net PnL")
        cum_data = []
        running = 0.0
        for t in recent:
            running += t.get("net_profit_usd", 0)
            cum_data.append({
                "Trade": t.get("symbol", ""),
                "Cumulative PnL ($)": round(running, 4),
            })
        df_chart = pd.DataFrame(cum_data)
        st.line_chart(df_chart.set_index("Trade")["Cumulative PnL ($)"])

st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# Strategy Info
# ─────────────────────────────────────────────────────────────────────────────
with st.expander("Strategy Details & Configuration", expanded=False):
    st.markdown("""
### CEX/DEX Statistical Arbitrage — How It Works

**Premise:** Perpetual futures on Hyperliquid frequently trade at a premium to the
underlying spot price on DEXes (Raydium, Aerodrome, Jupiter). This premium is the
*basis* and it always converges to zero as funding rates force alignment.

**Entry (Spread > 2.5%):**
1. **Spot BUY** on DEX — buy the token at the cheaper spot price
2. **1× Short** on Hyperliquid — short the perp at the inflated futures price
3. Net directional exposure = **zero** (delta neutral)

**Exit (Spread < 0.5%):**
1. **Close HL Short** — buy back the perp at the now-lower price
2. **Sell Spot** on DEX — sell the token at the now-higher spot price
3. Pocket the spread minus fees (~0.6% round-trip)

**Safety Gates:**
- Funding rate check: reject if 8h funding rate is too negative for shorts
- Minimum DEX liquidity: $10,000 required
- Max concurrent positions: configurable (default 5)
- Max hold time: auto-close after 24h regardless of spread

**Configuration (via .env):**
| Variable | Default | Description |
|---|---|---|
| `STAT_ARB_ENABLED` | `true` | Enable/disable the engine |
| `STAT_ARB_ENTRY_THRESHOLD_PCT` | `2.5` | Entry spread threshold (%) |
| `STAT_ARB_EXIT_THRESHOLD_PCT` | `0.5` | Exit spread threshold (%) |
| `STAT_ARB_TRADE_SIZE_USD` | `50` | Per-leg trade size (USD) |
| `STAT_ARB_MAX_POSITIONS` | `5` | Max concurrent arb pairs |
| `STAT_ARB_MAX_HOLD_HOURS` | `24` | Max hold time before force-close |
| `STAT_ARB_MIN_DEX_LIQUIDITY_USD` | `10000` | Min DEX liquidity required |
| `STAT_ARB_FUNDING_RATE_THRESHOLD` | `0.0005` | Max negative funding rate |
    """)

# ─────────────────────────────────────────────────────────────────────────────
# Footer
# ─────────────────────────────────────────────────────────────────────────────
last_updated = state.get("last_updated", "")
scan_count = state.get("scan_count", 0)
opps_found = state.get("total_opportunities_found", 0)

st.caption(
    f"Last updated: {last_updated[:19].replace('T', ' ')} UTC | "
    f"Scans: {scan_count:,} | Opportunities found: {opps_found:,} | "
    f"Auto-refreshes every 15s"
)

# Auto-refresh
st.markdown(
    '<meta http-equiv="refresh" content="15">',
    unsafe_allow_html=True,
)
