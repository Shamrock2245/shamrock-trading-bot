"""
core/hl_scanner_winning_tuning.py — Enhanced Entry Filters for "Winning" Tuning

Implements strict entry criteria to eliminate small-loss "death by a thousand cuts":
1. Volume Floor: Minimum $1M 24h volume (was $100k)
2. VWAP Filter: Only enter if price is above VWAP on 15m timeframe
3. Narrative Bonus: Coins with Narrative Score > 0.8 can bypass strict gate
4. Volatility Adjustment: High ATR (>5%) reduces position size by 50%

This module closes the entry-side code gap by preventing weak entries.
"""

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

class WinningEntryFilter:
    def __init__(self):
        # Volume Requirements
        self.min_volume_usd = 1_000_000  # $1M minimum (was $100k)
        
        # VWAP Filter
        self.use_vwap_filter = True
        self.vwap_timeframe = "15m"  # 15-minute VWAP
        
        # Narrative Bonus
        self.narrative_score_threshold = 0.8
        self.narrative_gate_bypass = True  # High narrative can bypass strict gate
        
        # Volatility Adjustment
        self.max_atr_pct = 5.0  # ATR > 5% of price = high volatility
        self.high_vol_size_multiplier = 0.5  # Reduce size by 50%
        
        # Blacklist (coins that have failed 3+ times in 24h)
        self.dynamic_blacklist = []
        
    def validate_entry(self, token_data: Dict) -> Dict:
        """
        Validate if a token meets "Winning" entry criteria.
        
        token_data: {
            'symbol': str,
            'current_price': float,
            'volume_24h_usd': float,
            'vwap_15m': float,
            'atr_pct': float,
            'narrative_score': float,
            'sl_count_24h': int (number of SL hits in 24h)
        }
        
        Returns: {
            'approved': bool,
            'reason': str,
            'position_size_multiplier': float
        }
        """
        symbol = token_data.get('symbol', 'UNKNOWN')
        volume = token_data.get('volume_24h_usd', 0)
        curr_px = token_data.get('current_price', 0)
        vwap = token_data.get('vwap_15m', 0)
        atr_pct = token_data.get('atr_pct', 0)
        narrative_score = token_data.get('narrative_score', 0)
        sl_count = token_data.get('sl_count_24h', 0)
        
        size_multiplier = 1.0
        
        # ─────────────────────────────────────────────────────────────
        # 1. Check Dynamic Blacklist
        # ─────────────────────────────────────────────────────────────
        if symbol in self.dynamic_blacklist:
            logger.warning(f"[{symbol}] ❌ Entry Blocked: On dynamic blacklist (3+ SL hits in 24h)")
            return {
                'approved': False,
                'reason': 'Dynamic blacklist (3+ SL hits)',
                'position_size_multiplier': 0
            }
        
        # ─────────────────────────────────────────────────────────────
        # 2. Volume Floor: $1M minimum
        # ─────────────────────────────────────────────────────────────
        if volume < self.min_volume_usd:
            logger.warning(f"[{symbol}] ❌ Entry Blocked: Volume ${volume:,.0f} < ${self.min_volume_usd:,.0f}")
            return {
                'approved': False,
                'reason': f'Volume ${volume:,.0f} below ${self.min_volume_usd:,.0f} floor',
                'position_size_multiplier': 0
            }
        
        # ─────────────────────────────────────────────────────────────
        # 3. VWAP Filter: Price must be above VWAP on 15m
        # ─────────────────────────────────────────────────────────────
        if self.use_vwap_filter and vwap > 0:
            if curr_px < vwap:
                logger.warning(f"[{symbol}] ❌ Entry Blocked: Price ${curr_px:.8f} < VWAP ${vwap:.8f}")
                return {
                    'approved': False,
                    'reason': f'Price below VWAP (${curr_px:.8f} < ${vwap:.8f})',
                    'position_size_multiplier': 0
                }
        
        # ─────────────────────────────────────────────────────────────
        # 4. Volatility Adjustment: High ATR reduces size
        # ─────────────────────────────────────────────────────────────
        if atr_pct > self.max_atr_pct:
            size_multiplier = self.high_vol_size_multiplier
            logger.info(f"[{symbol}] ⚠️  High Volatility: ATR {atr_pct:.2f}% → Reduce size to 50%")
        
        # ─────────────────────────────────────────────────────────────
        # 5. Narrative Bonus: High narrative can bypass strict gate
        # ─────────────────────────────────────────────────────────────
        if narrative_score >= self.narrative_score_threshold:
            logger.info(f"[{symbol}] 🎯 Narrative Bonus: Score {narrative_score:.2f} → Approved")
            return {
                'approved': True,
                'reason': f'Narrative Score {narrative_score:.2f} (Bonus Entry)',
                'position_size_multiplier': size_multiplier
            }
        
        # ─────────────────────────────────────────────────────────────
        # 6. Standard Entry Approval
        # ─────────────────────────────────────────────────────────────
        logger.info(f"[{symbol}] ✅ Entry Approved: Volume ${volume:,.0f}, Price above VWAP")
        return {
            'approved': True,
            'reason': 'All filters passed',
            'position_size_multiplier': size_multiplier
        }
    
    def update_blacklist(self, symbol: str, sl_count: int):
        """Update dynamic blacklist if a coin hits SL 3+ times in 24h."""
        if sl_count >= 3:
            if symbol not in self.dynamic_blacklist:
                self.dynamic_blacklist.append(symbol)
                logger.warning(f"[{symbol}] 🚫 Added to blacklist: {sl_count} SL hits in 24h")
    
    def clear_blacklist(self):
        """Clear the dynamic blacklist (should be called daily)."""
        if self.dynamic_blacklist:
            logger.info(f"Clearing dynamic blacklist: {self.dynamic_blacklist}")
        self.dynamic_blacklist = []


# Global instance
winning_entry_filter = WinningEntryFilter()
