"""core/hot_streak.py — HotStreakAmplifier: upside-only size/leverage ladder.

Asymmetric by design:
  - Downside ALWAYS wins. Hard-ban, Predator chop skip, toxic hours, daily open
    cap, and PAPER_MODE_LOCKED are never bypassed by this module.
  - Upside amplifier ONLY when proven hot on the HL allowlist close path.
  - Wire AFTER Predator allow so denied entries never get amplified.

Primary arm: N consecutive *closed* allowlist wins (HOT_STREAK_MIN_WINS, default 3).
Optional confirm: rolling last M closes WR>=W and PF>=P
  (HOT_STREAK_ROLLING_CONFIRM=true; defaults M=10, W=0.55, P=1.2).

Ladder (HOT_STREAK_MULT_LADDER): streak 3→1.25×, 5→1.5×, 7→1.75×; hard CAP
HOT_STREAK_MAX_MULT (default 2.0). Never above scanner/HL max leverage or max notional.

Instant disarm: any closed loss, day net PnL < 0, or open drawdown from day peak
> HOT_STREAK_DISARM_DD_PCT (default 3%). Streak resets to 0.

Persists to data/dashboard/hot_streak.json for the Predator Floor card.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_STATE_PATH = _ROOT / "data" / "dashboard" / "hot_streak.json"
_LOCK = threading.RLock()


def _flag(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(float(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


def parse_mult_ladder(raw: Optional[str] = None) -> list[tuple[int, float]]:
    """Parse '3:1.25,5:1.5,7:1.75' → sorted [(wins, mult), ...]."""
    raw = raw if raw is not None else os.getenv(
        "HOT_STREAK_MULT_LADDER", "3:1.25,5:1.5,7:1.75"
    )
    out: list[tuple[int, float]] = []
    for part in (raw or "").split(","):
        part = part.strip()
        if not part or ":" not in part:
            continue
        left, right = part.split(":", 1)
        try:
            wins = int(float(left.strip()))
            mult = float(right.strip())
        except (TypeError, ValueError):
            continue
        if wins > 0 and mult > 0:
            out.append((wins, mult))
    out.sort(key=lambda x: x[0])
    return out or [(3, 1.25), (5, 1.5), (7, 1.75)]


def ladder_multiplier(streak: int, ladder: Optional[list[tuple[int, float]]] = None,
                      max_mult: Optional[float] = None) -> float:
    """Highest ladder rung with wins <= streak, capped at max_mult. 1.0 if unarmed."""
    ladder = ladder if ladder is not None else parse_mult_ladder()
    max_mult = max_mult if max_mult is not None else _env_float("HOT_STREAK_MAX_MULT", 2.0)
    chosen = 1.0
    for wins, mult in ladder:
        if streak >= wins:
            chosen = mult
    return min(chosen, max_mult)


@dataclass
class HotStreakState:
    enabled: bool = False
    armed: bool = False
    consecutive_wins: int = 0
    multiplier: float = 1.0
    day_net_pnl: float = 0.0
    day_peak_pnl: float = 0.0
    day_key: str = ""
    disarm_reason: Optional[str] = None
    last_close_won: Optional[bool] = None
    rolling_closes: list[float] = field(default_factory=list)  # pnl_usd of recent closes
    last_update_utc: str = ""
    paper_only: bool = True


class HotStreakAmplifier:
    """Upside-only amplifier. Never grants entry permission."""

    def __init__(self, state_path: Optional[Path] = None) -> None:
        self.state_path = Path(
            os.getenv("HOT_STREAK_STATE_FILE", str(state_path or _DEFAULT_STATE_PATH))
        )
        self._state = HotStreakState()
        self._load()

    # ── config ──────────────────────────────────────────────────────────────
    def enabled(self) -> bool:
        return _flag("HOT_STREAK_ENABLED", "true")

    def min_wins(self) -> int:
        return max(1, _env_int("HOT_STREAK_MIN_WINS", 3))

    def max_mult(self) -> float:
        return max(1.0, _env_float("HOT_STREAK_MAX_MULT", 2.0))

    def disarm_dd_pct(self) -> float:
        return max(0.0, _env_float("HOT_STREAK_DISARM_DD_PCT", 3.0))

    def rolling_confirm(self) -> bool:
        return _flag("HOT_STREAK_ROLLING_CONFIRM", "false")

    def rolling_m(self) -> int:
        return max(1, _env_int("HOT_STREAK_ROLLING_M", 10))

    def rolling_wr(self) -> float:
        return _env_float("HOT_STREAK_ROLLING_WR", 0.55)

    def rolling_pf(self) -> float:
        return _env_float("HOT_STREAK_ROLLING_PF", 1.2)

    # ── persistence ─────────────────────────────────────────────────────────
    def _load(self) -> None:
        try:
            if not self.state_path.exists():
                return
            raw = json.loads(self.state_path.read_text(encoding="utf-8") or "{}")
            if not isinstance(raw, dict):
                return
            self._state = HotStreakState(
                enabled=bool(raw.get("enabled", False)),
                armed=bool(raw.get("armed", False)),
                consecutive_wins=int(raw.get("consecutive_wins", 0) or 0),
                multiplier=float(raw.get("multiplier", 1.0) or 1.0),
                day_net_pnl=float(raw.get("day_net_pnl", 0.0) or 0.0),
                day_peak_pnl=float(raw.get("day_peak_pnl", 0.0) or 0.0),
                day_key=str(raw.get("day_key") or ""),
                disarm_reason=raw.get("disarm_reason"),
                last_close_won=raw.get("last_close_won"),
                rolling_closes=[float(x) for x in (raw.get("rolling_closes") or [])],
                last_update_utc=str(raw.get("last_update_utc") or ""),
                paper_only=True,
            )
        except Exception as exc:
            logger.debug(f"[HOT-STREAK] load failed: {exc}")

    def _persist(self) -> None:
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            payload = asdict(self._state)
            payload["enabled"] = self.enabled()
            payload["paper_only"] = True
            payload["last_update_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            self._state.last_update_utc = payload["last_update_utc"]
            tmp = self.state_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            tmp.replace(self.state_path)
        except Exception as exc:
            logger.debug(f"[HOT-STREAK] persist failed: {exc}")

    def _today_key(self) -> str:
        # America/New_York trading day
        try:
            from zoneinfo import ZoneInfo
            from datetime import datetime
            return datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
        except Exception:
            return time.strftime("%Y-%m-%d", time.gmtime())

    def _rollover_day_if_needed(self) -> None:
        key = self._today_key()
        if self._state.day_key != key:
            self._state.day_key = key
            self._state.day_net_pnl = 0.0
            self._state.day_peak_pnl = 0.0
            # Streak persists across day boundary until a loss / DD / negative day
            # triggers disarm — but a fresh day with prior armed state is fine.
            if self._state.disarm_reason in ("day_net_negative", "drawdown"):
                self._state.disarm_reason = None

    # ── arm / disarm logic ──────────────────────────────────────────────────
    def _rolling_ok(self) -> bool:
        if not self.rolling_confirm():
            return True
        closes = self._state.rolling_closes[-self.rolling_m():]
        if len(closes) < self.rolling_m():
            return False
        wins = [p for p in closes if p > 0]
        losses = [p for p in closes if p < 0]
        wr = len(wins) / len(closes) if closes else 0.0
        gross_win = sum(wins) if wins else 0.0
        gross_loss = abs(sum(losses)) if losses else 0.0
        pf = (gross_win / gross_loss) if gross_loss > 0 else (999.0 if gross_win > 0 else 0.0)
        return wr >= self.rolling_wr() and pf >= self.rolling_pf()

    def _recompute_arm(self) -> None:
        streak = self._state.consecutive_wins
        if streak >= self.min_wins() and self._rolling_ok():
            self._state.armed = True
            self._state.multiplier = ladder_multiplier(
                streak, parse_mult_ladder(), self.max_mult()
            )
            self._state.disarm_reason = None
        else:
            self._state.armed = False
            self._state.multiplier = 1.0

    def _disarm(self, reason: str) -> None:
        self._state.armed = False
        self._state.consecutive_wins = 0
        self._state.multiplier = 1.0
        self._state.disarm_reason = reason
        logger.info(f"[HOT-STREAK] disarmed — {reason}")

    # ── public API ──────────────────────────────────────────────────────────
    def get_multiplier(self) -> float:
        with _LOCK:
            if not self.enabled():
                return 1.0
            self._rollover_day_if_needed()
            self._check_day_guards()
            if not self._state.armed:
                return 1.0
            return max(1.0, min(self._state.multiplier, self.max_mult()))

    def _check_day_guards(self) -> None:
        if self._state.day_net_pnl < 0 and self._state.armed:
            self._disarm("day_net_negative")
            return
        peak = self._state.day_peak_pnl
        if peak > 0:
            dd_pct = ((peak - self._state.day_net_pnl) / peak) * 100.0
            if dd_pct > self.disarm_dd_pct() and (self._state.armed or self._state.consecutive_wins > 0):
                self._disarm("drawdown")

    def update_open_equity(self, day_net_pnl: float) -> None:
        """Update day PnL / peak for open-drawdown disarm (call from scanner loop)."""
        with _LOCK:
            if not self.enabled():
                return
            self._rollover_day_if_needed()
            self._state.day_net_pnl = float(day_net_pnl)
            if self._state.day_net_pnl > self._state.day_peak_pnl:
                self._state.day_peak_pnl = self._state.day_net_pnl
            self._check_day_guards()
            self._persist()

    def record_close(
        self,
        won: bool,
        pnl_usd: float = 0.0,
        coin: str = "",
        *,
        on_allowlist: bool = True,
    ) -> HotStreakState:
        """Record a closed trade on the HL allowlist path.

        Non-allowlist closes are ignored for streak counting (Predator path only).
        Any loss on the allowlist path instantly disarms and resets streak to 0.
        """
        with _LOCK:
            if not self.enabled():
                self._state.enabled = False
                return self.snapshot()

            self._rollover_day_if_needed()
            coin_u = (coin or "").strip().upper()

            if not on_allowlist:
                logger.debug(f"[HOT-STREAK] ignore non-allowlist close {coin_u}")
                return self.snapshot()

            pnl = float(pnl_usd or 0.0)
            self._state.day_net_pnl = round(self._state.day_net_pnl + pnl, 4)
            if self._state.day_net_pnl > self._state.day_peak_pnl:
                self._state.day_peak_pnl = self._state.day_net_pnl

            self._state.rolling_closes.append(pnl)
            # Keep a bounded history (2× rolling window)
            keep = max(20, self.rolling_m() * 2)
            if len(self._state.rolling_closes) > keep:
                self._state.rolling_closes = self._state.rolling_closes[-keep:]

            self._state.last_close_won = bool(won)

            if (not won) or pnl < 0:
                self._disarm("closed_loss")
            else:
                self._state.consecutive_wins += 1
                self._recompute_arm()
                logger.info(
                    f"[HOT-STREAK] win #{self._state.consecutive_wins} on {coin_u or '?'} "
                    f"armed={self._state.armed} mult={self._state.multiplier:.2f}×"
                )

            # Day guards after PnL update
            if self._state.day_net_pnl < 0 and self._state.consecutive_wins > 0:
                self._disarm("day_net_negative")
            else:
                self._check_day_guards()

            self._persist()
            return self.snapshot()

    def amplify(
        self,
        size_usd: float,
        leverage: int,
        *,
        max_leverage: int,
        max_notional: float,
        max_position_usd: float,
        predator_allowed: bool = True,
    ) -> tuple[float, int, float]:
        """Apply ladder multiplier to size and leverage.

        Returns (new_size_usd, new_leverage, multiplier_applied).
        If predator_allowed is False, returns inputs unchanged (never bypass Predator).
        Caps: never above max_leverage, max_position_usd, or max_notional/leverage.
        """
        with _LOCK:
            if not self.enabled() or not predator_allowed:
                return float(size_usd), int(leverage), 1.0

            self._rollover_day_if_needed()
            self._check_day_guards()
            if not self._state.armed:
                return float(size_usd), int(leverage), 1.0
            mult = max(1.0, min(float(self._state.multiplier), self.max_mult()))
            if mult <= 1.0:
                return float(size_usd), int(leverage), 1.0

            new_lev = int(max(1, min(int(round(leverage * mult)), int(max_leverage))))
            new_size = float(size_usd) * mult
            new_size = min(new_size, float(max_position_usd))
            # Notional = margin × leverage; keep under hard notional cap
            lev_for_cap = max(1, new_lev)
            max_margin = float(max_notional) / lev_for_cap if max_notional > 0 else new_size
            new_size = min(new_size, max_margin)
            new_size = round(max(0.0, new_size), 2)

            logger.info(
                f"[HOT-STREAK] amplify ×{mult:.2f} "
                f"size ${size_usd:.2f}→${new_size:.2f} lev {leverage}x→{new_lev}x "
                f"(streak={self._state.consecutive_wins})"
            )
            self._persist()
            return new_size, new_lev, mult

    def snapshot(self) -> HotStreakState:
        self._state.enabled = self.enabled()
        return HotStreakState(**asdict(self._state))

    def get_state(self) -> dict[str, Any]:
        with _LOCK:
            self._rollover_day_if_needed()
            s = self.snapshot()
            d = asdict(s)
            d["min_wins"] = self.min_wins()
            d["max_mult"] = self.max_mult()
            d["ladder"] = [f"{w}:{m}" for w, m in parse_mult_ladder()]
            d["disarm_dd_pct"] = self.disarm_dd_pct()
            return d


_AMPLIFIER: Optional[HotStreakAmplifier] = None


def get_amplifier() -> HotStreakAmplifier:
    global _AMPLIFIER
    with _LOCK:
        if _AMPLIFIER is None:
            _AMPLIFIER = HotStreakAmplifier()
        return _AMPLIFIER


def reset_amplifier_for_tests(state_path: Optional[Path] = None) -> HotStreakAmplifier:
    """Test helper: drop singleton and optionally point at a temp state file."""
    global _AMPLIFIER
    with _LOCK:
        if state_path is not None:
            os.environ["HOT_STREAK_STATE_FILE"] = str(state_path)
        _AMPLIFIER = HotStreakAmplifier(state_path=state_path)
        return _AMPLIFIER


def get_hot_streak_state() -> dict[str, Any]:
    """Dashboard / external readers."""
    return get_amplifier().get_state()
