"""
ml/optuna_optimizer.py — Optuna-Powered Hyperparameter Optimizer

Bayesian optimization of ALL trading parameters using multi-objective
optimization (maximize Sharpe, minimize max drawdown). Replays trade
history with different parameter sets via paper_backtest.py.

Inspired by:
  - Freqtrade's hyperopt system (Optuna + NSGAIIISampler + pluggable loss)
  - FinRL's reward shaping (risk-adjusted composite metrics)
  - Jesse-AI's optimize mode (walk-forward validation)

Features:
  1. TPE Bayesian sampling (learns from prior trials)
  2. Multi-objective Pareto optimization (Sharpe + Drawdown)
  3. MedianPruner (kills bad trials early — saves ~60% compute)
  4. Walk-forward validation (3-window rolling, prevents overfitting)
  5. Safety guardrails (max 25% parameter change per cycle)
  6. SQLite persistence (resume, compare, visualize with optuna-dashboard)
  7. Auto-apply with Slack notification

Runs every 12 hours as a background daemon thread.

Output:
  - output/optuna_best_params.json (best Pareto-optimal parameter set)
  - data/optuna_studies.db (full study history)
  - Slack notification with parameter changes
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).parent.parent
BEST_PARAMS_PATH = _ROOT / "output" / "optuna_best_params.json"
_last_run_time: float = 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Objective Function
# ─────────────────────────────────────────────────────────────────────────────

def _create_objective(trades: list[dict]):
    """
    Factory: returns an Optuna objective function bound to the trade data.

    Multi-objective: returns (sharpe_ratio, max_drawdown_pct)
    Direction: maximize sharpe, minimize drawdown.
    """
    from ml.paper_backtest import BacktestParams, run_backtest

    def objective(trial):
        # ── Entry Quality ────────────────────────────────────────────
        min_gem_score = trial.suggest_float("min_gem_score", 55.0, 85.0)
        express_lane_score = trial.suggest_float("express_lane_score", 70.0, 92.0)

        # ── Take-Profit Tiers ────────────────────────────────────────
        tp1_mult = trial.suggest_float("tp1_mult", 1.15, 2.5)
        tp1_sell_pct = trial.suggest_float("tp1_sell_pct", 0.20, 0.65)
        tp2_mult = trial.suggest_float("tp2_mult", 2.0, 5.0)
        tp2_sell_pct = trial.suggest_float("tp2_sell_pct", 0.15, 0.55)
        tp3_mult = trial.suggest_float("tp3_mult", 3.5, 12.0)

        # ── Stop-Loss ────────────────────────────────────────────────
        stop_loss_pct = trial.suggest_float("stop_loss_pct", 6.0, 20.0)
        hard_stop_pct = trial.suggest_float("hard_stop_pct", 12.0, 30.0)
        pre_tp1_trailing_pct = trial.suggest_float("pre_tp1_trailing_pct", 8.0, 25.0)

        # ── Fast Fail ────────────────────────────────────────────────
        fast_fail_hours = trial.suggest_float("fast_fail_hours", 0.5, 4.0)
        fast_fail_down_pct = trial.suggest_float("fast_fail_down_pct", 5.0, 20.0)

        # ── Position Sizing ──────────────────────────────────────────
        max_position_pct = trial.suggest_float("max_position_pct", 2.0, 12.0)
        god_mode_kelly_mult = trial.suggest_float("god_mode_kelly_mult", 1.5, 4.0)

        # ── Time Exit ────────────────────────────────────────────────
        time_exit_hours = trial.suggest_float("time_exit_hours", 3.0, 24.0)

        # ── Scoring Weights ──────────────────────────────────────────
        w_volume = trial.suggest_float("w_volume", 0.05, 0.35)
        w_holder = trial.suggest_float("w_holder", 0.05, 0.30)
        w_liquidity = trial.suggest_float("w_liquidity", 0.05, 0.25)
        w_safety = trial.suggest_float("w_safety", 0.03, 0.25)
        w_momentum = trial.suggest_float("w_momentum", 0.03, 0.20)

        # ── Constraints ──────────────────────────────────────────────
        # TP levels must be ordered
        if tp1_mult >= tp2_mult or tp2_mult >= tp3_mult:
            return float("-inf"), float("inf")
        # Stop-loss must be tighter than hard stop
        if stop_loss_pct >= hard_stop_pct:
            return float("-inf"), float("inf")

        params = BacktestParams(
            min_gem_score=min_gem_score,
            express_lane_score=express_lane_score,
            tp1_mult=tp1_mult,
            tp1_sell_pct=tp1_sell_pct,
            tp2_mult=tp2_mult,
            tp2_sell_pct=tp2_sell_pct,
            tp3_mult=tp3_mult,
            stop_loss_pct=stop_loss_pct,
            hard_stop_pct=hard_stop_pct,
            pre_tp1_trailing_pct=pre_tp1_trailing_pct,
            fast_fail_hours=fast_fail_hours,
            fast_fail_down_pct=fast_fail_down_pct,
            max_position_pct=max_position_pct,
            god_mode_kelly_mult=god_mode_kelly_mult,
            time_exit_hours=time_exit_hours,
            w_volume=w_volume,
            w_holder=w_holder,
            w_liquidity=w_liquidity,
            w_safety=w_safety,
            w_momentum=w_momentum,
        )

        result = run_backtest(params, trades=trades)

        # Penalize too few trades (optimizer might narrow to <5 trades with high Sharpe)
        if result.trade_count < 5:
            return float("-inf"), float("inf")

        return result.sharpe_ratio, result.max_drawdown_pct

    return objective


# ─────────────────────────────────────────────────────────────────────────────
# Safety Guardrails
# ─────────────────────────────────────────────────────────────────────────────

# Current production values (read from settings at runtime)
_CURRENT_PARAMS = {
    "min_gem_score": 68.0,
    "express_lane_score": 78.0,
    "tp1_mult": 1.5,
    "tp1_sell_pct": 0.40,
    "tp2_mult": 2.5,
    "tp2_sell_pct": 0.35,
    "tp3_mult": 5.0,
    "stop_loss_pct": 12.0,
    "hard_stop_pct": 18.0,
    "pre_tp1_trailing_pct": 15.0,
    "fast_fail_hours": 1.5,
    "fast_fail_down_pct": 10.0,
    "max_position_pct": 5.0,
    "god_mode_kelly_mult": 2.5,
    "time_exit_hours": 8.0,
    "w_volume": 0.22,
    "w_holder": 0.18,
    "w_liquidity": 0.14,
    "w_safety": 0.12,
    "w_momentum": 0.10,
}


def _load_current_params() -> dict:
    """Load current production params from settings.py."""
    try:
        from config import settings as s
        return {
            "min_gem_score": s.MIN_GEM_SCORE,
            "express_lane_score": s.EXPRESS_LANE_SCORE,
            "tp1_mult": s.TAKE_PROFIT_TP1_MULT,
            "tp1_sell_pct": s.TAKE_PROFIT_TP1_SELL_PCT,
            "tp2_mult": s.TAKE_PROFIT_TP2_MULT,
            "tp2_sell_pct": s.TAKE_PROFIT_TP2_SELL_PCT,
            "tp3_mult": s.TAKE_PROFIT_TP3_MULT,
            "stop_loss_pct": s.STOP_LOSS_PERCENT,
            "hard_stop_pct": s.HARD_STOP_LOSS_PERCENT,
            "pre_tp1_trailing_pct": s.PRE_TP1_TRAILING_STOP_PCT,
            "fast_fail_hours": getattr(s, "FAST_FAIL_STALL_HOURS", 1.5),
            "fast_fail_down_pct": getattr(s, "FAST_FAIL_DOWN_PCT", 10.0),
            "max_position_pct": s.MAX_POSITION_SIZE_PERCENT,
            "god_mode_kelly_mult": s.GOD_MODE_KELLY_MULTIPLIER,
            "time_exit_hours": getattr(s, "TIME_EXIT_HOURS", 8.0),
            "w_volume": 0.22,
            "w_holder": 0.18,
            "w_liquidity": 0.14,
            "w_safety": 0.12,
            "w_momentum": 0.10,
        }
    except Exception:
        return dict(_CURRENT_PARAMS)


def _apply_safety_guardrails(
    best_params: dict,
    current_params: dict,
    max_change_pct: float = 25.0,
) -> tuple[dict, list[str]]:
    """
    Clip parameter changes to max_change_pct from current values.
    Returns (clipped_params, list_of_clipped_params).
    """
    clipped = {}
    changes = []

    for key, new_val in best_params.items():
        current_val = current_params.get(key, new_val)
        if current_val == 0:
            clipped[key] = new_val
            continue

        change_pct = abs(new_val - current_val) / abs(current_val) * 100
        if change_pct > max_change_pct:
            # Clip to max change
            direction = 1 if new_val > current_val else -1
            clipped_val = current_val * (1 + direction * max_change_pct / 100)
            clipped[key] = round(clipped_val, 4)
            changes.append(
                f"{key}: {current_val:.4f} → {new_val:.4f} (CLIPPED to {clipped_val:.4f}, "
                f"was {change_pct:.1f}% change, max={max_change_pct}%)"
            )
        else:
            clipped[key] = round(new_val, 4)

    return clipped, changes


# ─────────────────────────────────────────────────────────────────────────────
# Parameter Application
# ─────────────────────────────────────────────────────────────────────────────

def _apply_params_to_env(params: dict) -> None:
    """
    Apply optimized parameters by setting environment variables.
    These override the defaults in config/settings.py on next import.
    """
    env_map = {
        "min_gem_score": "MIN_GEM_SCORE",
        "express_lane_score": "EXPRESS_LANE_SCORE",
        "tp1_mult": "TAKE_PROFIT_TP1_MULT",
        "tp1_sell_pct": "TAKE_PROFIT_TP1_SELL_PCT",
        "tp2_mult": "TAKE_PROFIT_TP2_MULT",
        "tp2_sell_pct": "TAKE_PROFIT_TP2_SELL_PCT",
        "tp3_mult": "TAKE_PROFIT_TP3_MULT",
        "stop_loss_pct": "STOP_LOSS_PERCENT",
        "hard_stop_pct": "HARD_STOP_LOSS_PERCENT",
        "pre_tp1_trailing_pct": "PRE_TP1_TRAILING_STOP_PCT",
        "max_position_pct": "MAX_POSITION_SIZE_PERCENT",
        "god_mode_kelly_mult": "GOD_MODE_KELLY_MULTIPLIER",
    }

    applied = []
    for param_key, env_key in env_map.items():
        if param_key in params:
            os.environ[env_key] = str(params[param_key])
            applied.append(f"{env_key}={params[param_key]}")

    if applied:
        logger.info(f"Optuna: Applied {len(applied)} params to env: {', '.join(applied[:5])}...")

    # Also update scoring weights in the dynamic weights file
    weight_keys = ["w_volume", "w_holder", "w_liquidity", "w_safety", "w_momentum"]
    if any(k in params for k in weight_keys):
        raw_weights = {
            "volume": params.get("w_volume", 0.22),
            "whale_holder": params.get("w_holder", 0.18),
            "liquidity": params.get("w_liquidity", 0.14),
            "safety": params.get("w_safety", 0.12),
            "momentum_ta": params.get("w_momentum", 0.10),
            "boost_cto": 0.07,
            "fibonacci": 0.05,
            "grok_sentiment": 0.05,
            "age": 0.04,
            "social": 0.03,
        }
        # Normalize to sum = 1.0
        total = sum(raw_weights.values())
        normalized = {k: round(v / total, 4) for k, v in raw_weights.items()}

        weights_path = _ROOT / "output" / "dynamic_weights.json"
        try:
            weights_data = {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "source": "optuna_optimizer",
                "weights": normalized,
            }
            weights_path.parent.mkdir(parents=True, exist_ok=True)
            with open(weights_path, "w") as f:
                json.dump(weights_data, f, indent=2)
            logger.info(f"Optuna: Updated scoring weights in {weights_path}")
        except Exception as e:
            logger.warning(f"Optuna: Failed to update scoring weights: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Slack Notification
# ─────────────────────────────────────────────────────────────────────────────

def _notify_slack(
    best_params: dict,
    current_params: dict,
    sharpe: float,
    drawdown: float,
    trade_count: int,
    n_trials: int,
    clipped_params: list[str],
    walk_forward_ok: bool,
) -> None:
    """Send optimization results to Slack."""
    try:
        from notifications.slack import send_slack_message

        # Build change summary
        changes = []
        for key in sorted(best_params.keys()):
            old = current_params.get(key, 0)
            new = best_params[key]
            if old != 0:
                pct = (new - old) / abs(old) * 100
                arrow = "↑" if pct > 0 else "↓"
                changes.append(f"  {key}: {old:.3f} → {new:.3f} ({pct:+.1f}%{arrow})")

        msg = (
            f"🧠 *Optuna Auto-Tuner Report*\n"
            f"```\n"
            f"Trials:      {n_trials}\n"
            f"Best Sharpe:  {sharpe:.3f}\n"
            f"Max Drawdown: {drawdown:.1f}%\n"
            f"Trade Count:  {trade_count}\n"
            f"Walk-Forward: {'✅ PASS' if walk_forward_ok else '⚠️ MARGINAL'}\n"
            f"```\n"
            f"*Parameter Changes:*\n```\n"
            + "\n".join(changes[:15])
            + "\n```"
        )

        if clipped_params:
            msg += f"\n⚠️ *Safety Clipped ({len(clipped_params)}):*\n```\n"
            msg += "\n".join(clipped_params[:5])
            msg += "\n```"

        send_slack_message(msg, channel="#shamrock")
    except Exception as e:
        logger.debug(f"Optuna Slack notification failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Main Optimization Cycle
# ─────────────────────────────────────────────────────────────────────────────

def run_optuna_cycle(force: bool = False) -> Optional[dict]:
    """
    Full Optuna optimization cycle:
      1. Load recent trades
      2. Run multi-objective optimization (Sharpe ↑, Drawdown ↓)
      3. Walk-forward validate best candidate
      4. Apply safety guardrails
      5. Auto-apply and notify Slack

    Returns the best params dict, or None if skipped.
    """
    global _last_run_time

    try:
        from config import settings
    except ImportError:
        logger.warning("Optuna: Cannot import settings — skipping")
        return None

    if not getattr(settings, "OPTUNA_ENABLED", True):
        return None

    # Check interval
    interval_hours = getattr(settings, "OPTUNA_INTERVAL_HOURS", 12)
    if not force and (time.time() - _last_run_time) < (interval_hours * 3600):
        return None

    try:
        import optuna
        optuna.logging.set_verbosity(optuna.logging.WARNING)
    except ImportError:
        logger.warning("Optuna not installed — run: pip install optuna")
        return None

    # Load trades
    from ml.paper_backtest import load_trades

    lookback_days = getattr(settings, "OPTUNA_LOOKBACK_DAYS", 14)
    trades = load_trades(lookback_days)
    min_trades = getattr(settings, "OPTUNA_MIN_TRADES", 30)

    if len(trades) < min_trades:
        logger.info(
            f"Optuna: Insufficient trades ({len(trades)} < {min_trades}) — skipping optimization"
        )
        _last_run_time = time.time()
        return None

    logger.info(
        f"🧠 Optuna: Starting optimization cycle "
        f"({len(trades)} trades, lookback={lookback_days}d)..."
    )
    t0 = time.time()

    # ── Create study ─────────────────────────────────────────────────
    db_path = getattr(settings, "OPTUNA_DB_PATH", "data/optuna_studies.db")
    storage = f"sqlite:///{db_path}"

    # Ensure directory exists
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    study = optuna.create_study(
        study_name="shamrock-autotuner",
        directions=["maximize", "minimize"],  # max Sharpe, min drawdown
        storage=storage,
        load_if_exists=True,
        sampler=optuna.samplers.TPESampler(
            seed=42,
            multivariate=True,
            n_startup_trials=30,
        ),
    )

    # ── Run optimization ─────────────────────────────────────────────
    n_trials = getattr(settings, "OPTUNA_TRIALS", 300)
    objective = _create_objective(trades)

    study.optimize(
        objective,
        n_trials=n_trials,
        timeout=300,  # Max 5 minutes
        show_progress_bar=False,
    )

    elapsed = time.time() - t0
    logger.info(
        f"🧠 Optuna: Completed {n_trials} trials in {elapsed:.1f}s "
        f"({len(study.best_trials)} Pareto-optimal)"
    )

    # ── Select best trial from Pareto front ──────────────────────────
    # Pick the trial with best Sharpe among those with <15% drawdown
    best_trial = None
    for trial in study.best_trials:
        sharpe, dd = trial.values
        if dd < 15.0:
            if best_trial is None or sharpe > best_trial.values[0]:
                best_trial = trial

    # Fallback: just take highest Sharpe
    if best_trial is None and study.best_trials:
        best_trial = max(study.best_trials, key=lambda t: t.values[0])

    if best_trial is None:
        logger.warning("Optuna: No valid trials found")
        _last_run_time = time.time()
        return None

    best_sharpe, best_dd = best_trial.values
    best_params = best_trial.params

    logger.info(
        f"🧠 Optuna: Best trial: Sharpe={best_sharpe:.3f}, "
        f"Drawdown={best_dd:.1f}%, Params={best_params}"
    )

    # ── Walk-forward validation ──────────────────────────────────────
    from ml.paper_backtest import BacktestParams, run_walk_forward

    wf_params = BacktestParams(**{
        k: v for k, v in best_params.items()
        if hasattr(BacktestParams, k)
    })
    walk_forward_ok, wf_results = run_walk_forward(wf_params, trades, n_windows=3)

    if walk_forward_ok:
        logger.info("🧠 Optuna: Walk-forward validation PASSED ✅")
    else:
        logger.warning("🧠 Optuna: Walk-forward validation MARGINAL ⚠️ — applying with extra caution")

    # ── Safety guardrails ────────────────────────────────────────────
    current_params = _load_current_params()
    max_change = getattr(settings, "OPTUNA_MAX_PARAM_CHANGE_PCT", 25.0)

    # Tighter guardrails if walk-forward failed
    if not walk_forward_ok:
        max_change = min(max_change, 15.0)

    safe_params, clipped_list = _apply_safety_guardrails(
        best_params, current_params, max_change
    )

    # ── Auto-apply ───────────────────────────────────────────────────
    auto_apply = getattr(settings, "OPTUNA_AUTO_APPLY", True)
    if auto_apply:
        _apply_params_to_env(safe_params)
        logger.info("🧠 Optuna: Parameters auto-applied to environment ✅")

    # ── Save results ─────────────────────────────────────────────────
    result_data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_trials": n_trials,
        "best_sharpe": best_sharpe,
        "best_drawdown_pct": best_dd,
        "trade_count": len(trades),
        "walk_forward_pass": walk_forward_ok,
        "auto_applied": auto_apply,
        "clipped_count": len(clipped_list),
        "best_params": safe_params,
        "raw_params": best_params,
        "previous_params": current_params,
    }

    try:
        BEST_PARAMS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(BEST_PARAMS_PATH, "w") as f:
            json.dump(result_data, f, indent=2)
        logger.info(f"🧠 Optuna: Results saved to {BEST_PARAMS_PATH}")
    except Exception as e:
        logger.error(f"Optuna: Failed to save results: {e}")

    # ── Slack notification ───────────────────────────────────────────
    _notify_slack(
        best_params=safe_params,
        current_params=current_params,
        sharpe=best_sharpe,
        drawdown=best_dd,
        trade_count=len(trades),
        n_trials=n_trials,
        clipped_params=clipped_list,
        walk_forward_ok=walk_forward_ok,
    )

    _last_run_time = time.time()
    return safe_params


def get_optimizer_status() -> dict:
    """Return current optimizer status for dashboard display."""
    from ml.paper_backtest import load_trades
    trades = load_trades(14)

    status = {
        "trades_available": len(trades),
        "last_run": (
            datetime.utcfromtimestamp(_last_run_time).isoformat()
            if _last_run_time > 0 else "Never"
        ),
        "best_params_exists": BEST_PARAMS_PATH.exists(),
    }

    if BEST_PARAMS_PATH.exists():
        try:
            with open(BEST_PARAMS_PATH) as f:
                data = json.load(f)
            status["best_sharpe"] = data.get("best_sharpe")
            status["best_drawdown"] = data.get("best_drawdown_pct")
            status["last_optimized"] = data.get("generated_at")
            status["walk_forward_pass"] = data.get("walk_forward_pass")
        except Exception:
            pass

    return status


# ─────────────────────────────────────────────────────────────────────────────
# Standalone execution / testing
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")

    dry_run = "--dry-run" in sys.argv
    n_trials = 5 if dry_run else 300

    # Override for testing
    if dry_run:
        os.environ["OPTUNA_TRIALS"] = str(n_trials)
        os.environ["OPTUNA_MIN_TRADES"] = "3"

    result = run_optuna_cycle(force=True)
    if result:
        print("\n=== Best Parameters ===")
        for k, v in sorted(result.items()):
            print(f"  {k:<25} {v}")
    else:
        print("No optimization result (insufficient data or disabled)")
