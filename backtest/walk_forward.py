"""Walk-forward research harness (offline; proposals only).

    python3 -m backtest.walk_forward --out reports/backtest   # full run
    python3 -m backtest.walk_forward --coins INJ,BTC --days 120  # quick

Pipeline: candles (recorder cache ∪ API) → replay the bot's scan_coin per closed
1h bar → simulate exits (backtest.sim) for each exit variant → portfolio
selection per config (non-overlap per coin, max positions, opens/day, best
score first) → vectorbt rolling_split folds: pick the best config on each
train window, score it on the following unseen test window.

Requires vectorbt (pip install -r backtest/requirements.txt). Never imported by
the live bot; writes only under --out.
"""
from __future__ import annotations

import argparse
import itertools
import json
import logging
import math
import time
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from backtest import hl_data, replay, sim

ET = ZoneInfo("America/New_York")
log = logging.getLogger("walk_forward")

ALLOWLIST = ("BTC,AAVE,MON,DYDX,VVV,XMR,TNSR,VIRTUAL,BANANA,RESOLV,LTC,JUP,PUMP,AERO,INJ,LINK,SKY,SYRUP").split(",")
HARD_BAN = ("KAITO,APE,HEMI,ONDO,GRASS,TRB,HMSTR,FARTCOIN,MET,EIGEN,MORPHO,LIT,HYPE,BRETT,POPCAT,MEME,"
            "JTO,ENA,ZEC,ETH,BSV,CRV,PENDLE,UNI,ACE,ADA,STABLE,SUI,LDO,ETHFI,SOL,TRX").split(",")
OTHERS = "XRP,DOGE,AVAX,NEAR,ARB".split(",")
TOXIC_ET = set(range(8, 14))
ALLOWLIST_FORMED_UNTIL = datetime(2026, 7, 27, tzinfo=ET)  # hl_fills window Jun 17–Jul 26

# Current paper baseline (after PRs #21–#24): exec bar 56, long-only, toxic block,
# BE buffer 0.12 in paper, stretched TP demoted −10, 4h loss timeout.
BASELINE = {"exec_bar": 56, "shorts": False, "toxic_block": True, "be_buffer": 0.12,
            "stretched": "demote10", "timeout_h": 4.0}
PRE_FIX = {**BASELINE, "be_buffer": 0.05, "stretched": "keep"}

GRID = {
    "exec_bar": [52, 56, 60, 64, 68],
    "shorts": [False, True],
    "toxic_block": [True, False],
    "be_buffer": [0.05, 0.12],
    "stretched": ["keep", "demote10", "reject"],
    "timeout_h": [2.5, 4.0, 8.0],
}
MAX_POSITIONS = 4
MAX_OPENS_PER_DAY = 6


@dataclass
class Trade:
    coin: str
    direction: str
    entry_ms: int
    exit_ms: int
    hour_et: int
    score: float
    net_pct: float
    r: float
    reason: str
    tp_source: str


def _stretched(src: str) -> bool:
    return "rr_fallback" in src or "rr_stretch" in src


def exit_key(be: float, to: float) -> str:
    return f"be{be}_to{to}"


def compute_outcomes(signals, hourly_by_coin) -> dict:
    """outcomes[(coin, entry_ms, dir)][exit_key] = sim.Outcome"""
    idx = {c: {b["t"]: i for i, b in enumerate(h)} for c, h in hourly_by_coin.items()}
    out = {}
    for s in signals:
        h = hourly_by_coin[s.coin]
        i = idx[s.coin].get(s.t)
        if i is None:
            continue
        fut = h[i + 1:i + 1 + 168]
        res = {}
        for be in GRID["be_buffer"]:
            for to in GRID["timeout_h"]:
                res[exit_key(be, to)] = sim.simulate(s.direction, s.entry, s.sl, s.tp, fut,
                                                     sim.ExitParams(be_buffer_pct=be, timeout_h=to))
        out[(s.coin, s.entry_ms, s.direction)] = res
    return out


