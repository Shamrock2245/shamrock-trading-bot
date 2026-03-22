"""
config/wallets.py — Wallet configuration for Shamrock Trading Bot.

Defines the three managed wallets, their roles, strategy assignments,
and chain preferences. Private keys are NEVER stored here — they are
loaded exclusively from environment variables at runtime.

⚠️  SECURITY RULE: This file contains only PUBLIC addresses.
    Private keys must come from:
      - Environment variables (WALLET_PRIVATE_KEY_PRIMARY, etc.)
      - AWS Secrets Manager
      - HashiCorp Vault
    Never hardcode, log, or print private keys.

Solana wallets use a separate keypair (base58-encoded private key) stored
in WALLET_SOLANA_PRIVATE_KEY_PRIMARY / WALLET_SOLANA_PRIVATE_KEY_B env vars.
"""

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class WalletConfig:
    """Configuration for a single managed wallet."""
    alias: str                          # Human-readable name
    address: str                        # Public EVM address (safe to reference)
    private_key_env: str                # Name of env var holding the EVM private key
    role: str                           # Description of wallet's purpose
    strategies: list[str]               # Assigned strategy names
    chains: list[str]                   # Active chains for this wallet
    max_position_size_pct: float        # Max % of wallet per trade
    max_concurrent_positions: int       # Max open positions at once
    daily_loss_limit_eth: float         # Halt trading if daily loss exceeds this
    min_eth_balance_alert: float        # Alert if ETH balance drops below this
    is_cold_storage: bool = False       # If True, no automated trading — manual only
    # Solana-specific
    solana_address: str = ""            # Solana public key (base58)
    solana_private_key_env: str = ""    # Env var for Solana keypair (base58)

    @property
    def private_key(self) -> Optional[str]:
        """
        Load EVM private key from environment variable.
        Returns None if not set (paper trading mode).
        Never logs or exposes the key value.
        """
        key = os.getenv(self.private_key_env)
        if key and not key.startswith("your_"):
            return key
        return None

    @property
    def solana_private_key(self) -> Optional[str]:
        """
        Load Solana private key (base58) from environment variable.
        Returns None if not set.
        """
        if not self.solana_private_key_env:
            return None
        key = os.getenv(self.solana_private_key_env)
        if key and not key.startswith("your_"):
            return key
        return None

    @property
    def has_private_key(self) -> bool:
        """Check if EVM private key is configured (without exposing it)."""
        return self.private_key is not None

    @property
    def has_solana_key(self) -> bool:
        """Check if Solana private key is configured."""
        return self.solana_private_key is not None

    def supports_chain(self, chain: str) -> bool:
        """Check if this wallet is configured for a given chain."""
        return chain.lower() in self.chains

    def __repr__(self) -> str:
        """Safe repr — never includes private key."""
        return (
            f"WalletConfig(alias={self.alias!r}, "
            f"address={self.address!r}, "
            f"has_evm_key={self.has_private_key}, "
            f"has_sol_key={self.has_solana_key})"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Wallet Definitions
# ─────────────────────────────────────────────────────────────────────────────

WALLETS: dict[str, WalletConfig] = {

    "primary": WalletConfig(
        alias="Primary",
        address="0x3eb320fad3f51fe4f2a4531f911ef56694346eef",
        private_key_env="WALLET_PRIVATE_KEY_PRIMARY",
        solana_private_key_env="WALLET_SOLANA_PRIVATE_KEY_PRIMARY",
        solana_address=os.getenv("WALLET_SOLANA_ADDRESS_PRIMARY", ""),
        role="Main trading wallet — gem sniping & active positions",
        strategies=["gem_snipe", "momentum", "breakout"],
        chains=["ethereum", "base", "solana"],
        max_position_size_pct=float(os.getenv("MAX_POSITION_SIZE_PERCENT", "2.0")),
        max_concurrent_positions=int(os.getenv("MAX_CONCURRENT_POSITIONS", "10")),
        daily_loss_limit_eth=float(os.getenv("DAILY_LOSS_LIMIT_ETH", "0.5")),
        min_eth_balance_alert=float(os.getenv("MIN_ETH_BALANCE_ALERT", "0.05")),
    ),

    "wallet_b": WalletConfig(
        alias="Wallet B",
        address="0x0835eb8447f3ac90351951bb5d22e77afd9b81c0",
        private_key_env="WALLET_PRIVATE_KEY_B",
        solana_private_key_env="WALLET_SOLANA_PRIVATE_KEY_B",
        solana_address=os.getenv("WALLET_SOLANA_ADDRESS_B", ""),
        role="Secondary wallet — DCA, mean-reversion & Solana gem sniping",
        strategies=["dca", "mean_reversion", "gem_snipe"],
        chains=["arbitrum", "polygon", "bsc", "solana"],
        max_position_size_pct=float(os.getenv("MAX_POSITION_SIZE_PERCENT", "2.0")),
        max_concurrent_positions=int(os.getenv("MAX_CONCURRENT_POSITIONS", "10")),
        daily_loss_limit_eth=float(os.getenv("DAILY_LOSS_LIMIT_ETH", "0.5")),
        min_eth_balance_alert=float(os.getenv("MIN_ETH_BALANCE_ALERT", "0.05")),
    ),

    "wallet_c": WalletConfig(
        alias="Wallet C",
        address="0x32a71a0b8f10f263cd5d3fd8802fd9683ae6c860",
        private_key_env="WALLET_PRIVATE_KEY_C",
        role="Cold/reserve wallet — long-term holds & profit sweeps",
        strategies=["long_term"],
        chains=["ethereum"],
        max_position_size_pct=5.0,       # Larger positions — long-term conviction
        max_concurrent_positions=5,
        daily_loss_limit_eth=1.0,        # Higher tolerance for long-term holds
        min_eth_balance_alert=0.1,
        is_cold_storage=True,            # No automated trading — profit sweeps only
    ),
}


def get_wallet(alias: str) -> WalletConfig:
    """Get wallet config by alias. Raises KeyError if not found."""
    alias = alias.lower().replace(" ", "_")
    if alias not in WALLETS:
        raise KeyError(f"Unknown wallet: '{alias}'. Options: {list(WALLETS.keys())}")
    return WALLETS[alias]


def get_all_wallets() -> list[WalletConfig]:
    """Return all wallet configs."""
    return list(WALLETS.values())


def get_active_trading_wallets() -> list[WalletConfig]:
    """Return wallets that are configured for automated trading (not cold storage)."""
    return [w for w in WALLETS.values() if not w.is_cold_storage]


def get_wallets_for_chain(chain_name: str) -> list[WalletConfig]:
    """Return wallets that are active on a given chain."""
    return [w for w in WALLETS.values() if chain_name in w.chains and not w.is_cold_storage]


def get_all_addresses() -> list[str]:
    """Return all public EVM wallet addresses (safe to use anywhere)."""
    return [w.address for w in WALLETS.values()]
