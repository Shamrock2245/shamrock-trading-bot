"""
config/chains.py — Multi-chain configuration for Shamrock Trading Bot.

Defines RPC endpoints, chain IDs, block explorer APIs, and DEX router
addresses for all supported chains including Solana. All sensitive values
(RPC keys) are loaded from environment variables — never hardcoded.
"""

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ChainConfig:
    """Complete configuration for a single EVM-compatible chain."""
    name: str
    chain_id: int
    rpc_url: str
    rpc_fallback: str
    explorer_api_url: str
    explorer_api_key_env: str          # Name of the env var holding the API key
    native_token: str                  # e.g. "ETH", "MATIC", "BNB", "SOL"
    native_token_decimals: int = 18
    wrapped_native: str = ""           # WETH, WMATIC, WBNB address
    chain_type: str = "evm"            # "evm" or "solana"
    # DEX router addresses
    uniswap_v3_router: Optional[str] = None
    uniswap_v3_quoter: Optional[str] = None
    oneinch_router: Optional[str] = None
    aerodrome_router: Optional[str] = None   # Base only
    camelot_router: Optional[str] = None     # Arbitrum only
    quickswap_router: Optional[str] = None   # Polygon only
    pancakeswap_v3_router: Optional[str] = None  # BSC only
    jupiter_api_url: Optional[str] = None    # Solana only
    raydium_program_id: Optional[str] = None # Solana only
    # CoW Protocol
    cow_settlement: Optional[str] = None
    cow_vault_relayer: Optional[str] = None
    # Gas settings
    max_gas_gwei: int = 50
    block_time_seconds: float = 12.0
    # Stablecoin addresses for profit-taking
    usdc_address: str = ""
    # Solana-specific: USDC mint address
    usdc_mint: str = ""

    @property
    def explorer_api_key(self) -> str:
        return os.getenv(self.explorer_api_key_env, "")

    @property
    def is_solana(self) -> bool:
        return self.chain_type == "solana"

    @property
    def is_evm(self) -> bool:
        return self.chain_type == "evm"


# ─────────────────────────────────────────────────────────────────────────────
# Chain Definitions
# ─────────────────────────────────────────────────────────────────────────────

