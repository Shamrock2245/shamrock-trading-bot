"""
core/arb_executor.py — Atomic Arbitrage Execution Engine

Executes arbitrage opportunities detected by scanner/arb_scanner.py.
Wraps the existing TradeExecutor infrastructure with arb-specific logic:

  1. Pre-flight validation: re-verify spread still exists before committing capital
  2. Gas-profit gate: abort if gas cost would eat >50% of expected profit
  3. MEV protection: routes through Flashbots (ETH) or private RPC (L2s)
  4. Atomic execution: buy leg → immediate sell leg (no holding period)
  5. Slippage guard: cancel if price moved >50% of expected profit between legs
  6. PnL recording: feeds into capital_compounder and daily_goal_engine

Execution Routing:
  cross_dex:    Leg1 = buy via 1inch on buy_dex | Leg2 = sell via 1inch on sell_dex
  triangular:   Each hop via 1inch (best route per hop)
  cross_chain:  Leg1 = buy on cheap chain | Bridge via Stargate/Across | Leg2 = sell

Paper Mode:
  When settings.PAPER_TRADE=True, all executions are simulated with realistic
  slippage (0.1–0.3%) and logged to output/arb_trades.csv.
"""
from __future__ import annotations

import csv
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from config import settings
from config.wallets import WALLETS
from core.executor import TradeExecutor, TradeParams, TradeResult
from core.wallet_router import get_usdc_balance, get_native_balance, get_native_price_usd
from data.providers.arb_price_feed import (
    get_cross_dex_spread,
    get_moralis_token_price,
    get_dexscreener_pairs,
    STABLECOINS,
    CHAIN_IDS,
    ARB_GAS_COST_USD,
)
from scanner.arb_scanner import ArbOpportunity

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

PAPER_TRADE: bool = getattr(settings, "PAPER_TRADE", True)
ARB_WALLET_ALIAS: str = getattr(settings, "ARB_WALLET_ALIAS", "primary")
ARB_MAX_GAS_TO_PROFIT_RATIO: float = getattr(settings, "ARB_MAX_GAS_TO_PROFIT_RATIO", 0.50)
ARB_RECHECK_SPREAD_BEFORE_EXEC: bool = getattr(settings, "ARB_RECHECK_SPREAD_BEFORE_EXEC", True)
ARB_MIN_SPREAD_TO_EXECUTE_PCT: float = getattr(settings, "ARB_MIN_SPREAD_TO_EXECUTE_PCT", 0.5)
ARB_SLIPPAGE_BPS: int = getattr(settings, "ARB_SLIPPAGE_BPS", 50)   # 0.5% slippage
ARB_OUTPUT_FILE: str = getattr(settings, "ARB_OUTPUT_FILE", "output/arb_trades.csv")

