"""
data/providers/moralis_intelligence.py — Full Moralis Suite Intelligence Layer

Implements every Moralis endpoint NOT already covered by moralis_money.py,
moralis_wallet.py, moralis_price.py, or moralis_solana.py.

NEW ENDPOINTS ADDED:
  Token Signals (EVM + Solana):
    GET /erc20/{address}/top-traders          → Top profitable traders (smart money)
    GET /erc20/{address}/snipers              → REMOVED June 2026 — see moralis_sniper_detection.py
    GET /tokens/{address}/score/historical    → Token score timeseries (trending safer/riskier)
    POST /tokens/analytics/timeseries         → Analytics timeseries (momentum building/dying)
    GET /erc20/{address}/holders              → Current holder list with balances
    GET /erc20/{address}/holders/stats        → Holder concentration (Gini, top10%, etc.)
    GET /erc20/{address}/holders/historical   → Holder growth timeseries
    GET /erc20/{address}/swaps                → Full swap history for a token
    GET /pairs/{address}/swaps                → Real-time swap stream for a pair

  Wallet Intelligence (EVM):
    GET /wallets/{address}/history            → Fully decoded wallet activity feed
    GET /wallets/{address}/approvals          → Dangerous approval exposure
    GET /wallets/{address}/chains             → Multi-chain activity summary
    GET /wallets/{address}/defi/positions     → DeFi positions per protocol
    GET /wallets/{address}/defi/summary       → DeFi protocol summary

  Market Macro (MIGRATED June 2026 — original /volume/* endpoints removed):
    CoinGecko /api/v3/global fallback         → Global market cap, BTC dominance
    DeFiLlama /v2/chains fallback             → Chain TVL/volume metrics
    GET /tokens/categories                    → Category metrics (meme, defi, etc.)

  Universal (Cross-chain):
    GET /tokens/search                        → Token search by name/symbol
    GET /tokens/trending                      → Trending tokens cross-chain
    POST /tokens/analytics                    → Cross-chain analytics (already in moralis_money but re-exposed here with richer parsing)

  Solana Extended:
    GET /token/{network}/{address}/score/historical  → Solana score timeseries
    GET /token/{network}/{address}/holders/historical → Solana holder growth
    GET /token/{network}/{address}/holders/stats      → Solana holder metrics
    GET /token/{network}/exchange/pumpfun/new         → Pump.fun NEW tokens (catch them earliest)
    GET /token/{network}/exchange/pumpfun/bonding     → Pump.fun BONDING tokens

All results feed into:
  1. enrich_candidate_full() — master enrichment function
  2. calculate_intelligence_score_boost() — converts new signals into gem_score delta
  3. get_smart_money_wallets() — returns top trader addresses for copy-trade signals
  4. get_chain_heat() — macro chain health for position sizing decisions

Rate limiting: shared 25 req/min bucket (same as moralis_money.py).
Cache TTL: 5 min for fast-moving signals, 10 min for structural data.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from data.http_session import get_session

from config import settings

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────
MORALIS_API_KEY: str = getattr(settings, "MORALIS_API_KEY", "")
BASE_URL = "https://deep-index.moralis.io/api/v2.2"
SOL_BASE_URL = "https://solana-gateway.moralis.io"
SOL_NETWORK = "mainnet"

CHAIN_HEX: dict[str, str] = {
    "ethereum": "0x1",
    "base":     "0x2105",
    "arbitrum": "0xa4b1",
    "polygon":  "0x89",
    "bsc":      "0x38",
    "avalanche":"0xa86a",
}

CHAIN_MAP: dict[str, str] = {
    "ethereum": "eth",
    "base":     "base",
    "arbitrum": "arbitrum",
    "polygon":  "polygon",
    "bsc":      "bsc",
    "avalanche":"avalanche",
}

# Cache TTLs
FAST_CACHE_TTL = 300    # 5 min — fast-moving signals (snipers, swaps, traders)
SLOW_CACHE_TTL = 600    # 10 min — structural data (holders, chain metrics)

_cache: dict[str, dict] = {}

# Rate limiter — shared Pro-tier global limiter (60 RPS, CU-budget-aware)
from data.providers.moralis_rate_limiter import rate_check as _rate_check


# ─────────────────────────────────────────────────────────────────────────────
# Internal Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _headers() -> dict:
    return {"accept": "application/json", "X-API-Key": MORALIS_API_KEY}

def _json_headers() -> dict:
    return {
        "accept": "application/json",
        "Content-Type": "application/json",
        "X-API-Key": MORALIS_API_KEY,
    }

def _available(chain: str = "ethereum") -> bool:
    if not MORALIS_API_KEY:
        return False
    return chain in CHAIN_HEX or chain == "solana"

def _is_cached(key: str, ttl: int = SLOW_CACHE_TTL) -> bool:
    if key not in _cache:
        return False
    return time.time() - _cache[key]["ts"] < ttl

def _set_cache(key: str, data) -> None:
    _cache[key] = {"data": data, "ts": time.time()}

def _get_cache(key: str):
    return _cache[key]["data"]

def _safe_float(val) -> float:
    try:
        return float(val or 0)
    except (TypeError, ValueError):
        return 0.0

def _safe_int(val) -> int:
    try:
        return int(val or 0)
    except (TypeError, ValueError):
        return 0


# ─────────────────────────────────────────────────────────────────────────────
# 1. TOP TRADERS — Smart Money Identification
#    GET /erc20/{address}/top-traders
#    Returns the most profitable wallets trading this token.
#    TRADING SIGNAL: Copy-trade these wallets. If they're buying → strong signal.
# ─────────────────────────────────────────────────────────────────────────────

def get_top_traders(token_address: str, chain: str, limit: int = 10) -> list[dict]:
    """
    Get the top profitable traders for a token.
    Returns wallets sorted by realized PnL — these are the smart money addresses.
    """
    if not _available(chain) or chain not in CHAIN_HEX:
        return []
    cache_key = f"top_traders_{chain}_{token_address.lower()}"
    if _is_cached(cache_key, FAST_CACHE_TTL):
        return _get_cache(cache_key)
    _rate_check()
    try:
        resp = get_session().get(
            f"{BASE_URL}/erc20/{token_address}/top-traders",
            params={"chain": CHAIN_HEX[chain], "limit": limit},
            headers=_headers(),
            timeout=8,
        )
        if resp.status_code in (400, 404, 429):
            return []
        resp.raise_for_status()
        data = resp.json()
        traders = data.get("result", data) if isinstance(data, dict) else data
        result = []
        for t in (traders or []):
            result.append({
                "address":           t.get("address", ""),
                "realized_profit_usd": _safe_float(t.get("realized_profit_usd", 0)),
                "realized_profit_pct": _safe_float(t.get("realized_profit_percentage", 0)),
                "buy_volume_usd":    _safe_float(t.get("buy_volume_usd", 0)),
                "sell_volume_usd":   _safe_float(t.get("sell_volume_usd", 0)),
                "avg_buy_price":     _safe_float(t.get("avg_buy_price_usd", 0)),
                "avg_sell_price":    _safe_float(t.get("avg_sell_price_usd", 0)),
                "is_bot":            bool(t.get("is_bot", False)),
            })
        _set_cache(cache_key, result)
        logger.debug(f"Top traders: {len(result)} for {token_address[:8]} on {chain}")
        return result
    except Exception as e:
        logger.debug(f"Top traders error {chain}/{token_address[:8]}: {e}")
        return []


def get_top_trader_signal(token_address: str, chain: str) -> dict:
    """
    Distill top trader data into a trading signal.
    Returns: smart_money_buying (bool), avg_profit_pct (float), top_trader_count (int)
    """
    traders = get_top_traders(token_address, chain, limit=10)
    if not traders:
        return {"smart_money_buying": False, "avg_profit_pct": 0.0, "top_trader_count": 0,
                "total_smart_money_usd": 0.0, "smart_money_score": 50.0}

    # Filter out bots
    real_traders = [t for t in traders if not t.get("is_bot", False)]
    if not real_traders:
        return {"smart_money_buying": False, "avg_profit_pct": 0.0, "top_trader_count": 0,
                "total_smart_money_usd": 0.0, "smart_money_score": 50.0}

    profitable = [t for t in real_traders if t["realized_profit_usd"] > 0]
    avg_profit_pct = sum(t["realized_profit_pct"] for t in profitable) / max(len(profitable), 1)
    total_buy_vol = sum(t["buy_volume_usd"] for t in real_traders)

    # Smart money score: 0-100 based on profitability and volume
    smart_money_score = min(100.0, (
        (len(profitable) / max(len(real_traders), 1)) * 50  # % profitable traders
        + min(50.0, avg_profit_pct / 4)                      # avg profit % (200% = 50pts)
    ))

    return {
        "smart_money_buying":    len(profitable) >= 3,
        "avg_profit_pct":        round(avg_profit_pct, 1),
        "top_trader_count":      len(real_traders),
        "profitable_trader_count": len(profitable),
        "total_smart_money_usd": round(total_buy_vol, 2),
        "smart_money_score":     round(smart_money_score, 1),
        "top_trader_addresses":  [t["address"] for t in profitable[:5]],
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2. EVM SNIPERS — Launch Sniper Detection
#    MIGRATED June 4 2026: GET /erc20/{address}/snipers REMOVED from Moralis.
#    Now uses moralis_sniper_detection.discover_sniper_convergence() which
#    queries GET /wallets/{addr}/swaps for known alpha wallets — richer signal.
#    TRADING SIGNAL: High sniper convergence = coordinated dump setup = REJECT
# ─────────────────────────────────────────────────────────────────────────────

def get_evm_snipers(token_address: str, chain: str) -> dict:
    """
    Detect sniper bot activity on an EVM token at launch.
    MIGRATED June 4 2026: /erc20/{addr}/snipers REMOVED.
    Now uses moralis_sniper_detection (wallet swap convergence) for same signal.
    Returns sniper count, total sniped USD, and risk level.
    """
    if not _available(chain) or chain not in CHAIN_HEX:
        return {"sniper_count": 0, "risk_level": "unknown", "total_sniped_usd": 0.0}
    cache_key = f"evm_snipers_{chain}_{token_address.lower()}"
    if _is_cached(cache_key, FAST_CACHE_TTL):
        return _get_cache(cache_key)
    try:
        from data.providers.moralis_sniper_detection import discover_sniper_convergence
        convergences = discover_sniper_convergence()
        token_lower = token_address.lower()
        match = next(
            (c for c in convergences
             if c.get("token_address", "").lower() == token_lower
             and c.get("chain", "") == chain),
            None
        )
        sniper_count = match.get("sniper_count", 0) if match else 0
        total_sniped = _safe_float(match.get("total_buy_usd", 0)) if match else 0.0

        if sniper_count >= 10:
            risk = "critical"
        elif sniper_count >= 5:
            risk = "high"
        elif sniper_count >= 3:
            risk = "medium"
        elif sniper_count >= 1:
            risk = "low"
        else:
            risk = "none"

        result = {
            "sniper_count":     sniper_count,
            "risk_level":       risk,
            "total_sniped_usd": round(total_sniped, 2),
            "snipers":          match.get("sniper_wallets", [])[:5] if match else [],
        }
        _set_cache(cache_key, result)
        if sniper_count > 0:
            logger.info(f"🎯 EVM Snipers: {sniper_count} on {token_address[:8]}/{chain} "
                        f"(${total_sniped:,.0f} sniped, risk={risk})")
        return result
    except Exception as e:
        logger.debug(f"EVM snipers error {chain}/{token_address[:8]}: {e}")
        return {"sniper_count": 0, "risk_level": "unknown", "total_sniped_usd": 0.0}


# ─────────────────────────────────────────────────────────────────────────────
# 3. TOKEN SCORE TIMESERIES — Safety Trend
#    GET /tokens/{address}/score/historical
#    Shows whether a token is getting safer or riskier over time.
#    TRADING SIGNAL: Rising score = improving fundamentals = BUY signal
# ─────────────────────────────────────────────────────────────────────────────

def get_token_score_timeseries(token_address: str, chain: str, days: int = 7) -> dict:
    """
    Get historical token score to detect safety trend.
    Returns: score_trend ('improving'|'stable'|'declining'), score_delta, latest_score

    Solana Token Score timeseries sunsets July 31 2026 — neutral response, 0 CU.
    """
    if str(chain).lower() == "solana":
        return {"score_trend": "stable", "score_delta": 0.0, "latest_score": 50.0, "source": "solana_score_sunset"}
    if not _available(chain) or chain not in CHAIN_HEX:
        return {"score_trend": "stable", "score_delta": 0.0, "latest_score": 50.0}
    cache_key = f"score_ts_{chain}_{token_address.lower()}_{days}"
    if _is_cached(cache_key, SLOW_CACHE_TTL):
        return _get_cache(cache_key)
    try:
        from core.moralis_cu_budget import cu_budget
        if not cu_budget.can_afford("token_score_historical"):
            return {"score_trend": "stable", "score_delta": 0.0, "latest_score": 50.0}
    except Exception:
        pass
    _rate_check()
    try:
        resp = get_session().get(
            f"{BASE_URL}/tokens/{token_address}/score/historical",
            params={"chain": CHAIN_HEX[chain], "days": days},
            headers=_headers(),
            timeout=8,
        )
        try:
            from data.providers.moralis_http import _parse_request_weight, _record_usage
            _record_usage("token_score_historical", _parse_request_weight(resp) or 150)
        except Exception:
            pass
        if resp.status_code in (400, 404, 429):
            return {"score_trend": "stable", "score_delta": 0.0, "latest_score": 50.0}
        resp.raise_for_status()
        data = resp.json()
        scores = data.get("result", data) if isinstance(data, dict) else data
        if not scores or len(scores) < 2:
            return {"score_trend": "stable", "score_delta": 0.0, "latest_score": 50.0}

        # Sort by timestamp ascending
        scores_sorted = sorted(scores, key=lambda x: x.get("timestamp", ""))
        latest = _safe_float(scores_sorted[-1].get("score", 50))
        oldest = _safe_float(scores_sorted[0].get("score", 50))
        delta = latest - oldest

        if delta >= 5:
            trend = "improving"
        elif delta <= -5:
            trend = "declining"
        else:
            trend = "stable"

        result = {
            "score_trend":   trend,
            "score_delta":   round(delta, 1),
            "latest_score":  round(latest, 1),
            "oldest_score":  round(oldest, 1),
            "data_points":   len(scores),
        }
        _set_cache(cache_key, result)
        return result
    except Exception as e:
        logger.debug(f"Score timeseries error {chain}/{token_address[:8]}: {e}")
        return {"score_trend": "stable", "score_delta": 0.0, "latest_score": 50.0}


# ─────────────────────────────────────────────────────────────────────────────
# 4. TOKEN ANALYTICS TIMESERIES — Momentum Trend
#    POST /tokens/analytics/timeseries
#    Shows whether buy/sell volume momentum is building or dying.
#    TRADING SIGNAL: Rising buyers + falling sellers = STRONG BUY
# ─────────────────────────────────────────────────────────────────────────────

def get_analytics_timeseries(token_address: str, chain: str, timeframe: str = "1h") -> dict:
    """
    Get analytics timeseries to detect momentum trend.
    timeframe: '5m', '1h', '4h', '1d'
    Returns: momentum_trend, buyer_acceleration, volume_trend
    """
    if not _available(chain) or chain not in CHAIN_HEX:
        return {"momentum_trend": "neutral", "buyer_acceleration": 1.0, "volume_trend": "flat"}
    cache_key = f"analytics_ts_{chain}_{token_address.lower()}_{timeframe}"
    if _is_cached(cache_key, FAST_CACHE_TTL):
        return _get_cache(cache_key)
    _rate_check()
    try:
        resp = get_session().post(
            f"{BASE_URL}/tokens/analytics/timeseries",
            json={
                "tokens": [{"token_address": token_address, "chain": CHAIN_HEX[chain]}],
                "timeframe": timeframe,
            },
            headers=_json_headers(),
            timeout=10,
        )
        if resp.status_code in (400, 404, 429):
            return {"momentum_trend": "neutral", "buyer_acceleration": 1.0, "volume_trend": "flat"}
        resp.raise_for_status()
        data = resp.json()
        series = data.get("result", []) if isinstance(data, dict) else data
        if not series or len(series) < 2:
            return {"momentum_trend": "neutral", "buyer_acceleration": 1.0, "volume_trend": "flat"}

        # Analyze last 3 vs previous 3 periods
        recent = series[-3:]
        previous = series[-6:-3] if len(series) >= 6 else series[:3]

        recent_buyers = sum(_safe_float(p.get("buyers", 0)) for p in recent)
        prev_buyers = sum(_safe_float(p.get("buyers", 0)) for p in previous)
        recent_vol = sum(_safe_float(p.get("buy_volume_usd", 0)) for p in recent)
        prev_vol = sum(_safe_float(p.get("buy_volume_usd", 0)) for p in previous)

        buyer_accel = (recent_buyers / max(prev_buyers, 1))
        vol_accel = (recent_vol / max(prev_vol, 1))

        if buyer_accel >= 1.5 and vol_accel >= 1.3:
            trend = "accelerating"
        elif buyer_accel >= 1.2 or vol_accel >= 1.2:
            trend = "building"
        elif buyer_accel <= 0.6 or vol_accel <= 0.6:
            trend = "dying"
        elif buyer_accel <= 0.8 or vol_accel <= 0.8:
            trend = "fading"
        else:
            trend = "neutral"

        result = {
            "momentum_trend":     trend,
            "buyer_acceleration": round(buyer_accel, 2),
            "volume_acceleration": round(vol_accel, 2),
            "recent_buyers":      _safe_int(recent_buyers),
            "recent_buy_vol":     round(recent_vol, 2),
        }
        _set_cache(cache_key, result)
        return result
    except Exception as e:
        logger.debug(f"Analytics timeseries error {chain}/{token_address[:8]}: {e}")
        return {"momentum_trend": "neutral", "buyer_acceleration": 1.0, "volume_trend": "flat"}


# ─────────────────────────────────────────────────────────────────────────────
# 5. TOKEN HOLDERS — Holder Distribution
#    GET /erc20/{address}/holders
#    GET /erc20/{address}/holders/stats
#    GET /erc20/{address}/holders/historical
#    TRADING SIGNAL: Rising holder count + low concentration = healthy growth
# ─────────────────────────────────────────────────────────────────────────────

def get_holder_stats(token_address: str, chain: str) -> dict:
    """
    Get holder distribution statistics.
    Returns: total_holders, top10_pct, gini_coefficient, concentration_risk
    """
    if not _available(chain) or chain not in CHAIN_HEX:
        return {"total_holders": 0, "top10_pct": 0.0, "concentration_risk": "unknown"}
    cache_key = f"holder_stats_{chain}_{token_address.lower()}"
    if _is_cached(cache_key, SLOW_CACHE_TTL):
        return _get_cache(cache_key)
    _rate_check()
    try:
        resp = get_session().get(
            f"{BASE_URL}/erc20/{token_address}/holders/stats",
            params={"chain": CHAIN_HEX[chain]},
            headers=_headers(),
            timeout=8,
        )
        if resp.status_code in (400, 404, 429):
            return {"total_holders": 0, "top10_pct": 0.0, "concentration_risk": "unknown"}
        resp.raise_for_status()
        data = resp.json()

        total_holders = _safe_int(data.get("total_holders", 0))
        top10_pct = _safe_float(data.get("top_10_holders_percentage", 0))
        top1_pct = _safe_float(data.get("top_1_holder_percentage", 0))

        # Concentration risk assessment
        if top10_pct >= 80 or top1_pct >= 50:
            concentration_risk = "critical"
        elif top10_pct >= 60 or top1_pct >= 30:
            concentration_risk = "high"
        elif top10_pct >= 40:
            concentration_risk = "medium"
        else:
            concentration_risk = "low"

        result = {
            "total_holders":      total_holders,
            "top10_pct":          round(top10_pct, 1),
            "top1_pct":           round(top1_pct, 1),
            "concentration_risk": concentration_risk,
            "holder_score":       max(0.0, 100.0 - top10_pct),  # Lower concentration = higher score
        }
        _set_cache(cache_key, result)
        return result
    except Exception as e:
        logger.debug(f"Holder stats error {chain}/{token_address[:8]}: {e}")
        return {"total_holders": 0, "top10_pct": 0.0, "concentration_risk": "unknown"}


def get_holder_growth(token_address: str, chain: str, days: int = 7) -> dict:
    """
    Historical holder growth.

    EVM + Solana historical holder REST endpoints sunset July 31 2026.
    Without Data Feeds historical_balances recipe return neutral (0 CU).
    Current EVM holders/stats endpoints remain supported elsewhere.
    """
    return {
        "holder_trend": "stable",
        "growth_rate_pct": 0.0,
        "holder_velocity": 0.0,
        "source": "historical_holders_sunset",
    }


# ─────────────────────────────────────────────────────────────────────────────
# 6. TOKEN SWAPS — Real-time Swap Feed
#    GET /erc20/{address}/swaps
#    GET /pairs/{address}/swaps
#    TRADING SIGNAL: Large buy swaps from known wallets = whale accumulation
# ─────────────────────────────────────────────────────────────────────────────

def get_token_swaps(token_address: str, chain: str, limit: int = 20) -> list[dict]:
    """
    Get recent swap transactions for a token.
    Returns list of swaps with buyer/seller info, USD values, and entity labels.
    """
    if not _available(chain) or chain not in CHAIN_HEX:
        return []
    cache_key = f"token_swaps_{chain}_{token_address.lower()}"
    if _is_cached(cache_key, FAST_CACHE_TTL):
        return _get_cache(cache_key)
    _rate_check()
    try:
        resp = get_session().get(
            f"{BASE_URL}/erc20/{token_address}/swaps",
            params={"chain": CHAIN_HEX[chain], "limit": limit, "order": "DESC"},
            headers=_headers(),
            timeout=8,
        )
        if resp.status_code in (400, 404, 429):
            return []
        resp.raise_for_status()
        data = resp.json()
        swaps = data.get("result", data) if isinstance(data, dict) else data
        result = []
        for s in (swaps or [])[:limit]:
            # Entity label: Moralis tags known addresses (exchanges, funds, MEV bots)
            entity_label = (
                s.get("address_label")
                or s.get("wallet_label")
                or s.get("from_address_entity")
                or s.get("to_address_entity")
                or ""
            )
            entity_type = (
                s.get("address_entity_type")
                or s.get("from_address_entity_type")
                or s.get("to_address_entity_type")
                or ""
            )
            result.append({
                "tx_hash":         s.get("transaction_hash", ""),
                "block_timestamp": s.get("block_timestamp", ""),
                "wallet_address":  s.get("wallet_address", ""),
                "transaction_type": s.get("transaction_type", ""),  # buy/sell
                "usd_amount":      _safe_float(s.get("usd_amount", 0)),
                "token_amount":    _safe_float(s.get("token_amount", 0)),
                "price_usd":       _safe_float(s.get("price_usd", 0)),
                "entity_label":    entity_label,
                "entity_type":     entity_type.lower(),
            })
        _set_cache(cache_key, result)
        return result
    except Exception as e:
        logger.debug(f"Token swaps error {chain}/{token_address[:8]}: {e}")
        return []


def get_swap_entity_summary(token_address: str, chain: str) -> dict:
    """
    Aggregate entity labels from recent swaps to detect institutional interest.

    Returns:
        {
            "exchange_buying": bool,       # Known exchange is accumulating
            "fund_buying": bool,           # Known fund/VC is accumulating
            "mev_bot_count": int,          # MEV bots trading this token
            "labeled_buyer_count": int,    # Buyers with known entity labels
            "labeled_seller_count": int,   # Sellers with known entity labels
            "entity_labels": list[str],    # Unique entity labels seen
            "entity_conviction_score": float,  # 0-100 score
        }
    """
    swaps = get_token_swaps(token_address, chain, limit=50)
    if not swaps:
        return {
            "exchange_buying": False, "fund_buying": False, "mev_bot_count": 0,
            "labeled_buyer_count": 0, "labeled_seller_count": 0,
            "entity_labels": [], "entity_conviction_score": 50.0,
        }

    # Classify entities from swap labels
    EXCHANGE_KEYWORDS = {"binance", "coinbase", "kraken", "okx", "bybit", "kucoin", "gate", "bitfinex", "huobi", "htx", "mexc", "upbit"}
    FUND_KEYWORDS = {"capital", "ventures", "fund", "labs", "research", "dao", "treasury"}
    BOT_KEYWORDS = {"mev", "bot", "flashbot", "arbitrage", "sandwich"}

    exchange_buys = 0
    fund_buys = 0
    mev_count = 0
    labeled_buyers = 0
    labeled_sellers = 0
    unique_labels = set()

    for swap in swaps:
        label = (swap.get("entity_label") or "").lower()
        etype = (swap.get("entity_type") or "").lower()
        is_buy = swap.get("transaction_type") == "buy"

        if not label and not etype:
            continue

        unique_labels.add(swap.get("entity_label", ""))

        # Classify by type
        is_exchange = any(kw in label for kw in EXCHANGE_KEYWORDS) or etype in ("exchange", "cex")
        is_fund = any(kw in label for kw in FUND_KEYWORDS) or etype in ("fund", "vc", "institution")
        is_bot = any(kw in label for kw in BOT_KEYWORDS) or etype in ("mev", "bot")

        if is_buy:
            labeled_buyers += 1
            if is_exchange:
                exchange_buys += 1
            if is_fund:
                fund_buys += 1
        else:
            labeled_sellers += 1

        if is_bot:
            mev_count += 1

    # Conviction score: exchanges and funds buying = high conviction
    score = 50.0
    if exchange_buys >= 2:
        score += 20.0
    elif exchange_buys >= 1:
        score += 10.0
    if fund_buys >= 1:
        score += 15.0
    if mev_count >= 3:
        score -= 10.0  # Heavy MEV activity = front-running risk
    if labeled_buyers > labeled_sellers:
        score += 5.0

    result = {
        "exchange_buying": exchange_buys > 0,
        "fund_buying": fund_buys > 0,
        "mev_bot_count": mev_count,
        "labeled_buyer_count": labeled_buyers,
        "labeled_seller_count": labeled_sellers,
        "entity_labels": [l for l in unique_labels if l],
        "entity_conviction_score": round(min(100.0, max(0.0, score)), 1),
    }
    return result


def analyze_swap_flow(token_address: str, chain: str) -> dict:
    """
    Analyze recent swap flow to detect whale accumulation patterns.
    Returns: large_buy_count, large_sell_count, net_flow_usd, whale_buying (bool)
    """
    swaps = get_token_swaps(token_address, chain, limit=50)
    if not swaps:
        return {"large_buy_count": 0, "large_sell_count": 0, "net_flow_usd": 0.0,
                "whale_buying": False, "swap_flow_score": 50.0}

    LARGE_SWAP_USD = 5000  # $5k+ = whale swap
    large_buys = [s for s in swaps if s["transaction_type"] == "buy" and s["usd_amount"] >= LARGE_SWAP_USD]
    large_sells = [s for s in swaps if s["transaction_type"] == "sell" and s["usd_amount"] >= LARGE_SWAP_USD]
    total_buy_vol = sum(s["usd_amount"] for s in swaps if s["transaction_type"] == "buy")
    total_sell_vol = sum(s["usd_amount"] for s in swaps if s["transaction_type"] == "sell")
    net_flow = total_buy_vol - total_sell_vol

    # Swap flow score: 0-100 based on buy dominance
    total_vol = total_buy_vol + total_sell_vol
    if total_vol > 0:
        buy_dominance = total_buy_vol / total_vol
        swap_flow_score = min(100.0, buy_dominance * 120)  # 83% buy = 100 score
    else:
        swap_flow_score = 50.0

    return {
        "large_buy_count":  len(large_buys),
        "large_sell_count": len(large_sells),
        "net_flow_usd":     round(net_flow, 2),
        "total_buy_vol":    round(total_buy_vol, 2),
        "total_sell_vol":   round(total_sell_vol, 2),
        "whale_buying":     len(large_buys) > len(large_sells) and net_flow > 0,
        "swap_flow_score":  round(swap_flow_score, 1),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 7. WALLET INTELLIGENCE — Our Own Wallet Analysis
#    GET /wallets/{address}/history
#    GET /wallets/{address}/approvals
#    GET /wallets/{address}/chains
#    GET /wallets/{address}/defi/positions
#    TRADING SIGNAL: Know our exposure, approvals, and DeFi positions
# ─────────────────────────────────────────────────────────────────────────────

def get_wallet_history(wallet_address: str, limit: int = 50) -> list[dict]:
    """
    Get fully decoded wallet activity feed.
    Returns human-readable transaction history with categories.
    """
    if not MORALIS_API_KEY:
        return []
    cache_key = f"wallet_hist_{wallet_address.lower()}"
    if _is_cached(cache_key, FAST_CACHE_TTL):
        return _get_cache(cache_key)
    _rate_check()
    try:
        resp = get_session().get(
            f"{BASE_URL}/wallets/{wallet_address}/history",
            params={"limit": limit},
            headers=_headers(),
            timeout=10,
        )
        if resp.status_code in (400, 404, 429):
            return []
        resp.raise_for_status()
        data = resp.json()
        history = data.get("result", data) if isinstance(data, dict) else data
        result = []
        for tx in (history or [])[:limit]:
            result.append({
                "hash":          tx.get("hash", ""),
                "block_timestamp": tx.get("block_timestamp", ""),
                "category":      tx.get("category", ""),
                "summary":       tx.get("summary", ""),
                "chain":         tx.get("chain", ""),
                "value_usd":     _safe_float(tx.get("value_usd", 0)),
            })
        _set_cache(cache_key, result)
        return result
    except Exception as e:
        logger.debug(f"Wallet history error {wallet_address[:8]}: {e}")
        return []


def get_wallet_approvals(wallet_address: str, chain: str) -> list[dict]:
    """
    Get dangerous token approval/allowance exposure.
    Returns list of approvals with risk assessment.
    """
    if not _available(chain) or chain not in CHAIN_HEX:
        return []
    cache_key = f"wallet_approvals_{chain}_{wallet_address.lower()}"
    if _is_cached(cache_key, SLOW_CACHE_TTL):
        return _get_cache(cache_key)
    _rate_check()
    try:
        resp = get_session().get(
            f"{BASE_URL}/wallets/{wallet_address}/approvals",
            params={"chain": CHAIN_HEX[chain]},
            headers=_headers(),
            timeout=8,
        )
        if resp.status_code in (400, 404, 429):
            return []
        resp.raise_for_status()
        data = resp.json()
        approvals = data.get("result", data) if isinstance(data, dict) else data
        result = []
        for a in (approvals or []):
            result.append({
                "token_address":  a.get("token_address", ""),
                "token_symbol":   a.get("token_symbol", ""),
                "spender":        a.get("spender", ""),
                "spender_name":   a.get("spender_name", ""),
                "allowance_usd":  _safe_float(a.get("allowance_usd", 0)),
                "is_unlimited":   bool(a.get("is_unlimited", False)),
                "risk":           "high" if a.get("is_unlimited") else "medium",
            })
        _set_cache(cache_key, result)
        return result
    except Exception as e:
        logger.debug(f"Wallet approvals error {chain}/{wallet_address[:8]}: {e}")
        return []


def get_wallet_chain_activity(wallet_address: str) -> dict:
    """
    Get multi-chain activity summary for a wallet.
    Returns which chains are active and transaction counts.
    """
    if not MORALIS_API_KEY:
        return {}
    cache_key = f"wallet_chains_{wallet_address.lower()}"
    if _is_cached(cache_key, SLOW_CACHE_TTL):
        return _get_cache(cache_key)
    _rate_check()
    try:
        resp = get_session().get(
            f"{BASE_URL}/wallets/{wallet_address}/chains",
            headers=_headers(),
            timeout=8,
        )
        if resp.status_code in (400, 404, 429):
            return {}
        resp.raise_for_status()
        data = resp.json()
        chains = data.get("active_chains", data) if isinstance(data, dict) else []
        result = {}
        for c in (chains or []):
            chain_name = c.get("chain", "")
            result[chain_name] = {
                "first_transaction": c.get("first_transaction", {}).get("block_timestamp", ""),
                "last_transaction":  c.get("last_transaction", {}).get("block_timestamp", ""),
                "tx_count":          _safe_int(c.get("transactions_count", 0)),
            }
        _set_cache(cache_key, result)
        return result
    except Exception as e:
        logger.debug(f"Wallet chain activity error {wallet_address[:8]}: {e}")
        return {}


_ZERO_ADDRESSES = {
    "",
    "0x0000000000000000000000000000000000000000",
    "0x000000000000000000000000000000000000dead",
}


def get_wallet_defi_positions(wallet_address: str, chain: str) -> list[dict]:
    """
    Get DeFi protocol positions for a wallet.
    Returns positions in Uniswap, Aave, Compound, Jito, Save, Kamino, etc.
    Supports chain="all" to fetch and aggregate across all major EVM chains in one call.
    """
    if not wallet_address or wallet_address.lower() in _ZERO_ADDRESSES:
        return []
    
    params = {}
    if chain == "all":
        if not MORALIS_API_KEY:
            return []
        params["chains"] = ",".join(CHAIN_MAP.values())
    elif chain == "solana":
        if not MORALIS_API_KEY:
            return []
        params["chain"] = "solana"
    else:
        if not _available(chain):
            return []
        chain_hex = CHAIN_HEX.get(chain)
        if not chain_hex:
            return []
        params["chain"] = chain_hex

    cache_key = f"defi_pos_{chain}_{wallet_address.lower()}"
    if _is_cached(cache_key, SLOW_CACHE_TTL):
        return _get_cache(cache_key)
    _rate_check()
    try:
        resp = get_session().get(
            f"{BASE_URL}/wallets/{wallet_address}/defi/positions",
            params=params,
            headers=_headers(),
            timeout=10,
        )
        if resp.status_code in (400, 404, 429):
            return []
        resp.raise_for_status()
        data = resp.json()
        positions = data.get("result", data) if isinstance(data, dict) else data
        result = []
        for p in (positions or []):
            result.append({
                "protocol_name":  p.get("protocol_name", ""),
                "protocol_id":    p.get("protocol_id", ""),
                "position_type":  p.get("position_type", ""),
                "usd_value":      _safe_float(p.get("usd_value", 0)),
                "tokens":         p.get("tokens", []),
            })
        _set_cache(cache_key, result)
        return result
    except Exception as e:
        logger.debug(f"DeFi positions error {chain}/{wallet_address[:8]}: {e}")
        return []


def get_all_wallet_defi_exposure(wallet_address: str) -> dict:
    """
    Get total DeFi exposure across all chains for a wallet.
    Returns total_defi_usd and per-protocol breakdown.
    """
    total_usd = 0.0
    protocols: dict[str, float] = {}
    for chain in CHAIN_HEX:
        positions = get_wallet_defi_positions(wallet_address, chain)
        for p in positions:
            usd = p.get("usd_value", 0.0)
            total_usd += usd
            proto = p.get("protocol_name", "unknown")
            protocols[proto] = protocols.get(proto, 0.0) + usd
    return {
        "total_defi_usd": round(total_usd, 2),
        "protocols":      protocols,
        "protocol_count": len(protocols),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 8. CHAIN METRICS — Macro Market Heat
#    MIGRATED June 4 2026: GET /volume/chains and GET /volume/categories REMOVED.
#    Replacement: DeFiLlama /v2/chains for EVM chain TVL/volume, plus
#    Moralis /tokens/trending aggregated by chain for activity signal.
#    TRADING SIGNAL: Hot chain = more liquidity, better fills, more gems
# ─────────────────────────────────────────────────────────────────────────────

# DeFiLlama chain name mapping (their slugs differ from ours)
_DEFILLAMA_CHAIN_MAP = {
    "ethereum": "Ethereum",
    "base":     "Base",
    "arbitrum": "Arbitrum",
    "polygon":  "Polygon",
    "bsc":      "BSC",
    "avalanche":"Avalanche",
    "solana":   "Solana",
}

def get_chain_metrics() -> dict:
    """
    Get volume/TVL metrics for all chains.
    MIGRATED June 4 2026: /volume/chains removed from Moralis.
    Now uses DeFiLlama /v2/chains (free, no key, 24h vol + TVL) as primary,
    with Moralis /tokens/trending aggregated by chain as secondary signal.
    Returns chain heat scores — use to weight position sizing per chain.
    """
    cache_key = "chain_metrics"
    if _is_cached(cache_key, SLOW_CACHE_TTL):
        return _get_cache(cache_key)
    import math
    result = {}
    try:
        # Primary: DeFiLlama chain TVL + 24h volume (free, no rate limit)
        resp = get_session().get(
            "https://api.llama.fi/v2/chains",
            timeout=10,
        )
        if resp.status_code == 200:
            chains_data = resp.json()
            for c in (chains_data or []):
                name = c.get("name", "")
                our_name = next(
                    (k for k, v in _DEFILLAMA_CHAIN_MAP.items() if v == name), None
                )
                if not our_name:
                    continue
                tvl = _safe_float(c.get("tvl", 0))
                vol_24h = _safe_float(c.get("volume24h", tvl * 0.05))  # fallback: 5% of TVL
                change_pct = _safe_float(c.get("change_1d", 0))
                result[our_name] = {
                    "volume_24h":        vol_24h,
                    "tvl_usd":           tvl,
                    "volume_change_pct": change_pct,
                    "transactions_24h":  _safe_int(c.get("txsStats", {}).get("txsCount", 0)),
                    "active_addresses":  0,  # Not available from DeFiLlama
                    "heat_score":        min(100.0, math.log10(max(vol_24h, 1)) * 8 +
                                             (10 if change_pct >= 10 else 0)),
                }
    except Exception as e:
        logger.debug(f"DeFiLlama chain metrics error: {e}")

    # Secondary: Moralis trending tokens — count trending tokens per chain as activity proxy
    if MORALIS_API_KEY:
        try:
            _rate_check()
            resp2 = get_session().get(
                f"{BASE_URL}/tokens/trending",
                headers=_headers(),
                timeout=8,
            )
            if resp2.status_code == 200:
                trending = resp2.json()
                tokens = trending.get("result", trending) if isinstance(trending, dict) else trending
                chain_token_counts: dict[str, int] = {}
                for t in (tokens or []):
                    cid = t.get("chain_id", "")
                    cname = next((k for k, v in CHAIN_HEX.items() if v == cid), None)
                    if cname:
                        chain_token_counts[cname] = chain_token_counts.get(cname, 0) + 1
                for cname, count in chain_token_counts.items():
                    if cname in result:
                        # Boost heat score by trending token count
                        result[cname]["heat_score"] = min(
                            100.0, result[cname]["heat_score"] + count * 2
                        )
                        result[cname]["trending_tokens"] = count
                    else:
                        result[cname] = {
                            "volume_24h": 0, "tvl_usd": 0, "volume_change_pct": 0,
                            "transactions_24h": 0, "active_addresses": 0,
                            "heat_score": min(100.0, count * 5),
                            "trending_tokens": count,
                        }
        except Exception as e:
            logger.debug(f"Moralis trending chain signal error: {e}")

    if result:
        _set_cache(cache_key, result)
        logger.info(f"Chain metrics: {len(result)} chains loaded via DeFiLlama+Moralis")
    return result


def get_chain_heat(chain: str) -> float:
    """
    Get a 0-100 heat score for a specific chain.
    Used to scale position sizes — hot chains get bigger bets.
    """
    metrics = get_chain_metrics()
    chain_data = metrics.get(chain, {})
    if not chain_data:
        return 50.0  # Neutral default

    vol_24h = chain_data.get("volume_24h", 0)
    vol_change = chain_data.get("volume_change_pct", 0)

    # Base heat from volume (log scale)
    import math
    base_heat = min(80.0, math.log10(max(vol_24h, 1)) * 10)

    # Bonus for rising volume
    if vol_change >= 20:
        base_heat = min(100.0, base_heat + 20)
    elif vol_change >= 10:
        base_heat = min(100.0, base_heat + 10)
    elif vol_change <= -20:
        base_heat = max(0.0, base_heat - 20)

    return round(base_heat, 1)


def get_category_metrics() -> dict:
    """
    Get volume metrics by token category (meme, defi, gaming, etc.).
    MIGRATED June 4 2026: /volume/categories removed from Moralis.
    Now uses GET /tokens/categories (confirmed working) as primary,
    then cross-references with /tokens/trending to compute volume proxies.
    Returns which categories are trending — use to weight discovery sources.
    """
    if not MORALIS_API_KEY:
        return {}
    cache_key = "category_metrics"
    if _is_cached(cache_key, SLOW_CACHE_TTL):
        return _get_cache(cache_key)
    result = {}
    try:
        # Primary: GET /tokens/categories — confirmed working as of June 2026
        _rate_check()
        resp = get_session().get(
            f"{BASE_URL}/tokens/categories",
            headers=_headers(),
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            categories = data.get("result", data) if isinstance(data, dict) else data
            for cat in (categories or []):
                name = cat.get("category", cat.get("name", ""))
                if not name:
                    continue
                result[name] = {
                    "volume_24h":        _safe_float(cat.get("volume_24h", 0)),
                    "volume_change_pct": _safe_float(cat.get("volume_change_24h_percentage",
                                                              cat.get("change_24h", 0))),
                    "market_cap":        _safe_float(cat.get("market_cap", 0)),
                    "token_count":       _safe_int(cat.get("token_count", 0)),
                    "trending":          False,  # Will be set below
                }
    except Exception as e:
        logger.debug(f"Category metrics /tokens/categories error: {e}")

    # Secondary: use /tokens/trending to mark hot categories
    try:
        _rate_check()
        resp2 = get_session().get(
            f"{BASE_URL}/tokens/trending",
            headers=_headers(),
            timeout=8,
        )
        if resp2.status_code == 200:
            trending = resp2.json()
            tokens = trending.get("result", trending) if isinstance(trending, dict) else trending
            cat_counts: dict[str, int] = {}
            for t in (tokens or []):
                for cat_tag in (t.get("categories") or t.get("category", "").split(",")):
                    cat_tag = cat_tag.strip().lower()
                    if cat_tag:
                        cat_counts[cat_tag] = cat_counts.get(cat_tag, 0) + 1
            for cat_name, count in cat_counts.items():
                # Normalize to match our category names
                matched = next(
                    (k for k in result if k.lower() == cat_name), cat_name
                )
                if matched in result:
                    result[matched]["trending"] = count >= 3
                    result[matched]["trending_token_count"] = count
                else:
                    result[matched] = {
                        "volume_24h": 0, "volume_change_pct": 0,
                        "market_cap": 0, "token_count": count,
                        "trending": count >= 3,
                        "trending_token_count": count,
                    }
    except Exception as e:
        logger.debug(f"Category trending signal error: {e}")

    if result:
        _set_cache(cache_key, result)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# 9. TOKEN SEARCH — Discovery by Name/Symbol
#    GET /tokens/search
#    TRADING SIGNAL: Catch trending tokens before they hit the discovery feed
# ─────────────────────────────────────────────────────────────────────────────

def search_tokens(query: str, chain: str = None, limit: int = 10) -> list[dict]:
    """
    Search for tokens by name or symbol across all chains.
    Returns list of matching tokens with price and volume data.
    """
    if not MORALIS_API_KEY:
        return []
    cache_key = f"token_search_{query.lower()}_{chain or 'all'}"
    if _is_cached(cache_key, FAST_CACHE_TTL):
        return _get_cache(cache_key)
    _rate_check()
    try:
        params: dict = {"q": query, "limit": limit}
        if chain:
            params["chain"] = "solana" if chain == "solana" else CHAIN_HEX.get(chain, chain)
        resp = get_session().get(
            f"{BASE_URL}/tokens/search",
            params=params,
            headers=_headers(),
            timeout=8,
        )
        if resp.status_code in (400, 404, 429):
            return []
        resp.raise_for_status()
        data = resp.json()
        tokens = data.get("result", data) if isinstance(data, dict) else data
        result = []
        for t in (tokens or [])[:limit]:
            result.append({
                "address":        t.get("token_address", t.get("address", "")),
                "symbol":         t.get("token_symbol", t.get("symbol", "")),
                "name":           t.get("token_name", t.get("name", "")),
                "chain":          t.get("chain", chain or ""),
                "price_usd":      _safe_float(t.get("price_usd", 0)),
                "volume_24h":     _safe_float(t.get("volume_24h", 0)),
                "market_cap":     _safe_float(t.get("market_cap", 0)),
                "security_score": _safe_int(t.get("security_score", 0)),
            })
        _set_cache(cache_key, result)
        return result
    except Exception as e:
        logger.debug(f"Token search error '{query}': {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# 10. SOLANA EXTENDED — Pump.fun Early Detection + Holder Analytics
#     GET /token/{network}/exchange/pumpfun/new
#     GET /token/{network}/exchange/pumpfun/bonding
#     GET /token/{network}/{address}/score/historical
#     GET /token/{network}/{address}/holders/historical
#     GET /token/{network}/{address}/holders/stats
#     TRADING SIGNAL: Catch Pump.fun tokens BEFORE they graduate
# ─────────────────────────────────────────────────────────────────────────────

def get_pumpfun_new_tokens(limit: int = 20) -> list[dict]:
    """
    Get newly created Pump.fun tokens (pre-bonding curve).
    REST sunsets July 31 2026 → Data Feeds launchpad created events, else [].
    """
    cache_key = f"pumpfun_new_{limit}"
    if _is_cached(cache_key, FAST_CACHE_TTL):
        return _get_cache(cache_key)

    try:
        from data.providers import moralis_datafeeds as df
        if df.available():
            result = df.get_pumpfun_new(limit=limit)
            if result:
                _set_cache(cache_key, result)
                logger.info(f"Pump.fun NEW (DataFeeds): {len(result)}")
                return result
    except Exception as e:
        logger.debug(f"DataFeeds pumpfun new: {e}")

    # Free DexScreener approximation (newest Solana profiles)
    try:
        from data.providers.moralis_solana import _pumpfun_graduated_dexscreener
        free = _pumpfun_graduated_dexscreener(limit=limit)
        if free:
            result = [{
                "address": t.get("token_address", ""),
                "symbol": t.get("symbol", ""),
                "name": t.get("name", ""),
                "created_at": t.get("graduated_at", ""),
                "market_cap": _safe_float(t.get("market_cap", 0)),
                "bonding_pct": 0.0,
                "volume_24h": _safe_float(t.get("volume_24h", 0)),
                "source": "dexscreener_solana_newish",
                "chain": "solana",
            } for t in free]
            _set_cache(cache_key, result)
            logger.info(f"Pump.fun NEW (DexScreener approx): {len(result)}")
            return result
    except Exception as e:
        logger.debug(f"DexScreener pumpfun new approx: {e}")

    # Pre-sunset REST only if free fallbacks disabled
    prefer_free = getattr(settings, "MORALIS_PREFER_FREE_FALLBACKS", True)
    if prefer_free or not MORALIS_API_KEY:
        _set_cache(cache_key, [])
        return []

    try:
        from data.providers.moralis_http import moralis_get, is_past_sunset
        if is_past_sunset():
            _set_cache(cache_key, [])
            return []
        data = moralis_get(
            f"{SOL_BASE_URL}/token/{SOL_NETWORK}/exchange/pumpfun/new",
            params={"limit": limit},
            endpoint_key="pumpfun_new",
            timeout=8,
            allow_sunset=True,
        )
        if not data:
            _set_cache(cache_key, [])
            return []
        tokens = data.get("result", data) if isinstance(data, dict) else data
        result = []
        for t in (tokens or [])[:limit]:
            result.append({
                "address":       t.get("token_address", t.get("mint", t.get("tokenAddress", ""))),
                "symbol":        t.get("token_symbol", t.get("symbol", "")),
                "name":          t.get("token_name", t.get("name", "")),
                "created_at":    t.get("created_at", t.get("createdAt", "")),
                "market_cap":    _safe_float(t.get("market_cap", t.get("marketCap", 0))),
                "bonding_pct":   _safe_float(t.get("bonding_curve_progress", 0)),
                "volume_24h":    _safe_float(t.get("volume_24h", 0)),
                "source":        "pumpfun_new",
                "chain":         "solana",
            })
        _set_cache(cache_key, result)
        logger.info(f"Pump.fun NEW (legacy REST): {len(result)} tokens found")
        return result
    except Exception as e:
        logger.debug(f"Pump.fun new tokens error: {e}")
        return []


def get_pumpfun_bonding_tokens(limit: int = 20) -> list[dict]:
    """
    Get Pump.fun tokens currently in bonding phase (close to graduation).
    REST sunsets July 31 2026 → Data Feeds bonding status projection.
    """
    cache_key = f"pumpfun_bonding_{limit}"
    if _is_cached(cache_key, FAST_CACHE_TTL):
        return _get_cache(cache_key)

    try:
        from data.providers import moralis_datafeeds as df
        if df.available():
            result = df.get_pumpfun_bonding(limit=limit)
            if result:
                _set_cache(cache_key, result)
                logger.info(
                    f"Pump.fun BONDING (DataFeeds): {len(result)}, "
                    f"{sum(1 for t in result if t.get('near_graduation'))} near graduation"
                )
                return result
    except Exception as e:
        logger.debug(f"DataFeeds pumpfun bonding: {e}")

    # Without Data Feeds we cannot know true bonding %. Do not invent signals.
    # Pre-sunset REST only if free fallbacks disabled.
    prefer_free = getattr(settings, "MORALIS_PREFER_FREE_FALLBACKS", True)
    if prefer_free or not MORALIS_API_KEY:
        _set_cache(cache_key, [])
        return []

    try:
        from data.providers.moralis_http import moralis_get, is_past_sunset
        if is_past_sunset():
            _set_cache(cache_key, [])
            return []
        data = moralis_get(
            f"{SOL_BASE_URL}/token/{SOL_NETWORK}/exchange/pumpfun/bonding",
            params={"limit": limit},
            endpoint_key="pumpfun_bonding",
            timeout=8,
            allow_sunset=True,
        )
        if not data:
            _set_cache(cache_key, [])
            return []
        tokens = data.get("result", data) if isinstance(data, dict) else data
        result = []
        for t in (tokens or [])[:limit]:
            bonding_pct = _safe_float(t.get("bonding_curve_progress", t.get("bondingProgress", 0)))
            result.append({
                "address":       t.get("token_address", t.get("mint", t.get("tokenAddress", ""))),
                "symbol":        t.get("token_symbol", t.get("symbol", "")),
                "name":          t.get("token_name", t.get("name", "")),
                "bonding_pct":   bonding_pct,
                "market_cap":    _safe_float(t.get("market_cap", t.get("marketCap", 0))),
                "volume_24h":    _safe_float(t.get("volume_24h", 0)),
                "near_graduation": bonding_pct >= 80,
                "source":        "pumpfun_bonding",
                "chain":         "solana",
            })
        _set_cache(cache_key, result)
        logger.info(f"Pump.fun BONDING (legacy REST): {len(result)}")
        return result
    except Exception as e:
        logger.debug(f"Pump.fun bonding tokens error: {e}")
        return []


def get_solana_holder_stats(token_address: str) -> dict:
    """
    Holder distribution for a Solana token.
    REST metrics sunsets July 31 2026 → Data Feeds / Helius concentration.
    """
    empty = {"total_holders": 0, "top10_pct": 0.0, "concentration_risk": "unknown"}
    if not token_address:
        return empty
    cache_key = f"sol_holder_stats_{token_address}"
    if _is_cached(cache_key, SLOW_CACHE_TTL):
        return _get_cache(cache_key)

    # Data Feeds top holders → concentration
    try:
        from data.providers import moralis_datafeeds as df
        if df.available():
            top = df.get_top_holders(token_address, limit=10, chain="solana")
            if top.get("holders"):
                top10 = float(top.get("top10_concentration", 0)) * 100
                result = {
                    "total_holders": len(top["holders"]),
                    "top10_pct": round(top10, 1),
                    "top1_pct": round(top["holders"][0].get("percentage", 0), 1) if top["holders"] else 0.0,
                    "concentration_risk": top.get("concentration_risk", "unknown"),
                    "holder_score": max(0.0, 100.0 - top10),
                    "source": "datafeeds",
                }
                _set_cache(cache_key, result)
                return result
    except Exception:
        pass

    # Helius enrichment path (0 Moralis CU)
    try:
        from data.providers.moralis_solana import get_token_top_holders
        top = get_token_top_holders(token_address, limit=10)
        if top.get("holders"):
            top10 = float(top.get("top10_concentration", 0)) * 100
            result = {
                "total_holders": len(top["holders"]),
                "top10_pct": round(top10, 1),
                "top1_pct": round(top["holders"][0].get("percentage", 0), 1) if top["holders"] else 0.0,
                "concentration_risk": top.get("concentration_risk", "unknown"),
                "holder_score": max(0.0, 100.0 - top10),
                "source": top.get("source", "helius"),
            }
            _set_cache(cache_key, result)
            return result
    except Exception as e:
        logger.debug(f"Solana holder stats fallback error {token_address[:8]}: {e}")

    _set_cache(cache_key, empty)
    return empty


def get_solana_holder_growth(token_address: str, days: int = 7) -> dict:
    """
    Historical holder growth — REST sunsets July 31 2026.
    Without Data Feeds historical_balances recipe, return neutral (no CU burn).
    """
    # Historical series is not available free; skip REST to save CU.
    return {"holder_trend": "stable", "growth_rate_pct": 0.0, "source": "sunset_neutral"}


def get_solana_score_timeseries(token_address: str, days: int = 7) -> dict:
    """
    Solana Token Score is EVM-only after July 31 2026 — return neutral, 0 CU.
    """
    return {"score_trend": "stable", "score_delta": 0.0, "source": "solana_score_sunset"}


# ─────────────────────────────────────────────────────────────────────────────
# 11. MASTER INTELLIGENCE ENRICHMENT
#     Runs all new signals in parallel and returns a unified enrichment dict
#     that feeds directly into the gem_score calculation.
# ─────────────────────────────────────────────────────────────────────────────

def enrich_token_intelligence(
    token_address: str,
    chain: str,
    pair_address: str = "",
    is_solana: bool = False,
) -> dict:
    """
    Run all new intelligence signals for a token and return a unified dict.
    Designed to be called alongside moralis_money.enrich_candidate().

    Returns a dict with all new signal fields prefixed with 'intel_'.
    """
    result: dict = {
        # Top Traders
        "intel_smart_money_buying":    False,
        "intel_smart_money_score":     50.0,
        "intel_top_trader_count":      0,
        "intel_profitable_traders":    0,
        "intel_total_smart_money_usd": 0.0,
        "intel_top_trader_addresses":  [],
        # Snipers
        "intel_sniper_count":          0,
        "intel_sniper_risk":           "unknown",
        "intel_sniped_usd":            0.0,
        # Score Trend
        "intel_score_trend":           "stable",
        "intel_score_delta":           0.0,
        # Momentum Trend
        "intel_momentum_trend":        "neutral",
        "intel_buyer_acceleration":    1.0,
        # Holder Intelligence
        "intel_holder_trend":          "stable",
        "intel_holder_growth_pct":     0.0,
        "intel_holder_growth_7d_pct":  0.0,
        "intel_holder_growth_30d_pct": 0.0,
        "intel_holder_concentration":  50.0,
        "intel_concentration_risk":    "unknown",
        "intel_total_holders":         0,
        # Swap Flow
        "intel_whale_buying":          False,
        "intel_swap_flow_score":       50.0,
        "intel_large_buy_count":       0,
        "intel_net_flow_usd":          0.0,
        # Chain Heat
        "intel_chain_heat":            50.0,
        # Pro: Bonding Status (rug prevention)
        "intel_bonding_status":        "unknown",
        "intel_is_graduated":          True,  # Default True = assume graduated if no data
        "intel_graduation_pct":        100.0,
        # Pro: Top Profitable Wallets (smart money conviction)
        "intel_smart_money_conviction": 0.0,
        "intel_profitable_wallet_count": 0,
        "intel_total_realized_profit":  0.0,
        # Pro: Instant Token Score (early safety gate)
        "intel_moralis_score":          50,
        # Pro: DEX Pair Stats (buy/sell analysis)
        "intel_pair_buy_sell_ratio":    1.0,
        "intel_pair_unique_traders":    0,
        "intel_pair_is_accumulating":   False,
        # Pro: Single Token Analytics (stealth accumulation)
        "intel_stealth_accumulation":   False,
        "intel_buy_sell_vol_ratio":     1.0,
    }

    # ── Run all API calls in parallel with a hard 5-second total timeout ────────
    # This prevents intelligence enrichment from blocking the scan cycle.
    # Each individual call already has an 8s timeout — but running 8 sequentially
    # could take 64s. With parallel execution + 5s wall-clock cap, worst case is 5s.
    from concurrent.futures import ThreadPoolExecutor, as_completed as _as_completed
    INTEL_TIMEOUT = 8.0  # Pro-tier: 8s wall-clock cap (was 5s on Starter)

    try:
        if is_solana:
            tasks = {
                "holder_stats":  lambda: get_solana_holder_stats(token_address),
                "holder_growth": lambda: get_solana_holder_growth(token_address),
                "score_ts":      lambda: get_solana_score_timeseries(token_address),
                "chain_heat":    lambda: get_chain_heat("solana") if MORALIS_API_KEY else 50.0,
                "bonding":       lambda: get_token_bonding_status(token_address, "solana", is_solana=True),
                "holders_v2":    lambda: get_historical_token_holders_v2(token_address, "solana", is_solana=True),
                "top_holders":   lambda: get_solana_top_holders_detailed(token_address),
            }
            with ThreadPoolExecutor(max_workers=7, thread_name_prefix="intel_sol") as pool:
                fmap = {pool.submit(fn): name for name, fn in tasks.items()}
                done = {}
                for fut in _as_completed(fmap, timeout=INTEL_TIMEOUT):
                    done[fmap[fut]] = fut.result()
            holder_stats  = done.get("holder_stats", {})
            holder_growth = done.get("holder_growth", {})
            score_ts      = done.get("score_ts", {})
            chain_heat    = done.get("chain_heat", 50.0)
            bonding       = done.get("bonding") or {}
            holders_v2    = done.get("holders_v2") or {}
            top_holders   = done.get("top_holders") or {}
            result["intel_total_holders"]       = holder_stats.get("total_holders", 0)
            result["intel_holder_concentration"] = holder_stats.get("holder_score", 50.0)
            result["intel_concentration_risk"]  = top_holders.get("concentration_risk",
                                                     holder_stats.get("concentration_risk", "unknown"))
            result["intel_holder_trend"]        = holders_v2.get("holder_trend",
                                                     holder_growth.get("holder_trend", "stable"))
            result["intel_holder_growth_pct"]   = holders_v2.get("holder_growth_7d_pct",
                                                     holder_growth.get("growth_rate_pct", 0.0))
            result["intel_holder_growth_7d_pct"]  = holders_v2.get("holder_growth_7d_pct", 0.0)
            result["intel_holder_growth_30d_pct"] = holders_v2.get("holder_growth_30d_pct", 0.0)
            result["intel_score_trend"]         = score_ts.get("score_trend", "stable")
            result["intel_score_delta"]         = score_ts.get("score_delta", 0.0)
            result["intel_chain_heat"]          = chain_heat if isinstance(chain_heat, float) else 50.0
            # Pro: Bonding status
            result["intel_bonding_status"]      = bonding.get("bonding_status", "unknown")
            result["intel_is_graduated"]        = bonding.get("is_graduated", True)
            result["intel_graduation_pct"]      = bonding.get("graduation_pct", 100.0)

        else:
            if chain in CHAIN_HEX:
                tasks = {
                    "traders":      lambda: get_top_trader_signal(token_address, chain),
                    "snipers":      lambda: get_evm_snipers(token_address, chain),
                    "score_ts":     lambda: get_token_score_timeseries(token_address, chain),
                    "analytics_ts": lambda: get_analytics_timeseries(token_address, chain),
                    "holder_stats": lambda: get_holder_stats(token_address, chain),
                    "holder_growth":lambda: get_holder_growth(token_address, chain),
                    "swap_flow":    lambda: analyze_swap_flow(token_address, chain),
                    "chain_heat":   lambda: get_chain_heat(chain),
                    # Pro endpoints
                    "bonding":       lambda: get_token_bonding_status(token_address, chain),
                    "profit_wallets":lambda: get_top_profitable_wallets(token_address, chain),
                    "holders_v2":    lambda: get_historical_token_holders_v2(token_address, chain),
                    # New Pro endpoints (Sprint 2)
                    "instant_score": lambda: get_token_score_instant(token_address, chain),
                    "pair_stats":    lambda: get_pair_stats(pair_address, chain) if pair_address else None,
                    "tok_analytics": lambda: get_single_token_analytics(token_address, chain),
                }
                with ThreadPoolExecutor(max_workers=14, thread_name_prefix="intel_evm") as pool:
                    fmap = {pool.submit(fn): name for name, fn in tasks.items()}
                    done = {}
                    for fut in _as_completed(fmap, timeout=INTEL_TIMEOUT):
                        done[fmap[fut]] = fut.result()
                trader_signal = done.get("traders", {})
                sniper_data   = done.get("snipers", {})
                score_ts      = done.get("score_ts", {})
                analytics_ts  = done.get("analytics_ts", {})
                holder_stats  = done.get("holder_stats", {})
                holder_growth = done.get("holder_growth", {})
                swap_flow     = done.get("swap_flow", {})
                chain_heat    = done.get("chain_heat", 50.0)
                bonding       = done.get("bonding") or {}
                profit_wallets = done.get("profit_wallets") or {}
                holders_v2    = done.get("holders_v2") or {}
                result["intel_smart_money_buying"]    = trader_signal.get("smart_money_buying", False)
                result["intel_smart_money_score"]     = trader_signal.get("smart_money_score", 50.0)
                result["intel_top_trader_count"]      = trader_signal.get("top_trader_count", 0)
                result["intel_profitable_traders"]    = trader_signal.get("profitable_trader_count", 0)
                result["intel_total_smart_money_usd"] = trader_signal.get("total_smart_money_usd", 0.0)
                result["intel_top_trader_addresses"]  = trader_signal.get("top_trader_addresses", [])
                result["intel_sniper_count"]          = sniper_data.get("sniper_count", 0)
                result["intel_sniper_risk"]           = sniper_data.get("risk_level", "unknown")
                result["intel_sniped_usd"]            = sniper_data.get("total_sniped_usd", 0.0)
                result["intel_score_trend"]           = score_ts.get("score_trend", "stable")
                result["intel_score_delta"]           = score_ts.get("score_delta", 0.0)
                result["intel_momentum_trend"]        = analytics_ts.get("momentum_trend", "neutral")
                result["intel_buyer_acceleration"]    = analytics_ts.get("buyer_acceleration", 1.0)
                result["intel_total_holders"]         = holder_stats.get("total_holders", 0)
                result["intel_holder_concentration"]  = holder_stats.get("holder_score", 50.0)
                result["intel_concentration_risk"]   = holder_stats.get("concentration_risk", "unknown")
                result["intel_holder_trend"]          = holders_v2.get("holder_trend",
                                                           holder_growth.get("holder_trend", "stable"))
                result["intel_holder_growth_pct"]     = holders_v2.get("holder_growth_7d_pct",
                                                           holder_growth.get("growth_rate_pct", 0.0))
                result["intel_holder_growth_7d_pct"]  = holders_v2.get("holder_growth_7d_pct", 0.0)
                result["intel_holder_growth_30d_pct"] = holders_v2.get("holder_growth_30d_pct", 0.0)
                result["intel_whale_buying"]          = swap_flow.get("whale_buying", False)
                result["intel_swap_flow_score"]       = swap_flow.get("swap_flow_score", 50.0)
                result["intel_large_buy_count"]       = swap_flow.get("large_buy_count", 0)
                result["intel_net_flow_usd"]          = swap_flow.get("net_flow_usd", 0.0)
                result["intel_chain_heat"]            = chain_heat if isinstance(chain_heat, float) else 50.0
                # Pro: Bonding status
                result["intel_bonding_status"]        = bonding.get("bonding_status", "unknown")
                result["intel_is_graduated"]          = bonding.get("is_graduated", True)
                result["intel_graduation_pct"]        = bonding.get("graduation_pct", 100.0)
                # Pro: Smart money conviction from profitable wallets
                result["intel_smart_money_conviction"] = profit_wallets.get("smart_money_conviction", 0.0)
                result["intel_profitable_wallet_count"] = profit_wallets.get("total_profitable_wallets", 0)
                result["intel_total_realized_profit"]  = profit_wallets.get("total_realized_profit_usd", 0.0)
                # Pro: Instant score
                instant_score = done.get("instant_score") or {}
                result["intel_moralis_score"] = instant_score.get("moralis_score", 50)
                # Pro: Pair stats
                pair_data = done.get("pair_stats") or {}
                result["intel_pair_buy_sell_ratio"]  = pair_data.get("buy_sell_ratio", 1.0)
                result["intel_pair_unique_traders"]  = pair_data.get("unique_traders", 0)
                result["intel_pair_is_accumulating"] = pair_data.get("is_accumulating", False)
                # Pro: Single token analytics
                tok_analytics = done.get("tok_analytics") or {}
                result["intel_stealth_accumulation"] = tok_analytics.get("stealth_accumulation", False)
                result["intel_buy_sell_vol_ratio"]   = tok_analytics.get("buy_sell_vol_ratio", 1.0)

    except Exception as e:
        logger.warning(f"Intelligence enrichment timeout/error for {token_address[:8]}/{chain}: {e}")

    return result


# ─────────────────────────────────────────────────────────────────────────────
# 12. INTELLIGENCE SCORE BOOST
#     Converts all new signals into a gem_score delta.
#     Called from gem_scanner.py after the base score is computed.
# ─────────────────────────────────────────────────────────────────────────────

def calculate_intelligence_score_boost(intel: dict) -> tuple[float, list[str]]:
    """
    Calculate gem_score boost/penalty from intelligence signals.
    Returns: (score_delta, list_of_reasons)

    Max boost:  +30 points (all signals firing)
    Max penalty: -25 points (sniper attack + declining score + distributing holders)
    """
    delta = 0.0
    reasons = []

    # ── Smart Money Buying (+8 max) ──────────────────────────────────────────
    smart_money_score = intel.get("intel_smart_money_score", 50.0)
    if intel.get("intel_smart_money_buying") and smart_money_score >= 70:
        boost = min(8.0, (smart_money_score - 50) / 6.25)
        delta += boost
        reasons.append(f"smart_money_buying +{boost:.1f} ({intel['intel_profitable_traders']} profitable traders)")

    # ── Sniper Penalty (-15 max) ─────────────────────────────────────────────
    sniper_risk = intel.get("intel_sniper_risk", "unknown")
    sniper_count = intel.get("intel_sniper_count", 0)
    if sniper_risk == "critical" or sniper_count >= 10:
        delta -= 15.0
        reasons.append(f"sniper_critical -{15} ({sniper_count} snipers)")
    elif sniper_risk == "high" or sniper_count >= 5:
        delta -= 8.0
        reasons.append(f"sniper_high -{8} ({sniper_count} snipers)")
    elif sniper_risk == "medium":
        delta -= 3.0
        reasons.append(f"sniper_medium -{3}")

    # ── Score Trend (+5 / -5) ────────────────────────────────────────────────
    score_trend = intel.get("intel_score_trend", "stable")
    score_delta = intel.get("intel_score_delta", 0.0)
    if score_trend == "improving":
        boost = min(5.0, abs(score_delta) / 4)
        delta += boost
        reasons.append(f"score_improving +{boost:.1f}")
    elif score_trend == "declining":
        penalty = min(5.0, abs(score_delta) / 4)
        delta -= penalty
        reasons.append(f"score_declining -{penalty:.1f}")

    # ── Momentum Trend (+6 / -8) ─────────────────────────────────────────────
    momentum = intel.get("intel_momentum_trend", "neutral")
    buyer_accel = intel.get("intel_buyer_acceleration", 1.0)
    if momentum == "accelerating":
        boost = min(6.0, (buyer_accel - 1.0) * 6)
        delta += boost
        reasons.append(f"momentum_accelerating +{boost:.1f} ({buyer_accel:.1f}x buyers)")
    elif momentum == "building":
        delta += 3.0
        reasons.append("momentum_building +3")
    elif momentum == "dying":
        delta -= 8.0
        reasons.append(f"momentum_dying -8 ({buyer_accel:.1f}x buyers)")
    elif momentum == "fading":
        delta -= 4.0
        reasons.append("momentum_fading -4")

    # ── Holder Trend (+4 / -5) ───────────────────────────────────────────────
    holder_trend = intel.get("intel_holder_trend", "stable")
    holder_growth = intel.get("intel_holder_growth_pct", 0.0)
    if holder_trend == "accumulating":
        boost = min(4.0, holder_growth / 10)
        delta += boost
        reasons.append(f"holders_accumulating +{boost:.1f} (+{holder_growth:.0f}%)")
    elif holder_trend == "distributing":
        delta -= 5.0
        reasons.append(f"holders_distributing -5 ({holder_growth:.0f}%)")

    # ── Holder Concentration (+3 / -5) ───────────────────────────────────────
    conc_risk = intel.get("intel_concentration_risk", "unknown")
    if conc_risk == "critical":
        delta -= 5.0
        reasons.append("concentration_critical -5")
    elif conc_risk == "high":
        delta -= 2.0
        reasons.append("concentration_high -2")
    elif conc_risk == "low":
        delta += 3.0
        reasons.append("concentration_low +3 (healthy distribution)")

    # ── Whale Swap Flow (+5 / -3) ────────────────────────────────────────────
    swap_score = intel.get("intel_swap_flow_score", 50.0)
    if intel.get("intel_whale_buying") and swap_score >= 70:
        boost = min(5.0, (swap_score - 50) / 10)
        delta += boost
        reasons.append(f"whale_swap_buying +{boost:.1f} (${intel.get('intel_net_flow_usd', 0):,.0f} net)")
    elif swap_score <= 30:
        delta -= 3.0
        reasons.append("whale_swap_selling -3")

    # ── Smart Money Conviction from Profitable Wallets (+6 max) ───────────────
    conviction = intel.get("intel_smart_money_conviction", 0.0)
    if conviction >= 70:
        boost = min(6.0, (conviction - 50) / 5)
        delta += boost
        pcount = intel.get("intel_profitable_wallet_count", 0)
        reasons.append(f"smart_money_conviction +{boost:.1f} ({pcount} profitable wallets)")

    # ── Pair-Level Accumulation (+4 max) ─────────────────────────────────────
    if intel.get("intel_pair_is_accumulating"):
        ratio = intel.get("intel_pair_buy_sell_ratio", 1.0)
        boost = min(4.0, (ratio - 1.0) * 4)
        delta += boost
        reasons.append(f"pair_accumulating +{boost:.1f} (ratio={ratio:.1f})")

    # ── Stealth Accumulation (+5) ────────────────────────────────────────────
    if intel.get("intel_stealth_accumulation"):
        vol_ratio = intel.get("intel_buy_sell_vol_ratio", 1.0)
        boost = min(5.0, vol_ratio)
        delta += boost
        reasons.append(f"stealth_accumulation +{boost:.1f} (vol_ratio={vol_ratio:.1f}x)")

    # ── Chain Heat Multiplier (scales all bonuses) ───────────────────────────
    chain_heat = intel.get("intel_chain_heat", 50.0)
    if chain_heat >= 80 and delta > 0:
        delta *= 1.15  # Hot chain: 15% bonus on positive signals
        reasons.append(f"chain_hot x1.15 (heat={chain_heat:.0f})")
    elif chain_heat <= 20 and delta > 0:
        delta *= 0.85  # Cold chain: 15% reduction on positive signals
        reasons.append(f"chain_cold x0.85 (heat={chain_heat:.0f})")

    return round(delta, 2), reasons


# ─────────────────────────────────────────────────────────────────────────────
# 13. PORTFOLIO INTELLIGENCE — Full Wallet Analysis for Dashboard
# ─────────────────────────────────────────────────────────────────────────────

def get_full_portfolio_intelligence(wallet_addresses: list[str]) -> dict:
    """
    Run comprehensive intelligence on all our wallets.
    Returns a unified dict for the dashboard.
    """
    result = {
        "total_defi_usd":    0.0,
        "total_approvals":   0,
        "high_risk_approvals": 0,
        "active_chains":     [],
        "defi_protocols":    {},
        "wallet_histories":  {},
    }

    for addr in wallet_addresses:
        try:
            # Chain activity
            chain_activity = get_wallet_chain_activity(addr)
            for chain_name in chain_activity:
                if chain_name not in result["active_chains"]:
                    result["active_chains"].append(chain_name)

            # DeFi exposure
            defi = get_all_wallet_defi_exposure(addr)
            result["total_defi_usd"] += defi.get("total_defi_usd", 0.0)
            for proto, usd in defi.get("protocols", {}).items():
                result["defi_protocols"][proto] = result["defi_protocols"].get(proto, 0.0) + usd

            # Approvals (check main chains)
            for chain in ["ethereum", "base", "bsc"]:
                approvals = get_wallet_approvals(addr, chain)
                result["total_approvals"] += len(approvals)
                result["high_risk_approvals"] += sum(
                    1 for a in approvals if a.get("risk") == "high" or a.get("is_unlimited")
                )

        except Exception as e:
            logger.debug(f"Portfolio intelligence error for {addr[:8]}: {e}")

    return result


# ─────────────────────────────────────────────────────────────────────────────
# 14. USAGE STATS
# ─────────────────────────────────────────────────────────────────────────────

def get_usage_stats() -> dict:
    return {
        "api_key_configured": bool(MORALIS_API_KEY),
        "cached_keys":        len(_cache),
        "rate_limiter": "shared_pro_tier",
        "endpoints_covered": [
            "top_traders", "evm_snipers", "score_timeseries", "analytics_timeseries",
            "holder_stats", "holder_growth", "token_swaps", "swap_flow",
            "wallet_history", "wallet_approvals", "wallet_chain_activity",
            "wallet_defi_positions", "chain_metrics", "category_metrics",
            "token_search", "pumpfun_new", "pumpfun_bonding",
            "solana_holder_stats", "solana_holder_growth", "solana_score_timeseries",
            # Pro endpoints (Sprint 1)
            "bonding_status", "top_profitable_wallets", "wallet_insight",
            "wallet_profitability", "wallet_net_worth", "token_security",
            "wallet_labels", "entity_search", "historical_holders_v2",
            "solana_top_holders", "token_categories",
            # Pro endpoints (Sprint 2)
            "instant_token_score", "pair_stats", "single_token_analytics",
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# 15. TOKEN SECURITY API (EVM) — Cross-validates GoPlus
# GET /erc20/{address}/security?chain={chain}
# Returns: is_honeypot, buy_tax, sell_tax, has_mint_function, is_proxy
# ─────────────────────────────────────────────────────────────────────────────
def get_token_security(token_address: str, chain: str) -> Optional[dict]:
    """
    Fetch Moralis-native token security data for EVM tokens.
    Used in safety.py as a cross-validation layer alongside GoPlus.
    Returns None if key not set or token not found.
    """
    chain_hex = CHAIN_HEX.get(chain)
    if not chain_hex:
        return None
    cache_key = f"token_security_{chain}_{token_address.lower()}"
    if _is_cached(cache_key, SLOW_CACHE_TTL):
        return _get_cache(cache_key)
    _rate_check()
    try:
        resp = get_session().get(
            f"{BASE_URL}/erc20/{token_address}/security",
            params={"chain": chain_hex},
            headers=_headers(),
            timeout=10,
        )
        if resp.status_code in (400, 404, 429):
            return None
        resp.raise_for_status()
        data = resp.json()
        result = {
            "is_honeypot": bool(data.get("is_honeypot", False)),
            "buy_tax": _safe_float(data.get("buy_tax", 0)),
            "sell_tax": _safe_float(data.get("sell_tax", 0)),
            "has_mint_function": bool(data.get("has_mint_function", False)),
            "is_proxy": bool(data.get("is_proxy", False)),
            "is_open_source": bool(data.get("is_open_source", True)),
            "owner_address": data.get("owner_address", ""),
        }
        _set_cache(cache_key, result)
        return result
    except Exception as e:
        logger.debug(f"Token security error {chain}/{token_address[:8]}: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 16. WALLET ENTITY LABELS — Know WHO is buying
# GET /wallets/{address}/labels
# Returns entity type: Whale, Bot, Exchange, Fund, Smart Money, etc.
# ─────────────────────────────────────────────────────────────────────────────
def get_wallet_labels(address: str) -> Optional[dict]:
    """
    Fetch Moralis entity labels for a wallet address.
    Used in sniper_discovery.py to filter bots and boost known whales.
    Returns None if no labels found or key not set.
    """
    if not MORALIS_API_KEY:
        return None
    cache_key = f"wallet_labels_{address.lower()}"
    if _is_cached(cache_key, SLOW_CACHE_TTL):
        return _get_cache(cache_key)
    _rate_check()
    try:
        resp = get_session().get(
            f"{BASE_URL}/wallets/{address}/labels",
            headers=_headers(),
            timeout=10,
        )
        if resp.status_code in (400, 404, 429):
            return None
        resp.raise_for_status()
        data = resp.json()
        labels = data.get("labels", []) if isinstance(data, dict) else []
        if not labels:
            return None
        primary = labels[0] if labels else {}
        result = {
            "primary_label": primary.get("label", ""),
            "entity_type": primary.get("entity_type", ""),
            "confidence": _safe_float(primary.get("confidence", 0)),
            "all_labels": [lb.get("label", "") for lb in labels],
        }
        _set_cache(cache_key, result)
        return result
    except Exception as e:
        logger.debug(f"Wallet labels error {address[:8]}: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 17. ENTITY SEARCH API — Deployer address identity check
# GET /entities/search?query={address}
# Returns: entity name, type, category for known protocols/funds/exchanges
# ─────────────────────────────────────────────────────────────────────────────
def get_entity_label(address: str) -> Optional[dict]:
    """
    Search Moralis Entity API for a known entity by address.
    Used in safety.py to identify deployer wallets.
    Returns None if address is not a known entity.
    """
    if not MORALIS_API_KEY:
        return None
    cache_key = f"entity_label_{address.lower()}"
    if _is_cached(cache_key, SLOW_CACHE_TTL):
        return _get_cache(cache_key)
    _rate_check()
    try:
        resp = get_session().get(
            f"{BASE_URL}/entities/search",
            params={"query": address, "limit": 1},
            headers=_headers(),
            timeout=10,
        )
        if resp.status_code in (400, 404, 422, 429):
            return None
        resp.raise_for_status()
        data = resp.json()
        results = data.get("result", []) if isinstance(data, dict) else []
        if not results:
            return None
        entity = results[0]
        result = {
            "name": entity.get("name", ""),
            "type": entity.get("entity_type", ""),
            "category": entity.get("category", ""),
            "website": entity.get("website", ""),
        }
        _set_cache(cache_key, result)
        return result
    except Exception as e:
        logger.debug(f"Entity search error {address[:8]}: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 18. MARKET METRICS — Global crypto market data
#     MIGRATED June 4 2026: /market-data/global/market-cap and
#     /market-data/top-cryptocurrencies-by-market-cap REMOVED from Moralis.
#     Moralis Universal Market Metrics API is documented but returns 404 (not live).
#     Fallback: CoinGecko /global and /coins/markets (free, no API key required).
# ─────────────────────────────────────────────────────────────────────────────
_COINGECKO_BASE = "https://api.coingecko.com/api/v3"


def get_global_market_metrics() -> Optional[dict]:
    """
    Fetch global crypto market metrics.
    MIGRATED June 2026: Moralis /market-data/global/market-cap REMOVED.
    Now uses CoinGecko /global endpoint (free, no key required).
    Returns total market cap, BTC/ETH dominance, 24h volume, market cap change.
    """
    cache_key = "global_market_metrics"
    if _is_cached(cache_key, FAST_CACHE_TTL):
        return _get_cache(cache_key)
    try:
        resp = get_session().get(
            f"{_COINGECKO_BASE}/global",
            timeout=10,
        )
        if resp.status_code in (429, 503):
            logger.debug("CoinGecko /global rate-limited — skipping")
            return None
        resp.raise_for_status()
        data = resp.json().get("data", {})
        mcap = data.get("total_market_cap", {})
        vol = data.get("total_volume", {})
        result = {
            "total_market_cap_usd": _safe_float(mcap.get("usd", 0)),
            "total_volume_24h_usd": _safe_float(vol.get("usd", 0)),
            "btc_dominance_pct": _safe_float(data.get("market_cap_percentage", {}).get("btc", 0)),
            "eth_dominance_pct": _safe_float(data.get("market_cap_percentage", {}).get("eth", 0)),
            "market_cap_change_24h_pct": _safe_float(data.get("market_cap_change_percentage_24h_usd", 0)),
            "active_coins": _safe_int(data.get("active_cryptocurrencies", 0)),
        }
        _set_cache(cache_key, result)
        return result
    except Exception as e:
        logger.debug(f"Global market metrics (CoinGecko fallback) error: {e}")
        return None


def get_top_crypto_by_market_cap(limit: int = 10) -> list[dict]:
    """
    Fetch top cryptocurrencies by market cap.
    MIGRATED June 2026: Moralis /market-data/top-cryptocurrencies-by-market-cap REMOVED.
    Now uses CoinGecko /coins/markets (free, no key required).
    """
    cache_key = f"top_crypto_mcap_{limit}"
    if _is_cached(cache_key, FAST_CACHE_TTL):
        return _get_cache(cache_key)
    try:
        resp = get_session().get(
            f"{_COINGECKO_BASE}/coins/markets",
            params={
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": limit,
                "page": 1,
                "sparkline": False,
                "price_change_percentage": "24h,7d",
            },
            timeout=10,
        )
        if resp.status_code in (429, 503):
            logger.debug("CoinGecko /coins/markets rate-limited — skipping")
            return []
        resp.raise_for_status()
        coins = resp.json()
        result = [
            {
                "symbol": c.get("symbol", "").upper(),
                "name": c.get("name", ""),
                "price_usd": _safe_float(c.get("current_price", 0)),
                "market_cap_usd": _safe_float(c.get("market_cap", 0)),
                "price_change_24h_pct": _safe_float(c.get("price_change_percentage_24h", 0)),
                "price_change_7d_pct": _safe_float(c.get("price_change_percentage_7d_in_currency", 0)),
                "volume_24h_usd": _safe_float(c.get("total_volume", 0)),
            }
            for c in coins
        ]
        _set_cache(cache_key, result)
        return result
    except Exception as e:
        logger.debug(f"Top coins by market cap (CoinGecko fallback) error: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# 19. CORTEX AI — DEPRECATED (sunset June 4, 2026)
# Replaced by getTokenScore + getTokenAnalytics (see moralis_money.py,
# moralis_data.py) which are already integrated into the gem scanner.
# ─────────────────────────────────────────────────────────────────────────────
def cortex_analyze_token(
    token_address: str,
    chain: str,
    symbol: str = "",
    question: str = "",
) -> Optional[dict]:
    """
    PERMANENTLY DEACTIVATED.

    Moralis sunset the hosted Cortex API (`/cortex/chat`) on June 4, 2026.
    Replaced by `getTokenScore` + `getTokenAnalytics` endpoints, which are
    already integrated via moralis_money.py and moralis_data.py.
    """
    return None


# ─────────────────────────────────────────────────────────────────────────────
# 20. TOKEN BONDING STATUS — Pre-trade rug prevention
# GET /tokens/{address}/bonding-status?chain={chain}      (EVM)  — migrated June 2026
# GET /token/{network}/{address}/bonding-status            (Solana)
# Returns: graduation %, bonding curve exchange, bonding status, market cap
# Use case: Block trades on tokens still in bonding curve (pre-graduation)
# ─────────────────────────────────────────────────────────────────────────────
def get_token_bonding_status(
    token_address: str,
    chain: str,
    is_solana: bool = False,
) -> Optional[dict]:
    """
    Check if a token is still in a bonding curve (pre-graduation).
    Returns bonding progress and graduation status.

    Solana REST sunsets July 31 2026 → Data Feeds / moralis_money cascade.
    """
    # Delegate to money module cascade (Data Feeds → EVM REST, Solana free/DF)
    try:
        from data.providers.moralis_money import get_bonding_status as _money_bonding
        raw = _money_bonding(token_address, chain if not is_solana else "solana")
        if not raw:
            return None
        return {
            "bonding_status": "bonding" if raw.get("is_bonding") else (
                "graduated" if raw.get("is_graduated") else raw.get("bonding_status", "unknown")
            ),
            "graduation_pct": _safe_float(raw.get("graduation_pct", 0)),
            "exchange": raw.get("exchange", ""),
            "market_cap_usd": _safe_float(raw.get("market_cap_usd", 0)),
            "is_graduated": bool(raw.get("is_graduated") or not raw.get("is_bonding")),
        }
    except Exception as e:
        logger.debug(f"Token bonding status error {token_address[:8]}/{chain}: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 21. TOP PROFITABLE WALLETS PER TOKEN — Smart money signal
# GET /erc20/{address}/top-profitable-wallets?chain={chain}
# Returns: ranked list of most profitable traders for a specific token
# Use case: If top traders are accumulating → strong buy signal
# ─────────────────────────────────────────────────────────────────────────────
def get_top_profitable_wallets(
    token_address: str,
    chain: str,
    limit: int = 10,
) -> Optional[dict]:
    """
    Get the most profitable wallets trading a specific token.
    This is the BEST smart money signal available on Moralis Pro.

    Returns:
      - total_profitable_wallets: int
      - avg_realized_profit_usd: float
      - top_wallets: list of {address, realized_profit_usd, avg_buy_price, count_of_trades}
      - smart_money_conviction: float (0-100, our score)
    """
    if not MORALIS_API_KEY:
        return None
    hex_chain = CHAIN_HEX.get(chain)
    if not hex_chain:
        return None
    cache_key = f"top_profit_wallets_{chain}_{token_address.lower()}"
    if _is_cached(cache_key, FAST_CACHE_TTL):
        return _get_cache(cache_key)
    _rate_check()
    try:
        resp = get_session().get(
            f"{BASE_URL}/erc20/{token_address}/top-profitable-wallets",
            params={"chain": hex_chain, "limit": limit},
            headers=_headers(),
            timeout=10,
        )
        if resp.status_code in (400, 404, 429):
            return None
        resp.raise_for_status()
        data = resp.json()
        wallets = data.get("result", data) if isinstance(data, dict) else data
        if not isinstance(wallets, list):
            wallets = []

        profitable_wallets = []
        total_profit = 0.0
        for w in wallets[:limit]:
            profit = _safe_float(w.get("realized_profit_usd", w.get("total_sold_usd", 0))
                                 - w.get("total_bought_usd", 0))
            if profit <= 0:
                profit = _safe_float(w.get("realized_profit_usd", 0))
            total_profit += profit
            profitable_wallets.append({
                "address": w.get("address", w.get("wallet_address", "")),
                "realized_profit_usd": round(profit, 2),
                "count_of_trades": _safe_int(w.get("count_of_trades", w.get("total_trades", 0))),
                "avg_buy_price": _safe_float(w.get("avg_buy_price_usd", 0)),
            })

        n = len(profitable_wallets)
        avg_profit = total_profit / n if n else 0
        # Conviction = normalized score based on # of profitable wallets and avg profit
        conviction = min(100.0, (n * 10) + min(50.0, avg_profit / 500.0 * 50.0))

        result = {
            "total_profitable_wallets": n,
            "avg_realized_profit_usd": round(avg_profit, 2),
            "total_realized_profit_usd": round(total_profit, 2),
            "top_wallets": profitable_wallets[:5],  # Keep top 5 for copy-trade signals
            "smart_money_conviction": round(conviction, 1),
        }
        _set_cache(cache_key, result)
        return result
    except Exception as e:
        logger.debug(f"Top profitable wallets error {token_address[:8]}/{chain}: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 22. WALLET INSIGHT — Quality scoring for whale wallets
# GET /wallets/{address}/insight?chain={chain}
# Returns: activity age, transfer counts, counterparties, swap volume
# Use case: Qualify whale wallets as "real" vs bot/wash-trade accounts
# ─────────────────────────────────────────────────────────────────────────────
def get_wallet_insight(address: str, chain: str = "ethereum") -> Optional[dict]:
    """
    Get insight metrics for a wallet address.
    Use to qualify whale/smart-money wallets as legitimate.

    Returns:
      - wallet_age_days: int
      - total_transactions: int
      - total_counterparties: int
      - total_swap_volume_usd: float
      - quality_score: float (0-100, our computed score)
    """
    if not MORALIS_API_KEY:
        return None
    hex_chain = CHAIN_HEX.get(chain, "0x1")
    cache_key = f"wallet_insight_{chain}_{address.lower()}"
    if _is_cached(cache_key, SLOW_CACHE_TTL):
        return _get_cache(cache_key)
    _rate_check()
    try:
        resp = get_session().get(
            f"{BASE_URL}/wallets/{address}/insight",
            params={"chain": hex_chain},
            headers=_headers(),
            timeout=10,
        )
        if resp.status_code in (400, 404, 429):
            return None
        resp.raise_for_status()
        data = resp.json()

        age_days = _safe_int(data.get("wallet_age_in_days", data.get("age_in_days", 0)))
        total_txs = _safe_int(data.get("total_transactions", data.get("total_count_transactions", 0)))
        counterparties = _safe_int(data.get("total_counterparties", data.get("unique_counterparties", 0)))
        swap_vol = _safe_float(data.get("total_swap_volume_usd", data.get("swap_volume_usd", 0)))

        # Quality score: old wallet + many txs + many counterparties + swap volume
        age_score = min(30.0, age_days / 365.0 * 30.0)  # max 30 for 1yr+
        tx_score = min(25.0, total_txs / 1000.0 * 25.0)  # max 25 for 1k+ txs
        cp_score = min(20.0, counterparties / 200.0 * 20.0)  # max 20 for 200+ counterparties
        vol_score = min(25.0, swap_vol / 100_000.0 * 25.0)  # max 25 for $100k+ swap volume
        quality = min(100.0, age_score + tx_score + cp_score + vol_score)

        result = {
            "wallet_age_days": age_days,
            "total_transactions": total_txs,
            "total_counterparties": counterparties,
            "total_swap_volume_usd": round(swap_vol, 2),
            "quality_score": round(quality, 1),
        }
        _set_cache(cache_key, result)
        return result
    except Exception as e:
        logger.debug(f"Wallet insight error {address[:8]}/{chain}: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 23. WALLET PnL SUMMARY — Our own trade performance tracking
# GET /wallets/{address}/profitability/summary?chain={chain}&days={days}
# Returns: total_realized_pnl_usd, total_trades, win_rate, avg_profit_per_trade
# Use case: Track our bot wallet's actual performance (the money metric)
# ─────────────────────────────────────────────────────────────────────────────
def get_wallet_pnl_summary(
    address: str,
    chain: str = "ethereum",
    days: int = 30,
) -> Optional[dict]:
    """
    Get profit & loss summary for a wallet.
    Use to track OUR bot's trading performance.

    Returns:
      - total_realized_pnl_usd: float (net P&L in USD)
      - total_trades: int
      - profitable_trades: int
      - losing_trades: int
      - win_rate_pct: float (0-100)
      - avg_profit_per_trade_usd: float
      - total_bought_usd: float
      - total_sold_usd: float
    """
    if not MORALIS_API_KEY:
        return None
    hex_chain = CHAIN_HEX.get(chain, "0x1")
    cache_key = f"wallet_pnl_{chain}_{address.lower()}_{days}"
    if _is_cached(cache_key, SLOW_CACHE_TTL):
        return _get_cache(cache_key)
    _rate_check()
    try:
        resp = get_session().get(
            f"{BASE_URL}/wallets/{address}/profitability/summary",
            params={"chain": hex_chain, "days": days},
            headers=_headers(),
            timeout=10,
        )
        if resp.status_code in (400, 404, 429):
            return None
        resp.raise_for_status()
        data = resp.json()

        total_trades = _safe_int(data.get("total_count_of_trades", data.get("total_trades", 0)))
        profitable = _safe_int(data.get("total_profitable_trades", 0))
        losing = _safe_int(data.get("total_losing_trades", 0))
        total_bought = _safe_float(data.get("total_bought_usd", 0))
        total_sold = _safe_float(data.get("total_sold_usd", 0))
        realized_pnl = _safe_float(data.get("total_realized_profit_usd",
                                              data.get("total_pnl_usd", total_sold - total_bought)))

        win_rate = (profitable / total_trades * 100) if total_trades > 0 else 0.0
        avg_profit = realized_pnl / total_trades if total_trades > 0 else 0.0

        result = {
            "total_realized_pnl_usd": round(realized_pnl, 2),
            "total_trades": total_trades,
            "profitable_trades": profitable,
            "losing_trades": losing,
            "win_rate_pct": round(win_rate, 1),
            "avg_profit_per_trade_usd": round(avg_profit, 2),
            "total_bought_usd": round(total_bought, 2),
            "total_sold_usd": round(total_sold, 2),
        }
        _set_cache(cache_key, result)
        return result
    except Exception as e:
        logger.debug(f"Wallet PnL summary error {address[:8]}/{chain}: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 24. WALLET NET WORTH — Automated capital tracking
# GET /wallets/{address}/net-worth?chains[]={chain}
# Returns: total_networth_usd, chains breakdown
# Use case: Track total wallet value across chains (our capital base)
# ─────────────────────────────────────────────────────────────────────────────
def get_wallet_net_worth(
    address: str,
    chains: Optional[list[str]] = None,
) -> Optional[dict]:
    """
    Get total net worth of a wallet across chains.
    Use to track our bot's total capital automatically.

    Returns:
      - total_networth_usd: float
      - chains: dict[chain_name, usd_value]
    """
    if not MORALIS_API_KEY:
        return None
    cache_key = f"wallet_networth_{address.lower()}"
    if _is_cached(cache_key, SLOW_CACHE_TTL):
        return _get_cache(cache_key)
    _rate_check()
    try:
        params: dict = {"exclude_spam": "true", "exclude_unverified_contracts": "true"}
        if chains:
            for c in chains:
                hex_c = CHAIN_HEX.get(c)
                if hex_c:
                    params.setdefault("chains[]", [])
                    if isinstance(params["chains[]"], list):
                        params["chains[]"].append(hex_c)

        resp = get_session().get(
            f"{BASE_URL}/wallets/{address}/net-worth",
            params=params,
            headers=_headers(),
            timeout=10,
        )
        if resp.status_code in (400, 404, 429):
            return None
        resp.raise_for_status()
        data = resp.json()

        total_worth = _safe_float(data.get("total_networth_usd", 0))
        chain_breakdown = {}
        for chain_data in data.get("chains", []):
            chain_name = chain_data.get("chain", "unknown")
            chain_usd = _safe_float(chain_data.get("networth_usd", 0))
            if chain_usd > 0:
                chain_breakdown[chain_name] = round(chain_usd, 2)

        result = {
            "total_networth_usd": round(total_worth, 2),
            "chains": chain_breakdown,
        }
        _set_cache(cache_key, result)
        return result
    except Exception as e:
        logger.debug(f"Wallet net worth error {address[:8]}: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 25. HISTORICAL TOKEN HOLDERS V2 — Timeseries holder data (Pro)
# GET /erc20/{address}/holders/historical?chain={chain}  (EVM)
# GET /token/{network}/{address}/holders/historical       (Solana)
# Returns: structured time buckets with holder counts and changes
# Use case: Replaces holder_growth with richer structured timeseries
# ─────────────────────────────────────────────────────────────────────────────
def get_historical_token_holders_v2(
    token_address: str,
    chain: str,
    is_solana: bool = False,
) -> Optional[dict]:
    """
    Historical holder timeseries.

    REST endpoints for EVM + Solana historical holders sunset July 31 2026.
    Return None so callers skip growth signals without burning CU.
    Re-enable via Data Feeds historical_balances recipe when sink is live.
    """
    return None


# ─────────────────────────────────────────────────────────────────────────────
# 26. TOP HOLDERS (SOLANA) — Whale analysis for Solana tokens
# GET /token/{network}/{address}/top-holders
# Returns: paginated top holders with balances and percentages
# Use case: Identify whale concentration on Solana (EVM already has this)
# ─────────────────────────────────────────────────────────────────────────────
def get_solana_top_holders_detailed(
    token_address: str,
    limit: int = 20,
) -> Optional[dict]:
    """
    Get detailed top holders for a Solana token.

    REST sunsets July 31 2026 — uses moralis_solana cascade
    (Data Feeds → Helius → free RPC).
    """
    if not token_address:
        return None
    cache_key = f"sol_top_holders_{token_address}"
    if _is_cached(cache_key, SLOW_CACHE_TTL):
        return _get_cache(cache_key)
    try:
        from data.providers.moralis_solana import get_token_top_holders
        data = get_token_top_holders(token_address, limit=limit)
        holders = data.get("holders") or []
        if not holders:
            return None

        top_holders = []
        total_top10_pct = 0.0
        whale_count = 0
        for i, h in enumerate(holders[:limit]):
            pct = _safe_float(h.get("percentage", 0))
            usd = _safe_float(h.get("usd_value", 0))
            addr = h.get("address", "")
            top_holders.append({"address": addr, "percentage": round(pct, 2), "usd_value": round(usd, 2)})
            if i < 10:
                total_top10_pct += pct
            if pct >= 1.0:
                whale_count += 1

        if total_top10_pct >= 80:
            risk = "critical"
        elif total_top10_pct >= 50:
            risk = "high"
        elif total_top10_pct >= 25:
            risk = "medium"
        else:
            risk = "low"

        result = {
            "top_10_pct": round(total_top10_pct, 1),
            "whale_count": whale_count,
            "top_holders": top_holders[:10],
            "concentration_risk": risk,
            "source": data.get("source", "cascade"),
        }
        _set_cache(cache_key, result)
        return result
    except Exception as e:
        logger.debug(f"Solana top holders error {token_address[:8]}: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 27. TOKEN CATEGORIES — Auto-tag tokens (meme, defi, l2, stablecoin, etc.)
# GET /tokens/categories  (migrated from /discovery/tokens/categories)
# Returns: list of {category, description}
# GET /erc20/{address}/metadata includes categories in metadata
# Use case: Auto-filter by category (e.g., only trade meme coins, skip stables)
# ─────────────────────────────────────────────────────────────────────────────
def get_token_categories() -> list[dict]:
    """
    Get all available token categories from Moralis.
    Used to auto-classify tokens and filter by category preference.
    """
    if not MORALIS_API_KEY:
        return []
    cache_key = "token_categories_all"
    if _is_cached(cache_key, 3600):  # 1hr cache — categories don't change often
        return _get_cache(cache_key)
    _rate_check()
    try:
        resp = get_session().get(
            f"{BASE_URL}/tokens/categories",
            headers=_headers(),
            timeout=8,
        )
        if resp.status_code in (400, 404, 429):
            return []
        resp.raise_for_status()
        data = resp.json()
        categories = data.get("result", data) if isinstance(data, dict) else data
        if not isinstance(categories, list):
            return []
        result = [
            {"id": c.get("id", c.get("category", "")), "name": c.get("name", c.get("category", ""))}
            for c in categories
        ]
        _set_cache(cache_key, result)
        return result
    except Exception as e:
        logger.debug(f"Token categories error: {e}")
        return []


def get_token_category(token_address: str, chain: str) -> Optional[str]:
    """
    Get the primary category for a specific token.
    Returns category string like "meme", "defi", "l2", "stablecoin", etc.
    """
    if not MORALIS_API_KEY:
        return None
    hex_chain = CHAIN_HEX.get(chain)
    if not hex_chain:
        return None
    cache_key = f"token_cat_{chain}_{token_address.lower()}"
    if _is_cached(cache_key, SLOW_CACHE_TTL):
        return _get_cache(cache_key)
    _rate_check()
    try:
        resp = get_session().get(
            f"{BASE_URL}/erc20/metadata",
            params={"chain": hex_chain, "addresses[]": token_address},
            headers=_headers(),
            timeout=8,
        )
        if resp.status_code in (400, 404, 429):
            return None
        resp.raise_for_status()
        data = resp.json()
        tokens = data if isinstance(data, list) else [data]
        if not tokens:
            return None
        token = tokens[0]
        categories = token.get("categories", token.get("category", []))
        if isinstance(categories, list) and categories:
            cat = categories[0] if isinstance(categories[0], str) else categories[0].get("name", "")
        elif isinstance(categories, str):
            cat = categories
        else:
            cat = None
        if cat:
            _set_cache(cache_key, cat)
        return cat
    except Exception as e:
        logger.debug(f"Token category error {token_address[:8]}/{chain}: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 27. INSTANT TOKEN SCORE — Single-call safety gate
#    GET /tokens/{address}/score?chain={chain}
#    Returns a 0-100 composite score with sub-metrics.
#    Use as EARLY-OUT before heavy enrichment — score < 30 = block immediately.
#    CU cost: ~5 CU (very cheap).
# ─────────────────────────────────────────────────────────────────────────────
def get_token_score_instant(token_address: str, chain: str) -> Optional[dict]:
    """
    Get instant 0-100 safety score for a token.
    Returns: {score: int, price_usd, volume_24h, liquidity_usd, txn_count, ...}

    Solana Token Score sunsets July 31 2026 — returns None (0 CU).
    """
    if not MORALIS_API_KEY:
        return None
    if str(chain).lower() == "solana":
        return None
    hex_chain = CHAIN_HEX.get(chain)
    if not hex_chain:
        return None
    cache_key = f"score_inst_{chain}_{token_address.lower()}"
    if _is_cached(cache_key, FAST_CACHE_TTL):
        return _get_cache(cache_key)
    try:
        from core.moralis_cu_budget import cu_budget
        if not cu_budget.can_afford("token_score"):
            return None
    except Exception:
        pass
    _rate_check()
    try:
        resp = get_session().get(
            f"{BASE_URL}/tokens/{token_address}/score",
            params={"chain": hex_chain},
            headers=_headers(),
            timeout=6,
        )
        try:
            from data.providers.moralis_http import _parse_request_weight, _record_usage
            _record_usage("token_score", _parse_request_weight(resp) or 100)
        except Exception:
            pass
        if resp.status_code in (400, 404, 429):
            return None
        resp.raise_for_status()
        data = resp.json()
        result = {
            "moralis_score":   _safe_int(data.get("moralis_score", data.get("score", 50))),
            "price_usd":       _safe_float(data.get("price_usd", data.get("usdPrice", 0))),
            "volume_24h":      _safe_float(data.get("volume_24h", data.get("volume_usd", 0))),
            "liquidity_usd":   _safe_float(data.get("liquidity_usd", data.get("total_liquidity_usd", 0))),
            "txn_count_24h":   _safe_int(data.get("transaction_count_24h", data.get("transactions", 0))),
            "holders":         _safe_int(data.get("holders", data.get("holder_count", 0))),
        }
        _set_cache(cache_key, result)
        return result
    except Exception as e:
        logger.debug(f"Instant score error {token_address[:8]}/{chain}: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 28. DEX PAIR STATS — Buy/sell analysis per pair
#    GET /pairs/{pairAddress}/stats?chain={chain}
#    Returns: buyer/seller counts, buy/sell volumes per timeframe (5m,1h,4h,24h)
#    Trading signal: buy_volume > sell_volume + rising unique buyers = accumulation
# ─────────────────────────────────────────────────────────────────────────────
def get_pair_stats(pair_address: str, chain: str) -> Optional[dict]:
    """
    Get DEX pair-level trading statistics.
    Returns parsed dict with buy/sell ratios and unique trader counts.
    """
    if not MORALIS_API_KEY or not pair_address:
        return None
    hex_chain = CHAIN_HEX.get(chain)
    if not hex_chain:
        return None
    cache_key = f"pair_stats_{chain}_{pair_address.lower()}"
    if _is_cached(cache_key, FAST_CACHE_TTL):
        return _get_cache(cache_key)
    _rate_check()
    try:
        resp = get_session().get(
            f"{BASE_URL}/pairs/{pair_address}/stats",
            params={"chain": hex_chain},
            headers=_headers(),
            timeout=6,
        )
        if resp.status_code in (400, 404, 429):
            return None
        resp.raise_for_status()
        data = resp.json()
        # Parse the stats — field names may vary between versions
        buyers_24h  = _safe_int(data.get("buyers_24h", data.get("unique_buyers_24h", 0)))
        sellers_24h = _safe_int(data.get("sellers_24h", data.get("unique_sellers_24h", 0)))
        buy_vol     = _safe_float(data.get("buy_volume_24h_usd", data.get("buy_volume_24h", 0)))
        sell_vol    = _safe_float(data.get("sell_volume_24h_usd", data.get("sell_volume_24h", 0)))
        total_traders = buyers_24h + sellers_24h
        buy_sell_ratio = (buyers_24h / sellers_24h) if sellers_24h > 0 else (
            2.0 if buyers_24h > 0 else 1.0
        )
        buy_vol_ratio = (buy_vol / sell_vol) if sell_vol > 0 else (
            2.0 if buy_vol > 0 else 1.0
        )
        result = {
            "buyers_24h":       buyers_24h,
            "sellers_24h":      sellers_24h,
            "buy_sell_ratio":   round(buy_sell_ratio, 2),
            "buy_volume_24h":   buy_vol,
            "sell_volume_24h":  sell_vol,
            "buy_vol_ratio":    round(buy_vol_ratio, 2),
            "unique_traders":   total_traders,
            "is_accumulating":  buy_sell_ratio > 1.3 and buy_vol_ratio > 1.2,
        }
        _set_cache(cache_key, result)
        return result
    except Exception as e:
        logger.debug(f"Pair stats error {pair_address[:8]}/{chain}: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 29. SINGLE TOKEN ANALYTICS — Rich per-token analytics (GET version)
#    GET /tokens/{address}/analytics?chain={chain}
#    Returns: buy/sell volumes, buyer/seller counts, FDV trends, liquidity
#    Trading signal: buy_volume surging while price flat = stealth accumulation
# ─────────────────────────────────────────────────────────────────────────────
def get_single_token_analytics(token_address: str, chain: str) -> Optional[dict]:
    """
    Get rich trading analytics for a single token.
    Returns parsed dict with volume breakdowns and FDV trends.
    """
    if not MORALIS_API_KEY:
        return None
    hex_chain = CHAIN_HEX.get(chain)
    if not hex_chain:
        return None
    cache_key = f"tok_analytics_{chain}_{token_address.lower()}"
    if _is_cached(cache_key, FAST_CACHE_TTL):
        return _get_cache(cache_key)
    _rate_check()
    try:
        resp = get_session().get(
            f"{BASE_URL}/tokens/{token_address}/analytics",
            params={"chain": hex_chain},
            headers=_headers(),
            timeout=6,
        )
        if resp.status_code in (400, 404, 429):
            return None
        resp.raise_for_status()
        data = resp.json()
        buy_vol   = _safe_float(data.get("totalBuyVolume", data.get("buy_volume_usd", 0)))
        sell_vol  = _safe_float(data.get("totalSellVolume", data.get("sell_volume_usd", 0)))
        buyers    = _safe_int(data.get("totalBuyers", data.get("unique_buyers", 0)))
        sellers   = _safe_int(data.get("totalSellers", data.get("unique_sellers", 0)))
        txn_count = _safe_int(data.get("totalTransactions", data.get("transaction_count", 0)))
        liquidity = _safe_float(data.get("totalLiquidityUSD",
                        data.get("liquidity_usd", data.get("total_liquidity_usd", 0))))
        fdv       = _safe_float(data.get("fullyDilutedValuation", data.get("fdv", 0)))
        # Stealth accumulation: buy volume > 2x sell volume while not pumping
        stealth_accumulation = (buy_vol > sell_vol * 2.0 and buyers > sellers * 1.3) if sell_vol > 0 else False
        result = {
            "buy_volume_usd":        buy_vol,
            "sell_volume_usd":       sell_vol,
            "unique_buyers":         buyers,
            "unique_sellers":        sellers,
            "txn_count":             txn_count,
            "liquidity_usd":         liquidity,
            "fdv":                   fdv,
            "stealth_accumulation":  stealth_accumulation,
            "buy_sell_vol_ratio":    round((buy_vol / sell_vol) if sell_vol > 0 else 1.0, 2),
        }
        _set_cache(cache_key, result)
        return result
    except Exception as e:
        logger.debug(f"Single token analytics error {token_address[:8]}/{chain}: {e}")
        return None
