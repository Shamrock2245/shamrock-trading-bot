"""
core/wallet_monitor.py — Proactive Smart Money Copy-Trading Daemon

Monitors a curated list of alpha wallets in real-time and injects their
DEX buy transactions directly into the Shamrock execution pipeline.

Architecture:
  - Runs as a background thread alongside the main scanner loop
  - Polls each alpha wallet's recent transactions every POLL_INTERVAL seconds
  - Detects NEW DEX swap transactions (buys only) since last check
  - Validates the token against all existing hard gates (bundle, age, safety)
  - If valid: constructs a GemCandidate and injects it into the express lane
    (bypasses the 65-score floor — smart money IS the signal)
  - Deduplicates across wallets: same token bought by 2+ alpha wallets = 2× signal

Why this beats the old reactive approach:
  OLD: Check if smart money HOLDS a token we already found → score boost
  NEW: Detect smart money BUYING a token in real-time → front-run their entry

Supported chains:
  - EVM (Ethereum, Base, Arbitrum, Polygon, BSC): Moralis Wallet API
  - Solana: Helius enhanced transactions API

Alpha wallet tiers:
  TIER_1 (highest conviction): 3+ wallets buying same token = immediate execute
  TIER_2 (high conviction):    2 wallets buying same token = express lane
  TIER_3 (signal):             1 wallet buying = add to watchlist with boost

Settings (config/settings.py or .env):
  WALLET_MONITOR_ENABLED        = True
  WALLET_MONITOR_POLL_INTERVAL  = 30       # seconds between polls
  WALLET_MONITOR_MIN_BUY_USD    = 500      # ignore buys < $500
  WALLET_MONITOR_MAX_BUY_AGE    = 120      # ignore txs older than 2 min
  WALLET_MONITOR_TIER1_COUNT    = 3        # wallets needed for Tier 1
  WALLET_MONITOR_TIER2_COUNT    = 2        # wallets needed for Tier 2
  WALLET_MONITOR_COPY_SIZE_PCT  = 0.5      # copy 50% of alpha wallet's buy size
  WALLET_MONITOR_MAX_COPY_USD   = 500      # cap copy trade at $500
  ALPHA_WALLETS_EVM             = []       # override SMART_MONEY_WALLETS
  ALPHA_WALLETS_SOLANA          = []       # Solana alpha wallets
"""

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional, Callable

import requests

from config import settings

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────
ENABLED = getattr(settings, "WALLET_MONITOR_ENABLED", True)
POLL_INTERVAL = int(getattr(settings, "WALLET_MONITOR_POLL_INTERVAL", 30))
# ── Quality Gates — raised to prevent garbage trades ──────────────────────────
# MIN_BUY_USD: only copy alpha wallets making meaningful buys ($500+)
# A $50 alpha buy is noise; a $500+ buy is conviction.
MIN_BUY_USD = float(getattr(settings, "WALLET_MONITOR_MIN_BUY_USD", 500))
MAX_BUY_AGE_SECONDS = int(getattr(settings, "WALLET_MONITOR_MAX_BUY_AGE", 120))  # 2 min max age — stale = miss
# TIER counts: require 2 wallets for Tier2 (not 1 — single wallet is noise)
TIER1_COUNT = int(getattr(settings, "WALLET_MONITOR_TIER1_COUNT", 3))  # 3+ wallets = immediate execute
TIER2_COUNT = int(getattr(settings, "WALLET_MONITOR_TIER2_COUNT", 2))  # 2 wallets = express lane
COPY_SIZE_PCT = float(getattr(settings, "WALLET_MONITOR_COPY_SIZE_PCT", 0.05))   # 5% of OUR wallet balance per copy
MAX_COPY_USD = float(getattr(settings, "WALLET_MONITOR_MAX_COPY_USD", 250))      # cap at $250 per copy trade
# DEFAULT_COPY_USD=0: if Streams gives no buy_value_usd, DO NOT trade.
# A $0 unknown signal fires garbage $25 trades — better to miss than to bleed.
DEFAULT_COPY_USD = float(getattr(settings, "WALLET_MONITOR_DEFAULT_COPY_USD", 0))

# Tokens to NEVER copy-trade (stablecoins, wrapped natives, common bridging tokens)
IGNORED_SYMBOLS = {
    "USDT", "USDC", "USDC.E", "DAI", "BUSD", "TUSD", "FRAX", "LUSD", "PYUSD",
    "USDP", "GUSD", "SUSD", "MIM", "EUSD", "USDD", "FDUSD", "USDBC",
    "WETH", "WBTC", "WBNB", "WMATIC", "WAVAX", "WFTM", "WSOL",
    "STETH", "WSTETH", "RETH", "CBETH", "SETH2",  # Liquid staking derivatives
}
IGNORED_ADDRESSES = {
    "0xdac17f958d2ee523a2206206994597c13d831ec7",  # USDT
    "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",  # USDC
    "0x6b175474e89094c44da98b954eedeac495271d0f",  # DAI
    "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",  # WETH
    "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599",  # WBTC
    "0xae7ab96520de3a18e5e111b5eaab095312d7fe84",  # stETH
    "0x7f39c581f595b53c5cb19bd0b3f8da6c935e2ca0",  # wstETH
}

# Moralis API key (required for EVM wallet monitoring)
MORALIS_API_KEY = getattr(settings, "MORALIS_API_KEY", "") or os.getenv("MORALIS_API_KEY", "")
HELIUS_API_KEY = getattr(settings, "BUNDLE_HELIUS_API_KEY", "") or os.getenv("HELIUS_API_KEY", "")

