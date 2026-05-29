"""
core/moralis_streams_manager.py — Moralis Streams lifecycle manager.

Responsible for:
  1. Auto-creating streams on Moralis (alpha wallets, whale detection, liquidity events)
  2. Syncing wallet addresses from SMART_MONEY_WALLETS into the active stream
  3. Health-checking streams every N minutes and auto-recreating if terminated
  4. Retrieving webhook secret from Moralis settings
"""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Optional

from data.http_session import get_session

from config import settings

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────
BASE_URL = "https://api.moralis-streams.com"

# EVM chain IDs we care about (hex format — required by Moralis)
CHAIN_IDS = ["0x1", "0x2105", "0xa4b1", "0x89", "0x38", "0xa86a"]  # ETH, Base, Arb, Polygon, BSC, Avalanche

# Stream tags — used to identify our streams and route webhook events
TAG_ALPHA_WALLETS = "shamrock-alpha-wallets"
TAG_WHALE_DETECTOR = "shamrock-whale-detector"
TAG_LIQUIDITY = "shamrock-liquidity-events"
TAG_SOLANA_DISCOVERY = "shamrock-solana-discovery"
TAG_SOLANA_ALPHA_WALLETS = "shamrock-solana-alpha"
TAG_BTC_WHALE_WATCH = "shamrock-btc-whale-watch"

# Uniswap V2 Router / Factory event signatures
PAIR_CREATED_TOPIC = "PairCreated(address,address,address,uint256)"
TRANSFER_TOPIC = "Transfer(address,address,uint256)"

# Uniswap V2 Factory ABI (PairCreated only)
PAIR_CREATED_ABI = [
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "token0", "type": "address"},
            {"indexed": True, "name": "token1", "type": "address"},
            {"indexed": False, "name": "pair", "type": "address"},
            {"indexed": False, "name": "", "type": "uint256"},
        ],
        "name": "PairCreated",
        "type": "event",
    }
]

# Known DEX factory addresses (for liquidity event monitoring)
DEX_FACTORIES = {
    "0x1": [
        "0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f",  # Uniswap V2
        "0x1F98431c8aD98523631AE4a59f267346ea31F984",  # Uniswap V3
    ],
    "0x2105": [
        "0x8909Dc15e40173Ff4699343b6eB8132c65e18eC6",  # Uniswap V3 (Base)
        "0x02a84c1b3BBD7401a5f7fa98a384EBC70bB5749E",  # Aerodrome
    ],
    "0xa4b1": [
        "0x1F98431c8aD98523631AE4a59f267346ea31F984",  # Uniswap V3 (Arbitrum)
        "0xf1D7CC64Fb4452F05c498126312eBE29f30Fbcf9",  # Camelot V2
    ],
}

# ERC20 Transfer ABI (for allAddresses whale detection)
ERC20_TRANSFER_ABI = [
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "from", "type": "address"},
            {"indexed": True, "name": "to", "type": "address"},
            {"indexed": False, "name": "value", "type": "uint256"},
        ],
        "name": "Transfer",
        "type": "event",
    }
]


