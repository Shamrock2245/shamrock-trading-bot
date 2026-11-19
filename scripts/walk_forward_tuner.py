#!/usr/bin/env python3
"""Nightly walk-forward tuner. Writes a recommendation and stops there.

    python3 scripts/walk_forward_tuner.py --once
    python3 scripts/walk_forward_tuner.py          # loop every WALK_FORWARD_TUNER_INTERVAL_HOURS

Reads data/candles/*_1h.csv (the candle-recorder mount). Does not fetch, does
not edit .env, does not import the promote gate, and does not place orders.
Predator exits are not searched: the control vs atr2x_8h test stays as it is.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.walk_forward_tuner import (  # noqa: E402
    FUNDING_CARRY_NOTE,
    TAKER_FEE,
    SLIPPAGE,
    empty_report,
    guard_config,
    tune_predator,
    tune_rsi_dip,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("walk_forward_tuner")

ALLOWLIST = (
    "BTC,AAVE,MON,DYDX,VVV,XMR,TNSR,VIRTUAL,BANANA,RESOLV,LTC,JUP,PUMP,AERO,INJ,LINK,SKY,SYRUP"
).split(",")


def _enabled() -> bool:
    return os.getenv("WALK_FORWARD_TUNER_ENABLED", "true").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _replay_enabled() -> bool:
    return os.getenv("WALK_FORWARD_TUNER_PREDATOR_REPLAY", "true").strip().lower() in (
        "1", "true", "yes", "on",
    )


def load_candles(root: Path) -> dict[str, list[dict]]:
    from backtest.hl_data import read_cache

    found: dict[str, list[dict]] = {}
    root = Path(root)
    if not root.exists():
        return found
    allow = {c.strip().upper() for c in ALLOWLIST}
    for path in sorted(root.glob("*_1h.csv")):
        coin = path.name.split("_", 1)[0].upper()
        if coin not in allow:
            continue
        rows = read_cache(coin, "1h", root)
        if len(rows) >= 40:
            found[coin] = rows
    return found


def replay_predator_signals(candles: dict[str, list[dict]]) -> list[dict]:
    """Score the real scanner with the TA29 veto opened, then filter offline.

    Exits use the fixed control geometry (0.12% break-even buffer, 4h loss
    timeout). The atr2x_8h arm is not simulated and is not a candidate.
    """
    saved = {
        key: os.environ.get(key)
        for key in (
            "HL_PERPS_TA29_LONG_TREND_MIN",
            "HL_PERPS_TA29_SHORT_TREND_MAX",
            "MODE",
            "PAPER_MODE_LOCKED",
            "MORALIS_ENABLED",
        )
    }
    os.environ["HL_PERPS_TA29_LONG_TREND_MIN"] = "0"
    os.environ["HL_PERPS_TA29_SHORT_TREND_MAX"] = "100"
    os.environ["MODE"] = "paper"
    os.environ["PAPER_MODE_LOCKED"] = "true"
    os.environ["MORALIS_ENABLED"] = "false"
    try:
        from backtest.replay import make_scanner, replay_coin
        from backtest.sim import ExitParams, simulate

        # make_scanner returns (scanner, module). replay_coin unpacks that pair.
        scanner_pair = make_scanner()
        exits = ExitParams(be_buffer_pct=0.12, timeout_h=4.0)
        signals: list[dict] = []
        for coin, rows in candles.items():
            hourly = []
            for bar in rows:
                try:
                    hourly.append({
                        "t": int(bar["t"]),
                        "T": int(bar.get("T") or int(bar["t"]) + 3_600_000 - 1),
                        "o": float(bar["o"]),
                        "h": float(bar["h"]),
                        "l": float(bar["l"]),
                        "c": float(bar["c"]),
                        "v": float(bar.get("v") or 0),
                        "n": int(bar.get("n") or 0),
                    })
                except (KeyError, TypeError, ValueError):
                    continue
            hourly.sort(key=lambda b: b["t"])
            warmup = 24 * 61
            if len(hourly) <= warmup + 5:
                logger.info("WALK_FORWARD_TUNER predator skip %s — %d bars", coin, len(hourly))
                continue
            logger.info("WALK_FORWARD_TUNER predator replay %s bars=%d", coin, len(hourly))
            scanned = replay_coin(coin, hourly, hourly[warmup]["t"], scanner=scanner_pair)
            index = {bar["t"]: i for i, bar in enumerate(hourly)}
            for sig in scanned:
                i = index.get(sig.t)
                if i is None:
                    continue
                future = hourly[i + 1:i + 1 + 168]
                outcome = simulate(sig.direction, sig.entry, sig.sl, sig.tp, future, exits)
                if outcome.exit_ms == 0:
                    continue
                signals.append({
                    "coin": sig.coin,
                    "direction": sig.direction,
                    "entry_ms": sig.entry_ms,
                    "exit_ms": outcome.exit_ms,
                    "score": sig.score,
                    "ta29_trend": sig.ta29_trend,
                    "pnl": outcome.net_pct,
                })
        return signals
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _log_strategy(row: dict) -> None:
    oos = row.get("oos") or {}
    current = row.get("current_oos") or {}
    logger.info(
        "WALK_FORWARD_TUNER strategy=%s recommend=%s reason=%s "
        "current_oos_pf=%s candidate_oos_pf=%s oos_n=%s",
        row.get("strategy"),
        row.get("recommend"),
        row.get("reason"),
        current.get("pf"),
        oos.get("pf"),
        oos.get("n"),
    )


def run_report(root: Path) -> dict:
    """Build the recommendation. The only side effect is the caller's file write."""
    candles = load_candles(root)
    guards = guard_config()
    report = empty_report("ok" if candles else "no_candle_data")
    report.update({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "candle_root": str(root),
        "coins": sorted(candles),
        "costs": {"taker_fee_per_side": TAKER_FEE, "slippage_per_side": SLIPPAGE},
        "guards": guards,
        "applied": False,
        "changes_applied": False,
    })
    if not candles:
        report["strategies"] = {
            "rsi_dip_v1": {"strategy": "rsi_dip_v1", "recommend": False, "reason": "no_candle_data", "applied": False},
            "predator_v1": {
                "strategy": "predator_v1",
                "recommend": False,
                "reason": "no_candle_data",
                "applied": False,
                "exit_ab": "unchanged",
            },
        }
        return report
    try:
        rsi = tune_rsi_dip(candles, guards=guards)
    except Exception as exc:
        logger.exception("rsi dip tune failed")
        rsi = {"strategy": "rsi_dip_v1", "recommend": False, "reason": "tune_failed", "error": str(exc), "applied": False}
    rsi["applied"] = False
    report["strategies"]["rsi_dip_v1"] = rsi

    if not _replay_enabled():
        predator = {
            "strategy": "predator_v1",
            "recommend": False,
            "reason": "replay_disabled",
            "applied": False,
            "exit_ab": "unchanged",
        }
    else:
        try:
            signals = replay_predator_signals(candles)
            predator = tune_predator(signals, guards=guards)
            predator["signal_count"] = len(signals)
        except Exception as exc:
            logger.exception("predator replay failed")
            predator = {
                "strategy": "predator_v1",
                "recommend": False,
                "reason": "replay_failed",
                "error": str(exc),
                "applied": False,
                "exit_ab": "unchanged",
            }
    predator["applied"] = False
    report["strategies"]["predator_v1"] = predator
    report["research"] = {"funding_carry": {"added": False, "reason": FUNDING_CARRY_NOTE}}
    report["applied"] = False
    report["changes_applied"] = False
    return report


