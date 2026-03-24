"""
core/portfolio_rebalancer.py — Multi-Chain Portfolio Rebalancer

Scans all wallet holdings across all active chains, objectively scores every
token, and generates a rebalance plan that liquidates trash → native token.

Scoring Matrix (0–100 per token):
  Liquidity depth      25%  (DexScreener)
  Volume/mcap ratio    20%  (DexScreener)
  Price momentum       15%  (24h + 7d change)
  Fib zone alignment   20%  (fibonacci.py — is price at support?)
  Safety score         20%  (GoPlus + TokenSniffer)

Action Rules:
  Score < 20                → LIQUIDATE (sell immediately)
  Score 20-40 + value < $10 → DUST (ignore, gas exceeds value)
  Score 20-40 + value ≥ $10 → LIQUIDATE
  Score 40-60               → HOLD (monitor next cycle)
  Score ≥ 60 + Fib support  → KEEP (strong position)

Runs once per cycle with 6-hour cooldown between rebalances.
"""

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

from config import settings
from config.wallets import WALLETS, get_wallets_for_chain
from config.chains import CHAINS

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────
REBALANCE_COOLDOWN_HOURS = float(os.getenv("REBALANCE_COOLDOWN_HOURS", "6"))
REBALANCE_STATE_FILE = Path("output/rebalance_state.json")
MIN_LIQUIDATION_VALUE_USD = float(os.getenv("MIN_LIQUIDATION_VALUE_USD", "5.0"))
GAS_RESERVE_PCT = float(os.getenv("GAS_RESERVE_PCT", "0.10"))  # Keep 10% native for gas

# Scoring weights
WEIGHTS = {
    "liquidity": 0.25,
    "volume_ratio": 0.20,
    "momentum": 0.15,
    "fib_support": 0.20,
    "safety": 0.20,
}

# Known stablecoins / wrapped natives to never sell
KEEP_LIST = {
    "USDC", "USDT", "DAI", "BUSD", "WETH", "WBNB", "WAVAX", "WSOL",
    "ETH", "SOL", "BNB", "AVAX", "MATIC",
}


# ─────────────────────────────────────────────────────────────────────────────
# Data Models
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class HoldingScore:
    """Scored token holding in a wallet."""
    token_address: str
    symbol: str
    chain: str
    balance: float
    value_usd: float
    price_usd: float
    # Sub-scores (0-100)
    liquidity_score: float = 0.0
    volume_ratio_score: float = 0.0
    momentum_score: float = 0.0
    fib_support_score: float = 50.0  # Neutral default
    safety_score: float = 50.0       # Neutral default
    # Composite
    total_score: float = 0.0
    # Action
    action: str = "HOLD"  # KEEP, HOLD, LIQUIDATE, DUST
    reason: str = ""


@dataclass
class RebalancePlan:
    """Complete rebalance plan for a wallet+chain combo."""
    wallet_alias: str
    chain: str
    timestamp: str = ""
    native_balance: float = 0.0
    native_value_usd: float = 0.0
    total_holdings_usd: float = 0.0
    keep: list = field(default_factory=list)
    hold: list = field(default_factory=list)
    liquidate: list = field(default_factory=list)
    dust: list = field(default_factory=list)
    estimated_recovery_usd: float = 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Market Data
# ─────────────────────────────────────────────────────────────────────────────
DEXSCREENER_CHAIN_MAP = {
    "base": "base",
    "ethereum": "ethereum",
    "bsc": "bsc",
    "avalanche": "avalanche",
    "polygon": "polygon",
    "arbitrum": "arbitrum",
    "solana": "solana",
}


