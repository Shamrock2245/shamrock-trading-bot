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
from core import coinbase_client
from core import solana_executor

logger = logging.getLogger(__name__)

# Configuration
FUNDING_FARMER_ENABLED: bool = os.getenv("FUNDING_FARMER_ENABLED", "true").lower() == "true"
FUNDING_EXTREME_THRESHOLD: float = float(os.getenv("FUNDING_EXTREME_THRESHOLD", "0.001"))  # 0.1% per hour
FUNDING_POLL_INTERVAL: float = float(os.getenv("FUNDING_POLL_INTERVAL_SECONDS", "3600.0"))  # Check hourly
FUNDING_POSITION_SIZE_USD: float = float(os.getenv("FUNDING_POSITION_SIZE_USD", "100.0"))

_STATE_FILE = Path(os.getenv("DASHBOARD_STATE_DIR", "./data/dashboard")) / "funding_farms.json"

SOLANA_MINTS = {
    "WIF": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",
    "BONK": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
    "POPCAT": "7GCihgDB8xsUKnmRoDk3ZxjsWq1yXhtCGqj8KjHhFfB3",
    "MEW": "MEW1gQWJ3nEXg2qgERiKu7FAFj79PHvQVREqcMCNtT2"
}

class FundingFarmer:
    def __init__(self, hl_executor: HyperliquidExecutor):
        self.enabled = FUNDING_FARMER_ENABLED
        self.hl_executor = hl_executor
        self.active_farms: dict[str, dict] = {}  # coin -> farm state
        self._lock = threading.Lock()

    @staticmethod
    def _get_hourly_funding_from_asset(asset: dict) -> float:
        """Extract funding rate from a meta() asset dict, converted to hourly."""
        try:
            rate_8h = float(asset.get("funding", 0))
            return rate_8h / 8.0
        except (TypeError, ValueError):
            return 0.0

    def _execute_hedge(self, coin: str, side: str, size_usd: float) -> bool:
        """
        Execute the opposing hedge on a spot DEX/CEX.
        If we SHORT on HL, we BUY SPOT here.
        If we LONG on HL, we SELL SPOT here (or short elsewhere).
        """
        logger.info(f"FundingFarmer: Executing hedge {side.upper()} SPOT for {coin} size ${size_usd}")
        
        try:
            # Try to execute via Coinbase Agentic Wallet on Base first if the token is available there
            base_tokens = ["ETH", "USDC", "WETH", "cbBTC", "AERO"]
            
            if side.lower() == "sell" and coin.upper() not in base_tokens:
                logger.warning(f"FundingFarmer: Spot selling (shorting) not supported natively yet. Aborting farm for {coin}.")
                return False
            if coin.upper() in base_tokens:
                logger.info(f"FundingFarmer: Token {coin} is available on Base, executing hedge via Coinbase CEX API...")
                try:
                    # We are short on HL, so we BUY the token on Coinbase
                    # We are long on HL, so we SELL the token on Coinbase
                    if side.lower() == "sell":
                        # Hedge = Sell (Token -> USD)
                        price_data = coinbase_client.get_price(f"{coin.upper()}-USD")
                        if not price_data or price_data.mid <= 0:
                            logger.error(f"FundingFarmer: Could not fetch price for {coin} to execute CEX sell.")
                            return False
                        token_amount = size_usd / price_data.mid
                        order = coinbase_client.market_sell(f"{coin.upper()}-USD", token_amount, is_paper=False)
                    else:
                        # Hedge = Buy (USD -> Token)
                        order = coinbase_client.market_buy(f"{coin.upper()}-USD", size_usd, is_paper=False)
                        
                    if order and order.status == "FILLED":
                        logger.info(f"FundingFarmer: Coinbase CEX hedge successful: {order.order_id}")
                        return True
                    else:
                        logger.warning(f"FundingFarmer: Coinbase CEX hedge failed or unconfirmed. Falling back...")
                except Exception as e:
                    logger.warning(f"FundingFarmer: Coinbase CEX exception: {e}. Falling back...")

            # 1. Check if it's a Solana token
            if coin.upper() in SOLANA_MINTS:
                mint = SOLANA_MINTS[coin.upper()]
                logger.info(f"FundingFarmer: Routing {coin} hedge to Solana (Jupiter).")
                
                # We need to convert size_usd to sol_amount for execute_solana_buy
                sol_price_data = coinbase_client.get_price("SOL-USD")
                if not sol_price_data or sol_price_data.mid <= 0:
                    logger.error("FundingFarmer: Could not fetch SOL price to calculate hedge amount.")
                    return False
                    
                sol_amount = size_usd / sol_price_data.mid
                
                wallet_pub = os.getenv("WALLET_ADDRESS_PRIMARY", "")
                wallet_priv_env = "WALLET_PRIVATE_KEY_PRIMARY"
                
                if not wallet_pub or not os.getenv(wallet_priv_env):
                    logger.error("FundingFarmer: Solana wallet credentials missing.")
                    return False
                    
                res = solana_executor.execute_solana_buy(
                    token_mint=mint, 
                    sol_amount=sol_amount, 
                    wallet_public_key=wallet_pub, 
                    wallet_private_key_env=wallet_priv_env,
                    is_paper=False
                )
                return res is not None

            # 2. Check if it's supported on Coinbase
            elif f"{coin.upper()}-USD" in coinbase_client.COINBASE_ARB_PAIRS:
                logger.info(f"FundingFarmer: Routing {coin} hedge to Coinbase Advanced.")
                res = coinbase_client.market_buy(f"{coin.upper()}-USD", size_usd, is_paper=False)
                return res is not None
                
            else:
                logger.warning(f"FundingFarmer: {coin} is not supported on Coinbase or Solana. Cannot hedge.")
                return False
                
        except Exception as e:
            logger.error(f"FundingFarmer: Error executing spot hedge for {coin}: {e}", exc_info=True)
            return False

    def scan_and_farm(self):
        """Scan for extreme funding rates and open delta-neutral positions."""
        if not self.enabled or not self.hl_executor.is_available():
            return

        try:
            # Single API call — extract all funding rates from one meta() response
            meta = self.hl_executor._execute_api(self.hl_executor._info.meta)
            if not meta:
                logger.warning("FundingFarmer: meta() returned None, skipping scan")
                return
            for asset in meta.get("universe", []):
                coin = asset.get("name", "").upper()
                
                # Skip if already farming
                if coin in self.active_farms:
                    continue

                hourly_rate = self._get_hourly_funding_from_asset(asset)
                
                if abs(hourly_rate) >= FUNDING_EXTREME_THRESHOLD:
                    base_tokens = ["ETH", "USDC", "WETH", "cbBTC", "AERO"]
                    
                    if hourly_rate > 0:
                        logger.info(f"🌾 Extreme POSITIVE funding detected on {coin}: {hourly_rate*100:.4f}%/hr")
                        # Positive funding = longs pay shorts. We SHORT on HL, BUY on Spot.
                        hl_side = "sell"
                        hedge_side = "buy"
                    else:
                        if coin.upper() not in base_tokens:
                            logger.debug(f"FundingFarmer: {coin} has extreme NEGATIVE funding, but spot shorting is unsupported on CEX/Solana. Skipping.")
                            continue
                        logger.info(f"🌾 Extreme NEGATIVE funding detected on {coin}: {hourly_rate*100:.4f}%/hr")
                        # Negative funding = shorts pay longs. We LONG on HL, SELL on Spot (Base).
                        hl_side = "buy"
                        hedge_side = "sell"
                    
                    with self._lock:
                        # 1. Execute Hedge first
                        hedge_ok = self._execute_hedge(coin, hedge_side, FUNDING_POSITION_SIZE_USD)
                        if not hedge_ok:
                            logger.error(f"FundingFarmer: Hedge failed for {coin}, aborting HL entry.")
                            continue
                            
                        # 2. Execute HL position (1x leverage)
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
                            logger.error(f"🚨 HEDGE ROLLBACK 🚨 HL entry failed for {coin}! Unwinding Spot {hedge_side.upper()} position.")
                            # Immediate Rollback (Sell what we just bought)
                            base_tokens = ["ETH", "USDC", "WETH", "cbBTC", "AERO"]
                            if coin.upper() in base_tokens:
                                try:
                                    # Rollback: if we bought Token, sell Token
                                    if hedge_side.lower() == "buy":
                                        price_data = coinbase_client.get_price(f"{coin.upper()}-USD")
                                        if price_data and price_data.mid > 0:
                                            token_amount = FUNDING_POSITION_SIZE_USD / price_data.mid
                                            coinbase_client.market_sell(f"{coin.upper()}-USD", token_amount, is_paper=False)
                                        else:
                                            logger.error(f"FATAL ROLLBACK ERROR: Could not fetch price to unwind {coin} via CEX!")
                                            continue
                                    else:
                                        # Rollback: we sold Token, so buy Token back
                                        coinbase_client.market_buy(f"{coin.upper()}-USD", FUNDING_POSITION_SIZE_USD, is_paper=False)
                                    logger.info(f"FundingFarmer: Coinbase CEX rollback executed for {coin}.")
                                except Exception as e:
                                    logger.error(f"FundingFarmer: Coinbase CEX rollback failed: {e}")
                            elif coin.upper() in SOLANA_MINTS:
                                mint = SOLANA_MINTS[coin.upper()]
                                wallet_pub = os.getenv("WALLET_ADDRESS_PRIMARY", "")
                                wallet_priv_env = "WALLET_PRIVATE_KEY_PRIMARY"
                                solana_executor.execute_solana_sell(
                                    token_mint=mint,
                                    sell_percentage=100.0,
                                    wallet_public_key=wallet_pub,
                                    wallet_private_key_env=wallet_priv_env,
                                    is_paper=False
                                )
                            elif f"{coin.upper()}-USD" in coinbase_client.COINBASE_ARB_PAIRS:
                                # We need base_size to sell on Coinbase, so fetch price
                                price_data = coinbase_client.get_price(f"{coin.upper()}-USD")
                                if price_data and price_data.mid > 0:
                                    base_size = FUNDING_POSITION_SIZE_USD / price_data.mid
                                    coinbase_client.market_sell(f"{coin.upper()}-USD", base_size, is_paper=False)
                                else:
                                    logger.error(f"FATAL ROLLBACK ERROR: Could not fetch Coinbase price to unwind {coin}!")
                            
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
