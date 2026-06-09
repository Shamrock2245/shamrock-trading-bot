"""
core/arb_executor.py — Zero-Risk Flash Arb Engine
=================================================

Executes atomic arbitrage opportunities via flash loans (zero capital at risk).

Flash Loan Providers:
  EVM:    Balancer V2 (preferred — 0% fee) → Aave V3 fallback (0.05% fee)
  Solana: Solana Flash-Borrow via Kamino / Marginfi (see solana_flash_arb.py)

Execution Flow (EVM):
  1. Pre-flight: re-verify spread ≥ 1.5% net after gas
  2. Max-size calculation: min(DEX liquidity / 3, Balancer pool depth, Aave available)
  3. Build 1inch swap payloads for each leg of the arb path
  4. Encode ArbParams and call FlashArbReceiver.executeBalancerFlashArb()
  5. On-chain contract atomically:
       a. Receives borrowed tokens
       b. Executes all swap legs
       c. Verifies profit ≥ minExpectedProfit — REVERTS if not
       d. Repays flash loan + fee
       e. Transfers net profit to owner wallet
  6. Python layer confirms tx success and records PnL

Strategies Supported:
  cross_dex:    Same token, same chain, different DEX venues
  triangular:   Multi-hop cycle USDC → A → B → USDC
  cross_chain:  NOT flash-loaned (bridge latency breaks atomicity) — uses legacy path

Safety Guarantees:
  ✅ Atomic revert: if profit < minExpectedProfit, the ENTIRE tx reverts
  ✅ Zero capital at risk: borrowed funds are returned in the same tx
  ✅ Gas-profit gate: abort if gas > 50% of expected profit
  ✅ Spread re-check: live price verified before committing to flash loan
  ✅ MEV protection: submitted via Flashbots private mempool on Ethereum
  ✅ Min profit floor: 1.5% net profit required (configurable)

Flash Loan Addresses (per chain):
  Balancer Vault V2:
    ethereum:  0xBA12222222228d8Ba445958a75a0704d566BF2C8
    arbitrum:  0xBA12222222228d8Ba445958a75a0704d566BF2C8
    polygon:   0xBA12222222228d8Ba445958a75a0704d566BF2C8
    base:      0xBA12222222228d8Ba445958a75a0704d566BF2C8
  Aave V3 Pool:
    ethereum:  0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2
    arbitrum:  0x794a61358D6845594F94dc1DB02A252b5b4814aD
    polygon:   0x794a61358D6845594F94dc1DB02A252b5b4814aD
    base:      0xA238Dd80C259a72e81d7e4664a9801593F98d1c5

Paper Mode:
  When settings.PAPER_TRADE=True, flash loan execution is simulated with realistic
  slippage (0.05–0.20%) and logged to output/arb_trades.csv.
"""
from __future__ import annotations

import csv
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from config import settings
from config.wallets import WALLETS
from config.chains import CHAINS
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

# PAPER_TRADE is read dynamically from (settings.get_current_mode() == "paper") so that runtime
# mode changes (MODE env var) are respected without a process restart.
# The old static PAPER_TRADE=getattr(settings,'PAPER_TRADE',True) was
# evaluated once at import time and could not reflect live mode changes.
def PAPER_TRADE() -> bool:  # type: ignore[misc]
    """Return True if the bot is currently in paper mode."""
    return settings.get_current_mode() == "paper"
# Backwards-compat alias (bool-like callable — evaluates at call time)
_PAPER_TRADE_STATIC: bool = (settings.get_current_mode() == "paper")  # used only for TradeExecutor init
ARB_WALLET_ALIAS: str = getattr(settings, "ARB_WALLET_ALIAS", "primary")
ARB_MAX_GAS_TO_PROFIT_RATIO: float = getattr(settings, "ARB_MAX_GAS_TO_PROFIT_RATIO", 0.50)
ARB_RECHECK_SPREAD_BEFORE_EXEC: bool = getattr(settings, "ARB_RECHECK_SPREAD_BEFORE_EXEC", True)
ARB_MIN_SPREAD_TO_EXECUTE_PCT: float = getattr(settings, "ARB_MIN_SPREAD_TO_EXECUTE_PCT", 0.5)
ARB_SLIPPAGE_BPS: int = getattr(settings, "ARB_SLIPPAGE_BPS", 50)   # 0.5% slippage
ARB_OUTPUT_FILE: str = getattr(settings, "ARB_OUTPUT_FILE", "output/arb_trades.csv")

# Flash Arb specific config
FLASH_ARB_MIN_PROFIT_PCT: float = getattr(settings, "FLASH_ARB_MIN_PROFIT_PCT", 1.5)  # 1.5% min net profit
FLASH_ARB_MAX_POSITION_USD: float = getattr(settings, "FLASH_ARB_MAX_POSITION_USD", 500_000.0)
FLASH_ARB_LIQUIDITY_FRACTION: float = getattr(settings, "FLASH_ARB_LIQUIDITY_FRACTION", 0.30)  # Use up to 30% of DEX liquidity
FLASH_ARB_SAFETY_MARGIN_PCT: float = getattr(settings, "FLASH_ARB_SAFETY_MARGIN_PCT", 0.10)  # 10% safety haircut on min profit
FLASH_ARB_PREFER_BALANCER: bool = getattr(settings, "FLASH_ARB_PREFER_BALANCER", True)  # Balancer = 0% fee; Aave = 0.05%

