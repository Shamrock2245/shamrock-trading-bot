"""
core/bluechip_anchor.py — Blue-Chip Anchor Portfolio Manager

Always maintains a configurable % of total capital in the strongest
upward-trending blue-chip asset (ETH, BTC/WBTC, SOL, BNB).

Purpose:
  - Ensures the portfolio always has exposure to assets that trend up
    over time, providing a "floor" of value even when gem trades fail
  - Acts as the rotation target during Capital Preservation Mode
  - Auto-rebalances to the strongest momentum blue chip each day

Logic:
  1. Score each blue chip using 7d + 24h momentum from Moralis price API
  2. Select the top-scoring blue chip as the "anchor asset"
  3. Maintain BLUECHIP_ANCHOR_PCT (default 20%) of total capital in it
  4. Rebalance when:
       a. Anchor % drifts > ANCHOR_DRIFT_TOLERANCE_PCT from target
       b. A different blue chip has > ANCHOR_SWITCH_THRESHOLD_PCT better momentum
       c. Capital Preservation Mode is activated (rotate ALL freed capital in)

Integration:
  from core.bluechip_anchor import BluechipAnchor
  anchor = BluechipAnchor()
  status = anchor.evaluate(portfolio_usd=5000.0)
  if status["needs_rebalance"]:
      # Execute anchor rebalance trade
"""

import json
import logging
import os
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
ANCHOR_STATE_FILE = Path(os.environ.get(
    "BLUECHIP_ANCHOR_STATE_FILE",
    os.path.join(os.path.dirname(__file__), "..", "output", "bluechip_anchor.json"),
))

# % of total portfolio to keep in blue-chip anchor
ANCHOR_TARGET_PCT = float(os.environ.get("BLUECHIP_ANCHOR_PCT", "20.0"))

# Rebalance if anchor drifts more than this from target
ANCHOR_DRIFT_TOLERANCE_PCT = float(os.environ.get("ANCHOR_DRIFT_TOLERANCE_PCT", "5.0"))

# Switch to a different blue chip if it has this much better momentum score
ANCHOR_SWITCH_THRESHOLD_PCT = float(os.environ.get("ANCHOR_SWITCH_THRESHOLD_PCT", "15.0"))

# Minimum portfolio size to activate anchor (don't anchor tiny accounts)
ANCHOR_MIN_PORTFOLIO_USD = float(os.environ.get("ANCHOR_MIN_PORTFOLIO_USD", "100.0"))

# Cooldown between rebalances (hours)
ANCHOR_REBALANCE_COOLDOWN_HOURS = float(os.environ.get("ANCHOR_REBALANCE_COOLDOWN_HOURS", "6.0"))

# Blue-chip definitions: symbol → {chain, address, coingecko_id}
BLUE_CHIPS = {
    "ETH": {
        "chain": "ethereum",
        "address": "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE",  # Native ETH
        "coingecko_id": "ethereum",
        "is_native": True,
        "priority": 1,  # Preferred anchor (most liquid)
    },
    "WBTC": {
        "chain": "ethereum",
        "address": "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599",
        "coingecko_id": "wrapped-bitcoin",
        "is_native": False,
        "priority": 2,
    },
    "SOL": {
        "chain": "solana",
        "address": "So11111111111111111111111111111111111111112",
        "coingecko_id": "solana",
        "is_native": True,
        "priority": 3,
    },
    "BNB": {
        "chain": "bsc",
        "address": "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE",  # Native BNB
        "coingecko_id": "binancecoin",
        "is_native": True,
        "priority": 4,
    },
}

# Momentum scoring weights
MOMENTUM_WEIGHTS = {
    "change_7d": 0.45,    # 7-day trend is the primary signal
    "change_24h": 0.30,   # 24h momentum
    "change_1h": 0.15,    # Short-term direction
    "volume_trend": 0.10, # Volume confirms momentum
}


