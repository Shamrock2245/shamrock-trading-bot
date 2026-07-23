"""
core/self_improving_agent.py — Self-Improving AI Trading Agent (OpenAlice style).

Implements a closed-loop feedback system that:
1. Ingests trade history from output/trades.json and calculates performance metrics.
2. Detects key failure modes:
   - Weak Entries (small losses < $5 or < -1.5%)
   - Hope Trades (losses held > 30 minutes)
   - Toxic Zone Losses (entries between 08:00 and 14:00 EST resulting in loss)
   - Repeat Losers (coins hitting stop-loss >= 2 times)
3. Uses LLM reasoning (or deterministic rule fallback) to generate self-correction commits.
4. Persists audit reports to output/self_improving_audit.json and updates dynamic blacklist.
5. Enforces a 24-hour cooldown lock to prevent unnecessary re-audits.
"""

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

from config import settings

logger = logging.getLogger(__name__)

# Default model matching llm_auto_tuner.py
DEFAULT_OPENAI_MODEL = "gpt-5-mini"
DEFAULT_INTERVAL_SECONDS = 86400.0  # 24 hours


def get_openai_model() -> str:
    return (os.getenv("OPENAI_MODEL") or DEFAULT_OPENAI_MODEL).strip()


def get_openai_client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        from openai import OpenAI
        return OpenAI(api_key=api_key)
    except Exception as e:
        logger.warning(f"Failed to initialize OpenAI client for self-improving agent: {e}")
        return None


