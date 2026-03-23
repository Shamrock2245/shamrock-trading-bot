"""
core/offensive_guardrails.py — Aggressive offensive guardrails to accelerate
portfolio growth toward a seven-figure goal.

Philosophy:
  Defensive guardrails protect capital. Offensive guardrails MULTIPLY it.
  When the market gives us an edge, we press it HARD. When momentum is on
  our side, we increase size. When we're on a hot streak, we compound.
  Dead money gets cut fast so capital can be redeployed into live opportunities.

Offensive Guardrails:
  1. Hot Streak Tracker     — Tracks consecutive wins; scales Kelly fraction up
  2. House Money Protocol   — Reinvests daily realized profits at higher conviction
  3. God Mode               — Full Kelly + tighter stops when up >20% in a day
  4. Tiered Pyramiding      — Adds to winners at +30%, +100%, +300% with tightening stops
  5. Fast Fail              — Cuts momentum-dead positions in 2-4h (not 12h)
  6. Express Lane Overdrive — 1.5x sizing + wider slippage for highest-conviction snipes
  7. Momentum Reentry       — Immediately re-enters a token that just hit TP1 if momentum
                              is still screaming (volume still surging, price still rising)
  8. Winner Reinvestment    — Sweeps TP1 proceeds back into the next gem immediately
  9. Cascade Boost          — Each profitable trade in a session lowers the MIN_GEM_SCORE
                              threshold slightly, allowing more aggressive discovery
 10. Trailing Stop Tightening — As a position pyramids, trailing stop tightens to lock gains

All guardrails are individually toggleable via environment variables.
All thresholds are configurable — defaults are aggressive but not reckless.
"""

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# State file (persists across restarts)
# ─────────────────────────────────────────────────────────────────────────────
OFFENSIVE_STATE_FILE = Path("output/offensive_state.json")
OFFENSIVE_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# Offensive State Dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class OffensiveState:
    """
    Persistent offensive guardrail state. Survives restarts.
    """
    # Hot streak tracking
    consecutive_wins: int = 0
    consecutive_losses: int = 0
    win_streak_started_at: Optional[str] = None

    # Daily PnL tracking (resets at midnight UTC)
    daily_realized_pnl_usd: float = 0.0
    daily_pnl_date: str = ""          # "2026-03-23"
    daily_trades_count: int = 0
    daily_wins: int = 0
    daily_losses: int = 0

    # Session-level stats (resets on bot restart)
    session_realized_pnl_usd: float = 0.0
    session_trades: int = 0

    # God Mode state
    god_mode_active: bool = False
    god_mode_activated_at: Optional[str] = None
    god_mode_peak_pnl_usd: float = 0.0

    # Profit boost (existing system, enhanced)
    profit_boost_remaining: int = 0
    profit_boost_multiplier: float = 1.0  # Dynamic, not static

    # Cascade boost (lowers MIN_GEM_SCORE as wins accumulate)
    cascade_score_reduction: float = 0.0  # Max -10 points

    # Momentum reentry tracking (tokens eligible for immediate reentry)
    momentum_reentry_tokens: dict = field(default_factory=dict)  # addr -> {chain, score, tp1_price}

    # Express lane overdrive (tracks which trades got overdrive)
    express_overdrive_count: int = 0

    # House money pool (USD available from locked profits for reinvestment)
    house_money_pool_usd: float = 0.0


