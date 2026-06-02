"""
Benchmark Optimization Loop (ECC Skill: benchmark-optimization-loop)
Reads the Recursive Decision Ledger and backtests parameters to find optimal settings.
"""

import os
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

LEDGER_DIR = Path("logs/decision_ledger")

def run_benchmark():
    """
    Simulates parsing the ledger files to find optimization opportunities.
    In a real scenario, this would query Moralis Historical API for actual 
    outcomes of rejected trades to see if the bot "missed" out.
    """
    logger.info("Starting Benchmark Optimization Loop...")
    
    if not LEDGER_DIR.exists():
        logger.warning(f"No ledger directory found at {LEDGER_DIR}")
        return

    accepts = 0
    rejects = 0
    reasons = {}

    for file_path in LEDGER_DIR.glob("*.jsonl"):
        with open(file_path, 'r') as f:
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
                except Exception as e:
                    continue
                    
    logger.info(f"Analyzed {accepts + rejects} decisions ({accepts} accepts, {rejects} rejects).")
    
    if rejects > 0:
        logger.info("Top Rejection Reasons:")
        sorted_reasons = sorted(reasons.items(), key=lambda x: x[1], reverse=True)
        for r, count in sorted_reasons[:5]:
            logger.info(f" - {r}: {count}")
            
    # Auto-optimization logic
    if accepts == 0 and rejects > 10:
        logger.info("Recommendation: Lowering MIN_GEM_SCORE to increase trade frequency.")
        _update_env_var("MIN_GEM_SCORE", "40.0")  # Example adjustment
        logger.info("✅ Auto-applied optimization. Will take effect on next bot restart.")
    elif accepts > 10 and (reasons.get("Stale signal", 0) > 5):
        logger.info("Recommendation: Tightening latency SLO to reduce stale signals.")
        _update_env_var("COPYTRADE_LATENCY_SLO_SECONDS", "3.0")
        logger.info("✅ Auto-applied latency optimization.")

def _update_env_var(key: str, value: str):
    env_path = Path(".env")
    if not env_path.exists():
        return
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

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_benchmark()
