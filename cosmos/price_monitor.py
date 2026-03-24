"""
cosmos/price_monitor.py — Multi-DEX price monitor for Cosmos ecosystem.

Polls Osmosis and Astroport for price discrepancies to enable arbitrage.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import requests

from cosmos.cosmos_config import (
    COSMOS_CHAINS,
    OSMOSIS_IBC_DENOMS,
    ARB_SCAN_INTERVAL_SECONDS,
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Price data models
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TokenPrice:
    """Price of a token on a specific DEX."""
    symbol: str
    denom: str
    price_usd: float
    dex: str            # "osmosis", "astroport", "coingecko"
    pool_id: Optional[int] = None
    timestamp: float = 0.0
    volume_24h: float = 0.0
    liquidity_usd: float = 0.0


@dataclass
class PriceSpread:
    """Price spread between two DEXes for the same token."""
    symbol: str
    dex_low: str
    dex_high: str
    price_low: float
    price_high: float
    spread_pct: float
    pool_id_low: Optional[int] = None
    pool_id_high: Optional[int] = None
    timestamp: float = 0.0


class PriceMonitor:
    """
    Monitor token prices across multiple Cosmos DEXes.
    Detects arbitrage opportunities when spreads exceed threshold.
    """
    
    def __init__(self):
        self._session = requests.Session()
        self._price_cache: dict[str, list[TokenPrice]] = {}
        self._last_scan = 0.0
    
    # ── Osmosis prices ───────────────────────────────────────────────────────
    
    def fetch_osmosis_prices(self) -> list[TokenPrice]:
        """Fetch all token prices from Osmosis aggregator API."""
        try:
            resp = self._session.get(
                "https://api-osmosis.imperator.co/tokens/v2/all",
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            
            prices = []
            now = time.time()
            
            for token in data:
                symbol = token.get("symbol", "")
                price = float(token.get("price", 0))
                denom = token.get("denom", "")
                volume = float(token.get("volume_24h", 0))
                liquidity = float(token.get("liquidity", 0))
                
                if symbol and price > 0:
                    prices.append(TokenPrice(
                        symbol=symbol,
                        denom=denom,
                        price_usd=price,
                        dex="osmosis",
                        volume_24h=volume,
                        liquidity_usd=liquidity,
                        timestamp=now,
                    ))
            
            logger.info(f"Fetched {len(prices)} token prices from Osmosis")
            return prices
            
        except Exception as e:
            logger.error(f"Osmosis price fetch failed: {e}")
            return []
    
    # ── Astroport (Neutron) prices ───────────────────────────────────────────
    
    def fetch_astroport_prices(self) -> list[TokenPrice]:
        """Fetch token prices from Astroport on Neutron."""
        try:
            resp = self._session.get(
                "https://app.astroport.fi/api/trpc/charts.prices",
                params={"input": '{"json":{"chainId":"neutron-1"}}'},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            
            prices = []
            now = time.time()
            
            # Parse Astroport's response format
            result = data.get("result", {}).get("data", {}).get("json", [])
            for item in result:
                symbol = item.get("token", "")
                price = float(item.get("priceInUsd", 0))
                
                if symbol and price > 0:
                    prices.append(TokenPrice(
                        symbol=symbol,
                        denom="",
                        price_usd=price,
                        dex="astroport",
                        timestamp=now,
                    ))
            
            logger.info(f"Fetched {len(prices)} token prices from Astroport")
            return prices
            
        except Exception as e:
            logger.debug(f"Astroport price fetch failed: {e}")
            return []
    
    # ── CoinGecko prices (reference) ─────────────────────────────────────────
    
    def fetch_coingecko_prices(self, ids: list[str] = None) -> list[TokenPrice]:
        """Fetch reference prices from CoinGecko."""
        if ids is None:
            ids = ["cosmos", "osmosis", "celestia", "stride"]
        
        try:
            resp = self._session.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={
                    "ids": ",".join(ids),
                    "vs_currencies": "usd",
                    "include_24hr_vol": "true",
                },
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            
            symbol_map = {
                "cosmos": "ATOM",
                "osmosis": "OSMO",
                "celestia": "TIA",
                "stride": "STRD",
            }
            
            prices = []
            now = time.time()
            
            for cg_id, values in data.items():
                symbol = symbol_map.get(cg_id, cg_id.upper())
                price = float(values.get("usd", 0))
                volume = float(values.get("usd_24h_vol", 0))
                
                if price > 0:
                    prices.append(TokenPrice(
                        symbol=symbol,
                        denom="",
                        price_usd=price,
                        dex="coingecko",
                        volume_24h=volume,
                        timestamp=now,
                    ))
            
            return prices
            
        except Exception as e:
            logger.debug(f"CoinGecko price fetch failed: {e}")
            return []
    
    # ── Spread detection ─────────────────────────────────────────────────────
    
    def scan_all_prices(self) -> dict[str, list[TokenPrice]]:
        """Scan all DEXes and group prices by symbol."""
        all_prices = []
        
        # Parallel fetch from all sources
        all_prices.extend(self.fetch_osmosis_prices())
        all_prices.extend(self.fetch_astroport_prices())
        all_prices.extend(self.fetch_coingecko_prices())
        
        # Group by symbol
        by_symbol: dict[str, list[TokenPrice]] = {}
        for p in all_prices:
            key = p.symbol.upper()
            if key not in by_symbol:
                by_symbol[key] = []
            by_symbol[key].append(p)
        
        self._price_cache = by_symbol
        self._last_scan = time.time()
        
        return by_symbol
    
    def find_spreads(self, min_spread_pct: float = 0.3) -> list[PriceSpread]:
        """
        Find tokens with price spreads between DEXes exceeding threshold.
        
        Returns list of PriceSpread objects sorted by spread (highest first).
        """
        if not self._price_cache:
            self.scan_all_prices()
        
        spreads = []
        
        for symbol, prices in self._price_cache.items():
            # Need at least 2 DEX prices to compare
            dex_prices = [p for p in prices if p.dex != "coingecko"]
            if len(dex_prices) < 2:
                continue
            
            # Find min and max prices
            sorted_prices = sorted(dex_prices, key=lambda p: p.price_usd)
            low = sorted_prices[0]
            high = sorted_prices[-1]
            
            if low.price_usd <= 0:
                continue
            
            spread_pct = ((high.price_usd - low.price_usd) / low.price_usd) * 100
            
            if spread_pct >= min_spread_pct:
                spreads.append(PriceSpread(
                    symbol=symbol,
                    dex_low=low.dex,
                    dex_high=high.dex,
                    price_low=low.price_usd,
                    price_high=high.price_usd,
                    spread_pct=spread_pct,
                    pool_id_low=low.pool_id,
                    pool_id_high=high.pool_id,
                    timestamp=time.time(),
                ))
        
        # Sort by spread descending
        spreads.sort(key=lambda s: s.spread_pct, reverse=True)
        return spreads
    
    def get_price(self, symbol: str, dex: str = "osmosis") -> float:
        """Get the latest price for a symbol from a specific DEX."""
        prices = self._price_cache.get(symbol.upper(), [])
        for p in prices:
            if p.dex == dex:
                return p.price_usd
        return 0.0
