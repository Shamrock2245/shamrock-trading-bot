"""
cosmos/arb_engine.py — IBC cross-chain arbitrage engine.

Scans for price discrepancies between Cosmos DEXes and executes
profitable arbitrage trades.
"""

import logging
import time
from dataclasses import dataclass
from typing import Optional

from cosmos.cosmos_config import (
    ARB_MIN_SPREAD_PCT,
    ARB_MAX_TRADE_USD,
    ARB_DAILY_LOSS_LIMIT_USD,
    ARB_GAS_BUDGET_DAILY_USD,
    COSMOS_MODE,
)
from cosmos.price_monitor import PriceMonitor, PriceSpread
from cosmos.osmosis_executor import OsmosisExecutor

logger = logging.getLogger(__name__)


@dataclass
class ArbOpportunity:
    """A detected arbitrage opportunity."""
    symbol: str
    buy_dex: str
    sell_dex: str
    buy_price: float
    sell_price: float
    spread_pct: float
    estimated_profit_usd: float
    trade_size_usd: float
    gas_cost_usd: float
    net_profit_usd: float


@dataclass
class ArbTradeResult:
    """Result of an executed arbitrage trade."""
    success: bool
    opportunity: Optional[ArbOpportunity] = None
    buy_tx_hash: Optional[str] = None
    sell_tx_hash: Optional[str] = None
    actual_profit_usd: float = 0.0
    error: Optional[str] = None
    is_paper: bool = True


