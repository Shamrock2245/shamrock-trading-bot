"""
config/jit_settings.py — JIT Liquidity Sniper Settings

All settings are read from environment variables with safe defaults.
Add these to your .env file to configure JIT behavior.

Required for live execution:
  JIT_CONTRACT_ETHEREUM   = 0x...  (deployed JITLiquidityProvider.sol on Ethereum)
  JIT_CONTRACT_BASE       = 0x...  (deployed on Base)
  JIT_CONTRACT_ARBITRUM   = 0x...  (deployed on Arbitrum)
  JIT_MEMPOOL_RPC_URL     = wss://... (private WebSocket RPC for mempool access)
  FLASHBOTS_SIGNING_KEY   = 0x...  (Flashbots auth key — separate from wallet key)

Optional tuning:
  JIT_ENABLED                 = true
  JIT_MIN_TRADE_SIZE_USD      = 100000.0
  JIT_MAX_FLASH_BORROW_USD    = 500000.0
  JIT_MIN_PROFIT_USD          = 5.0
  JIT_MAX_GAS_TO_PROFIT_RATIO = 0.50
  JIT_TICK_RANGE_TICKS        = 10
  MEV_EXTRACTOR_ENABLED       = true
  MEV_BACKRUN_ENABLED         = true
  MEV_BACKRUN_MIN_PROFIT_USD  = 2.0
"""

import os

# ─────────────────────────────────────────────────────────────────────────────
# JIT Liquidity Sniper
# ─────────────────────────────────────────────────────────────────────────────

JIT_ENABLED: bool = os.getenv("JIT_ENABLED", "true").lower() == "true"

# Minimum whale trade size to trigger JIT provisioning
JIT_MIN_TRADE_SIZE_USD: float = float(os.getenv("JIT_MIN_TRADE_SIZE_USD", "100000.0"))

# Maximum flash loan size per JIT opportunity
JIT_MAX_FLASH_BORROW_USD: float = float(os.getenv("JIT_MAX_FLASH_BORROW_USD", "500000.0"))

# Minimum net profit (after gas + Aave fee) to proceed with JIT
JIT_MIN_PROFIT_USD: float = float(os.getenv("JIT_MIN_PROFIT_USD", "5.0"))

# Reject if estimated gas > this fraction of gross profit
JIT_MAX_GAS_TO_PROFIT_RATIO: float = float(os.getenv("JIT_MAX_GAS_TO_PROFIT_RATIO", "0.50"))

# Tick range around the whale's execution price (±N ticks × tick_spacing)
# Tighter = higher fee concentration but more likely to miss the swap
# Wider = lower fee concentration but more robust
JIT_TICK_RANGE_TICKS: int = int(os.getenv("JIT_TICK_RANGE_TICKS", "10"))

# Deployed JITLiquidityProvider.sol contract addresses per chain
# These MUST be set in .env for live execution
JIT_CONTRACT_ETHEREUM: str = os.getenv("JIT_CONTRACT_ETHEREUM", "")
JIT_CONTRACT_BASE: str = os.getenv("JIT_CONTRACT_BASE", "")
JIT_CONTRACT_ARBITRUM: str = os.getenv("JIT_CONTRACT_ARBITRUM", "")
JIT_CONTRACT_POLYGON: str = os.getenv("JIT_CONTRACT_POLYGON", "")

# Private WebSocket RPC URL for mempool access
# Use a private node (Alchemy, Infura, QuickNode) — NOT a public RPC
JIT_MEMPOOL_RPC_URL: str = os.getenv(
    "JIT_MEMPOOL_RPC_URL",
    os.getenv("FLASHBOTS_RPC_URL", "https://rpc.flashbots.net"),
)

# ─────────────────────────────────────────────────────────────────────────────
# MEV Extractor
# ─────────────────────────────────────────────────────────────────────────────

MEV_EXTRACTOR_ENABLED: bool = os.getenv("MEV_EXTRACTOR_ENABLED", "true").lower() == "true"
MEV_BACKRUN_ENABLED: bool = os.getenv("MEV_BACKRUN_ENABLED", "true").lower() == "true"
MEV_BACKRUN_MIN_PROFIT_USD: float = float(os.getenv("MEV_BACKRUN_MIN_PROFIT_USD", "2.0"))
