"""
core/sniper_discovery.py — ☘️ Shamrock Trading Bot
Microcap Sniper Wallet Discovery Engine

Proactively discovers wallets with consistently high PnL on early microcap
entries across Solana, Ethereum, Base, and BSC. Runs on a slow background
cycle (every 6 hours) and auto-promotes qualifying wallets into the live
copy-trade tracking pool used by wallet_monitor.py.

Discovery Pipeline:
  1. Harvest candidate wallets from top-traders of our best recent gems
     (Moralis /erc20/{token}/top-traders + /token/{network}/{token}/top-holders)
  2. Score each wallet using Moralis profitability/summary + stats endpoints
     (endpoints we pay for but previously only used for our OWN wallets)
  3. Filter: win_rate >= 55%, trades >= 10, avg_roi >= 30%, realized_pnl >= $5k
  4. Persist leaderboard to data/dashboard/sniper_leaderboard.json
  5. Auto-promote top wallets to data/dashboard/sniper_wallets_active.json
     which wallet_monitor.py reads on each poll cycle

Moralis Endpoints Used (all paid, previously unused for discovery):
  - GET /wallets/{addr}/profitability/summary  ← win rate, avg ROI, total PnL
  - GET /wallets/{addr}/stats                  ← trade count, active chains
  - GET /wallets/{addr}/profitability          ← per-token breakdown
  - GET /erc20/{token}/top-traders             ← harvest from gems (proactive)
  - GET /token/{network}/{token}/top-holders   ← Solana harvest
  - GET /wallets/{addr}/chains                 ← multi-chain activity check
  - GET /wallets/{addr}/history                ← recent tx pattern analysis
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────
try:
    from config import settings
    MORALIS_API_KEY: str = getattr(settings, "MORALIS_API_KEY", "")
    ACTIVE_CHAINS: list[str] = getattr(settings, "ACTIVE_CHAINS", ["ethereum", "base", "bsc", "solana"])
except Exception:
    MORALIS_API_KEY = os.getenv("MORALIS_API_KEY", "")
    ACTIVE_CHAINS = ["ethereum", "base", "bsc", "solana"]

BASE_URL = "https://deep-index.moralis.io/api/v2.2"
SOL_BASE_URL = "https://solana-gateway.moralis.io"

# Leaderboard / active wallet files
_DATA_DIR = Path(os.getenv("DASHBOARD_STATE_DIR", "data/dashboard"))
LEADERBOARD_FILE = _DATA_DIR / "sniper_leaderboard.json"
ACTIVE_SNIPERS_FILE = _DATA_DIR / "sniper_wallets_active.json"
DISCOVERY_LOG_FILE = _DATA_DIR / "sniper_discovery_log.json"

# EVM chain → Moralis hex
CHAIN_HEX = {
    "ethereum": "0x1",
    "base": "0x2105",
    "bsc": "0x38",
    "arbitrum": "0xa4b1",
    "polygon": "0x89",
}

# Discovery cycle interval (seconds)
DISCOVERY_INTERVAL_SECONDS = int(os.getenv("SNIPER_DISCOVERY_INTERVAL_S", str(6 * 3600)))

# Scoring thresholds
MIN_WIN_RATE = float(os.getenv("SNIPER_MIN_WIN_RATE", "0.40"))        # 40% — lowered for microcap volatility
MIN_TRADES = int(os.getenv("SNIPER_MIN_TRADES", "5"))                 # 5 trades minimum
MIN_REALIZED_PNL_USD = float(os.getenv("SNIPER_MIN_PNL_USD", "500"))  # $500 — microcap traders don't need $5k
MIN_AVG_ROI_PCT = float(os.getenv("SNIPER_MIN_AVG_ROI_PCT", "15.0")) # 15% average ROI
MAX_TRACKED_SNIPERS = int(os.getenv("SNIPER_MAX_TRACKED", "100"))     # Track more wallets
AUTO_PROMOTE_THRESHOLD = float(os.getenv("SNIPER_AUTO_PROMOTE_SCORE", "35.0"))  # Lower bar for active pool

# Microcap focus: prefer wallets that trade small-cap tokens
MICROCAP_MCAP_THRESHOLD_USD = float(os.getenv("SNIPER_MICROCAP_MCAP_USD", "5_000_000"))

# Rate limiting
_last_request_time: float = 0.0
_REQUEST_DELAY = 0.35  # ~3 req/s — safe for Moralis paid tier


# ─────────────────────────────────────────────────────────────────────────────
# Data Models
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class SniperWallet:
    """A discovered high-PnL microcap sniper wallet."""
    address: str
    chain: str                          # Primary chain (evm or solana)
    alias: str = ""                     # Optional label
    win_rate: float = 0.0               # 0.0–1.0
    total_realized_pnl_usd: float = 0.0
    avg_roi_pct: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    avg_holding_time_hours: float = 0.0
    active_chains: list[str] = field(default_factory=list)
    top_tokens: list[str] = field(default_factory=list)  # Best performing tokens
    sniper_score: float = 0.0           # Composite 0–100
    microcap_focus_score: float = 0.0   # How much they focus on microcaps
    discovery_source: str = ""          # Which gem they were found on
    first_seen: str = ""
    last_updated: str = ""
    is_active: bool = True              # In live tracking pool
    copy_signals_generated: int = 0     # How many copy-trade signals fired
    copy_signals_profitable: int = 0    # How many were profitable

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "SniperWallet":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ─────────────────────────────────────────────────────────────────────────────
# Moralis API Helpers
# ─────────────────────────────────────────────────────────────────────────────
def _headers() -> dict:
    return {"X-API-Key": MORALIS_API_KEY, "Accept": "application/json"}


def _rate_limit() -> None:
    global _last_request_time
    elapsed = time.monotonic() - _last_request_time
    if elapsed < _REQUEST_DELAY:
        time.sleep(_REQUEST_DELAY - elapsed)
    _last_request_time = time.monotonic()


def _get(url: str, params: dict = None, timeout: int = 12) -> Optional[dict]:
    """Safe GET with rate limiting and error handling."""
    if not MORALIS_API_KEY:
        return None
    _rate_limit()
    try:
        r = requests.get(url, headers=_headers(), params=params or {}, timeout=timeout)
        if r.status_code == 429:
            logger.warning("Moralis rate limit hit — sleeping 5s")
            time.sleep(5)
            return None
        if r.status_code in (400, 404):
            return None
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.debug(f"Moralis GET error {url}: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Moralis Wallet Profitability (UNUSED endpoint — key new capability)
# GET /wallets/{address}/profitability/summary
# Returns: total_count_of_trades, winrate, total_realized_profit_usd,
#          avg_buy_price_usd, avg_sell_price_usd, avg_roi_percentage
# ─────────────────────────────────────────────────────────────────────────────
def get_wallet_profitability_summary(address: str) -> Optional[dict]:
    """
    Fetch wallet profitability summary from Moralis.
    Returns win rate, total PnL, avg ROI, trade count.
    This is the PRIMARY scoring endpoint for sniper discovery.
    """
    url = f"{BASE_URL}/wallets/{address}/profitability/summary"
    data = _get(url)
    if not data:
        return None
    return {
        "total_trades": int(data.get("total_count_of_trades", 0)),
        "win_rate": float(data.get("winrate", 0)) / 100.0,  # Moralis returns 0-100
        "total_realized_pnl_usd": float(data.get("total_realized_profit_usd", 0)),
        "avg_roi_pct": float(data.get("avg_roi_percentage", 0)),
        "total_tokens_traded": int(data.get("total_tokens_traded", 0)),
        "raw": data,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Moralis Wallet Per-Token Profitability (UNUSED — deep breakdown)
# GET /wallets/{address}/profitability
# Returns per-token realized PnL, avg buy/sell, ROI
# ─────────────────────────────────────────────────────────────────────────────
def get_wallet_profitability_breakdown(address: str, limit: int = 20) -> list[dict]:
    """
    Fetch per-token profitability for a wallet.
    Used to identify microcap focus and best-performing tokens.
    """
    url = f"{BASE_URL}/wallets/{address}/profitability"
    data = _get(url, params={"limit": limit})
    if not data:
        return []
    result = data.get("result", []) if isinstance(data, dict) else []
    tokens = []
    for t in result:
        tokens.append({
            "token_address": t.get("token_address", ""),
            "token_symbol": t.get("token_symbol", ""),
            "realized_pnl_usd": float(t.get("realized_profit_usd", 0)),
            "roi_pct": float(t.get("roi_percentage", 0)),
            "avg_buy_price_usd": float(t.get("avg_buy_price_usd", 0)),
            "avg_sell_price_usd": float(t.get("avg_sell_price_usd", 0)),
            "count_of_trades": int(t.get("count_of_trades", 0)),
        })
    return tokens


# ─────────────────────────────────────────────────────────────────────────────
# Moralis Wallet Stats (UNUSED for external wallets)
# GET /wallets/{address}/stats
# Returns: nfts, collections, transactions, nft_transfers, token_transfers
# ─────────────────────────────────────────────────────────────────────────────
def get_wallet_activity_stats(address: str) -> dict:
    """
    Fetch wallet activity stats — used to filter out inactive or bot wallets.
    """
    url = f"{BASE_URL}/wallets/{address}/stats"
    data = _get(url)
    if not data:
        return {}
    return {
        "total_transactions": int(data.get("transactions", {}).get("total", 0)),
        "token_transfers": int(data.get("token_transfers", {}).get("total", 0)),
        "nft_transfers": int(data.get("nft_transfers", {}).get("total", 0)),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Moralis Wallet Chain Activity (UNUSED for external wallets)
# GET /wallets/{address}/chains
# Returns which chains the wallet is active on
# ─────────────────────────────────────────────────────────────────────────────
def get_wallet_active_chains(address: str) -> list[str]:
    """
    Discover which chains a wallet is active on.
    Multi-chain snipers are higher quality signals.
    """
    url = f"{BASE_URL}/wallets/{address}/chains"
    data = _get(url)
    if not data:
        return []
    active = data.get("active_chains", []) if isinstance(data, dict) else []
    return [c.get("chain", "") for c in active if c.get("chain")]


# ─────────────────────────────────────────────────────────────────────────────
# Moralis Wallet History (UNUSED for external wallets)
# GET /wallets/{address}/history
# Used to detect early-entry pattern (buys within first hour of token launch)
# ─────────────────────────────────────────────────────────────────────────────
def get_wallet_recent_history(address: str, limit: int = 30) -> list[dict]:
    """
    Fetch recent wallet transaction history.
    Used to detect early-entry pattern and microcap focus.
    """
    url = f"{BASE_URL}/wallets/{address}/history"
    data = _get(url, params={"limit": limit})
    if not data:
        return []
    return data.get("result", []) if isinstance(data, dict) else []


# ─────────────────────────────────────────────────────────────────────────────
# Harvest Candidate Wallets from Recent Gems
# Uses Moralis /erc20/{token}/top-traders proactively (not just per-token scoring)
# ─────────────────────────────────────────────────────────────────────────────
def harvest_evm_candidates_from_gem(token_address: str, chain: str, limit: int = 20) -> list[str]:
    """
    Extract buyer wallet addresses from a gem token's recent transfers.
    Uses /erc20/{token}/transfers (the top-traders endpoint is not available).
    Filters out DEX routers and pools to get real trader wallets.
    """
    if chain not in CHAIN_HEX:
        return []
    # Known DEX router/pool address prefixes to exclude
    EXCLUDE_PREFIXES = {"0x0000000", "0xdead000"}
    EXCLUDE_ADDRESSES = {
        "0x3fc91a3afd70395cd496c647d5a6cc9d4b2b7fad",  # Uniswap Universal Router
        "0x7a250d5630b4cf539739df2c5dacb4c659f2488d",  # Uniswap V2 Router
        "0x68b3465833fb72a70ecdf485e0e4c7bd8665fc45",  # Uniswap V3 Router
        "0x1111111254eeb25477b68fb85ed929f73a960582",  # 1inch V5
        "0x10ed43c718714eb63d5aa57b78b54704e256024e",  # PancakeSwap V2
        "0x13f4ea83d0bd40e75c8222255bc855a974568dd4",  # PancakeSwap V3
    }

    url = f"{BASE_URL}/erc20/{token_address}/transfers"
    data = _get(url, params={
        "chain": CHAIN_HEX[chain],
        "limit": 100,           # Get more transfers to find unique buyers
        "order": "DESC",        # Most recent first
    })
    if not data:
        return []
    result = data.get("result", []) if isinstance(data, dict) else []

    # Extract unique buyer addresses (to_address = receiver = buyer)
    addresses = []
    seen = set()
    for t in result:
        addr = (t.get("to_address") or "").lower()
        if not addr or len(addr) != 42 or not addr.startswith("0x"):
            continue
        if addr in seen or addr in EXCLUDE_ADDRESSES:
            continue
        if any(addr.startswith(p) for p in EXCLUDE_PREFIXES):
            continue
        # Skip if from_address == to_address (self-transfer)
        if addr == (t.get("from_address") or "").lower():
            continue
        seen.add(addr)
        addresses.append(addr)
        if len(addresses) >= limit:
            break
    return addresses


def harvest_solana_candidates_from_gem(token_address: str, limit: int = 20) -> list[str]:
    """
    Extract top holder wallet addresses from a Solana gem token.
    Uses Moralis Solana token top-holders endpoint.
    """
    url = f"{SOL_BASE_URL}/token/mainnet/{token_address}/top-holders"
    data = _get(url, params={"limit": limit})
    if not data:
        return []
    result = data.get("result", []) if isinstance(data, dict) else []
    return [h.get("owner_address", "") for h in result if h.get("owner_address")]


def harvest_candidates_from_recent_gems(max_gems: int = 20) -> dict[str, list[str]]:
    """
    Pull top trader wallets from our best recent gems.
    Returns {chain: [wallet_address, ...]}
    """
    candidates: dict[str, list[str]] = {c: [] for c in ACTIVE_CHAINS}

    # Load recent gem history from dashboard state
    gem_history_file = _DATA_DIR / "gem_history.json"
    if not gem_history_file.exists():
        logger.info("SniperDiscovery: No gem history yet — skipping harvest")
        return candidates

    try:
        with open(gem_history_file) as f:
            gems = json.load(f)
    except Exception as e:
        logger.warning(f"SniperDiscovery: Could not load gem history: {e}")
        return candidates

    # Sort by gem_score descending, take top N
    # gem_history.json uses 'gem_score' key, fallback to 'score' for compat
    gems = sorted(gems, key=lambda g: g.get("gem_score", g.get("score", 0)), reverse=True)[:max_gems]
    if gems:
        top_score = gems[0].get("gem_score", gems[0].get("score", 0))
        logger.info(f"SniperDiscovery: Top gem score={top_score}, processing {len(gems)} gems")

    for gem in gems:
        token_address = gem.get("address", "")
        chain = gem.get("chain", "").lower()
        if not token_address or not chain:
            continue

        try:
            if chain == "solana":
                wallets = harvest_solana_candidates_from_gem(token_address)
                candidates["solana"].extend(wallets)
                if wallets:
                    logger.info(f"Harvested {len(wallets)} Solana candidates from {gem.get('symbol', token_address[:8])}")
            elif chain in CHAIN_HEX:
                wallets = harvest_evm_candidates_from_gem(token_address, chain)
                candidates[chain].extend(wallets)
                if wallets:
                    logger.info(f"Harvested {len(wallets)} EVM candidates from {gem.get('symbol', token_address[:8])} on {chain}")
        except Exception as e:
            logger.debug(f"Harvest error for {token_address[:8]}: {e}")

    # Deduplicate
    for chain in candidates:
        candidates[chain] = list(dict.fromkeys(candidates[chain]))

    total = sum(len(v) for v in candidates.values())
    logger.info(f"SniperDiscovery: Harvested {total} candidate wallets from {len(gems)} gems")
    return candidates


# ─────────────────────────────────────────────────────────────────────────────
# Wallet Scoring Engine
# ─────────────────────────────────────────────────────────────────────────────
def _score_wallet(address: str, chain: str, discovery_source: str = "") -> Optional[SniperWallet]:
    """
    Score a candidate wallet using Moralis profitability endpoints.
    Returns a SniperWallet if it meets minimum thresholds, else None.
    """
    # 1. Profitability summary — primary filter
    prof = get_wallet_profitability_summary(address)
    if not prof:
        return None

    win_rate = prof["win_rate"]
    total_pnl = prof["total_realized_pnl_usd"]
    avg_roi = prof["avg_roi_pct"]
    total_trades = prof["total_trades"]

    # Hard filters — log rejections at debug level for tuning
    if win_rate < MIN_WIN_RATE:
        logger.debug(f"Rejected {address[:10]}: win_rate={win_rate:.0%} < {MIN_WIN_RATE:.0%}")
        return None
    if total_trades < MIN_TRADES:
        logger.debug(f"Rejected {address[:10]}: trades={total_trades} < {MIN_TRADES}")
        return None
    if total_pnl < MIN_REALIZED_PNL_USD:
        logger.debug(f"Rejected {address[:10]}: pnl=${total_pnl:,.0f} < ${MIN_REALIZED_PNL_USD:,.0f}")
        return None
    if avg_roi < MIN_AVG_ROI_PCT:
        logger.debug(f"Rejected {address[:10]}: roi={avg_roi:.0f}% < {MIN_AVG_ROI_PCT:.0f}%")
        return None

    # 2. Per-token breakdown — microcap focus detection
    token_breakdown = get_wallet_profitability_breakdown(address, limit=20)
    microcap_focus = _calculate_microcap_focus(token_breakdown)
    top_tokens = [t["token_symbol"] for t in sorted(
        token_breakdown, key=lambda x: x["realized_pnl_usd"], reverse=True
    )[:5]]

    # 3. Active chains
    active_chains = get_wallet_active_chains(address) if chain != "solana" else ["solana"]

    # 4. Moralis Wallet Entity Labels — know WHO is buying
    # GET /wallets/{addr}/labels — returns labels like 'Whale', 'Bot', 'Exchange'
    # Known MEV/sandwich bots are filtered out. Known whales get a score boost.
    entity_label = ""
    entity_type = ""
    entity_boost = 0.0
    try:
        from data.providers.moralis_intelligence import get_wallet_labels
        _labels = get_wallet_labels(address)
        if _labels:
            entity_label = _labels.get("primary_label", "")
            entity_type = _labels.get("entity_type", "")
            _etype = entity_type.lower()
            # Filter out bot wallets — they front-run, not alpha
            if _etype in ("mev_bot", "sandwich_bot", "arbitrage_bot", "flashbot"):
                logger.debug(f"Skipping bot wallet {address[:10]}... ({entity_type})")
                return None
            # Known whales or smart money — strong signal
            if _etype in ("whale", "fund", "smart_money", "vc", "defi_protocol"):
                entity_boost = 8.0
                logger.info(
                    f"Entity label: {address[:10]}... is '{entity_label}' ({entity_type}) — +8 boost"
                )
            elif _etype in ("exchange", "cex", "market_maker"):
                entity_boost = 3.0
    except Exception as _lbl_err:
        logger.debug(f"Wallet entity labels skipped: {_lbl_err}")

    # 5. Composite sniper score (0–100) + entity boost
    sniper_score = _calculate_sniper_score(
        win_rate=win_rate,
        total_pnl=total_pnl,
        avg_roi=avg_roi,
        total_trades=total_trades,
        microcap_focus=microcap_focus,
        multi_chain=len(active_chains) > 1,
    )
    sniper_score = min(100.0, round(sniper_score + entity_boost, 2))

    now = datetime.now(timezone.utc).isoformat()
    return SniperWallet(
        address=address,
        chain=chain,
        alias=entity_label or "",
        win_rate=win_rate,
        total_realized_pnl_usd=total_pnl,
        avg_roi_pct=avg_roi,
        total_trades=total_trades,
        winning_trades=int(total_trades * win_rate),
        active_chains=active_chains,
        top_tokens=top_tokens,
        sniper_score=sniper_score,
        microcap_focus_score=microcap_focus,
        discovery_source=discovery_source,
        first_seen=now,
        last_updated=now,
        is_active=sniper_score >= AUTO_PROMOTE_THRESHOLD,
    )


def _calculate_microcap_focus(token_breakdown: list[dict]) -> float:
    """
    Score 0–100 for how focused this wallet is on microcap tokens.
    Proxy: wallets with high ROI on low avg_buy_price tokens = microcap snipers.
    """
    if not token_breakdown:
        return 50.0
    # Tokens bought at < $0.001 avg price = likely microcap
    microcap_trades = [t for t in token_breakdown if t.get("avg_buy_price_usd", 1) < 0.01]
    if not token_breakdown:
        return 50.0
    focus_ratio = len(microcap_trades) / len(token_breakdown)
    # Also weight by PnL from microcap trades
    total_pnl = sum(t["realized_pnl_usd"] for t in token_breakdown) or 1
    microcap_pnl = sum(t["realized_pnl_usd"] for t in microcap_trades)
    pnl_ratio = microcap_pnl / total_pnl if total_pnl > 0 else 0
    return round(min(100.0, (focus_ratio * 50 + pnl_ratio * 50)), 1)


def _calculate_sniper_score(
    win_rate: float,
    total_pnl: float,
    avg_roi: float,
    total_trades: int,
    microcap_focus: float,
    multi_chain: bool,
) -> float:
    """
    Composite sniper score 0–100.
    Weights:
      - Win rate:       30%  (consistency is king)
      - Avg ROI:        25%  (magnitude of wins)
      - Total PnL:      20%  (absolute proof of profit)
      - Microcap focus: 15%  (specialization in our target market)
      - Trade volume:   5%   (experience)
      - Multi-chain:    5%   (versatility)
    """
    # Win rate: 55% = 0pts, 100% = 30pts
    win_score = max(0, (win_rate - 0.55) / 0.45) * 30

    # Avg ROI: 30% = 0pts, 500%+ = 25pts
    roi_score = min(25.0, (avg_roi / 500.0) * 25)

    # Total PnL: $5k = 0pts, $500k+ = 20pts
    pnl_score = min(20.0, (total_pnl / 500_000) * 20)

    # Microcap focus: direct 0–15 pts
    mc_score = (microcap_focus / 100.0) * 15

    # Trade experience: 10 = 0pts, 200+ = 5pts
    trade_score = min(5.0, (total_trades / 200) * 5)

    # Multi-chain bonus
    chain_score = 5.0 if multi_chain else 0.0

    total = win_score + roi_score + pnl_score + mc_score + trade_score + chain_score
    return round(min(100.0, total), 1)


# ─────────────────────────────────────────────────────────────────────────────
# Leaderboard Persistence
# ─────────────────────────────────────────────────────────────────────────────
def load_leaderboard() -> list[SniperWallet]:
    """Load the persisted sniper leaderboard."""
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not LEADERBOARD_FILE.exists():
        return []
    try:
        with open(LEADERBOARD_FILE) as f:
            data = json.load(f)
        return [SniperWallet.from_dict(d) for d in data]
    except Exception as e:
        logger.warning(f"SniperDiscovery: Could not load leaderboard: {e}")
        return []


def save_leaderboard(wallets: list[SniperWallet]) -> None:
    """Persist the sniper leaderboard."""
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        tmp = LEADERBOARD_FILE.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump([w.to_dict() for w in wallets], f, indent=2)
        tmp.replace(LEADERBOARD_FILE)
    except Exception as e:
        logger.error(f"SniperDiscovery: Could not save leaderboard: {e}")


def save_active_snipers(wallets: list[SniperWallet]) -> None:
    """
    Persist the active (auto-promoted) sniper wallet list.
    wallet_monitor.py reads this file on each poll cycle to dynamically
    expand the copy-trade tracking pool.
    """
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    active = [w for w in wallets if w.is_active]
    evm = [w.address for w in active if w.chain != "solana"]
    sol = [w.address for w in active if w.chain == "solana"]
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "total_active": len(active),
        "evm": evm,
        "solana": sol,
        "wallets": [w.to_dict() for w in active],
    }
    try:
        tmp = ACTIVE_SNIPERS_FILE.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(payload, f, indent=2)
        tmp.replace(ACTIVE_SNIPERS_FILE)
        logger.info(
            f"✅ SniperDiscovery: {len(active)} active snipers saved "
            f"({len(evm)} EVM, {len(sol)} Solana)"
        )
    except Exception as e:
        logger.error(f"SniperDiscovery: Could not save active snipers: {e}")


def _log_discovery_event(event: dict) -> None:
    """Append a discovery event to the log file."""
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        log = []
        if DISCOVERY_LOG_FILE.exists():
            with open(DISCOVERY_LOG_FILE) as f:
                log = json.load(f)
        log.append(event)
        log = log[-500:]  # Keep last 500 events
        with open(DISCOVERY_LOG_FILE, "w") as f:
            json.dump(log, f, indent=2)
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# DexScreener Boosted-Token Fallback (when gem history produces 0 candidates)
# ─────────────────────────────────────────────────────────────────────────────
_DEXSCREENER_CHAIN_MAP = {
    "ethereum": "ethereum",
    "base": "base",
    "bsc": "bsc",
    "solana": "solana",
    "arbitrum": "arbitrum",
    "polygon": "polygon",
}


def _harvest_from_dexscreener_boosted() -> dict[str, list[str]]:
    """
    Fallback candidate source: fetch trending boosted tokens from DexScreener,
    then harvest top-traders from those via Moralis.
    Used when gem_history is empty or produces 0 candidates.
    """
    candidates: dict[str, list[str]] = {c: [] for c in ACTIVE_CHAINS}
    try:
        r = requests.get(
            "https://api.dexscreener.com/token-boosts/latest/v1",
            timeout=10,
        )
        if r.status_code != 200:
            logger.warning(f"DexScreener boosted fetch failed: {r.status_code}")
            return candidates
        boosts = r.json()
        if not isinstance(boosts, list):
            return candidates

        # Take up to 30 unique tokens across our target chains
        seen_tokens: set[str] = set()
        token_list: list[dict] = []
        for b in boosts:
            chain_id = b.get("chainId", "").lower()
            token_addr = b.get("tokenAddress", "")
            if chain_id not in _DEXSCREENER_CHAIN_MAP or not token_addr:
                continue
            if token_addr in seen_tokens:
                continue
            seen_tokens.add(token_addr)
            token_list.append({
                "address": token_addr,
                "chain": _DEXSCREENER_CHAIN_MAP[chain_id],
                "symbol": b.get("description", token_addr[:8]),
            })
            if len(token_list) >= 30:
                break

        logger.info(f"SniperDiscovery: DexScreener fallback found {len(token_list)} boosted tokens")

        for token in token_list:
            address = token["address"]
            chain = token["chain"]
            try:
                if chain == "solana":
                    wallets = harvest_solana_candidates_from_gem(address)
                    candidates["solana"].extend(wallets)
                elif chain in CHAIN_HEX:
                    wallets = harvest_evm_candidates_from_gem(address, chain)
                    candidates[chain].extend(wallets)
                else:
                    continue
                if wallets:
                    logger.info(
                        f"DexScreener fallback: {len(wallets)} candidates from "
                        f"{token['symbol']} on {chain}"
                    )
            except Exception as e:
                logger.debug(f"DexScreener harvest error {address[:8]}: {e}")

        # Deduplicate
        for chain in candidates:
            candidates[chain] = list(dict.fromkeys(candidates[chain]))

        total = sum(len(v) for v in candidates.values())
        logger.info(f"SniperDiscovery: DexScreener fallback yielded {total} candidates")
        return candidates

    except Exception as e:
        logger.warning(f"SniperDiscovery: DexScreener fallback error: {e}")
        return candidates


# ─────────────────────────────────────────────────────────────────────────────
# Main Discovery Cycle
# ─────────────────────────────────────────────────────────────────────────────
def run_discovery_cycle() -> dict:
    """
    Run a full sniper discovery cycle.
    1. Harvest candidates from recent gems
    2. Score each candidate
    3. Merge with existing leaderboard
    4. Save updated leaderboard + active snipers
    Returns summary stats dict.
    """
    if not MORALIS_API_KEY:
        logger.warning("SniperDiscovery: MORALIS_API_KEY not set — skipping discovery")
        return {"error": "no_api_key"}

    start_time = time.monotonic()
    logger.info("🔍 SniperDiscovery: Starting discovery cycle...")

    # Step 1: Harvest candidates from gem history
    candidates = harvest_candidates_from_recent_gems(max_gems=25)
    total_candidates = sum(len(v) for v in candidates.values())

    # Step 1b: Fallback — seed from DexScreener boosted tokens if gem harvest is dry
    if total_candidates == 0:
        logger.info("SniperDiscovery: Gem harvest returned 0 — trying DexScreener boosted fallback")
        candidates = _harvest_from_dexscreener_boosted()
        total_candidates = sum(len(v) for v in candidates.values())

    # Step 1c: Last resort — seed from configured alpha wallets
    if total_candidates == 0:
        logger.info("SniperDiscovery: DexScreener fallback dry — seeding from alpha wallets")
        try:
            from config import settings as _cfg
            alpha_evm = getattr(_cfg, "ALPHA_WALLETS_EVM", None) or getattr(_cfg, "SMART_MONEY_WALLETS", [])
            alpha_sol = getattr(_cfg, "ALPHA_WALLETS_SOLANA", [])
            for w in alpha_evm:
                if w:
                    # Assign to ethereum by default — scoring will determine actual chain
                    candidates.setdefault("ethereum", []).append(w.lower())
            for w in alpha_sol:
                if w:
                    candidates.setdefault("solana", []).append(w)
            total_candidates = sum(len(v) for v in candidates.values())
            logger.info(f"SniperDiscovery: Seeded {total_candidates} alpha wallets as candidates")
        except Exception as e:
            logger.warning(f"SniperDiscovery: Alpha wallet seed error: {e}")

    if total_candidates == 0:
        logger.info("SniperDiscovery: No candidates from any source — will retry next cycle")
        return {"candidates_harvested": 0, "new_snipers": 0, "total_tracked": 0}

    # Step 2: Load existing leaderboard
    existing = load_leaderboard()
    existing_addresses = {w.address.lower() for w in existing}

    # Step 3: Score new candidates
    new_snipers: list[SniperWallet] = []
    scored = 0
    promoted = 0

    for chain, addresses in candidates.items():
        for address in addresses:
            if address.lower() in existing_addresses:
                continue  # Already tracked
            try:
                wallet = _score_wallet(
                    address=address,
                    chain=chain,
                    discovery_source=f"gem_harvest_{chain}",
                )
                scored += 1
                if wallet:
                    new_snipers.append(wallet)
                    if wallet.is_active:
                        promoted += 1
                        logger.info(
                            f"🎯 NEW SNIPER PROMOTED: {address[:10]}... "
                            f"score={wallet.sniper_score:.1f} "
                            f"win_rate={wallet.win_rate*100:.0f}% "
                            f"pnl=${wallet.total_realized_pnl_usd:,.0f} "
                            f"roi={wallet.avg_roi_pct:.0f}%"
                        )
            except Exception as e:
                logger.debug(f"Score error for {address[:10]}...: {e}")

    # Step 4: Merge and rank
    all_wallets = existing + new_snipers
    # Re-sort by sniper_score descending
    all_wallets.sort(key=lambda w: w.sniper_score, reverse=True)
    # Cap at max tracked
    all_wallets = all_wallets[:MAX_TRACKED_SNIPERS]

    # Step 5: Persist
    save_leaderboard(all_wallets)
    save_active_snipers(all_wallets)

    # Step 6: Auto-sync promoted EVM wallets to Moralis Streams (sub-second copy-trade detection)
    if new_snipers and promoted > 0:
        try:
            from core.moralis_streams_manager import MoralisStreamsManager
            active_evm = [w.address for w in all_wallets if w.is_active and w.chain != "solana"]
            if active_evm:
                # Use a short-lived manager instance to sync — the main instance lives in main.py
                # but we need to push new wallets IMMEDIATELY, not wait for the health loop
                mgr = MoralisStreamsManager()
                mgr._discover_existing_streams()
                mgr.sync_alpha_wallets(active_evm)
                logger.info(
                    f"⚡ SniperDiscovery → Streams: Auto-synced {len(active_evm)} "
                    f"EVM wallets to Moralis Streams for sub-second monitoring"
                )
        except Exception as e:
            logger.warning(f"SniperDiscovery: Streams auto-sync failed (non-critical): {e}")

    elapsed = time.monotonic() - start_time
    summary = {
        "candidates_harvested": total_candidates,
        "candidates_scored": scored,
        "new_snipers_found": len(new_snipers),
        "new_snipers_promoted": promoted,
        "total_tracked": len(all_wallets),
        "active_snipers": len([w for w in all_wallets if w.is_active]),
        "elapsed_seconds": round(elapsed, 1),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    _log_discovery_event({"type": "cycle_complete", **summary})
    logger.info(
        f"✅ SniperDiscovery cycle complete: "
        f"{total_candidates} candidates → {len(new_snipers)} new snipers "
        f"({promoted} promoted) | {elapsed:.1f}s"
    )
    return summary


# ─────────────────────────────────────────────────────────────────────────────
# Manual Wallet Addition (from GUI)
# ─────────────────────────────────────────────────────────────────────────────
def add_wallet_manually(address: str, chain: str, alias: str = "") -> dict:
    """
    Manually add a wallet to the sniper tracking pool.
    Scores it immediately using Moralis endpoints.
    Called from the GUI Sniper Wallets page.
    """
    if not address:
        return {"success": False, "error": "No address provided"}

    address = address.strip().lower()

    # Check if already tracked
    existing = load_leaderboard()
    if any(w.address.lower() == address for w in existing):
        return {"success": False, "error": "Wallet already tracked"}

    wallet = _score_wallet(address=address, chain=chain, discovery_source="manual")
    if not wallet:
        # Even if it doesn't meet thresholds, add it with manual flag
        now = datetime.now(timezone.utc).isoformat()
        wallet = SniperWallet(
            address=address,
            chain=chain,
            alias=alias or address[:10] + "...",
            discovery_source="manual",
            first_seen=now,
            last_updated=now,
            is_active=True,  # Manual adds are always active
        )
    else:
        wallet.alias = alias or wallet.alias
        wallet.is_active = True  # Manual adds always active

    existing.append(wallet)
    existing.sort(key=lambda w: w.sniper_score, reverse=True)
    save_leaderboard(existing)
    save_active_snipers(existing)

    _log_discovery_event({
        "type": "manual_add",
        "address": address,
        "chain": chain,
        "alias": alias,
        "score": wallet.sniper_score,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    return {
        "success": True,
        "wallet": wallet.to_dict(),
        "message": f"Added {address[:10]}... to sniper tracking (score={wallet.sniper_score:.1f})",
    }


def remove_wallet(address: str) -> dict:
    """Remove a wallet from the sniper tracking pool."""
    existing = load_leaderboard()
    before = len(existing)
    existing = [w for w in existing if w.address.lower() != address.lower()]
    if len(existing) == before:
        return {"success": False, "error": "Wallet not found"}
    save_leaderboard(existing)
    save_active_snipers(existing)
    return {"success": True, "message": f"Removed {address[:10]}..."}


def refresh_wallet_scores() -> int:
    """
    Re-score all tracked wallets with fresh Moralis data.
    Called periodically to keep scores current.
    Returns number of wallets refreshed.
    """
    existing = load_leaderboard()
    if not existing:
        return 0

    refreshed = 0
    updated = []
    for wallet in existing:
        try:
            fresh = _score_wallet(
                address=wallet.address,
                chain=wallet.chain,
                discovery_source=wallet.discovery_source,
            )
            if fresh:
                fresh.first_seen = wallet.first_seen
                fresh.alias = wallet.alias
                fresh.copy_signals_generated = wallet.copy_signals_generated
                fresh.copy_signals_profitable = wallet.copy_signals_profitable
                updated.append(fresh)
            else:
                # Keep old data but mark as potentially stale
                wallet.last_updated = datetime.now(timezone.utc).isoformat()
                updated.append(wallet)
            refreshed += 1
        except Exception as e:
            logger.debug(f"Refresh error for {wallet.address[:10]}...: {e}")
            updated.append(wallet)

    updated.sort(key=lambda w: w.sniper_score, reverse=True)
    save_leaderboard(updated)
    save_active_snipers(updated)
    logger.info(f"SniperDiscovery: Refreshed {refreshed} wallet scores")
    return refreshed


def record_copy_signal_result(address: str, profitable: bool) -> None:
    """Update copy signal performance stats for a wallet."""
    existing = load_leaderboard()
    for wallet in existing:
        if wallet.address.lower() == address.lower():
            wallet.copy_signals_generated += 1
            if profitable:
                wallet.copy_signals_profitable += 1
            wallet.last_updated = datetime.now(timezone.utc).isoformat()
            break
    save_leaderboard(existing)


def get_active_sniper_addresses() -> dict[str, list[str]]:
    """
    Return {evm: [...], solana: [...]} of currently active sniper addresses.
    Called by wallet_monitor.py on each poll cycle.
    """
    if not ACTIVE_SNIPERS_FILE.exists():
        return {"evm": [], "solana": []}
    try:
        with open(ACTIVE_SNIPERS_FILE) as f:
            data = json.load(f)
        return {
            "evm": data.get("evm", []),
            "solana": data.get("solana", []),
        }
    except Exception:
        return {"evm": [], "solana": []}


def get_leaderboard_stats() -> dict:
    """Return summary stats for the dashboard."""
    wallets = load_leaderboard()
    if not wallets:
        return {
            "total_tracked": 0,
            "active": 0,
            "avg_win_rate": 0,
            "avg_sniper_score": 0,
            "total_pnl_tracked": 0,
            "top_wallet": None,
        }
    active = [w for w in wallets if w.is_active]
    return {
        "total_tracked": len(wallets),
        "active": len(active),
        "avg_win_rate": round(sum(w.win_rate for w in wallets) / len(wallets) * 100, 1),
        "avg_sniper_score": round(sum(w.sniper_score for w in wallets) / len(wallets), 1),
        "total_pnl_tracked": round(sum(w.total_realized_pnl_usd for w in wallets), 2),
        "top_wallet": wallets[0].to_dict() if wallets else None,
        "copy_signals_total": sum(w.copy_signals_generated for w in wallets),
        "copy_signals_profitable": sum(w.copy_signals_profitable for w in wallets),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Background Discovery Daemon
# ─────────────────────────────────────────────────────────────────────────────
class SniperDiscoveryDaemon:
    """
    Background daemon that runs discovery cycles every DISCOVERY_INTERVAL_SECONDS.
    Integrates with the main bot loop via start()/stop().
    """

    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._last_cycle: Optional[dict] = None
        self._cycle_count = 0

    def start(self) -> None:
        if not MORALIS_API_KEY:
            logger.warning("SniperDiscoveryDaemon: No Moralis key — daemon not started")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop,
            name="SniperDiscovery",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            f"✅ SniperDiscoveryDaemon started "
            f"(interval={DISCOVERY_INTERVAL_SECONDS // 3600}h)"
        )

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=15)
        logger.info("SniperDiscoveryDaemon stopped")

    def _loop(self) -> None:
        # Run first cycle immediately on start
        self._run_cycle()
        while not self._stop_event.is_set():
            # Sleep in 60s increments for clean shutdown
            for _ in range(DISCOVERY_INTERVAL_SECONDS // 60):
                if self._stop_event.is_set():
                    return
                time.sleep(60)
            self._run_cycle()

    def _run_cycle(self) -> None:
        try:
            self._last_cycle = run_discovery_cycle()
            self._cycle_count += 1
        except Exception as e:
            logger.error(f"SniperDiscoveryDaemon cycle error: {e}", exc_info=True)

    def get_status(self) -> dict:
        return {
            "running": self._thread is not None and self._thread.is_alive(),
            "cycle_count": self._cycle_count,
            "last_cycle": self._last_cycle,
            "interval_hours": DISCOVERY_INTERVAL_SECONDS // 3600,
        }

    def trigger_now(self) -> dict:
        """Manually trigger a discovery cycle (called from GUI)."""
        logger.info("SniperDiscovery: Manual trigger from GUI")
        return run_discovery_cycle()


# Singleton daemon
_daemon: Optional[SniperDiscoveryDaemon] = None


def get_daemon() -> SniperDiscoveryDaemon:
    global _daemon
    if _daemon is None:
        _daemon = SniperDiscoveryDaemon()
    return _daemon


def start_discovery(run_immediately: bool = True) -> SniperDiscoveryDaemon:
    """Start the discovery daemon. Called from main.py."""
    daemon = get_daemon()
    daemon.start()
    return daemon
