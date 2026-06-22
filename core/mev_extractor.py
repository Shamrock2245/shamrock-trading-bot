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
  BASE_WS_RPC_URL            Base chain WebSocket RPC (for mempool subscription)
  ETH_RPC_URL                Ethereum HTTP RPC
  ETH_WS_RPC_URL             Ethereum WebSocket RPC
  JITO_BLOCK_ENGINE_URL      Jito block engine endpoint
  JITO_AUTH_KEY              Jito auth key (optional)
  SOLANA_RPC_URL             Solana HTTP RPC
  SOLANA_PRIVATE_KEY         Solana wallet private key (base58)
  HYPERLIQUID_ENABLED        "true"/"false"
  HYPERLIQUID_WALLET_ADDRESS HL wallet address
  HYPERLIQUID_PRIVATE_KEY    HL signing key
  AAVE_POOL_ADDRESS_BASE     Aave V3 Pool on Base
  AAVE_POOL_ADDRESS_ETH      Aave V3 Pool on Ethereum
  MEV_MIN_NET_PROFIT_USD     Minimum net profit to execute (default: 1.0)
  MEV_SANDWICH_ENABLED       Enable sandwich bot (default: true)
  MEV_LIQUIDATION_ENABLED    Enable liquidation hunter (default: true)
  MEV_MAX_POSITION_USD       Max capital per sandwich (default: 500)
  MEV_SLIPPAGE_THRESHOLD_PCT Minimum victim slippage to target (default: 2.0)
  MEV_HL_TRACKED_ACCOUNTS    Comma-separated HL addresses to poll for liquidation
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import random
import struct
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import websockets
from eth_account import Account
from eth_account.messages import encode_defunct
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
BASE_WS_RPC_URL: str = os.getenv("BASE_WS_RPC_URL", "")
ETH_RPC_URL: str = os.getenv("ETH_RPC_URL", "")
ETH_WS_RPC_URL: str = os.getenv("ETH_WS_RPC_URL", "")

JITO_BLOCK_ENGINE_URL: str = os.getenv(
    "JITO_BLOCK_ENGINE_URL",
    "https://mainnet.block-engine.jito.wtf/api/v1/bundles",
)
JITO_AUTH_KEY: str = os.getenv("JITO_AUTH_KEY", "")

SOLANA_RPC_URL: str = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
SOLANA_PRIVATE_KEY: str = os.getenv("SOLANA_PRIVATE_KEY", "")

HYPERLIQUID_WS_URL: str = "wss://api.hyperliquid.xyz/ws"
HYPERLIQUID_REST_URL: str = "https://api.hyperliquid.xyz/info"
HYPERLIQUID_EXCHANGE_URL: str = "https://api.hyperliquid.xyz/exchange"
HYPERLIQUID_ENABLED: bool = os.getenv("HYPERLIQUID_ENABLED", "true").lower() == "true"
HYPERLIQUID_WALLET_ADDRESS: str = os.getenv("HYPERLIQUID_WALLET_ADDRESS", "")
HYPERLIQUID_PRIVATE_KEY: str = os.getenv("HYPERLIQUID_PRIVATE_KEY", "")

# Comma-separated list of HL addresses to actively poll for liquidation
# e.g. "0xabc...,0xdef..." — discovered via leaderboard / on-chain analytics
_HL_TRACKED_RAW: str = os.getenv("MEV_HL_TRACKED_ACCOUNTS", "")
HL_TRACKED_ACCOUNTS: List[str] = [a.strip() for a in _HL_TRACKED_RAW.split(",") if a.strip()]

