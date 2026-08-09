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

XGBOOST_INTERVAL_SECONDS = 3600  # 1 hour
OPTUNA_INTERVAL_SECONDS = 3600  # 1 hour

def main():
    mode = getattr(settings, "MODE", os.getenv("MODE", "paper"))
    paper_locked = getattr(settings, "PAPER_MODE_LOCKED", True)
    campaign = getattr(settings, "PAPER_TUNING_CAMPAIGN_ENABLED", True)
    campaign_days = getattr(settings, "PAPER_TUNING_CAMPAIGN_DAYS", 21)

    logger.info("🤖 Auto-Tuning Service Started.")
    logger.info(
        f"Mode={mode} | PAPER_MODE_LOCKED={paper_locked} | "
        f"campaign={campaign} ({campaign_days}d) — tuning never places live orders"
    )
    logger.info(f"XGBoost Interval: {XGBOOST_INTERVAL_SECONDS}s")
    logger.info(f"Optuna Interval: {OPTUNA_INTERVAL_SECONDS}s")

    # Ensure campaign state file exists (starts the 2–3 week clock)
    try:
        from core.paper_to_live_promoter import _load_or_init_campaign_state
        _load_or_init_campaign_state(
            start_iso=getattr(settings, "PAPER_TUNING_CAMPAIGN_START", "") or "",
            days=int(campaign_days),
        )
    except Exception as e:
        logger.debug(f"Campaign state init skipped: {e}")

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

        # 3. Run Self-Improving AI Agent Audit (OpenAlice style)
        try:
            from core.self_improving_agent import improving_agent
            improving_agent.run_self_audit(force=False)
        except Exception as e:
            logger.error(f"❌ Self-Improving Agent audit failed: {e}")
            
        # Sleep for 15 minutes before checking again
        time.sleep(900)

if __name__ == "__main__":
    main()
