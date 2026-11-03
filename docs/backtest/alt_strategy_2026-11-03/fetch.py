# Offline research script (2026-11-03). Never imported by the live bot. See ../ALT_STRATEGY_RESEARCH_2026-11-03.md
import json, sys, time, csv
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from backtest import hl_data
OLD = Path(__file__).parent / "old_cache"  # optional older cache to merge
OUT = Path(__file__).parent / "data"; OUT.mkdir(exist_ok=True)
ALLOW = "BTC,AAVE,MON,DYDX,VVV,XMR,TNSR,VIRTUAL,BANANA,RESOLV,LTC,JUP,PUMP,AERO,INJ,LINK,SKY,SYRUP".split(",")
coins = ALLOW + ["ETH", "SOL"]
now = int(time.time()*1000)
for c in coins:
    old = {}
    p = OLD / f"{c}_1h.csv"
    if p.exists():
        for r in csv.DictReader(open(p)):
            old[int(r["t"])] = {k: float(r[k]) for k in "ohlcv"} | {"t": int(r["t"])}
    start = (max(old) - 48*3600_000) if old else now - 4990*3600_000
    new = hl_data.fetch_candles(c, "1h", start, now)
    for n in new: old[int(n["t"])] = {"t": int(n["t"]), **{k: float(n[k]) for k in "ohlcv"}}
    rows = [old[k] for k in sorted(old) if k + 3600_000 <= now]  # closed bars only
    with open(OUT / f"{c}_1h.csv", "w") as f:
        w = csv.DictWriter(f, fieldnames=list("tohlcv")); w.writeheader(); w.writerows(rows)
    fo = {}
    fp = OLD / "funding" / f"{c}.json"
    if fp.exists():
        for r in json.load(open(fp)): fo[r["time"]] = r
    fstart = (max(fo) - 48*3600_000) if fo else rows[0]["t"]
    for r in hl_data.fetch_funding_history(c, fstart, now): fo[r["time"]] = r
    json.dump([fo[k] for k in sorted(fo)], open(OUT / f"{c}_funding.json", "w"))
    # 15m (max ~5000 bars)
    m15 = hl_data.fetch_candles(c, "15m", now - 5000*900_000, now)
    with open(OUT / f"{c}_15m.csv", "w") as f:
        w = csv.DictWriter(f, fieldnames=list("tohlcv")); w.writeheader()
        w.writerows([{"t": int(n["t"]), **{k: float(n[k]) for k in "ohlcv"}} for n in m15 if int(n["t"]) + 900_000 <= now])
    print(c, len(rows), len(fo), len(m15), flush=True)
