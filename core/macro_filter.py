"""
core/macro_filter.py — Macro Market Regime Filter

Detects the current macro crypto market regime (BULL / NEUTRAL / BEAR) using:
  - BTC, ETH, SOL, BNB daily OHLC from CoinGecko (free, no key required)
  - EMA50 and EMA200 position (golden/death cross awareness)
  - 7-day and 30-day price change momentum
  - Fear & Greed Index (alternative.me — free, no key)
  - Altcoin season index (ETH/SOL relative strength vs BTC)

Regime is cached for 1 hour to avoid hammering free APIs.

Outputs a MacroRegime object with:
  - regime: "BULL" | "NEUTRAL" | "BEAR" | "EXTREME_FEAR"
  - score_multiplier: float (0.5–1.15) — applied to gem_score before MIN_GEM_SCORE gate
  - min_score_override: float | None — raises MIN_GEM_SCORE in bear markets
  - details: dict — full breakdown for dashboard display
  - summary: str — human-readable one-liner

Integration points:
  - gem_scanner.py: apply multiplier before score gate
  - dashboard: macro widget on main page
  - main.py: log regime on each cycle
"""

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

CACHE_FILE = Path("output/macro_regime.json")
CACHE_TTL_SECONDS = 3600  # 1 hour — free API rate limit friendly

# CoinGecko coin IDs → display symbols
COINS = {
    "bitcoin":      "BTC",
    "ethereum":     "ETH",
    "solana":       "SOL",
    "binancecoin":  "BNB",
}

# Chain → which coin drives its regime
CHAIN_COIN_MAP = {
    "ethereum":  "ETH",
    "base":      "ETH",
    "arbitrum":  "ETH",
    "polygon":   "ETH",
    "bsc":       "BNB",
    "solana":    "SOL",
}

# ─────────────────────────────────────────────────────────────────────────────
# Data model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CoinRegime:
    symbol: str
    price_usd: float
    ema50: float
    ema200: float
    chg_7d_pct: float
    chg_30d_pct: float
    above_ema50: bool
    above_ema200: bool
    golden_cross: bool          # EMA50 > EMA200
    regime: str                 # "BULL" | "NEUTRAL" | "BEAR"
    regime_score: float         # 0–100


@dataclass
class MacroRegime:
    regime: str                 # "BULL" | "NEUTRAL" | "BEAR" | "EXTREME_FEAR"
    score_multiplier: float     # Applied to gem_score (0.5–1.15)
    min_score_override: float   # Effective MIN_GEM_SCORE for this regime
    fear_greed_value: int       # 0–100
    fear_greed_label: str       # "Extreme Fear" | "Fear" | "Neutral" | "Greed" | "Extreme Greed"
    coins: dict                 # symbol -> CoinRegime
    btc_dominance_signal: str   # "ALTCOIN_SEASON" | "BTC_DOMINANT" | "NEUTRAL"
    summary: str
    timestamp: str
    cached: bool = False
    details: dict = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# EMA calculation
# ─────────────────────────────────────────────────────────────────────────────

def _ema(prices: list[float], period: int) -> float:
    """Calculate EMA for the last `period` candles."""
    if not prices:
        return 0.0
    k = 2 / (period + 1)
    ema = prices[0]
    for p in prices[1:]:
        ema = p * k + ema * (1 - k)
    return ema


# ─────────────────────────────────────────────────────────────────────────────
# Data fetchers
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_coin_history(coin_id: str, days: int = 200) -> list[float]:
    """Fetch daily close prices from CoinGecko. Returns list of closes, oldest first."""
    try:
        r = requests.get(
            f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart",
            params={"vs_currency": "usd", "days": str(days), "interval": "daily"},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        prices = data.get("prices", [])
        return [p[1] for p in prices]
    except Exception as e:
        logger.warning(f"MacroFilter: CoinGecko fetch failed for {coin_id}: {e}")
        return []


def _fetch_fear_greed() -> tuple[int, str]:
    """Fetch current Fear & Greed Index from alternative.me. Returns (value, label)."""
    try:
        r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=10)
        r.raise_for_status()
        data = r.json()
        entry = data.get("data", [{}])[0]
        return int(entry.get("value", 50)), entry.get("value_classification", "Neutral")
    except Exception as e:
        logger.warning(f"MacroFilter: Fear & Greed fetch failed: {e}")
        return 50, "Neutral"


