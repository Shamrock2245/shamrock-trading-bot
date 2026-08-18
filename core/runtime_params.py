"""
core/runtime_params.py — Live parameter overlay for auto-tuning.

settings.py reads env vars once at import. Writing os.environ after boot
does nothing to settings.MIN_GEM_SCORE (and friends). This module is the
single apply path:

  1. Mutate config.settings module attributes (what scanners/executors read)
  2. Mutate live StrategyProfile objects (what wallet_router + position_monitor read)
  3. Push env vars so child processes / WinningRiskConfig(default_config) see them
  4. Persist output/runtime_params.json so the bot process can pick up
     params written by the standalone auto-tuner service

Callers: Optuna apply_regime_params, self-improving agent, main.py startup.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent.parent
OVERLAY_PATH = Path(os.getenv("RUNTIME_PARAMS_FILE", str(_ROOT / "output" / "runtime_params.json")))

# Tuner-key / settings-name → settings attribute
PARAM_TO_SETTING: dict[str, str] = {
    "min_gem_score": "MIN_GEM_SCORE",
    "MIN_GEM_SCORE": "MIN_GEM_SCORE",
    "express_lane_score": "EXPRESS_LANE_SCORE",
    "EXPRESS_LANE_SCORE": "EXPRESS_LANE_SCORE",
    "tp1_mult": "TAKE_PROFIT_TP1_MULT",
    "TAKE_PROFIT_TP1_MULT": "TAKE_PROFIT_TP1_MULT",
    "tp1_sell_pct": "TAKE_PROFIT_TP1_SELL_PCT",
    "TAKE_PROFIT_TP1_SELL_PCT": "TAKE_PROFIT_TP1_SELL_PCT",
    "tp2_mult": "TAKE_PROFIT_TP2_MULT",
    "TAKE_PROFIT_TP2_MULT": "TAKE_PROFIT_TP2_MULT",
    "tp2_sell_pct": "TAKE_PROFIT_TP2_SELL_PCT",
    "TAKE_PROFIT_TP2_SELL_PCT": "TAKE_PROFIT_TP2_SELL_PCT",
    "tp3_mult": "TAKE_PROFIT_TP3_MULT",
    "TAKE_PROFIT_TP3_MULT": "TAKE_PROFIT_TP3_MULT",
    "tp3_sell_pct": "TAKE_PROFIT_TP3_SELL_PCT",
    "TAKE_PROFIT_TP3_SELL_PCT": "TAKE_PROFIT_TP3_SELL_PCT",
    "stop_loss_pct": "STOP_LOSS_PERCENT",
    "STOP_LOSS_PERCENT": "STOP_LOSS_PERCENT",
    "hard_stop_pct": "HARD_STOP_LOSS_PERCENT",
    "HARD_STOP_LOSS_PERCENT": "HARD_STOP_LOSS_PERCENT",
    "pre_tp1_trailing_pct": "PRE_TP1_TRAILING_STOP_PCT",
    "PRE_TP1_TRAILING_STOP_PCT": "PRE_TP1_TRAILING_STOP_PCT",
    "fast_fail_hours": "FAST_FAIL_HOURS",
    "FAST_FAIL_HOURS": "FAST_FAIL_HOURS",
    "FAST_FAIL_STALL_HOURS": "FAST_FAIL_STALL_HOURS",
    "fast_fail_down_pct": "FAST_FAIL_DOWN_PCT",
    "FAST_FAIL_DOWN_PCT": "FAST_FAIL_DOWN_PCT",
    "max_position_pct": "MAX_POSITION_SIZE_PERCENT",
    "MAX_POSITION_SIZE_PERCENT": "MAX_POSITION_SIZE_PERCENT",
    "god_mode_kelly_mult": "GOD_MODE_KELLY_MULTIPLIER",
    "GOD_MODE_KELLY_MULTIPLIER": "GOD_MODE_KELLY_MULTIPLIER",
    "time_exit_hours": "TIME_EXIT_HOURS",
    "TIME_EXIT_HOURS": "TIME_EXIT_HOURS",
    # Self-improving agent aliases
    "VOLUME_FLOOR_USD": "MIN_VOLUME_USD",
    "MIN_VOLUME_USD": "MIN_VOLUME_USD",
    "FAST_BREAK_EVEN_PCT": "FAST_BREAK_EVEN_PCT",
}

# Settings that also need a duplicate env/attr write
SETTING_ALIASES: dict[str, tuple[str, ...]] = {
    "FAST_FAIL_HOURS": ("FAST_FAIL_STALL_HOURS",),
}

BOUNDS: dict[str, tuple[float, float]] = {
    "MIN_GEM_SCORE": (55.0, 90.0),
    "EXPRESS_LANE_SCORE": (65.0, 95.0),
    "TAKE_PROFIT_TP1_MULT": (1.10, 3.50),
    "TAKE_PROFIT_TP1_SELL_PCT": (0.15, 0.70),
    "TAKE_PROFIT_TP2_MULT": (1.30, 8.00),
    "TAKE_PROFIT_TP2_SELL_PCT": (0.10, 0.70),
    "TAKE_PROFIT_TP3_MULT": (1.80, 20.00),
    "TAKE_PROFIT_TP3_SELL_PCT": (0.10, 1.00),
    "STOP_LOSS_PERCENT": (4.0, 25.0),
    "HARD_STOP_LOSS_PERCENT": (6.0, 35.0),
    "PRE_TP1_TRAILING_STOP_PCT": (5.0, 30.0),
    "FAST_FAIL_HOURS": (0.5, 8.0),
    "FAST_FAIL_STALL_HOURS": (0.5, 8.0),
    "FAST_FAIL_DOWN_PCT": (4.0, 25.0),
    "MAX_POSITION_SIZE_PERCENT": (1.0, 25.0),
    "GOD_MODE_KELLY_MULTIPLIER": (1.0, 4.0),
    "TIME_EXIT_HOURS": (2.0, 48.0),
    "MIN_VOLUME_USD": (100_000.0, 5_000_000.0),
    "FAST_BREAK_EVEN_PCT": (0.25, 5.0),
}

# Tuner key → StrategyProfile field
PROFILE_FIELD_MAP: dict[str, str] = {
    "min_gem_score": "min_gem_score",
    "MIN_GEM_SCORE": "min_gem_score",
    "express_lane_score": "express_lane_score",
    "EXPRESS_LANE_SCORE": "express_lane_score",
    "tp1_mult": "tp1_mult",
    "TAKE_PROFIT_TP1_MULT": "tp1_mult",
    "tp1_sell_pct": "tp1_sell_pct",
    "TAKE_PROFIT_TP1_SELL_PCT": "tp1_sell_pct",
    "tp2_mult": "tp2_mult",
    "TAKE_PROFIT_TP2_MULT": "tp2_mult",
    "tp2_sell_pct": "tp2_sell_pct",
    "TAKE_PROFIT_TP2_SELL_PCT": "tp2_sell_pct",
    "tp3_mult": "tp3_mult",
    "TAKE_PROFIT_TP3_MULT": "tp3_mult",
    "tp3_sell_pct": "tp3_sell_pct",
    "TAKE_PROFIT_TP3_SELL_PCT": "tp3_sell_pct",
    "stop_loss_pct": "trailing_stop_pct",
    "STOP_LOSS_PERCENT": "trailing_stop_pct",
    "hard_stop_pct": "hard_stop_pct",
    "HARD_STOP_LOSS_PERCENT": "hard_stop_pct",
    "max_position_pct": "max_position_pct",
    "MAX_POSITION_SIZE_PERCENT": "max_position_pct",
    "fast_fail_hours": "fast_fail_hours",
    "FAST_FAIL_HOURS": "fast_fail_hours",
    "fast_fail_down_pct": "fast_fail_down_pct",
    "FAST_FAIL_DOWN_PCT": "fast_fail_down_pct",
}

_last_loaded_mtime: float = 0.0
_last_applied: dict[str, Any] = {}


def _clamp(name: str, value: Any) -> Any:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return value
    bounds = BOUNDS.get(name)
    if not bounds:
        return numeric
    lo, hi = bounds
    return max(lo, min(hi, numeric))


def _coerce(existing: Any, incoming: Any) -> Any:
    if isinstance(existing, bool):
        if isinstance(incoming, bool):
            return incoming
        return str(incoming).strip().lower() in ("1", "true", "yes", "on")
    if isinstance(existing, int) and not isinstance(existing, bool):
        try:
            return int(float(incoming))
        except (TypeError, ValueError):
            return existing
    if isinstance(existing, float):
        try:
            return float(incoming)
        except (TypeError, ValueError):
            return existing
    return incoming


def _set_setting(attr: str, value: Any) -> Optional[Any]:
    from config import settings

    if not hasattr(settings, attr):
        # Still set so later getattr / env readers can see it
        setattr(settings, attr, value)
        os.environ[attr] = str(value)
        return value

    existing = getattr(settings, attr)
    coerced = _coerce(existing, value)
    if isinstance(coerced, (int, float)) and not isinstance(coerced, bool):
        coerced = _clamp(attr, coerced)
        if isinstance(existing, int) and not isinstance(existing, bool):
            coerced = int(coerced)
    setattr(settings, attr, coerced)
    os.environ[attr] = str(coerced)
    return coerced


def _apply_to_profiles(params: dict, nuclear_offset: bool = True) -> list[str]:
    """Push matching fields onto conservative + nuclear StrategyProfiles."""
    applied: list[str] = []
    try:
        from config.wallets import CONSERVATIVE_PROFILE, NUCLEAR_PROFILE
    except Exception as e:
        logger.debug(f"runtime_params: profiles unavailable: {e}")
        return applied

    for key, raw in params.items():
        field = PROFILE_FIELD_MAP.get(key)
        if not field or not hasattr(CONSERVATIVE_PROFILE, field):
            continue
        setting_name = PARAM_TO_SETTING.get(key, key)
        value = _clamp(setting_name, raw)
        try:
            setattr(CONSERVATIVE_PROFILE, field, float(value))
            nuclear_val = float(value)
            if nuclear_offset and field == "min_gem_score":
                nuclear_val = min(92.0, float(value) + 3.0)
            elif nuclear_offset and field == "express_lane_score":
                nuclear_val = min(95.0, float(value) + 2.0)
            elif nuclear_offset and field == "tp1_mult":
                nuclear_val = min(4.0, float(value) * 1.15)
            elif nuclear_offset and field == "trailing_stop_pct":
                nuclear_val = min(25.0, float(value) * 1.25)
            setattr(NUCLEAR_PROFILE, field, nuclear_val)
            applied.append(field)
        except Exception as e:
            logger.debug(f"runtime_params: failed to set profile.{field}: {e}")
    return applied


def _apply_side_effects(applied: dict[str, Any]) -> None:
    """Push volume floor / BE into modules that cache config at import."""
    vol = applied.get("MIN_VOLUME_USD")
    if vol is not None:
        try:
            from core.hl_scanner_winning_tuning import winning_entry_filter
            winning_entry_filter.config.min_volume_usd = float(vol)
        except Exception as e:
            logger.debug(f"runtime_params: volume floor side-effect skipped: {e}")


def apply_params(
    params: dict,
    source: str = "auto-tuner",
    persist: bool = True,
    extra: Optional[dict] = None,
) -> dict[str, Any]:
    """
    Apply a dict of tuner keys or SETTINGS names to the live process.

    Returns the dict of settings-name → applied value.
    """
    global _last_applied, _last_loaded_mtime

    if not params:
        return {}

    applied: dict[str, Any] = {}
    for key, raw in params.items():
        if raw is None:
            continue
        attr = PARAM_TO_SETTING.get(key)
        if not attr:
            continue
        value = _set_setting(attr, raw)
        if value is None:
            continue
        applied[attr] = value
        for alias in SETTING_ALIASES.get(attr, ()):
            alias_val = _set_setting(alias, value)
            if alias_val is not None:
                applied[alias] = alias_val

    profile_fields = _apply_to_profiles(params)
    _apply_side_effects(applied)

    _last_applied = dict(applied)
    if persist:
        payload = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "source": source,
            "params": applied,
            "profile_fields": profile_fields,
        }
        if extra:
            payload["extra"] = extra
        try:
            OVERLAY_PATH.parent.mkdir(parents=True, exist_ok=True)
            tmp = OVERLAY_PATH.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, indent=2))
            tmp.replace(OVERLAY_PATH)
            _last_loaded_mtime = OVERLAY_PATH.stat().st_mtime
        except Exception as e:
            logger.warning(f"runtime_params: failed to persist overlay: {e}")

    if applied:
        preview = ", ".join(f"{k}={v}" for k, v in list(applied.items())[:6])
        logger.info(
            f"runtime_params: applied {len(applied)} settings from {source} "
            f"({preview}{'…' if len(applied) > 6 else ''})"
        )
    return applied


def load_overlay() -> dict:
    if not OVERLAY_PATH.exists():
        return {}
    try:
        data = json.loads(OVERLAY_PATH.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def reload_overlay_if_newer(force: bool = False) -> dict[str, Any]:
    """
    If another process (auto-tuner service) wrote a newer overlay, apply it.
    """
    global _last_loaded_mtime
    if not OVERLAY_PATH.exists():
        return {}
    try:
        mtime = OVERLAY_PATH.stat().st_mtime
    except OSError:
        return {}
    if not force and mtime <= _last_loaded_mtime:
        return {}
    data = load_overlay()
    params = data.get("params") or {}
    if not params:
        _last_loaded_mtime = mtime
        return {}
    applied = apply_params(params, source=f"overlay:{data.get('source', 'disk')}", persist=False)
    _last_loaded_mtime = mtime
    return applied


def get_applied_params() -> dict[str, Any]:
    return dict(_last_applied)


def overlay_age_seconds() -> Optional[float]:
    if not OVERLAY_PATH.exists():
        return None
    try:
        return time.time() - OVERLAY_PATH.stat().st_mtime
    except OSError:
        return None
