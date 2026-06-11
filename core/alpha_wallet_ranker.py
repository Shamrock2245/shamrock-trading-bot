"""
Alpha Wallet Ranker (ECC Skill: social-graph-ranker adapted)
Analyzes historical performance of tracked alpha wallets and generates 
a dynamic size multiplier to cut off losing streaks and compound winners.
The engine queries Moralis streams to monitor a curated list of top-performing DEX traders.
It continuously calculates their win rate, average ROI per trade, and risk profile.
When a tier-1 wallet (e.g., >75% win rate over 50 trades) initiates a buy on a new token,
the engine triggers a mirror trade using our defined position sizing.
"""

import json
import logging
import threading
from pathlib import Path
from typing import Dict, Any, Tuple
from core.position_monitor import load_positions
from config import settings

logger = logging.getLogger(__name__)

SCORES_FILE = Path("data/wallet_scores.json")
SCORES_FILE.parent.mkdir(parents=True, exist_ok=True)

class AlphaWalletRanker:
    def __init__(self, base_multiplier=1.0, max_multiplier=3.0, min_multiplier=0.5):
        self.base_multiplier = base_multiplier
        self.max_multiplier = max_multiplier
        self.min_multiplier = min_multiplier
        self._cache_lock = threading.Lock()
        self._scores_cache: Dict[str, float] = {}
        self._load_cache()

    def _load_cache(self):
        """Loads scores into memory for fastlane execution."""
        try:
            if SCORES_FILE.exists():
                with open(SCORES_FILE, "r") as f:
                    self._scores_cache = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load wallet scores cache: {e}")
            self._scores_cache = {}

    def recalculate_scores(self):
        """
        Reads closed positions and computes win-rate and ROI per alpha wallet.
        Writes the results to wallet_scores.json
        """
        try:
            positions = load_positions()
            closed_positions = [p for p in positions if p.get("status") == "closed"]
            
            stats = {}
            for p in closed_positions:
                wallet = p.get("wallet", "unknown")
                if wallet not in stats:
                    stats[wallet] = {"trades": 0, "wins": 0, "total_roi": 0.0}
                
                stats[wallet]["trades"] += 1
                roi = p.get("realized_pnl_pct", 0.0)
                stats[wallet]["total_roi"] += roi
                if roi > 0:
                    stats[wallet]["wins"] += 1

            scores = {}
            for wallet, data in stats.items():
                if data["trades"] < 3:
                    scores[wallet] = self.base_multiplier
                    continue
                
                win_rate = data["wins"] / data["trades"]
                avg_roi = data["total_roi"] / data["trades"]
                
                # Multiplier logic:
                # High win-rate (>60%) + positive ROI = scale up
                # Low win-rate (<40%) or negative ROI = scale down
                multiplier = self.base_multiplier
                if win_rate >= 0.6 and avg_roi > 0:
                    multiplier += (win_rate - 0.5) * 2.0  # Boost
                elif win_rate < 0.4 or avg_roi < 0:
                    multiplier -= (0.5 - win_rate) * 2.0  # Penalize
                
                # Cap multiplier
                multiplier = max(self.min_multiplier, min(multiplier, self.max_multiplier))
                scores[wallet] = round(multiplier, 2)

            # Atomic write
            tmp_file = SCORES_FILE.with_suffix(".tmp")
            with open(tmp_file, "w") as f:
                json.dump(scores, f, indent=2)
            tmp_file.replace(SCORES_FILE)
            
            with self._cache_lock:
                self._scores_cache = scores
                
            logger.info(f"Updated Alpha Wallet scores: {len(scores)} wallets ranked.")
        except Exception as e:
            logger.error(f"Failed to recalculate wallet scores: {e}")

    def get_multiplier(self, wallet_alias: str) -> float:
        """
        Fast RAM read for fastlane execution. 
        """
        with self._cache_lock:
            return self._scores_cache.get(wallet_alias, self.base_multiplier)

    def evaluate_wallet_tier(self, wallet_alias: str) -> Tuple[int, float]:
        """
        Evaluates a wallet's performance to determine its tier.
        Returns (tier, win_rate) where tier 1 is the highest conviction.
        """
        try:
            positions = load_positions()
            closed_positions = [p for p in positions if p.get("status") == "closed" and p.get("wallet") == wallet_alias]
            
            if not closed_positions:
                return 3, 0.0
                
            trades = len(closed_positions)
            wins = sum(1 for p in closed_positions if p.get("realized_pnl_pct", 0) > 0)
            win_rate = wins / trades if trades > 0 else 0.0
            
            if trades >= 50 and win_rate >= 0.75:
                return 1, win_rate
            elif trades >= 20 and win_rate >= 0.60:
                return 2, win_rate
            else:
                return 3, win_rate
        except Exception as e:
            logger.error(f"Failed to evaluate wallet tier for {wallet_alias}: {e}")
            return 3, 0.0

wallet_ranker = AlphaWalletRanker()
