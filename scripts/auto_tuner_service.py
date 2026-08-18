#!/usr/bin/env python3
"""
scripts/auto_tuner_service.py — Standalone Auto-Tuning Service

Runs independently from the main trading bot.
Periodically invokes the full tuner suite against paper-journaled trades
and writes results to shared output/ files. The bot process reloads those
files (runtime overlay + optuna_best_params.json) without placing live orders.

Usage:
  python3 scripts/auto_tuner_service.py
"""

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Ensure the root directory is in the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("AutoTunerService")

STATUS_PATH = Path(os.getenv("AUTO_TUNER_STATUS_FILE", "output/auto_tuner_status.json"))


def _interval(name: str, default: float) -> float:
    try:
        return float(getattr(settings, name, default))
    except (TypeError, ValueError):
        return default


def _write_status(status: dict) -> None:
    try:
        STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(status)
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        tmp = STATUS_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2))
        tmp.replace(STATUS_PATH)
    except Exception as e:
        logger.debug(f"status write failed: {e}")


def main():
    mode = getattr(settings, "MODE", os.getenv("MODE", "paper"))
    paper_locked = getattr(settings, "PAPER_MODE_LOCKED", True)
    campaign = getattr(settings, "PAPER_TUNING_CAMPAIGN_ENABLED", True)
    campaign_days = getattr(settings, "PAPER_TUNING_CAMPAIGN_DAYS", 21)

    xgb_interval = _interval("ML_WEIGHT_RETRAIN_HOURS", 6.0) * 3600
    optuna_interval = _interval("OPTUNA_INTERVAL_HOURS", 12.0) * 3600
    sia_interval = _interval("SELF_IMPROVEMENT_INTERVAL_SECONDS", 86400.0)
    llm_interval = 1800.0
    rl_interval = float(os.getenv("RL_TRAINING_INTERVAL_HOURS", "24")) * 3600

    logger.info("🤖 Auto-Tuning Service Started.")
    logger.info(
        f"Mode={mode} | PAPER_MODE_LOCKED={paper_locked} | "
        f"campaign={campaign} ({campaign_days}d) — tuning never places live orders"
    )
    logger.info(
        f"Intervals: XGBoost={xgb_interval:.0f}s Optuna={optuna_interval:.0f}s "
        f"SelfImprove={sia_interval:.0f}s LLM={llm_interval:.0f}s RL={rl_interval:.0f}s"
    )

    try:
        from core.paper_to_live_promoter import _load_or_init_campaign_state
        _load_or_init_campaign_state(
            start_iso=getattr(settings, "PAPER_TUNING_CAMPAIGN_START", "") or "",
            days=int(campaign_days),
        )
    except Exception as e:
        logger.debug(f"Campaign state init skipped: {e}")

    last = {
        "xgboost": 0.0,
        "optuna": 0.0,
        "self_improve": 0.0,
        "llm": 0.0,
        "rl": 0.0,
    }
    last_ok = {k: None for k in last}
    last_err = {k: None for k in last}

    while True:
        now = time.time()

        if now - last["xgboost"] > xgb_interval:
            last["xgboost"] = now
            if settings.ML_WEIGHT_OPTIMIZER_ENABLED:
                logger.info("🚀 Triggering XGBoost Weight Optimization cycle...")
                try:
                    from ml.weight_optimizer import run_training_cycle
                    run_training_cycle()
                    last_ok["xgboost"] = datetime.now(timezone.utc).isoformat()
                    last_err["xgboost"] = None
                except Exception as e:
                    logger.error(f"❌ XGBoost cycle failed: {e}")
                    last_err["xgboost"] = str(e)
            else:
                logger.info("⏸️ XGBoost Weight Optimizer disabled via config.")

        if now - last["optuna"] > optuna_interval:
            last["optuna"] = now
            logger.info("🚀 Triggering Optuna Hyperparameter Optimization cycle...")
            try:
                from ml.optuna_optimizer import run_optuna_cycle
                run_optuna_cycle(force=False)
                last_ok["optuna"] = datetime.now(timezone.utc).isoformat()
                last_err["optuna"] = None
            except Exception as e:
                logger.error(f"❌ Optuna cycle failed: {e}")
                last_err["optuna"] = str(e)

        if now - last["self_improve"] > min(sia_interval, 3600.0):
            last["self_improve"] = now
            try:
                from core.self_improving_agent import improving_agent
                improving_agent.run_self_audit(force=False)
                last_ok["self_improve"] = datetime.now(timezone.utc).isoformat()
                last_err["self_improve"] = None
            except Exception as e:
                logger.error(f"❌ Self-Improving Agent audit failed: {e}")
                last_err["self_improve"] = str(e)

        if now - last["llm"] > llm_interval:
            last["llm"] = now
            try:
                from core.llm_auto_tuner import run_auto_tuner_cycle
                run_auto_tuner_cycle(force=False)
                last_ok["llm"] = datetime.now(timezone.utc).isoformat()
                last_err["llm"] = None
            except Exception as e:
                logger.error(f"❌ LLM Auto-Tuner cycle failed: {e}")
                last_err["llm"] = str(e)

        if now - last["rl"] > min(rl_interval, 3600.0):
            last["rl"] = now
            try:
                from ml.rl_position_sizer import train_rl_agent
                train_rl_agent(force=False)
                last_ok["rl"] = datetime.now(timezone.utc).isoformat()
                last_err["rl"] = None
            except Exception as e:
                logger.error(f"❌ RL position sizer cycle failed: {e}")
                last_err["rl"] = str(e)

        _write_status({
            "mode": mode,
            "paper_locked": paper_locked,
            "last_ok": last_ok,
            "last_error": last_err,
            "intervals_seconds": {
                "xgboost": xgb_interval,
                "optuna": optuna_interval,
                "self_improve": sia_interval,
                "llm": llm_interval,
                "rl": rl_interval,
            },
        })

        time.sleep(60)


if __name__ == "__main__":
    main()
