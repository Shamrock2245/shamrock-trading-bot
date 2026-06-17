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
        
        # No profit-side caps — make as much as possible.
        # Previously capped trades near goal and in bank_it mode.
        # User directive: "do not cap what we can make per day"
                
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