def _fetch_btc_dominance() -> float:
    """Fetch BTC dominance % from CoinGecko global endpoint."""
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/global",
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        return float(data.get("data", {}).get("market_cap_percentage", {}).get("btc", 50.0))
    except Exception as e:
        logger.warning(f"MacroFilter: BTC dominance fetch failed: {e}")
        return 50.0


# ─────────────────────────────────────────────────────────────────────────────
# Coin regime scorer
# ─────────────────────────────────────────────────────────────────────────────

def _score_coin(symbol: str, closes: list[float]) -> CoinRegime:
    """Score a single coin's regime based on EMA position and momentum."""
    if len(closes) < 50:
        return CoinRegime(
            symbol=symbol, price_usd=closes[-1] if closes else 0,
            ema50=0, ema200=0, chg_7d_pct=0, chg_30d_pct=0,
            above_ema50=False, above_ema200=False, golden_cross=False,
            regime="NEUTRAL", regime_score=50.0,
        )

    price = closes[-1]
    ema50 = _ema(closes[-50:], 50)
    ema200 = _ema(closes, 200) if len(closes) >= 200 else _ema(closes, len(closes))
    chg_7d = (price / closes[-7] - 1) * 100 if len(closes) >= 7 else 0
    chg_30d = (price / closes[-30] - 1) * 100 if len(closes) >= 30 else 0

    above50 = price > ema50
    above200 = price > ema200
    golden = ema50 > ema200

    # Score 0–100
    score = 50.0
    if above50:   score += 15
    else:         score -= 15
    if above200:  score += 20
    else:         score -= 20
    if golden:    score += 10
    else:         score -= 10
    score += min(max(chg_7d * 1.5, -15), 15)   # 7d momentum ±15
    score += min(max(chg_30d * 0.5, -10), 10)  # 30d momentum ±10
    score = max(0.0, min(100.0, score))

    if score >= 65:
        regime = "BULL"
    elif score <= 35:
        regime = "BEAR"
    else:
        regime = "NEUTRAL"

    return CoinRegime(
        symbol=symbol, price_usd=price,
        ema50=ema50, ema200=ema200,
        chg_7d_pct=chg_7d, chg_30d_pct=chg_30d,
        above_ema50=above50, above_ema200=above200,
        golden_cross=golden, regime=regime, regime_score=score,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Main regime calculator
# ─────────────────────────────────────────────────────────────────────────────

def calculate_macro_regime() -> MacroRegime:
    """
    Full macro regime calculation. Fetches live data, scores all coins,
    combines with Fear & Greed, and returns a MacroRegime with score multiplier.
    """
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)

    coin_regimes: dict[str, CoinRegime] = {}
    fetch_errors = 0

    for coin_id, symbol in COINS.items():
        closes = _fetch_coin_history(coin_id, days=200)
        if closes:
            coin_regimes[symbol] = _score_coin(symbol, closes)
        else:
            fetch_errors += 1
        time.sleep(0.5)  # CoinGecko free tier rate limit

    fear_greed_val, fear_greed_label = _fetch_fear_greed()
    btc_dominance = _fetch_btc_dominance()

    # ── Composite regime score ──────────────────────────────────────────────
    # BTC is the market leader — weight it most heavily
    weights = {"BTC": 0.45, "ETH": 0.25, "SOL": 0.20, "BNB": 0.10}
    composite = sum(
        coin_regimes[sym].regime_score * w
        for sym, w in weights.items()
        if sym in coin_regimes
    )

    # Fear & Greed adjustment (±10 pts)
    fg_adjustment = (fear_greed_val - 50) * 0.2  # -10 to +10
    composite += fg_adjustment
    composite = max(0.0, min(100.0, composite))

    # ── Determine overall regime ────────────────────────────────────────────
    if fear_greed_val <= 20:
        regime = "EXTREME_FEAR"
    elif composite >= 65:
        regime = "BULL"
    elif composite <= 35:
        regime = "BEAR"
    else:
        regime = "NEUTRAL"

    # ── BTC dominance signal ────────────────────────────────────────────────
    if btc_dominance >= 58:
        btc_dom_signal = "BTC_DOMINANT"   # Alt season NOT in effect
    elif btc_dominance <= 45:
        btc_dom_signal = "ALTCOIN_SEASON"  # Alts outperforming BTC
    else:
        btc_dom_signal = "NEUTRAL"

    # ── Score multiplier ────────────────────────────────────────────────────
    # Applied to gem_score before the MIN_GEM_SCORE gate
    # In bear markets we raise the bar; in bull markets we can be slightly more aggressive
    if regime == "BULL" and btc_dom_signal == "ALTCOIN_SEASON":
        score_multiplier = 1.10   # Altcoin season bull — be more aggressive
        min_score_override = 63.0  # Slightly lower bar
    elif regime == "BULL":
        score_multiplier = 1.05   # Standard bull
        min_score_override = 65.0
    elif regime == "NEUTRAL":
        score_multiplier = 1.00   # No change
        min_score_override = 65.0
    elif regime == "BEAR":
        score_multiplier = 0.90   # Raise the bar — only high-conviction gems
        min_score_override = 70.0
    else:  # EXTREME_FEAR
        score_multiplier = 0.80   # Extreme caution — only exceptional gems
        min_score_override = 75.0

    # ── Human-readable summary ──────────────────────────────────────────────
    btc = coin_regimes.get("BTC")
    btc_str = (
        f"BTC ${btc.price_usd:,.0f} ({btc.chg_7d_pct:+.1f}% 7d, "
        f"{'above' if btc.above_ema200 else 'below'} EMA200)"
        if btc else "BTC: N/A"
    )
    summary = (
        f"{regime} | Score: {composite:.0f}/100 | F&G: {fear_greed_val} ({fear_greed_label}) | "
        f"BTC Dom: {btc_dominance:.1f}% ({btc_dom_signal}) | {btc_str} | "
        f"Gem multiplier: {score_multiplier:.2f}× | Min score: {min_score_override:.0f}"
    )

    result = MacroRegime(
        regime=regime,
        score_multiplier=score_multiplier,
        min_score_override=min_score_override,
        fear_greed_value=fear_greed_val,
        fear_greed_label=fear_greed_label,
        coins=coin_regimes,
        btc_dominance_signal=btc_dom_signal,
        summary=summary,
        timestamp=datetime.now(timezone.utc).isoformat(),
        cached=False,
        details={
            "composite_score": composite,
            "btc_dominance_pct": btc_dominance,
            "fetch_errors": fetch_errors,
            "fg_adjustment": fg_adjustment,
            "weights_used": weights,
        },
    )

    # ── Cache to disk ───────────────────────────────────────────────────────
    try:
        cache_data = {
            "regime": result.regime,
            "score_multiplier": result.score_multiplier,
            "min_score_override": result.min_score_override,
            "fear_greed_value": result.fear_greed_value,
            "fear_greed_label": result.fear_greed_label,
            "btc_dominance_signal": result.btc_dominance_signal,
            "summary": result.summary,
            "timestamp": result.timestamp,
            "details": result.details,
            "coins": {
                sym: {
                    "symbol": cr.symbol,
                    "price_usd": cr.price_usd,
                    "ema50": cr.ema50,
                    "ema200": cr.ema200,
                    "chg_7d_pct": cr.chg_7d_pct,
                    "chg_30d_pct": cr.chg_30d_pct,
                    "above_ema50": cr.above_ema50,
                    "above_ema200": cr.above_ema200,
                    "golden_cross": cr.golden_cross,
                    "regime": cr.regime,
                    "regime_score": cr.regime_score,
                }
                for sym, cr in coin_regimes.items()
            },
        }
        with open(CACHE_FILE, "w") as f:
            json.dump(cache_data, f, indent=2)
    except Exception as e:
        logger.warning(f"MacroFilter: Cache write failed: {e}")

    logger.info(f"MacroFilter: {summary}")
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Cached getter — main entry point used by gem_scanner and dashboard
# ─────────────────────────────────────────────────────────────────────────────

