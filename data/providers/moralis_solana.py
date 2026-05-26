"""
data/providers/moralis_solana.py — Moralis Solana Data API Provider.

Solana-native intelligence endpoints:

  1. get_sol_balance(address)                    → Native SOL balance (10 CU)
  2. get_solana_portfolio(address)               → Full portfolio: SOL + SPL tokens (10 CU)
  3. get_spl_token_balances(address)             → SPL token holdings with metadata (10 CU)
  4. get_token_snipers(pair_address)             → Sniper wallets for a pair (50 CU)
  5. get_token_top_holders(token_address)        → Top holders + concentration (50 CU)
  6. get_pumpfun_graduated()                     → Newly graduated Pump.fun tokens (25 CU)
  7. get_token_pairs(token_address)              → Trading pairs with liquidity (25 CU)
  8. get_token_price(token_address)              → Current price in USD (10 CU)
  9. get_wallet_swaps(address)                   → DEX swap history (50 CU)
 10. get_token_ohlcv(pair_address)              → Candlestick OHLCV data (10 CU)

Base URL: https://solana-gateway.moralis.io
Auth: X-Api-Key header (same key as EVM Moralis API)

Usage:
  from data.providers.moralis_solana import get_token_snipers, get_pumpfun_graduated
"""

import logging
import time
import threading
from typing import Optional

from data.http_session import get_session

from config import settings

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────
MORALIS_API_KEY: str = getattr(settings, "MORALIS_API_KEY", "")
BASE_URL = "https://solana-gateway.moralis.io"
NETWORK = "mainnet"

# Cache: Solana data is fast-moving — shorter TTL
CACHE_TTL = 120  # 2 minutes
_cache: dict[str, dict] = {}

# Rate limiting (shared budget with EVM calls — be conservative)
_rate_window_start: float = time.time()
_rate_calls_in_window: int = 0
RATE_LIMIT_PER_MIN = 20  # Conservative to share with EVM
_rate_lock = threading.Lock()


def _headers() -> dict:
    return {"accept": "application/json", "X-API-Key": MORALIS_API_KEY}


def _available() -> bool:
    return bool(MORALIS_API_KEY)


def _rate_check() -> None:
    global _rate_window_start, _rate_calls_in_window
    with _rate_lock:
        now = time.time()
        if now - _rate_window_start >= 60:
            _rate_window_start = now
            _rate_calls_in_window = 0
        _rate_calls_in_window += 1
        if _rate_calls_in_window >= RATE_LIMIT_PER_MIN:
            sleep_for = 60 - (now - _rate_window_start) + 1
            if sleep_for > 0:
                logger.debug(f"Moralis Solana rate limit: sleeping {sleep_for:.1f}s")
                time.sleep(sleep_for)
            _rate_window_start = time.time()
            _rate_calls_in_window = 1


def _is_cached(key: str) -> bool:
    entry = _cache.get(key)
    return bool(entry and (time.time() - entry.get("ts", 0)) < CACHE_TTL)


def _get_cache(key: str):
    return _cache.get(key, {}).get("data")


def _set_cache(key: str, data) -> None:
    _cache[key] = {"data": data, "ts": time.time()}


