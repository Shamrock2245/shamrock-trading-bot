#!/usr/bin/env python3
"""
scripts/monte_carlo_stress_test.py — Monte Carlo Strategy Validation
Injects randomized slippage and execution timing delays into historical trades
to ensure profitability is driven by structural edge, not overfitted random luck.
"""
import json
import logging
import random
import sys
from pathlib import Path
from typing import List, Dict
import numpy as np

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
)
logger = logging.getLogger("monte_carlo")

def load_trades() -> List[Dict]:
    trades_path = PROJECT_ROOT / "output" / "trades.json"
    if not trades_path.exists():
        logger.error(f"Trades file not found: {trades_path}")
        return []
    try:
        with open(trades_path, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load trades: {e}")
        return []

def run_monte_carlo(trades: List[Dict], iterations: int = 500, max_slippage_pct: float = 15.0) -> Dict:
    """
    Run Monte Carlo simulation on historical trades.
    Randomizes slippage penalty by ± max_slippage_pct for each trade.
    """
    if not trades:
        return {}

    logger.info(f"Running Monte Carlo Stress Test ({iterations} iterations)...")
    
    baseline_pnl = sum(t.get("pnl_usd", 0.0) for t in trades)
    baseline_win_rate = sum(1 for t in trades if t.get("pnl_usd", 0.0) > 0) / len(trades)
    
    iteration_pnls = []
    iteration_win_rates = []
    
    for i in range(iterations):
        simulated_pnl = 0.0
        wins = 0
        for trade in trades:
            original_pnl = trade.get("pnl_usd", 0.0)
            position_size = trade.get("value_usd", 100.0)
            
            # Inject random slippage penalty (e.g., up to 15% worse execution)
            # We assume slippage always hurts us (negative impact)
            slippage_impact = position_size * (random.uniform(0, max_slippage_pct) / 100.0)
            
            # 50% chance of delayed execution causing a missed entry entirely
            if random.random() < 0.05: # 5% chance trade drops due to timing
                adjusted_pnl = 0.0
            else:
                adjusted_pnl = original_pnl - slippage_impact
                
            simulated_pnl += adjusted_pnl
            if adjusted_pnl > 0:
                wins += 1
                
        iteration_pnls.append(simulated_pnl)
        iteration_win_rates.append(wins / len(trades))
        
    avg_simulated_pnl = np.mean(iteration_pnls)
    worst_case_pnl = np.min(iteration_pnls)
    avg_win_rate = np.mean(iteration_win_rates)
    
    survival_rate = sum(1 for p in iteration_pnls if p > 0) / iterations
    
    results = {
        "baseline_pnl": baseline_pnl,
        "baseline_win_rate": baseline_win_rate,
        "avg_simulated_pnl": avg_simulated_pnl,
        "worst_case_pnl": worst_case_pnl,
        "avg_simulated_win_rate": avg_win_rate,
        "survival_rate": survival_rate,
        "is_robust": survival_rate > 0.95
    }
    
    logger.info("=== Monte Carlo Results ===")
    logger.info(f"Baseline PnL: ${baseline_pnl:.2f} (Win Rate: {baseline_win_rate:.1%})")
    logger.info(f"Average Simulated PnL: ${avg_simulated_pnl:.2f} (Win Rate: {avg_win_rate:.1%})")
    logger.info(f"Worst Case PnL: ${worst_case_pnl:.2f}")
    logger.info(f"Strategy Survival Rate (>0 PnL): {survival_rate:.1%}")
    logger.info(f"Verdict: {'ROBUST ✅' if results['is_robust'] else 'OVERFITTED ❌'}")
    
    return results

if __name__ == "__main__":
    trades = load_trades()
    if trades:
        run_monte_carlo(trades)
    else:
        logger.warning("No trades available for Monte Carlo simulation. Run paper trading first.")
