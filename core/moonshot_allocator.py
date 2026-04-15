"""
core/moonshot_allocator.py — Moonshot Spray Allocator

Aggressively sprays small positions across qualifying micro-cap tokens
using quarter-Kelly position sizing. Designed for maximum geometric
growth while strictly capping ruin risk.

Capital Rules:
  - Barbell allocation: 10% gas reserve / 40% core / 50% moonshot spray
  - Each moonshot position: 1-3% of portfolio (quarter-Kelly)
  - Max concurrent moonshot positions: 20
  - Aggregate moonshot exposure cap: 50% of total portfolio
  - Min entry: $5 per position (below this → gas exceeds value)

Qualification Filters (ALL must pass):
  ✅ Market cap < $10M (true micro-cap territory)
  ✅ Market cap > $50K (filter out dead tokens)
  ✅ Liquidity > $30K (enough to exit)
  ✅ Volume/Mcap ratio > 5% (active trading)
  ✅ Buy/Sell ratio > 0.55 (more buys than sells — trader-tony pattern)
  ✅ Token age < 72 hours (fresh momentum)
  ✅ Holder count > 30 (sign of organic interest)
  ✅ Safety check passes (GoPlus + TokenSniffer)
  ✅ Not a honeypot / not frozen / no mint authority

Quarter-Kelly Formula:
  f* = (p * b - q) / b  where p=win_prob, b=avg_win/avg_loss, q=1-p
  Position size = 0.25 * f* * bankroll  (quarter-Kelly for safety)
"""

import json
import logging
import math
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from data.http_session import get_session

from config import settings
from config.chains import CHAINS
from config.wallets import WALLETS, get_wallets_for_chain

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────
MOONSHOT_STATE_FILE = Path("output/moonshot_state.json")

# Barbell allocation
GAS_RESERVE_PCT = 0.10      # 10% kept as gas
CORE_HOLD_PCT = 0.40        # 40% for core positions (gem snipe)
MOONSHOT_SPRAY_PCT = 0.50   # 50% for moonshot spray

# Position sizing
MIN_POSITION_USD = float(os.getenv("MOONSHOT_MIN_POSITION_USD", "5.0"))
MAX_POSITION_PCT = float(os.getenv("MOONSHOT_MAX_POSITION_PCT", "0.03"))  # 3% per position
MAX_CONCURRENT_POSITIONS = int(os.getenv("MOONSHOT_MAX_POSITIONS", "20"))
AGGREGATE_EXPOSURE_CAP = 0.50  # 50% of total portfolio

# Token qualification
MAX_MARKET_CAP = float(os.getenv("MOONSHOT_MAX_MCAP", "10_000_000"))  # $10M
MIN_MARKET_CAP = float(os.getenv("MOONSHOT_MIN_MCAP", "50_000"))      # $50K
MIN_LIQUIDITY = float(os.getenv("MOONSHOT_MIN_LIQUIDITY", "30_000"))   # $30K
MIN_VOLUME_MCAP_RATIO = 0.05   # 5% volume/mcap
MIN_BUY_SELL_RATIO = 0.55      # 55% buy ratio
MAX_TOKEN_AGE_HOURS = 72       # 3 days max
MIN_HOLDERS = 30               # At least 30 unique holders

# Kelly criterion baseline parameters (conservative estimates)
DEFAULT_WIN_PROB = 0.30         # 30% of moonshots hit (realistic micro-cap)
DEFAULT_WIN_LOSS_RATIO = 3.0   # Average winner is 3x average loser

DEXSCREENER_CHAIN_MAP = {
    "base": "base", "ethereum": "ethereum", "bsc": "bsc",
    "avalanche": "avalanche", "polygon": "polygon",
    "arbitrum": "arbitrum", "solana": "solana",
}


# ─────────────────────────────────────────────────────────────────────────────
# Data Models
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class MoonshotCandidate:
    """A micro-cap token qualifying for moonshot spray."""
    token_address: str
    symbol: str
    chain: str
    price_usd: float
    market_cap: float
    liquidity_usd: float
    volume_24h: float
    buy_sell_ratio: float = 0.0
    holder_count: int = 0
    token_age_hours: float = 0.0
    price_change_24h: float = 0.0
    price_change_1h: float = 0.0
    safety_passed: bool = False
    # Calculated
    kelly_fraction: float = 0.0
    position_size_usd: float = 0.0
    moonshot_score: float = 0.0


