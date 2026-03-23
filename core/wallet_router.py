"""
core/wallet_router.py — Multi-wallet routing, Kelly Criterion sizing, and phase scaling.

Determines which wallet to use for a given trade and how much capital to deploy,
based on:
  1. Chain support (which wallets are active on the target chain)
  2. Strategy assignment (gem_snipe, dca, momentum, etc.)
  3. Current wallet balance (fetched live from RPC)
  4. Kelly Criterion position sizing (bet size proportional to edge)
  5. Phase-based capital scaling (seed → growth → acceleration → whale)
  6. Daily loss limit enforcement
  7. Max concurrent position limits
  8. Chain-aware slippage (new tokens on Base/Solana get wider slippage)

Kelly Criterion (modified half-Kelly for safety):
  Kelly% = (win_rate × avg_win - loss_rate × avg_loss) / avg_win
  We use half-Kelly to reduce variance: actual_size = kelly% × 0.5 × balance

Phase-Based Capital Scaling (from docs/POSITION_SIZING.md):
  Phase 1 (Seed):         $0–$15K    → 5% max position, 5 concurrent
  Phase 2 (Growth):       $15K–$50K  → 3% max position, 8 concurrent
  Phase 3 (Acceleration): $50K–$250K → 2% max position, 10 concurrent
  Phase 4 (Whale):        $250K+     → 1% max position, 15 concurrent

Chain-Aware Slippage:
  Solana/Base new tokens: 150–300 bps (1.5–3%)
  Arbitrum/Polygon:       100 bps (1%)
  Ethereum:               50 bps (0.5%) — high liquidity, tight spreads
  BSC:                    200 bps (2%) — low liquidity, wide spreads

Security:
  - Private keys are NEVER stored here — loaded from env vars at execution time
  - Balances are fetched live from public RPCs — never hardcoded
"""

import logging
import math
from dataclasses import dataclass, field
from typing import Optional

from config import settings
from config.wallets import WALLETS, WalletConfig, get_wallets_for_chain
from config.chains import CHAINS, ChainConfig

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Phase-Based Capital Scaling
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CapitalPhase:
    """Defines position sizing parameters for a capital phase."""
    name: str
    min_usd: float
    max_usd: float
    max_position_pct: float   # % of total portfolio per trade
    max_concurrent: int       # Max open positions
    description: str


CAPITAL_PHASES = [
    CapitalPhase("seed",         0,       15_000,   5.0, 5,  "Seed — concentrate, move fast"),
    CapitalPhase("growth",       15_000,  50_000,   3.0, 8,  "Growth — scale with discipline"),
    CapitalPhase("acceleration", 50_000,  250_000,  2.0, 10, "Acceleration — diversify"),
    CapitalPhase("whale",        250_000, float("inf"), 1.0, 15, "Whale — wealth preservation"),
]


def get_capital_phase(portfolio_usd: float) -> CapitalPhase:
    """Return the appropriate capital phase for the current portfolio size."""
    for phase in CAPITAL_PHASES:
        if phase.min_usd <= portfolio_usd < phase.max_usd:
            return phase
    return CAPITAL_PHASES[-1]  # Whale mode for very large portfolios


# ─────────────────────────────────────────────────────────────────────────────
# Chain-Aware Slippage
# ─────────────────────────────────────────────────────────────────────────────

# Slippage in basis points (100 bps = 1%)
CHAIN_SLIPPAGE_BPS = {
    "ethereum": 50,    # Deep liquidity, tight spreads
    "base": 200,       # New tokens, moderate liquidity
    "arbitrum": 100,   # Good liquidity on major pairs
    "polygon": 150,    # Moderate liquidity
    "bsc": 200,        # Wide spreads on altcoins
    "solana": 150,     # Jupiter handles routing well
}

# Express lane tokens (very new, high volatility) get extra slippage buffer
EXPRESS_LANE_SLIPPAGE_BONUS_BPS = 100  # Add 1% for express lane trades


def get_chain_slippage_bps(chain: str, is_express: bool = False, token_age_hours: float = 24) -> int:
    """
    Get appropriate slippage in basis points for a chain and token.

    Args:
        chain: Chain name
        is_express: Whether this is an express lane (very new token) trade
        token_age_hours: Token age — newer tokens need wider slippage

    Returns:
        Slippage in basis points (e.g., 150 = 1.5%)
    """
    base_slippage = CHAIN_SLIPPAGE_BPS.get(chain, 200)

    # Very new tokens (< 6h) need extra buffer for price impact
    if token_age_hours < 6:
        base_slippage += 100
    elif token_age_hours < 24:
        base_slippage += 50

    # Express lane gets extra buffer
    if is_express:
        base_slippage += EXPRESS_LANE_SLIPPAGE_BONUS_BPS

    # Cap at 500 bps (5%) — anything above this is too risky
    return min(base_slippage, 500)