# ─────────────────────────────────────────────────────────────────────────────
# 1. Native SOL Balance  (GET /account/{network}/{address}/balance) — 10 CU
# ─────────────────────────────────────────────────────────────────────────────
def get_sol_balance(address: str) -> dict:
    """
    Get native SOL balance for a Solana wallet.

    Returns:
        {"solana": "1.5", "lamports": "1500000000"}
    """
    if not _available() or not address:
        return {"solana": "0", "lamports": "0"}

    cache_key = f"sol_bal_{address}"
    if _is_cached(cache_key):
        return _get_cache(cache_key)

    _rate_check()
    try:
        resp = get_session().get(
            f"{BASE_URL}/account/{NETWORK}/{address}/balance",
            headers=_headers(),
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        _set_cache(cache_key, data)
        return data
    except Exception as e:
        logger.warning(f"Moralis SOL balance failed for {address}: {e}")
        return {"solana": "0", "lamports": "0"}


# ─────────────────────────────────────────────────────────────────────────────
# 2. Solana Portfolio  (GET /account/{network}/{address}/portfolio) — 10 CU
# ─────────────────────────────────────────────────────────────────────────────
def get_solana_portfolio(address: str) -> dict:
    """
    Get complete Solana portfolio: native SOL + all SPL tokens + NFTs.

    Returns:
        {"nativeBalance": {...}, "tokens": [...], "nfts": [...]}
    """
    if not _available() or not address:
        return {"nativeBalance": {}, "tokens": [], "nfts": []}

    cache_key = f"sol_portfolio_{address}"
    if _is_cached(cache_key):
        return _get_cache(cache_key)

    _rate_check()
    try:
        resp = get_session().get(
            f"{BASE_URL}/account/{NETWORK}/{address}/portfolio",
            params={"excludeSpam": "true"},
            headers=_headers(),
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        _set_cache(cache_key, data)
        return data
    except Exception as e:
        logger.warning(f"Moralis Solana portfolio failed for {address}: {e}")
        return {"nativeBalance": {}, "tokens": [], "nfts": []}


# ─────────────────────────────────────────────────────────────────────────────
# 3. SPL Token Balances  (GET /account/{network}/{address}/tokens) — 10 CU
# ─────────────────────────────────────────────────────────────────────────────
def get_spl_token_balances(address: str) -> list:
    """
    Get all SPL token balances for a Solana wallet.

    Returns list of:
        {"mint": "...", "name": "...", "symbol": "...", "amount": "...", "decimals": 9, ...}
    """
    if not _available() or not address:
        return []

    cache_key = f"spl_balances_{address}"
    if _is_cached(cache_key):
        return _get_cache(cache_key)

    _rate_check()
    try:
        resp = get_session().get(
            f"{BASE_URL}/account/{NETWORK}/{address}/tokens",
            params={"excludeSpam": "true"},
            headers=_headers(),
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        _set_cache(cache_key, data)
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.warning(f"Moralis SPL balances failed for {address}: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# 4. Token Snipers  (GET /token/{network}/pairs/{pairAddress}/snipers) — 50 CU
# ─────────────────────────────────────────────────────────────────────────────
def get_token_snipers(pair_address: str, blocks_after_creation: int = 10) -> dict:
    """
    Get snipers for a Solana token pair.

    Args:
        pair_address: The Raydium/Orca pair address
        blocks_after_creation: How many blocks after pool creation to scan (default: 10)

    Returns:
        {
            "sniper_count": int,
            "total_sniped_usd": float,
            "snipers": [{
                "wallet": str,
                "tokens_sniped": float,
                "usd_sniped": float,
                "realized_profit_pct": float,
                "current_balance": float,
                "sold": bool,
            }],
            "risk_level": "low" | "medium" | "high" | "critical",
        }
    """
    if not _available() or not pair_address:
        return {"sniper_count": 0, "total_sniped_usd": 0, "snipers": [], "risk_level": "unknown"}

    cache_key = f"snipers_{pair_address}"
    if _is_cached(cache_key):
        return _get_cache(cache_key)

    _rate_check()
    try:
        params = {}
        if blocks_after_creation:
            params["blocksAfterCreation"] = blocks_after_creation

        resp = get_session().get(
            f"{BASE_URL}/token/{NETWORK}/pairs/{pair_address}/snipers",
            params=params,
            headers=_headers(),
            timeout=15,
        )
        resp.raise_for_status()
        raw = resp.json()

        # Parse the response
        raw_snipers = raw.get("result", [])
        total_sniped_usd = sum(s.get("totalSnipedUsd", 0) for s in raw_snipers)

        snipers = []
        for s in raw_snipers:
            snipers.append({
                "wallet": s.get("walletAddress", ""),
                "tokens_sniped": s.get("totalTokensSniped", 0),
                "usd_sniped": s.get("totalSnipedUsd", 0),
                "realized_profit_pct": s.get("realizedProfitPercentage", 0),
                "current_balance": s.get("currentBalance", 0),
                "sold": s.get("totalTokensSold", 0) > 0,
                "sell_txns": s.get("totalSellTransactions", 0),
            })

        # Risk classification based on sniper behavior
        sniper_count = len(snipers)
        dumped_count = sum(1 for s in snipers if s["sold"])

        if sniper_count >= 10 or total_sniped_usd >= 50_000:
            risk_level = "critical"
        elif sniper_count >= 5 or dumped_count >= 3:
            risk_level = "high"
        elif sniper_count >= 2:
            risk_level = "medium"
        else:
            risk_level = "low"

        result = {
            "sniper_count": sniper_count,
            "total_sniped_usd": total_sniped_usd,
            "snipers": snipers,
            "risk_level": risk_level,
            "dumped_count": dumped_count,
        }

        _set_cache(cache_key, result)
        logger.info(
            f"🎯 Snipers for {pair_address[:8]}...: "
            f"{sniper_count} snipers (${total_sniped_usd:,.0f} sniped) — risk={risk_level}"
        )
        return result
    except Exception as e:
        logger.warning(f"Moralis snipers fetch failed for {pair_address}: {e}")
        return {"sniper_count": 0, "total_sniped_usd": 0, "snipers": [], "risk_level": "unknown"}


def get_sniper_score(pair_address: str) -> float:
    """
    Convert sniper data into a 0-100 safety score.

    100 = no snipers (clean launch)
    0   = heavily sniped (insider dump likely)
    """
    data = get_token_snipers(pair_address)
    risk = data["risk_level"]

    if risk == "critical":
        return 10.0
    elif risk == "high":
        return 30.0
    elif risk == "medium":
        return 60.0
    elif risk == "low":
        return 85.0
    else:
        return 50.0  # Unknown — neutral


# ─────────────────────────────────────────────────────────────────────────────
# 5. Token Top Holders  (GET /token/{network}/{address}/top-holders) — 50 CU
# ─────────────────────────────────────────────────────────────────────────────
def get_token_top_holders(token_address: str, limit: int = 10) -> dict:
    """
    Get top holder data for a Solana token.

    Returns:
        {
            "holders": [{address, balance, percentage, usdValue}],
            "top10_concentration": float,  # 0.0-1.0
            "concentration_risk": "low" | "medium" | "high" | "critical",
        }
    """
    if not _available() or not token_address:
        return {"holders": [], "top10_concentration": 0.0, "concentration_risk": "unknown"}

    cache_key = f"holders_{token_address}_{limit}"
    if _is_cached(cache_key):
        return _get_cache(cache_key)

    _rate_check()
    try:
        resp = get_session().get(
            f"{BASE_URL}/token/{NETWORK}/{token_address}/top-holders",
            params={"limit": limit},
            headers=_headers(),
            timeout=15,
        )
        resp.raise_for_status()
        raw = resp.json()

        holders = raw.get("result", [])
        total_pct = sum(float(h.get("percentageRelativeToTotalSupply", 0)) for h in holders[:10])

        if total_pct >= 80:
            risk = "critical"
        elif total_pct >= 50:
            risk = "high"
        elif total_pct >= 30:
            risk = "medium"
        else:
            risk = "low"

        result = {
            "holders": [
                {
                    "address": h.get("ownerAddress", ""),
                    "balance": float(h.get("balance", 0)),
                    "percentage": float(h.get("percentageRelativeToTotalSupply", 0)),
                    "usd_value": float(h.get("usdValue", 0)),
                }
                for h in holders
            ],
            "top10_concentration": total_pct / 100.0,
            "concentration_risk": risk,
        }

        _set_cache(cache_key, result)
        return result
    except Exception as e:
        logger.warning(f"Moralis Solana top holders failed for {token_address}: {e}")
        return {"holders": [], "top10_concentration": 0.0, "concentration_risk": "unknown"}


# ─────────────────────────────────────────────────────────────────────────────
# 6. Pump.fun Graduated  (GET /token/{network}/exchange/pumpfun/graduated) — 25 CU
# ─────────────────────────────────────────────────────────────────────────────
def get_pumpfun_graduated(limit: int = 20) -> list[dict]:
    """
    Get recently graduated Pump.fun tokens (moved from bonding curve to Raydium).

    This is THE moment for early entry on Solana meme tokens.

    Returns list of:
        {
            "token_address": str (mint),
            "name": str,
            "symbol": str,
            "pair_address": str,
            "price_usd": float,
            "liquidity_usd": float,
            "volume_24h": float,
            "graduated_at": str (ISO timestamp),
        }
    """
    if not _available():
        return []

    cache_key = f"pumpfun_graduated_{limit}"
    if _is_cached(cache_key):
        return _get_cache(cache_key)

    _rate_check()
    try:
        resp = get_session().get(
            f"{BASE_URL}/token/{NETWORK}/exchange/pumpfun/graduated",
            params={"limit": limit},
            headers=_headers(),
            timeout=15,
        )
        resp.raise_for_status()
        raw = resp.json()

        tokens = []
        for t in raw.get("result", raw if isinstance(raw, list) else []):
            tokens.append({
                "token_address": t.get("tokenAddress", t.get("mint", "")),
                "name": t.get("name", ""),
                "symbol": t.get("symbol", ""),
                "pair_address": t.get("pairAddress", ""),
                "price_usd": float(t.get("priceUsd") or t.get("usdPrice") or 0),
                "liquidity_usd": float(t.get("liquidityUsd") or 0),
                "volume_24h": float(t.get("volume24h") or 0),
                "graduated_at": t.get("graduatedAt", t.get("blockTimestamp", "")),
                "market_cap": float(t.get("marketCap") or 0),
            })

        _set_cache(cache_key, tokens)
        if tokens:
            logger.info(f"🚀 Pump.fun graduated: {len(tokens)} new tokens found")
        return tokens
    except Exception as e:
        logger.warning(f"Moralis Pump.fun graduated fetch failed: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# 7. Token Pairs  (GET /token/{network}/{address}/pairs) — 25 CU
# ─────────────────────────────────────────────────────────────────────────────
def get_solana_token_pairs(token_address: str) -> list[dict]:
    """
    Get all DEX trading pairs for a Solana token.

    Returns list of:
        {"pair_address": str, "exchange": str, "liquidity_usd": float, ...}
    """
    if not _available() or not token_address:
        return []

    cache_key = f"sol_pairs_{token_address}"
    if _is_cached(cache_key):
        return _get_cache(cache_key)

    _rate_check()
    try:
        resp = get_session().get(
            f"{BASE_URL}/token/{NETWORK}/{token_address}/pairs",
            headers=_headers(),
            timeout=15,
        )
        resp.raise_for_status()
        raw = resp.json()

        pairs = []
        for p in raw.get("result", raw if isinstance(raw, list) else []):
            pairs.append({
                "pair_address": p.get("pairAddress", ""),
                "pair_label": p.get("pairLabel", ""),
                "exchange_name": p.get("exchangeName", ""),
                "exchange_address": p.get("exchangeAddress", ""),
                "liquidity_usd": float(p.get("liquidityUsd", 0)),
                "price_usd": float(p.get("usdPrice", 0)),
                "volume_24h": float(p.get("volume24h", 0)),
            })

        _set_cache(cache_key, pairs)
        return pairs
    except Exception as e:
        logger.warning(f"Moralis Solana pairs failed for {token_address}: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# 7b. Pair Stats  (GET /token/{network}/pairs/{pairAddress}/stats) — 25 CU
#     Buyer/seller velocity across multiple timeframes for Solana pairs.
#     TRADING SIGNAL: Rising buyer count + falling seller count = accumulation.
# ─────────────────────────────────────────────────────────────────────────────
def get_solana_pair_stats(pair_address: str) -> dict:
    """
    Get real-time buyer/seller stats for a Solana DEX pair across timeframes.

    Returns:
        {
            "buyers_5m": int, "sellers_5m": int,
            "buyers_1h": int, "sellers_1h": int,
            "buyers_4h": int, "sellers_4h": int,
            "buyers_24h": int, "sellers_24h": int,
            "buy_volume_1h": float, "sell_volume_1h": float,
            "total_liquidity_usd": float,
            "buy_pressure_5m": float,  # 0-1 ratio
            "buy_pressure_1h": float,
            "buy_pressure_24h": float,
        }

    Cost: 25 CU
    """
    if not _available() or not pair_address:
        return {}

    cache_key = f"sol_pair_stats_{pair_address}"
    if _is_cached(cache_key):
        return _get_cache(cache_key)

    _rate_check()
    try:
        resp = get_session().get(
            f"{BASE_URL}/token/{NETWORK}/pairs/{pair_address}/stats",
            headers=_headers(),
            timeout=10,
        )
        if resp.status_code in (400, 404, 429):
            return {}
        resp.raise_for_status()
        data = resp.json()

        # Moralis returns nested timeframe objects
        def _extract_tf(tf_key: str) -> tuple:
            """Extract buyer/seller/volume counts for a timeframe."""
            tf_data = data.get(tf_key, {})
            buyers = int(tf_data.get("buyers", tf_data.get("buys", 0)) or 0)
            sellers = int(tf_data.get("sellers", tf_data.get("sells", 0)) or 0)
            buy_vol = float(tf_data.get("buy_volume_usd", tf_data.get("buyVolumeUsd", 0)) or 0)
            sell_vol = float(tf_data.get("sell_volume_usd", tf_data.get("sellVolumeUsd", 0)) or 0)
            return buyers, sellers, buy_vol, sell_vol

        b5, s5, bv5, sv5 = _extract_tf("5m")
        b1h, s1h, bv1h, sv1h = _extract_tf("1h")
        b4h, s4h, bv4h, sv4h = _extract_tf("4h")
        b24h, s24h, bv24h, sv24h = _extract_tf("24h")

        def _pressure(buys: int, sells: int) -> float:
            total = buys + sells
            return round(buys / total, 3) if total > 0 else 0.5

        result = {
            "buyers_5m": b5, "sellers_5m": s5,
            "buyers_1h": b1h, "sellers_1h": s1h,
            "buyers_4h": b4h, "sellers_4h": s4h,
            "buyers_24h": b24h, "sellers_24h": s24h,
            "buy_volume_1h": round(bv1h, 2),
            "sell_volume_1h": round(sv1h, 2),
            "buy_volume_24h": round(bv24h, 2),
            "sell_volume_24h": round(sv24h, 2),
            "total_liquidity_usd": float(data.get("totalLiquidityUsd", data.get("total_liquidity_usd", 0)) or 0),
            "buy_pressure_5m": _pressure(b5, s5),
            "buy_pressure_1h": _pressure(b1h, s1h),
            "buy_pressure_24h": _pressure(b24h, s24h),
        }

        _set_cache(cache_key, result)
        logger.debug(
            f"Solana pair stats {pair_address[:12]}...: "
            f"5m={b5}b/{s5}s 1h={b1h}b/{s1h}s "
            f"bp_5m={result['buy_pressure_5m']:.0%}"
        )
        return result

    except Exception as e:
        logger.debug(f"Moralis Solana pair stats failed for {pair_address}: {e}")
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# 8. Token Price  (GET /token/{network}/{address}/price) — 10 CU
# ─────────────────────────────────────────────────────────────────────────────
def get_solana_token_price(token_address: str) -> dict:
    """
    Get current price for a Solana token.

    Returns:
        {"usdPrice": float, "nativePrice": {...}, "exchangeName": str, ...}
    """
    if not _available() or not token_address:
        return {"usdPrice": 0}

    cache_key = f"sol_price_{token_address}"
    if _is_cached(cache_key):
        return _get_cache(cache_key)

    _rate_check()
    try:
        resp = get_session().get(
            f"{BASE_URL}/token/{NETWORK}/{token_address}/price",
            headers=_headers(),
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        _set_cache(cache_key, data)
        return data
    except Exception as e:
        logger.warning(f"Moralis Solana price failed for {token_address}: {e}")
        return {"usdPrice": 0}


# ─────────────────────────────────────────────────────────────────────────────
# 9. Wallet Swaps  (GET /account/{network}/{address}/swaps) — 50 CU
# ─────────────────────────────────────────────────────────────────────────────
def get_wallet_swaps(
    address: str,
    limit: int = 50,
    token_address: Optional[str] = None,
) -> list[dict]:
    """
    Get DEX swap history for a Solana wallet.

    Returns list of:
        {
            "tx_hash": str,
            "type": "buy" | "sell",
            "timestamp": str,
            "exchange": str,
            "bought": {"address": str, "symbol": str, "amount": str, "usd": float},
            "sold": {"address": str, "symbol": str, "amount": str, "usd": float},
            "total_usd": float,
        }
    """
    if not _available() or not address:
        return []

    cache_key = f"sol_swaps_{address}_{token_address or 'all'}"
    if _is_cached(cache_key):
        return _get_cache(cache_key)

    _rate_check()
    try:
        params = {"limit": limit, "order": "DESC"}
        if token_address:
            params["tokenAddress"] = token_address

        resp = get_session().get(
            f"{BASE_URL}/account/{NETWORK}/{address}/swaps",
            params=params,
            headers=_headers(),
            timeout=15,
        )
        resp.raise_for_status()
        raw = resp.json()

        swaps = []
        for s in raw.get("result", []):
            bought = s.get("bought") or {}
            sold = s.get("sold") or {}
            swaps.append({
                "tx_hash": s.get("transactionHash", ""),
                "type": s.get("transactionType", ""),
                "timestamp": s.get("blockTimestamp", ""),
                "exchange": s.get("exchangeName", ""),
                "bought": {
                    "address": bought.get("address", ""),
                    "symbol": bought.get("symbol", ""),
                    "amount": bought.get("amount", "0"),
                    "usd": float(bought.get("usdAmount", 0)),
                },
                "sold": {
                    "address": sold.get("address", ""),
                    "symbol": sold.get("symbol", ""),
                    "amount": sold.get("amount", "0"),
                    "usd": float(sold.get("usdAmount", 0)),
                },
                "total_usd": float(s.get("totalValueUsd", 0)),
            })

        _set_cache(cache_key, swaps)
        return swaps
    except Exception as e:
        logger.warning(f"Moralis wallet swaps failed for {address}: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Convenience / Composite functions
# ─────────────────────────────────────────────────────────────────────────────
def get_sol_balance_usd(address: str, sol_price: float = 0) -> float:
    """Get SOL balance as USD value."""
    bal = get_sol_balance(address)
    sol_amount = float(bal.get("solana", 0))
    if sol_price <= 0:
        # Fallback: get from CoinGecko
        try:
            resp = get_session().get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={"ids": "solana", "vs_currencies": "usd"},
                timeout=8,
            )
            sol_price = float(resp.json().get("solana", {}).get("usd", 140))
        except Exception:
            sol_price = 140.0
    return sol_amount * sol_price


def get_usage_stats() -> dict:
    """Return current rate limiter state for dashboard display."""
    return {
        "calls_this_minute": _rate_calls_in_window,
        "limit_per_minute": RATE_LIMIT_PER_MIN,
        "cache_entries": len(_cache),
        "cache_ttl_seconds": CACHE_TTL,
    }

# ─────────────────────────────────────────────────────────────────────────────
# 10. Token OHLCV (Candlesticks)
# ─────────────────────────────────────────────────────────────────────────────

def get_token_ohlcv(
    pair_address: str,
    timeframe: str = "1h",
    currency: str = "usd",
    limit: int = 1000
) -> Optional[list[dict]]:
    """
    GET /token/{network}/pairs/{pairAddress}/ohlcv
    Cost: 10 CU
    
    Fetch OHLCV (candlestick) data for a specific Solana pair.
    
    Args:
        pair_address: The DEX pair address (e.g., Raydium pool)
        timeframe: "1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w", "1M"
        currency: "usd" or "native"
        limit: Number of candles to return (max 1000)
        
    Returns:
        List of dicts with keys: timestamp, open, high, low, close, volume
    """
    if not _available():
        return None

    cache_key = f"ohlcv_solana_{pair_address}_{timeframe}_{currency}_{limit}"
    if _is_cached(cache_key):
        return _get_cache(cache_key)

    try:
        _rate_check()
        url = f"{BASE_URL}/token/{NETWORK}/pairs/{pair_address}/ohlcv"
        params = {
            "timeframe": timeframe,
            "currency": currency,
            "limit": limit
        }
        
        resp = get_session().get(url, headers=_headers(), params=params, timeout=10)
        
        if resp.status_code == 404:
            logger.debug(f"Moralis Solana OHLCV: pair not found {pair_address}")
            return None
            
        resp.raise_for_status()
        data = resp.json()
        
        candles = data.get("result", [])
        if not candles:
            return None
            
        # Format to match expected OHLCV structure
        formatted_candles = []
        for c in candles:
            formatted_candles.append({
                "timestamp": c.get("timestamp"),
                "open": float(c.get("open", 0)),
                "high": float(c.get("high", 0)),
                "low": float(c.get("low", 0)),
                "close": float(c.get("close", 0)),
                "volume": float(c.get("volume", 0))
            })
            
        _cache[cache_key] = {"ts": time.time(), "data": formatted_candles}
        return formatted_candles

    except Exception as e:
        logger.debug(f"Moralis Solana OHLCV error for {pair_address}: {e}")
        return None
