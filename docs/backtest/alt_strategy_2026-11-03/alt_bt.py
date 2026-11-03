"""Alt-strategy walk-forward research (mean reversion + funding carry) on HL perps.
Research only. Costs mirror backtest/sim.py: taker 4.5 bps/side + 5 bps adverse slip
(applied on BOTH entry and exit here, stricter than sim.py), funding paid/received hourly.
Signal on bar close -> enter next bar open. Stop checked intrabar first (conservative).
"""
import json, itertools, sys
from pathlib import Path
import numpy as np, pandas as pd

D = Path(__file__).parent / "data"
TAKER, SLIP, NOTIONAL = 0.00045, 0.0005, 100.0
ALLOW = "BTC,AAVE,MON,DYDX,VVV,XMR,TNSR,VIRTUAL,BANANA,RESOLV,LTC,JUP,PUMP,AERO,INJ,LINK,SKY,SYRUP".split(",")
HARD_BAN = set("KAITO,APE,HEMI,ONDO,GRASS,TRB,HMSTR,FARTCOIN,MET,EIGEN,MORPHO,LIT,HYPE,BRETT,POPCAT,MEME,JTO,ENA,ZEC,ETH,BSV,CRV,PENDLE,UNI,ACE,ADA,STABLE,SUI,LDO,ETHFI,SOL,TRX".split(","))
HOUR = 3600_000

