"""
core/profit_lock_manager.py — Dynamic Profit-Locking & Trailing Stop Manager

Implements the "Money Machine" profit-locking strategy:
1. Break-even Lock: Once +1.5% profit, move SL to Entry + 0.1% (covers fees)
2. Trailing Profit Ratchet: At +3%, lock in 1.5% with trailing SL
3. Hard Time-Out: Close any position in loss for > 4 hours to free capital

This module works alongside position_monitor.py to ensure consistent profit capture.
"""

import json
import logging
import os
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

class ProfitLockManager:
    def __init__(self, state_file: str = "/app/data/hl_trailing_state.json"):
        self.state_file = state_file
        self.state: Dict = self._load_state()
        self._lock = threading.Lock()

    def _load_state(self) -> Dict:
        """Load trailing stop state from disk."""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"ProfitLockManager: Failed to load state: {e}. Starting fresh.")
                return {}
        return {}

    def _save_state(self):
        """Persist trailing stop state to disk."""
        with self._lock:
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            try:
                with open(self.state_file, 'w') as f:
                    json.dump(self.state, f, indent=4)
            except Exception as e:
                logger.error(f"ProfitLockManager: Failed to save state: {e}")

    def process_position(self, coin: str, current_price: float, entry_price: float, 
                        entry_time: datetime, side: str = 'long') -> Dict:
        """
        Update stop loss based on profit-locking and trailing logic.
        
        Returns:
            Dict with updated position state (sl_price, status, etc.)
        """
        with self._lock:
            if coin not in self.state:
                self.state[coin] = {
                    "entry_price": entry_price,
                    "entry_time": entry_time.isoformat() if isinstance(entry_time, datetime) else entry_time,
                    "peak_price": current_price,
                    "sl_price": entry_price * 0.95 if side == 'long' else entry_price * 1.05,
                    "status": "active",
                    "locked_profit_pct": 0.0,
                    "side": side
                }

            pos = self.state[coin]
            
            # Calculate PnL %
            if side == 'long':
                pnl_pct = ((current_price - entry_price) / entry_price) * 100
                
                # Update peak price
                if current_price > pos['peak_price']:
                    pos['peak_price'] = current_price
                
                # ─────────────────────────────────────────────────────────────
                # Break-even Lock: +1.5% → Move SL to Entry + 0.1%
                # ─────────────────────────────────────────────────────────────
                if pnl_pct >= 1.5 and pos['sl_price'] < entry_price:
                    pos['sl_price'] = entry_price * 1.001
                    pos['locked_profit_pct'] = 0.1
                    logger.info(f"[{coin}] Break-even SL locked at {pos['sl_price']:.8f} (Entry: {entry_price:.8f})")
                
                # ─────────────────────────────────────────────────────────────
                # Trailing Profit Lock: +3% → Lock 1.5%, Trail from peak
                # ─────────────────────────────────────────────────────────────
                if pnl_pct >= 3.0:
                    # Trail 1.5% from peak
                    trail_sl = pos['peak_price'] * 0.985
                    if trail_sl > pos['sl_price']:
                        pos['sl_price'] = trail_sl
                        pos['locked_profit_pct'] = 1.5
                        logger.info(f"[{coin}] Trailing SL updated to {pos['sl_price']:.8f} (Peak: {pos['peak_price']:.8f}, Trail: 1.5%)")
                
                # ─────────────────────────────────────────────────────────────
                # Hard Time-Out: > 4 hours in loss → Close to free capital
                # ─────────────────────────────────────────────────────────────
                entry_dt = datetime.fromisoformat(pos['entry_time']) if isinstance(pos['entry_time'], str) else pos['entry_time']
                time_held = datetime.utcnow() - entry_dt
                
                if pnl_pct < 0 and time_held > timedelta(hours=4):
                    pos['status'] = 'timeout_close'
                    logger.warning(f"[{coin}] Hard time-out triggered: {time_held.total_seconds() / 3600:.1f}h in loss ({pnl_pct:.2f}%). Marking for closure.")
            
            else:  # Short side
                pnl_pct = ((entry_price - current_price) / entry_price) * 100
                
                # Update peak price (lowest for shorts)
                if current_price < pos['peak_price']:
                    pos['peak_price'] = current_price
                
                # Break-even lock for shorts
                if pnl_pct >= 1.5 and pos['sl_price'] > entry_price:
                    pos['sl_price'] = entry_price * 0.999
                    pos['locked_profit_pct'] = 0.1
                    logger.info(f"[{coin}] Short break-even SL locked at {pos['sl_price']:.8f}")
                
                # Trailing for shorts
                if pnl_pct >= 3.0:
                    trail_sl = pos['peak_price'] * 1.015
                    if trail_sl < pos['sl_price']:
                        pos['sl_price'] = trail_sl
                        pos['locked_profit_pct'] = 1.5
                        logger.info(f"[{coin}] Short trailing SL updated to {pos['sl_price']:.8f}")
            
            self._save_state()
            return pos

    def get_position_state(self, coin: str) -> Optional[Dict]:
        """Retrieve current state for a position."""
        with self._lock:
            return self.state.get(coin)

    def mark_closed(self, coin: str):
        """Mark a position as closed."""
        with self._lock:
            if coin in self.state:
                self.state[coin]['status'] = 'closed'
                self._save_state()

    def cleanup_closed(self):
        """Remove closed positions from state to keep file lean."""
        with self._lock:
            closed_coins = [c for c, s in self.state.items() if s.get('status') == 'closed']
            for coin in closed_coins:
                del self.state[coin]
            if closed_coins:
                logger.info(f"ProfitLockManager: Cleaned up {len(closed_coins)} closed positions.")
                self._save_state()


# Global instance
profit_lock_manager = ProfitLockManager()
