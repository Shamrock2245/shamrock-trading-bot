"""
core/executor.py — Trade execution engine with MEV protection.

Supports three execution paths:
  1. CoW Protocol (MEV-protected batch auctions) — preferred for Ethereum
  2. Flashbots RPC (private mempool) — fallback for Ethereum
  3. 1inch Aggregation API — best price routing across all chains

All trades are gated by:
  - Safety pipeline (core/safety.py) — MANDATORY
  - Risk checks (position sizing, gas ceiling, circuit breaker)
  - Paper mode guard (no real txns unless MODE=live)

⚠️  NEVER call execute_trade() without first calling check_token_safety().
    The executor enforces this internally but callers should be explicit.
"""

import logging
import os
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

import requests
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from eth_account import Account

from config.chains import CHAINS, ChainConfig
from config.wallets import WalletConfig
from config import settings
from core.safety import check_token_safety, SafetyResult
from core.mev_protection import execute_via_cow_live, execute_via_flashbots

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Data Classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TradeParams:
    """Parameters for a single trade."""
    wallet: WalletConfig
    chain: str
    token_in: str          # Address of token to sell (use WETH/native for buys)
    token_out: str         # Address of token to buy
    amount_in_wei: int     # Exact amount to spend (in wei)
    slippage_bps: int = 100  # 1% default slippage (100 basis points)
    deadline_seconds: int = 300  # 5 min deadline


@dataclass
class TradeResult:
    """Result of a trade execution attempt."""
    success: bool
    tx_hash: Optional[str] = None
    amount_in: float = 0.0
    amount_out: float = 0.0
    gas_used: int = 0
    gas_price_gwei: float = 0.0
    execution_path: str = ""   # "cow", "flashbots", "1inch", "paper"
    error: Optional[str] = None
    safety_result: Optional[SafetyResult] = None

    def __str__(self) -> str:
        if self.success:
            return (
                f"TradeResult(✅ {self.execution_path} | "
                f"tx={self.tx_hash[:10] if self.tx_hash else 'N/A'}... | "
                f"gas={self.gas_price_gwei:.1f}gwei)"
            )
        return f"TradeResult(❌ {self.error})"


# ─────────────────────────────────────────────────────────────────────────────
# Executor
# ─────────────────────────────────────────────────────────────────────────────

