import streamlit as st
import json
from pathlib import Path
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(page_title="Paycheck Wallet", page_icon="🏦", layout="wide")

st.title("🏦 Wallet C — Paycheck Tracker")
st.markdown("Monitor the automated profit sweep from trading capital to cold storage.")

# Load Compound State
state_path = Path("output/compound_state.json")
if not state_path.exists():
    st.warning("No compound state found. The bot needs to run and log trades first.")
    st.stop()

try:
    with open(state_path, "r") as f:
        state = json.load(f)
except Exception as e:
    st.error(f"Failed to load compound state: {e}")
    st.stop()

# Extract key metrics
accumulator = state.get("paycheck_accumulator_usd", 0.0)
total_swept = state.get("total_swept_usd", 0.0)
threshold = 500.0  # Hardcoded in capital_compounder.py
progress_pct = min(100.0, (accumulator / threshold) * 100)

# Top Metrics
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Total Swept to Wallet C", f"${total_swept:,.2f}", "Lifetime Income")
with col2:
    st.metric("Current Accumulator", f"${accumulator:,.2f}", f"{progress_pct:.1f}% to next paycheck")
with col3:
    st.metric("Next Paycheck Trigger", f"${threshold:,.2f}", "Sweeps 50% ($250)")

st.markdown("---")

# Progress Bar
st.subheader("Next Paycheck Progress")
st.progress(progress_pct / 100.0)
st.caption(f"${accumulator:,.2f} / ${threshold:,.2f} accumulated")

st.markdown("---")

# Load Trades to show recent sweeps
trades_path = Path("output/trades.json")
if trades_path.exists():
    try:
        with open(trades_path, "r") as f:
            trades = json.load(f)
            
        # Filter for trades that triggered a sweep
        sweep_trades = [t for t in trades if t.get("sweep_triggered", False)]
        
        if sweep_trades:
            st.subheader("Recent Paycheck Sweeps")
            
            df = pd.DataFrame(sweep_trades)
            df["time"] = pd.to_datetime(df["exit_time"], unit="s")
            df["sweep_amount"] = df["pnl_usd"] * 0.5  # Approximate, actual logic is in compounder
            
            display_df = df[["time", "token_symbol", "chain", "pnl_usd", "sweep_amount"]].copy()
            display_df.columns = ["Time", "Token", "Chain", "Trade PnL ($)", "Est. Swept ($)"]
            display_df = display_df.sort_values("Time", ascending=False)
            
            st.dataframe(display_df, use_container_width=True, hide_index=True)
        else:
            st.info("No paycheck sweeps recorded yet.")
            
    except Exception as e:
        st.error(f"Failed to load trades: {e}")
else:
    st.info("No trades recorded yet.")
