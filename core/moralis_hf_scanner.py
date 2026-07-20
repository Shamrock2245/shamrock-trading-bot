"""
core/moralis_hf_scanner.py — High-Frequency Moralis Alpha Scanner

Extends moralis_alpha_discovery.py with aggressive, high-frequency token hunting:
1. Scans for tokens with >50% volume spike in 1h
2. Filters by liquidity thresholds ($100k+)
3. Detects narrative alignment (Memes, AI, DePIN, etc.)
4. Feeds high-confidence signals to the Hyperliquid executor

This module runs every 5-15 minutes to catch early alpha before the market.
"""

import logging
import threading
import time
from typing import List, Dict, Optional
from datetime import datetime

from config import settings

logger = logging.getLogger(__name__)

class HighFrequencyMoralisScanner:
    def __init__(self):
        self.enabled = getattr(settings, "HF_MORALIS_SCANNER_ENABLED", True)
        self.interval = getattr(settings, "HF_SCANNER_INTERVAL", 300)  # 5 minutes
        self._thread = None
        self._stop_event = threading.Event()
        self._last_scan_time = None
        
        # Thresholds
        self.min_liquidity_usd = 100000.0  # $100k minimum
        self.min_volume_spike_pct = 50.0  # 50% volume increase in 1h
        self.min_holders = 50  # At least 50 holders
        
        # Trending narratives for 2026
        self.trending_narratives = {
            "memes": ["BONK", "DOGE", "SHIB", "PEPE", "BRETT", "FARTCOIN"],
            "ai": ["BITTENSOR", "RNDR", "KAITO", "VIRTUAL", "GROK"],
            "depin": ["RNDR", "DIONE", "GRASS", "RENDER"],
            "hyperliquid": ["HYPE"],
            "prediction": ["RESOLV", "ONDO"],
        }

    def start(self):
        if not self.enabled:
            logger.info("HF Moralis Scanner: Disabled via config.")
            return
        if self._thread and self._thread.is_alive():
            return
            
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="HFMoralisScanner")
        self._thread.start()
        logger.info("HF Moralis Scanner: Started high-frequency alpha hunting daemon.")

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def _loop(self):
        while not self._stop_event.wait(self.interval):
            try:
                self.scan_for_alpha()
            except Exception as e:
                logger.error(f"HF Moralis Scanner: Error during scan: {e}")

    def scan_for_alpha(self) -> List[Dict]:
        """
        Execute a high-frequency alpha scan.
        
        Returns:
            List of high-confidence alpha tokens ready for entry.
        """
        self._last_scan_time = datetime.utcnow()
        alpha_tokens = []
        
        logger.debug(f"HF Moralis Scanner: Starting scan at {self._last_scan_time}")
        
        try:
            # Placeholder: In production, this would call Moralis API endpoints
            # For now, we'll structure the logic that would be used
            
            # Step 1: Get trending tokens with volume spike
            spiking_tokens = self._get_volume_spiking_tokens()
            logger.info(f"HF Moralis Scanner: Found {len(spiking_tokens)} tokens with volume spike")
            
            # Step 2: Filter by liquidity and narrative alignment
            for token in spiking_tokens:
                if self._is_high_alpha_candidate(token):
                    alpha_tokens.append(token)
                    logger.info(f"HF Moralis Scanner: 🎯 Alpha Found: {token['symbol']} | "
                               f"Vol Spike: {token['volume_spike_pct']:.1f}% | "
                               f"Liquidity: ${token['liquidity_usd']:,.0f} | "
                               f"Narrative: {token.get('narrative', 'N/A')}")
            
            # Step 3: Return top 5 by confidence score
            alpha_tokens.sort(key=lambda x: x.get('confidence_score', 0), reverse=True)
            return alpha_tokens[:5]
            
        except Exception as e:
            logger.error(f"HF Moralis Scanner: Scan failed: {e}")
            return []

    def _get_volume_spiking_tokens(self) -> List[Dict]:
        """
        Fetch tokens with >50% volume spike in the last hour.
        
        In production, this would call:
        - Moralis /discovery/tokens/trending
        - Filter by volume_24h_percent_change > 50
        """
        # Placeholder implementation
        return []

    def _is_high_alpha_candidate(self, token: Dict) -> bool:
        """
        Validate if a token meets high-alpha criteria.
        """
        # Check liquidity
        if token.get('liquidity_usd', 0) < self.min_liquidity_usd:
            return False
        
        # Check volume spike
        if token.get('volume_spike_pct', 0) < self.min_volume_spike_pct:
            return False
        
        # Check holders
        if token.get('holder_count', 0) < self.min_holders:
            return False
        
        # Check narrative alignment
        symbol = token.get('symbol', '').upper()
        for narrative, symbols in self.trending_narratives.items():
            if any(s.upper() in symbol for s in symbols):
                token['narrative'] = narrative
                token['confidence_score'] = 0.85
                return True
        
        # Default confidence for non-narrative tokens
        token['narrative'] = 'generic'
        token['confidence_score'] = 0.60
        return True

    def get_last_scan_time(self) -> Optional[datetime]:
        """Get the timestamp of the last scan."""
        return self._last_scan_time


# Global instance
hf_moralis_scanner = HighFrequencyMoralisScanner()