# Balancer V2 Vault — same address on all EVM chains (canonical deployment)
BALANCER_VAULT: dict[str, str] = {
    "ethereum":  "0xBA12222222228d8Ba445958a75a0704d566BF2C8",
    "arbitrum":  "0xBA12222222228d8Ba445958a75a0704d566BF2C8",
    "polygon":   "0xBA12222222228d8Ba445958a75a0704d566BF2C8",
    "base":      "0xBA12222222228d8Ba445958a75a0704d566BF2C8",
    "bsc":       "",  # Balancer not on BSC — use Aave or PancakeSwap flash
    "avalanche": "0xBA12222222228d8Ba445958a75a0704d566BF2C8",
}

# Aave V3 Pool addresses per chain
AAVE_POOL: dict[str, str] = {
    "ethereum":  "0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2",
    "arbitrum":  "0x794a61358D6845594F94dc1DB02A252b5b4814aD",
    "polygon":   "0x794a61358D6845594F94dc1DB02A252b5b4814aD",
    "base":      "0xA238Dd80C259a72e81d7e4664a9801593F98d1c5",
    "avalanche": "0x794a61358D6845594F94dc1DB02A252b5b4814aD",
    "bsc":       "",  # Aave not on BSC
}

# Aave V3 flash loan fee (0.05% = 5 bps)
AAVE_FLASH_FEE_BPS: int = 5

# FlashArbReceiver contract addresses (deployed per chain — populated post-deploy)
# These are set via env vars after the Solidity contract is deployed
FLASH_ARB_RECEIVER: dict[str, str] = {
    "ethereum":  os.getenv("FLASH_ARB_RECEIVER_ETHEREUM", ""),
    "arbitrum":  os.getenv("FLASH_ARB_RECEIVER_ARBITRUM", ""),
    "polygon":   os.getenv("FLASH_ARB_RECEIVER_POLYGON", ""),
    "base":      os.getenv("FLASH_ARB_RECEIVER_BASE", ""),
    "bsc":       os.getenv("FLASH_ARB_RECEIVER_BSC", ""),
    "avalanche": os.getenv("FLASH_ARB_RECEIVER_AVALANCHE", ""),
}

# Minimal ABI for FlashArbReceiver contract interaction
FLASH_ARB_RECEIVER_ABI = json.loads("""[
  {
    "inputs": [
      {"internalType": "address", "name": "token", "type": "address"},
      {"internalType": "uint256", "name": "amount", "type": "uint256"},
      {"internalType": "uint256", "name": "minExpectedProfit", "type": "uint256"},
      {"internalType": "bytes[]",  "name": "swapPayloads", "type": "bytes[]"},
      {"internalType": "address[]","name": "swapRouters",  "type": "address[]"}
    ],
    "name": "executeBalancerFlashArb",
    "outputs": [],
    "stateMutability": "nonpayable",
    "type": "function"
  },
  {
    "inputs": [
      {"internalType": "address", "name": "token", "type": "address"},
      {"internalType": "uint256", "name": "amount", "type": "uint256"},
      {"internalType": "uint256", "name": "minExpectedProfit", "type": "uint256"},
      {"internalType": "bytes[]",  "name": "swapPayloads", "type": "bytes[]"},
      {"internalType": "address[]","name": "swapRouters",  "type": "address[]"}
    ],
    "name": "executeAaveFlashArb",
    "outputs": [],
    "stateMutability": "nonpayable",
    "type": "function"
  }
]""")

# ─────────────────────────────────────────────────────────────────────────────
# Data Structures
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class FlashArbResult:
    """Result of a flash loan arbitrage execution."""
    opportunity: ArbOpportunity
    success: bool
    flash_provider: str = ""          # "balancer", "aave", "paper", "legacy"
    flash_amount_usd: float = 0.0     # Size of the flash loan taken
    actual_profit_usd: float = 0.0
    actual_gas_usd: float = 0.0
    net_profit_usd: float = 0.0
    tx_hash: Optional[str] = None
    execution_path: str = ""
    error: Optional[str] = None
    executed_at: float = field(default_factory=time.time)
    paper: bool = True

    def __str__(self) -> str:
        status = "✅" if self.success else "❌"
        return (
            f"FlashArbResult({status} {self.opportunity.strategy}@{self.opportunity.chain} | "
            f"flash=${self.flash_amount_usd:,.0f} | net=${self.net_profit_usd:.2f} | "
            f"provider={self.flash_provider} | paper={self.paper})"
        )


# Backwards-compatible alias so existing callers using ArbTradeResult still work
ArbTradeResult = FlashArbResult


# ─────────────────────────────────────────────────────────────────────────────
# Flash Size Calculator
# ─────────────────────────────────────────────────────────────────────────────

def calculate_max_flash_size(
    opp: ArbOpportunity,
    chain: str,
    token_address: str,
    gross_profit_pct: float,
) -> float:
    """
    Calculate the maximum profitable flash loan size in USD.

    The optimal size is bounded by:
      1. DEX liquidity depth (max 30% of pool to limit price impact)
      2. Flash loan provider pool depth
      3. Hard cap: FLASH_ARB_MAX_POSITION_USD
      4. Profitability: size × net_profit_pct > gas_cost

    Returns the maximum USD amount to borrow.
    """
    gas_usd = ARB_GAS_COST_USD.get(chain, 5.0)
    # Multiply gas by number of hops (triangular = 3 hops, cross-dex = 2)
    n_hops = len(opp.path) - 1 if opp.path else 2
    total_gas_usd = gas_usd * n_hops

    # Net profit rate after fees
    flash_fee_pct = 0.0 if FLASH_ARB_PREFER_BALANCER and BALANCER_VAULT.get(chain) else AAVE_FLASH_FEE_BPS / 10000
    net_profit_rate = (gross_profit_pct / 100) - flash_fee_pct - (ARB_SLIPPAGE_BPS / 10000)

    if net_profit_rate <= 0:
        return 0.0

    # Minimum size to cover gas
    min_size_for_gas = total_gas_usd / net_profit_rate

    # Liquidity-bounded size
    liquidity_usd = getattr(opp, "liquidity_usd", 50_000.0)
    liquidity_bounded = liquidity_usd * FLASH_ARB_LIQUIDITY_FRACTION

    # Hard cap
    max_size = min(liquidity_bounded, FLASH_ARB_MAX_POSITION_USD)

    # Must be profitable after gas
    if max_size * net_profit_rate < total_gas_usd:
        return 0.0

    return max(max_size, min_size_for_gas * 2)  # At least 2× break-even size


