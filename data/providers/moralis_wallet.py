"""
data/providers/moralis_wallet.py — Moralis Pro Wallet Intelligence Provider.

Portfolio-level intelligence:

  1. get_wallet_net_worth(address, chains)     → Total USD value across chains (50 CU)
  2. get_wallet_pnl(address, chain)            → Realized P&L per token (100 CU)
  3. get_wallet_token_balances(address, chain)  → All ERC20 holdings with metadata (5 CU)
  4. get_wallet_history(address, chain)         → Raw transaction history (5 CU)

Usage:
  from data.providers.moralis_wallet import get_wallet_net_worth, get_wallet_pnl

Chain support: ethereum, base, arbitrum, polygon, bsc, avalanche
Rate limited: 25 req/min with 10-minute cache for wallet data.
"""

import logging
import time
from typing import Optional

import requests

from config import settings

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────
MORALIS_API_KEY: str = getattr(settings, "MORALIS_API_KEY", "")
BASE_URL = "https://deep-index.moralis.io/api/v2.2"

CHAIN_HEX: dict[str, str] = {
    "ethereum":  "0x1",
    "base":      "0x2105",
    "arbitrum":  "0xa4b1",
    "polygon":   "0x89",
    "bsc":       "0x38",
    "avalanche": "0xa86a",
}

# Wallet data changes slower — longer cache
CACHE_TTL = 600  # 10 minutes
_cache: dict[str, dict] = {}

_rate_window_start: float = time.time()
_rate_calls_in_window: int = 0
RATE_LIMIT_PER_MIN = 25


def _headers() -> dict:
    return {"accept": "application/json", "X-API-Key": MORALIS_API_KEY}


def _rate_check() -> None:
    global _rate_window_start, _rate_calls_in_window
    now = time.time()
    if now - _rate_window_start >= 60:
        _rate_window_start = now
        _rate_calls_in_window = 0
    _rate_calls_in_window += 1
    if _rate_calls_in_window >= RATE_LIMIT_PER_MIN:
        sleep_for = 60 - (now - _rate_window_start) + 1
        if sleep_for > 0:
            logger.debug(f"Moralis wallet rate limit: sleeping {sleep_for:.1f}s")
            time.sleep(sleep_for)
        _rate_window_start = time.time()
        _rate_calls_in_window = 1


def _is_cached(key: str) -> bool:
    entry = _cache.get(key)
    return bool(entry and (time.time() - entry.get("ts", 0)) < CACHE_TTL)


def _set_cache(key: str, data) -> None:
    _cache[key] = {"data": data, "ts": time.time()}


def _get_cache(key: str):
    return _cache.get(key, {}).get("data")


def _available() -> bool:
    return bool(MORALIS_API_KEY)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Wallet Net Worth  (GET /wallets/{address}/net-worth)  — 50 CU