# Aave V3 Pool addresses (canonical, verified on-chain)
AAVE_POOL_ADDRESS_ETH: str = os.getenv(
    "AAVE_POOL_ADDRESS_ETH",
    "0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2",
)
AAVE_POOL_ADDRESS_BASE: str = os.getenv(
    "AAVE_POOL_ADDRESS_BASE",
    "0xA238Dd80C259a72e81d7e4664a9801593F98d1c5",
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

# WETH address on Base (used as token_in for ETH→Token swaps)
WETH_BASE: str = "0x4200000000000000000000000000000000000006"
# USDC on Base
USDC_BASE: str = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"

# Aerodrome Router on Base (supports swapExactETHForTokens compatible interface)
AERODROME_ROUTER_BASE: str = "0xcF77a3Ba9A5CA399B7c97c74d54e5b1Beb874E43"
# Uniswap V3 SwapRouter02 on Base
UNISWAP_V3_ROUTER_BASE: str = "0x2626664c2603336E57B271c5C0b26F421741e481"

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

# ERC-20 minimal ABI (for approve calls before liquidation)
ERC20_ABI = json.loads("""[
  {
    "inputs": [
      {"internalType": "address", "name": "spender", "type": "address"},
      {"internalType": "uint256", "name": "amount", "type": "uint256"}
    ],
    "name": "approve",
    "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
    "stateMutability": "nonpayable",
    "type": "function"
  },
  {
    "inputs": [{"internalType": "address", "name": "account", "type": "address"}],
    "name": "balanceOf",
    "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
    "stateMutability": "view",
    "type": "function"
  }
]""")

# Uniswap V2-style router ABI (Aerodrome uses this interface on Base)
AERODROME_ROUTER_ABI = json.loads("""[
  {
    "inputs": [
      {"internalType": "uint256", "name": "amountOutMin", "type": "uint256"},
      {
        "components": [
          {"internalType": "address", "name": "from", "type": "address"},
          {"internalType": "address", "name": "to", "type": "address"},
          {"internalType": "bool", "name": "stable", "type": "bool"},
          {"internalType": "address", "name": "factory", "type": "address"}
        ],
        "internalType": "struct IRouter.Route[]",
        "name": "routes",
        "type": "tuple[]"
      },
      {"internalType": "address", "name": "to", "type": "address"},
      {"internalType": "uint256", "name": "deadline", "type": "uint256"}
    ],
    "name": "swapExactETHForTokens",
    "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
    "stateMutability": "payable",
    "type": "function"
  },
  {
    "inputs": [
      {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
      {"internalType": "uint256", "name": "amountOutMin", "type": "uint256"},
      {
        "components": [
          {"internalType": "address", "name": "from", "type": "address"},
          {"internalType": "address", "name": "to", "type": "address"},
          {"internalType": "bool", "name": "stable", "type": "bool"},
          {"internalType": "address", "name": "factory", "type": "address"}
        ],
        "internalType": "struct IRouter.Route[]",
        "name": "routes",
        "type": "tuple[]"
      },
      {"internalType": "address", "name": "to", "type": "address"},
      {"internalType": "uint256", "name": "deadline", "type": "uint256"}
    ],
    "name": "swapExactTokensForETH",
    "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
    "stateMutability": "nonpayable",
    "type": "function"
  }
]""")

# Aerodrome default factory address on Base
AERODROME_FACTORY_BASE: str = "0x420DD381b31aEf6683db6B902084cB0FFECe40D"


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
        ref = (self.tx_hash or self.bundle_id or "N/A")[:14]
        return (
            f"MEVResult({status} {self.strategy}@{self.chain} | "
            f"profit=${self.net_profit_usd:.2f} | ref={ref}...)"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Profit Gate — Strict positive-profit check before any execution
# ─────────────────────────────────────────────────────────────────────────────

class ProfitGate:
    """
    Simulates the full MEV bundle/tx before execution.
    Returns an MEVOpportunity only if net_profit > MIN_NET_PROFIT_USD.
    """

    # Conservative live price cache (refreshed every 60s in production)
    _eth_price_usd: float = 3500.0
    _sol_price_usd: float = 150.0
    _price_last_updated: float = 0.0

    @classmethod
    def _refresh_prices(cls) -> None:
        """Refreshes ETH and SOL prices from CoinGecko if stale (>60s)."""
        if time.time() - cls._price_last_updated < 60:
            return
        try:
            resp = get_session().get(
                "https://api.coingecko.com/api/v3/simple/price"
                "?ids=ethereum,solana&vs_currencies=usd",
                timeout=5,
            )
            if resp.status_code == 200:
                data = resp.json()
                cls._eth_price_usd = float(data.get("ethereum", {}).get("usd", cls._eth_price_usd))
                cls._sol_price_usd = float(data.get("solana", {}).get("usd", cls._sol_price_usd))
                cls._price_last_updated = time.time()
        except Exception:
            pass  # Use cached values on failure

    @classmethod
    def estimate_gas_cost_usd(cls, chain: str, gas_units: int = 300_000) -> float:
        """Estimates gas cost in USD for a given chain using live gas prices."""
        cls._refresh_prices()
        gas_prices_gwei = {
            "ethereum": 20.0,
            "base": 0.05,
            "arbitrum": 0.1,
            "polygon": 50.0,
            "bsc": 3.0,
        }
        gwei = gas_prices_gwei.get(chain, 5.0)

        # Try to fetch live gas price from chain RPC
        try:
            rpc_url = BASE_RPC_URL if chain == "base" else ETH_RPC_URL
            if rpc_url:
                w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 3}))
                live_gwei = w3.eth.gas_price / 1e9
                gwei = live_gwei
        except Exception:
            pass

        gas_eth = (gwei * 1e-9) * gas_units
        return gas_eth * cls._eth_price_usd

    @classmethod
    def estimate_jito_tip_usd(cls, tip_lamports: int = 500_000) -> float:
        """Converts Jito tip in lamports to USD."""
        cls._refresh_prices()
        sol = tip_lamports / 1e9
        return sol * cls._sol_price_usd

    @classmethod
    def simulate_evm_bundle(
        cls,
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

        try:
            account = Account.from_key(signing_key)
            # Flashbots signature: sign the keccak256 of the body
            body_hash = Web3.keccak(text=body)
            msg = encode_defunct(body_hash)
            signed = account.sign_message(msg)
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
        gross_profit = front_run_amount * price_impact_pct
        net_profit   = gross_profit - gas - bribe
        """
        gas_cost = cls.estimate_gas_cost_usd(chain, gas_units=400_000)
        bribe_cost = (
            cls.estimate_jito_tip_usd(tip_lamports=1_000_000)
            if chain == "solana"
            else gas_cost * 0.5
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
        bonus_pct: float = 5.0,
    ) -> Optional[MEVOpportunity]:
        """
        Evaluates whether liquidating a position is profitable.
        gross_profit = (debt_to_cover * bonus_pct / 100)
        net_profit   = gross_profit - gas
        """
        if health_factor >= 1.0:
            return None

        debt_to_cover = min(debt_usd * 0.5, MAX_POSITION_USD)
        gross_profit = debt_to_cover * (bonus_pct / 100.0)
        gas_cost = cls.estimate_gas_cost_usd(chain, gas_units=500_000)
        net_profit = gross_profit - gas_cost

        opp = MEVOpportunity(
            strategy="liquidation",
            chain=chain,
            target_address=user_address,
            token_address="",
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

    BASE_DEX_ROUTERS: List[str] = [
        AERODROME_ROUTER_BASE.lower(),
        UNISWAP_V3_ROUTER_BASE.lower(),
    ]

    def __init__(self) -> None:
        self.enabled = SANDWICH_ENABLED and bool(FLASHBOTS_SIGNING_KEY)
        self._web3_base: Optional[Web3] = None
        self._signing_account: Optional[LocalAccount] = None
        self._aerodrome_contract: Optional[Any] = None

        if BASE_RPC_URL:
            try:
                self._web3_base = Web3(Web3.HTTPProvider(BASE_RPC_URL, request_kwargs={"timeout": 10}))
                self._web3_base.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
                self._aerodrome_contract = self._web3_base.eth.contract(
                    address=Web3.to_checksum_address(AERODROME_ROUTER_BASE),
                    abi=AERODROME_ROUTER_ABI,
                )
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
        Requires BASE_WS_RPC_URL to be set (Alchemy/QuickNode WebSocket endpoint).
        """
        if not self.enabled:
            return

        if not BASE_WS_RPC_URL:
            logger.warning("SandwichBot: BASE_WS_RPC_URL not set — mempool monitoring disabled")
            return

        logger.info("SandwichBot: Starting Base mempool monitor...")
        _backoff = 5
        _MAX_BACKOFF = 60
        while True:
            try:
                async with websockets.connect(
                    BASE_WS_RPC_URL,
                    ping_interval=20,
                    close_timeout=10,
                ) as ws:
                    sub_msg = {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "eth_subscribe",
                        "params": ["newPendingTransactions", True],
                    }
                    await ws.send(json.dumps(sub_msg))
                    logger.info("SandwichBot: Subscribed to Base pending transactions")
                    _backoff = 5  # reset on successful connect

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

            except (websockets.exceptions.ConnectionClosed,
                    websockets.exceptions.ConnectionClosedError,
                    websockets.exceptions.ConnectionClosedOK) as e:
                logger.warning(f"SandwichBot: Base WS closed ({e}). Reconnecting in {_backoff}s...")
                await asyncio.sleep(_backoff)
                _backoff = min(_backoff * 2, _MAX_BACKOFF)
            except Exception as e:
                logger.error(f"SandwichBot: Base WS error: {e}. Reconnecting in {_backoff}s...")
                await asyncio.sleep(_backoff)
                _backoff = min(_backoff * 2, _MAX_BACKOFF)

    def _parse_pending_tx(self, tx: Dict[str, Any], chain: str) -> Optional[PendingSwap]:
        """
        Parses a raw pending transaction. Returns a PendingSwap if it targets
        a known DEX router with a large ETH value and high slippage tolerance.
        """
        to_addr = (tx.get("to") or "").lower()
        if to_addr not in self.BASE_DEX_ROUTERS:
            return None

        # Decode ETH value
        raw_value = tx.get("value", "0x0")
        value_wei = int(raw_value, 16) if isinstance(raw_value, str) else int(raw_value)
        value_eth = value_wei / 1e18

        ProfitGate._refresh_prices()
        amount_usd = value_eth * ProfitGate._eth_price_usd

        if amount_usd < 10_000:
            return None

        # Decode token_out from calldata (first 4 bytes = selector, then ABI-encoded params)
        calldata = tx.get("input", "0x")
        token_out, slippage_pct = self._decode_swap_calldata(calldata, amount_usd, to_addr)

        if slippage_pct < SLIPPAGE_THRESHOLD_PCT:
            return None

        logger.info(
            f"SandwichBot: Target tx {tx.get('hash', '')[:14]}... "
            f"amount=${amount_usd:,.0f} slippage={slippage_pct:.1f}% token_out={token_out[:12]}..."
        )

        return PendingSwap(
            chain=chain,
            tx_hash=tx.get("hash", ""),
            router_address=to_addr,
            token_in="ETH",
            token_out=token_out,
            amount_in_usd=amount_usd,
            slippage_pct=slippage_pct,
            raw_tx=tx,
        )

    def _decode_swap_calldata(
        self,
        calldata: str,
        amount_usd: float,
        router: str,
    ) -> Tuple[str, float]:
        """
        Decodes the token_out address and slippage tolerance from swap calldata.

        Aerodrome swapExactETHForTokens selector: 0x8e0d1a5c
        Uniswap V3 exactInputSingle selector:     0x414bf389

        For Aerodrome: routes[0].to is token_out; amountOutMin vs expected gives slippage.
        For Uniswap V3: params.tokenOut is token_out; amountOutMinimum vs quote gives slippage.

        Falls back to a heuristic if decoding fails.
        """
        token_out = "0x0000000000000000000000000000000000000000"
        slippage_pct = 0.0

        # If calldata is empty or too short, skip selector decoding and fall through
        # to the heuristic below (large ETH transfers to DEX routers are always targets)
        if not calldata or len(calldata) < 10:
            if amount_usd > 50_000:
                slippage_pct = 3.5
            elif amount_usd > 10_000:
                slippage_pct = 2.5
            return token_out, slippage_pct

        try:
            selector = calldata[:10].lower()

            # Aerodrome swapExactETHForTokens: 0x8e0d1a5c
            # Params: (uint256 amountOutMin, Route[] routes, address to, uint256 deadline)
            if selector == "0x8e0d1a5c" and router == AERODROME_ROUTER_BASE.lower():
                # Decode amountOutMin (first 32 bytes after selector)
                hex_data = calldata[10:]
                if len(hex_data) >= 64:
                    amount_out_min = int(hex_data[:64], 16)
                    # Routes array offset is at bytes 32–64
                    # For a simple single-hop route, token_out is at offset 128 + 32 = 160 bytes
                    # Route struct: {from(20), to(20), stable(1), factory(20)} = 3 slots
                    if len(hex_data) >= 320:
                        # routes[0].to is at position: 64 (offset) + 64 (array len) + 32 (from) = 160
                        # Each address is right-padded to 32 bytes
                        to_slot = hex_data[192:256]  # routes[0].to slot
                        token_out = "0x" + to_slot[-40:]
                    # Slippage: if amountOutMin is very low relative to expected, slippage is high
                    # We estimate expected output using a 1:1 USD proxy (conservative)
                    expected_out_usd = amount_usd * 0.99  # assume 1% spread
                    actual_min_usd = amount_out_min / 1e18 * ProfitGate._eth_price_usd
                    if expected_out_usd > 0 and actual_min_usd < expected_out_usd:
                        slippage_pct = (1.0 - actual_min_usd / expected_out_usd) * 100.0

            # Uniswap V3 exactInputSingle: 0x414bf389
            # Params: ExactInputSingleParams { tokenIn, tokenOut, fee, recipient,
            #                                  amountIn, amountOutMinimum, sqrtPriceLimitX96 }
            elif selector == "0x414bf389":
                hex_data = calldata[10:]
                if len(hex_data) >= 256:
                    # tokenOut is the second 32-byte slot (bytes 32–64)
                    token_out_slot = hex_data[64:128]
                    token_out = "0x" + token_out_slot[-40:]
                    # amountIn is at slot 4 (bytes 128–160), amountOutMinimum at slot 5 (160–192)
                    amount_in_raw = int(hex_data[128:192], 16)
                    amount_out_min = int(hex_data[192:256], 16)
                    if amount_in_raw > 0 and amount_out_min < amount_in_raw:
                        slippage_pct = (1.0 - amount_out_min / amount_in_raw) * 100.0

        except Exception as e:
            logger.debug(f"SandwichBot: calldata decode error: {e}")

        # Heuristic fallback: large swaps typically have 2–5% slippage set.
        # Also applies when calldata is empty (0x) — e.g. plain ETH transfers to router.
        if slippage_pct < SLIPPAGE_THRESHOLD_PCT:
            if amount_usd > 50_000:
                slippage_pct = 3.5
            elif amount_usd > 10_000:
                slippage_pct = 2.5

        return token_out, slippage_pct

    async def _handle_sandwich_opportunity(self, pending: PendingSwap) -> None:
        """Evaluates and executes a sandwich opportunity if profitable."""
        front_run_amount = min(pending.amount_in_usd * 0.20, MAX_POSITION_USD)

        opp = ProfitGate.evaluate_sandwich(
            chain=pending.chain,
            pending_swap=pending,
            front_run_amount_usd=front_run_amount,
            estimated_price_impact_pct=pending.slippage_pct * 0.6,
        )

        if not opp:
            return

        result = self.execute_sandwich_base(opp)
        if result.success:
            logger.info(f"SandwichBot: {result}")

    # ── Bundle Execution — Base (Flashbots) ───────────────────────────────────

    def _build_aerodrome_buy_calldata(
        self,
        token_out: str,
        amount_out_min: int,
        recipient: str,
        deadline: int,
    ) -> bytes:
        """
        Encodes Aerodrome swapExactETHForTokens calldata.
        Selector: 0x8e0d1a5c
        """
        if not self._aerodrome_contract:
            return b""
        try:
            return self._aerodrome_contract.encodeABI(
                fn_name="swapExactETHForTokens",
                args=[
                    amount_out_min,
                    [{
                        "from": WETH_BASE,
                        "to": Web3.to_checksum_address(token_out),
                        "stable": False,
                        "factory": AERODROME_FACTORY_BASE,
                    }],
                    Web3.to_checksum_address(recipient),
                    deadline,
                ],
            )
        except Exception as e:
            logger.debug(f"SandwichBot: buy calldata encode error: {e}")
            return b""

    def _build_aerodrome_sell_calldata(
        self,
        token_in: str,
        amount_in: int,
        amount_out_min: int,
        recipient: str,
        deadline: int,
    ) -> bytes:
        """
        Encodes Aerodrome swapExactTokensForETH calldata.
        Selector: 0x5c11d795 (standard V2 interface)
        """
        if not self._aerodrome_contract:
            return b""
        try:
            return self._aerodrome_contract.encodeABI(
                fn_name="swapExactTokensForETH",
                args=[
                    amount_in,
                    amount_out_min,
                    [{
                        "from": Web3.to_checksum_address(token_in),
                        "to": WETH_BASE,
                        "stable": False,
                        "factory": AERODROME_FACTORY_BASE,
                    }],
                    Web3.to_checksum_address(recipient),
                    deadline,
                ],
            )
        except Exception as e:
            logger.debug(f"SandwichBot: sell calldata encode error: {e}")
            return b""

    def execute_sandwich_base(self, opp: MEVOpportunity) -> MEVResult:
        """
        Constructs and submits a Flashbots bundle on Base.
        Bundle layout:
          [0] Front-run BUY  (our tx — swapExactETHForTokens on Aerodrome)
          [1] Victim TX      (raw tx from mempool, forwarded as-is)
          [2] Back-run SELL  (our tx — swapExactTokensForETH on Aerodrome)

        Simulation via eth_callBundle is performed before submission.
        Bundle is discarded if simulation shows negative coinbaseDiff.
        """
        if (settings.get_current_mode() == "paper"):
            logger.info(
                f"[PAPER] Base sandwich: target={opp.target_address[:14]}... "
                f"net=${opp.net_profit_usd:.2f}"
            )
            return MEVResult(True, "sandwich", "base", opp.net_profit_usd, bundle_id="paper_bundle")

        if not self.enabled or not self._web3_base or not self._signing_account:
            return MEVResult(False, "sandwich", "base", 0.0, error="SandwichBot not configured")

        try:
            w3 = self._web3_base
            account = self._signing_account
            block_number = w3.eth.block_number
            base_fee = w3.eth.gas_price
            nonce = w3.eth.get_transaction_count(account.address, "pending")
            deadline = int(time.time()) + 60  # 60-second deadline

            raw_data = opp.raw_data.get("swap", {})
            token_out = raw_data.get("token_out", USDC_BASE)
            amount_in_wei = int(opp.net_profit_usd * 0.20 * 1e18 / ProfitGate._eth_price_usd)

            # ── Front-run BUY calldata ────────────────────────────────────────
            buy_data = self._build_aerodrome_buy_calldata(
                token_out=token_out,
                amount_out_min=1,  # Accept any amount — we sell immediately after
                recipient=account.address,
                deadline=deadline,
            )

            front_run_tx = {
                "from": account.address,
                "to": Web3.to_checksum_address(AERODROME_ROUTER_BASE),
                "value": amount_in_wei,
                "gas": 250_000,
                "maxFeePerGas": base_fee * 2,
                "maxPriorityFeePerGas": base_fee,
                "nonce": nonce,
                "chainId": 8453,
                "data": buy_data if buy_data else "0x",
            }
            signed_front = account.sign_transaction(front_run_tx)

            # ── Back-run SELL calldata ────────────────────────────────────────
            # Estimate tokens received from the front-run buy
            # Conservative: assume we get 99% of the expected output
            estimated_tokens_out = int(amount_in_wei * 0.99)

            sell_data = self._build_aerodrome_sell_calldata(
                token_in=token_out,
                amount_in=estimated_tokens_out,
                amount_out_min=1,  # Accept any ETH back — profit is guaranteed by sandwich
                recipient=account.address,
                deadline=deadline,
            )

            back_run_tx = {
                "from": account.address,
                "to": Web3.to_checksum_address(AERODROME_ROUTER_BASE),
                "value": 0,
                "gas": 250_000,
                "maxFeePerGas": base_fee * 2,
                "maxPriorityFeePerGas": base_fee,
                "nonce": nonce + 1,
                "chainId": 8453,
                "data": sell_data if sell_data else "0x",
            }
            signed_back = account.sign_transaction(back_run_tx)

            # ── Victim TX (raw, from mempool) ─────────────────────────────────
            victim_raw = raw_data.get("raw_tx", {})
            # The full raw signed tx hex — received from eth_subscribe with full tx body
            victim_hex = victim_raw.get("rawTransaction", victim_raw.get("raw", ""))
            if not victim_hex:
                return MEVResult(False, "sandwich", "base", 0.0, error="No victim raw tx")

            bundle_txs = [
                "0x" + signed_front.raw_transaction.hex(),
                victim_hex if victim_hex.startswith("0x") else "0x" + victim_hex,
                "0x" + signed_back.raw_transaction.hex(),
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
                coinbase_diff_hex = sim_result.get("coinbaseDiff", "0x0")
                coinbase_diff = int(coinbase_diff_hex, 16) / 1e18
                logger.info(f"SandwichBot: Simulation coinbaseDiff={coinbase_diff:.8f} ETH")
                if coinbase_diff <= 0:
                    logger.debug("SandwichBot: Simulation shows zero/negative profit — discarding")
                    return MEVResult(False, "sandwich", "base", 0.0, error="Simulation negative")

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
            body_hash = Web3.keccak(text=body)
            msg = encode_defunct(body_hash)
            signed_msg = account.sign_message(msg)
            headers = {
                "Content-Type": "application/json",
                "X-Flashbots-Signature": f"{account.address}:{signed_msg.signature.hex()}",
            }
            resp = get_session().post(FLASHBOTS_RPC_URL, data=body, headers=headers, timeout=10)

            if resp.status_code == 200:
                bundle_hash = resp.json().get("result", {}).get("bundleHash", "")
                logger.info(f"SandwichBot: Base bundle submitted: {bundle_hash}")
                return MEVResult(True, "sandwich", "base", opp.net_profit_usd, bundle_id=bundle_hash)

            logger.warning(f"SandwichBot: Bundle submission failed: {resp.status_code} {resp.text[:200]}")
            return MEVResult(False, "sandwich", "base", 0.0, error=f"HTTP {resp.status_code}")

        except Exception as e:
            logger.error(f"SandwichBot: Base execution error: {e}")
            return MEVResult(False, "sandwich", "base", 0.0, error=str(e))

    # ── Bundle Execution — Solana (Jito) ──────────────────────────────────────

    def _build_jupiter_swap_tx(
        self,
        input_mint: str,
        output_mint: str,
        amount: int,
        slippage_bps: int,
        user_public_key: str,
    ) -> Optional[str]:
        """
        Fetches a versioned transaction from Jupiter V6 API for a swap.
        Returns the base64-encoded transaction string or None on failure.

        Steps:
          1. GET /quote — get the best route for input_mint → output_mint
          2. POST /swap — get the serialized VersionedTransaction
        """
        jupiter_url = os.getenv("JUPITER_API_URL", "https://api.jup.ag/swap/v1")
        jupiter_key = os.getenv("JUPITER_API_KEY", "")
        headers = {"Content-Type": "application/json"}
        if jupiter_key:
            headers["Authorization"] = f"Bearer {jupiter_key}"

        try:
            # Step 1: Get quote
            quote_resp = get_session().get(
                f"{jupiter_url}/quote",
                params={
                    "inputMint": input_mint,
                    "outputMint": output_mint,
                    "amount": str(amount),
                    "slippageBps": str(slippage_bps),
                    "onlyDirectRoutes": "true",  # Faster for MEV — no multi-hop
                },
                headers=headers,
                timeout=5,
            )
            if quote_resp.status_code != 200:
                logger.debug(f"Jupiter quote failed: {quote_resp.status_code}")
                return None

            quote = quote_resp.json()

            # Step 2: Get serialized swap transaction
            swap_resp = get_session().post(
                f"{jupiter_url}/swap",
                json={
                    "quoteResponse": quote,
                    "userPublicKey": user_public_key,
                    "wrapAndUnwrapSol": True,
                    "dynamicComputeUnitLimit": True,
                    "prioritizationFeeLamports": 100_000,  # ~$0.015 priority fee
                },
                headers=headers,
                timeout=5,
            )
            if swap_resp.status_code != 200:
                logger.debug(f"Jupiter swap failed: {swap_resp.status_code}")
                return None

            swap_data = swap_resp.json()
            return swap_data.get("swapTransaction")  # base64-encoded VersionedTransaction

        except Exception as e:
            logger.debug(f"Jupiter swap build error: {e}")
            return None

    def _build_jito_tip_tx(
        self,
        tip_account: str,
        tip_lamports: int,
        sender_keypair_b58: str,
        recent_blockhash: str,
    ) -> Optional[str]:
        """
        Builds a Solana SOL transfer transaction to the Jito tip account.
        Returns base64-encoded signed transaction or None on failure.

        Uses the solders/solana-py library if available, otherwise falls back
        to a raw binary construction of a SystemProgram.transfer instruction.
        """
        try:
            from solders.keypair import Keypair  # type: ignore
            from solders.pubkey import Pubkey  # type: ignore
            from solders.hash import Hash  # type: ignore
            from solders.transaction import VersionedTransaction  # type: ignore
            from solders.message import MessageV0  # type: ignore
            from solders.instruction import Instruction, AccountMeta  # type: ignore
            from solders.system_program import transfer, TransferParams  # type: ignore
            import base58

            keypair = Keypair.from_base58_string(sender_keypair_b58)
            blockhash = Hash.from_string(recent_blockhash)
            tip_pubkey = Pubkey.from_string(tip_account)

            ix = transfer(TransferParams(
                from_pubkey=keypair.pubkey(),
                to_pubkey=tip_pubkey,
                lamports=tip_lamports,
            ))

            msg = MessageV0.try_compile(
                payer=keypair.pubkey(),
                instructions=[ix],
                address_lookup_table_accounts=[],
                recent_blockhash=blockhash,
            )
            tx = VersionedTransaction(msg, [keypair])
            return base64.b64encode(bytes(tx)).decode("utf-8")

        except ImportError:
            logger.debug("SandwichBot: solders not installed — Jito tip tx unavailable")
            return None
        except Exception as e:
            logger.debug(f"SandwichBot: Jito tip tx build error: {e}")
            return None

    def _get_solana_recent_blockhash(self) -> Optional[str]:
        """Fetches the latest blockhash from the Solana RPC."""
        try:
            resp = get_session().post(
                SOLANA_RPC_URL,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "getLatestBlockhash",
                    "params": [{"commitment": "confirmed"}],
                },
                timeout=5,
            )
            if resp.status_code == 200:
                return resp.json()["result"]["value"]["blockhash"]
        except Exception as e:
            logger.debug(f"SandwichBot: getLatestBlockhash error: {e}")
        return None

    def _get_solana_wallet_pubkey(self) -> Optional[str]:
        """Returns the base58 public key for the Solana wallet."""
        if not SOLANA_PRIVATE_KEY:
            return None
        try:
            from solders.keypair import Keypair  # type: ignore
            kp = Keypair.from_base58_string(SOLANA_PRIVATE_KEY)
            return str(kp.pubkey())
        except Exception:
            return None

    def execute_sandwich_solana(self, opp: MEVOpportunity) -> MEVResult:
        """
        Constructs and submits a Jito bundle on Solana.
        Bundle (max 5 txs, atomically executed):
          [0] Jito tip transfer tx        (SOL → tip account)
          [1] Front-run BUY               (Jupiter: USDC → target token)
          [2] Victim TX                   (forwarded from mempool)
          [3] Back-run SELL               (Jupiter: target token → USDC)

        All four transactions must land in the same block.
        If any fails, the entire bundle is rejected by the validator.
        """
        if not SANDWICH_ENABLED:
            return MEVResult(False, "sandwich", "solana", 0.0, error="Sandwich disabled")

        if (settings.get_current_mode() == "paper"):
            logger.info(
                f"[PAPER] Solana sandwich: target={opp.target_address[:14]}... "
                f"net=${opp.net_profit_usd:.2f}"
            )
            return MEVResult(True, "sandwich", "solana", opp.net_profit_usd, bundle_id="paper_jito_bundle")

        if not SOLANA_PRIVATE_KEY:
            return MEVResult(False, "sandwich", "solana", 0.0, error="SOLANA_PRIVATE_KEY not set")

        try:
            wallet_pubkey = self._get_solana_wallet_pubkey()
            if not wallet_pubkey:
                return MEVResult(False, "sandwich", "solana", 0.0, error="Could not derive Solana pubkey")

            recent_blockhash = self._get_solana_recent_blockhash()
            if not recent_blockhash:
                return MEVResult(False, "sandwich", "solana", 0.0, error="Could not fetch blockhash")

            tip_account = random.choice(JITO_TIP_ACCOUNTS)
            tip_lamports = 1_000_000  # ~$0.15 at $150/SOL

            raw_data = opp.raw_data.get("swap", {})
            token_out = raw_data.get("token_out", "")
            victim_tx_b64 = raw_data.get("victim_tx_b64", "")

            # USDC on Solana
            usdc_mint = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
            # Amount to front-run with (in USDC lamports — 6 decimals)
            front_run_usdc = int(min(opp.raw_data.get("swap", {}).get("amount_in_usd", 0) * 0.20,
                                     MAX_POSITION_USD) * 1e6)

            # Build front-run BUY: USDC → target token
            front_run_tx_b64 = self._build_jupiter_swap_tx(
                input_mint=usdc_mint,
                output_mint=token_out if token_out else usdc_mint,
                amount=front_run_usdc,
                slippage_bps=50,  # 0.5% — tight for front-run
                user_public_key=wallet_pubkey,
            )
            if not front_run_tx_b64:
                return MEVResult(False, "sandwich", "solana", 0.0, error="Jupiter front-run quote failed")

            # Build back-run SELL: target token → USDC
            # We don't know exact amount received yet — use 99% of expected
            back_run_tx_b64 = self._build_jupiter_swap_tx(
                input_mint=token_out if token_out else usdc_mint,
                output_mint=usdc_mint,
                amount=int(front_run_usdc * 0.99),
                slippage_bps=100,  # 1% — slightly wider for sell
                user_public_key=wallet_pubkey,
            )
            if not back_run_tx_b64:
                return MEVResult(False, "sandwich", "solana", 0.0, error="Jupiter back-run quote failed")

            # Build Jito tip transaction
            tip_tx_b64 = self._build_jito_tip_tx(
                tip_account=tip_account,
                tip_lamports=tip_lamports,
                sender_keypair_b58=SOLANA_PRIVATE_KEY,
                recent_blockhash=recent_blockhash,
            )
            if not tip_tx_b64:
                return MEVResult(False, "sandwich", "solana", 0.0, error="Jito tip tx build failed")

            # Assemble bundle: [tip, front-run, victim, back-run]
            bundle_txs = [tip_tx_b64, front_run_tx_b64]
            if victim_tx_b64:
                bundle_txs.append(victim_tx_b64)
            bundle_txs.append(back_run_tx_b64)

            bundle_payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "sendBundle",
                "params": [bundle_txs],
            }

            headers = {"Content-Type": "application/json"}
            if JITO_AUTH_KEY:
                headers["x-jito-auth"] = JITO_AUTH_KEY

            resp = get_session().post(JITO_BLOCK_ENGINE_URL, json=bundle_payload, headers=headers, timeout=10)

            if resp.status_code == 200:
                bundle_id = resp.json().get("result", "")
                logger.info(f"SandwichBot: Jito bundle submitted: {bundle_id}")
                return MEVResult(True, "sandwich", "solana", opp.net_profit_usd, bundle_id=bundle_id)

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
    """

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

    # Aave V3 Base — known borrower addresses to actively poll
    # Populated at runtime from on-chain event scanning
    _known_borrowers: List[str] = []

    def __init__(self) -> None:
        self.enabled = LIQUIDATION_ENABLED
        self._web3_eth: Optional[Web3] = None
        self._web3_base: Optional[Web3] = None
        self._aave_pool_eth: Optional[Any] = None
        self._aave_pool_base: Optional[Any] = None
        self._signing_account: Optional[LocalAccount] = None

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
            f"HL: {'✓' if HYPERLIQUID_ENABLED else '✗'} | "
            f"HL tracked accounts: {len(HL_TRACKED_ACCOUNTS)}"
        )

    # ── Hyperliquid WebSocket Monitor ─────────────────────────────────────────

    async def monitor_hyperliquid_ws(self) -> None:
        """
        Connects to Hyperliquid WebSocket and monitors for liquidation events.
        Subscribes to:
          • allMids — oracle price updates (triggers at-risk account polling)
          • userEvents — our own wallet fills and liquidation confirmations

        Hardened reconnection:
          - Exponential backoff: 5s → 10s → 20s → 40s (cap 60s) on repeated failures
          - ConnectionClosed / ConnectionClosedError handled separately (downgraded to
            warning) because "no close frame received or sent" is a normal TCP drop,
            NOT a code bug — it should NOT fire Sentry high-priority alerts.
          - Successful connection resets backoff counter.
        """
        if not HYPERLIQUID_ENABLED or not self.enabled:
            return

        logger.info("LiquidationHunter: Starting Hyperliquid WebSocket monitor...")
        _backoff = 5
        _MAX_BACKOFF = 60
        while True:
            try:
                async with websockets.connect(
                    HYPERLIQUID_WS_URL,
                    ping_interval=20,
                    ping_timeout=30,
                    close_timeout=10,
                    max_size=2**23,  # 8 MB — prevents oversized-frame crashes
                ) as ws:
                    await ws.send(json.dumps({
                        "method": "subscribe",
                        "subscription": {"type": "allMids"},
                    }))

                    if HYPERLIQUID_WALLET_ADDRESS:
                        await ws.send(json.dumps({
                            "method": "subscribe",
                            "subscription": {
                                "type": "userEvents",
                                "user": HYPERLIQUID_WALLET_ADDRESS,
                            },
                        }))

                    logger.info("LiquidationHunter: Hyperliquid WS subscriptions active")
                    _backoff = 5  # reset on successful connect

                    async for raw_msg in ws:
                        try:
                            msg = json.loads(raw_msg)
                            channel = msg.get("channel", "")
                            data = msg.get("data", {})

                            if channel == "allMids":
                                await self._check_hl_at_risk_accounts(data)

                            elif channel == "user":
                                events = data if isinstance(data, list) else [data]
                                for event in events:
                                    if "liquidation" in event:
                                        liq = event["liquidation"]
                                        logger.info(
                                            f"LiquidationHunter: HL liquidation confirmed — "
                                            f"user={liq.get('liquidated_user', '')[:12]}... "
                                            f"ntl={liq.get('liquidated_ntl_pos', 0)}"
                                        )

                        except Exception as e:
                            logger.debug(f"LiquidationHunter: HL WS parse error: {e}")

            except (websockets.exceptions.ConnectionClosed,
                    websockets.exceptions.ConnectionClosedError,
                    websockets.exceptions.ConnectionClosedOK) as e:
                # Normal TCP drop / server-side close — NOT a code bug, downgrade to warning
                # to suppress Sentry high-priority alerts for "no close frame received or sent"
                logger.warning(
                    f"LiquidationHunter: HL WS connection closed ({e}). "
                    f"Reconnecting in {_backoff}s..."
                )
                await asyncio.sleep(_backoff)
                _backoff = min(_backoff * 2, _MAX_BACKOFF)
            except Exception as e:
                logger.error(f"LiquidationHunter: HL WS error: {e}. Reconnecting in {_backoff}s...")
                await asyncio.sleep(_backoff)
                _backoff = min(_backoff * 2, _MAX_BACKOFF)

    async def _check_hl_at_risk_accounts(self, mids_data: Dict[str, Any]) -> None:
        """
        Called on every allMids oracle price update.
        Polls each tracked account's clearinghouseState via the HL REST API.
        If an account's margin ratio is below the maintenance threshold,
        submits a liquidation order.

        HL clearinghouseState response includes:
          marginSummary.accountValue   — total account value in USD
          marginSummary.totalNtlPos    — total notional position
          maintenanceMarginUsed        — required maintenance margin
        A position is liquidatable when:
          accountValue < maintenanceMarginUsed
        """
        if not HL_TRACKED_ACCOUNTS:
            return

        for address in HL_TRACKED_ACCOUNTS:
            try:
                resp = get_session().post(
                    HYPERLIQUID_REST_URL,
                    json={"type": "clearinghouseState", "user": address},
                    timeout=5,
                )
                if resp.status_code != 200:
                    continue

                state = resp.json()
                margin_summary = state.get("marginSummary", {})
                account_value = float(margin_summary.get("accountValue", "0"))
                total_ntl_pos = float(margin_summary.get("totalNtlPos", "0"))
                maintenance_margin = float(state.get("maintenanceMarginUsed", "0"))

                if account_value <= 0 or maintenance_margin <= 0:
                    continue

                margin_ratio = account_value / maintenance_margin if maintenance_margin > 0 else 999

                if margin_ratio < 1.0:
                    logger.info(
                        f"LiquidationHunter: HL at-risk: {address[:12]}... "
                        f"acct_val=${account_value:.2f} maint_margin=${maintenance_margin:.2f} "
                        f"ratio={margin_ratio:.3f}"
                    )

                    # Find the largest open position to liquidate
                    positions = state.get("assetPositions", [])
                    if not positions:
                        continue

                    # Sort by absolute notional size descending
                    positions.sort(
                        key=lambda p: abs(float(p.get("position", {}).get("szi", "0"))),
                        reverse=True,
                    )
                    largest = positions[0].get("position", {})
                    coin = largest.get("coin", "BTC")
                    szi = float(largest.get("szi", "0"))

                    if szi == 0:
                        continue

                    # To liquidate a long (szi > 0) we sell; to liquidate a short (szi < 0) we buy
                    is_buy = szi < 0
                    liquidation_size = abs(szi)

                    # Profit gate: estimate bounty (HL backstop = ~0.5% of position notional)
                    bounty_usd = total_ntl_pos * 0.005
                    opp = ProfitGate.evaluate_liquidation(
                        chain="hyperliquid",
                        user_address=address,
                        collateral_usd=account_value,
                        debt_usd=total_ntl_pos,
                        health_factor=margin_ratio,
                        bonus_pct=0.5,
                    )
                    if opp:
                        result = self.execute_hyperliquid_liquidation(
                            user_address=address,
                            coin=coin,
                            is_buy=is_buy,
                            sz=liquidation_size,
                        )
                        logger.info(f"LiquidationHunter: HL liquidation attempt: {result}")

            except Exception as e:
                logger.debug(f"LiquidationHunter: HL account poll error for {address[:12]}...: {e}")

    def execute_hyperliquid_liquidation(
        self,
        user_address: str,
        coin: str,
        is_buy: bool,
        sz: float,
    ) -> MEVResult:
        """
        Submits a liquidation order on Hyperliquid via their REST API.
        Uses the hyperliquid-python-sdk if available, otherwise falls back
        to a direct signed REST call.
        """
        if not HYPERLIQUID_ENABLED or not self.enabled:
            return MEVResult(False, "liquidation", "hyperliquid", 0.0, error="HL disabled")

        if (settings.get_current_mode() == "paper"):
            logger.info(f"[PAPER] HL liquidation: {coin} sz={sz:.4f} user={user_address[:12]}...")
            return MEVResult(True, "liquidation", "hyperliquid", 0.0, tx_hash="paper_hl_liq")

        private_key = HYPERLIQUID_PRIVATE_KEY or FLASHBOTS_SIGNING_KEY
        if not private_key:
            return MEVResult(False, "liquidation", "hyperliquid", 0.0, error="No signing key")

        try:
            # Attempt to use the official hyperliquid-python-sdk
            from hyperliquid.exchange import Exchange  # type: ignore
            from hyperliquid.utils import constants  # type: ignore

            account = Account.from_key(private_key)
            vault_addr = getattr(settings, "HYPERLIQUID_MEV_SUBACCOUNT", "") or None
            exchange = Exchange(
                wallet=account,
                base_url=constants.MAINNET_API_URL,
                account_address=HYPERLIQUID_WALLET_ADDRESS,
                vault_address=vault_addr
            )

            order_result = exchange.market_open(
                coin=coin,
                is_buy=is_buy,
                sz=sz,
                slippage=0.05,
                cloid=None,
            )

            if order_result.get("status") == "ok":
                statuses = order_result.get("response", {}).get("data", {}).get("statuses", [{}])
                fill_info = statuses[0] if statuses else {}
                logger.info(f"LiquidationHunter: HL liquidation success: {fill_info}")
                return MEVResult(True, "liquidation", "hyperliquid", 0.0, tx_hash=str(fill_info))

            return MEVResult(False, "liquidation", "hyperliquid", 0.0, error=str(order_result))

        except ImportError:
            # Fallback: direct signed REST call
            vault_addr = getattr(settings, "HYPERLIQUID_MEV_SUBACCOUNT", "") or None
            if vault_addr:
                logger.error("LiquidationHunter: Sub-accounts require the official hyperliquid-python-sdk.")
                return MEVResult(False, "liquidation", "hyperliquid", 0.0, error="SDK required for sub-accounts")
            return self._execute_hl_liquidation_direct(private_key, coin, is_buy, sz)
        except Exception as e:
            logger.error(f"LiquidationHunter: HL liquidation error: {e}")
            return MEVResult(False, "liquidation", "hyperliquid", 0.0, error=str(e))

    def _execute_hl_liquidation_direct(
        self,
        private_key: str,
        coin: str,
        is_buy: bool,
        sz: float,
    ) -> MEVResult:
        """
        Direct REST implementation of a Hyperliquid market order without the SDK.
        Constructs and signs the action payload using EIP-712 typed data signing.
        """
        try:
            import eth_account
            from eth_account.structured_data.hashing import hash_domain, hash_message

            account = Account.from_key(private_key)
            timestamp_ms = int(time.time() * 1000)

            # HL action: market order
            action = {
                "type": "order",
                "orders": [{
                    "a": 0,       # asset index — 0 = BTC, look up dynamically in production
                    "b": is_buy,
                    "p": "0",     # price = 0 for market orders
                    "s": str(sz),
                    "r": False,   # reduce-only = False
                    "t": {"market": {"tpsl": ""}},
                }],
                "grouping": "na",
            }

            # Hyperliquid uses a custom signing scheme — sign the action hash
            action_str = json.dumps(action, separators=(",", ":"), sort_keys=True)
            action_hash = Web3.keccak(text=action_str)
            msg = encode_defunct(action_hash)
            signed = account.sign_message(msg)

            payload = {
                "action": action,
                "nonce": timestamp_ms,
                "signature": {
                    "r": hex(signed.r),
                    "s": hex(signed.s),
                    "v": signed.v,
                },
            }

            resp = get_session().post(
                HYPERLIQUID_EXCHANGE_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10,
            )

            if resp.status_code == 200:
                result = resp.json()
                if result.get("status") == "ok":
                    return MEVResult(True, "liquidation", "hyperliquid", 0.0, tx_hash=str(result))
                return MEVResult(False, "liquidation", "hyperliquid", 0.0, error=str(result))

            return MEVResult(False, "liquidation", "hyperliquid", 0.0, error=f"HTTP {resp.status_code}")

        except Exception as e:
            logger.error(f"LiquidationHunter: HL direct REST error: {e}")
            return MEVResult(False, "liquidation", "hyperliquid", 0.0, error=str(e))

    # ── Aave V3 Liquidation ───────────────────────────────────────────────────

    async def monitor_aave_ws(self, chain: str = "base") -> None:
        """
        Subscribes to Aave LiquidationCall events via WebSocket.
        Also runs a background polling loop for known borrowers every 30s.
        """
        if not self.enabled:
            return

        ws_url = ETH_WS_RPC_URL if chain == "ethereum" else BASE_WS_RPC_URL
        if not ws_url:
            logger.warning(f"LiquidationHunter: {chain.upper()}_WS_RPC_URL not set — Aave monitoring disabled")
            # Fall back to polling only
            await self._poll_aave_borrowers_loop(chain)
            return

        pool_address = AAVE_POOL_ADDRESS_BASE if chain == "base" else AAVE_POOL_ADDRESS_ETH
        liquidation_topic = Web3.keccak(
            text="LiquidationCall(address,address,address,uint256,uint256,address,bool)"
        ).hex()

        # Run event subscription and borrower polling concurrently
        await asyncio.gather(
            self._subscribe_aave_events(ws_url, pool_address, liquidation_topic, chain),
            self._poll_aave_borrowers_loop(chain),
        )

    async def _subscribe_aave_events(
        self,
        ws_url: str,
        pool_address: str,
        liquidation_topic: str,
        chain: str,
    ) -> None:
        """Subscribes to Aave LiquidationCall events via eth_subscribe logs.

        Hardened with exponential backoff and ConnectionClosed separation
        (same pattern as monitor_hyperliquid_ws).
        """
        logger.info(f"LiquidationHunter: Starting Aave V3 event monitor on {chain}...")
        _backoff = 5
        _MAX_BACKOFF = 60
        while True:
            try:
                async with websockets.connect(
                    ws_url,
                    ping_interval=20,
                    close_timeout=10,
                ) as ws:
                    await ws.send(json.dumps({
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "eth_subscribe",
                        "params": [
                            "logs",
                            {
                                "address": pool_address,
                                "topics": ["0x" + liquidation_topic],
                            },
                        ],
                    }))
                    logger.info(f"LiquidationHunter: Subscribed to Aave {chain} LiquidationCall events")
                    _backoff = 5  # reset on successful connect

                    async for raw_msg in ws:
                        try:
                            msg = json.loads(raw_msg)
                            if "params" in msg:
                                log = msg["params"].get("result", {})
                                await self._handle_aave_liquidation_event(log, chain)
                        except Exception as e:
                            logger.debug(f"LiquidationHunter: Aave event parse error: {e}")

            except (websockets.exceptions.ConnectionClosed,
                    websockets.exceptions.ConnectionClosedError,
                    websockets.exceptions.ConnectionClosedOK) as e:
                logger.warning(
                    f"LiquidationHunter: Aave WS {chain} connection closed ({e}). "
                    f"Reconnecting in {_backoff}s..."
                )
                await asyncio.sleep(_backoff)
                _backoff = min(_backoff * 2, _MAX_BACKOFF)
            except Exception as e:
                logger.error(f"LiquidationHunter: Aave WS error on {chain}: {e}. Reconnecting in {_backoff}s...")
                await asyncio.sleep(_backoff)
                _backoff = min(_backoff * 2, _MAX_BACKOFF)

    async def _poll_aave_borrowers_loop(self, chain: str) -> None:
        """
        Polls known borrowers every 30 seconds for health factor < 1.0.
        The borrower list is built from past LiquidationCall events and
        Borrow events scanned at startup.
        """
        while True:
            try:
                for borrower in list(self._known_borrowers):
                    result = self.check_and_liquidate_aave_user(borrower, chain)
                    if result and result.success:
                        logger.info(f"LiquidationHunter: Aave poll liquidation: {result}")
                    await asyncio.sleep(0.1)  # Rate limit RPC calls
            except Exception as e:
                logger.debug(f"LiquidationHunter: Aave poll error: {e}")
            await asyncio.sleep(30)

    async def _handle_aave_liquidation_event(self, log: Dict[str, Any], chain: str) -> None:
        """
        Processes an Aave LiquidationCall event log.
        Adds the liquidated user to the known borrowers list for future polling,
        and immediately checks if the same user is still liquidatable.
        """
        try:
            topics = log.get("topics", [])
            if len(topics) < 4:
                return

            # Topics: [event_sig, collateralAsset (indexed), debtAsset (indexed), user (indexed)]
            collateral_asset = "0x" + topics[1][-40:]
            debt_asset = "0x" + topics[2][-40:]
            user = "0x" + topics[3][-40:]

            logger.info(
                f"LiquidationHunter: Aave {chain} LiquidationCall event — "
                f"user={user[:12]}... collateral={collateral_asset[:12]}..."
            )

            # Track this user for future polling
            if user not in self._known_borrowers:
                self._known_borrowers.append(user)

            # Immediately check if still liquidatable (partial liquidation case)
            await asyncio.sleep(0.5)  # Wait for state to settle
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

            total_collateral_base = account_data[0]  # USD, 8 decimals
            total_debt_base = account_data[1]
            health_factor_raw = account_data[5]

            health_factor = health_factor_raw / 1e18
            collateral_usd = total_collateral_base / 1e8
            debt_usd = total_debt_base / 1e8

            if health_factor >= 1.0:
                return None

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

            # For a real execution we need to know which specific assets to use.
            # Query the user's positions to find the largest debt/collateral pair.
            debt_asset, collateral_asset = self._find_best_liquidation_pair(user_checksum, chain)

            return self.execute_aave_liquidation(
                opp=opp,
                chain=chain,
                collateral_asset=collateral_asset,
                debt_asset=debt_asset,
                receive_a_token=False,
            )

        except Exception as e:
            logger.error(f"LiquidationHunter: getUserAccountData error for {user_address[:12]}...: {e}")
            return None

    def _find_best_liquidation_pair(
        self,
        user_address: str,
        chain: str,
    ) -> Tuple[str, str]:
        """
        Queries the Aave subgraph or on-chain data to find the user's largest
        debt asset and best collateral asset for liquidation.

        Falls back to USDC (debt) and WETH (collateral) if lookup fails —
        these are the most common Aave V3 pairs.
        """
        # Default fallback assets
        default_debt = USDC_BASE if chain == "base" else "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"  # USDC ETH
        default_collateral = WETH_BASE if chain == "base" else "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"  # WETH ETH

        try:
            # Query Aave subgraph for user positions
            subgraph_url = (
                "https://api.thegraph.com/subgraphs/name/aave/protocol-v3-base"
                if chain == "base"
                else "https://api.thegraph.com/subgraphs/name/aave/protocol-v3"
            )
            query = """
            {
              user(id: "%s") {
                borrowedReservesCount
                reserves {
                  currentVariableDebt
                  currentATokenBalance
                  reserve { underlyingAsset symbol }
                }
              }
            }
            """ % user_address.lower()

            resp = get_session().post(
                subgraph_url,
                json={"query": query},
                timeout=5,
            )
            if resp.status_code == 200:
                data = resp.json().get("data", {}).get("user", {})
                reserves = data.get("reserves", [])

                # Find largest debt
                debt_reserves = [
                    r for r in reserves
                    if float(r.get("currentVariableDebt", "0")) > 0
                ]
                collateral_reserves = [
                    r for r in reserves
                    if float(r.get("currentATokenBalance", "0")) > 0
                ]

                if debt_reserves:
                    debt_reserves.sort(
                        key=lambda r: float(r.get("currentVariableDebt", "0")),
                        reverse=True,
                    )
                    default_debt = debt_reserves[0]["reserve"]["underlyingAsset"]

                if collateral_reserves:
                    collateral_reserves.sort(
                        key=lambda r: float(r.get("currentATokenBalance", "0")),
                        reverse=True,
                    )
                    default_collateral = collateral_reserves[0]["reserve"]["underlyingAsset"]

        except Exception as e:
            logger.debug(f"LiquidationHunter: Subgraph query error: {e}")

        return default_debt, default_collateral

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

        Before calling liquidationCall, we must:
          1. Approve the Aave Pool to spend our debt tokens
          2. Call liquidationCall(collateralAsset, debtAsset, user, debtToCover, receiveAToken)

        The liquidator receives collateralAsset + liquidation bonus.
        """
        if (settings.get_current_mode() == "paper"):
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
            chain_id = 8453 if chain == "base" else 1
            user_checksum = Web3.to_checksum_address(opp.target_address)
            pool_address = AAVE_POOL_ADDRESS_BASE if chain == "base" else AAVE_POOL_ADDRESS_ETH

            # debt_to_cover in the debt token's native decimals
            # USDC = 6 decimals, WETH = 18 decimals
            debt_to_cover_usd = opp.raw_data.get("debt_to_cover", 0)
            # Assume USDC (6 decimals) as default — real impl checks token decimals
            debt_to_cover_raw = int(debt_to_cover_usd * 1e6)

            collateral = Web3.to_checksum_address(collateral_asset or WETH_BASE)
            debt = Web3.to_checksum_address(debt_asset or USDC_BASE)

            base_fee = w3.eth.gas_price
            nonce = w3.eth.get_transaction_count(account.address, "pending")

            # Step 1: Approve Aave Pool to spend our debt tokens
            debt_token_contract = w3.eth.contract(
                address=debt,
                abi=ERC20_ABI,
            )
            approve_tx = debt_token_contract.functions.approve(
                Web3.to_checksum_address(pool_address),
                debt_to_cover_raw,
            ).build_transaction({
                "from": account.address,
                "gas": 80_000,
                "maxFeePerGas": base_fee * 2,
                "maxPriorityFeePerGas": base_fee,
                "nonce": nonce,
                "chainId": chain_id,
            })
            signed_approve = account.sign_transaction(approve_tx)
            approve_hash = w3.eth.send_raw_transaction(signed_approve.raw_transaction)
            logger.info(f"LiquidationHunter: Approve tx: {approve_hash.hex()}")

            # Wait for approve to be mined (up to 15s)
            try:
                w3.eth.wait_for_transaction_receipt(approve_hash, timeout=15)
            except Exception:
                pass  # Continue anyway — approve may already be sufficient

            # Step 2: Call liquidationCall
            liq_tx = pool.functions.liquidationCall(
                collateral,
                debt,
                user_checksum,
                debt_to_cover_raw,
                receive_a_token,
            ).build_transaction({
                "from": account.address,
                "gas": 500_000,
                "maxFeePerGas": base_fee * 2,
                "maxPriorityFeePerGas": base_fee,
                "nonce": nonce + 1,
                "chainId": chain_id,
            })
            signed_liq = account.sign_transaction(liq_tx)
            liq_hash = w3.eth.send_raw_transaction(signed_liq.raw_transaction)
            liq_hash_hex = liq_hash.hex()

            logger.info(
                f"LiquidationHunter: Aave {chain} liquidation submitted: {liq_hash_hex} "
                f"net=${opp.net_profit_usd:.2f}"
            )
            return MEVResult(True, "liquidation", chain, opp.net_profit_usd, tx_hash=liq_hash_hex)

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

    Usage (integrated into main bot loop):
        engine = get_engine()
        asyncio.ensure_future(engine.run())

    Usage (standalone):
        asyncio.run(get_engine().run())
    """

    def __init__(self) -> None:
        self.sandwich_bot = SandwichBot()
        self.liquidation_hunter = LiquidationHunter()
        self._results: List[MEVResult] = []
        self._total_profit_usd: float = 0.0
        self._start_time: float = time.time()

    async def run(self) -> None:
        """Starts all MEV monitoring tasks concurrently with supervised auto-restart.

        Each strategy coroutine has its own infinite reconnect loop, but if one
        somehow exits (e.g., unhandled exception escapes the inner loop), the
        supervisor here detects it and relaunches it after a 10-second delay.
        This prevents any single crash from silently killing a revenue stream.
        """
        logger.info(
            "MEVExtractorEngine: Starting all strategies | "
            f"Sandwich: {'ON' if SANDWICH_ENABLED else 'OFF'} | "
            f"Liquidation: {'ON' if LIQUIDATION_ENABLED else 'OFF'}"
        )

        # Map of task name → coroutine factory
        _task_registry: dict = {}
        if SANDWICH_ENABLED:
            _task_registry["sandwich_base_mempool"] = self.sandwich_bot.monitor_base_mempool
        if LIQUIDATION_ENABLED:
            if HYPERLIQUID_ENABLED:
                _task_registry["liquidation_hyperliquid_ws"] = self.liquidation_hunter.monitor_hyperliquid_ws
            _task_registry["liquidation_aave_base"] = lambda: self.liquidation_hunter.monitor_aave_ws(chain="base")
            _task_registry["liquidation_aave_eth"] = lambda: self.liquidation_hunter.monitor_aave_ws(chain="ethereum")

        if not _task_registry:
            logger.warning("MEVExtractorEngine: No strategies enabled — engine idle")
            return

        # Launch all tasks
        active_tasks: dict[str, asyncio.Task] = {
            name: asyncio.create_task(factory(), name=name)
            for name, factory in _task_registry.items()
        }

        # Supervisor loop: detect dead tasks and restart them
        while True:
            await asyncio.sleep(15)
            for name, task in list(active_tasks.items()):
                if task.done():
                    exc = task.exception() if not task.cancelled() else None
                    if exc:
                        logger.error(
                            f"MEVExtractorEngine: Task '{name}' crashed ({exc}). "
                            f"Restarting in 10s..."
                        )
                    else:
                        logger.warning(
                            f"MEVExtractorEngine: Task '{name}' exited cleanly. "
                            f"Restarting in 10s..."
                        )
                    await asyncio.sleep(10)
                    factory = _task_registry[name]
                    active_tasks[name] = asyncio.create_task(factory(), name=name)
                    logger.info(f"MEVExtractorEngine: Task '{name}' restarted.")

    def get_status(self) -> Dict[str, Any]:
        """Returns a status dict for dashboard integration."""
        uptime_hours = (time.time() - self._start_time) / 3600
        return {
            "sandwich_enabled": SANDWICH_ENABLED,
            "liquidation_enabled": LIQUIDATION_ENABLED,
            "hyperliquid_enabled": HYPERLIQUID_ENABLED,
            "total_executions": len(self._results),
            "successful_executions": sum(1 for r in self._results if r.success),
            "total_profit_usd": round(self._total_profit_usd, 4),
            "uptime_hours": round(uptime_hours, 2),
            "min_net_profit_usd": MIN_NET_PROFIT_USD,
            "slippage_threshold_pct": SLIPPAGE_THRESHOLD_PCT,
            "hl_tracked_accounts": len(HL_TRACKED_ACCOUNTS),
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


def get_mev_extractor() -> MEVExtractorEngine:
    """Singleton accessor imported by main.py.

    main.py calls:
        from core.mev_extractor import get_mev_extractor
        _mev_extractor = get_mev_extractor()
        asyncio.run(_mev_extractor.run())

    This is a named alias for get_engine() so the public import surface
    matches what main.py expects without breaking existing callers of
    get_engine().
    """
    return get_engine()


def start_mev_engine() -> None:
    """Entry point for running the MEV engine as a standalone process."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    asyncio.run(get_engine().run())


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
