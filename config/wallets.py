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
    # TUNED: 68→62 — Base L2 gems typically score 60-76 due to less liquidity
    # depth and fewer data signals vs Ethereum. 68 was filtering out ALL Base
    # gems. Lowered to 62 for paper-mode validation (2026-06-09).
    min_gem_score=62.0,
    express_lane_score=74.0,
    # TP: 1.5x sell 40%, 1.8x sell 35%, 5x sell 25% (Optimized via Shadow Account Backtest)
    tp1_mult=1.5,
    tp1_sell_pct=0.40,
    tp2_mult=1.8,
    tp2_sell_pct=0.35,
    tp3_mult=5.0,
    tp3_sell_pct=0.25,
    # Stops — TUNED 2026-06-10: tightened after paper trades showed $103 single-trade losses
    hard_stop_pct=8.0,             # 10→8% — cut losers faster ($4 max loss on $50 trade)
    trailing_stop_pct=6.0,
    trailing_tighten={1.8: 4.0, 2.5: 3.0},
    # Sizing — TUNED 2026-06-10: avg $160/trade on $1000 = 16% = catastrophic
    # 5% × 5 concurrent = 25% deployed, 75% reserve. Survivable.
    max_position_pct=5.0,          # 8→5% — max $50 on $1000 account
    kelly_clamp_max=0.15,          # 0.25→0.15 — Kelly can't exceed 15%
    max_position_usd=5_000.0,
    max_concurrent=5,              # 8→5 — fewer positions, higher quality
    # Fast fail — TUNED: 30-minute window, 7% threshold
    fast_fail_down_pct=7.0,        # 10→7% — faster kill switch
    fast_fail_hours=0.5,           # 1.5→0.5h — 30-minute fast fail window
    max_slippage_pct=4.0,
)

NUCLEAR_PROFILE = StrategyProfile(
    name="nuclear",
    # TUNED: 72→65 — Arbitrum gems scoring 60-70 were all blocked.
    min_gem_score=65.0,
    express_lane_score=76.0,
    # TP: 2x sell 25%, 5x sell 30%, 15x sell 20%
    tp1_mult=2.0,
    tp1_sell_pct=0.25,
    tp2_mult=5.0,
    tp2_sell_pct=0.30,
    tp3_mult=15.0,
    tp3_sell_pct=0.20,
    # Stops — TUNED 2026-06-10: tightened for capital preservation
    hard_stop_pct=10.0,            # 12→10%
    trailing_stop_pct=20.0,
    trailing_tighten={5.0: 12.0, 10.0: 7.0},
    # Sizing — TUNED 2026-06-10: 20→10% per trade, 4→3 concurrent
    max_position_pct=10.0,         # 20→10%
    kelly_clamp_max=0.25,          # 0.50→0.25
    max_position_usd=0.0,
    max_concurrent=3,              # 4→3
    # Fast fail
    fast_fail_down_pct=10.0,       # 12→10%
    fast_fail_hours=1.0,           # 1.5→1.0h
    max_slippage_pct=8.0,
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
    fast_fail_down_pct=5.0,       # Tighter for blue chips
    fast_fail_hours=1.0,
    max_slippage_pct=1.0,         # Very tight — liquid tokens
)

# ─────────────────────────────────────────────────────────────────────────────
# MTF (Multi-Timeframe) Strategy Profiles
# Each profile is tuned for a specific hold horizon and exit cadence.
# These are used by the MTF strategy engine (strategies/mtf_strategy.py) and
# registered on positions so the monitor applies the correct TP/SL rules.
# ─────────────────────────────────────────────────────────────────────────────

# ── 1H Scalp Profile: fast in/out, tight stops, small TP targets ─────────────
MTF_1H_SCALP_PROFILE = StrategyProfile(
    name="mtf_1h_scalp",
    min_gem_score=62.0,
    express_lane_score=80.0,
    # TP: +25% sell 50%, +50% sell 100% — fast scalp exits
    tp1_mult=1.25,
    tp1_sell_pct=0.50,
    tp2_mult=1.50,
    tp2_sell_pct=1.0,
    tp3_mult=0.0,          # No TP3 — scalps exit fully at TP2
    tp3_sell_pct=0.0,
    # Stops — tight: scalps must cut fast
    hard_stop_pct=8.0,
    trailing_stop_pct=8.0,
    trailing_tighten={1.3: 5.0, 1.45: 3.0},
    # Sizing — smaller per-trade, higher frequency
    max_position_pct=8.0,
    kelly_clamp_max=0.20,
    max_position_usd=500.0,
    max_concurrent=8,
    fast_fail_down_pct=7.0,
    fast_fail_hours=1.0,
    max_slippage_pct=3.0,
)

# ── 4H Swing Profile: technicals-driven, 1-2 day holds ───────────────────────
MTF_4H_SWING_PROFILE = StrategyProfile(
    name="mtf_4h_swing",
    min_gem_score=65.0,
    express_lane_score=82.0,
    # TP: +50% sell 40%, +100% sell 35%, +200% sell 25%
    tp1_mult=1.50,
    tp1_sell_pct=0.40,
    tp2_mult=2.00,
    tp2_sell_pct=0.35,
    tp3_mult=3.00,
    tp3_sell_pct=0.25,
    # Stops — moderate: give room to breathe on 4H candles
    hard_stop_pct=15.0,
    trailing_stop_pct=15.0,
    trailing_tighten={2.0: 10.0, 3.0: 7.0},
    # Sizing — standard
    max_position_pct=10.0,
    kelly_clamp_max=0.30,
    max_position_usd=2_000.0,
    max_concurrent=6,
    fast_fail_down_pct=12.0,
    fast_fail_hours=3.0,
    max_slippage_pct=4.0,
)