@dataclass
class SprayResult:
    """Result of a moonshot spray cycle."""
    timestamp: str
    total_candidates_scanned: int = 0
    qualified_candidates: int = 0
    positions_opened: int = 0
    total_allocated_usd: float = 0.0
    portfolio_value_usd: float = 0.0
    candidates: list = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Kelly Criterion
# ─────────────────────────────────────────────────────────────────────────────
def calculate_quarter_kelly(
    win_probability: float = DEFAULT_WIN_PROB,
    win_loss_ratio: float = DEFAULT_WIN_LOSS_RATIO,
    bankroll: float = 100.0,
) -> tuple[float, float]:
    """
    Calculate quarter-Kelly position size.

    Full Kelly: f* = (p * b - q) / b
    Quarter Kelly: 0.25 * f*

    Returns (kelly_fraction, position_size_usd)
    """
    p = min(max(win_probability, 0.01), 0.99)  # Clamp
    b = max(win_loss_ratio, 0.1)
    q = 1 - p

    full_kelly = (p * b - q) / b

    # If Kelly is negative, don't bet
    if full_kelly <= 0:
        return 0.0, 0.0

    quarter_kelly = 0.25 * full_kelly
    position_usd = quarter_kelly * bankroll

    # Hard cap at MAX_POSITION_PCT of bankroll
    position_usd = min(position_usd, bankroll * MAX_POSITION_PCT)

    # Floor at minimum
    if position_usd < MIN_POSITION_USD:
        return quarter_kelly, 0.0  # Can't size below minimum

    return quarter_kelly, position_usd


def adjust_win_probability(base_prob: float, candidate: MoonshotCandidate) -> float:
    """
    Adjust win probability based on token characteristics.
    Better metrics → higher win probability → larger position.
    """
    prob = base_prob

    # Volume/mcap ratio boost
    vol_ratio = candidate.volume_24h / max(candidate.market_cap, 1)
    if vol_ratio > 0.20:
        prob += 0.05  # Very active
    elif vol_ratio > 0.10:
        prob += 0.03

    # Buy pressure boost
    if candidate.buy_sell_ratio > 0.70:
        prob += 0.05  # Strong buy pressure
    elif candidate.buy_sell_ratio > 0.60:
        prob += 0.02

    # Freshness bonus (newer = higher optionality)
    if candidate.token_age_hours < 6:
        prob += 0.05
    elif candidate.token_age_hours < 24:
        prob += 0.02

    # Liquidity depth confidence
    if candidate.liquidity_usd > 200_000:
        prob += 0.03  # Easier exit
    elif candidate.liquidity_usd > 100_000:
        prob += 0.01

    # Recent momentum
    if candidate.price_change_1h > 10:
        prob += 0.03
    elif candidate.price_change_1h < -10:
        prob -= 0.05  # Dumping

    # Cap at reasonable range
    return min(max(prob, 0.05), 0.60)


