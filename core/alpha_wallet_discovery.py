"""
core/alpha_wallet_discovery.py — ☘️ Shamrock Trading Bot
Alpha Wallet Auto-Discovery Engine (72-Hour PnL Hunter)

A self-updating background daemon that continuously discovers, scores, and
appends the highest-conviction copy-trade wallets to the sniper leaderboard
so the MempoolAlphaSniper always has a fresh pool of insiders to shadow.

Design Philosophy
─────────────────
This module is ADDITIVE to core/sniper_discovery.py. The existing daemon
runs on a 6-hour slow cycle and harvests wallets from our own gem history.
This engine runs on a FASTER 2-hour cycle and uses a completely different
multi-source pipeline focused on the last 72 hours of on-chain performance:

  Source 1  — Moralis Top Traders per token (EVM, all active chains)
  Source 2  — Moralis Whale Accumulation tokens → top-traders
  Source 3  — Moralis Top Gainers (1h) → top-traders
  Source 4  — DexScreener Latest Boosts → top-traders
  Source 5  — Pump.fun Graduated Solana tokens → top holders
  Source 6  — GMGN.ai Solana smart-money feed (if credentials available)
  Source 7  — Moralis EVM Token Snipers (early-entry wallets at launch)
  Source 8  — Re-score existing leaderboard wallets (prune losers)

Scoring Dimensions
──────────────────
  1. Win Rate           (27%)  — consistency is the primary signal
  2. Average ROI        (22%)  — magnitude of wins
  3. Total PnL (72h)    (18%)  — absolute proof of profit in the window
  4. Speed-to-Entry     (15%)  — how early they buy after liquidity seeds
  5. Microcap Focus     (10%)  — specialisation in our target market
  6. Trade Volume        (5%)  — experience proxy
  7. Multi-chain         (3%)  — versatility bonus

Entry Criteria (any one of):
  • Total realized PnL ≥ $50,000 in last 72 hours
  • Average ROI ≥ 10× (1,000%) across trades in last 72 hours

Bot / CEX Filters (binary REJECT):
  • Moralis Insights category: mev_bot | sandwich_bot | arbitrage_bot | bot
  • Moralis Insights: is_contract = True
  • Moralis Insights: is_suspicious = True
  • Known CEX hot wallet addresses (Binance, Coinbase, Kraken, etc.)
  • Win rate < 50% (below coin-flip threshold)
  • Fewer than 3 trades in window (insufficient data)

Leaderboard Management
──────────────────────
  • Wallets scoring ≥ 90 are appended to data/dashboard/sniper_leaderboard.json
  • Full deduplication by address (case-insensitive)
  • Existing entries are re-scored and updated (not duplicated)
  • Wallets that drop below 70 on re-score are marked is_active=False
  • Leaderboard is sorted by sniper_score descending after every write
  • Maximum 200 wallets tracked (oldest/lowest-scored are pruned)

Integration
───────────
  main.py already starts sniper_discovery.start_discovery() — this module
  is started separately as a complementary daemon:

    from core.alpha_wallet_discovery import start_alpha_discovery
    alpha_discovery_daemon = start_alpha_discovery()

  The MempoolAlphaSniper reads from sniper_leaderboard.json on a 5-minute
  cache TTL, so new wallets discovered here are automatically picked up.
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
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Configuration (all env-overridable)
# ─────────────────────────────────────────────────────────────────────────────
try:
    from config import settings as _settings
    MORALIS_API_KEY: str = getattr(_settings, "MORALIS_API_KEY", "")
    ACTIVE_CHAINS: List[str] = getattr(_settings, "ACTIVE_CHAINS", ["ethereum", "base", "bsc", "solana"])
except Exception:
    MORALIS_API_KEY = os.getenv("MORALIS_API_KEY", "")
    ACTIVE_CHAINS = ["ethereum", "base", "bsc", "solana"]

BASE_URL = "https://deep-index.moralis.io/api/v2.2"
SOL_BASE_URL = "https://solana-gateway.moralis.io"

# Leaderboard paths (shared with sniper_discovery.py and mempool_alpha_sniper.py)
_DATA_DIR = Path(os.getenv("DASHBOARD_STATE_DIR", "data/dashboard"))
LEADERBOARD_FILE = _DATA_DIR / "sniper_leaderboard.json"
ACTIVE_SNIPERS_FILE = _DATA_DIR / "sniper_wallets_active.json"
DISCOVERY_LOG_FILE = _DATA_DIR / "alpha_discovery_log.json"

# EVM chain → Moralis hex chain ID
CHAIN_HEX: Dict[str, str] = {
    "ethereum": "0x1",
    "base":     "0x2105",
    "arbitrum": "0xa4b1",
    "polygon":  "0x89",
    "bsc":      "0x38",
}

# Moralis chain slug (for discovery endpoints)
CHAIN_SLUG: Dict[str, str] = {
    "ethereum": "eth",
    "base":     "base",
    "arbitrum": "arbitrum",
    "polygon":  "polygon",
    "bsc":      "bsc",
}

# ── Tunable thresholds ────────────────────────────────────────────────────────
DISCOVERY_INTERVAL_S    = int(os.getenv("ALPHA_DISCOVERY_INTERVAL_S", str(2 * 3600)))  # 2 hours
SCORE_THRESHOLD         = float(os.getenv("ALPHA_DISCOVERY_SCORE_THRESHOLD", "90.0"))
PRUNE_SCORE_FLOOR       = float(os.getenv("ALPHA_DISCOVERY_PRUNE_FLOOR", "70.0"))
MAX_LEADERBOARD_SIZE    = int(os.getenv("ALPHA_DISCOVERY_MAX_WALLETS", "200"))

# Entry criteria — must meet AT LEAST ONE
MIN_72H_PNL_USD         = float(os.getenv("ALPHA_DISCOVERY_MIN_PNL_USD", "50000.0"))
MIN_ROI_MULTIPLIER      = float(os.getenv("ALPHA_DISCOVERY_MIN_ROI_MULT", "10.0"))  # 10× = 1000%

# Hard filters
MIN_WIN_RATE            = float(os.getenv("ALPHA_DISCOVERY_MIN_WIN_RATE", "0.50"))
MIN_TRADES              = int(os.getenv("ALPHA_DISCOVERY_MIN_TRADES", "3"))

# Tokens to harvest per source per chain
TOKENS_PER_SOURCE       = int(os.getenv("ALPHA_DISCOVERY_TOKENS_PER_SOURCE", "10"))
TRADERS_PER_TOKEN       = int(os.getenv("ALPHA_DISCOVERY_TRADERS_PER_TOKEN", "10"))

# Rate limiting (conservative — Moralis Pro: 60 RPS, but we share with main bot)
_REQUEST_DELAY = 0.40   # ~2.5 req/s
_last_req_ts: float = 0.0
_rate_lock = threading.Lock()

# ── Known CEX hot wallet addresses (binary REJECT) ────────────────────────────
# These are publicly known exchange deposit/hot wallets — never organic traders.
_CEX_ADDRESSES: Set[str] = {
    # Binance
    "0x3f5ce5fbfe3e9af3971dd833d26ba9b5c936f0be",
    "0xd551234ae421e3bcba99a0da6d736074f22192ff",
    "0x564286362092d8e7936f0549571a803b203aaced",
    "0x0681d8db095565fe8a346fa0277bffde9c0edbbf",
    "0xe0f0cfde7ee664943906f17f7f14342e76a5cec7",
    "0x8d6f396d210d385033b348bcae9e4f9ea4e045bd",
    # Coinbase
    "0x71660c4005ba85c37ccec55d0c4493e66fe775d3",
    "0x503828976d22510aad0201ac7ec88293211d23da",
    "0xddfabcdc4d8ffc6d5beaf154f18b778f892a0740",
    "0x3cd751e6b0078be393132286c442345e5dc49699",
    "0xb5d85cbf7cb3ee0d56b3bb207d5fc4b82f43f511",
    # Kraken
    "0x2910543af39aba0cd09dbb2d50200b3e800a63d2",
    "0x0a869d79a7052c7f1b55a8ebabbea3420f0d1e13",
    "0xe853c56864a2ebe4576a807d26fdc4a0ada51919",
    # OKX
    "0x6cc5f688a315f3dc28a7781717a9a798a59fda7b",
    "0x236f9f97e0e62388479bf9e5ba4889e46b0273c3",
    # Bybit
    "0xf89d7b9c864f589bbf53a82105107622b35eaa40",
    # Gate.io
    "0x0d0707963952f2fba59dd06f2b425ace40b492fe",
}

# ─────────────────────────────────────────────────────────────────────────────
# Data Model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AlphaWallet:
    """
    Represents a discovered alpha wallet with full scoring metadata.
    Schema is compatible with SniperWallet in sniper_discovery.py so the
    MempoolAlphaSniper can consume both leaderboard sources transparently.
    """
    address: str
    chain: str                          # Primary chain detected on
    alias: str = ""
    win_rate: float = 0.0               # 0.0–1.0
    total_realized_pnl_usd: float = 0.0
    avg_roi_pct: float = 0.0            # Average ROI % across trades
    total_trades: int = 0
    winning_trades: int = 0
    avg_hold_time_hours: float = 0.0    # Speed-to-entry proxy
    early_entry_rate: float = 0.0       # Fraction of buys within 60min of launch
    active_chains: List[str] = field(default_factory=list)
    top_tokens: List[str] = field(default_factory=list)
    sniper_score: float = 0.0           # Composite 0–100
    microcap_focus_score: float = 0.0
    net_worth_usd: float = 0.0
    discovery_source: str = ""
    first_seen: str = ""
    last_updated: str = ""
    is_active: bool = True
    # 72-hour specific fields
    pnl_72h_usd: float = 0.0
    roi_72h_pct: float = 0.0
    trades_72h: int = 0
    # Copy-trade performance tracking
    copy_signals_generated: int = 0
    copy_signals_profitable: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AlphaWallet":
        valid = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**valid)


# ─────────────────────────────────────────────────────────────────────────────
# Moralis API Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _headers() -> Dict[str, str]:
    return {"X-API-Key": MORALIS_API_KEY, "Accept": "application/json"}


def _rate_limit() -> None:
    global _last_req_ts
    with _rate_lock:
        elapsed = time.monotonic() - _last_req_ts
        if elapsed < _REQUEST_DELAY:
            time.sleep(_REQUEST_DELAY - elapsed)
        _last_req_ts = time.monotonic()


def _get(url: str, params: Optional[Dict] = None, timeout: int = 12) -> Optional[Dict]:
    """Rate-limited GET with error handling. Returns None on any failure."""
    if not MORALIS_API_KEY:
        return None
    _rate_limit()
    try:
        from data.http_session import get_session
        r = get_session().get(url, headers=_headers(), params=params or {}, timeout=timeout)
        if r.status_code == 429:
            logger.warning("AlphaDiscovery: Moralis rate limit hit — sleeping 10s")
            time.sleep(10)
            return None
        if r.status_code in (400, 404, 402, 403):
            return None
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.debug(f"AlphaDiscovery GET error {url}: {e}")
        return None


def _safe_float(val: Any) -> float:
    try:
        return float(val) if val is not None else 0.0
    except (ValueError, TypeError):
        return 0.0


def _safe_int(val: Any) -> int:
    try:
        return int(val) if val is not None else 0
    except (ValueError, TypeError):
        return 0


# ─────────────────────────────────────────────────────────────────────────────
# Bot / CEX Filter
# ─────────────────────────────────────────────────────────────────────────────

# Categories returned by Moralis Insights that indicate non-organic wallets
_BOT_CATEGORIES: Set[str] = {
    "mev_bot", "sandwich_bot", "arbitrage_bot", "bot",
    "exchange", "cex", "bridge", "contract",
}


def _is_bot_or_cex(address: str, chain: str) -> bool:
    """
    Return True if the wallet should be REJECTED as a bot, CEX, or contract.

    Uses three layers:
      1. Static CEX address blocklist (instant, no API call)
      2. Moralis Wallet Insights category classifier (30 CU)
      3. is_contract / is_suspicious flags from Insights
    """
    addr_lower = address.lower()

    # Layer 1: Static blocklist
    if addr_lower in _CEX_ADDRESSES:
        logger.debug(f"AlphaDiscovery: CEX blocklist reject {addr_lower[:12]}...")
        return True

    # Layer 2 & 3: Moralis Insights (EVM only — Solana has no insights endpoint)
    if chain != "solana" and chain in CHAIN_HEX:
        try:
            from data.providers.moralis_wallet import get_wallet_insights
            insights = get_wallet_insights(address, chain)
            if insights.get("is_contract", False):
                logger.debug(f"AlphaDiscovery: Contract reject {addr_lower[:12]}...")
                return True
            if insights.get("is_suspicious", False):
                logger.debug(f"AlphaDiscovery: Suspicious wallet reject {addr_lower[:12]}...")
                return True
            category = insights.get("category", "").lower()
            if category in _BOT_CATEGORIES:
                logger.debug(f"AlphaDiscovery: Bot category '{category}' reject {addr_lower[:12]}...")
                return True
        except Exception as e:
            logger.debug(f"AlphaDiscovery: Insights check failed for {addr_lower[:12]}: {e}")

    return False


# ─────────────────────────────────────────────────────────────────────────────
# Scoring Engine
# ─────────────────────────────────────────────────────────────────────────────

def _calculate_alpha_score(
    win_rate: float,
    total_pnl: float,
    avg_roi_pct: float,
    total_trades: int,
    early_entry_rate: float,
    avg_hold_hours: float,
    microcap_focus: float,
    multi_chain: bool,
) -> float:
    """
    Composite alpha score 0–100.

    Weights:
      Win Rate          27%  — consistency is king
      Avg ROI           22%  — magnitude of wins
      Total PnL         18%  — absolute proof of profit
      Speed-to-Entry    15%  — how early they buy (early_entry_rate 0–1)
      Microcap Focus    10%  — specialisation in our target market
      Trade Volume       5%  — experience proxy
      Multi-chain        3%  — versatility bonus

    Bonuses:
      Hold-time sweet spot (0.5–12h avg): +3 pts
      Extraordinary PnL (>$500k):         +5 pts
      Near-perfect win rate (>90%):        +3 pts
    """
    # Win rate: 50% = 0pts, 100% = 27pts
    win_score = max(0.0, (win_rate - 0.50) / 0.50) * 27.0

    # Avg ROI: 100% = 0pts, 1000%+ = 22pts (1000% = 10× = our minimum threshold)
    roi_score = min(22.0, (avg_roi_pct / 1000.0) * 22.0)

    # Total PnL: $50k = 0pts, $500k+ = 18pts
    pnl_score = min(18.0, ((total_pnl - 50_000) / 450_000) * 18.0) if total_pnl >= 50_000 else 0.0

    # Speed-to-Entry: early_entry_rate 0–1.0 → 0–15 pts
    # early_entry_rate = fraction of buys made within 60 min of token launch
    speed_score = min(15.0, early_entry_rate * 15.0)

    # Microcap focus: 0–100 → 0–10 pts
    mc_score = (microcap_focus / 100.0) * 10.0

    # Trade experience: 3 = 0pts, 100+ = 5pts
    trade_score = min(5.0, (total_trades / 100.0) * 5.0)

    # Multi-chain bonus
    chain_score = 3.0 if multi_chain else 0.0

    # Bonuses
    hold_bonus = 3.0 if 0.5 <= avg_hold_hours <= 12.0 else 0.0
    pnl_bonus = 5.0 if total_pnl >= 500_000 else 0.0
    wr_bonus = 3.0 if win_rate >= 0.90 else 0.0

    total = (
        win_score + roi_score + pnl_score + speed_score +
        mc_score + trade_score + chain_score +
        hold_bonus + pnl_bonus + wr_bonus
    )
    return round(min(100.0, max(0.0, total)), 1)


def _calculate_microcap_focus(token_breakdown: List[Dict]) -> float:
    """
    Score 0–100 for how focused this wallet is on microcap tokens.
    Proxy: wallets with high ROI on tokens bought at < $0.01 avg price.
    """
    if not token_breakdown:
        return 50.0
    microcap_trades = [t for t in token_breakdown if _safe_float(t.get("avg_buy_price_usd", 1)) < 0.01]
    focus_ratio = len(microcap_trades) / len(token_breakdown)
    total_pnl = sum(_safe_float(t.get("realized_profit_usd", 0)) for t in token_breakdown) or 1
    microcap_pnl = sum(_safe_float(t.get("realized_profit_usd", 0)) for t in microcap_trades)
    pnl_ratio = microcap_pnl / total_pnl if total_pnl > 0 else 0.0
    return round(min(100.0, (focus_ratio * 50 + pnl_ratio * 50)), 1)


# ─────────────────────────────────────────────────────────────────────────────
# Wallet Profiling (72-hour window)
# ─────────────────────────────────────────────────────────────────────────────

def _profile_evm_wallet(address: str, chain: str, discovery_source: str) -> Optional[AlphaWallet]:
    """
    Full profiling pipeline for an EVM wallet candidate.

    Steps:
      1. Bot/CEX filter (fast reject)
      2. 72-hour PnL summary via Moralis (30 CU)
      3. Entry criteria check (>$50k PnL OR >10× ROI)
      4. Win rate / trade count hard filters
      5. Per-token breakdown for microcap focus (100 CU)
      6. Swap history for speed-to-entry + hold time (50 CU)
      7. Net worth estimate (50 CU)
      8. Composite score calculation

    Returns AlphaWallet if score ≥ SCORE_THRESHOLD, else None.
    """
    addr_lower = address.lower()

    # Step 1: Bot/CEX filter
    if _is_bot_or_cex(addr_lower, chain):
        return None

    # Step 2: 72-hour PnL summary
    try:
        from data.providers.moralis_wallet import get_wallet_pnl_summary
        summary = get_wallet_pnl_summary(addr_lower, chain, days="3")
    except Exception as e:
        logger.debug(f"AlphaDiscovery: PnL summary failed for {addr_lower[:12]}: {e}")
        return None

    if not summary:
        return None

    total_pnl = _safe_float(summary.get("total_realized_profit_usd", 0))
    total_trades = _safe_int(summary.get("total_count_of_trades", 0))
    win_rate_raw = _safe_float(summary.get("win_rate", 0))
    # Moralis returns win_rate as 0–1 in get_wallet_pnl_summary
    win_rate = win_rate_raw if win_rate_raw <= 1.0 else win_rate_raw / 100.0

    # Derive avg ROI from total_realized_profit_percentage
    avg_roi_pct = _safe_float(summary.get("total_realized_profit_percentage", 0))

    # Step 3: Entry criteria — must meet AT LEAST ONE
    meets_pnl_criteria = total_pnl >= MIN_72H_PNL_USD
    meets_roi_criteria = avg_roi_pct >= (MIN_ROI_MULTIPLIER * 100)  # 10× = 1000%
    if not meets_pnl_criteria and not meets_roi_criteria:
        logger.debug(
            f"AlphaDiscovery: Entry criteria fail {addr_lower[:12]} "
            f"pnl=${total_pnl:,.0f} roi={avg_roi_pct:.0f}%"
        )
        return None

    # Step 4: Hard filters
    if win_rate < MIN_WIN_RATE:
        logger.debug(f"AlphaDiscovery: Win rate reject {addr_lower[:12]} wr={win_rate:.0%}")
        return None
    if total_trades < MIN_TRADES:
        logger.debug(f"AlphaDiscovery: Trade count reject {addr_lower[:12]} trades={total_trades}")
        return None

    # Step 5: Per-token breakdown for microcap focus
    microcap_focus = 50.0
    top_tokens: List[str] = []
    try:
        from data.providers.moralis_wallet import get_wallet_pnl
        breakdown_data = get_wallet_pnl(addr_lower, chain, days=3)
        token_list = breakdown_data.get("tokens", [])
        if token_list:
            # Normalize field names (Moralis uses realized_profit_usd)
            normalized = [
                {
                    "avg_buy_price_usd": _safe_float(t.get("avg_buy_price", 0)),
                    "realized_profit_usd": _safe_float(t.get("realized_profit_usd", 0)),
                    "token_symbol": t.get("symbol", ""),
                }
                for t in token_list
            ]
            microcap_focus = _calculate_microcap_focus(normalized)
            top_tokens = [
                t.get("symbol", "?")
                for t in sorted(token_list, key=lambda x: _safe_float(x.get("realized_profit_usd", 0)), reverse=True)[:5]
            ]
    except Exception as e:
        logger.debug(f"AlphaDiscovery: Breakdown failed for {addr_lower[:12]}: {e}")

    # Step 6: Swap history for speed-to-entry
    early_entry_rate = 0.0
    avg_hold_hours = 0.0
    try:
        from data.providers.moralis_wallet import get_wallet_swaps
        swap_data = get_wallet_swaps(addr_lower, chain, limit=50)
        early_entry_rate = _safe_float(swap_data.get("early_entry_rate", 0))
        avg_hold_hours = _safe_float(swap_data.get("avg_hold_time_hours", 0))
    except Exception as e:
        logger.debug(f"AlphaDiscovery: Swap history failed for {addr_lower[:12]}: {e}")

    # Step 7: Net worth estimate
    net_worth = 0.0
    try:
        from data.providers.moralis_wallet import get_wallet_net_worth
        nw_data = get_wallet_net_worth(addr_lower)
        net_worth = _safe_float(nw_data.get("total_networth_usd", 0))
    except Exception as e:
        logger.debug(f"AlphaDiscovery: Net worth failed for {addr_lower[:12]}: {e}")

    # Multi-chain check
    multi_chain = False
    try:
        from core.sniper_discovery import get_wallet_active_chains
        active_chains = get_wallet_active_chains(addr_lower)
        multi_chain = len(active_chains) > 1
    except Exception:
        pass

    # Step 8: Score
    score = _calculate_alpha_score(
        win_rate=win_rate,
        total_pnl=total_pnl,
        avg_roi_pct=avg_roi_pct,
        total_trades=total_trades,
        early_entry_rate=early_entry_rate,
        avg_hold_hours=avg_hold_hours,
        microcap_focus=microcap_focus,
        multi_chain=multi_chain,
    )

    now = datetime.now(timezone.utc).isoformat()
    return AlphaWallet(
        address=addr_lower,
        chain=chain,
        win_rate=round(win_rate, 4),
        total_realized_pnl_usd=round(total_pnl, 2),
        avg_roi_pct=round(avg_roi_pct, 2),
        total_trades=total_trades,
        winning_trades=int(win_rate * total_trades),
        avg_hold_time_hours=round(avg_hold_hours, 2),
        early_entry_rate=round(early_entry_rate, 4),
        active_chains=[chain] if not multi_chain else [],
        top_tokens=top_tokens,
        sniper_score=score,
        microcap_focus_score=round(microcap_focus, 1),
        net_worth_usd=round(net_worth, 2),
        discovery_source=discovery_source,
        pnl_72h_usd=round(total_pnl, 2),
        roi_72h_pct=round(avg_roi_pct, 2),
        trades_72h=total_trades,
        first_seen=now,
        last_updated=now,
        is_active=True,
    )


def _profile_solana_wallet(address: str, discovery_source: str) -> Optional[AlphaWallet]:
    """
    Profile a Solana wallet using GMGN.ai (primary) with Moralis as fallback.

    GMGN provides richer Solana-specific PnL data including per-token realized
    profit, win rate, and recent activity — all critical for 72h scoring.
    """
    # Step 1: Bot filter (address-level only for Solana — no Insights endpoint)
    if address.lower() in _CEX_ADDRESSES:
        return None

    win_rate = 0.0
    total_pnl = 0.0
    avg_roi_pct = 0.0
    total_trades = 0
    top_tokens: List[str] = []
    microcap_focus = 50.0
    early_entry_rate = 0.0
    avg_hold_hours = 0.0

    # Step 2: GMGN primary source
    gmgn_ok = False
    try:
        from core.gmgn_client import get_gmgn_client
        gmgn = get_gmgn_client()
        holdings = gmgn.get_wallet_holdings(address, chain="sol", limit=50)
        if holdings:
            total_realized = sum(_safe_float(h.get("realized_profit", 0)) for h in holdings)
            wins = sum(1 for h in holdings if _safe_float(h.get("realized_profit", 0)) > 0)
            total_pnl = total_realized
            win_rate = wins / len(holdings) if holdings else 0.0
            total_trades = len(holdings)
            top_tokens = [
                (h.get("token", {}) or {}).get("symbol", "?")
                for h in sorted(holdings, key=lambda x: _safe_float(x.get("realized_profit", 0)), reverse=True)[:5]
            ]
            # Microcap focus: tokens with very low buy price
            microcap_trades = [
                h for h in holdings
                if _safe_float((h.get("token", {}) or {}).get("price", 1)) < 0.01
            ]
            microcap_focus = min(100.0, (len(microcap_trades) / max(len(holdings), 1)) * 100)
            gmgn_ok = True

        # Speed-to-entry from recent activity
        if gmgn_ok:
            activity = gmgn.get_wallet_activity(address, chain="sol", limit=30, activity_type="buy")
            if activity:
                # Estimate early entry rate: buys within 2h of token creation
                # GMGN activity has 'timestamp' and 'token_created_at' fields
                early_buys = 0
                hold_times: List[float] = []
                for act in activity:
                    token_age_h = _safe_float(act.get("token_age_hours", 999))
                    if token_age_h < 2.0:
                        early_buys += 1
                    hold_h = _safe_float(act.get("hold_duration_hours", 0))
                    if hold_h > 0:
                        hold_times.append(hold_h)
                early_entry_rate = early_buys / max(len(activity), 1)
                avg_hold_hours = sum(hold_times) / max(len(hold_times), 1)
    except Exception as e:
        logger.debug(f"AlphaDiscovery: GMGN profile failed for {address[:12]}: {e}")

    # Step 3: Moralis fallback for Solana (limited but available)
    if not gmgn_ok:
        try:
            # Moralis Solana wallet swaps for activity data
            from data.providers.moralis_solana import get_wallet_swaps as sol_swaps
            swap_data = sol_swaps(address, limit=50)
            swaps = swap_data.get("swaps", [])
            if swaps:
                buys = [s for s in swaps if s.get("direction") == "buy"]
                sells = [s for s in swaps if s.get("direction") == "sell"]
                total_trades = len(buys)
                # Rough PnL from buy/sell matching is complex — use volume as proxy
                buy_vol = sum(_safe_float(s.get("token_bought_usd", 0)) for s in buys)
                sell_vol = sum(_safe_float(s.get("token_sold_usd", 0)) for s in sells)
                total_pnl = sell_vol - buy_vol
                win_rate = 0.5  # Unknown without per-token breakdown
        except Exception as e:
            logger.debug(f"AlphaDiscovery: Moralis Solana fallback failed for {address[:12]}: {e}")

    # Step 4: Entry criteria
    meets_pnl = total_pnl >= MIN_72H_PNL_USD
    meets_roi = avg_roi_pct >= (MIN_ROI_MULTIPLIER * 100)
    if not meets_pnl and not meets_roi:
        return None
    if win_rate < MIN_WIN_RATE:
        return None
    if total_trades < MIN_TRADES:
        return None

    # Step 5: Score
    score = _calculate_alpha_score(
        win_rate=win_rate,
        total_pnl=total_pnl,
        avg_roi_pct=avg_roi_pct,
        total_trades=total_trades,
        early_entry_rate=early_entry_rate,
        avg_hold_hours=avg_hold_hours,
        microcap_focus=microcap_focus,
        multi_chain=False,
    )

    now = datetime.now(timezone.utc).isoformat()
    return AlphaWallet(
        address=address,
        chain="solana",
        win_rate=round(win_rate, 4),
        total_realized_pnl_usd=round(total_pnl, 2),
        avg_roi_pct=round(avg_roi_pct, 2),
        total_trades=total_trades,
        winning_trades=int(win_rate * total_trades),
        avg_hold_time_hours=round(avg_hold_hours, 2),
        early_entry_rate=round(early_entry_rate, 4),
        active_chains=["solana"],
        top_tokens=top_tokens,
        sniper_score=score,
        microcap_focus_score=round(microcap_focus, 1),
        net_worth_usd=0.0,
        discovery_source=discovery_source,
        pnl_72h_usd=round(total_pnl, 2),
        roi_72h_pct=round(avg_roi_pct, 2),
        trades_72h=total_trades,
        first_seen=now,
        last_updated=now,
        is_active=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Candidate Harvesting — 8 Sources
# ─────────────────────────────────────────────────────────────────────────────

def _harvest_source_1_moralis_top_traders() -> Dict[str, List[str]]:
    """
    Source 1: Moralis Top Traders per token.
    Fetches top gainers on each chain, then pulls top-traders for each token.
    These are wallets that have already made the most profit on hot tokens.
    """
    candidates: Dict[str, List[str]] = {c: [] for c in ACTIVE_CHAINS if c != "solana"}
    try:
        from data.providers.moralis_money import get_top_gainers
        from data.providers.moralis_intelligence import get_top_traders

        evm_chains = [c for c in ACTIVE_CHAINS if c in CHAIN_HEX]
        if not evm_chains:
            logger.warning(
                f"AlphaDiscovery Source 1: No EVM chains in ACTIVE_CHAINS "
                f"({ACTIVE_CHAINS}) — all chains filtered out by CHAIN_HEX check. "
                f"Set ACTIVE_CHAINS env var to include at least one of: {list(CHAIN_HEX.keys())}"
            )
        for chain in evm_chains:
            try:
                gainers = get_top_gainers(chain, time_frame="1h")[:TOKENS_PER_SOURCE]
                if not gainers:
                    logger.debug(f"AlphaDiscovery Source 1 [{chain}]: get_top_gainers returned 0 tokens")
                    continue
                chain_count = 0
                for token in gainers:
                    token_addr = token.get("token_address", "")
                    if not token_addr:
                        continue
                    traders = get_top_traders(token_addr, chain, limit=TRADERS_PER_TOKEN)
                    if not traders:
                        logger.debug(
                            f"AlphaDiscovery Source 1 [{chain}]: "
                            f"get_top_traders returned 0 for {token_addr[:10]}"
                        )
                    for t in traders:
                        addr = t.get("address", "").lower()
                        if addr and not t.get("is_bot", False):
                            candidates[chain].append(addr)
                            chain_count += 1
                    time.sleep(0.3)
                logger.debug(
                    f"AlphaDiscovery Source 1 [{chain}]: "
                    f"{len(gainers)} gainers → {chain_count} wallet candidates"
                )
            except Exception as chain_err:
                logger.warning(f"AlphaDiscovery Source 1 [{chain}] error: {chain_err}")

        for chain in candidates:
            candidates[chain] = list(dict.fromkeys(candidates[chain]))
        logger.info(
            f"AlphaDiscovery Source 1 (Moralis Top Traders): "
            f"{sum(len(v) for v in candidates.values())} candidates "
            f"(chains: {evm_chains if 'evm_chains' in dir() else 'none'})"
        )
    except Exception as e:
        logger.warning(f"AlphaDiscovery Source 1 error: {e}", exc_info=True)
    return candidates


def _harvest_source_2_whale_accumulation() -> Dict[str, List[str]]:
    """
    Source 2: Moralis Whale Accumulation tokens → top-traders.
    Whale accumulation = netExperiencedBuyers signal — the strongest smart money indicator.
    """
    candidates: Dict[str, List[str]] = {c: [] for c in ACTIVE_CHAINS if c != "solana"}
    try:
        from data.providers.moralis_money import get_whale_accumulation_tokens
        from data.providers.moralis_intelligence import get_top_traders

        evm_chains = [c for c in ACTIVE_CHAINS if c in CHAIN_HEX]
        if not evm_chains:
            logger.warning(
                f"AlphaDiscovery Source 2: No EVM chains in ACTIVE_CHAINS ({ACTIVE_CHAINS})"
            )
        for chain in evm_chains:
            try:
                tokens = get_whale_accumulation_tokens(chain)[:TOKENS_PER_SOURCE]
                if not tokens:
                    logger.debug(f"AlphaDiscovery Source 2 [{chain}]: get_whale_accumulation_tokens returned 0")
                    continue
                chain_count = 0
                for token in tokens:
                    token_addr = token.get("token_address", "")
                    if not token_addr:
                        continue
                    traders = get_top_traders(token_addr, chain, limit=TRADERS_PER_TOKEN)
                    for t in traders:
                        addr = t.get("address", "").lower()
                        if addr and not t.get("is_bot", False):
                            candidates[chain].append(addr)
                            chain_count += 1
                    time.sleep(0.3)
                logger.debug(
                    f"AlphaDiscovery Source 2 [{chain}]: "
                    f"{len(tokens)} whale tokens → {chain_count} wallet candidates"
                )
            except Exception as chain_err:
                logger.warning(f"AlphaDiscovery Source 2 [{chain}] error: {chain_err}")

        for chain in candidates:
            candidates[chain] = list(dict.fromkeys(candidates[chain]))
        logger.info(
            f"AlphaDiscovery Source 2 (Whale Accumulation): "
            f"{sum(len(v) for v in candidates.values())} candidates "
            f"(chains: {evm_chains if 'evm_chains' in dir() else 'none'})"
        )
    except Exception as e:
        logger.warning(f"AlphaDiscovery Source 2 error: {e}", exc_info=True)
    return candidates


def _harvest_source_3_top_gainers_24h() -> Dict[str, List[str]]:
    """
    Source 3: Moralis Top Gainers (24h) → top-traders.
    24h gainers catch wallets that made big moves in the last day.
    """
    candidates: Dict[str, List[str]] = {c: [] for c in ACTIVE_CHAINS if c != "solana"}
    try:
        from data.providers.moralis_money import get_top_gainers
        from data.providers.moralis_intelligence import get_top_traders

        evm_chains = [c for c in ACTIVE_CHAINS if c in CHAIN_HEX]
        if not evm_chains:
            logger.warning(
                f"AlphaDiscovery Source 3: No EVM chains in ACTIVE_CHAINS ({ACTIVE_CHAINS})"
            )
        for chain in evm_chains:
            try:
                gainers = get_top_gainers(chain, time_frame="1d")[:TOKENS_PER_SOURCE]
                if not gainers:
                    logger.debug(f"AlphaDiscovery Source 3 [{chain}]: get_top_gainers(1d) returned 0 tokens")
                    continue
                chain_count = 0
                for token in gainers:
                    token_addr = token.get("token_address", "")
                    if not token_addr:
                        continue
                    traders = get_top_traders(token_addr, chain, limit=TRADERS_PER_TOKEN)
                    for t in traders:
                        addr = t.get("address", "").lower()
                        if addr and not t.get("is_bot", False):
                            candidates[chain].append(addr)
                            chain_count += 1
                    time.sleep(0.3)
                logger.debug(
                    f"AlphaDiscovery Source 3 [{chain}]: "
                    f"{len(gainers)} gainers(1d) → {chain_count} wallet candidates"
                )
            except Exception as chain_err:
                logger.warning(f"AlphaDiscovery Source 3 [{chain}] error: {chain_err}")

        for chain in candidates:
            candidates[chain] = list(dict.fromkeys(candidates[chain]))
        logger.info(
            f"AlphaDiscovery Source 3 (Top Gainers 24h): "
            f"{sum(len(v) for v in candidates.values())} candidates "
            f"(chains: {evm_chains if 'evm_chains' in dir() else 'none'})"
        )
    except Exception as e:
        logger.warning(f"AlphaDiscovery Source 3 error: {e}", exc_info=True)
    return candidates


def _harvest_source_4_dexscreener_boosts() -> Dict[str, List[str]]:
    """
    Source 4: DexScreener Latest Boosts → top-traders via Moralis.
    Boosted tokens = community-paid visibility = hype signal. The wallets
    that bought BEFORE the boost was purchased are the insiders.
    """
    candidates: Dict[str, List[str]] = {c: [] for c in ACTIVE_CHAINS if c != "solana"}
    _DEXSCREENER_CHAIN_MAP = {
        "ethereum": "ethereum", "base": "base", "bsc": "bsc",
        "arbitrum": "arbitrum", "polygon": "polygon",
    }
    try:
        from data.http_session import get_session
        from data.providers.moralis_intelligence import get_top_traders

        r = get_session().get(
            "https://api.dexscreener.com/token-boosts/latest/v1",
            timeout=10,
        )
        if r.status_code != 200:
            logger.warning(
                f"AlphaDiscovery Source 4: DexScreener boosts API returned "
                f"{r.status_code} — {r.text[:200]}"
            )
            return candidates

        boosts = r.json() if isinstance(r.json(), list) else []
        if not boosts:
            logger.warning(
                "AlphaDiscovery Source 4: DexScreener boosts returned empty list "
                "(API may have changed format or returned non-list JSON)"
            )
        seen_tokens: Set[str] = set()
        token_list: List[Dict] = []
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
            })
            if len(token_list) >= TOKENS_PER_SOURCE * len(CHAIN_HEX):
                break

        logger.debug(
            f"AlphaDiscovery Source 4: {len(boosts)} boosts from DexScreener, "
            f"{len(token_list)} tokens matched active chains"
        )
        total_count = 0
        for token in token_list:
            chain = token["chain"]
            if chain not in CHAIN_HEX:
                logger.debug(
                    f"AlphaDiscovery Source 4: skipping chain '{chain}' — not in CHAIN_HEX"
                )
                continue
            try:
                traders = get_top_traders(token["address"], chain, limit=TRADERS_PER_TOKEN)
                if not traders:
                    logger.debug(
                        f"AlphaDiscovery Source 4 [{chain}]: "
                        f"get_top_traders returned 0 for {token['address'][:10]}"
                    )
                for t in traders:
                    addr = t.get("address", "").lower()
                    if addr and not t.get("is_bot", False):
                        candidates[chain].append(addr)
                        total_count += 1
                time.sleep(0.3)
            except Exception as token_err:
                logger.warning(
                    f"AlphaDiscovery Source 4 [{chain}] token {token['address'][:10]} error: {token_err}"
                )

        for chain in candidates:
            candidates[chain] = list(dict.fromkeys(candidates[chain]))
        logger.info(
            f"AlphaDiscovery Source 4 (DexScreener Boosts): "
            f"{sum(len(v) for v in candidates.values())} candidates "
            f"from {len(token_list)} boosted tokens"
        )
    except Exception as e:
        logger.warning(f"AlphaDiscovery Source 4 error: {e}", exc_info=True)
    return candidates


def _harvest_source_5_pumpfun_graduated() -> List[str]:
    """
    Source 5: Pump.fun Graduated Solana tokens → top holders.
    Wallets that hold graduated tokens are early-entry Solana insiders.
    """
    candidates: List[str] = []
    try:
        from data.providers.moralis_solana import get_pumpfun_graduated, get_token_top_holders

        graduated = get_pumpfun_graduated(limit=15)
        for token in graduated[:TOKENS_PER_SOURCE]:
            token_addr = token.get("address", token.get("token_address", ""))
            if not token_addr:
                continue
            holders_data = get_token_top_holders(token_addr, limit=TRADERS_PER_TOKEN)
            for h in holders_data.get("holders", []):
                addr = h.get("address", "")
                if addr and addr not in _CEX_ADDRESSES:
                    candidates.append(addr)
            time.sleep(0.3)

        candidates = list(dict.fromkeys(candidates))
        logger.info(f"AlphaDiscovery Source 5 (Pump.fun Graduated): {len(candidates)} candidates")
    except Exception as e:
        logger.warning(f"AlphaDiscovery Source 5 error: {e}")
    return candidates


def _harvest_source_6_gmgn_smart_money() -> List[str]:
    """
    Source 6: GMGN.ai Solana smart-money feed.
    GMGN tracks the top-performing Solana wallets natively — if credentials
    are configured, this is the highest-signal Solana source.
    """
    candidates: List[str] = []
    try:
        from core.gmgn_client import get_gmgn_client
        gmgn = get_gmgn_client()
        # GMGN doesn't have a public leaderboard endpoint, but we can
        # audit the known seed wallets from settings to find new ones
        # via their activity feed (who they interacted with recently).
        from config import settings as _cfg
        seeds = list(getattr(_cfg, "ALPHA_WALLETS_SOLANA", []))
        for seed in seeds[:5]:
            activity = gmgn.get_wallet_activity(seed, chain="sol", limit=20)
            for act in activity:
                # Extract counterparty wallets from swap activity
                counterparty = act.get("counterparty", "")
                if counterparty and counterparty not in _CEX_ADDRESSES:
                    candidates.append(counterparty)
            time.sleep(0.5)

        candidates = list(dict.fromkeys(candidates))
        logger.info(f"AlphaDiscovery Source 6 (GMGN Smart Money): {len(candidates)} candidates")
    except Exception as e:
        logger.debug(f"AlphaDiscovery Source 6 (GMGN): not available — {e}")
    return candidates


def _harvest_source_7_evm_snipers() -> Dict[str, List[str]]:
    """
    Source 7: Moralis EVM Token Snipers — wallets that bought within the
    first few blocks of a new token launch. These are the earliest-entry
    wallets and are extremely high-value for copy-trading.
    """
    candidates: Dict[str, List[str]] = {c: [] for c in ACTIVE_CHAINS if c != "solana"}
    try:
        from data.providers.moralis_money import get_top_gainers
        from data.providers.moralis_intelligence import get_evm_snipers

        for chain in [c for c in ACTIVE_CHAINS if c in CHAIN_HEX]:
            # Use newest tokens (age < 1 day) from top gainers as sniper targets
            gainers = get_top_gainers(chain, time_frame="1h")
            new_tokens = [
                t for t in gainers
                if _safe_float(t.get("token_age_days", 999)) < 1.0
            ][:TOKENS_PER_SOURCE]

            for token in new_tokens:
                token_addr = token.get("token_address", "")
                if not token_addr:
                    continue
                sniper_data = get_evm_snipers(token_addr, chain)
                for s in sniper_data.get("snipers", []):
                    addr = s.get("wallet_address", s.get("address", "")).lower()
                    if addr and addr not in _CEX_ADDRESSES:
                        candidates[chain].append(addr)
                time.sleep(0.3)

        for chain in candidates:
            candidates[chain] = list(dict.fromkeys(candidates[chain]))
        logger.info(
            f"AlphaDiscovery Source 7 (EVM Snipers): "
            f"{sum(len(v) for v in candidates.values())} candidates"
        )
    except Exception as e:
        logger.warning(f"AlphaDiscovery Source 7 error: {e}")
    return candidates


def _harvest_source_8_rescore_existing() -> List[str]:
    """
    Source 8: Re-score existing leaderboard wallets.
    Pulls all currently tracked wallets for fresh re-scoring.
    This prunes losers and updates scores for winners.
    """
    existing = _load_leaderboard()
    return [w.address for w in existing]


# ─────────────────────────────────────────────────────────────────────────────
# Leaderboard Management
# ─────────────────────────────────────────────────────────────────────────────

def _load_leaderboard() -> List[AlphaWallet]:
    """Load the current leaderboard from disk."""
    if not LEADERBOARD_FILE.exists():
        return []
    try:
        with open(LEADERBOARD_FILE) as f:
            data = json.load(f)
        wallets = []
        for entry in data:
            try:
                wallets.append(AlphaWallet.from_dict(entry))
            except Exception:
                # Fallback: create minimal entry from raw dict
                addr = entry.get("address", "")
                if addr:
                    wallets.append(AlphaWallet(
                        address=addr.lower(),
                        chain=entry.get("chain", "ethereum"),
                        sniper_score=_safe_float(entry.get("sniper_score", 0)),
                        win_rate=_safe_float(entry.get("win_rate", 0)),
                        total_realized_pnl_usd=_safe_float(entry.get("total_realized_pnl_usd", 0)),
                        net_worth_usd=_safe_float(entry.get("net_worth_usd", 0)),
                        is_active=entry.get("is_active", True),
                        first_seen=entry.get("first_seen", ""),
                        last_updated=entry.get("last_updated", ""),
                        discovery_source=entry.get("discovery_source", ""),
                        copy_signals_generated=_safe_int(entry.get("copy_signals_generated", 0)),
                        copy_signals_profitable=_safe_int(entry.get("copy_signals_profitable", 0)),
                    ))
        return wallets
    except Exception as e:
        logger.error(f"AlphaDiscovery: Could not load leaderboard: {e}")
        return []


def _save_leaderboard(wallets: List[AlphaWallet]) -> None:
    """
    Persist the leaderboard to disk.
    Sorts by sniper_score descending, prunes to MAX_LEADERBOARD_SIZE.
    Uses atomic write (tmp → rename) to prevent corruption.
    """
    _DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Sort by score descending
    wallets.sort(key=lambda w: w.sniper_score, reverse=True)

    # Prune to max size (keep highest-scored)
    if len(wallets) > MAX_LEADERBOARD_SIZE:
        pruned = wallets[MAX_LEADERBOARD_SIZE:]
        wallets = wallets[:MAX_LEADERBOARD_SIZE]
        logger.info(f"AlphaDiscovery: Pruned {len(pruned)} wallets from leaderboard (max {MAX_LEADERBOARD_SIZE})")

    payload = [w.to_dict() for w in wallets]
    try:
        tmp = LEADERBOARD_FILE.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(payload, f, indent=2)
        tmp.replace(LEADERBOARD_FILE)
        logger.info(f"✅ AlphaDiscovery: Leaderboard saved — {len(wallets)} wallets")
    except Exception as e:
        logger.error(f"AlphaDiscovery: Could not save leaderboard: {e}")


def _update_active_snipers(wallets: List[AlphaWallet]) -> None:
    """
    Update the active snipers file that wallet_monitor.py and
    MempoolAlphaSniper read dynamically.
    """
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    active = [w for w in wallets if w.is_active and w.sniper_score >= SCORE_THRESHOLD]
    evm = [w.address for w in active if w.chain != "solana"]
    sol = [w.address for w in active if w.chain == "solana"]
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source": "alpha_wallet_discovery",
        "total_active": len(active),
        "evm": evm,
        "solana": sol,
        "wallets": [w.to_dict() for w in active],
    }
    try:
        tmp = ACTIVE_SNIPERS_FILE.with_suffix(".alpha.tmp")
        with open(tmp, "w") as f:
            json.dump(payload, f, indent=2)
        tmp.replace(ACTIVE_SNIPERS_FILE)
        logger.info(
            f"✅ AlphaDiscovery: Active snipers updated — "
            f"{len(active)} total ({len(evm)} EVM, {len(sol)} Solana)"
        )
    except Exception as e:
        logger.error(f"AlphaDiscovery: Could not update active snipers: {e}")


def _merge_into_leaderboard(
    new_wallets: List[AlphaWallet],
    existing: List[AlphaWallet],
) -> tuple[List[AlphaWallet], int, int, int]:
    """
    Merge new wallets into the existing leaderboard with full deduplication.

    Rules:
      - New wallet (not in existing): append if score ≥ SCORE_THRESHOLD
      - Existing wallet (re-scored): update score + last_updated, preserve
        copy_signals_generated / copy_signals_profitable
      - Existing wallet that dropped below PRUNE_SCORE_FLOOR: mark is_active=False

    Returns:
      (merged_list, added_count, updated_count, deactivated_count)
    """
    existing_by_addr: Dict[str, AlphaWallet] = {w.address.lower(): w for w in existing}
    added = 0
    updated = 0
    deactivated = 0

    for nw in new_wallets:
        addr = nw.address.lower()
        if addr in existing_by_addr:
            # Update existing entry
            ew = existing_by_addr[addr]
            ew.sniper_score = nw.sniper_score
            ew.win_rate = nw.win_rate
            ew.total_realized_pnl_usd = nw.total_realized_pnl_usd
            ew.avg_roi_pct = nw.avg_roi_pct
            ew.total_trades = nw.total_trades
            ew.winning_trades = nw.winning_trades
            ew.avg_hold_time_hours = nw.avg_hold_time_hours
            ew.early_entry_rate = nw.early_entry_rate
            ew.microcap_focus_score = nw.microcap_focus_score
            ew.top_tokens = nw.top_tokens or ew.top_tokens
            ew.pnl_72h_usd = nw.pnl_72h_usd
            ew.roi_72h_pct = nw.roi_72h_pct
            ew.trades_72h = nw.trades_72h
            ew.last_updated = datetime.now(timezone.utc).isoformat()
            # Prune check
            if ew.sniper_score < PRUNE_SCORE_FLOOR and ew.is_active:
                ew.is_active = False
                deactivated += 1
                logger.info(
                    f"AlphaDiscovery: Deactivated {addr[:12]}... "
                    f"(score dropped to {ew.sniper_score:.1f})"
                )
            elif ew.sniper_score >= SCORE_THRESHOLD:
                ew.is_active = True
            updated += 1
        else:
            # New wallet — only add if score qualifies
            if nw.sniper_score >= SCORE_THRESHOLD:
                existing_by_addr[addr] = nw
                added += 1
                logger.info(
                    f"✅ AlphaDiscovery: NEW alpha wallet {addr[:16]}... "
                    f"score={nw.sniper_score:.1f} pnl=${nw.total_realized_pnl_usd:,.0f} "
                    f"wr={nw.win_rate:.0%} src={nw.discovery_source}"
                )

    return list(existing_by_addr.values()), added, updated, deactivated


def _log_cycle_event(event: Dict) -> None:
    """Append a discovery cycle event to the log file."""
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        log = []
        if DISCOVERY_LOG_FILE.exists():
            with open(DISCOVERY_LOG_FILE) as f:
                log = json.load(f)
        log.append(event)
        log = log[-200:]  # Keep last 200 events
        with open(DISCOVERY_LOG_FILE, "w") as f:
            json.dump(log, f, indent=2)
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Main Discovery Cycle
# ─────────────────────────────────────────────────────────────────────────────

def run_alpha_discovery_cycle() -> Dict[str, Any]:
    """
    Execute one full alpha wallet discovery cycle.

    1. Harvest candidates from 8 sources
    2. Deduplicate candidate addresses
    3. Profile + score each candidate
    4. Merge qualified wallets into leaderboard
    5. Update active snipers file
    6. Log cycle results

    Returns a summary dict with cycle statistics.
    """
    if not MORALIS_API_KEY:
        logger.warning("AlphaDiscovery: No MORALIS_API_KEY — skipping cycle")
        return {"error": "no_api_key"}

    start_ts = time.monotonic()
    logger.info("🔍 AlphaDiscovery: Starting 72-hour alpha wallet discovery cycle...")

    # ── Phase 1: Harvest candidates from all 8 sources ────────────────────
    all_evm_candidates: Dict[str, Set[str]] = {c: set() for c in ACTIVE_CHAINS if c != "solana"}
    all_sol_candidates: Set[str] = set()

    # Source 1: Moralis Top Traders
    s1 = _harvest_source_1_moralis_top_traders()
    for chain, addrs in s1.items():
        all_evm_candidates.setdefault(chain, set()).update(addrs)

    # Source 2: Whale Accumulation
    s2 = _harvest_source_2_whale_accumulation()
    for chain, addrs in s2.items():
        all_evm_candidates.setdefault(chain, set()).update(addrs)

    # Source 3: Top Gainers 24h
    s3 = _harvest_source_3_top_gainers_24h()
    for chain, addrs in s3.items():
        all_evm_candidates.setdefault(chain, set()).update(addrs)

    # Source 4: DexScreener Boosts
    s4 = _harvest_source_4_dexscreener_boosts()
    for chain, addrs in s4.items():
        all_evm_candidates.setdefault(chain, set()).update(addrs)

    # Source 5: Pump.fun Graduated (Solana)
    if "solana" in ACTIVE_CHAINS:
        s5 = _harvest_source_5_pumpfun_graduated()
        all_sol_candidates.update(s5)

    # Source 6: GMGN Smart Money (Solana)
    if "solana" in ACTIVE_CHAINS:
        s6 = _harvest_source_6_gmgn_smart_money()
        all_sol_candidates.update(s6)

    # Source 7: EVM Snipers
    s7 = _harvest_source_7_evm_snipers()
    for chain, addrs in s7.items():
        all_evm_candidates.setdefault(chain, set()).update(addrs)

    # Source 8: Re-score existing leaderboard
    existing_addrs = _harvest_source_8_rescore_existing()
    # Distribute existing wallets to their respective chains for re-scoring
    existing_lb = _load_leaderboard()
    for w in existing_lb:
        if w.chain == "solana":
            all_sol_candidates.add(w.address)
        elif w.chain in all_evm_candidates:
            all_evm_candidates[w.chain].add(w.address)

    total_evm = sum(len(v) for v in all_evm_candidates.values())
    total_sol = len(all_sol_candidates)
    logger.info(
        f"AlphaDiscovery: Harvested {total_evm} EVM + {total_sol} Solana "
        f"unique candidates across all sources"
    )

    # ── Phase 2: Profile + score each candidate ───────────────────────────
    scored_wallets: List[AlphaWallet] = []
    profiled_count = 0
    rejected_count = 0

    # EVM wallets
    for chain, addrs in all_evm_candidates.items():
        for addr in addrs:
            try:
                wallet = _profile_evm_wallet(addr, chain, f"alpha_discovery_{chain}")
                if wallet:
                    scored_wallets.append(wallet)
                    profiled_count += 1
                    logger.debug(
                        f"AlphaDiscovery: Profiled {addr[:12]}... "
                        f"score={wallet.sniper_score:.1f} chain={chain}"
                    )
                else:
                    rejected_count += 1
            except Exception as e:
                logger.debug(f"AlphaDiscovery: Profile error {addr[:12]}: {e}")
                rejected_count += 1

    # Solana wallets
    for addr in all_sol_candidates:
        try:
            wallet = _profile_solana_wallet(addr, "alpha_discovery_solana")
            if wallet:
                scored_wallets.append(wallet)
                profiled_count += 1
            else:
                rejected_count += 1
        except Exception as e:
            logger.debug(f"AlphaDiscovery: Solana profile error {addr[:12]}: {e}")
            rejected_count += 1

    qualified = [w for w in scored_wallets if w.sniper_score >= SCORE_THRESHOLD]
    logger.info(
        f"AlphaDiscovery: Profiled {profiled_count} wallets — "
        f"{len(qualified)} qualified (score ≥ {SCORE_THRESHOLD}), "
        f"{rejected_count} rejected"
    )

    # ── Phase 3: Merge into leaderboard ───────────────────────────────────
    existing_lb = _load_leaderboard()
    merged, added, updated, deactivated = _merge_into_leaderboard(scored_wallets, existing_lb)

    # ── Phase 4: Save leaderboard + active snipers ────────────────────────
    _save_leaderboard(merged)
    _update_active_snipers(merged)

    # ── Phase 5: Log cycle ────────────────────────────────────────────────
    elapsed = round(time.monotonic() - start_ts, 1)
    cycle_summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": elapsed,
        "candidates_harvested": total_evm + total_sol,
        "wallets_profiled": profiled_count,
        "wallets_rejected": rejected_count,
        "wallets_qualified": len(qualified),
        "added_to_leaderboard": added,
        "updated_in_leaderboard": updated,
        "deactivated": deactivated,
        "leaderboard_size": len(merged),
        "active_snipers": len([w for w in merged if w.is_active and w.sniper_score >= SCORE_THRESHOLD]),
    }
    _log_cycle_event(cycle_summary)

    logger.info(
        f"✅ AlphaDiscovery cycle complete in {elapsed}s — "
        f"added={added} updated={updated} deactivated={deactivated} "
        f"leaderboard={len(merged)} active={cycle_summary['active_snipers']}"
    )

    # Log top 5 new additions
    new_wallets = [w for w in merged if w.discovery_source.startswith("alpha_discovery")]
    new_wallets.sort(key=lambda w: w.sniper_score, reverse=True)
    if new_wallets[:5]:
        logger.info("🏆 AlphaDiscovery Top 5 this cycle:")
        for i, w in enumerate(new_wallets[:5], 1):
            logger.info(
                f"  #{i} {w.address[:16]}... | "
                f"Score={w.sniper_score:.1f} | "
                f"PnL=${w.total_realized_pnl_usd:,.0f} | "
                f"WR={w.win_rate:.0%} | "
                f"Chain={w.chain} | "
                f"Src={w.discovery_source}"
            )

    return cycle_summary


# ─────────────────────────────────────────────────────────────────────────────
# Background Daemon
# ─────────────────────────────────────────────────────────────────────────────

class AlphaWalletDiscoveryDaemon:
    """
    Background daemon that runs run_alpha_discovery_cycle() on a configurable
    interval (default 2 hours). Designed to complement the existing
    SniperDiscoveryDaemon in core/sniper_discovery.py.

    The two daemons are intentionally separate:
      - SniperDiscoveryDaemon: 6-hour cycle, harvests from our own gem history
      - AlphaWalletDiscoveryDaemon: 2-hour cycle, 72h PnL focus, 8 sources

    Together they ensure the MempoolAlphaSniper always has a fresh, diverse
    pool of high-conviction wallets to shadow.
    """

    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._cycle_count = 0
        self._last_cycle: Optional[Dict] = None

    def start(self) -> None:
        if not MORALIS_API_KEY:
            logger.warning(
                "AlphaWalletDiscoveryDaemon: No MORALIS_API_KEY configured — daemon not started. "
                "Set MORALIS_API_KEY in .env to enable 72-hour alpha wallet discovery."
            )
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop,
            name="AlphaWalletDiscovery",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            f"✅ AlphaWalletDiscoveryDaemon started "
            f"(interval={DISCOVERY_INTERVAL_S // 3600}h, "
            f"score_threshold={SCORE_THRESHOLD}, "
            f"min_pnl_72h=${MIN_72H_PNL_USD:,.0f})"
        )

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=15)
        logger.info("AlphaWalletDiscoveryDaemon stopped")

    def _loop(self) -> None:
        # Run first cycle immediately on start
        self._run_cycle()
        while not self._stop_event.is_set():
            # Sleep in 60s increments for clean shutdown
            for _ in range(DISCOVERY_INTERVAL_S // 60):
                if self._stop_event.is_set():
                    return
                time.sleep(60)
            self._run_cycle()

    def _run_cycle(self) -> None:
        try:
            self._last_cycle = run_alpha_discovery_cycle()
            self._cycle_count += 1
        except Exception as e:
            logger.error(f"AlphaWalletDiscoveryDaemon cycle error: {e}", exc_info=True)

    def trigger_now(self) -> Dict:
        """Manually trigger a discovery cycle (e.g., from dashboard GUI)."""
        logger.info("AlphaWalletDiscovery: Manual trigger")
        result = run_alpha_discovery_cycle()
        self._cycle_count += 1
        self._last_cycle = result
        return result

    def get_status(self) -> Dict:
        return {
            "running": self._thread is not None and self._thread.is_alive(),
            "cycle_count": self._cycle_count,
            "last_cycle": self._last_cycle,
            "interval_hours": DISCOVERY_INTERVAL_S // 3600,
            "score_threshold": SCORE_THRESHOLD,
            "min_pnl_72h_usd": MIN_72H_PNL_USD,
            "min_roi_multiplier": MIN_ROI_MULTIPLIER,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

_daemon: Optional[AlphaWalletDiscoveryDaemon] = None


def get_alpha_discovery_daemon() -> AlphaWalletDiscoveryDaemon:
    """Return the singleton daemon instance."""
    global _daemon
    if _daemon is None:
        _daemon = AlphaWalletDiscoveryDaemon()
    return _daemon


def start_alpha_discovery(run_immediately: bool = True) -> AlphaWalletDiscoveryDaemon:
    """
    Start the Alpha Wallet Discovery daemon.
    Call this from main.py alongside start_discovery() from sniper_discovery.py.

    Example (main.py):
        from core.alpha_wallet_discovery import start_alpha_discovery
        alpha_daemon = start_alpha_discovery()
    """
    daemon = get_alpha_discovery_daemon()
    daemon.start()
    return daemon


def get_leaderboard_snapshot() -> List[Dict]:
    """
    Return the current leaderboard as a list of dicts.
    Used by the dashboard and monitoring endpoints.
    """
    return [w.to_dict() for w in _load_leaderboard()]


def get_alpha_discovery_stats() -> Dict:
    """Return summary stats for monitoring / dashboard display."""
    wallets = _load_leaderboard()
    if not wallets:
        return {
            "total_tracked": 0, "active": 0, "avg_score": 0,
            "avg_win_rate": 0, "total_pnl_tracked": 0, "top_wallet": None,
        }
    active = [w for w in wallets if w.is_active]
    return {
        "total_tracked": len(wallets),
        "active": len(active),
        "avg_score": round(sum(w.sniper_score for w in wallets) / len(wallets), 1),
        "avg_win_rate": round(sum(w.win_rate for w in wallets) / len(wallets) * 100, 1),
        "total_pnl_tracked": round(sum(w.total_realized_pnl_usd for w in wallets), 2),
        "top_wallet": wallets[0].to_dict() if wallets else None,
        "daemon_status": get_alpha_discovery_daemon().get_status(),
    }