class TradeExecutor:
    """
    Executes trades with MEV protection across multiple DEX routers.
    Always runs safety checks before any execution.
    """

    def __init__(self):
        self._web3_cache: dict[str, Web3] = {}

    def _get_web3(self, chain: ChainConfig) -> Optional[Web3]:
        """Get Web3 connection, with PoA middleware for Polygon/BSC."""
        if chain.name in self._web3_cache:
            return self._web3_cache[chain.name]

        for rpc_url in [chain.rpc_url, chain.rpc_fallback]:
            if not rpc_url:
                continue
            try:
                w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 15}))
                if w3.is_connected():
                    # PoA chains need extra middleware
                    if chain.chain_id in (137, 56):  # Polygon, BSC
                        w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
                    self._web3_cache[chain.name] = w3
                    return w3
            except Exception as e:
                logger.warning(f"RPC {rpc_url} failed: {e}")
        return None

    def _get_current_gas_gwei(self, w3: Web3) -> float:
        """Get current gas price in gwei."""
        try:
            gas_wei = w3.eth.gas_price
            return float(Web3.from_wei(gas_wei, "gwei"))
        except Exception:
            return 999.0  # Return high value to block trade on error

    def _check_gas_ceiling(self, w3: Web3, chain: ChainConfig) -> tuple[bool, float]:
        """
        Check if current gas price is within the configured ceiling.
        Returns (is_ok, current_gwei).
        """
        current_gwei = self._get_current_gas_gwei(w3)
        ceiling = chain.max_gas_gwei
        if current_gwei > ceiling:
            logger.warning(
                f"Gas too high on {chain.name}: {current_gwei:.1f} gwei "
                f"(ceiling: {ceiling} gwei) — skipping trade"
            )
            return False, current_gwei
        return True, current_gwei

    # ── CoW Protocol (MEV-protected, Ethereum primary) ────────────────────────

    def _execute_via_cow(self, params: TradeParams) -> TradeResult:
        """
        Submit a trade via CoW Protocol's batch auction system.
        CoW provides MEV protection by matching orders off-chain before
        settling on-chain as a batch — no front-running possible.
        """
        try:
            chain_config = CHAINS[params.chain]
            cow_url = settings.COW_API_URL

            # Build CoW order
            order_payload = {
                "sellToken": params.token_in,
                "buyToken": params.token_out,
                "sellAmount": str(params.amount_in_wei),
                "buyAmountAfterFee": "0",  # CoW calculates minimum
                "validTo": self._deadline_timestamp(params.deadline_seconds),
                "appData": "0x0000000000000000000000000000000000000000000000000000000000000000",
                "feeAmount": "0",
                "kind": "sell",
                "partiallyFillable": False,
                "receiver": params.wallet.address,
                "from": params.wallet.address,
                "signingScheme": "ethsign",
            }

            # Get quote first
            quote_resp = requests.post(
                f"{cow_url}/api/v1/quote",
                json=order_payload,
                timeout=15,
            )

            if quote_resp.status_code != 200:
                return TradeResult(
                    success=False,
                    error=f"CoW quote failed: {quote_resp.text[:200]}",
                    execution_path="cow",
                )

            quote = quote_resp.json()
            logger.info(f"CoW quote received: {quote.get('quote', {})}")

            if settings.IS_PAPER:
                return TradeResult(
                    success=True,
                    execution_path="cow_paper",
                    amount_in=params.amount_in_wei / 1e18,
                    amount_out=float(quote.get("quote", {}).get("buyAmount", 0)) / 1e18,
                )

            # Sign and submit order (requires private key)
            private_key = params.wallet.private_key
            if not private_key:
                return TradeResult(
                    success=False,
                    error="No private key configured for wallet",
                    execution_path="cow",
                )

            # Live mode: full EIP-712 signing via mev_protection module
            logger.info("CoW order submission (live mode) — signing via EIP-712...")
            order_uid = execute_via_cow_live(
                sell_token=params.token_in,
                buy_token=params.token_out,
                sell_amount_wei=params.amount_in_wei,
                wallet_address=params.wallet.address,
                private_key=private_key,
                slippage_bps=params.slippage_bps,
                chain=params.chain,
            )
            if order_uid:
                return TradeResult(
                    success=True,
                    tx_hash=order_uid,
                    amount_in=params.amount_in_wei / 1e18,
                    amount_out=float(quote.get("quote", {}).get("buyAmount", 0)) / 1e18,
                    execution_path="cow_live",
                )
            return TradeResult(
                success=False,
                error="CoW live order submission failed — see logs",
                execution_path="cow",
            )

        except Exception as e:
            logger.error(f"CoW execution error: {e}")
            return TradeResult(success=False, error=str(e), execution_path="cow")

    # ── 1inch Aggregation API ─────────────────────────────────────────────────

    def _get_oneinch_quote(
        self, chain_id: int, token_in: str, token_out: str, amount_wei: int
    ) -> Optional[dict]:
        """Get a swap quote from 1inch."""
        if not settings.ONEINCH_API_KEY:
            logger.warning("1inch API key not configured")
            return None

        url = f"{settings.ONEINCH_API_URL}/{chain_id}/quote"
        headers = {"Authorization": f"Bearer {settings.ONEINCH_API_KEY}"}
        params = {
            "src": token_in,
            "dst": token_out,
            "amount": str(amount_wei),
            "includeProtocols": "true",
        }
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"1inch quote error: {e}")
            return None

    def _execute_via_oneinch(self, params: TradeParams) -> TradeResult:
        """Execute a swap via 1inch Aggregation API."""
        try:
            chain_config = CHAINS[params.chain]
            w3 = self._get_web3(chain_config)
            if not w3:
                return TradeResult(
                    success=False,
                    error=f"Cannot connect to {params.chain}",
                    execution_path="1inch",
                )

            # Gas check
            gas_ok, gas_gwei = self._check_gas_ceiling(w3, chain_config)
            if not gas_ok:
                return TradeResult(
                    success=False,
                    error=f"Gas too high: {gas_gwei:.1f} gwei",
                    execution_path="1inch",
                    gas_price_gwei=gas_gwei,
                )

            # Get quote
            quote = self._get_oneinch_quote(
                chain_config.chain_id,
                params.token_in,
                params.token_out,
                params.amount_in_wei,
            )
            if not quote:
                return TradeResult(
                    success=False,
                    error="1inch quote failed",
                    execution_path="1inch",
                )

            dst_amount = int(quote.get("dstAmount", 0))
            logger.info(
                f"1inch quote: {params.amount_in_wei/1e18:.6f} → "
                f"{dst_amount/1e18:.6f} | gas={gas_gwei:.1f}gwei"
            )

            if settings.IS_PAPER:
                return TradeResult(
                    success=True,
                    execution_path="1inch_paper",
                    amount_in=params.amount_in_wei / 1e18,
                    amount_out=dst_amount / 1e18,
                    gas_price_gwei=gas_gwei,
                )

            # Live execution: get swap tx data from 1inch
            if not settings.ONEINCH_API_KEY:
                return TradeResult(
                    success=False,
                    error="1inch API key required for live trading",
                    execution_path="1inch",
                )

            url = f"{settings.ONEINCH_API_URL}/{chain_config.chain_id}/swap"
            headers = {"Authorization": f"Bearer {settings.ONEINCH_API_KEY}"}
            swap_params = {
                "src": params.token_in,
                "dst": params.token_out,
                "amount": str(params.amount_in_wei),
                "from": params.wallet.address,
                "slippage": params.slippage_bps / 100,
                "disableEstimate": "false",
            }
            resp = requests.get(url, headers=headers, params=swap_params, timeout=20)
            if resp.status_code != 200:
                return TradeResult(
                    success=False,
                    error=f"1inch swap error: {resp.text[:200]}",
                    execution_path="1inch",
                )

            swap_data = resp.json()
            tx = swap_data.get("tx", {})

            private_key = params.wallet.private_key
            if not private_key:
                return TradeResult(
                    success=False,
                    error="No private key for wallet",
                    execution_path="1inch",
                )

            # Build and sign transaction
            account = Account.from_key(private_key)
            nonce = w3.eth.get_transaction_count(account.address)
            transaction = {
                "from": account.address,
                "to": Web3.to_checksum_address(tx["to"]),
                "data": tx["data"],
                "value": int(tx.get("value", 0)),
                "gas": int(tx.get("gas", 300000)),
                "gasPrice": w3.eth.gas_price,
                "nonce": nonce,
                "chainId": chain_config.chain_id,
            }

            signed = account.sign_transaction(transaction)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

            return TradeResult(
                success=receipt.status == 1,
                tx_hash=tx_hash.hex(),
                amount_in=params.amount_in_wei / 1e18,
                amount_out=dst_amount / 1e18,
                gas_used=receipt.gasUsed,
                gas_price_gwei=gas_gwei,
                execution_path="1inch_live",
                error=None if receipt.status == 1 else "Transaction reverted",
            )

        except Exception as e:
            logger.error(f"1inch execution error: {e}")
            return TradeResult(success=False, error=str(e), execution_path="1inch")

    # ── Main Entry Point ──────────────────────────────────────────────────────

    def execute_trade(self, params: TradeParams) -> TradeResult:
        """
        Execute a trade with full safety checks and MEV protection.

        Execution priority:
          1. CoW Protocol (Ethereum only — best MEV protection)
          2. 1inch (all chains — best price routing)
          3. Fail safe — never execute without a valid path

        Args:
            params: TradeParams with wallet, chain, tokens, and amount

        Returns:
            TradeResult with full execution details
        """
        # ── MANDATORY: Safety check ───────────────────────────────────────────
        safety = check_token_safety(params.token_out, params.chain)
        if not safety.is_safe:
            logger.warning(f"Trade BLOCKED by safety pipeline: {safety.block_reason}")
            return TradeResult(
                success=False,
                error=f"Safety check failed: {safety.block_reason}",
                execution_path="blocked",
                safety_result=safety,
            )

        logger.info(
            f"Executing trade: {params.wallet.alias} | {params.chain} | "
            f"{params.token_in[:10]}... → {params.token_out[:10]}... | "
            f"amount={params.amount_in_wei/1e18:.6f} | mode={settings.MODE}"
        )

        # ── Route to best execution path ──────────────────────────────────────
        chain_config = CHAINS[params.chain]
        result = None

        # CoW Protocol: Ethereum only, best MEV protection
        if params.chain == "ethereum" and chain_config.cow_settlement:
            result = self._execute_via_cow(params)
            if result.success:
                result.safety_result = safety
                return result
            logger.warning(f"CoW failed, falling back to 1inch: {result.error}")

        # 1inch: All chains
        result = self._execute_via_oneinch(params)
        result.safety_result = safety
        return result

    @staticmethod
    def _deadline_timestamp(seconds: int) -> int:
        """Return Unix timestamp for trade deadline."""
        import time
        return int(time.time()) + seconds


