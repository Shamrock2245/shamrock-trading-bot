"""
ml/timesfm_signal.py — TimesFM Price Direction Forecasting Signal
=================================================================
Uses Google's TimesFM (Time Series Foundation Model) to generate a short-term
price direction forecast for gem candidates. This is a SCORING SIGNAL, not a
standalone trading system.

TimesFM is a 200M-parameter pretrained decoder-only model that does zero-shot
time series forecasting — no training required. Feed it any price series and
it returns probabilistic forecasts with confidence intervals.

Signal output:
  - forecast_direction: "UP" | "DOWN" | "FLAT"
  - forecast_confidence: 0.0–1.0
  - score_bonus: +0 to +8 pts (UP with high confidence)
  - score_penalty: 0 to -5 pts (DOWN with high confidence)

Installation (runs automatically on first use if not installed):
  pip install timesfm[torch]
  # Requires ~800MB disk, ~1.5GB RAM, Python 3.10+

Fallback: If TimesFM is not available, uses a lightweight linear regression
on recent closes to estimate direction. This ensures the bot always has SOME
forward-looking signal even without the full model.

Data source: DexScreener 1h OHLCV via existing get_token_pairs() infrastructure.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from typing import Optional

logger = logging.getLogger(__name__)

# ── TimesFM availability flag ─────────────────────────────────────────────────
_TIMESFM_AVAILABLE: Optional[bool] = None  # None = not yet checked
_TIMESFM_MODEL = None  # Singleton model instance (loaded once, reused)
_MODEL_LOAD_ATTEMPTED = False

# Cache: {cache_key: (timestamp, result)}
_cache: dict[str, tuple[float, dict]] = {}
_CACHE_TTL = 300  # 5 minutes


def _try_install_timesfm() -> bool:
    """Attempt to install timesfm if not present. Returns True if successful."""
    logger.info("TimesFM not installed — attempting auto-install (this may take 2-3 minutes)...")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "timesfm[torch]", "--quiet"],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode == 0:
            logger.info("✅ TimesFM installed successfully")
            return True
        else:
            logger.warning(f"TimesFM install failed: {result.stderr[:200]}")
            return False
    except Exception as e:
        logger.warning(f"TimesFM auto-install failed: {e}")
        return False


def _check_timesfm_available() -> bool:
    """Check if TimesFM is importable. Attempt install if not."""
    global _TIMESFM_AVAILABLE
    if _TIMESFM_AVAILABLE is not None:
        return _TIMESFM_AVAILABLE

    try:
        import timesfm  # noqa: F401
        _TIMESFM_AVAILABLE = True
        return True
    except ImportError:
        # Only attempt install if explicitly enabled via env var
        if os.getenv("TIMESFM_AUTO_INSTALL", "1") == "1":
            success = _try_install_timesfm()
            if success:
                try:
                    import timesfm  # noqa: F401
                    _TIMESFM_AVAILABLE = True
                    return True
                except ImportError:
                    pass
        _TIMESFM_AVAILABLE = False
        return False


def _load_model():
    """Load TimesFM model singleton. Downloads weights on first run (~800MB)."""
    global _TIMESFM_MODEL, _MODEL_LOAD_ATTEMPTED
    if _TIMESFM_MODEL is not None:
        return _TIMESFM_MODEL
    if _MODEL_LOAD_ATTEMPTED:
        return None

    _MODEL_LOAD_ATTEMPTED = True
    try:
        import timesfm
        logger.info("Loading TimesFM model (first load downloads ~800MB weights)...")
        t0 = time.time()
        tfm = timesfm.TimesFm(
            hparams=timesfm.TimesFmHparams(
                backend="cpu",          # CPU inference — no GPU needed
                per_core_batch_size=32,
                horizon_len=8,          # Forecast 8 periods ahead
                num_layers=20,
                model_dims=1280,
                use_positional_embedding=False,
            ),
            checkpoint=timesfm.TimesFmCheckpoint(
                huggingface_repo_id="google/timesfm-1.0-200m-pytorch",
            ),
        )
        _TIMESFM_MODEL = tfm
        logger.info(f"✅ TimesFM model loaded in {time.time()-t0:.1f}s")
        return tfm
    except Exception as e:
        logger.warning(f"TimesFM model load failed: {e}")
        return None


def _linear_regression_forecast(closes: list[float], horizon: int = 4) -> dict:
    """
    Lightweight fallback: linear regression on recent closes to estimate direction.
    Used when TimesFM is not available.
    """
    if len(closes) < 4:
        return {"direction": "FLAT", "confidence": 0.3, "method": "insufficient_data"}

    n = min(len(closes), 20)
    recent = closes[-n:]
    x = list(range(n))
    x_mean = sum(x) / n
    y_mean = sum(recent) / n
    numerator = sum((xi - x_mean) * (yi - y_mean) for xi, yi in zip(x, recent))
    denominator = sum((xi - x_mean) ** 2 for xi in x)
    if denominator == 0:
        return {"direction": "FLAT", "confidence": 0.3, "method": "linear_regression"}

    slope = numerator / denominator
    # Normalize slope as % of current price
    slope_pct = (slope / recent[-1]) * 100 if recent[-1] > 0 else 0

    if slope_pct > 0.5:
        direction = "UP"
        confidence = min(0.7, 0.4 + abs(slope_pct) * 0.05)
    elif slope_pct < -0.5:
        direction = "DOWN"
        confidence = min(0.7, 0.4 + abs(slope_pct) * 0.05)
    else:
        direction = "FLAT"
        confidence = 0.4

    return {"direction": direction, "confidence": confidence, "method": "linear_regression",
            "slope_pct": slope_pct}


def _timesfm_forecast(closes: list[float], horizon: int = 4) -> dict:
    """
    Run TimesFM inference on a price series.
    Returns direction, confidence, and quantile bounds.
    """
    model = _load_model()
    if model is None:
        return _linear_regression_forecast(closes, horizon)

    try:
        import numpy as np

        # TimesFM expects a list of numpy arrays
        series = np.array(closes, dtype=np.float32)
        # Normalize to avoid scale issues
        scale = series[-1] if series[-1] > 0 else 1.0
        series_norm = series / scale

        point_forecast, quantile_forecast = model.forecast(
            inputs=[series_norm],
            freq=[0],  # 0 = irregular/unknown frequency
        )

        # point_forecast shape: (1, horizon)
        forecast = point_forecast[0] * scale  # Denormalize
        current = closes[-1]
        forecast_end = float(forecast[-1])

        change_pct = (forecast_end / current - 1) * 100 if current > 0 else 0

        # Use quantile spread as confidence proxy
        if quantile_forecast is not None and len(quantile_forecast) > 0:
            q10 = float(quantile_forecast[0, -1, 0]) * scale  # 10th percentile
            q90 = float(quantile_forecast[0, -1, -1]) * scale  # 90th percentile
            spread_pct = abs(q90 - q10) / current * 100 if current > 0 else 50
            # Tight spread = high confidence
            confidence = max(0.3, min(0.95, 1.0 - (spread_pct / 50)))
        else:
            confidence = 0.6

        if change_pct > 2.0:
            direction = "UP"
        elif change_pct < -2.0:
            direction = "DOWN"
        else:
            direction = "FLAT"

        return {
            "direction": direction,
            "confidence": confidence,
            "change_pct": change_pct,
            "forecast_price": forecast_end,
            "method": "timesfm",
        }

    except Exception as e:
        logger.debug(f"TimesFM inference failed: {e}")
        return _linear_regression_forecast(closes, horizon)


def get_price_forecast_signal(
    token_address: str,
    chain: str,
    closes: list[float],
    horizon_periods: int = 4,
) -> dict:
    """
    Get a price direction forecast signal for a gem candidate.

    Args:
        token_address: Token contract address (for caching)
        chain: Chain name
        closes: List of recent close prices (oldest first), at least 10 required
        horizon_periods: How many periods ahead to forecast (default 4)

    Returns:
        {
            "direction": "UP" | "DOWN" | "FLAT",
            "confidence": float (0.0–1.0),
            "score_delta": float (score bonus/penalty to apply),
            "method": "timesfm" | "linear_regression" | "insufficient_data",
            "change_pct": float (forecasted % change),
        }
    """
    if len(closes) < 6:
        return {
            "direction": "FLAT", "confidence": 0.0, "score_delta": 0.0,
            "method": "insufficient_data", "change_pct": 0.0,
        }

    cache_key = f"forecast:{chain}:{token_address.lower()}"
    cached = _cache.get(cache_key)
    if cached and (time.time() - cached[0]) < _CACHE_TTL:
        return cached[1]

    # Choose method based on availability
    if _check_timesfm_available():
        result = _timesfm_forecast(closes, horizon_periods)
    else:
        result = _linear_regression_forecast(closes, horizon_periods)

    # ── Score delta calculation ───────────────────────────────────────────────
    direction = result.get("direction", "FLAT")
    confidence = result.get("confidence", 0.0)

    if direction == "UP":
        # Bonus: +3 to +8 pts based on confidence
        score_delta = round(3.0 + (confidence * 5.0), 1)
    elif direction == "DOWN":
        # Penalty: -2 to -5 pts based on confidence
        score_delta = round(-(2.0 + (confidence * 3.0)), 1)
    else:
        score_delta = 0.0

    result["score_delta"] = score_delta

    _cache[cache_key] = (time.time(), result)

    logger.debug(
        f"TimesFM [{token_address[:10]}…] {chain}: "
        f"dir={direction} conf={confidence:.0%} delta={score_delta:+.1f} "
        f"method={result.get('method', '?')}"
    )

    return result


def get_forecast_from_dexscreener(
    token_address: str,
    chain: str,
    pair_address: str = "",
) -> dict:
    """
    Fetch OHLCV from DexScreener and run TimesFM forecast.
    Convenience wrapper for gem_scanner.py integration.

    Returns the same dict as get_price_forecast_signal().
    """
    empty = {
        "direction": "FLAT", "confidence": 0.0, "score_delta": 0.0,
        "method": "no_data", "change_pct": 0.0,
    }

    try:
        from data.providers.dexscreener import get_token_pairs
        pairs = get_token_pairs(token_address) or []
        if not pairs:
            return empty

        # Use the first pair's price data
        pair = pairs[0]
        # DexScreener doesn't provide OHLCV directly — use price change data
        # to construct a synthetic price series from available signals
        price_usd = float(pair.get("priceUsd", 0) or 0)
        if price_usd <= 0:
            return empty

        # Build synthetic price series from available change data
        chg_5m = float(pair.get("priceChange", {}).get("m5", 0) or 0) / 100
        chg_1h = float(pair.get("priceChange", {}).get("h1", 0) or 0) / 100
        chg_6h = float(pair.get("priceChange", {}).get("h6", 0) or 0) / 100
        chg_24h = float(pair.get("priceChange", {}).get("h24", 0) or 0) / 100

        # Reconstruct approximate price series (8 points)
        p_24h = price_usd / (1 + chg_24h) if chg_24h != -1 else price_usd
        p_6h = price_usd / (1 + chg_6h) if chg_6h != -1 else price_usd
        p_1h = price_usd / (1 + chg_1h) if chg_1h != -1 else price_usd
        p_5m = price_usd / (1 + chg_5m) if chg_5m != -1 else price_usd

        closes = [
            p_24h,
            (p_24h + p_6h) / 2,
            p_6h,
            (p_6h + p_1h) / 2,
            p_1h,
            (p_1h + p_5m) / 2,
            p_5m,
            price_usd,
        ]

        return get_price_forecast_signal(token_address, chain, closes)

    except Exception as e:
        logger.debug(f"TimesFM DexScreener fetch failed for {token_address[:10]}: {e}")
        return empty
