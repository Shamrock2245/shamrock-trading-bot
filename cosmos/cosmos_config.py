"""
cosmos/cosmos_config.py — Configuration for Cosmos ecosystem autotrading.

All chain configs, RPC endpoints, thresholds, and strategy parameters.
"""

import os
from dataclasses import dataclass, field


# ─────────────────────────────────────────────────────────────────────────────
# Chain Configuration
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CosmosChainConfig:
    """Configuration for a single Cosmos chain."""
    name: str
    chain_id: str
    denom: str                   # Native token denomination (e.g., "uatom")
    display_denom: str           # Human-readable (e.g., "ATOM")
    decimals: int                # Denomination decimals (6 for most Cosmos)
    bech32_prefix: str           # Address prefix
    rpc_url: str                 # Tendermint RPC
    rest_url: str                # LCD REST API
    gas_price: float             # Gas price in denom
    gas_adjustment: float = 1.3  # Gas estimate multiplier
    coin_type: int = 118         # BIP44 coin type (118 for Cosmos)
    # IBC channel IDs for common routes
    ibc_channels: dict = field(default_factory=dict)


# ── Chain definitions ────────────────────────────────────────────────────────

COSMOS_CHAINS = {
    "cosmoshub": CosmosChainConfig(
        name="Cosmos Hub",
        chain_id="cosmoshub-4",
        denom="uatom",
        display_denom="ATOM",
        decimals=6,
        bech32_prefix="cosmos",
        rpc_url=os.getenv("COSMOS_RPC_URL", "https://rpc.cosmos.directory/cosmoshub"),
        rest_url=os.getenv("COSMOS_REST_URL", "https://rest.cosmos.directory/cosmoshub"),
        gas_price=0.025,
        ibc_channels={
            "osmosis": "channel-141",       # Cosmos → Osmosis
            "stride": "channel-391",        # Cosmos → Stride
            "celestia": "channel-617",      # Cosmos → Celestia
        },
    ),
    "osmosis": CosmosChainConfig(
        name="Osmosis",
        chain_id="osmosis-1",
        denom="uosmo",
        display_denom="OSMO",
        decimals=6,
        bech32_prefix="osmo",
        rpc_url=os.getenv("OSMOSIS_RPC_URL", "https://rpc.cosmos.directory/osmosis"),
        rest_url=os.getenv("OSMOSIS_REST_URL", "https://rest.cosmos.directory/osmosis"),
        gas_price=0.0025,
        ibc_channels={
            "cosmoshub": "channel-0",       # Osmosis → Cosmos
            "celestia": "channel-6994",     # Osmosis → Celestia
            "stride": "channel-326",        # Osmosis → Stride
        },
    ),
    "celestia": CosmosChainConfig(
        name="Celestia",
        chain_id="celestia",
        denom="utia",
        display_denom="TIA",
        decimals=6,
        bech32_prefix="celestia",
        rpc_url=os.getenv("CELESTIA_RPC_URL", "https://rpc.cosmos.directory/celestia"),
        rest_url=os.getenv("CELESTIA_REST_URL", "https://rest.cosmos.directory/celestia"),
        gas_price=0.002,
        coin_type=118,
        ibc_channels={
            "osmosis": "channel-2",         # Celestia → Osmosis
        },
    ),
    "stride": CosmosChainConfig(
        name="Stride",
        chain_id="stride-1",
        denom="ustrd",
        display_denom="STRD",
        decimals=6,
        bech32_prefix="stride",
        rpc_url=os.getenv("STRIDE_RPC_URL", "https://rpc.cosmos.directory/stride"),
        rest_url=os.getenv("STRIDE_REST_URL", "https://rest.cosmos.directory/stride"),
        gas_price=0.0025,
        ibc_channels={
            "cosmoshub": "channel-0",       # Stride → Cosmos
            "osmosis": "channel-5",         # Stride → Osmosis
        },
    ),
    "neutron": CosmosChainConfig(
        name="Neutron",
        chain_id="neutron-1",
        denom="untrn",
        display_denom="NTRN",
        decimals=6,
        bech32_prefix="neutron",
        rpc_url=os.getenv("NEUTRON_RPC_URL", "https://rpc.cosmos.directory/neutron"),
        rest_url=os.getenv("NEUTRON_REST_URL", "https://rest.cosmos.directory/neutron"),
        gas_price=0.01,
        ibc_channels={
            "osmosis": "channel-10",
        },
    ),
}


