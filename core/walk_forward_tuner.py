"""Walk-forward tuner for paper strategies. Recommendations only.

Picks parameters on each train window, scores them on the following unseen
window, and writes a judgment. It does not edit env files, constants, MODE,
the promote gate, or the Predator exit A/B (control vs atr2x_8h).

Costs on the RSI simulator: taker fee both sides and adverse slippage both
sides. Predator rows are precomputed net returns; this module only filters
entry thresholds (exec score and the TA29 long-trend veto).
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Callable, Optional

from core.rsi_dip_v1 import (
    ATR_MULT,
    ATR_PERIOD,
    MAX_HOLD_HOURS,
    RSI_ENTRY,
    RSI_EXIT,
    atr_path,
    cooldown_hours,
    rearm_level,
    rsi_path,
)

TAKER_FEE = 0.00045
SLIPPAGE = 0.0005
HOUR_MS = 3_600_000
DAY_MS = 86_400_000

FUNDING_CARRY_NOTE = (
    "Not added. docs/backtest/ALT_STRATEGY_RESEARCH_2026-11-03.md found no "
    "1h funding-carry variant with a positive out-of-sample edge after fees, "
    "slippage, and funding (OOS PF 0.90-0.95, 0/16 variants). Mean-reversion "
    "shorts failed the same bar. The RSI dip sleeve is the only research "
    "candidate already in paper."
)


def _int_env(name: str, default: str) -> int:
    try:
        return int(float(os.getenv(name, default)))
    except (TypeError, ValueError):
        return int(float(default))


def _float_env(name: str, default: str) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return float(default)


def guard_config() -> dict:
    return {
        "min_oos_trades": max(1, _int_env("WALK_FORWARD_TUNER_MIN_OOS_TRADES", "30")),
        "min_is_trades": max(1, _int_env("WALK_FORWARD_TUNER_MIN_IS_TRADES", "20")),
        "pf_margin": _float_env("WALK_FORWARD_TUNER_PF_MARGIN", "0.15"),
        "min_oos_pf": _float_env("WALK_FORWARD_TUNER_MIN_OOS_PF", "1.0"),
        "train_days": max(1, _int_env("WALK_FORWARD_TUNER_TRAIN_DAYS", "60")),
        "test_days": max(1, _int_env("WALK_FORWARD_TUNER_TEST_DAYS", "20")),
    }


def pnl_metrics(pnls: list[float]) -> dict:
    n = len(pnls)
    if n == 0:
        return {"n": 0, "wr": None, "pf": None, "net": 0.0}
    gross_profit = sum(p for p in pnls if p > 0)
    gross_loss = -sum(p for p in pnls if p < 0)
    wins = sum(1 for p in pnls if p > 0)
    if gross_loss > 0:
        pf = gross_profit / gross_loss
    elif gross_profit > 0:
        pf = 999.0
    else:
        pf = 0.0
    return {
        "n": n,
        "wr": round(wins / n, 4),
        "pf": round(pf, 4),
        "net": round(sum(pnls), 4),
    }


def iter_folds(start_ms: int, end_ms: int, train_days: int, test_days: int):
    """Yield (train_start, train_end, test_end) walking forward by one test window."""
    train = int(train_days) * DAY_MS
    test = int(test_days) * DAY_MS
    cursor = int(start_ms)
    end = int(end_ms)
    while cursor + train + test <= end:
        yield cursor, cursor + train, cursor + train + test
        cursor += test


def pick_best_is(candidates: list[dict], min_is: int) -> Optional[dict]:
    """Highest in-sample profit factor, then more trades, then key. None if all are thin."""
    best = None
    best_rank = None
    for cand in candidates:
        stats = pnl_metrics(list(cand.get("is_pnls") or []))
        if stats["n"] < min_is or stats["pf"] is None:
            continue
        rank = (float(stats["pf"]), int(stats["n"]), str(cand.get("key")))
        if best_rank is None or rank > best_rank:
            best_rank = rank
            best = {"key": cand.get("key"), "params": cand.get("params"), "is": stats}
    return best


def judge(
    current_pnls: list[float],
    candidate_pnls: list[float],
    *,
    min_oos: int,
    margin: float,
    min_pf: float,
) -> tuple[bool, str]:
    """True only when unseen trades clear the count, the PF floor, and the margin over current."""
    current = pnl_metrics(list(current_pnls or []))
    candidate = pnl_metrics(list(candidate_pnls or []))
    if candidate["n"] < min_oos:
        return False, "oos_trade_count"
    cand_pf = 0.0 if candidate["pf"] is None else float(candidate["pf"])
    if cand_pf < float(min_pf):
        return False, "oos_pf_floor"
    cur_pf = current["pf"]
    if current["n"] > 0 and cur_pf is not None and cand_pf + 1e-9 < float(cur_pf) + float(margin):
        return False, "oos_pf_margin"
    if current["n"] >= min_oos:
        return True, "oos_improved"
    return True, "oos_improved_starved_baseline"


def assemble_recommendation(
    strategy: str,
    folds: list[dict],
    current_params: dict,
    guards: dict,
) -> dict:
    """Judge the last fold's in-sample winner on that fold's unseen window.

    Earlier folds are a stability check: with three or more folds, a last
    window that looks good is still rejected when half of the folds' own
    in-sample winners fail the out-of-sample PF floor.
    """
    base = {
        "strategy": strategy,
        "recommend": False,
        "reason": "no_folds",
        "applied": False,
        "current_params": current_params,
        "candidate_params": None,
        "is": None,
        "oos": None,
        "current_oos": None,
        "folds": len(folds),
        "fold_reports": [],
    }
    if not folds:
        return base
    min_is = int(guards["min_is_trades"])
    min_oos = int(guards["min_oos_trades"])
    margin = float(guards["pf_margin"])
    min_pf = float(guards["min_oos_pf"])
    reports = []
    for fold in folds:
        picked = pick_best_is(fold.get("candidates") or [], min_is)
        chosen_oos: list[float] = []
        chosen_key = None
        is_stats = None
        if picked is not None:
            chosen_key = picked["key"]
            is_stats = picked["is"]
            match = next(
                (c for c in fold["candidates"] if c.get("key") == chosen_key),
                None,
            )
            if match is not None:
                chosen_oos = list(match.get("oos_pnls") or [])
        current_oos = list(fold.get("current_oos_pnls") or [])
        oos_stats = pnl_metrics(chosen_oos)
        cur_stats = pnl_metrics(current_oos)
        reports.append({
            "chosen_key": chosen_key,
            "is_pf": None if not is_stats else is_stats.get("pf"),
            "is_n": None if not is_stats else is_stats.get("n"),
            "oos_pf": oos_stats.get("pf"),
            "oos_n": oos_stats.get("n"),
            "current_oos_pf": cur_stats.get("pf"),
            "current_oos_n": cur_stats.get("n"),
        })
    last = folds[-1]
    picked = pick_best_is(last.get("candidates") or [], min_is)
    base["fold_reports"] = reports
    if picked is None:
        base["reason"] = "no_is_candidate"
        return base
    chosen = next(c for c in last["candidates"] if c.get("key") == picked["key"])
    current_oos = list(last.get("current_oos_pnls") or [])
    base["candidate_params"] = chosen.get("params")
    base["is"] = picked["is"]
    base["oos"] = pnl_metrics(list(chosen.get("oos_pnls") or []))
    base["current_oos"] = pnl_metrics(current_oos)
    if picked["key"] == last.get("current_key"):
        base["reason"] = "current_is_best"
        return base
    ok, reason = judge(
        current_oos,
        list(chosen.get("oos_pnls") or []),
        min_oos=min_oos,
        margin=margin,
        min_pf=min_pf,
    )
    if ok and len(folds) >= 3:
        good = 0
        for fold in folds:
            champ = pick_best_is(fold.get("candidates") or [], min_is)
            if champ is None:
                continue
            match = next(c for c in fold["candidates"] if c.get("key") == champ["key"])
            stats = pnl_metrics(list(match.get("oos_pnls") or []))
            if stats["n"] >= min_oos and (stats["pf"] or 0) >= min_pf:
                good += 1
        if good * 2 < len(folds):
            ok, reason = False, "oos_unstable"
    base["recommend"] = ok
    base["reason"] = reason
    return base


@dataclass(frozen=True)
class DipParams:
    rsi_entry: float = RSI_ENTRY
    rsi_exit: float = RSI_EXIT
    atr_mult: float = ATR_MULT
    max_hold_hours: float = MAX_HOLD_HOURS
    cooldown_hours: float = 6.0
    rearm_rsi: float = 35.0

    def key(self) -> str:
        return (
            f"e{self.rsi_entry:g}|x{self.rsi_exit:g}|a{self.atr_mult:g}|"
            f"h{self.max_hold_hours:g}|c{self.cooldown_hours:g}|r{self.rearm_rsi:g}"
        )


def current_dip_params() -> DipParams:
    return DipParams(
        rsi_entry=float(RSI_ENTRY),
        rsi_exit=float(RSI_EXIT),
        atr_mult=float(ATR_MULT),
        max_hold_hours=float(MAX_HOLD_HOURS),
        cooldown_hours=float(cooldown_hours()),
        rearm_rsi=float(rearm_level() or 0.0),
    )


def default_dip_grid(current: DipParams) -> list[DipParams]:
    grid: list[DipParams] = []
    seen: set[str] = set()
    for entry in (15.0, 20.0, 25.0, 30.0):
        for exit_ in (45.0, 50.0, 55.0):
            if exit_ <= entry:
                continue
            for atr in (2.0, 3.0, 4.0):
                for hold in (8.0, 12.0, 24.0):
                    for cool in (0.0, 6.0, 12.0):
                        params = DipParams(
                            entry, exit_, atr, hold, cool, float(current.rearm_rsi)
                        )
                        if params.key() not in seen:
                            seen.add(params.key())
                            grid.append(params)
    if current.key() not in seen:
        grid.append(current)
    return grid


def _bars(raw) -> list[dict]:
    out = []
    for candle in raw or []:
        if not isinstance(candle, dict):
            continue
        try:
            bar = {
                "t": int(candle["t"]),
                "o": float(candle["o"]),
                "h": float(candle["h"]),
                "l": float(candle["l"]),
                "c": float(candle["c"]),
            }
        except (KeyError, TypeError, ValueError):
            continue
        if min(bar["o"], bar["h"], bar["l"], bar["c"]) <= 0 or bar["h"] < bar["l"]:
            continue
        out.append(bar)
    out.sort(key=lambda b: b["t"])
    deduped = []
    seen_t = set()
    for bar in out:
        if bar["t"] in seen_t:
            continue
        seen_t.add(bar["t"])
        deduped.append(bar)
    return deduped


def _position_exit(bar: dict, rsi: Optional[float], pos: dict, params: DipParams, slip: float):
    stop = pos["stop"]
    if bar["l"] <= stop:
        return "stop", min(stop, bar["o"]) * (1.0 - slip)
    if rsi is not None and rsi >= params.rsi_exit:
        return "rsi_revert", bar["c"] * (1.0 - slip)
    held_h = (int(bar["t"]) + HOUR_MS - int(pos["entry_ms"])) / HOUR_MS
    if held_h >= params.max_hold_hours:
        return "time", bar["c"] * (1.0 - slip)
    return None, None


def _close_trade(coin: str, pos: dict, fill: float, reason: str, bar: dict, fee: float) -> dict:
    entry = float(pos["entry"])
    ret = ((fill - entry) / entry) - 2.0 * fee if entry else -2.0 * fee
    return {
        "coin": coin,
        "entry_ms": int(pos["entry_ms"]),
        "exit_ms": int(bar["t"]) + HOUR_MS,
        "pnl": ret * 100.0,
        "reason": reason,
    }


def simulate_dip(
    candles_by_coin: dict,
    params: DipParams,
    *,
    fee: float = TAKER_FEE,
    slip: float = SLIPPAGE,
    max_concurrent: int = 3,
) -> list[dict]:
    """Long-only RSI dip book. Signal on the closed bar, fill the next open.

    Stop is checked before the RSI exit and the time stop. A stop arms the
    cooldown and, when rearm_rsi > 0, waits for RSI to print at or above it.
    """
    books = {}
    for coin, raw in (candles_by_coin or {}).items():
        bars = _bars(raw)
        if len(bars) < ATR_PERIOD + 2:
            continue
        highs = [b["h"] for b in bars]
        lows = [b["l"] for b in bars]
        closes = [b["c"] for b in bars]
        books[str(coin).upper()] = {
            "bars": bars,
            "rsi": rsi_path(closes),
            "atr": atr_path(highs, lows, closes),
        }
    if not books:
        return []
    times = sorted({bar["t"] for book in books.values() for bar in book["bars"]})
    loc = {
        coin: {bar["t"]: i for i, bar in enumerate(book["bars"])}
        for coin, book in books.items()
    }
    positions: dict[str, dict] = {}
    cooldown: dict[str, dict] = {}
    trades: list[dict] = []

    for t in times:
        for coin, book in books.items():
            i = loc[coin].get(t)
            if i is None or coin not in positions:
                continue
            if int(positions[coin]["entry_t"]) >= t:
                continue
            reason, fill = _position_exit(book["bars"][i], book["rsi"][i], positions[coin], params, slip)
            if not reason:
                continue
            trades.append(_close_trade(coin, positions[coin], fill, reason, book["bars"][i], fee))
            if reason == "stop":
                cooldown[coin] = {"stop_ms": int(book["bars"][i]["t"]) + HOUR_MS, "rearmed": False}
            del positions[coin]

        if params.rearm_rsi > 0:
            for coin, book in books.items():
                state = cooldown.get(coin)
                if not state or state.get("rearmed") or coin in positions:
                    continue
                i = loc[coin].get(t)
                if i is None:
                    continue
                bar = book["bars"][i]
                if int(bar["t"]) + HOUR_MS <= int(state["stop_ms"]):
                    continue
                rsi = book["rsi"][i]
                if rsi is not None and float(rsi) >= params.rearm_rsi:
                    state["rearmed"] = True

        if len(positions) >= max_concurrent:
            continue
        pending = []
        for coin, book in books.items():
            if coin in positions:
                continue
            i = loc[coin].get(t)
            if i is None or i < 1:
                continue
            prev = book["bars"][i - 1]
            if t - prev["t"] > int(HOUR_MS * 1.5):
                continue
            rsi = book["rsi"][i - 1]
            atr = book["atr"][i - 1]
            if rsi is None or atr is None or atr <= 0 or float(rsi) > params.rsi_entry:
                continue
            state = cooldown.get(coin)
            if state:
                if t < int(state["stop_ms"]):
                    continue
                cool_until = int(state["stop_ms"] + params.cooldown_hours * HOUR_MS)
                if params.cooldown_hours > 0 and t < cool_until:
                    continue
                if params.rearm_rsi > 0 and not state.get("rearmed"):
                    continue
            pending.append((float(rsi), coin, float(atr), i))
        pending.sort()
        for rsi, coin, atr, i in pending:
            if len(positions) >= max_concurrent:
                break
            bar = books[coin]["bars"][i]
            raw_entry = float(bar["o"])
            stop = raw_entry - params.atr_mult * atr
            if raw_entry <= 0 or stop <= 0 or stop >= raw_entry:
                continue
            positions[coin] = {
                "entry": raw_entry * (1.0 + slip),
                "stop": stop,
                "entry_t": t,
                "entry_ms": t,
            }
            cooldown.pop(coin, None)
            reason, fill = _position_exit(bar, books[coin]["rsi"][i], positions[coin], params, slip)
            if not reason:
                continue
            trades.append(_close_trade(coin, positions[coin], fill, reason, bar, fee))
            if reason == "stop":
                cooldown[coin] = {"stop_ms": int(bar["t"]) + HOUR_MS, "rearmed": False}
            del positions[coin]

    for coin, pos in list(positions.items()):
        bar = books[coin]["bars"][-1]
        fill = float(bar["c"]) * (1.0 - slip)
        trades.append(_close_trade(coin, pos, fill, "eod", bar, fee))
    trades.sort(key=lambda row: (row["entry_ms"], row["coin"]))
    return trades


def _span_ms(candles_by_coin: dict) -> tuple[int, int]:
    stamps = []
    for raw in candles_by_coin.values():
        for candle in raw or []:
            try:
                stamps.append(int(candle["t"]))
            except (KeyError, TypeError, ValueError):
                continue
    if not stamps:
        return 0, 0
    return min(stamps), max(stamps) + HOUR_MS


def tune_rsi_dip(
    candles_by_coin: dict,
    *,
    grid: Optional[list[DipParams]] = None,
    current: Optional[DipParams] = None,
    guards: Optional[dict] = None,
    simulate: Optional[Callable] = None,
) -> dict:
    guards = dict(guards or guard_config())
    current = current or current_dip_params()
    if not candles_by_coin:
        return assemble_recommendation("rsi_dip_v1", [], asdict(current), guards) | {
            "reason": "no_candle_data",
        }
    start, end = _span_ms(candles_by_coin)
    folds_ix = list(iter_folds(start, end, guards["train_days"], guards["test_days"]))
    if not folds_ix:
        empty = assemble_recommendation("rsi_dip_v1", [], asdict(current), guards)
        empty["reason"] = "insufficient_history"
        return empty
    grid = list(grid or default_dip_grid(current))
    if all(p.key() != current.key() for p in grid):
        grid.append(current)
    sim = simulate or simulate_dip
    cached = []
    for params in grid:
        cached.append((params, list(sim(candles_by_coin, params))))
    folds = []
    for train_start, train_end, test_end in folds_ix:
        candidates = []
        current_oos: list[float] = []
        for params, trades in cached:
            is_pnls = [
                t["pnl"] for t in trades
                if train_start <= t["entry_ms"] < train_end and t["exit_ms"] <= train_end
            ]
            oos_pnls = [
                t["pnl"] for t in trades
                if train_end <= t["entry_ms"] < test_end and t["exit_ms"] <= test_end
            ]
            candidates.append({
                "key": params.key(),
                "params": asdict(params),
                "is_pnls": is_pnls,
                "oos_pnls": oos_pnls,
            })
            if params.key() == current.key():
                current_oos = oos_pnls
        folds.append({
            "candidates": candidates,
            "current_oos_pnls": current_oos,
            "current_key": current.key(),
        })
    return assemble_recommendation("rsi_dip_v1", folds, asdict(current), guards)


def current_predator_params() -> dict:
    """Paper exec bar (score plus the paper delta, floored at 52) and the TA29 veto."""
    try:
        exec_score = float(os.getenv("HL_PERPS_EXEC_SCORE", "65"))
    except (TypeError, ValueError):
        exec_score = 65.0
    try:
        delta = float(os.getenv("HL_PERPS_PAPER_EXEC_SCORE_DELTA", "-5"))
    except (TypeError, ValueError):
        delta = -5.0
    effective = max(52.0, exec_score + min(0.0, delta))
    try:
        ta29 = float(os.getenv("HL_PERPS_TA29_LONG_TREND_MIN", "35"))
    except (TypeError, ValueError):
        ta29 = 35.0
    return {
        "exec_score": effective,
        "ta29_long_trend_min": ta29,
        "long_only": True,
    }


def predator_key(params: dict) -> str:
    return f"bar{float(params['exec_score']):g}|ta{float(params['ta29_long_trend_min']):g}"


def default_predator_grid(current: dict) -> list[dict]:
    execs = {52.0, 56.0, 58.0, 60.0, 64.0, float(current["exec_score"])}
    trends = {20.0, 25.0, 30.0, 35.0, 45.0, float(current["ta29_long_trend_min"])}
    return [
        {"exec_score": e, "ta29_long_trend_min": t, "long_only": True}
        for e in sorted(execs)
        for t in sorted(trends)
    ]


def filter_predator_pnls(
    signals: list[dict],
    params: dict,
    *,
    entry_start: int,
    entry_end: int,
    exit_before: Optional[int] = None,
    max_positions: int = 4,
) -> list[float]:
    """Entry filter only. PnL is whatever the caller precomputed (exits stay fixed).

    exit_before drops trades that close after the window, so in-sample selection
    cannot see prices from the unseen window.
    """
    rows = [
        s for s in signals
        if entry_start <= int(s.get("entry_ms") or 0) < entry_end
    ]
    rows.sort(key=lambda s: (int(s["entry_ms"]), -float(s.get("score") or 0)))
    long_only = bool(params.get("long_only", True))
    exec_score = float(params["exec_score"])
    ta29_min = float(params["ta29_long_trend_min"])
    busy: dict[str, int] = {}
    open_until: list[int] = []
    pnls: list[float] = []
    for sig in rows:
        if long_only and str(sig.get("direction") or "long") != "long":
            continue
        if float(sig.get("score") or 0) < exec_score:
            continue
        trend = sig.get("ta29_trend")
        if trend is not None and float(trend) < ta29_min:
            continue
        coin = str(sig.get("coin") or "")
        entry_ms = int(sig["entry_ms"])
        if busy.get(coin, 0) > entry_ms:
            continue
        open_until = [ts for ts in open_until if ts > entry_ms]
        if len(open_until) >= max_positions:
            continue
        exit_ms = int(sig.get("exit_ms") or entry_ms + HOUR_MS)
        busy[coin] = exit_ms
        open_until.append(exit_ms)
        if exit_before is not None and exit_ms > exit_before:
            continue
        pnls.append(float(sig["pnl"]))
    return pnls


def tune_predator(
    signals: list[dict],
    *,
    grid: Optional[list[dict]] = None,
    current: Optional[dict] = None,
    guards: Optional[dict] = None,
) -> dict:
    guards = dict(guards or guard_config())
    current = dict(current or current_predator_params())
    note = {
        "exit_ab": "unchanged",
        "thresholds_only": ["exec_score", "ta29_long_trend_min"],
    }
    if not signals:
        result = assemble_recommendation("predator_v1", [], current, guards)
        result["reason"] = "no_signal_data"
        result.update(note)
        return result
    start = min(int(s["entry_ms"]) for s in signals)
    end = max(int(s["entry_ms"]) for s in signals) + HOUR_MS
    windows = list(iter_folds(start, end, guards["train_days"], guards["test_days"]))
    if not windows:
        result = assemble_recommendation("predator_v1", [], current, guards)
        result["reason"] = "insufficient_history"
        result.update(note)
        return result
    grid = list(grid or default_predator_grid(current))
    if all(predator_key(p) != predator_key(current) for p in grid):
        grid.append(current)
    folds = []
    for train_start, train_end, test_end in windows:
        candidates = []
        current_oos: list[float] = []
        for params in grid:
            item = {
                "key": predator_key(params),
                "params": dict(params),
                "is_pnls": filter_predator_pnls(
                    signals, params, entry_start=train_start, entry_end=train_end,
                    exit_before=train_end,
                ),
                "oos_pnls": filter_predator_pnls(
                    signals, params, entry_start=train_end, entry_end=test_end,
                    exit_before=test_end,
                ),
            }
            candidates.append(item)
            if item["key"] == predator_key(current):
                current_oos = item["oos_pnls"]
        folds.append({
            "candidates": candidates,
            "current_oos_pnls": current_oos,
            "current_key": predator_key(current),
        })
    result = assemble_recommendation("predator_v1", folds, current, guards)
    result.update(note)
    return result


def empty_report(reason: str) -> dict:
    return {
        "applied": False,
        "paper_only": True,
        "changes_applied": False,
        "exit_ab": "unchanged",
        "reason": reason,
        "strategies": {},
        "research": {"funding_carry": {"added": False, "reason": FUNDING_CARRY_NOTE}},
    }