def write_recommendation(report: dict, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(report)
    payload["applied"] = False
    payload["changes_applied"] = False
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    tmp.replace(path)


def run_once(root: Path, out: Path) -> dict:
    report = run_report(root)
    write_recommendation(report, out)
    for row in (report.get("strategies") or {}).values():
        _log_strategy(row)
    logger.info(
        "WALK_FORWARD_TUNER wrote %s applied=%s",
        out,
        report.get("applied"),
    )
    return report


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Paper walk-forward tuner (recommendations only)")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--root", default=os.getenv("CANDLE_RECORDER_DIR", "data/candles"))
    parser.add_argument("--out", default=os.getenv("WALK_FORWARD_TUNER_OUT", "output/tuner_recommendation.json"))
    args = parser.parse_args(argv)
    root = Path(args.root)
    out = Path(args.out)
    try:
        interval_h = float(os.getenv("WALK_FORWARD_TUNER_INTERVAL_HOURS", "24"))
    except (TypeError, ValueError):
        interval_h = 24.0
    interval_s = max(60.0, interval_h * 3600.0)
    logger.info(
        "WALK_FORWARD_TUNER start once=%s enabled=%s interval_h=%s paper_only=true",
        args.once,
        _enabled(),
        interval_h,
    )
    while True:
        if _enabled() or args.once:
            try:
                run_once(root, out)
            except Exception:
                logger.exception("WALK_FORWARD_TUNER cycle failed")
        else:
            logger.info("WALK_FORWARD_TUNER disabled — sleeping")
        if args.once:
            return
        time.sleep(interval_s)


if __name__ == "__main__":
    main()