# Alpha wallet lists — override with your own curated wallets
# EVM: pulled from settings.SMART_MONEY_WALLETS by default
_ALPHA_WALLETS_EVM: list[str] = (
    getattr(settings, "ALPHA_WALLETS_EVM", None)
    or getattr(settings, "SMART_MONEY_WALLETS", [])
)

# Solana alpha wallets — must be configured separately
_ALPHA_WALLETS_SOLANA: list[str] = getattr(settings, "ALPHA_WALLETS_SOLANA", [])

# ─────────────────────────────────────────────────────────────────────────────
# Dynamic Sniper Wallet Loading (from sniper_discovery.py)
# Merges auto-discovered high-PnL wallets into the live tracking pool
# ─────────────────────────────────────────────────────────────────────────────
_SNIPER_RELOAD_INTERVAL = 300  # Reload discovered snipers every 5 minutes
_last_sniper_reload: float = 0.0


def _load_discovered_snipers() -> tuple[list[str], list[str]]:
    """
    Load auto-discovered sniper wallets from sniper_discovery.py output.
    Returns (evm_addresses, solana_addresses) of NEW wallets not already tracked.
    """
    global _last_sniper_reload
    now = time.monotonic()
    if now - _last_sniper_reload < _SNIPER_RELOAD_INTERVAL:
        return [], []
    _last_sniper_reload = now
    try:
        from core.sniper_discovery import get_active_sniper_addresses
        addrs = get_active_sniper_addresses()
        evm = [a.lower() for a in addrs.get("evm", []) if a]
        sol = [a for a in addrs.get("solana", []) if a]
        if evm or sol:
            logger.info(
                f"WalletMonitor: Loaded {len(evm)} EVM + {len(sol)} Solana "
                f"discovered snipers into tracking pool"
            )
        return evm, sol
    except Exception as e:
        logger.debug(f"WalletMonitor: Could not load discovered snipers: {e}")
        return [], []

# ─────────────────────────────────────────────────────────────────────────────
# Top Sniper Wallet Detection (for tier-gate bypass)
# Discovered snipers from sniper_discovery.py get Tier 3 pass-through
# ─────────────────────────────────────────────────────────────────────────────
_top_sniper_addresses: set[str] = set()
_top_sniper_last_load: float = 0.0
_TOP_SNIPER_RELOAD_S = 300  # Refresh every 5 minutes


def _is_top_sniper_wallet(address: str) -> bool:
    """
    Check if a wallet is in the active discovered sniper pool.
    These wallets get Tier 3 pass-through (single-wallet polling signals
    are treated as high-conviction because the discovery engine already
    validated their profitability).
    """
    global _top_sniper_addresses, _top_sniper_last_load
    now = time.monotonic()
    if now - _top_sniper_last_load > _TOP_SNIPER_RELOAD_S:
        try:
            from core.sniper_discovery import get_active_sniper_addresses
            addrs = get_active_sniper_addresses()
            _top_sniper_addresses = set(a.lower() for a in addrs.get("solana", []))
            _top_sniper_addresses.update(a.lower() for a in addrs.get("evm", []))
            _top_sniper_last_load = now
            if _top_sniper_addresses:
                logger.debug(
                    f"Top sniper cache refreshed: {len(_top_sniper_addresses)} wallets"
                )
        except Exception:
            pass
    return address.lower() in _top_sniper_addresses


# Moralis API base
_MORALIS_BASE = "https://deep-index.moralis.io/api/v2.2"
_HELIUS_RPC = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}" if HELIUS_API_KEY else "https://api.mainnet-beta.solana.com"

# Chain ID map for Moralis
_MORALIS_CHAIN_IDS = {
    "ethereum": "0x1",
    "base": "0x2105",
    "arbitrum": "0xa4b1",
    "polygon": "0x89",
    "bsc": "0x38",
}


# ─────────────────────────────────────────────────────────────────────────────
# Data structures
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AlphaSignal:
    """A detected buy transaction from an alpha wallet."""
    wallet_address: str
    token_address: str
    token_symbol: str
    chain: str
    buy_value_usd: float
    tx_hash: str
    timestamp: datetime
    # Enriched fields (filled after initial detection)
    token_name: str = ""
    liquidity_usd: float = 0.0
    volume_24h: float = 0.0
    price_usd: float = 0.0
    # Signal aggregation
    confirming_wallets: list[str] = field(default_factory=list)
    tier: int = 3  # 1=immediate, 2=express, 3=watchlist
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    candidate_built_at: Optional[datetime] = None
    risk_passed_at: Optional[datetime] = None
    broadcasted_at: Optional[datetime] = None
    source: str = "polling"

    @property
    def conviction_score(self) -> float:
        """Score 0–100 based on number of confirming wallets and buy size."""
        wallet_score = min(100, len(self.confirming_wallets) * 33.3)
        size_score = min(100, (self.buy_value_usd / MAX_COPY_USD) * 100)
        return round((wallet_score * 0.7) + (size_score * 0.3), 1)


@dataclass
class WalletMonitorState:
    """Persistent state for the wallet monitor daemon."""
    # Last seen transaction hash per wallet
    last_tx: dict[str, str] = field(default_factory=dict)
    # Last poll timestamp per wallet
    last_poll: dict[str, float] = field(default_factory=dict)
    # Active signals: token_address → AlphaSignal
    active_signals: dict[str, AlphaSignal] = field(default_factory=dict)
    # Processed tx hashes (dedup)
    processed_txs: set[str] = field(default_factory=set)
    processed_keys: set[str] = field(default_factory=set)  # tx_hash:token:wallet
    # Stats
    total_signals_detected: int = 0
    total_copy_trades_executed: int = 0