# ── 12-24H Momentum Profile: multi-day trend plays ───────────────────────────
MTF_12H_MOMENTUM_PROFILE = StrategyProfile(
    name="mtf_12h_momentum",
    min_gem_score=67.0,
    express_lane_score=84.0,
    # TP: +75% sell 35%, +150% sell 35%, +300% sell 30%
    tp1_mult=1.75,
    tp1_sell_pct=0.35,
    tp2_mult=2.50,
    tp2_sell_pct=0.35,
    tp3_mult=4.00,
    tp3_sell_pct=0.30,
    # Stops — wider: multi-day plays need room
    hard_stop_pct=18.0,
    trailing_stop_pct=18.0,
    trailing_tighten={2.5: 12.0, 4.0: 8.0},
    # Sizing — moderate-large
    max_position_pct=12.0,
    kelly_clamp_max=0.35,
    max_position_usd=3_000.0,
    max_concurrent=5,
    fast_fail_down_pct=14.0,
    fast_fail_hours=6.0,
    max_slippage_pct=5.0,
)

# ── 5-Day Position Profile: conviction plays, ride the trend ─────────────────
MTF_5D_POSITION_PROFILE = StrategyProfile(
    name="mtf_5d_position",
    min_gem_score=70.0,
    express_lane_score=85.0,
    # TP: +100% sell 30%, +250% sell 30%, +500% sell 25% — ride the wave
    tp1_mult=2.00,
    tp1_sell_pct=0.30,
    tp2_mult=3.50,
    tp2_sell_pct=0.30,
    tp3_mult=6.00,
    tp3_sell_pct=0.25,
    # Stops — widest: 5-day plays need room for multi-day drawdowns
    hard_stop_pct=22.0,
    trailing_stop_pct=22.0,
    trailing_tighten={3.5: 15.0, 6.0: 10.0},
    # Sizing — larger conviction bets
    max_position_pct=15.0,
    kelly_clamp_max=0.40,
    max_position_usd=5_000.0,
    max_concurrent=4,
    fast_fail_down_pct=18.0,
    fast_fail_hours=12.0,
    max_slippage_pct=5.0,
)

# ── Solana Alpha Profile (high conviction 90% cap deploy) ────────────────────
ALPHA_SOL_PROFILE = StrategyProfile(
    name="alpha_sol",
    # TUNED: min_gem_score kept at 85 — Solana quality bar must stay high
    # The problem was not the score floor but the position sizing.
    min_gem_score=85.0,
    express_lane_score=92.0,
    # TP: OPTIMIZED via Shadow Account Backtest for highly volatile Solana memes
    tp1_mult=1.3,
    tp1_sell_pct=0.35,
    tp2_mult=1.8,
    tp2_sell_pct=0.30,
    tp3_mult=5.0,
    tp3_sell_pct=0.35,
    # Stops — OPTIMIZED via Shadow Account Backtest
    hard_stop_pct=10.0,
    trailing_stop_pct=6.0,
    trailing_tighten={1.8: 4.0, 2.5: 3.0},
    # Sizing — TUNED: 20% per trade (was 45%), max 3 concurrent (was 2)
    # 45% per trade on Solana memes = -$192 in losses. 20% × 3 = 60% deployed.
    # This is still aggressive but survivable when trades go wrong.
    max_position_pct=20.0,
    kelly_clamp_max=0.40,
    max_position_usd=0.0,
    max_concurrent=3,
    fast_fail_down_pct=12.0,
    fast_fail_hours=1.0,  # Solana moves fast — fail fast too
    max_slippage_pct=5.0,
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
        solana_private_key_env="SOLANA_PRIVATE_KEY",
        solana_address=os.getenv("SOLANA_ADDRESS_PRIMARY", ""),
        role="Safety net — conservative gem sniping",
        strategies=["gem_snipe", "momentum", "breakout"],
        # Ethereum + BSC removed — not gem hunting there right now (CU budget + gas cost)
        chains=["base", "arbitrum", "solana"],
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
        solana_private_key_env="SOLANA_PRIVATE_KEY",
        solana_address=os.getenv("SOLANA_ADDRESS_B", ""),
        role="Nuclear predator — aggressive momentum + explosive compounding",
        strategies=["gem_snipe", "momentum", "breakout", "nuclear"],
        # Ethereum + BSC removed — not gem hunting there right now (CU budget + gas cost)
        chains=["base", "arbitrum", "solana"],
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

    "wallet_sol_alpha": WalletConfig(
        alias="Wallet Sol Alpha",
        address="FzZwd2Zqw7bMpzUoxNA7QwqziAVLddtDftecvs5p8gt2",  # Store mapped Solana address into address field as placeholder
        private_key_env="WALLET_PRIVATE_KEY_SOL_ALPHA",  # Not strictly used for Sol
        solana_private_key_env="SOLANA_PRIVATE_KEY",
        solana_address="FzZwd2Zqw7bMpzUoxNA7QwqziAVLddtDftecvs5p8gt2",
        role="High-conviction sniper for top-tier Solana gems — targets 90% capital deployment",
        strategies=["gem_snipe", "momentum", "breakout"],
        chains=["solana"],
        max_position_size_pct=45.0,
        max_concurrent_positions=2,
        daily_loss_limit_eth=2.0,           
        min_eth_balance_alert=0.05,
        strategy_profile=ALPHA_SOL_PROFILE,
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