# ─────────────────────────────────────────────────────────────────────────────
def get_wallet_net_worth(
    wallet_address: str,
    chains: list[str] = None,
    exclude_spam: bool = True,
    exclude_unverified: bool = True,
) -> dict:
    """
    Get total portfolio value across multiple chains in one call.

    Args:
        wallet_address: EVM wallet address (0x...)
        chains: List of chain names to include. None = all supported.
        exclude_spam: Filter out spam tokens.
        exclude_unverified: Filter out unverified contracts.

    Returns:
        {
            "total_networth_usd": float,
            "chains": [{"chain": "base", "native_balance_usd": ..., "token_balance_usd": ..., ...}],
            "wallet_address": str,
        }

    Cost: 50 Compute Units per call.
    """
    if not _available():
        return {"total_networth_usd": 0.0, "chains": [], "wallet_address": wallet_address}

    cache_key = f"networth_{wallet_address.lower()}"
    if _is_cached(cache_key):
        return _get_cache(cache_key)

    if chains is None:
        chains = list(CHAIN_HEX.keys())

    # Build chain hex list
    chain_hexes = [CHAIN_HEX[c] for c in chains if c in CHAIN_HEX]
    if not chain_hexes:
        return {"total_networth_usd": 0.0, "chains": [], "wallet_address": wallet_address}

    _rate_check()
    try:
        params = {
            "exclude_spam": str(exclude_spam).lower(),
            "exclude_unverified_contracts": str(exclude_unverified).lower(),
        }
        # Moralis accepts chains[] as repeated query params
        for ch in chain_hexes:
            params.setdefault("chains[]", [])
            if isinstance(params["chains[]"], list):
                params["chains[]"].append(ch)

        # Use requests with multiple chain params
        resp = requests.get(
            f"{BASE_URL}/wallets/{wallet_address}/net-worth",
            params=[("chains[]", ch) for ch in chain_hexes]
                + [("exclude_spam", str(exclude_spam).lower()),
                   ("exclude_unverified_contracts", str(exclude_unverified).lower())],
            headers=_headers(),
            timeout=20,
        )
        if resp.status_code in (400, 404):
            logger.debug(f"Moralis net worth: wallet not found {wallet_address[:12]}...")
            return {"total_networth_usd": 0.0, "chains": [], "wallet_address": wallet_address}
        if resp.status_code in (402, 403):
            logger.debug("Moralis net worth: plan limitation")
            return {"total_networth_usd": 0.0, "chains": [], "wallet_address": wallet_address}
        resp.raise_for_status()

        data = resp.json()

        # Parse response
        total_usd = float(data.get("total_networth_usd", 0) or 0)
        chain_data = []
        for chain_entry in data.get("chains", []):
            chain_hex = chain_entry.get("chain", "")
            # Reverse map hex → name
            chain_name = next(
                (name for name, hex_val in CHAIN_HEX.items() if hex_val == chain_hex),
                chain_hex,
            )
            chain_data.append({
                "chain": chain_name,
                "chain_hex": chain_hex,
                "native_balance": chain_entry.get("native_balance", "0"),
                "native_balance_usd": float(chain_entry.get("native_balance_usd", 0) or 0),
                "token_balance_usd": float(chain_entry.get("token_balance_usd", 0) or 0),
                "networth_usd": float(chain_entry.get("networth_usd", 0) or 0),
            })

        result = {
            "total_networth_usd": total_usd,
            "chains": chain_data,
            "wallet_address": wallet_address,
        }
        _set_cache(cache_key, result)
        logger.info(
            f"Moralis net worth: ${total_usd:,.2f} across {len(chain_data)} chains "
            f"for {wallet_address[:12]}..."
        )
        return result

    except Exception as e:
        logger.warning(f"Moralis net worth error for {wallet_address[:12]}...: {e}")
        return {"total_networth_usd": 0.0, "chains": [], "wallet_address": wallet_address}


