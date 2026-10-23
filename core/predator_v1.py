"""
core/predator_v1.py — Expansion-only Hyperliquid entry gate.

This is the sniper layer the 29-indicator blender never was.

Rules (all must pass when PREDATOR_V1_ENABLED=true):
  1. Coin is on the profit allowlist (HL_PERPS_ALLOWLIST).
  2. Coin is not hard-banned (HL_PERPS_HARD_BAN_COINS).
  3. Regime is EXPANSION/TRENDING. CHOP is a skip in live;
     in paper with PREDATOR_PAPER_CHOP_HALF_SIZE=true, CHOP/RANGE is
     allowed at 0.5× size and tagged regime=chop_half (never above 0.5×).
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

_CHOP_NAMES = {"CHOPPY", "CHOP", "RANGE", "RANGING", "DEAD"}
_NUKE_NAMES = {"NUKE", "CRASH", "BEAR"}
_EXPANSION_NAMES = {"TRENDING", "EXPANSION", "TREND", "BULL", "NORMAL"}


def _flag(name: str, default: str = "true") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


def enabled() -> bool:
    return _flag("PREDATOR_V1_ENABLED", "false")


def paper_chop_half_size_enabled() -> bool:
    """Paper-only: allow CHOP/RANGE entries at 0.5×. Live always blocks chop."""
    return _flag("PREDATOR_PAPER_CHOP_HALF_SIZE", "true")


def is_paper_mode() -> bool:
    return os.getenv("MODE", "paper").strip().lower() != "live"


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

    chop_half = False
    if _flag("PREDATOR_EXPANSION_ONLY", "true"):
        if regime in _CHOP_NAMES:
            # Live (or flag off): chop is a hard skip. Paper + flag: half-size only.
            if paper_chop_half_size_enabled() and is_paper_mode():
                chop_half = True
            else:
                return _reject(coin_u, direction_u, regime, hour, "regime_chop", persist)
        elif regime in _NUKE_NAMES and direction_u == "long":
            return _reject(coin_u, direction_u, regime, hour, "regime_nuke_long", persist)
        elif regime == "UNKNOWN":
            return _reject(coin_u, direction_u, regime, hour, "regime_unknown", persist)
        elif regime not in _EXPANSION_NAMES and regime not in _NUKE_NAMES:
            return _reject(coin_u, direction_u, regime, hour, f"regime_{regime.lower()}", persist)

    if _flag("PREDATOR_BLOCK_TOXIC_HOURS", "true") and hour in toxic_hours_et():
        return _reject(coin_u, direction_u, regime, hour, f"toxic_hour_et_{hour:02d}", persist)

    cap = max_opens_per_day()
    if cap > 0 and opens_today >= cap:
        return _reject(coin_u, direction_u, regime, hour, "daily_open_cap", persist)

    _EVAL_STATS["evaluations"] += 1
    _EVAL_STATS["allowed"] += 1

    if chop_half:
        verdict = PredatorVerdict(
            allow=True,
            reason="regime_chop_half",
            regime=regime,
            hour_et=hour,
            coin=coin_u,
            direction=direction_u,
            extra={"size_mult": 0.5, "regime_tag": "chop_half"},
        )
    else:
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


GATE_SCOPE = "hyperliquid_perps_paper"
_CLOSE_ACTIONS = ("SELL", "CLOSE", "SELL_SHORT")
_ORPHAN_REASONS = {"restart_orphan"}


def is_hl_perps_row(t: dict) -> bool:
    """True for Hyperliquid perps rows (Predator's book), never gem/DEX chains.

    trades.json is shared with the Solana/Base/Ethereum gem side; those rows
    must not leak into the Predator promotion gate. StatArb paper never writes
    trades.json, so it is excluded by construction.
    """
    chain = str(t.get("chain") or "").strip().lower()
    if chain and chain != "hyperliquid":
        return False
    if chain == "hyperliquid":
        return True
    # Legacy rows without chain: accept only explicit HL markers
    return (
        str(t.get("strategy_profile") or "") == "hl_perps"
        or str(t.get("token_address") or "").startswith("hl:")
    )


def is_gate_close(t: dict) -> bool:
    """A paper Hyperliquid perps close that counts toward the Predator gate.

    Excludes: live rows, gem/DEX chains, opens, rows without PnL, exact $0
    rows (placeholder/no-fill artefacts), restart orphans and anything tagged
    exclude_from_metrics. Thresholds are unchanged (50 / 50% / 1.30).
    """
    if not isinstance(t, dict) or t.get("is_paper") is not True:
        return False
    if not is_hl_perps_row(t):
        return False
    if str(t.get("action", "")).upper() not in _CLOSE_ACTIONS:
        return False
    if t.get("exclude_from_metrics"):
        return False
    if str(t.get("reason") or "") in _ORPHAN_REASONS:
        return False
    pnl = t.get("pnl_usd")
    if pnl is None:
        return False
    try:
        pnl_f = float(pnl)
    except (TypeError, ValueError):
        return False
    if pnl_f != pnl_f or abs(pnl_f) < 1e-9:  # NaN or exact $0
        return False
    return True


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

    closes = [t for t in trades if is_gate_close(t)]
    if not closes:
        return {
            "scope": GATE_SCOPE,
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
            "by_variant": paper_metrics_by_variant([]),
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
        "scope": GATE_SCOPE,
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
        "by_variant": paper_metrics_by_variant(closes),
    }


AB_VARIANTS = ("control", "atr2x_8h")


def _variant_summary(rows: list) -> dict:
    pnls = [float(t["pnl_usd"]) for t in rows]
    wins = [p for p in pnls if p > 0]
    gl = abs(sum(p for p in pnls if p < 0))
    gw = sum(wins)
    return {
        "closed_trades": len(rows),
        "positions_closed": sum(1 for t in rows if t.get("exit_reason") != "tp1_partial"),
        "win_rate": round(len(wins) / len(rows), 3) if rows else 0.0,
        "profit_factor": (round(gw / gl, 2) if gl > 0 else (999.0 if gw > 0 else 0.0)) if rows else 0.0,
        "net_pnl": round(sum(pnls), 2),
        "avg_pnl": round(sum(pnls) / len(rows), 2) if rows else 0.0,
    }


def paper_metrics_by_variant(closes: list) -> dict:
    """Reporting-only split of gate closes by paper exit A/B arm
    (core/paper_exit_ab.py). Rows from before the A/B are "untagged".
    Does not change the gate itself (overall thresholds 50 / 50% / 1.30)."""
    groups: dict = {v: [] for v in AB_VARIANTS}
    groups["untagged"] = []
    for t in closes:
        v = str(t.get("exit_variant") or "")
        groups[v if v in groups else "untagged"].append(t)
    return {k: _variant_summary(v) for k, v in groups.items()}


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


def snapshot_payload(last, last_block=None) -> dict:
    """``last`` / ``last_block`` may be PredatorVerdict objects or plain dicts
    (refresh_snapshot re-uses the last persisted verdicts)."""
    def _d(v):
        if v is None:
            return None
        return v if isinstance(v, dict) else asdict(v)

    return {
        "enabled": enabled(),
        "expansion_only": _flag("PREDATOR_EXPANSION_ONLY", "true"),
        "paper_chop_half_size": paper_chop_half_size_enabled(),
        "block_toxic_hours": _flag("PREDATOR_BLOCK_TOXIC_HOURS", "true"),
        "toxic_hours_et": sorted(toxic_hours_et()),
        "max_opens_per_day": max_opens_per_day(),
        "allowlist": sorted(allowlist()),
        "hard_ban": sorted(hard_ban()),
        "last": _d(last),
        "last_block": _d(last_block),
        "deny_stats": get_deny_stats(),
        "paper_metrics": get_paper_metrics(),
        "updated_at": datetime.now(_ET).isoformat(),
    }


# Last verdicts written to the snapshot, so a refresh (on close / timer)
# rewrites paper_metrics without losing what the gate last decided.
_LAST: Optional[dict] = None
_LAST_BLOCK: Optional[dict] = None
_LAST_REFRESH_TS: float = 0.0


def _write_snapshot(last: PredatorVerdict, last_block: Optional[PredatorVerdict]) -> None:
    global _LAST, _LAST_BLOCK
    _LAST = asdict(last)
    if last_block is not None:
        _LAST_BLOCK = asdict(last_block)
    _flush_snapshot(reason="evaluate")


def _flush_snapshot(reason: str) -> bool:
    global _LAST, _LAST_BLOCK, _LAST_REFRESH_TS
    import time as _time

    try:
        _SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        if _LAST is None and _SNAPSHOT.exists():
            # Process restart: keep the verdicts already on disk.
            try:
                prev = json.loads(_SNAPSHOT.read_text(encoding="utf-8") or "{}")
                _LAST = prev.get("last") or None
                _LAST_BLOCK = _LAST_BLOCK or prev.get("last_block") or None
            except Exception:
                pass
        payload = snapshot_payload(_LAST, _LAST_BLOCK)
        payload["refresh_reason"] = reason
        tmp = _SNAPSHOT.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2))
        tmp.replace(_SNAPSHOT)
        _LAST_REFRESH_TS = _time.time()
        return True
    except Exception as exc:
        logger.debug("predator snapshot write failed: %s", exc)
        return False


def snapshot_refresh_sec() -> float:
    try:
        return float(os.getenv("PREDATOR_SNAPSHOT_REFRESH_SEC", "300"))
    except ValueError:
        return 300.0


def refresh_snapshot(reason: str = "manual", force: bool = True) -> bool:
    """Rewrite predator_v1.json (paper_metrics, deny stats) outside of an
    entry evaluation. Called on every HL close and on a timer from the scanner
    cycle, so the dashboard never shows hours-old gate stats.

    ``force=False`` honours PREDATOR_SNAPSHOT_REFRESH_SEC (0 disables the timer).
    No-op when the Predator gate is disabled."""
    if not enabled():
        return False
    if not force:
        interval = snapshot_refresh_sec()
        import time as _time

        if interval <= 0 or (_time.time() - _LAST_REFRESH_TS) < interval:
            return False
    return _flush_snapshot(reason=reason)
