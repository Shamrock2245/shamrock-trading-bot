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


def _reject(
    coin: str,
    direction: str,
    regime: str,
    hour: int,
    reason: str,
    persist: bool,
) -> PredatorVerdict:
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
