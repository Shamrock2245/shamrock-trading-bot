"""
core/wallet_router.py — Multi-wallet routing and dynamic position sizing.

Determines which wallet to use for a given trade and how much capital to deploy,
based on:
  1. Chain support (which wallets are active on the target chain)
  2. Strategy assignment (gem_snipe, dca, momentum, etc.)
  3. Current wallet balance (fetched live from RPC)
  4. Conviction score (gem_score → position size multiplier)
  5. Daily loss limit enforcement
  6. Max concurrent position limits

Position Sizing (Alex Becker conviction-based model):
  - Score ≥ 82 (express lane): 100% of max position size
  - Score 70-82: 75% of max position size
  - Score 55-70: 50% of max position size
  - Max position size = wallet_balance × MAX_POSITION_SIZE_PERCENT / 100

Security:
  - Private keys are NEVER stored here — loaded from env vars at execution time
  - Balances are fetched live from public RPCs — never hardcoded
"""

import logging
from dataclasses import dataclass
from typing import Optional

from config import settings
from config.wallets import WALLETS, WalletConfig, get_wallets_for_chain
from config.chains import CHAINS, ChainConfig

logger = logging.getLogger(__name__)


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
    reason: str                    # Human-readable routing decision


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
    try:
        import requests
        payload = {
            "jsonrpc": "2.0",
            "method": "eth_getBalance",
            "params": [wallet_address, "latest"],
            "id": 1,
        }
        resp = requests.post(chain.rpc_url, json=payload, timeout=10)
        result = resp.json().get("result", "0x0")
        balance_wei = int(result, 16)
        decimals = chain.native_token_decimals
        return balance_wei / (10 ** decimals)
    except Exception as e:
        logger.debug(f"EVM balance fetch failed for {wallet_address} on {chain.name}: {e}")
        # Try fallback RPC
        try:
            import requests
            payload = {
                "jsonrpc": "2.0",
                "method": "eth_getBalance",
                "params": [wallet_address, "latest"],
                "id": 1,
            }
            resp = requests.post(chain.rpc_fallback, json=payload, timeout=10)
            result = resp.json().get("result", "0x0")
            balance_wei = int(result, 16)
            return balance_wei / (10 ** chain.native_token_decimals)
        except Exception as e2:
            logger.warning(f"Fallback RPC also failed for {wallet_address}: {e2}")
            return 0.0


def _get_sol_balance(wallet_address: str) -> float:
    """Fetch SOL balance via Solana JSON-RPC."""
    try:
        import requests
        from config import settings as cfg
        rpc_url = cfg.SOLANA_RPC_URL
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getBalance",
            "params": [wallet_address],
        }
        resp = requests.post(rpc_url, json=payload, timeout=10)
        result = resp.json().get("result", {})
        lamports = result.get("value", 0)
        return lamports / 1_000_000_000  # Convert lamports to SOL
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

        url = f"https://api.coingecko.com/api/v3/simple/price"
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


def get_daily_loss_eth(wallet_alias: str) -> float:
    """Calculate today's realized losses for a wallet from the trades log."""
    try:
        import json
        from pathlib import Path
        from datetime import datetime, timezone, date

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


def route_trade(
    chain: str,
    gem_score: float,
    strategy: str = "gem_snipe",
) -> Optional[TradeAllocation]:
    """
    Determine the best wallet and position size for a trade.

    Args:
        chain: Target chain name (e.g. "base", "solana")
        gem_score: Gem score 0-100 (drives position size)
        strategy: Strategy name for wallet matching

    Returns:
        TradeAllocation if a suitable wallet is found, None otherwise.
    """
    # Get wallets active on this chain
    eligible_wallets = get_wallets_for_chain(chain)
    if not eligible_wallets:
        logger.warning(f"No wallets configured for chain: {chain}")
        return None

    # Filter by strategy
    strategy_wallets = [w for w in eligible_wallets if strategy in w.strategies]
    if not strategy_wallets:
        # Fall back to any eligible wallet
        strategy_wallets = eligible_wallets
        logger.debug(f"No wallet with strategy '{strategy}' for {chain} — using any eligible")

    chain_config = CHAINS.get(chain)
    if not chain_config:
        logger.error(f"Unknown chain: {chain}")
        return None

    # Try each wallet in priority order (primary first)
    wallet_priority = ["primary", "wallet_b", "wallet_c"]
    strategy_wallets.sort(
        key=lambda w: wallet_priority.index(w.alias.lower().replace(" ", "_"))
        if w.alias.lower().replace(" ", "_") in wallet_priority else 99
    )

    for wallet in strategy_wallets:
        # Check max concurrent positions
        open_count = get_open_position_count(wallet.alias.lower().replace(" ", "_"))
        if open_count >= wallet.max_concurrent_positions:
            logger.debug(
                f"Wallet {wallet.alias} at max positions "
                f"({open_count}/{wallet.max_concurrent_positions})"
            )
            continue

        # Check daily loss limit
        daily_loss = get_daily_loss_eth(wallet.alias.lower().replace(" ", "_"))
        if daily_loss >= wallet.daily_loss_limit_eth * get_native_price_usd(chain_config.native_token):
            logger.warning(
                f"Wallet {wallet.alias} daily loss limit reached "
                f"(${daily_loss:.2f} lost today)"
            )
            continue

        # Fetch live balance — use Solana address for Solana chain
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

        # Get native token price
        native_price = get_native_price_usd(chain_config.native_token)
        wallet_balance_usd = native_balance * native_price

        # Calculate conviction multiplier
        if gem_score >= settings.CONVICTION_HIGH_THRESHOLD:
            multiplier = settings.CONVICTION_HIGH_MULTIPLIER
        elif gem_score >= settings.CONVICTION_MID_THRESHOLD:
            multiplier = settings.CONVICTION_MID_MULTIPLIER
        else:
            multiplier = settings.CONVICTION_LOW_MULTIPLIER

        # Calculate position size
        max_position_usd = wallet_balance_usd * (wallet.max_position_size_pct / 100)
        position_size_usd = max_position_usd * multiplier

        # Minimum trade size: $50 (avoid dust trades)
        if position_size_usd < 50:
            logger.debug(
                f"Position size too small for {wallet.alias}: "
                f"${position_size_usd:.2f}"
            )
            continue

        position_size_native = position_size_usd / native_price

        reason = (
            f"{wallet.alias} | score={gem_score:.0f} | "
            f"multiplier={multiplier:.2f} | "
            f"balance={native_balance:.4f} {chain_config.native_token} | "
            f"size=${position_size_usd:.2f}"
        )

        logger.info(f"Trade routed: {reason}")

        return TradeAllocation(
            wallet=wallet,
            chain=chain_config,
            position_size_usd=position_size_usd,
            position_size_native=position_size_native,
            native_balance=native_balance,
            native_price_usd=native_price,
            conviction_multiplier=multiplier,
            reason=reason,
        )

    logger.warning(f"No eligible wallet found for {chain} trade (score={gem_score:.0f})")
    return None
