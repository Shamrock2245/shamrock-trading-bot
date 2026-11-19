"""Paper-only sleeve tournament.

Tracks rolling forward paper closes per strategy tag and writes
output/strategy_tournament.json. A managed sleeve whose rolling profit
factor is under the floor, after a minimum number of closes, gets no new
paper entries. Slot shift only moves sleeve capacity toward the stronger
sleeve. Predator is reported and never paused. Live mode is a no-op.

This module does not touch MODE, the promote gate, exit A/B, autoban, or
the hot streak.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from core.paper_sleeves import is_sleeve_strategy, sleeve_strategies

_CLOSE_ACTIONS = ("SELL", "CLOSE", "SELL_SHORT")


def _enabled() -> bool:
    return os.getenv("STRATEGY_TOURNAMENT_ENABLED", "true").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _shift() -> bool:
    return os.getenv("STRATEGY_TOURNAMENT_SHIFT_SLOTS", "true").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _paper() -> bool:
    try:
        from config import settings as settings
        return settings.get_current_mode() == "paper"
    except Exception:
        return False


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


def min_closes() -> int:
    return max(1, _int_env("STRATEGY_TOURNAMENT_MIN_CLOSES", "20"))


def pf_floor() -> float:
    return _float_env("STRATEGY_TOURNAMENT_PF_FLOOR", "0.80")


def window_size() -> int:
    return max(1, _int_env("STRATEGY_TOURNAMENT_WINDOW", "30"))


def status_path() -> Path:
    return Path(os.getenv("STRATEGY_TOURNAMENT_STATUS_FILE", "output/strategy_tournament.json"))


def _pnl(row: dict) -> float | None:
    raw = row.get("pnl_usd")
    if raw is None:
        return None
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    if val != val:  # NaN
        return None
    return val


def _ts(row: dict) -> float:
    raw = row.get("timestamp") or row.get("time") or row.get("closed_at") or 0
    try:
        if isinstance(raw, (int, float)):
            return float(raw) / (1000.0 if raw > 1e12 else 1.0)
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return 0.0


def is_paper_hl_close(row: dict) -> bool:
    if not isinstance(row, dict) or row.get("is_paper") is not True:
        return False
    if str(row.get("chain") or "").strip().lower() != "hyperliquid":
        return False
    if str(row.get("action") or "").upper() not in _CLOSE_ACTIONS:
        return False
    if "orphan" in str(row.get("reason") or "").lower():
        return False
    return _pnl(row) is not None


def strategy_of(row: dict) -> str:
    name = str(row.get("strategy") or "")
    if is_sleeve_strategy(name):
        return name
    return "predator_v1"


def metrics(pnls: list[float]) -> dict:
    n = len(pnls)
    if n == 0:
        return {"trades": 0, "win_rate": None, "profit_factor": None, "net": 0.0}
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
        "trades": n,
        "win_rate": round(wins / n, 4),
        "profit_factor": round(pf, 4),
        "net": round(sum(pnls), 4),
    }


def _load_trades() -> list:
    path = Path(os.getenv("TRADES_FILE", "output/trades.json"))
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8") or "[]")
    except (OSError, json.JSONDecodeError):
        return []
    return raw if isinstance(raw, list) else []


def _should_pause(row_metrics: dict, *, managed: bool) -> bool:
    if not managed or not _enabled() or not _paper():
        return False
    trades = int(row_metrics.get("trades") or 0)
    if trades < min_closes():
        return False
    pf = row_metrics.get("profit_factor")
    if pf is None:
        return False
    return float(pf) < pf_floor()


def build_status() -> dict:
    grouped: dict[str, list[tuple[float, float]]] = {}
    for row in _load_trades():
        if not is_paper_hl_close(row):
            continue
        name = strategy_of(row)
        grouped.setdefault(name, []).append((_ts(row), _pnl(row) or 0.0))
    window = window_size()
    names = ["predator_v1"] + sorted(sleeve_strategies())
    for extra in grouped:
        if extra not in names:
            names.append(extra)
    active = _enabled() and _paper()
    sleeves: dict[str, dict] = {}
    for name in names:
        series = [pnl for _ts, pnl in sorted(grouped.get(name, []))]
        rolled = metrics(series[-window:])
        managed = is_sleeve_strategy(name)
        sleeves[name] = {
            **rolled,
            "managed": managed,
            "paused": _should_pause(rolled, managed=managed),
            "window": window,
            "closes_seen": len(series),
        }
    return {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "paper_only": True,
        "applied_to_live": False,
        "enabled": active,
        "min_closes": min_closes(),
        "pf_floor": pf_floor(),
        "window": window,
        "shift_slots": _shift(),
        "sleeves": sleeves,
    }


def publish() -> dict:
    status = build_status()
    path = status_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(status, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass
    return status


def slot_cap(strategy: str, default_slots: int) -> int:
    """How many open positions this sleeve may hold. Predator is untouched."""
    try:
        default = max(0, int(default_slots))
    except (TypeError, ValueError):
        default = 0
    if not is_sleeve_strategy(strategy) or not _enabled() or not _paper():
        return default
    status = publish()
    row = (status.get("sleeves") or {}).get(strategy) or {}
    if row.get("paused"):
        return 0
    if not _shift():
        return default
    ranked = []
    for name, sleeve in (status.get("sleeves") or {}).items():
        if not sleeve.get("managed") or sleeve.get("paused"):
            continue
        if int(sleeve.get("trades") or 0) < min_closes():
            continue
        ranked.append((float(sleeve.get("profit_factor") or 0.0), name))
    if len(ranked) < 2:
        return default
    best = max(pf for pf, _name in ranked)
    mine = float(row.get("profit_factor") or 0.0)
    if mine + 1e-9 < best:
        return max(1, default // 2)
    return default
