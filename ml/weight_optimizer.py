"""
ml/weight_optimizer.py — XGBoost-Powered Dynamic Indicator Weight Optimizer

Reads the trade journal (output/trades.json) and trains an XGBoost classifier
to predict which signal sub-scores actually drive profitable trades in the
current 7-day market window. The resulting feature importances are translated
into dynamic scoring weights that override the static defaults in gem_scanner.py.

How it works:
  1. Load all closed trades from output/trades.json
  2. Filter to trades in the last LOOKBACK_DAYS (default: 7)
  3. Build feature matrix from signal sub-scores stored at buy time
  4. Label each trade: 1 = profitable (pnl_pct > WIN_THRESHOLD), 0 = loss
  5. Train XGBoost classifier on features → profit label
  6. Extract feature importances (which signals predicted wins?)
  7. Normalize importances into weights that sum to 1.0
  8. Save to output/dynamic_weights.json
  9. gem_scanner.py loads these weights at the start of each scan cycle

The weights are recalculated every RETRAIN_INTERVAL_HOURS (default: 6).
If fewer than MIN_TRADES_REQUIRED trades exist, static defaults are used.

Signal features used (must match GemCandidate fields):
  - age_score
  - volume_score
  - liquidity_score
  - holder_score
  - social_score
  - boost_score
  - grok_score
  - moralis_score
  - safety_score
  - momentum_score
  - fib_score
  - gem_score (composite — used as a meta-feature)

Output: output/dynamic_weights.json
  {
    "generated_at": "2025-01-01T00:00:00Z",
    "lookback_days": 7,
    "trade_count": 42,
    "win_rate": 0.62,
    "weights": {
      "volume": 0.24,
      "whale_holder": 0.19,
      "liquidity": 0.15,
      "safety": 0.11,
      "momentum_ta": 0.09,
      "boost_cto": 0.07,
      "fibonacci": 0.05,
      "grok_sentiment": 0.05,
      "age": 0.03,
      "social": 0.02
    },
    "model_accuracy": 0.71,
    "feature_importances": { ... }
  }
"""

import json
import logging
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────
LOOKBACK_DAYS = int(os.getenv("ML_LOOKBACK_DAYS", "7"))
MIN_TRADES_REQUIRED = int(os.getenv("ML_MIN_TRADES", "20"))
WIN_THRESHOLD_PCT = float(os.getenv("ML_WIN_THRESHOLD_PCT", "15.0"))  # >15% = win
RETRAIN_INTERVAL_HOURS = float(os.getenv("ML_RETRAIN_INTERVAL_HOURS", "6.0"))

# Paths
_ROOT = Path(__file__).parent.parent
TRADES_PATH = _ROOT / "output" / "trades.json"
WEIGHTS_PATH = _ROOT / "output" / "dynamic_weights.json"
MODEL_PATH = _ROOT / "output" / "ml_model.json"

# Static fallback weights (used when insufficient trade data)
# These match the current gem_scanner.py scoring weights
STATIC_WEIGHTS = {
    "volume": 0.22,
    "whale_holder": 0.18,
    "liquidity": 0.14,
    "safety": 0.12,
    "momentum_ta": 0.10,
    "boost_cto": 0.07,
    "fibonacci": 0.05,
    "grok_sentiment": 0.05,
    "age": 0.04,
    "social": 0.03,
}

# Mapping: weight category → GemCandidate sub-score fields
# Multiple fields per category are averaged
FEATURE_MAP = {
    "volume": ["volume_score"],
    "whale_holder": ["holder_score"],
    "liquidity": ["liquidity_score"],
    "safety": ["safety_score"],
    "momentum_ta": ["momentum_score"],
    "boost_cto": ["boost_score"],
    "fibonacci": ["fib_score"],
    "grok_sentiment": ["grok_score"],
    "age": ["age_score"],
    "social": ["social_score"],
}

# All individual feature columns for the XGBoost model
FEATURE_COLS = [
    "age_score", "volume_score", "liquidity_score", "holder_score",
    "social_score", "boost_score", "grok_score", "moralis_score",
    "safety_score", "momentum_score", "fib_score",
]


# ─────────────────────────────────────────────────────────────────────────────
# Data Loading
# ─────────────────────────────────────────────────────────────────────────────

def load_trades(lookback_days: int = LOOKBACK_DAYS) -> list[dict]:
    """
    Load closed trades from output/trades.json.
    Filters to the last `lookback_days` days and only SELL records
    (which contain the final PnL outcome).
    """
    if not TRADES_PATH.exists():
        logger.warning(f"trades.json not found at {TRADES_PATH}")
        return []

    try:
        with open(TRADES_PATH, "r") as f:
            all_trades = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"Failed to load trades.json: {e}")
        return []

    if not isinstance(all_trades, list):
        logger.warning("trades.json is not a list — skipping ML training")
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    recent_sells = []

    for trade in all_trades:
        # Only use SELL records — they have the final PnL
        if trade.get("action", "").upper() != "SELL":
            continue
        # Parse timestamp
        try:
            ts_str = trade.get("timestamp", "")
            if ts_str:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if ts < cutoff:
                    continue
        except Exception:
            continue
        # Must have pnl_pct for labeling
        if trade.get("pnl_pct") is None:
            continue
        recent_sells.append(trade)

    logger.info(f"ML: Loaded {len(recent_sells)} closed trades from last {lookback_days} days")
    return recent_sells


