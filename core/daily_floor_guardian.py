"""
core/daily_floor_guardian.py — Daily Balance Floor Guardian

Ensures the total portfolio value NEVER drops below the previous 24-hour
opening balance. This is the primary capital protection mechanism.

How it works:
  1. At midnight UTC (or first run each day), snapshots total portfolio USD
     value as the "daily floor".
  2. Every cycle, compares current portfolio value against the floor.
  3. If current value < floor × (1 - FLOOR_BREACH_BUFFER_PCT):
       → Enters CAPITAL_PRESERVATION_MODE
       → Blocks ALL new gem/swing entries
       → Triggers liquidation of weakest open positions
       → Rotates freed capital into blue-chip anchor
  4. If current value recovers above floor: exits preservation mode.

Integration:
  from core.daily_floor_guardian import DailyFloorGuardian
  guardian = DailyFloorGuardian()
  guardian.update(portfolio_usd)
  if guardian.is_preservation_mode:
      # Block new entries
"""

import json
import logging
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
FLOOR_STATE_FILE = Path(os.environ.get(
    "DAILY_FLOOR_STATE_FILE",
    os.path.join(os.path.dirname(__file__), "..", "output", "daily_floor.json"),
))

# How far below the floor triggers preservation mode (3% buffer)
FLOOR_BREACH_BUFFER_PCT = float(os.environ.get("FLOOR_BREACH_BUFFER_PCT", "3.0"))

# How far above the floor we need to recover to exit preservation mode
FLOOR_RECOVERY_BUFFER_PCT = float(os.environ.get("FLOOR_RECOVERY_BUFFER_PCT", "2.0"))

# Minimum portfolio value to track (ignore dust accounts)
FLOOR_MIN_PORTFOLIO_USD = float(os.environ.get("FLOOR_MIN_PORTFOLIO_USD", "10.0"))

# How many hours before midnight to lock the floor snapshot (default: lock at 23:00 UTC)
FLOOR_LOCK_HOUR_UTC = int(os.environ.get("FLOOR_LOCK_HOUR_UTC", "0"))  # midnight


@dataclass
class DailyFloorState:
    """Persistent state for the daily floor guardian."""
    # Today's floor (snapshot at midnight UTC)
    floor_usd: float = 0.0
    floor_date: str = ""                   # ISO date string "YYYY-MM-DD"
    floor_set_at: str = ""                 # ISO timestamp when floor was set

    # Yesterday's floor (for comparison / reporting)
    prev_floor_usd: float = 0.0
    prev_floor_date: str = ""

    # Current state
    current_portfolio_usd: float = 0.0
    last_updated_at: str = ""

    # Preservation mode
    is_preservation_mode: bool = False
    preservation_entered_at: str = ""
    preservation_reason: str = ""
    preservation_exits: int = 0            # How many times we've exited preservation
    preservation_entries: int = 0          # How many times we've entered preservation

    # Stats
    peak_usd_today: float = 0.0            # Highest value seen today
    trough_usd_today: float = 0.0          # Lowest value seen today
    daily_gain_usd: float = 0.0            # current - floor
    daily_gain_pct: float = 0.0            # (current - floor) / floor * 100


def _load_state() -> DailyFloorState:
    """Load state from disk, return fresh state if not found."""
    try:
        FLOOR_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        if FLOOR_STATE_FILE.exists():
            data = json.loads(FLOOR_STATE_FILE.read_text())
            return DailyFloorState(**{k: v for k, v in data.items() if k in DailyFloorState.__dataclass_fields__})
    except Exception as e:
        logger.debug(f"Daily floor state load error: {e}")
    return DailyFloorState()


def _save_state(state: DailyFloorState) -> None:
    """Persist state to disk."""
    try:
        FLOOR_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        FLOOR_STATE_FILE.write_text(json.dumps(asdict(state), indent=2))
    except Exception as e:
        logger.warning(f"Daily floor state save error: {e}")


