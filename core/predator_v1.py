"""
core/predator_v1.py — Expansion-only Hyperliquid entry gate.

This is the sniper layer the 29-indicator blender never was.

Rules (all must pass when PREDATOR_V1_ENABLED=true):
  1. Coin is on the profit allowlist (HL_PERPS_ALLOWLIST).
  2. Coin is not hard-banned (HL_PERPS_HARD_BAN_COINS).
  3. Regime is EXPANSION/TRENDING. CHOP and NUKE are skips, not half-size.
  4. Toxic hours (default 08–13 ET) are skips.
  5. Daily open cap — no spray days.

Disabled = no-op so legacy gates keep running unchanged.
Moralis is not scored here. Moralis is a veto elsewhere, not padding.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")
_SNAPSHOT = Path(os.getenv("DASHBOARD_STATE_DIR", "./data/dashboard")) / "predator_v1.json"

# Fills-derived defaults. Keep in lockstep with scanner env defaults.
_DEFAULT_ALLOWLIST = (
    "BTC,AAVE,MON,DYDX,VVV,XMR,TNSR,VIRTUAL,BANANA,RESOLV,LTC,JUP,PUMP,AERO,INJ,LINK,SKY,SYRUP"
)
_DEFAULT_HARD_BAN = (
    "KAITO,APE,HEMI,ONDO,GRASS,TRB,HMSTR,FARTCOIN,MET,EIGEN,MORPHO,LIT,HYPE,"
    "BRETT,POPCAT,MEME,JTO,ENA,ZEC,ETH,BSV,CRV,PENDLE,UNI,ACE,ADA,STABLE,SUI,"
    "LDO,ETHFI,SOL,TRX"
)

_CHOP_NAMES = {"CHOPPY", "CHOP", "RANGE", "DEAD"}
_NUKE_NAMES = {"NUKE", "CRASH", "BEAR"}
_EXPANSION_NAMES = {"TRENDING", "EXPANSION", "TREND", "BULL", "NORMAL"}


def _flag(name: str, default: str = "true") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


def enabled() -> bool:
    return _flag("PREDATOR_V1_ENABLED", "false")


def _csv_set(env_name: str, default: str) -> set[str]:
    raw = os.getenv(env_name, default) or ""
    return {c.strip().upper() for c in raw.split(",") if c.strip()}


def allowlist() -> set[str]:
    return _csv_set("HL_PERPS_ALLOWLIST", _DEFAULT_ALLOWLIST)


def hard_ban() -> set[str]:
    return _csv_set("HL_PERPS_HARD_BAN_COINS", _DEFAULT_HARD_BAN)


def toxic_hours_et() -> set[int]:
    raw = os.getenv("PREDATOR_TOXIC_HOURS_ET", "8,9,10,11,12,13")
    out: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            out.add(int(part))
    return out


def max_opens_per_day() -> int:
    try:
        return int(os.getenv("PREDATOR_MAX_OPENS_PER_DAY", os.getenv("HL_PERPS_MAX_OPENS_PER_DAY", "6")))
    except ValueError:
        return 6


@dataclass
class PredatorVerdict:
    allow: bool
    reason: str
    regime: str = "UNKNOWN"
    hour_et: Optional[int] = None
    coin: str = ""
    direction: str = ""
    extra: dict = field(default_factory=dict)


def _hour_et(now: Optional[datetime] = None) -> int:
    now = now or datetime.now(_ET)
    if now.tzinfo is None:
        now = now.replace(tzinfo=_ET)
    return now.astimezone(_ET).hour


def _norm_regime(regime_name: Optional[str]) -> str:
    if not regime_name:
        return "UNKNOWN"
    return str(regime_name).strip().upper()


def evaluate_entry(
    coin: str,
    direction: str = "long",
    regime_name: Optional[str] = None,
    opens_today: int = 0,
    now: Optional[datetime] = None,
    persist: bool = True,
) -> PredatorVerdict:
    """Return whether Predator v1 will let this order through.

    When the flag is off, allow=True and reason=disabled so the scanner
    falls through to existing gates.
    """
    coin_u = (coin or "").strip().upper()
    direction_u = (direction or "long").strip().lower()
    regime = _norm_regime(regime_name)
    hour = _hour_et(now)

    if not enabled():
        verdict = PredatorVerdict(
            allow=True,
            reason="predator_disabled",
            regime=regime,
            hour_et=hour,
            coin=coin_u,
            direction=direction_u,
        )
        if persist:
            _write_snapshot(verdict, last_block=None)
        return verdict

    if coin_u in hard_ban():
        return _reject(coin_u, direction_u, regime, hour, "hard_banned", persist)
    if coin_u not in allowlist():
        return _reject(coin_u, direction_u, regime, hour, "not_on_allowlist", persist)

    if _flag("PREDATOR_EXPANSION_ONLY", "true"):
        if regime in _CHOP_NAMES:
            return _reject(coin_u, direction_u, regime, hour, "regime_chop", persist)
        if regime in _NUKE_NAMES and direction_u == "long":
            return _reject(coin_u, direction_u, regime, hour, "regime_nuke_long", persist)
        if regime == "UNKNOWN":
            return _reject(coin_u, direction_u, regime, hour, "regime_unknown", persist)
        if regime not in _EXPANSION_NAMES and regime not in _NUKE_NAMES:
            return _reject(coin_u, direction_u, regime, hour, f"regime_{regime.lower()}", persist)

    if _flag("PREDATOR_BLOCK_TOXIC_HOURS", "true") and hour in toxic_hours_et():
        return _reject(coin_u, direction_u, regime, hour, f"toxic_hour_et_{hour:02d}", persist)

    cap = max_opens_per_day()
    if cap > 0 and opens_today >= cap:
        return _reject(coin_u, direction_u, regime, hour, "daily_open_cap", persist)

    _EVAL_STATS["evaluations"] += 1
    _EVAL_STATS["allowed"] += 1

    verdict = PredatorVerdict(
        allow=True,
        reason="expansion_clear",
        regime=regime,
        hour_et=hour,
        coin=coin_u,
        direction=direction_u,
    )
    if persist:
        _write_snapshot(verdict, last_block=None)
    return verdict


_EVAL_STATS: dict = {"evaluations": 0, "allowed": 0, "denied": 0, "reasons": {}}


def get_deny_stats() -> dict:
    total = _EVAL_STATS["evaluations"]
    denied = _EVAL_STATS["denied"]
    rate = round((denied / total * 100.0), 1) if total > 0 else 0.0
    return {
        "evaluations": total,
        "allowed": _EVAL_STATS["allowed"],
        "denied": denied,
        "deny_rate_pct": rate,
        "reasons": dict(_EVAL_STATS["reasons"]),
    }


def get_paper_metrics() -> dict:
    candidates = [
        Path(os.getenv("TRADES_FILE", "output/trades.json")),
        Path("output/trades.json"),
        Path("/app/output/trades.json"),
    ]
    trades: list = []
    for path in candidates:
        if not path.exists():
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8") or "[]")
            if isinstance(raw, list) and raw:
                trades = raw
                break
        except Exception:
            continue

    paper = [t for t in trades if t.get("is_paper") is True]
    pool = paper if paper else trades
    closes = [
        t for t in pool
        if str(t.get("action", "")).upper() in ("SELL", "CLOSE", "SELL_SHORT")
        and t.get("pnl_usd") is not None
    ]
    if not closes:
        return {
            "closed_trades": 0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "net_pnl": 0.0,
            "avg_mfe_winners_pct": None,
            "avg_realized_winner_pct": None,
            "mfe_capture_ratio_pct": None,
            "gates": {
                "min_trades": 50,
                "min_wr": 0.50,
                "min_pf": 1.30,
                "trades_ok": False,
                "wr_ok": False,
                "pf_ok": False,
                "ready": False,
            },
        }

    wins = [float(t["pnl_usd"]) for t in closes if float(t["pnl_usd"]) > 0]
    losses = [float(t["pnl_usd"]) for t in closes if float(t["pnl_usd"]) < 0]
    gross_win = sum(wins) if wins else 0.0
    gross_loss = abs(sum(losses)) if losses else 0.0
    pf = round((gross_win / gross_loss), 2) if gross_loss > 0 else (999.0 if gross_win > 0 else 0.0)
    wr = round((len(wins) / len(closes)), 3) if closes else 0.0
    net_pnl = round(sum(float(t["pnl_usd"]) for t in closes), 2)

    # MFE capture ratio (how much of favorable peak move was locked in)
    mfe_vals = [float(t["mfe_pct"]) for t in closes if t.get("mfe_pct") is not None and float(t["pnl_usd"]) > 0]
    win_pcts = [float(t.get("pnl_pct", 0.0) or 0.0) for t in closes if float(t["pnl_usd"]) > 0]
    avg_mfe = (sum(mfe_vals) / len(mfe_vals)) if mfe_vals else None
    avg_win_pct = (sum(win_pcts) / len(win_pcts)) if win_pcts else None
    mfe_capture_ratio = None
    if avg_mfe and avg_mfe > 0 and avg_win_pct is not None:
        mfe_capture_ratio = round((avg_win_pct / avg_mfe) * 100.0, 1)

    trades_ok = len(closes) >= 50
    wr_ok = wr >= 0.50
    pf_ok = pf >= 1.30

    return {
        "closed_trades": len(closes),
        "win_rate": wr,
        "profit_factor": pf,
        "net_pnl": net_pnl,
        "avg_mfe_winners_pct": round(avg_mfe, 2) if avg_mfe else None,
        "avg_realized_winner_pct": round(avg_win_pct, 2) if avg_win_pct else None,
        "mfe_capture_ratio_pct": mfe_capture_ratio,
        "gates": {
            "min_trades": 50,
            "min_wr": 0.50,
            "min_pf": 1.30,
            "trades_ok": trades_ok,
            "wr_ok": wr_ok,
            "pf_ok": pf_ok,
            "ready": trades_ok and wr_ok and pf_ok,
        },
    }


def _reject(
    coin: str,
    direction: str,
    regime: str,
    hour: int,
    reason: str,
    persist: bool,
) -> PredatorVerdict:
    _EVAL_STATS["evaluations"] += 1
    _EVAL_STATS["denied"] += 1
    _EVAL_STATS["reasons"][reason] = _EVAL_STATS["reasons"].get(reason, 0) + 1

    verdict = PredatorVerdict(
        allow=False,
        reason=reason,
        regime=regime,
        hour_et=hour,
        coin=coin,
        direction=direction,
    )
    if persist:
        _write_snapshot(verdict, last_block=verdict)
    return verdict


def snapshot_payload(last: PredatorVerdict, last_block: Optional[PredatorVerdict] = None) -> dict:
    return {
        "enabled": enabled(),
        "expansion_only": _flag("PREDATOR_EXPANSION_ONLY", "true"),
        "block_toxic_hours": _flag("PREDATOR_BLOCK_TOXIC_HOURS", "true"),
        "toxic_hours_et": sorted(toxic_hours_et()),
        "max_opens_per_day": max_opens_per_day(),
        "allowlist": sorted(allowlist()),
        "hard_ban": sorted(hard_ban()),
        "last": asdict(last),
        "last_block": asdict(last_block) if last_block else None,
        "deny_stats": get_deny_stats(),
        "paper_metrics": get_paper_metrics(),
        "updated_at": datetime.now(_ET).isoformat(),
    }


def _write_snapshot(last: PredatorVerdict, last_block: Optional[PredatorVerdict]) -> None:
    try:
        _SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        payload = snapshot_payload(last, last_block)
        tmp = _SNAPSHOT.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2))
        tmp.replace(_SNAPSHOT)
    except Exception as exc:
        logger.debug("predator snapshot write failed: %s", exc)