def _extract_features(trade: dict) -> Optional[dict]:
    """
    Extract signal sub-score features from a trade record.
    Returns None if insufficient data.
    """
    features = {}
    for col in FEATURE_COLS:
        val = trade.get(col)
        if val is None:
            # Try nested signal_scores dict
            val = trade.get("signal_scores", {}).get(col)
        features[col] = float(val) if val is not None else 0.0

    # At least some non-zero features required
    if sum(features.values()) == 0:
        return None

    return features


# ─────────────────────────────────────────────────────────────────────────────
# Model Training
# ─────────────────────────────────────────────────────────────────────────────

def train_weight_model(trades: list[dict]) -> Optional[dict]:
    """
    Train an XGBoost classifier on trade outcomes and extract feature importances.

    Returns a dict with weights and metadata, or None if training fails.
    """
    try:
        import numpy as np
        from xgboost import XGBClassifier
        from sklearn.model_selection import cross_val_score
        from sklearn.preprocessing import StandardScaler
    except ImportError as e:
        logger.error(f"ML dependencies not installed: {e}. Run: pip install xgboost scikit-learn")
        return None

    # Build feature matrix and labels
    X_rows = []
    y_labels = []

    for trade in trades:
        features = _extract_features(trade)
        if features is None:
            continue
        pnl_pct = float(trade.get("pnl_pct", 0))
        label = 1 if pnl_pct >= WIN_THRESHOLD_PCT else 0
        X_rows.append([features[col] for col in FEATURE_COLS])
        y_labels.append(label)

    if len(X_rows) < MIN_TRADES_REQUIRED:
        logger.info(
            f"ML: Only {len(X_rows)} usable trades (need {MIN_TRADES_REQUIRED}) "
            f"— using static weights"
        )
        return None

    X = np.array(X_rows, dtype=np.float32)
    y = np.array(y_labels, dtype=np.int32)

    win_count = int(y.sum())
    loss_count = len(y) - win_count
    win_rate = win_count / len(y)

    logger.info(
        f"ML: Training on {len(X_rows)} trades | "
        f"wins={win_count} ({win_rate:.1%}) | losses={loss_count}"
    )

    # Scale features
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # Handle class imbalance
    scale_pos_weight = loss_count / win_count if win_count > 0 else 1.0

    # Train XGBoost
    model = XGBClassifier(
        n_estimators=200,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        scale_pos_weight=scale_pos_weight,
        eval_metric="logloss",
        random_state=42,
        verbosity=0,
    )

    # Cross-validation accuracy
    try:
        cv_scores = cross_val_score(model, X_scaled, y, cv=min(5, len(X_rows) // 4), scoring="accuracy")
        model_accuracy = float(cv_scores.mean())
    except Exception:
        model_accuracy = 0.0

    # Fit on full dataset
    model.fit(X_scaled, y)

    # Save model
    try:
        MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        model.save_model(str(MODEL_PATH))
    except Exception as e:
        logger.warning(f"Could not save ML model: {e}")

    # Extract feature importances
    importances = model.feature_importances_  # shape: (n_features,)
    feature_importances = {
        col: float(importances[i])
        for i, col in enumerate(FEATURE_COLS)
    }

    logger.info(f"ML: Feature importances: {feature_importances}")
    logger.info(f"ML: Cross-val accuracy: {model_accuracy:.3f}")

    # ── Map individual feature importances → scoring weight categories ────────
    # Each weight category aggregates one or more feature columns.
    # Importance is summed across all features in the category.
    category_importances = {}
    for category, cols in FEATURE_MAP.items():
        category_importances[category] = sum(
            feature_importances.get(col, 0.0) for col in cols
        )

    # Normalize to sum = 1.0
    total = sum(category_importances.values())
    if total > 0:
        raw_weights = {k: v / total for k, v in category_importances.items()}
    else:
        raw_weights = dict(STATIC_WEIGHTS)

    # ── Apply guardrails: no single weight > 35%, no weight < 1% ─────────────
    # This prevents the model from collapsing to a single feature
    # during short-window overfitting (e.g., 3-day memecoin bull run).
    MAX_WEIGHT = 0.35
    MIN_WEIGHT = 0.01
    clipped = {k: max(MIN_WEIGHT, min(MAX_WEIGHT, v)) for k, v in raw_weights.items()}

    # Re-normalize after clipping
    total_clipped = sum(clipped.values())
    final_weights = {k: round(v / total_clipped, 4) for k, v in clipped.items()}

    logger.info(f"ML: Dynamic weights computed: {final_weights}")

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lookback_days": LOOKBACK_DAYS,
        "trade_count": len(X_rows),
        "win_rate": round(win_rate, 4),
        "model_accuracy": round(model_accuracy, 4),
        "weights": final_weights,
        "feature_importances": feature_importances,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Weight Loading (called by gem_scanner.py each cycle)
# ─────────────────────────────────────────────────────────────────────────────

def load_dynamic_weights() -> dict:
    """
    Load dynamic weights from output/dynamic_weights.json.

    Returns the weights dict if the file exists and is fresh
    (< RETRAIN_INTERVAL_HOURS old). Otherwise returns STATIC_WEIGHTS.

    This is the function called by gem_scanner.py at the start of each scan.
    """
    if not WEIGHTS_PATH.exists():
        logger.debug("No dynamic_weights.json found — using static weights")
        return dict(STATIC_WEIGHTS)

    try:
        with open(WEIGHTS_PATH, "r") as f:
            data = json.load(f)

        # Check freshness
        generated_at_str = data.get("generated_at", "")
        if generated_at_str:
            generated_at = datetime.fromisoformat(generated_at_str.replace("Z", "+00:00"))
            age_hours = (datetime.now(timezone.utc) - generated_at).total_seconds() / 3600
            if age_hours > RETRAIN_INTERVAL_HOURS:
                logger.info(
                    f"ML weights are {age_hours:.1f}h old "
                    f"(threshold: {RETRAIN_INTERVAL_HOURS}h) — retraining..."
                )
                return run_training_cycle()

        weights = data.get("weights", {})
        if not weights:
            return dict(STATIC_WEIGHTS)

        logger.info(
            f"ML: Loaded dynamic weights (trade_count={data.get('trade_count', '?')}, "
            f"win_rate={data.get('win_rate', '?'):.1%}, "
            f"accuracy={data.get('model_accuracy', '?'):.1%})"
        )
        return weights

    except Exception as e:
        logger.warning(f"Failed to load dynamic_weights.json: {e} — using static weights")
        return dict(STATIC_WEIGHTS)


# ─────────────────────────────────────────────────────────────────────────────
# Training Cycle (called on schedule or when weights are stale)
# ─────────────────────────────────────────────────────────────────────────────

def run_training_cycle() -> dict:
    """
    Full training cycle: load trades → train model → save weights → return weights.

    Called:
      1. By load_dynamic_weights() when existing weights are stale
      2. By the scheduler (every RETRAIN_INTERVAL_HOURS)
      3. Manually for testing

    Returns the weights dict (dynamic if training succeeded, static otherwise).
    """
    logger.info(f"ML: Starting weight optimization cycle (lookback={LOOKBACK_DAYS}d)...")

    trades = load_trades(LOOKBACK_DAYS)

    if len(trades) < MIN_TRADES_REQUIRED:
        logger.info(
            f"ML: Insufficient trades ({len(trades)} < {MIN_TRADES_REQUIRED}) "
            f"— using static weights"
        )
        return dict(STATIC_WEIGHTS)

    result = train_weight_model(trades)

    if result is None:
        logger.warning("ML: Training failed — using static weights")
        return dict(STATIC_WEIGHTS)

    # Save to disk
    try:
        WEIGHTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(WEIGHTS_PATH, "w") as f:
            json.dump(result, f, indent=2)
        logger.info(f"ML: Dynamic weights saved to {WEIGHTS_PATH}")
    except Exception as e:
        logger.error(f"ML: Failed to save dynamic weights: {e}")

    # Run trade analytics (exit performance, signal decay, risk metrics)
    try:
        from ml.trade_analytics import run_analytics
        analytics = run_analytics()
        if analytics.get("status") != "insufficient_data":
            # Store best exit reason in weights for dashboard visibility
            best_exit = None
            by_exit = analytics.get("by_exit_reason", {})
            if by_exit:
                best_exit = max(by_exit.items(), key=lambda x: x[1].get("avg_pnl_pct", -999))
                result.setdefault("analytics", {})["best_exit_reason"] = best_exit[0]
                result["analytics"]["overall_win_rate"] = analytics.get("overall_win_rate_pct")
                result["analytics"]["sharpe_7d"] = analytics.get("risk_metrics", {}).get("sharpe_7d")
                # Re-save with analytics metadata
                with open(WEIGHTS_PATH, "w") as f:
                    json.dump(result, f, indent=2)
    except Exception as _analytics_err:
        logger.debug(f"ML: Trade analytics skipped: {_analytics_err}")

    from ml.autoresearch_logger import log_weight_changes
    log_weight_changes(dict(STATIC_WEIGHTS), result["weights"], "UNKNOWN")
    return result["weights"]


# ─────────────────────────────────────────────────────────────────────────────
# Standalone execution (for testing / manual retraining)
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    weights = run_training_cycle()
    print("\n=== Dynamic Weights ===")
    for k, v in sorted(weights.items(), key=lambda x: -x[1]):
        bar = "█" * int(v * 40)
        print(f"  {k:<20} {v:.4f}  {bar}")