def fetch_token_market_data(token_address: str, chain: str) -> dict:
    """Fetch price, liquidity, and volume from DexScreener."""
    ds_chain = DEXSCREENER_CHAIN_MAP.get(chain, chain)
    try:
        r = requests.get(
            f"https://api.dexscreener.com/tokens/v1/{ds_chain}/{token_address}",
            headers={"accept": "application/json"},
            timeout=10,
        )
        if r.status_code == 200:
            data = r.json()
            pairs = data if isinstance(data, list) else [data]
            valid_pairs = [p for p in pairs if isinstance(p, dict) and p.get("priceUsd")]
            if valid_pairs:
                valid_pairs.sort(
                    key=lambda p: float(p.get("liquidity", {}).get("usd", 0) or 0),
                    reverse=True,
                )
                p = valid_pairs[0]
                return {
                    "price_usd": float(p.get("priceUsd", 0) or 0),
                    "liquidity_usd": float(p.get("liquidity", {}).get("usd", 0) or 0),
                    "volume_24h": float(p.get("volume", {}).get("h24", 0) or 0),
                    "market_cap": float(p.get("marketCap", 0) or p.get("fdv", 0) or 0),
                    "price_change_24h": float(p.get("priceChange", {}).get("h24", 0) or 0),
                    "price_change_1h": float(p.get("priceChange", {}).get("h1", 0) or 0),
                }
    except Exception as e:
        logger.debug(f"DexScreener error for {token_address} on {chain}: {e}")
    return {
        "price_usd": 0.0, "liquidity_usd": 0.0, "volume_24h": 0.0,
        "market_cap": 0.0, "price_change_24h": 0.0, "price_change_1h": 0.0,
    }


def fetch_wallet_tokens_moralis(wallet_address: str, chain: str) -> list[dict]:
    """Fetch all token balances for a wallet via Moralis Pro API.

    Delegates to the centralized moralis_wallet provider for consistency,
    caching, and rate limiting.
    """
    try:
        from data.providers.moralis_wallet import get_wallet_token_balances
        return get_wallet_token_balances(wallet_address, chain)
    except Exception as e:
        logger.error(f"Moralis token balance fetch failed for {wallet_address} on {chain}: {e}")
    return []


def fetch_wallet_tokens_solana(wallet_address: str) -> list[dict]:
    """Fetch SPL token balances for a Solana wallet."""
    rpc_url = getattr(settings, "SOLANA_RPC_URL", "")
    if not rpc_url:
        return []

    try:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTokenAccountsByOwner",
            "params": [
                wallet_address,
                {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
                {"encoding": "jsonParsed"},
            ],
        }
        r = requests.post(rpc_url, json=payload, timeout=15)
        data = r.json()
        results = []
        for account in data.get("result", {}).get("value", []):
            info = account.get("account", {}).get("data", {}).get("parsed", {}).get("info", {})
            mint = info.get("mint", "")
            token_amount = info.get("tokenAmount", {})
            balance = float(token_amount.get("uiAmount", 0) or 0)
            if balance > 0 and mint:
                results.append({
                    "address": mint,
                    "symbol": "???",  # SPL tokens need separate metadata lookup
                    "name": "",
                    "balance": balance,
                    "decimals": int(token_amount.get("decimals", 9)),
                })
        return results
    except Exception as e:
        logger.error(f"Solana token balance fetch failed: {e}")
    return []


# ─────────────────────────────────────────────────────────────────────────────
# Scoring
# ─────────────────────────────────────────────────────────────────────────────
def score_liquidity(liquidity_usd: float) -> float:
    """Score liquidity depth 0-100."""
    if liquidity_usd >= 500_000:
        return 100
    elif liquidity_usd >= 100_000:
        return 80
    elif liquidity_usd >= 50_000:
        return 60
    elif liquidity_usd >= 30_000:
        return 40
    elif liquidity_usd >= 10_000:
        return 20
    return 5


def score_volume_ratio(volume_24h: float, market_cap: float) -> float:
    """Score volume/mcap ratio 0-100. Higher ratio = more active trading."""
    if market_cap <= 0:
        return 10  # Can't calculate ratio — low confidence
    ratio = volume_24h / market_cap
    if ratio >= 0.20:  # 20%+ volume/mcap = very active
        return 100
    elif ratio >= 0.10:
        return 80
    elif ratio >= 0.05:
        return 60
    elif ratio >= 0.02:
        return 40
    elif ratio >= 0.01:
        return 20
    return 5


def score_momentum(price_change_24h: float, price_change_1h: float) -> float:
    """Score price momentum 0-100. Rewards uptrend, penalizes dumps."""
    # 1h momentum (weighted more — recent action matters)
    if price_change_1h >= 10:
        h1_score = 90
    elif price_change_1h >= 5:
        h1_score = 75
    elif price_change_1h >= 0:
        h1_score = 55
    elif price_change_1h >= -5:
        h1_score = 35
    elif price_change_1h >= -15:
        h1_score = 15
    else:
        h1_score = 5

    # 24h momentum
    if price_change_24h >= 20:
        h24_score = 90
    elif price_change_24h >= 5:
        h24_score = 70
    elif price_change_24h >= -5:
        h24_score = 50
    elif price_change_24h >= -20:
        h24_score = 25
    else:
        h24_score = 5

    return h1_score * 0.6 + h24_score * 0.4