def load(coin, tf="1h"):
    df = pd.read_csv(D / f"{coin}_{tf}.csv")
    f = pd.DataFrame(json.load(open(D / f"{coin}_funding.json")))
    f["h"] = (f.time // HOUR) * HOUR
    fr = f.groupby("h").funding.last()
    bar = HOUR if tf == "1h" else 900_000
    # funding settled at hour boundary h is attributed to the bar that ENDS at h
    df["fund_end"] = ((df.t + bar) // HOUR * HOUR).map(fr).where(((df.t + bar) % HOUR) == 0).fillna(0.0)
    # last known hourly rate at bar close (for signals)
    df["fund_now"] = ((df.t + bar) // HOUR * HOUR).map(fr).ffill()
    return df

def indicators(df, bph):
    c, h, l, v = df.c, df.h, df.l, df.v
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    df["atr"] = tr.ewm(alpha=1/14, adjust=False).mean()
    for n in (24, 48):
        N = n * bph
        m = c.rolling(N).mean(); s = c.rolling(N).std()
        df[f"sma{n}"] = m; df[f"z{n}"] = (c - m) / s
    d = c.diff(); up = d.clip(lower=0).ewm(alpha=1/14, adjust=False).mean(); dn = (-d.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
    df["rsi"] = 100 - 100 / (1 + up / dn)
    tp = (h + l + c) / 3; N = 24 * bph
    df["vwap24"] = (tp * v).rolling(N).sum() / v.rolling(N).sum()
    df["vdev"] = (c - df.vwap24) / df.atr
    df["f3"] = df.fund_now.rolling(3 * bph).mean()
    df["f8"] = df.fund_now.rolling(8 * bph).mean()
    return df

def simulate(df, coin, entry_fn, exit_fn, side, hold_bars, atr_k):
    """side: +1 long, -1 short. entry_fn(i)->bool on bar i close. exit_fn(j)->bool on bar j close."""
    o, h, l, c, t = df.o.values, df.h.values, df.l.values, df.c.values, df.t.values
    fe, atr = df.fund_end.values, df.atr.values
    sig = entry_fn
    trades, i, n = [], 0, len(df)
    while i < n - 2:
        if not sig[i] or np.isnan(atr[i]):
            i += 1; continue
        e = i + 1; px = o[e] * (1 + side * SLIP)
        stop = px - side * atr_k * atr[i] if atr_k else None
        fund, x, xp, reason = 0.0, None, None, None
        j = e
        while j < n:
            if stop is not None:
                if side == 1 and (o[j] <= stop or l[j] <= stop):
                    xp = min(o[j], stop) * (1 - SLIP); x = j; reason = "stop"; break
                if side == -1 and (o[j] >= stop or h[j] >= stop):
                    xp = max(o[j], stop) * (1 + SLIP); x = j; reason = "stop"; break
            fund += fe[j]          # funding at end of bar j while held
            if j + 1 >= n: xp = c[j]; x = j; reason = "eod"; break
            if exit_fn[j]: xp = o[j + 1] * (1 - side * SLIP); x = j + 1; reason = "target"; break
            if j - e + 1 >= hold_bars: xp = o[j + 1] * (1 - side * SLIP); x = j + 1; reason = "time"; break
            j += 1
        ret = side * (xp / px - 1) - 2 * TAKER - side * fund
        trades.append((coin, side, int(t[e]), int(t[x]), ret, reason, fund * -side))
        i = x  # next signal no earlier than the exit bar
    return trades

def mr_variants():
    sigs = [("z24", 2.0), ("z24", 2.5), ("z48", 2.0), ("z48", 2.5), ("rsi", 25), ("rsi", 20), ("vdev", 2.0), ("vdev", 3.0)]
    for (kind, thr), hold, k in itertools.product(sigs, (12, 24), (2.0, 3.0)):
        yield dict(strat="MR", kind=kind, thr=thr, hold=hold, atr_k=k)

def fc_variants():
    for thr, hold, k, filt in itertools.product((5e-5, 1e-4), (24, 72), (0, 3.0), (False, True)):
        yield dict(strat="FC", thr=thr, hold=hold, atr_k=k, filt=filt)

def run_variant(dfs, var, side, bph):
    out = []
    for coin, df in dfs.items():
        if var["strat"] == "MR":
            kind, thr = var["kind"], var["thr"]
            if kind.startswith("z"):
                z = df[kind]; m = df["sma" + kind[1:]]
                ent = (z <= -thr) if side == 1 else (z >= thr)
                ext = (df.c >= m) if side == 1 else (df.c <= m)
            elif kind == "rsi":
                ent = (df.rsi <= thr) if side == 1 else (df.rsi >= 100 - thr)
                ext = (df.rsi >= 50) if side == 1 else (df.rsi <= 50)
            else:
                ent = (df.vdev <= -thr) if side == 1 else (df.vdev >= thr)
                ext = (df.c >= df.vwap24) if side == 1 else (df.c <= df.vwap24)
        else:
            thr = var["thr"]
            if side == -1:   # collect positive funding by shorting
                ent = df.f3 >= thr; ext = df.f8 < thr / 2
                if var["filt"]: ent &= df.c < df.sma48
            else:            # collect negative funding by going long
                ent = df.f3 <= -thr / 2; ext = df.f8 > -thr / 4
                if var["filt"]: ent &= df.c > df.sma48
        out += simulate(df, coin, ent.fillna(False).values, ext.fillna(False).values, side, var["hold"] * bph, var["atr_k"])
    return pd.DataFrame(out, columns=["coin", "side", "t_in", "t_out", "ret", "reason", "fund_pnl"])

def stats(tr, days):
    if len(tr) == 0: return dict(n=0, pf=0, wr=0, net=0, dd=0, tpw=0, fund=0)
    r = tr.ret.values; w = r[r > 0].sum(); ls = -r[r < 0].sum()
    eq = (tr.sort_values("t_out").ret.values * NOTIONAL).cumsum(); dd = (np.maximum.accumulate(np.r_[0, eq]) - np.r_[0, eq]).max()
    return dict(n=len(r), pf=round(w / ls, 3) if ls else 99.0, wr=round((r > 0).mean() * 100, 1), net=round(r.sum() * NOTIONAL, 2),
                dd=round(dd, 2), tpw=round(len(r) / (days / 7), 1), fund=round(tr.fund_pnl.sum() * NOTIONAL, 2))

def walk_forward(results, t0, t1, train_d=60, test_d=20, min_is=20):
    folds, oos, picks = [], [], []
    s = t0 + train_d * 86400_000
    while s < t1:
        e = min(s + test_d * 86400_000, t1)
        best, bkey = None, None
        for key, tr in results.items():
            is_ = tr[(tr.t_in >= s - train_d * 86400_000) & (tr.t_in < s)]
            st = stats(is_, train_d)
            if st["n"] < min_is: continue
            score = (st["pf"], st["net"])
            if best is None or score > best: best, bkey = score, key
        if bkey is not None:
            o = results[bkey]; o = o[(o.t_in >= s) & (o.t_in < e)]
            oos.append(o); picks.append((pd.to_datetime(s, unit="ms", utc=True).tz_convert("America/New_York").strftime("%m-%d"), bkey, best[0], len(o)))
        s = e
    allo = pd.concat(oos) if oos else pd.DataFrame(columns=["ret", "t_out", "fund_pnl"])
    return allo, picks, (t1 - (t0 + train_d * 86400_000)) / 86400_000

def main(tf="1h", universe="all", train_d=60, test_d=20, min_is=20, tag=None):
    bph = 1 if tf == "1h" else 4
    coins = ALLOW + ["ETH", "SOL"]
    if universe == "noban": coins = [c for c in coins if c not in HARD_BAN]
    dfs = {c: indicators(load(c, tf), bph) for c in coins}
    warm = 50 * bph
    t0 = max(int(df.t.iloc[warm]) for df in dfs.values()); t1 = max(int(df.t.iloc[-1]) for df in dfs.values())
    for df in dfs.values(): df.drop(df.index[df.t < t0 - 0], inplace=True); df.reset_index(drop=True, inplace=True)
    report = {"tf": tf, "universe": universe, "coins": coins, "t0": t0, "t1": t1, "strategies": {}}
    for strat, gen in (("MR", mr_variants), ("FC", fc_variants)):
        for side_name, sides in (("long", (1,)), ("short", (-1,)), ("both", (1, -1))):
            results = {}
            for var in gen():
                key = json.dumps(var, sort_keys=True)
                results[key] = pd.concat([run_variant(dfs, var, sd, bph) for sd in sides], ignore_index=True)
            oos, picks, oos_days = walk_forward(results, t0, t1, train_d, test_d, min_is)
            full = {k: stats(v, (t1 - t0) / 86400_000) for k, v in results.items()}
            # hindsight-best (for context only, NOT a valid pick)
            hb = max(full.items(), key=lambda kv: (kv[1]["pf"] if kv[1]["n"] >= 40 else 0))
            hb_oos = results[hb[0]]; hb_oos = hb_oos[hb_oos.t_in >= t0 + train_d * 86400_000]
            report["strategies"][f"{strat}_{side_name}"] = dict(
                variants=len(results), wf_oos=stats(oos, oos_days), oos_days=round(oos_days, 1), picks=picks,
                wf_oos_by_coin=oos.groupby("coin").ret.agg(["count", "sum"]).round(4).to_dict("index") if len(oos) else {},
                wf_oos_reasons=oos.reason.value_counts().to_dict() if len(oos) else {},
                hindsight_best=dict(var=hb[0], full=hb[1], oos_window=stats(hb_oos, oos_days)),
                n_variants_full_pf_gt_1=sum(1 for v in full.values() if v["pf"] > 1 and v["n"] >= 40),
                median_full_pf=float(np.median([v["pf"] for v in full.values() if v["n"] >= 40] or [0])))
            r = report["strategies"][f"{strat}_{side_name}"]
            print(tf, universe, strat, side_name, "variants", len(results), "WF-OOS", r["wf_oos"], "| hindsight", hb[1]["pf"], r["hindsight_best"]["oos_window"]["pf"], "| #full PF>1:", r["n_variants_full_pf_gt_1"], "median", r["median_full_pf"], flush=True)
    tag = tag or f"{tf}_{universe}"
    json.dump(report, open(Path(__file__).parent / f"result_{tag}.json", "w"), indent=1, default=str)

if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "15m": main("15m", a[1] if len(a) > 1 else "all", train_d=21, test_d=7, min_is=15)
    else: main("1h", a[0] if a else "all")