class ArbEngine:
    """
    Arbitrage engine for Cosmos ecosystem.
    
    Scans for price discrepancies between Osmosis, Astroport, and other DEXes.
    Executes buy-low/sell-high when spread exceeds threshold after fees.
    """
    
    def __init__(self):
        self.price_monitor = PriceMonitor()
        self.osmosis = OsmosisExecutor()
        self.is_paper = COSMOS_MODE != "live"
        
        # Daily tracking
        self._daily_pnl = 0.0
        self._daily_gas_spent = 0.0
        self._daily_trades = 0
        self._day_start = time.time()
        self._arbs_executed = []
    
    def _reset_daily_if_needed(self):
        """Reset daily counters at midnight."""
        now = time.time()
        if now - self._day_start > 86400:
            logger.info(
                f"Arb daily reset: PnL=${self._daily_pnl:.2f}, "
                f"trades={self._daily_trades}, gas=${self._daily_gas_spent:.2f}"
            )
            self._daily_pnl = 0.0
            self._daily_gas_spent = 0.0
            self._daily_trades = 0
            self._day_start = now
    
    def scan_opportunities(self) -> list[ArbOpportunity]:
        """
        Scan for arbitrage opportunities across all monitored DEXes.
        
        Returns opportunities sorted by estimated net profit (highest first).
        """
        self._reset_daily_if_needed()
        
        # Check daily limits
        if self._daily_pnl <= -ARB_DAILY_LOSS_LIMIT_USD:
            logger.warning(
                f"Arb daily loss limit reached (${self._daily_pnl:.2f}), "
                f"pausing until tomorrow"
            )
            return []
        
        if self._daily_gas_spent >= ARB_GAS_BUDGET_DAILY_USD:
            logger.warning(
                f"Arb daily gas budget exhausted (${self._daily_gas_spent:.2f}), "
                f"pausing until tomorrow"
            )
            return []
        
        # Fetch fresh prices
        self.price_monitor.scan_all_prices()
        
        # Find spreads above threshold
        spreads = self.price_monitor.find_spreads(min_spread_pct=ARB_MIN_SPREAD_PCT)
        
        opportunities = []
        for spread in spreads:
            # Estimate trade size (capped by max)
            trade_size_usd = min(ARB_MAX_TRADE_USD, 100.0)  # Start conservative
            
            # Estimate gas cost (~$0.10 per Osmosis TX)
            gas_cost_usd = 0.10
            
            # Estimate profit
            gross_profit = trade_size_usd * (spread.spread_pct / 100)
            net_profit = gross_profit - gas_cost_usd
            
            if net_profit > 0.05:  # Min $0.05 profit to bother
                opportunities.append(ArbOpportunity(
                    symbol=spread.symbol,
                    buy_dex=spread.dex_low,
                    sell_dex=spread.dex_high,
                    buy_price=spread.price_low,
                    sell_price=spread.price_high,
                    spread_pct=spread.spread_pct,
                    estimated_profit_usd=gross_profit,
                    trade_size_usd=trade_size_usd,
                    gas_cost_usd=gas_cost_usd,
                    net_profit_usd=net_profit,
                ))
        
        # Sort by net profit
        opportunities.sort(key=lambda o: o.net_profit_usd, reverse=True)
        
        if opportunities:
            logger.info(
                f"Found {len(opportunities)} arb opportunities. "
                f"Best: {opportunities[0].symbol} "
                f"{opportunities[0].spread_pct:.2f}% spread "
                f"(est. ${opportunities[0].net_profit_usd:.2f} profit)"
            )
        
        return opportunities
    
    def execute_arb(self, opportunity: ArbOpportunity) -> ArbTradeResult:
        """
        Execute an arbitrage trade.
        
        For now, focuses on Osmosis-internal arb (different pool routes)
        and Osmosis↔Astroport cross-DEX arb.
        """
        logger.info(
            f"Executing arb: {opportunity.symbol} | "
            f"buy@{opportunity.buy_dex} ${opportunity.buy_price:.4f} → "
            f"sell@{opportunity.sell_dex} ${opportunity.sell_price:.4f} | "
            f"spread={opportunity.spread_pct:.2f}% | "
            f"size=${opportunity.trade_size_usd:.2f}"
        )
        
        if self.is_paper:
            # Paper mode — simulate the trade
            self._daily_trades += 1
            self._daily_pnl += opportunity.net_profit_usd
            self._daily_gas_spent += opportunity.gas_cost_usd
            
            result = ArbTradeResult(
                success=True,
                opportunity=opportunity,
                buy_tx_hash=f"paper_arb_buy_{int(time.time())}",
                sell_tx_hash=f"paper_arb_sell_{int(time.time())}",
                actual_profit_usd=opportunity.net_profit_usd,
                is_paper=True,
            )
            
            self._arbs_executed.append(result)
            
            logger.info(
                f"📄 PAPER ARB: {opportunity.symbol} | "
                f"profit=${opportunity.net_profit_usd:.2f} | "
                f"daily_pnl=${self._daily_pnl:.2f} | "
                f"trades_today={self._daily_trades}"
            )
            
            return result
        
        # Live execution
        # Step 1: Buy on cheaper DEX
        # Step 2: IBC transfer if cross-chain
        # Step 3: Sell on more expensive DEX
        
        logger.warning("Live arb execution requires full signing pipeline")
        return ArbTradeResult(
            success=False,
            opportunity=opportunity,
            error="Live arb execution not yet implemented",
            is_paper=False,
        )
    
    def run_arb_cycle(self) -> list[ArbTradeResult]:
        """
        Run one arbitrage scanning + execution cycle.
        
        Returns list of executed trades.
        """
        results = []
        
        opportunities = self.scan_opportunities()
        
        for opp in opportunities[:3]:  # Max 3 arbs per cycle
            # Re-verify spread is still valid (prices move fast)
            # In production, we'd re-fetch the specific price pair
            
            result = self.execute_arb(opp)
            results.append(result)
            
            if not result.success:
                logger.warning(f"Arb failed for {opp.symbol}: {result.error}")
                break  # Stop on first failure
        
        return results
    
    def get_daily_summary(self) -> dict:
        """Get daily arb performance summary."""
        return {
            "daily_pnl_usd": self._daily_pnl,
            "daily_gas_usd": self._daily_gas_spent,
            "daily_trades": self._daily_trades,
            "total_arbs_session": len(self._arbs_executed),
            "loss_limit_remaining": ARB_DAILY_LOSS_LIMIT_USD + self._daily_pnl,
            "gas_budget_remaining": ARB_GAS_BUDGET_DAILY_USD - self._daily_gas_spent,
        }