# ─────────────────────────────────────────────────────────────────────────────
# EVM Transaction Fetching (Moralis)
# ─────────────────────────────────────────────────────────────────────────────

def _get_evm_recent_swaps(
    wallet_address: str,
    chain: str,
    since_seconds: int = MAX_BUY_AGE_SECONDS,
) -> list[dict]:
    """
    Fetch recent DEX swap transactions for an EVM wallet via Moralis.
    Returns only BUY transactions (token received in exchange for ETH/stables).
    """
    if not MORALIS_API_KEY:
        return []

    chain_id = _MORALIS_CHAIN_IDS.get(chain)
    if not chain_id:
        return []

    try:
        # Use Moralis wallet token swaps endpoint
        url = f"{_MORALIS_BASE}/wallets/{wallet_address}/swaps"
        params = {
            "chain": chain_id,
            "limit": 10,
            "order": "DESC",
        }
        headers = {"X-API-Key": MORALIS_API_KEY, "Accept": "application/json"}
        resp = requests.get(url, params=params, headers=headers, timeout=10)

        if resp.status_code == 404:
            # Fallback: use token transfers endpoint
            url = f"{_MORALIS_BASE}/{wallet_address}/erc20/transfers"
            params = {"chain": chain_id, "limit": 20, "order": "DESC"}
            resp = requests.get(url, params=params, headers=headers, timeout=10)

        if resp.status_code != 200:
            logger.debug(f"Moralis swap fetch failed for {wallet_address[:10]}...: HTTP {resp.status_code}")
            return []

        data = resp.json()
        swaps = data.get("result", []) if isinstance(data, dict) else data
        if not swaps:
            return []

        # Filter to recent buys
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=since_seconds)
        recent_buys = []
        for swap in swaps:
            # Parse timestamp
            try:
                ts_str = swap.get("block_timestamp") or swap.get("transaction_timestamp", "")
                if ts_str:
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    if ts < cutoff:
                        continue
            except Exception:
                continue

            # Determine if this is a buy (token received, not sent)
            # In Moralis swap format: tokenIn = what was spent, tokenOut = what was received
            token_in = swap.get("tokenIn", {}) or {}
            token_out = swap.get("tokenOut", {}) or {}

            # Skip stable-to-stable swaps
            stable_symbols = {"USDC", "USDT", "DAI", "WETH", "ETH", "WBNB", "BNB", "MATIC"}
            in_symbol = (token_in.get("symbol") or "").upper()
            out_symbol = (token_out.get("symbol") or "").upper()

            if out_symbol in stable_symbols:
                continue  # This is a sell, not a buy

            if not token_out.get("address"):
                continue

            # Estimate buy value in USD
            # Primary: use Moralis-provided usdValue
            buy_value = float(swap.get("usdValue") or swap.get("value_usd") or 0)

            # Fallback: derive from tokenIn (what was spent) — Moralis often returns
            # usdValue=0 for new/micro-cap tokens even though the trade was real.
            if buy_value == 0:
                try:
                    # tokenIn = the token spent by the alpha wallet (e.g. USDC or ETH)
                    ti_price = float(token_in.get("usdPrice") or token_in.get("price_usd") or 0)
                    ti_amount = float(
                        token_in.get("amount") or
                        token_in.get("value") or
                        token_in.get("amount_decimal") or 0
                    )
                    if ti_price > 0 and ti_amount > 0:
                        buy_value = ti_price * ti_amount
                except Exception:
                    pass

            # Still zero? Try reading usd from tokenOut value (some endpoints)
            if buy_value == 0:
                try:
                    to_price = float(token_out.get("usdPrice") or token_out.get("price_usd") or 0)
                    to_amount = float(
                        token_out.get("amount") or
                        token_out.get("value") or
                        token_out.get("amount_decimal") or 0
                    )
                    if to_price > 0 and to_amount > 0:
                        buy_value = to_price * to_amount
                except Exception:
                    pass

            if buy_value < MIN_BUY_USD:
                continue

            recent_buys.append({
                "token_address": token_out.get("address", "").lower(),
                "token_symbol": out_symbol or token_out.get("symbol", "UNKNOWN"),
                "token_name": token_out.get("name", ""),
                "buy_value_usd": buy_value,
                "tx_hash": swap.get("transactionHash") or swap.get("transaction_hash", ""),
                "timestamp": ts_str,
                "chain": chain,
            })

        return recent_buys

    except Exception as e:
        logger.debug(f"EVM swap fetch error for {wallet_address[:10]}...: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Solana Transaction Fetching — GMGN Primary, Helius Fallback
# ─────────────────────────────────────────────────────────────────────────────

# Lazy-loaded GMGN client (avoids import overhead when GMGN not configured)
_gmgn_client = None
_gmgn_client_failed: bool = False


def _get_gmgn_client():
    """Return cached GMGNClient instance, or None if not configured/fails."""
    global _gmgn_client, _gmgn_client_failed
    if _gmgn_client_failed:
        return None
    if _gmgn_client is not None:
        return _gmgn_client
    try:
        from core.gmgn_client import GMGNClient
        _gmgn_client = GMGNClient()
        logger.info("WalletMonitor: GMGN client initialized — using GMGN for Solana polling")
        return _gmgn_client
    except Exception as e:
        _gmgn_client_failed = True
        logger.warning(f"WalletMonitor: GMGN client unavailable, falling back to Helius: {e}")
        return None


def _get_solana_recent_swaps_gmgn(
    wallet_address: str,
    since_seconds: int = MAX_BUY_AGE_SECONDS,
) -> list[dict]:
    """
    Fetch recent Solana DEX buys via GMGNClient.get_wallet_activity().

    GMGN advantages over raw Helius RPC:
    - Returns token symbol/name directly (no separate enrichment needed)
    - Returns USD value per swap (from GMGN's pricing oracle)
    - Returns DEX name, pair address, and direction (buy/sell) pre-parsed
    - Respects the 3 Smart Money wallets audited with $500K+ proven PnL
    """
    client = _get_gmgn_client()
    if not client:
        return []

    cutoff_ts = time.time() - since_seconds
    recent_buys = []

    try:
        activity = client.get_wallet_activity(wallet_address, limit=20)
        for tx in activity:
            # GMGN activity items: {timestamp, token_address, token_symbol,
            #   token_name, side, amount, price_usd, realized_profit, tx_hash}
            side = str(tx.get("side", "")).lower()
            if side not in ("buy", "1", "long"):
                continue  # Only copy buys

            ts_raw = tx.get("timestamp") or tx.get("block_time") or 0
            # ts_raw may be ISO string or unix int
            if isinstance(ts_raw, str):
                try:
                    from datetime import datetime as _dt
                    ts_unix = _dt.fromisoformat(ts_raw.replace("Z", "+00:00")).timestamp()
                except Exception:
                    ts_unix = 0.0
            else:
                ts_unix = float(ts_raw or 0)

            if ts_unix and ts_unix < cutoff_ts:
                continue  # Too old

            token_addr = tx.get("token_address", "") or tx.get("token", "")
            if not token_addr:
                continue

            # USD value: from GMGN price oracle (much more accurate than Helius 0.0)
            amount = float(tx.get("amount") or 0)
            price_usd = float(tx.get("price_usd") or 0)
            buy_usd = float(tx.get("cost_usd") or tx.get("value_usd") or 0)
            if buy_usd == 0 and amount and price_usd:
                buy_usd = amount * price_usd

            ts_iso = (
                datetime.fromtimestamp(ts_unix, tz=timezone.utc).isoformat()
                if ts_unix else datetime.now(tz=timezone.utc).isoformat()
            )

            recent_buys.append({
                "token_address": token_addr,
                "token_symbol": tx.get("token_symbol") or tx.get("symbol") or "UNKNOWN",
                "token_name": tx.get("token_name") or tx.get("name") or "",
                "buy_value_usd": buy_usd,
                "tx_hash": tx.get("tx_hash") or tx.get("signature") or "",
                "timestamp": ts_iso,
                "chain": "solana",
                "source": "gmgn",
            })

        if recent_buys:
            logger.info(
                f"GMGN: {len(recent_buys)} recent buy(s) for {wallet_address[:8]}..."
            )
        return recent_buys

    except Exception as e:
        logger.debug(f"GMGN Solana swap fetch error for {wallet_address[:8]}...: {e}")
        return []


def _get_solana_recent_swaps_helius(
    wallet_address: str,
    since_seconds: int = MAX_BUY_AGE_SECONDS,
) -> list[dict]:
    """
    Fallback: Fetch recent Solana DEX swap transactions via raw Helius RPC.
    Used when GMGN client is not available or fails.
    Note: buy_value_usd will be 0.0 — enriched via DexScreener later.
    """
    if not HELIUS_API_KEY:
        return []

    try:
        # Step 1: Get recent signatures
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getSignaturesForAddress",
            "params": [
                wallet_address,
                {"limit": 20, "commitment": "confirmed"},
            ],
        }
        resp = requests.post(_HELIUS_RPC, json=payload, timeout=10)
        sigs_data = resp.json()
        signatures = sigs_data.get("result", [])
        if not signatures:
            return []

        cutoff_ts = time.time() - since_seconds
        recent_buys = []

        for sig_info in signatures[:10]:  # Check last 10 txs max
            block_time = sig_info.get("blockTime", 0) or 0
            if block_time < cutoff_ts:
                break  # Signatures are sorted newest-first

            sig = sig_info.get("signature", "")
            if not sig:
                continue

            try:
                tx_payload = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "getTransaction",
                    "params": [
                        sig,
                        {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0},
                    ],
                }
                tx_resp = requests.post(_HELIUS_RPC, json=tx_payload, timeout=10)
                tx_data = tx_resp.json().get("result")
                if not tx_data:
                    continue

                pre_balances = tx_data.get("meta", {}).get("preTokenBalances", [])
                post_balances = tx_data.get("meta", {}).get("postTokenBalances", [])

                pre_map = {
                    b["mint"]: float(b.get("uiTokenAmount", {}).get("uiAmount") or 0)
                    for b in pre_balances
                    if b.get("owner") == wallet_address
                }
                for post_bal in post_balances:
                    if post_bal.get("owner") != wallet_address:
                        continue
                    mint = post_bal.get("mint", "")
                    post_amount = float(post_bal.get("uiTokenAmount", {}).get("uiAmount") or 0)
                    pre_amount = pre_map.get(mint, 0)

                    if post_amount <= pre_amount:
                        continue  # Not a buy

                    recent_buys.append({
                        "token_address": mint,
                        "token_symbol": "UNKNOWN",
                        "token_name": "",
                        "buy_value_usd": 0.0,  # Enriched via DexScreener
                        "tx_hash": sig,
                        "timestamp": datetime.fromtimestamp(block_time, tz=timezone.utc).isoformat(),
                        "chain": "solana",
                        "source": "helius",
                    })

            except Exception as e:
                logger.debug(f"Helius tx parse error for {sig[:8]}...: {e}")
                continue

        return recent_buys

    except Exception as e:
        logger.debug(f"Helius Solana swap fetch error for {wallet_address[:8]}...: {e}")
        return []