CHAINS: dict[str, ChainConfig] = {

    "ethereum": ChainConfig(
        name="Ethereum",
        chain_id=1,
        rpc_url=os.getenv("ETH_RPC_URL", "https://cloudflare-eth.com"),
        rpc_fallback=os.getenv("ETH_RPC_FALLBACK", "https://eth.llamarpc.com"),
        explorer_api_url="https://api.etherscan.io/api",
        explorer_api_key_env="ETHERSCAN_API_KEY",
        native_token="ETH",
        wrapped_native="0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
        uniswap_v3_router="0xE592427A0AEce92De3Edee1F18E0157C05861564",
        uniswap_v3_quoter="0xb27308f9F90D607463bb33eA1BeBb41C27CE5AB6",
        oneinch_router="0x1111111254EEB25477B68fb85Ed929f73A960582",
        cow_settlement="0x9008D19f58AAbD9eD0D60971565AA8510560ab41",
        cow_vault_relayer="0xC92E8bdf79f0507f65a392b0ab4667716BFE0110",
        max_gas_gwei=int(os.getenv("MAX_GAS_GWEI", "50")),
        block_time_seconds=12.0,
        usdc_address="0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
    ),

    "base": ChainConfig(
        name="Base",
        chain_id=8453,
        rpc_url=os.getenv("BASE_RPC_URL", "https://mainnet.base.org"),
        rpc_fallback=os.getenv("BASE_RPC_FALLBACK", "https://base.publicnode.com"),
        explorer_api_url="https://api.basescan.org/api",
        explorer_api_key_env="BASESCAN_API_KEY",
        native_token="ETH",
        wrapped_native="0x4200000000000000000000000000000000000006",
        uniswap_v3_router="0x2626664c2603336E57B271c5C0b26F421741e481",
        uniswap_v3_quoter="0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a",
        aerodrome_router="0xcF77a3Ba9A5CA399B7c97c74d54e5b1Beb874E43",
        oneinch_router="0x1111111254EEB25477B68fb85Ed929f73A960582",
        max_gas_gwei=5,
        block_time_seconds=2.0,
        usdc_address="0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    ),

    "arbitrum": ChainConfig(
        name="Arbitrum One",
        chain_id=42161,
        rpc_url=os.getenv("ARB_RPC_URL", "https://arb1.arbitrum.io/rpc"),
        rpc_fallback=os.getenv("ARB_RPC_FALLBACK", "https://arbitrum.publicnode.com"),
        explorer_api_url="https://api.arbiscan.io/api",
        explorer_api_key_env="ARBISCAN_API_KEY",
        native_token="ETH",
        wrapped_native="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
        uniswap_v3_router="0xE592427A0AEce92De3Edee1F18E0157C05861564",
        uniswap_v3_quoter="0xb27308f9F90D607463bb33eA1BeBb41C27CE5AB6",
        camelot_router="0xc873fEcbd354f5A56E00E710B90EF4201db2448d",
        oneinch_router="0x1111111254EEB25477B68fb85Ed929f73A960582",
        max_gas_gwei=2,
        block_time_seconds=0.25,
        usdc_address="0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
    ),

    "polygon": ChainConfig(
        name="Polygon",
        chain_id=137,
        rpc_url=os.getenv("POLYGON_RPC_URL", "https://polygon-rpc.com"),
        rpc_fallback=os.getenv("POLYGON_RPC_FALLBACK", "https://polygon.publicnode.com"),
        explorer_api_url="https://api.polygonscan.com/api",
        explorer_api_key_env="POLYGONSCAN_API_KEY",
        native_token="MATIC",
        wrapped_native="0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270",
        uniswap_v3_router="0xE592427A0AEce92De3Edee1F18E0157C05861564",
        uniswap_v3_quoter="0xb27308f9F90D607463bb33eA1BeBb41C27CE5AB6",
        quickswap_router="0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff",
        oneinch_router="0x1111111254EEB25477B68fb85Ed929f73A960582",
        max_gas_gwei=200,
        block_time_seconds=2.0,
        usdc_address="0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359",
    ),

    "bsc": ChainConfig(
        name="BNB Smart Chain",
        chain_id=56,
        rpc_url=os.getenv("BSC_RPC_URL", "https://bsc-dataseed.binance.org"),
        rpc_fallback=os.getenv("BSC_RPC_FALLBACK", "https://bsc.publicnode.com"),
        explorer_api_url="https://api.bscscan.com/api",
        explorer_api_key_env="BSCSCAN_API_KEY",
        native_token="BNB",
        wrapped_native="0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",
        pancakeswap_v3_router="0x13f4EA83D0bd40E75C8222255bc855a974568Dd4",
        oneinch_router="0x1111111254EEB25477B68fb85Ed929f73A960582",
        max_gas_gwei=5,
        block_time_seconds=3.0,
        usdc_address="0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d",
    ),

    # ── Solana ────────────────────────────────────────────────────────────────
    # Solana is not EVM — uses Jupiter aggregator for swaps, native SOL for gas.
    # chain_id=900 is a convention used by DexScreener/GeckoTerminal for Solana.
    "solana": ChainConfig(
        name="Solana",
        chain_id=900,
        chain_type="solana",
        rpc_url=os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com"),
        rpc_fallback=os.getenv("SOLANA_RPC_FALLBACK", "https://solana-mainnet.g.alchemy.com/v2/demo"),
        explorer_api_url="https://api.solscan.io",
        explorer_api_key_env="SOLSCAN_API_KEY",
        native_token="SOL",
        native_token_decimals=9,
        wrapped_native="So11111111111111111111111111111111111111112",  # Wrapped SOL mint
        jupiter_api_url=os.getenv("JUPITER_API_URL", "https://quote-api.jup.ag/v6"),
        raydium_program_id="675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8",
        max_gas_gwei=0,          # Solana uses lamports, not gwei
        block_time_seconds=0.4,  # ~400ms slot time
        # USDC on Solana (SPL token mint address)
        usdc_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        usdc_address="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    ),
}

# ─────────────────────────────────────────────────────────────────────────────
# DexScreener chain ID mapping (their internal chain names)
# ─────────────────────────────────────────────────────────────────────────────
DEXSCREENER_CHAIN_MAP = {
    "ethereum": "ethereum",
    "base": "base",
    "arbitrum": "arbitrum",
    "polygon": "polygon",
    "bsc": "bsc",
    "solana": "solana",
}

# GoPlus Security chain ID mapping
GOPLUS_CHAIN_MAP = {
    "ethereum": "1",
    "base": "8453",
    "arbitrum": "42161",
    "polygon": "137",
    "bsc": "56",
    "solana": "solana",  # GoPlus uses string "solana" for Solana
}

# Honeypot.is chain ID mapping (EVM only — Solana handled separately)
HONEYPOT_CHAIN_MAP = {
    "ethereum": 1,
    "base": 8453,
    "arbitrum": 42161,
    "polygon": 137,
    "bsc": 56,
}


def get_chain(chain_name: str) -> ChainConfig:
    """Get chain config by name. Raises KeyError if not found."""
    chain_name = chain_name.lower()
    if chain_name not in CHAINS:
        raise KeyError(f"Unknown chain: '{chain_name}'. Supported: {list(CHAINS.keys())}")
    return CHAINS[chain_name]


def get_all_chains() -> list[ChainConfig]:
    """Return all configured chains."""
    return list(CHAINS.values())


def get_evm_chains() -> list[ChainConfig]:
    """Return only EVM-compatible chains."""
    return [c for c in CHAINS.values() if c.is_evm]


def get_solana_chain() -> ChainConfig:
    """Return Solana chain config."""
    return CHAINS["solana"]
