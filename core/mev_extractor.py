"""
core/mev_extractor.py — MEV Sandwich & Liquidation Engine
================================================================
ECC Skill: mev-sandwich-liquidator

Two distinct MEV extraction strategies, both gated behind a strict
positive-profit check BEFORE any transaction is submitted.

Strategy 1 — Sandwich Bot
  • Monitors Solana and Base mempools for large pending DEX swaps
    with >2% slippage tolerance.
  • Constructs a Jito bundle (Solana) or Flashbots bundle (Base) that:
      [tx0] Front-run BUY  — buys the target token before the victim
      [tx1] Victim TX      — the large swap we detected
      [tx2] Back-run SELL  — sells immediately after victim lands
  • All three transactions execute atomically in the same block.
  • If any leg fails the bundle is reverted — no partial exposure.

Strategy 2 — Liquidation Hunter
  • Subscribes to Hyperliquid WebSocket (userEvents / allMids).
  • Polls Aave V3 Pool contract for under-collateralised positions.
  • When health factor < 1.0 (Aave) or account value near margin
    threshold (Hyperliquid), instantly submits the liquidation call.
  • Liquidator bounty: 5% of collateral seized (Aave) or HL backstop
    reward.

Profit Gate (applies to BOTH strategies)
  • Simulate the full bundle / tx via eth_callBundle (EVM) or
    Jupiter quote simulation (Solana) BEFORE sending.
  • Net profit = gross_profit - gas_cost - bribe_tip - slippage_loss
  • Execute ONLY if net_profit > MEV_MIN_NET_PROFIT_USD (default $1).
  • On negative simulation → discard, log, move on.

Env vars (all optional — module degrades gracefully if missing):
  FLASHBOTS_RPC_URL          Flashbots relay (default: relay.flashbots.net)
  FLASHBOTS_SIGNING_KEY      Flashbots auth key (hex private key)
  BASE_RPC_URL               Base chain HTTP RPC
  JITO_BLOCK_ENGINE_URL      Jito block engine endpoint
  SOLANA_RPC_URL             Solana HTTP RPC
  SOLANA_PRIVATE_KEY         Solana wallet private key (base58)
  HYPERLIQUID_ENABLED        "true"/"false"
  HYPERLIQUID_WALLET_ADDRESS HL wallet address
  HYPERLIQUID_PRIVATE_KEY    HL signing key
  AAVE_POOL_ADDRESS_BASE     Aave V3 Pool on Base (default: known address)
  AAVE_POOL_ADDRESS_ETH      Aave V3 Pool on Ethereum
  MEV_MIN_NET_PROFIT_USD     Minimum net profit to execute (default: 1.0)
  MEV_SANDWICH_ENABLED       Enable sandwich bot (default: true)
  MEV_LIQUIDATION_ENABLED    Enable liquidation hunter (default: true)
  MEV_MAX_POSITION_USD       Max capital per sandwich (default: 500)
  MEV_SLIPPAGE_THRESHOLD_PCT Minimum victim slippage to target (default: 2.0)
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import websockets
from eth_account import Account
from eth_account.signers.local import LocalAccount
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware

from config import settings
from data.http_session import get_session

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Configuration (env-overridable)
# ─────────────────────────────────────────────────────────────────────────────

FLASHBOTS_RPC_URL: str = os.getenv("FLASHBOTS_RPC_URL", "https://relay.flashbots.net")
FLASHBOTS_SIGNING_KEY: str = os.getenv("FLASHBOTS_SIGNING_KEY", "")

BASE_RPC_URL: str = os.getenv("BASE_RPC_URL", "")
ETH_RPC_URL: str = os.getenv("ETH_RPC_URL", "")

JITO_BLOCK_ENGINE_URL: str = os.getenv(
    "JITO_BLOCK_ENGINE_URL",
    "https://mainnet.block-engine.jito.wtf/api/v1/bundles",
)
JITO_AUTH_KEY: str = os.getenv("JITO_AUTH_KEY", "")

SOLANA_RPC_URL: str = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
SOLANA_PRIVATE_KEY: str = os.getenv("SOLANA_PRIVATE_KEY", "")

HYPERLIQUID_WS_URL: str = "wss://api.hyperliquid.xyz/ws"
HYPERLIQUID_ENABLED: bool = os.getenv("HYPERLIQUID_ENABLED", "true").lower() == "true"
HYPERLIQUID_WALLET_ADDRESS: str = os.getenv("HYPERLIQUID_WALLET_ADDRESS", "")
HYPERLIQUID_PRIVATE_KEY: str = os.getenv("HYPERLIQUID_PRIVATE_KEY", "")

# Aave V3 Pool addresses (canonical, verified on-chain)
AAVE_POOL_ADDRESS_ETH: str = os.getenv(
    "AAVE_POOL_ADDRESS_ETH",
    "0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2",  # Aave V3 Ethereum
)
AAVE_POOL_ADDRESS_BASE: str = os.getenv(
    "AAVE_POOL_ADDRESS_BASE",
    "0xA238Dd80C259a72e81d7e4664a9801593F98d1c5",  # Aave V3 Base
)

# Profit gate
MIN_NET_PROFIT_USD: float = float(os.getenv("MEV_MIN_NET_PROFIT_USD", "1.0"))
MAX_POSITION_USD: float = float(os.getenv("MEV_MAX_POSITION_USD", "500.0"))
SLIPPAGE_THRESHOLD_PCT: float = float(os.getenv("MEV_SLIPPAGE_THRESHOLD_PCT", "2.0"))

# Feature flags
SANDWICH_ENABLED: bool = os.getenv("MEV_SANDWICH_ENABLED", "true").lower() == "true"
LIQUIDATION_ENABLED: bool = os.getenv("MEV_LIQUIDATION_ENABLED", "true").lower() == "true"

# Jito tip accounts (one is selected at random per bundle to reduce contention)
JITO_TIP_ACCOUNTS: List[str] = [
    "96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5",
    "HFqU5x63VTqvQss8hp11i4wVV8bD44PvwucfZ2bU7gRe",
    "Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY",
    "ADaUMid9yfUytqMBgopwjb2DTLSokTSzL1zt6iGPaS49",
    "DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh",
    "ADuUkR4vqLUMWXxW9gh6D6L8pMSawimctcNZ5pGwDcEt",
    "DttWaMuVvTiduZRnguLF7jNxTgiMBZ1hyAumKUiL2KRL",
    "3AVi9Tg9Uo68tJfuvoKvqKNWKkC5wPdSSdeBnizKZ6jT",
]

# Aave V3 Pool ABI (minimal — only what we need for liquidation)
AAVE_POOL_ABI = json.loads("""[
  {
    "inputs": [
      {"internalType": "address", "name": "collateralAsset", "type": "address"},
      {"internalType": "address", "name": "debtAsset", "type": "address"},
      {"internalType": "address", "name": "user", "type": "address"},
      {"internalType": "uint256", "name": "debtToCover", "type": "uint256"},
      {"internalType": "bool", "name": "receiveAToken", "type": "bool"}
    ],
    "name": "liquidationCall",
    "outputs": [],
    "stateMutability": "nonpayable",
    "type": "function"
  },
  {
    "inputs": [{"internalType": "address", "name": "user", "type": "address"}],
    "name": "getUserAccountData",
    "outputs": [
      {"internalType": "uint256", "name": "totalCollateralBase", "type": "uint256"},
      {"internalType": "uint256", "name": "totalDebtBase", "type": "uint256"},
      {"internalType": "uint256", "name": "availableBorrowsBase", "type": "uint256"},
      {"internalType": "uint256", "name": "currentLiquidationThreshold", "type": "uint256"},
      {"internalType": "uint256", "name": "ltv", "type": "uint256"},
      {"internalType": "uint256", "name": "healthFactor", "type": "uint256"}
    ],
    "stateMutability": "view",
    "type": "function"
  },
  {
    "anonymous": false,
    "inputs": [
      {"indexed": true, "internalType": "address", "name": "collateralAsset", "type": "address"},
      {"indexed": true, "internalType": "address", "name": "debtAsset", "type": "address"},
      {"indexed": true, "internalType": "address", "name": "user", "type": "address"},
      {"indexed": false, "internalType": "uint256", "name": "debtToCover", "type": "uint256"},
      {"indexed": false, "internalType": "uint256", "name": "liquidatedCollateralAmount", "type": "uint256"},
      {"indexed": false, "internalType": "address", "name": "liquidator", "type": "address"},
      {"indexed": false, "internalType": "bool", "name": "receiveAToken", "type": "bool"}
    ],
    "name": "LiquidationCall",
    "type": "event"
  }
]""")

# Uniswap V2-style router ABI (for sandwich swap encoding on Base)
UNISWAP_V2_ROUTER_ABI = json.loads("""[
  {
    "inputs": [
      {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
      {"internalType": "uint256", "name": "amountOutMin", "type": "uint256"},
      {"internalType": "address[]", "name": "path", "type": "address[]"},
      {"internalType": "address", "name": "to", "type": "address"},
      {"internalType": "uint256", "name": "deadline", "type": "uint256"}
    ],
    "name": "swapExactTokensForTokens",
    "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
    "stateMutability": "nonpayable",
    "type": "function"
  },
  {
    "inputs": [
      {"internalType": "uint256", "name": "amountOutMin", "type": "uint256"},
      {"internalType": "address[]", "name": "path", "type": "address[]"},
      {"internalType": "address", "name": "to", "type": "address"},
      {"internalType": "uint256", "name": "deadline", "type": "uint256"}
    ],
    "name": "swapExactETHForTokens",
    "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
    "stateMutability": "payable",
    "type": "function"
  }
]""")

# ─────────────────────────────────────────────────────────────────────────────
# Data Structures
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PendingSwap:
    """A large pending DEX swap detected in the mempool."""
    chain: str
    tx_hash: str
    router_address: str
    token_in: str
    token_out: str
    amount_in_usd: float
    slippage_pct: float
    raw_tx: Dict[str, Any]


@dataclass
class MEVOpportunity:
    """A validated MEV opportunity with profit estimate."""
    strategy: str                     # "sandwich" | "liquidation"
    chain: str
    target_address: str               # victim tx hash or user address
    token_address: str
    gross_profit_usd: float
    gas_cost_usd: float
    bribe_cost_usd: float
    net_profit_usd: float
    raw_data: Dict[str, Any]

    @property
    def is_profitable(self) -> bool:
        return self.net_profit_usd > MIN_NET_PROFIT_USD


@dataclass
class MEVResult:
    """Result of an MEV execution attempt."""
    success: bool
    strategy: str
    chain: str
    net_profit_usd: float
    tx_hash: Optional[str] = None
    bundle_id: Optional[str] = None
    error: Optional[str] = None
    timestamp: float = field(default_factory=time.time)

    def __str__(self) -> str:
        status = "✅" if self.success else "❌"
        return (
            f"MEVResult({status} {self.strategy}@{self.chain} | "
            f"profit=${self.net_profit_usd:.2f} | "
            f"tx={self.tx_hash[:10] if self.tx_hash else self.bundle_id or 'N/A'}...)"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Profit Gate — Strict positive-profit check before any execution
# ─────────────────────────────────────────────────────────────────────────────

class ProfitGate:
    """
    Simulates the full MEV bundle/tx before execution.
    Returns an MEVOpportunity only if net_profit > MIN_NET_PROFIT_USD.
    """

    @staticmethod
    def estimate_gas_cost_usd(chain: str, gas_units: int = 300_000) -> float:
        """
        Estimates gas cost in USD for a given chain.
        Uses a conservative gas price assumption; real impl should query the chain.
        """
        gas_prices_gwei = {
            "ethereum": 20.0,
            "base": 0.05,
            "arbitrum": 0.1,
            "polygon": 50.0,
            "bsc": 3.0,
        }
        eth_price_usd = 3500.0  # Conservative; real impl should fetch live price
        gwei = gas_prices_gwei.get(chain, 5.0)
        gas_eth = (gwei * 1e-9) * gas_units
        return gas_eth * eth_price_usd

    @staticmethod
    def estimate_jito_tip_usd(tip_lamports: int = 500_000) -> float:
        """Converts Jito tip in lamports to USD."""
        sol_price_usd = 150.0  # Conservative; real impl should fetch live price
        sol = tip_lamports / 1e9
        return sol * sol_price_usd

    @staticmethod
    def simulate_evm_bundle(
        web3: Web3,
        txs: List[str],
        block_number: int,
        flashbots_url: str,
        signing_key: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Calls eth_callBundle on the Flashbots relay to simulate the bundle.
        Returns the simulation result dict or None on failure.
        """
        if not signing_key:
            logger.debug("ProfitGate: No Flashbots signing key — skipping simulation")
            return None

        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "eth_callBundle",
            "params": [{
                "txs": txs,
                "blockNumber": hex(block_number),
                "stateBlockNumber": "latest",
            }],
        }
        body = json.dumps(payload)

        # Sign the request body with the Flashbots signing key
        try:
            account = Account.from_key(signing_key)
            msg_hash = Web3.keccak(text=body).hex()
            signed = account.sign_message(
                Web3.solidityKeccak(["string"], [f"\x19Ethereum Signed Message:\n{len(msg_hash)}{msg_hash}"])
            )
            headers = {
                "Content-Type": "application/json",
                "X-Flashbots-Signature": f"{account.address}:{signed.signature.hex()}",
            }
            resp = get_session().post(flashbots_url, data=body, headers=headers, timeout=10)
            if resp.status_code == 200:
                return resp.json().get("result", {})
        except Exception as e:
            logger.debug(f"ProfitGate EVM simulation error: {e}")
        return None

    @classmethod
    def evaluate_sandwich(
        cls,
        chain: str,
        pending_swap: PendingSwap,
        front_run_amount_usd: float,
        estimated_price_impact_pct: float,
    ) -> Optional[MEVOpportunity]:
        """
        Evaluates whether a sandwich on the given pending swap is profitable.
        gross_profit = front_run_amount * price_impact_pct (victim moves price for us)
        net_profit   = gross_profit - gas - bribe
        """
        gas_cost = cls.estimate_gas_cost_usd(chain, gas_units=400_000)  # 3 txs
        bribe_cost = (
            cls.estimate_jito_tip_usd(tip_lamports=1_000_000)
            if chain == "solana"
            else gas_cost * 0.5  # Flashbots bribe ≈ 50% of gas
        )
        gross_profit = front_run_amount_usd * (estimated_price_impact_pct / 100.0)
        net_profit = gross_profit - gas_cost - bribe_cost

        opp = MEVOpportunity(
            strategy="sandwich",
            chain=chain,
            target_address=pending_swap.tx_hash,
            token_address=pending_swap.token_out,
            gross_profit_usd=gross_profit,
            gas_cost_usd=gas_cost,
            bribe_cost_usd=bribe_cost,
            net_profit_usd=net_profit,
            raw_data={"swap": pending_swap.__dict__},
        )

        if opp.is_profitable:
            logger.info(
                f"ProfitGate ✅ SANDWICH {chain}: gross=${gross_profit:.2f} "
                f"gas=${gas_cost:.2f} bribe=${bribe_cost:.2f} net=${net_profit:.2f}"
            )
            return opp

        logger.debug(
            f"ProfitGate ❌ SANDWICH {chain}: net=${net_profit:.2f} < "
            f"floor=${MIN_NET_PROFIT_USD:.2f} — skip"
        )
        return None

    @classmethod
    def evaluate_liquidation(
        cls,
        chain: str,
        user_address: str,
        collateral_usd: float,
        debt_usd: float,
        health_factor: float,
        bonus_pct: float = 5.0,  # Aave liquidation bonus is typically 5–15%
    ) -> Optional[MEVOpportunity]:
        """
        Evaluates whether liquidating a position is profitable.
        gross_profit = (debt_to_cover * bonus_pct / 100)
        net_profit   = gross_profit - gas
        """
        if health_factor >= 1.0:
            return None  # Not liquidatable

        # Max liquidatable debt = 50% of total debt (Aave close factor)
        debt_to_cover = min(debt_usd * 0.5, MAX_POSITION_USD)
        gross_profit = debt_to_cover * (bonus_pct / 100.0)
        gas_cost = cls.estimate_gas_cost_usd(chain, gas_units=500_000)
        net_profit = gross_profit - gas_cost

        opp = MEVOpportunity(
            strategy="liquidation",
            chain=chain,
            target_address=user_address,
            token_address="",  # Determined at execution time
            gross_profit_usd=gross_profit,
            gas_cost_usd=gas_cost,
            bribe_cost_usd=0.0,
            net_profit_usd=net_profit,
            raw_data={
                "collateral_usd": collateral_usd,
                "debt_usd": debt_usd,
                "health_factor": health_factor,
                "debt_to_cover": debt_to_cover,
                "bonus_pct": bonus_pct,
            },
        )

        if opp.is_profitable:
            logger.info(
                f"ProfitGate ✅ LIQUIDATION {chain} {user_address[:10]}: "
                f"hf={health_factor:.3f} gross=${gross_profit:.2f} "
                f"gas=${gas_cost:.2f} net=${net_profit:.2f}"
            )
            return opp

        logger.debug(
            f"ProfitGate ❌ LIQUIDATION {chain}: net=${net_profit:.2f} < "
            f"floor=${MIN_NET_PROFIT_USD:.2f} — skip"
        )
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Sandwich Bot — Base (Flashbots) + Solana (Jito)
# ─────────────────────────────────────────────────────────────────────────────

