"""
data/providers/moralis_wallet.py — Moralis Pro Wallet Intelligence Provider.

Portfolio-level intelligence:

  1. get_wallet_net_worth(address, chains)       → Total USD value across chains (50 CU)
  2. get_wallet_pnl(address, chain)              → Realized P&L per token (100 CU)
  3. get_wallet_token_balances(address, chain)    → All ERC20 holdings with metadata (5 CU)
  4. get_wallet_pnl_summary(address, chain)      → Light PnL summary: trades, vol, PnL (30 CU)
  5. get_wallet_token_balances_v2(address, chain) → Enriched balances with USD prices (100 CU)
  6. get_wallet_stats(address, chain)            → Quick tx/NFT/transfer counts (50 CU)
  7. get_enhanced_token_metadata(addresses, chain) → Rich metadata incl. FDV/market cap (10 CU)

  ── Sprint 2 additions ─────────────────────────────────────────────────────────
  8. get_wallet_swaps(address, chain)            → DEX swap history + hold-time analysis (50 CU)
  9. get_wallet_insights(address, chain)         → Moralis smart-money intelligence labels (30 CU)

Usage:
  from data.providers.moralis_wallet import get_wallet_net_worth, get_wallet_pnl
  from data.providers.moralis_wallet import get_wallet_swaps, get_wallet_insights

Chain support: ethereum, base, arbitrum, polygon, bsc, avalanche
Rate limited: 25 req/min with 10-minute cache for wallet data.
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
_rate_lock = threading.Lock()


def _headers() -> dict:
    return {"accept": "application/json", "X-API-Key": MORALIS_API_KEY}


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
        resp = get_session().get(
            f"{BASE_URL}/wallets/{wallet_address}/net-worth",
            params=[("chains[]", ch) for ch in chain_hexes]
                + [("exclude_spam", str(exclude_spam).lower()),
                   ("exclude_unverified_contracts", str(exclude_unverified).lower())],
            headers=_headers(),
            timeout=10,
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
        resp = get_session().get(
            f"{BASE_URL}/wallets/{wallet_address}/profitability",
            params=params,
            headers=_headers(),
            timeout=10,
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
        resp = get_session().get(
            f"{BASE_URL}/{wallet_address}/erc20",
            params=params,
            headers=_headers(),
            timeout=8,
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
        resp = get_session().get(
            f"{BASE_URL}/wallets/{wallet_address}/profitability/summary",
            params={"chain": CHAIN_HEX[chain], "days": days},
            headers=_headers(),
            timeout=8,
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

        resp = get_session().get(
            f"{BASE_URL}/wallets/{wallet_address}/tokens",
            params=params,
            headers=_headers(),
            timeout=10,
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
        resp = get_session().get(
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

        resp = get_session().get(
            f"{BASE_URL}/erc20/metadata",
            params=params,
            headers=_headers(),
            timeout=8,
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
# 8. Wallet Swaps  (GET /wallets/{address}/swaps)  — 50 CU            SPRINT 2
#    DEX swap history with exact buy/sell timestamps — critical for:
#      - Avg holding time (fast flippers vs long holders)
#      - Early-entry detection (did they buy within <60min of token launch?)
#      - Per-swap P&L context (pair address + amounts in/out)
# ─────────────────────────────────────────────────────────────────────────────
def get_wallet_swaps(
    wallet_address: str,
    chain: str = "ethereum",
    limit: int = 50,
    order: str = "DESC",
) -> dict:
    """
    Fetch recent DEX swaps for a wallet — used to profile sniper behaviour.

    Args:
        wallet_address: EVM wallet address
        chain: Chain to query
        limit: Max swaps to return (default 50, max 100)
        order: 'DESC' (newest first) or 'ASC'

    Returns:
        {
            "swaps": [
                {
                    "block_timestamp": str,
                    "transaction_hash": str,
                    "exchange_name":    str,  # e.g. "Uniswap v3"
                    "exchange_address": str,
                    "token_sold_address":   str,
                    "token_sold_symbol":    str,
                    "token_sold_amount":    float,
                    "token_sold_usd":       float,
                    "token_bought_address": str,
                    "token_bought_symbol":  str,
                    "token_bought_amount":  float,
                    "token_bought_usd":     float,
                    "pair_address":         str,
                    "is_buy":               bool,   # True = buying a token
                    "direction":            str,    # 'buy' | 'sell'
                }
            ],
            "avg_hold_time_hours": float,   # Derived from matched buy/sell pairs
            "early_entry_rate":    float,   # Fraction that entered <60min of pair creation
            "total_swaps":         int,
            "unique_tokens":       int,
            "buy_count":           int,
            "sell_count":          int,
            "wallet_address":      str,
            "chain":               str,
        }

    Cost: 50 Compute Units per call.
    """
    if not _available() or chain not in CHAIN_HEX:
        return {
            "swaps": [], "avg_hold_time_hours": 0.0, "early_entry_rate": 0.0,
            "total_swaps": 0, "unique_tokens": 0, "buy_count": 0, "sell_count": 0,
            "wallet_address": wallet_address, "chain": chain,
        }

    cache_key = f"swaps_{chain}_{wallet_address.lower()}_{limit}"
    if _is_cached(cache_key):
        return _get_cache(cache_key)

    _rate_check()
    try:
        resp = get_session().get(
            f"{BASE_URL}/wallets/{wallet_address}/swaps",
            params={
                "chain": CHAIN_HEX[chain],
                "limit": min(limit, 100),
                "order": order,
            },
            headers=_headers(),
            timeout=12,
        )
        if resp.status_code in (400, 404):
            logger.debug(f"Moralis swaps: no data for {wallet_address[:12]}...")
            return {
                "swaps": [], "avg_hold_time_hours": 0.0, "early_entry_rate": 0.0,
                "total_swaps": 0, "unique_tokens": 0, "buy_count": 0, "sell_count": 0,
                "wallet_address": wallet_address, "chain": chain,
            }
        if resp.status_code in (402, 403):
            logger.debug("Moralis swaps: plan limitation")
            return {
                "swaps": [], "avg_hold_time_hours": 0.0, "early_entry_rate": 0.0,
                "total_swaps": 0, "unique_tokens": 0, "buy_count": 0, "sell_count": 0,
                "wallet_address": wallet_address, "chain": chain,
            }
        resp.raise_for_status()

        data = resp.json()
        raw_swaps = data.get("result", []) if isinstance(data, dict) else []

        # Parse each swap
        swaps: list[dict] = []
        buy_ts: dict[str, list[float]] = {}   # token_addr → [buy_timestamps]
        sell_ts: dict[str, list[float]] = {}  # token_addr → [sell_timestamps]
        buy_count = 0
        sell_count = 0

        for s in raw_swaps:
            ts_str = s.get("block_timestamp", "")
            tx_hash = s.get("transaction_hash", "")
            pair_addr = (s.get("pair_address") or "").lower()

            # Moralis swap direction: if token_bought is NOT a stablecoin/WETH → it's a BUY
            # We detect buy/sell by checking which token is the "quote" side.
            # Moralis v2.2 returns token_sold / token_bought as the two legs.
            sold_sym   = (s.get("token_sold",   {}) or {}).get("symbol",  "") or s.get("token_sold_symbol", "")
            bought_sym = (s.get("token_bought", {}) or {}).get("symbol",  "") or s.get("token_bought_symbol", "")
            sold_addr   = ((s.get("token_sold",   {}) or {}).get("address", "") or s.get("token_sold_address",   "")).lower()
            bought_addr = ((s.get("token_bought", {}) or {}).get("address", "") or s.get("token_bought_address", "")).lower()

            # Amount helpers — handle string amounts from API
            def _amt(key_nested, key_flat) -> float:
                v = (s.get(key_nested, {}) or {}).get("value", None)
                if v is None:
                    v = s.get(key_flat, 0)
                try:
                    return float(v)
                except (TypeError, ValueError):
                    return 0.0

            sold_usd   = _amt("token_sold",   "token_sold_usd")
            bought_usd = _amt("token_bought", "token_bought_usd")
            sold_amt   = _amt("token_sold",   "token_sold_amount")
            bought_amt = _amt("token_bought", "token_bought_amount")

            _STABLE_SYMS = {"USDC", "USDT", "DAI", "BUSD", "FRAX", "LUSD", "WETH", "ETH", "WBNB", "BNB", "WMATIC", "MATIC", "WAVAX", "AVAX"}
            # If we're spending stables/WETH to buy a non-stable → it's a BUY of that token
            is_buy = sold_sym.upper() in _STABLE_SYMS and bought_sym.upper() not in _STABLE_SYMS
            direction = "buy" if is_buy else "sell"

            # Track timestamps per token for hold-time calculation
            target_addr = bought_addr if is_buy else sold_addr
            if ts_str and target_addr:
                try:
                    from datetime import timezone as _tz
                    from datetime import datetime as _dt
                    ts_epoch = _dt.fromisoformat(ts_str.replace("Z", "+00:00")).timestamp()
                    if is_buy:
                        buy_ts.setdefault(target_addr, []).append(ts_epoch)
                    else:
                        sell_ts.setdefault(target_addr, []).append(ts_epoch)
                except Exception:
                    pass

            if is_buy:
                buy_count += 1
            else:
                sell_count += 1

            exchange_info = s.get("exchange") or {}
            swaps.append({
                "block_timestamp":      ts_str,
                "transaction_hash":     tx_hash,
                "exchange_name":        exchange_info.get("exchange_name",    s.get("exchange_name",    "")),
                "exchange_address":     exchange_info.get("exchange_address", s.get("exchange_address", "")),
                "token_sold_address":   sold_addr,
                "token_sold_symbol":    sold_sym,
                "token_sold_amount":    sold_amt,
                "token_sold_usd":       sold_usd,
                "token_bought_address": bought_addr,
                "token_bought_symbol":  bought_sym,
                "token_bought_amount":  bought_amt,
                "token_bought_usd":     bought_usd,
                "pair_address":         pair_addr,
                "is_buy":               is_buy,
                "direction":            direction,
            })

        # Derive avg holding time from matched buy→sell pairs per token
        hold_times: list[float] = []
        for token_addr, buys in buy_ts.items():
            sells = sell_ts.get(token_addr, [])
            # Pair each earliest buy with the earliest sell that comes after it
            buys_sorted = sorted(buys)
            sells_sorted = sorted(sells)
            for buy_time in buys_sorted:
                for sell_time in sells_sorted:
                    if sell_time > buy_time:
                        hold_times.append((sell_time - buy_time) / 3600.0)  # → hours
                        break

        avg_hold_hours = round(sum(hold_times) / len(hold_times), 2) if hold_times else 0.0
        unique_tokens = len(set(
            s["token_bought_address"] for s in swaps if s["is_buy"]
        ) | set(
            s["token_sold_address"] for s in swaps if not s["is_buy"]
        ) - {""})

        # Early-entry rate: fraction of buy swaps within 60 min of token's first appearance
        # We don't have pair creation time here, but we approximate:
        # if the token was first seen in our swaps list at this timestamp, any buy
        # within 3600s of the FIRST buy of that token = early entry.
        early_entries = 0
        for token_addr, buys in buy_ts.items():
            if buys:
                first_buy = min(buys)
                early_buys = [b for b in buys if b - first_buy <= 3600]
                early_entries += len(early_buys)
        early_entry_rate = round(early_entries / max(buy_count, 1), 3)

        result = {
            "swaps":               swaps,
            "avg_hold_time_hours": avg_hold_hours,
            "early_entry_rate":    early_entry_rate,
            "total_swaps":         len(swaps),
            "unique_tokens":       unique_tokens,
            "buy_count":           buy_count,
            "sell_count":          sell_count,
            "wallet_address":      wallet_address,
            "chain":               chain,
        }
        _set_cache(cache_key, result)
        logger.info(
            f"Moralis swaps: {len(swaps)} swaps ({buy_count}B/{sell_count}S), "
            f"avg_hold={avg_hold_hours:.1f}h, early_entry={early_entry_rate:.0%} "
            f"for {wallet_address[:12]}... on {chain}"
        )
        return result

    except Exception as e:
        logger.warning(f"Moralis swaps error for {wallet_address[:12]}... on {chain}: {e}")
        return {
            "swaps": [], "avg_hold_time_hours": 0.0, "early_entry_rate": 0.0,
            "total_swaps": 0, "unique_tokens": 0, "buy_count": 0, "sell_count": 0,
            "wallet_address": wallet_address, "chain": chain,
        }


# ─────────────────────────────────────────────────────────────────────────────
# 9. Wallet Insights  (GET /wallets/{address}/insights)  — 30 CU       SPRINT 2
#    Moralis smart-money intelligence classifier:
#      - Classifies wallet as: fresh_wallet, rug_trader, sniper, etc.
#      - Provides DeFi experience score (0-100)
#      - Returns activity breakdown: last_seen_days_ago, preferred_dex
#      - Particularly useful as a BOT / MEV filter before scoring
# ─────────────────────────────────────────────────────────────────────────────
def get_wallet_insights(
    wallet_address: str,
    chain: str = "ethereum",
) -> dict:
    """
    Get Moralis smart-money insights for a wallet — their proprietary classifier.

    Args:
        wallet_address: EVM wallet address
        chain: Chain to query

    Returns:
        {
            "is_contract":           bool,
            "is_fresh_wallet":       bool,   # < 30 days old
            "is_suspicious":         bool,   # Flagged for rug/spam activity
            "wallet_age_days":       int,
            "last_active_days_ago":  int,
            "defi_score":            float,  # 0–100, Moralis DeFi experience rating
            "category":              str,    # 'sniper' | 'whale' | 'bot' | 'retail' | ...
            "preferred_dex":         str,    # Which DEX they trade most
            "activity_summary":      dict,   # Breakdown from Moralis
            "wallet_address":        str,
            "chain":                 str,
        }

    Cost: 30 Compute Units per call.
    """
    if not _available() or chain not in CHAIN_HEX:
        return {
            "is_contract": False, "is_fresh_wallet": False, "is_suspicious": False,
            "wallet_age_days": 0, "last_active_days_ago": 0, "defi_score": 0.0,
            "category": "", "preferred_dex": "", "activity_summary": {},
            "wallet_address": wallet_address, "chain": chain,
        }

    cache_key = f"insights_{chain}_{wallet_address.lower()}"
    if _is_cached(cache_key):
        return _get_cache(cache_key)

    _rate_check()
    try:
        resp = get_session().get(
            f"{BASE_URL}/wallets/{wallet_address}/insights",
            params={"chain": CHAIN_HEX[chain], "includeChainBreakdown": "true"},
            headers=_headers(),
            timeout=10,
        )
        if resp.status_code in (400, 404):
            return {
                "is_contract": False, "is_fresh_wallet": False, "is_suspicious": False,
                "wallet_age_days": 0, "last_active_days_ago": 0, "defi_score": 0.0,
                "category": "", "preferred_dex": "", "activity_summary": {},
                "wallet_address": wallet_address, "chain": chain,
            }
        if resp.status_code in (402, 403):
            logger.debug("Moralis wallet insights: plan limitation")
            return {
                "is_contract": False, "is_fresh_wallet": False, "is_suspicious": False,
                "wallet_age_days": 0, "last_active_days_ago": 0, "defi_score": 0.0,
                "category": "", "preferred_dex": "", "activity_summary": {},
                "wallet_address": wallet_address, "chain": chain,
            }
        resp.raise_for_status()

        data = resp.json()

        # Moralis response shape varies — normalize defensively
        # The API may wrap in a top-level key or return flat
        payload = data if isinstance(data, dict) else {}

        # DeFi score: may be nested under 'insights' or at top level
        insights_block = payload.get("insights") or payload
        defi_score = float(
            insights_block.get("defi_score",
                payload.get("defi_score", 0)) or 0
        )

        # Category / classification
        category = (
            insights_block.get("category") or
            payload.get("category") or
            payload.get("wallet_type") or
            ""
        ).lower()

        # Freshness / age
        wallet_age_days = int(
            insights_block.get("wallet_age_days",
                payload.get("wallet_age_days", 0)) or 0
        )
        last_active = int(
            insights_block.get("last_active_days_ago",
                payload.get("last_active_days_ago", 0)) or 0
        )
        is_fresh = wallet_age_days < 30 or bool(
            insights_block.get("is_fresh_wallet", payload.get("is_fresh_wallet", False))
        )
        is_suspicious = bool(
            insights_block.get("is_suspicious", payload.get("is_suspicious", False))
        ) or category in ("rug_trader", "scammer", "spam")
        is_contract = bool(
            payload.get("is_contract", False)
        )

        # Preferred DEX
        preferred_dex = (
            insights_block.get("preferred_dex") or
            payload.get("preferred_dex") or
            ""
        )

        # Full activity breakdown — pass through for debugging
        activity_summary = {
            k: v for k, v in insights_block.items()
            if isinstance(v, (int, float, str, bool))
        }

        # Chain breakdown: per-chain portfolio decomposition (requires includeChainBreakdown=true)
        raw_breakdown = payload.get("chainBreakdown") or payload.get("chain_breakdown") or {}
        chain_breakdown = {}
        if isinstance(raw_breakdown, dict):
            for chn, chn_data in raw_breakdown.items():
                if isinstance(chn_data, dict):
                    chain_breakdown[chn] = {
                        "native_balance_usd": float(chn_data.get("nativeBalanceUsd", chn_data.get("native_balance_usd", 0)) or 0),
                        "token_balance_usd": float(chn_data.get("tokenBalanceUsd", chn_data.get("token_balance_usd", 0)) or 0),
                        "total_usd": float(chn_data.get("totalUsd", chn_data.get("total_usd", 0)) or 0),
                    }
        active_chains_count = len([c for c, v in chain_breakdown.items() if v.get("total_usd", 0) > 0])

        result = {
            "is_contract":          is_contract,
            "is_fresh_wallet":      is_fresh,
            "is_suspicious":        is_suspicious,
            "wallet_age_days":      wallet_age_days,
            "last_active_days_ago": last_active,
            "defi_score":           defi_score,
            "category":             category,
            "preferred_dex":        preferred_dex,
            "activity_summary":     activity_summary,
            "chain_breakdown":      chain_breakdown,
            "active_chains_count":  active_chains_count,
            "wallet_address":       wallet_address,
            "chain":                chain,
        }
        _set_cache(cache_key, result)
        logger.info(
            f"Moralis insights: category='{category}' defi_score={defi_score:.0f} "
            f"age={wallet_age_days}d suspicious={is_suspicious} "
            f"for {wallet_address[:12]}... on {chain}"
        )
        return result

    except Exception as e:
        logger.warning(f"Moralis insights error for {wallet_address[:12]}... on {chain}: {e}")
        return {
            "is_contract": False, "is_fresh_wallet": False, "is_suspicious": False,
            "wallet_age_days": 0, "last_active_days_ago": 0, "defi_score": 0.0,
            "category": "", "preferred_dex": "", "activity_summary": {},
            "wallet_address": wallet_address, "chain": chain,
        }


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
