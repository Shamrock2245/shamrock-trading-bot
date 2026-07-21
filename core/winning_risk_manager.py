"""
core/winning_risk_manager.py — "Winning" Risk Management & Profit Capture Engine

Implements aggressive profit-locking and loss-prevention strategies:
1. Ultra-Fast Break-even: Lock break-even at +0.75% profit (vs. +1.5%)
2. TP1 Front-loading: Close 50% at +2% profit to secure "house money"
3. The 30-Min Rule: Tighten SL to -1% if no profit within 30 minutes
4. Aggressive Trailing: 0.5% trailing stop after TP1 (vs. 1.5%)

This module closes the "Slow Leak" by preventing small losses and long-duration bleeds.
"""

import logging
import time
from typing import Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class WinningRiskManager:
    def __init__(self):
        # Ultra-Fast Break-even Settings
        self.fast_break_even_pct = 0.75  # Lock break-even at +0.75%
        self.fast_break_even_sl_offset = 0.05  # Entry + 0.05%
        
        # TP1 Front-loading Settings
        self.tp1_profit_pct = 2.0       # Take profit at +2%
        self.tp1_size_pct = 50          # Sell 50% of position
        
        # The 30-Min Rule
        self.min_rule_time_minutes = 30  # Close or tighten SL after 30 min
        self.min_rule_sl_offset = -1.0   # Tighten to -1%
        
        # Aggressive Trailing Stop
        self.trailing_stop_pct = 0.5    # 0.5% trailing (vs. 1.5%)
        
        # Toxic Zone Restriction (08:00-14:00 EST)
        self.toxic_zone_start = 8
        self.toxic_zone_end = 14
        
    def evaluate_position(self, pos_data: Dict) -> Dict:
        """
        Evaluate a position and return action recommendations.
        
        pos_data: {
            'coin': str,
            'entry_price': float,
            'current_price': float,
            'entry_time': float (unix timestamp),
            'side': str ('long' or 'short'),
            'tp1_hit': bool (has TP1 been executed?),
            'peak_price': float (highest price seen),
            'position_size': float
        }
        
        Returns: {
            'action': str ('none', 'update_sl', 'partial_close', 'close_all'),
            'sl_price': float (if action is update_sl),
            'close_size_pct': float (if action is partial_close),
            'reason': str
        }
        """
        coin = pos_data.get('coin', 'UNKNOWN')
        entry_px = pos_data['entry_price']
        curr_px = pos_data['current_price']
        side = pos_data['side']
        entry_time = pos_data['entry_time']
        tp1_hit = pos_data.get('tp1_hit', False)
        peak_px = pos_data.get('peak_price', curr_px)
        
        # Calculate PnL %
        if side == 'long':
            pnl_pct = ((curr_px - entry_px) / entry_px) * 100
        else:  # short
            pnl_pct = ((entry_px - curr_px) / entry_px) * 100
        
        # Calculate time elapsed (minutes)
        time_elapsed = (time.time() - entry_time) / 60
        
        # ─────────────────────────────────────────────────────────────
        # 1. Ultra-Fast Break-even at +0.75%
        # ─────────────────────────────────────────────────────────────
        if pnl_pct >= self.fast_break_even_pct:
            if side == 'long':
                new_sl = entry_px * (1 + self.fast_break_even_sl_offset / 100)
            else:
                new_sl = entry_px * (1 - self.fast_break_even_sl_offset / 100)
            
            logger.info(f"[{coin}] 🎯 Ultra-Fast Break-even: +{pnl_pct:.2f}% → SL to {new_sl:.8f}")
            return {
                'action': 'update_sl',
                'sl_price': new_sl,
                'reason': f'Ultra-Fast Break-even at +{pnl_pct:.2f}%'
            }
        
        # ─────────────────────────────────────────────────────────────
        # 2. TP1 Front-loading at +2%
        # ─────────────────────────────────────────────────────────────
        if pnl_pct >= self.tp1_profit_pct and not tp1_hit:
            logger.info(f"[{coin}] 💰 TP1 Front-loading: +{pnl_pct:.2f}% → Close {self.tp1_size_pct}%")
            return {
                'action': 'partial_close',
                'close_size_pct': self.tp1_size_pct,
                'reason': f'TP1 Front-loading at +{pnl_pct:.2f}%'
            }
        
        # ─────────────────────────────────────────────────────────────
        # 3. The 30-Min Rule: Tighten SL if no profit in 30 min
        # ─────────────────────────────────────────────────────────────
        if time_elapsed >= self.min_rule_time_minutes and pnl_pct < 0:
            if side == 'long':
                new_sl = entry_px * (1 + self.min_rule_sl_offset / 100)
            else:
                new_sl = entry_px * (1 - self.min_rule_sl_offset / 100)
            
            logger.warning(f"[{coin}] ⏱️  30-Min Rule: {time_elapsed:.0f}m in loss ({pnl_pct:.2f}%) → Tighten SL to {new_sl:.8f}")
            return {
                'action': 'update_sl',
                'sl_price': new_sl,
                'reason': f'30-Min Rule: {time_elapsed:.0f}m in loss'
            }
        
        # ─────────────────────────────────────────────────────────────
        # 4. Aggressive Trailing Stop (0.5%) after TP1
        # ─────────────────────────────────────────────────────────────
        if tp1_hit and pnl_pct > 0:
            if side == 'long':
                trail_sl = peak_px * (1 - self.trailing_stop_pct / 100)
            else:
                trail_sl = peak_px * (1 + self.trailing_stop_pct / 100)
            
            logger.debug(f"[{coin}] 📉 Aggressive Trailing: Peak {peak_px:.8f} → Trail SL {trail_sl:.8f}")
            return {
                'action': 'update_sl',
                'sl_price': trail_sl,
                'reason': f'Aggressive Trailing at {pnl_pct:.2f}%'
            }
        
        return {'action': 'none', 'reason': 'No action required'}

    def is_toxic_zone(self, hour: int) -> bool:
        """Check if current hour is in the toxic zone (08:00-14:00 EST)."""
        return self.toxic_zone_start <= hour < self.toxic_zone_end

    def get_position_size_multiplier(self, hour: int) -> float:
        """
        Return position size multiplier based on time of day.
        During toxic zone, reduce size by 50%.
        """
        if self.is_toxic_zone(hour):
            logger.info(f"⚠️  Toxic Zone detected (hour {hour}). Reducing position size to 50%.")
            return 0.5
        return 1.0


# Global instance
winning_risk_manager = WinningRiskManager()