def _get_solana_recent_swaps(
    wallet_address: str,
    since_seconds: int = MAX_BUY_AGE_SECONDS,
) -> list[dict]:
    """
    Public entry point for Solana swap detection.
    Strategy: GMGN first (rich data + USD values), Helius fallback (raw RPC).
    """
    # Try GMGN first — returns richer data with USD values and token metadata
    gmgn_results = _get_solana_recent_swaps_gmgn(wallet_address, since_seconds)
    if gmgn_results:
        return gmgn_results

    # Fall back to Helius raw RPC
    return _get_solana_recent_swaps_helius(wallet_address, since_seconds)


# ─────────────────────────────────────────────────────────────────────────────
# Signal Enrichment
# ─────────────────────────────────────────────────────────────────────────────

def _enrich_signal(signal: AlphaSignal) -> AlphaSignal:
    """
    Enrich an AlphaSignal with current market data from DexScreener.
    Fills in liquidity, volume, price, and symbol.
    """
    try:
        from data.providers.dexscreener import get_token_pairs
        pairs = get_token_pairs(signal.token_address) or []
        if pairs:
            pair = pairs[0]
            signal.liquidity_usd = float(pair.get("liquidity", {}).get("usd", 0) or 0)
            signal.volume_24h = float(pair.get("volume", {}).get("h24", 0) or 0)
            signal.price_usd = float(pair.get("priceUsd", 0) or 0)
            base_token = pair.get("baseToken", {})
            if signal.token_symbol == "UNKNOWN":
                signal.token_symbol = base_token.get("symbol", "UNKNOWN")
            if not signal.token_name:
                signal.token_name = base_token.get("name", "")
    except Exception as e:
        logger.debug(f"Signal enrichment failed for {signal.token_address[:10]}...: {e}")
    return signal