# ─────────────────────────────────────────────────────────────────────────────
# Kelly Criterion Position Sizing
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class KellyParams:
    """Historical performance parameters for Kelly calculation."""
    win_rate: float = 0.55       # 55% win rate (conservative estimate for gem sniping)
    avg_win_multiple: float = 3.0  # Average 3x on winners (TP1=2x, TP2=5x, TP3=10x)
    avg_loss_multiple: float = 0.25  # Average 25% loss on losers (stop-loss)
    kelly_fraction: float = 0.5   # Half-Kelly for safety (reduces variance)


def calculate_kelly_position_pct(
    gem_score: float,
    params: Optional[KellyParams] = None,
) -> float:
    """
    Calculate Kelly Criterion position size as a percentage of portfolio.

    The Kelly formula: f* = (p × b - q) / b
    Where:
      p = win probability
      q = loss probability (1 - p)
      b = win/loss ratio (avg_win / avg_loss)

    We use half-Kelly (f* × 0.5) to reduce variance while preserving edge.
    We also scale by gem_score to bet more on higher-conviction trades.

    Args:
        gem_score: Gem score 0-100 (higher = more conviction)
        params: Kelly parameters (uses defaults if None)

    Returns:
        Position size as a fraction (e.g., 0.03 = 3% of portfolio)
    """
    if params is None:
        params = KellyParams()

    # Adjust win rate based on gem score
    # Score 55 → 50% win rate, Score 82+ → 65% win rate
    score_bonus = max(0, (gem_score - 55) / 27) * 0.15  # 0 to +15% win rate
    adjusted_win_rate = min(params.win_rate + score_bonus, 0.75)
    loss_rate = 1 - adjusted_win_rate

    # Win/loss ratio
    b = params.avg_win_multiple / params.avg_loss_multiple

    # Full Kelly
    kelly_full = (adjusted_win_rate * b - loss_rate) / b

    # Half-Kelly for safety
    kelly_half = kelly_full * params.kelly_fraction

    # Clamp to reasonable range (0.5% to 10%)
    kelly_clamped = max(0.005, min(kelly_half, 0.10))

    logger.debug(
        f"Kelly sizing: score={gem_score:.0f} | win_rate={adjusted_win_rate:.1%} | "
        f"b={b:.2f} | full_kelly={kelly_full:.1%} | half_kelly={kelly_half:.1%} | "
        f"clamped={kelly_clamped:.1%}"
    )

    return kelly_clamped


# ─────────────────────────────────────────────────────────────────────────────
# Trade Allocation Result
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TradeAllocation:
    """Result of wallet routing — defines exactly how to execute a trade."""
    wallet: WalletConfig
    chain: ChainConfig
    position_size_usd: float       # Dollar value to deploy
    position_size_native: float    # Native token amount (ETH, SOL, etc.)
    native_balance: float          # Current wallet balance in native token
    native_price_usd: float        # Current native token price
    conviction_multiplier: float   # 0.5, 0.75, or 1.0
    slippage_bps: int              # Recommended slippage for this trade
    kelly_pct: float               # Kelly fraction used
    capital_phase: str             # "seed", "growth", "acceleration", "whale"
    reason: str                    # Human-readable routing decision


# ─────────────────────────────────────────────────────────────────────────────
# Balance Fetching
# ─────────────────────────────────────────────────────────────────────────────

def get_native_balance(wallet_address: str, chain: str) -> float:
    """
    Fetch current native token balance from public RPC.
    Returns 0.0 on failure (safe default — won't trade with zero balance).
    """
    chain_config = CHAINS.get(chain)
    if not chain_config:
        return 0.0

    if chain_config.is_solana:
        return _get_sol_balance(wallet_address)
    else:
        return _get_evm_balance(wallet_address, chain_config)


def _get_evm_balance(wallet_address: str, chain: ChainConfig) -> float:
    """Fetch ETH/BNB/MATIC balance via eth_getBalance JSON-RPC."""
    for rpc_url in [chain.rpc_url, chain.rpc_fallback]:
        if not rpc_url:
            continue
        try:
            import requests
            payload = {
                "jsonrpc": "2.0",
                "method": "eth_getBalance",
                "params": [wallet_address, "latest"],
                "id": 1,
            }
            resp = requests.post(rpc_url, json=payload, timeout=10)
            result = resp.json().get("result", "0x0")
            balance_wei = int(result, 16)
            return balance_wei / (10 ** chain.native_token_decimals)
        except Exception as e:
            logger.debug(f"EVM balance fetch failed ({rpc_url}): {e}")
    return 0.0