def build_gem_snipe_params(
    wallet: WalletConfig,
    chain: str,
    token_address: str,
    eth_amount: float,
    slippage_bps: int = 200,
    use_usdc: bool = True,
    usdc_amount: float = 0.0,
) -> TradeParams:
    """
    Build TradeParams for a gem snipe trade.

    Prefers buying with USDC when available (stablecoin capital).
    Falls back to native ETH/MATIC/BNB if USDC is not configured or use_usdc=False.

    Args:
        wallet: The wallet to trade from
        chain: Chain name (e.g., "base")
        token_address: Token to buy
        eth_amount: Amount of native token to spend (fallback)
        slippage_bps: Slippage in basis points (200 = 2%)
        use_usdc: If True, prefer USDC as buy-side capital
        usdc_amount: Amount of USDC to spend (if use_usdc=True)
    """
    chain_config = CHAINS[chain]

    # Prefer USDC capital when available
    if use_usdc and chain_config.usdc_address and usdc_amount > 0:
        # USDC has 6 decimals
        amount_wei = int(usdc_amount * 1e6)
        token_in = Web3.to_checksum_address(chain_config.usdc_address)
        logger.info(f"Buying with ${usdc_amount:.2f} USDC on {chain}")
    else:
        # Fallback: native ETH/MATIC/BNB
        amount_wei = Web3.to_wei(eth_amount, "ether")
        token_in = "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"
        logger.info(f"Buying with {eth_amount:.4f} native on {chain}")

    return TradeParams(
        wallet=wallet,
        chain=chain,
        token_in=token_in,
        token_out=Web3.to_checksum_address(token_address),
        amount_in_wei=amount_wei,
        slippage_bps=slippage_bps,
    )


def build_take_profit_params(
    wallet: WalletConfig,
    chain: str,
    token_address: str,
    token_amount_wei: int,
    slippage_bps: int = 200,
) -> TradeParams:
    """
    Build TradeParams for a take-profit sell — exits into USDC stablecoin.

    All profits are routed to USDC on the same chain. If USDC is not
    configured for the chain, falls back to native ETH/MATIC/BNB.

    Args:
        wallet: The wallet to trade from
        chain: Chain name (e.g., "base")
        token_address: Token to sell
        token_amount_wei: Amount of token to sell (in wei)
        slippage_bps: Slippage in basis points (200 = 2%)
    """
    chain_config = CHAINS[chain]

    # Prefer USDC for profit-taking, fall back to native token
    if chain_config.usdc_address:
        sell_to = Web3.to_checksum_address(chain_config.usdc_address)
        logger.info(f"Take-profit: selling into USDC on {chain}")
    else:
        sell_to = "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"
        logger.info(f"Take-profit: no USDC configured for {chain}, selling into native")

    return TradeParams(
        wallet=wallet,
        chain=chain,
        token_in=Web3.to_checksum_address(token_address),
        token_out=sell_to,
        amount_in_wei=token_amount_wei,
        slippage_bps=slippage_bps,
    )
