"""
Benchmark Optimization Loop (ECC Skill: benchmark-optimization-loop adapted)
Runs continuously in the background to dynamically adapt risk management parameters.

This script parses the Recursive Decision Ledger and historical trade outcomes
to simulate thousands of alternative scenarios using different take-profit (TP),
stop-loss (SL), and trailing stop parameters against recent market data.
It pushes the most profitable parameter set to the live bot.
"""

import os
import json
import time
import logging
import threading
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional

from config import settings
from core.position_monitor import load_positions

logger = logging.getLogger(__name__)

LEDGER_DIR = Path("logs/decision_ledger")
TRADES_FILE = Path(getattr(settings, "TRADES_FILE", "output/trades.json"))

class BenchmarkOptimizationLoop:
    def __init__(self):
        self.running = False
        # Interval is env-configurable — default 6h per audit spec
        self.interval_s = int(os.getenv("BENCHMARK_INTERVAL_SECONDS", str(6 * 3600)))
        self._thread: Optional[threading.Thread] = None

    def start(self):
        """Starts the continuous background optimization loop."""
        if self.running:
            return
            
        self.running = True
        self._thread = threading.Thread(target=self._run_loop, name="BenchmarkLoop", daemon=True)
        self._thread.start()
        logger.info("✅ Benchmark Optimization Loop started.")

    def stop(self):
        """Stops the loop."""
        self.running = False
        if self._thread:
            self._thread.join(timeout=2.0)

    def _run_loop(self):
        """Main background loop."""
        while self.running:
            try:
                self._run_optimization_cycle()
            except Exception as e:
                logger.error(f"Benchmark loop error: {e}", exc_info=True)
                
            # Sleep in small increments to allow clean shutdown
            for _ in range(self.interval_s):
                if not self.running:
                    break
                time.sleep(1)

    def _run_optimization_cycle(self):
        """
        Executes one full optimization cycle:
        1. Analyzes recent trades.
        2. Simulates alternative TP/SL parameters.
        3. Applies the optimal configuration to the live environment.
        """
        logger.info("Starting Benchmark Optimization Cycle...")
        
        # 1. Recalculate alpha wallet scores
        try:
            from core.alpha_wallet_ranker import wallet_ranker
            logger.info("Recalculating Alpha Wallet Rankings...")
            wallet_ranker.recalculate_scores()
        except ImportError:
            logger.warning("Could not import alpha_wallet_ranker. Skipping score recalculation.")
            
        # 2. Analyze decision ledger
        self._analyze_ledger()
        
        # 3. Optimize parameters based on historical trades
        self._optimize_parameters()

    def _analyze_ledger(self):
        """Analyzes the decision ledger to find bottlenecks."""
        if not LEDGER_DIR.exists():
            logger.warning(f"No ledger directory found at {LEDGER_DIR}")
            return
            
        accepts = 0
        rejects = 0
        reasons: Dict[str, int] = {}
        
        # Only look at the current month's ledger to save memory
        from datetime import datetime, timezone
        current_ledger = LEDGER_DIR / f"ledger_{datetime.now(timezone.utc).strftime('%Y-%m')}.jsonl"
        
        if not current_ledger.exists():
            return
            
        try:
            with open(current_ledger, 'r') as f:
                for line in f:
                    try:
                        data = json.loads(line)
                        decision = data.get("decision")
                        reason = data.get("reason", "Unknown")
                        
                        if decision == "ACCEPT":
                            accepts += 1
                        else:
                            rejects += 1
                            reasons[reason] = reasons.get(reason, 0) + 1
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.error(f"Failed to read ledger {current_ledger}: {e}")
            return
            
        logger.info(f"Analyzed recent decisions: {accepts} accepts, {rejects} rejects.")
        
        if rejects > 0:
            logger.info("Top Rejection Reasons:")
            sorted_reasons = sorted(reasons.items(), key=lambda x: x[1], reverse=True)
            for r, count in sorted_reasons[:5]:
                logger.info(f" - {r}: {count}")
                
        # Auto-optimization logic for trade frequency
        if accepts == 0 and rejects > 20:
            logger.info("Recommendation: Lowering MIN_GEM_SCORE to increase trade frequency.")
            self._update_env_var("MIN_GEM_SCORE", "60.0")  # Adjust floor
            logger.info("✅ Auto-applied MIN_GEM_SCORE optimization.")
        elif accepts > 10 and (reasons.get("Stale signal", 0) > 10):
            logger.info("Recommendation: Tightening latency SLO to reduce stale signals.")
            self._update_env_var("COPYTRADE_LATENCY_SLO_SECONDS", "3.0")
            logger.info("✅ Auto-applied latency optimization.")

    def _optimize_parameters(self):
        """
        Simulates different TP/SL parameters on recent trades to find the optimal set.
        """
        trades = self._load_recent_trades()
        if not trades or len(trades) < 10:
            logger.info("Not enough recent trades to run parameter optimization.")
            return
            
        logger.info(f"Running parameter optimization on {len(trades)} recent trades...")
        
        # Define parameter grid to test
        sl_options = [8.0, 10.0, 12.0, 15.0, 20.0]
        tp1_options = [1.3, 1.5, 2.0]
        trail_options = [10.0, 15.0, 20.0]
        
        best_params = None
        best_pnl = -float('inf')
        
        # Current baseline PnL
        baseline_pnl = sum(t.get("realized_pnl_usd", 0) for t in trades)
        
        for sl in sl_options:
            for tp1 in tp1_options:
                for trail in trail_options:
                    simulated_pnl = self._simulate_trades(trades, sl, tp1, trail)
                    if simulated_pnl > best_pnl:
                        best_pnl = simulated_pnl
                        best_params = (sl, tp1, trail)
                        
        if best_params and best_pnl > baseline_pnl * 1.05: # Only update if 5% better
            sl, tp1, trail = best_params
            logger.info(f"Found optimal parameters! Simulated PnL: ${best_pnl:.2f} (Baseline: ${baseline_pnl:.2f})")
            logger.info(f"Applying: SL={sl}%, TP1={tp1}x, Trail={trail}%")
            
            self._update_env_var("HARD_STOP_LOSS_PERCENT", str(sl))
            self._update_env_var("TAKE_PROFIT_TP1_MULT", str(tp1))
            self._update_env_var("STOP_LOSS_PERCENT", str(trail))  # Trailing stop
            
            logger.info("✅ Dynamically adapted risk management parameters.")
        else:
            logger.info("Current parameters are optimal. No changes applied.")

    def _load_recent_trades(self, limit: int = 100) -> List[Dict]:
        """Loads the most recent completed trades."""
        if not TRADES_FILE.exists():
            return []
            
        try:
            with open(TRADES_FILE, 'r') as f:
                trades = json.load(f)
                return trades[-limit:] if trades else []
        except Exception as e:
            logger.error(f"Failed to load trades for optimization: {e}")
            return []

    def _simulate_trades(self, trades: List[Dict], sl_pct: float, tp1_mult: float, trail_pct: float) -> float:
        """
        Simulates the PnL of a set of trades using given parameters.
        Note: In a full production environment, this requires high-resolution tick data.
        This is a simplified heuristic model based on recorded max_price and min_price.
        """
        simulated_pnl = 0.0
        
        for trade in trades:
            entry_price = trade.get("entry_price", 0)
            max_price = trade.get("highest_price_seen", entry_price)
            min_price = trade.get("lowest_price_seen", entry_price)
            position_size = trade.get("entry_value_usd", 100)
            
            if entry_price <= 0:
                continue
                
            # Heuristic simulation
            # Did it hit the hard stop loss before hitting TP1?
            sl_price = entry_price * (1 - sl_pct / 100)
            tp1_price = entry_price * tp1_mult
            
            # If max_price never reached TP1, and min_price hit SL, it's a loss
            if max_price < tp1_price and min_price <= sl_price:
                simulated_pnl -= position_size * (sl_pct / 100)
            # If it hit TP1
            elif max_price >= tp1_price:
                # Simplified: Assume we capture TP1 profit
                simulated_pnl += position_size * 0.4 * (tp1_mult - 1)
                
                # And the rest is stopped out at trailing stop from max price
                trail_price = max_price * (1 - trail_pct / 100)
                exit_price = max(trail_price, entry_price) # Assume worst case is breakeven after TP1
                
                simulated_pnl += position_size * 0.6 * ((exit_price / entry_price) - 1)
            else:
                # It just hovered, use actual recorded PnL
                simulated_pnl += trade.get("realized_pnl_usd", 0)
                
        return simulated_pnl

    def _update_env_var(self, key: str, value: str):
        """Safely updates an environment variable in the .env file."""
        env_path = Path(".env")
        if not env_path.exists():
            return
            
        try:
            lines = env_path.read_text().splitlines()
            updated = False
            
            for i, line in enumerate(lines):
                if line.startswith(f"{key}="):
                    lines[i] = f"{key}={value}"
                    updated = True
                    break
                    
            if not updated:
                lines.append(f"{key}={value}")
                
            env_path.write_text("\n".join(lines) + "\n")
            
            # Update running config
            setattr(settings, key, type(getattr(settings, key, 0.0))(value))
            
        except Exception as e:
            logger.error(f"Failed to update env var {key}: {e}")

def start_benchmark_loop():
    loop = BenchmarkOptimizationLoop()
    loop.start()
    return loop


def run_benchmark():
    """Run a single benchmark optimization cycle synchronously (for daemon use)."""
    loop = BenchmarkOptimizationLoop()
    loop._run_optimization_cycle()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    loop = BenchmarkOptimizationLoop()
    loop._run_optimization_cycle()