def _get_sol_balance(wallet_address: str) -> float:
    """Fetch SOL balance via Solana JSON-RPC."""
    try:
        import requests
        rpc_url = settings.SOLANA_RPC_URL
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getBalance",
            "params": [wallet_address],
        }
        resp = requests.post(rpc_url, json=payload, timeout=10)
        result = resp.json().get("result", {})
        lamports = result.get("value", 0)
        return lamports / 1_000_000_000
    except Exception as e:
        logger.debug(f"SOL balance fetch failed for {wallet_address}: {e}")
        return 0.0


def get_native_price_usd(native_token: str) -> float:
    """
    Fetch current native token price in USD from CoinGecko.
    Falls back to hardcoded estimates on failure.
    """
    _FALLBACK_PRICES = {
        "ETH": 3200.0,
        "MATIC": 0.85,
        "BNB": 580.0,
        "SOL": 175.0,
    }
    try:
        import requests
        coin_ids = {
            "ETH": "ethereum",
            "MATIC": "matic-network",
            "BNB": "binancecoin",
            "SOL": "solana",
        }
        coin_id = coin_ids.get(native_token.upper())
        if not coin_id:
            return _FALLBACK_PRICES.get(native_token.upper(), 1.0)
        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {"ids": coin_id, "vs_currencies": "usd"}
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        return float(data.get(coin_id, {}).get("usd", _FALLBACK_PRICES.get(native_token, 1.0)))
    except Exception as e:
        logger.debug(f"Price fetch failed for {native_token}: {e}")
        return _FALLBACK_PRICES.get(native_token.upper(), 1.0)


def get_open_position_count(wallet_alias: str) -> int:
    """Count open positions for a wallet from the positions file."""
    try:
        from core.position_monitor import load_positions
        positions = load_positions()
        return sum(
            1 for p in positions
            if p.get("wallet") == wallet_alias and p.get("status") == "open"
        )
    except Exception:
        return 0


def get_daily_loss_usd(wallet_alias: str) -> float:
    """Calculate today's realized losses for a wallet from the trades log."""
    try:
        import json
        from pathlib import Path
        from datetime import date

        trades_file = Path(settings.TRADES_FILE)
        if not trades_file.exists():
            return 0.0

        with open(trades_file) as f:
            trades = json.load(f)

        today = date.today()
        daily_loss = 0.0
        for t in trades:
            if t.get("wallet") != wallet_alias:
                continue
            if t.get("action") != "SELL":
                continue
            ts = t.get("timestamp", "")
            try:
                from datetime import datetime
                trade_date = datetime.fromisoformat(str(ts).replace("Z", "+00:00")).date()
                if trade_date != today:
                    continue
            except Exception:
                continue
            pnl = float(t.get("pnl_usd", 0))
            if pnl < 0:
                daily_loss += abs(pnl)

        return daily_loss
    except Exception:
        return 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Main Routing Function
# ─────────────────────────────────────────────────────────────────────────────