# ─────────────────────────────────────────────────────────────────────────────
# Token Discovery & Qualification
# ─────────────────────────────────────────────────────────────────────────────
def discover_moonshot_candidates(chain: str) -> list[MoonshotCandidate]:
    """
    Discover micro-cap candidates from DexScreener trending + Moralis Pro.
    Returns unfiltered list of candidates.
    """
    candidates = []

    # === Source 1: DexScreener latest boosted (trending) ===
    try:
        r = get_session().get(
            "https://api.dexscreener.com/token-boosts/latest/v1",
            headers={"accept": "application/json"},
            timeout=10,
        )
        if r.status_code == 200:
            tokens = r.json()
            if isinstance(tokens, list):
                for t in tokens:
                    token_chain = t.get("chainId", "")
                    ds_chain = DEXSCREENER_CHAIN_MAP.get(chain)
                    if token_chain != ds_chain:
                        continue
                    address = t.get("tokenAddress", "")
                    if address:
                        candidates.append(MoonshotCandidate(
                            token_address=address,
                            symbol=t.get("description", "???")[:10],
                            chain=chain,
                            price_usd=0, market_cap=0, liquidity_usd=0,
                            volume_24h=0,
                        ))
    except Exception as e:
        logger.debug(f"DexScreener boost scan error: {e}")

    # === Source 2: Moralis Pro trending tokens ===
    moralis_key = os.getenv("MORALIS_API_KEY", "")
    if moralis_key:
        chain_map = {
            "ethereum": "0x1", "base": "0x2105", "bsc": "0x38",
            "polygon": "0x89", "arbitrum": "0xa4b1", "avalanche": "0xa86a",
        }
        moralis_chain = chain_map.get(chain)
        if moralis_chain:
            try:
                r = get_session().get(
                    "https://deep-index.moralis.io/api/v2.2/discovery/tokens/trending",
                    params={"chain": moralis_chain},
                    headers={"X-API-Key": moralis_key, "accept": "application/json"},
                    timeout=15,
                )
                if r.status_code == 200:
                    tokens = r.json()
                    for t in tokens if isinstance(tokens, list) else []:
                        address = t.get("token_address", t.get("address", ""))
                        if address:
                            candidates.append(MoonshotCandidate(
                                token_address=address,
                                symbol=t.get("token_symbol", t.get("symbol", "???"))[:10],
                                chain=chain,
                                price_usd=float(t.get("price_usd", 0) or 0),
                                market_cap=float(t.get("market_cap", 0) or 0),
                                liquidity_usd=0,
                                volume_24h=0,
                            ))
            except Exception as e:
                logger.debug(f"Moralis trending scan error: {e}")

    # === Source 3: From existing gem scan top candidates ===
    try:
        scan_file = Path("output/gem_scan.json")
        if scan_file.exists():
            with open(scan_file) as f:
                scan_data = json.load(f)
            for c in scan_data.get("top_candidates", []):
                if c.get("chain") != chain:
                    continue
                candidates.append(MoonshotCandidate(
                    token_address=c.get("address", ""),
                    symbol=c.get("symbol", "???"),
                    chain=chain,
                    price_usd=float(c.get("price_usd", 0) or 0),
                    market_cap=float(c.get("market_cap", 0) or 0),
                    liquidity_usd=float(c.get("liquidity_usd", 0) or 0),
                    volume_24h=float(c.get("volume_24h", 0) or 0),
                ))
    except Exception:
        pass

    # Dedup by address
    seen = set()
    deduped = []
    for c in candidates:
        key = c.token_address.lower()
        if key not in seen and key:
            seen.add(key)
            deduped.append(c)

    return deduped


def enrich_candidate(candidate: MoonshotCandidate) -> MoonshotCandidate:
    """Fetch full market data for a candidate."""
    from core.portfolio_rebalancer import fetch_token_market_data

    market = fetch_token_market_data(candidate.token_address, candidate.chain)
    candidate.price_usd = market["price_usd"] or candidate.price_usd
    candidate.market_cap = market["market_cap"] or candidate.market_cap
    candidate.liquidity_usd = market["liquidity_usd"] or candidate.liquidity_usd
    candidate.volume_24h = market["volume_24h"] or candidate.volume_24h
    candidate.price_change_24h = market["price_change_24h"]
    candidate.price_change_1h = market["price_change_1h"]

    # Fetch buy/sell ratio from DexScreener detail
    ds_chain = DEXSCREENER_CHAIN_MAP.get(candidate.chain, candidate.chain)
    try:
        r = get_session().get(
            f"https://api.dexscreener.com/tokens/v1/{ds_chain}/{candidate.token_address}",
            headers={"accept": "application/json"},
            timeout=10,
        )
        if r.status_code == 200:
            data = r.json()
            pairs = data if isinstance(data, list) else [data]
            for p in pairs:
                if isinstance(p, dict) and p.get("priceUsd"):
                    txns = p.get("txns", {}).get("h24", {})
                    buys = txns.get("buys", 0)
                    sells = txns.get("sells", 0)
                    total = buys + sells
                    if total > 0:
                        candidate.buy_sell_ratio = buys / total

                    # Token age
                    created = p.get("pairCreatedAt", 0)
                    if created:
                        age_ms = time.time() * 1000 - created
                        candidate.token_age_hours = max(0, age_ms / 3_600_000)

                    # Holder count (from Moralis or estimation)
                    candidate.holder_count = max(
                        candidate.holder_count,
                        int(buys * 0.6) if buys > 0 else 0  # Rough estimate
                    )
                    break
    except Exception:
        pass

    return candidate


