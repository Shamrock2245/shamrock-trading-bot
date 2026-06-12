"""
core/daily_goal_engine.py — Dynamic Daily Profit Goal Engine

Tracks daily PnL across ALL strategies (gem sniping + arbitrage + scalping)
and dynamically escalates the profit target as consistency is proven.

Target Escalation Logic:
  ┌─────────────────────────────────────────────────────────────────────┐
  │  Tier 0  │ $500/day   │ Starting floor — must hit 5 days in a row  │
  │  Tier 1  │ $750/day   │ After 5 consecutive $500+ days             │
  │  Tier 2  │ $1,000/day │ After 5 consecutive $750+ days             │
  │  Tier 3  │ $1,500/day │ After 5 consecutive $1,000+ days           │
  │  Tier 4  │ $2,000/day │ After 5 consecutive $1,500+ days           │
  │  Tier 5  │ $3,000/day │ After 7 consecutive $2,000+ days           │
  │  Tier 6  │ $5,000/day │ After 7 consecutive $3,000+ days           │
  │  Tier 7  │ UNLIMITED  │ After 7 consecutive $5,000+ days — max mode│
  └─────────────────────────────────────────────────────────────────────┘

  - Tier drops back one level after 3 consecutive misses
  - Never drops below Tier 0 ($500/day floor)
  - Tier 7 ("UNLIMITED") means: deploy max capital, no goal ceiling

Strategy Mix Shifting:
  When daily progress < 30% of goal by 6 PM UTC:
    → Increase arb scan frequency (every 5s instead of 30s)
    → Lower arb min spread threshold (0.5% instead of 0.8%)
    → Activate "catch-up mode" in gem scanner (lower score floor by 2pts)

  When daily progress > 100% of goal:
    → Enter "protect mode" — reduce position sizes by 30%
    → Raise arb min spread threshold (1.5% instead of 0.8%)
    → Tighten trailing stops on open positions

  When daily progress > 150% of goal:
    → Enter "bank it mode" — close weakest positions, sweep profits to USDC

Integration:
  from core.daily_goal_engine import get_daily_goal_engine
  engine = get_daily_goal_engine()
  engine.record_profit(profit_usd, source="arb_cross_dex")
  mode = engine.get_strategy_mode()   # "normal", "catch_up", "protect", "bank_it"
  target = engine.current_target_usd  # Today's goal
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

GOAL_STATE_FILE = Path(
    getattr(settings, "DAILY_GOAL_STATE_FILE", "output/daily_goal_state.json")
)
GOAL_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

# Escalation tiers: (target_usd, days_needed_to_advance, label)
GOAL_TIERS: list[tuple[float, int, str]] = [
    (500.0,    5, "Tier 0 — Foundation"),
    (750.0,    5, "Tier 1 — Growing"),
    (1_000.0,  5, "Tier 2 — Consistent"),
    (1_500.0,  5, "Tier 3 — Scaling"),
    (2_000.0,  5, "Tier 4 — Serious"),
    (3_000.0,  7, "Tier 5 — Elite"),
    (5_000.0,  7, "Tier 6 — Institutional"),
    (0.0,      0, "Tier 7 — UNLIMITED"),  # 0 = no ceiling
]

TIER_DROP_AFTER_MISSES: int = 3          # Consecutive misses before dropping a tier
CATCH_UP_THRESHOLD_PCT: float = 30.0     # % of goal by 6 PM UTC to trigger catch-up
PROTECT_MODE_THRESHOLD_PCT: float = 100.0
BANK_IT_THRESHOLD_PCT: float = 150.0
CATCH_UP_HOUR_UTC: int = 18              # 6 PM UTC — catch-up trigger time

# ─────────────────────────────────────────────────────────────────────────────
# State
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DailyGoalState:
    """Persistent state for the daily goal engine. Survives restarts."""

    # Current tier
    current_tier: int = 0
    current_target_usd: float = 500.0

    # Streak tracking
    consecutive_hits: int = 0           # Days in a row hitting the current tier target
    consecutive_misses: int = 0         # Days in a row missing the current tier target
    all_time_best_day_usd: float = 0.0
    all_time_total_usd: float = 0.0

    # Today's progress
    today_date: str = ""                # "2026-05-29"
    today_profit_usd: float = 0.0
    today_trade_count: int = 0
    today_arb_profit_usd: float = 0.0
    today_gem_profit_usd: float = 0.0
    today_scalp_profit_usd: float = 0.0
    goal_locked_today: bool = False

    # Historical daily records (last 30 days)
    daily_history: list[dict] = field(default_factory=list)  # [{date, profit, target, hit}]

    # Strategy mode
    strategy_mode: str = "normal"       # "normal", "catch_up", "protect", "bank_it"
    mode_activated_at: str = ""

    # Tier history
    tier_history: list[dict] = field(default_factory=list)  # [{date, from_tier, to_tier, reason}]


# ─────────────────────────────────────────────────────────────────────────────
# Engine
# ─────────────────────────────────────────────────────────────────────────────

class DailyGoalEngine:
    """
    Tracks daily profit across all strategies and dynamically escalates
    the profit target as consistency is proven.
    """

    def __init__(self):
        self._state = self._load_state()
        self._reset_day_if_needed()

    # ─────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────

    def record_profit(
        self,
        profit_usd: float,
        source: str = "unknown",
    ) -> None:
        """
        Record a profit event from any strategy.
        source: "arb_cross_dex", "arb_triangular", "arb_cross_chain",
                "gem_snipe", "gem_swing", "scalp", "btc_rotation"
        """
        self._reset_day_if_needed()
        s = self._state

        s.today_profit_usd += profit_usd
        s.today_trade_count += 1
        s.all_time_total_usd += profit_usd

        if profit_usd > 0:
            if s.today_profit_usd > s.all_time_best_day_usd:
                s.all_time_best_day_usd = s.today_profit_usd

        # Bucket by source
        if "arb" in source:
            s.today_arb_profit_usd += profit_usd
        elif "gem" in source or "snipe" in source or "swing" in source:
            s.today_gem_profit_usd += profit_usd
        elif "scalp" in source:
            s.today_scalp_profit_usd += profit_usd

        # Update strategy mode
        self._update_strategy_mode()
        self._save_state()

        logger.info(
            f"📊 DAILY GOAL: +${profit_usd:.2f} from {source} | "
            f"today=${s.today_profit_usd:.2f} / target=${s.current_target_usd:.0f} "
            f"({self.progress_pct:.1f}%) | mode={s.strategy_mode} | "
            f"tier={s.current_tier} ({GOAL_TIERS[s.current_tier][2]})"
        )

        # ── Paper-to-Live auto-promotion check ──────────────────────────
        try:
            from core.paper_to_live_promoter import check_and_promote
            check_and_promote(today_profit_usd=s.today_profit_usd)
        except Exception as _promo_err:
            logger.debug(f"Promotion check error: {_promo_err}")

    @property
    def current_target_usd(self) -> float:
        """Today's profit target in USD."""
        return self._state.current_target_usd

    @property
    def today_profit_usd(self) -> float:
        self._reset_day_if_needed()
        return self._state.today_profit_usd

    @property
    def progress_pct(self) -> float:
        """How far through today's goal we are (0–200%+)."""
        target = self._state.current_target_usd
        if target <= 0:
            return 100.0  # Tier 7 unlimited
        return self._state.today_profit_usd / target * 100

    @property
    def remaining_usd(self) -> float:
        """How much more profit needed to hit today's goal."""
        target = self._state.current_target_usd
        if target <= 0:
            return 0.0
        return max(0.0, target - self._state.today_profit_usd)

    @property
    def current_tier(self) -> int:
        return self._state.current_tier

    @property
    def strategy_mode(self) -> str:
        return self._state.strategy_mode

    def get_strategy_mode(self) -> str:
        """
        Returns current strategy mode for the scan loop to act on.
        Modes:
          "normal"    — standard operation
          "catch_up"  — behind pace, lower thresholds, increase arb frequency
          "protect"   — goal hit, reduce risk
          "bank_it"   — 150%+ of goal, sweep profits, tighten everything
        """
        self._update_strategy_mode()
        return self._state.strategy_mode

    def get_arb_config_overrides(self) -> dict:
        """
        Returns arb scanner config overrides based on current strategy mode.
        These are injected into arb_scanner at runtime.
        """
        mode = self.get_strategy_mode()
        tier = self._state.current_tier

        # Base config scales with tier (bigger positions as we scale up)
        tier_position_multiplier = 1.0 + (tier * 0.25)  # +25% per tier

        if mode == "catch_up":
            return {
                "ARB_MIN_SPREAD_PCT": 0.5,           # Lower threshold
                "ARB_TRIANGULAR_MIN_PROFIT_PCT": 0.8,
                "ARB_CROSS_CHAIN_MIN_SPREAD_PCT": 2.0,
                "ARB_MAX_POSITION_USD": 3000.0 * tier_position_multiplier,
                "ARB_MIN_PROFIT_USD": 5.0,           # Lower bar
                "scan_interval_seconds": 5,           # Scan more often
            }
        elif mode == "protect":
            return {
                "ARB_MIN_SPREAD_PCT": 1.2,           # Higher threshold (better opps only)
                "ARB_TRIANGULAR_MIN_PROFIT_PCT": 1.8,
                "ARB_CROSS_CHAIN_MIN_SPREAD_PCT": 3.5,
                "ARB_MAX_POSITION_USD": 1500.0 * tier_position_multiplier,
                "ARB_MIN_PROFIT_USD": 12.0,
                "scan_interval_seconds": 20,
            }
        elif mode == "bank_it":
            return {
                "ARB_MIN_SPREAD_PCT": 2.0,           # Only the best opps
                "ARB_TRIANGULAR_MIN_PROFIT_PCT": 2.5,
                "ARB_CROSS_CHAIN_MIN_SPREAD_PCT": 4.0,
                "ARB_MAX_POSITION_USD": 1000.0 * tier_position_multiplier,
                "ARB_MIN_PROFIT_USD": 20.0,
                "scan_interval_seconds": 30,
            }
        elif mode == "parabolic":
            return {
                "ARB_MIN_SPREAD_PCT": 0.4,           # Very aggressive threshold
                "ARB_TRIANGULAR_MIN_PROFIT_PCT": 0.6,
                "ARB_CROSS_CHAIN_MIN_SPREAD_PCT": 1.5,
                "ARB_MAX_POSITION_USD": 8000.0 * tier_position_multiplier,
                "ARB_MIN_PROFIT_USD": 5.0,
                "scan_interval_seconds": 5,
            }
        else:  # normal
            return {
                "ARB_MIN_SPREAD_PCT": 0.8,
                "ARB_TRIANGULAR_MIN_PROFIT_PCT": 1.2,
                "ARB_CROSS_CHAIN_MIN_SPREAD_PCT": 2.5,
                "ARB_MAX_POSITION_USD": 5000.0 * tier_position_multiplier,
                "ARB_MIN_PROFIT_USD": 8.0,
                "scan_interval_seconds": 15,
            }

    def get_gem_score_override(self) -> Optional[float]:
        """
        Returns a modified MIN_GEM_SCORE for the gem scanner based on mode.
        None = use default.
        """
        mode = self.get_strategy_mode()
        base_score = getattr(settings, "MIN_GEM_SCORE", 65.0)
        if mode in ("catch_up", "parabolic"):
            return max(base_score - 2.0, 58.0)   # Lower by 2pts (catch-up / parabolic)
        elif mode in ("protect", "bank_it"):
            return min(base_score + 3.0, 78.0)   # Raise by 3pts (be selective)
        return None  # Normal: use default

    def get_position_size_multiplier(self) -> float:
        """
        Returns a multiplier for position sizing based on mode and tier.
        Used by wallet_router to scale trade sizes.
        """
        mode = self.get_strategy_mode()
        tier = self._state.current_tier

        # Tier bonus: +10% per tier (reward consistency with bigger bets)
        tier_bonus = 1.0 + (tier * 0.10)

        if mode == "catch_up":
            return 1.15 * tier_bonus   # 15% bigger positions to catch up
        elif mode == "protect":
            return 0.70 * tier_bonus   # 30% smaller positions
        elif mode == "bank_it":
            return 0.50 * tier_bonus   # 50% smaller — just protecting gains
        elif mode == "parabolic":
            return 1.50 * tier_bonus   # 50% bigger positions for exponential scaling
        else:
            return 1.0 * tier_bonus    # Normal

    def close_day(self) -> dict:
        """
        Called at midnight UTC to close out the day, evaluate tier progress,
        record the daily result, and execute the Aggressive Auto-Compounding Loop.
        """
        s = self._state
        today = s.today_date
        profit = s.today_profit_usd
        target = s.current_target_usd
        hit = (target <= 0) or (profit >= target)  # Tier 7 always "hits"

        # ── Upgrade 4: Aggressive Auto-Compounding Loop ───────────────────────
        # Automatically sweep 80% of daily realized profits back into the base capital
        # PAPER_WALLET_BALANCE_USD at midnight UTC to utilize compound interest scaling.
        swept_amount = 0.0
        if profit > 0:
            swept_amount = profit * 0.80
            
            # Update settings.PAPER_WALLET_BALANCE_USD
            old_balance = getattr(settings, "PAPER_WALLET_BALANCE_USD", 1000.0)
            new_balance = old_balance + swept_amount
            setattr(settings, "PAPER_WALLET_BALANCE_USD", new_balance)
            
            # Hot-patch the .env file to persist the balance across restarts
            env_path = Path(".env")
            if env_path.exists():
                try:
                    content = env_path.read_text()
                    lines = content.splitlines()
                    updated = False
                    for i, line in enumerate(lines):
                        if line.strip().startswith("PAPER_WALLET_BALANCE_USD="):
                            lines[i] = f"PAPER_WALLET_BALANCE_USD={new_balance:.2f}"
                            updated = True
                            break
                    if not updated:
                        lines.append(f"PAPER_WALLET_BALANCE_USD={new_balance:.2f}")
                    env_path.write_text("\n".join(lines) + "\n")
                    logger.info(f"💾 Persisted compounded PAPER_WALLET_BALANCE_USD={new_balance:.2f} to .env")
                except Exception as env_err:
                    logger.error(f"Failed to persist compounded balance to .env: {env_err}")
            
            # Update capital_compounder state if available to keep systems aligned
            try:
                from core.capital_compounder import load_compound_state, save_compound_state
                compound_state = load_compound_state()
                compound_state.current_capital_usd += swept_amount
                compound_state.total_realized_pnl_usd += swept_amount
                save_compound_state(compound_state)
                logger.info(
                    f"🍀 COMPOUNDER ALIGNED: Swept ${swept_amount:.2f} into capital compounder. "
                    f"New Compounder Capital: ${compound_state.current_capital_usd:.2f}"
                )
            except Exception as comp_err:
                logger.debug(f"Could not update capital compounder state: {comp_err}")

            logger.info(
                f"🔄 MIDNIGHT AUTO-COMPOUND SWEEP: Yesterday's Profit: ${profit:.2f} | "
                f"Compounded (80%): ${swept_amount:.2f} | "
                f"Base Capital: ${old_balance:.2f} → ${new_balance:.2f} (Exponential Scaling)"
            )

        # Record daily history
        daily_record = {
            "date": today,
            "profit_usd": round(profit, 2),
            "target_usd": target,
            "hit": hit,
            "tier": s.current_tier,
            "arb_usd": round(s.today_arb_profit_usd, 2),
            "gem_usd": round(s.today_gem_profit_usd, 2),
            "scalp_usd": round(s.today_scalp_profit_usd, 2),
            "trades": s.today_trade_count,
            "mode": s.strategy_mode,
            "compounded_usd": round(swept_amount, 2),
        }
        s.daily_history.append(daily_record)
        if len(s.daily_history) > 30:
            s.daily_history = s.daily_history[-30:]

        # Update streak
        if hit:
            s.consecutive_hits += 1
            s.consecutive_misses = 0
            logger.info(
                f"🎯 DAILY GOAL HIT: ${profit:.2f} / ${target:.0f} | "
                f"streak={s.consecutive_hits} | tier={s.current_tier}"
            )
        else:
            s.consecutive_misses += 1
            s.consecutive_hits = 0
            logger.warning(
                f"⚠️ DAILY GOAL MISSED: ${profit:.2f} / ${target:.0f} | "
                f"misses={s.consecutive_misses} | tier={s.current_tier}"
            )

        # Tier escalation
        self._evaluate_tier_change(hit)

        # Save and return summary
        self._save_state()
        return daily_record

    def get_dashboard(self) -> dict:
        """Returns a full status dashboard for logging/display."""
        self._reset_day_if_needed()
        s = self._state
        tier_info = GOAL_TIERS[s.current_tier]
        next_tier = GOAL_TIERS[s.current_tier + 1] if s.current_tier < len(GOAL_TIERS) - 1 else None

        return {
            "today_date": s.today_date,
            "today_profit_usd": round(s.today_profit_usd, 2),
            "today_target_usd": s.current_target_usd,
            "progress_pct": round(self.progress_pct, 1),
            "remaining_usd": round(self.remaining_usd, 2),
            "strategy_mode": s.strategy_mode,
            "current_tier": s.current_tier,
            "tier_label": tier_info[2],
            "consecutive_hits": s.consecutive_hits,
            "consecutive_misses": s.consecutive_misses,
            "days_to_next_tier": max(0, tier_info[1] - s.consecutive_hits) if next_tier else 0,
            "next_tier_target": next_tier[0] if next_tier else None,
            "all_time_best_day_usd": round(s.all_time_best_day_usd, 2),
            "all_time_total_usd": round(s.all_time_total_usd, 2),
            "today_breakdown": {
                "arb": round(s.today_arb_profit_usd, 2),
                "gem": round(s.today_gem_profit_usd, 2),
                "scalp": round(s.today_scalp_profit_usd, 2),
            },
            "position_size_multiplier": round(self.get_position_size_multiplier(), 2),
            "gem_score_override": self.get_gem_score_override(),
        }

    # ─────────────────────────────────────────────────────────────────────
    # Internal Logic
    # ─────────────────────────────────────────────────────────────────────

    def _reset_day_if_needed(self) -> None:
        """Reset daily counters at midnight UTC."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self._state.today_date != today:
            # Close previous day if it had any activity
            if self._state.today_date and self._state.today_trade_count > 0:
                self.close_day()

            # Reset daily counters
            self._state.today_date = today
            self._state.today_profit_usd = 0.0
            self._state.today_trade_count = 0
            self._state.today_arb_profit_usd = 0.0
            self._state.today_gem_profit_usd = 0.0
            self._state.today_scalp_profit_usd = 0.0
            self._state.goal_locked_today = False
            self._state.strategy_mode = "normal"
            self._save_state()

    def _update_strategy_mode(self) -> None:
        """Determine the current strategy mode based on progress and time."""
        s = self._state
        progress = self.progress_pct
        target = s.current_target_usd

        # Paper mode: always stay in normal — nothing real to protect or bank
        if settings.MODE != "live":
            s.strategy_mode = "normal"
            return

        # Tier 7 (unlimited): always normal mode
        if target <= 0:
            s.strategy_mode = "normal"
            return

        # Bank it: 150%+ of goal
        if progress >= BANK_IT_THRESHOLD_PCT:
            s.goal_locked_today = True
            if getattr(settings, "PARABOLIC_MODE_ENABLED", False) is True:
                if s.strategy_mode != "parabolic":
                    s.strategy_mode = "parabolic"
                    s.mode_activated_at = datetime.now(timezone.utc).isoformat()
                    logger.info(f"🚀 PARABOLIC MODE: ${s.today_profit_usd:.2f} = {progress:.0f}% of goal - Pushing for max gains!")
            else:
                if s.strategy_mode != "bank_it":
                    s.strategy_mode = "bank_it"
                    s.mode_activated_at = datetime.now(timezone.utc).isoformat()
                    logger.info(f"🏦 BANK IT MODE: ${s.today_profit_usd:.2f} = {progress:.0f}% of goal")
                    try:
                        from core.profit_sweeper import execute_sweep
                        execute_sweep()
                    except Exception as e:
                        logger.error(f"❌ Failed to execute profit sweep: {e}")
            return

        # Protect / Parabolic: 100%+ of goal
        if progress >= PROTECT_MODE_THRESHOLD_PCT:
            s.goal_locked_today = True
            if getattr(settings, "PARABOLIC_MODE_ENABLED", False) is True:
                if s.strategy_mode != "parabolic":
                    s.strategy_mode = "parabolic"
                    s.mode_activated_at = datetime.now(timezone.utc).isoformat()
                    logger.info(f"🚀 PARABOLIC MODE: ${s.today_profit_usd:.2f} = {progress:.0f}% of goal - Pushing for max gains!")
            else:
                if s.strategy_mode not in ("protect", "bank_it"):
                    s.strategy_mode = "protect"
                    s.mode_activated_at = datetime.now(timezone.utc).isoformat()
                    logger.info(f"🛡️ PROTECT MODE: ${s.today_profit_usd:.2f} = {progress:.0f}% of goal")
            return

        # Dropped below 100% after locking? Protect the locked goal!
        if s.goal_locked_today and progress < PROTECT_MODE_THRESHOLD_PCT:
            if s.strategy_mode != "bank_it":
                s.strategy_mode = "bank_it"
                s.mode_activated_at = datetime.now(timezone.utc).isoformat()
                logger.warning(
                    f"🔒 GOAL LOCK ENFORCED: Dropped from parabolic peak to ${s.today_profit_usd:.2f} "
                    f"({progress:.0f}%). Locking down to preserve tier goal!"
                )
                try:
                    from core.profit_sweeper import execute_sweep
                    execute_sweep()
                except Exception as e:
                    pass
            return

        # Catch-up: behind pace after 6 PM UTC
        current_hour = datetime.now(timezone.utc).hour
        if current_hour >= CATCH_UP_HOUR_UTC and progress < CATCH_UP_THRESHOLD_PCT:
            if s.strategy_mode != "catch_up":
                s.strategy_mode = "catch_up"
                s.mode_activated_at = datetime.now(timezone.utc).isoformat()
                logger.warning(
                    f"⚡ CATCH-UP MODE: ${s.today_profit_usd:.2f} = {progress:.0f}% of goal "
                    f"at {current_hour}:00 UTC — lowering thresholds"
                )
            return

        # Normal
        if s.strategy_mode not in ("protect", "bank_it", "parabolic"):
            s.strategy_mode = "normal"

    def _evaluate_tier_change(self, today_hit: bool) -> None:
        """Evaluate whether to advance or drop a tier after closing a day."""
        s = self._state
        current_tier_config = GOAL_TIERS[s.current_tier]
        days_needed = current_tier_config[1]

        # Advance tier?
        if today_hit and s.consecutive_hits >= days_needed:
            next_tier_idx = s.current_tier + 1
            if next_tier_idx < len(GOAL_TIERS):
                old_tier = s.current_tier
                old_target = s.current_target_usd
                s.current_tier = next_tier_idx
                new_target = GOAL_TIERS[next_tier_idx][0]
                s.current_target_usd = new_target if new_target > 0 else 0.0
                s.consecutive_hits = 0  # Reset streak for new tier

                tier_record = {
                    "date": s.today_date,
                    "from_tier": old_tier,
                    "to_tier": next_tier_idx,
                    "reason": f"Advanced: {days_needed} consecutive hits at ${old_target:.0f}/day",
                    "new_target": s.current_target_usd,
                }
                s.tier_history.append(tier_record)

                logger.info(
                    f"🚀 TIER ADVANCE: {GOAL_TIERS[old_tier][2]} → {GOAL_TIERS[next_tier_idx][2]} | "
                    f"New daily target: ${s.current_target_usd:.0f}"
                    if s.current_target_usd > 0 else
                    f"🚀 TIER ADVANCE: {GOAL_TIERS[old_tier][2]} → UNLIMITED MODE 🔥"
                )

        # Drop tier?
        elif not today_hit and s.consecutive_misses >= TIER_DROP_AFTER_MISSES:
            if s.current_tier > 0:
                old_tier = s.current_tier
                s.current_tier = max(0, s.current_tier - 1)
                s.current_target_usd = GOAL_TIERS[s.current_tier][0]
                s.consecutive_misses = 0  # Reset miss streak

                tier_record = {
                    "date": s.today_date,
                    "from_tier": old_tier,
                    "to_tier": s.current_tier,
                    "reason": f"Dropped: {TIER_DROP_AFTER_MISSES} consecutive misses",
                    "new_target": s.current_target_usd,
                }
                s.tier_history.append(tier_record)

                logger.warning(
                    f"📉 TIER DROP: {GOAL_TIERS[old_tier][2]} → {GOAL_TIERS[s.current_tier][2]} | "
                    f"New daily target: ${s.current_target_usd:.0f}"
                )
            else:
                # Already at Tier 0 — just reset miss counter, never go below $500
                s.consecutive_misses = 0
                logger.warning(
                    f"⚠️ TIER 0 FLOOR: Missed ${s.current_target_usd:.0f}/day target "
                    f"{TIER_DROP_AFTER_MISSES} times — holding at $500/day floor"
                )

    # ─────────────────────────────────────────────────────────────────────
    # Persistence
    # ─────────────────────────────────────────────────────────────────────

    def _load_state(self) -> DailyGoalState:
        try:
            if GOAL_STATE_FILE.exists():
                with open(GOAL_STATE_FILE) as f:
                    data = json.load(f)
                state = DailyGoalState(**{
                    k: v for k, v in data.items()
                    if k in DailyGoalState.__dataclass_fields__
                })
                return state
        except Exception as e:
            logger.warning(f"Could not load daily goal state: {e}")
        return DailyGoalState()

    def _save_state(self) -> None:
        try:
            with open(GOAL_STATE_FILE, "w") as f:
                json.dump(asdict(self._state), f, indent=2, default=str)
        except Exception as e:
            logger.warning(f"Could not save daily goal state: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Singleton
# ─────────────────────────────────────────────────────────────────────────────

_engine: Optional[DailyGoalEngine] = None


def get_daily_goal_engine() -> DailyGoalEngine:
    global _engine
    if _engine is None:
        _engine = DailyGoalEngine()
    return _engine
