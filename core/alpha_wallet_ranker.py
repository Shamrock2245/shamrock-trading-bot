"""
Alpha Wallet Ranker (ECC Skill: social-graph-ranker adapted)
Analyzes historical performance of tracked alpha wallets and generates 
a dynamic size multiplier to cut off losing streaks and compound winners.
"""

import json
import logging
from pathlib import Path
from core.position_monitor import load_positions

logger = logging.getLogger(__name__)

SCORES_FILE = Path("data/wallet_scores.json")
SCORES_FILE.parent.mkdir(parents=True, exist_ok=True)

class AlphaWalletRanker:
    def __init__(self, base_multiplier=1.0, max_multiplier=3.0, min_multiplier=0.1):
        self.base_multiplier = base_multiplier
        self.max_multiplier = max_multiplier
        self.min_multiplier = min_multiplier

    def recalculate_scores(self):
        """
        Reads closed positions and computes win-rate and ROI per alpha wallet.
        Writes the results to wallet_scores.json
        """
        positions = load_positions()
        closed_positions = [p for p in positions if p.get("status") == "closed"]

        stats = {}
        for p in closed_positions:
            wallet = p.get("wallet", "unknown")
            if wallet not in stats:
                stats[wallet] = {"trades": 0, "wins": 0, "total_roi": 0.0}
            
            stats[wallet]["trades"] += 1
            roi = p.get("realized_pnl_pct", 0)
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
            
        try:
            with open(SCORES_FILE, "w") as f:
                json.dump(scores, f, indent=2)
            logger.info(f"Updated Alpha Wallet scores: {scores}")
        except Exception as e:
            logger.error(f"Failed to write wallet scores: {e}")

    @staticmethod
    def get_multiplier(wallet_alias: str) -> float:
        """
        Fast RAM read for fastlane execution. 
        """
        try:
            if SCORES_FILE.exists():
                with open(SCORES_FILE, "r") as f:
                    scores = json.load(f)
                return scores.get(wallet_alias, 1.0)
        except Exception:
            return 1.0
        return 1.0

wallet_ranker = AlphaWalletRanker()
