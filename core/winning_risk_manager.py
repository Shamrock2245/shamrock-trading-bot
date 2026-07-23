"""
core/winning_risk_manager.py — "Winning" Risk Management decision engine

Wired into main.py → _hl_trailing_monitor_daemon when WINNING_RISK_MANAGER_ENABLED=true.
Does NOT own on-chain order state (executor / hl_trailing_state.json does).

Closes capital leaks diagnosed from trade_history (29), retuned by trade_history (34):
  v31 killed the fat tails (worst loss −13% → −2.7%) but over-corrected — the 0.5%
  trail + 1.5h loss timeout choked every runner (post-v31: WR 22.5%, max win +2.16%,
  37 churn exits in −0.5..0%). 7/14–7/21 proved the edge: 18 winners >2% = +$151.

Rules (price-move %, leverage-agnostic) — v32 "Let Winners Breathe":
1. Hard loss timeout (default 4h) — force-close multi-hour red holds
   (1–4h is the historically profitable hold bucket; 1.5h was closing winners early)
2. 45-Min Rule — if still red after 45m, tighten SL to −1.5%
3. TP1 front-load — partial close 40% at +2% (keep more runner)
4. Ultra-fast break-even — lock SL to entry±buffer at +0.75%
5. Tiered trail — profit-laddered distance from peak (OpenAlice trailing_stop):
   +2% → 1.25% | +4% → 1.75% | +8% → 2.5% (runners get room as they grow)

Manus originally shipped a priority-bugged class (BE always returned before TP1/trail
could fire) with zero callers. This rewrite matches profit_lock_manager style.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    try:
        return int(float(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class WinningRiskConfig:
    enabled: bool = True
    # Ultra-fast break-even
    be_pct: float = 0.75
    be_buffer_pct: float = 0.05
    # TP1 front-load (v32: 40% — keep more of the runner)
    tp1_profit_pct: float = 2.0
    tp1_size_pct: float = 40.0
    # Trail (after TP1 or once trail activates)
    trail_activate_pct: float = 2.0
    trail_distance_pct: float = 1.25
    # v32 profit-tiered trail ladder "peak_pnl:trail_dist,…" — wider trail as the
    # runner grows. trade_history 34: 0.5% flat trail capped every winner ≤ +2.16%
    # post-v31 while >2% winners were the only net-positive bucket (+$151).
    trail_ladder: str = "2:1.25,4:1.75,8:2.5"
    # 45-min rule (v32: was 30m/−1% — too twitchy, fed the −0.5..0% churn band)
    min_rule_minutes: float = 45.0
    min_rule_sl_pct: float = -1.5  # tighten SL to −1.5% from entry
    # Hard timeout — v32: 4h. Hold-bucket PnL: 1–4h +$13 (36.7% WR), 4–12h 52.8% WR.
    # The 1.5h timeout was force-closing trades that were about to work.
    loss_timeout_hours: float = 4.0
    # Toxic zone (America/New_York wall-clock hour)
    toxic_zone_enabled: bool = True
    toxic_zone_start: int = 8
    toxic_zone_end: int = 14
    toxic_zone_size_mult: float = 0.5


@dataclass
class WinningRiskDecision:
    """Result of evaluating one open position under Winning rules."""

    status: str  # "active" | "timeout_close" | "partial_close"
    sl_price: Optional[float] = None
    close_size_pct: float = 0.0  # 0–100 for partial_close
    reason: str = ""
    pnl_pct: float = 0.0
    hold_minutes: float = 0.0
    mark_tp1: bool = False  # caller should persist tp1_hit=True after partial

    @property
    def should_close(self) -> bool:
        return self.status == "timeout_close"

    @property
    def should_partial_close(self) -> bool:
        return self.status == "partial_close" and self.close_size_pct > 0

    @property
    def should_update_sl(self) -> bool:
        return self.sl_price is not None and self.status == "active"


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def default_config() -> WinningRiskConfig:
    """Fresh config from current env (tests can monkeypatch env)."""
    return WinningRiskConfig(
        enabled=_env_bool("WINNING_RISK_MANAGER_ENABLED", True),
        be_pct=_env_float("FAST_BREAK_EVEN_PCT", 0.75),
        be_buffer_pct=_env_float("FAST_BREAK_EVEN_SL_OFFSET", 0.05),
        tp1_profit_pct=_env_float("TP1_PROFIT_PCT", 2.0),
        tp1_size_pct=_env_float("TP1_SIZE_PCT", 40.0),
        trail_activate_pct=_env_float("TP1_PROFIT_PCT", 2.0),  # trail arms at same level
        trail_distance_pct=_env_float("TRAILING_STOP_PCT", 1.25),
        trail_ladder=os.getenv("TRAIL_LADDER", "2:1.25,4:1.75,8:2.5"),
        min_rule_minutes=_env_float("MIN_RULE_TIME_MINUTES", 45.0),
        min_rule_sl_pct=_env_float("MIN_RULE_SL_OFFSET", -1.5),
        # v32: 4h (was 1.5h) — 1–4h holds are the profitable bucket; 1.5h choked them
        loss_timeout_hours=_env_float("WINNING_LOSS_TIMEOUT_HOURS", 4.0),
        toxic_zone_enabled=_env_bool("TOXIC_ZONE_RESTRICTION", True),
        toxic_zone_start=_env_int("TOXIC_ZONE_START", 8),
        toxic_zone_end=_env_int("TOXIC_ZONE_END", 14),
        toxic_zone_size_mult=_env_float("TOXIC_ZONE_SIZE_MULT", 0.5),
    )


def _pnl_pct(side: str, entry: float, current: float) -> float:
    if entry <= 0:
        return 0.0
    if side == "long":
        return ((current - entry) / entry) * 100.0
    return ((entry - current) / entry) * 100.0


def parse_trail_ladder(raw: str) -> list:
    """Parse "2:1.25,4:1.75,8:2.5" → [(2.0, 1.25), (4.0, 1.75), (8.0, 2.5)].

    Sorted ascending by peak-pnl threshold. Malformed entries are skipped; an
    empty or fully-malformed string returns [] (caller falls back to flat trail).
    """
    rungs = []
    for part in (raw or "").split(","):
        part = part.strip()
        if not part or ":" not in part:
            continue
        lhs, rhs = part.split(":", 1)
        try:
            thresh = float(lhs.strip())
            dist = float(rhs.strip())
        except (TypeError, ValueError):
            continue
        if dist > 0:
            rungs.append((thresh, dist))
    rungs.sort(key=lambda r: r[0])
    return rungs


def trail_distance_for_pnl(peak_pnl_pct: float, ladder: list, base_distance: float) -> float:
    """Pick trail distance for the current peak-pnl from the tiered ladder.

    The highest rung whose threshold ≤ peak_pnl wins; below the first rung (or
    with an empty ladder) the flat base distance applies.
    """
    dist = base_distance
    for thresh, rung_dist in ladder:
        if peak_pnl_pct >= thresh:
            dist = rung_dist
        else:
            break
    return dist


def _sl_is_improvement(
    side: str,
    new_sl: float,
    current_sl: Optional[float],
) -> bool:
    """True if new_sl is strictly tighter (more protective) than current_sl."""
    if current_sl is None or current_sl <= 0:
        return True
    if side == "long":
        return new_sl > current_sl
    return new_sl < current_sl


def evaluate_position(
    *,
    coin: str,
    current_price: float,
    entry_price: float,
    entry_time: datetime,
    side: str = "long",
    peak_price: Optional[float] = None,
    current_sl: Optional[float] = None,
    tp1_hit: bool = False,
    now: Optional[datetime] = None,
    config: Optional[WinningRiskConfig] = None,
) -> WinningRiskDecision:
    """
    Evaluate Winning risk rules for one open position.

    Priority (first match wins for terminal actions; SL picks most protective):
      1. Hard loss timeout → timeout_close
      2. TP1 partial close at +tp1_profit_pct (once)
      3. Merge SL candidates: aggressive trail | BE lock | 30-min tighten
    """
    cfg = config or default_config()
    side = (side or "long").lower()
    if side not in ("long", "short"):
        side = "long"

    if not cfg.enabled:
        return WinningRiskDecision(status="active", reason="disabled")

    if entry_price <= 0 or current_price <= 0:
        return WinningRiskDecision(status="active", reason="invalid_price")

    now_utc = _to_utc(now or datetime.now(timezone.utc))
    entry_utc = _to_utc(entry_time)
    hold_minutes = max(0.0, (now_utc - entry_utc).total_seconds() / 60.0)
    hold_hours = hold_minutes / 60.0
    pnl = _pnl_pct(side, entry_price, current_price)

    if side == "long":
        peak = peak_price if peak_price and peak_price > 0 else current_price
        peak = max(peak, current_price)
    else:
        if peak_price and peak_price > 0:
            peak = min(peak_price, current_price)
        else:
            peak = current_price

    # ── 1. Hard loss timeout ──────────────────────────────────────────────────
    if pnl < 0 and hold_hours >= cfg.loss_timeout_hours:
        logger.warning(
            f"[{coin}] Winning hard timeout: {hold_hours:.1f}h in loss ({pnl:.2f}%). "
            f"Force-close to free capital."
        )
        return WinningRiskDecision(
            status="timeout_close",
            reason=f"winning_loss_timeout_{hold_hours:.1f}h",
            pnl_pct=pnl,
            hold_minutes=hold_minutes,
        )

    # ── 2. TP1 front-load (before BE/trail so partial can fire) ───────────────
    if (not tp1_hit) and pnl >= cfg.tp1_profit_pct and cfg.tp1_size_pct > 0:
        logger.info(
            f"[{coin}] 💰 TP1 Front-loading: +{pnl:.2f}% → close {cfg.tp1_size_pct:.0f}%"
        )
        return WinningRiskDecision(
            status="partial_close",
            close_size_pct=cfg.tp1_size_pct,
            reason=f"tp1_front_load_+{pnl:.2f}%",
            pnl_pct=pnl,
            hold_minutes=hold_minutes,
            mark_tp1=True,
        )

    # ── 3. SL candidates (pick most protective) ───────────────────────────────
    recommended_sl: Optional[float] = None
    reason = "hold"

    # 3a. Tiered trail after TP1, or once pnl reaches trail activate.
    # v32: distance widens with PEAK profit (entry→peak move picks the rung),
    # so an +8% runner trails 2.5% while a fresh +2% winner trails 1.25%.
    trail_armed = tp1_hit or pnl >= cfg.trail_activate_pct
    if trail_armed and pnl > 0:
        peak_pnl = _pnl_pct(side, entry_price, peak)
        ladder = parse_trail_ladder(getattr(cfg, "trail_ladder", "") or "")
        trail_dist = trail_distance_for_pnl(peak_pnl, ladder, cfg.trail_distance_pct)
        trail_frac = trail_dist / 100.0
        if side == "long":
            trail_sl = peak * (1.0 - trail_frac)
        else:
            trail_sl = peak * (1.0 + trail_frac)
        if _sl_is_improvement(side, trail_sl, current_sl):
            recommended_sl = trail_sl
            reason = "winning_aggressive_trail"

    # 3b. Ultra-fast break-even at +0.75%
    if pnl >= cfg.be_pct:
        if side == "long":
            be_sl = entry_price * (1.0 + cfg.be_buffer_pct / 100.0)
        else:
            be_sl = entry_price * (1.0 - cfg.be_buffer_pct / 100.0)
        if _sl_is_improvement(side, be_sl, current_sl):
            # Prefer trail if already tighter; else BE
            if recommended_sl is None:
                recommended_sl = be_sl
                reason = "winning_break_even"
            elif side == "long" and be_sl > recommended_sl:
                # BE higher than trail only if trail is somehow below BE (unusual)
                pass
            elif side == "short" and be_sl < recommended_sl:
                pass
            # If trail not set yet, BE wins; if trail set, keep trail (more protective on runners)
            if reason != "winning_aggressive_trail":
                recommended_sl = be_sl
                reason = "winning_break_even"

    # 3c. 45-Min Rule (v32): still red after N minutes → tighten SL to −1.5%
    if hold_minutes >= cfg.min_rule_minutes and pnl < 0:
        # min_rule_sl_pct is negative (e.g. -1.0) → long SL below entry, short above
        offset = cfg.min_rule_sl_pct / 100.0
        if side == "long":
            tight_sl = entry_price * (1.0 + offset)  # e.g. entry * 0.99
        else:
            tight_sl = entry_price * (1.0 - offset)  # e.g. entry * 1.01
        if _sl_is_improvement(side, tight_sl, current_sl):
            # Prefer if tighter than any other candidate (we're in loss — usually only this fires)
            if recommended_sl is None:
                recommended_sl = tight_sl
                reason = "winning_30min_rule"
            elif side == "long" and tight_sl > recommended_sl:
                recommended_sl = tight_sl
                reason = "winning_30min_rule"
            elif side == "short" and tight_sl < recommended_sl:
                recommended_sl = tight_sl
                reason = "winning_30min_rule"

    if recommended_sl is not None:
        logger.info(
            f"[{coin}] Winning SL | reason={reason} | sl={recommended_sl:.8f} | "
            f"pnl={pnl:.2f}% | hold={hold_minutes:.0f}m"
        )

    return WinningRiskDecision(
        status="active",
        sl_price=recommended_sl,
        reason=reason,
        pnl_pct=pnl,
        hold_minutes=hold_minutes,
    )


def is_toxic_zone(
    hour: Optional[int] = None,
    config: Optional[WinningRiskConfig] = None,
) -> bool:
    """True if wall-clock hour is in the toxic trading window (default 08–14 ET)."""
    cfg = config or default_config()
    if not cfg.toxic_zone_enabled:
        return False
    if hour is None:
        try:
            from zoneinfo import ZoneInfo

            hour = datetime.now(ZoneInfo("America/New_York")).hour
        except Exception:
            hour = datetime.now(timezone.utc).hour
    return cfg.toxic_zone_start <= hour < cfg.toxic_zone_end


def get_position_size_multiplier(
    hour: Optional[int] = None,
    config: Optional[WinningRiskConfig] = None,
) -> float:
    """Reduce size during toxic hours (trade_history 29: 08–14 ET −$326 vs +$28 elsewhere)."""
    cfg = config or default_config()
    if is_toxic_zone(hour=hour, config=cfg):
        logger.info(
            f"⚠️  Toxic Zone hour — reducing position size to "
            f"{cfg.toxic_zone_size_mult * 100:.0f}%"
        )
        return cfg.toxic_zone_size_mult
    return 1.0


class WinningRiskManager:
    """Thin wrapper for convenience imports (same pattern as ProfitLockManager)."""

    def __init__(self, config: Optional[WinningRiskConfig] = None):
        self.config = config

    def evaluate_position(self, pos_data: dict) -> dict:
        """Dict-style API compatible with Manus's original sketch."""
        entry_time = pos_data.get("entry_time")
        if isinstance(entry_time, (int, float)):
            entry_time = datetime.fromtimestamp(float(entry_time), tz=timezone.utc)
        elif not isinstance(entry_time, datetime):
            entry_time = datetime.now(timezone.utc)

        d = evaluate_position(
            coin=str(pos_data.get("coin", "UNKNOWN")),
            current_price=float(pos_data["current_price"]),
            entry_price=float(pos_data["entry_price"]),
            entry_time=entry_time,
            side=str(pos_data.get("side", "long")),
            peak_price=pos_data.get("peak_price"),
            current_sl=pos_data.get("current_sl") or pos_data.get("sl_price"),
            tp1_hit=bool(pos_data.get("tp1_hit", False)),
            config=self.config,
        )
        out: dict = {
            "action": "none",
            "reason": d.reason,
            "pnl_pct": d.pnl_pct,
            "hold_minutes": d.hold_minutes,
        }
        if d.should_close:
            out["action"] = "close_all"
        elif d.should_partial_close:
            out["action"] = "partial_close"
            out["close_size_pct"] = d.close_size_pct
        elif d.should_update_sl:
            out["action"] = "update_sl"
            out["sl_price"] = d.sl_price
        return out

    def is_toxic_zone(self, hour: int) -> bool:
        return is_toxic_zone(hour=hour, config=self.config)

    def get_position_size_multiplier(self, hour: int) -> float:
        return get_position_size_multiplier(hour=hour, config=self.config)


# Global instance
winning_risk_manager = WinningRiskManager()
