import pandas as pd
import numpy as np

csv_path = "/Users/brendan/Downloads/trade_history (39).csv"
df = pd.read_csv(csv_path)
df["dt"] = pd.to_datetime(df["time"], format="%m/%d/%Y - %H:%M:%S")
df = df.sort_values("dt").reset_index(drop=True)

# Pair opens and closes per coin
trades = []

for coin, group in df.groupby("coin"):
    open_stack = []
    for idx, row in group.iterrows():
        is_open = row["dir"].startswith("Open")
        is_close = row["dir"].startswith("Close")
        
        if is_open:
            open_stack.append(row)
        elif is_close:
            if open_stack:
                # FIFO matching or aggregate
                open_row = open_stack.pop(0) # match oldest open
                duration_min = (row["dt"] - open_row["dt"]).total_seconds() / 60.0
                direction = "Long" if "Long" in row["dir"] else "Short"
                trades.append({
                    "coin": coin,
                    "direction": direction,
                    "open_time": open_row["dt"],
                    "close_time": row["dt"],
                    "duration_min": duration_min,
                    "open_px": open_row["px"],
                    "close_px": row["px"],
                    "size": row["sz"],
                    "ntl": row["ntl"],
                    "pnl": row["closedPnl"],
                    "fee": open_row["fee"] + row["fee"]
                })
            else:
                # Close without open in CSV
                trades.append({
                    "coin": coin,
                    "direction": "Long" if "Long" in row["dir"] else "Short",
                    "open_time": row["dt"],
                    "close_time": row["dt"],
                    "duration_min": 0,
                    "open_px": row["px"],
                    "close_px": row["px"],
                    "size": row["sz"],
                    "ntl": row["ntl"],
                    "pnl": row["closedPnl"],
                    "fee": row["fee"]
                })

tdf = pd.DataFrame(trades)

print("==================================================")
print(f"PAIRED TRADES ANALYSIS ({len(tdf)} total trades)")
print("==================================================")

# Duration Buckets
def get_dur_bucket(m):
    if m <= 1: return "< 1m"
    elif m <= 5: return "1m - 5m"
    elif m <= 30: return "5m - 30m"
    elif m <= 90: return "30m - 1.5h"
    elif m <= 240: return "1.5h - 4h"
    else: return "> 4h"

tdf["dur_bucket"] = tdf["duration_min"].apply(get_dur_bucket)
dur_order = ["< 1m", "1m - 5m", "5m - 30m", "30m - 1.5h", "1.5h - 4h", "> 4h"]

dur_summary = tdf.groupby("dur_bucket").agg(
    count=("pnl", "count"),
    net_pnl=("pnl", "sum"),
    wins=("pnl", lambda s: (s > 0).sum()),
    losses=("pnl", lambda s: (s <= 0).sum()),
    avg_pnl=("pnl", "mean")
).reindex(dur_order).reset_index()
dur_summary["win_rate"] = dur_summary["wins"] / dur_summary["count"] * 100

print("\n--- PERFORMANCE BY HOLD DURATION ---")
print(dur_summary.to_string(index=False))

# Direction Breakdown
dir_summary = tdf.groupby("direction").agg(
    count=("pnl", "count"),
    net_pnl=("pnl", "sum"),
    wins=("pnl", lambda s: (s > 0).sum()),
    losses=("pnl", lambda s: (s <= 0).sum()),
    avg_pnl=("pnl", "mean")
).reset_index()
dir_summary["win_rate"] = dir_summary["wins"] / dir_summary["count"] * 100

print("\n--- PERFORMANCE BY DIRECTION (Long vs Short) ---")
print(dir_summary.to_string(index=False))

# Small Losses (< -$2) vs Larger Losses
tdf_losses = tdf[tdf["pnl"] < 0]
small_losses = tdf_losses[tdf_losses["pnl"] >= -2.0]
mid_losses = tdf_losses[(tdf_losses["pnl"] < -2.0) & (tdf_losses["pnl"] >= -10.0)]
huge_losses = tdf_losses[tdf_losses["pnl"] < -10.0]

print("\n--- LOSS SIZE BREAKDOWN ---")
print(f"Small Losses ($-0.01 to $-2.00): {len(small_losses)} trades | Total PnL: ${small_losses['pnl'].sum():.2f} (Avg: ${small_losses['pnl'].mean():.2f})")
print(f"Medium Losses ($-2.01 to $-10.00): {len(mid_losses)} trades | Total PnL: ${mid_losses['pnl'].sum():.2f} (Avg: ${mid_losses['pnl'].mean():.2f})")
print(f"Huge Bleeders (< $-10.00): {len(huge_losses)} trades | Total PnL: ${huge_losses['pnl'].sum():.2f} (Avg: ${huge_losses['pnl'].mean():.2f})")

print("\n--- LIST OF HUGE BLEEDERS (< $-10.00) ---")
print(huge_losses[["coin", "direction", "open_time", "close_time", "duration_min", "pnl"]].to_string(index=False))
