"""
Adaptive Mode Controller — Capital Recovery State Machine

Automatically switches between NORMAL (gem-first) and RECOVERY (swing-first)
modes based on portfolio performance.

NORMAL:   Gems every cycle, swing every 3rd cycle
RECOVERY: Swing every cycle, gems every 3rd cycle, tighter exits

Triggers:
  NORMAL → RECOVERY:
    - Drawdown from high-water mark ≥ 5%
    - Zero profitable gem trades in last 4 hours
    - Capital below critical threshold ($250)

  RECOVERY → NORMAL:
    - Capital restored to 95% of high-water mark
    - 3 consecutive profitable swing trades
"""

import json
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── State persistence ─────────────────────────────────────────────────────────
_STATE_FILE = Path(os.environ.get(
    "ADAPTIVE_MODE_STATE",
    os.path.join(os.path.dirname(__file__), "..", "output", "adaptive_mode_state.json"),
))


class BotMode(str, Enum):
    NORMAL = "normal"
    RECOVERY = "recovery"


@dataclass
class AdaptiveModeState:
    """Persistent state for the adaptive mode controller."""
    mode: str = BotMode.NORMAL.value
    high_water_mark_usd: float = 0.0          # Peak portfolio value seen
    current_capital_usd: float = 0.0           # Latest portfolio snapshot
    drawdown_pct: float = 0.0                  # Current drawdown from HWM

    # Gem performance tracking
    last_profitable_gem_ts: float = 0.0        # Unix timestamp of last profitable gem trade
    gem_trades_last_window: int = 0            # Gem trades in current window
    gem_wins_last_window: int = 0              # Profitable gem trades in current window

    # Swing performance tracking
    consecutive_swing_wins: int = 0            # Consecutive profitable swing trades
    swing_trades_total: int = 0
    swing_wins_total: int = 0

    # Mode transition history
    mode_entered_at: float = 0.0               # When current mode started
    recovery_entries: int = 0                  # How many times we've entered recovery
    last_mode_change: str = ""                 # ISO timestamp of last switch

    # Cycle control
    swing_frequency: int = 3                   # Run swing every N cycles (1 = every cycle)
    gem_frequency: int = 1                     # Run gems every N cycles (1 = every cycle)
    max_swing_entries_per_cycle: int = 3        # Max swing entries per cycle
    swing_position_cap_usd: float = 100.0      # Position cap for swing trades


# ── Thresholds ────────────────────────────────────────────────────────────────
DRAWDOWN_TRIGGER_PCT = 5.0          # Enter recovery at 5% drawdown
CAPITAL_CRITICAL_USD = 250.0        # Enter recovery if capital drops below this
GEM_DROUGHT_HOURS = 4.0             # Enter recovery after 4h with no gem wins
RECOVERY_EXIT_PCT = 95.0            # Exit recovery when capital hits 95% of HWM
CONSECUTIVE_SWING_WINS_EXIT = 3     # Exit recovery after 3 swing wins in a row

# Recovery mode overrides
RECOVERY_SWING_FREQUENCY = 1       # Swing every cycle in recovery
RECOVERY_GEM_FREQUENCY = 3         # Gems every 3rd cycle in recovery
RECOVERY_MAX_SWING_ENTRIES = 5     # More swing entries per cycle
RECOVERY_SWING_CAP_USD = 200.0     # Higher swing cap in recovery

# Normal mode defaults
NORMAL_SWING_FREQUENCY = 3
NORMAL_GEM_FREQUENCY = 1
NORMAL_MAX_SWING_ENTRIES = 3
NORMAL_SWING_CAP_USD = 100.0


def load_mode_state() -> AdaptiveModeState:
    """Load persisted mode state from disk."""
    try:
        if _STATE_FILE.exists():
            with open(_STATE_FILE) as f:
                data = json.load(f)
            return AdaptiveModeState(**{
                k: v for k, v in data.items()
                if k in AdaptiveModeState.__dataclass_fields__
            })
    except Exception as e:
        logger.warning(f"Failed to load adaptive mode state: {e}")
    return AdaptiveModeState()