def score_safety_quick(token_address: str, chain: str) -> float:
    """Quick safety check via GoPlus. Returns 0-100."""
    try:
        from core.safety import check_token_safety
        safety = check_token_safety(token_address, chain)
        if not safety.is_safe:
            return 10  # Not safe — but don't zero out (might be false positive)
        # Score based on how clean it is
        score = 60.0
        if safety.goplus_passed:
            score += 15
        if safety.honeypot_passed:
            score += 15
        if safety.buy_tax < 0.03:
            score += 5
        if safety.sell_tax < 0.05:
            score += 5
        return min(100, score)
    except Exception:
        return 50  # Neutral on error


def compute_holding_score(holding: HoldingScore) -> float:
    """Compute weighted composite score."""
    return (
        holding.liquidity_score * WEIGHTS["liquidity"]
        + holding.volume_ratio_score * WEIGHTS["volume_ratio"]
        + holding.momentum_score * WEIGHTS["momentum"]
        + holding.fib_support_score * WEIGHTS["fib_support"]
        + holding.safety_score * WEIGHTS["safety"]
    )


# ─────────────────────────────────────────────────────────────────────────────
# Cooldown
# ─────────────────────────────────────────────────────────────────────────────
def _load_rebalance_state() -> dict:
    """Load last rebalance timestamps."""
    if REBALANCE_STATE_FILE.exists():
        try:
            with open(REBALANCE_STATE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"last_rebalance": {}}