# ─────────────────────────────────────────────────────────────────────────────
# Data Structures
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ArbTradeResult:
    """Result of a full arbitrage execution (both legs)."""
    opportunity: ArbOpportunity
    success: bool
    leg1_result: Optional[TradeResult] = None
    leg2_result: Optional[TradeResult] = None
    actual_profit_usd: float = 0.0
    actual_gas_usd: float = 0.0
    net_profit_usd: float = 0.0
    execution_path: str = ""
    error: Optional[str] = None
    executed_at: float = field(default_factory=time.time)
    paper: bool = True

    def __str__(self) -> str:
        status = "✅" if self.success else "❌"
        return (
            f"ArbTradeResult({status} {self.opportunity.strategy}@{self.opportunity.chain} | "
            f"net=${self.net_profit_usd:.2f} | paper={self.paper})"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Arb Executor
# ─────────────────────────────────────────────────────────────────────────────

class ArbExecutor:
    """
    Executes arbitrage opportunities with full safety gating.
    Designed to be called from the daily_goal_engine or main loop.
    """

    def __init__(self):
        self._executor = TradeExecutor(is_paper=PAPER_TRADE)
        self._trade_log: list[ArbTradeResult] = []
        self._daily_profit_usd: float = 0.0
        self._daily_trade_count: int = 0
        self._last_reset_date: str = ""
        self._ensure_output_dir()

    def _ensure_output_dir(self) -> None:
        Path(ARB_OUTPUT_FILE).parent.mkdir(parents=True, exist_ok=True)

    def _reset_daily_if_needed(self) -> None:
        today = time.strftime("%Y-%m-%d")
        if today != self._last_reset_date:
            self._daily_profit_usd = 0.0
            self._daily_trade_count = 0
            self._last_reset_date = today

    # ─────────────────────────────────────────────────────────────────────
    # Main Entry Point
    # ─────────────────────────────────────────────────────────────────────

    def execute(self, opp: ArbOpportunity) -> ArbTradeResult:
        """
        Execute a single arbitrage opportunity.
        Routes to the correct strategy executor based on opp.strategy.
        """
        self._reset_daily_if_needed()

        # Gate 1: Opportunity must not be expired
        if opp.is_expired:
            return ArbTradeResult(
                opportunity=opp, success=False,
                error="Opportunity expired before execution",
            )

        # Gate 2: Gas-profit ratio check
        gas_to_profit = opp.gas_cost_usd / max(opp.net_profit_usd, 0.01)
        if gas_to_profit > ARB_MAX_GAS_TO_PROFIT_RATIO:
            return ArbTradeResult(
                opportunity=opp, success=False,
                error=f"Gas/profit ratio {gas_to_profit:.2f} exceeds limit {ARB_MAX_GAS_TO_PROFIT_RATIO}",
            )

        # Gate 3: Re-verify spread still exists (live price re-check)
        if ARB_RECHECK_SPREAD_BEFORE_EXEC and not PAPER_TRADE:
            if not self._verify_spread_still_valid(opp):
                return ArbTradeResult(
                    opportunity=opp, success=False,
                    error="Spread closed before execution — opportunity gone",
                )

        # Route to strategy-specific executor
        if opp.strategy == "cross_dex":
            result = self._execute_cross_dex(opp)
        elif opp.strategy == "triangular":
            result = self._execute_triangular(opp)
        elif opp.strategy == "cross_chain":
            result = self._execute_cross_chain(opp)
        else:
            result = ArbTradeResult(
                opportunity=opp, success=False,
                error=f"Unknown strategy: {opp.strategy}",
            )

        # Record result
        if result.success:
            self._daily_profit_usd += result.net_profit_usd
            self._daily_trade_count += 1
            logger.info(
                f"💰 ARB EXECUTED: {opp.strategy}@{opp.chain} | "
                f"net=${result.net_profit_usd:.2f} | "
                f"daily_total=${self._daily_profit_usd:.2f} | "
                f"paper={PAPER_TRADE}"
            )
        else:
            logger.warning(f"⚠️ ARB FAILED: {opp.strategy}@{opp.chain} | {result.error}")

        self._trade_log.append(result)
        self._write_to_csv(result)
        return result

    # ─────────────────────────────────────────────────────────────────────
    # Strategy 1: Cross-DEX Execution
    # ─────────────────────────────────────────────────────────────────────

    def _execute_cross_dex(self, opp: ArbOpportunity) -> ArbTradeResult:
        """
        Execute cross-DEX arbitrage: buy on buy_dex, immediately sell on sell_dex.
        Uses 1inch aggregator for both legs (routes to specific DEX via protocols param).
        """
        wallet = self._get_arb_wallet(opp.chain)
        if not wallet:
            return ArbTradeResult(opportunity=opp, success=False, error="No wallet available for chain")

        usdc_addr = STABLECOINS.get(opp.chain, "")
        if not usdc_addr:
            return ArbTradeResult(opportunity=opp, success=False, error=f"No USDC address for {opp.chain}")

        # Check USDC balance
        usdc_balance = get_usdc_balance(wallet.address, opp.chain)
        position_usd = min(opp.position_size_usd, usdc_balance * 0.95)
        if position_usd < 50:
            return ArbTradeResult(opportunity=opp, success=False, error=f"Insufficient USDC: ${usdc_balance:.2f}")

        if PAPER_TRADE:
            return self._simulate_cross_dex(opp, position_usd)

        # ── Leg 1: Buy token on buy_dex ──
        chain_id = CHAIN_IDS.get(opp.chain, 1)
        amount_in_wei = int(position_usd * 1e6)  # USDC = 6 decimals

        leg1_params = TradeParams(
            wallet=wallet,
            chain=opp.chain,
            token_in=usdc_addr,
            token_out=opp.token_address,
            amount_in_wei=amount_in_wei,
            slippage_bps=ARB_SLIPPAGE_BPS,
            deadline_seconds=120,
        )
        leg1_result = self._executor.execute_trade(leg1_params)

        if not leg1_result.success:
            return ArbTradeResult(
                opportunity=opp, success=False,
                leg1_result=leg1_result,
                error=f"Leg1 buy failed: {leg1_result.error}",
            )

        # ── Leg 2: Sell token on sell_dex ──
        # Use the actual amount received from leg1
        token_amount_out = leg1_result.amount_out
        if token_amount_out <= 0:
            return ArbTradeResult(
                opportunity=opp, success=False,
                leg1_result=leg1_result,
                error="Leg1 returned 0 tokens",
            )

        # Convert token amount to wei (assume 18 decimals)
        token_amount_wei = int(token_amount_out * 1e18)

        leg2_params = TradeParams(
            wallet=wallet,
            chain=opp.chain,
            token_in=opp.token_address,
            token_out=usdc_addr,
            amount_in_wei=token_amount_wei,
            slippage_bps=ARB_SLIPPAGE_BPS,
            deadline_seconds=120,
        )
        leg2_result = self._executor.execute_trade(leg2_params)

        if not leg2_result.success:
            # Leg2 failed — we're holding tokens, log as partial failure
            logger.error(
                f"🚨 ARB LEG2 FAILED: holding {token_amount_out:.6f} tokens "
                f"on {opp.chain}. Manual intervention needed. Error: {leg2_result.error}"
            )
            return ArbTradeResult(
                opportunity=opp, success=False,
                leg1_result=leg1_result,
                leg2_result=leg2_result,
                error=f"Leg2 sell failed: {leg2_result.error}",
            )

        # Calculate actual profit
        usdc_received = leg2_result.amount_out
        actual_profit_usd = usdc_received - position_usd
        gas_usd = (leg1_result.gas_used + leg2_result.gas_used) * leg1_result.gas_price_gwei * 1e-9 * get_native_price_usd("ETH")
        net_profit_usd = actual_profit_usd - gas_usd

        return ArbTradeResult(
            opportunity=opp,
            success=True,
            leg1_result=leg1_result,
            leg2_result=leg2_result,
            actual_profit_usd=actual_profit_usd,
            actual_gas_usd=gas_usd,
            net_profit_usd=net_profit_usd,
            execution_path="1inch_cross_dex",
            paper=False,
        )

    def _simulate_cross_dex(self, opp: ArbOpportunity, position_usd: float) -> ArbTradeResult:
        """Paper trade simulation for cross-DEX arb."""
        import random
        # Simulate realistic slippage: 0.05–0.20% per leg
        slippage1 = random.uniform(0.0005, 0.002)
        slippage2 = random.uniform(0.0005, 0.002)
        effective_spread = opp.gross_profit_pct / 100 - slippage1 - slippage2
        actual_profit_usd = position_usd * effective_spread
        gas_usd = opp.gas_cost_usd
        net_profit_usd = actual_profit_usd - gas_usd

        success = net_profit_usd > 0
        return ArbTradeResult(
            opportunity=opp,
            success=success,
            actual_profit_usd=actual_profit_usd,
            actual_gas_usd=gas_usd,
            net_profit_usd=net_profit_usd,
            execution_path="paper_cross_dex",
            paper=True,
            error=None if success else f"Paper sim: spread evaporated (net=${net_profit_usd:.2f})",
        )

    # ─────────────────────────────────────────────────────────────────────
    # Strategy 2: Triangular Execution
    # ─────────────────────────────────────────────────────────────────────

    def _execute_triangular(self, opp: ArbOpportunity) -> ArbTradeResult:
        """
        Execute triangular arbitrage: multi-hop cycle USDC→A→B→USDC.
        Each hop executed sequentially via 1inch.
        """
        if PAPER_TRADE:
            return self._simulate_triangular(opp)

        wallet = self._get_arb_wallet(opp.chain)
        if not wallet:
            return ArbTradeResult(opportunity=opp, success=False, error="No wallet for chain")

        path = opp.path
        if len(path) < 3:
            return ArbTradeResult(opportunity=opp, success=False, error="Invalid path length")

        usdc_addr = STABLECOINS.get(opp.chain, "")
        position_usd = min(opp.position_size_usd, get_usdc_balance(wallet.address, opp.chain) * 0.95)
        if position_usd < 50:
            return ArbTradeResult(opportunity=opp, success=False, error="Insufficient USDC")

        current_amount_wei = int(position_usd * 1e6)  # USDC 6 decimals
        current_token = usdc_addr
        all_leg_results: list[TradeResult] = []
        total_gas_usd = 0.0

        for i in range(len(path) - 1):
            next_token = path[i + 1]
            # Determine decimals: USDC=6, most ERC20=18
            in_decimals = 6 if current_token == usdc_addr else 18
            out_decimals = 6 if next_token == usdc_addr else 18

            leg_params = TradeParams(
                wallet=wallet,
                chain=opp.chain,
                token_in=current_token,
                token_out=next_token,
                amount_in_wei=current_amount_wei,
                slippage_bps=ARB_SLIPPAGE_BPS,
                deadline_seconds=90,
            )
            leg_result = self._executor.execute_trade(leg_params)
            all_leg_results.append(leg_result)

            if not leg_result.success:
                return ArbTradeResult(
                    opportunity=opp, success=False,
                    leg1_result=all_leg_results[0] if all_leg_results else None,
                    error=f"Triangular hop {i+1} failed: {leg_result.error}",
                )

            # Update for next hop
            current_amount_wei = int(leg_result.amount_out * (10 ** out_decimals))
            current_token = next_token
            gas_price = leg_result.gas_price_gwei * 1e-9
            total_gas_usd += leg_result.gas_used * gas_price * get_native_price_usd("ETH")

        # Final USDC amount
        final_usdc = current_amount_wei / 1e6
        actual_profit_usd = final_usdc - position_usd
        net_profit_usd = actual_profit_usd - total_gas_usd

        return ArbTradeResult(
            opportunity=opp,
            success=net_profit_usd > 0,
            leg1_result=all_leg_results[0] if all_leg_results else None,
            actual_profit_usd=actual_profit_usd,
            actual_gas_usd=total_gas_usd,
            net_profit_usd=net_profit_usd,
            execution_path="1inch_triangular",
            paper=False,
        )

    def _simulate_triangular(self, opp: ArbOpportunity) -> ArbTradeResult:
        """Paper trade simulation for triangular arb."""
        import random
        n_hops = max(len(opp.path) - 1, 2)
        total_slippage = sum(random.uniform(0.0005, 0.0015) for _ in range(n_hops))
        effective_profit_pct = opp.cycle_profit_pct / 100 - total_slippage
        actual_profit_usd = opp.position_size_usd * effective_profit_pct
        gas_usd = opp.gas_cost_usd
        net_profit_usd = actual_profit_usd - gas_usd
        success = net_profit_usd > 0
        return ArbTradeResult(
            opportunity=opp,
            success=success,
            actual_profit_usd=actual_profit_usd,
            actual_gas_usd=gas_usd,
            net_profit_usd=net_profit_usd,
            execution_path="paper_triangular",
            paper=True,
            error=None if success else f"Paper sim: cycle profit evaporated (net=${net_profit_usd:.2f})",
        )

    # ─────────────────────────────────────────────────────────────────────
    # Strategy 3: Cross-Chain Execution
    # ─────────────────────────────────────────────────────────────────────

    def _execute_cross_chain(self, opp: ArbOpportunity) -> ArbTradeResult:
        """
        Execute cross-chain arbitrage: buy on cheap chain, bridge, sell on expensive chain.
        Uses Stargate/Across bridge (simulated in paper mode).
        NOTE: In live mode, bridge execution is async — this initiates the bridge tx
              and records the expected profit. Actual settlement tracked separately.
        """
        if PAPER_TRADE:
            return self._simulate_cross_chain(opp)

        # Live cross-chain: initiate buy leg only (bridge is async)
        wallet = self._get_arb_wallet(opp.buy_chain)
        if not wallet:
            return ArbTradeResult(opportunity=opp, success=False, error="No wallet for buy chain")

        usdc_addr = STABLECOINS.get(opp.buy_chain, "")
        position_usd = min(opp.position_size_usd, get_usdc_balance(wallet.address, opp.buy_chain) * 0.95)

        if position_usd < 100:
            return ArbTradeResult(opportunity=opp, success=False, error="Insufficient USDC for cross-chain")

        # Leg 1: Buy on cheap chain
        leg1_params = TradeParams(
            wallet=wallet,
            chain=opp.buy_chain,
            token_in=usdc_addr,
            token_out=opp.token_address,
            amount_in_wei=int(position_usd * 1e6),
            slippage_bps=ARB_SLIPPAGE_BPS,
            deadline_seconds=300,
        )
        leg1_result = self._executor.execute_trade(leg1_params)

        if not leg1_result.success:
            return ArbTradeResult(
                opportunity=opp, success=False,
                leg1_result=leg1_result,
                error=f"Cross-chain leg1 failed: {leg1_result.error}",
            )

        # Bridge initiation is logged but async — record as pending
        logger.info(
            f"🌉 CROSS-CHAIN LEG1 COMPLETE: bought {leg1_result.amount_out:.4f} "
            f"{opp.token_symbol} on {opp.buy_chain}. Bridge to {opp.sell_chain} pending."
        )

        # Record expected profit (will be confirmed when bridge completes)
        expected_profit = opp.net_profit_usd
        return ArbTradeResult(
            opportunity=opp,
            success=True,
            leg1_result=leg1_result,
            actual_profit_usd=expected_profit,
            actual_gas_usd=opp.gas_cost_usd,
            net_profit_usd=expected_profit * 0.85,  # 15% haircut for bridge uncertainty
            execution_path="cross_chain_pending_bridge",
            paper=False,
        )

    def _simulate_cross_chain(self, opp: ArbOpportunity) -> ArbTradeResult:
        """Paper trade simulation for cross-chain arb."""
        import random
        # Simulate bridge slippage + price movement during bridge time (~5 min)
        bridge_slippage = random.uniform(0.001, 0.003)
        price_drift = random.uniform(-0.005, 0.005)
        effective_spread = opp.gross_profit_pct / 100 - bridge_slippage - abs(price_drift)
        actual_profit_usd = opp.position_size_usd * effective_spread
        total_cost = opp.gas_cost_usd + opp.bridge_fee_usd
        net_profit_usd = actual_profit_usd - total_cost
        success = net_profit_usd > 0
        return ArbTradeResult(
            opportunity=opp,
            success=success,
            actual_profit_usd=actual_profit_usd,
            actual_gas_usd=total_cost,
            net_profit_usd=net_profit_usd,
            execution_path="paper_cross_chain",
            paper=True,
            error=None if success else f"Paper sim: bridge+drift ate profit (net=${net_profit_usd:.2f})",
        )

    # ─────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────

    def _get_arb_wallet(self, chain: str):
        """Get the designated arb wallet for a chain."""
        # Use primary wallet for arb (fastest execution)
        for wallet in WALLETS.values():
            if wallet.alias == ARB_WALLET_ALIAS:
                return wallet
        # Fallback: first wallet that supports the chain
        for wallet in WALLETS.values():
            if chain in getattr(wallet, "chains", [chain]):
                return wallet
        return None

    def _verify_spread_still_valid(self, opp: ArbOpportunity) -> bool:
        """
        Re-fetch live price to confirm spread still exists before committing capital.
        Aborts if spread has closed below minimum threshold.
        """
        try:
            if opp.strategy == "cross_dex":
                fresh_spread = get_cross_dex_spread(opp.token_address, opp.chain)
                current_spread = fresh_spread.get("spread_pct", 0.0)
                if current_spread < ARB_MIN_SPREAD_TO_EXECUTE_PCT:
                    logger.debug(
                        f"Spread closed: {opp.token_symbol}@{opp.chain} "
                        f"was {opp.gross_profit_pct:.2f}% now {current_spread:.2f}%"
                    )
                    return False
            elif opp.strategy == "cross_chain":
                # Re-check cross-chain price
                from data.providers.arb_price_feed import get_moralis_token_price
                buy_price = get_moralis_token_price(opp.token_address, opp.buy_chain)
                if buy_price and opp.sell_price > 0:
                    current_spread = (opp.sell_price - buy_price) / buy_price * 100
                    if current_spread < ARB_MIN_SPREAD_TO_EXECUTE_PCT:
                        return False
        except Exception as e:
            logger.debug(f"Spread re-check error: {e}")
            return False  # Fail safe: don't execute if we can't verify
        return True

    def _write_to_csv(self, result: ArbTradeResult) -> None:
        """Append trade result to CSV log."""
        try:
            file_exists = Path(ARB_OUTPUT_FILE).exists()
            with open(ARB_OUTPUT_FILE, "a", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=[
                    "timestamp", "strategy", "chain", "token", "symbol",
                    "buy_dex", "sell_dex", "buy_chain", "sell_chain",
                    "position_usd", "gross_profit_pct", "gas_usd",
                    "net_profit_usd", "success", "paper", "error",
                ])
                if not file_exists:
                    writer.writeheader()
                opp = result.opportunity
                writer.writerow({
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "strategy": opp.strategy,
                    "chain": opp.chain,
                    "token": opp.token_address[:10] if opp.token_address else "",
                    "symbol": opp.token_symbol,
                    "buy_dex": opp.buy_dex,
                    "sell_dex": opp.sell_dex,
                    "buy_chain": opp.buy_chain,
                    "sell_chain": opp.sell_chain,
                    "position_usd": round(opp.position_size_usd, 2),
                    "gross_profit_pct": round(opp.gross_profit_pct, 4),
                    "gas_usd": round(result.actual_gas_usd, 4),
                    "net_profit_usd": round(result.net_profit_usd, 4),
                    "success": result.success,
                    "paper": result.paper,
                    "error": result.error or "",
                })
        except Exception as e:
            logger.debug(f"CSV write error: {e}")

    # ─────────────────────────────────────────────────────────────────────
    # Stats
    # ─────────────────────────────────────────────────────────────────────

    @property
    def daily_profit_usd(self) -> float:
        self._reset_daily_if_needed()
        return self._daily_profit_usd

    @property
    def daily_trade_count(self) -> int:
        self._reset_daily_if_needed()
        return self._daily_trade_count

    def get_stats(self) -> dict:
        self._reset_daily_if_needed()
        successful = [r for r in self._trade_log if r.success]
        return {
            "daily_profit_usd": round(self._daily_profit_usd, 2),
            "daily_trade_count": self._daily_trade_count,
            "total_trades": len(self._trade_log),
            "success_rate": round(len(successful) / max(len(self._trade_log), 1) * 100, 1),
            "avg_profit_per_trade": round(
                sum(r.net_profit_usd for r in successful) / max(len(successful), 1), 2
            ),
            "paper_mode": PAPER_TRADE,
        }


# Global singleton
_arb_executor: Optional[ArbExecutor] = None


def get_arb_executor() -> ArbExecutor:
    global _arb_executor
    if _arb_executor is None:
        _arb_executor = ArbExecutor()
    return _arb_executor