def save_mode_state(state: AdaptiveModeState) -> None:
    """Persist mode state to disk."""
    try:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_STATE_FILE, "w") as f:
            json.dump(asdict(state), f, indent=2)
    except Exception as e:
        logger.warning(f"Failed to save adaptive mode state: {e}")


def update_capital(state: AdaptiveModeState, portfolio_value_usd: float) -> None:
    """
    Update the capital tracker with latest portfolio value.
    Call this at the start of each cycle with total portfolio value.
    """
    state.current_capital_usd = portfolio_value_usd

    # Update high-water mark
    if portfolio_value_usd > state.high_water_mark_usd:
        state.high_water_mark_usd = portfolio_value_usd
        logger.debug(f"📈 New high-water mark: ${portfolio_value_usd:.2f}")

    # Calculate drawdown
    if state.high_water_mark_usd > 0:
        state.drawdown_pct = (
            (state.high_water_mark_usd - portfolio_value_usd)
            / state.high_water_mark_usd
        ) * 100.0
    else:
        state.drawdown_pct = 0.0


def record_gem_trade(state: AdaptiveModeState, profitable: bool) -> None:
    """Record result of a gem snipe trade."""
    state.gem_trades_last_window += 1
    if profitable:
        state.gem_wins_last_window += 1
        state.last_profitable_gem_ts = time.time()


def record_swing_trade(state: AdaptiveModeState, profitable: bool) -> None:
    """Record result of a swing trade."""
    state.swing_trades_total += 1
    if profitable:
        state.swing_wins_total += 1
        state.consecutive_swing_wins += 1
    else:
        state.consecutive_swing_wins = 0


def evaluate_mode(state: AdaptiveModeState) -> BotMode:
    """
    Core decision engine: should we be in NORMAL or RECOVERY mode?

    Returns the recommended mode. Does NOT apply it — call apply_mode() after.
    """
    current = BotMode(state.mode)
    now = time.time()

    if current == BotMode.NORMAL:
        # ── Check NORMAL → RECOVERY triggers ─────────────────────────────
        reasons = []

        # 1. Drawdown trigger
        if state.drawdown_pct >= DRAWDOWN_TRIGGER_PCT:
            reasons.append(
                f"drawdown {state.drawdown_pct:.1f}% ≥ {DRAWDOWN_TRIGGER_PCT}%"
            )

        # 2. Capital critical
        if 0 < state.current_capital_usd < CAPITAL_CRITICAL_USD:
            reasons.append(
                f"capital ${state.current_capital_usd:.0f} < ${CAPITAL_CRITICAL_USD:.0f}"
            )

        # 3. Gem drought — no profitable gem in 4 hours
        if state.last_profitable_gem_ts > 0:
            hours_since_win = (now - state.last_profitable_gem_ts) / 3600
            if hours_since_win >= GEM_DROUGHT_HOURS and state.gem_trades_last_window >= 2:
                reasons.append(
                    f"gem drought: {hours_since_win:.1f}h since last win "
                    f"({state.gem_wins_last_window}/{state.gem_trades_last_window} win rate)"
                )

        if reasons:
            logger.warning(
                f"🔴 RECOVERY MODE TRIGGERED — {' | '.join(reasons)}"
            )
            return BotMode.RECOVERY

    elif current == BotMode.RECOVERY:
        # ── Check RECOVERY → NORMAL triggers ─────────────────────────────
        reasons = []

        # 1. Capital restored
        if state.high_water_mark_usd > 0:
            recovery_target = state.high_water_mark_usd * (RECOVERY_EXIT_PCT / 100.0)
            if state.current_capital_usd >= recovery_target:
                reasons.append(
                    f"capital ${state.current_capital_usd:.0f} ≥ "
                    f"${recovery_target:.0f} (95% of HWM)"
                )

        # 2. Consecutive swing wins
        if state.consecutive_swing_wins >= CONSECUTIVE_SWING_WINS_EXIT:
            reasons.append(
                f"{state.consecutive_swing_wins} consecutive swing wins"
            )

        if reasons:
            logger.info(
                f"🟢 NORMAL MODE RESTORED — {' | '.join(reasons)}"
            )
            return BotMode.NORMAL

    return current