class SelfImprovingAgent:
    def __init__(self, history_file: Optional[str] = None):
        self.history_file_override = history_file
        self.lock_file = Path(os.getenv("SELF_IMPROVING_LOCK_FILE", "output/self_improving_lock.json"))
        self.audit_file = Path(os.getenv("SELF_IMPROVING_AUDIT_FILE", "output/self_improving_audit.json"))

    @property
    def history_file(self) -> Path:
        if self.history_file_override:
            return Path(self.history_file_override)
        trades_env = os.getenv("TRADES_FILE", "output/trades.json")
        path = Path(trades_env)
        if not path.exists() and Path("/app/output/trades.json").exists():
            return Path("/app/output/trades.json")
        return path

    def _read_lock_timestamp(self) -> float:
        try:
            if self.lock_file.exists():
                data = json.loads(self.lock_file.read_text())
                return float(data.get("last_run_time", 0.0))
        except Exception:
            pass
        return 0.0

    def _write_lock_timestamp(self, ts: float) -> None:
        try:
            self.lock_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.lock_file.with_suffix(".tmp")
            data = {
                "last_run_time": ts,
                "last_run_utc": datetime.utcfromtimestamp(ts).isoformat() + "Z"
            }
            tmp.write_text(json.dumps(data, indent=2))
            tmp.replace(self.lock_file)
        except Exception as e:
            logger.debug(f"Self-Improving Agent: Lock file write failed: {e}")

    def load_trade_history(self) -> List[Dict[str, Any]]:
        path = self.history_file
        if not path.exists():
            logger.info(f"Self-Improving Agent: Trade history file not found at {path}")
            return []
        try:
            data = json.loads(path.read_text())
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.error(f"Self-Improving Agent: Error reading {path}: {e}")
            return []

    def calculate_metrics(self, trades: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not trades:
            return {
                "win_rate": 0.0,
                "total_pnl": 0.0,
                "trade_count": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "avg_win_usd": 0.0,
                "avg_loss_usd": 0.0
            }

        closed_pnls = []
        for t in trades:
            pnl = t.get("closedPnl") if "closedPnl" in t else t.get("pnl_usd", t.get("realized_pnl", 0.0))
            try:
                closed_pnls.append(float(pnl or 0.0))
            except (ValueError, TypeError):
                continue

        if not closed_pnls:
            return {
                "win_rate": 0.0,
                "total_pnl": 0.0,
                "trade_count": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "avg_win_usd": 0.0,
                "avg_loss_usd": 0.0
            }

        wins = [p for p in closed_pnls if p > 0]
        losses = [p for p in closed_pnls if p < 0]
        win_rate = (len(wins) / len(closed_pnls)) * 100.0 if closed_pnls else 0.0
        total_pnl = sum(closed_pnls)

        metrics = {
            "win_rate": round(win_rate, 2),
            "total_pnl": round(total_pnl, 2),
            "trade_count": len(closed_pnls),
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "avg_win_usd": round(sum(wins) / len(wins), 2) if wins else 0.0,
            "avg_loss_usd": round(sum(losses) / len(losses), 2) if losses else 0.0
        }

        # ── v32 (OpenAlice retrospective): MFE/MAE excursion calibration ──────
        # From trades that journal mfe_pct/mae_pct, compute how much favorable
        # move winners give back and how deep losers dip before dying. These
        # feed the nightly audit: e.g. if avg winner MFE is 3.1% but avg
        # realized win is 1.2%, the trail is too tight (giving back 60%+).
        mfe_wins, mfe_losses, mae_wins, mae_losses = [], [], [], []
        for t in trades:
            try:
                pnl = float(t.get("closedPnl", t.get("pnl_usd", 0.0)) or 0.0)
                mfe = t.get("mfe_pct")
                mae = t.get("mae_pct")
                if mfe is not None:
                    (mfe_wins if pnl > 0 else mfe_losses).append(float(mfe))
                if mae is not None:
                    (mae_wins if pnl > 0 else mae_losses).append(float(mae))
            except (ValueError, TypeError):
                continue
        def _avg(lst):
            return round(sum(lst) / len(lst), 3) if lst else None
        if mfe_wins or mfe_losses:
            metrics["excursion"] = {
                "avg_mfe_winners_pct": _avg(mfe_wins),
                "avg_mfe_losers_pct": _avg(mfe_losses),   # >1% here = losers that WERE winners → trail/BE too slow
                "avg_mae_winners_pct": _avg(mae_wins),    # how deep winners dip → SL must sit below this
                "avg_mae_losers_pct": _avg(mae_losses),
                "sample_count": len(mfe_wins) + len(mfe_losses),
            }

        return metrics

    def identify_failure_modes(self, trades: List[Dict[str, Any]]) -> Dict[str, Any]:
        recent_trades = trades[-30:] if len(trades) > 30 else trades

        small_losses = []
        hope_trades = []
        toxic_zone_losses = []
        sl_hits_by_coin: Dict[str, int] = {}

        for t in recent_trades:
            pnl = float(t.get("closedPnl", t.get("pnl_usd", 0.0)) or 0.0)
            pnl_pct = float(t.get("pnl_pct", 0.0) or 0.0)
            token = str(t.get("token_symbol") or t.get("coin") or t.get("symbol") or "UNKNOWN").upper()
            exit_reason = str(t.get("exit_reason") or t.get("reason") or "").lower()

            if "sl" in exit_reason or "stop" in exit_reason or pnl < -1.0:
                if token != "UNKNOWN":
                    sl_hits_by_coin[token] = sl_hits_by_coin.get(token, 0) + 1

            if -5.0 <= pnl < 0 or -1.5 <= pnl_pct < 0:
                small_losses.append(t)

            hold_time_sec = float(t.get("holding_duration_seconds", t.get("hold_time", 0)) or 0)
            if pnl < 0 and hold_time_sec > 1800:
                hope_trades.append(t)

            entry_time_str = t.get("entry_time") or t.get("opened_at")
            if entry_time_str and pnl < 0:
                try:
                    if isinstance(entry_time_str, (int, float)):
                        dt = datetime.fromtimestamp(entry_time_str)
                    else:
                        dt = datetime.fromisoformat(str(entry_time_str).replace("Z", "+00:00"))
                    if 8 <= dt.hour < 14:
                        toxic_zone_losses.append(t)
                except Exception:
                    pass

        repeat_losers = [coin for coin, count in sl_hits_by_coin.items() if count >= 2]

        descriptions = []
        if len(small_losses) >= 5:
            descriptions.append(f"Weak Entries: {len(small_losses)} small loss trades (< $5 or < -1.5%).")
        if len(hope_trades) >= 3:
            descriptions.append(f"Hope Trades: {len(hope_trades)} loss trades held for > 30 minutes.")
        if len(toxic_zone_losses) >= 3:
            descriptions.append(f"Toxic Zone Leaks: {len(toxic_zone_losses)} losses entered between 08:00 and 14:00 EST.")
        if repeat_losers:
            descriptions.append(f"Repeat Losers: Coins hitting SL multiple times: {', '.join(repeat_losers)}.")

        return {
            "small_loss_count": len(small_losses),
            "hope_trade_count": len(hope_trades),
            "toxic_loss_count": len(toxic_zone_losses),
            "repeat_losers": repeat_losers,
            "failure_descriptions": descriptions
        }

    def get_llm_correction(self, metrics: Dict[str, Any], failure_data: Dict[str, Any]) -> Dict[str, Any]:
        client = get_openai_client()
        model = get_openai_model()

        if not client:
            logger.info("Self-Improving Agent: No OPENAI_API_KEY found. Executing deterministic rule-based audit.")
            return self._deterministic_fallback_correction(metrics, failure_data)

        prompt = f"""
        You are the Shamrock Self-Improving AI Trading Agent (OpenAlice Trading-as-Git style).
        
        Current Trade Performance Metrics:
        {json.dumps(metrics, indent=2)}

        Detected Failure Patterns:
        {json.dumps(failure_data, indent=2)}

        Current Strategy Rules (v32 "Let Winners Breathe"):
        - Volume Floor: $1,000,000 USD
        - Fast Break-Even: +0.75%
        - 45-Min Rule: Active (tightens SL to -1.5% after 45m if negative)
        - Loss Timeout: 4h force-close for red holds
        - Tiered Trail: +2%→1.25% | +4%→1.75% | +8%→2.5% from peak
        - TP1 Partial: 40% at +2%
        - Daily Open Cap: 24 opens/day, max 2 new per scan
        - Per-Coin Edge Sizing: 0.6x–1.3x by realized win rate
        - Toxic Hours: 08:00-14:00 EST (50% position sizing)
        If `excursion` metrics are present, use them to calibrate:
        - avg_mfe_losers_pct > 1% → losers were once winners → recommend faster break-even
        - avg_mfe_winners_pct much larger than realized avg win → trail too tight → widen ladder
        - avg_mae_winners_pct close to SL distance → SL too tight → widen initial SL

        Task:
        Analyze these findings and propose parameter tuning or dynamic blacklisting recommendations.
        Return ONLY valid JSON matching this schema:
        {{
            "new_params": {{
                "VOLUME_FLOOR_USD": 1500000,
                "FAST_BREAK_EVEN_PCT": 0.75
            }},
            "blacklist_candidates": ["TOKEN1", "TOKEN2"],
            "rationale": "Trading-as-Git commit message explaining the operational adjustment."
        }}
        """

        try:
            kwargs = {
                "model": model,
                "messages": [
                    {"role": "system", "content": "You are a quantitative trading self-tuning engine. Output only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                "response_format": {"type": "json_object"}
            }
            if model.lower().startswith("gpt-5") or "5.6" in model.lower():
                kwargs["max_completion_tokens"] = 1000
            else:
                kwargs["temperature"] = 0.2
                kwargs["max_tokens"] = 1000

            resp = client.chat.completions.create(**kwargs)
            content = resp.choices[0].message.content
            if content:
                res = json.loads(content)
                if isinstance(res, dict):
                    return res
        except Exception as e:
            logger.error(f"Self-Improving Agent: LLM call failed with model={model}: {e}")

        return self._deterministic_fallback_correction(metrics, failure_data)

    def _deterministic_fallback_correction(self, metrics: Dict[str, Any], failure_data: Dict[str, Any]) -> Dict[str, Any]:
        new_params = {}
        repeat_losers = failure_data.get("repeat_losers", [])

        if failure_data.get("small_loss_count", 0) >= 5:
            new_params["VOLUME_FLOOR_USD"] = 1500000
        if failure_data.get("hope_trade_count", 0) >= 3:
            new_params["FAST_BREAK_EVEN_PCT"] = 0.5

        rationale = "Deterministic Fallback Audit: "
        parts = []
        if new_params:
            parts.append(f"Adjusted params {new_params}")
        if repeat_losers:
            parts.append(f"Blacklisted repeat losers {repeat_losers}")
        if not parts:
            parts.append("Metrics within normal parameters; no immediate tuning changes required.")
        rationale += " | ".join(parts)

        return {
            "new_params": new_params,
            "blacklist_candidates": repeat_losers,
            "rationale": rationale
        }

    def apply_correction(self, update: Dict[str, Any]) -> None:
        rationale = update.get("rationale", "No rationale provided.")
        logger.info(f"📝 TaG COMMIT (Self-Improving Agent): {rationale}")

        blacklist_candidates = update.get("blacklist_candidates", [])
        if blacklist_candidates:
            try:
                from core.hl_scanner_winning_tuning import winning_entry_filter
                for token in blacklist_candidates:
                    if hasattr(winning_entry_filter, "update_blacklist"):
                        winning_entry_filter.update_blacklist(token, sl_count=3)
                    elif hasattr(winning_entry_filter, "add_to_blacklist"):
                        winning_entry_filter.add_to_blacklist(token, sl_count=3)
                logger.info(f"Self-Improving Agent: Added {blacklist_candidates} to dynamic blacklist.")
            except Exception as e:
                logger.warning(f"Self-Improving Agent: Dynamic blacklist application failed: {e}")

        # Persist audit report
        try:
            self.audit_file.parent.mkdir(parents=True, exist_ok=True)
            report = {
                "timestamp_utc": datetime.utcnow().isoformat() + "Z",
                "update": update
            }
            tmp = self.audit_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(report, indent=2))
            tmp.replace(self.audit_file)
            logger.info(f"Self-Improving Agent: Persisted audit report to {self.audit_file}")
        except Exception as e:
            logger.error(f"Self-Improving Agent: Failed to save audit file: {e}")

    def run_self_audit(self, force: bool = False) -> Optional[Dict[str, Any]]:
        if not getattr(settings, "SELF_IMPROVEMENT_ENABLED", True):
            logger.info("Self-Improving Agent: Feature disabled via settings.SELF_IMPROVEMENT_ENABLED.")
            return None

        interval = float(getattr(settings, "SELF_IMPROVEMENT_INTERVAL_SECONDS", DEFAULT_INTERVAL_SECONDS))
        now = time.time()

        if not force:
            last_ts = self._read_lock_timestamp()
            if last_ts > 0 and (now - last_ts) < interval:
                remaining = interval - (now - last_ts)
                logger.info(f"Self-Improving Agent: Cooldown active — next audit in {remaining:.0f}s.")
                return None

        logger.info("🧠 Self-Improving Agent: Starting performance audit...")

        try:
            trades = self.load_trade_history()
            metrics = self.calculate_metrics(trades)
            failure_data = self.identify_failure_modes(trades)
            correction = self.get_llm_correction(metrics, failure_data)

            if correction:
                self.apply_correction(correction)

            self._write_lock_timestamp(now)
            return correction

        except Exception as e:
            logger.error(f"Self-Improving Agent: Performance audit failed: {e}", exc_info=True)
            return None


# Global instance
improving_agent = SelfImprovingAgent()