# ─────────────────────────────────────────────────────────────────────────────
# Wallet addresses (derived from mnemonic — known values)
# ─────────────────────────────────────────────────────────────────────────────

COSMOS_ADDRESSES = {
    "cosmoshub": "cosmos1ddd7djxdc6hctnz7r5a6cmkgl582k07h4d46at",
    "osmosis": "osmo1ddd7djxdc6hctnz7r5a6cmkgl582k07hakx2te",
    "celestia": "celestia1ddd7djxdc6hctnz7r5a6cmkgl582k07hy8y28x",
    "stride": "stride1ddd7djxdc6hctnz7r5a6cmkgl582k07hkx4xf8",
    "neutron": "neutron1ddd7djxdc6hctnz7r5a6cmkgl582k07h3juc8v",
}


# ─────────────────────────────────────────────────────────────────────────────
# IBC denom registry (map IBC hash → human-readable on Osmosis)
# ─────────────────────────────────────────────────────────────────────────────

OSMOSIS_IBC_DENOMS = {
    # ATOM on Osmosis
    "ibc/27394FB092D2ECCD56123C74F36E4C1F926001CEADA9CA97EA622B25F41E5EB2": {
        "symbol": "ATOM",
        "decimals": 6,
        "origin_chain": "cosmoshub",
    },
    # TIA on Osmosis
    "ibc/D79E7D83AB399BFFF93433E54FAA480C191248FC556924A2A8351AE2638B3877": {
        "symbol": "TIA",
        "decimals": 6,
        "origin_chain": "celestia",
    },
    # stATOM on Osmosis (from Stride)
    "ibc/C140AFD542AE77BD7DCC83F13FDD8C5E5BB8C4929B0DC205DA45717718D4A8CA": {
        "symbol": "stATOM",
        "decimals": 6,
        "origin_chain": "stride",
    },
    # USDC on Osmosis (from Noble)
    "ibc/498A0751C798A0D9A389AA3691123DADA57DAA4FE165D5C75894505B876BA6E4": {
        "symbol": "USDC",
        "decimals": 6,
        "origin_chain": "noble",
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Strategy Parameters
# ─────────────────────────────────────────────────────────────────────────────

# Yield Strategy
YIELD_AUTO_COMPOUND_INTERVAL_HOURS = 24  # How often to claim + restake
STRIDE_LIQUID_STAKE_ENABLED = True       # Use Stride for liquid ATOM staking
NATIVE_STAKE_TIA = True                  # Stake TIA natively on Celestia
NATIVE_STAKE_OSMO = True                 # Stake OSMO natively (or superfluid)

# LP Strategy
LP_REBALANCE_THRESHOLD_PCT = 5.0         # Rebalance when price drifts this far
LP_COMPOUND_FEES = True                  # Auto-compound earned swap fees
SUPERFLUID_STAKING_ENABLED = True        # Use superfluid staking on Osmosis LPs

# Arbitrage Strategy
ARB_MIN_SPREAD_PCT = 0.3                 # Min spread needed to attempt arb
ARB_MAX_TRADE_USD = 200.0                # Max single arb trade size in USD
ARB_DAILY_LOSS_LIMIT_USD = 50.0          # Stop arb if daily losses exceed this
ARB_GAS_BUDGET_DAILY_USD = 5.0           # Max daily gas spend on arb
ARB_SCAN_INTERVAL_SECONDS = 30           # How often to check for arb opps

# Osmosis Pools of Interest
OSMOSIS_TARGET_POOLS = [
    # pool_id, pair, description
    (1, "ATOM/OSMO", "Deepest liquidity pool"),
    (678, "stATOM/ATOM", "Tight range, low IL"),
    (1263, "TIA/OSMO", "Celestia on Osmosis"),
]

# Paper mode (set from env)
COSMOS_MODE = os.getenv("COSMOS_MODE", os.getenv("MODE", "paper"))