def apply_mode(state: AdaptiveModeState, new_mode: BotMode) -> bool:
    """
    Apply the mode transition. Returns True if mode actually changed.
    Updates all cycle frequencies and position caps.
    """
    old_mode = BotMode(state.mode)
    if new_mode == old_mode:
        return False

    state.mode = new_mode.value
    state.mode_entered_at = time.time()
    state.last_mode_change = datetime.now(timezone.utc).isoformat()

    if new_mode == BotMode.RECOVERY:
        state.recovery_entries += 1
        state.swing_frequency = RECOVERY_SWING_FREQUENCY
        state.gem_frequency = RECOVERY_GEM_FREQUENCY
        state.max_swing_entries_per_cycle = RECOVERY_MAX_SWING_ENTRIES
        state.swing_position_cap_usd = RECOVERY_SWING_CAP_USD

        # Reset gem tracking for fresh window in recovery
        state.gem_trades_last_window = 0
        state.gem_wins_last_window = 0

        logger.warning(
            f"⚡ MODE SWITCH: {old_mode.value.upper()} → RECOVERY | "
            f"Swing every cycle, gems every 3rd | "
            f"Swing cap ${state.swing_position_cap_usd:.0f} | "
            f"Recovery entry #{state.recovery_entries}"
        )

    elif new_mode == BotMode.NORMAL:
        state.swing_frequency = NORMAL_SWING_FREQUENCY
        state.gem_frequency = NORMAL_GEM_FREQUENCY
        state.max_swing_entries_per_cycle = NORMAL_MAX_SWING_ENTRIES
        state.swing_position_cap_usd = NORMAL_SWING_CAP_USD

        # Reset swing consecutive counter
        state.consecutive_swing_wins = 0

        logger.info(
            f"✅ MODE SWITCH: RECOVERY → NORMAL | "
            f"Gems every cycle, swing every 3rd | "
            f"Capital: ${state.current_capital_usd:.0f}"
        )

    save_mode_state(state)
    return True


def should_run_gems(state: AdaptiveModeState, cycle: int) -> bool:
    """Should the gem scanner run this cycle?"""
    return cycle % state.gem_frequency == 0


def should_run_swing(state: AdaptiveModeState, cycle: int) -> bool:
    """Should the swing scanner run this cycle?"""
    return cycle % state.swing_frequency == 0


def get_mode_status(state: AdaptiveModeState) -> dict:
    """Return a summary dict for logging/dashboard."""
    return {
        "mode": state.mode,
        "capital_usd": round(state.current_capital_usd, 2),
        "hwm_usd": round(state.high_water_mark_usd, 2),
        "drawdown_pct": round(state.drawdown_pct, 2),
        "gem_frequency": state.gem_frequency,
        "swing_frequency": state.swing_frequency,
        "swing_cap_usd": state.swing_position_cap_usd,
        "recovery_entries": state.recovery_entries,
        "consecutive_swing_wins": state.consecutive_swing_wins,
    }


def log_mode_banner(state: AdaptiveModeState) -> None:
    """Log a visible mode banner at the start of each cycle."""
    mode = BotMode(state.mode)
    if mode == BotMode.RECOVERY:
        logger.warning(
            f"🔴 RECOVERY MODE | Capital: ${state.current_capital_usd:.0f} | "
            f"HWM: ${state.high_water_mark_usd:.0f} | "
            f"Drawdown: {state.drawdown_pct:.1f}% | "
            f"Swing wins: {state.consecutive_swing_wins}"
        )
    else:
        logger.info(
            f"🟢 NORMAL MODE | Capital: ${state.current_capital_usd:.0f} | "
            f"HWM: ${state.high_water_mark_usd:.0f}"
        )