_cached_regime: Optional[MacroRegime] = None
_cache_fetched_at: float = 0.0


def get_macro_regime(force_refresh: bool = False) -> MacroRegime:
    """
    Get current macro regime. Uses in-memory cache (1h TTL) to avoid
    hammering free APIs on every gem scan cycle.

    Args:
        force_refresh: Bypass cache and fetch fresh data.

    Returns:
        MacroRegime with regime, score_multiplier, and full details.
    """
    global _cached_regime, _cache_fetched_at

    now = time.monotonic()
    cache_age = now - _cache_fetched_at

    # Return in-memory cache if fresh
    if not force_refresh and _cached_regime and cache_age < CACHE_TTL_SECONDS:
        _cached_regime.cached = True
        return _cached_regime

    # Try loading from disk cache if in-memory is stale
    if not force_refresh and CACHE_FILE.exists():
        try:
            with open(CACHE_FILE) as f:
                data = json.load(f)
            ts = datetime.fromisoformat(data["timestamp"])
            age_seconds = (datetime.now(timezone.utc) - ts).total_seconds()
            if age_seconds < CACHE_TTL_SECONDS:
                # Reconstruct from disk cache
                coin_regimes = {}
                for sym, cd in data.get("coins", {}).items():
                    coin_regimes[sym] = CoinRegime(**cd)
                regime = MacroRegime(
                    regime=data["regime"],
                    score_multiplier=data["score_multiplier"],
                    min_score_override=data["min_score_override"],
                    fear_greed_value=data["fear_greed_value"],
                    fear_greed_label=data["fear_greed_label"],
                    coins=coin_regimes,
                    btc_dominance_signal=data["btc_dominance_signal"],
                    summary=data["summary"],
                    timestamp=data["timestamp"],
                    cached=True,
                    details=data.get("details", {}),
                )
                _cached_regime = regime
                _cache_fetched_at = now
                return regime
        except Exception as e:
            logger.debug(f"MacroFilter: Disk cache load failed: {e}")

    # Fetch fresh data
    try:
        regime = calculate_macro_regime()
        _cached_regime = regime
        _cache_fetched_at = now
        return regime
    except Exception as e:
        logger.error(f"MacroFilter: Fresh fetch failed: {e}")
        # Return safe neutral fallback
        fallback = MacroRegime(
            regime="NEUTRAL",
            score_multiplier=1.0,
            min_score_override=65.0,
            fear_greed_value=50,
            fear_greed_label="Neutral",
            coins={},
            btc_dominance_signal="NEUTRAL",
            summary="NEUTRAL (fallback — data unavailable)",
            timestamp=datetime.now(timezone.utc).isoformat(),
            cached=True,
            details={"error": str(e)},
        )
        return fallback