def select_trades(signals, outcomes, cfg, start_ms=None, end_ms=None, coins=None) -> list[Trade]:
    ek = exit_key(cfg["be_buffer"], cfg["timeout_h"])
    pool = []
    for s in signals:
        if start_ms is not None and s.entry_ms < start_ms:
            continue
        if end_ms is not None and s.entry_ms >= end_ms:
            continue
        if coins is not None and s.coin not in coins:
            continue
        if s.direction == "short" and not cfg["shorts"]:
            continue
        if cfg["toxic_block"] and s.hour_et in TOXIC_ET:
            continue
        score = s.score
        if _stretched(s.tp_source):
            if cfg["stretched"] == "reject":
                continue
            if cfg["stretched"] == "demote10":
                score -= 10.0
        if score < cfg["exec_bar"]:
            continue
        o = outcomes.get((s.coin, s.entry_ms, s.direction), {}).get(ek)
        if o is None or o.exit_ms == 0:
            continue
        pool.append((s.entry_ms, -score, s, o, score))
    pool.sort(key=lambda x: (x[0], x[1]))
    busy_until: dict[str, int] = {}
    open_exits: list[int] = []
    opens_per_day: dict[str, int] = defaultdict(int)
    trades: list[Trade] = []
    for entry_ms, _, s, o, score in pool:
        if busy_until.get(s.coin, 0) > entry_ms:
            continue
        open_exits = [x for x in open_exits if x > entry_ms]
        if len(open_exits) >= MAX_POSITIONS:
            continue
        day = datetime.fromtimestamp(entry_ms / 1000, ET).strftime("%Y-%m-%d")
        if opens_per_day[day] >= MAX_OPENS_PER_DAY:
            continue
        opens_per_day[day] += 1
        busy_until[s.coin] = o.exit_ms
        open_exits.append(o.exit_ms)
        trades.append(Trade(s.coin, s.direction, entry_ms, o.exit_ms, s.hour_et, score,
                            o.net_pct, o.r, o.reason, s.tp_source))
    return trades


def metrics(trades: list[Trade], days: float | None = None) -> dict:
    n = len(trades)
    if n == 0:
        return {"n": 0, "wr": None, "pf": None, "avg_pct": None, "avg_r": None, "sum_pct": 0.0,
                "max_dd_pct": 0.0, "per_day": 0.0}
    w = [t.net_pct for t in trades if t.net_pct > 0]
    l = [t.net_pct for t in trades if t.net_pct <= 0]
    gl = -sum(l)
    eq = peak = dd = 0.0
    for t in sorted(trades, key=lambda x: x.exit_ms):
        eq += t.net_pct
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
    return {
        "n": n,
        "wr": round(len(w) / n, 3),
        "pf": round(sum(w) / gl, 2) if gl > 0 else (999.0 if w else 0.0),
        "avg_pct": round(sum(t.net_pct for t in trades) / n, 3),
        "avg_r": round(sum(t.r for t in trades) / n, 3),
        "sum_pct": round(sum(t.net_pct for t in trades), 2),
        "max_dd_pct": round(dd, 2),
        "per_day": round(n / days, 2) if days else None,
    }


def all_configs():
    keys = list(GRID)
    for vals in itertools.product(*(GRID[k] for k in keys)):
        yield dict(zip(keys, vals))


def cfg_name(c):
    return (f"bar{c['exec_bar']}|{'L+S' if c['shorts'] else 'L'}|{'tox' if c['toxic_block'] else 'noTox'}"
            f"|be{c['be_buffer']}|{c['stretched']}|to{c['timeout_h']}")


