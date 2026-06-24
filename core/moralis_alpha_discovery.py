"""
core/moralis_alpha_discovery.py — Automated Alpha Wallet Discovery Loop

Hunts for highly profitable "Smart Money" wallets by:
1. Identifying trending tokens
2. Extracting top gainers from those tokens
3. Validating the wallets' overall profitability
4. Pushing them to the Moralis Streams manager
"""

import logging
import threading
import time
from typing import Set

from config import settings
from data.providers.moralis_discovery import (
    get_trending_tokens,
    get_top_profitable_wallets,
    get_wallet_profitability_summary
)
from core.moralis_streams_manager import streams_manager

logger = logging.getLogger(__name__)

class AlphaDiscoveryLoop:
    def __init__(self):
        self.enabled = getattr(settings, "ALPHA_DISCOVERY_ENABLED", True)
        self.interval = getattr(settings, "ALPHA_DISCOVERY_INTERVAL", 3600 * 6)  # 6 hours
        self._thread = None
        self._stop_event = threading.Event()
        self._discovered_wallets: Set[str] = set()
        
        # Criteria
        self.min_realized_profit_usd = 50000.0
        self.min_total_trades = 20

    def start(self):
        if not self.enabled:
            return
        if self._thread and self._thread.is_alive():
            return
            
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="AlphaDiscoveryLoop")
        self._thread.start()
        logger.info("AlphaDiscoveryLoop: Started automated alpha wallet discovery daemon.")

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def _loop(self):
        # Run immediately on startup, then loop
        self.run_discovery_cycle()
        
        while not self._stop_event.wait(self.interval):
            self.run_discovery_cycle()

    def run_discovery_cycle(self):
        logger.info("AlphaDiscoveryLoop: Starting discovery cycle...")
        try:
            new_wallets = set()
            
            # 1. Get trending tokens
            trending = get_trending_tokens(chain="eth")
            if not trending:
                logger.warning("AlphaDiscoveryLoop: No trending tokens found.")
                return
                
            # Limit to top 5 trending to conserve CUs, even with Business plan
            for token in trending[:5]:
                token_addr = token.get("token_address")
                if not token_addr:
                    continue
                    
                # 2. Get top gainers for this token
                gainers = get_top_profitable_wallets(token_addr, chain="eth")
                for gainer in gainers[:10]:  # Top 10 gainers per token
                    wallet_addr = gainer.get("wallet_address")
                    if not wallet_addr or wallet_addr in self._discovered_wallets:
                        continue
                        
                    # 3. Validate overall profitability
                    summary = get_wallet_profitability_summary(wallet_address=wallet_addr, chain="eth")
                    if not summary:
                        continue
                        
                    total_pnl = float(summary.get("total_realized_profit_usd", 0) or 0)
                    total_trades = int(summary.get("total_trades", 0) or 0)
                    
                    if total_pnl > self.min_realized_profit_usd and total_trades > self.min_total_trades:
                        logger.info(f"AlphaDiscoveryLoop: 💎 Found Alpha Wallet {wallet_addr} (PnL: ${total_pnl:,.2f}, Trades: {total_trades})")
                        new_wallets.add(wallet_addr)
                        self._discovered_wallets.add(wallet_addr)
            
            # 4. Push to Streams Manager if we found new ones
            if new_wallets:
                logger.info(f"AlphaDiscoveryLoop: Found {len(new_wallets)} new alpha wallets. Injecting into active stream.")
                current_alpha = set(getattr(settings, "SMART_MONEY_WALLETS", []))
                current_alpha.update(new_wallets)
                
                # Update in-memory settings
                settings.SMART_MONEY_WALLETS = list(current_alpha)
                
                # Resync stream
                if streams_manager:
                    streams_manager.sync_alpha_wallets(settings.SMART_MONEY_WALLETS)
                    
        except Exception as e:
            logger.error(f"AlphaDiscoveryLoop: Error during cycle: {e}")

alpha_discovery = AlphaDiscoveryLoop()
