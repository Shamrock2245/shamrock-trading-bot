"""
core/circuit_breakers.py — ECC Autonomous Execution Guardrails.

Enforces hard mathematical caps on daily deployable capital and trade velocity.
Prevents rogue loops and extreme drawdown events irrespective of profitability.
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Dict, Any

from config import settings

logger = logging.getLogger(__name__)

STATE_FILE = "output/circuit_breakers.json"
PANIC_FILE = "data/dashboard/panic_switch.json"

class CircuitBreakers:
    @classmethod
    def _load_state(cls) -> Dict[str, Any]:
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load circuit breaker state: {e}")
        return {"spends": [], "trades": []}

    @classmethod
    def _save_state(cls, state: Dict[str, Any]) -> None:
        tmp_file = f"{STATE_FILE}.tmp"
        try:
            with open(tmp_file, "w") as f:
                json.dump(state, f, indent=2)
            os.rename(tmp_file, STATE_FILE)
        except Exception as e:
            logger.error(f"Failed to save circuit breaker state: {e}")

    @classmethod
    def _clean_old_records(cls, state: Dict[str, Any], now: float) -> None:
        # Keep spends for 24 hours
        day_ago = now - 86400
        state["spends"] = [s for s in state.get("spends", []) if s["ts"] >= day_ago]
        
        # Keep trades for the velocity window
        window_ago = now - settings.ECC_VELOCITY_WINDOW_SECONDS
        state["trades"] = [t for t in state.get("trades", []) if t["ts"] >= window_ago]

    @classmethod
    def is_panic_engaged(cls) -> bool:
        """Check dynamic JSON file and environment variable for global kill switch."""
        if os.getenv("PANIC_SELL_ONLY", "false").lower() == "true":
            return True
            
        if os.path.exists(PANIC_FILE):
            try:
                with open(PANIC_FILE, "r") as f:
                    data = json.load(f)
                    return data.get("panic", False)
            except Exception:
                pass
        return False

    @classmethod
    def engage_panic(cls) -> None:
        """Dynamically engage the global kill switch."""
        Path("data/dashboard").mkdir(parents=True, exist_ok=True)
        with open(PANIC_FILE, "w") as f:
            json.dump({"panic": True, "ts": time.time()}, f)
        logger.critical("🚨 GLOBAL PANIC SWITCH ENGAGED. All buys halted.")

    @classmethod
    def disengage_panic(cls) -> None:
        """Dynamically disengage the global kill switch."""
        Path("data/dashboard").mkdir(parents=True, exist_ok=True)
        with open(PANIC_FILE, "w") as f:
            json.dump({"panic": False, "ts": time.time()}, f)
        logger.info("🟢 Global panic switch disengaged. Normal operations resumed.")

    @classmethod
    def check_trade_allowed(cls, planned_usd_size: float) -> tuple[bool, str]:
        """
        Check if a trade is permitted based on ECC guardrails.
        Returns (is_allowed, reason_if_blocked).
        """
        if cls.is_panic_engaged():
            return False, "PANIC SWITCH ENGAGED: Buys are globally halted."

        state = cls._load_state()
        now = time.time()
        cls._clean_old_records(state, now)
        
        # Velocity Check
        recent_trades = len(state["trades"])
        if recent_trades >= settings.ECC_VELOCITY_LIMIT:
            return False, f"Velocity Breaker: {recent_trades} trades in {settings.ECC_VELOCITY_WINDOW_SECONDS}s exceeds limit ({settings.ECC_VELOCITY_LIMIT})."

        # Daily Spend Cap Check
        daily_spend = sum(s["amount"] for s in state["spends"])
        if daily_spend + planned_usd_size > settings.ECC_DAILY_SPEND_CAP:
            return False, f"Daily Spend Cap: ${daily_spend + planned_usd_size:.2f} exceeds 24h limit (${settings.ECC_DAILY_SPEND_CAP:.2f})."

        return True, ""

    @classmethod
    def record_trade(cls, usd_size: float) -> None:
        """
        Record an executed trade to update the circuit breaker state.
        Call this immediately after a buy transaction succeeds.
        """
        state = cls._load_state()
        now = time.time()
        cls._clean_old_records(state, now)
        
        state["spends"].append({"ts": now, "amount": usd_size})
        state["trades"].append({"ts": now})
        
        cls._save_state(state)
        logger.info(f"Circuit Breaker recorded trade of ${usd_size:.2f}")
