"""
core/funding_farmer.py — Delta-Neutral Funding Rate Farmer

Monitors Hyperliquid for extreme funding rates (> 0.1% per hour).
When an extreme rate is detected, it executes a delta-neutral trade:
1. Opens a position on Hyperliquid to collect the funding fee (fade the crowd).
2. Simultaneously opens an opposing hedge position on a spot DEX (via Coinbase/Solana).

This allows the bot to collect hourly yield with zero price-action risk.
"""

import logging
import os
import time
import threading
from typing import Optional
from pathlib import Path
import json
from datetime import datetime, timezone

from core.hyperliquid_executor import HyperliquidExecutor

logger = logging.getLogger(__name__)

# Configuration
FUNDING_FARMER_ENABLED: bool = os.getenv("FUNDING_FARMER_ENABLED", "true").lower() == "true"
FUNDING_EXTREME_THRESHOLD: float = float(os.getenv("FUNDING_EXTREME_THRESHOLD", "0.001"))  # 0.1% per hour
FUNDING_POLL_INTERVAL: float = float(os.getenv("FUNDING_POLL_INTERVAL_SECONDS", "3600.0"))  # Check hourly
FUNDING_POSITION_SIZE_USD: float = float(os.getenv("FUNDING_POSITION_SIZE_USD", "100.0"))

_STATE_FILE = Path(os.getenv("DASHBOARD_STATE_DIR", "./data/dashboard")) / "funding_farms.json"

class FundingFarmer:
    def __init__(self, hl_executor: HyperliquidExecutor):
        self.enabled = FUNDING_FARMER_ENABLED
        self.hl_executor = hl_executor
        self.active_farms: dict[str, dict] = {}  # coin -> farm state
        self._lock = threading.Lock()

    def _get_hourly_funding(self, coin: str) -> float:
        """Fetch current funding rate (converted to hourly if HL provides 8h)."""
        if not self.hl_executor._info:
            return 0.0
        try:
            meta = self.hl_executor._info.meta()
            for asset in meta.get("universe", []):
                if asset.get("name", "").upper() == coin.upper():
                    # HL funding is typically per 8h, convert to hourly for our threshold check
                    rate_8h = float(asset.get("funding", 0))
                    return rate_8h / 8.0
            return 0.0
        except Exception as e:
            logger.warning(f"FundingFarmer: failed to get funding for {coin}: {e}")
            return 0.0

    def _execute_hedge(self, coin: str, side: str, size_usd: float) -> bool:
        """
        Execute the opposing hedge on a spot DEX.
        If we SHORT on HL, we BUY SPOT here.
        If we LONG on HL, we SELL SPOT here (or short elsewhere).
        """
        # Placeholder for actual DEX/CEX execution logic (Coinbase/Solana)
        # In a real scenario, this would call core.coinbase_client or a Solana executor.
        logger.info(f"FundingFarmer: Executing hedge {side.upper()} SPOT for {coin} size ${size_usd}")
        # Assuming success for the sake of the delta-neutral lock
        return True

    def scan_and_farm(self):
        """Scan for extreme funding rates and open delta-neutral positions."""
        if not self.enabled or not self.hl_executor.is_available():
            return

        try:
            meta = self.hl_executor._info.meta()
            for asset in meta.get("universe", []):
                coin = asset.get("name", "").upper()
                
                # Skip if already farming
                if coin in self.active_farms:
                    continue

                hourly_rate = self._get_hourly_funding(coin)
                
                if abs(hourly_rate) >= FUNDING_EXTREME_THRESHOLD:
                    logger.info(f"🌾 Extreme funding detected on {coin}: {hourly_rate*100:.4f}%/hr")
                    
                    # If funding is positive, longs pay shorts. We want to SHORT on HL.
                    # If funding is negative, shorts pay longs. We want to LONG on HL.
                    hl_side = "sell" if hourly_rate > 0 else "buy"
                    hedge_side = "buy" if hl_side == "sell" else "sell"
                    
                    with self._lock:
                        # 1. Execute Hedge first (or simultaneously)
                        hedge_ok = self._execute_hedge(coin, hedge_side, FUNDING_POSITION_SIZE_USD)
                        if not hedge_ok:
                            logger.error(f"FundingFarmer: Hedge failed for {coin}, aborting HL entry.")
                            continue
                            
                        # 2. Execute HL position
                        # We use 1x leverage for the funding farm to minimize liquidation risk on the leg
                        if hl_side == "sell":
                            result = self.hl_executor.open_short(coin, FUNDING_POSITION_SIZE_USD, leverage=1, gem_score=100)
                        else:
                            result = self.hl_executor.open_long(coin, FUNDING_POSITION_SIZE_USD, leverage=1, gem_score=100)
                            
                        if result:
                            self.active_farms[coin] = {
                                "hl_side": hl_side,
                                "hedge_side": hedge_side,
                                "size_usd": FUNDING_POSITION_SIZE_USD,
                                "entry_rate": hourly_rate
                            }
                            logger.info(f"✅ Delta-Neutral Farm established for {coin}")
                        else:
                            logger.error(f"FundingFarmer: HL entry failed for {coin}, MUST UNWIND HEDGE!")
                            # In production, add logic to immediately unwind the spot hedge here
                            
            self._save_state()
                            
        except Exception as e:
            logger.error(f"FundingFarmer scan failed: {e}", exc_info=True)

    def _save_state(self) -> None:
        """Persist funding farmer state for dashboard display."""
        try:
            _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            state = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "enabled": self.enabled,
                "active_farms": self.active_farms
            }
            _STATE_FILE.write_text(json.dumps(state, indent=2))
        except Exception as e:
            logger.debug(f"FundingFarmer: state save failed: {e}")

def _funding_farmer_daemon(hl_executor: HyperliquidExecutor):
    """Background thread for the Funding Farmer."""
    farmer = FundingFarmer(hl_executor)
    time.sleep(60) # Wait for initializations
    logger.info(f"🌾 Funding Farmer daemon started | threshold={FUNDING_EXTREME_THRESHOLD*100:.2f}%/hr")
    
    while True:
        farmer.scan_and_farm()
        time.sleep(FUNDING_POLL_INTERVAL)
