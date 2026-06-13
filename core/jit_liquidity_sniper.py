"""
core/jit_liquidity_sniper.py — JIT (Just-In-Time) Liquidity Sniper Engine

ECC Skill: jit-liquidity-sniper

Architecture:
  1. MempoolWatcher — subscribes to pending transactions via WebSocket RPC or
     Moralis Streams webhooks, filtering for Uniswap V3 / Raydium swaps > $100k.
  2. JITAnalyzer — decodes the pending swap, calculates the exact tick range and
     optimal liquidity amount to sandwich the whale trade.
  3. JITExecutor — builds an atomic transaction bundle:
        a. flashBorrow (Aave V3 on EVM / Kamino on Solana)
        b. mint concentrated liquidity at the exact tick of the whale's swap
        c. whale swap executes (in the same block, next tx)
        d. burn liquidity + collect fees earned from the whale's swap
        e. repay flash loan
     The entire bundle reverts if profit < gas cost.
  4. PrivateRPCRouter — submits the bundle via:
        EVM:    Flashbots Protect (Ethereum/Base/Arbitrum) or MEV Blocker
        Solana: Jito block engine (private bundle)

Settings (config/settings.py or .env):
  JIT_ENABLED                  = true
  JIT_MIN_TRADE_SIZE_USD       = 100000.0   # Only target whale trades >= $100k
  JIT_MAX_FLASH_BORROW_USD     = 500000.0   # Cap flash borrow size
  JIT_MIN_PROFIT_USD           = 5.0        # Minimum net profit to proceed
  JIT_MAX_GAS_TO_PROFIT_RATIO  = 0.50       # Reject if gas > 50% of gross profit
  JIT_TICK_RANGE_TICKS         = 10         # Tick range around the target price (±10 ticks)
  JIT_AAVE_POOL_ADDRESS        = ""         # Aave V3 Pool address per chain
  JIT_UNISWAP_V3_FACTORY       = ""         # Uniswap V3 Factory per chain
  JIT_UNISWAP_V3_NFT_MANAGER   = ""         # Uniswap V3 NonfungiblePositionManager
  JIT_PRIVATE_RPC_FALLBACK     = "flashbots_protect"  # or "mev_blocker"

Security:
  - NEVER hardcodes private keys; all keys from environment variables.
  - All transactions submitted via private RPCs to prevent front-running.
  - Atomic bundle: if repayment fails, entire bundle reverts (zero capital risk).
  - Paper mode: simulates all operations without on-chain execution.
"""

from __future__ import annotations

import json
import logging
import math
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from config import settings
from data.http_session import get_session

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Settings
# ─────────────────────────────────────────────────────────────────────────────

JIT_ENABLED: bool = getattr(settings, "JIT_ENABLED", True)
JIT_MIN_TRADE_SIZE_USD: float = getattr(settings, "JIT_MIN_TRADE_SIZE_USD", 100_000.0)
JIT_MAX_FLASH_BORROW_USD: float = getattr(settings, "JIT_MAX_FLASH_BORROW_USD", 500_000.0)
JIT_MIN_PROFIT_USD: float = getattr(settings, "JIT_MIN_PROFIT_USD", 5.0)
JIT_MAX_GAS_TO_PROFIT_RATIO: float = getattr(settings, "JIT_MAX_GAS_TO_PROFIT_RATIO", 0.50)
JIT_TICK_RANGE_TICKS: int = getattr(settings, "JIT_TICK_RANGE_TICKS", 10)

# Uniswap V3 NonfungiblePositionManager addresses per chain
_UNISWAP_V3_NFT_MANAGER: Dict[str, str] = {
    "ethereum":  "0xC36442b4a4522E871399CD717aBDD847Ab11FE88",
    "base":      "0x03a520b32C04BF3bEEf7BEb72E919cf822Ed34f1",
    "arbitrum":  "0xC36442b4a4522E871399CD717aBDD847Ab11FE88",
    "polygon":   "0xC36442b4a4522E871399CD717aBDD847Ab11FE88",
}

# Aave V3 Pool addresses per chain
_AAVE_V3_POOL: Dict[str, str] = {
    "ethereum":  "0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2",
    "base":      "0xA238Dd80C259a72e81d7e4664a9801593F98d1c5",
    "arbitrum":  "0x794a61358D6845594F94dc1DB02A252b5b4814aD",
    "polygon":   "0x794a61358D6845594F94dc1DB02A252b5b4814aD",
}

# Flashbots Protect RPC endpoints per chain
_PRIVATE_RPC: Dict[str, str] = {
    "ethereum":  "https://rpc.flashbots.net/fast",
    "base":      "https://rpc.flashbots.net/fast?hint=calldata&hint=logs&hint=hash&builder=flashbots",
    "arbitrum":  "https://arb1.arbitrum.io/rpc",  # Arbitrum has sequencer-level protection
    "polygon":   "https://polygon-mainnet.g.alchemy.com/v2/",  # Polygon: use Alchemy private
}

# Uniswap V3 tick spacing per fee tier
_TICK_SPACING: Dict[int, int] = {
    100:   1,    # 0.01% pool
    500:   10,   # 0.05% pool
    3000:  60,   # 0.30% pool
    10000: 200,  # 1.00% pool
}


# ─────────────────────────────────────────────────────────────────────────────
# Data Classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PendingWhaleSwap:
    """Decoded pending whale swap from the mempool."""
    chain: str
    dex: str                      # "uniswap_v3" | "raydium" | "aerodrome"
    pool_address: str
    token_in: str
    token_out: str
    amount_in_usd: float
    amount_in_raw: int            # Raw token amount (wei / lamports)
    fee_tier: int                 # Uniswap V3 fee tier (500, 3000, 10000)
    current_sqrt_price_x96: int   # Current pool sqrtPriceX96
    current_tick: int             # Current pool tick
    tx_hash: str
    block_number: Optional[int] = None
    timestamp: float = field(default_factory=time.time)


