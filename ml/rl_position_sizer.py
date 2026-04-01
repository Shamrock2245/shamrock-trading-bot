"""
ml/rl_position_sizer.py — Reinforcement Learning Position Sizing Agent
=======================================================================
Uses Stable Baselines3 (PPO) to learn optimal position sizing based on
historical trade outcomes. This AUGMENTS (not replaces) the existing
Kelly + offensive guardrails system.

How it works:
  1. Background training loop runs every 24h on completed trades from trades.json
  2. Agent observes: gem_score, macro_regime, win_streak, capital_phase,
     chain, timesfm_direction, chainaware_risk, perplexity_risk
  3. Agent outputs: position_size_multiplier (0.5x to 2.0x)
  4. Multiplier is applied ON TOP of the existing Kelly/offensive sizing
  5. Agent is rewarded for profitable trades, penalized for losses

The RL agent starts with a neutral 1.0x multiplier and only diverges as it
accumulates enough trade history to learn meaningful patterns.

Minimum trade history to activate: 50 completed trades (configurable).
Below this threshold, always returns 1.0x (no effect).

Model: PPO (Proximal Policy Optimization) — stable, sample-efficient
Framework: Stable Baselines3
Auto-install: pip install stable-baselines3 gymnasium

Model persistence: output/rl_position_sizer.zip (reloaded on restart)
Training data: output/trades.json (existing trade log)
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
_MODEL_PATH = Path("output/rl_position_sizer.zip")
_TRAINING_DATA_PATH = Path("output/trades.json")
_MIN_TRADES_TO_ACTIVATE = int(os.getenv("RL_MIN_TRADES", "50"))
_TRAINING_INTERVAL_HOURS = float(os.getenv("RL_TRAINING_INTERVAL_HOURS", "24"))
_MAX_MULTIPLIER = float(os.getenv("RL_MAX_MULTIPLIER", "2.0"))
_MIN_MULTIPLIER = float(os.getenv("RL_MIN_MULTIPLIER", "0.5"))

# State
_model = None
_model_loaded = False
_last_training_time: float = 0.0
_SB3_AVAILABLE: Optional[bool] = None


def _try_install_sb3() -> bool:
    """Attempt to install stable-baselines3 if not present."""
    logger.info("Stable Baselines3 not installed — attempting auto-install...")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install",
             "stable-baselines3[extra]", "gymnasium", "--quiet"],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode == 0:
            logger.info("✅ Stable Baselines3 installed successfully")
            return True
        logger.warning(f"SB3 install failed: {result.stderr[:200]}")
        return False
    except Exception as e:
        logger.warning(f"SB3 auto-install failed: {e}")
        return False


def _check_sb3_available() -> bool:
    """Check if SB3 is importable. Attempt install if not."""
    global _SB3_AVAILABLE
    if _SB3_AVAILABLE is not None:
        return _SB3_AVAILABLE
    try:
        import stable_baselines3  # noqa: F401
        import gymnasium  # noqa: F401
        _SB3_AVAILABLE = True
        return True
    except ImportError:
        if os.getenv("SB3_AUTO_INSTALL", "1") == "1":
            success = _try_install_sb3()
            if success:
                try:
                    import stable_baselines3  # noqa: F401
                    import gymnasium  # noqa: F401
                    _SB3_AVAILABLE = True
                    return True
                except ImportError:
                    pass
        _SB3_AVAILABLE = False
        return False


# ── Observation space encoding ────────────────────────────────────────────────

def _encode_observation(
    gem_score: float,
    macro_regime: str,
    win_streak: int,
    loss_streak: int,
    capital_phase: int,
    chain: str,
    timesfm_direction: str,
    chainaware_risk: float,
    perplexity_risk: float,
    is_express: bool,
) -> np.ndarray:
    """
    Encode trade context into a normalized observation vector.
    All values normalized to [0, 1] range.

    Observation vector (10 features):
      [0] gem_score / 100
      [1] macro_regime_encoded (BEAR=0, NEUTRAL=0.5, BULL=1.0, EXTREME_FEAR=0.2, EXTREME_GREED=0.8)
      [2] win_streak / 10 (capped)
      [3] loss_streak / 10 (capped)
      [4] capital_phase / 5 (0=seed, 1=growth, 2=aggressive, 3=moonshot, 4=empire, 5=legend)
      [5] chain_encoded (ethereum=0.1, base=0.2, arbitrum=0.3, polygon=0.4, bsc=0.5, solana=1.0)
      [6] timesfm_direction_encoded (DOWN=0, FLAT=0.5, UP=1.0)
      [7] chainaware_risk / 100
      [8] perplexity_risk / 100
      [9] is_express (0 or 1)
    """
    _regime_map = {
        "EXTREME_FEAR": 0.1, "BEAR": 0.2, "NEUTRAL": 0.5,
        "BULL": 0.8, "EXTREME_GREED": 0.9,
    }
    _chain_map = {
        "ethereum": 0.1, "base": 0.2, "arbitrum": 0.3,
        "polygon": 0.4, "bsc": 0.5, "solana": 1.0,
    }
    _dir_map = {"DOWN": 0.0, "FLAT": 0.5, "UP": 1.0}

    return np.array([
        min(1.0, gem_score / 100.0),
        _regime_map.get(macro_regime, 0.5),
        min(1.0, win_streak / 10.0),
        min(1.0, loss_streak / 10.0),
        min(1.0, capital_phase / 5.0),
        _chain_map.get(chain, 0.5),
        _dir_map.get(timesfm_direction, 0.5),
        min(1.0, chainaware_risk / 100.0),
        min(1.0, perplexity_risk / 100.0),
        1.0 if is_express else 0.0,
    ], dtype=np.float32)


# ── Training environment ──────────────────────────────────────────────────────

def _build_training_env():
    """Build a Gymnasium environment from historical trades for RL training."""
    try:
        import gymnasium as gym
        from gymnasium import spaces

        trades = _load_trades()
        if len(trades) < _MIN_TRADES_TO_ACTIVATE:
            return None

        class TradeSizingEnv(gym.Env):
            """
            Custom Gymnasium environment for position sizing.
            Each step = one historical trade.
            Action: continuous multiplier [0.5, 2.0]
            Reward: PnL * action (scaled by actual outcome)
            """
            metadata = {"render_modes": []}

            def __init__(self, trade_list: list):
                super().__init__()
                self.trades = trade_list
                self.idx = 0
                # Action space: continuous multiplier [0.5, 2.0]
                self.action_space = spaces.Box(
                    low=np.array([_MIN_MULTIPLIER], dtype=np.float32),
                    high=np.array([_MAX_MULTIPLIER], dtype=np.float32),
                    dtype=np.float32,
                )
                # Observation space: 10 features, all [0, 1]
                self.observation_space = spaces.Box(
                    low=np.zeros(10, dtype=np.float32),
                    high=np.ones(10, dtype=np.float32),
                    dtype=np.float32,
                )

            def reset(self, seed=None, options=None):
                super().reset(seed=seed)
                self.idx = 0
                return self._get_obs(), {}

            def _get_obs(self):
                if self.idx >= len(self.trades):
                    return np.zeros(10, dtype=np.float32)
                t = self.trades[self.idx]
                return _encode_observation(
                    gem_score=t.get("gem_score", 65.0),
                    macro_regime=t.get("macro_regime", "NEUTRAL"),
                    win_streak=t.get("win_streak", 0),
                    loss_streak=t.get("loss_streak", 0),
                    capital_phase=t.get("capital_phase", 0),
                    chain=t.get("chain", "ethereum"),
                    timesfm_direction=t.get("timesfm_direction", "FLAT"),
                    chainaware_risk=t.get("chainaware_risk", 0.0),
                    perplexity_risk=t.get("perplexity_risk", 0.0),
                    is_express=t.get("is_express", False),
                )

            def step(self, action):
                if self.idx >= len(self.trades):
                    return np.zeros(10, dtype=np.float32), 0.0, True, False, {}

                t = self.trades[self.idx]
                multiplier = float(action[0])
                pnl_pct = t.get("pnl_pct", 0.0)  # e.g., 0.5 = +50%

                # Reward: PnL scaled by multiplier
                # Penalize large positions on losing trades more than small positions
                if pnl_pct >= 0:
                    reward = pnl_pct * multiplier  # Profit: bigger position = bigger reward
                else:
                    reward = pnl_pct * multiplier * 1.5  # Loss: penalize oversizing more

                self.idx += 1
                done = self.idx >= len(self.trades)
                obs = self._get_obs()
                return obs, reward, done, False, {}

        return TradeSizingEnv(trades)

    except Exception as e:
        logger.debug(f"RL env build failed: {e}")
        return None


def _load_trades() -> list[dict]:
    """Load completed trades from trades.json."""
    if not _TRAINING_DATA_PATH.exists():
        return []
    try:
        with open(_TRAINING_DATA_PATH) as f:
            data = json.load(f)
        # Filter to completed trades with PnL data
        trades = [
            t for t in data
            if t.get("status") in ("closed", "tp1", "tp2", "tp3", "stale_exit")
            and "pnl_pct" in t
        ]
        return trades
    except Exception as e:
        logger.debug(f"RL: Failed to load trades: {e}")
        return []


def train_rl_agent(force: bool = False) -> bool:
    """
    Train the RL position sizing agent on historical trades.
    Returns True if training succeeded.

    Called automatically every 24h from main.py daemon.
    Can be triggered manually via dashboard.
    """
    global _model, _model_loaded, _last_training_time

    if not _check_sb3_available():
        logger.debug("SB3 not available — skipping RL training")
        return False

    # Check training interval
    if not force and (time.time() - _last_training_time) < (_TRAINING_INTERVAL_HOURS * 3600):
        return False

    trades = _load_trades()
    if len(trades) < _MIN_TRADES_TO_ACTIVATE:
        logger.info(
            f"RL: Not enough trades to train ({len(trades)}/{_MIN_TRADES_TO_ACTIVATE}) — "
            f"using 1.0x neutral multiplier"
        )
        return False

    try:
        from stable_baselines3 import PPO

        logger.info(f"RL: Training position sizer on {len(trades)} trades...")
        t0 = time.time()

        env = _build_training_env()
        if env is None:
            return False

        if _MODEL_PATH.exists() and not force:
            # Continue training from existing model
            model = PPO.load(_MODEL_PATH, env=env)
            model.set_env(env)
        else:
            # Fresh model
            model = PPO(
                "MlpPolicy",
                env,
                verbose=0,
                learning_rate=3e-4,
                n_steps=min(2048, len(trades)),
                batch_size=64,
                n_epochs=10,
                gamma=0.99,
                ent_coef=0.01,  # Encourage exploration
            )

        # Train for a reasonable number of steps
        total_steps = max(10_000, len(trades) * 20)
        model.learn(total_timesteps=total_steps, reset_num_timesteps=False)

        # Save model
        _MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        model.save(str(_MODEL_PATH))

        _model = model
        _model_loaded = True
        _last_training_time = time.time()

        logger.info(
            f"✅ RL position sizer trained: {len(trades)} trades | "
            f"{total_steps:,} steps | {time.time()-t0:.1f}s | "
            f"saved to {_MODEL_PATH}"
        )
        return True

    except Exception as e:
        logger.warning(f"RL training failed: {e}")
        return False


def _load_model() -> bool:
    """Load the trained RL model from disk."""
    global _model, _model_loaded
    if _model_loaded:
        return True
    if not _MODEL_PATH.exists():
        return False
    if not _check_sb3_available():
        return False
    try:
        from stable_baselines3 import PPO
        _model = PPO.load(str(_MODEL_PATH))
        _model_loaded = True
        logger.info(f"✅ RL position sizer loaded from {_MODEL_PATH}")
        return True
    except Exception as e:
        logger.debug(f"RL model load failed: {e}")
        return False


def get_position_multiplier(
    gem_score: float,
    macro_regime: str = "NEUTRAL",
    win_streak: int = 0,
    loss_streak: int = 0,
    capital_phase: int = 0,
    chain: str = "ethereum",
    timesfm_direction: str = "FLAT",
    chainaware_risk: float = 0.0,
    perplexity_risk: float = 0.0,
    is_express: bool = False,
) -> tuple[float, str]:
    """
    Get the RL-recommended position size multiplier.

    Returns:
        (multiplier: float, reason: str)
        multiplier is 1.0 if model not trained yet (neutral — no effect)
    """
    # Try to load model if not loaded
    if not _model_loaded:
        _load_model()

    if not _model_loaded or _model is None:
        return 1.0, "rl_inactive"

    trades = _load_trades()
    if len(trades) < _MIN_TRADES_TO_ACTIVATE:
        return 1.0, f"rl_warmup({len(trades)}/{_MIN_TRADES_TO_ACTIVATE})"

    try:
        obs = _encode_observation(
            gem_score=gem_score,
            macro_regime=macro_regime,
            win_streak=win_streak,
            loss_streak=loss_streak,
            capital_phase=capital_phase,
            chain=chain,
            timesfm_direction=timesfm_direction,
            chainaware_risk=chainaware_risk,
            perplexity_risk=perplexity_risk,
            is_express=is_express,
        )
        action, _ = _model.predict(obs, deterministic=True)
        multiplier = float(np.clip(action[0], _MIN_MULTIPLIER, _MAX_MULTIPLIER))
        # Round to nearest 0.05 for cleaner logging
        multiplier = round(multiplier * 20) / 20

        direction = "↑" if multiplier > 1.05 else ("↓" if multiplier < 0.95 else "→")
        reason = f"rl={multiplier:.2f}x{direction}"

        logger.debug(
            f"RL position sizer: score={gem_score:.0f} regime={macro_regime} "
            f"chain={chain} tf={timesfm_direction} → {multiplier:.2f}x"
        )
        return multiplier, reason

    except Exception as e:
        logger.debug(f"RL inference failed: {e}")
        return 1.0, "rl_error"


def get_training_status() -> dict:
    """Return current RL agent training status for dashboard display."""
    trades = _load_trades()
    return {
        "sb3_available": _check_sb3_available(),
        "model_trained": _MODEL_PATH.exists(),
        "model_loaded": _model_loaded,
        "trade_count": len(trades),
        "min_trades_required": _MIN_TRADES_TO_ACTIVATE,
        "ready": _model_loaded and len(trades) >= _MIN_TRADES_TO_ACTIVATE,
        "last_training": (
            time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(_last_training_time))
            if _last_training_time > 0 else "Never"
        ),
        "next_training": (
            time.strftime(
                "%Y-%m-%d %H:%M UTC",
                time.gmtime(_last_training_time + _TRAINING_INTERVAL_HOURS * 3600)
            )
            if _last_training_time > 0 else "On next bot restart"
        ),
    }
