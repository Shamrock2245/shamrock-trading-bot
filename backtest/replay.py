"""Replay the bot's own HLPerpsScanner.scan_coin() over historical candles.

Faithful by construction: the real scoring (TA, Fib, TA29 gate, geometry
repair, R/R guard, daily-trend veto) runs unchanged. Only I/O is swapped:
  * _get_candles serves the history visible at bar i (1h window + daily bars
    aggregated from 1h incl. the partial current day, exactly like live)
  * asset ctxs (OI / dVol share) → {} (no point-in-time history yet; the
    candle recorder now captures them going forward)
  * cooldowns / correlation / leverage caps / goal engine → neutral
  * exec bar → 0 so every scored setup is captured; the bar is swept offline
  * LONG_ONLY=false so shorts are captured; filtered offline
Signals carry the raw score, tp_source, SL/TP, direction and ET entry hour.
"""
from __future__ import annotations

import logging
import os
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")


def _prepare_env() -> None:
    tmp = tempfile.mkdtemp(prefix="bt_state_")
    os.environ.setdefault("MODE", "paper")
    os.environ["HL_PERPS_ENABLED"] = "false"      # no API init / no network in scanner
    os.environ["HL_PERPS_LONG_ONLY"] = "false"    # capture shorts; filtered offline
    os.environ["MORALIS_ENABLED"] = "false"
    # Stretched-TP demotion is swept offline in walk_forward; keep raw scores here.
    os.environ["HL_PERPS_PAPER_STRETCHED_TP_PENALTY"] = "0"
    os.environ["DASHBOARD_STATE_DIR"] = tmp
    os.environ["TRADES_FILE"] = os.path.join(tmp, "trades.json")
    os.environ.setdefault("HL_PERPS_STATE_DIR", tmp)


@dataclass
class Signal:
    coin: str
    t: int                 # bar open ms of the signal bar (entry at its close)
    entry_ms: int          # entry time (bar close)
    hour_et: int
    direction: str
    score: float
    entry: float
    sl: float
    tp: float
    tp_source: str
    fib_zone: str
    funding: float


def daily_from_hourly(h: list[dict]) -> list[dict]:
    days: dict[int, dict] = {}
    for c in h:
        d = (c["t"] // 86_400_000) * 86_400_000
        x = days.get(d)
        if x is None:
            days[d] = {"t": d, "T": d + 86_399_999, "o": c["o"], "h": c["h"], "l": c["l"],
                       "c": c["c"], "v": c["v"], "n": c.get("n", 0)}
        else:
            x["h"] = max(x["h"], c["h"]); x["l"] = min(x["l"], c["l"])
            x["c"] = c["c"]; x["v"] += c["v"]
    return [days[k] for k in sorted(days)]


class _Feed:
    def __init__(self, hourly: list[dict]):
        self.h = hourly
        self.i = 0
        # incremental daily aggregation, rebuilt per bar cheaply
        self._day_index: dict[int, int] = {}

    def candles(self, interval: str, lookback_hours: int) -> list[dict]:
        end = self.i + 1
        if interval == "1h":
            n = max(1, int(lookback_hours))
            return [{**c, "c": str(c["c"]), "v": str(c["v"])} for c in self.h[max(0, end - n):end]]
        if interval == "1d":
            span = self.h[max(0, end - int(lookback_hours) - 24):end]
            days = daily_from_hourly(span)[-int(lookback_hours // 24 or 1):]
            return [{**c, "c": str(c["c"]), "v": str(c["v"])} for c in days]
        return []


def make_scanner():
    _prepare_env()
    logging.getLogger("core").setLevel(logging.WARNING)
    logging.getLogger("strategies").setLevel(logging.WARNING)
    import core.hl_perps_scanner as sc
    s = sc.HLPerpsScanner(hl_executor=None)
    s._initialized = True
    s._is_on_cooldown = lambda coin: False
    s._get_asset_ctxs_cached = lambda: {}
    s.get_max_allowed_leverage = lambda coin, lev: lev
    s._record_price_history = lambda coin, px: None
    s._goal_frequency_params = lambda: {"exec_score": 0.0, "reentry_cooldown_min": 0,
                                        "loss_cooldown_min": 0, "max_positions": 99,
                                        "size_multiplier": 1.0, "mode": "backtest",
                                        "progress_pct": 0.0, "remaining_usd": 0.0,
                                        "behind_pace": False}
    return s, sc


def replay_coin(coin: str, hourly: list[dict], start_ms: int, funding_by_hour: Optional[dict] = None,
                scanner=None, warmup_bars: int = 24 * 61) -> list[Signal]:
    """One scan per closed 1h bar from start_ms (needs ≥61d of warmup)."""
    s, sc = scanner or make_scanner()
    feed = _Feed(hourly)
    s._get_candles = lambda c, interval="1h", lookback_hours=72: feed.candles(interval, lookback_hours)
    out: list[Signal] = []
    funding_by_hour = funding_by_hour or {}
    for i in range(warmup_bars, len(hourly)):
        bar = hourly[i]
        if bar["t"] < start_ms:
            continue
        feed.i = i
        hour_key = (bar["t"] // 3_600_000) * 3_600_000
        fr = float(funding_by_hour.get(hour_key, 0.0))
        try:
            sig = s.scan_coin(coin, fr)
        except Exception as e:  # scoring must never crash the run
            logging.getLogger(__name__).debug("scan error %s @%s: %s", coin, bar["t"], e)
            continue
        if not sig:
            continue
        entry_ms = bar["t"] + 3_600_000
        out.append(Signal(
            coin=coin, t=bar["t"], entry_ms=entry_ms,
            hour_et=datetime.fromtimestamp(entry_ms / 1000, ET).hour,
            direction=sig.direction, score=float(sig.score), entry=float(sig.entry_price),
            sl=float(sig.stop_loss_price), tp=float(sig.take_profit_price),
            tp_source=str((sig.components or {}).get("tp_source") or _tp_src(sig.reasoning)),
            fib_zone=str(sig.fib_zone or "none"), funding=fr,
        ))
    return out


def _tp_src(reasoning: str) -> str:
    for part in (reasoning or "").split("|"):
        part = part.strip()
        if part.startswith("tp_src="):
            return part[len("tp_src="):]
    return ""
