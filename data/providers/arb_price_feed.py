"""
data/providers/arb_price_feed.py — Unified Multi-DEX Real-Time Price Feed for Arbitrage

Aggregates live bid/ask prices across all DEXes and chains simultaneously.
Inspired by:
  - wardbradt/peregrine: async multi-exchange price fetching + Bellman-Ford graph
  - Drakkar-Software/Triangular-Arbitrage: NetworkX directed graph of currency pairs
  - webpolis/blackbird: bid/ask spread tracking between venues

Price Sources (in priority order per chain):
  1. Moralis pair stats (get_pair_stats) — most accurate, includes buy/sell pressure
  2. 1inch quote API — best execution price including all DEX aggregation
  3. DexScreener pair data — fallback, 30s cache
  4. Moralis token price — last resort

Supported DEX Venues per Chain:
  ethereum:  Uniswap V2, Uniswap V3, Curve, Balancer, 1inch aggregated
  base:      Uniswap V3, Aerodrome, BaseSwap, 1inch aggregated
  arbitrum:  Uniswap V3, Camelot, Balancer, 1inch aggregated
  polygon:   Uniswap V3, QuickSwap, SushiSwap, 1inch aggregated
  bsc:       PancakeSwap V3, BiSwap, 1inch aggregated
  solana:    Jupiter V6 (aggregates Raydium, Orca, Meteora, Phoenix)

CU Cost: ~5 CU per pair per DEX (Moralis pair stats)
         ~0 CU for 1inch (external API, not Moralis)
         ~0 CU for DexScreener (external API, not Moralis)
"""
from __future__ import annotations

import asyncio
import logging
import math
import time
from dataclasses import dataclass, field
from typing import Optional

import aiohttp
import networkx as nx

from config import settings
from data.http_session import get_session

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

MORALIS_API_KEY: str = getattr(settings, "MORALIS_API_KEY", "")
MORALIS_BASE = "https://deep-index.moralis.io/api/v2.2"
ONEINCH_BASE = "https://api.1inch.dev/swap/v6.0"
DEXSCREENER_BASE = "https://api.dexscreener.com/latest/dex"
JUPITER_PRICE_URL = "https://price.jup.ag/v6/price"

# EVM chain ID map for 1inch
CHAIN_IDS: dict[str, int] = {
    "ethereum": 1,
    "base": 8453,
    "arbitrum": 42161,
    "polygon": 137,
    "bsc": 56,
}

# Moralis chain hex map
MORALIS_CHAIN: dict[str, str] = {
    "ethereum": "0x1",
    "base": "0x2105",
    "arbitrum": "0xa4b1",
    "polygon": "0x89",
    "bsc": "0x38",
}

# Well-known stablecoins per chain (used as triangular arb base currency)
STABLECOINS: dict[str, str] = {
    "ethereum": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",   # USDC
    "base":     "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",   # USDC on Base
    "arbitrum": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",   # USDC on Arb
    "polygon":  "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",   # USDC on Polygon
    "bsc":      "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d",   # USDC on BSC
}

# WETH / wrapped native per chain
WRAPPED_NATIVE: dict[str, str] = {
    "ethereum": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
    "base":     "0x4200000000000000000000000000000000000006",
    "arbitrum": "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
    "polygon":  "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270",  # WMATIC
    "bsc":      "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",  # WBNB
}

# Price cache: key → (price, timestamp)
_price_cache: dict[str, tuple[float, float]] = {}
_PRICE_CACHE_TTL = 8.0   # 8 seconds — arb windows are short

# ─────────────────────────────────────────────────────────────────────────────
# Data Structures
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DexPrice:
    """Price quote from a single DEX venue."""
    dex: str                        # e.g. "uniswap_v3", "aerodrome", "1inch"
    chain: str
    token_in: str                   # address
    token_out: str                  # address
    token_in_symbol: str = ""
    token_out_symbol: str = ""
    price: float = 0.0              # token_out per token_in
    price_impact_pct: float = 0.0   # slippage estimate
    liquidity_usd: float = 0.0
    buy_pressure: float = 0.5       # 0–1
    pair_address: str = ""
    source: str = "unknown"         # "moralis", "1inch", "dexscreener"
    timestamp: float = field(default_factory=time.time)

    @property
    def is_stale(self) -> bool:
        return (time.time() - self.timestamp) > _PRICE_CACHE_TTL

    @property
    def log_weight(self) -> float:
        """Negative log price for Bellman-Ford graph (Peregrine pattern)."""
        if self.price <= 0:
            return float("inf")
        return -math.log(self.price)


