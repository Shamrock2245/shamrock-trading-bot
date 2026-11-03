# Offline research script (2026-11-03). Never imported by the live bot. See ../ALT_STRATEGY_RESEARCH_2026-11-03.md
import json, numpy as np, pandas as pd, alt_bt as A
coins = A.ALLOW + ["ETH", "SOL"]
dfs = {c: A.indicators(A.load(c), 1) for c in coins}
t0 = max(int(df.t.iloc[50]) for df in dfs.values()); t1 = max(int(df.t.iloc[-1]) for df in dfs.values())
oos0 = t0 + 60 * 86400_000
for df in dfs.values(): df.drop(df.index[df.t < t0], inplace=True); df.reset_index(drop=True, inplace=True)
bh = {c: round((df.c.iloc[-1] / df.c[df.t >= oos0].iloc[0] - 1) * 100, 1) for c, df in dfs.items()}
print("buy&hold OOS window % by coin:", bh, "median", np.median(list(bh.values())))
V = dict(strat="MR", kind="rsi", thr=20, hold=12, atr_k=3.0)
tr = A.run_variant(dfs, V, 1, 1)
oos = tr[tr.t_in >= oos0]
print("fixed RSI20 long full", A.stats(tr, (t1 - t0) / 864e5), "oos", A.stats(oos, (t1 - oos0) / 864e5))
# per-fold
s = oos0
while s < t1:
    e = min(s + 20 * 864e5, t1); f = tr[(tr.t_in >= s) & (tr.t_in < e)]
    print("  fold", pd.to_datetime(s, unit="ms", utc=True).tz_convert("America/New_York").strftime("%m-%d"), A.stats(f, 20)); s = e
# clustering: distinct entry days
print("distinct entry hours", oos.t_in.nunique(), "distinct entry days", (oos.t_in // 864e5).nunique(), "of", len(oos))
# top-5 trades share
r = oos.ret.sort_values(ascending=False); print("net excl top5 trades $", round(r.iloc[5:].sum() * 100, 2), "total", round(r.sum() * 100, 2))
# cost stress
A.SLIP = 0.001; tr2 = A.run_variant(dfs, V, 1, 1); print("slip10bps oos", A.stats(tr2[tr2.t_in >= oos0], (t1 - oos0) / 864e5)); A.SLIP = 0.0005
# random-entry control: same coin, same count, same exits (RSI>=50 / 12h / 3ATR)
rng = np.random.default_rng(7); pfs = []
for k in range(200):
    allr = []
    for c, df in dfs.items():
        n_c = (oos.coin == c).sum()
        if n_c == 0: continue
        idx = np.where((df.t >= oos0).values)[0][:-2]
        ent = np.zeros(len(df), bool); ent[rng.choice(idx, size=n_c * 3, replace=False)] = True
        ext = (df.rsi >= 50).fillna(False).values
        t = pd.DataFrame(A.simulate(df, c, ent, ext, 1, 12, 3.0), columns=["coin", "side", "t_in", "t_out", "ret", "reason", "fund_pnl"])
        allr.append(t.sample(min(n_c, len(t)), random_state=k))
    a = pd.concat(allr); r = a.ret; pfs.append(r[r > 0].sum() / -r[r < 0].sum())
pfs = np.array(pfs); print("random-long control PF: median %.3f  p95 %.3f  share>=fixedOOS %.3f" % (np.median(pfs), np.percentile(pfs, 95), (pfs >= A.stats(oos, 1)["pf"]).mean()))
