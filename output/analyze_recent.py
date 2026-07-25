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
                open_row = open_stack.pop(0)
                duration_min = (row["dt"] - open_row["dt"]).total_seconds() / 60.0
                trades.append({
                    "coin": coin,
                    "direction": "Long" if "Long" in row["dir"] else "Short",
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

# Filter for recent (July 17 - July 24)
rec = tdf[tdf["close_time"] >= "2026-07-17"].copy()

print("==================================================")
print(f"RECENT PERIOD TRADES ANALYSIS (July 17 - July 24, {len(rec)} trades)")
print("==================================================")

def get_dur_bucket(m):
    if m <= 1: return "< 1m"
    elif m <= 5: return "1m - 5m"
    elif m <= 30: return "5m - 30m"
    elif m <= 90: return "30m - 1.5h"
    elif m <= 240: return "1.5h - 4h"
    else: return "> 4h"

rec["dur_bucket"] = rec["duration_min"].apply(get_dur_bucket)
dur_order = ["< 1m", "1m - 5m", "5m - 30m", "30m - 1.5h", "1.5h - 4h", "> 4h"]

dur_summary = rec.groupby("dur_bucket").agg(
    count=("pnl", "count"),
    net_pnl=("pnl", "sum"),
    wins=("pnl", lambda s: (s > 0).sum()),
    losses=("pnl", lambda s: (s <= 0).sum()),
    avg_pnl=("pnl", "mean")
).reindex(dur_order).reset_index()
dur_summary["win_rate"] = dur_summary["wins"] / dur_summary["count"] * 100

print("\n--- RECENT PERFORMANCE BY HOLD DURATION ---")
print(dur_summary.to_string(index=False))

rec_coin = rec.groupby("coin").agg(
    count=("pnl", "count"),
    net_pnl=("pnl", "sum"),
    wins=("pnl", lambda s: (s > 0).sum()),
    losses=("pnl", lambda s: (s <= 0).sum())
).reset_index()
rec_coin["win_rate"] = rec_coin["wins"] / rec_coin["count"] * 100
rec_coin = rec_coin.sort_values("net_pnl", ascending=False)

print("\n--- RECENT PERFORMANCE BY COIN (July 17 - July 24) ---")
print(rec_coin.to_string(index=False))

print("\n--- RECENT TRADES SUMMARY (< 1m duration sample) ---")
print(rec[rec["duration_min"] <= 1][["coin", "direction", "open_time", "close_time", "pnl", "fee"]].head(20).to_string(index=False))