@dataclass
class AnchorState:
    """Persistent state for the blue-chip anchor manager."""
    # Current anchor
    anchor_symbol: str = "ETH"
    anchor_chain: str = "ethereum"
    anchor_address: str = ""
    anchor_target_pct: float = ANCHOR_TARGET_PCT
    anchor_current_usd: float = 0.0
    anchor_current_pct: float = 0.0

    # Last rebalance
    last_rebalance_at: str = ""
    last_rebalance_reason: str = ""
    rebalance_count: int = 0

    # Momentum scores (last evaluated)
    last_scores: dict = None  # symbol → score
    last_evaluated_at: str = ""

    # Stats
    total_anchor_value_locked: float = 0.0  # Cumulative value protected
    switches: int = 0  # How many times we switched blue chips

    def __post_init__(self):
        if self.last_scores is None:
            self.last_scores = {}


def _load_state() -> AnchorState:
    try:
        ANCHOR_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        if ANCHOR_STATE_FILE.exists():
            data = json.loads(ANCHOR_STATE_FILE.read_text())
            state = AnchorState()
            for k, v in data.items():
                if k in AnchorState.__dataclass_fields__:
                    setattr(state, k, v)
            return state
    except Exception as e:
        logger.debug(f"Anchor state load error: {e}")
    return AnchorState()


def _save_state(state: AnchorState) -> None:
    try:
        ANCHOR_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        ANCHOR_STATE_FILE.write_text(json.dumps(asdict(state), indent=2))
    except Exception as e:
        logger.warning(f"Anchor state save error: {e}")


def _score_blue_chip(symbol: str, price_data: dict) -> float:
    """
    Score a blue chip 0–100 based on momentum signals.
    Higher = stronger upward trend = better anchor candidate.
    """
    change_7d = price_data.get("price_change_percentage_7d", 0.0) or 0.0
    change_24h = price_data.get("price_change_percentage_24h", 0.0) or 0.0
    change_1h = price_data.get("price_change_percentage_1h", 0.0) or 0.0
    volume_change = price_data.get("volume_change_24h_pct", 0.0) or 0.0

    # Normalize each signal to 0–100
    # 7d: +20% → 100, -20% → 0, linear
    score_7d = max(0.0, min(100.0, (change_7d + 20.0) / 40.0 * 100.0))
    # 24h: +10% → 100, -10% → 0, linear
    score_24h = max(0.0, min(100.0, (change_24h + 10.0) / 20.0 * 100.0))
    # 1h: +3% → 100, -3% → 0, linear
    score_1h = max(0.0, min(100.0, (change_1h + 3.0) / 6.0 * 100.0))
    # Volume: +50% → 100, -50% → 0
    score_vol = max(0.0, min(100.0, (volume_change + 50.0) / 100.0 * 100.0))

    composite = (
        score_7d * MOMENTUM_WEIGHTS["change_7d"]
        + score_24h * MOMENTUM_WEIGHTS["change_24h"]
        + score_1h * MOMENTUM_WEIGHTS["change_1h"]
        + score_vol * MOMENTUM_WEIGHTS["volume_trend"]
    )

    return round(composite, 1)


def _fetch_blue_chip_prices() -> dict:
    """
    Fetch price data for all blue chips from CoinGecko (free tier).
    Returns {symbol: {price_usd, change_24h, change_7d, change_1h, volume_change_24h_pct}}
    """
    ids = ",".join(bc["coingecko_id"] for bc in BLUE_CHIPS.values())
    url = (
        f"https://api.coingecko.com/api/v3/coins/markets"
        f"?vs_currency=usd&ids={ids}"
        f"&price_change_percentage=1h,24h,7d"
        f"&order=market_cap_desc&per_page=10&page=1"
    )
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        result = {}
        cg_id_to_symbol = {bc["coingecko_id"]: sym for sym, bc in BLUE_CHIPS.items()}

        for item in data:
            sym = cg_id_to_symbol.get(item["id"])
            if not sym:
                continue
            result[sym] = {
                "price_usd": item.get("current_price", 0.0),
                "price_change_percentage_24h": item.get("price_change_percentage_24h", 0.0),
                "price_change_percentage_7d": item.get("price_change_percentage_7d_in_currency", 0.0),
                "price_change_percentage_1h": item.get("price_change_percentage_1h_in_currency", 0.0),
                "volume_24h": item.get("total_volume", 0.0),
                "market_cap": item.get("market_cap", 0.0),
                "volume_change_24h_pct": 0.0,  # CoinGecko free tier doesn't provide this
            }
        return result
    except Exception as e:
        logger.warning(f"Blue chip price fetch failed: {e}")
        return {}


