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


# ─────────────────────────────────────────────────────────────────────────────
# Strategy Profiles — per-wallet risk/reward configurations
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class StrategyProfile:
    """Per-wallet trading strategy profile.

    Bundles TP tiers, stops, sizing, and score thresholds so each wallet
    can run a completely different risk profile on the same scan pipeline.
    """
    name: str                       # "conservative" or "nuclear"
    # ── Score thresholds ──────────────────────────────────────────────────
    min_gem_score: float            # Minimum gem score to enter
    express_lane_score: float       # Score for instant market buy
    # ── Take-profit tiers ─────────────────────────────────────────────────
    tp1_mult: float                 # TP1 multiplier (e.g. 2.0 = 2x)
    tp1_sell_pct: float             # Fraction to sell at TP1 (0.0-1.0)
    tp2_mult: float                 # TP2 multiplier
    tp2_sell_pct: float             # Fraction of REMAINING to sell at TP2
    tp3_mult: float                 # TP3 multiplier (0 = disabled)
    tp3_sell_pct: float             # Fraction of REMAINING to sell at TP3
    # ── Stop losses ───────────────────────────────────────────────────────
    hard_stop_pct: float            # Hard stop loss %
    trailing_stop_pct: float        # Post-TP1 trailing stop %
    trailing_tighten: dict = field(default_factory=dict)  # {mult: trail%} dynamic tightening
    # ── Position sizing ───────────────────────────────────────────────────
    max_position_pct: float = 5.0       # Base max position % of wallet
    kelly_clamp_max: float = 0.25       # Kelly upper bound (fraction, e.g. 0.25 = 25%)
    max_position_usd: float = 0.0       # Absolute dollar cap (0 = no cap)
    max_concurrent: int = 10            # Max open positions
    # ── Fast fail ─────────────────────────────────────────────────────────
    fast_fail_down_pct: float = 15.0    # Down % to trigger fast-fail
    fast_fail_hours: float = 2.0        # Hours window for fast-fail check
    # ── Slippage ──────────────────────────────────────────────────────────
    max_slippage_pct: float = 5.0       # Max slippage tolerance %


# ── Pre-configured profiles ──────────────────────────────────────────────────

CONSERVATIVE_PROFILE = StrategyProfile(
    name="conservative",
    # FIX: was 65.0 — created a dead zone where cascade-boost-eligible tokens (60-64)
    # passed the scanner's dynamic MIN_GEM_SCORE gate but got rejected HERE, causing
    # "No wallet available". Set to 58.0 = CASCADE_BOOST_FLOOR_SCORE (the absolute
    # minimum the dynamic gate can reach). Primary wallet will accept anything the
    # scanner already cleared. Nuclear profile remains at 82.0 (express-lane only).
    min_gem_score=58.0,
    express_lane_score=82.0,
    # TP: 1.5x sell 40%, 2.5x sell 35%, 5x sell 25% — project spec pyramid (TP3 re-enabled)
    tp1_mult=1.5,
    tp1_sell_pct=0.40,
    tp2_mult=2.5,
    tp2_sell_pct=0.35,
    tp3_mult=5.0,       # FIX: re-enabled — Primary wallet must capture moonshots
    tp3_sell_pct=0.25,
    # Stops — project spec: 20% hard stop, 20% trailing after TP1
    hard_stop_pct=20.0,
    trailing_stop_pct=20.0,  # FIX: was 15%, project spec Tier 1 trailing = 20%
    trailing_tighten={2.5: 15.0, 5.0: 10.0},  # At TP2 → 15% trail, at TP3 → 10%
    # Sizing
    max_position_pct=20.0,    # SEED STAGE: concentrate bets — 20% per trade (~$50-100 per signal)
    kelly_clamp_max=0.30,
    max_position_usd=5_000.0,
    max_concurrent=5,
    # Fast fail
    fast_fail_down_pct=10.0,
    fast_fail_hours=2.0,
    max_slippage_pct=5.0,
)

