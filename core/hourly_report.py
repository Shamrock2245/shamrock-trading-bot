"""
core/hourly_report.py — Generates and sends hourly status updates.

Provides a summary of bot performance, daily PnL, active positions, and 
current strategy mode, sending it to Slack and Telegram.
"""

import logging
from typing import Dict, Any

from config import settings
from core.daily_goal_engine import get_daily_goal_engine
from core.position_monitor import load_positions
from core.regime_filter import get_regime

# Use the existing notification functions
from notifications.slack import notify_alert as slack_alert
from notifications.telegram import notify_alert as tg_alert

logger = logging.getLogger(__name__)

def send_hourly_report():
    """
    Generate an hourly performance summary and dispatch to configured notification channels.
    """
    logger.info("📊 Generating hourly performance report...")
    
    try:
        engine = get_daily_goal_engine()
        positions = load_positions()
        
        # PnL & Goal stats
        today_pnl = engine.today_profit_usd
        target = engine.current_target_usd
        progress = engine.progress_pct
        mode = engine.strategy_mode
        
        # Regime stats
        regime_state = get_regime()
        regime_name = regime_state.regime.name if hasattr(regime_state, "regime") else "UNKNOWN"
        
        # Position stats
        open_positions = [p for p in positions if p.get("status") == "open"]
        num_open = len(open_positions)
        
        total_unrealized_usd = 0.0
        winners = 0
        losers = 0
        
        for p in open_positions:
            entry = float(p.get("entry_price", 0))
            current = float(p.get("current_price", entry) or entry)
            qty = float(p.get("quantity", 0))
            
            if entry > 0 and qty > 0:
                unrealized_usd = (current - entry) * qty
                total_unrealized_usd += unrealized_usd
                if current > entry:
                    winners += 1
                elif current < entry:
                    losers += 1

        title = f"Hourly Report: {settings.MODE.upper()}"
        
        message = (
            f"🎯 *Daily Goal Progress:* ${today_pnl:.2f} / ${target:.2f} ({progress:.1f}%)\n"
            f"🧠 *Strategy Mode:* {mode.upper()}\n"
            f"🌊 *Market Regime:* {regime_name}\n"
            f"💼 *Open Positions:* {num_open} ({winners} green, {losers} red)\n"
            f"💸 *Unrealized PnL:* ${total_unrealized_usd:.2f}\n"
        )
        
        # Add a quick breakdown of top positions if any
        if num_open > 0:
            # Sort positions by unrealized gain percentage
            def get_gain_pct(p):
                entry = float(p.get("entry_price", 0))
                current = float(p.get("current_price", entry) or entry)
                return ((current - entry) / entry * 100) if entry > 0 else 0
                
            sorted_pos = sorted(open_positions, key=get_gain_pct, reverse=True)
            
            message += "\n*Top 3 Positions:*\n"
            for i, p in enumerate(sorted_pos[:3]):
                token = p.get("token_symbol", "UNKNOWN")
                gain_pct = get_gain_pct(p)
                trail = float(p.get("trailing_stop_pct", 0.0))
                icon = "🟢" if gain_pct > 0 else "🔴"
                message += f"  {icon} {token}: {gain_pct:+.1f}% (Trail: {trail}%)\n"

        # Dispatch
        slack_alert(title, message, level="info")
        tg_alert(title, message, level="info")
        
        logger.info(f"Hourly report sent successfully.\n{message}")
        
    except Exception as e:
        logger.error(f"Failed to generate hourly report: {e}", exc_info=True)

if __name__ == "__main__":
    send_hourly_report()