# ─────────────────────────────────────────────────────────────────────────────
# Signal Validation (hard gates)
# ─────────────────────────────────────────────────────────────────────────────

def _validate_signal(signal: AlphaSignal) -> tuple[bool, str]:
    """
    Run the signal through hard gates before acting on it.
    Returns (is_valid, reason_if_rejected).
    """
    # Gate 1: Minimum liquidity — alpha wallets trade real tokens; $10k floor
    # ($25k was blocking confirmed signals like BLUR with $11k liq)
    if signal.liquidity_usd > 0 and signal.liquidity_usd < 10_000:
        return False, f"Liquidity too low: ${signal.liquidity_usd:,.0f} < $10k"

    # Gate 2: Bundle detection
    try:
        from core.bundle_detector import check_bundle
        bundle = check_bundle(signal.token_address, signal.chain)
        if bundle.is_bundled:
            return False, f"Bundle detected: {bundle.reject_reason}"
    except Exception:
        pass  # Don't block on bundle detection errors

    # Gate 3: Solana age gate (2h minimum)
    if signal.chain == "solana":
        try:
            ts = datetime.fromisoformat(signal.timestamp.isoformat())
            # We don't have token age here — skip this gate for copy trades
            # (alpha wallet already validated the token)
            pass
        except Exception:
            pass

    return True, ""


# ─────────────────────────────────────────────────────────────────────────────
# Copy Trade Execution
# ─────────────────────────────────────────────────────────────────────────────