# ─────────────────────────────────────────────────────────────────────────────
# 2. Wallet Profitability / PnL  (GET /wallets/{address}/profitability)  — 100 CU
# ─────────────────────────────────────────────────────────────────────────────
def get_wallet_pnl(
    wallet_address: str,
    chain: str = "ethereum",
    days: int = 30,
) -> dict:
    """
    Get comprehensive P&L data for a wallet on a specific chain.

    Returns realized profit/loss per token with total portfolio summary.

    Args:
        wallet_address: EVM wallet address
        chain: Chain to query
        days: Lookback period (default 30 days)

    Returns:
        {
            "total_realized_profit_usd": float,
            "total_count_of_trades": int,
            "tokens": [
                {
                    "token_address": str,
                    "symbol": str,
                    "realized_profit_usd": float,
                    "avg_buy_price": float,
                    "avg_sell_price": float,
                    "total_tokens_bought": float,
                    "total_tokens_sold": float,
                    "count_of_trades": int,
                    "profit_percentage": float,
                }
            ],
        }

    Cost: 100 Compute Units per call.
    """
    if not _available() or chain not in CHAIN_HEX:
        return {"total_realized_profit_usd": 0.0, "total_count_of_trades": 0, "tokens": []}

    cache_key = f"pnl_{chain}_{wallet_address.lower()}_{days}"
    if _is_cached(cache_key):
        return _get_cache(cache_key)

    _rate_check()
    try:
        params = {
            "chain": CHAIN_HEX[chain],
            "days": days,
        }
        resp = requests.get(
            f"{BASE_URL}/wallets/{wallet_address}/profitability",
            params=params,
            headers=_headers(),
            timeout=20,
        )
        if resp.status_code in (400, 404):
            return {"total_realized_profit_usd": 0.0, "total_count_of_trades": 0, "tokens": []}
        if resp.status_code in (402, 403):
            logger.debug("Moralis PnL: plan limitation")
            return {"total_realized_profit_usd": 0.0, "total_count_of_trades": 0, "tokens": []}
        resp.raise_for_status()

        data = resp.json()
        result_items = data.get("result", data) if isinstance(data, dict) else data

        tokens_pnl = []
        total_profit = 0.0
        total_trades = 0

        items = result_items if isinstance(result_items, list) else result_items.get("result", [])
        for item in items if isinstance(items, list) else []:
            realized = float(item.get("realized_profit_usd", 0) or 0)
            trades = int(item.get("count_of_trades", 0) or 0)
            total_profit += realized
            total_trades += trades

            tokens_pnl.append({
                "token_address": item.get("token_address", ""),
                "symbol": item.get("token_symbol", item.get("symbol", "???")),
                "name": item.get("token_name", item.get("name", "")),
                "logo": item.get("token_logo", ""),
                "realized_profit_usd": realized,
                "realized_profit_percentage": float(item.get("realized_profit_percentage", 0) or 0),
                "avg_buy_price_usd": float(item.get("avg_buy_price_usd", 0) or 0),
                "avg_sell_price_usd": float(item.get("avg_sell_price_usd", 0) or 0),
                "total_tokens_bought": float(item.get("total_tokens_bought", 0) or 0),
                "total_tokens_sold": float(item.get("total_tokens_sold", 0) or 0),
                "total_usd_invested": float(item.get("total_usd_invested", 0) or 0),
                "count_of_trades": trades,
            })

        # Sort by profit descending
        tokens_pnl.sort(key=lambda t: t["realized_profit_usd"], reverse=True)

        result = {
            "total_realized_profit_usd": total_profit,
            "total_count_of_trades": total_trades,
            "tokens": tokens_pnl,
            "wallet_address": wallet_address,
            "chain": chain,
            "days": days,
        }
        _set_cache(cache_key, result)
        logger.info(
            f"Moralis PnL: ${total_profit:+,.2f} across {total_trades} trades "
            f"({len(tokens_pnl)} tokens) for {wallet_address[:12]}... on {chain}"
        )
        return result

    except Exception as e:
        logger.warning(f"Moralis PnL error for {wallet_address[:12]}... on {chain}: {e}")
        return {"total_realized_profit_usd": 0.0, "total_count_of_trades": 0, "tokens": []}