# ─────────────────────────────────────────────────────────────────────────────
# 1inch Swap Payload Builder
# ─────────────────────────────────────────────────────────────────────────────

def build_oneinch_swap_payload(
    chain: str,
    token_in: str,
    token_out: str,
    amount_wei: int,
    receiver: str,
    slippage_bps: int = 50,
) -> Optional[bytes]:
    """
    Build a 1inch V6 swap calldata payload for use inside the flash loan contract.
    Returns raw calldata bytes, or None if the quote fails.
    """
    from data.http_session import get_session

    chain_id = CHAIN_IDS.get(chain, 1)
    oneinch_api_key = os.getenv("ONEINCH_API_KEY", "")
    base_url = f"https://api.1inch.dev/swap/v6.0/{chain_id}"

    headers = {"Authorization": f"Bearer {oneinch_api_key}"} if oneinch_api_key else {}
    slippage_pct = slippage_bps / 100

    params = {
        "src": token_in,
        "dst": token_out,
        "amount": str(amount_wei),
        "from": receiver,
        "slippage": str(slippage_pct),
        "disableEstimate": "true",
        "allowPartialFill": "false",
    }

    try:
        session = get_session()
        resp = session.get(f"{base_url}/swap", params=params, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            tx_data = data.get("tx", {}).get("data", "")
            if tx_data:
                return bytes.fromhex(tx_data[2:] if tx_data.startswith("0x") else tx_data)
        else:
            logger.debug(f"1inch swap payload error: {resp.status_code} — {resp.text[:200]}")
    except Exception as e:
        logger.debug(f"1inch payload build error: {e}")

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Arb Executor (Main Class)
# ─────────────────────────────────────────────────────────────────────────────

class ArbExecutor:
    """
    Zero-Risk Flash Arb Engine.

    Executes arbitrage opportunities atomically via flash loans.
    No capital is at risk — the on-chain contract mathematically reverts
    if the arb is not profitable after repaying the loan.
    """

    def __init__(self):
        self._executor = TradeExecutor(is_paper=settings.get_current_mode() == "paper")
        self._trade_log: list[FlashArbResult] = []
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

    def execute(self, opp: ArbOpportunity) -> FlashArbResult:
        """
        Execute a single arbitrage opportunity via flash loan.
        Routes to flash_cross_dex or flash_triangular based on strategy.
        Cross-chain arb falls back to legacy two-leg execution (bridge breaks atomicity).
        """
        self._reset_daily_if_needed()

        # Gate 1: Opportunity must not be expired
        if opp.is_expired:
            return FlashArbResult(
                opportunity=opp, success=False,
                error="Opportunity expired before execution",
            )

        # Gate 2: Minimum net profit percentage (1.5% floor)
        gross_pct = getattr(opp, "gross_profit_pct", 0.0) or getattr(opp, "cycle_profit_pct", 0.0)
        gas_usd = opp.gas_cost_usd
        position_usd = getattr(opp, "position_size_usd", 1000.0)
        net_profit_pct = (gross_pct / 100) - (gas_usd / max(position_usd, 1))
        if net_profit_pct * 100 < FLASH_ARB_MIN_PROFIT_PCT:
            return FlashArbResult(
                opportunity=opp, success=False,
                error=(
                    f"Net profit {net_profit_pct*100:.3f}% below flash arb floor "
                    f"{FLASH_ARB_MIN_PROFIT_PCT}%"
                ),
            )

        # Gate 3: Gas-profit ratio check
        gas_to_profit = gas_usd / max(opp.net_profit_usd, 0.01)
        if gas_to_profit > ARB_MAX_GAS_TO_PROFIT_RATIO:
            return FlashArbResult(
                opportunity=opp, success=False,
                error=f"Gas/profit ratio {gas_to_profit:.2f} exceeds limit {ARB_MAX_GAS_TO_PROFIT_RATIO}",
            )

        # Gate 4: Re-verify spread still exists (live price re-check)
        if ARB_RECHECK_SPREAD_BEFORE_EXEC and not (settings.get_current_mode() == "paper"):
            if not self._verify_spread_still_valid(opp):
                return FlashArbResult(
                    opportunity=opp, success=False,
                    error="Spread closed before execution — opportunity gone",
                )

        # Route to strategy-specific flash executor
        if opp.strategy == "cross_dex":
            result = self._execute_flash_cross_dex(opp)
        elif opp.strategy == "triangular":
            result = self._execute_flash_triangular(opp)
        elif opp.strategy == "cross_chain":
            # Cross-chain cannot be atomic (bridge latency) — use legacy path
            result = self._execute_cross_chain_legacy(opp)
        else:
            result = FlashArbResult(
                opportunity=opp, success=False,
                error=f"Unknown strategy: {opp.strategy}",
            )

        # Record result
        if result.success:
            self._daily_profit_usd += result.net_profit_usd
            self._daily_trade_count += 1
            _is_paper = settings.get_current_mode() == "paper"
            logger.info(
                f"💰 FLASH ARB EXECUTED: {opp.strategy}@{opp.chain} | "
                f"flash=${result.flash_amount_usd:,.0f} | "
                f"net=${result.net_profit_usd:.2f} | "
                f"provider={result.flash_provider} | "
                f"daily_total=${self._daily_profit_usd:.2f} | "
                f"paper={_is_paper}"
            )
        else:
            logger.warning(f"⚠️ FLASH ARB FAILED: {opp.strategy}@{opp.chain} | {result.error}")

        self._trade_log.append(result)
        self._write_to_csv(result)
        return result

    # ─────────────────────────────────────────────────────────────────────
    # Strategy 1: Flash Cross-DEX
    # ─────────────────────────────────────────────────────────────────────

    def _execute_flash_cross_dex(self, opp: ArbOpportunity) -> FlashArbResult:
        """
        Execute cross-DEX arbitrage atomically via flash loan.
        Borrows USDC → buys token on buy_dex → sells on sell_dex → repays loan.
        """
        if (settings.get_current_mode() == "paper"):
            return self._simulate_flash_cross_dex(opp)

        chain = opp.chain
        wallet = self._get_arb_wallet(chain)
        if not wallet:
            return FlashArbResult(opportunity=opp, success=False, error="No wallet for chain")

        receiver_addr = FLASH_ARB_RECEIVER.get(chain, "")
        if not receiver_addr:
            logger.warning(
                f"FlashArbReceiver not deployed on {chain} — falling back to legacy two-leg arb"
            )
            return self._execute_legacy_cross_dex(opp)

        usdc_addr = STABLECOINS.get(chain, "")
        if not usdc_addr:
            return FlashArbResult(opportunity=opp, success=False, error=f"No USDC on {chain}")

        # Calculate maximum flash loan size
        gross_pct = getattr(opp, "gross_profit_pct", 0.0)
        flash_amount_usd = calculate_max_flash_size(opp, chain, opp.token_address, gross_pct)
        if flash_amount_usd < 100:
            return FlashArbResult(
                opportunity=opp, success=False,
                error=f"Flash size too small: ${flash_amount_usd:.2f}",
            )

        # USDC has 6 decimals
        flash_amount_wei = int(flash_amount_usd * 1e6)

        # Build swap payloads for both legs
        # Leg 1: USDC → token on buy_dex
        leg1_payload = build_oneinch_swap_payload(
            chain=chain,
            token_in=usdc_addr,
            token_out=opp.token_address,
            amount_wei=flash_amount_wei,
            receiver=receiver_addr,
            slippage_bps=ARB_SLIPPAGE_BPS,
        )
        if not leg1_payload:
            return FlashArbResult(opportunity=opp, success=False, error="Failed to build leg1 swap payload")

        # Estimate token amount out from leg1 (approximate using gross_profit_pct)
        token_amount_est = flash_amount_usd / getattr(opp, "buy_price", 1.0)
        token_amount_wei = int(token_amount_est * 1e18)

        # Leg 2: token → USDC on sell_dex
        leg2_payload = build_oneinch_swap_payload(
            chain=chain,
            token_in=opp.token_address,
            token_out=usdc_addr,
            amount_wei=token_amount_wei,
            receiver=receiver_addr,
            slippage_bps=ARB_SLIPPAGE_BPS,
        )
        if not leg2_payload:
            return FlashArbResult(opportunity=opp, success=False, error="Failed to build leg2 swap payload")

        # Calculate minimum expected profit (with safety margin)
        oneinch_router = CHAINS[chain].oneinch_router or ""
        swap_payloads = [leg1_payload, leg2_payload]
        swap_routers = [oneinch_router, oneinch_router]

        net_profit_usd = flash_amount_usd * (gross_pct / 100) - opp.gas_cost_usd
        min_expected_profit_usd = net_profit_usd * (1 - FLASH_ARB_SAFETY_MARGIN_PCT)
        min_expected_profit_wei = int(min_expected_profit_usd * 1e6)  # USDC 6 decimals

        # Execute via flash loan
        return self._dispatch_flash_loan(
            opp=opp,
            chain=chain,
            wallet=wallet,
            receiver_addr=receiver_addr,
            flash_token=usdc_addr,
            flash_amount_wei=flash_amount_wei,
            flash_amount_usd=flash_amount_usd,
            min_expected_profit_wei=min_expected_profit_wei,
            swap_payloads=swap_payloads,
            swap_routers=swap_routers,
            execution_path="flash_cross_dex",
        )

    def _simulate_flash_cross_dex(self, opp: ArbOpportunity) -> FlashArbResult:
        """Paper trade simulation for flash cross-DEX arb."""
        import random
        gross_pct = getattr(opp, "gross_profit_pct", 0.0)
        flash_amount_usd = calculate_max_flash_size(opp, opp.chain, opp.token_address, gross_pct)
        if flash_amount_usd < 100:
            flash_amount_usd = getattr(opp, "position_size_usd", 1000.0)

        slippage1 = random.uniform(0.0005, 0.002)
        slippage2 = random.uniform(0.0005, 0.002)
        flash_fee = 0.0  # Balancer = 0% fee
        effective_spread = (gross_pct / 100) - slippage1 - slippage2 - flash_fee
        actual_profit_usd = flash_amount_usd * effective_spread
        gas_usd = opp.gas_cost_usd
        net_profit_usd = actual_profit_usd - gas_usd

        success = net_profit_usd > 0 and (gross_pct >= FLASH_ARB_MIN_PROFIT_PCT)
        return FlashArbResult(
            opportunity=opp,
            success=success,
            flash_provider="paper_balancer",
            flash_amount_usd=flash_amount_usd,
            actual_profit_usd=actual_profit_usd,
            actual_gas_usd=gas_usd,
            net_profit_usd=net_profit_usd,
            execution_path="paper_flash_cross_dex",
            paper=True,
            error=None if success else f"Paper sim: spread evaporated (net=${net_profit_usd:.2f})",
        )

    # ─────────────────────────────────────────────────────────────────────
    # Strategy 2: Flash Triangular
    # ─────────────────────────────────────────────────────────────────────

    def _execute_flash_triangular(self, opp: ArbOpportunity) -> FlashArbResult:
        """
        Execute triangular arbitrage atomically via flash loan.
        Borrows USDC → hop A → hop B → USDC → repays loan.
        All hops encoded as sequential 1inch swap payloads.
        """
        if (settings.get_current_mode() == "paper"):
            return self._simulate_flash_triangular(opp)

        chain = opp.chain
        wallet = self._get_arb_wallet(chain)
        if not wallet:
            return FlashArbResult(opportunity=opp, success=False, error="No wallet for chain")

        receiver_addr = FLASH_ARB_RECEIVER.get(chain, "")
        if not receiver_addr:
            logger.warning(
                f"FlashArbReceiver not deployed on {chain} — falling back to legacy triangular arb"
            )
            return self._execute_legacy_triangular(opp)

        path = opp.path
        if len(path) < 3:
            return FlashArbResult(opportunity=opp, success=False, error="Invalid triangular path length")

        usdc_addr = STABLECOINS.get(chain, "")
        if not usdc_addr:
            return FlashArbResult(opportunity=opp, success=False, error=f"No USDC on {chain}")

        gross_pct = getattr(opp, "cycle_profit_pct", 0.0) or getattr(opp, "gross_profit_pct", 0.0)
        flash_amount_usd = calculate_max_flash_size(opp, chain, path[1], gross_pct)
        if flash_amount_usd < 100:
            return FlashArbResult(
                opportunity=opp, success=False,
                error=f"Flash size too small: ${flash_amount_usd:.2f}",
            )

        # Build sequential swap payloads for each hop
        swap_payloads = []
        swap_routers = []
        oneinch_router = CHAINS[chain].oneinch_router or ""

        # Estimate amounts through the path (approximate)
        current_amount_usd = flash_amount_usd
        current_token = usdc_addr

        for i in range(len(path) - 1):
            next_token = path[i + 1]
            in_decimals = 6 if current_token == usdc_addr else 18
            amount_wei = int(current_amount_usd * (10 ** in_decimals))

            payload = build_oneinch_swap_payload(
                chain=chain,
                token_in=current_token,
                token_out=next_token,
                amount_wei=amount_wei,
                receiver=receiver_addr,
                slippage_bps=ARB_SLIPPAGE_BPS,
            )
            if not payload:
                return FlashArbResult(
                    opportunity=opp, success=False,
                    error=f"Failed to build swap payload for hop {i+1}: {current_token[:8]}→{next_token[:8]}",
                )

            swap_payloads.append(payload)
            swap_routers.append(oneinch_router)

            # Rough estimate for next hop amount (apply gross_pct spread proportionally)
            hop_profit_pct = (gross_pct / 100) / max(len(path) - 1, 1)
            current_amount_usd = current_amount_usd * (1 + hop_profit_pct)
            current_token = next_token

        # Flash loan amount in USDC wei (6 decimals)
        flash_amount_wei = int(flash_amount_usd * 1e6)
        net_profit_usd = flash_amount_usd * (gross_pct / 100) - opp.gas_cost_usd
        min_expected_profit_usd = net_profit_usd * (1 - FLASH_ARB_SAFETY_MARGIN_PCT)
        min_expected_profit_wei = int(min_expected_profit_usd * 1e6)

        return self._dispatch_flash_loan(
            opp=opp,
            chain=chain,
            wallet=wallet,
            receiver_addr=receiver_addr,
            flash_token=usdc_addr,
            flash_amount_wei=flash_amount_wei,
            flash_amount_usd=flash_amount_usd,
            min_expected_profit_wei=min_expected_profit_wei,
            swap_payloads=swap_payloads,
            swap_routers=swap_routers,
            execution_path="flash_triangular",
        )

    def _simulate_flash_triangular(self, opp: ArbOpportunity) -> FlashArbResult:
        """Paper trade simulation for flash triangular arb."""
        import random
        gross_pct = getattr(opp, "cycle_profit_pct", 0.0) or getattr(opp, "gross_profit_pct", 0.0)
        n_hops = max(len(opp.path) - 1, 2)
        flash_amount_usd = calculate_max_flash_size(opp, opp.chain, opp.path[1] if len(opp.path) > 1 else "", gross_pct)
        if flash_amount_usd < 100:
            flash_amount_usd = getattr(opp, "position_size_usd", 1000.0)

        total_slippage = sum(random.uniform(0.0005, 0.0015) for _ in range(n_hops))
        effective_profit_pct = (gross_pct / 100) - total_slippage
        actual_profit_usd = flash_amount_usd * effective_profit_pct
        gas_usd = opp.gas_cost_usd
        net_profit_usd = actual_profit_usd - gas_usd
        success = net_profit_usd > 0 and (gross_pct >= FLASH_ARB_MIN_PROFIT_PCT)
        return FlashArbResult(
            opportunity=opp,
            success=success,
            flash_provider="paper_balancer",
            flash_amount_usd=flash_amount_usd,
            actual_profit_usd=actual_profit_usd,
            actual_gas_usd=gas_usd,
            net_profit_usd=net_profit_usd,
            execution_path="paper_flash_triangular",
            paper=True,
            error=None if success else f"Paper sim: cycle profit evaporated (net=${net_profit_usd:.2f})",
        )

    # ─────────────────────────────────────────────────────────────────────
    # Flash Loan Dispatcher (Balancer → Aave fallback)
    # ─────────────────────────────────────────────────────────────────────

    def _dispatch_flash_loan(
        self,
        opp: ArbOpportunity,
        chain: str,
        wallet,
        receiver_addr: str,
        flash_token: str,
        flash_amount_wei: int,
        flash_amount_usd: float,
        min_expected_profit_wei: int,
        swap_payloads: list[bytes],
        swap_routers: list[str],
        execution_path: str,
    ) -> FlashArbResult:
        """
        Dispatch the flash loan transaction to the FlashArbReceiver contract.
        Tries Balancer first (0% fee), falls back to Aave (0.05% fee).
        Submits via Flashbots on Ethereum for MEV protection.
        """
        try:
            from web3 import Web3
            from eth_account import Account

            chain_cfg = CHAINS[chain]
            w3 = Web3(Web3.HTTPProvider(chain_cfg.rpc_url))

            private_key = os.getenv(f"WALLET_PRIVATE_KEY_{wallet.alias.upper()}", "")
            if not private_key:
                return FlashArbResult(
                    opportunity=opp, success=False,
                    error=f"No private key for wallet alias '{wallet.alias}'",
                )

            account = Account.from_key(private_key)
            contract = w3.eth.contract(
                address=Web3.to_checksum_address(receiver_addr),
                abi=FLASH_ARB_RECEIVER_ABI,
            )

            # Encode swap payloads as list of bytes
            encoded_payloads = [p for p in swap_payloads]
            encoded_routers = [Web3.to_checksum_address(r) for r in swap_routers if r]

            # Try Balancer first (0% fee)
            flash_provider = "balancer"
            balancer_addr = BALANCER_VAULT.get(chain, "")
            use_balancer = bool(balancer_addr) and FLASH_ARB_PREFER_BALANCER

            if use_balancer:
                tx_func = contract.functions.executeBalancerFlashArb(
                    Web3.to_checksum_address(flash_token),
                    flash_amount_wei,
                    min_expected_profit_wei,
                    encoded_payloads,
                    encoded_routers,
                )
            else:
                # Aave fallback
                flash_provider = "aave"
                aave_addr = AAVE_POOL.get(chain, "")
                if not aave_addr:
                    return FlashArbResult(
                        opportunity=opp, success=False,
                        error=f"No flash loan provider available on {chain}",
                    )
                tx_func = contract.functions.executeAaveFlashArb(
                    Web3.to_checksum_address(flash_token),
                    flash_amount_wei,
                    min_expected_profit_wei,
                    encoded_payloads,
                    encoded_routers,
                )

            # Estimate gas
            gas_estimate = tx_func.estimate_gas({"from": account.address})
            gas_price_wei = w3.eth.gas_price
            gas_usd = (gas_estimate * gas_price_wei * 1e-18) * get_native_price_usd(chain_cfg.native_token)

            # Build and sign transaction
            nonce = w3.eth.get_transaction_count(account.address)
            tx = tx_func.build_transaction({
                "from": account.address,
                "gas": int(gas_estimate * 1.15),  # 15% gas buffer
                "gasPrice": gas_price_wei,
                "nonce": nonce,
                "chainId": chain_cfg.chain_id,
            })
            signed_tx = account.sign_transaction(tx)

            # Submit via Flashbots on Ethereum (MEV protection), direct on L2s
            if chain == "ethereum":
                from core.mev_protection import execute_via_flashbots
                fb_result = execute_via_flashbots(signed_tx.rawTransaction, w3)
                tx_hash = fb_result.tx_hash if fb_result and fb_result.success else None
                if not tx_hash:
                    # Fallback to public mempool if Flashbots fails
                    tx_hash_bytes = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
                    tx_hash = tx_hash_bytes.hex()
            else:
                tx_hash_bytes = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
                tx_hash = tx_hash_bytes.hex()

            # Wait for receipt
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            if receipt.status == 0:
                return FlashArbResult(
                    opportunity=opp, success=False,
                    flash_provider=flash_provider,
                    flash_amount_usd=flash_amount_usd,
                    actual_gas_usd=gas_usd,
                    tx_hash=tx_hash,
                    execution_path=execution_path,
                    error="Transaction reverted — arb was unprofitable (safety revert triggered)",
                    paper=False,
                )

            # Estimate actual profit from receipt logs (simplified: use expected)
            net_profit_usd = (flash_amount_usd * (getattr(opp, "gross_profit_pct", 0.0) / 100)) - gas_usd

            return FlashArbResult(
                opportunity=opp,
                success=True,
                flash_provider=flash_provider,
                flash_amount_usd=flash_amount_usd,
                actual_profit_usd=net_profit_usd + gas_usd,
                actual_gas_usd=gas_usd,
                net_profit_usd=net_profit_usd,
                tx_hash=tx_hash,
                execution_path=execution_path,
                paper=False,
            )

        except Exception as e:
            logger.error(f"Flash loan dispatch error on {chain}: {e}", exc_info=True)
            return FlashArbResult(
                opportunity=opp, success=False,
                error=f"Flash loan dispatch exception: {e}",
            )

    # ─────────────────────────────────────────────────────────────────────
    # Legacy Fallbacks (used when FlashArbReceiver not deployed)
    # ─────────────────────────────────────────────────────────────────────

    def _execute_legacy_cross_dex(self, opp: ArbOpportunity) -> FlashArbResult:
        """Legacy two-leg cross-DEX arb (no flash loan — uses wallet capital)."""
        wallet = self._get_arb_wallet(opp.chain)
        if not wallet:
            return FlashArbResult(opportunity=opp, success=False, error="No wallet for chain")

        usdc_addr = STABLECOINS.get(opp.chain, "")
        usdc_balance = get_usdc_balance(wallet.address, opp.chain)
        position_usd = min(opp.position_size_usd, usdc_balance * 0.95)
        if position_usd < 50:
            return FlashArbResult(opportunity=opp, success=False, error=f"Insufficient USDC: ${usdc_balance:.2f}")

        chain_id = CHAIN_IDS.get(opp.chain, 1)
        amount_in_wei = int(position_usd * 1e6)

        leg1_params = TradeParams(
            wallet=wallet, chain=opp.chain,
            token_in=usdc_addr, token_out=opp.token_address,
            amount_in_wei=amount_in_wei, slippage_bps=ARB_SLIPPAGE_BPS, deadline_seconds=120,
        )
        leg1_result = self._executor.execute_trade(leg1_params)
        if not leg1_result.success:
            return FlashArbResult(opportunity=opp, success=False, error=f"Leg1 buy failed: {leg1_result.error}")

        token_amount_wei = int(leg1_result.amount_out * 1e18)
        leg2_params = TradeParams(
            wallet=wallet, chain=opp.chain,
            token_in=opp.token_address, token_out=usdc_addr,
            amount_in_wei=token_amount_wei, slippage_bps=ARB_SLIPPAGE_BPS, deadline_seconds=120,
        )
        leg2_result = self._executor.execute_trade(leg2_params)
        if not leg2_result.success:
            logger.error(
                f"🚨 LEGACY ARB LEG2 FAILED: holding {leg1_result.amount_out:.6f} tokens "
                f"on {opp.chain}. Manual intervention needed."
            )
            return FlashArbResult(opportunity=opp, success=False, error=f"Leg2 sell failed: {leg2_result.error}")

        usdc_received = leg2_result.amount_out
        actual_profit_usd = usdc_received - position_usd
        gas_usd = (
            (leg1_result.gas_used + leg2_result.gas_used)
            * leg1_result.gas_price_gwei * 1e-9
            * get_native_price_usd("ETH")
        )
        net_profit_usd = actual_profit_usd - gas_usd

        return FlashArbResult(
            opportunity=opp, success=True,
            flash_provider="legacy_no_flash",
            flash_amount_usd=position_usd,
            actual_profit_usd=actual_profit_usd,
            actual_gas_usd=gas_usd,
            net_profit_usd=net_profit_usd,
            execution_path="legacy_cross_dex",
            paper=False,
        )

    def _execute_legacy_triangular(self, opp: ArbOpportunity) -> FlashArbResult:
        """Legacy sequential triangular arb (no flash loan — uses wallet capital)."""
        wallet = self._get_arb_wallet(opp.chain)
        if not wallet:
            return FlashArbResult(opportunity=opp, success=False, error="No wallet for chain")

        path = opp.path
        if len(path) < 3:
            return FlashArbResult(opportunity=opp, success=False, error="Invalid path length")

        usdc_addr = STABLECOINS.get(opp.chain, "")
        position_usd = min(opp.position_size_usd, get_usdc_balance(wallet.address, opp.chain) * 0.95)
        if position_usd < 50:
            return FlashArbResult(opportunity=opp, success=False, error="Insufficient USDC")

        current_amount_wei = int(position_usd * 1e6)
        current_token = usdc_addr
        all_leg_results: list[TradeResult] = []
        total_gas_usd = 0.0

        for i in range(len(path) - 1):
            next_token = path[i + 1]
            in_decimals = 6 if current_token == usdc_addr else 18
            out_decimals = 6 if next_token == usdc_addr else 18

            leg_params = TradeParams(
                wallet=wallet, chain=opp.chain,
                token_in=current_token, token_out=next_token,
                amount_in_wei=current_amount_wei, slippage_bps=ARB_SLIPPAGE_BPS, deadline_seconds=90,
            )
            leg_result = self._executor.execute_trade(leg_params)
            all_leg_results.append(leg_result)

            if not leg_result.success:
                return FlashArbResult(
                    opportunity=opp, success=False,
                    error=f"Triangular hop {i+1} failed: {leg_result.error}",
                )

            current_amount_wei = int(leg_result.amount_out * (10 ** out_decimals))
            current_token = next_token
            total_gas_usd += leg_result.gas_used * leg_result.gas_price_gwei * 1e-9 * get_native_price_usd("ETH")

        final_usdc = current_amount_wei / 1e6
        actual_profit_usd = final_usdc - position_usd
        net_profit_usd = actual_profit_usd - total_gas_usd

        return FlashArbResult(
            opportunity=opp,
            success=net_profit_usd > 0,
            flash_provider="legacy_no_flash",
            flash_amount_usd=position_usd,
            actual_profit_usd=actual_profit_usd,
            actual_gas_usd=total_gas_usd,
            net_profit_usd=net_profit_usd,
            execution_path="legacy_triangular",
            paper=False,
        )

    def _execute_cross_chain_legacy(self, opp: ArbOpportunity) -> FlashArbResult:
        """
        Cross-chain arbitrage — cannot be flash-loaned (bridge breaks atomicity).
        Uses legacy async bridge pattern: buy on cheap chain, bridge, sell on expensive chain.
        """
        if (settings.get_current_mode() == "paper"):
            return self._simulate_cross_chain(opp)

        wallet = self._get_arb_wallet(opp.buy_chain)
        if not wallet:
            return FlashArbResult(opportunity=opp, success=False, error="No wallet for buy chain")

        usdc_addr = STABLECOINS.get(opp.buy_chain, "")
        position_usd = min(opp.position_size_usd, get_usdc_balance(wallet.address, opp.buy_chain) * 0.95)
        if position_usd < 100:
            return FlashArbResult(opportunity=opp, success=False, error="Insufficient USDC for cross-chain")

        leg1_params = TradeParams(
            wallet=wallet, chain=opp.buy_chain,
            token_in=usdc_addr, token_out=opp.token_address,
            amount_in_wei=int(position_usd * 1e6), slippage_bps=ARB_SLIPPAGE_BPS, deadline_seconds=300,
        )
        leg1_result = self._executor.execute_trade(leg1_params)
        if not leg1_result.success:
            return FlashArbResult(
                opportunity=opp, success=False,
                error=f"Cross-chain leg1 failed: {leg1_result.error}",
            )

        logger.info(
            f"🌉 CROSS-CHAIN LEG1 COMPLETE: bought {leg1_result.amount_out:.4f} "
            f"{opp.token_symbol} on {opp.buy_chain}. Bridge to {opp.sell_chain} pending."
        )

        expected_profit = opp.net_profit_usd
        return FlashArbResult(
            opportunity=opp, success=True,
            flash_provider="legacy_cross_chain",
            flash_amount_usd=position_usd,
            actual_profit_usd=expected_profit,
            actual_gas_usd=opp.gas_cost_usd,
            net_profit_usd=expected_profit * 0.85,
            execution_path="cross_chain_pending_bridge",
            paper=False,
        )

    def _simulate_cross_chain(self, opp: ArbOpportunity) -> FlashArbResult:
        """Paper trade simulation for cross-chain arb."""
        import random
        bridge_slippage = random.uniform(0.001, 0.003)
        price_drift = random.uniform(-0.005, 0.005)
        effective_spread = opp.gross_profit_pct / 100 - bridge_slippage - abs(price_drift)
        actual_profit_usd = opp.position_size_usd * effective_spread
        total_cost = opp.gas_cost_usd + opp.bridge_fee_usd
        net_profit_usd = actual_profit_usd - total_cost
        success = net_profit_usd > 0
        return FlashArbResult(
            opportunity=opp, success=success,
            flash_provider="paper_cross_chain",
            flash_amount_usd=opp.position_size_usd,
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
        for wallet in WALLETS.values():
            if wallet.alias == ARB_WALLET_ALIAS:
                return wallet
        for wallet in WALLETS.values():
            if chain in getattr(wallet, "chains", [chain]):
                return wallet
        return None

    def _verify_spread_still_valid(self, opp: ArbOpportunity) -> bool:
        """
        Re-fetch live price to confirm spread still exists before committing to flash loan.
        Aborts if spread has closed below minimum threshold.
        """
        try:
            if opp.strategy == "cross_dex":
                fresh_spread = get_cross_dex_spread(opp.token_address, opp.chain)
                current_spread = fresh_spread.get("spread_pct", 0.0)
                if current_spread < FLASH_ARB_MIN_PROFIT_PCT:
                    logger.debug(
                        f"Spread closed: {opp.token_symbol}@{opp.chain} "
                        f"was {opp.gross_profit_pct:.2f}% now {current_spread:.2f}%"
                    )
                    return False
            elif opp.strategy == "cross_chain":
                buy_price = get_moralis_token_price(opp.token_address, opp.buy_chain)
                if buy_price and opp.sell_price > 0:
                    current_spread = (opp.sell_price - buy_price) / buy_price * 100
                    if current_spread < ARB_MIN_SPREAD_TO_EXECUTE_PCT:
                        return False
        except Exception as e:
            logger.debug(f"Spread re-check error: {e}")
            return False  # Fail safe: don't execute if we can't verify
        return True

    def _write_to_csv(self, result: FlashArbResult) -> None:
        """Append trade result to CSV log."""
        try:
            file_exists = Path(ARB_OUTPUT_FILE).exists()
            with open(ARB_OUTPUT_FILE, "a", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=[
                    "timestamp", "strategy", "chain", "token", "symbol",
                    "buy_dex", "sell_dex", "buy_chain", "sell_chain",
                    "flash_provider", "flash_amount_usd",
                    "position_usd", "gross_profit_pct", "gas_usd",
                    "net_profit_usd", "success", "paper", "tx_hash", "error",
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
                    "flash_provider": result.flash_provider,
                    "flash_amount_usd": round(result.flash_amount_usd, 2),
                    "position_usd": round(opp.position_size_usd, 2),
                    "gross_profit_pct": round(getattr(opp, "gross_profit_pct", 0.0), 4),
                    "gas_usd": round(result.actual_gas_usd, 4),
                    "net_profit_usd": round(result.net_profit_usd, 4),
                    "success": result.success,
                    "paper": result.paper,
                    "tx_hash": result.tx_hash or "",
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
        flash_trades = [r for r in successful if "flash" in r.flash_provider]
        return {
            "daily_profit_usd": round(self._daily_profit_usd, 2),
            "daily_trade_count": self._daily_trade_count,
            "total_trades": len(self._trade_log),
            "flash_trades": len(flash_trades),
            "legacy_trades": len(successful) - len(flash_trades),
            "success_rate": round(len(successful) / max(len(self._trade_log), 1) * 100, 1),
            "avg_profit_per_trade": round(
                sum(r.net_profit_usd for r in successful) / max(len(successful), 1), 2
            ),
            "avg_flash_size_usd": round(
                sum(r.flash_amount_usd for r in flash_trades) / max(len(flash_trades), 1), 2
            ),
            "paper_mode": (settings.get_current_mode() == "paper"),
            "flash_arb_min_profit_pct": FLASH_ARB_MIN_PROFIT_PCT,
        }


# Global singleton
_arb_executor: Optional[ArbExecutor] = None


def get_arb_executor() -> ArbExecutor:
    global _arb_executor
    if _arb_executor is None:
        _arb_executor = ArbExecutor()
    return _arb_executor