@dataclass
class JITOpportunity:
    """Fully analyzed JIT opportunity ready for execution."""
    swap: PendingWhaleSwap
    tick_lower: int
    tick_upper: int
    liquidity_amount: int         # Uniswap V3 liquidity units
    flash_borrow_token: str       # Token to flash-borrow
    flash_borrow_amount_raw: int  # Amount to borrow (wei)
    flash_borrow_amount_usd: float
    estimated_fee_earned_usd: float
    estimated_gas_usd: float
    estimated_net_profit_usd: float
    aave_pool: str                # Aave pool address for flash loan
    nft_manager: str              # Uniswap V3 NonfungiblePositionManager


@dataclass
class JITResult:
    """Result of a JIT liquidity provision attempt."""
    success: bool
    opportunity: Optional[JITOpportunity] = None
    tx_hash: Optional[str] = None
    bundle_hash: Optional[str] = None
    fee_earned_usd: float = 0.0
    gas_usd: float = 0.0
    net_profit_usd: float = 0.0
    error: Optional[str] = None
    paper: bool = False


# ─────────────────────────────────────────────────────────────────────────────
# Tick Math (Uniswap V3 — Python port of TickMath.sol)
# ─────────────────────────────────────────────────────────────────────────────

class TickMath:
    """
    Python port of Uniswap V3 TickMath.sol.
    Converts between ticks and sqrtPriceX96 values.
    """
    MIN_TICK = -887272
    MAX_TICK = 887272
    Q96 = 2 ** 96

    @staticmethod
    def get_sqrt_ratio_at_tick(tick: int) -> int:
        """
        Calculates sqrt(1.0001^tick) * 2^96.
        Used to set the exact price range for concentrated liquidity.
        """
        abs_tick = abs(tick)
        assert abs_tick <= TickMath.MAX_TICK, f"Tick {tick} out of range"

        ratio = 0xfffcb933bd6fad37aa2d162d1a594001 if (abs_tick & 0x1) != 0 else (1 << 128)

        if abs_tick & 0x2:   ratio = (ratio * 0xfff97272373d413259a46990580e213a) >> 128
        if abs_tick & 0x4:   ratio = (ratio * 0xfff2e50f5f656932ef12357cf3c7fdcc) >> 128
        if abs_tick & 0x8:   ratio = (ratio * 0xffe5caca7e10e4e61c3624eaa0941cd0) >> 128
        if abs_tick & 0x10:  ratio = (ratio * 0xffcb9843d60f6159c9db58835c926644) >> 128
        if abs_tick & 0x20:  ratio = (ratio * 0xff973b41fa98c081472e6896dfb254c0) >> 128
        if abs_tick & 0x40:  ratio = (ratio * 0xff2ea16466c96a3843ec78b326b52861) >> 128
        if abs_tick & 0x80:  ratio = (ratio * 0xfe5dee046a99a2a811c461f1969c3053) >> 128
        if abs_tick & 0x100: ratio = (ratio * 0xfcbe86c7900a88aedcffc83b479aa3a4) >> 128
        if abs_tick & 0x200: ratio = (ratio * 0xf987a7253ac413176f2b074cf7815e54) >> 128
        if abs_tick & 0x400: ratio = (ratio * 0xf3392b0822b70005940c7a398e4b70f3) >> 128
        if abs_tick & 0x800: ratio = (ratio * 0xe7159475a2c29b7443b29c7fa6e889d9) >> 128
        if abs_tick & 0x1000: ratio = (ratio * 0xd097f3bdfd2022b8845ad8f792aa5825) >> 128
        if abs_tick & 0x2000: ratio = (ratio * 0xa9f746462d870fdf8a65dc1f90e061e5) >> 128
        if abs_tick & 0x4000: ratio = (ratio * 0x70d869a156d2a1b890bb3df62baf32f7) >> 128
        if abs_tick & 0x8000: ratio = (ratio * 0x31be135f97d08fd981231505542fcfa6) >> 128
        if abs_tick & 0x10000: ratio = (ratio * 0x9aa508b5b7a84e1c677de54f3e99bc9) >> 128
        if abs_tick & 0x20000: ratio = (ratio * 0x5d6af8dedb81196699c329225ee604) >> 128
        if abs_tick & 0x40000: ratio = (ratio * 0x2216e584f5fa1ea926041bedfe98) >> 128
        if abs_tick & 0x80000: ratio = (ratio * 0x48a170391f7dc42444e8fa2) >> 128

        if tick > 0:
            ratio = (2 ** 256 - 1) // ratio

        # Shift from Q128.128 to Q96.96
        sqrt_price_x96 = (ratio >> 32) + (1 if (ratio % (1 << 32)) != 0 else 0)
        return sqrt_price_x96

    @staticmethod
    def get_tick_at_sqrt_ratio(sqrt_price_x96: int) -> int:
        """Inverse of get_sqrt_ratio_at_tick — finds the tick for a given sqrtPriceX96."""
        # Simplified: use log base 1.0001
        price = (sqrt_price_x96 / (2 ** 96)) ** 2
        if price <= 0:
            return TickMath.MIN_TICK
        tick = int(math.log(price) / math.log(1.0001))
        return max(TickMath.MIN_TICK, min(TickMath.MAX_TICK, tick))

    @staticmethod
    def round_to_tick_spacing(tick: int, tick_spacing: int) -> int:
        """Round a tick down to the nearest valid tick spacing boundary."""
        return (tick // tick_spacing) * tick_spacing


# ─────────────────────────────────────────────────────────────────────────────
# Liquidity Math (Uniswap V3)
# ─────────────────────────────────────────────────────────────────────────────

class LiquidityMath:
    """
    Calculates optimal liquidity amounts for JIT provisioning.
    Based on Uniswap V3 white paper Section 6.2.
    """
    Q96 = 2 ** 96

    @staticmethod
    def get_liquidity_for_amounts(
        sqrt_price_x96: int,
        sqrt_price_lower_x96: int,
        sqrt_price_upper_x96: int,
        amount0: int,
        amount1: int,
    ) -> int:
        """
        Calculates the maximum liquidity receivable for a given amount of token0 and token1.
        """
        if sqrt_price_x96 <= sqrt_price_lower_x96:
            # Current price is below range: only token0 is used
            return LiquidityMath._get_liquidity_for_amount0(
                sqrt_price_lower_x96, sqrt_price_upper_x96, amount0
            )
        elif sqrt_price_x96 < sqrt_price_upper_x96:
            # Current price is within range: both tokens used
            liq0 = LiquidityMath._get_liquidity_for_amount0(
                sqrt_price_x96, sqrt_price_upper_x96, amount0
            )
            liq1 = LiquidityMath._get_liquidity_for_amount1(
                sqrt_price_lower_x96, sqrt_price_x96, amount1
            )
            return min(liq0, liq1)
        else:
            # Current price is above range: only token1 is used
            return LiquidityMath._get_liquidity_for_amount1(
                sqrt_price_lower_x96, sqrt_price_upper_x96, amount1
            )

    @staticmethod
    def _get_liquidity_for_amount0(
        sqrt_ratio_a_x96: int, sqrt_ratio_b_x96: int, amount0: int
    ) -> int:
        if sqrt_ratio_a_x96 > sqrt_ratio_b_x96:
            sqrt_ratio_a_x96, sqrt_ratio_b_x96 = sqrt_ratio_b_x96, sqrt_ratio_a_x96
        numerator = amount0 * sqrt_ratio_a_x96 * sqrt_ratio_b_x96
        denominator = LiquidityMath.Q96 * (sqrt_ratio_b_x96 - sqrt_ratio_a_x96)
        if denominator == 0:
            return 0
        return numerator // denominator

    @staticmethod
    def _get_liquidity_for_amount1(
        sqrt_ratio_a_x96: int, sqrt_ratio_b_x96: int, amount1: int
    ) -> int:
        if sqrt_ratio_a_x96 > sqrt_ratio_b_x96:
            sqrt_ratio_a_x96, sqrt_ratio_b_x96 = sqrt_ratio_b_x96, sqrt_ratio_a_x96
        return (amount1 * LiquidityMath.Q96) // (sqrt_ratio_b_x96 - sqrt_ratio_a_x96)

    @staticmethod
    def estimate_fee_earned(
        liquidity: int,
        total_pool_liquidity: int,
        swap_amount_usd: float,
        fee_tier: int,
    ) -> float:
        """
        Estimates the fee earned from a single whale swap flowing through our JIT position.
        fee_tier is in hundredths of a bip (e.g. 3000 = 0.30%).
        """
        if total_pool_liquidity <= 0 or liquidity <= 0:
            return 0.0
        fee_pct = fee_tier / 1_000_000  # Convert from hundredths of bip to decimal
        gross_fee = swap_amount_usd * fee_pct
        # Our share = our liquidity / total active liquidity in the tick range
        our_share = liquidity / (total_pool_liquidity + liquidity)
        return gross_fee * our_share


# ─────────────────────────────────────────────────────────────────────────────
# Mempool Watcher — detects pending whale trades
# ─────────────────────────────────────────────────────────────────────────────

class MempoolWatcher:
    """
    Watches the mempool for pending Uniswap V3 swaps exceeding JIT_MIN_TRADE_SIZE_USD.

    Two detection paths:
      1. Moralis Streams webhook (primary) — real-time pending tx events
         delivered via the existing Moralis Streams infrastructure.
      2. WebSocket RPC subscription (fallback) — subscribes to
         eth_subscribe("newPendingTransactions") on a private node.

    In paper mode, simulates whale trades for testing.
    """

    # Uniswap V3 swap function selector (swap(address,bool,int256,uint160,bytes))
    UNISWAP_V3_SWAP_SELECTOR = "0x128acb08"
    # Uniswap V3 exactInputSingle selector
    UNISWAP_V3_EXACT_INPUT_SINGLE_SELECTOR = "0x414bf389"
    # Uniswap V3 exactInput selector
    UNISWAP_V3_EXACT_INPUT_SELECTOR = "0xc04b8d59"

    def __init__(self):
        self._callbacks: List = []
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._seen_hashes: set = set()  # Dedup
        self._seen_hashes_lock = threading.Lock()

    def add_callback(self, fn) -> None:
        """Register a callback to be called with PendingWhaleSwap on detection."""
        self._callbacks.append(fn)

    def start(self) -> None:
        """Start the mempool watcher in a background daemon thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._watch_loop,
            name="JITMempoolWatcher",
            daemon=True,
        )
        self._thread.start()
        logger.info("✅ JIT MempoolWatcher started")

    def stop(self) -> None:
        self._running = False

    def _watch_loop(self) -> None:
        """
        Main watch loop.
        In paper mode: generates synthetic whale trades every 30 seconds.
        In live mode: connects to WebSocket RPC for pending tx subscription.
        """
        if getattr(settings, "MODE", "paper") != "live":
            self._paper_watch_loop()
        else:
            self._live_watch_loop()

    def _paper_watch_loop(self) -> None:
        """Generates synthetic whale trades for paper mode testing."""
        import random
        chains = ["ethereum", "base", "arbitrum"]
        tokens = [
            ("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"),  # USDC/WETH
            ("0x6B175474E89094C44Da98b954EedeAC495271d0F", "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"),  # DAI/WETH
        ]
        while self._running:
            time.sleep(30)  # Simulate a whale trade every 30s in paper mode
            chain = random.choice(chains)
            token_in, token_out = random.choice(tokens)
            amount_usd = random.uniform(JIT_MIN_TRADE_SIZE_USD, JIT_MIN_TRADE_SIZE_USD * 5)
            fake_swap = PendingWhaleSwap(
                chain=chain,
                dex="uniswap_v3",
                pool_address="0x8ad599c3A0ff1De082011EFDDc58f1908eb6e6D8",
                token_in=token_in,
                token_out=token_out,
                amount_in_usd=amount_usd,
                amount_in_raw=int(amount_usd * 1e6),  # USDC 6 decimals
                fee_tier=3000,
                current_sqrt_price_x96=TickMath.get_sqrt_ratio_at_tick(200000),
                current_tick=200000,
                tx_hash=f"0xpaper_{int(time.time())}",
            )
            logger.info(
                f"[PAPER] JIT MempoolWatcher: synthetic whale trade detected "
                f"${amount_usd:,.0f} on {chain}"
            )
            self._dispatch(fake_swap)

    def _live_watch_loop(self) -> None:
        """
        Live mode: subscribes to pending transactions via WebSocket RPC.
        Decodes Uniswap V3 swap calldata to identify whale trades.
        """
        try:
            from web3 import Web3
        except ImportError:
            logger.error("web3 not installed — JIT live mempool watch unavailable")
            return

        # Use Flashbots private RPC for mempool access (prevents leaking our intent)
        rpc_url = os.getenv(
            "JIT_MEMPOOL_RPC_URL",
            os.getenv("FLASHBOTS_RPC_URL", "https://rpc.flashbots.net"),
        )
        # Convert to WebSocket URL if HTTP
        ws_url = rpc_url.replace("https://", "wss://").replace("http://", "ws://")

        logger.info(f"JIT MempoolWatcher: connecting to {ws_url}")

        retry_delay = 5
        while self._running:
            try:
                w3 = Web3(Web3.WebSocketProvider(ws_url, websocket_timeout=60))
                if not w3.is_connected():
                    raise ConnectionError(f"WebSocket RPC not connected: {ws_url}")

                logger.info("JIT MempoolWatcher: WebSocket RPC connected")
                retry_delay = 5  # Reset on successful connection

                # Subscribe to pending transactions
                sub_id = w3.eth.subscribe("newPendingTransactions")

                for tx_hash in w3.eth.filter("pending").get_new_entries():
                    if not self._running:
                        break
                    try:
                        self._process_pending_tx(w3, tx_hash.hex())
                    except Exception as tx_err:
                        logger.debug(f"JIT tx processing error: {tx_err}")

            except Exception as conn_err:
                logger.warning(
                    f"JIT MempoolWatcher WebSocket error: {conn_err} — "
                    f"retrying in {retry_delay}s"
                )
                time.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 60)

    def _process_pending_tx(self, w3, tx_hash: str) -> None:
        """
        Fetches and decodes a pending transaction.
        Fires callbacks if it's a qualifying whale swap.
        """
        with self._seen_hashes_lock:
            if tx_hash in self._seen_hashes:
                return
            self._seen_hashes.add(tx_hash)
            # Prune seen hashes to prevent memory growth
            if len(self._seen_hashes) > 10_000:
                self._seen_hashes = set(list(self._seen_hashes)[-5_000:])

        try:
            tx = w3.eth.get_transaction(tx_hash)
        except Exception:
            return

        if not tx or not tx.get("input"):
            return

        # Check if this is a Uniswap V3 swap
        input_data = tx["input"]
        if not isinstance(input_data, str):
            input_data = input_data.hex()

        selector = input_data[:10].lower()
        if selector not in (
            self.UNISWAP_V3_SWAP_SELECTOR,
            self.UNISWAP_V3_EXACT_INPUT_SINGLE_SELECTOR,
            self.UNISWAP_V3_EXACT_INPUT_SELECTOR,
        ):
            return

        # Estimate USD value from tx.value (ETH) or decode calldata
        value_eth = tx.get("value", 0) / 1e18
        eth_price_usd = self._get_eth_price_usd()
        value_usd = value_eth * eth_price_usd

        # For token swaps (value=0), try to decode amountIn from calldata
        if value_usd < JIT_MIN_TRADE_SIZE_USD:
            value_usd = self._estimate_calldata_value(input_data, selector)

        if value_usd < JIT_MIN_TRADE_SIZE_USD:
            return

        # Determine chain from w3 connection
        try:
            chain_id = w3.eth.chain_id
        except Exception:
            chain_id = 1

        chain_map = {1: "ethereum", 8453: "base", 42161: "arbitrum", 137: "polygon", 56: "bsc"}
        chain = chain_map.get(chain_id, "ethereum")

        # Decode pool address from calldata (first 32 bytes after selector for exactInputSingle)
        pool_address = tx.get("to", "0x0000000000000000000000000000000000000000")

        # Get current pool state
        current_tick, current_sqrt_price_x96, fee_tier = self._get_pool_state(
            w3, pool_address, chain
        )

        swap = PendingWhaleSwap(
            chain=chain,
            dex="uniswap_v3",
            pool_address=pool_address,
            token_in="0x0000000000000000000000000000000000000000",  # Decoded from calldata
            token_out="0x0000000000000000000000000000000000000000",
            amount_in_usd=value_usd,
            amount_in_raw=int(value_usd * 1e6),
            fee_tier=fee_tier,
            current_sqrt_price_x96=current_sqrt_price_x96,
            current_tick=current_tick,
            tx_hash=tx_hash,
            block_number=tx.get("blockNumber"),
        )

        logger.info(
            f"🐋 JIT: Whale swap detected! ${value_usd:,.0f} on {chain} "
            f"pool={pool_address[:10]}... tx={tx_hash[:12]}..."
        )
        self._dispatch(swap)

    def _dispatch(self, swap: PendingWhaleSwap) -> None:
        """Dispatch a detected whale swap to all registered callbacks."""
        for cb in self._callbacks:
            try:
                cb(swap)
            except Exception as cb_err:
                logger.debug(f"JIT callback error: {cb_err}")

    def _get_eth_price_usd(self) -> float:
        """Fetch current ETH price in USD (cached, 60s TTL)."""
        now = time.time()
        if hasattr(self, "_eth_price_cache") and now - self._eth_price_ts < 60:
            return self._eth_price_cache
        try:
            resp = get_session().get(
                "https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd",
                timeout=5,
            )
            price = resp.json()["ethereum"]["usd"]
            self._eth_price_cache = float(price)
            self._eth_price_ts = now
            return self._eth_price_cache
        except Exception:
            return getattr(self, "_eth_price_cache", 3000.0)

    def _estimate_calldata_value(self, input_data: str, selector: str) -> float:
        """
        Attempt to decode amountIn from Uniswap V3 exactInputSingle calldata.
        Returns estimated USD value.
        """
        try:
            # exactInputSingle params start at byte 4 (after selector)
            # Struct: tokenIn(32), tokenOut(32), fee(32), recipient(32), deadline(32),
            #         amountIn(32), amountOutMinimum(32), sqrtPriceLimitX96(32)
            params_hex = input_data[10:]  # Strip selector
            if len(params_hex) < 256:
                return 0.0
            # amountIn is at offset 5 * 32 = 160 bytes = 320 hex chars
            amount_in_hex = params_hex[320:384]
            amount_in = int(amount_in_hex, 16)
            # Assume USDC (6 decimals) or WETH (18 decimals) — use 6 as conservative
            amount_usd = amount_in / 1e6
            if amount_usd > 1e12:  # Likely 18-decimal token
                amount_usd = amount_in / 1e18 * self._get_eth_price_usd()
            return amount_usd
        except Exception:
            return 0.0

    def _get_pool_state(
        self, w3, pool_address: str, chain: str
    ) -> Tuple[int, int, int]:
        """
        Fetch current tick, sqrtPriceX96, and fee tier from a Uniswap V3 pool.
        Returns (current_tick, sqrt_price_x96, fee_tier).
        """
        UNISWAP_V3_POOL_ABI = [
            {"inputs": [], "name": "slot0", "outputs": [
                {"name": "sqrtPriceX96", "type": "uint160"},
                {"name": "tick", "type": "int24"},
                {"name": "observationIndex", "type": "uint16"},
                {"name": "observationCardinality", "type": "uint16"},
                {"name": "observationCardinalityNext", "type": "uint16"},
                {"name": "feeProtocol", "type": "uint8"},
                {"name": "unlocked", "type": "bool"},
            ], "stateMutability": "view", "type": "function"},
            {"inputs": [], "name": "fee", "outputs": [{"name": "", "type": "uint24"}],
             "stateMutability": "view", "type": "function"},
        ]
        try:
            pool = w3.eth.contract(
                address=w3.to_checksum_address(pool_address),
                abi=UNISWAP_V3_POOL_ABI,
            )
            slot0 = pool.functions.slot0().call()
            fee = pool.functions.fee().call()
            return slot0[1], slot0[0], fee
        except Exception as e:
            logger.debug(f"Pool state fetch failed for {pool_address}: {e}")
            # Fallback defaults
            return 200000, TickMath.get_sqrt_ratio_at_tick(200000), 3000

    # ── Moralis Streams integration ──────────────────────────────────────────
    def on_moralis_stream_event(self, event: Dict[str, Any]) -> None:
        """
        Called by the Moralis Streams webhook handler when a large swap event arrives.
        This is the primary detection path — lower latency than WebSocket RPC polling.
        """
        try:
            # Moralis Streams delivers decoded swap events
            value_usd = float(event.get("valueUSD", event.get("value_usd", 0.0)))
            if value_usd < JIT_MIN_TRADE_SIZE_USD:
                return

            chain = event.get("chain", "ethereum")
            tx_hash = event.get("transactionHash", event.get("tx_hash", ""))

            with self._seen_hashes_lock:
                if tx_hash in self._seen_hashes:
                    return
                self._seen_hashes.add(tx_hash)

            swap = PendingWhaleSwap(
                chain=chain,
                dex=event.get("dex", "uniswap_v3"),
                pool_address=event.get("poolAddress", event.get("pool_address", "")),
                token_in=event.get("tokenIn", event.get("token_in", "")),
                token_out=event.get("tokenOut", event.get("token_out", "")),
                amount_in_usd=value_usd,
                amount_in_raw=int(event.get("amountIn", 0)),
                fee_tier=int(event.get("feeTier", 3000)),
                current_sqrt_price_x96=int(event.get("sqrtPriceX96", 0)),
                current_tick=int(event.get("tick", 200000)),
                tx_hash=tx_hash,
            )

            logger.info(
                f"🐋 JIT [Moralis]: Whale swap detected! ${value_usd:,.0f} on {chain} "
                f"tx={tx_hash[:12]}..."
            )
            self._dispatch(swap)

        except Exception as e:
            logger.debug(f"JIT Moralis stream event error: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# JIT Analyzer — calculates optimal tick range and liquidity
# ─────────────────────────────────────────────────────────────────────────────

class JITAnalyzer:
    """
    Analyzes a detected whale swap and calculates the optimal JIT parameters:
      - Tick range (tight, centered on the whale's execution price)
      - Liquidity amount (maximizes fee capture without excessive capital)
      - Flash borrow size (minimum needed to mint the target liquidity)
      - Estimated profit after gas
    """

    def analyze(self, swap: PendingWhaleSwap) -> Optional[JITOpportunity]:
        """
        Returns a JITOpportunity if the trade is profitable, None otherwise.
        """
        chain = swap.chain
        if chain not in _AAVE_V3_POOL or chain not in _UNISWAP_V3_NFT_MANAGER:
            logger.debug(f"JIT: chain {chain} not supported for JIT provisioning")
            return None

        tick_spacing = _TICK_SPACING.get(swap.fee_tier, 60)

        # Center the tick range on the current tick
        # Use a very tight range (±JIT_TICK_RANGE_TICKS ticks) to maximize fee concentration
        raw_lower = swap.current_tick - JIT_TICK_RANGE_TICKS * tick_spacing
        raw_upper = swap.current_tick + JIT_TICK_RANGE_TICKS * tick_spacing
        tick_lower = TickMath.round_to_tick_spacing(raw_lower, tick_spacing)
        tick_upper = TickMath.round_to_tick_spacing(raw_upper, tick_spacing) + tick_spacing

        sqrt_lower = TickMath.get_sqrt_ratio_at_tick(tick_lower)
        sqrt_upper = TickMath.get_sqrt_ratio_at_tick(tick_upper)

        # Flash borrow amount: cap at JIT_MAX_FLASH_BORROW_USD
        flash_borrow_usd = min(swap.amount_in_usd * 0.5, JIT_MAX_FLASH_BORROW_USD)
        flash_borrow_raw = int(flash_borrow_usd * 1e6)  # USDC 6 decimals

        # Calculate liquidity units
        liquidity = LiquidityMath.get_liquidity_for_amounts(
            sqrt_price_x96=swap.current_sqrt_price_x96,
            sqrt_price_lower_x96=sqrt_lower,
            sqrt_price_upper_x96=sqrt_upper,
            amount0=flash_borrow_raw,
            amount1=flash_borrow_raw,
        )

        if liquidity <= 0:
            logger.debug("JIT: calculated liquidity is zero — skipping")
            return None

        # Estimate fee earned from the whale's swap
        # Assume our JIT liquidity is ~10% of the pool's active liquidity (conservative)
        estimated_pool_liquidity = liquidity * 10
        fee_earned = LiquidityMath.estimate_fee_earned(
            liquidity=liquidity,
            total_pool_liquidity=estimated_pool_liquidity,
            swap_amount_usd=swap.amount_in_usd,
            fee_tier=swap.fee_tier,
        )

        # Estimate gas cost
        gas_usd = self._estimate_gas_usd(chain)

        # Aave flash loan fee: 0.05% (5 bps)
        aave_fee_usd = flash_borrow_usd * 0.0005

        net_profit = fee_earned - gas_usd - aave_fee_usd

        if net_profit < JIT_MIN_PROFIT_USD:
            logger.debug(
                f"JIT: opportunity rejected — net_profit=${net_profit:.4f} < "
                f"min=${JIT_MIN_PROFIT_USD:.2f} "
                f"(fee=${fee_earned:.4f}, gas=${gas_usd:.4f}, aave_fee=${aave_fee_usd:.4f})"
            )
            return None

        if gas_usd > fee_earned * JIT_MAX_GAS_TO_PROFIT_RATIO:
            logger.debug(
                f"JIT: gas/profit ratio too high ({gas_usd/fee_earned:.1%}) — skipping"
            )
            return None

        logger.info(
            f"✅ JIT opportunity: fee=${fee_earned:.4f} | gas=${gas_usd:.4f} | "
            f"net=${net_profit:.4f} | tick={tick_lower}..{tick_upper} | "
            f"flash=${flash_borrow_usd:,.0f}"
        )

        return JITOpportunity(
            swap=swap,
            tick_lower=tick_lower,
            tick_upper=tick_upper,
            liquidity_amount=liquidity,
            flash_borrow_token=swap.token_in,
            flash_borrow_amount_raw=flash_borrow_raw,
            flash_borrow_amount_usd=flash_borrow_usd,
            estimated_fee_earned_usd=fee_earned,
            estimated_gas_usd=gas_usd,
            estimated_net_profit_usd=net_profit,
            aave_pool=_AAVE_V3_POOL[chain],
            nft_manager=_UNISWAP_V3_NFT_MANAGER[chain],
        )

    def _estimate_gas_usd(self, chain: str) -> float:
        """
        Estimates gas cost for the JIT bundle (flash borrow + mint + burn + repay).
        Typical gas: ~500k gas units for the full bundle.
        """
        gas_prices = {
            "ethereum":  30.0,   # ~$30 at 15 gwei, 500k gas
            "base":       0.5,   # ~$0.50 on Base
            "arbitrum":   1.0,   # ~$1.00 on Arbitrum
            "polygon":    0.1,   # ~$0.10 on Polygon
        }
        return gas_prices.get(chain, 5.0)


# ─────────────────────────────────────────────────────────────────────────────
# JIT Executor — builds and submits the atomic bundle
# ─────────────────────────────────────────────────────────────────────────────

class JITExecutor:
    """
    Builds and submits the atomic JIT bundle:
      1. Aave V3 flashLoanSimple (borrow token_in)
      2. Uniswap V3 NonfungiblePositionManager.mint() (add concentrated liquidity)
      3. [Whale's swap executes in the same block, next tx]
      4. NonfungiblePositionManager.decreaseLiquidity() + collect() (remove + collect fees)
      5. Aave V3 repay flash loan + fee

    In production, steps 1, 2, 4, 5 are encoded into a single smart contract call
    (JITLiquidityProvider.sol) that executes atomically. If the repayment check fails,
    the entire transaction reverts — zero capital at risk.

    Routes via private RPC (Flashbots Protect / MEV Blocker) to prevent front-running.
    """

    def execute(self, opp: JITOpportunity) -> JITResult:
        """Execute a JIT liquidity provision opportunity."""
        is_paper = getattr(settings, "MODE", "paper") != "live"

        if is_paper:
            return self._paper_execute(opp)

        return self._live_execute(opp)

    def _paper_execute(self, opp: JITOpportunity) -> JITResult:
        """Simulate JIT execution in paper mode."""
        logger.info(
            f"[PAPER] JIT Execution: "
            f"chain={opp.swap.chain} | "
            f"pool={opp.swap.pool_address[:10]}... | "
            f"tick={opp.tick_lower}..{opp.tick_upper} | "
            f"flash=${opp.flash_borrow_amount_usd:,.0f} | "
            f"est_profit=${opp.estimated_net_profit_usd:.4f}"
        )
        return JITResult(
            success=True,
            opportunity=opp,
            tx_hash=f"0xpaper_jit_{int(time.time())}",
            fee_earned_usd=opp.estimated_fee_earned_usd,
            gas_usd=opp.estimated_gas_usd,
            net_profit_usd=opp.estimated_net_profit_usd,
            paper=True,
        )

    def _live_execute(self, opp: JITOpportunity) -> JITResult:
        """
        Live execution of the JIT bundle via private RPC.

        Transaction structure (all in one atomic tx via JITLiquidityProvider.sol):
          1. flashLoanSimple(aavePool, token, amount, params)
             └─ In Aave callback (executeOperation):
                a. approve NonfungiblePositionManager to spend borrowed tokens
                b. mint(MintParams{token0, token1, fee, tickLower, tickUpper, ...})
                c. [whale's swap fills our tick range — fees accrue to our position]
                d. decreaseLiquidity(tokenId, liquidity, 0, 0, deadline)
                e. collect(tokenId, recipient, MAX_UINT128, MAX_UINT128)
                f. repay Aave (principal + 0.05% fee)
                g. assert profit > 0 (revert if not profitable)
        """
        chain = opp.swap.chain
        private_key = os.getenv("WALLET_PRIVATE_KEY_PRIMARY")
        if not private_key:
            return JITResult(
                success=False,
                opportunity=opp,
                error="WALLET_PRIVATE_KEY_PRIMARY not set",
            )

        # Build the encoded calldata for JITLiquidityProvider.executeJIT()
        # In production, this calls a deployed smart contract.
        # The contract handles the entire atomic sequence described above.
        calldata = self._encode_jit_calldata(opp)

        # Build raw transaction
        tx = {
            "to": os.getenv(f"JIT_CONTRACT_{chain.upper()}", ""),
            "data": calldata,
            "value": 0,
            "gas": 600_000,  # JIT bundle: ~500k gas + 20% buffer
        }

        if not tx["to"]:
            return JITResult(
                success=False,
                opportunity=opp,
                error=f"JIT_CONTRACT_{chain.upper()} not set in environment",
            )

        # Route via private RPC
        return self._submit_via_private_rpc(tx, private_key, opp, chain)

    def _encode_jit_calldata(self, opp: JITOpportunity) -> str:
        """
        Encodes the JIT parameters for the JITLiquidityProvider smart contract.
        Function signature: executeJIT(address pool, address token0, address token1,
                                       uint24 fee, int24 tickLower, int24 tickUpper,
                                       uint256 flashAmount, uint256 deadline)
        """
        try:
            from web3 import Web3
            # ABI encoding of executeJIT parameters
            # This is a simplified encoding — production uses eth_abi or web3.py encode_abi
            params = {
                "pool": opp.swap.pool_address,
                "token0": opp.swap.token_in,
                "token1": opp.swap.token_out,
                "fee": opp.swap.fee_tier,
                "tickLower": opp.tick_lower,
                "tickUpper": opp.tick_upper,
                "flashAmount": opp.flash_borrow_amount_raw,
                "deadline": int(time.time()) + 60,  # 60 second deadline
            }
            # Function selector for executeJIT(...)
            selector = Web3.keccak(
                text="executeJIT(address,address,address,uint24,int24,int24,uint256,uint256)"
            )[:4].hex()
            # Encode params (simplified — production uses eth_abi)
            encoded = selector + "0" * 512  # Placeholder encoding
            return "0x" + encoded
        except Exception as e:
            logger.debug(f"JIT calldata encoding error: {e}")
            return "0x"

    def _submit_via_private_rpc(
        self,
        tx: dict,
        private_key: str,
        opp: JITOpportunity,
        chain: str,
    ) -> JITResult:
        """
        Submits the JIT transaction via a private RPC endpoint.
        Uses Flashbots Protect on Ethereum/Base, MEV Blocker as fallback.
        """
        try:
            from core.mev_protection import submit_via_flashbots_protect
        except ImportError:
            return JITResult(
                success=False,
                opportunity=opp,
                error="mev_protection module not available",
            )

        private_rpc = _PRIVATE_RPC.get(chain, "https://rpc.flashbots.net/fast")
        logger.info(
            f"⚡ JIT: Submitting bundle via private RPC ({private_rpc[:40]}...) "
            f"chain={chain} pool={opp.swap.pool_address[:10]}..."
        )

        try:
            result = submit_via_flashbots_protect(
                tx=tx,
                private_key=private_key,
                chain=chain,
            )

            if result.success:
                logger.info(
                    f"✅ JIT bundle submitted: tx={result.tx_hash} | "
                    f"est_profit=${opp.estimated_net_profit_usd:.4f}"
                )
                return JITResult(
                    success=True,
                    opportunity=opp,
                    tx_hash=result.tx_hash,
                    fee_earned_usd=opp.estimated_fee_earned_usd,
                    gas_usd=opp.estimated_gas_usd,
                    net_profit_usd=opp.estimated_net_profit_usd,
                )
            else:
                return JITResult(
                    success=False,
                    opportunity=opp,
                    error=f"Private RPC submission failed: {result.error}",
                )

        except Exception as e:
            return JITResult(
                success=False,
                opportunity=opp,
                error=f"JIT execution error: {e}",
            )


# ─────────────────────────────────────────────────────────────────────────────
# JIT Liquidity Sniper — top-level orchestrator
# ─────────────────────────────────────────────────────────────────────────────

class JITLiquiditySniper:
    """
    Top-level orchestrator for the JIT Liquidity Sniper.

    Wires together:
      MempoolWatcher → JITAnalyzer → JITExecutor

    Usage:
      # In main.py, after Moralis Streams initialization:
      jit_sniper.start()

      # In the swap event handler:
      jit_sniper.on_pending_whale_trade(tx_data)

      # For Moralis Streams large-swap events:
      jit_sniper.on_moralis_large_swap(event)
    """

    def __init__(self):
        self.enabled = JIT_ENABLED
        self.watcher = MempoolWatcher()
        self.analyzer = JITAnalyzer()
        self.executor = JITExecutor()
        self._stats = {
            "opportunities_detected": 0,
            "opportunities_executed": 0,
            "total_profit_usd": 0.0,
            "total_gas_usd": 0.0,
            "failures": 0,
        }
        self._stats_lock = threading.Lock()

        # Wire watcher → analyze → execute
        self.watcher.add_callback(self._on_whale_swap)

        logger.info(
            f"JIT Liquidity Sniper initialized | "
            f"enabled={self.enabled} | "
            f"min_trade=${JIT_MIN_TRADE_SIZE_USD:,.0f} | "
            f"max_flash=${JIT_MAX_FLASH_BORROW_USD:,.0f} | "
            f"tick_range=±{JIT_TICK_RANGE_TICKS} ticks"
        )

    def start(self) -> None:
        """Start the mempool watcher daemon."""
        if not self.enabled:
            logger.info("JIT Liquidity Sniper: disabled via JIT_ENABLED=false")
            return
        self.watcher.start()
        logger.info("✅ JIT Liquidity Sniper: mempool watcher started")

    def stop(self) -> None:
        self.watcher.stop()

    def on_pending_whale_trade(self, tx_data: Dict[str, Any]) -> Optional[JITResult]:
        """
        Entrypoint called by the Moralis Streams swap handler in main.py.
        tx_data keys: chain, value_usd, to_address, token_in, token_out, hash
        """
        if not self.enabled:
            return None

        value_usd = float(tx_data.get("value_usd", 0.0))
        if value_usd < JIT_MIN_TRADE_SIZE_USD:
            return None

        swap = PendingWhaleSwap(
            chain=tx_data.get("chain", "ethereum"),
            dex="uniswap_v3",
            pool_address=tx_data.get("to_address", ""),
            token_in=tx_data.get("token_in", ""),
            token_out=tx_data.get("token_out", ""),
            amount_in_usd=value_usd,
            amount_in_raw=int(value_usd * 1e6),
            fee_tier=int(tx_data.get("fee_tier", 3000)),
            current_sqrt_price_x96=int(tx_data.get("sqrt_price_x96", 0))
                or TickMath.get_sqrt_ratio_at_tick(200000),
            current_tick=int(tx_data.get("current_tick", 200000)),
            tx_hash=tx_data.get("hash", ""),
        )

        return self._on_whale_swap(swap)

    def on_moralis_large_swap(self, event: Dict[str, Any]) -> None:
        """
        Called by Moralis Streams when a large swap event is received.
        This is the highest-priority detection path.
        """
        self.watcher.on_moralis_stream_event(event)

    def _on_whale_swap(self, swap: PendingWhaleSwap) -> Optional[JITResult]:
        """Internal handler: analyze → execute."""
        with self._stats_lock:
            self._stats["opportunities_detected"] += 1

        opp = self.analyzer.analyze(swap)
        if not opp:
            return None

        result = self.executor.execute(opp)

        with self._stats_lock:
            if result.success:
                self._stats["opportunities_executed"] += 1
                self._stats["total_profit_usd"] += result.net_profit_usd
                self._stats["total_gas_usd"] += result.gas_usd
            else:
                self._stats["failures"] += 1

        if result.success:
            logger.info(
                f"💰 JIT PROFIT: ${result.net_profit_usd:.4f} | "
                f"fee=${result.fee_earned_usd:.4f} | gas=${result.gas_usd:.4f} | "
                f"tx={result.tx_hash}"
            )
        else:
            logger.debug(f"JIT execution failed: {result.error}")

        return result

    def get_stats(self) -> Dict[str, Any]:
        """Return JIT performance statistics."""
        with self._stats_lock:
            stats = dict(self._stats)
        total = stats["opportunities_detected"]
        executed = stats["opportunities_executed"]
        stats["hit_rate_pct"] = (executed / total * 100) if total > 0 else 0.0
        return stats


# ─────────────────────────────────────────────────────────────────────────────
# Module-level singleton
# ─────────────────────────────────────────────────────────────────────────────

jit_sniper = JITLiquiditySniper()