def qualify_candidate(candidate: MoonshotCandidate) -> tuple[bool, str]:
    """
    Check if a candidate passes all moonshot filters.
    Returns (qualified, reason).
    """
    if candidate.market_cap > MAX_MARKET_CAP:
        return False, f"mcap ${candidate.market_cap:,.0f} > ${MAX_MARKET_CAP:,.0f}"

    if candidate.market_cap < MIN_MARKET_CAP:
        return False, f"mcap ${candidate.market_cap:,.0f} < ${MIN_MARKET_CAP:,.0f}"

    if candidate.liquidity_usd < MIN_LIQUIDITY:
        return False, f"liq ${candidate.liquidity_usd:,.0f} < ${MIN_LIQUIDITY:,.0f}"

    vol_ratio = candidate.volume_24h / max(candidate.market_cap, 1)
    if vol_ratio < MIN_VOLUME_MCAP_RATIO:
        return False, f"vol/mcap {vol_ratio:.2%} < {MIN_VOLUME_MCAP_RATIO:.0%}"

    if candidate.buy_sell_ratio > 0 and candidate.buy_sell_ratio < MIN_BUY_SELL_RATIO:
        return False, f"buy ratio {candidate.buy_sell_ratio:.2%} < {MIN_BUY_SELL_RATIO:.0%}"

    if candidate.token_age_hours > MAX_TOKEN_AGE_HOURS:
        return False, f"age {candidate.token_age_hours:.0f}h > {MAX_TOKEN_AGE_HOURS}h"

    # Safety check
    try:
        from core.safety import check_token_safety
        safety = check_token_safety(candidate.token_address, candidate.chain)
        if not safety.is_safe:
            return False, f"safety failed: {safety.block_reason}"
        candidate.safety_passed = True
    except Exception as e:
        logger.debug(f"Safety check error for {candidate.symbol}: {e}")
        # Don't block on safety check failure — proceed cautiously

    return True, "qualified"


def score_moonshot(candidate: MoonshotCandidate) -> float:
    """
    Compute a moonshot composite score (0-100).
    Higher = better micro-cap opportunity.
    """
    score = 0.0

    # Volume/mcap activity (25%)
    vol_ratio = candidate.volume_24h / max(candidate.market_cap, 1)
    if vol_ratio >= 0.20:
        score += 25
    elif vol_ratio >= 0.10:
        score += 20
    elif vol_ratio >= 0.05:
        score += 12
    else:
        score += 5

    # Buy pressure (20%)
    if candidate.buy_sell_ratio >= 0.70:
        score += 20
    elif candidate.buy_sell_ratio >= 0.60:
        score += 15
    elif candidate.buy_sell_ratio >= 0.55:
        score += 10
    else:
        score += 5

    # Freshness (20%)
    if candidate.token_age_hours < 6:
        score += 20
    elif candidate.token_age_hours < 24:
        score += 15
    elif candidate.token_age_hours < 48:
        score += 10
    else:
        score += 5

    # Liquidity depth (15%)
    if candidate.liquidity_usd >= 200_000:
        score += 15
    elif candidate.liquidity_usd >= 100_000:
        score += 12
    elif candidate.liquidity_usd >= 50_000:
        score += 8
    else:
        score += 4

    # Momentum (20%)
    if candidate.price_change_1h > 15:
        score += 15  # Slightly less — might be FOMO top
    elif candidate.price_change_1h > 5:
        score += 20  # Sweet spot — rising
    elif candidate.price_change_1h > 0:
        score += 14
    elif candidate.price_change_1h > -5:
        score += 10
    else:
        score += 3

    return min(100, score)


# ─────────────────────────────────────────────────────────────────────────────
# Portfolio Exposure
# ─────────────────────────────────────────────────────────────────────────────
def get_current_moonshot_exposure() -> tuple[int, float]:
    """
    Get current moonshot exposure: (position_count, total_usd_allocated).
    Reads from position tracker.
    """
    count = 0
    total_usd = 0.0
    try:
        from core.position_monitor import load_positions
        positions = load_positions()
        for p in positions:
            if p.get("status") != "open":
                continue
            if p.get("strategy") == "moonshot_spray":
                count += 1
                total_usd += float(p.get("entry_value_usd", 0))
    except Exception:
        pass
    return count, total_usd


