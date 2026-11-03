# Offline research script (2026-11-03). Never imported by the live bot. See ../ALT_STRATEGY_RESEARCH_2026-11-03.md
import json, numpy as np, pandas as pd, alt_bt as A
coins = A.ALLOW + ["ETH", "SOL"]
dfs = {c: A.indicators(A.load(c), 1) for c in coins}
t0 = max(int(df.t.iloc[50]) for df in dfs.values()); t1 = max(int(df.t.iloc[-1]) for df in dfs.values())
for df in dfs.values(): df.drop(df.index[df.t < t0], inplace=True); df.reset_index(drop=True, inplace=True)
res = {json.dumps(v, sort_keys=True): A.run_variant(dfs, v, 1, 1) for v in A.mr_variants()}
oos, picks, d = A.walk_forward(res, t0, t1)
oos = oos.copy(); oos["fold"] = pd.cut(oos.t_in, bins=[t0 + (60 + 20 * k) * 864e5 for k in range(8)] + [t1 + 1], labels=False)
for f, g in oos.groupby("fold"): print("fold", f, A.stats(g, 20))
print("distinct entry days", (oos.t_in // 864e5).nunique(), "of", len(oos))
ev = sorted([(r.t_in, 1) for r in oos.itertuples()] + [(r.t_out, -1) for r in oos.itertuples()]); cur = mx = 0
for _, x in ev: cur += x; mx = max(mx, cur)
print("max concurrent", mx)
print("ET date range OOS:", pd.to_datetime(t0 + 60 * 864e5, unit="ms", utc=True).tz_convert("America/New_York"), "->", pd.to_datetime(t1, unit="ms", utc=True).tz_convert("America/New_York"))
print("data start", pd.to_datetime(t0, unit="ms", utc=True).tz_convert("America/New_York"))
fx = res[json.dumps(dict(strat="MR", kind="rsi", thr=20, hold=12, atr_k=3.0), sort_keys=True)]
print(fx[fx.t_in >= t0 + 60 * 864e5].reason.value_counts().to_dict())
top = fx.assign(day=pd.to_datetime(fx.t_in, unit="ms", utc=True).dt.tz_convert("America/New_York").dt.date).groupby("day").ret.agg(["count", "sum"]).sort_values("sum", ascending=False).head(6); print(top)
