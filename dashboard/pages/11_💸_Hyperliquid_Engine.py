"""
Page 11 — 💸 Institutional Hyperliquid Engine

Tracks the 4 flagship algorithmic features:
1. Retracement Sniper
2. Dynamic Trailing Profit-Lock
3. Delta-Neutral Funding Farmer
4. Kelly Criterion Position Sizing
"""

import sys
import os
import math
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timezone

from styles import PREMIUM_CSS, ACCENT, DANGER, WARNING
from nav import render_nav
from state import (
    get_hl_scanner_state,
    get_hl_trailing_state,
    get_funding_farms,
    get_positions
)

st.set_page_config(page_title="Hyperliquid Engine | Shamrock", page_icon="💸", layout="wide")
st.markdown(PREMIUM_CSS, unsafe_allow_html=True)
render_nav("HL Engine")

st.markdown("""
<div class='section-header'>
    <span class='section-icon'>💸</span>
    <h2>Institutional Engine Operations</h2>
    <div class='pulse-indicator'>LIVE</div>
</div>
<p style="color:#8B949E; font-size:0.8rem; margin-top:-10px; margin-bottom:20px;">
    Monitoring Retracement Sniper, Trailing Locks, Yield Farms, and Kelly Scaling.
</p>
""", unsafe_allow_html=True)

# Fetch States
hl_state = get_hl_scanner_state()
trailing_state = get_hl_trailing_state()
farm_state = get_funding_farms()
positions = get_positions()

# Create a lookup dict for active positions
pos_lookup = {}
for p in positions:
    coin = p.get("coin", "").upper()
    pos_lookup[coin] = {
        "pnl": p.get("unrealized_pnl", 0.0),
        "roi": p.get("roi", 0.0),
        "size": p.get("size", 0.0)
    }

st.markdown("### 1. Dynamic Trailing Profit-Lock 🔒")
if trailing_state:
    trailing_data = []
    for coin, data in trailing_state.items():
        entry = data.get("entry_price", 0)
        highest = data.get("highest_price", 0)
        lowest = data.get("lowest_price")
        if lowest is None:
            lowest = float('inf')
        sl_price = data.get("stop_loss_price", 0)
        is_active = data.get("trailing_stop_active", False)
        side = data.get("side", "")
        
        # Calculate distance
        if side == "long":
            distance = ((highest - sl_price) / highest * 100) if highest else 0
            peak_str = f"${highest:.4f}"
        else:
            distance = ((sl_price - lowest) / lowest * 100) if lowest and lowest != float('inf') else 0
            peak_str = f"${lowest:.4f}" if lowest != float('inf') else "N/A"
            
        # Try to find live PnL
        live_pnl = "N/A"
        live_roi = ""
        if coin in pos_lookup:
            pnl_val = pos_lookup[coin]["pnl"]
            roi_val = pos_lookup[coin]["roi"]
            live_pnl = f"${pnl_val:.2f}"
            live_roi = f"({roi_val:.2f}%)"
            
        trailing_data.append({
            "Coin": coin,
            "Side": side.upper(),
            "Live P&L": f"{live_pnl} {live_roi}",
            "Entry": f"${entry:.4f}",
            "Peak (Best)": peak_str,
            "Trailing SL": f"${sl_price:.4f}",
            "Distance to SL": f"{distance:.2f}%",
            "Active": "🟢 YES" if is_active else "⚪ NO"
        })
    
    if trailing_data:
        st.dataframe(pd.DataFrame(trailing_data), use_container_width=True, hide_index=True)
    else:
        st.info("No active trailing stops. Waiting for a position to hit the ROE trigger.")
else:
    st.info("No active trailing stops. Waiting for a position to hit the ROE trigger.")

st.markdown("<br>", unsafe_allow_html=True)

col1, col2 = st.columns(2)

with col1:
    st.markdown("### 2. Retracement Sniper 🎯")
    last_signals = hl_state.get("last_signals", [])
    if last_signals:
        snipes = []
        for s in last_signals:
            snipes.append({
                "Coin": s.get("coin"),
                "Direction": s.get("direction", "").upper(),
                "Score": s.get("score"),
                "Limit Entry": f"${s.get('entry_price', 0):.4f}",
                "Status": "⏳ Pending EMA21" if s.get("score", 0) >= 65 else "Filtered"
            })
        st.dataframe(pd.DataFrame(snipes), use_container_width=True, hide_index=True)
    else:
        st.info("No recent sniper signals generated.")

with col2:
    st.markdown("### 3. Delta-Neutral Funding Farmer 🌾")
    farms = farm_state.get("active_farms", {})
    if farms:
        farm_data = []
        for coin, data in farms.items():
            live_pnl = "N/A"
            if coin in pos_lookup:
                live_pnl = f"${pos_lookup[coin]['pnl']:.2f}"
                
            farm_data.append({
                "Coin": coin,
                "HL Leg": data.get("hl_side", "").upper(),
                "Spot Leg": data.get("hedge_side", "").upper(),
                "HL Leg P&L": live_pnl,
                "Hourly Yield": f"{data.get('entry_rate', 0)*100:.4f}%/hr",
                "Size": f"${data.get('size_usd', 0):.2f}"
            })
        st.dataframe(pd.DataFrame(farm_data), use_container_width=True, hide_index=True)
    else:
        st.info("No extreme funding rates detected. Farming module idle.")

st.markdown("<br>", unsafe_allow_html=True)

st.markdown("### 4. Kelly Criterion Position Sizing 📈")
st.markdown("Exponential size scaling relative to the 29-indicator signal score.")

# Build a small dataframe for the plot
plot_data = []
min_size = 250.0
max_size = 2500.0
min_score = 65.0
max_score = 95.0
k = math.log(max_size / min_size) / (max_score - min_score)

for score in range(65, 101):
    size = min_size * math.exp(k * (score - min_score))
    size = min(size, max_size)
    plot_data.append({"Signal Score": score, "Allocated Size (USD)": size})
    
df = pd.DataFrame(plot_data)

fig = px.area(df, x="Signal Score", y="Allocated Size (USD)", 
              title="Exponential Position Sizing Curve",
              color_discrete_sequence=["#00D09C"])

# Add markers for recent signals if available
if last_signals:
    for s in last_signals:
        sc = s.get("score", 0)
        if sc >= 65:
            sz = min_size * math.exp(k * (sc - min_score))
            sz = min(sz, max_size)
            fig.add_annotation(x=sc, y=sz,
                               text=s.get("coin"),
                               showarrow=True,
                               arrowhead=1,
                               arrowsize=1,
                               arrowwidth=2,
                               arrowcolor="#FFB84D",
                               font=dict(color="#FFB84D", size=10),
                               ax=0, ay=-30)

fig.update_layout(
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#8B949E"),
    margin=dict(l=0, r=0, t=30, b=0),
    xaxis=dict(gridcolor="rgba(48,54,61,0.2)", showgrid=True),
    yaxis=dict(gridcolor="rgba(48,54,61,0.2)", showgrid=True)
)
st.plotly_chart(fig, use_container_width=True)
