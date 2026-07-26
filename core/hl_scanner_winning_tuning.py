"""
core/hl_scanner_winning_tuning.py — Winning entry filters for HL perps

Wired into core/hl_perps_scanner.py → _execute_signal / scan sizing when
WINNING_ENTRY_FILTER_ENABLED=true.

Closes entry-side leaks from trade_history (29):
  - Illiquid / thin names → $1M dayNtlVlm floor
  - Choppy 08–14 ET → size ×0.5 (via winning_risk_manager toxic zone)
  - Repeat SL hits → dynamic blacklist (3+ SL in 24h)

VWAP: optional. If vwap_15m is provided and >0, require price ≥ VWAP for longs
(price ≤ VWAP for shorts). Missing VWAP does NOT block (scanner may not compute it).
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class WinningEntryConfig:
    enabled: bool = True
    # Soft floor: below this → size cut (not hard reject). CSV40: $1M binary starved mid-caps.
    min_volume_usd: float = 500_000.0
    # Hard floor: below this → reject (illiquid trash / thin books)
    hard_volume_usd: float = 250_000.0
    # Between hard and soft → size multiplier
    low_volume_size_multiplier: float = 0.5
    # Above this → mild size boost for deep books
    high_volume_usd: float = 2_000_000.0
    high_volume_size_multiplier: float = 1.1
    use_vwap_filter: bool = True
    narrative_score_threshold: float = 0.8
    narrative_gate_bypass: bool = True
    max_atr_pct: float = 5.0
    high_vol_size_multiplier: float = 0.5
    blacklist_sl_hits: int = 2
    blacklist_window_sec: float = 12 * 3600
    hard_blacklist: List[str] = field(
        default_factory=lambda: [
            "TRB", "GRASS", "EIGEN", "MET", "SOL", "ENA", "ZEC", "ETH",
            "BSV", "CRV", "PENDLE", "UNI", "ACE", "ADA", "STABLE", "SUI",
            "KAITO", "APE", "HEMI", "ONDO", "MORPHO", "LIT"
        ]
    )


def default_entry_config() -> WinningEntryConfig:
    return WinningEntryConfig(
        enabled=_env_bool("WINNING_ENTRY_FILTER_ENABLED", True),
        min_volume_usd=_env_float("MIN_VOLUME_USD", 500_000.0),
        hard_volume_usd=_env_float("MIN_VOLUME_HARD_USD", 250_000.0),
        low_volume_size_multiplier=_env_float("LOW_VOLUME_SIZE_MULT", 0.5),
        high_volume_usd=_env_float("HIGH_VOLUME_USD", 2_000_000.0),
        high_volume_size_multiplier=_env_float("HIGH_VOLUME_SIZE_MULT", 1.1),
        use_vwap_filter=_env_bool("USE_VWAP_FILTER", True),
        narrative_score_threshold=_env_float("NARRATIVE_SCORE_THRESHOLD", 0.8),
        narrative_gate_bypass=_env_bool("NARRATIVE_GATE_BYPASS", True),
        max_atr_pct=_env_float("MAX_ATR_PCT", 5.0),
        high_vol_size_multiplier=_env_float("HIGH_VOL_SIZE_MULTIPLIER", 0.5),
        blacklist_sl_hits=int(_env_float("WINNING_BLACKLIST_SL_HITS", 2)),
        blacklist_window_sec=_env_float("WINNING_BLACKLIST_WINDOW_SEC", 12 * 3600),
    )


@dataclass
class WinningEntryFilter:
    """Stateful entry gate + SL-hit blacklist (process memory; clears on restart)."""

    config: WinningEntryConfig = field(default_factory=default_entry_config)
    # symbol → list of unix timestamps of SL hits
    _sl_hits: Dict[str, List[float]] = field(default_factory=dict)
    dynamic_blacklist: List[str] = field(default_factory=list)


    def _prune_hits(self, symbol: str, now: Optional[float] = None) -> None:
        now = now if now is not None else time.time()
        window = self.config.blacklist_window_sec
        hits = self._sl_hits.get(symbol, [])
        hits = [t for t in hits if now - t <= window]
        if hits:
            self._sl_hits[symbol] = hits
        else:
            self._sl_hits.pop(symbol, None)
        # Drop from blacklist if under threshold after prune
        if symbol in self.dynamic_blacklist and len(hits) < self.config.blacklist_sl_hits:
            self.dynamic_blacklist = [s for s in self.dynamic_blacklist if s != symbol]

    def record_sl_hit(self, symbol: str, now: Optional[float] = None) -> None:
        """Call when a position stops out — feeds dynamic blacklist."""
        symbol = (symbol or "").upper()
        if not symbol:
            return
        now = now if now is not None else time.time()
        self._prune_hits(symbol, now)
        self._sl_hits.setdefault(symbol, []).append(now)
        count = len(self._sl_hits[symbol])
        if count >= self.config.blacklist_sl_hits and symbol not in self.dynamic_blacklist:
            self.dynamic_blacklist.append(symbol)
            logger.warning(
                f"[{symbol}] 🚫 Winning blacklist: {count} SL hits in "
                f"{self.config.blacklist_window_sec / 3600:.0f}h"
            )

    def update_blacklist(self, symbol: str, sl_count: int) -> None:
        """Manus-compatible API: set blacklist if sl_count ≥ threshold."""
        symbol = (symbol or "").upper()
        if sl_count >= self.config.blacklist_sl_hits and symbol not in self.dynamic_blacklist:
            self.dynamic_blacklist.append(symbol)
            logger.warning(f"[{symbol}] 🚫 Added to blacklist: {sl_count} SL hits in 24h")

    add_to_blacklist = update_blacklist

    def clear_blacklist(self) -> None:
        if self.dynamic_blacklist:
            logger.info(f"Clearing dynamic blacklist: {self.dynamic_blacklist}")
        self.dynamic_blacklist = []
        self._sl_hits.clear()

    def validate_entry(self, token_data: Dict) -> Dict:
        """
        Validate if a token meets Winning entry criteria.

        token_data keys (all optional except volume for hard gate when present):
          symbol, current_price, volume_24h_usd, vwap_15m, atr_pct,
          narrative_score, sl_count_24h, side ("long"|"short")

        Returns: {approved, reason, position_size_multiplier}
        """
        cfg = self.config
        if not cfg.enabled:
            return {
                "approved": True,
                "reason": "winning_entry_filter_disabled",
                "position_size_multiplier": 1.0,
            }

        symbol = str(token_data.get("symbol", "UNKNOWN")).upper()
        volume = float(token_data.get("volume_24h_usd") or 0)
        curr_px = float(token_data.get("current_price") or 0)
        vwap = float(token_data.get("vwap_15m") or 0)
        atr_pct = float(token_data.get("atr_pct") or 0)
        narrative_score = float(token_data.get("narrative_score") or 0)
        sl_count = int(token_data.get("sl_count_24h") or 0)
        side = str(token_data.get("side") or "long").lower()

        size_multiplier = 1.0
        self._prune_hits(symbol)

        # ── 0. Hard blacklist (toxic tokens from trade_history diagnosis) ─────
        if symbol in cfg.hard_blacklist:
            logger.warning(f"[{symbol}] ❌ Entry Blocked: static hard blacklist")
            return {
                "approved": False,
                "reason": "hard_blacklist",
                "position_size_multiplier": 0.0,
            }

        # ── 1. Dynamic blacklist ──────────────────────────────────────────────
        if symbol in self.dynamic_blacklist or sl_count >= cfg.blacklist_sl_hits:
            if sl_count >= cfg.blacklist_sl_hits:
                self.update_blacklist(symbol, sl_count)
            logger.warning(f"[{symbol}] ❌ Entry Blocked: dynamic blacklist / SL spam")
            return {
                "approved": False,
                "reason": "dynamic_blacklist",
                "position_size_multiplier": 0.0,
            }


        # ── 2. Volume tiers (CSV40 / live STBL-GMX starvation fix) ────────────
        # Only when volume is provided (>0). Missing data → log + allow so a
        # bad ctx cache does not halt all trading.
        #   < hard_volume_usd      → reject (too thin)
        #   hard..soft (min_vol)   → size × low_volume_size_multiplier
        #   soft..high             → full size
        #   ≥ high_volume_usd      → mild size boost
        if volume > 0:
            hard_floor = min(cfg.hard_volume_usd, cfg.min_volume_usd)
            if volume < hard_floor:
                logger.warning(
                    f"[{symbol}] ❌ Entry Blocked: Volume ${volume:,.0f} < "
                    f"hard floor ${hard_floor:,.0f}"
                )
                return {
                    "approved": False,
                    "reason": f"volume_below_hard_${volume:,.0f}",
                    "position_size_multiplier": 0.0,
                }
            if volume < cfg.min_volume_usd:
                size_multiplier *= cfg.low_volume_size_multiplier
                logger.info(
                    f"[{symbol}] ⚠️  Volume ${volume:,.0f} < soft floor "
                    f"${cfg.min_volume_usd:,.0f} → size ×{cfg.low_volume_size_multiplier}"
                )
            elif volume >= cfg.high_volume_usd:
                size_multiplier *= cfg.high_volume_size_multiplier
                logger.info(
                    f"[{symbol}] 💎 Volume ${volume:,.0f} ≥ high tier "
                    f"${cfg.high_volume_usd:,.0f} → size ×{cfg.high_volume_size_multiplier}"
                )

        # ── 3. VWAP filter (only when vwap supplied) ──────────────────────────
        if cfg.use_vwap_filter and vwap > 0 and curr_px > 0:
            if side == "short":
                # Shorts want price at/above VWAP (fade into strength)
                if curr_px < vwap:
                    logger.warning(
                        f"[{symbol}] ❌ Short blocked: price ${curr_px:.8f} < VWAP ${vwap:.8f}"
                    )
                    return {
                        "approved": False,
                        "reason": "price_below_vwap_short",
                        "position_size_multiplier": 0.0,
                    }
            else:
                if curr_px < vwap:
                    logger.warning(
                        f"[{symbol}] ❌ Long blocked: price ${curr_px:.8f} < VWAP ${vwap:.8f}"
                    )
                    return {
                        "approved": False,
                        "reason": "price_below_vwap",
                        "position_size_multiplier": 0.0,
                    }

        # ── 4. High ATR → cut size ────────────────────────────────────────────
        if atr_pct > cfg.max_atr_pct:
            size_multiplier = cfg.high_vol_size_multiplier
            logger.info(
                f"[{symbol}] ⚠️  High ATR {atr_pct:.2f}% → size ×{size_multiplier}"
            )

        # ── 5. Narrative bonus (soft approval path — does not skip blacklist/vol)
        if (
            cfg.narrative_gate_bypass
            and narrative_score >= cfg.narrative_score_threshold
        ):
            logger.info(
                f"[{symbol}] 🎯 Narrative bonus score={narrative_score:.2f} → approved"
            )
            return {
                "approved": True,
                "reason": f"narrative_bonus_{narrative_score:.2f}",
                "position_size_multiplier": size_multiplier,
            }

        logger.info(
            f"[{symbol}] ✅ Winning entry OK | vol=${volume:,.0f} | size_mult={size_multiplier}"
        )
        return {
            "approved": True,
            "reason": "all_filters_passed",
            "position_size_multiplier": size_multiplier,
        }


# Global instance
winning_entry_filter = WinningEntryFilter()