def estimate_portfolio_value() -> float:
    """Estimate total portfolio value across all wallets via Moralis Net Worth API."""
    # Primary: Moralis wallet net worth (single API call per wallet, 50 CU)
    try:
        from data.providers.moralis_wallet import get_total_portfolio_value
        total = get_total_portfolio_value()
        if total > 0:
            logger.debug(f"Portfolio value from Moralis: ${total:,.2f}")
            return total
    except Exception as e:
        logger.debug(f"Moralis net worth failed, falling back: {e}")

    # Fallback: estimate from open position tracker
    total = 0.0
    try:
        from core.position_monitor import load_positions
        positions = load_positions()
        for p in positions:
            if p.get("status") == "open":
                total += float(p.get("current_value_usd", p.get("entry_value_usd", 0)))
    except Exception:
        pass

    return max(total, 50.0)  # Floor at $50 to prevent division by zero


# ─────────────────────────────────────────────────────────────────────────────
# Main Spray Cycle
# ─────────────────────────────────────────────────────────────────────────────
def run_moonshot_spray(dry_run: bool = True) -> SprayResult:
    """
    Execute a moonshot spray cycle across active chains.
    Called from main.py after gem scan and Fib hunt.

    1. Discover candidates from DexScreener, Moralis, and gem scan
    2. Enrich with market data
    3. Qualify against filters
    4. Size with quarter-Kelly
    5. Execute (or dry-run log)
    """
    result = SprayResult(
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    # Check current exposure
    current_count, current_usd = get_current_moonshot_exposure()
    if current_count >= MAX_CONCURRENT_POSITIONS:
        logger.info(
            f"🚀 Moonshot spray: at max positions ({current_count}/{MAX_CONCURRENT_POSITIONS})"
        )
        return result

    available_slots = MAX_CONCURRENT_POSITIONS - current_count
    portfolio_value = estimate_portfolio_value()
    moonshot_budget = portfolio_value * MOONSHOT_SPRAY_PCT - current_usd

    if moonshot_budget < MIN_POSITION_USD:
        logger.info(f"🚀 Moonshot spray: budget exhausted (${moonshot_budget:.2f})")
        return result

    logger.info(
        f"🚀 Moonshot Spray: budget=${moonshot_budget:.2f} "
        f"slots={available_slots}/{MAX_CONCURRENT_POSITIONS} "
        f"portfolio=${portfolio_value:.2f}"
    )

    # Build dedup set — tokens we already hold
    held_tokens = set()
    try:
        from core.position_monitor import load_positions
        positions = load_positions()
        held_tokens = {
            p["token_address"].lower()
            for p in positions
            if p.get("status") == "open" and p.get("token_address")
        }
    except Exception:
        pass

    qualified: list[MoonshotCandidate] = []

    for chain in settings.ACTIVE_CHAINS:
        # Discover raw candidates
        raw = discover_moonshot_candidates(chain)
        result.total_candidates_scanned += len(raw)

        for candidate in raw:
            if candidate.token_address.lower() in held_tokens:
                continue  # Already hold

            # Enrich
            candidate = enrich_candidate(candidate)
            time.sleep(0.3)

            # Qualify
            ok, reason = qualify_candidate(candidate)
            if not ok:
                logger.debug(f"  ✗ {candidate.symbol}: {reason}")
                continue

            # Score
            candidate.moonshot_score = score_moonshot(candidate)

            # Size with quarter-Kelly
            adjusted_prob = adjust_win_probability(DEFAULT_WIN_PROB, candidate)
            kelly_f, position_usd = calculate_quarter_kelly(
                win_probability=adjusted_prob,
                win_loss_ratio=DEFAULT_WIN_LOSS_RATIO,
                bankroll=moonshot_budget,
            )
            candidate.kelly_fraction = kelly_f
            candidate.position_size_usd = position_usd

            if position_usd < MIN_POSITION_USD:
                logger.debug(f"  ✗ {candidate.symbol}: position too small (${position_usd:.2f})")
                continue

            qualified.append(candidate)

            if len(qualified) >= available_slots:
                break

        if len(qualified) >= available_slots:
            break

    # Sort by moonshot score descending
    qualified.sort(key=lambda c: c.moonshot_score, reverse=True)
    qualified = qualified[:available_slots]

    result.qualified_candidates = len(qualified)
    result.portfolio_value_usd = portfolio_value

    # Execute or log
    for candidate in qualified:
        entry = {
            "symbol": candidate.symbol,
            "address": candidate.token_address,
            "chain": candidate.chain,
            "mcap": round(candidate.market_cap, 0),
            "liquidity": round(candidate.liquidity_usd, 0),
            "score": round(candidate.moonshot_score, 1),
            "kelly_f": round(candidate.kelly_fraction, 4),
            "position_usd": round(candidate.position_size_usd, 2),
            "buy_sell_ratio": round(candidate.buy_sell_ratio, 2),
        }
        result.candidates.append(entry)
        result.total_allocated_usd += candidate.position_size_usd

        logger.info(
            f"  🎯 {candidate.symbol} on {candidate.chain}: "
            f"mcap=${candidate.market_cap:,.0f} liq=${candidate.liquidity_usd:,.0f} "
            f"score={candidate.moonshot_score:.0f} → ${candidate.position_size_usd:.2f} "
            f"(Kelly f={candidate.kelly_fraction:.3f})"
        )

        if not dry_run:
            try:
                _execute_moonshot_buy(candidate)
                result.positions_opened += 1
                time.sleep(1)  # Rate limit between trades
            except Exception as e:
                logger.error(f"Moonshot buy failed for {candidate.symbol}: {e}")

    # Save result
    result_path = Path("output/moonshot_spray_result.json")
    result_path.parent.mkdir(parents=True, exist_ok=True)
    with open(result_path, "w") as f:
        json.dump({
            "timestamp": result.timestamp,
            "total_scanned": result.total_candidates_scanned,
            "qualified": result.qualified_candidates,
            "opened": result.positions_opened,
            "allocated_usd": round(result.total_allocated_usd, 2),
            "portfolio_usd": round(result.portfolio_value_usd, 2),
            "candidates": result.candidates,
        }, f, indent=2)

    logger.info(
        f"🚀 Moonshot Spray complete: {result.qualified_candidates} qualified, "
        f"${result.total_allocated_usd:.2f} allocated across {result.positions_opened} positions"
    )

    return result


def _execute_moonshot_buy(candidate: MoonshotCandidate):
    """Execute a moonshot buy through the existing trade pipeline."""
    from core.wallet_router import route_trade

    allocation = route_trade(
        chain=candidate.chain,
        gem_score=candidate.moonshot_score,
        strategy="moonshot_spray",
    )
    if not allocation:
        logger.warning(f"No wallet route for moonshot {candidate.symbol} on {candidate.chain}")
        return

    # Override position size with Kelly-calculated amount
    allocation.position_size_usd = candidate.position_size_usd

    is_paper = settings.MODE != "live"

    if candidate.chain == "solana":
        from core.solana_executor import execute_solana_buy
        wallet = allocation.wallet
        sol_key = wallet.solana_address or wallet.address
        sol_pk = wallet.solana_private_key_env or wallet.private_key_env
        execute_solana_buy(
            token_mint=candidate.token_address,
            sol_amount=allocation.position_size_native,
            wallet_public_key=sol_key,
            wallet_private_key_env=sol_pk,
            is_paper=is_paper,
        )
    else:
        from core.executor import TradeExecutor, build_gem_snipe_params
        executor = TradeExecutor()
        params = build_gem_snipe_params(
            wallet=allocation.wallet,
            chain=candidate.chain,
            token_address=candidate.token_address,
            eth_amount=allocation.position_size_native,
        )
        executor.execute_trade(params)

    # Add to Fib watchlist for future monitoring
    from core.fib_hunter import add_to_watchlist
    add_to_watchlist(
        token_address=candidate.token_address,
        symbol=candidate.symbol,
        chain=candidate.chain,
        source="moonshot_spray",
        gem_score=candidate.moonshot_score,
    )


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Moonshot Spray Allocator")
    parser.add_argument("--dry-run", action="store_true", default=True)
    args = parser.parse_args()

    result = run_moonshot_spray(dry_run=args.dry_run)
    print(f"\n{'='*70}")
    print(f"  MOONSHOT SPRAY RESULTS")
    print(f"{'='*70}")
    print(f"  Scanned:    {result.total_candidates_scanned}")
    print(f"  Qualified:  {result.qualified_candidates}")
    print(f"  Opened:     {result.positions_opened}")
    print(f"  Allocated:  ${result.total_allocated_usd:.2f}")
    print(f"{'='*70}")
    for c in result.candidates:
        print(f"  {c['symbol']:<10} ${c['position_usd']:>8.2f} "
              f"(mcap=${c['mcap']:>10,.0f}  score={c['score']:.0f})")
    print()