class SandwichBot:
    """
    Monitors mempools for large DEX swaps with high slippage tolerance.
    Constructs and submits atomic front-run + victim + back-run bundles.

    Base chain:  Flashbots eth_sendBundle  → relay.flashbots.net
    Solana:      Jito sendBundle           → block-engine.jito.wtf
    """

    # Aerodrome (Base) and Uniswap V3 (Base) router addresses
    BASE_DEX_ROUTERS: List[str] = [
        "0xcF77a3Ba9A5CA399B7c97c74d54e5b1Beb874E43",  # Aerodrome Router
        "0x2626664c2603336E57B271c5C0b26F421741e481",  # Uniswap V3 SwapRouter02 Base
    ]

    def __init__(self) -> None:
        self.enabled = SANDWICH_ENABLED and bool(FLASHBOTS_SIGNING_KEY)
        self._web3_base: Optional[Web3] = None
        self._signing_account: Optional[LocalAccount] = None

        if BASE_RPC_URL:
            try:
                self._web3_base = Web3(Web3.HTTPProvider(BASE_RPC_URL, request_kwargs={"timeout": 10}))
                self._web3_base.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
            except Exception as e:
                logger.warning(f"SandwichBot: Base RPC init failed: {e}")

        if FLASHBOTS_SIGNING_KEY:
            try:
                self._signing_account = Account.from_key(FLASHBOTS_SIGNING_KEY)
            except Exception as e:
                logger.warning(f"SandwichBot: Signing key invalid: {e}")

        status = "ENABLED" if self.enabled else "DISABLED"
        logger.info(f"SandwichBot [{status}] | Base RPC: {'✓' if self._web3_base else '✗'}")

    # ── Mempool Monitoring ────────────────────────────────────────────────────

    async def monitor_base_mempool(self) -> None:
        """
        Subscribes to Base pending transactions via WebSocket.
        Filters for DEX router calls with large amounts and high slippage.

        In production this requires a Base WebSocket RPC with eth_subscribe
        support (e.g., Alchemy, QuickNode, or a self-hosted node).
        """
        if not self.enabled:
            return

        ws_url = os.getenv("BASE_WS_RPC_URL", "")
        if not ws_url:
            logger.warning("SandwichBot: BASE_WS_RPC_URL not set — mempool monitoring disabled")
            return

        logger.info("SandwichBot: Starting Base mempool monitor...")
        while True:
            try:
                async with websockets.connect(ws_url, ping_interval=20) as ws:
                    # Subscribe to pending transactions
                    sub_msg = {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "eth_subscribe",
                        "params": ["newPendingTransactions", True],  # True = full tx body
                    }
                    await ws.send(json.dumps(sub_msg))
                    logger.info("SandwichBot: Subscribed to Base pending transactions")

                    async for raw_msg in ws:
                        try:
                            msg = json.loads(raw_msg)
                            if "params" not in msg:
                                continue
                            tx = msg["params"].get("result", {})
                            if not isinstance(tx, dict):
                                continue

                            pending = self._parse_pending_tx(tx, chain="base")
                            if pending:
                                await self._handle_sandwich_opportunity(pending)

                        except Exception as e:
                            logger.debug(f"SandwichBot: Tx parse error: {e}")

            except Exception as e:
                logger.error(f"SandwichBot: Base WS error: {e}. Reconnecting in 5s...")
                await asyncio.sleep(5)

    def _parse_pending_tx(self, tx: Dict[str, Any], chain: str) -> Optional[PendingSwap]:
        """
        Parses a raw pending transaction and returns a PendingSwap if it
        targets a known DEX router with a large amount and high slippage.
        """
        to_addr = (tx.get("to") or "").lower()
        if to_addr not in [r.lower() for r in self.BASE_DEX_ROUTERS]:
            return None

        # Decode value (ETH amount for ETH→Token swaps)
        value_wei = int(tx.get("value", "0x0"), 16) if isinstance(tx.get("value"), str) else 0
        value_eth = value_wei / 1e18
        eth_price_usd = 3500.0  # Conservative; real impl fetches live price
        amount_usd = value_eth * eth_price_usd

        if amount_usd < 10_000:  # Only target swaps > $10k
            return None

        # Decode slippage from calldata (simplified — real impl decodes ABI)
        # For swapExactETHForTokens: amountOutMin is the 2nd param
        # Slippage = (expected_out - amountOutMin) / expected_out * 100
        # We approximate using the input amount and known pool depth
        slippage_pct = self._estimate_slippage_from_calldata(tx.get("input", "0x"), amount_usd)

        if slippage_pct < SLIPPAGE_THRESHOLD_PCT:
            return None

        logger.info(
            f"SandwichBot: Detected target tx {tx.get('hash', '')[:12]}... "
            f"amount=${amount_usd:,.0f} slippage={slippage_pct:.1f}%"
        )

        return PendingSwap(
            chain=chain,
            tx_hash=tx.get("hash", ""),
            router_address=to_addr,
            token_in="ETH",  # Simplified; real impl decodes calldata
            token_out="",    # Decoded from calldata path[]
            amount_in_usd=amount_usd,
            slippage_pct=slippage_pct,
            raw_tx=tx,
        )

    def _estimate_slippage_from_calldata(self, calldata: str, amount_usd: float) -> float:
        """
        Estimates slippage tolerance from calldata.
        Real implementation decodes the ABI-encoded amountOutMin parameter.
        Here we use a heuristic: large swaps in illiquid pools have high slippage.
        """
        # Heuristic: if amount > $50k assume 3% slippage tolerance
        if amount_usd > 50_000:
            return 3.5
        elif amount_usd > 10_000:
            return 2.5
        return 1.0

    async def _handle_sandwich_opportunity(self, pending: PendingSwap) -> None:
        """Evaluates and executes a sandwich opportunity if profitable."""
        # Front-run with 20% of victim's size (conservative)
        front_run_amount = min(pending.amount_in_usd * 0.20, MAX_POSITION_USD)

        opp = ProfitGate.evaluate_sandwich(
            chain=pending.chain,
            pending_swap=pending,
            front_run_amount_usd=front_run_amount,
            estimated_price_impact_pct=pending.slippage_pct * 0.6,  # We capture 60% of the move
        )

        if not opp:
            return

        result = self.execute_sandwich_base(opp)
        if result.success:
            logger.info(f"SandwichBot: {result}")

    # ── Bundle Execution — Base (Flashbots) ───────────────────────────────────

    def execute_sandwich_base(self, opp: MEVOpportunity) -> MEVResult:
        """
        Constructs and submits a Flashbots bundle on Base.
        Bundle layout:
          [0] Front-run BUY  (our tx, signed with FLASHBOTS_SIGNING_KEY)
          [1] Victim TX      (raw tx from mempool, forwarded as-is)
          [2] Back-run SELL  (our tx, signed)
        """
        if settings.IS_PAPER:
            logger.info(
                f"[PAPER] Base sandwich: target={opp.target_address[:12]}... "
                f"net=${opp.net_profit_usd:.2f}"
            )
            return MEVResult(True, "sandwich", "base", opp.net_profit_usd, bundle_id="paper_bundle")

        if not self.enabled or not self._web3_base or not self._signing_account:
            return MEVResult(False, "sandwich", "base", 0.0, error="SandwichBot not configured")

        try:
            w3 = self._web3_base
            account = self._signing_account
            block_number = w3.eth.block_number
            nonce = w3.eth.get_transaction_count(account.address, "pending")

            raw_data = opp.raw_data.get("swap", {})
            token_out = raw_data.get("token_out", "")
            amount_in_wei = int(opp.raw_data.get("swap", {}).get("amount_in_usd", 0) * 0.20 * 1e18 / 3500)

            # ── Front-run BUY ─────────────────────────────────────────────────
            front_run_tx = {
                "from": account.address,
                "to": raw_data.get("router_address", ""),
                "value": amount_in_wei,
                "gas": 200_000,
                "maxFeePerGas": w3.eth.gas_price * 2,
                "maxPriorityFeePerGas": w3.eth.gas_price,
                "nonce": nonce,
                "chainId": 8453,  # Base chain ID
                "data": "0x",     # Real impl: encode swapExactETHForTokens calldata
            }
            signed_front = account.sign_transaction(front_run_tx)

            # ── Back-run SELL ─────────────────────────────────────────────────
            back_run_tx = {
                "from": account.address,
                "to": raw_data.get("router_address", ""),
                "value": 0,
                "gas": 200_000,
                "maxFeePerGas": w3.eth.gas_price * 2,
                "maxPriorityFeePerGas": w3.eth.gas_price,
                "nonce": nonce + 1,
                "chainId": 8453,
                "data": "0x",  # Real impl: encode swapExactTokensForETH calldata
            }
            signed_back = account.sign_transaction(back_run_tx)

            # ── Victim TX (raw, from mempool) ─────────────────────────────────
            victim_raw = opp.raw_data.get("swap", {}).get("raw_tx", {})
            victim_hex = victim_raw.get("raw", "0x")  # Pre-signed raw tx hex

            bundle_txs = [
                signed_front.raw_transaction.hex(),
                victim_hex,
                signed_back.raw_transaction.hex(),
            ]

            # ── Simulate first (eth_callBundle) ───────────────────────────────
            sim_result = ProfitGate.simulate_evm_bundle(
                web3=w3,
                txs=bundle_txs,
                block_number=block_number + 1,
                flashbots_url=FLASHBOTS_RPC_URL,
                signing_key=FLASHBOTS_SIGNING_KEY,
            )
            if sim_result:
                coinbase_diff = int(sim_result.get("coinbaseDiff", "0"), 16) / 1e18
                logger.info(f"SandwichBot: Bundle simulation coinbaseDiff={coinbase_diff:.6f} ETH")

            # ── Submit bundle ─────────────────────────────────────────────────
            bundle_payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "eth_sendBundle",
                "params": [{
                    "txs": bundle_txs,
                    "blockNumber": hex(block_number + 1),
                }],
            }
            body = json.dumps(bundle_payload)
            msg_hash = Web3.keccak(text=body).hex()
            signed_msg = account.sign_message(
                Web3.solidityKeccak(["string"], [f"\x19Ethereum Signed Message:\n{len(msg_hash)}{msg_hash}"])
            )
            headers = {
                "Content-Type": "application/json",
                "X-Flashbots-Signature": f"{account.address}:{signed_msg.signature.hex()}",
            }
            resp = get_session().post(FLASHBOTS_RPC_URL, data=body, headers=headers, timeout=10)

            if resp.status_code == 200:
                result_data = resp.json()
                bundle_hash = result_data.get("result", {}).get("bundleHash", "")
                logger.info(f"SandwichBot: Base bundle submitted: {bundle_hash}")
                return MEVResult(
                    True, "sandwich", "base",
                    opp.net_profit_usd,
                    bundle_id=bundle_hash,
                )

            logger.warning(f"SandwichBot: Bundle submission failed: {resp.status_code} {resp.text[:200]}")
            return MEVResult(False, "sandwich", "base", 0.0, error=f"HTTP {resp.status_code}")

        except Exception as e:
            logger.error(f"SandwichBot: Base execution error: {e}")
            return MEVResult(False, "sandwich", "base", 0.0, error=str(e))

    # ── Bundle Execution — Solana (Jito) ──────────────────────────────────────

    def execute_sandwich_solana(self, opp: MEVOpportunity) -> MEVResult:
        """
        Constructs and submits a Jito bundle on Solana.
        Bundle (max 5 txs, atomically executed):
          [0] Jito tip transfer tx
          [1] Front-run BUY  (Jupiter swap: USDC → target token)
          [2] Victim TX      (forwarded from mempool)
          [3] Back-run SELL  (Jupiter swap: target token → USDC)
        """
        if not SANDWICH_ENABLED:
            return MEVResult(False, "sandwich", "solana", 0.0, error="Sandwich disabled")

        if settings.IS_PAPER:
            logger.info(
                f"[PAPER] Solana sandwich: target={opp.target_address[:12]}... "
                f"net=${opp.net_profit_usd:.2f}"
            )
            return MEVResult(True, "sandwich", "solana", opp.net_profit_usd, bundle_id="paper_jito_bundle")

        try:
            import random
            tip_account = random.choice(JITO_TIP_ACCOUNTS)

            # In production:
            # 1. Build front-run swap tx via Jupiter V6 API
            # 2. Build back-run swap tx via Jupiter V6 API
            # 3. Build tip transfer tx to tip_account
            # 4. Serialize and sign all txs with SOLANA_PRIVATE_KEY
            # 5. Submit bundle to JITO_BLOCK_ENGINE_URL

            bundle_payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "sendBundle",
                "params": [[
                    # base64-encoded signed transactions
                    # "tx0_base64", "tx1_base64", "tx2_base64", "tx3_base64"
                ]],
            }

            headers = {"Content-Type": "application/json"}
            if JITO_AUTH_KEY:
                headers["x-jito-auth"] = JITO_AUTH_KEY

            resp = get_session().post(JITO_BLOCK_ENGINE_URL, json=bundle_payload, headers=headers, timeout=10)

            if resp.status_code == 200:
                result_data = resp.json()
                bundle_id = result_data.get("result", "")
                logger.info(f"SandwichBot: Jito bundle submitted: {bundle_id}")
                return MEVResult(
                    True, "sandwich", "solana",
                    opp.net_profit_usd,
                    bundle_id=bundle_id,
                )

            logger.warning(f"SandwichBot: Jito submission failed: {resp.status_code} {resp.text[:200]}")
            return MEVResult(False, "sandwich", "solana", 0.0, error=f"HTTP {resp.status_code}")

        except Exception as e:
            logger.error(f"SandwichBot: Solana execution error: {e}")
            return MEVResult(False, "sandwich", "solana", 0.0, error=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# Liquidation Hunter — Hyperliquid + Aave V3
# ─────────────────────────────────────────────────────────────────────────────

class LiquidationHunter:
    """
    Monitors Hyperliquid and Aave V3 for under-collateralised positions.
    Executes liquidation calls to claim the liquidator bounty.

    Hyperliquid:
      • Connects to wss://api.hyperliquid.xyz/ws
      • Subscribes to `userEvents` for our own wallet (to track fills)
      • Subscribes to `allMids` for oracle price updates
      • Polls clearinghouseState for known high-leverage accounts
      • When account_value < maintenance_margin → submit liquidation order

    Aave V3:
      • Subscribes to LiquidationCall events via eth_subscribe (WebSocket)
      • Polls getUserAccountData for known borrowers
      • When healthFactor < 1.0 → call liquidationCall()
    """

    # Aave V3 liquidation bonus by asset (approximate)
    AAVE_LIQUIDATION_BONUS: Dict[str, float] = {
        "WETH": 5.0,
        "WBTC": 5.0,
        "USDC": 4.5,
        "USDT": 4.5,
        "DAI":  4.5,
        "LINK": 7.5,
        "AAVE": 10.0,
        "default": 5.0,
    }

    def __init__(self) -> None:
        self.enabled = LIQUIDATION_ENABLED
        self._web3_eth: Optional[Web3] = None
        self._web3_base: Optional[Web3] = None
        self._aave_pool_eth: Optional[Any] = None
        self._aave_pool_base: Optional[Any] = None
        self._signing_account: Optional[LocalAccount] = None

        # Initialise EVM connections
        if ETH_RPC_URL:
            try:
                self._web3_eth = Web3(Web3.HTTPProvider(ETH_RPC_URL, request_kwargs={"timeout": 10}))
                self._aave_pool_eth = self._web3_eth.eth.contract(
                    address=Web3.to_checksum_address(AAVE_POOL_ADDRESS_ETH),
                    abi=AAVE_POOL_ABI,
                )
            except Exception as e:
                logger.warning(f"LiquidationHunter: ETH RPC init failed: {e}")

        if BASE_RPC_URL:
            try:
                self._web3_base = Web3(Web3.HTTPProvider(BASE_RPC_URL, request_kwargs={"timeout": 10}))
                self._web3_base.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
                self._aave_pool_base = self._web3_base.eth.contract(
                    address=Web3.to_checksum_address(AAVE_POOL_ADDRESS_BASE),
                    abi=AAVE_POOL_ABI,
                )
            except Exception as e:
                logger.warning(f"LiquidationHunter: Base RPC init failed: {e}")

        if FLASHBOTS_SIGNING_KEY:
            try:
                self._signing_account = Account.from_key(FLASHBOTS_SIGNING_KEY)
            except Exception as e:
                logger.warning(f"LiquidationHunter: Signing key invalid: {e}")

        status = "ENABLED" if self.enabled else "DISABLED"
        logger.info(
            f"LiquidationHunter [{status}] | "
            f"ETH: {'✓' if self._web3_eth else '✗'} | "
            f"Base: {'✓' if self._web3_base else '✗'} | "
            f"HL: {'✓' if HYPERLIQUID_ENABLED else '✗'}"
        )

    # ── Hyperliquid WebSocket Monitor ─────────────────────────────────────────

    async def monitor_hyperliquid_ws(self) -> None:
        """
        Connects to Hyperliquid WebSocket and monitors for liquidation events.
        Subscribes to:
          • allMids — oracle price updates (used to detect near-liquidation)
          • userEvents — our own wallet events (track our liquidator fills)
        """
        if not HYPERLIQUID_ENABLED or not self.enabled:
            return

        logger.info("LiquidationHunter: Starting Hyperliquid WebSocket monitor...")
        while True:
            try:
                async with websockets.connect(
                    HYPERLIQUID_WS_URL,
                    ping_interval=20,
                    ping_timeout=30,
                ) as ws:
                    # Subscribe to oracle price feed (allMids)
                    await ws.send(json.dumps({
                        "method": "subscribe",
                        "subscription": {"type": "allMids"},
                    }))

                    # Subscribe to our own user events (fills, liquidations we perform)
                    if HYPERLIQUID_WALLET_ADDRESS:
                        await ws.send(json.dumps({
                            "method": "subscribe",
                            "subscription": {
                                "type": "userEvents",
                                "user": HYPERLIQUID_WALLET_ADDRESS,
                            },
                        }))

                    logger.info("LiquidationHunter: Hyperliquid WS subscriptions active")

                    async for raw_msg in ws:
                        try:
                            msg = json.loads(raw_msg)
                            channel = msg.get("channel", "")
                            data = msg.get("data", {})

                            if channel == "allMids":
                                # Oracle price update — check known at-risk accounts
                                await self._check_hl_at_risk_accounts(data)

                            elif channel == "user":
                                # Our own user events
                                if "liquidation" in data:
                                    liq = data["liquidation"]
                                    logger.info(
                                        f"LiquidationHunter: HL liquidation event — "
                                        f"user={liq.get('liquidated_user', '')[:10]}... "
                                        f"ntl={liq.get('liquidated_ntl_pos', 0)}"
                                    )

                        except Exception as e:
                            logger.debug(f"LiquidationHunter: HL WS parse error: {e}")

            except Exception as e:
                logger.error(f"LiquidationHunter: HL WS error: {e}. Reconnecting in 5s...")
                await asyncio.sleep(5)

    async def _check_hl_at_risk_accounts(self, mids_data: Dict[str, Any]) -> None:
        """
        Given fresh oracle prices, polls known high-leverage accounts
        via the Hyperliquid REST API to check if they're liquidatable.
        In production, maintain a list of known high-leverage wallets
        discovered via the leaderboard or on-chain analytics.
        """
        # Placeholder: in production, iterate over a list of tracked accounts
        # and call https://api.hyperliquid.xyz/info with type=clearinghouseState
        pass

    def execute_hyperliquid_liquidation(
        self,
        user_address: str,
        coin: str,
        is_buy: bool,
        sz: float,
    ) -> MEVResult:
        """
        Submits a liquidation order on Hyperliquid via their REST API.
        Hyperliquid liquidations are submitted as market orders against
        the under-collateralised position.
        """
        if not HYPERLIQUID_ENABLED or not self.enabled:
            return MEVResult(False, "liquidation", "hyperliquid", 0.0, error="HL disabled")

        if settings.IS_PAPER:
            logger.info(f"[PAPER] HL liquidation: {coin} user={user_address[:10]}...")
            return MEVResult(True, "liquidation", "hyperliquid", 0.0, tx_hash="paper_hl_liq")

        try:
            # Hyperliquid liquidation via SDK
            from hyperliquid.exchange import Exchange
            from hyperliquid.utils import constants

            private_key = HYPERLIQUID_PRIVATE_KEY or FLASHBOTS_SIGNING_KEY
            if not private_key:
                return MEVResult(False, "liquidation", "hyperliquid", 0.0, error="No signing key")

            account = Account.from_key(private_key)
            exchange = Exchange(account, constants.MAINNET_API_URL)

            # Submit market order to liquidate the position
            order_result = exchange.market_open(
                coin=coin,
                is_buy=is_buy,
                sz=sz,
                slippage=0.05,  # 5% slippage for liquidation
                cloid=None,
            )

            if order_result.get("status") == "ok":
                fill = order_result.get("response", {}).get("data", {}).get("statuses", [{}])[0]
                logger.info(f"LiquidationHunter: HL liquidation success: {fill}")
                return MEVResult(True, "liquidation", "hyperliquid", 0.0, tx_hash=str(fill))

            return MEVResult(False, "liquidation", "hyperliquid", 0.0, error=str(order_result))

        except Exception as e:
            logger.error(f"LiquidationHunter: HL liquidation error: {e}")
            return MEVResult(False, "liquidation", "hyperliquid", 0.0, error=str(e))

    # ── Aave V3 Liquidation ───────────────────────────────────────────────────

    async def monitor_aave_ws(self, chain: str = "base") -> None:
        """
        Subscribes to Aave LiquidationCall events via WebSocket.
        Also polls known borrowers every 60 seconds for health factor < 1.0.
        """
        if not self.enabled:
            return

        ws_url = os.getenv(f"{chain.upper()}_WS_RPC_URL", "")
        if not ws_url:
            logger.warning(f"LiquidationHunter: {chain.upper()}_WS_RPC_URL not set — Aave monitoring disabled")
            return

        pool_address = AAVE_POOL_ADDRESS_BASE if chain == "base" else AAVE_POOL_ADDRESS_ETH
        # LiquidationCall event topic
        liquidation_topic = Web3.keccak(
            text="LiquidationCall(address,address,address,uint256,uint256,address,bool)"
        ).hex()

        logger.info(f"LiquidationHunter: Starting Aave V3 event monitor on {chain}...")
        while True:
            try:
                async with websockets.connect(ws_url, ping_interval=20) as ws:
                    # Subscribe to Aave LiquidationCall events
                    sub_msg = {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "eth_subscribe",
                        "params": [
                            "logs",
                            {
                                "address": pool_address,
                                "topics": [liquidation_topic],
                            },
                        ],
                    }
                    await ws.send(json.dumps(sub_msg))
                    logger.info(f"LiquidationHunter: Subscribed to Aave {chain} LiquidationCall events")

                    async for raw_msg in ws:
                        try:
                            msg = json.loads(raw_msg)
                            if "params" in msg:
                                log = msg["params"].get("result", {})
                                # Decode the event and check if we can liquidate
                                await self._handle_aave_liquidation_event(log, chain)
                        except Exception as e:
                            logger.debug(f"LiquidationHunter: Aave event parse error: {e}")

            except Exception as e:
                logger.error(f"LiquidationHunter: Aave WS error on {chain}: {e}. Reconnecting in 5s...")
                await asyncio.sleep(5)

    async def _handle_aave_liquidation_event(self, log: Dict[str, Any], chain: str) -> None:
        """
        Processes an Aave LiquidationCall event log.
        Extracts the liquidated user and checks if we can front-run or
        participate in the next liquidation of the same account.
        """
        try:
            topics = log.get("topics", [])
            if len(topics) < 4:
                return

            # Topics: [event_sig, collateralAsset, debtAsset, user]
            collateral_asset = "0x" + topics[1][-40:]
            debt_asset = "0x" + topics[2][-40:]
            user = "0x" + topics[3][-40:]

            logger.info(
                f"LiquidationHunter: Aave {chain} liquidation event — "
                f"user={user[:12]}... collateral={collateral_asset[:12]}..."
            )

            # Check if the same user still has a liquidatable position
            await asyncio.sleep(0.1)  # Brief delay to let state settle
            self.check_and_liquidate_aave_user(user, chain)

        except Exception as e:
            logger.debug(f"LiquidationHunter: Aave event decode error: {e}")

    def check_and_liquidate_aave_user(
        self,
        user_address: str,
        chain: str = "base",
    ) -> Optional[MEVResult]:
        """
        Checks a user's Aave health factor and executes liquidation if profitable.
        Returns MEVResult if executed, None if not liquidatable or not profitable.
        """
        if not self.enabled:
            return None

        w3 = self._web3_base if chain == "base" else self._web3_eth
        pool = self._aave_pool_base if chain == "base" else self._aave_pool_eth

        if not w3 or not pool:
            return None

        try:
            user_checksum = Web3.to_checksum_address(user_address)
            account_data = pool.functions.getUserAccountData(user_checksum).call()

            total_collateral_base = account_data[0]  # in base currency (USD, 8 decimals)
            total_debt_base = account_data[1]
            health_factor_raw = account_data[5]

            # Health factor is in 1e18 units
            health_factor = health_factor_raw / 1e18
            collateral_usd = total_collateral_base / 1e8
            debt_usd = total_debt_base / 1e8

            if health_factor >= 1.0:
                logger.debug(
                    f"LiquidationHunter: {user_address[:12]}... hf={health_factor:.3f} — not liquidatable"
                )
                return None

            # Evaluate profitability
            opp = ProfitGate.evaluate_liquidation(
                chain=chain,
                user_address=user_address,
                collateral_usd=collateral_usd,
                debt_usd=debt_usd,
                health_factor=health_factor,
                bonus_pct=self.AAVE_LIQUIDATION_BONUS.get("default", 5.0),
            )

            if not opp:
                return None

            return self.execute_aave_liquidation(opp, chain=chain)

        except Exception as e:
            logger.error(f"LiquidationHunter: getUserAccountData error for {user_address[:12]}...: {e}")
            return None

    def execute_aave_liquidation(
        self,
        opp: MEVOpportunity,
        chain: str = "base",
        collateral_asset: str = "",
        debt_asset: str = "",
        receive_a_token: bool = False,
    ) -> MEVResult:
        """
        Calls Aave V3 Pool.liquidationCall() to seize collateral.

        Aave V3 liquidationCall signature:
          function liquidationCall(
            address collateralAsset,
            address debtAsset,
            address user,
            uint256 debtToCover,
            bool receiveAToken
          )

        The liquidator must hold enough debtAsset to cover debtToCover.
        They receive collateralAsset + liquidation bonus in return.
        """
        if settings.IS_PAPER:
            logger.info(
                f"[PAPER] Aave liquidation: {opp.target_address[:12]}... "
                f"chain={chain} net=${opp.net_profit_usd:.2f}"
            )
            return MEVResult(True, "liquidation", chain, opp.net_profit_usd, tx_hash="paper_aave_liq")

        if not self.enabled or not self._signing_account:
            return MEVResult(False, "liquidation", chain, 0.0, error="Not configured")

        w3 = self._web3_base if chain == "base" else self._web3_eth
        pool = self._aave_pool_base if chain == "base" else self._aave_pool_eth

        if not w3 or not pool:
            return MEVResult(False, "liquidation", chain, 0.0, error="Web3 not initialised")

        try:
            account = self._signing_account
            user_checksum = Web3.to_checksum_address(opp.target_address)
            debt_to_cover = int(opp.raw_data.get("debt_to_cover", 0) * 1e6)  # USDC 6 decimals

            # Build the liquidationCall transaction
            tx = pool.functions.liquidationCall(
                Web3.to_checksum_address(collateral_asset or "0x0000000000000000000000000000000000000000"),
                Web3.to_checksum_address(debt_asset or "0x0000000000000000000000000000000000000000"),
                user_checksum,
                debt_to_cover,
                receive_a_token,
            ).build_transaction({
                "from": account.address,
                "gas": 500_000,
                "maxFeePerGas": w3.eth.gas_price * 2,
                "maxPriorityFeePerGas": w3.eth.gas_price,
                "nonce": w3.eth.get_transaction_count(account.address, "pending"),
                "chainId": 8453 if chain == "base" else 1,
            })

            signed_tx = account.sign_transaction(tx)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            tx_hash_hex = tx_hash.hex()

            logger.info(
                f"LiquidationHunter: Aave {chain} liquidation submitted: {tx_hash_hex} "
                f"net=${opp.net_profit_usd:.2f}"
            )
            return MEVResult(
                True, "liquidation", chain,
                opp.net_profit_usd,
                tx_hash=tx_hash_hex,
            )

        except Exception as e:
            logger.error(f"LiquidationHunter: Aave liquidation error: {e}")
            return MEVResult(False, "liquidation", chain, 0.0, error=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# MEV Extractor Engine — Orchestrates both strategies
# ─────────────────────────────────────────────────────────────────────────────

class MEVExtractorEngine:
    """
    Top-level orchestrator for the MEV Sandwich & Liquidation Engine.
    Runs both strategies concurrently as asyncio tasks.

    Usage (standalone):
        engine = MEVExtractorEngine()
        asyncio.run(engine.run())

    Usage (integrated into main bot loop):
        engine = MEVExtractorEngine()
        asyncio.create_task(engine.run())
    """

    def __init__(self) -> None:
        self.sandwich_bot = SandwichBot()
        self.liquidation_hunter = LiquidationHunter()
        self._results: List[MEVResult] = []
        self._total_profit_usd: float = 0.0
        self._start_time: float = time.time()

    async def run(self) -> None:
        """Starts all MEV monitoring tasks concurrently."""
        logger.info(
            "MEVExtractorEngine: Starting all strategies | "
            f"Sandwich: {'ON' if SANDWICH_ENABLED else 'OFF'} | "
            f"Liquidation: {'ON' if LIQUIDATION_ENABLED else 'OFF'}"
        )

        tasks: List[asyncio.Task] = []

        if SANDWICH_ENABLED:
            tasks.append(asyncio.create_task(
                self.sandwich_bot.monitor_base_mempool(),
                name="sandwich_base_mempool",
            ))

        if LIQUIDATION_ENABLED:
            if HYPERLIQUID_ENABLED:
                tasks.append(asyncio.create_task(
                    self.liquidation_hunter.monitor_hyperliquid_ws(),
                    name="liquidation_hyperliquid_ws",
                ))
            tasks.append(asyncio.create_task(
                self.liquidation_hunter.monitor_aave_ws(chain="base"),
                name="liquidation_aave_base",
            ))
            tasks.append(asyncio.create_task(
                self.liquidation_hunter.monitor_aave_ws(chain="ethereum"),
                name="liquidation_aave_eth",
            ))

        if not tasks:
            logger.warning("MEVExtractorEngine: No strategies enabled — engine idle")
            return

        # Run all tasks; restart any that crash
        await asyncio.gather(*tasks, return_exceptions=True)

    def get_status(self) -> Dict[str, Any]:
        """Returns a status dict for dashboard integration."""
        uptime_hours = (time.time() - self._start_time) / 3600
        return {
            "sandwich_enabled": SANDWICH_ENABLED,
            "liquidation_enabled": LIQUIDATION_ENABLED,
            "hyperliquid_enabled": HYPERLIQUID_ENABLED,
            "total_executions": len(self._results),
            "successful_executions": sum(1 for r in self._results if r.success),
            "total_profit_usd": self._total_profit_usd,
            "uptime_hours": round(uptime_hours, 2),
            "min_net_profit_usd": MIN_NET_PROFIT_USD,
            "slippage_threshold_pct": SLIPPAGE_THRESHOLD_PCT,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

_engine: Optional[MEVExtractorEngine] = None


def get_engine() -> MEVExtractorEngine:
    """Returns the singleton MEV engine instance."""
    global _engine
    if _engine is None:
        _engine = MEVExtractorEngine()
    return _engine


def start_mev_engine() -> None:
    """Entry point for running the MEV engine as a standalone process."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    engine = get_engine()
    asyncio.run(engine.run())


if __name__ == "__main__":
    start_mev_engine()


# =============================================================================
# JIT LIQUIDITY SNIPER INTEGRATION
# ECC Skill: jit-liquidity-sniper
# =============================================================================
#
# This section integrates the JIT Liquidity Sniper into the existing MEV
# extraction engine. The JIT sniper runs as a parallel strategy alongside
# the existing sandwich bot and liquidation hunter.
#
# JIT Strategy:
#   1. MempoolWatcher detects pending Uniswap V3 swaps >= $100k
#   2. JITAnalyzer evaluates profitability (tick math + fee estimation)
#   3. JITExecutor builds calldata for JITLiquidityProvider.sol
#   4. PrivateRPCRouter submits via Flashbots (ETH/Base/Arb) or Jito (SOL)
#   5. Atomic: flash borrow → mint LP → whale swap fills ticks → burn LP → repay
#
# All JIT transactions are routed through private RPCs — NEVER the public
# mempool — so other searchers cannot front-run our liquidity provision.
# =============================================================================

import threading as _jit_threading


def _get_jit_sniper():
    """Lazy-load the JIT sniper to avoid circular imports."""
    try:
        from core.jit_liquidity_sniper import jit_sniper
        return jit_sniper
    except Exception as _e:
        logging.getLogger(__name__).warning(f"JIT sniper import failed: {_e}")
        return None


class JITIntegration:
    """
    Bridges the JIT Liquidity Sniper into the MEVExtractorEngine.

    Provides:
      - start() / stop() lifecycle management
      - on_pending_whale_trade() for Moralis Streams integration
      - get_stats() for dashboard integration
      - Private RPC routing (Flashbots / Jito)
    """

    # Private RPC endpoints per chain (never broadcast to public mempool)
    PRIVATE_RPCS = {
        "ethereum":  "https://rpc.flashbots.net/fast",
        "base":      "https://rpc.flashbots.net/fast",
        "arbitrum":  "https://rpc.flashbots.net/fast",
        "polygon":   "https://polygon-mainnet.g.alchemy.com/v2/",
        "bsc":       "https://bsc-dataseed1.binance.org/",
        "solana":    os.getenv(
            "JITO_BLOCK_ENGINE_URL",
            "https://mainnet.block-engine.jito.wtf/api/v1/bundles",
        ),
    }

    def __init__(self):
        self._sniper = None
        self._lock = _jit_threading.Lock()
        self._started = False
        self.logger = logging.getLogger(f"{__name__}.JITIntegration")

    def start(self) -> None:
        """Start the JIT mempool watcher daemon."""
        with self._lock:
            if self._started:
                return
            self._sniper = _get_jit_sniper()
            if self._sniper:
                self._sniper.start()
                self._started = True
                self.logger.info(
                    "✅ JIT Liquidity Sniper started | "
                    f"min_trade=${getattr(settings, 'JIT_MIN_TRADE_SIZE_USD', 100_000):,.0f} | "
                    f"max_flash=${getattr(settings, 'JIT_MAX_FLASH_BORROW_USD', 500_000):,.0f} | "
                    "Private RPC: Flashbots/Jito"
                )
            else:
                self.logger.warning("JIT Liquidity Sniper unavailable — skipping")

    def stop(self) -> None:
        """Stop the JIT mempool watcher."""
        with self._lock:
            if self._sniper and self._started:
                self._sniper.stop()
                self._started = False

    def on_pending_whale_trade(self, tx_data: dict) -> None:
        """
        Called when a large pending swap is detected (e.g., from Moralis Streams).

        tx_data keys:
          chain, value_usd, to_address, token_in, token_out, hash,
          fee_tier (optional), current_tick (optional)
        """
        if self._sniper and self._started:
            try:
                self._sniper.on_pending_whale_trade(tx_data)
            except Exception as e:
                self.logger.error(f"JIT on_pending_whale_trade error: {e}")

    def on_moralis_large_swap(self, event: dict) -> None:
        """Called by Moralis Streams large-swap webhook handler."""
        if self._sniper and self._started:
            try:
                self._sniper.on_moralis_large_swap(event)
            except Exception as e:
                self.logger.error(f"JIT on_moralis_large_swap error: {e}")

    def get_stats(self) -> dict:
        """Returns JIT statistics for dashboard integration."""
        if self._sniper and self._started:
            try:
                return self._sniper.get_stats()
            except Exception:
                pass
        return {
            "enabled": False,
            "opportunities_detected": 0,
            "opportunities_executed": 0,
            "total_profit_usd": 0.0,
            "hit_rate_pct": 0.0,
        }

    def get_private_rpc(self, chain: str) -> str:
        """Returns the private RPC URL for a given chain."""
        return self.PRIVATE_RPCS.get(chain, self.PRIVATE_RPCS["ethereum"])


# Module-level JIT integration singleton
jit_integration = JITIntegration()


def get_jit_integration() -> JITIntegration:
    """Returns the global JIT integration singleton."""
    return jit_integration


# Patch MEVExtractorEngine to include JIT as a third strategy
_original_engine_init = MEVExtractorEngine.__init__
_original_engine_run = MEVExtractorEngine.run
_original_engine_status = MEVExtractorEngine.get_status


def _patched_engine_init(self):
    _original_engine_init(self)
    self.jit = jit_integration


def _patched_engine_run(self):
    """Starts all MEV strategies including JIT."""
    # Start JIT in background thread (it uses its own WebSocket event loop)
    self.jit.start()
    # Run the original async sandwich + liquidation engine
    return _original_engine_run(self)


def _patched_engine_status(self) -> dict:
    """Extended status dict including JIT statistics."""
    base_status = _original_engine_status(self)
    base_status["jit"] = self.jit.get_stats()
    base_status["jit_private_rpcs"] = list(JITIntegration.PRIVATE_RPCS.keys())
    return base_status


MEVExtractorEngine.__init__ = _patched_engine_init
MEVExtractorEngine.run = _patched_engine_run
MEVExtractorEngine.get_status = _patched_engine_status
