# Offline research script (2026-11-03). Never imported by the live bot. See ../ALT_STRATEGY_RESEARCH_2026-11-03.md
import json, numpy as np, pandas as pd, alt_bt as A
coins = A.ALLOW + ["ETH", "SOL"]
dfs = {c: A.indicators(A.load(c), 1) for c in coins}
t0 = max(int(df.t.iloc[50]) for df in dfs.values()); t1 = max(int(df.t.iloc[-1]) for df in dfs.values())
for df in dfs.values(): df.drop(df.index[df.t < t0], inplace=True); df.reset_index(drop=True, inplace=True)
def cap(tr, k):
    tr = tr.sort_values("t_in"); keep, open_ = [], []
    for r in tr.itertuples():
        open_ = [x for x in open_ if x > r.t_in]
        if len(open_) < k: keep.append(r.Index); open_.append(r.t_out)
    return tr.loc[keep]
res = {json.dumps(v, sort_keys=True): A.run_variant(dfs, v, 1, 1) for v in A.mr_variants()}
od = (t1 - t0) / 864e5 - 60
for k in (3, 5):
    rc = {key: cap(v, k) for key, v in res.items()}
    oos, picks, d = A.walk_forward(rc, t0, t1)
    fx = rc[json.dumps(dict(strat="MR", kind="rsi", thr=20, hold=12, atr_k=3.0), sort_keys=True)]
    print("cap", k, "WF", A.stats(oos, od), "| fixed rsi20 oos", A.stats(fx[fx.t_in >= t0 + 60 * 864e5], od))