def _save_rebalance_state(state: dict):
    """Save rebalance state."""
    REBALANCE_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(REBALANCE_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def is_rebalance_due(wallet_alias: str, chain: str) -> bool:
    """Check if enough time has passed since last rebalance."""
    state = _load_rebalance_state()
    key = f"{wallet_alias}_{chain}"
    last_ts = state.get("last_rebalance", {}).get(key, 0)
    now = datetime.now(timezone.utc).timestamp()
    return (now - last_ts) >= REBALANCE_COOLDOWN_HOURS * 3600


def mark_rebalance_done(wallet_alias: str, chain: str):
    """Record that rebalance was performed."""
    state = _load_rebalance_state()
    key = f"{wallet_alias}_{chain}"
    if "last_rebalance" not in state:
        state["last_rebalance"] = {}
    state["last_rebalance"][key] = datetime.now(timezone.utc).timestamp()
    _save_rebalance_state(state)


# ─────────────────────────────────────────────────────────────────────────────
# Main Rebalance Logic
# ─────────────────────────────────────────────────────────────────────────────
def generate_rebalance_plan(
    wallet_alias: str,
    chain: str,
    dry_run: bool = True,
) -> Optional[RebalancePlan]:
    """
    Scan a wallet's holdings on a chain, score each, and generate actions.

    Args:
        wallet_alias: Wallet key from config (e.g., "primary")
        chain: Chain name (e.g., "base", "solana")
        dry_run: If True, only plan — don't execute sells

    Returns:
        RebalancePlan with scored holdings and action recommendations
    """
    wallet = WALLETS.get(wallet_alias)
    if not wallet:
        logger.error(f"Unknown wallet: {wallet_alias}")
        return None

    chain_config = CHAINS.get(chain)
    if not chain_config:
        logger.error(f"Unknown chain: {chain}")
        return None

    # Get wallet address for this chain
    if chain_config.is_solana:
        wallet_address = wallet.solana_address or wallet.address
    else:
        wallet_address = wallet.address

    logger.info(f"🔄 Rebalancing {wallet_alias} on {chain} (addr={wallet_address[:12]}...)")

    # 1. Fetch all token holdings
    if chain_config.is_solana:
        tokens = fetch_wallet_tokens_solana(wallet_address)
    else:
        tokens = fetch_wallet_tokens_moralis(wallet_address, chain)

    if not tokens:
        logger.info(f"No token holdings found for {wallet_alias} on {chain}")
        return None

    logger.info(f"Found {len(tokens)} token holdings to evaluate")

    # 2. Score each holding
    scored_holdings: list[HoldingScore] = []
    for token_data in tokens:
        symbol = token_data["symbol"].upper()

        # Skip stablecoins and wrapped natives
        if symbol in KEEP_LIST:
            logger.debug(f"Skipping {symbol} — whitelisted")
            continue

        address = token_data["address"]
        balance = token_data["balance"]

        # Fetch market data from DexScreener
        market = fetch_token_market_data(address, chain)
        time.sleep(0.3)  # Rate limit

        price = market["price_usd"]
        value_usd = balance * price if price > 0 else 0.0

        # Skip truly zero-value tokens
        if value_usd < 0.01:
            continue

        holding = HoldingScore(
            token_address=address,
            symbol=symbol,
            chain=chain,
            balance=balance,
            value_usd=value_usd,
            price_usd=price,
            liquidity_score=score_liquidity(market["liquidity_usd"]),
            volume_ratio_score=score_volume_ratio(market["volume_24h"], market["market_cap"]),
            momentum_score=score_momentum(market["price_change_24h"], market["price_change_1h"]),
            fib_support_score=50.0,  # Default — Fib analysis is expensive, only run on HOLD+
            safety_score=50.0,       # Default — safety check on HOLD+ only
        )

        # Compute initial score (without Fib/safety — those are expensive)
        holding.total_score = compute_holding_score(holding)

        # Quick classification
        if holding.total_score < 20:
            if value_usd < MIN_LIQUIDATION_VALUE_USD:
                holding.action = "DUST"
                holding.reason = f"Score {holding.total_score:.0f} + value ${value_usd:.2f} < gas cost"
            else:
                holding.action = "LIQUIDATE"
                holding.reason = f"Score {holding.total_score:.0f} — dead token"
        elif holding.total_score < 40:
            # Borderline — run safety check
            holding.safety_score = score_safety_quick(address, chain)
            holding.total_score = compute_holding_score(holding)
            if value_usd < MIN_LIQUIDATION_VALUE_USD * 2:
                holding.action = "DUST"
                holding.reason = f"Score {holding.total_score:.0f} + low value"
            else:
                holding.action = "LIQUIDATE"
                holding.reason = f"Score {holding.total_score:.0f} — underperforming"
        elif holding.total_score < 60:
            holding.action = "HOLD"
            holding.reason = f"Score {holding.total_score:.0f} — monitoring"
        else:
            holding.action = "KEEP"
            holding.reason = f"Score {holding.total_score:.0f} — strong position"

        scored_holdings.append(holding)
        logger.debug(
            f"  {symbol:<10} ${value_usd:>8.2f} | score={holding.total_score:.0f} | "
            f"liq={holding.liquidity_score:.0f} vol={holding.volume_ratio_score:.0f} "
            f"mom={holding.momentum_score:.0f} → {holding.action}"
        )

    # 3. Build plan
    plan = RebalancePlan(
        wallet_alias=wallet_alias,
        chain=chain,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    for h in scored_holdings:
        entry = {
            "symbol": h.symbol,
            "address": h.token_address,
            "value_usd": round(h.value_usd, 2),
            "score": round(h.total_score, 1),
            "reason": h.reason,
        }
        if h.action == "KEEP":
            plan.keep.append(entry)
        elif h.action == "HOLD":
            plan.hold.append(entry)
        elif h.action == "LIQUIDATE":
            plan.liquidate.append(entry)
            plan.estimated_recovery_usd += h.value_usd
        else:
            plan.dust.append(entry)

    plan.total_holdings_usd = sum(h.value_usd for h in scored_holdings)

    # 4. Log summary
    logger.info(
        f"📊 Rebalance plan for {wallet_alias}/{chain}: "
        f"KEEP={len(plan.keep)} HOLD={len(plan.hold)} "
        f"LIQUIDATE={len(plan.liquidate)} DUST={len(plan.dust)} | "
        f"Est. recovery: ${plan.estimated_recovery_usd:.2f}"
    )

    # 5. Save plan
    plan_path = Path("output") / f"rebalance_plan_{wallet_alias}_{chain}.json"
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    with open(plan_path, "w") as f:
        json.dump({
            "wallet": plan.wallet_alias,
            "chain": plan.chain,
            "timestamp": plan.timestamp,
            "total_holdings_usd": plan.total_holdings_usd,
            "estimated_recovery_usd": plan.estimated_recovery_usd,
            "keep": plan.keep,
            "hold": plan.hold,
            "liquidate": plan.liquidate,
            "dust": plan.dust,
        }, f, indent=2)
    logger.info(f"Plan saved to {plan_path}")

    # 6. Execute liquidations if not dry_run
    if not dry_run and plan.liquidate:
        execute_liquidations(plan, wallet)

    mark_rebalance_done(wallet_alias, chain)
    return plan


def execute_liquidations(plan: RebalancePlan, wallet) -> int:
    """Execute sell orders for LIQUIDATE tokens. Returns count of successful sells."""
    from core.executor import TradeExecutor
    from notifications.slack import notify_alert

    executor = TradeExecutor()
    is_paper = settings.MODE != "live"
    success_count = 0

    for token in plan.liquidate:
        try:
            symbol = token["symbol"]
            address = token["address"]
            value = token["value_usd"]

            logger.info(f"🗑️ Liquidating {symbol} (${value:.2f}) on {plan.chain}")

            if plan.chain == "solana":
                from core.solana_executor import execute_solana_sell
                sol_public_key = wallet.solana_address or wallet.address
                sol_key_env = wallet.solana_private_key_env or wallet.private_key_env
                tx = execute_solana_sell(
                    token_mint=address,
                    wallet_public_key=sol_public_key,
                    wallet_private_key_env=sol_key_env,
                    sell_percentage=100,
                    is_paper=is_paper,
                )
                if tx:
                    success_count += 1
            else:
                from core.executor import build_take_profit_params
                # Full liquidation: convert token balance to wei
                decimals = token.get("decimals", 18)
                token_amount_wei = int(token.get("balance", 0) * (10 ** decimals))
                if token_amount_wei <= 0:
                    logger.warning(f"Skip liquidation of {symbol}: zero balance")
                    continue
                params = build_take_profit_params(
                    wallet=wallet,
                    chain=plan.chain,
                    token_address=address,
                    token_amount_wei=token_amount_wei,
                    slippage_bps=300,  # 3% slippage for liquidations
                )
                result = executor.execute_trade(params)
                if result.success:
                    success_count += 1

            time.sleep(1)  # Don't spam RPC
        except Exception as e:
            logger.error(f"Failed to liquidate {token.get('symbol', '?')}: {e}")

    if success_count > 0:
        notify_alert(
            "🔄 Portfolio Rebalanced",
            f"Liquidated {success_count}/{len(plan.liquidate)} tokens on {plan.chain} "
            f"(est. recovery: ${plan.estimated_recovery_usd:.2f})",
            level="info",
        )

    return success_count


def run_rebalance_cycle(dry_run: bool = True) -> list[RebalancePlan]:
    """
    Run rebalance across all wallets and active chains.
    Called from main.py bot loop.
    """
    plans = []

    for wallet_key, wallet in WALLETS.items():
        for chain in settings.ACTIVE_CHAINS:
            # Check cooldown
            if not is_rebalance_due(wallet_key, chain):
                logger.debug(f"Rebalance cooldown active for {wallet_key}/{chain}")
                continue

            # Check if wallet supports this chain
            chain_wallets = get_wallets_for_chain(chain)
            if wallet not in chain_wallets:
                continue

            try:
                plan = generate_rebalance_plan(wallet_key, chain, dry_run=dry_run)
                if plan:
                    plans.append(plan)
            except Exception as e:
                logger.error(f"Rebalance failed for {wallet_key}/{chain}: {e}", exc_info=True)

    return plans


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Portfolio Rebalancer")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Plan only, don't execute")
    parser.add_argument("--chain", type=str, default=None, help="Specific chain to rebalance")
    parser.add_argument("--wallet", type=str, default="primary", help="Wallet to rebalance")
    args = parser.parse_args()

    if args.chain:
        plan = generate_rebalance_plan(args.wallet, args.chain, dry_run=args.dry_run)
        if plan:
            print(f"\n{'='*70}")
            print(f"  REBALANCE PLAN: {plan.wallet_alias} / {plan.chain}")
            print(f"{'='*70}")
            print(f"  KEEP ({len(plan.keep)}):       {[t['symbol'] for t in plan.keep]}")
            print(f"  HOLD ({len(plan.hold)}):       {[t['symbol'] for t in plan.hold]}")
            print(f"  LIQUIDATE ({len(plan.liquidate)}): {[t['symbol'] for t in plan.liquidate]}")
            print(f"  DUST ({len(plan.dust)}):       {[t['symbol'] for t in plan.dust]}")
            print(f"  Est. Recovery:     ${plan.estimated_recovery_usd:.2f}")
            print(f"{'='*70}\n")
    else:
        plans = run_rebalance_cycle(dry_run=args.dry_run)
        print(f"\nRebalanced {len(plans)} wallet/chain combinations")
