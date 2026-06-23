#!/usr/bin/env python3
"""
scripts/auto_tuner_service.py — Standalone Auto-Tuning Service

Runs independently from the main trading bot.
Periodically invokes ML weight optimization (XGBoost) and hyperparameter tuning (Optuna)
to ensure the bot's weights and TP/SL ratios remain state-of-the-art without blocking
the main thread.

Usage:
  python3 scripts/auto_tuner_service.py
"""

import time
import logging
import sys
import os

# Ensure the root directory is in the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ml.weight_optimizer import run_training_cycle
from ml.optuna_optimizer import run_optuna_cycle
from config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("AutoTunerService")

XGBOOST_INTERVAL_SECONDS = 6 * 3600  # 6 hours
OPTUNA_INTERVAL_SECONDS = 12 * 3600  # 12 hours

def main():
    logger.info("🤖 Auto-Tuning Service Started.")
    logger.info(f"XGBoost Interval: {XGBOOST_INTERVAL_SECONDS}s")
    logger.info(f"Optuna Interval: {OPTUNA_INTERVAL_SECONDS}s")

    last_xgb_run = 0
    last_optuna_run = 0

    while True:
        now = time.time()
        
        # 1. Run XGBoost Weight Optimizer
        if now - last_xgb_run > XGBOOST_INTERVAL_SECONDS:
            if settings.ML_WEIGHT_OPTIMIZER_ENABLED:
                logger.info("🚀 Triggering XGBoost Weight Optimization cycle...")
                try:
                    run_training_cycle()
                except Exception as e:
                    logger.error(f"❌ XGBoost cycle failed: {e}")
                last_xgb_run = time.time()
            else:
                logger.info("⏸️ XGBoost Weight Optimizer disabled via config.")
                last_xgb_run = time.time()

        # 2. Run Optuna Hyperparameter Optimizer
        if now - last_optuna_run > OPTUNA_INTERVAL_SECONDS:
            logger.info("🚀 Triggering Optuna Hyperparameter Optimization cycle...")
            try:
                run_optuna_cycle(force=False)
            except Exception as e:
                logger.error(f"❌ Optuna cycle failed: {e}")
            last_optuna_run = time.time()
            
        # Sleep for 15 minutes before checking again
        time.sleep(900)

if __name__ == "__main__":
    main()
