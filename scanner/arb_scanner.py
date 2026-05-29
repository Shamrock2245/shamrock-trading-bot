"""
scanner/arb_scanner.py — Multi-Strategy Arbitrage Opportunity Scanner

Three arbitrage strategies running in parallel every scan cycle:

STRATEGY 1: Cross-DEX Arbitrage (Blackbird pattern)
  - Same token, same chain, different DEX venues
  - Buy on Uniswap V3, sell on Aerodrome (or vice versa)
  - Minimum spread: 0.8% after fees and gas
  - Typical profit: 0.5–3% per trade
  - Frequency: High — runs on every token in the gem watchlist

STRATEGY 2: Triangular Arbitrage (Drakkar + Peregrine Bellman-Ford pattern)
  - Three-hop cycle: USDC → TokenA → TokenB → USDC
  - Detects negative-weight cycles in the currency graph
  - Uses NetworkX + Bellman-Ford (same algorithm as peregrine/bellmannx.py)
  - Minimum profit: 1.2% after fees (covers 3× gas)
  - Frequency: Medium — runs on top 50 tokens by volume per chain

STRATEGY 3: Cross-Chain Arbitrage (Blackbird long/short pattern adapted for DEX)
  - Same token listed on multiple chains at different prices
  - Buy on cheap chain, bridge + sell on expensive chain
  - Uses Moralis cross-chain price comparison
  - Minimum spread: 2.5% (covers bridge fees ~0.1–0.3% + gas both sides)
  - Frequency: Low — runs every 60s on blue-chip tokens (WETH, USDC, stables)

All opportunities are scored by:
  net_profit_usd = gross_profit - gas_cost - bridge_fee (if applicable)
  Only opportunities with net_profit_usd >= ARB_MIN_PROFIT_USD are returned.
"""
from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from typing import Optional

import networkx as nx