def route_trade(
    chain: str,
    gem_score: float,
    strategy: str = "gem_snipe",
    token_age_hours: float = 24.0,
    is_express: bool = False,
    use_kelly: bool = True,
) -> Optional[TradeAllocation]:
    """
    Determine the best wallet and position size for a trade.

    Uses Kelly Criterion for position sizing when use_kelly=True (default).
    Falls back to conviction-multiplier sizing if Kelly produces too small a size.

    Args:
        chain: Target chain name (e.g. "base", "solana")
        gem_score: Gem score 0-100 (drives position size and Kelly win rate)
        strategy: Strategy name for wallet matching
        token_age_hours: Token age in hours (affects slippage recommendation)
        is_express: Whether this is an express lane trade
        use_kelly: Whether to use Kelly Criterion sizing (default True)

    Returns:
        TradeAllocation if a suitable wallet is found, None otherwise.
    """
    eligible_wallets = get_wallets_for_chain(chain)
    if not eligible_wallets:
        logger.warning(f"No wallets configured for chain: {chain}")
        return None

    strategy_wallets = [w for w in eligible_wallets if strategy in w.strategies]
    if not strategy_wallets:
        strategy_wallets = eligible_wallets
        logger.debug(f"No wallet with strategy '{strategy}' for {chain} — using any eligible")

    chain_config = CHAINS.get(chain)
    if not chain_config:
        logger.error(f"Unknown chain: {chain}")
        return None

    # Priority: primary → wallet_b → wallet_c
    wallet_priority = ["primary", "wallet_b", "wallet_c"]
    strategy_wallets.sort(
        key=lambda w: wallet_priority.index(w.alias.lower().replace(" ", "_"))
        if w.alias.lower().replace(" ", "_") in wallet_priority else 99
    )

    # Calculate slippage recommendation for this trade
    slippage_bps = get_chain_slippage_bps(chain, is_express=is_express, token_age_hours=token_age_hours)

    for wallet in strategy_wallets:
        # Check max concurrent positions
        open_count = get_open_position_count(wallet.alias.lower().replace(" ", "_"))
        if open_count >= wallet.max_concurrent_positions:
            logger.debug(
                f"Wallet {wallet.alias} at max positions "
                f"({open_count}/{wallet.max_concurrent_positions})"
            )
            continue

        # Check daily loss limit (in USD)
        daily_loss_usd = get_daily_loss_usd(wallet.alias.lower().replace(" ", "_"))
        native_price = get_native_price_usd(chain_config.native_token)
        daily_loss_limit_usd = wallet.daily_loss_limit_eth * native_price
        if daily_loss_usd >= daily_loss_limit_usd:
            logger.warning(
                f"Wallet {wallet.alias} daily loss limit reached "
                f"(${daily_loss_usd:.2f} lost today, limit ${daily_loss_limit_usd:.2f})"
            )
            continue

        # Fetch live balance
        balance_address = (
            wallet.solana_address if chain_config.is_solana and wallet.solana_address
            else wallet.address
        )
        native_balance = get_native_balance(balance_address, chain)
        if native_balance <= wallet.min_eth_balance_alert:
            logger.warning(
                f"Wallet {wallet.alias} balance too low: "
                f"{native_balance:.4f} {chain_config.native_token}"
            )
            continue

        wallet_balance_usd = native_balance * native_price

        # ── Phase-based capital scaling ───────────────────────────────────────
        phase = get_capital_phase(wallet_balance_usd)
        phase_max_pct = phase.max_position_pct / 100

        # Override max concurrent positions from phase if phase is more restrictive
        effective_max_concurrent = min(wallet.max_concurrent_positions, phase.max_concurrent)
        if open_count >= effective_max_concurrent:
            logger.debug(
                f"Wallet {wallet.alias} at phase max positions "
                f"({open_count}/{effective_max_concurrent}) — phase: {phase.name}"
            )
            continue

        # ── Kelly Criterion sizing ────────────────────────────────────────────
        if use_kelly:
            kelly_pct = calculate_kelly_position_pct(gem_score)
            # Kelly is bounded by phase max position size
            effective_pct = min(kelly_pct, phase_max_pct)
            position_size_usd = wallet_balance_usd * effective_pct
        else:
            # Fallback: conviction-multiplier sizing
            if gem_score >= settings.CONVICTION_HIGH_THRESHOLD:
                multiplier = settings.CONVICTION_HIGH_MULTIPLIER
            elif gem_score >= settings.CONVICTION_MID_THRESHOLD:
                multiplier = settings.CONVICTION_MID_MULTIPLIER
            else:
                multiplier = settings.CONVICTION_LOW_MULTIPLIER

            max_position_usd = wallet_balance_usd * phase_max_pct
            position_size_usd = max_position_usd * multiplier
            kelly_pct = phase_max_pct * multiplier

        # Conviction multiplier for display/logging
        if gem_score >= settings.CONVICTION_HIGH_THRESHOLD:
            conviction_multiplier = 1.0
        elif gem_score >= settings.CONVICTION_MID_THRESHOLD:
            conviction_multiplier = 0.75
        else:
            conviction_multiplier = 0.50

        # ── Chain-specific minimum trade sizes ────────────────────────────────
        # Ethereum: min $100 (gas is expensive), others: min $25
        min_trade_usd = 100.0 if chain == "ethereum" else 25.0
        if position_size_usd < min_trade_usd:
            logger.debug(
                f"Position size too small for {wallet.alias} on {chain}: "
                f"${position_size_usd:.2f} (min ${min_trade_usd:.2f})"
            )
            continue

        position_size_native = position_size_usd / native_price

        reason = (
            f"{wallet.alias} | phase={phase.name} | score={gem_score:.0f} | "
            f"kelly={kelly_pct:.1%} | conviction={conviction_multiplier:.2f} | "
            f"balance={native_balance:.4f} {chain_config.native_token} | "
            f"size=${position_size_usd:.2f} | slippage={slippage_bps}bps"
        )

        logger.info(f"Trade routed: {reason}")

        return TradeAllocation(
            wallet=wallet,
            chain=chain_config,
            position_size_usd=position_size_usd,
            position_size_native=position_size_native,
            native_balance=native_balance,
            native_price_usd=native_price,
            conviction_multiplier=conviction_multiplier,
            slippage_bps=slippage_bps,
            kelly_pct=kelly_pct,
            capital_phase=phase.name,
            reason=reason,
        )

    logger.warning(f"No eligible wallet found for {chain} trade (score={gem_score:.0f})")
    return None
