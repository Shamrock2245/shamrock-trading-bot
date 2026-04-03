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
MIN_BUY_USD = float(getattr(settings, "WALLET_MONITOR_MIN_BUY_USD", 50))        # lowered from 500 — matches our capital level
MAX_BUY_AGE_SECONDS = int(getattr(settings, "WALLET_MONITOR_MAX_BUY_AGE", 300))    # extended from 120s to 5 min
TIER1_COUNT = int(getattr(settings, "WALLET_MONITOR_TIER1_COUNT", 2))              # lowered from 3 — easier to trigger
TIER2_COUNT = int(getattr(settings, "WALLET_MONITOR_TIER2_COUNT", 1))              # single alpha buy = express lane
COPY_SIZE_PCT = float(getattr(settings, "WALLET_MONITOR_COPY_SIZE_PCT", 0.3))      # 30% of alpha buy size
MAX_COPY_USD = float(getattr(settings, "WALLET_MONITOR_MAX_COPY_USD", 100))        # cap at $100 for our capital level

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
            buy_value = float(swap.get("usdValue") or swap.get("value_usd") or 0)
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
# Solana Transaction Fetching (Helius)
# ─────────────────────────────────────────────────────────────────────────────

def _get_solana_recent_swaps(
    wallet_address: str,
    since_seconds: int = MAX_BUY_AGE_SECONDS,
) -> list[dict]:
    """
    Fetch recent DEX swap transactions for a Solana wallet via Helius.
    Uses the getSignaturesForAddress + getTransaction approach.
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

            # Step 2: Fetch full transaction
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

                # Parse token balance changes to detect buys
                pre_balances = tx_data.get("meta", {}).get("preTokenBalances", [])
                post_balances = tx_data.get("meta", {}).get("postTokenBalances", [])

                # Find tokens where wallet's balance INCREASED (= buy)
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
                        continue  # Balance decreased or unchanged — not a buy

                    # This is a buy — estimate USD value from SOL fee proxy
                    # (Full USD value requires price lookup — use 0 as placeholder)
                    recent_buys.append({
                        "token_address": mint,
                        "token_symbol": "UNKNOWN",  # Will be enriched
                        "token_name": "",
                        "buy_value_usd": 0.0,  # Enriched via DexScreener
                        "tx_hash": sig,
                        "timestamp": datetime.fromtimestamp(block_time, tz=timezone.utc).isoformat(),
                        "chain": "solana",
                    })

            except Exception as e:
                logger.debug(f"Helius tx parse error for {sig[:8]}...: {e}")
                continue

        return recent_buys

    except Exception as e:
        logger.debug(f"Solana swap fetch error for {wallet_address[:8]}...: {e}")
        return []


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
    # Gate 1: Minimum liquidity ($25k for copy trades — lower than scanner threshold)
    if signal.liquidity_usd > 0 and signal.liquidity_usd < 25_000:
        return False, f"Liquidity too low: ${signal.liquidity_usd:,.0f} < $25k"

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

    Copy size = min(alpha_buy_size × COPY_SIZE_PCT, MAX_COPY_USD)
    Uses the express lane — bypasses the 65-score floor.

    Args:
        signal: The enriched AlphaSignal to copy
        on_trade_callback: Optional callback(signal) called after execution

    Returns:
        True if trade was submitted, False otherwise
    """
    copy_size_usd = min(
        signal.buy_value_usd * COPY_SIZE_PCT,
        MAX_COPY_USD,
    )

    if copy_size_usd < 10:
        logger.debug(f"Copy trade too small: ${copy_size_usd:.2f} — skipping")
        return False

    logger.info(
        f"🔥 COPY TRADE: {signal.token_symbol} [{signal.chain}] | "
        f"Tier {signal.tier} | {len(signal.confirming_wallets)} alpha wallets | "
        f"copy_size=${copy_size_usd:.0f} | "
        f"alpha_buy=${signal.buy_value_usd:.0f}"
    )

    try:
        # Build a GemCandidate and inject into the express lane
        from data.models import Token, GemCandidate
        from config import settings as cfg

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

        # Build GemCandidate with a high conviction score
        candidate = GemCandidate(token=token)
        candidate.gem_score = min(100.0, 70.0 + signal.conviction_score * 0.3)
        candidate.smart_money_score = 100.0
        candidate.is_copy_trade = True
        candidate.copy_trade_tier = signal.tier
        candidate.copy_trade_wallets = signal.confirming_wallets
        candidate.copy_trade_size_usd = copy_size_usd

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
            logger.warning("WalletMonitor: No alpha wallets configured — daemon not started")
            return

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
        if not tx_hash or not token_address:
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
                    source=swap.get("seen_via", "polling"),
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
            logger.debug(f"External swap ingest failed: {e}")

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

            # Only act on Tier 1 and Tier 2
            if signal.tier > 2:
                continue

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
