"""
ml/drift_detector.py — Feature Drift Detection for RL Position Sizer
=====================================================================
Detects statistical drift in the RL position sizer's actual observation vector
(the 13 features passed to _encode_observation) before the 24h retrain cycle.
When significant drift is detected, the position sizer falls back to
conservative static Kelly Criterion sizing to avoid stale model weights.

Critical design note (Codex P2 fix):
  The RL model consumes 13 features: gem_score, macro_regime, win/loss streaks,
  capital_phase, chain, timesfm_direction, chainaware_risk, perplexity_risk,
  is_express, fear_greed_score, portfolio_heat, hourly_volatility.
  These are NOT the 29 TA indicators — monitoring the wrong features would cause
  both false positives (TA drifts but RL inputs stable) and false negatives
  (RL inputs drift but TA is stable).

How it works:
  1. Load recent trades from output/trades.json (same source RL trains on)
  2. Load the historical training baseline from output/training_stats.json
  3. Calculate Kolmogorov-Smirnov (KS) distance for each RL input feature
  4. If >30% of features show significant drift (p < 0.05):
       - Log a WARNING with per-feature breakdown
       - Set DRIFT_DETECTED flag → position sizer uses conservative static Kelly

Integration with rl_position_sizer.py:
  from ml.drift_detector import check_feature_drift, DRIFT_DETECTED
  if check_feature_drift():
      # Use static Kelly sizing — ML model weights are stale
      return 1.0, "rl_drift_fallback"

Artifacts:
  output/trades.json          — Trade log with RL observation features
  output/training_stats.json  — Historical distribution stats (written by this module after
                                each successful retrain to establish the baseline)
  output/drift_report.json    — Last drift check results for dashboard display
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────
_TRADES_PATH = Path("output/trades.json")
_TRAINING_STATS_PATH = Path("output/training_stats.json")
_DRIFT_REPORT_PATH = Path("output/drift_report.json")

# ── Config ────────────────────────────────────────────────────────────────────
# Fraction of indicators that must show drift to trigger the fallback flag.
_DRIFT_THRESHOLD_FRACTION = float(os.getenv("DRIFT_THRESHOLD_FRACTION", "0.30"))
# KS test p-value below which an indicator is considered drifted.
_KS_P_VALUE_THRESHOLD = float(os.getenv("DRIFT_KS_P_VALUE", "0.05"))
# Minimum number of live samples required to run the KS test.
_MIN_LIVE_SAMPLES = int(os.getenv("DRIFT_MIN_LIVE_SAMPLES", "30"))
# Minimum number of historical samples required to run the KS test.
_MIN_HIST_SAMPLES = int(os.getenv("DRIFT_MIN_HIST_SAMPLES", "50"))
# Cache drift check result for this many seconds to avoid repeated computation.
_CACHE_TTL_SECONDS = float(os.getenv("DRIFT_CACHE_TTL_SECONDS", "1800"))  # 30 min

# ── The 13 RL observation features (must match _encode_observation) ───────────
# These are the actual inputs the RL model sees. Monitoring these for drift
# ensures we detect shifts in the feature space the model was trained on.
_RL_FEATURE_NAMES: list[str] = [
    "gem_score",
    "macro_regime",
    "win_streak",
    "loss_streak",
    "capital_phase",
    "chain",
    "timesfm_direction",
    "chainaware_risk",
    "perplexity_risk",
    "is_express",
    "fear_greed_score",
    "portfolio_heat",
    "hourly_volatility",
]

# Encoding maps (must match _encode_observation in rl_position_sizer.py)
_REGIME_MAP = {
    "EXTREME_FEAR": 0.1, "BEAR": 0.2, "NEUTRAL": 0.5,
    "BULL": 0.8, "EXTREME_GREED": 0.9,
}
_CHAIN_MAP = {
    "ethereum": 0.1, "base": 0.2, "arbitrum": 0.3,
    "polygon": 0.4, "bsc": 0.5, "solana": 1.0,
}
_DIR_MAP = {"DOWN": 0.0, "FLAT": 0.5, "UP": 1.0}


def _encode_feature(name: str, raw_val) -> float:
    """Encode a raw trade feature value to the same [0,1] scale as _encode_observation."""
    if raw_val is None:
        return 0.5  # neutral default
    try:
        if name == "gem_score":
            return min(1.0, float(raw_val) / 100.0)
        elif name == "macro_regime":
            return _REGIME_MAP.get(str(raw_val), 0.5)
        elif name in ("win_streak", "loss_streak"):
            return min(1.0, float(raw_val) / 10.0)
        elif name == "capital_phase":
            return min(1.0, float(raw_val) / 5.0)
        elif name == "chain":
            return _CHAIN_MAP.get(str(raw_val), 0.5)
        elif name == "timesfm_direction":
            return _DIR_MAP.get(str(raw_val), 0.5)
        elif name in ("chainaware_risk", "perplexity_risk"):
            return min(1.0, float(raw_val) / 100.0)
        elif name == "is_express":
            return 1.0 if raw_val else 0.0
        elif name == "fear_greed_score":
            return min(1.0, float(raw_val) / 100.0)
        elif name == "portfolio_heat":
            return min(1.0, abs(float(raw_val)) / 20.0)
        elif name == "hourly_volatility":
            return min(1.0, float(raw_val) / 100.0)
        else:
            return float(raw_val)
    except (TypeError, ValueError):
        return 0.5

# ── Module-level state ────────────────────────────────────────────────────────
DRIFT_DETECTED: bool = False
_last_check_time: float = 0.0
_last_drift_result: Optional[dict] = None


# ── scipy KS test with graceful fallback ─────────────────────────────────────
def _ks_test(live_samples: list[float], hist_samples: list[float]) -> tuple[float, float]:
    """
    Run a two-sample Kolmogorov-Smirnov test.

    Returns:
        (ks_statistic, p_value)
        Falls back to (0.0, 1.0) — no drift — if scipy is unavailable or
        if either sample is too small to be meaningful.
    """
    if len(live_samples) < _MIN_LIVE_SAMPLES or len(hist_samples) < _MIN_HIST_SAMPLES:
        return 0.0, 1.0

    try:
        from scipy.stats import ks_2samp  # type: ignore
        stat, p_val = ks_2samp(live_samples, hist_samples)
        return float(stat), float(p_val)
    except ImportError:
        # scipy not installed — use a simple manual approximation
        return _ks_manual(live_samples, hist_samples)
    except Exception as e:
        logger.debug(f"KS test error: {e}")
        return 0.0, 1.0


def _ks_manual(a: list[float], b: list[float]) -> tuple[float, float]:
    """
    Minimal KS statistic approximation without scipy.
    Uses the empirical CDF max-distance formula.
    p-value is approximated via the Kolmogorov distribution asymptotic formula.
    """
    try:
        a_sorted = sorted(a)
        b_sorted = sorted(b)
        n1, n2 = len(a_sorted), len(b_sorted)
        combined = sorted(set(a_sorted + b_sorted))
        max_diff = 0.0
        for x in combined:
            cdf_a = sum(1 for v in a_sorted if v <= x) / n1
            cdf_b = sum(1 for v in b_sorted if v <= x) / n2
            max_diff = max(max_diff, abs(cdf_a - cdf_b))
        # Asymptotic p-value approximation
        en = (n1 * n2 / (n1 + n2)) ** 0.5
        z = (en + 0.12 + 0.11 / en) * max_diff
        # Approximate p-value from KS distribution
        p_val = 2.0 * sum(
            ((-1) ** (k - 1)) * np.exp(-2.0 * k * k * z * z)
            for k in range(1, 10)
        )
        p_val = float(np.clip(p_val, 0.0, 1.0))
        return float(max_diff), p_val
    except Exception:
        return 0.0, 1.0


# ── Data loading ──────────────────────────────────────────────────────────────
def _load_recent_trades() -> dict[str, list[float]]:
    """
    Load recent trades and extract RL observation features.

    Reads from trades.json (the same file the RL agent trains on)
    and encodes each trade's features using the same normalization as
    _encode_observation in rl_position_sizer.py.

    Returns a dict mapping feature_name → list of encoded float values.
    Returns an empty dict if the file doesn't exist or has no recent trades.
    """
    if not _TRADES_PATH.exists():
        logger.debug(f"Trades file not found at {_TRADES_PATH} — drift check skipped")
        return {}

    try:
        with open(_TRADES_PATH) as f:
            raw = json.load(f)

        if not isinstance(raw, list):
            logger.debug("trades.json is not a list — skipping drift check")
            return {}

        # Use the most recent trades (last 100 or last 7 days)
        cutoff = time.time() - 7 * 86_400
        recent = [
            t for t in raw
            if isinstance(t, dict) and t.get("timestamp", t.get("opened_at", 0)) >= cutoff
        ]
        # Also include recent completed trades without timestamp filter if few recent
        if len(recent) < _MIN_LIVE_SAMPLES and len(raw) >= _MIN_LIVE_SAMPLES:
            recent = raw[-100:]  # Last 100 trades as fallback

        if not recent:
            logger.debug("No recent trades for drift check")
            return {}

        # Pivot: feature_name → list of encoded values
        feature_data: dict[str, list[float]] = {name: [] for name in _RL_FEATURE_NAMES}
        for trade in recent:
            for name in _RL_FEATURE_NAMES:
                raw_val = trade.get(name)
                if raw_val is not None:
                    encoded = _encode_feature(name, raw_val)
                    feature_data[name].append(encoded)

        return feature_data

    except Exception as e:
        logger.debug(f"Failed to load trades.json for drift check: {e}")
        return {}


def _load_training_stats() -> dict[str, list[float]]:
    """
    Load historical training data distribution from training_stats.json.

    Expected format (now uses RL feature names, not TA indicators):
    {
        "gem_score": [0.65, 0.72, 0.58, ...],
        "macro_regime": [0.5, 0.8, 0.2, ...],
        ...
    }

    Returns a dict mapping feature_name → list of historical float values.
    Returns an empty dict if the file doesn't exist or is malformed.
    """
    if not _TRAINING_STATS_PATH.exists():
        logger.debug(
            f"Training stats not found at {_TRAINING_STATS_PATH} — "
            f"drift check requires a baseline. Run save_training_stats() after first retrain."
        )
        return {}

    try:
        with open(_TRAINING_STATS_PATH) as f:
            data = json.load(f)

        if not isinstance(data, dict):
            logger.debug("training_stats.json is not a dict — skipping drift check")
            return {}

        # Validate and convert
        result: dict[str, list[float]] = {}
        for name in _RL_FEATURE_NAMES:
            vals = data.get(name, [])
            if isinstance(vals, list) and vals:
                try:
                    result[name] = [float(v) for v in vals if v is not None]
                except (TypeError, ValueError):
                    pass

        return result

    except Exception as e:
        logger.debug(f"Failed to load training_stats.json: {e}")
        return {}


# ── Core drift check ──────────────────────────────────────────────────────────
def check_feature_drift(force: bool = False) -> bool:
    """
    Run the KS-based feature drift check.

    Returns True if drift is detected (>30% of indicators have p < 0.05).
    Updates the module-level DRIFT_DETECTED flag.

    Args:
        force: If True, bypass the cache TTL and recompute immediately.

    Side effects:
        - Sets the module-level DRIFT_DETECTED flag
        - Writes output/drift_report.json with per-indicator results
        - Logs WARNING if drift is detected
    """
    global DRIFT_DETECTED, _last_check_time, _last_drift_result

    # Return cached result if within TTL
    if not force and (time.time() - _last_check_time) < _CACHE_TTL_SECONDS:
        if _last_drift_result is not None:
            return _last_drift_result.get("drift_detected", False)

    logger.debug("Running feature drift check...")
    t0 = time.time()

    live_data = _load_recent_trades()
    hist_data = _load_training_stats()

    if not live_data or not hist_data:
        # Cannot check without both datasets — assume no drift
        logger.debug(
            "Drift check skipped: missing recent trade data or training stats baseline. "
            "Assuming no drift — RL sizing proceeds normally."
        )
        DRIFT_DETECTED = False
        _last_check_time = time.time()
        return False

    # Run KS test for each indicator
    drifted_indicators: list[str] = []
    stable_indicators: list[str] = []
    skipped_indicators: list[str] = []
    per_indicator: dict[str, dict] = {}

    for name in _RL_FEATURE_NAMES:
        live_vals = live_data.get(name, [])
        hist_vals = hist_data.get(name, [])

        if len(live_vals) < _MIN_LIVE_SAMPLES or len(hist_vals) < _MIN_HIST_SAMPLES:
            skipped_indicators.append(name)
            per_indicator[name] = {
                "status": "skipped",
                "live_n": len(live_vals),
                "hist_n": len(hist_vals),
                "ks_stat": None,
                "p_value": None,
            }
            continue

        ks_stat, p_val = _ks_test(live_vals, hist_vals)

        is_drifted = p_val < _KS_P_VALUE_THRESHOLD
        per_indicator[name] = {
            "status": "drifted" if is_drifted else "stable",
            "live_n": len(live_vals),
            "hist_n": len(hist_vals),
            "ks_stat": round(ks_stat, 4),
            "p_value": round(p_val, 4),
        }

        if is_drifted:
            drifted_indicators.append(name)
        else:
            stable_indicators.append(name)

    # Calculate drift fraction (only over tested indicators, not skipped)
    tested_count = len(drifted_indicators) + len(stable_indicators)
    if tested_count == 0:
        logger.debug("No indicators had enough data for KS test — assuming no drift")
        drift_fraction = 0.0
        drift_detected = False
    else:
        drift_fraction = len(drifted_indicators) / tested_count
        drift_detected = drift_fraction > _DRIFT_THRESHOLD_FRACTION

    elapsed = time.time() - t0

    # Build report
    report = {
        "timestamp": time.time(),
        "timestamp_utc": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
        "drift_detected": drift_detected,
        "drift_fraction": round(drift_fraction, 4),
        "drift_threshold": _DRIFT_THRESHOLD_FRACTION,
        "drifted_count": len(drifted_indicators),
        "stable_count": len(stable_indicators),
        "skipped_count": len(skipped_indicators),
        "tested_count": tested_count,
        "drifted_indicators": drifted_indicators,
        "stable_indicators": stable_indicators,
        "skipped_indicators": skipped_indicators,
        "per_indicator": per_indicator,
        "elapsed_seconds": round(elapsed, 3),
        "ks_p_threshold": _KS_P_VALUE_THRESHOLD,
        "min_live_samples": _MIN_LIVE_SAMPLES,
        "min_hist_samples": _MIN_HIST_SAMPLES,
    }

    # Persist report for dashboard display
    try:
        _DRIFT_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_DRIFT_REPORT_PATH, "w") as f:
            json.dump(report, f, indent=2)
    except Exception as e:
        logger.debug(f"Failed to write drift report: {e}")

    # Update module state
    DRIFT_DETECTED = drift_detected
    _last_check_time = time.time()
    _last_drift_result = report

    if drift_detected:
        logger.warning(
            f"⚠️  FEATURE DRIFT DETECTED: {len(drifted_indicators)}/{tested_count} indicators "
            f"show significant distribution shift (p < {_KS_P_VALUE_THRESHOLD}) — "
            f"drift_fraction={drift_fraction:.1%} > threshold={_DRIFT_THRESHOLD_FRACTION:.0%}. "
            f"RL position sizer will fall back to conservative static Kelly sizing. "
            f"Drifted indicators: {', '.join(drifted_indicators[:10])}"
            + (f" ... (+{len(drifted_indicators)-10} more)" if len(drifted_indicators) > 10 else "")
        )
    else:
        logger.info(
            f"✅ Feature drift check passed: {len(drifted_indicators)}/{tested_count} indicators "
            f"drifted ({drift_fraction:.1%} < {_DRIFT_THRESHOLD_FRACTION:.0%} threshold) — "
            f"RL sizing active. [{elapsed:.2f}s]"
        )

    return drift_detected


# ── Training stats persistence ────────────────────────────────────────────────
def save_training_stats(ta_records: Optional[list[dict]] = None) -> bool:
    """
    Save the current TA indicator distribution as the new training baseline.

    Called after each successful RL retrain to update the reference distribution.
    If ta_records is None, loads from ta_cache.json automatically.

    Args:
        ta_records: Optional list of TA snapshot dicts. If None, reads ta_cache.json.

    Returns:
        True if saved successfully, False otherwise.
    """
    try:
        if ta_records is None:
            if not _TA_CACHE_PATH.exists():
                logger.debug("Cannot save training stats: ta_cache.json not found")
                return False
            with open(_TA_CACHE_PATH) as f:
                ta_records = json.load(f)

        if not isinstance(ta_records, list) or not ta_records:
            logger.debug("Cannot save training stats: empty or invalid ta_records")
            return False

        # Build distribution per RL feature (encoded to [0,1] scale)
        stats: dict[str, list[float]] = {name: [] for name in _RL_FEATURE_NAMES}
        for entry in ta_records:
            if not isinstance(entry, dict):
                continue
            for name in _RL_FEATURE_NAMES:
                raw_val = entry.get(name)
                if raw_val is not None:
                    encoded = _encode_feature(name, raw_val)
                    stats[name].append(encoded)

        # Only save indicators with enough data
        filtered_stats = {
            name: vals
            for name, vals in stats.items()
            if len(vals) >= _MIN_HIST_SAMPLES
        }

        if not filtered_stats:
            logger.debug(
                f"Cannot save training stats: no indicator has >= {_MIN_HIST_SAMPLES} samples"
            )
            return False

        _TRAINING_STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_TRAINING_STATS_PATH, "w") as f:
            json.dump(filtered_stats, f)

        indicator_count = len(filtered_stats)
        sample_count = sum(len(v) for v in filtered_stats.values())
        logger.info(
            f"✅ Training stats saved: {indicator_count} indicators, "
            f"{sample_count:,} total samples → {_TRAINING_STATS_PATH}"
        )
        return True

    except Exception as e:
        logger.warning(f"Failed to save training stats: {e}")
        return False


# ── Status helper for dashboard ───────────────────────────────────────────────
def get_drift_status() -> dict:
    """Return current drift detection status for dashboard display."""
    report = _last_drift_result or {}
    return {
        "drift_detected": DRIFT_DETECTED,
        "last_check": (
            time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(_last_check_time))
            if _last_check_time > 0 else "Never"
        ),
        "drift_fraction": report.get("drift_fraction", 0.0),
        "drifted_count": report.get("drifted_count", 0),
        "tested_count": report.get("tested_count", 0),
        "drifted_indicators": report.get("drifted_indicators", []),
        "trades_file_exists": _TRADES_PATH.exists(),
        "training_stats_exists": _TRAINING_STATS_PATH.exists(),
        "drift_report_exists": _DRIFT_REPORT_PATH.exists(),
        "ks_p_threshold": _KS_P_VALUE_THRESHOLD,
        "drift_threshold_fraction": _DRIFT_THRESHOLD_FRACTION,
    }