def _today_utc() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def load_offensive_state() -> OffensiveState:
    """Load offensive state from disk. Returns fresh state if file missing."""
    try:
        if OFFENSIVE_STATE_FILE.exists():
            with open(OFFENSIVE_STATE_FILE) as f:
                data = json.load(f)
            state = OffensiveState(**{k: v for k, v in data.items()
                                      if k in OffensiveState.__dataclass_fields__})
            # Reset daily stats if it's a new day
            if state.daily_pnl_date != _today_utc():
                logger.info(
                    f"New trading day — resetting daily PnL "
                    f"(yesterday: ${state.daily_realized_pnl_usd:.2f}, "
                    f"{state.daily_wins}W/{state.daily_losses}L)"
                )
                state.daily_realized_pnl_usd = 0.0
                state.daily_pnl_date = _today_utc()
                state.daily_trades_count = 0
                state.daily_wins = 0
                state.daily_losses = 0
                # God Mode resets daily
                state.god_mode_active = False
                state.god_mode_activated_at = None
                state.god_mode_peak_pnl_usd = 0.0
            return state
    except Exception as e:
        logger.warning(f"Could not load offensive state: {e} — starting fresh")
    return OffensiveState(daily_pnl_date=_today_utc())


def save_offensive_state(state: OffensiveState) -> None:
    """Persist offensive state to disk (atomic write)."""
    try:
        tmp = OFFENSIVE_STATE_FILE.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(state.__dict__, f, indent=2, default=str)
        tmp.replace(OFFENSIVE_STATE_FILE)
    except Exception as e:
        logger.error(f"Failed to save offensive state: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# 1. Hot Streak Tracker
# ─────────────────────────────────────────────────────────────────────────────

def get_kelly_streak_multiplier(state: OffensiveState) -> float:
    """
    Return a Kelly fraction multiplier based on current win streak.

    Consecutive wins → increase Kelly fraction (more aggressive sizing):
      0-1 wins  → 1.0x  (Half-Kelly, baseline)
      2-3 wins  → 1.25x (62.5% Kelly)
      4-5 wins  → 1.5x  (75% Kelly — Three-Quarter Kelly)
      6+ wins   → 2.0x  (Full Kelly — maximum aggression)

    Consecutive losses → decrease Kelly fraction (protect capital):
      1 loss    → 0.85x
      2 losses  → 0.70x
      3+ losses → 0.50x (Quarter-Kelly — minimum)
    """
    if not settings.HOT_STREAK_ENABLED:
        return 1.0

    wins = state.consecutive_wins
    losses = state.consecutive_losses

    if losses >= 3:
        mult = 0.50
    elif losses == 2:
        mult = 0.70
    elif losses == 1:
        mult = 0.85
    elif wins >= 6:
        mult = 2.0   # Full Kelly on a 6+ win streak
    elif wins >= 4:
        mult = 1.5   # Three-Quarter Kelly
    elif wins >= 2:
        mult = 1.25  # 62.5% Kelly
    else:
        mult = 1.0   # Baseline Half-Kelly

    if mult != 1.0:
        logger.debug(
            f"Hot streak multiplier: {mult:.2f}x "
            f"(streak: {wins}W/{losses}L)"
        )
    return mult


def record_trade_result(state: OffensiveState, pnl_usd: float, token_symbol: str = "") -> OffensiveState:
    """
    Record a trade close and update all streak/PnL state.
    Call this whenever a position is fully or partially closed.
    """
    now = datetime.now(timezone.utc).isoformat()
    is_win = pnl_usd > 0

    # Update streak
    if is_win:
        state.consecutive_wins += 1
        state.consecutive_losses = 0
        state.daily_wins += 1
        if state.win_streak_started_at is None:
            state.win_streak_started_at = now
        logger.info(
            f"🏆 Win recorded: {token_symbol} +${pnl_usd:.2f} | "
            f"streak: {state.consecutive_wins}W"
        )
    else:
        state.consecutive_losses += 1
        state.consecutive_wins = 0
        state.win_streak_started_at = None
        state.daily_losses += 1
        logger.info(
            f"📉 Loss recorded: {token_symbol} -${abs(pnl_usd):.2f} | "
            f"loss streak: {state.consecutive_losses}"
        )

    # Update PnL
    state.daily_realized_pnl_usd += pnl_usd
    state.session_realized_pnl_usd += pnl_usd
    state.daily_trades_count += 1
    state.session_trades += 1
    state.daily_pnl_date = _today_utc()

    # Update house money pool (only from wins)
    if is_win and settings.HOUSE_MONEY_ENABLED:
        reinvest_pct = settings.HOUSE_MONEY_REINVEST_PCT / 100.0
        house_money_contribution = pnl_usd * reinvest_pct
        state.house_money_pool_usd += house_money_contribution
        # Cap house money pool at a reasonable limit
        state.house_money_pool_usd = min(
            state.house_money_pool_usd,
            settings.HOUSE_MONEY_MAX_POOL_USD
        )
        if house_money_contribution > 1.0:
            logger.info(
                f"💰 House money pool: +${house_money_contribution:.2f} → "
                f"total ${state.house_money_pool_usd:.2f}"
            )

    # Update cascade score reduction
    if settings.CASCADE_BOOST_ENABLED:
        if is_win:
            # Each win reduces MIN_GEM_SCORE by 0.5 points (max 10 points total)
            state.cascade_score_reduction = min(
                state.cascade_score_reduction + settings.CASCADE_BOOST_PER_WIN,
                settings.CASCADE_BOOST_MAX_REDUCTION
            )
        else:
            # Each loss adds back 1 point (recovery is slower than gain)
            state.cascade_score_reduction = max(
                0.0,
                state.cascade_score_reduction - settings.CASCADE_BOOST_RECOVERY_PER_LOSS
            )

    # Update profit boost
    if is_win and pnl_usd >= settings.PROFIT_BOOST_MIN_GAIN_USD:
        if settings.PROFIT_BOOST_ENABLED:
            # Dynamic multiplier: bigger wins = bigger boost
            if pnl_usd >= settings.PROFIT_BOOST_LARGE_WIN_USD:
                state.profit_boost_multiplier = settings.PROFIT_BOOST_LARGE_MULTIPLIER
                state.profit_boost_remaining = settings.PROFIT_BOOST_LARGE_TRADES
                logger.info(
                    f"🔥🔥 LARGE WIN PROFIT BOOST: ${pnl_usd:.2f} → "
                    f"next {state.profit_boost_remaining} trades at "
                    f"{state.profit_boost_multiplier:.0%}x"
                )
            else:
                state.profit_boost_multiplier = settings.PROFIT_BOOST_MULTIPLIER
                state.profit_boost_remaining = settings.PROFIT_BOOST_TRADES
                logger.info(
                    f"🔥 PROFIT BOOST: ${pnl_usd:.2f} → "
                    f"next {state.profit_boost_remaining} trades at "
                    f"{state.profit_boost_multiplier:.0%}x"
                )

    # Check God Mode
    _check_god_mode(state)

    save_offensive_state(state)
    return state


# ─────────────────────────────────────────────────────────────────────────────
# 2. God Mode
# ─────────────────────────────────────────────────────────────────────────────

def _check_god_mode(state: OffensiveState) -> None:
    """
    Activate God Mode if daily PnL exceeds the threshold.
    God Mode: Full Kelly sizing, tighter trailing stops, skip TP1 (hold for 5x).
    """
    if not settings.GOD_MODE_ENABLED:
        return

    if state.god_mode_active:
        # Track peak PnL while in God Mode
        if state.daily_realized_pnl_usd > state.god_mode_peak_pnl_usd:
            state.god_mode_peak_pnl_usd = state.daily_realized_pnl_usd
        return

    if state.daily_realized_pnl_usd >= settings.GOD_MODE_DAILY_PNL_THRESHOLD_USD:
        state.god_mode_active = True
        state.god_mode_activated_at = datetime.now(timezone.utc).isoformat()
        state.god_mode_peak_pnl_usd = state.daily_realized_pnl_usd
        logger.info(
            f"⚡⚡⚡ GOD MODE ACTIVATED ⚡⚡⚡ "
            f"Daily PnL: ${state.daily_realized_pnl_usd:.2f} "
            f"(threshold: ${settings.GOD_MODE_DAILY_PNL_THRESHOLD_USD:.0f}) | "
            f"Full Kelly sizing active | TP1 skipped | Stops tightened"
        )


def get_god_mode_kelly_multiplier(state: OffensiveState) -> float:
    """Return Kelly multiplier for God Mode (2.0x = Full Kelly from Half-Kelly baseline)."""
    if state.god_mode_active and settings.GOD_MODE_ENABLED:
        return settings.GOD_MODE_KELLY_MULTIPLIER
    return 1.0


def get_effective_stop_loss_pct(state: OffensiveState, base_stop_pct: float) -> float:
    """
    Return the effective trailing stop loss percentage.
    God Mode tightens stops to protect the day's gains.
    """
    if state.god_mode_active and settings.GOD_MODE_ENABLED:
        return settings.GOD_MODE_TRAILING_STOP_PCT
    return base_stop_pct


def should_skip_tp1(state: OffensiveState) -> bool:
    """
    In God Mode, skip TP1 (the 2x sell) and hold for TP2 (5x).
    This maximizes gains when we're already playing with house money.
    """
    return state.god_mode_active and settings.GOD_MODE_SKIP_TP1


# ─────────────────────────────────────────────────────────────────────────────
# 3. House Money Protocol
# ─────────────────────────────────────────────────────────────────────────────

def get_house_money_bonus_usd(state: OffensiveState, base_position_usd: float) -> float:
    """
    If house money pool has funds, add them to the next high-conviction trade.
    Returns the additional USD to add to the position (drawn from the pool).
    Depletes the pool by the amount used.
    """
    if not settings.HOUSE_MONEY_ENABLED:
        return 0.0

    if state.house_money_pool_usd < settings.HOUSE_MONEY_MIN_DEPLOY_USD:
        return 0.0

    # Deploy up to HOUSE_MONEY_MAX_DEPLOY_PCT of the pool per trade
    max_deploy = state.house_money_pool_usd * (settings.HOUSE_MONEY_MAX_DEPLOY_PCT / 100.0)
    # Also cap at a multiple of the base position to avoid over-concentration
    max_deploy = min(max_deploy, base_position_usd * settings.HOUSE_MONEY_MAX_POSITION_MULT)

    if max_deploy < 1.0:
        return 0.0

    state.house_money_pool_usd -= max_deploy
    logger.info(
        f"💰 House money deployed: +${max_deploy:.2f} | "
        f"pool remaining: ${state.house_money_pool_usd:.2f}"
    )
    return max_deploy


# ─────────────────────────────────────────────────────────────────────────────
# 4. Cascade Score Boost
# ─────────────────────────────────────────────────────────────────────────────

def get_effective_min_gem_score(state: OffensiveState) -> float:
    """
    Return the effective MIN_GEM_SCORE after applying cascade reduction.
    Each win lowers the threshold slightly, allowing more gems through.
    """
    if not settings.CASCADE_BOOST_ENABLED:
        return settings.MIN_GEM_SCORE
    effective = settings.MIN_GEM_SCORE - state.cascade_score_reduction
    if state.cascade_score_reduction > 0:
        logger.debug(
            f"Cascade boost: MIN_GEM_SCORE {settings.MIN_GEM_SCORE} → {effective:.1f} "
            f"(reduction: {state.cascade_score_reduction:.1f})"
        )
    return max(effective, settings.CASCADE_BOOST_FLOOR_SCORE)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Express Lane Overdrive
# ─────────────────────────────────────────────────────────────────────────────

def get_express_overdrive_multiplier(is_express: bool, gem_score: float, state: OffensiveState) -> float:
    """
    Express Lane Overdrive: highest-conviction snipes get 1.5x position size
    and the bot is willing to pay wider slippage to guarantee entry.

    Only applies to express lane tokens (score ≥ EXPRESS_LANE_SCORE).
    """
    if not settings.EXPRESS_OVERDRIVE_ENABLED:
        return 1.0
    if not is_express:
        return 1.0
    # Scale overdrive with score: 82 → 1.5x, 90+ → 2.0x
    score_above_express = max(0, gem_score - settings.EXPRESS_LANE_SCORE)
    overdrive = 1.5 + min(score_above_express / 20.0, 0.5)  # 1.5x to 2.0x
    logger.info(
        f"⚡ EXPRESS OVERDRIVE: score={gem_score:.0f} → {overdrive:.2f}x position size"
    )
    state.express_overdrive_count += 1
    return overdrive


def get_express_overdrive_slippage_bps(is_express: bool, base_slippage_bps: int) -> int:
    """
    Express Lane Overdrive: add extra slippage buffer to guarantee entry
    on fast-moving tokens. We'd rather pay 0.5% more than miss the trade.
    """
    if not settings.EXPRESS_OVERDRIVE_ENABLED or not is_express:
        return base_slippage_bps
    return min(base_slippage_bps + settings.EXPRESS_OVERDRIVE_EXTRA_SLIPPAGE_BPS, 500)


# ─────────────────────────────────────────────────────────────────────────────
# 6. Tiered Pyramiding (enhanced winner scaling)
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_pyramid_scaling(pos: dict, current_price: float) -> Optional[dict]:
    """
    Tiered pyramiding: add to winners at multiple gain tiers.
    Each tier adds a smaller % of the original position (pyramid shape).
    Trailing stop tightens as we add to protect accumulated gains.

    Tiers:
      Tier 1: +30%  → add 50% of original size, trailing stop = 20%
      Tier 2: +100% → add 25% of original size, trailing stop = 15% (house money)
      Tier 3: +300% → add 10% of original size, trailing stop = 10%

    Returns a scale-in signal dict, or None if no tier triggered.
    """
    if not settings.PYRAMID_SCALING_ENABLED:
        return None

    entry_price = float(pos.get("entry_price", 0))
    if entry_price <= 0:
        return None

    gain_pct = ((current_price - entry_price) / entry_price) * 100
    scale_count = int(pos.get("scale_in_count", 0))
    original_size_usd = float(pos.get("entry_value_usd", 0))

    # Tier 1: +30% gain, first add
    if (gain_pct >= settings.PYRAMID_TIER1_GAIN_PCT
            and scale_count < 1
            and settings.PYRAMID_TIER1_ENABLED):
        return {
            "action": "pyramid_tier1",
            "token_address": pos.get("token_address"),
            "token_symbol": pos.get("token_symbol"),
            "chain": pos.get("chain"),
            "wallet": pos.get("wallet"),
            "gain_pct": gain_pct,
            "current_price": current_price,
            "add_size_pct": settings.PYRAMID_TIER1_ADD_PCT,  # % of original position
            "add_size_usd": original_size_usd * (settings.PYRAMID_TIER1_ADD_PCT / 100.0),
            "new_trailing_stop_pct": settings.PYRAMID_TIER1_TRAILING_STOP_PCT,
            "tier": 1,
        }

    # Tier 2: +100% gain (TP1 level), second add — using house money
    if (gain_pct >= settings.PYRAMID_TIER2_GAIN_PCT
            and scale_count < 2
            and scale_count >= 1
            and settings.PYRAMID_TIER2_ENABLED):
        return {
            "action": "pyramid_tier2",
            "token_address": pos.get("token_address"),
            "token_symbol": pos.get("token_symbol"),
            "chain": pos.get("chain"),
            "wallet": pos.get("wallet"),
            "gain_pct": gain_pct,
            "current_price": current_price,
            "add_size_pct": settings.PYRAMID_TIER2_ADD_PCT,
            "add_size_usd": original_size_usd * (settings.PYRAMID_TIER2_ADD_PCT / 100.0),
            "new_trailing_stop_pct": settings.PYRAMID_TIER2_TRAILING_STOP_PCT,
            "tier": 2,
            "house_money": True,  # Flag: use house money pool for this add
        }

    # Tier 3: +300% gain, third add — maximum aggression
    if (gain_pct >= settings.PYRAMID_TIER3_GAIN_PCT
            and scale_count < 3
            and scale_count >= 2
            and settings.PYRAMID_TIER3_ENABLED):
        return {
            "action": "pyramid_tier3",
            "token_address": pos.get("token_address"),
            "token_symbol": pos.get("token_symbol"),
            "chain": pos.get("chain"),
            "wallet": pos.get("wallet"),
            "gain_pct": gain_pct,
            "current_price": current_price,
            "add_size_pct": settings.PYRAMID_TIER3_ADD_PCT,
            "add_size_usd": original_size_usd * (settings.PYRAMID_TIER3_ADD_PCT / 100.0),
            "new_trailing_stop_pct": settings.PYRAMID_TIER3_TRAILING_STOP_PCT,
            "tier": 3,
            "house_money": True,
        }

    return None


def get_dynamic_trailing_stop_pct(pos: dict, base_stop_pct: float, state: OffensiveState) -> float:
    """
    Return the effective trailing stop percentage for a position.
    Tightens as the position pyramids and as God Mode activates.
    """
    # Check if position has a custom trailing stop from pyramiding
    custom_stop = pos.get("trailing_stop_pct")
    if custom_stop:
        effective = float(custom_stop)
    else:
        effective = base_stop_pct

    # God Mode tightens further
    if state.god_mode_active and settings.GOD_MODE_ENABLED:
        effective = min(effective, settings.GOD_MODE_TRAILING_STOP_PCT)

    return effective


# ─────────────────────────────────────────────────────────────────────────────
# 7. Fast Fail (aggressive underperformer exit)
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_fast_fail(pos: dict, current_price: float) -> Optional[dict]:
    """
    Fast Fail: cut momentum-dead positions quickly to free capital.

    Two triggers:
      A) Momentum Death: position is down >FAST_FAIL_DOWN_PCT after
         FAST_FAIL_HOURS hours AND volume is declining.
         Micro-caps that don't pump in the first few hours are usually dead.

      B) Stale Momentum: position hasn't moved +FAST_FAIL_STALL_PCT in
         FAST_FAIL_STALL_HOURS hours. Capital is better deployed elsewhere.
    """
    if not settings.FAST_FAIL_ENABLED:
        return None

    entry_price = float(pos.get("entry_price", 0))
    if entry_price <= 0:
        return None

    # Don't fast-fail positions that have already hit TP1 (they're winners)
    if pos.get("tp1_hit"):
        return None

    gain_pct = ((current_price - entry_price) / entry_price) * 100
    entry_time = pos.get("entry_time")
    if not entry_time:
        return None

    try:
        entry_dt = datetime.fromisoformat(str(entry_time).replace("Z", "+00:00"))
        age_hours = (datetime.now(timezone.utc) - entry_dt).total_seconds() / 3600
    except Exception:
        return None

    # ── Trigger A: Momentum Death ─────────────────────────────────────────────
    if (age_hours >= settings.FAST_FAIL_HOURS
            and gain_pct <= -settings.FAST_FAIL_DOWN_PCT):
        # Check if volume is also declining (confirms momentum is dead)
        volume_1h = float(pos.get("volume_1h", 0))
        volume_24h = float(pos.get("volume_24h", 0))
        volume_declining = True
        if volume_24h > 0 and volume_1h > 0:
            hourly_avg = volume_24h / 24
            # Volume is still above average — maybe it's just a dip
            if volume_1h > hourly_avg * 0.5:
                volume_declining = False

        if volume_declining:
            return {
                "reason": (
                    f"fast_fail_momentum_death "
                    f"({gain_pct:+.1f}% after {age_hours:.1f}h, vol declining)"
                ),
                "sell_pct": 1.0,
                "urgency": "immediate",
            }

    # ── Trigger B: Stale Momentum ─────────────────────────────────────────────
    if (age_hours >= settings.FAST_FAIL_STALL_HOURS
            and gain_pct < settings.FAST_FAIL_STALL_PCT):
        return {
            "reason": (
                f"fast_fail_stale_momentum "
                f"({gain_pct:+.1f}% after {age_hours:.1f}h — expected >{settings.FAST_FAIL_STALL_PCT:.0f}%)"
            ),
            "sell_pct": 1.0,
            "urgency": "normal",
        }

    return None


# ─────────────────────────────────────────────────────────────────────────────
# 8. Momentum Reentry
# ─────────────────────────────────────────────────────────────────────────────

def register_momentum_reentry(
    state: OffensiveState,
    token_address: str,
    token_symbol: str,
    chain: str,
    tp1_price: float,
    gem_score: float,
    volume_1h: float,
    volume_24h: float,
) -> None:
    """
    After TP1 is hit, check if momentum is still strong enough to reenter.
    If volume is still surging and price is still rising, flag for immediate reentry.
    """
    if not settings.MOMENTUM_REENTRY_ENABLED:
        return

    # Volume must still be surging (>3x hourly average)
    if volume_24h > 0 and volume_1h > 0:
        hourly_avg = volume_24h / 24
        if hourly_avg > 0 and volume_1h / hourly_avg >= settings.MOMENTUM_REENTRY_VOLUME_MULT:
            state.momentum_reentry_tokens[token_address.lower()] = {
                "token_symbol": token_symbol,
                "chain": chain,
                "tp1_price": tp1_price,
                "gem_score": gem_score,
                "registered_at": datetime.now(timezone.utc).isoformat(),
                "volume_surge": volume_1h / hourly_avg if hourly_avg > 0 else 0,
            }
            logger.info(
                f"🔄 Momentum reentry registered: {token_symbol} "
                f"(TP1 @ ${tp1_price:.6f}, vol={volume_1h/hourly_avg:.1f}x avg)"
            )
            save_offensive_state(state)


def get_momentum_reentry_candidates(state: OffensiveState) -> list[dict]:
    """
    Return tokens eligible for momentum reentry.
    Cleans up stale entries (>30 min old).
    """
    if not settings.MOMENTUM_REENTRY_ENABLED:
        return []

    now_ts = time.time()
    valid = []
    stale_keys = []

    for addr, info in state.momentum_reentry_tokens.items():
        try:
            reg_ts = datetime.fromisoformat(
                str(info["registered_at"]).replace("Z", "+00:00")
            ).timestamp()
            age_min = (now_ts - reg_ts) / 60
            if age_min > settings.MOMENTUM_REENTRY_MAX_AGE_MINUTES:
                stale_keys.append(addr)
            else:
                valid.append({"address": addr, **info})
        except Exception:
            stale_keys.append(addr)

    for k in stale_keys:
        del state.momentum_reentry_tokens[k]

    return valid


# ─────────────────────────────────────────────────────────────────────────────
# 9. Composite Position Size Calculation
# ─────────────────────────────────────────────────────────────────────────────

def calculate_offensive_position_size(
    base_position_usd: float,
    gem_score: float,
    is_express: bool,
    state: OffensiveState,
    is_momentum_reentry: bool = False,
) -> tuple[float, str]:
    """
    Apply all offensive multipliers to the base position size.

    Returns:
        (final_position_usd, reason_string)

    Multipliers applied in order:
      1. Hot streak Kelly multiplier
      2. God Mode Kelly multiplier
      3. Express Lane Overdrive multiplier
      4. Profit boost multiplier
      5. House money bonus (additive, not multiplicative)
    """
    multiplier = 1.0
    reasons = []

    # 1. Hot streak
    streak_mult = get_kelly_streak_multiplier(state)
    if streak_mult != 1.0:
        multiplier *= streak_mult
        direction = "↑" if streak_mult > 1 else "↓"
        reasons.append(f"streak={streak_mult:.2f}x{direction}")

    # 2. God Mode
    god_mult = get_god_mode_kelly_multiplier(state)
    if god_mult != 1.0:
        multiplier *= god_mult
        reasons.append(f"god_mode={god_mult:.2f}x⚡")

    # 3. Express Overdrive
    express_mult = get_express_overdrive_multiplier(is_express, gem_score, state)
    if express_mult != 1.0:
        multiplier *= express_mult
        reasons.append(f"express={express_mult:.2f}x⚡")

    # 4. Profit boost (existing system, now dynamic)
    if state.profit_boost_remaining > 0 and settings.PROFIT_BOOST_ENABLED:
        boost_mult = state.profit_boost_multiplier
        multiplier *= boost_mult
        state.profit_boost_remaining -= 1
        reasons.append(f"profit_boost={boost_mult:.2f}x🔥({state.profit_boost_remaining} left)")

    # 5. Momentum reentry gets a bonus (we know this token moves)
    if is_momentum_reentry and settings.MOMENTUM_REENTRY_ENABLED:
        multiplier *= settings.MOMENTUM_REENTRY_SIZE_MULT
        reasons.append(f"reentry={settings.MOMENTUM_REENTRY_SIZE_MULT:.2f}x🔄")

    # Apply multiplier to base position
    final_position_usd = base_position_usd * multiplier

    # 6. House money bonus (additive — uses locked profits)
    house_bonus = get_house_money_bonus_usd(state, final_position_usd)
    if house_bonus > 0:
        final_position_usd += house_bonus
        reasons.append(f"+${house_bonus:.0f} house_money💰")

    # Cap at absolute maximum to prevent runaway sizing
    max_position = settings.OFFENSIVE_MAX_POSITION_USD
    if final_position_usd > max_position:
        logger.warning(
            f"Offensive position capped: ${final_position_usd:.2f} → ${max_position:.2f}"
        )
        final_position_usd = max_position

    reason_str = " | ".join(reasons) if reasons else "baseline"
    if multiplier != 1.0 or house_bonus > 0:
        logger.info(
            f"🎯 Offensive sizing: ${base_position_usd:.2f} → ${final_position_usd:.2f} "
            f"({reason_str})"
        )

    return final_position_usd, reason_str


# ─────────────────────────────────────────────────────────────────────────────
# 10. Daily Performance Summary
# ─────────────────────────────────────────────────────────────────────────────

def get_daily_summary(state: OffensiveState) -> dict:
    """Return a summary of today's offensive guardrail activity."""
    win_rate = (
        state.daily_wins / state.daily_trades_count * 100
        if state.daily_trades_count > 0 else 0
    )
    return {
        "date": state.daily_pnl_date,
        "realized_pnl_usd": state.daily_realized_pnl_usd,
        "trades": state.daily_trades_count,
        "wins": state.daily_wins,
        "losses": state.daily_losses,
        "win_rate_pct": win_rate,
        "consecutive_wins": state.consecutive_wins,
        "consecutive_losses": state.consecutive_losses,
        "god_mode_active": state.god_mode_active,
        "profit_boost_remaining": state.profit_boost_remaining,
        "profit_boost_multiplier": state.profit_boost_multiplier,
        "house_money_pool_usd": state.house_money_pool_usd,
        "cascade_score_reduction": state.cascade_score_reduction,
        "express_overdrive_count": state.express_overdrive_count,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Global singleton (loaded once, shared across the bot)
# ─────────────────────────────────────────────────────────────────────────────
_offensive_state: Optional[OffensiveState] = None


def get_offensive_state() -> OffensiveState:
    """Get the global offensive state singleton. Loads from disk on first call."""
    global _offensive_state
    if _offensive_state is None:
        _offensive_state = load_offensive_state()
    return _offensive_state


def refresh_offensive_state() -> OffensiveState:
    """Force reload from disk (call after external modifications)."""
    global _offensive_state
    _offensive_state = load_offensive_state()
    return _offensive_state