class MoralisStreamsManager:
    """Manages the full lifecycle of Moralis Streams for the trading bot."""

    def __init__(self):
        self.api_key = settings.MORALIS_API_KEY
        self.webhook_url = settings.MORALIS_STREAMS_WEBHOOK_URL
        self._headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        }
        self._health_thread: Optional[threading.Thread] = None
        self._running = False

        # Cache of stream IDs we manage (tag → stream_id)
        self._managed_streams: dict[str, str] = {}

        # Metrics
        self.metrics = {
            "streams_created": 0,
            "streams_recreated": 0,
            "health_checks": 0,
            "addresses_synced": 0,
            "errors": 0,
            "last_health_check": None,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Initialize all streams and start health monitoring."""
        if not self.api_key:
            logger.warning("MoralisStreamsManager: MORALIS_API_KEY not set — skipping")
            return
        if not self.webhook_url:
            logger.warning(
                "MoralisStreamsManager: MORALIS_STREAMS_WEBHOOK_URL not set — "
                "cannot create streams (Moralis needs a public URL to POST to)"
            )
            return

        logger.info("MoralisStreamsManager: Starting stream lifecycle management")

        # 1. Discover existing streams we manage
        self._discover_existing_streams()

        # 2. Ensure alpha wallet stream exists
        self._ensure_alpha_wallet_stream()

        # 3. Optional: whale detection stream
        if settings.MORALIS_STREAMS_WHALE_ENABLED:
            self._ensure_whale_stream()

        # 4. Optional: liquidity event stream
        if settings.MORALIS_STREAMS_LIQUIDITY_ENABLED:
            self._ensure_liquidity_stream()

        # 4.5. Optional: Solana highly active discovery stream
        if settings.MORALIS_STREAMS_SOLANA_DISCOVERY_ENABLED:
            self._ensure_solana_discovery_stream()

        # 4.6. Optional: Solana alpha wallet copy-trade stream
        if settings.MORALIS_STREAMS_SOLANA_ALPHA_ENABLED:
            self._ensure_solana_alpha_wallet_stream()

        # 4.7. Optional: Bitcoin Whale Watch stream
        if getattr(settings, "MORALIS_STREAMS_BTC_WHALE_ENABLED", True):
            self._ensure_btc_stream()

        # 5. Start health check loop
        if settings.MORALIS_STREAMS_AUTO_SYNC:
            self._running = True
            self._health_thread = threading.Thread(
                target=self._health_loop,
                name="MoralisStreamsHealthCheck",
                daemon=True,
            )
            self._health_thread.start()
            logger.info(
                f"MoralisStreamsManager: Health check loop started "
                f"(interval={settings.MORALIS_STREAMS_HEALTH_INTERVAL}s)"
            )

    def stop(self) -> None:
        """Stop health monitoring (does NOT delete streams — they persist)."""
        self._running = False
        if self._health_thread and self._health_thread.is_alive():
            self._health_thread.join(timeout=10)
        logger.info("MoralisStreamsManager: Stopped")

    def sync_alpha_wallets(self, wallets: list[str]) -> None:
        """
        Replace the address list on the alpha wallet stream with the given wallets.
        Called by sniper_discovery or wallet_monitor when the wallet list changes.
        """
        stream_id = self._managed_streams.get(TAG_ALPHA_WALLETS)
        if not stream_id:
            logger.warning("MoralisStreamsManager: No alpha wallet stream to sync")
            return

        # Moralis PATCH replaces all addresses — exactly what we want
        self._replace_addresses(stream_id, wallets)
        self.metrics["addresses_synced"] += len(wallets)
        logger.info(f"MoralisStreamsManager: Synced {len(wallets)} alpha wallets to stream {stream_id}")

    def get_status(self) -> dict[str, Any]:
        """Return current status for dashboard display."""
        streams_info = {}
        for tag, stream_id in self._managed_streams.items():
            info = self._get_stream(stream_id)
            if info:
                streams_info[tag] = {
                    "id": stream_id,
                    "status": info.get("status", "unknown"),
                    "statusMessage": info.get("statusMessage", ""),
                    "chains": info.get("chainIds", []),
                    "tag": tag,
                }
        return {
            "managed_streams": streams_info,
            "metrics": self.metrics.copy(),
            "webhook_url": self.webhook_url,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Stream Creation
    # ─────────────────────────────────────────────────────────────────────────

    def _ensure_alpha_wallet_stream(self) -> None:
        """Create or verify the alpha wallet monitoring stream."""
        if TAG_ALPHA_WALLETS in self._managed_streams:
            logger.info(f"MoralisStreamsManager: Alpha wallet stream already exists: {self._managed_streams[TAG_ALPHA_WALLETS]}")
            self._sync_current_alpha_wallets()
            return

        webhook = f"{self.webhook_url}/moralis/streams"
        body = {
            "webhookUrl": webhook,
            "description": "Shamrock Trading Bot — Alpha Wallet ERC20 Transfer Monitor",
            "tag": TAG_ALPHA_WALLETS,
            "topic0": [TRANSFER_TOPIC],
            "allAddresses": False,
            "includeContractLogs": True,
            "includeNativeTxs": True,
            "chainIds": CHAIN_IDS,
            "abi": ERC20_TRANSFER_ABI,
            "advancedOptions": [
                {
                    "topic0": TRANSFER_TOPIC,
                    "includeNativeTxs": True,
                }
            ],
            # Triggers: enrich webhook with receiver's post-transfer token balance
            # This eliminates a separate API call per event — data arrives in the webhook
            "triggers": [{
                "type": "erc20transfer",
                "contractAddress": "$contract",
                "functionAbi": [{
                    "constant": True,
                    "inputs": [{"name": "account", "type": "address"}],
                    "name": "balanceOf",
                    "outputs": [{"name": "balance", "type": "uint256"}],
                    "type": "function",
                }],
                "inputs": [["$to"]],
                "outputName": "receiverBalance",
                "callFrom": "0x0000000000000000000000000000000000000000",
            }],
        }

        stream_id = self._create_stream(body)
        if stream_id:
            self._managed_streams[TAG_ALPHA_WALLETS] = stream_id
            self._sync_current_alpha_wallets()
            logger.info(f"MoralisStreamsManager: ✅ Alpha wallet stream created: {stream_id}")

    def _ensure_whale_stream(self) -> None:
        """Create or verify the whale detection stream (allAddresses=true)."""
        if TAG_WHALE_DETECTOR in self._managed_streams:
            logger.info(f"MoralisStreamsManager: Whale stream already exists: {self._managed_streams[TAG_WHALE_DETECTOR]}")
            return

        # Only monitor Base and Arbitrum — that's where our gems live
        whale_chains = ["0x2105", "0xa4b1"]
        webhook = f"{self.webhook_url}/moralis/streams"

        body = {
            "webhookUrl": webhook,
            "description": "Shamrock Trading Bot — Whale ERC20 Transfer Detector (>$50K)",
            "tag": TAG_WHALE_DETECTOR,
            "topic0": [TRANSFER_TOPIC],
            "allAddresses": True,
            "includeContractLogs": True,
            "chainIds": whale_chains,
            "abi": ERC20_TRANSFER_ABI,
        }

        stream_id = self._create_stream(body)
        if stream_id:
            self._managed_streams[TAG_WHALE_DETECTOR] = stream_id
            logger.info(f"MoralisStreamsManager: ✅ Whale detector stream created: {stream_id}")

    def _ensure_liquidity_stream(self) -> None:
        """Create or verify the liquidity event stream (PairCreated on DEX factories)."""
        if TAG_LIQUIDITY in self._managed_streams:
            logger.info(f"MoralisStreamsManager: Liquidity stream already exists: {self._managed_streams[TAG_LIQUIDITY]}")
            return

        # Monitor Base, Arbitrum, Ethereum factories
        liquidity_chains = ["0x1", "0x2105", "0xa4b1"]
        webhook = f"{self.webhook_url}/moralis/streams"

        body = {
            "webhookUrl": webhook,
            "description": "Shamrock Trading Bot — DEX Liquidity Pool Creation Monitor",
            "tag": TAG_LIQUIDITY,
            "topic0": [PAIR_CREATED_TOPIC],
            "allAddresses": False,
            "includeContractLogs": True,
            "chainIds": liquidity_chains,
            "abi": PAIR_CREATED_ABI,
        }

        stream_id = self._create_stream(body)
        if stream_id:
            self._managed_streams[TAG_LIQUIDITY] = stream_id
            # Add DEX factory addresses
            all_factories = []
            for chain_factories in DEX_FACTORIES.values():
                all_factories.extend(chain_factories)
            if all_factories:
                self._replace_addresses(stream_id, list(set(all_factories)))
            logger.info(f"MoralisStreamsManager: ✅ Liquidity stream created: {stream_id}")

    def _sync_current_alpha_wallets(self) -> None:
        """Push current SMART_MONEY_WALLETS to the alpha stream."""
        wallets = settings.SMART_MONEY_WALLETS
        if wallets:
            self.sync_alpha_wallets(wallets)


    def _ensure_solana_discovery_stream(self) -> None:
        if TAG_SOLANA_DISCOVERY in self._managed_streams:
            logger.info(f"MoralisStreamsManager: Solana discovery stream already exists: {self._managed_streams[TAG_SOLANA_DISCOVERY]}")
            return

        webhook = f"{self.webhook_url}/moralis/streams"
        addresses = []
        if settings.PUMP_FUN_PROGRAM_ID:
            addresses.append(settings.PUMP_FUN_PROGRAM_ID)
        if settings.RAYDIUM_AMM_PROGRAM_ID:
            addresses.append(settings.RAYDIUM_AMM_PROGRAM_ID)

        body = {
            "webhookUrl": webhook,
            "description": "Shamrock Trading Bot — Solana Zero-Latency Token Discovery",
            "tag": TAG_SOLANA_DISCOVERY,
            "network": ["mainnet"],
            "address": addresses
        }

        stream_id = self._create_stream(body, network="solana")
        if stream_id:
            self._managed_streams[TAG_SOLANA_DISCOVERY] = stream_id
            logger.info(f"MoralisStreamsManager: ✅ Solana discovery stream created: {stream_id}")

    # ─────────────────────────────────────────────────────────────────────────
    # Health Monitoring
    # ─────────────────────────────────────────────────────────────────────────

    def _health_loop(self) -> None:
        """Periodically check stream health and auto-recreate if terminated."""
        while self._running:
            try:
                self._run_health_check()
            except Exception as e:
                logger.error(f"MoralisStreamsManager: Health check error: {e}")
                self.metrics["errors"] += 1

            time.sleep(settings.MORALIS_STREAMS_HEALTH_INTERVAL)

    def _run_health_check(self) -> None:
        """Check all managed streams and handle error/terminated states."""
        self.metrics["health_checks"] += 1
        self.metrics["last_health_check"] = time.time()

        for tag, stream_id in list(self._managed_streams.items()):
            net = "solana" if tag == TAG_SOLANA_DISCOVERY else "evm"
            info = self._get_stream(stream_id, network=net)
            if not info:
                logger.warning(f"MoralisStreamsManager: Stream {tag} ({stream_id}) not found — will recreate")
                del self._managed_streams[tag]
                self._recreate_stream(tag)
                continue

            status = info.get("status", "unknown")
            if status == "active":
                continue
            elif status == "error":
                logger.warning(
                    f"MoralisStreamsManager: Stream {tag} ({stream_id}) is in ERROR state — "
                    f"message: {info.get('statusMessage', 'unknown')}. "
                    f"Will auto-terminate in 24h if not fixed."
                )
                # Try to unpause/reset by updating the stream
                self._update_stream_status(stream_id, "active", network=net)
            elif status == "paused":
                logger.info(f"MoralisStreamsManager: Stream {tag} ({stream_id}) is paused — resuming")
                self._update_stream_status(stream_id, "active", network=net)
            elif status == "terminated":
                logger.warning(
                    f"MoralisStreamsManager: Stream {tag} ({stream_id}) is TERMINATED — "
                    f"this is unrecoverable. Recreating..."
                )
                # Delete the dead stream and recreate
                self._delete_stream(stream_id, network=net)
                del self._managed_streams[tag]
                self._recreate_stream(tag)
                self.metrics["streams_recreated"] += 1

    def _recreate_stream(self, tag: str) -> None:
        """Recreate a stream by tag."""
        if tag == TAG_ALPHA_WALLETS:
            self._ensure_alpha_wallet_stream()
        elif tag == TAG_WHALE_DETECTOR:
            self._ensure_whale_stream()
        elif tag == TAG_LIQUIDITY:
            self._ensure_liquidity_stream()
        elif tag == TAG_SOLANA_DISCOVERY:
            self._ensure_solana_discovery_stream()
        elif tag == TAG_SOLANA_ALPHA_WALLETS:
            self._ensure_solana_alpha_wallet_stream()
        elif tag == TAG_BTC_WHALE_WATCH:
            self._ensure_btc_stream()

    # ─────────────────────────────────────────────────────────────────────────
    # Moralis API Calls
    # ─────────────────────────────────────────────────────────────────────────

    def _create_stream(self, body: dict, network: str = "evm") -> Optional[str]:
        """Create a new stream. Returns stream ID or None."""
        try:
            # CRITICAL: Moralis uses PUT for create, NOT POST
            resp = get_session().put(
                f"{BASE_URL}/streams/{network}",
                headers=self._headers,
                json=body,
                timeout=30,
            )
            if resp.status_code in (200, 201):
                data = resp.json()
                stream_id = data.get("id")
                self.metrics["streams_created"] += 1
                logger.info(f"MoralisStreamsManager: Created stream {body.get('tag')} → {stream_id}")
                return stream_id
            else:
                logger.error(
                    f"MoralisStreamsManager: Failed to create stream {body.get('tag')}: "
                    f"{resp.status_code} {resp.text}"
                )
                self.metrics["errors"] += 1
                return None
        except Exception as e:
            logger.error(f"MoralisStreamsManager: Error creating stream: {e}")
            self.metrics["errors"] += 1
            return None

    def _get_stream(self, stream_id: str, network: str = "evm") -> Optional[dict]:
        """Get a specific stream's info."""
        try:
            resp = get_session().get(
                f"{BASE_URL}/streams/{network}/{stream_id}",
                headers=self._headers,
                timeout=15,
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except Exception:
            return None

    def _get_all_streams(self, network: str = "evm") -> list[dict]:
        """Get all streams for this API key."""
        try:
            resp = get_session().get(
                f"{BASE_URL}/streams/{network}?limit=100",
                headers=self._headers,
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("result", [])
            return []
        except Exception as e:
            logger.error(f"MoralisStreamsManager: Error listing streams: {e}")
            return []

    def _delete_stream(self, stream_id: str, network: str = "evm") -> bool:
        """Delete a stream."""
        try:
            resp = get_session().delete(
                f"{BASE_URL}/streams/{network}/{stream_id}",
                headers=self._headers,
                timeout=15,
            )
            return resp.status_code in (200, 204)
        except Exception:
            return False

    def _replace_addresses(self, stream_id: str, addresses: list[str], network: str = "evm") -> bool:
        """Replace all addresses on a stream (PATCH)."""
        if not addresses:
            return True
        try:
            # Moralis expects address in body as {"address": [...]}
            resp = get_session().post(
                f"{BASE_URL}/streams/{network}/{stream_id}/address",
                headers=self._headers,
                json={"address": addresses},
                timeout=30,
            )
            if resp.status_code in (200, 201):
                logger.debug(f"MoralisStreamsManager: Added {len(addresses)} addresses to stream {stream_id}")
                return True
            else:
                logger.error(
                    f"MoralisStreamsManager: Failed to add addresses to {stream_id}: "
                    f"{resp.status_code} {resp.text}"
                )
                return False
        except Exception as e:
            logger.error(f"MoralisStreamsManager: Error adding addresses: {e}")
            return False

    def _update_stream_status(self, stream_id: str, status: str, network: str = "evm") -> bool:
        """Update stream status (active/paused)."""
        try:
            resp = get_session().post(
                f"{BASE_URL}/streams/{network}/{stream_id}/status",
                headers=self._headers,
                json={"status": status},
                timeout=15,
            )
            return resp.status_code == 200
        except Exception:
            return False

    def _discover_existing_streams(self) -> None:
        """Find streams we previously created (by tag prefix)."""
        streams = self._get_all_streams("evm") + self._get_all_streams("solana")
        for s in streams:
            tag = s.get("tag", "")
            sid = s.get("id", "")
            if tag in (TAG_ALPHA_WALLETS, TAG_WHALE_DETECTOR, TAG_LIQUIDITY, TAG_SOLANA_DISCOVERY, TAG_SOLANA_ALPHA_WALLETS) and sid:
                self._managed_streams[tag] = sid
                logger.info(f"MoralisStreamsManager: Discovered existing stream {tag} → {sid} (status={s.get('status')})")

    # ─────────────────────────────────────────────────────────────────────────
    # Solana Alpha Wallet Stream (copy-trading on Solana)
    # ─────────────────────────────────────────────────────────────────────────

    def _ensure_btc_stream(self) -> None:
        """Create or verify the Bitcoin whale watch stream."""
        if TAG_BTC_WHALE_WATCH in self._managed_streams:
            logger.info(f"MoralisStreamsManager: BTC stream already exists: {self._managed_streams[TAG_BTC_WHALE_WATCH]}")
            return

        webhook = f"{self.webhook_url}/moralis/streams"
        # We watch the top 100 Bitcoin whale addresses
        # Let's pull some prominent whale addresses or watch all transfers > 50 BTC
        # Moralis Bitcoin Streams supports 'allAddresses' or a list of addresses.
        # We will use allAddresses: True and a custom filter for large values
        body = {
            "webhookUrl": webhook,
            "description": "Shamrock Trading Bot — Bitcoin Whale Watch (all transfers > 10 BTC)",
            "tag": TAG_BTC_WHALE_WATCH,
            "allAddresses": True,
            "chainIds": ["btc-mainnet"],
            "includeInputs": True,
        }

        # Create stream under 'bitcoin' network (EVM streams use 'evm', Solana 'solana', Bitcoin 'bitcoin')
        stream_id = self._create_stream(body, network="bitcoin")
        if stream_id:
            self._managed_streams[TAG_BTC_WHALE_WATCH] = stream_id
            logger.info(f"MoralisStreamsManager: ✅ Bitcoin whale watch stream created: {stream_id}")

    def _ensure_solana_alpha_wallet_stream(self) -> None:
        """Create or verify the Solana alpha wallet SPL transfer monitoring stream."""
        if TAG_SOLANA_ALPHA_WALLETS in self._managed_streams:
            logger.info(f"MoralisStreamsManager: Solana alpha wallet stream already exists: {self._managed_streams[TAG_SOLANA_ALPHA_WALLETS]}")
            self._sync_solana_alpha_wallets()
            return

        webhook = f"{self.webhook_url}/moralis/streams"
        addresses = list(settings.SOLANA_SMART_MONEY_WALLETS) if settings.SOLANA_SMART_MONEY_WALLETS else []

        body = {
            "webhookUrl": webhook,
            "description": "Shamrock Trading Bot — Solana Alpha Wallet SPL Transfer Monitor",
            "tag": TAG_SOLANA_ALPHA_WALLETS,
            "network": ["mainnet"],
            "address": addresses,
        }

        stream_id = self._create_stream(body, network="solana")
        if stream_id:
            self._managed_streams[TAG_SOLANA_ALPHA_WALLETS] = stream_id
            logger.info(f"MoralisStreamsManager: ✅ Solana alpha wallet stream created: {stream_id}")

    def _sync_solana_alpha_wallets(self) -> None:
        """Push current SOLANA_SMART_MONEY_WALLETS to the Solana alpha stream."""
        wallets = settings.SOLANA_SMART_MONEY_WALLETS
        if wallets:
            self.sync_solana_alpha_wallets(wallets)

    def sync_solana_alpha_wallets(self, wallets: list[str]) -> None:
        """Replace the address list on the Solana alpha wallet stream."""
        stream_id = self._managed_streams.get(TAG_SOLANA_ALPHA_WALLETS)
        if not stream_id:
            logger.warning("MoralisStreamsManager: No Solana alpha wallet stream to sync")
            return
        self._replace_addresses(stream_id, wallets, network="solana")
        self.metrics["addresses_synced"] += len(wallets)
        logger.info(f"MoralisStreamsManager: Synced {len(wallets)} Solana alpha wallets")
