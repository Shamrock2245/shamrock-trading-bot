"""
core/shamrock_guard.py — Pre-execution risk management middleware.

This acts as a global guard boundary before trades are routed. 
It uses the DailyGoalEngine to track progress and enforce risk limits.
"""

import logging
from typing import Tuple

from core.daily_goal_engine import get_daily_goal_engine
from config import settings

logger = logging.getLogger(__name__)

class ShamrockGuard:
    """Global Risk Management Guard that prevents trades that violate daily profit targets/drawdowns."""

    @classmethod
    def check_trade_guard(cls, requested_position_usd: float) -> Tuple[bool, str]:
        """
        Check if the requested trade size is allowed given the current daily PnL context.
        
        Args:
            requested_position_usd: The dollar value of the trade we want to open.
            
        Returns:
            (is_allowed, reason)
        """
        engine = get_daily_goal_engine()
        progress_pct = engine.progress_pct
        current_profit = engine.today_profit_usd
        target = engine.current_target_usd
        
        # 1. Protect the profit if we are very close to the goal.
        # e.g., if target is 500, and we are at 480, we shouldn't open a $100 position, 
        # because a 50% loss would drop us to 430. We should cap the position size.
        if progress_pct > 80.0 and progress_pct < 100.0 and target > 0:
            remaining = target - current_profit
            # Hard limit: do not risk more than what we need + a small buffer.
            # Assume max loss is 25% (stop loss). To lose 'remaining', position size would be remaining / 0.25
            max_allowed_position = max(remaining * 2.0, 50.0) # at least $50
            if requested_position_usd > max_allowed_position:
                reason = (f"Guard Blocked: Daily PnL (${current_profit:.2f}) is near target (${target:.2f}). "
                          f"Requested ${requested_position_usd:.2f} exceeds dynamic risk cap of ${max_allowed_position:.2f}.")
                logger.warning(f"🛡️ {reason}")
                return False, reason

        # 2. Bank It Mode Protection
        # If we are >150% of goal, we should strictly limit new positions to preserve the sweep.
        if engine.strategy_mode == "bank_it":
            # Only allow very small positions in bank_it mode (e.g. 10% of normal)
            max_allowed_position = 50.0
            if requested_position_usd > max_allowed_position:
                reason = (f"Guard Blocked: In BANK IT mode. "
                          f"Requested ${requested_position_usd:.2f} exceeds bank_it cap of ${max_allowed_position:.2f}.")
                logger.warning(f"🛡️ {reason}")
                return False, reason
                
        # 3. Maximum Daily Drawdown Guard
        # If today's profit is deeply negative (e.g., -$200 on a $500 goal), we should throttle.
        if current_profit < -(target * 0.40) and target > 0:
            # We are down 40% of our daily target. Enter highly restricted mode.
            max_allowed_position = 20.0
            if requested_position_usd > max_allowed_position:
                reason = (f"Guard Blocked: High daily drawdown (${current_profit:.2f}). "
                          f"Requested ${requested_position_usd:.2f} exceeds drawdown cap of ${max_allowed_position:.2f}.")
                logger.warning(f"🛡️ {reason}")
                return False, reason

        return True, "Passed Guard"