class BluechipAnchor:
    """
    Manages the blue-chip anchor allocation.
    Call evaluate() each cycle to get rebalance recommendations.
    """

    def __init__(self):
        self._state = _load_state()
        logger.info(
            f"BluechipAnchor initialized | "
            f"anchor={self._state.anchor_symbol} | "
            f"target={self._state.anchor_target_pct:.0f}% | "
            f"current=${self._state.anchor_current_usd:,.2f}"
        )

    @property
    def anchor_symbol(self) -> str:
        return self._state.anchor_symbol

    @property
    def anchor_current_usd(self) -> float:
        return self._state.anchor_current_usd

    @property
    def anchor_target_pct(self) -> float:
        return self._state.anchor_target_pct

    @property
    def state(self) -> AnchorState:
        return self._state

    def evaluate(
        self,
        portfolio_usd: float,
        anchor_current_usd: Optional[float] = None,
        force_rebalance: bool = False,
    ) -> dict:
        """
        Evaluate whether the anchor needs rebalancing.

        Args:
            portfolio_usd: Total portfolio value in USD
            anchor_current_usd: Current USD value held in anchor asset (if known)
            force_rebalance: Force rebalance regardless of cooldown (used in preservation mode)

        Returns:
            {
                "needs_rebalance": bool,
                "action": "buy" | "sell" | "switch" | "hold",
                "current_symbol": str,
                "recommended_symbol": str,
                "current_usd": float,
                "target_usd": float,
                "delta_usd": float,  # Positive = buy more, negative = sell
                "reason": str,
                "scores": dict,  # All blue chip momentum scores
                "anchor_pct": float,  # Current anchor % of portfolio
            }
        """
        if portfolio_usd < ANCHOR_MIN_PORTFOLIO_USD:
            return {
                "needs_rebalance": False, "action": "hold",
                "current_symbol": self._state.anchor_symbol,
                "recommended_symbol": self._state.anchor_symbol,
                "current_usd": 0.0, "target_usd": 0.0, "delta_usd": 0.0,
                "reason": "Portfolio too small for anchor", "scores": {},
                "anchor_pct": 0.0,
            }

        now_utc = datetime.now(timezone.utc)
        state = self._state

        # Update current anchor value
        if anchor_current_usd is not None:
            state.anchor_current_usd = anchor_current_usd
        current_usd = state.anchor_current_usd
        current_pct = (current_usd / portfolio_usd * 100) if portfolio_usd > 0 else 0.0
        state.anchor_current_pct = round(current_pct, 2)

        target_usd = round(portfolio_usd * ANCHOR_TARGET_PCT / 100.0, 2)

        # ── Score all blue chips ──────────────────────────────────────────────
        price_data = _fetch_blue_chip_prices()
        scores = {}
        for sym in BLUE_CHIPS:
            if sym in price_data:
                scores[sym] = _score_blue_chip(sym, price_data[sym])
            else:
                # Fallback: use priority (ETH > WBTC > SOL > BNB)
                scores[sym] = 50.0 - (BLUE_CHIPS[sym]["priority"] * 5)

        state.last_scores = scores
        state.last_evaluated_at = now_utc.isoformat()

        # ── Select best blue chip ─────────────────────────────────────────────
        best_symbol = max(scores, key=lambda s: scores[s])
        best_score = scores[best_symbol]
        current_score = scores.get(state.anchor_symbol, 50.0)

        # Log scores
        scores_str = " | ".join(f"{s}={v:.0f}" for s, v in sorted(scores.items(), key=lambda x: -x[1]))
        logger.debug(f"Blue chip scores: {scores_str} | current={state.anchor_symbol}({current_score:.0f}) | best={best_symbol}({best_score:.0f})")

        # ── Check cooldown ────────────────────────────────────────────────────
        cooldown_ok = True
        if state.last_rebalance_at and not force_rebalance:
            try:
                last_rb = datetime.fromisoformat(state.last_rebalance_at)
                if last_rb.tzinfo is None:
                    last_rb = last_rb.replace(tzinfo=timezone.utc)
                hours_since = (now_utc - last_rb).total_seconds() / 3600
                if hours_since < ANCHOR_REBALANCE_COOLDOWN_HOURS:
                    cooldown_ok = False
            except Exception:
                pass

        # ── Determine action ──────────────────────────────────────────────────
        needs_rebalance = False
        action = "hold"
        reason = "Anchor within tolerance"
        recommended_symbol = state.anchor_symbol

        # Check if we should switch blue chips
        score_improvement = best_score - current_score
        should_switch = (
            best_symbol != state.anchor_symbol
            and score_improvement >= ANCHOR_SWITCH_THRESHOLD_PCT
            and cooldown_ok
        )

        if should_switch:
            recommended_symbol = best_symbol
            needs_rebalance = True
            action = "switch"
            reason = (
                f"Switching {state.anchor_symbol}→{best_symbol}: "
                f"{best_symbol} momentum {best_score:.0f} vs {state.anchor_symbol} {current_score:.0f} "
                f"(+{score_improvement:.0f} pts improvement)"
            )
        else:
            recommended_symbol = state.anchor_symbol

        # Check if anchor size needs adjustment
        drift_pct = abs(current_pct - ANCHOR_TARGET_PCT)
        if drift_pct > ANCHOR_DRIFT_TOLERANCE_PCT and cooldown_ok:
            needs_rebalance = True
            if current_usd < target_usd:
                action = "buy" if action == "hold" else action
                reason = (
                    f"Anchor underfunded: {current_pct:.1f}% vs target {ANCHOR_TARGET_PCT:.0f}% "
                    f"(need ${target_usd - current_usd:,.0f} more in {recommended_symbol})"
                )
            else:
                action = "sell" if action == "hold" else action
                reason = (
                    f"Anchor overfunded: {current_pct:.1f}% vs target {ANCHOR_TARGET_PCT:.0f}% "
                    f"(release ${current_usd - target_usd:,.0f} from {recommended_symbol})"
                )

        if force_rebalance and not needs_rebalance:
            needs_rebalance = True
            action = "buy"
            reason = "Capital Preservation Mode: rotating freed capital to blue-chip anchor"

        delta_usd = round(target_usd - current_usd, 2)

        # ── Execute state update if rebalancing ───────────────────────────────
        if needs_rebalance:
            if action == "switch":
                old_sym = state.anchor_symbol
                state.anchor_symbol = recommended_symbol
                state.anchor_chain = BLUE_CHIPS[recommended_symbol]["chain"]
                state.anchor_address = BLUE_CHIPS[recommended_symbol]["address"]
                state.switches += 1
                logger.info(f"🔄 ANCHOR SWITCH: {old_sym} → {recommended_symbol} | {reason}")
            state.last_rebalance_at = now_utc.isoformat()
            state.last_rebalance_reason = reason
            state.rebalance_count += 1
            if current_usd > 0:
                state.total_anchor_value_locked += current_usd

        _save_state(state)

        return {
            "needs_rebalance": needs_rebalance,
            "action": action,
            "current_symbol": self._state.anchor_symbol,
            "recommended_symbol": recommended_symbol,
            "current_usd": current_usd,
            "target_usd": target_usd,
            "delta_usd": delta_usd,
            "reason": reason,
            "scores": scores,
            "anchor_pct": current_pct,
            "price_data": {sym: price_data.get(sym, {}) for sym in BLUE_CHIPS},
        }

    def get_status(self) -> dict:
        """Return current anchor status for dashboard display."""
        s = self._state
        return {
            "anchor_symbol": s.anchor_symbol,
            "anchor_chain": s.anchor_chain,
            "anchor_target_pct": s.anchor_target_pct,
            "anchor_current_usd": s.anchor_current_usd,
            "anchor_current_pct": s.anchor_current_pct,
            "last_rebalance_at": s.last_rebalance_at,
            "last_rebalance_reason": s.last_rebalance_reason,
            "rebalance_count": s.rebalance_count,
            "switches": s.switches,
            "last_scores": s.last_scores,
            "total_anchor_value_locked": s.total_anchor_value_locked,
        }

    def record_anchor_value(self, usd_value: float) -> None:
        """Update the current anchor position value (call from position monitor)."""
        self._state.anchor_current_usd = round(usd_value, 2)
        self._state.anchor_current_pct = round(
            usd_value / max(1.0, self._state.anchor_current_usd) * 100, 2
        )
        _save_state(self._state)
