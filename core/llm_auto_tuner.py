"""
core/llm_auto_tuner.py — Reasoning-Driven Auto-Tuning Engine (OpenAlice style).

Ingests live market data, current daily PnL, and active positions, 
then queries an LLM to auto-tune position parameters (e.g., trailing stops) 
using natural language reasoning (Trading-as-Git).

Dedup:
    - Internal 30-minute cooldown (_last_run_time) prevents double-runs
      even if called from multiple sites.
    - File-based lock (output/auto_tune_lock.json) survives restarts
      so the tuner doesn't fire immediately after a reboot within the
      30-min window.
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
from openai import OpenAI

from config import settings
from core.daily_goal_engine import get_daily_goal_engine
from core.position_monitor import load_positions, save_positions

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Dedup: 30-minute minimum interval (in-memory + file-based)
# ─────────────────────────────────────────────────────────────────────────────
AUTO_TUNE_COOLDOWN_SECONDS = 1800.0  # 30 minutes

_last_run_time: float = 0.0
_LOCK_FILE = Path(os.getenv("AUTO_TUNE_LOCK_FILE", "output/auto_tune_lock.json"))


def _read_lock_timestamp() -> float:
    """Read the last successful run timestamp from the lock file."""
    try:
        if _LOCK_FILE.exists():
            with open(_LOCK_FILE, "r") as f:
                data = json.load(f)
                return float(data.get("last_run_time", 0.0))
    except Exception:
        pass
    return 0.0


def _write_lock_timestamp(ts: float) -> None:
    """Persist the last successful run timestamp to the lock file."""
    try:
        _LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = _LOCK_FILE.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump({
                "last_run_time": ts,
                "last_run_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts)),
                "cooldown_seconds": AUTO_TUNE_COOLDOWN_SECONDS,
            }, f, indent=2)
        tmp.replace(_LOCK_FILE)
    except Exception as e:
        logger.debug(f"Auto-Tuner lock file write failed (non-blocking): {e}")


# ─────────────────────────────────────────────────────────────────────────────
# OpenAI Client
# ─────────────────────────────────────────────────────────────────────────────
_openai_client = None

def get_openai_client():
    global _openai_client
    if not _openai_client:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            logger.warning("OPENAI_API_KEY not found. LLM Auto-Tuner disabled.")
            return None
        _openai_client = OpenAI(api_key=api_key)
    return _openai_client


# ─────────────────────────────────────────────────────────────────────────────
# LLM Tuning Command Generation
# ─────────────────────────────────────────────────────────────────────────────

def generate_tuning_commands(positions: List[Dict[str, Any]], daily_pnl: float, target_pnl: float) -> List[Dict[str, Any]]:
    """
    Use OpenAI to evaluate positions and propose parameter adjustments (Trading-as-Git).
    """
    client = get_openai_client()
    if not client or not positions:
        return []

    # Filter to only open positions
    open_positions = [p for p in positions if p.get("status") == "open"]
    if not open_positions:
        return []

    # Simplify positions to save tokens
    simplified_positions = []
    for p in open_positions:
        entry = float(p.get("entry_price", 0))
        current = float(p.get("current_price", entry) or entry)
        gain_pct = 0.0
        if entry > 0:
            gain_pct = ((current - entry) / entry) * 100
            
        simplified_positions.append({
            "token": p.get("token_symbol"),
            "entry_price": entry,
            "current_price": current,
            "highest_price": float(p.get("highest_price", current) or current),
            "gain_pct": round(gain_pct, 2),
            "trailing_stop_pct": float(p.get("trailing_stop_pct", 5.0)),
            "wallet": p.get("wallet")
        })

    prompt = f"""
    You are an expert AI Quantitative Trader (like OpenAlice).
    Your goal is to optimize the risk parameters of active crypto meme coin trades.
    
    Context:
    Daily PnL: ${daily_pnl:.2f}
    Daily Target: ${target_pnl:.2f}
    
    Active Positions:
    {json.dumps(simplified_positions, indent=2)}
    
    Rules:
    1. If Daily PnL is close to the Target (e.g. within 10-20%), tighten trailing stops aggressively to protect gains.
    2. Output a JSON array of commands. Each command must have:
       - "token": The token symbol
       - "action": "update_trailing_stop"
       - "new_trailing_stop_pct": A float (e.g., 2.5) representing the tighter stop percentage.
       - "rationale": A detailed explanation of WHY you are making this change (Trading-as-Git commit message).
    3. If no changes are needed, return an empty array [].
    
    Output ONLY valid JSON containing a list of dictionaries. Do not wrap it in a root object.
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a quantitative trading auto-tuner. Output only a JSON array."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            response_format={"type": "json_object"}
        )
        content = response.choices[0].message.content
        if not content:
            return []
            
        result = json.loads(content)
        # Handle cases where the LLM might wrap the array in an object like {"commands": [...]}
        if isinstance(result, dict):
            # Sometimes it wraps with a key, find the first list
            for v in result.values():
                if isinstance(v, list):
                    return v
            return []
        elif isinstance(result, list):
            return result
        return []
        
    except Exception as e:
        logger.error(f"Error querying OpenAI for tuning commands: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Main Entry Point (with dedup)
# ─────────────────────────────────────────────────────────────────────────────

def run_auto_tuner_cycle(force: bool = False) -> None:
    """
    Run a single cycle of the LLM auto-tuner.

    Enforces a 30-minute minimum interval between runs via both an in-memory
    timestamp and a file-based lock (survives restarts).  Pass force=True to
    bypass the cooldown (e.g. from CLI / __main__).
    """
    global _last_run_time

    now = time.time()

    if not force:
        # Check in-memory timestamp first (fast path)
        if _last_run_time > 0 and (now - _last_run_time) < AUTO_TUNE_COOLDOWN_SECONDS:
            remaining = AUTO_TUNE_COOLDOWN_SECONDS - (now - _last_run_time)
            logger.debug(
                f"🧠 Auto-Tuner dedup: skipping — last run {now - _last_run_time:.0f}s ago, "
                f"next in {remaining:.0f}s"
            )
            return

        # Check file-based lock (survives restarts)
        file_ts = _read_lock_timestamp()
        if file_ts > 0 and (now - file_ts) < AUTO_TUNE_COOLDOWN_SECONDS:
            _last_run_time = file_ts  # Sync in-memory with file
            remaining = AUTO_TUNE_COOLDOWN_SECONDS - (now - file_ts)
            logger.debug(
                f"🧠 Auto-Tuner dedup (file lock): skipping — last run {now - file_ts:.0f}s ago, "
                f"next in {remaining:.0f}s"
            )
            return

    engine = get_daily_goal_engine()
    daily_pnl = engine.today_profit_usd
    target_pnl = engine.current_target_usd
    
    logger.info("🧠 Running LLM Auto-Tuner Cycle (30-min interval)...")
    
    positions = load_positions()
    commands = generate_tuning_commands(positions, daily_pnl, target_pnl)

    # Update timestamps regardless of whether commands were generated
    # (we don't want to re-run immediately if there were no open positions)
    _last_run_time = now
    _write_lock_timestamp(now)
    
    if not commands:
        logger.info("🧠 Auto-Tuner: No tuning commands generated.")
        return
        
    updated = False
    for cmd in commands:
        token = cmd.get("token")
        action = cmd.get("action")
        rationale = cmd.get("rationale")
        
        if action == "update_trailing_stop" and "new_trailing_stop_pct" in cmd:
            new_pct = float(cmd["new_trailing_stop_pct"])
            
            # Apply to position
            for p in positions:
                if p.get("status") == "open" and p.get("token_symbol") == token:
                    old_pct = float(p.get("trailing_stop_pct", 5.0))
                    # Only allow tightening (lower percentage means tighter trail)
                    if new_pct < old_pct:
                        p["trailing_stop_pct"] = new_pct
                        logger.info(f"📝 TaG COMMIT [{token}]: {rationale} (Trailing Stop: {old_pct}% -> {new_pct}%)")
                        updated = True
                    break

    if updated:
        save_positions(positions)
        logger.info("💾 Auto-Tuner: Saved updated positions to disk.")

if __name__ == "__main__":
    run_auto_tuner_cycle(force=True)

