"""
core/capital_compounder.py — ☘️ Shamrock Trading Bot
Automated Capital Compounding Loop

Tracks cumulative PnL milestones and automatically scales position sizes,
triggers profit sweeps to Wallet C (cold storage), and manages the
house money pool to compound $5k → 7-8 figures.

Compounding Strategy:
  Phase 1: $0–$10k     → Conservative (5% per trade, max $500)
  Phase 2: $10k–$50k   → Growth (8% per trade, max $2k)
  Phase 3: $50k–$200k  → Aggressive (12% per trade, max $10k)
  Phase 4: $200k–$1M   → Predator (15% per trade, max $50k)
  Phase 5: $1M+        → Apex (20% per trade, max $200k)

Profit Sweep Rules (to Wallet C cold storage):
  - Sweep 25% of profits when daily PnL > $500
  - Sweep 35% of profits when daily PnL > $2,000
  - Sweep 50% of profits when crossing a milestone threshold
  - Always keep minimum $500 in Primary for gas + next trades

Capital Loop:
  1. Trade fires → position_monitor records PnL
  2. capital_compounder.record_trade_pnl() called
  3. Updates cumulative PnL, checks milestone
  4. If milestone crossed → scale up position sizes + trigger sweep
  5. House money pool refilled from profits
  6. Next trade uses scaled-up sizes → faster compounding
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────
try:
    from config import settings
    _SETTINGS_AVAILABLE = True
except Exception:
    _SETTINGS_AVAILABLE = False

_DATA_DIR = Path(os.getenv("DASHBOARD_STATE_DIR", "data/dashboard"))
COMPOUNDER_STATE_FILE = Path("output/capital_compounder_state.json")
COMPOUNDER_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

# ─────────────────────────────────────────────────────────────────────────────
# Compounding Phases
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class CompoundPhase:
    name: str
    min_capital_usd: float
    max_capital_usd: float
    base_position_pct: float    # % of total capital per trade
    max_position_usd: float     # Hard cap per trade
    offensive_max_usd: float    # Offensive guardrail max
    sweep_pct: float            # % of daily profits to sweep to Wallet C
    description: str


COMPOUND_PHASES = [
    CompoundPhase(
        name="Seed",
        min_capital_usd=0,
        max_capital_usd=10_000,
        base_position_pct=5.0,
        max_position_usd=500,
        offensive_max_usd=1_000,
        sweep_pct=20.0,
        description="Building the base — protect capital, compound steadily",
    ),
    CompoundPhase(
        name="Growth",
        min_capital_usd=10_000,
        max_capital_usd=50_000,
        base_position_pct=8.0,
        max_position_usd=2_000,
        offensive_max_usd=5_000,
        sweep_pct=25.0,
        description="Scaling up — bigger positions, start sweeping profits",
    ),
    CompoundPhase(
        name="Aggressive",
        min_capital_usd=50_000,
        max_capital_usd=200_000,
        base_position_pct=12.0,
        max_position_usd=10_000,
        offensive_max_usd=25_000,
        sweep_pct=30.0,
        description="Full aggression — max Moralis signals, whale-size entries",
    ),
    CompoundPhase(
        name="Predator",
        min_capital_usd=200_000,
        max_capital_usd=1_000_000,
        base_position_pct=15.0,
        max_position_usd=50_000,
        offensive_max_usd=100_000,
        sweep_pct=35.0,
        description="Predator mode — targeting 10x gems with serious capital",
    ),
    CompoundPhase(
        name="Apex",
        min_capital_usd=1_000_000,
        max_capital_usd=float("inf"),
        base_position_pct=20.0,
        max_position_usd=200_000,
        offensive_max_usd=500_000,
        sweep_pct=40.0,
        description="Apex predator — 7-8 figure capital, institutional-scale moves",
    ),
]

# Milestone thresholds for special sweep + notification events
MILESTONES_USD = [
    10_000, 25_000, 50_000, 100_000, 250_000,
    500_000, 1_000_000, 2_500_000, 5_000_000, 10_000_000,
]

# Minimum capital to keep in Primary wallet for gas + trades
MIN_PRIMARY_RESERVE_USD = float(os.getenv("MIN_PRIMARY_RESERVE_USD", "500"))

# Daily sweep thresholds
DAILY_SWEEP_THRESHOLD_1_USD = float(os.getenv("DAILY_SWEEP_THRESHOLD_1_USD", "500"))
DAILY_SWEEP_THRESHOLD_2_USD = float(os.getenv("DAILY_SWEEP_THRESHOLD_2_USD", "2000"))


# ─────────────────────────────────────────────────────────────────────────────
# State
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class CompoundState:
    """Persistent compounding state."""
    # Capital tracking
    starting_capital_usd: float = 5_000.0
    current_capital_usd: float = 5_000.0
    peak_capital_usd: float = 5_000.0
    total_realized_pnl_usd: float = 0.0
    total_swept_to_cold_usd: float = 0.0

    # Phase tracking
    current_phase_name: str = "Seed"
    phase_entered_at: str = ""
    phase_entry_capital: float = 5_000.0

    # Milestone tracking
    milestones_hit: list[float] = field(default_factory=list)
    last_milestone_usd: float = 0.0

    # Daily tracking
    daily_pnl_usd: float = 0.0
    daily_pnl_date: str = ""
    daily_sweeps_usd: float = 0.0
    daily_trades: int = 0
    daily_wins: int = 0

    # Sweep log
    sweep_log: list[dict] = field(default_factory=list)

    # Timestamps
    created_at: str = ""
    last_updated: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "CompoundState":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


def _today_utc() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def load_compound_state() -> CompoundState:
    """Load compounding state from disk."""
    if COMPOUNDER_STATE_FILE.exists():
        try:
            with open(COMPOUNDER_STATE_FILE) as f:
                data = json.load(f)
            state = CompoundState.from_dict(data)
            # Reset daily stats on new day
            if state.daily_pnl_date != _today_utc():
                state.daily_pnl_usd = 0.0
                state.daily_pnl_date = _today_utc()
                state.daily_sweeps_usd = 0.0
                state.daily_trades = 0
                state.daily_wins = 0
            return state
        except Exception as e:
            logger.warning(f"CompoundState: Could not load state: {e}")

    now = datetime.now(timezone.utc).isoformat()
    return CompoundState(
        created_at=now,
        last_updated=now,
        daily_pnl_date=_today_utc(),
        phase_entered_at=now,
    )


def save_compound_state(state: CompoundState) -> None:
    """Persist compounding state."""
    state.last_updated = datetime.now(timezone.utc).isoformat()
    try:
        tmp = COMPOUNDER_STATE_FILE.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(state.to_dict(), f, indent=2)
        tmp.replace(COMPOUNDER_STATE_FILE)
    except Exception as e:
        logger.error(f"CompoundState: Could not save: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Phase Management
# ─────────────────────────────────────────────────────────────────────────────
def get_current_phase(capital_usd: float) -> CompoundPhase:
    """Return the compounding phase for the given capital level."""
    for phase in reversed(COMPOUND_PHASES):
        if capital_usd >= phase.min_capital_usd:
            return phase
    return COMPOUND_PHASES[0]


def _check_phase_transition(state: CompoundState) -> Optional[str]:
    """
    Check if we've crossed into a new compounding phase.
    Returns phase name if transitioned, else None.
    """
    new_phase = get_current_phase(state.current_capital_usd)
    if new_phase.name != state.current_phase_name:
        old_phase = state.current_phase_name
        state.current_phase_name = new_phase.name
        state.phase_entered_at = datetime.now(timezone.utc).isoformat()
        state.phase_entry_capital = state.current_capital_usd
        logger.info(
            f"🚀 COMPOUND PHASE TRANSITION: {old_phase} → {new_phase.name} "
            f"(capital=${state.current_capital_usd:,.0f}) | "
            f"New max position: ${new_phase.max_position_usd:,.0f}"
        )
        return new_phase.name
    return None


def _check_milestones(state: CompoundState) -> list[float]:
    """Check if any new capital milestones have been crossed."""
    new_milestones = []
    for milestone in MILESTONES_USD:
        if (milestone not in state.milestones_hit and
                state.current_capital_usd >= milestone):
            state.milestones_hit.append(milestone)
            state.last_milestone_usd = milestone
            new_milestones.append(milestone)
            logger.info(
                f"🏆 MILESTONE HIT: ${milestone:,.0f}! "
                f"Total PnL: ${state.total_realized_pnl_usd:,.0f} | "
                f"Started at: ${state.starting_capital_usd:,.0f}"
            )
    return new_milestones


# ─────────────────────────────────────────────────────────────────────────────
# Profit Sweep Logic
# ─────────────────────────────────────────────────────────────────────────────
def calculate_sweep_amount(state: CompoundState, pnl_usd: float) -> float:
    """
    Calculate how much of a profit to sweep to Wallet C cold storage.
    Returns USD amount to sweep (0 if no sweep needed).
    """
    if pnl_usd <= 0:
        return 0.0

    phase = get_current_phase(state.current_capital_usd)

    # Milestone crossing → larger sweep
    new_milestones = [m for m in MILESTONES_USD
                      if m not in state.milestones_hit
                      and state.current_capital_usd + pnl_usd >= m]
    if new_milestones:
        # Sweep 50% on milestone crossing
        return round(pnl_usd * 0.50, 2)

    # Daily PnL thresholds
    if state.daily_pnl_usd >= DAILY_SWEEP_THRESHOLD_2_USD:
        sweep_pct = phase.sweep_pct + 10  # Extra sweep at high daily PnL
    elif state.daily_pnl_usd >= DAILY_SWEEP_THRESHOLD_1_USD:
        sweep_pct = phase.sweep_pct
    else:
        sweep_pct = 0.0  # Below threshold — no sweep yet

    return round(pnl_usd * (sweep_pct / 100.0), 2)


def record_sweep(state: CompoundState, amount_usd: float, reason: str) -> None:
    """Record a profit sweep to cold storage."""
    state.total_swept_to_cold_usd += amount_usd
    state.daily_sweeps_usd += amount_usd
    state.sweep_log.append({
        "amount_usd": round(amount_usd, 2),
        "reason": reason,
        "capital_at_sweep": round(state.current_capital_usd, 2),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    # Keep last 100 sweep records
    state.sweep_log = state.sweep_log[-100:]
    logger.info(
        f"💰 PROFIT SWEEP: ${amount_usd:.2f} → Wallet C | "
        f"Reason: {reason} | "
        f"Total swept: ${state.total_swept_to_cold_usd:,.2f}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Dynamic Settings Update
# ─────────────────────────────────────────────────────────────────────────────
def apply_phase_to_settings(phase: CompoundPhase) -> None:
    """
    Dynamically update bot settings to match the current compound phase.
    This scales up position sizes as capital grows.
    """
    if not _SETTINGS_AVAILABLE:
        return
    try:
        # Update offensive guardrail max position
        settings.OFFENSIVE_MAX_POSITION_USD = phase.offensive_max_usd
        # Update house money max pool (scales with phase)
        settings.HOUSE_MONEY_MAX_POOL_USD = phase.max_position_usd * 5
        # Update house money max deploy per trade
        settings.HOUSE_MONEY_MAX_POSITION_MULT = 2.0 if phase.name in ("Predator", "Apex") else 1.5
        logger.info(
            f"⚙️  CompoundPhase settings applied: {phase.name} | "
            f"max_position=${phase.max_position_usd:,.0f} | "
            f"offensive_max=${phase.offensive_max_usd:,.0f}"
        )
    except Exception as e:
        logger.debug(f"Could not apply phase settings: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Main API — called by position_monitor.py after each trade close
# ─────────────────────────────────────────────────────────────────────────────
def record_trade_pnl(
    pnl_usd: float,
    token_symbol: str = "",
    wallet: str = "primary",
    trade_id: str = "",
) -> dict:
    """
    Record a completed trade's PnL and run the compounding loop.

    Called by position_monitor.py after every position close.
    Returns a dict with:
      - phase: current compound phase name
      - phase_changed: bool
      - milestones_hit: list of new milestones
      - sweep_amount_usd: amount to sweep to cold storage
      - new_max_position_usd: updated position size cap
    """
    state = load_compound_state()

    # Update capital
    state.current_capital_usd += pnl_usd
    state.current_capital_usd = max(0, state.current_capital_usd)
    state.total_realized_pnl_usd += pnl_usd
    state.peak_capital_usd = max(state.peak_capital_usd, state.current_capital_usd)

    # Daily tracking
    if state.daily_pnl_date != _today_utc():
        state.daily_pnl_usd = 0.0
        state.daily_pnl_date = _today_utc()
        state.daily_sweeps_usd = 0.0
        state.daily_trades = 0
        state.daily_wins = 0

    state.daily_pnl_usd += pnl_usd
    state.daily_trades += 1
    if pnl_usd > 0:
        state.daily_wins += 1

    # Calculate sweep
    sweep_amount = calculate_sweep_amount(state, pnl_usd)

    # Check milestones (before applying sweep)
    new_milestones = _check_milestones(state)

    # Check phase transition
    phase_changed = _check_phase_transition(state)
    current_phase = get_current_phase(state.current_capital_usd)

    # Apply sweep
    if sweep_amount > 0:
        reason = (
            f"milestone_${new_milestones[0]:,.0f}" if new_milestones
            else f"daily_pnl_${state.daily_pnl_usd:.0f}"
        )
        record_sweep(state, sweep_amount, reason)

    # Apply new phase settings to bot
    if phase_changed:
        apply_phase_to_settings(current_phase)

    # Save state
    save_compound_state(state)

    result = {
        "phase": current_phase.name,
        "phase_changed": phase_changed is not None,
        "new_phase": phase_changed,
        "milestones_hit": new_milestones,
        "sweep_amount_usd": sweep_amount,
        "current_capital_usd": round(state.current_capital_usd, 2),
        "total_pnl_usd": round(state.total_realized_pnl_usd, 2),
        "new_max_position_usd": current_phase.max_position_usd,
        "new_offensive_max_usd": current_phase.offensive_max_usd,
        "daily_pnl_usd": round(state.daily_pnl_usd, 2),
        "daily_win_rate": round(state.daily_wins / max(state.daily_trades, 1) * 100, 1),
    }

    if new_milestones or phase_changed:
        logger.info(
            f"🎯 COMPOUND LOOP: ${pnl_usd:+.2f} trade | "
            f"Capital: ${state.current_capital_usd:,.0f} | "
            f"Phase: {current_phase.name} | "
            f"Milestones: {new_milestones} | "
            f"Sweep: ${sweep_amount:.2f}"
        )

    return result


def get_position_size_for_capital(capital_usd: float, gem_score: float = 75.0) -> float:
    """
    Return the recommended position size in USD for the given capital level.
    Used by wallet_router.py to dynamically scale trade sizes.

    gem_score: 0-100, higher = larger position within phase limits
    """
    phase = get_current_phase(capital_usd)
    base = capital_usd * (phase.base_position_pct / 100.0)
    # Scale within phase limits based on gem score
    score_mult = 0.5 + (gem_score / 100.0) * 0.5  # 0.5x to 1.0x based on score
    position = base * score_mult
    return round(min(position, phase.max_position_usd), 2)


def get_compound_summary() -> dict:
    """Return a full summary for the dashboard."""
    state = load_compound_state()
    phase = get_current_phase(state.current_capital_usd)
    next_milestone = next(
        (m for m in MILESTONES_USD if m > state.current_capital_usd), None
    )
    progress_to_next = 0.0
    if next_milestone:
        prev_milestone = state.last_milestone_usd or state.starting_capital_usd
        if next_milestone > prev_milestone:
            progress_to_next = min(100.0, (
                (state.current_capital_usd - prev_milestone) /
                (next_milestone - prev_milestone) * 100
            ))

    return {
        "starting_capital_usd": state.starting_capital_usd,
        "current_capital_usd": round(state.current_capital_usd, 2),
        "peak_capital_usd": round(state.peak_capital_usd, 2),
        "total_realized_pnl_usd": round(state.total_realized_pnl_usd, 2),
        "total_return_pct": round(
            (state.current_capital_usd - state.starting_capital_usd) /
            max(state.starting_capital_usd, 1) * 100, 1
        ),
        "total_swept_to_cold_usd": round(state.total_swept_to_cold_usd, 2),
        "current_phase": phase.name,
        "phase_description": phase.description,
        "current_max_position_usd": phase.max_position_usd,
        "current_offensive_max_usd": phase.offensive_max_usd,
        "current_base_position_pct": phase.base_position_pct,
        "milestones_hit": state.milestones_hit,
        "next_milestone_usd": next_milestone,
        "progress_to_next_milestone_pct": round(progress_to_next, 1),
        "daily_pnl_usd": round(state.daily_pnl_usd, 2),
        "daily_win_rate_pct": round(
            state.daily_wins / max(state.daily_trades, 1) * 100, 1
        ),
        "daily_trades": state.daily_trades,
        "sweep_log": state.sweep_log[-10:],  # Last 10 sweeps
        "last_updated": state.last_updated,
    }


def get_compound_state() -> CompoundState:
    """Public accessor for the compound state."""
    return load_compound_state()