NUCLEAR_PROFILE = StrategyProfile(
    name="nuclear",
    min_gem_score=72.0,   # UNLOCKED: lowered 82→72 — most quality signals score 72-80, nuclear now fires
    express_lane_score=80.0,  # Express lane at 80+ (instant market buy, no limit)
    # TP: 5x sell 20%, 12x sell 25%, 30x sell 20% (ride 35% with trail)
    # TUNED: tp1_sell_pct 15% → 20% — take more off at 5x to bank gains
    tp1_mult=5.0,
    tp1_sell_pct=0.20,   # TUNED: was 0.15 — bank 20% at 5x
    tp2_mult=12.0,
    tp2_sell_pct=0.25,
    tp3_mult=30.0,
    tp3_sell_pct=0.20,
    # Stops — tighten aggressively as it runs
    hard_stop_pct=8.0,   # TUNED: was 10% — tighter stop = less capital burned on losers
    trailing_stop_pct=28.0,  # TUNED: was 30% — slightly tighter to protect nuclear gains
    trailing_tighten={10: 15.0, 20: 7.0},  # TUNED: tighter at 10x/20x milestones
    # Sizing — the missile
    max_position_pct=60.0,
    kelly_clamp_max=0.70,
    max_position_usd=0.0,  # No hard cap
    max_concurrent=3,
    # Fast fail — tighter
    fast_fail_down_pct=12.0,  # TUNED: was 15% — cut losers faster
    fast_fail_hours=1.0,      # TUNED: was 1.5h — faster failure detection
    max_slippage_pct=8.0,  # Wider for nuclear entries on memes
)

# ── Swing Scalp Profile (capital recovery — tight TP/SL for blue chips) ──────
SWING_SCALP_PROFILE = StrategyProfile(
    name="swing",
    min_gem_score=0.0,            # Not used — pure TA entries
    express_lane_score=999.0,     # Not used
    # TP: 1.03x sell 50%, 1.06x sell 100% (tight scalp targets)
    tp1_mult=1.03,
    tp1_sell_pct=0.50,
    tp2_mult=1.06,
    tp2_sell_pct=1.0,
    tp3_mult=0.0,                 # Disabled — exit fully at TP2
    tp3_sell_pct=0.0,
    # Stop — tight for liquid tokens
    hard_stop_pct=2.5,
    trailing_stop_pct=1.5,        # Post-TP1 trailing
    trailing_tighten={1.04: 1.0}, # At +4%, tighten trail to 1%
    # Sizing — conservative for capital recovery
    max_position_pct=5.0,
    kelly_clamp_max=0.15,
    max_position_usd=100.0,       # Hard cap $100 per swing trade
    max_concurrent=5,
    # Fast fail
    fast_fail_down_pct=5.0,       # Tighter for blue chips
    fast_fail_hours=1.0,
    max_slippage_pct=1.0,         # Very tight — liquid tokens
)


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
    # Strategy profile — per-wallet risk/reward config
    strategy_profile: StrategyProfile = field(default_factory=lambda: CONSERVATIVE_PROFILE)

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
        solana_private_key_env="SOLANA_PRIVATE_KEY_PRIMARY",
        solana_address=os.getenv("SOLANA_ADDRESS_PRIMARY", ""),
        role="Safety net — conservative gem sniping",
        strategies=["gem_snipe", "momentum", "breakout"],
        chains=["ethereum", "base", "bsc", "avalanche", "polygon", "arbitrum", "solana"],
        max_position_size_pct=5.0,
        max_concurrent_positions=5,
        daily_loss_limit_eth=float(os.getenv("DAILY_LOSS_LIMIT_ETH", "0.5")),
        min_eth_balance_alert=float(os.getenv("MIN_ETH_BALANCE_ALERT", "0.05")),
        strategy_profile=CONSERVATIVE_PROFILE,
    ),

    "wallet_b": WalletConfig(
        alias="Wallet B",
        address="0x0835eb8447f3ac90351951bb5d22e77afd9b81c0",
        private_key_env="WALLET_PRIVATE_KEY_B",
        solana_private_key_env="SOLANA_PRIVATE_KEY_B",
        solana_address=os.getenv("SOLANA_ADDRESS_B", ""),
        role="Nuclear predator — aggressive momentum + explosive compounding",
        strategies=["gem_snipe", "momentum", "breakout", "nuclear"],
        chains=["ethereum", "base", "bsc", "avalanche", "polygon", "arbitrum", "solana"],  # ADDED ethereum
        max_position_size_pct=60.0,
        max_concurrent_positions=3,
        daily_loss_limit_eth=float(os.getenv("DAILY_LOSS_LIMIT_ETH_B", "2.0")),
        min_eth_balance_alert=float(os.getenv("MIN_ETH_BALANCE_ALERT", "0.05")),
        strategy_profile=NUCLEAR_PROFILE,
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
