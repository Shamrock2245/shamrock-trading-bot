"""
Ito Trade Planner (ECC Skill: ito-trade-planner)
Dynamically calculates Take-Profit, Stop-Loss, and Position Sizing
using mathematical expectation and risk adjustment models.
Bypasses static hardcoded percentages for responsive trade management.
"""

import math
import logging

logger = logging.getLogger(__name__)

class ItoTradePlanner:
    def __init__(self, base_tp_pct=0.20, base_sl_pct=0.10, risk_free_rate=0.0):
        self.base_tp_pct = base_tp_pct
        self.base_sl_pct = base_sl_pct
        self.risk_free_rate = risk_free_rate

    def calculate_trade_plan(self, gem_score: float, token_age_hours: float, current_price: float, volatility_proxy: float = 1.0):
        """
        Generates dynamic TP/SL levels based on the asset's characteristics.
        volatility_proxy: normalized metric where 1.0 is average volatility, >1 is high, <1 is low.
        """
        # Younger tokens = higher volatility = wider stops and higher targets
        age_factor = 1.0
        if token_age_hours < 1.0:
            age_factor = 2.0
        elif token_age_hours < 24.0:
            age_factor = 1.5

        # Score confidence adjusts stops. High score = tighter stops (trust the thesis), higher TPs.
        confidence = min(gem_score / 100.0, 1.0)
        
        dynamic_tp_pct = self.base_tp_pct * age_factor * volatility_proxy * (1 + confidence)
        dynamic_sl_pct = self.base_sl_pct * age_factor * volatility_proxy * (1.5 - confidence)

        # Kelly criterion for optimal position size scaling (simplified proxy)
        win_prob = 0.45 + (confidence * 0.15)  # Max 60% expected win rate
        reward_risk_ratio = dynamic_tp_pct / max(dynamic_sl_pct, 0.01)
        
        # Kelly % = W - [(1 - W) / R]
        kelly_pct = win_prob - ((1.0 - win_prob) / reward_risk_ratio)
        kelly_pct = max(0.01, min(kelly_pct, 1.0)) # Cap between 1% and full Kelly

        return {
            "entry_price": current_price,
            "tp1": current_price * (1 + (dynamic_tp_pct * 0.5)),
            "tp2": current_price * (1 + dynamic_tp_pct),
            "tp3": current_price * (1 + (dynamic_tp_pct * 1.5)),
            "sl": current_price * (1 - dynamic_sl_pct),
            "dynamic_tp_pct": dynamic_tp_pct,
            "dynamic_sl_pct": dynamic_sl_pct,
            "recommended_kelly_sizing": kelly_pct
        }

trade_planner = ItoTradePlanner()
