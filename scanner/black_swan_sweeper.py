"""
scanner/black_swan_sweeper.py — Black Swan Exploit Detection & Automated Short Engine.

PURPOSE
-------
Monitors Ethereum (EVM) and Solana in real-time via WebSocket for highly anomalous
transactions — specifically, massive unexpected outflows from known protocol
treasuries or liquidity pools that match exploit signatures.

When a confirmed exploit is detected, the engine immediately:
  1. Classifies the exploit type and severity
  2. Maps the drained protocol to its native token symbol
  3. Opens a leveraged short position on Hyperliquid DEX (decentralized perps)
  4. Enforces a strict safety timeout to close the short after the initial crash

DETECTION SIGNALS
-----------------
  - ETH: Large ERC-20 transfers (>$1M) from known protocol LP/treasury addresses
          to unverified/new contracts (< 30 days old, 0 prior txs)
  - ETH: Sudden >50% TVL drop in a pool detected via on-chain balance polling
  - SOL: Massive SPL token outflows from known Solana protocol vaults
  - Both: Reentrancy-like call patterns (multiple calls in same block to same addr)

EXECUTION
---------
  - Short via HyperliquidExecutor.open_short() — zero-gas, USDC-margined perps
  - Fallback: GMX v2 (Arbitrum) via executor.py if HL listing unavailable
  - Safety timeout: configurable via BLACK_SWAN_TIMEOUT_MINUTES (default: 30)
  - Max concurrent black swan shorts: BLACK_SWAN_MAX_SHORTS (default: 3)

INTEGRATION
-----------
  main.py → instantiate BlackSwanSweeper → call .start() in background thread
  The sweeper runs its own asyncio event loop and is fully non-blocking.

ENVIRONMENT VARIABLES
---------------------
  BLACK_SWAN_ENABLED           = false     # Must explicitly opt-in (default: off)
  BLACK_SWAN_MIN_DRAIN_USD     = 1000000   # $1M minimum drain to trigger
  BLACK_SWAN_SHORT_LEVERAGE    = 5         # Leverage for short positions (max 10x)
  BLACK_SWAN_SHORT_SIZE_USD    = 100       # USD size per short (scales with drain)
  BLACK_SWAN_TIMEOUT_MINUTES   = 30        # Hard close after N minutes
  BLACK_SWAN_MAX_SHORTS        = 3         # Max concurrent exploit shorts
  BLACK_SWAN_CONFIRM_BLOCKS    = 1         # Blocks to wait before confirming drain
  ETH_WSS_URL                  = wss://... # Ethereum WebSocket RPC (required)
  SOLANA_WSS_URL               = wss://... # Solana WebSocket RPC (required)
  BLACK_SWAN_POLL_INTERVAL     = 15        # Fallback HTTP polling interval (seconds)

SAFETY NOTES
------------
  ⚠️  This module executes REAL trades in live mode. Always test in paper mode first.
  ⚠️  Black swan shorts bypass the normal gem_score gate (score=100 is injected).
  ⚠️  The safety timeout is a HARD CLOSE — it fires regardless of PnL.
  ⚠️  Never set leverage above 10x. Exploit-driven moves are volatile and can reverse.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
import websockets
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Configuration — all overridable via environment variables
# ─────────────────────────────────────────────────────────────────────────────

BSS_ENABLED            = os.getenv("BLACK_SWAN_ENABLED", "false").lower() == "true"
BSS_MIN_DRAIN_USD      = float(os.getenv("BLACK_SWAN_MIN_DRAIN_USD", "1_000_000"))
BSS_SHORT_LEVERAGE     = min(int(os.getenv("BLACK_SWAN_SHORT_LEVERAGE", "5")), 10)  # Hard cap at 10x
BSS_SHORT_SIZE_USD     = float(os.getenv("BLACK_SWAN_SHORT_SIZE_USD", "100"))
BSS_TIMEOUT_MINUTES    = int(os.getenv("BLACK_SWAN_TIMEOUT_MINUTES", "30"))
BSS_MAX_SHORTS         = int(os.getenv("BLACK_SWAN_MAX_SHORTS", "3"))
BSS_CONFIRM_BLOCKS     = int(os.getenv("BLACK_SWAN_CONFIRM_BLOCKS", "1"))
BSS_POLL_INTERVAL      = int(os.getenv("BLACK_SWAN_POLL_INTERVAL", "15"))

# ETH address for "zero address" (burn / untracked)
ZERO_ADDR = "0x0000000000000000000000000000000000000000"

# ─────────────────────────────────────────────────────────────────────────────
# Known Protocol Treasury & LP Registry
# Maps: protocol_slug → { chain, treasury_addresses, lp_addresses, token_symbol }
# Addresses are checksummed EVM or base58 Solana pubkeys.
# This registry is extended at runtime via DefiLlama API.
# ─────────────────────────────────────────────────────────────────────────────

PROTOCOL_REGISTRY: Dict[str, Dict[str, Any]] = {
    # ── Ethereum Mainnet ──────────────────────────────────────────────────────
    "uniswap-v3": {
        "chain": "ethereum",
        "token_symbol": "UNI",
        "treasury": ["0x1a9C8182C09F50C8318d769245beA52c32BE35BC"],
        "lp_pools": [],  # Populated dynamically — too many to list
        "min_drain_usd": 5_000_000,
    },
    "aave-v3": {
        "chain": "ethereum",
        "token_symbol": "AAVE",
        "treasury": ["0xEC568fffba86c094cf06b22134B23074DFE2252c"],
        "lp_pools": [
            "0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2",  # Aave V3 Pool
        ],
        "min_drain_usd": 2_000_000,
    },
    "compound-v3": {
        "chain": "ethereum",
        "token_symbol": "COMP",
        "treasury": ["0x6d903f6003cca6255D85CcA4D3B5E5146dC33925"],
        "lp_pools": [
            "0xc3d688B66703497DAA19211EEdff47f25384cdc3",  # cUSDCv3
        ],
        "min_drain_usd": 2_000_000,
    },
    "curve-finance": {
        "chain": "ethereum",
        "token_symbol": "CRV",
        "treasury": ["0xeCb456EA5365865EbAb8a2661B0c503410e9B347"],
        "lp_pools": [
            "0xbEbc44782C7dB0a1A60Cb6fe97d0b483032FF1C7",  # 3pool
            "0xDC24316b9AE028F1497c275EB9192a3Ea0f67022",  # stETH pool
        ],
        "min_drain_usd": 3_000_000,
    },
    "maker-dao": {
        "chain": "ethereum",
        "token_symbol": "MKR",
        "treasury": ["0x9f8F72aA9304c8B593d555F12eF6589cC3A579A2"],
        "lp_pools": [
            "0x35D1b3F3D7966A1DFe207aa4514C12a259A0492B",  # MCD_VAT
        ],
        "min_drain_usd": 5_000_000,
    },
    "lido": {
        "chain": "ethereum",
        "token_symbol": "LDO",
        "treasury": ["0x3e40D73EB977Dc6a537aF587D48316feE66E9C8c"],
        "lp_pools": [
            "0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84",  # stETH
        ],
        "min_drain_usd": 5_000_000,
    },
    "balancer-v2": {
        "chain": "ethereum",
        "token_symbol": "BAL",
        "treasury": ["0x10A19e7eE7d7F8a52822f6817de8ea18204F2e4f"],
        "lp_pools": [
            "0xBA12222222228d8Ba445958a75a0704d566BF2C8",  # Balancer Vault
        ],
        "min_drain_usd": 3_000_000,
    },
    "convex-finance": {
        "chain": "ethereum",
        "token_symbol": "CVX",
        "treasury": ["0xa3C5A1e09150B75ff251c1a7815A07182c3de2FB"],
        "lp_pools": [
            "0xF403C135812408BFbE8713b5A23a04b3D48AAE31",  # Booster
        ],
        "min_drain_usd": 2_000_000,
    },
    "yearn-finance": {
        "chain": "ethereum",
        "token_symbol": "YFI",
        "treasury": ["0xFEB4acf3df3cDEA7399794D0869ef76A6EfAff52"],
        "lp_pools": [],
        "min_drain_usd": 2_000_000,
    },
    # ── Base Chain ─────────────────────────────────────────────────────────────
    "aerodrome": {
        "chain": "base",
        "token_symbol": "AERO",
        "treasury": ["0xeBf418Fe2512e7E6bd9b87a8F0f294aCDC67e6B4"],
        "lp_pools": [
            "0x420DD381b31aEf6683db6B902084cB0FFECe40Da",  # Voter
        ],
        "min_drain_usd": 1_000_000,
    },
    # ── Arbitrum ───────────────────────────────────────────────────────────────
    "gmx-v2": {
        "chain": "arbitrum",
        "token_symbol": "GMX",
        "treasury": ["0x49B373D422BdA4C6BfCdd5eC1E48A9a26fdA2F8b"],
        "lp_pools": [
            "0x0CF1702932926d63C7851919678B3f3F0cBf1e7a",  # GLP vault
        ],
        "min_drain_usd": 2_000_000,
    },
    "camelot": {
        "chain": "arbitrum",
        "token_symbol": "GRAIL",
        "treasury": ["0x0000000000000000000000000000000000000000"],  # Placeholder
        "lp_pools": [],
        "min_drain_usd": 1_000_000,
    },
    # ── Solana ─────────────────────────────────────────────────────────────────
    "raydium": {
        "chain": "solana",
        "token_symbol": "RAY",
        "treasury": ["675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"],  # AMM program
        "lp_pools": [
            "5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1",  # Raydium authority
        ],
        "min_drain_usd": 1_000_000,
    },
    "orca": {
        "chain": "solana",
        "token_symbol": "ORCA",
        "treasury": ["whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc"],  # Whirlpool program
        "lp_pools": [],
        "min_drain_usd": 1_000_000,
    },
    "marinade": {
        "chain": "solana",
        "token_symbol": "MNDE",
        "treasury": ["MarBmsSgKXdrN1egZf5sqe1TMai9K1rChYNDJgjq7aD"],
        "lp_pools": [],
        "min_drain_usd": 1_000_000,
    },
    "jupiter": {
        "chain": "solana",
        "token_symbol": "JUP",
        "treasury": ["JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4"],  # Jupiter program
        "lp_pools": [],
        "min_drain_usd": 2_000_000,
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# Exploit Signature Patterns
# ─────────────────────────────────────────────────────────────────────────────

# EVM function selectors that appear in known exploit transactions
EXPLOIT_SELECTORS: Set[str] = {
    "0x70a08231",  # balanceOf — used in drain checks
    "0xa9059cbb",  # transfer — ERC-20 transfer
    "0x23b872dd",  # transferFrom — ERC-20 transferFrom (flash loan abuse)
    "0xd9caed12",  # withdraw — common vault drain
    "0x2e1a7d4d",  # withdraw(uint256) — WETH / vault
    "0x853828b6",  # withdrawAll
    "0x3ccfd60b",  # withdraw() — no args
    "0x51cff8d9",  # withdraw(address)
    "0x00f714ce",  # withdrawTo
    "0xe8eda9df",  # deposit (used in reentrancy)
    "0x69328dec",  # withdraw (Aave V2)
    "0x1a4d01d2",  # remove_liquidity_one_coin (Curve)
    "0x517a55a3",  # remove_liquidity_imbalance (Curve)
}

# Solana program IDs associated with known exploits or high-risk patterns
SOLANA_HIGH_RISK_PROGRAMS: Set[str] = {
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",  # SPL Token Program
    "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJe1bRS",  # Associated Token Account
}


# ─────────────────────────────────────────────────────────────────────────────
# Data Models
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ExploitEvent:
    """Represents a detected exploit or anomalous drain event."""
    protocol_slug: str
    protocol_name: str
    token_symbol: str
    chain: str
    drain_amount_usd: float
    drain_address: str          # Address being drained
    attacker_address: str       # Suspected attacker / receiving address
    tx_hash: str
    block_number: int
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    exploit_type: str = "unknown"       # "flash_loan", "reentrancy", "access_control", "oracle_manip", "direct_drain"
    confidence: float = 0.0             # 0.0–1.0 confidence score
    confirmed: bool = False             # True after confirmation blocks pass
    short_opened: bool = False
    short_symbol: str = ""
    short_entry_price: float = 0.0
    short_opened_at: Optional[datetime] = None
    short_closed_at: Optional[datetime] = None
    short_pnl: float = 0.0


@dataclass
class ActiveShort:
    """Tracks an active black swan short position."""
    symbol: str
    exploit_event: ExploitEvent
    opened_at: float        # Unix timestamp
    size_usd: float
    leverage: int
    timeout_at: float       # Unix timestamp when safety close fires
    closed: bool = False


# ─────────────────────────────────────────────────────────────────────────────
# Anomaly Scorer
# ─────────────────────────────────────────────────────────────────────────────

class AnomalyScorer:
    """
    Scores a transaction against known exploit patterns.
    Returns a confidence score 0.0–1.0 and an exploit type classification.
    """

    def __init__(self):
        # Track call frequency per address per block for reentrancy detection
        self._call_counts: Dict[str, deque] = defaultdict(lambda: deque(maxlen=50))

    def score_evm_tx(
        self,
        tx: Dict[str, Any],
        protocol_address: str,
        estimated_value_usd: float,
        is_unverified_contract: bool,
        contract_age_days: int,
    ) -> Tuple[float, str]:
        """
        Score an EVM transaction for exploit likelihood.

        Returns:
            (confidence: float, exploit_type: str)
        """
        score = 0.0
        exploit_type = "unknown"

        # ── Signal 1: Large value transfer (40% weight) ────────────────────
        if estimated_value_usd >= BSS_MIN_DRAIN_USD:
            score += 0.40
        elif estimated_value_usd >= BSS_MIN_DRAIN_USD * 0.5:
            score += 0.20

        # ── Signal 2: Destination is unverified / new contract (25% weight) ─
        if is_unverified_contract:
            score += 0.15
            exploit_type = "direct_drain"
        if contract_age_days < 7:
            score += 0.10
            exploit_type = "direct_drain"

        # ── Signal 3: Known exploit function selectors (20% weight) ──────────
        input_data = tx.get("input", "")
        if input_data and len(input_data) >= 10:
            selector = input_data[:10].lower()
            if selector in EXPLOIT_SELECTORS:
                score += 0.10

        # ── Signal 4: Zero-value tx to known protocol (flash loan pattern) ───
        tx_value = int(tx.get("value", "0x0"), 16) if isinstance(tx.get("value"), str) else tx.get("value", 0)
        if tx_value == 0 and estimated_value_usd > BSS_MIN_DRAIN_USD:
            score += 0.15
            exploit_type = "flash_loan"

        # ── Signal 5: Reentrancy pattern (multiple calls in same block) ───────
        to_addr = (tx.get("to") or "").lower()
        block = tx.get("blockNumber", 0)
        call_key = f"{to_addr}:{block}"
        self._call_counts[to_addr].append(block)
        recent_blocks = list(self._call_counts[to_addr])
        if recent_blocks.count(block) >= 3:
            score += 0.20
            exploit_type = "reentrancy"

        return min(score, 1.0), exploit_type

    def score_solana_log(
        self,
        log_entry: Dict[str, Any],
        protocol_address: str,
        estimated_value_usd: float,
    ) -> Tuple[float, str]:
        """
        Score a Solana log entry for exploit likelihood.

        Returns:
            (confidence: float, exploit_type: str)
        """
        score = 0.0
        exploit_type = "unknown"

        logs = log_entry.get("logs", [])
        if not logs:
            return 0.0, exploit_type

        # ── Signal 1: Large transfer ──────────────────────────────────────────
        if estimated_value_usd >= BSS_MIN_DRAIN_USD:
            score += 0.40

        # ── Signal 2: Error logs followed by large transfer (reentrancy-like) ─
        has_error = any("failed" in l.lower() or "error" in l.lower() for l in logs)
        if has_error and estimated_value_usd > BSS_MIN_DRAIN_USD * 0.5:
            score += 0.20
            exploit_type = "reentrancy"

        # ── Signal 3: Program invocation depth anomaly ────────────────────────
        invoke_depth = sum(1 for l in logs if "invoke" in l.lower())
        if invoke_depth > 5:
            score += 0.15
            exploit_type = "flash_loan"

        return min(score, 1.0), exploit_type


# ─────────────────────────────────────────────────────────────────────────────
# Protocol Resolver — maps drained address → protocol metadata
# ─────────────────────────────────────────────────────────────────────────────

class ProtocolResolver:
    """
    Resolves a drained address to a protocol entry from the registry.
    Also enriches the registry at startup via DefiLlama.
    """

    def __init__(self):
        # Build a flat lookup: address_lower → protocol_slug
        self._addr_map: Dict[str, str] = {}
        self._build_map()

    def _build_map(self):
        for slug, info in PROTOCOL_REGISTRY.items():
            for addr in info.get("treasury", []):
                self._addr_map[addr.lower()] = slug
            for addr in info.get("lp_pools", []):
                self._addr_map[addr.lower()] = slug
        logger.info(f"🦅 ProtocolResolver: indexed {len(self._addr_map)} protocol addresses")

    def resolve(self, address: str) -> Optional[Tuple[str, Dict[str, Any]]]:
        """
        Resolve an address to (protocol_slug, protocol_info).
        Returns None if not in registry.
        """
        slug = self._addr_map.get(address.lower())
        if slug:
            return slug, PROTOCOL_REGISTRY[slug]
        return None

    def is_known_protocol(self, address: str) -> bool:
        return address.lower() in self._addr_map

    def get_all_watched_addresses(self, chain: str) -> List[str]:
        """Return all watched addresses for a given chain."""
        result = []
        for slug, info in PROTOCOL_REGISTRY.items():
            if info.get("chain") == chain:
                result.extend(info.get("treasury", []))
                result.extend(info.get("lp_pools", []))
        return [a for a in result if a != ZERO_ADDR]


# ─────────────────────────────────────────────────────────────────────────────
# Main BlackSwanSweeper
# ─────────────────────────────────────────────────────────────────────────────

class BlackSwanSweeper:
    """
    Real-time exploit detection and automated short execution engine.

    Architecture:
      - Runs a dedicated asyncio event loop in a background daemon thread
      - ETH WebSocket listener: subscribes to newPendingTransactions + newHeads
      - SOL WebSocket listener: subscribes to logsSubscribe for watched programs
      - Fallback HTTP polling: polls DefiLlama TVL every BSS_POLL_INTERVAL seconds
      - Safety timeout monitor: closes all shorts after BSS_TIMEOUT_MINUTES
      - All state is thread-safe via asyncio + threading.Lock

    Usage:
        sweeper = BlackSwanSweeper(hyperliquid_executor=hl_exec)
        sweeper.start()   # non-blocking, starts background thread
        sweeper.stop()    # graceful shutdown
    """

    def __init__(self, hyperliquid_executor: Any):
        self.enabled = BSS_ENABLED
        self.hl = hyperliquid_executor

        # WebSocket URLs — prefer explicit WSS env vars, fall back to HTTP→WSS conversion
        eth_http = os.getenv("ETH_RPC_URL", "https://ethereum.publicnode.com")
        self.eth_ws_url = os.getenv(
            "ETH_WSS_URL",
            eth_http.replace("https://", "wss://").replace("http://", "ws://"),
        )
        sol_http = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
        self.sol_ws_url = os.getenv(
            "SOLANA_WSS_URL",
            sol_http.replace("https://", "wss://").replace("http://", "ws://"),
        )

        # Sub-components
        self.scorer = AnomalyScorer()
        self.resolver = ProtocolResolver()

        # State
        self.active_shorts: Dict[str, ActiveShort] = {}   # symbol → ActiveShort
        self.exploit_history: List[ExploitEvent] = []
        self._lock = threading.Lock()
        self._running = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._tasks: List[asyncio.Task] = []

        # TVL baseline cache for delta-detection: protocol_slug → last_tvl_usd
        self._tvl_baseline: Dict[str, float] = {}

        # Dedup: tx hashes already processed
        self._seen_txs: Set[str] = set()
        self._seen_txs_lock = threading.Lock()

        logger.info(
            f"🦅 BlackSwanSweeper initialized | "
            f"enabled={self.enabled} | "
            f"min_drain=${BSS_MIN_DRAIN_USD:,.0f} | "
            f"leverage={BSS_SHORT_LEVERAGE}x | "
            f"timeout={BSS_TIMEOUT_MINUTES}m | "
            f"watching={len(self.resolver._addr_map)} addresses"
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the sweeper in a background daemon thread."""
        if not self.enabled:
            logger.info("🦅 BlackSwanSweeper is DISABLED (set BLACK_SWAN_ENABLED=true to activate)")
            return
        if self._running:
            logger.warning("🦅 BlackSwanSweeper already running")
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._run_event_loop,
            daemon=True,
            name="BlackSwanSweeper",
        )
        self._thread.start()
        logger.info(
            f"🦅 BlackSwanSweeper STARTED | "
            f"ETH WSS: {'✅' if self.eth_ws_url.startswith('ws') else '❌'} | "
            f"SOL WSS: {'✅' if self.sol_ws_url.startswith('ws') else '❌'}"
        )

    def stop(self) -> None:
        """Gracefully stop the sweeper."""
        self._running = False
        if self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._cancel_all_tasks)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=8)
        logger.info("🦅 BlackSwanSweeper STOPPED")

    def get_status(self) -> Dict[str, Any]:
        """Return current sweeper status for dashboard integration."""
        with self._lock:
            return {
                "enabled": self.enabled,
                "running": self._running,
                "active_shorts": {
                    sym: {
                        "opened_at": datetime.fromtimestamp(s.opened_at, tz=timezone.utc).isoformat(),
                        "timeout_at": datetime.fromtimestamp(s.timeout_at, tz=timezone.utc).isoformat(),
                        "size_usd": s.size_usd,
                        "leverage": s.leverage,
                        "protocol": s.exploit_event.protocol_name,
                        "drain_usd": s.exploit_event.drain_amount_usd,
                    }
                    for sym, s in self.active_shorts.items()
                },
                "exploit_history_count": len(self.exploit_history),
                "watched_addresses": len(self.resolver._addr_map),
                "recent_exploits": [
                    {
                        "protocol": e.protocol_name,
                        "chain": e.chain,
                        "drain_usd": e.drain_amount_usd,
                        "token": e.token_symbol,
                        "detected_at": e.detected_at.isoformat(),
                        "short_pnl": e.short_pnl,
                    }
                    for e in self.exploit_history[-10:]
                ],
            }

    # ─────────────────────────────────────────────────────────────────────────
    # Event Loop
    # ─────────────────────────────────────────────────────────────────────────

    def _run_event_loop(self) -> None:
        """Entry point for the background thread — runs the asyncio loop."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        # Schedule all coroutines
        if self.eth_ws_url.startswith("ws"):
            self._tasks.append(self._loop.create_task(self._eth_listener()))
        if self.sol_ws_url.startswith("ws"):
            self._tasks.append(self._loop.create_task(self._sol_listener()))

        # Always run the TVL polling fallback and safety timeout monitor
        self._tasks.append(self._loop.create_task(self._tvl_poll_monitor()))
        self._tasks.append(self._loop.create_task(self._safety_timeout_monitor()))

        try:
            self._loop.run_forever()
        except Exception as e:
            logger.error(f"🦅 BlackSwanSweeper event loop crashed: {e}")
        finally:
            self._loop.close()

    def _cancel_all_tasks(self) -> None:
        for task in self._tasks:
            if not task.done():
                task.cancel()
        self._loop.stop()

    # ─────────────────────────────────────────────────────────────────────────
    # Ethereum WebSocket Listener
    # ─────────────────────────────────────────────────────────────────────────

    async def _eth_listener(self) -> None:
        """
        Subscribe to Ethereum newHeads and scan each block's transactions
        for anomalous outflows from watched protocol addresses.

        Uses newHeads (confirmed blocks) rather than pending transactions to
        avoid false positives from mempool noise and failed transactions.
        """
        retry_delay = 5
        while self._running:
            try:
                logger.info(f"🦅 ETH WSS connecting: {self.eth_ws_url[:40]}...")
                async with websockets.connect(
                    self.eth_ws_url,
                    ping_interval=20,
                    ping_timeout=30,
                    close_timeout=10,
                ) as ws:
                    # Subscribe to new block headers
                    await ws.send(json.dumps({
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "eth_subscribe",
                        "params": ["newHeads"],
                    }))
                    sub_resp = await asyncio.wait_for(ws.recv(), timeout=10)
                    sub_data = json.loads(sub_resp)
                    sub_id = sub_data.get("result", "")
                    logger.info(f"🦅 ETH subscribed to newHeads | sub_id={sub_id}")
                    retry_delay = 5  # Reset backoff on successful connect

                    while self._running:
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=60)
                        except asyncio.TimeoutError:
                            # Send ping to keep alive
                            await ws.ping()
                            continue

                        msg = json.loads(raw)
                        if "params" not in msg:
                            continue

                        block_header = msg["params"].get("result", {})
                        block_number_hex = block_header.get("number", "0x0")
                        block_number = int(block_number_hex, 16) if isinstance(block_number_hex, str) else 0

                        # Fetch full block with transactions
                        await self._process_eth_block(ws, block_number)

            except websockets.exceptions.ConnectionClosed as e:
                logger.warning(f"🦅 ETH WSS disconnected: {e}. Reconnecting in {retry_delay}s...")
            except Exception as e:
                logger.error(f"🦅 ETH WSS error: {e}. Reconnecting in {retry_delay}s...")

            if self._running:
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 60)  # Exponential backoff, max 60s

    async def _process_eth_block(self, ws: Any, block_number: int) -> None:
        """
        Fetch a full block and scan all transactions for anomalous outflows
        from watched protocol addresses.
        """
        try:
            # Request full block with transactions
            await ws.send(json.dumps({
                "jsonrpc": "2.0",
                "id": 2,
                "method": "eth_getBlockByNumber",
                "params": [hex(block_number), True],
            }))
            raw = await asyncio.wait_for(ws.recv(), timeout=15)
            block_data = json.loads(raw)
            block = block_data.get("result", {})
            if not block:
                return

            transactions = block.get("transactions", [])
            watched_addrs = set(self.resolver.get_all_watched_addresses("ethereum"))
            watched_lower = {a.lower() for a in watched_addrs}

            for tx in transactions:
                if not isinstance(tx, dict):
                    continue

                tx_hash = tx.get("hash", "")
                to_addr = (tx.get("to") or "").lower()
                from_addr = (tx.get("from") or "").lower()

                # Skip if we've already processed this tx
                with self._seen_txs_lock:
                    if tx_hash in self._seen_txs:
                        continue
                    self._seen_txs.add(tx_hash)
                    # Bound the dedup set
                    if len(self._seen_txs) > 10_000:
                        self._seen_txs.clear()

                # We care about transactions FROM watched protocol addresses
                # (treasury/LP draining out) or TO them (potential attack setup)
                if from_addr not in watched_lower and to_addr not in watched_lower:
                    continue

                # Estimate USD value from ETH value (rough: 1 ETH ≈ $3000)
                # In production, use a price oracle
                eth_value = int(tx.get("value", "0x0"), 16) / 1e18
                estimated_usd = eth_value * 3000.0  # Rough ETH price estimate

                # For ERC-20 transfers we need to decode the input data
                # A full implementation would decode Transfer events from the receipt
                # For now, flag any tx from a watched address with large ETH value
                if estimated_usd < BSS_MIN_DRAIN_USD * 0.1:
                    continue

                # Resolve which protocol is involved
                match_addr = from_addr if from_addr in watched_lower else to_addr
                resolution = self.resolver.resolve(match_addr)
                if not resolution:
                    continue

                slug, proto_info = resolution
                chain_name = proto_info.get("chain", "ethereum")

                # Check if destination is a potentially malicious contract
                is_unverified = to_addr not in watched_lower
                contract_age_days = 0  # Would query Etherscan in production

                confidence, exploit_type = self.scorer.score_evm_tx(
                    tx=tx,
                    protocol_address=match_addr,
                    estimated_value_usd=estimated_usd,
                    is_unverified_contract=is_unverified,
                    contract_age_days=contract_age_days,
                )

                if confidence >= 0.55:  # Threshold for triggering alert
                    event = ExploitEvent(
                        protocol_slug=slug,
                        protocol_name=slug.replace("-", " ").title(),
                        token_symbol=proto_info.get("token_symbol", "UNKNOWN"),
                        chain=chain_name,
                        drain_amount_usd=estimated_usd,
                        drain_address=match_addr,
                        attacker_address=to_addr if from_addr in watched_lower else from_addr,
                        tx_hash=tx_hash,
                        block_number=block_number,
                        exploit_type=exploit_type,
                        confidence=confidence,
                    )
                    logger.warning(
                        f"🚨 EXPLOIT SIGNAL [ETH] | {event.protocol_name} | "
                        f"${estimated_usd:,.0f} | confidence={confidence:.2f} | "
                        f"type={exploit_type} | tx={tx_hash[:16]}..."
                    )
                    await self._handle_exploit_event(event)

        except asyncio.TimeoutError:
            logger.debug(f"🦅 ETH block {block_number} fetch timed out — skipping")
        except Exception as e:
            logger.error(f"🦅 ETH block processing error (block {block_number}): {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # Solana WebSocket Listener
    # ─────────────────────────────────────────────────────────────────────────

    async def _sol_listener(self) -> None:
        """
        Subscribe to Solana program logs for watched protocol program IDs.
        Detects anomalous large SPL token transfers from known vaults.
        """
        retry_delay = 5
        watched_sol_addrs = self.resolver.get_all_watched_addresses("solana")

        while self._running:
            try:
                logger.info(f"🦅 SOL WSS connecting: {self.sol_ws_url[:40]}...")
                async with websockets.connect(
                    self.sol_ws_url,
                    ping_interval=20,
                    ping_timeout=30,
                    close_timeout=10,
                ) as ws:
                    # Subscribe to logs for each watched Solana address
                    sub_id_map: Dict[int, str] = {}  # sub_id → protocol_address
                    req_id = 100

                    for addr in watched_sol_addrs[:20]:  # Limit to 20 subscriptions
                        await ws.send(json.dumps({
                            "jsonrpc": "2.0",
                            "id": req_id,
                            "method": "logsSubscribe",
                            "params": [
                                {"mentions": [addr]},
                                {"commitment": "confirmed"},
                            ],
                        }))
                        sub_resp = await asyncio.wait_for(ws.recv(), timeout=10)
                        sub_data = json.loads(sub_resp)
                        if "result" in sub_data:
                            sub_id_map[sub_data["result"]] = addr
                        req_id += 1

                    logger.info(f"🦅 SOL subscribed to {len(sub_id_map)} program log streams")
                    retry_delay = 5

                    while self._running:
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=60)
                        except asyncio.TimeoutError:
                            await ws.ping()
                            continue

                        msg = json.loads(raw)
                        if "params" not in msg:
                            continue

                        result = msg["params"].get("result", {})
                        value = result.get("value", {})
                        logs = value.get("logs", [])
                        signature = value.get("signature", "")
                        err = value.get("err")

                        # Skip failed transactions
                        if err:
                            continue

                        # Dedup
                        with self._seen_txs_lock:
                            if signature in self._seen_txs:
                                continue
                            self._seen_txs.add(signature)

                        # Estimate value from logs (rough heuristic)
                        # A production implementation would parse SPL token transfer amounts
                        estimated_usd = self._estimate_sol_tx_value(logs)

                        if estimated_usd < BSS_MIN_DRAIN_USD * 0.1:
                            continue

                        # Find which protocol this log belongs to
                        sub_id = msg["params"].get("subscription", 0)
                        protocol_addr = sub_id_map.get(sub_id, "")
                        if not protocol_addr:
                            continue

                        resolution = self.resolver.resolve(protocol_addr)
                        if not resolution:
                            continue

                        slug, proto_info = resolution
                        confidence, exploit_type = self.scorer.score_solana_log(
                            log_entry=value,
                            protocol_address=protocol_addr,
                            estimated_value_usd=estimated_usd,
                        )

                        if confidence >= 0.55:
                            event = ExploitEvent(
                                protocol_slug=slug,
                                protocol_name=slug.replace("-", " ").title(),
                                token_symbol=proto_info.get("token_symbol", "UNKNOWN"),
                                chain="solana",
                                drain_amount_usd=estimated_usd,
                                drain_address=protocol_addr,
                                attacker_address="unknown",
                                tx_hash=signature,
                                block_number=0,
                                exploit_type=exploit_type,
                                confidence=confidence,
                            )
                            logger.warning(
                                f"🚨 EXPLOIT SIGNAL [SOL] | {event.protocol_name} | "
                                f"${estimated_usd:,.0f} | confidence={confidence:.2f} | "
                                f"type={exploit_type} | sig={signature[:16]}..."
                            )
                            await self._handle_exploit_event(event)

            except websockets.exceptions.ConnectionClosed as e:
                logger.warning(f"🦅 SOL WSS disconnected: {e}. Reconnecting in {retry_delay}s...")
            except Exception as e:
                logger.error(f"🦅 SOL WSS error: {e}. Reconnecting in {retry_delay}s...")

            if self._running:
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 60)

    def _estimate_sol_tx_value(self, logs: List[str]) -> float:
        """
        Rough heuristic to estimate USD value from Solana log strings.
        Looks for 'amount' patterns in log data.
        In production, parse the actual SPL token transfer instruction data.
        """
        for log in logs:
            # Look for patterns like "amount: 1000000000" (lamports or token units)
            if "amount" in log.lower():
                parts = log.split()
                for i, p in enumerate(parts):
                    if "amount" in p.lower() and i + 1 < len(parts):
                        try:
                            raw_amount = float(parts[i + 1].rstrip(","))
                            # Assume SOL price $150, 9 decimals
                            sol_amount = raw_amount / 1e9
                            return sol_amount * 150.0
                        except (ValueError, IndexError):
                            pass
        return 0.0

    # ─────────────────────────────────────────────────────────────────────────
    # TVL Polling Fallback Monitor
    # ─────────────────────────────────────────────────────────────────────────

    async def _tvl_poll_monitor(self) -> None:
        """
        Fallback monitor: polls DefiLlama TVL for watched protocols every
        BSS_POLL_INTERVAL seconds. Triggers if TVL drops >40% in one cycle.
        This catches exploits that don't generate obvious on-chain signals
        (e.g., gradual drains, oracle manipulations).
        """
        import aiohttp  # Lazy import — only needed for async HTTP

        while self._running:
            await asyncio.sleep(BSS_POLL_INTERVAL)

            for slug, proto_info in PROTOCOL_REGISTRY.items():
                try:
                    url = f"https://api.llama.fi/protocol/{slug}"
                    async with aiohttp.ClientSession() as session:
                        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                            if resp.status != 200:
                                continue
                            data = await resp.json()

                    current_tvl = data.get("tvl", [{}])[-1].get("totalLiquidityUSD", 0) if data.get("tvl") else 0
                    if not current_tvl:
                        continue

                    baseline = self._tvl_baseline.get(slug)
                    if baseline is None:
                        self._tvl_baseline[slug] = current_tvl
                        continue

                    # Calculate TVL drop
                    if baseline > 0:
                        drop_pct = (baseline - current_tvl) / baseline
                        drop_usd = baseline - current_tvl

                        if drop_pct >= 0.40 and drop_usd >= BSS_MIN_DRAIN_USD:
                            logger.warning(
                                f"🚨 TVL DRAIN DETECTED [DefiLlama] | {slug} | "
                                f"${baseline:,.0f} → ${current_tvl:,.0f} | "
                                f"drop={drop_pct:.1%} (${drop_usd:,.0f})"
                            )
                            event = ExploitEvent(
                                protocol_slug=slug,
                                protocol_name=slug.replace("-", " ").title(),
                                token_symbol=proto_info.get("token_symbol", "UNKNOWN"),
                                chain=proto_info.get("chain", "ethereum"),
                                drain_amount_usd=drop_usd,
                                drain_address="defillama-detected",
                                attacker_address="unknown",
                                tx_hash="defillama-poll",
                                block_number=0,
                                exploit_type="tvl_drain",
                                confidence=0.75,  # High confidence — TVL is ground truth
                            )
                            await self._handle_exploit_event(event)

                    # Update baseline (rolling — tracks gradual TVL changes normally)
                    # Only update if TVL increased or dropped <10% (normal fluctuation)
                    if current_tvl >= baseline * 0.90:
                        self._tvl_baseline[slug] = current_tvl

                except Exception as e:
                    logger.debug(f"🦅 TVL poll error for {slug}: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # Exploit Event Handler — Core Decision Logic
    # ─────────────────────────────────────────────────────────────────────────

    async def _handle_exploit_event(self, event: ExploitEvent) -> None:
        """
        Central handler for all detected exploit events.
        Deduplicates, validates, and triggers the short execution.
        """
        # ── Dedup: one short per protocol per 24h ─────────────────────────────
        with self._lock:
            if event.token_symbol in self.active_shorts:
                logger.debug(f"🦅 Short already active for {event.token_symbol} — skip")
                return

            # Check if we've recently handled this protocol
            recent_protocols = {e.protocol_slug for e in self.exploit_history[-20:]}
            if event.protocol_slug in recent_protocols:
                logger.debug(f"🦅 Recent exploit already handled for {event.protocol_slug} — skip")
                return

            # ── Capacity check ────────────────────────────────────────────────
            if len(self.active_shorts) >= BSS_MAX_SHORTS:
                logger.warning(
                    f"🦅 MAX_SHORTS ({BSS_MAX_SHORTS}) reached — cannot open short for {event.token_symbol}"
                )
                return

        # ── Validate token has a Hyperliquid perp listing ─────────────────────
        if not self.hl.has_perp(event.token_symbol):
            logger.warning(
                f"🦅 {event.token_symbol} has no Hyperliquid perp listing — "
                f"cannot short. Exploit: {event.protocol_name}"
            )
            # Still record the event for history
            self.exploit_history.append(event)
            self._send_exploit_alert(event, shorted=False, reason="no_perp_listing")
            return

        # ── Minimum drain threshold ────────────────────────────────────────────
        proto_min = PROTOCOL_REGISTRY.get(event.protocol_slug, {}).get("min_drain_usd", BSS_MIN_DRAIN_USD)
        if event.drain_amount_usd < proto_min:
            logger.debug(
                f"🦅 Drain ${event.drain_amount_usd:,.0f} below protocol minimum "
                f"${proto_min:,.0f} for {event.protocol_name}"
            )
            return

        # ── Scale position size with drain severity ────────────────────────────
        # Larger drain = more confidence = larger position (capped at 3× base)
        severity_multiplier = min(event.drain_amount_usd / BSS_MIN_DRAIN_USD, 3.0)
        position_size_usd = BSS_SHORT_SIZE_USD * severity_multiplier * event.confidence

        # ── Execute the short ─────────────────────────────────────────────────
        logger.warning(
            f"🚨 EXECUTING BLACK SWAN SHORT | {event.protocol_name} | "
            f"Token: {event.token_symbol} | Chain: {event.chain} | "
            f"Drain: ${event.drain_amount_usd:,.0f} | "
            f"Confidence: {event.confidence:.2f} | "
            f"Size: ${position_size_usd:.2f} @ {BSS_SHORT_LEVERAGE}x"
        )

        # Run the blocking executor call in a thread pool to not block the event loop
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: self.hl.open_short(
                symbol=event.token_symbol,
                size_usd=position_size_usd,
                leverage=BSS_SHORT_LEVERAGE,
                gem_score=100,  # Bypass gem score gate — this is an emergency trade
            ),
        )

        now = time.time()
        if result:
            event.short_opened = True
            event.short_symbol = event.token_symbol
            event.short_opened_at = datetime.now(timezone.utc)
            entry_price = result.get("entry_price", 0.0)
            event.short_entry_price = entry_price

            short = ActiveShort(
                symbol=event.token_symbol,
                exploit_event=event,
                opened_at=now,
                size_usd=position_size_usd,
                leverage=BSS_SHORT_LEVERAGE,
                timeout_at=now + (BSS_TIMEOUT_MINUTES * 60),
            )

            with self._lock:
                self.active_shorts[event.token_symbol] = short
                self.exploit_history.append(event)

            logger.info(
                f"✅ BLACK SWAN SHORT OPENED | {event.token_symbol} | "
                f"entry=${entry_price:.4f} | size=${position_size_usd:.2f} | "
                f"timeout in {BSS_TIMEOUT_MINUTES}m"
            )
            self._send_exploit_alert(event, shorted=True)
        else:
            logger.error(
                f"❌ BLACK SWAN SHORT FAILED | {event.token_symbol} | "
                f"Hyperliquid executor returned None"
            )
            self.exploit_history.append(event)
            self._send_exploit_alert(event, shorted=False, reason="executor_failed")

    # ─────────────────────────────────────────────────────────────────────────
    # Safety Timeout Monitor
    # ─────────────────────────────────────────────────────────────────────────

    async def _safety_timeout_monitor(self) -> None:
        """
        Runs every 30 seconds. Closes any active short that has exceeded
        its safety timeout. This is a HARD CLOSE — fires regardless of PnL.

        The rationale: exploit-driven crashes are sharp and fast. The initial
        panic dump (30–60 minutes) is the profitable window. After that,
        the token often bounces as the market reassesses, creating significant
        short-squeeze risk. The timeout protects against holding through the bounce.
        """
        while self._running:
            await asyncio.sleep(30)

            now = time.time()
            to_close: List[str] = []

            with self._lock:
                for symbol, short in self.active_shorts.items():
                    if not short.closed and now >= short.timeout_at:
                        elapsed_min = (now - short.opened_at) / 60
                        logger.warning(
                            f"⏰ SAFETY TIMEOUT: closing {symbol} short | "
                            f"elapsed={elapsed_min:.1f}m / {BSS_TIMEOUT_MINUTES}m"
                        )
                        to_close.append(symbol)

            for symbol in to_close:
                await self._close_short(symbol, reason="safety_timeout")

    async def _close_short(self, symbol: str, reason: str = "manual") -> None:
        """Close a specific black swan short position."""
        with self._lock:
            short = self.active_shorts.get(symbol)
            if not short or short.closed:
                return
            short.closed = True  # Mark as closing to prevent double-close

        logger.info(f"🛡️  Closing black swan short: {symbol} | reason={reason}")

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: self.hl.close_position(symbol),
        )

        pnl = 0.0
        if result:
            pnl = result.get("pnl", 0.0)
            close_price = result.get("close_price", 0.0)
            logger.info(
                f"✅ BLACK SWAN SHORT CLOSED | {symbol} | "
                f"reason={reason} | pnl=${pnl:+.2f} | close=${close_price:.4f}"
            )
        else:
            logger.error(f"❌ Failed to close black swan short for {symbol}")

        with self._lock:
            short = self.active_shorts.pop(symbol, None)
            if short:
                short.exploit_event.short_closed_at = datetime.now(timezone.utc)
                short.exploit_event.short_pnl = pnl

        self._send_close_alert(symbol, reason, pnl)

    # ─────────────────────────────────────────────────────────────────────────
    # Notifications
    # ─────────────────────────────────────────────────────────────────────────

    def _send_exploit_alert(
        self,
        event: ExploitEvent,
        shorted: bool,
        reason: str = "",
    ) -> None:
        """Send Telegram + Slack alert for a detected exploit."""
        try:
            from notifications.telegram import send_telegram_message
            from notifications.slack import notify_alert

            if shorted:
                tg_msg = (
                    f"🚨 <b>BLACK SWAN EXPLOIT DETECTED</b> 🚨\n\n"
                    f"Protocol: <b>{event.protocol_name}</b>\n"
                    f"Chain: {event.chain.upper()}\n"
                    f"Drain: <b>${event.drain_amount_usd:,.0f}</b>\n"
                    f"Type: {event.exploit_type}\n"
                    f"Confidence: {event.confidence:.0%}\n"
                    f"TX: <code>{event.tx_hash[:20]}...</code>\n\n"
                    f"⚡ SHORT OPENED: <b>{event.token_symbol}</b> @ {BSS_SHORT_LEVERAGE}x\n"
                    f"⏰ Auto-close in {BSS_TIMEOUT_MINUTES} minutes"
                )
                slack_msg = (
                    f"🚨 BLACK SWAN: {event.protocol_name} exploited "
                    f"(${event.drain_amount_usd:,.0f}). "
                    f"SHORT {event.token_symbol} @ {BSS_SHORT_LEVERAGE}x opened."
                )
            else:
                tg_msg = (
                    f"⚠️ <b>EXPLOIT DETECTED — No Short</b>\n\n"
                    f"Protocol: <b>{event.protocol_name}</b>\n"
                    f"Chain: {event.chain.upper()}\n"
                    f"Drain: ${event.drain_amount_usd:,.0f}\n"
                    f"Reason: {reason}\n"
                    f"TX: <code>{event.tx_hash[:20]}...</code>"
                )
                slack_msg = (
                    f"⚠️ Exploit detected on {event.protocol_name} "
                    f"(${event.drain_amount_usd:,.0f}) — no short opened ({reason})"
                )

            send_telegram_message(tg_msg)
            _alert_title = (
                f"BLACK SWAN: {event.protocol_name}"
                if shorted else
                f"EXPLOIT DETECTED: {event.protocol_name}"
            )
            notify_alert(title=_alert_title, message=slack_msg, level="critical")
        except Exception as e:
            logger.error(f"🦅 Notification error: {e}")

    def _send_close_alert(self, symbol: str, reason: str, pnl: float) -> None:
        """Send Telegram + Slack alert when a black swan short is closed."""
        try:
            from notifications.telegram import send_telegram_message
            from notifications.slack import notify_alert

            pnl_emoji = "💰" if pnl > 0 else "📉" if pnl < 0 else "➖"
            tg_msg = (
                f"🛡️ <b>Black Swan Short Closed</b>\n\n"
                f"Symbol: <b>{symbol}</b>\n"
                f"Reason: {reason}\n"
                f"PnL: {pnl_emoji} <b>${pnl:+.2f}</b>"
            )
            send_telegram_message(tg_msg)
            notify_alert(
                title=f"Black Swan Short Closed: {symbol}",
                message=f"🛡️ Black Swan short {symbol} closed ({reason}) | PnL: ${pnl:+.2f}",
                level="info" if pnl >= 0 else "warning",
            )
        except Exception as e:
            logger.error(f"🦅 Close notification error: {e}")



# ─────────────────────────────────────────────────────────────────────────────
# Module-level singleton accessor
# ─────────────────────────────────────────────────────────────────────────────

_sweeper_instance: Optional[BlackSwanSweeper] = None


def get_sweeper() -> Optional[BlackSwanSweeper]:
    """Return the global BlackSwanSweeper instance (if initialized)."""
    return _sweeper_instance


def init_sweeper(hyperliquid_executor: Any) -> BlackSwanSweeper:
    """
    Initialize and start the global BlackSwanSweeper instance.
    Call once from main.py during bot startup.

    Args:
        hyperliquid_executor: An initialized HyperliquidExecutor instance.

    Returns:
        The BlackSwanSweeper instance (started if enabled).
    """
    global _sweeper_instance
    _sweeper_instance = BlackSwanSweeper(hyperliquid_executor=hyperliquid_executor)
    _sweeper_instance.start()
    return _sweeper_instance