# ─────────────────────────────────────────────────────────────────────────────
# 3. Token Balances  (GET /{address}/erc20)  — 5 CU
# ─────────────────────────────────────────────────────────────────────────────
def get_wallet_token_balances(
    wallet_address: str,
    chain: str,
    exclude_spam: bool = True,
) -> list[dict]:
    """
    Get all ERC20 token balances for a wallet (enhanced version of
    the inline function in portfolio_rebalancer.py).

    Returns list of token holdings with parsed balances.
    Cost: 5 CU.
    """
    if not _available() or chain not in CHAIN_HEX:
        return []

    cache_key = f"balances_{chain}_{wallet_address.lower()}"
    if _is_cached(cache_key):
        return _get_cache(cache_key)

    _rate_check()
    try:
        params = {
            "chain": CHAIN_HEX[chain],
            "exclude_spam": str(exclude_spam).lower(),
        }
        resp = requests.get(
            f"{BASE_URL}/{wallet_address}/erc20",
            params=params,
            headers=_headers(),
            timeout=15,
        )
        if resp.status_code in (400, 404):
            return []
        resp.raise_for_status()

        tokens = resp.json()
        results = []
        for t in tokens if isinstance(tokens, list) else []:
            decimals = int(t.get("decimals", 18) or 18)
            raw_balance = int(t.get("balance", "0") or "0")
            balance = raw_balance / (10 ** decimals) if decimals > 0 else raw_balance
            if balance > 0:
                results.append({
                    "address": (t.get("token_address", "") or "").lower(),
                    "symbol": t.get("symbol", "???"),
                    "name": t.get("name", ""),
                    "balance": balance,
                    "decimals": decimals,
                    "logo": t.get("logo", t.get("thumbnail", "")),
                    "usd_price": float(t.get("usd_price", 0) or 0),
                    "usd_value": float(t.get("usd_value", 0) or 0),
                    "possible_spam": t.get("possible_spam", False),
                    "verified_contract": t.get("verified_contract", False),
                    "chain": chain,
                })

        _set_cache(cache_key, results)
        logger.info(
            f"Moralis balances: {len(results)} tokens for {wallet_address[:12]}... on {chain}"
        )
        return results

    except Exception as e:
        logger.warning(f"Moralis balance error for {wallet_address[:12]}... on {chain}: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# 4. Wallet PnL Summary  (GET /wallets/{address}/profitability/summary)  — 30 CU
#    Lightweight alternative to the per-token breakdown (50 CU). Use this when
#    you only need totals, not per-token detail.
# ─────────────────────────────────────────────────────────────────────────────
def get_wallet_pnl_summary(
    wallet_address: str,
    chain: str = "ethereum",
    days: str = "30",
) -> dict:
    """
    Get a lightweight P&L summary for a wallet — total trades, volume,
    realized profit, buy/sell counts. Only 30 CU vs 50 CU for the breakdown.

    Args:
        wallet_address: EVM wallet address
        chain: Chain to query
        days: Lookback period ('all', '7', '30', '60', '90')

    Returns:
        {
            "total_count_of_trades": int,
            "total_trade_volume": float,
            "total_realized_profit_usd": float,
            "total_realized_profit_percentage": float,
            "total_buys": int,
            "total_sells": int,
            "total_bought_volume_usd": float,
            "total_sold_volume_usd": float,
            "win_rate": float,  # derived: sells > buys = net profitable
        }

    Cost: 30 Compute Units per call.
    """
    if not _available() or chain not in CHAIN_HEX:
        return {"total_realized_profit_usd": 0.0, "total_count_of_trades": 0}

    cache_key = f"pnl_summary_{chain}_{wallet_address.lower()}_{days}"
    if _is_cached(cache_key):
        return _get_cache(cache_key)

    _rate_check()
    try:
        resp = requests.get(
            f"{BASE_URL}/wallets/{wallet_address}/profitability/summary",
            params={"chain": CHAIN_HEX[chain], "days": days},
            headers=_headers(),
            timeout=15,
        )
        if resp.status_code in (400, 404):
            return {"total_realized_profit_usd": 0.0, "total_count_of_trades": 0}
        if resp.status_code in (402, 403):
            logger.debug("Moralis PnL summary: plan limitation")
            return {"total_realized_profit_usd": 0.0, "total_count_of_trades": 0}
        resp.raise_for_status()

        data = resp.json()
        total_buys = int(data.get("total_buys", 0) or 0)
        total_sells = int(data.get("total_sells", 0) or 0)

        result = {
            "total_count_of_trades": int(data.get("total_count_of_trades", 0) or 0),
            "total_trade_volume": float(data.get("total_trade_volume", 0) or 0),
            "total_realized_profit_usd": float(data.get("total_realized_profit_usd", 0) or 0),
            "total_realized_profit_percentage": float(data.get("total_realized_profit_percentage", 0) or 0),
            "total_buys": total_buys,
            "total_sells": total_sells,
            "total_bought_volume_usd": float(data.get("total_bought_volume_usd", 0) or 0),
            "total_sold_volume_usd": float(data.get("total_sold_volume_usd", 0) or 0),
            "wallet_address": wallet_address,
            "chain": chain,
            "days": days,
        }
        _set_cache(cache_key, result)
        logger.info(
            f"Moralis PnL summary: ${result['total_realized_profit_usd']:+,.2f} "
            f"({result['total_count_of_trades']} trades) for {wallet_address[:12]}... on {chain}"
        )
        return result

    except Exception as e:
        logger.warning(f"Moralis PnL summary error for {wallet_address[:12]}... on {chain}: {e}")
        return {"total_realized_profit_usd": 0.0, "total_count_of_trades": 0}


# ─────────────────────────────────────────────────────────────────────────────
# 5. Enhanced Token Balances v2  (GET /wallets/{address}/tokens)  — 100 CU
#    Richer than the old /erc20 endpoint: includes USD prices, spam filtering,
#    verified status, portfolio %, and liquidity-based filtering.
# ─────────────────────────────────────────────────────────────────────────────
def get_wallet_token_balances_v2(
    wallet_address: str,
    chain: str,
    exclude_spam: bool = True,
    exclude_unverified: bool = False,
    min_liquidity_usd: float = 0,
    max_token_inactivity_days: int = 0,
) -> list[dict]:
    """
    Enhanced token balances with USD prices, spam/liquidity filtering.
    Uses the newer /wallets/{address}/tokens endpoint (100 CU) which
    returns richer data including portfolio percentages.

    Args:
        wallet_address: EVM wallet address
        chain: Chain to query
        exclude_spam: Filter out known spam tokens
        exclude_unverified: Filter out unverified contracts
        min_liquidity_usd: Minimum single-side liquidity in USD
        max_token_inactivity_days: Exclude tokens inactive > N days (0=disabled)

    Returns list of enriched token holdings.
    Cost: 100 Compute Units per call.
    """
    if not _available() or chain not in CHAIN_HEX:
        return []

    cache_key = f"balances_v2_{chain}_{wallet_address.lower()}_{min_liquidity_usd}"
    if _is_cached(cache_key):
        return _get_cache(cache_key)

    _rate_check()
    try:
        params = {
            "chain": CHAIN_HEX[chain],
            "exclude_spam": str(exclude_spam).lower(),
            "exclude_unverified_contracts": str(exclude_unverified).lower(),
            "exclude_native": "false",
        }
        if min_liquidity_usd > 0:
            params["min_pair_side_liquidity_usd"] = str(min_liquidity_usd)
        if max_token_inactivity_days > 0:
            params["max_token_inactivity"] = str(max_token_inactivity_days)

        resp = requests.get(
            f"{BASE_URL}/wallets/{wallet_address}/tokens",
            params=params,
            headers=_headers(),
            timeout=20,
        )
        if resp.status_code in (400, 404):
            return []
        resp.raise_for_status()

        data = resp.json()
        items = data.get("result", data) if isinstance(data, dict) else data
        results = []
        for t in (items if isinstance(items, list) else []):
            balance_formatted = float(t.get("balance_formatted", 0) or 0)
            if balance_formatted <= 0:
                continue
            results.append({
                "address": (t.get("token_address", "") or "").lower(),
                "symbol": t.get("symbol", "???"),
                "name": t.get("name", ""),
                "balance": balance_formatted,
                "decimals": int(t.get("decimals", 18) or 18),
                "logo": t.get("logo", t.get("thumbnail", "")),
                "usd_price": float(t.get("usd_price", 0) or 0),
                "usd_price_24hr_change": float(t.get("usd_price_24hr_percent_change", 0) or 0),
                "usd_value": float(t.get("usd_value", 0) or 0),
                "portfolio_percentage": float(t.get("portfolio_percentage", 0) or 0),
                "possible_spam": t.get("possible_spam", False),
                "verified_contract": t.get("verified_contract", False),
                "native_token": t.get("native_token", False),
                "total_supply": t.get("total_supply_formatted", ""),
                "pct_of_total_supply": float(t.get("percentage_relative_to_total_supply", 0) or 0),
                "chain": chain,
            })

        # Sort by USD value descending
        results.sort(key=lambda x: x.get("usd_value", 0), reverse=True)

        _set_cache(cache_key, results)
        total_usd = sum(r.get("usd_value", 0) for r in results)
        logger.info(
            f"Moralis balances v2: {len(results)} tokens (${total_usd:,.2f}) "
            f"for {wallet_address[:12]}... on {chain}"
        )
        return results

    except Exception as e:
        logger.warning(f"Moralis balances v2 error for {wallet_address[:12]}... on {chain}: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# 6. Wallet Stats  (GET /wallets/{address}/stats)  — 50 CU
#    Quick wallet profiling: total tx count, NFTs, collections, transfers.
#    Used for smart money detection — high tx count = experienced trader.
# ─────────────────────────────────────────────────────────────────────────────
def get_wallet_stats(
    wallet_address: str,
    chain: str = "ethereum",
) -> dict:
    """
    Get quick stats for a wallet — total transactions, NFT counts,
    token transfer counts. Useful for smart money profiling.

    Cost: 50 Compute Units per call.
    """
    if not _available() or chain not in CHAIN_HEX:
        return {"transactions_total": 0}

    cache_key = f"stats_{chain}_{wallet_address.lower()}"
    if _is_cached(cache_key):
        return _get_cache(cache_key)

    _rate_check()
    try:
        resp = requests.get(
            f"{BASE_URL}/wallets/{wallet_address}/stats",
            params={"chain": CHAIN_HEX[chain]},
            headers=_headers(),
            timeout=10,
        )
        if resp.status_code in (400, 404):
            return {"transactions_total": 0}
        if resp.status_code in (402, 403):
            return {"transactions_total": 0}
        resp.raise_for_status()

        data = resp.json()
        result = {
            "nfts": int(data.get("nfts", 0) or 0),
            "collections": int(data.get("collections", 0) or 0),
            "transactions_total": int(
                (data.get("transactions") or {}).get("total", 0) or 0
            ),
            "nft_transfers_total": int(
                (data.get("nft_transfers") or {}).get("total", 0) or 0
            ),
            "token_transfers_total": int(
                (data.get("token_transfers") or {}).get("total", 0) or 0
            ),
            "wallet_address": wallet_address,
            "chain": chain,
        }
        _set_cache(cache_key, result)
        logger.info(
            f"Moralis wallet stats: {result['transactions_total']} txns, "
            f"{result['token_transfers_total']} token transfers "
            f"for {wallet_address[:12]}... on {chain}"
        )
        return result

    except Exception as e:
        logger.warning(f"Moralis wallet stats error for {wallet_address[:12]}... on {chain}: {e}")
        return {"transactions_total": 0}


# ─────────────────────────────────────────────────────────────────────────────
# 7. Enhanced Token Metadata  (GET /erc20/metadata)  — 10 CU
#    Rich metadata: FDV, market cap, categories, social links, spam detection,
#    verification status. Essential for gem scoring enrichment.
# ─────────────────────────────────────────────────────────────────────────────
def get_enhanced_token_metadata(
    token_addresses: list[str],
    chain: str = "ethereum",
) -> list[dict]:
    """
    Get rich metadata for up to 10 tokens in one call.
    Includes FDV, market cap, categories, social links, spam/verified flags.

    Args:
        token_addresses: List of token contract addresses (max 10)
        chain: Chain to query

    Returns list of token metadata dicts with enhanced fields.
    Cost: 10 Compute Units per call (very cheap!).
    """
    if not _available() or chain not in CHAIN_HEX:
        return []
    if not token_addresses:
        return []

    # Limit to 10 per Moralis constraint
    token_addresses = token_addresses[:10]

    # Check cache for all addresses
    cache_key = f"metadata_{chain}_{'_'.join(sorted(a.lower() for a in token_addresses))}"
    if _is_cached(cache_key):
        return _get_cache(cache_key)

    _rate_check()
    try:
        params = [("chain", CHAIN_HEX[chain])]
        for addr in token_addresses:
            params.append(("addresses", addr))

        resp = requests.get(
            f"{BASE_URL}/erc20/metadata",
            params=params,
            headers=_headers(),
            timeout=15,
        )
        if resp.status_code in (400, 404):
            return []
        resp.raise_for_status()

        data = resp.json()
        items = data if isinstance(data, list) else [data]
        results = []
        for t in items:
            links = t.get("links", {}) or {}
            results.append({
                "address": (t.get("address", "") or "").lower(),
                "name": t.get("name", ""),
                "symbol": t.get("symbol", ""),
                "decimals": int(t.get("decimals", 18) or 18),
                "logo": t.get("logo", ""),
                "total_supply": t.get("total_supply_formatted", ""),
                "fdv": float(t.get("fully_diluted_valuation", 0) or 0),
                "market_cap": float(t.get("market_cap", 0) or 0),
                "circulating_supply": t.get("circulating_supply", ""),
                "possible_spam": t.get("possible_spam", False),
                "verified_contract": t.get("verified_contract", False),
                "categories": t.get("categories", []) or [],
                "created_at": t.get("created_at", ""),
                # Social links — useful for assessing project legitimacy
                "twitter": links.get("twitter", ""),
                "website": links.get("website", ""),
                "telegram": links.get("telegram", ""),
                "discord": links.get("discord", ""),
                "github": links.get("github", ""),
                "reddit": links.get("reddit", ""),
                "chain": chain,
            })

        _set_cache(cache_key, results)
        logger.info(
            f"Moralis metadata: {len(results)} tokens enriched on {chain}"
        )
        return results

    except Exception as e:
        logger.warning(f"Moralis metadata error on {chain}: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Aggregate Helpers
# ─────────────────────────────────────────────────────────────────────────────
def get_total_portfolio_value(wallets: dict = None) -> float:
    """
    Get total portfolio value across all configured wallets.
    Uses the net-worth endpoint for efficiency (one call per wallet).
    """
    if not _available():
        return 0.0

    if wallets is None:
        try:
            from config.wallets import WALLETS
            wallets = WALLETS
        except ImportError:
            return 0.0

    total = 0.0
    for wallet_key, wallet in wallets.items():
        try:
            nw = get_wallet_net_worth(wallet.address)
            total += nw.get("total_networth_usd", 0.0)
        except Exception as e:
            logger.debug(f"Net worth failed for {wallet_key}: {e}")

    return max(total, 0.0)


def get_aggregate_pnl(wallets: dict = None, days: int = 30) -> dict:
    """
    Get aggregate P&L across all wallets and chains.
    Returns summary with total profit and per-chain breakdown.
    """
    if not _available():
        return {"total_profit_usd": 0.0, "chains": {}}

    if wallets is None:
        try:
            from config.wallets import WALLETS
            wallets = WALLETS
        except ImportError:
            return {"total_profit_usd": 0.0, "chains": {}}

    total_profit = 0.0
    chain_breakdown = {}

    for wallet_key, wallet in wallets.items():
        for chain in CHAIN_HEX:
            try:
                pnl = get_wallet_pnl(wallet.address, chain, days=days)
                chain_profit = pnl.get("total_realized_profit_usd", 0.0)
                if chain_profit != 0:
                    total_profit += chain_profit
                    if chain not in chain_breakdown:
                        chain_breakdown[chain] = 0.0
                    chain_breakdown[chain] += chain_profit
            except Exception:
                pass

    return {
        "total_profit_usd": total_profit,
        "chains": chain_breakdown,
        "days": days,
    }


def get_usage_stats() -> dict:
    """Return cache stats for monitoring."""
    return {
        "api_key_configured": bool(MORALIS_API_KEY),
        "cached_keys": len(_cache),
        "rate_calls_in_window": _rate_calls_in_window,
    }