@dataclass
class ArbPriceSurface:
    """Complete price surface for a token across all DEXes on a chain."""
    token_address: str
    chain: str
    symbol: str = ""
    prices: list[DexPrice] = field(default_factory=list)
    best_bid: float = 0.0    # highest price any DEX will buy at
    best_ask: float = 0.0    # lowest price any DEX will sell at
    spread_pct: float = 0.0  # (best_bid - best_ask) / best_ask * 100
    timestamp: float = field(default_factory=time.time)

    def update_best(self) -> None:
        if not self.prices:
            return
        valid = [p for p in self.prices if p.price > 0]
        if not valid:
            return
        self.best_bid = max(p.price for p in valid)
        self.best_ask = min(p.price for p in valid)
        if self.best_ask > 0:
            self.spread_pct = (self.best_bid - self.best_ask) / self.best_ask * 100


# ─────────────────────────────────────────────────────────────────────────────
# Moralis Price Feed
# ─────────────────────────────────────────────────────────────────────────────

def _moralis_headers() -> dict:
    return {"accept": "application/json", "X-API-Key": MORALIS_API_KEY}


def get_moralis_pair_price(
    pair_address: str,
    chain: str,
    dex_name: str = "unknown",
) -> Optional[DexPrice]:
    """
    Fetch live price from a Moralis pair address.
    Returns DexPrice with price, liquidity, buy_pressure.
    CU cost: ~5 per call (cached 8s).
    """
    if not MORALIS_API_KEY or chain not in MORALIS_CHAIN:
        return None

    cache_key = f"arb_pair_{chain}_{pair_address.lower()}"
    cached = _price_cache.get(cache_key)
    if cached and (time.time() - cached[1]) < _PRICE_CACHE_TTL:
        return cached[0]

    try:
        resp = get_session().get(
            f"{MORALIS_BASE}/pairs/{pair_address}/stats",
            params={"chain": MORALIS_CHAIN[chain]},
            headers=_moralis_headers(),
            timeout=5,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        stats = data[0] if isinstance(data, list) and data else data

        def _f(key: str, tf: str = "5m") -> float:
            v = stats.get(key, {})
            if isinstance(v, dict):
                return float(v.get(tf, 0) or 0)
            return float(v or 0)

        price = float(stats.get("priceUsd") or stats.get("price_usd") or 0)
        liq = float(stats.get("liquidityUsd") or stats.get("total_liquidity_usd") or 0)
        buys_5m = _f("buyers", "5m")
        sells_5m = _f("sellers", "5m")
        buy_pressure = buys_5m / max(buys_5m + sells_5m, 1)

        dp = DexPrice(
            dex=dex_name,
            chain=chain,
            token_in=STABLECOINS.get(chain, ""),
            token_out=pair_address,
            price=price,
            liquidity_usd=liq,
            buy_pressure=buy_pressure,
            pair_address=pair_address,
            source="moralis",
        )
        _price_cache[cache_key] = (dp, time.time())
        return dp
    except Exception as e:
        logger.debug(f"Moralis pair price error {pair_address[:10]}@{chain}: {e}")
        return None


def get_moralis_token_price(
    token_address: str,
    chain: str,
) -> Optional[float]:
    """
    Fetch token price in USD from Moralis token price endpoint.
    CU cost: 1 per call.
    """
    if not MORALIS_API_KEY or chain not in MORALIS_CHAIN:
        return None

    cache_key = f"arb_tokprice_{chain}_{token_address.lower()}"
    cached = _price_cache.get(cache_key)
    if cached and (time.time() - cached[1]) < _PRICE_CACHE_TTL:
        return cached[0]

    try:
        resp = get_session().get(
            f"{MORALIS_BASE}/erc20/{token_address}/price",
            params={"chain": MORALIS_CHAIN[chain], "include": "percent_change"},
            headers=_moralis_headers(),
            timeout=5,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        price = float(data.get("usdPrice") or data.get("usd_price") or 0)
        _price_cache[cache_key] = (price, time.time())
        return price if price > 0 else None
    except Exception as e:
        logger.debug(f"Moralis token price error {token_address[:10]}@{chain}: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 1inch Price Feed (free, no Moralis CU cost)
# ─────────────────────────────────────────────────────────────────────────────

def get_1inch_quote(
    chain: str,
    token_in: str,
    token_out: str,
    amount_usd: float = 1000.0,
) -> Optional[DexPrice]:
    """
    Get best execution price from 1inch aggregator.
    1inch aggregates Uniswap, Curve, Balancer, etc. in one call.
    No Moralis CU cost — uses 1inch API directly.
    """
    chain_id = CHAIN_IDS.get(chain)
    api_key = getattr(settings, "ONEINCH_API_KEY", "")
    if not chain_id or not api_key:
        return None

    cache_key = f"arb_1inch_{chain}_{token_in[:8]}_{token_out[:8]}"
    cached = _price_cache.get(cache_key)
    if cached and (time.time() - cached[1]) < _PRICE_CACHE_TTL:
        return cached[0]

    # Convert USD amount to token_in amount (use USDC = 6 decimals)
    amount_wei = int(amount_usd * 1e6)  # USDC has 6 decimals

    try:
        resp = get_session().get(
            f"{ONEINCH_BASE}/{chain_id}/quote",
            params={
                "src": token_in,
                "dst": token_out,
                "amount": str(amount_wei),
                "includeProtocols": "true",
                "includeGas": "true",
            },
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=8,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()

        dst_amount = float(data.get("dstAmount") or data.get("toAmount") or 0)
        if dst_amount <= 0:
            return None

        # Price = dst_amount (in token_out decimals) / amount_wei (in token_in decimals)
        # Normalize: assume token_out has 18 decimals (adjust per token if needed)
        price = (dst_amount / 1e18) / (amount_usd)  # token_out per USD

        gas_estimate = float(data.get("gas") or data.get("estimatedGas") or 200000)

        dp = DexPrice(
            dex="1inch_aggregated",
            chain=chain,
            token_in=token_in,
            token_out=token_out,
            price=price,
            price_impact_pct=0.0,  # 1inch already accounts for this
            source="1inch",
        )
        _price_cache[cache_key] = (dp, time.time())
        return dp
    except Exception as e:
        logger.debug(f"1inch quote error {chain} {token_in[:8]}→{token_out[:8]}: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# DexScreener Price Feed (free fallback, no CU cost)
# ─────────────────────────────────────────────────────────────────────────────

def get_dexscreener_pairs(
    token_address: str,
    chain: str,
) -> list[DexPrice]:
    """
    Fetch all DEX pairs for a token from DexScreener.
    Returns multiple DexPrice objects — one per DEX listing.
    No Moralis CU cost.
    """
    cache_key = f"arb_dex_{chain}_{token_address.lower()}"
    cached = _price_cache.get(cache_key)
    if cached and (time.time() - cached[1]) < 15.0:  # 15s cache for DexScreener
        return cached[0]

    results: list[DexPrice] = []
    try:
        resp = get_session().get(
            f"{DEXSCREENER_BASE}/tokens/{token_address}",
            timeout=8,
        )
        if resp.status_code != 200:
            return results
        data = resp.json()
        pairs = data.get("pairs") or []

        for pair in pairs:
            if pair.get("chainId", "").lower() != _dex_chain_id(chain):
                continue
            price_usd = float(pair.get("priceUsd") or 0)
            if price_usd <= 0:
                continue
            liq = float((pair.get("liquidity") or {}).get("usd") or 0)
            dex_id = pair.get("dexId", "unknown")
            pair_addr = pair.get("pairAddress", "")

            dp = DexPrice(
                dex=dex_id,
                chain=chain,
                token_in=STABLECOINS.get(chain, ""),
                token_out=token_address,
                price=price_usd,
                liquidity_usd=liq,
                pair_address=pair_addr,
                source="dexscreener",
            )
            results.append(dp)

        _price_cache[cache_key] = (results, time.time())
    except Exception as e:
        logger.debug(f"DexScreener pairs error {token_address[:10]}@{chain}: {e}")
    return results


def _dex_chain_id(chain: str) -> str:
    """Map internal chain name to DexScreener chainId string."""
    mapping = {
        "ethereum": "ethereum",
        "base": "base",
        "arbitrum": "arbitrum",
        "polygon": "polygon",
        "bsc": "bsc",
        "solana": "solana",
    }
    return mapping.get(chain, chain)


# ─────────────────────────────────────────────────────────────────────────────
# Jupiter Price Feed (Solana)
# ─────────────────────────────────────────────────────────────────────────────

def get_jupiter_price(
    token_mint: str,
    vs_token: str = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
) -> Optional[DexPrice]:
    """
    Fetch Solana token price from Jupiter Price API V6.
    Aggregates Raydium, Orca, Meteora, Phoenix — best price across all.
    No Moralis CU cost.
    """
    cache_key = f"arb_jup_{token_mint[:12]}"
    cached = _price_cache.get(cache_key)
    if cached and (time.time() - cached[1]) < _PRICE_CACHE_TTL:
        return cached[0]

    try:
        resp = get_session().get(
            JUPITER_PRICE_URL,
            params={"ids": token_mint, "vsToken": vs_token},
            timeout=6,
        )
        if resp.status_code != 200:
            return None
        data = resp.json().get("data", {}).get(token_mint, {})
        price = float(data.get("price") or 0)
        if price <= 0:
            return None

        dp = DexPrice(
            dex="jupiter_v6",
            chain="solana",
            token_in=vs_token,
            token_out=token_mint,
            price=price,
            source="jupiter",
        )
        _price_cache[cache_key] = (dp, time.time())
        return dp
    except Exception as e:
        logger.debug(f"Jupiter price error {token_mint[:12]}: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Async Batch Price Fetcher (Peregrine-style parallel fetching)
# ─────────────────────────────────────────────────────────────────────────────

async def _fetch_dexscreener_async(
    session: aiohttp.ClientSession,
    token_address: str,
    chain: str,
) -> list[DexPrice]:
    """Async DexScreener fetch for batch operations."""
    results: list[DexPrice] = []
    try:
        async with session.get(
            f"{DEXSCREENER_BASE}/tokens/{token_address}",
            timeout=aiohttp.ClientTimeout(total=8),
        ) as resp:
            if resp.status != 200:
                return results
            data = await resp.json()
            for pair in (data.get("pairs") or []):
                if pair.get("chainId", "").lower() != _dex_chain_id(chain):
                    continue
                price_usd = float(pair.get("priceUsd") or 0)
                if price_usd <= 0:
                    continue
                liq = float((pair.get("liquidity") or {}).get("usd") or 0)
                results.append(DexPrice(
                    dex=pair.get("dexId", "unknown"),
                    chain=chain,
                    token_in=STABLECOINS.get(chain, ""),
                    token_out=token_address,
                    price=price_usd,
                    liquidity_usd=liq,
                    pair_address=pair.get("pairAddress", ""),
                    source="dexscreener",
                ))
    except Exception as e:
        logger.debug(f"Async DexScreener error {token_address[:10]}@{chain}: {e}")
    return results


async def fetch_price_surface_async(
    token_address: str,
    chain: str,
    symbol: str = "",
) -> ArbPriceSurface:
    """
    Fetch complete price surface for a token across all DEXes asynchronously.
    Combines Moralis (primary) + DexScreener (multi-DEX breakdown).
    """
    surface = ArbPriceSurface(
        token_address=token_address,
        chain=chain,
        symbol=symbol,
    )

    # Moralis token price (primary, 1 CU)
    moralis_price = get_moralis_token_price(token_address, chain)
    if moralis_price and moralis_price > 0:
        surface.prices.append(DexPrice(
            dex="moralis_aggregated",
            chain=chain,
            token_in=STABLECOINS.get(chain, ""),
            token_out=token_address,
            price=moralis_price,
            source="moralis",
        ))

    # DexScreener multi-DEX breakdown (async, free)
    async with aiohttp.ClientSession() as session:
        dex_prices = await _fetch_dexscreener_async(session, token_address, chain)
        surface.prices.extend(dex_prices)

    surface.update_best()
    return surface


def fetch_price_surface(
    token_address: str,
    chain: str,
    symbol: str = "",
) -> ArbPriceSurface:
    """Synchronous wrapper for fetch_price_surface_async."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Already in async context — use thread executor
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(
                    asyncio.run,
                    fetch_price_surface_async(token_address, chain, symbol)
                )
                return future.result(timeout=15)
        else:
            return loop.run_until_complete(
                fetch_price_surface_async(token_address, chain, symbol)
            )
    except Exception as e:
        logger.debug(f"fetch_price_surface error {token_address[:10]}@{chain}: {e}")
        return ArbPriceSurface(token_address=token_address, chain=chain, symbol=symbol)


# ─────────────────────────────────────────────────────────────────────────────
# Triangular Arbitrage Graph Builder (Drakkar + Peregrine pattern)
# ─────────────────────────────────────────────────────────────────────────────

def build_arb_graph(
    token_prices: dict[str, dict[str, float]],
    chain: str,
) -> nx.DiGraph:
    """
    Build a directed weighted graph for Bellman-Ford negative cycle detection.

    token_prices: {token_address: {dex_name: price_in_usd}}

    Graph edges: token_A → token_B with weight = -log(exchange_rate)
    A negative cycle in this graph = profitable triangular arbitrage.

    Adapted from wardbradt/peregrine bellmannx.py.
    """
    graph = nx.DiGraph()
    usdc = STABLECOINS.get(chain, "USDC")
    weth = WRAPPED_NATIVE.get(chain, "WETH")

    # Add USDC→token and token→USDC edges for each token
    for token_addr, dex_prices in token_prices.items():
        for dex, price_usd in dex_prices.items():
            if price_usd <= 0:
                continue
            # USDC → token: 1 USDC buys (1/price) tokens
            rate_buy = 1.0 / price_usd
            # token → USDC: 1 token sells for price USDC
            rate_sell = price_usd

            # Apply 0.3% DEX fee (standard Uniswap V3 pool fee)
            fee = _get_dex_fee(dex)
            rate_buy_net = rate_buy * (1 - fee)
            rate_sell_net = rate_sell * (1 - fee)

            # Bellman-Ford uses negative log weights
            w_buy = -math.log(rate_buy_net) if rate_buy_net > 0 else float("inf")
            w_sell = -math.log(rate_sell_net) if rate_sell_net > 0 else float("inf")

            edge_key = f"{dex}:{chain}"
            graph.add_edge(usdc, token_addr, weight=w_buy, dex=dex, chain=chain, rate=rate_buy_net)
            graph.add_edge(token_addr, usdc, weight=w_sell, dex=dex, chain=chain, rate=rate_sell_net)

            # Also add WETH ↔ token edges if we have WETH price
            if weth in token_prices and dex in token_prices[weth]:
                weth_price = token_prices[weth][dex]
                if weth_price > 0 and price_usd > 0:
                    # token → WETH rate
                    rate_tok_weth = (price_usd / weth_price) * (1 - fee)
                    rate_weth_tok = (weth_price / price_usd) * (1 - fee)
                    if rate_tok_weth > 0:
                        graph.add_edge(token_addr, weth,
                                       weight=-math.log(rate_tok_weth), dex=dex, chain=chain, rate=rate_tok_weth)
                    if rate_weth_tok > 0:
                        graph.add_edge(weth, token_addr,
                                       weight=-math.log(rate_weth_tok), dex=dex, chain=chain, rate=rate_weth_tok)

    return graph


def _get_dex_fee(dex: str) -> float:
    """Return standard fee for a DEX (as decimal, e.g. 0.003 = 0.3%)."""
    fee_map = {
        "uniswap_v3": 0.0005,       # 0.05% (most liquid pools)
        "uniswap_v2": 0.003,
        "aerodrome": 0.0005,
        "camelot": 0.003,
        "quickswap": 0.003,
        "pancakeswap": 0.0025,
        "curve": 0.0004,
        "balancer": 0.002,
        "1inch_aggregated": 0.001,  # avg across aggregated pools
        "jupiter_v6": 0.0025,
        "raydium": 0.0025,
        "orca": 0.003,
    }
    for key in fee_map:
        if key in dex.lower():
            return fee_map[key]
    return 0.003  # default 0.3%


# ─────────────────────────────────────────────────────────────────────────────
# Cross-Chain Price Comparison
# ─────────────────────────────────────────────────────────────────────────────

def get_cross_chain_prices(
    token_symbol: str,
    token_addresses: dict[str, str],  # {chain: address}
) -> dict[str, float]:
    """
    Fetch the same token's price across multiple chains simultaneously.
    Used for cross-chain arbitrage detection.

    Returns {chain: price_usd}
    """
    prices: dict[str, float] = {}
    for chain, address in token_addresses.items():
        if chain == "solana":
            dp = get_jupiter_price(address)
            if dp:
                prices[chain] = dp.price
        else:
            price = get_moralis_token_price(address, chain)
            if price:
                prices[chain] = price
            else:
                # DexScreener fallback
                dex_prices = get_dexscreener_pairs(address, chain)
                if dex_prices:
                    # Use highest-liquidity pair
                    best = max(dex_prices, key=lambda p: p.liquidity_usd)
                    prices[chain] = best.price

    return prices


def get_cross_dex_spread(
    token_address: str,
    chain: str,
) -> dict:
    """
    Find the best buy price and best sell price for a token across all DEXes on one chain.
    Returns spread data for cross-DEX arbitrage.

    Blackbird-inspired: find lowest ask + highest bid across venues.
    """
    dex_prices = get_dexscreener_pairs(token_address, chain)
    if not dex_prices:
        return {"spread_pct": 0.0, "best_buy_dex": None, "best_sell_dex": None}

    # Filter by minimum liquidity ($10k)
    liquid = [p for p in dex_prices if p.liquidity_usd >= 10_000]
    if len(liquid) < 2:
        return {"spread_pct": 0.0, "best_buy_dex": None, "best_sell_dex": None}

    # Lowest ask = best place to buy (lowest price)
    best_buy = min(liquid, key=lambda p: p.price)
    # Highest bid = best place to sell (highest price)
    best_sell = max(liquid, key=lambda p: p.price)

    if best_buy.price <= 0:
        return {"spread_pct": 0.0, "best_buy_dex": None, "best_sell_dex": None}

    spread_pct = (best_sell.price - best_buy.price) / best_buy.price * 100

    return {
        "spread_pct": spread_pct,
        "best_buy_dex": best_buy.dex,
        "best_buy_price": best_buy.price,
        "best_buy_pair": best_buy.pair_address,
        "best_buy_liquidity": best_buy.liquidity_usd,
        "best_sell_dex": best_sell.dex,
        "best_sell_price": best_sell.price,
        "best_sell_pair": best_sell.pair_address,
        "best_sell_liquidity": best_sell.liquidity_usd,
        "token_address": token_address,
        "chain": chain,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Cache Management
# ─────────────────────────────────────────────────────────────────────────────

def clear_stale_cache() -> int:
    """Remove expired entries from the price cache. Returns count removed."""
    now = time.time()
    stale_keys = [k for k, (_, ts) in _price_cache.items() if (now - ts) > 60]
    for k in stale_keys:
        del _price_cache[k]
    return len(stale_keys)


def get_cache_stats() -> dict:
    return {
        "entries": len(_price_cache),
        "cache_ttl_seconds": _PRICE_CACHE_TTL,
    }