from config import settings
from data.providers.arb_price_feed import (
    CHAIN_IDS,
    STABLECOINS,
    WRAPPED_NATIVE,
    DexPrice,
    build_arb_graph,
    get_cross_chain_prices,
    get_cross_dex_spread,
    get_dexscreener_pairs,
    get_moralis_token_price,
    get_jupiter_price,
    _get_dex_fee,
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Config (overridable via settings.py / .env)
# ─────────────────────────────────────────────────────────────────────────────

ARB_MIN_PROFIT_USD: float = getattr(settings, "ARB_MIN_PROFIT_USD", 8.0)
ARB_MIN_SPREAD_PCT: float = getattr(settings, "ARB_MIN_SPREAD_PCT", 0.8)
ARB_TRIANGULAR_MIN_PROFIT_PCT: float = getattr(settings, "ARB_TRIANGULAR_MIN_PROFIT_PCT", 1.2)
ARB_CROSS_CHAIN_MIN_SPREAD_PCT: float = getattr(settings, "ARB_CROSS_CHAIN_MIN_SPREAD_PCT", 2.5)
ARB_MAX_POSITION_USD: float = getattr(settings, "ARB_MAX_POSITION_USD", 5000.0)
ARB_MIN_LIQUIDITY_USD: float = getattr(settings, "ARB_MIN_LIQUIDITY_USD", 25_000.0)
ARB_GAS_COST_USD: dict[str, float] = {
    "ethereum": 15.0,    # ~$15 per swap on ETH mainnet
    "base":      0.20,   # ~$0.20 on Base (L2)
    "arbitrum":  0.35,   # ~$0.35 on Arbitrum
    "polygon":   0.05,   # ~$0.05 on Polygon
    "bsc":       0.15,   # ~$0.15 on BSC
    "solana":    0.001,  # ~$0.001 on Solana
}
ARB_BRIDGE_FEE_PCT: float = 0.30  # 0.3% typical bridge fee (Stargate, Across)

# Cross-chain token registry: well-known tokens with multi-chain presence
CROSS_CHAIN_TOKENS: list[dict] = [
    {
        "symbol": "WETH",
        "chains": {
            "ethereum": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
            "base":     "0x4200000000000000000000000000000000000006",
            "arbitrum": "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            "polygon":  "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619",
        },
    },
    {
        "symbol": "USDC",
        "chains": {
            "ethereum": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
            "base":     "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
            "arbitrum": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
            "polygon":  "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",
            "bsc":      "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d",
        },
    },
    {
        "symbol": "LINK",
        "chains": {
            "ethereum": "0x514910771AF9Ca656af840dff83E8264EcF986CA",
            "base":     "0x88Fb150BDc53A65fe94Dea0c9BA0a6dAf8C6e196",
            "arbitrum": "0xf97f4df75117a78c1A5a0DBb814Af92458539FB4",
            "polygon":  "0x53E0bca35eC356BD5ddDFebbD1Fc0fD03FaBad39",
        },
    },
    {
        "symbol": "AAVE",
        "chains": {
            "ethereum": "0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9",
            "base":     "0x63706e401c06ac8513145b7687A14804d17f814b",
            "arbitrum": "0xba5DdD1f9d7F570dc94a51479a000E3BCE967196",
            "polygon":  "0xD6DF932A45C0f255f85145f286eA0b292B21C90B",
        },
    },
]

# Active chains for arb scanning
ARB_CHAINS: list[str] = getattr(
    settings, "ARB_CHAINS",
    ["base", "arbitrum", "polygon", "bsc"]  # Exclude ETH mainnet (gas too high for small arb)
)

# ─────────────────────────────────────────────────────────────────────────────
# Data Structures
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ArbOpportunity:
    """A detected arbitrage opportunity ready for execution."""
    strategy: str                    # "cross_dex", "triangular", "cross_chain"
    chain: str
    token_address: str
    token_symbol: str = ""

    # Cross-DEX fields
    buy_dex: str = ""
    buy_price: float = 0.0
    buy_pair: str = ""
    sell_dex: str = ""
    sell_price: float = 0.0
    sell_pair: str = ""

    # Triangular fields
    path: list[str] = field(default_factory=list)   # [USDC, TokenA, TokenB, USDC]
    path_dexes: list[str] = field(default_factory=list)
    cycle_profit_pct: float = 0.0

    # Cross-chain fields
    buy_chain: str = ""
    sell_chain: str = ""
    bridge_fee_usd: float = 0.0

    # Financials
    gross_profit_pct: float = 0.0
    gas_cost_usd: float = 0.0
    net_profit_usd: float = 0.0
    position_size_usd: float = 0.0
    liquidity_usd: float = 0.0

    # Metadata
    confidence: float = 0.0          # 0–1
    detected_at: float = field(default_factory=time.time)
    expires_at: float = 0.0          # Unix timestamp — opportunity window

    @property
    def is_expired(self) -> bool:
        return self.expires_at > 0 and time.time() > self.expires_at

    @property
    def roi_pct(self) -> float:
        if self.position_size_usd <= 0:
            return 0.0
        return self.net_profit_usd / self.position_size_usd * 100

    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy,
            "chain": self.chain,
            "token": self.token_address,
            "symbol": self.token_symbol,
            "buy_dex": self.buy_dex,
            "sell_dex": self.sell_dex,
            "buy_chain": self.buy_chain,
            "sell_chain": self.sell_chain,
            "gross_profit_pct": round(self.gross_profit_pct, 4),
            "gas_cost_usd": round(self.gas_cost_usd, 4),
            "net_profit_usd": round(self.net_profit_usd, 4),
            "position_size_usd": round(self.position_size_usd, 2),
            "roi_pct": round(self.roi_pct, 4),
            "confidence": round(self.confidence, 3),
            "path": self.path,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Strategy 1: Cross-DEX Arbitrage
# ─────────────────────────────────────────────────────────────────────────────

def scan_cross_dex(
    token_address: str,
    chain: str,
    token_symbol: str = "",
) -> Optional[ArbOpportunity]:
    """
    Detect cross-DEX arbitrage: same token, different DEX prices on same chain.
    Blackbird-inspired: find lowest ask (best buy) and highest bid (best sell).

    Returns ArbOpportunity if net profit >= ARB_MIN_PROFIT_USD, else None.
    """
    spread_data = get_cross_dex_spread(token_address, chain)
    spread_pct = spread_data.get("spread_pct", 0.0)

    if spread_pct < ARB_MIN_SPREAD_PCT:
        return None

    buy_price = spread_data.get("best_buy_price", 0.0)
    sell_price = spread_data.get("best_sell_price", 0.0)
    buy_liq = spread_data.get("best_buy_liquidity", 0.0)
    sell_liq = spread_data.get("best_sell_liquidity", 0.0)

    if buy_price <= 0 or sell_price <= 0:
        return None

    # Liquidity gate: need enough depth on both sides
    min_liq = min(buy_liq, sell_liq)
    if min_liq < ARB_MIN_LIQUIDITY_USD:
        return None

    # Position size: limited by min liquidity, capped at ARB_MAX_POSITION_USD
    # Use 2% of pool depth to avoid significant price impact
    position_usd = min(min_liq * 0.02, ARB_MAX_POSITION_USD)
    position_usd = max(position_usd, 100.0)  # minimum $100 trade

    # Fee deduction: buy fee + sell fee
    buy_dex = spread_data.get("best_buy_dex", "unknown")
    sell_dex = spread_data.get("best_sell_dex", "unknown")
    buy_fee = _get_dex_fee(buy_dex)
    sell_fee = _get_dex_fee(sell_dex)
    total_fee_pct = (buy_fee + sell_fee) * 100

    # Gas cost: 2 swaps on the same chain
    gas_cost = ARB_GAS_COST_USD.get(chain, 1.0) * 2

    # Net profit calculation
    gross_profit_pct = spread_pct - total_fee_pct
    gross_profit_usd = position_usd * gross_profit_pct / 100
    net_profit_usd = gross_profit_usd - gas_cost

    if net_profit_usd < ARB_MIN_PROFIT_USD:
        return None

    # Confidence: based on spread size, liquidity depth, and recency
    confidence = min(1.0, (spread_pct / 5.0) * 0.5 + (min(min_liq, 500_000) / 500_000) * 0.5)

    opp = ArbOpportunity(
        strategy="cross_dex",
        chain=chain,
        token_address=token_address,
        token_symbol=token_symbol,
        buy_dex=buy_dex,
        buy_price=buy_price,
        buy_pair=spread_data.get("best_buy_pair", ""),
        sell_dex=sell_dex,
        sell_price=sell_price,
        sell_pair=spread_data.get("best_sell_pair", ""),
        gross_profit_pct=gross_profit_pct,
        gas_cost_usd=gas_cost,
        net_profit_usd=net_profit_usd,
        position_size_usd=position_usd,
        liquidity_usd=min_liq,
        confidence=confidence,
        expires_at=time.time() + 30.0,  # 30-second window
    )

    logger.info(
        f"💱 CROSS-DEX ARB: {token_symbol or token_address[:10]}@{chain} | "
        f"buy={buy_dex}@${buy_price:.6f} sell={sell_dex}@${sell_price:.6f} | "
        f"spread={spread_pct:.2f}% | net=${net_profit_usd:.2f}"
    )
    return opp


# ─────────────────────────────────────────────────────────────────────────────
# Strategy 2: Triangular Arbitrage (Bellman-Ford)
# ─────────────────────────────────────────────────────────────────────────────

def scan_triangular(
    token_list: list[dict],  # [{"address": str, "symbol": str, "price_usd": float, "dex_prices": dict}]
    chain: str,
) -> list[ArbOpportunity]:
    """
    Detect triangular arbitrage opportunities using Bellman-Ford negative cycle detection.
    Adapted from wardbradt/peregrine bellmannx.py and Drakkar-Software/Triangular-Arbitrage detector.py.

    token_list: list of tokens with their prices across DEXes
    Returns list of ArbOpportunity objects sorted by net_profit_usd descending.
    """
    if len(token_list) < 3:
        return []

    # Build price map: {token_address: {dex_name: price_usd}}
    token_prices: dict[str, dict[str, float]] = {}
    for tok in token_list:
        addr = tok.get("address", "")
        if not addr:
            continue
        dex_prices = tok.get("dex_prices", {})
        if not dex_prices and tok.get("price_usd", 0) > 0:
            dex_prices = {"moralis_aggregated": tok["price_usd"]}
        if dex_prices:
            token_prices[addr] = dex_prices

    if len(token_prices) < 3:
        return []

    # Build directed graph with negative log weights
    graph = build_arb_graph(token_prices, chain)
    if graph.number_of_nodes() < 3:
        return []

    opportunities: list[ArbOpportunity] = []
    usdc = STABLECOINS.get(chain, "")

    # Bellman-Ford: find all negative cycles (= profitable triangular paths)
    # Starting from USDC (most liquid base currency)
    source = usdc if usdc in graph else list(graph.nodes())[0]

    try:
        negative_cycles = _find_negative_cycles_bellman_ford(graph, source)
    except Exception as e:
        logger.debug(f"Bellman-Ford error on {chain}: {e}")
        return []

    for cycle, cycle_profit_ratio in negative_cycles:
        if len(cycle) < 3:
            continue

        # cycle_profit_ratio > 1.0 means profitable
        cycle_profit_pct = (cycle_profit_ratio - 1.0) * 100

        if cycle_profit_pct < ARB_TRIANGULAR_MIN_PROFIT_PCT:
            continue

        # Estimate gas: 1 swap per hop in the cycle
        n_hops = len(cycle) - 1
        gas_cost = ARB_GAS_COST_USD.get(chain, 1.0) * n_hops

        # Position size: use $1000 as base for triangular (limited by smallest pool)
        position_usd = min(1000.0, ARB_MAX_POSITION_USD)

        # Net profit
        gross_profit_usd = position_usd * cycle_profit_pct / 100
        net_profit_usd = gross_profit_usd - gas_cost

        if net_profit_usd < ARB_MIN_PROFIT_USD:
            continue

        # Build path labels
        path_labels = []
        for node in cycle:
            # Try to find symbol from token_list
            sym = next((t.get("symbol", node[:8]) for t in token_list if t.get("address") == node), node[:8])
            path_labels.append(sym)

        # Confidence: based on profit margin and path length
        confidence = min(1.0, cycle_profit_pct / 5.0 * 0.7 + (1.0 / n_hops) * 0.3)

        opp = ArbOpportunity(
            strategy="triangular",
            chain=chain,
            token_address=cycle[1] if len(cycle) > 1 else "",
            token_symbol=" → ".join(path_labels),
            path=cycle,
            cycle_profit_pct=cycle_profit_pct,
            gross_profit_pct=cycle_profit_pct,
            gas_cost_usd=gas_cost,
            net_profit_usd=net_profit_usd,
            position_size_usd=position_usd,
            confidence=confidence,
            expires_at=time.time() + 20.0,  # 20-second window (tighter for triangular)
        )
        opportunities.append(opp)

        logger.info(
            f"🔺 TRIANGULAR ARB: {chain} | path={' → '.join(path_labels)} | "
            f"profit={cycle_profit_pct:.2f}% | net=${net_profit_usd:.2f}"
        )

    # Sort by net profit descending
    opportunities.sort(key=lambda o: o.net_profit_usd, reverse=True)
    return opportunities[:5]  # Return top 5 to avoid overloading execution


def _find_negative_cycles_bellman_ford(
    graph: nx.DiGraph,
    source: str,
) -> list[tuple[list[str], float]]:
    """
    Find all negative-weight cycles in graph using Bellman-Ford.
    Returns list of (cycle_path, profit_ratio) tuples.

    Adapted from wardbradt/peregrine NegativeWeightFinder.bellman_ford().
    """
    results: list[tuple[list[str], float]] = []
    nodes = list(graph.nodes())
    n = len(nodes)

    if n == 0:
        return results

    # Initialize distances
    dist = {node: float("inf") for node in nodes}
    pred = {node: None for node in nodes}
    dist[source] = 0.0

    # Relax edges n-1 times
    for _ in range(n - 1):
        for u, v, data in graph.edges(data=True):
            w = data.get("weight", float("inf"))
            if dist[u] + w < dist[v]:
                dist[v] = dist[u] + w
                pred[v] = u

    # Find negative cycles: if we can still relax, there's a negative cycle
    seen_cycles: set[frozenset] = set()
    for u, v, data in graph.edges(data=True):
        w = data.get("weight", float("inf"))
        if dist[u] + w < dist[v]:
            # Retrace the cycle
            cycle = _retrace_cycle(pred, v)
            if cycle is None:
                continue
            cycle_key = frozenset(cycle)
            if cycle_key in seen_cycles:
                continue
            seen_cycles.add(cycle_key)

            # Calculate actual profit ratio along the cycle
            profit_ratio = 1.0
            valid = True
            for i in range(len(cycle) - 1):
                edge_data = graph.get_edge_data(cycle[i], cycle[i + 1])
                if not edge_data:
                    valid = False
                    break
                rate = edge_data.get("rate", 0)
                if rate <= 0:
                    valid = False
                    break
                profit_ratio *= rate

            if valid and profit_ratio > 1.001:  # >0.1% profit minimum
                results.append((cycle, profit_ratio))

    return results


def _retrace_cycle(pred: dict, start: str) -> Optional[list[str]]:
    """Retrace a negative cycle from the predecessor map."""
    visited = {}
    node = start
    for _ in range(len(pred) + 1):
        if node in visited:
            # Found the cycle start
            cycle_start = node
            cycle = [cycle_start]
            current = pred[cycle_start]
            while current != cycle_start and current is not None:
                cycle.append(current)
                current = pred.get(current)
            cycle.append(cycle_start)
            cycle.reverse()
            return cycle
        visited[node] = True
        node = pred.get(node)
        if node is None:
            return None
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Strategy 3: Cross-Chain Arbitrage (Blackbird long/short adapted for DEX)
# ─────────────────────────────────────────────────────────────────────────────

def scan_cross_chain(
    token_info: dict = None,  # Optional single token override
) -> list[ArbOpportunity]:
    """
    Detect cross-chain arbitrage: same token at different prices on different chains.
    Blackbird-inspired: long on cheap chain, short-equivalent on expensive chain.

    For DEX (no shorting): buy on cheap chain, bridge to expensive chain, sell.
    Minimum spread: ARB_CROSS_CHAIN_MIN_SPREAD_PCT (default 2.5%) to cover bridge fees.

    Returns list of ArbOpportunity objects sorted by net_profit_usd descending.
    """
    opportunities: list[ArbOpportunity] = []
    tokens_to_scan = [token_info] if token_info else CROSS_CHAIN_TOKENS

    for token in tokens_to_scan:
        symbol = token.get("symbol", "")
        chain_addresses = token.get("chains", {})

        if len(chain_addresses) < 2:
            continue

        # Fetch prices across all chains simultaneously
        prices = get_cross_chain_prices(symbol, chain_addresses)

        if len(prices) < 2:
            continue

        # Find cheapest and most expensive chain
        sorted_chains = sorted(prices.items(), key=lambda x: x[1])
        cheap_chain, cheap_price = sorted_chains[0]
        expensive_chain, expensive_price = sorted_chains[-1]

        if cheap_price <= 0:
            continue

        spread_pct = (expensive_price - cheap_price) / cheap_price * 100

        if spread_pct < ARB_CROSS_CHAIN_MIN_SPREAD_PCT:
            continue

        # Cost calculation
        gas_buy = ARB_GAS_COST_USD.get(cheap_chain, 1.0)
        gas_sell = ARB_GAS_COST_USD.get(expensive_chain, 1.0)
        bridge_fee_pct = ARB_BRIDGE_FEE_PCT  # 0.3%

        # Position size: conservative for cross-chain (bridge risk)
        position_usd = min(2000.0, ARB_MAX_POSITION_USD * 0.4)

        bridge_fee_usd = position_usd * bridge_fee_pct / 100
        gas_cost_total = gas_buy + gas_sell + 2.0  # +$2 for bridge tx
        total_cost_usd = bridge_fee_usd + gas_cost_total

        gross_profit_usd = position_usd * spread_pct / 100
        net_profit_usd = gross_profit_usd - total_cost_usd

        if net_profit_usd < ARB_MIN_PROFIT_USD * 2:  # Higher bar for cross-chain (more risk)
            continue

        confidence = min(1.0, spread_pct / 10.0 * 0.6 + 0.4)

        opp = ArbOpportunity(
            strategy="cross_chain",
            chain=cheap_chain,
            token_address=chain_addresses.get(cheap_chain, ""),
            token_symbol=symbol,
            buy_chain=cheap_chain,
            buy_price=cheap_price,
            sell_chain=expensive_chain,
            sell_price=expensive_price,
            bridge_fee_usd=bridge_fee_usd,
            gross_profit_pct=spread_pct,
            gas_cost_usd=gas_cost_total,
            net_profit_usd=net_profit_usd,
            position_size_usd=position_usd,
            confidence=confidence,
            expires_at=time.time() + 120.0,  # 2-minute window (bridge takes time)
        )
        opportunities.append(opp)

        logger.info(
            f"🌉 CROSS-CHAIN ARB: {symbol} | "
            f"buy@{cheap_chain}=${cheap_price:.4f} sell@{expensive_chain}=${expensive_price:.4f} | "
            f"spread={spread_pct:.2f}% | net=${net_profit_usd:.2f}"
        )

    opportunities.sort(key=lambda o: o.net_profit_usd, reverse=True)
    return opportunities


# ─────────────────────────────────────────────────────────────────────────────
# Main Scanner — runs all three strategies
# ─────────────────────────────────────────────────────────────────────────────

class ArbScanner:
    """
    Orchestrates all three arbitrage strategies.
    Designed to run as a background daemon alongside the gem scanner.
    """

    def __init__(self):
        self.last_cross_chain_scan: float = 0.0
        self.last_triangular_scan: float = 0.0
        self.scan_count: int = 0
        self.total_opportunities_found: int = 0
        self.total_net_profit_detected_usd: float = 0.0

    def scan_all(
        self,
        watchlist_tokens: list[dict] = None,
        chains: list[str] = None,
    ) -> list[ArbOpportunity]:
        """
        Run all three strategies and return all opportunities sorted by net profit.

        watchlist_tokens: tokens from gem_scanner watchlist (already scored)
        chains: chains to scan (defaults to ARB_CHAINS)
        """
        all_opps: list[ArbOpportunity] = []
        scan_chains = chains or ARB_CHAINS
        tokens = watchlist_tokens or []

        self.scan_count += 1
        t_start = time.time()

        # ── Strategy 1: Cross-DEX (every cycle, on all watchlist tokens) ──
        for tok in tokens:
            addr = tok.get("token_address") or tok.get("address", "")
            chain = tok.get("chain", "base")
            symbol = tok.get("symbol", "")
            if not addr or chain not in scan_chains:
                continue
            opp = scan_cross_dex(addr, chain, symbol)
            if opp:
                all_opps.append(opp)

        # ── Strategy 2: Triangular (every 30s, per chain) ──
        now = time.time()
        if now - self.last_triangular_scan >= 30.0:
            self.last_triangular_scan = now
            for chain in scan_chains:
                # Build token list for this chain from watchlist
                chain_tokens = [
                    t for t in tokens
                    if t.get("chain") == chain and t.get("price_usd", 0) > 0
                ]
                if len(chain_tokens) >= 3:
                    # Enrich with DexScreener multi-DEX prices
                    enriched = _enrich_with_dex_prices(chain_tokens, chain)
                    tri_opps = scan_triangular(enriched, chain)
                    all_opps.extend(tri_opps)

        # ── Strategy 3: Cross-Chain (every 60s, on blue-chip tokens) ──
        if now - self.last_cross_chain_scan >= 60.0:
            self.last_cross_chain_scan = now
            cc_opps = scan_cross_chain()
            all_opps.extend(cc_opps)

        # Sort all by net profit
        all_opps.sort(key=lambda o: o.net_profit_usd, reverse=True)

        # Update stats
        self.total_opportunities_found += len(all_opps)
        self.total_net_profit_detected_usd += sum(o.net_profit_usd for o in all_opps)

        elapsed = time.time() - t_start
        if all_opps:
            logger.info(
                f"🔍 ARB SCAN #{self.scan_count}: {len(all_opps)} opportunities found "
                f"in {elapsed:.2f}s | best=${all_opps[0].net_profit_usd:.2f} "
                f"({all_opps[0].strategy}@{all_opps[0].chain})"
            )

        return all_opps

    def get_stats(self) -> dict:
        return {
            "scan_count": self.scan_count,
            "total_opportunities_found": self.total_opportunities_found,
            "total_net_profit_detected_usd": round(self.total_net_profit_detected_usd, 2),
            "avg_profit_per_scan": round(
                self.total_net_profit_detected_usd / max(self.scan_count, 1), 2
            ),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _enrich_with_dex_prices(
    tokens: list[dict],
    chain: str,
) -> list[dict]:
    """
    Enrich token list with per-DEX prices from DexScreener.
    Adds "dex_prices" field: {dex_name: price_usd}
    """
    enriched = []
    for tok in tokens:
        addr = tok.get("token_address") or tok.get("address", "")
        if not addr:
            enriched.append(tok)
            continue
        dex_prices_list = get_dexscreener_pairs(addr, chain)
        dex_prices_map = {}
        for dp in dex_prices_list:
            if dp.price > 0 and dp.liquidity_usd >= 5000:
                dex_prices_map[dp.dex] = dp.price
        tok_copy = dict(tok)
        tok_copy["dex_prices"] = dex_prices_map
        tok_copy["address"] = addr
        enriched.append(tok_copy)
    return enriched


# Global singleton
_arb_scanner: Optional[ArbScanner] = None


def get_arb_scanner() -> ArbScanner:
    global _arb_scanner
    if _arb_scanner is None:
        _arb_scanner = ArbScanner()
    return _arb_scanner
