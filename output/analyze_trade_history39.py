import pandas as pd
import numpy as np

csv_path = "/Users/brendan/Downloads/trade_history (39).csv"
df = pd.read_csv(csv_path)
df["dt"] = pd.to_datetime(df["time"], format="%m/%d/%Y - %H:%M:%S")
df = df.sort_values("dt").reset_index(drop=True)

# Closes & Opens
closes = df[df["dir"].str.startswith("Close")].copy()
opens = df[df["dir"].str.startswith("Open")].copy()

total_fills = len(df)
total_fees = df["fee"].sum()
total_net_pnl = closes["closedPnl"].sum()

print("==================================================")
print("     SHAMROCK TRADING BOT - AUDIT OF CSV 39      ")
print("==================================================")
print(f"File: {csv_path}")
print(f"Date Range: {df['dt'].min()} to {df['dt'].max()}")
print(f"Total Fills: {total_fills} ({len(opens)} Opens, {len(closes)} Closes)")
print(f"Total Fees Paid: ${total_fees:.2f}")
print(f"Net Realized PnL: ${total_net_pnl:.2f}")

wins = closes[closes["closedPnl"] > 0]
losses = closes[closes["closedPnl"] <= 0]
win_rate = (len(wins) / len(closes) * 100) if len(closes) > 0 else 0.0
gp = wins["closedPnl"].sum()
gl = abs(losses["closedPnl"].sum())
pf = gp / gl if gl > 0 else 0.0
avg_w = wins["closedPnl"].mean() if len(wins) > 0 else 0.0
avg_l = losses["closedPnl"].mean() if len(losses) > 0 else 0.0

print("\n--- OVERALL CLOSE STATISTICS ---")
print(f"Win Rate: {win_rate:.2f}% ({len(wins)} W / {len(losses)} L out of {len(closes)} closes)")
print(f"Gross Profit: ${gp:.2f}")
print(f"Gross Loss: ${gl:.2f}")
print(f"Profit Factor: {pf:.3f}")
print(f"Avg Win: ${avg_w:.2f} | Avg Loss: ${avg_l:.2f}")
print(f"Payoff Ratio (Avg W / Avg L): {abs(avg_w / avg_l):.2f}" if avg_l != 0 else "N/A")

# Breakdown by Coin
print("\n--- PERFORMANCE BY COIN (Top & Bottom PnL) ---")
coin_summary = closes.groupby("coin").agg(
    count=("closedPnl", "count"),
    net_pnl=("closedPnl", "sum"),
    wins=("closedPnl", lambda s: (s > 0).sum()),
    losses=("closedPnl", lambda s: (s <= 0).sum()),
).reset_index()
coin_summary["win_rate"] = coin_summary["wins"] / coin_summary["count"] * 100
coin_summary = coin_summary.sort_values("net_pnl", ascending=False)

print("Top 10 Winning Coins:")
print(coin_summary.head(10).to_string(index=False))

print("\nBottom 10 Losing Coins:")
print(coin_summary.tail(10).to_string(index=False))

# Breakdown by Hour of Day (UTC and EST)
closes["hour_utc"] = closes["dt"].dt.hour
closes["dt_est"] = closes["dt"].dt.tz_localize("UTC").dt.tz_convert("America/New_York") if closes["dt"].dt.tz else closes["dt"] - pd.Timedelta(hours=4) # EST offset approx
closes["hour_est"] = closes["dt_est"].dt.hour

hour_summary = closes.groupby("hour_est").agg(
    count=("closedPnl", "count"),
    net_pnl=("closedPnl", "sum"),
    win_rate=("closedPnl", lambda s: (s > 0).mean() * 100)
).reset_index()

print("\n--- PERFORMANCE BY HOUR OF DAY (EST / New York) ---")
print(hour_summary.to_string(index=False))

# Breakdown by Date Range (e.g. Last 7 Days, Last 3 Days)
p_7d = closes[closes["dt"] >= "2026-07-17"]
p_7d_w = (p_7d["closedPnl"] > 0).sum()
p_7d_l = (p_7d["closedPnl"] <= 0).sum()
p_7d_pnl = p_7d["closedPnl"].sum()
p_7d_gp = p_7d[p_7d["closedPnl"] > 0]["closedPnl"].sum()
p_7d_gl = abs(p_7d[p_7d["closedPnl"] <= 0]["closedPnl"].sum())
p_7d_pf = p_7d_gp / p_7d_gl if p_7d_gl > 0 else 0.0

print("\n--- RECENT PERIOD (July 17 - July 24, 2026) ---")
print(f"Closes: {len(p_7d)} | Net PnL: ${p_7d_pnl:.2f}")
print(f"Win Rate: {(p_7d_w / len(p_7d) * 100):.2f}% ({p_7d_w} W / {p_7d_l} L)")
print(f"Profit Factor: {p_7d_pf:.3f}")

p_3d = closes[closes["dt"] >= "2026-07-22"]
p_3d_w = (p_3d["closedPnl"] > 0).sum()
p_3d_l = (p_3d["closedPnl"] <= 0).sum()
p_3d_pnl = p_3d["closedPnl"].sum()
p_3d_gp = p_3d[p_3d["closedPnl"] > 0]["closedPnl"].sum()
p_3d_gl = abs(p_3d[p_3d["closedPnl"] <= 0]["closedPnl"].sum())
p_3d_pf = p_3d_gp / p_3d_gl if p_3d_gl > 0 else 0.0

print("\n--- VERY RECENT PERIOD (July 22 - July 24, 2026) ---")
print(f"Closes: {len(p_3d)} | Net PnL: ${p_3d_pnl:.2f}")
print(f"Win Rate: {(p_3d_w / len(p_3d) * 100):.2f}% ({p_3d_w} W / {p_3d_l} L)")
print(f"Profit Factor: {p_3d_pf:.3f}")