def _execute_copy_trade(signal: AlphaSignal, on_trade_callback: Optional[Callable] = None) -> bool:
    """
    Execute a copy trade based on an alpha wallet signal.

    Sizing rules:
      1. alpha_buy_usd must be known (> 0) — no speculative $25 defaults
      2. copy_size = min(our_wallet_balance × COPY_SIZE_PCT, MAX_COPY_USD)
      3. alpha buy must exceed MIN_BUY_USD ($500) — small buys are noise

    Args:
        signal: The enriched AlphaSignal to copy
        on_trade_callback: Optional callback(signal) called after execution

    Returns:
        True if trade was submitted, False otherwise
    """
    # ── Gate 1: Source logging only — no hard block on buy_value_usd=0 ─────────
    # Moralis Streams AND polling both frequently return buy_value_usd=0.
    # We size our copy off OUR wallet balance in Gate 3, not the alpha's buy size.
    # Gate 2 below enforces conviction: if USD IS known, it must be ≥ MIN_BUY_USD.
    is_streams = "streams" in (signal.source or "")

    # ── Gate 2: Alpha buy must be a meaningful position (only when USD is known) ─
    # If buy_value_usd is 0 (Moralis didn't return USD), skip this gate and
    # let Gate 3 size the trade off our own wallet balance.
    if signal.buy_value_usd > 0 and signal.buy_value_usd < MIN_BUY_USD:
        logger.info(
            f"⛔ Copy trade skipped: {signal.token_symbol} [{signal.chain}] — "
            f"alpha buy ${signal.buy_value_usd:.0f} < min ${MIN_BUY_USD:.0f} (noise filter)"
        )
        return False

    # ── Gate 3: Size based on OUR wallet balance, not alpha's ────────────────
    # Use wallet_router to get current balance of our primary wallet on this chain
    try:
        from core.wallet_router import get_native_balance, get_native_price_usd
        from config.wallets import WALLETS
        from config.chains import CHAINS
        chain_cfg = CHAINS.get(signal.chain)
        primary = WALLETS.get("primary")
        if chain_cfg and primary:
            addr = primary.solana_address if chain_cfg.is_solana else primary.address
            bal = get_native_balance(addr, signal.chain)
            price = get_native_price_usd(chain_cfg.native_token)
            wallet_balance_usd = bal * price
            if wallet_balance_usd < 10:
                logger.warning(
                    f"⛔ Copy trade skipped: {signal.token_symbol} — "
                    f"primary wallet balance ${wallet_balance_usd:.2f} too low"
                )
                return False
            # Size = 5% of our balance, capped at MAX_COPY_USD
            copy_size_usd = min(wallet_balance_usd * COPY_SIZE_PCT, MAX_COPY_USD)
        else:
            # Fallback: 5% of alpha buy, capped
            copy_size_usd = min(signal.buy_value_usd * COPY_SIZE_PCT, MAX_COPY_USD)
    except Exception as e:
        logger.warning(f"Balance fetch failed for copy sizing: {e} — using conservative fallback")
        copy_size_usd = min(signal.buy_value_usd * 0.03, MAX_COPY_USD)  # 3% of alpha buy as safe fallback

    if copy_size_usd < 10:
        logger.info(f"⛔ Copy trade too small: ${copy_size_usd:.2f} < $10 minimum — skipping")
        return False

    logger.info(
        f"🔥 COPY TRADE: {signal.token_symbol} [{signal.chain}] | "
        f"Tier {signal.tier} | {len(signal.confirming_wallets)} alpha wallets | "
        f"copy_size=${copy_size_usd:.0f} | "
        f"alpha_buy=${signal.buy_value_usd:.0f}"
    )

    try:
        from data.models import Token, GemCandidate
        from config import settings as cfg

        # ── Route through full gem scanner pipeline (score >= 65 to execute) ──
        # User requirement: "score it through our gem scanner pipeline and
        # auto-execute if it scores 65+." Instead of bypassing the scanner
        # with express_lane=True, we run the real 7-layer validation.
        gem_scanner_score: Optional[float] = None
        gem_scanner_candidate: Optional[GemCandidate] = None
        try:
            from scanner.gem_scanner import GemScanner
            from data.providers.dexscreener import get_token_pairs, extract_gem_signals

            # Fetch real market data for the token from DexScreener
            pairs = get_token_pairs(signal.token_address) or []
            if pairs:
                signals = extract_gem_signals(pairs[0])
                scanner = GemScanner()
                token_obj = scanner._signals_to_token(signals, signal.chain)
                if token_obj:
                    gem_scanner_candidate = scanner._score_token(token_obj, is_boosted=False)
                    if gem_scanner_candidate:
                        gem_scanner_score = gem_scanner_candidate.gem_score
                        logger.info(
                            f"📊 Gem Scanner score for {signal.token_symbol}: "
                            f"{gem_scanner_score:.1f}"
                        )
        except Exception as scan_err:
            logger.warning(
                f"Gem scanner routing skipped for {signal.token_symbol}: {scan_err} "
                f"— falling back to conviction-based scoring"
            )

        # ── Gate: Gem score must be >= 65 to proceed ─────────────────────────
        MIN_COPY_GEM_SCORE = float(getattr(cfg, "MIN_GEM_SCORE", 65.0))
        if gem_scanner_score is not None and gem_scanner_score < MIN_COPY_GEM_SCORE:
            logger.info(
                f"⛔ Copy trade rejected by gem scanner: {signal.token_symbol} "
                f"[{signal.chain}] — score={gem_scanner_score:.1f} < {MIN_COPY_GEM_SCORE:.0f}"
            )
            return False

        # ── Build the GemCandidate for execution ─────────────────────────────
        # Construct a minimal Token object from signal data
        token = Token(
            address=signal.token_address,
            symbol=signal.token_symbol,
            name=signal.token_name,
            chain=signal.chain,
            price_usd=signal.price_usd,
            volume_24h=signal.volume_24h,
            liquidity_usd=signal.liquidity_usd,
        )

        candidate = GemCandidate(token=token)
        # Use real gem scanner score if available, otherwise conviction-based
        if gem_scanner_score is not None:
            candidate.gem_score = gem_scanner_score
        else:
            candidate.gem_score = min(100.0, 70.0 + signal.conviction_score * 0.3)
        candidate.smart_money_score = 100.0
        candidate.is_copy_trade = True
        candidate.copy_trade_tier = signal.tier
        candidate.copy_trade_wallets = signal.confirming_wallets
        candidate.copy_trade_size_usd = copy_size_usd
        # Express lane: bypass TA/signal-engine gate in main.py
        # The gem scanner already validated the token quality;
        # express_lane ensures RSI/MACD don't kill a confirmed alpha signal.
        candidate.express_lane = True

        # Inject into express lane via callback
        if on_trade_callback:
            on_trade_callback(candidate, signal)
            return True

        # Fallback: log the signal for manual review
        logger.info(
            f"📋 Copy trade candidate queued: {signal.token_symbol} "
            f"score={candidate.gem_score:.1f} | "
            f"size=${copy_size_usd:.0f} | "
            f"wallets={signal.confirming_wallets}"
        )
        return True

    except Exception as e:
        logger.error(f"Copy trade execution failed for {signal.token_symbol}: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Core Monitor Loop
# ─────────────────────────────────────────────────────────────────────────────

class WalletMonitor:
    """
    Proactive smart money copy-trading daemon.

    Usage:
        monitor = WalletMonitor(on_signal_callback=my_handler)
        monitor.start()   # Starts background thread
        monitor.stop()    # Graceful shutdown
    """

    def __init__(self, on_signal_callback: Optional[Callable] = None):
        """
        Args:
            on_signal_callback: Called with (GemCandidate, AlphaSignal) when
                                 a Tier 1 or Tier 2 signal is detected.
                                 If None, signals are logged but not executed.
        """
        self.on_signal = on_signal_callback
        self.state = WalletMonitorState()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

        # Polling interval — can be adjusted at runtime via activate_hybrid_mode()
        self._poll_interval = POLL_INTERVAL
        self._streams_active = False  # True when Moralis Streams is providing primary signals

        # Build full wallet list
        self._evm_wallets = [w.lower() for w in _ALPHA_WALLETS_EVM if w]
        self._solana_wallets = [w for w in _ALPHA_WALLETS_SOLANA if w]

        logger.info(
            f"WalletMonitor initialized: "
            f"{len(self._evm_wallets)} EVM wallets | "
            f"{len(self._solana_wallets)} Solana wallets | "
            f"poll={self._poll_interval}s | "
            f"min_buy=${MIN_BUY_USD:.0f}"
        )

    def start(self) -> None:
        """Start the monitor daemon in a background thread."""
        if not ENABLED:
            logger.info("WalletMonitor disabled (WALLET_MONITOR_ENABLED=False)")
            return

        if not self._evm_wallets and not self._solana_wallets:
            logger.warning(
                "WalletMonitor: No alpha wallets configured at startup — "
                "daemon will start and attempt to load discovered snipers on first poll tick. "
                "Set ALPHA_WALLETS_EVM / ALPHA_WALLETS_SOL in .env or "
                "use the Sniper Discovery daemon to auto-populate sniper_wallets_active.json."
            )
            # Do NOT return here — discovered snipers are hot-loaded in _poll_all_wallets()
            # and this daemon also needs to be running to receive copy-trade signals.

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._monitor_loop,
            name="WalletMonitor",
            daemon=True,
        )
        self._thread.start()
        logger.info("✅ WalletMonitor daemon started")

    def stop(self) -> None:
        """Signal the daemon to stop and wait for it to finish."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10)
        logger.info("WalletMonitor daemon stopped")

    def get_stats(self) -> dict:
        """Return current monitor statistics."""
        return {
            "evm_wallets": len(self._evm_wallets),
            "solana_wallets": len(self._solana_wallets),
            "active_signals": len(self.state.active_signals),
            "total_signals_detected": self.state.total_signals_detected,
            "total_copy_trades_executed": self.state.total_copy_trades_executed,
            "processed_txs": len(self.state.processed_txs),
            "processed_keys": len(self.state.processed_keys),
            "poll_interval": self._poll_interval,
            "streams_active": self._streams_active,
        }

    def activate_hybrid_mode(self) -> None:
        """
        Switch to hybrid mode: Moralis Streams provides primary detection,
        polling becomes a fallback with extended interval (120s instead of 30s).
        Reduces API usage by ~75% while maintaining coverage.
        """
        fallback_interval = int(getattr(settings, "MORALIS_STREAMS_FALLBACK_POLL_INTERVAL", 120))
        old_interval = self._poll_interval
        self._poll_interval = fallback_interval
        self._streams_active = True
        logger.info(
            f"WalletMonitor: 🔄 Hybrid mode ACTIVATED — "
            f"poll interval extended {old_interval}s → {fallback_interval}s "
            f"(Moralis Streams is primary, polling is fallback)"
        )

    def deactivate_hybrid_mode(self) -> None:
        """Revert to full polling mode (e.g. if Streams goes down)."""
        self._poll_interval = POLL_INTERVAL
        self._streams_active = False
        logger.info(
            f"WalletMonitor: 🔄 Hybrid mode DEACTIVATED — "
            f"poll interval restored to {POLL_INTERVAL}s"
        )

    # ── Internal loop ─────────────────────────────────────────────────────────

    def _monitor_loop(self) -> None:
        """Main polling loop — interval adjusts based on Streams hybrid mode."""
        logger.info(f"WalletMonitor loop started (interval={self._poll_interval}s)")

        while not self._stop_event.is_set():
            try:
                self._poll_all_wallets()
                self._process_signals()
                self._cleanup_stale_signals()
            except Exception as e:
                logger.error(f"WalletMonitor loop error: {e}", exc_info=True)

            # Sleep in small increments to allow clean shutdown
            # Uses instance-level interval (may be extended in hybrid mode)
            for _ in range(self._poll_interval):
                if self._stop_event.is_set():
                    break
                time.sleep(1)

    def _poll_all_wallets(self) -> None:
        """Poll all alpha wallets for new transactions."""
        # Dynamically merge newly discovered sniper wallets into tracking pool
        new_evm, new_sol = _load_discovered_snipers()
        for addr in new_evm:
            if addr not in self._evm_wallets:
                self._evm_wallets.append(addr)
        for addr in new_sol:
            if addr not in self._solana_wallets:
                self._solana_wallets.append(addr)

        # EVM wallets — poll each chain
        evm_chains = [c for c in ["ethereum", "base", "arbitrum", "polygon", "bsc"]
                      if c in getattr(settings, "ACTIVE_CHAINS", [])]

        for wallet in self._evm_wallets:
            for chain in evm_chains:
                try:
                    swaps = _get_evm_recent_swaps(wallet, chain)
                    for swap in swaps:
                        self._process_swap(wallet, swap)
                except Exception as e:
                    logger.debug(f"EVM poll error {wallet[:8]}... on {chain}: {e}")

        # Solana wallets
        for wallet in self._solana_wallets:
            try:
                swaps = _get_solana_recent_swaps(wallet)
                for swap in swaps:
                    self._process_swap(wallet, swap)
            except Exception as e:
                logger.debug(f"Solana poll error {wallet[:8]}...: {e}")

    def _process_swap(self, wallet_address: str, swap: dict) -> None:
        """Process a single swap transaction from an alpha wallet."""
        tx_hash = swap.get("tx_hash", "")
        token_address = swap.get("token_address", "").lower()
        token_symbol = swap.get("token_symbol", "").upper()
        if not tx_hash or not token_address:
            return

        # Skip stablecoins, wrapped tokens, and common bridging assets
        if token_symbol in IGNORED_SYMBOLS or token_address in IGNORED_ADDRESSES:
            return
        idem_key = f"{tx_hash.lower()}:{token_address}:{wallet_address.lower()}"
        if tx_hash in self.state.processed_txs or idem_key in self.state.processed_keys:
            return

        chain = swap.get("chain", "")
        buy_value_usd = float(swap.get("buy_value_usd", 0))

        with self._lock:
            self.state.processed_txs.add(tx_hash)
            self.state.processed_keys.add(idem_key)

            # Check if we already have a signal for this token
            if token_address in self.state.active_signals:
                existing = self.state.active_signals[token_address]
                if wallet_address not in existing.confirming_wallets:
                    existing.confirming_wallets.append(wallet_address)
                    existing.buy_value_usd = max(existing.buy_value_usd, buy_value_usd)
                    logger.info(
                        f"🔥 Signal confirmed: {existing.token_symbol} [{chain}] | "
                        f"{len(existing.confirming_wallets)} alpha wallets | "
                        f"${existing.buy_value_usd:.0f}"
                    )
            else:
                # New signal
                try:
                    ts = datetime.fromisoformat(
                        swap.get("timestamp", datetime.now(timezone.utc).isoformat())
                        .replace("Z", "+00:00")
                    )
                except Exception:
                    ts = datetime.now(timezone.utc)

                signal = AlphaSignal(
                    wallet_address=wallet_address,
                    token_address=token_address,
                    token_symbol=swap.get("token_symbol", "UNKNOWN"),
                    chain=chain,
                    buy_value_usd=buy_value_usd,
                    tx_hash=tx_hash,
                    timestamp=ts,
                    token_name=swap.get("token_name", ""),
                    confirming_wallets=[wallet_address],
                    source=swap.get("seen_via") or swap.get("source", "polling"),
                )
                self.state.active_signals[token_address] = signal
                self.state.total_signals_detected += 1

                logger.info(
                    f"📡 New alpha signal: {signal.token_symbol} [{chain}] | "
                    f"wallet={wallet_address[:8]}... | "
                    f"buy=${buy_value_usd:.0f} | tx={tx_hash[:8]}..."
                )

    def ingest_external_swap(self, wallet_address: str, swap: dict) -> None:
        """
        Inject a swap from an external source (e.g., Moralis Streams webhook).
        """
        try:
            self._process_swap(wallet_address, swap)
        except Exception as e:
            logger.warning(f"External swap ingest failed for {wallet_address[:10]}...: {e}")

    def _process_signals(self) -> None:
        """Evaluate active signals and execute copy trades for qualifying ones."""
        with self._lock:
            signals_to_process = list(self.state.active_signals.values())

        for signal in signals_to_process:
            wallet_count = len(signal.confirming_wallets)

            # Determine tier
            if wallet_count >= TIER1_COUNT:
                signal.tier = 1
            elif wallet_count >= TIER2_COUNT:
                signal.tier = 2
            else:
                signal.tier = 3

            # Tier gate: Tier 1 & 2 always proceed.
            # Tier 3 (single wallet) proceeds if:
            #   a) It came from Moralis Streams (real-time, on-chain confirmed), OR
            #   b) The wallet is a top-10 discovered sniper (pre-validated profitability)
            # Single-wallet polling signals from unknown wallets are noise — skip them.
            is_streams_signal = "streams" in (signal.source or "")
            is_top_sniper = _is_top_sniper_wallet(signal.wallet_address)
            if signal.tier > 2 and not is_streams_signal and not is_top_sniper:
                continue
            if is_top_sniper and signal.tier > 2:
                logger.info(
                    f"🎯 Top sniper pass-through: {signal.token_symbol} [{signal.chain}] "
                    f"from discovered wallet {signal.wallet_address[:10]}..."
                )

            # Enrich with market data
            signal = _enrich_signal(signal)

            # Validate through hard gates
            is_valid, reject_reason = _validate_signal(signal)
            if not is_valid:
                logger.info(
                    f"⛔ Copy trade rejected: {signal.token_symbol} [{signal.chain}] — "
                    f"{reject_reason}"
                )
                with self._lock:
                    self.state.active_signals.pop(signal.token_address, None)
                continue

            # Execute copy trade
            success = _execute_copy_trade(signal, self.on_signal)
            if success:
                self.state.total_copy_trades_executed += 1
                with self._lock:
                    self.state.active_signals.pop(signal.token_address, None)

    def _cleanup_stale_signals(self) -> None:
        """Remove signals older than MAX_BUY_AGE_SECONDS × 3."""
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=MAX_BUY_AGE_SECONDS * 3)
        with self._lock:
            stale = [
                addr for addr, sig in self.state.active_signals.items()
                if sig.timestamp < cutoff
            ]
            for addr in stale:
                sig = self.state.active_signals.pop(addr)
                logger.debug(f"Stale signal cleaned: {sig.token_symbol} [{sig.chain}]")


# ─────────────────────────────────────────────────────────────────────────────
# Singleton accessor
# ─────────────────────────────────────────────────────────────────────────────

_monitor_instance: Optional[WalletMonitor] = None


def get_monitor(on_signal_callback: Optional[Callable] = None) -> WalletMonitor:
    """Get or create the global WalletMonitor instance."""
    global _monitor_instance
    if _monitor_instance is None:
        _monitor_instance = WalletMonitor(on_signal_callback=on_signal_callback)
    return _monitor_instance


def start_monitor(on_signal_callback: Optional[Callable] = None) -> WalletMonitor:
    """Start the global wallet monitor daemon."""
    monitor = get_monitor(on_signal_callback)
    monitor.start()
    return monitor