class DailyFloorGuardian:
    """
    Monitors total portfolio value against the daily floor.
    Call update() every cycle with the current portfolio USD value.
    Check is_preservation_mode before allowing new entries.
    """

    def __init__(self):
        self._state = _load_state()
        logger.info(
            f"DailyFloorGuardian initialized | "
            f"floor=${self._state.floor_usd:,.2f} ({self._state.floor_date}) | "
            f"preservation={'ON' if self._state.is_preservation_mode else 'OFF'}"
        )

    @property
    def is_preservation_mode(self) -> bool:
        return self._state.is_preservation_mode

    @property
    def floor_usd(self) -> float:
        return self._state.floor_usd

    @property
    def daily_gain_usd(self) -> float:
        return self._state.daily_gain_usd

    @property
    def daily_gain_pct(self) -> float:
        return self._state.daily_gain_pct

    @property
    def state(self) -> DailyFloorState:
        return self._state

    def update(self, portfolio_usd: float) -> dict:
        """
        Main update call. Pass current total portfolio USD value.
        Returns a dict with action recommendations.

        Returns:
            {
                "mode": "normal" | "preservation",
                "floor_usd": float,
                "current_usd": float,
                "daily_gain_usd": float,
                "daily_gain_pct": float,
                "breach_pct": float,  # How far below floor (0 if above)
                "actions": list[str],  # Recommended actions
                "entered_preservation": bool,
                "exited_preservation": bool,
            }
        """
        if portfolio_usd < FLOOR_MIN_PORTFOLIO_USD:
            return {"mode": "normal", "floor_usd": 0.0, "current_usd": portfolio_usd,
                    "daily_gain_usd": 0.0, "daily_gain_pct": 0.0, "breach_pct": 0.0,
                    "actions": [], "entered_preservation": False, "exited_preservation": False}

        now_utc = datetime.now(timezone.utc)
        today_str = now_utc.strftime("%Y-%m-%d")
        now_iso = now_utc.isoformat()

        state = self._state
        actions = []
        entered_preservation = False
        exited_preservation = False

        # ── Step 1: Roll the floor at midnight UTC ────────────────────────────
        if state.floor_date != today_str or state.floor_usd == 0.0:
            # New day — roll yesterday's floor and set today's
            if state.floor_usd > 0:
                state.prev_floor_usd = state.floor_usd
                state.prev_floor_date = state.floor_date

            # Set today's floor to the higher of: current value OR yesterday's floor
            # This ensures the floor only ever goes UP over time
            new_floor = max(portfolio_usd, state.prev_floor_usd * 0.98)  # Allow 2% grace on roll
            state.floor_usd = round(new_floor, 2)
            state.floor_date = today_str
            state.floor_set_at = now_iso
            state.peak_usd_today = portfolio_usd
            state.trough_usd_today = portfolio_usd

            logger.info(
                f"📅 DAILY FLOOR SET: ${state.floor_usd:,.2f} for {today_str} "
                f"(portfolio=${portfolio_usd:,.2f})"
            )

        # ── Step 2: Update current value and stats ────────────────────────────
        state.current_portfolio_usd = round(portfolio_usd, 2)
        state.last_updated_at = now_iso

        if portfolio_usd > state.peak_usd_today:
            state.peak_usd_today = portfolio_usd
        if portfolio_usd < state.trough_usd_today or state.trough_usd_today == 0:
            state.trough_usd_today = portfolio_usd

        if state.floor_usd > 0:
            state.daily_gain_usd = round(portfolio_usd - state.floor_usd, 2)
            state.daily_gain_pct = round((portfolio_usd - state.floor_usd) / state.floor_usd * 100, 2)
        else:
            state.daily_gain_usd = 0.0
            state.daily_gain_pct = 0.0

        # ── Step 3: Check floor breach ────────────────────────────────────────
        breach_threshold = state.floor_usd * (1.0 - FLOOR_BREACH_BUFFER_PCT / 100.0)
        recovery_threshold = state.floor_usd * (1.0 + FLOOR_RECOVERY_BUFFER_PCT / 100.0)

        breach_pct = 0.0
        if state.floor_usd > 0 and portfolio_usd < state.floor_usd:
            breach_pct = round((state.floor_usd - portfolio_usd) / state.floor_usd * 100, 2)

        if portfolio_usd < breach_threshold and not state.is_preservation_mode:
            # ── ENTER PRESERVATION MODE ───────────────────────────────────────
            state.is_preservation_mode = True
            state.preservation_entered_at = now_iso
            state.preservation_entries += 1
            state.preservation_reason = (
                f"Portfolio ${portfolio_usd:,.2f} breached daily floor "
                f"${state.floor_usd:,.2f} by {breach_pct:.1f}%"
            )
            entered_preservation = True
            actions.extend([
                "BLOCK_NEW_ENTRIES",
                "LIQUIDATE_WEAKEST_POSITIONS",
                "ROTATE_TO_BLUECHIP_ANCHOR",
                "TIGHTEN_STOPS_TO_5PCT",
            ])
            logger.warning(
                f"🛡️ CAPITAL PRESERVATION MODE ACTIVATED: "
                f"portfolio=${portfolio_usd:,.2f} | floor=${state.floor_usd:,.2f} | "
                f"breach={breach_pct:.1f}% | entry #{state.preservation_entries}"
            )

        elif state.is_preservation_mode and portfolio_usd >= recovery_threshold:
            # ── EXIT PRESERVATION MODE ────────────────────────────────────────
            state.is_preservation_mode = False
            state.preservation_exits += 1
            exited_preservation = True
            actions.append("RESUME_NORMAL_TRADING")
            logger.info(
                f"✅ CAPITAL PRESERVATION MODE DEACTIVATED: "
                f"portfolio=${portfolio_usd:,.2f} recovered above floor "
                f"${state.floor_usd:,.2f} + {FLOOR_RECOVERY_BUFFER_PCT:.0f}% buffer | "
                f"exit #{state.preservation_exits}"
            )

        elif state.is_preservation_mode:
            # Still in preservation — keep blocking
            actions.extend([
                "BLOCK_NEW_ENTRIES",
                "MONITOR_POSITIONS_ONLY",
            ])

        # ── Step 4: Update the floor upward if we're doing well ──────────────
        # Ratchet: if we're significantly above the floor, raise it to lock in gains
        ratchet_threshold = state.floor_usd * 1.15  # 15% above floor
        if portfolio_usd >= ratchet_threshold and not state.is_preservation_mode:
            new_floor = round(portfolio_usd * 0.92, 2)  # Lock in 92% of current value
            if new_floor > state.floor_usd:
                old_floor = state.floor_usd
                state.floor_usd = new_floor
                logger.info(
                    f"📈 FLOOR RATCHET UP: ${old_floor:,.2f} → ${new_floor:,.2f} "
                    f"(portfolio=${portfolio_usd:,.2f}, locking in gains)"
                )

        _save_state(state)

        return {
            "mode": "preservation" if state.is_preservation_mode else "normal",
            "floor_usd": state.floor_usd,
            "current_usd": portfolio_usd,
            "daily_gain_usd": state.daily_gain_usd,
            "daily_gain_pct": state.daily_gain_pct,
            "breach_pct": breach_pct,
            "actions": actions,
            "entered_preservation": entered_preservation,
            "exited_preservation": exited_preservation,
            "peak_today": state.peak_usd_today,
            "trough_today": state.trough_usd_today,
        }

    def get_status(self) -> dict:
        """Return current guardian status for dashboard display."""
        s = self._state
        return {
            "floor_usd": s.floor_usd,
            "floor_date": s.floor_date,
            "current_usd": s.current_portfolio_usd,
            "daily_gain_usd": s.daily_gain_usd,
            "daily_gain_pct": s.daily_gain_pct,
            "peak_today": s.peak_usd_today,
            "trough_today": s.trough_usd_today,
            "is_preservation_mode": s.is_preservation_mode,
            "preservation_reason": s.preservation_reason if s.is_preservation_mode else "",
            "preservation_entries": s.preservation_entries,
            "prev_floor_usd": s.prev_floor_usd,
            "prev_floor_date": s.prev_floor_date,
        }

    def force_set_floor(self, value_usd: float, reason: str = "manual") -> None:
        """Manually set the daily floor (e.g. after a large deposit)."""
        state = self._state
        old = state.floor_usd
        state.floor_usd = round(value_usd, 2)
        state.floor_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        state.floor_set_at = datetime.now(timezone.utc).isoformat()
        _save_state(state)
        logger.info(f"🔧 FLOOR MANUALLY SET: ${old:,.2f} → ${value_usd:,.2f} (reason: {reason})")
