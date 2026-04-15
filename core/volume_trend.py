"""
core/volume_trend.py — Cross-cycle volume trend tracking.

Tracks volume_1h readings across scan cycles to detect sustained
momentum vs fading spikes. Used by the gem scanner as a trend bonus.

Usage:
    from core.volume_trend import VolumeTrendTracker

    tracker = VolumeTrendTracker()
    tracker.record(token_address, chain, volume_1h)
    trend = tracker.get_trend(token_address, chain)
    # trend = {"direction": "rising", "readings": 3, "change_pct": 55.0}
"""

import json
import logging
import os
import time
from pathlib import Path
from collections import defaultdict

logger = logging.getLogger(__name__)

TREND_FILE = Path(os.getenv("VOLUME_TREND_FILE", "output/volume_trends.json"))
TREND_FILE.parent.mkdir(parents=True, exist_ok=True)

# Keep max 6 readings per token (~30 min of 5-min cycles)
MAX_READINGS = 6
# Auto-expire tokens not seen for 2 hours
EXPIRY_SECONDS = 7200


class VolumeTrendTracker:
    """Track volume_1h readings across scan cycles to detect momentum trends."""

    def __init__(self):
        self._trends: dict[str, list[dict]] = {}
        self._load()

    def _key(self, token_address: str, chain: str) -> str:
        return f"{chain}:{token_address.lower()}"

    def _load(self):
        """Load persisted trend data."""
        if TREND_FILE.exists():
            try:
                with open(TREND_FILE) as f:
                    self._trends = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._trends = {}

    def _save(self):
        """Persist trend data."""
        try:
            tmp = TREND_FILE.with_suffix(".tmp")
            with open(tmp, "w") as f:
                json.dump(self._trends, f, default=str)
            tmp.replace(TREND_FILE)
        except Exception as e:
            logger.debug(f"Failed to save volume trends: {e}")

    def _prune_expired(self):
        """Remove tokens not seen recently."""
        now = time.time()
        expired_keys = [
            k for k, readings in self._trends.items()
            if readings and (now - readings[-1].get("ts", 0)) > EXPIRY_SECONDS
        ]
        for k in expired_keys:
            del self._trends[k]

    def record(self, token_address: str, chain: str, volume_1h: float) -> None:
        """Record a volume_1h reading for a token."""
        key = self._key(token_address, chain)
        if key not in self._trends:
            self._trends[key] = []
        
        self._trends[key].append({
            "vol": volume_1h,
            "ts": time.time(),
        })
        
        # Keep only recent readings
        self._trends[key] = self._trends[key][-MAX_READINGS:]

    def get_trend(self, token_address: str, chain: str) -> dict:
        """
        Get the volume trend for a token.
        
        Returns:
            {
                "direction": "rising" | "falling" | "flat" | "unknown",
                "readings": int,
                "change_pct": float,  # % change from first to last reading
                "score_bonus": float,  # Suggested score adjustment (-5 to +10)
            }
        """
        key = self._key(token_address, chain)
        readings = self._trends.get(key, [])
        
        if len(readings) < 2:
            return {"direction": "unknown", "readings": len(readings), "change_pct": 0, "score_bonus": 0}

        first_vol = readings[0]["vol"]
        last_vol = readings[-1]["vol"]

        if first_vol <= 0:
            return {"direction": "unknown", "readings": len(readings), "change_pct": 0, "score_bonus": 0}

        change_pct = ((last_vol - first_vol) / first_vol) * 100

        # Determine trend direction
        if change_pct > 30:
            direction = "rising"
            # Sustained rising volume = strong momentum
            score_bonus = min(10.0, change_pct / 20)  # Cap at +10
        elif change_pct < -30:
            direction = "falling"
            # Fading volume = dying momentum
            score_bonus = max(-5.0, change_pct / 20)  # Cap at -5
        else:
            direction = "flat"
            score_bonus = 0.0

        return {
            "direction": direction,
            "readings": len(readings),
            "change_pct": round(change_pct, 1),
            "score_bonus": round(score_bonus, 1),
        }

    def flush(self):
        """Save trends and prune expired entries."""
        self._prune_expired()
        self._save()