def walk_forward(signals, outcomes, start_ms, end_ms, train_days=60, test_days=20, min_train_trades=20):
    import numpy as np
    import pandas as pd
    import vectorbt as vbt  # noqa: F401  (registers the .vbt accessor)

    days = pd.date_range(pd.Timestamp(start_ms, unit="ms", tz="UTC").normalize(),
                         pd.Timestamp(end_ms, unit="ms", tz="UTC").normalize(), freq="D")
    ser = pd.Series(np.arange(len(days)), index=days)
    window = train_days + test_days
    n_folds = max(1, (len(days) - train_days) // test_days)
    (_, train_ix), (_, test_ix) = ser.vbt.rolling_split(
        n=n_folds, window_len=window, set_lens=(test_days,), left_to_right=False)
    configs = list(all_configs())
    folds = []
    oos_trades: list[Trade] = []
    oos_baseline: list[Trade] = []

    def _ms(ts) -> int:
        return int(pd.Timestamp(ts).timestamp() * 1000)

    for tr, te in zip(train_ix, test_ix):
        tr_s, tr_e = _ms(tr[0]), _ms(tr[-1] + pd.Timedelta(days=1))
        te_s, te_e = _ms(te[0]), _ms(te[-1] + pd.Timedelta(days=1))
        best, best_key = None, None
        for c in configs:
            m = metrics(select_trades(signals, outcomes, c, tr_s, tr_e, coins=set(ALLOWLIST)))
            if m["n"] < min_train_trades or m["avg_pct"] is None or m["avg_pct"] <= 0:
                continue
            key = (min(m["pf"], 10.0), m["avg_pct"])
            if best_key is None or key > best_key:
                best, best_key = c, key
        test_tr = select_trades(signals, outcomes, best, te_s, te_e, coins=set(ALLOWLIST)) if best else []
        base_tr = select_trades(signals, outcomes, BASELINE, te_s, te_e, coins=set(ALLOWLIST))
        oos_trades += test_tr
        oos_baseline += base_tr
        folds.append({
            "train": [str(tr[0].date()), str(tr[-1].date())],
            "test": [str(te[0].date()), str(te[-1].date())],
            "chosen": cfg_name(best) if best else "none (no config with ≥%d trades and +expectancy)" % min_train_trades,
            "train_metrics": metrics(select_trades(signals, outcomes, best, tr_s, tr_e, coins=set(ALLOWLIST))) if best else None,
            "test_metrics": metrics(test_tr, test_days),
            "baseline_test_metrics": metrics(base_tr, test_days),
        })
    span = len(folds) * test_days
    return {"folds": folds, "oos_selected": metrics(oos_trades, span), "oos_baseline": metrics(oos_baseline, span)}


def one_factor(signals, outcomes, start_ms, end_ms, days):
    rows = []
    for key, vals in GRID.items():
        for v in vals:
            c = {**BASELINE, key: v}
            rows.append({"factor": key, "value": v, "is_baseline": v == BASELINE[key],
                         **metrics(select_trades(signals, outcomes, c, start_ms, end_ms, set(ALLOWLIST)), days)})
    return rows


def allowlist_oos(signals, outcomes, end_ms):
    s = int(ALLOWLIST_FORMED_UNTIL.timestamp() * 1000)
    days = (end_ms - s) / 86_400_000
    out = {}
    for name, coins in (("allowlist", ALLOWLIST), ("hard_banned", HARD_BAN), ("others", OTHERS)):
        out[name] = metrics(select_trades(signals, outcomes, {**BASELINE, "toxic_block": True}, s, end_ms, set(coins)), days)
    per_coin = {}
    for c in ALLOWLIST + HARD_BAN + OTHERS:
        per_coin[c] = metrics(select_trades(signals, outcomes, BASELINE, s, end_ms, {c}), days)
    out["per_coin"] = per_coin
    return out


def hour_profile(signals, outcomes, start_ms, end_ms):
    cfg = {**BASELINE, "toxic_block": False}
    tr = select_trades(signals, outcomes, cfg, start_ms, end_ms, set(ALLOWLIST))
    by = defaultdict(list)
    for t in tr:
        by[t.hour_et].append(t)
    return {h: metrics(by[h]) for h in sorted(by)}


def exit_reason_mix(trades):
    d = defaultdict(lambda: [0, 0.0])
    for t in trades:
        d[t.reason][0] += 1
        d[t.reason][1] += t.net_pct
    return {k: {"n": v[0], "sum_pct": round(v[1], 2)} for k, v in sorted(d.items())}


def run(coins, out_dir: Path, days_back: float | None, cache_root: Path, refresh=True, train_days=60, test_days=20,
        reuse=False):
    out_dir.mkdir(parents=True, exist_ok=True)
    now = int(time.time() * 1000)
    hist_start = now - 4990 * 3_600_000  # HL serves ≤5000 1h bars
    eval_start = hist_start + 61 * 86_400_000
    if days_back:
        eval_start = max(eval_start, now - int(days_back * 86_400_000))
    hourly, signals = {}, []
    sig_file = out_dir / "signals.json"
    if reuse and sig_file.exists():
        signals = [replay.Signal(**d) for d in json.loads(sig_file.read_text())]
        want = {s.coin for s in signals}
        for c in sorted(want):
            hourly[c] = hl_data.read_cache(c, "1h", cache_root)
        signals = [s for s in signals if s.entry_ms >= eval_start and hourly.get(s.coin)]
        coins = []
        log.info("reused %d signals for %d coins", len(signals), len(hourly))
    sc = replay.make_scanner() if coins else None
    for c in coins:
        try:
            h = hl_data.load_history(c, "1h", hist_start, root=cache_root, refresh=refresh)
            fund = hl_data.fetch_funding_history(c, eval_start - 3_600_000) if refresh else []
        except Exception as e:
            log.warning("data %s failed: %s", c, e)
            continue
        if len(h) < 24 * 70:
            log.warning("skip %s: only %d bars", c, len(h))
            continue
        fmap = {(r["time"] // 3_600_000) * 3_600_000: r["funding"] for r in fund}
        t0 = time.time()
        sigs = replay.replay_coin(c, h, eval_start, fmap, scanner=sc)
        hourly[c] = h
        signals += sigs
        log.info("%s: %d bars, %d scored setups (%.0fs)", c, len(h), len(sigs), time.time() - t0)
    if not (reuse and sig_file.exists()):
        sig_file.write_text(json.dumps([asdict(s) for s in signals]))
    outcomes = compute_outcomes(signals, hourly)
    span_days = (now - eval_start) / 86_400_000
    report = {
        "generated_at": datetime.now(ET).isoformat(),
        "eval_window_et": [datetime.fromtimestamp(eval_start / 1000, ET).isoformat(),
                           datetime.fromtimestamp(now / 1000, ET).isoformat()],
        "coins": sorted(hourly),
        "baseline": BASELINE,
        "pre_fix": PRE_FIX,
        "full_period": {
            "baseline": metrics(select_trades(signals, outcomes, BASELINE, eval_start, now, set(ALLOWLIST)), span_days),
            "pre_fix": metrics(select_trades(signals, outcomes, PRE_FIX, eval_start, now, set(ALLOWLIST)), span_days),
            "baseline_no_sltp_enforcement": _no_enforce(signals, hourly, eval_start, now, span_days),
        },
        "baseline_exit_mix": exit_reason_mix(select_trades(signals, outcomes, BASELINE, eval_start, now, set(ALLOWLIST))),
        "one_factor": one_factor(signals, outcomes, eval_start, now, span_days),
        "hour_profile_et": hour_profile(signals, outcomes, eval_start, now),
        "allowlist_oos": allowlist_oos(signals, outcomes, now),
        "walk_forward": walk_forward(signals, outcomes, eval_start, now, train_days, test_days),
    }
    (out_dir / "walk_forward.json").write_text(json.dumps(report, indent=2, default=str))
    (out_dir / "WALK_FORWARD.md").write_text(render_md(report))
    return report


def _no_enforce(signals, hourly, s_ms, e_ms, days):
    """Old paper behaviour: no SL/TP triggers (only TP1, timeout, hard cap)."""
    idx = {c: {b["t"]: i for i, b in enumerate(h)} for c, h in hourly.items()}
    outs = {}
    for s in signals:
        i = idx[s.coin].get(s.t)
        if i is None:
            continue
        o = sim.simulate(s.direction, s.entry, s.sl, s.tp, hourly[s.coin][i + 1:i + 169],
                         sim.ExitParams(be_buffer_pct=0.05, timeout_h=4.0, enforce_sltp=False))
        outs[(s.coin, s.entry_ms, s.direction)] = {exit_key(0.05, 4.0): o}
    return metrics(select_trades(signals, outs, PRE_FIX, s_ms, e_ms, set(ALLOWLIST)), days)


def _fmt(m):
    if not m or not m.get("n"):
        return "0 trades"
    return (f"n={m['n']} · WR {m['wr']:.0%} · PF {m['pf']} · avg {m['avg_pct']:+.3f}% · "
            f"avgR {m['avg_r']:+.2f} · Σ {m['sum_pct']:+.1f}% · maxDD {m['max_dd_pct']:.1f}%"
            + (f" · {m['per_day']}/day" if m.get("per_day") else ""))


def render_md(r) -> str:
    L = ["# Walk-forward results (offline, proposals only)", "",
         f"Generated {r['generated_at']} · window {r['eval_window_et'][0][:16]} → {r['eval_window_et'][1][:16]} ET",
         f"Coins replayed: {len(r['coins'])} · returns are % of notional, unlevered, net of 0.09% fees + 5 bps stop slippage", "",
         "## Full period (allowlist coins)", "",
         f"- Current paper baseline: {_fmt(r['full_period']['baseline'])}",
         f"- Pre-fix config (BE 0.05, stretched kept): {_fmt(r['full_period']['pre_fix'])}",
         f"- Pre-fix + no paper SL/TP enforcement (old paper): {_fmt(r['full_period']['baseline_no_sltp_enforcement'])}", "",
         "Baseline exit mix: " + ", ".join(f"{k} {v['n']} ({v['sum_pct']:+.1f}%)" for k, v in r["baseline_exit_mix"].items()), "",
         "## One factor at a time (vs baseline)", "", "| factor | value | result |", "|---|---|---|"]
    for row in r["one_factor"]:
        L.append(f"| {row['factor']} | {row['value']}{' (baseline)' if row['is_baseline'] else ''} | {_fmt(row)} |")
    L += ["", "## Entry hour (ET), baseline without toxic block", "", "| hour | result |", "|---|---|"]
    for h, m in r["hour_profile_et"].items():
        L.append(f"| {h} | {_fmt(m)} |")
    a = r["allowlist_oos"]
    L += ["", "## Allowlist out-of-sample (after 2026-07-27, when it was formed)", "",
          f"- Allowlist: {_fmt(a['allowlist'])}", f"- Hard-banned: {_fmt(a['hard_banned'])}",
          f"- Others: {_fmt(a['others'])}", ""]
    wf = r["walk_forward"]
    L += ["## Walk-forward (train → pick best config → unseen test)", "",
          f"- OOS selected configs: {_fmt(wf['oos_selected'])}",
          f"- OOS fixed baseline: {_fmt(wf['oos_baseline'])}", "",
          "| train | test | chosen | train | test | baseline test |", "|---|---|---|---|---|---|"]
    for f in wf["folds"]:
        L.append(f"| {f['train'][0]}→{f['train'][1]} | {f['test'][0]}→{f['test'][1]} | {f['chosen']} | "
                 f"{_fmt(f['train_metrics'])} | {_fmt(f['test_metrics'])} | {_fmt(f['baseline_test_metrics'])} |")
    L += ["", "Limitations: 1h bars (conservative intrabar order), no historical OI/dVol ctxs, no Predator regime "
          "classifier / expectancy gate / hot streak / sizing; correlation guard off. Use for relative comparisons."]
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--coins", default=",".join(ALLOWLIST + HARD_BAN + OTHERS))
    ap.add_argument("--out", default="reports/backtest")
    ap.add_argument("--days", type=float, default=None)
    ap.add_argument("--cache", default="data/candles")
    ap.add_argument("--no-refresh", action="store_true")
    ap.add_argument("--train-days", type=int, default=60)
    ap.add_argument("--test-days", type=int, default=20)
    ap.add_argument("--reuse-signals", action="store_true", help="skip replay; reuse <out>/signals.json")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    coins = [c.strip().upper() for c in a.coins.split(",") if c.strip()]
    run(coins, Path(a.out), a.days, Path(a.cache), refresh=not a.no_refresh,
        train_days=a.train_days, test_days=a.test_days, reuse=a.reuse_signals)


if __name__ == "__main__":
    main()