def get_chain_regime(chain: str) -> tuple[str, float]:
    """
    Get the regime and score multiplier for a specific chain.
    Uses the chain's primary coin (ETH for EVM, SOL for Solana, BNB for BSC).

    Returns: (regime_str, score_multiplier)
    """
    macro = get_macro_regime()
    chain_coin = CHAIN_COIN_MAP.get(chain.lower(), "BTC")
    coin_regime = macro.coins.get(chain_coin)

    # If chain's primary coin is in a different regime than macro, use the worse of the two
    if coin_regime:
        if coin_regime.regime == "BEAR" or macro.regime in ("BEAR", "EXTREME_FEAR"):
            worst = "BEAR" if macro.regime not in ("EXTREME_FEAR",) else "EXTREME_FEAR"
        elif coin_regime.regime == "BULL" and macro.regime == "BULL":
            worst = "BULL"
        else:
            worst = "NEUTRAL"
        # Chain-specific multiplier: blend macro and coin-specific
        chain_score = coin_regime.regime_score
        macro_score = macro.details.get("composite_score", 50)
        blended = chain_score * 0.6 + macro_score * 0.4
        if blended >= 65:
            chain_mult = macro.score_multiplier
        elif blended <= 35:
            chain_mult = min(macro.score_multiplier, 0.85)
        else:
            chain_mult = min(macro.score_multiplier, 1.0)
        return worst, chain_mult

    return macro.regime, macro.score_multiplier


def apply_macro_adjustment(gem_score: float, chain: str) -> tuple[float, str]:
    """
    Apply macro regime multiplier to a gem score.

    Args:
        gem_score: Raw gem score 0–100
        chain: Token's chain

    Returns:
        (adjusted_score, regime_label)
    """
    regime, multiplier = get_chain_regime(chain)
    adjusted = gem_score * multiplier
    return adjusted, regime


def get_effective_min_score(base_min_score: float, chain: str = "") -> float:
    """
    Get the effective minimum gem score for the current macro regime.
    Overrides the base MIN_GEM_SCORE in bear markets.
    """
    macro = get_macro_regime()
    chain_regime, _ = get_chain_regime(chain) if chain else (macro.regime, 1.0)

    # Use the more conservative of macro and chain-specific overrides
    if chain_regime in ("BEAR", "EXTREME_FEAR") or macro.regime in ("BEAR", "EXTREME_FEAR"):
        return max(base_min_score, macro.min_score_override)
    return base_min_score
