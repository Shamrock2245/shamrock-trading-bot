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
  9. Gas-vs-position-size guard (reject trades where gas > 20% of position)
  10. Daily trade count cap (prevent gas burn)
  11. Auto-scaling absolute position cap (grows with wallet)

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
import os
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from config import settings
from config.wallets import WALLETS, WalletConfig, get_wallets_for_chain
from config.chains import CHAINS, ChainConfig

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Daily Trade Counter
# ─────────────────────────────────────────────────────────────────────────────
_daily_trade_count: dict[str, int] = {}  # {date_str: count}


def get_daily_trade_count() -> int:
    """Get the number of trades executed today."""
    today = date.today().isoformat()
    return _daily_trade_count.get(today, 0)


def increment_daily_trade_count() -> int:
    """Increment and return today's trade count. Call after a successful trade."""
    today = date.today().isoformat()
    # Clean up old dates
    for k in list(_daily_trade_count.keys()):
        if k != today:
            del _daily_trade_count[k]
    _daily_trade_count[today] = _daily_trade_count.get(today, 0) + 1
    return _daily_trade_count[today]


# ─────────────────────────────────────────────────────────────────────────────
# Estimated Gas Costs (USD) per chain — for gas-vs-size guard
# ─────────────────────────────────────────────────────────────────────────────
ESTIMATED_GAS_COST_USD = {
    "ethereum": 15.0,   # ~$15 per swap on ETH mainnet
    "base": 0.10,       # Base L2 is very cheap
    "arbitrum": 0.25,   # Arbitrum L2
    "polygon": 0.05,    # Polygon is very cheap
    "bsc": 0.50,        # BSC is cheap
    "avalanche": 0.50,  # AVAX moderate
    "solana": 0.01,     # Solana is near-free
}


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
    CapitalPhase("seed",         0,       15_000,   25.0, 5,  "Seed — concentrate, move fast"),
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
    "avalanche": 150,  # Similar to Polygon liquidity
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
    clamp_max: float = 0.10,
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
        clamp_max: Upper bound for Kelly fraction (profile-specific: 0.10 conservative, 0.70 nuclear)

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

    # Clamp to profile-specific range (0.5% to clamp_max)
    kelly_clamped = max(0.005, min(kelly_half, clamp_max))

    logger.debug(
        f"Kelly sizing: score={gem_score:.0f} | win_rate={adjusted_win_rate:.1%} | "
        f"b={b:.2f} | full_kelly={kelly_full:.1%} | half_kelly={kelly_half:.1%} | "
        f"clamped={kelly_clamped:.1%} (max={clamp_max:.0%})"
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
    """Fetch SOL balance via Solana JSON-RPC with fallback endpoints."""
    rpc_urls = [
        settings.SOLANA_RPC_URL,
        getattr(settings, 'SOLANA_RPC_FALLBACK', 'https://solana-mainnet.g.alchemy.com/v2/demo'),
    ]
    for rpc_url in rpc_urls:
        if not rpc_url:
            continue
        try:
            import requests
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getBalance",
                "params": [wallet_address],
            }
            resp = requests.post(rpc_url, json=payload, timeout=10)
            data = resp.json()
            if "result" in data and "value" in data["result"]:
                lamports = data["result"]["value"]
                return lamports / 1_000_000_000
            else:
                logger.warning(f"Solana RPC returned unexpected format: {data}")
        except Exception as e:
            logger.debug(f"SOL balance fetch failed for {wallet_address} ({rpc_url}): {e}")
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
        "AVAX": 35.0,
    }
    try:
        import requests
        coin_ids = {
            "ETH": "ethereum",
            "MATIC": "matic-network",
            "BNB": "binancecoin",
            "SOL": "solana",
            "AVAX": "avalanche-2",
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
    specific_wallet: str = "",
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
        specific_wallet: If set, only consider this wallet alias (e.g. "primary", "wallet_b")

    Returns:
        TradeAllocation if a suitable wallet is found, None otherwise.
    """
    eligible_wallets = get_wallets_for_chain(chain)
    if not eligible_wallets:
        logger.warning(f"No wallets configured for chain: {chain}")
        return None

    # If specific_wallet is set, filter to only that wallet
    if specific_wallet:
        eligible_wallets = [
            w for w in eligible_wallets
            if w.alias.lower().replace(" ", "_") == specific_wallet.lower().replace(" ", "_")
        ]
        if not eligible_wallets:
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

    logger.info(f"Routing {chain} trade: {len(strategy_wallets)} wallets eligible, strategy={strategy}")

    # ── Daily trade cap (global across all wallets) ────────────────────────
    if settings.MAX_TRADES_PER_DAY > 0:
        daily_count = get_daily_trade_count()
        if daily_count >= settings.MAX_TRADES_PER_DAY:
            logger.warning(
                f"Daily trade cap reached: {daily_count}/{settings.MAX_TRADES_PER_DAY} — "
                f"no more trades today"
            )
            return None

    for wallet in strategy_wallets:
        logger.debug(f"  Evaluating {wallet.alias} for {chain}...")
        # Check max concurrent positions (relaxed in moonshot mode)
        open_count = get_open_position_count(wallet.alias.lower().replace(" ", "_"))
        moonshot_mode = os.getenv("MOONSHOT_MODE", "false").lower() in ("true", "1", "yes")
        max_pos = max(wallet.max_concurrent_positions, 20) if moonshot_mode else wallet.max_concurrent_positions
        if open_count >= max_pos:
            logger.debug(
                f"Wallet {wallet.alias} at max positions "
                f"({open_count}/{max_pos})"
            )
            continue

        # Check daily loss limit (in USD)
        daily_loss_usd = get_daily_loss_usd(wallet.alias.lower().replace(" ", "_"))
        native_price = get_native_price_usd(chain_config.native_token)
        logger.debug(f"  {wallet.alias} native_price={native_price:.2f} USD for {chain_config.native_token}")
        daily_loss_limit_usd = wallet.daily_loss_limit_eth * native_price
        if daily_loss_usd >= daily_loss_limit_usd:
            logger.warning(
                f"Wallet {wallet.alias} daily loss limit reached "
                f"(${daily_loss_usd:.2f} lost today, limit ${daily_loss_limit_usd:.2f})"
            )
            continue

        # Fetch live balance
        if chain_config.is_solana:
            if not wallet.solana_address:
                logger.warning(f"Wallet {wallet.alias} missing solana_address, skipping for Solana trade")
                continue
            balance_address = wallet.solana_address
            min_balance_required = 0.005  # 0.005 SOL minimum for rent + priority fees
        else:
            balance_address = wallet.address
            min_balance_required = wallet.min_eth_balance_alert

        native_balance = get_native_balance(balance_address, chain)
        usdc_balance = get_usdc_balance(balance_address, chain)
        
        # USDC-as-capital: if wallet has USDC > $25 on ANY EVM chain, use it
        # Native balance only needs to cover gas (0.005 ETH/MATIC/BNB)
        min_gas_balance = 0.005  # Just enough for gas fees
        if not chain_config.is_solana and usdc_balance > 25.0:
            wallet_balance_usd = usdc_balance
            logger.info(f"  {wallet.alias} using USDC capital=${usdc_balance:.2f} on {chain} (native={native_balance:.4f} for gas)")
            if native_balance < min_gas_balance:
                logger.warning(
                    f"Wallet {wallet.alias} needs gas on {chain}: "
                    f"{native_balance:.4f} < {min_gas_balance} {chain_config.native_token} — skipping"
                )
                continue
        else:
            logger.debug(f"  {wallet.alias} balance={native_balance:.6f} on {chain} (addr={balance_address[:12]}...)")
            if native_balance <= min_balance_required:
                logger.warning(
                    f"Wallet {wallet.alias} balance too low on {chain}: "
                    f"{native_balance:.4f} <= {min_balance_required} {chain_config.native_token}"
                )
                continue
            wallet_balance_usd = native_balance * native_price

        # ── Phase-based capital scaling ───────────────────────────────────────
        phase = get_capital_phase(wallet_balance_usd)
        phase_max_pct = phase.max_position_pct / 100

        # Override max concurrent from phase OR wallet profile (most restrictive wins)
        profile = wallet.strategy_profile
        profile_max_concurrent = profile.max_concurrent
        effective_max_concurrent = min(wallet.max_concurrent_positions, phase.max_concurrent, profile_max_concurrent)
        if open_count >= effective_max_concurrent:
            logger.debug(
                f"Wallet {wallet.alias} at max positions "
                f"({open_count}/{effective_max_concurrent}) — phase: {phase.name}, profile: {profile.name}"
            )
            continue

        # ── Capital Recovery Mode ─────────────────────────────────────────────
        # If the wallet is below the recovery threshold, apply conservative
        # constraints: lower max position %, higher min gem score, fewer
        # concurrent positions. This protects depleted wallets from making
        # desperate low-quality trades while trying to rebuild capital.
        in_recovery_mode = (
            settings.CAPITAL_RECOVERY_ENABLED
            and wallet_balance_usd < settings.CAPITAL_RECOVERY_THRESHOLD_USD
        )
        if in_recovery_mode:
            logger.warning(
                f"⚠️  CAPITAL RECOVERY MODE: {wallet.alias} balance=${wallet_balance_usd:.0f} "
                f"< threshold=${settings.CAPITAL_RECOVERY_THRESHOLD_USD:.0f} — "
                f"applying conservative sizing (max {settings.CAPITAL_RECOVERY_MAX_POSITION_PCT}%, "
                f"min score {settings.CAPITAL_RECOVERY_MIN_SCORE})"
            )
            # Enforce higher gem score gate in recovery mode
            if gem_score < settings.CAPITAL_RECOVERY_MIN_SCORE:
                logger.info(
                    f"  Recovery mode: {wallet.alias} rejecting gem_score={gem_score:.1f} "
                    f"< recovery threshold {settings.CAPITAL_RECOVERY_MIN_SCORE}"
                )
                continue
            # Enforce max concurrent positions in recovery mode
            if open_count >= settings.CAPITAL_RECOVERY_MAX_POSITIONS:
                logger.info(
                    f"  Recovery mode: {wallet.alias} at max recovery positions "
                    f"({open_count}/{settings.CAPITAL_RECOVERY_MAX_POSITIONS})"
                )
                continue

        # ── Profile-aware sizing ───────────────────────────────────────────────
        # Use the wallet's strategy profile for Kelly clamp and max position %
        profile_max_pct = profile.max_position_pct / 100  # e.g. 0.60 for nuclear
        # In recovery mode, cap at CAPITAL_RECOVERY_MAX_POSITION_PCT
        if in_recovery_mode:
            recovery_cap_pct = settings.CAPITAL_RECOVERY_MAX_POSITION_PCT / 100
            effective_max_pct = min(phase_max_pct, profile_max_pct, recovery_cap_pct)
        else:
            effective_max_pct = min(phase_max_pct, profile_max_pct)

        # ── Regime filter — global multiplier ─────────────────────────────────
        try:
            from core.regime_filter import get_regime, get_sizing_multiplier
            regime_state = get_regime()
            regime_mult = get_sizing_multiplier(regime_state.regime, profile.name)
        except Exception:
            regime_mult = 1.0
            regime_state = None

        # ── Kelly Criterion sizing ────────────────────────────────────────────
        if use_kelly:
            kelly_pct = calculate_kelly_position_pct(
                gem_score,
                clamp_max=profile.kelly_clamp_max,  # 0.10 conservative, 0.70 nuclear
            )
            # Kelly bounded by effective max, then scaled by regime
            effective_pct = min(kelly_pct, effective_max_pct) * regime_mult
            position_size_usd = wallet_balance_usd * effective_pct
        else:
            # Fallback: conviction-multiplier sizing
            if gem_score >= settings.CONVICTION_HIGH_THRESHOLD:
                multiplier = settings.CONVICTION_HIGH_MULTIPLIER
            elif gem_score >= settings.CONVICTION_MID_THRESHOLD:
                multiplier = settings.CONVICTION_MID_MULTIPLIER
            else:
                multiplier = settings.CONVICTION_LOW_MULTIPLIER

            max_position_usd = wallet_balance_usd * effective_max_pct
            position_size_usd = max_position_usd * multiplier * regime_mult
            kelly_pct = effective_max_pct * multiplier

        # ── Apply absolute USD cap from profile ───────────────────────────────
        # Use the GREATER of fixed cap or auto-scaling % cap (so it grows with the wallet)
        fixed_cap = profile.max_position_usd if profile.max_position_usd > 0 else settings.OFFENSIVE_MAX_POSITION_USD
        wallet_pct_cap = wallet_balance_usd * (settings.OFFENSIVE_MAX_POSITION_WALLET_PCT / 100)
        dynamic_cap = max(fixed_cap, wallet_pct_cap)
        if position_size_usd > dynamic_cap:
            position_size_usd = dynamic_cap

        # Conviction multiplier for display/logging
        if gem_score >= settings.CONVICTION_HIGH_THRESHOLD:
            conviction_multiplier = 1.0
        elif gem_score >= settings.CONVICTION_MID_THRESHOLD:
            conviction_multiplier = 0.75
        else:
            conviction_multiplier = 0.50

        # ── Chain-specific minimum trade sizes ────────────────────────────────
        if settings.MODE == "paper":
            min_trade_usd = 1.0
        elif chain == "ethereum":
            min_trade_usd = 100.0
        elif chain == "solana":
            min_trade_usd = 1.0
        else:
            min_trade_usd = 25.0

        regime_label = regime_state.regime.value if regime_state else "unknown"
        logger.debug(
            f"  {wallet.alias} [{profile.name}] phase={phase.name} max_pct={effective_max_pct:.1%} "
            f"regime={regime_label}(x{regime_mult:.1f}) balance=${wallet_balance_usd:.2f} "
            f"pos_size=${position_size_usd:.2f} min_trade=${min_trade_usd}"
        )
        if position_size_usd < min_trade_usd:
            logger.debug(
                f"Position size too small for {wallet.alias} on {chain}: "
                f"${position_size_usd:.2f} (min ${min_trade_usd:.2f})"
            )
            continue

        # ── Gas-vs-position-size guard ─────────────────────────────────────
        estimated_gas = ESTIMATED_GAS_COST_USD.get(chain, 1.0)
        # Round-trip gas: buy + sell
        round_trip_gas = estimated_gas * 2
        min_position_for_gas = round_trip_gas * settings.MIN_POSITION_GAS_RATIO
        if position_size_usd < min_position_for_gas:
            logger.warning(
                f"Gas guard: ${position_size_usd:.2f} position < "
                f"${min_position_for_gas:.2f} min ({settings.MIN_POSITION_GAS_RATIO}x "
                f"round-trip gas ${round_trip_gas:.2f}) on {chain} — skipping"
            )
            continue

        position_size_native = position_size_usd / native_price

        # Nuclear entry labeling
        entry_label = "🚀 NUCLEAR ENTRY" if profile.name == "nuclear" else "📊 CONSERVATIVE ENTRY"
        pct_of_wallet = (position_size_usd / wallet_balance_usd * 100) if wallet_balance_usd > 0 else 0

        reason = (
            f"{entry_label} — {wallet.alias} | phase={phase.name} | "
            f"score={gem_score:.0f} | kelly={kelly_pct:.1%} | "
            f"regime={regime_label} | conviction={conviction_multiplier:.2f} | "
            f"balance={native_balance:.4f} {chain_config.native_token} | "
            f"size=${position_size_usd:.2f} ({pct_of_wallet:.0f}% of wallet) | "
            f"slippage={slippage_bps}bps"
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


def route_trade_all(
    chain: str,
    gem_score: float,
    strategy: str = "gem_snipe",
    token_age_hours: float = 24.0,
    is_express: bool = False,
    use_kelly: bool = True,
) -> list:
    """
    Route a trade to ALL eligible wallets (not just the first one).

    For each active wallet, checks if the gem_score meets the wallet's
    strategy_profile.min_gem_score threshold. Returns a list of
    TradeAllocations — one per eligible wallet.

    This enables both Primary (conservative) and Wallet B (nuclear) to
    enter the same token simultaneously with different position sizes.
    """
    allocations = []
    eligible_wallets = get_wallets_for_chain(chain)
    if not eligible_wallets:
        return allocations

    for wallet in eligible_wallets:
        profile = wallet.strategy_profile
        # Skip if gem score doesn't meet this wallet's profile threshold
        if gem_score < profile.min_gem_score:
            logger.debug(
                f"  {wallet.alias} [{profile.name}] skipped: "
                f"score {gem_score:.0f} < min {profile.min_gem_score:.0f}"
            )
            continue

        # Determine express for this wallet's profile
        wallet_is_express = is_express or gem_score >= profile.express_lane_score
        wallet_alias = wallet.alias.lower().replace(" ", "_")

        # Route to this specific wallet only
        alloc = route_trade(
            chain=chain,
            gem_score=gem_score,
            strategy=strategy,
            token_age_hours=token_age_hours,
            is_express=wallet_is_express,
            use_kelly=use_kelly,
            specific_wallet=wallet_alias,
        )
        if alloc:
            allocations.append(alloc)

    if not allocations:
        logger.debug(f"No wallets qualify for {chain} trade (score={gem_score:.0f})")

    return allocations

def get_usdc_balance(wallet_address: str, chain: str) -> float:
    """
    Fetch current USDC balance from public RPC.
    Returns 0.0 on failure.
    """
    chain_config = CHAINS.get(chain)
    if not chain_config or not chain_config.usdc_address:
        return 0.0

    if chain_config.is_solana:
        # Solana USDC balance fetching not implemented here yet
        return 0.0
    else:
        for rpc_url in [chain_config.rpc_url, chain_config.rpc_fallback]:
            if not rpc_url:
                continue
            try:
                import requests
                # ERC20 balanceOf signature: 0x70a08231
                # padded address
                addr_padded = wallet_address.lower().replace("0x", "").zfill(64)
                data = f"0x70a08231{addr_padded}"
                payload = {
                    "jsonrpc": "2.0",
                    "method": "eth_call",
                    "params": [{"to": chain_config.usdc_address, "data": data}, "latest"],
                    "id": 1
                }
                resp = requests.post(rpc_url, json=payload, timeout=5)
                if resp.status_code == 200:
                    res_json = resp.json()
                    if "result" in res_json and res_json["result"] != "0x":
                        # USDC has 6 decimals
                        balance_wei = int(res_json["result"], 16)
                        return balance_wei / 1e6
            except Exception as e:
                logger.debug(f"USDC balance fetch failed on {chain} via {rpc_url}: {e}")
        return 0.0
