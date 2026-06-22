"""
core/hyperliquid_executor.py — Perpetual Futures Execution on Hyperliquid DEX.

Routes trading signals to Hyperliquid's on-chain perp exchange instead of
on-chain spot swaps. Benefits:
  - Zero gas fees (only taker/maker fees)
  - Up to 50x leverage (we cap at 3-5x for risk management)
  - USDC-only margin (no need for native tokens on each chain)
  - Automatic TP/SL management
  - Can SHORT as well as long

Integration:
  main.py fastlane_worker → HyperliquidExecutor.open_long()
  when on-chain swap would fail (no gas/balance) but token has HL perp listing.
"""

from __future__ import annotations

import json
import logging
import os
import time
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from config import settings

# ─────────────────────────────────────────────────────────────────────────────
# Trailing stop state persistence
# Survives bot restarts — highest_price, sl_order_id, etc. are reloaded on boot
# ─────────────────────────────────────────────────────────────────────────────
_TRAILING_STATE_FILE = (
    Path(os.getenv("DASHBOARD_STATE_DIR", "./data/dashboard"))
    / "hl_trailing_state.json"
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Known Hyperliquid perp tickers (refreshed on startup from HL API)
# These are the tokens that have perpetual futures on Hyperliquid
# ─────────────────────────────────────────────────────────────────────────────
_HL_PERP_TICKERS: set[str] = set()
_HL_TICKER_LOCK = threading.Lock()

# ─────────────────────────────────────────────────────────────────────────────
# Known HL order rejection reasons that are expected/non-critical.
# These are downgraded from logger.error → logger.warning to suppress Sentry noise.
# ─────────────────────────────────────────────────────────────────────────────
_HL_EXPECTED_REJECTIONS = (
    # Price deviation / liquidity rejections
    "Order price cannot be more than 95% away from the reference price",
    "Order could not immediately match against any resting orders",
    "Order could not be placed",
    "Insufficient liquidity",
    "Market order could not be filled",
    # Position / margin rejections
    "Reduce only order would increase position",
    "Post only order would have immediately matched",
    "Insufficient margin",
    "Would exceed max leverage",
    "Position size too small",
    "Notional too small",
    "Max position size exceeded",
    # Rate / duplicate rejections
    "Duplicate order",
    "Too many open orders",
    "Order size is too small",
)


@dataclass
class HLPosition:
    """Tracks an open Hyperliquid position."""
    coin: str
    side: str  # "long" or "short"
    entry_price: float
    size: float  # in coin units
    size_usd: float
    leverage: int
    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    opened_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    pnl: float = 0.0
    # ── Trailing Profit-Lock state ────────────────────────────────────────────
    # Persisted to hl_trailing_state.json so restarts resume where they left off.
    highest_price: float = 0.0          # Peak mark price seen (longs)
    lowest_price: float = float("inf")  # Trough mark price seen (shorts)
    trailing_stop_active: bool = False  # True once ROE > 5% threshold hit
    sl_order_id: Optional[int] = None   # On-chain SL order ID (int on HL)
    tp_order_id: Optional[int] = None   # On-chain TP order ID (for reference)


class HyperliquidExecutor:
    """
    Executes leveraged perpetual futures trades on Hyperliquid DEX.
    
    Designed as a zero-gas alternative to on-chain spot swaps.
    Automatically manages TP/SL orders for every position.
    """
    
    # Global cache to prevent burst 429s across multiple instances
    _global_mids_cache: dict = {}
    _global_mids_cache_ts: float = 0.0
    _GLOBAL_MIDS_CACHE_TTL: float = 3.0  # seconds
    _global_mids_lock = threading.Lock()

    # Balance cache — 30s TTL prevents 3x get_balance() calls per scan cycle
    _global_balance_cache: dict = {}
    _global_balance_cache_ts: float = 0.0
    _GLOBAL_BALANCE_CACHE_TTL: float = 30.0  # seconds
    _global_balance_lock = threading.Lock()

    def __init__(self, sub_account_address: Optional[str] = None):
        self.enabled = settings.HYPERLIQUID_ENABLED
        self.wallet_address = settings.HYPERLIQUID_WALLET_ADDRESS
        self.private_key = settings.HYPERLIQUID_PRIVATE_KEY
        self.sub_account_address = sub_account_address or None
        self.default_leverage = settings.HYPERLIQUID_DEFAULT_LEVERAGE
        # Override the env-based flat limits to accommodate Kelly Sizing (up to $2500 per trade)
        # while keeping the overall total exposure scaled accordingly.
        self.max_position_usd = max(settings.HYPERLIQUID_MAX_POSITION_USD, 2500.0)
        self.max_total_exposure = max(settings.HYPERLIQUID_MAX_TOTAL_EXPOSURE, 15000.0)
        self.max_positions = settings.HYPERLIQUID_MAX_POSITIONS
        self.stop_loss_pct = settings.HYPERLIQUID_STOP_LOSS_PCT
        self.take_profit_pct = settings.HYPERLIQUID_TAKE_PROFIT_PCT
        self.daily_loss_limit = settings.HYPERLIQUID_DAILY_LOSS_LIMIT
        self.min_gem_score = getattr(settings, "HYPERLIQUID_MIN_GEM_SCORE", 80)
        self.use_testnet = settings.HYPERLIQUID_USE_TESTNET

        # State
        self.positions: dict[str, HLPosition] = {}
        self.daily_pnl: float = 0.0
        self.daily_pnl_reset_date: str = ""
        self._info = None
        self._exchange = None
        self._initialized = False
        self._lock = threading.Lock()
        self._rate_limit_until: float = 0.0  # Timestamp until which we refuse signed requests (cumulative rate limit cooldown)

        if self.enabled and self.wallet_address and self.private_key:
            self._initialized = True

    def _execute_api(self, func, *args, **kwargs):
        """Execute SDK call with exponential backoff for rate limits."""
        import time

        # Proactive cooldown: refuse signed requests while cumulative rate limit is active
        if time.time() < self._rate_limit_until:
            remaining = int(self._rate_limit_until - time.time())
            logger.debug(f"Hyperliquid: rate limit cooldown active ({remaining}s remaining) — skipping API call")
            return {"status": "err", "response": f"Rate limit cooldown active ({remaining}s remaining)"}

        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                result = func(*args, **kwargs)
                if isinstance(result, dict) and result.get("status") == "err":
                    err_msg = str(result.get("response", "")).lower()
                    if "too many" in err_msg or "rate limit" in err_msg or "429" in err_msg:
                        # Cumulative rate limit — long cooldown (10 minutes)
                        if "cumulative" in err_msg:
                            self._rate_limit_until = time.time() + 600  # 10-minute cooldown
                            logger.warning(
                                f"⚠️ Hyperliquid CUMULATIVE rate limit hit — cooldown until "
                                f"{time.strftime('%H:%M:%S', time.localtime(self._rate_limit_until))}. "
                                f"All signed requests paused for 10 minutes."
                            )
                            return result  # Don't retry — just stop
                        raise Exception(f"Hyperliquid API Rate Limit: {result}")
                return result
            except Exception as e:
                err_msg = str(e).lower()
                if "too many" in err_msg or "rate limit" in err_msg or "429" in err_msg:
                    if "cumulative" in err_msg:
                        self._rate_limit_until = time.time() + 600
                        logger.warning(
                            f"⚠️ Hyperliquid CUMULATIVE rate limit hit — 10-minute cooldown active"
                        )
                        return {"status": "err", "response": str(e)}
                    if attempt == max_retries:
                        logger.error(f"Hyperliquid rate limit failed after {max_retries} attempts.")
                        raise
                    sleep_time = 2 ** attempt
                    logger.warning(f"Hyperliquid API rate limit hit, sleeping {sleep_time}s... (Attempt {attempt}/{max_retries})")
                    time.sleep(sleep_time)
                else:
                    raise

    def _initialize_sdk(self) -> None:
        """Initialize Hyperliquid SDK clients with retry for transient failures."""
        import time as _time

        try:
            from hyperliquid.info import Info
            from hyperliquid.exchange import Exchange
            from hyperliquid.utils import constants
        except ImportError:
            logger.error("❌ hyperliquid-python-sdk not installed — pip install hyperliquid-python-sdk")
            self.enabled = False
            return

        max_retries = 5
        for attempt in range(1, max_retries + 1):
            try:
                api_url = constants.TESTNET_API_URL if self.use_testnet else constants.MAINNET_API_URL

                self._info = Info(api_url, skip_ws=False)
                # Ensure WS is connected before subscribing
                _time.sleep(1)

                # Initialize Exchange with private key for signing
                from eth_account import Account
                _wallet = Account.from_key(self.private_key)
                self._exchange = Exchange(
                    wallet=_wallet,
                    base_url=api_url,
                    account_address=self.wallet_address,
                    vault_address=self.sub_account_address,
                )

                # Load available perp tickers
                self._refresh_perp_tickers()

                # Sync existing positions
                self._sync_positions()

                # Setup Websocket subscriptions
                self._setup_websockets()

                self._initialized = True
                mode = "TESTNET" if self.use_testnet else "MAINNET"
                vault_tag = f" | vault={self.sub_account_address[:10]}..." if self.sub_account_address else ""
                logger.info(
                    f"🟢 Hyperliquid executor initialized ({mode}) | "
                    f"wallet={self.wallet_address[:10]}...{vault_tag} | "
                    f"leverage={self.default_leverage}x | "
                    f"max_pos=${self.max_position_usd} | "
                    f"perps_available={len(_HL_PERP_TICKERS)}"
                )
                return  # Success — exit retry loop

            except Exception as e:
                err_str = str(e).lower()
                is_transient = any(k in err_str for k in ("429", "rate limit", "too many", "timeout", "connection", "503", "502"))

                if is_transient and attempt < max_retries:
                    backoff = 2 ** attempt  # 2s, 4s, 8s, 16s, 32s
                    logger.warning(
                        f"⚠️ Hyperliquid init transient error (attempt {attempt}/{max_retries}), "
                        f"retrying in {backoff}s: {e}"
                    )
                    _time.sleep(backoff)
                elif is_transient:
                    # All retries exhausted but error is transient — do NOT disable permanently.
                    # is_available() will call _initialize_sdk() again next cycle.
                    logger.error(
                        f"❌ Hyperliquid init failed after {max_retries} attempts (transient): {e}. "
                        f"Will retry on next is_available() call."
                    )
                    return
                else:
                    # Non-transient error (bad key, wrong wallet, SDK bug) — disable permanently
                    logger.error(f"❌ Hyperliquid init failed (permanent): {e}")
                    self.enabled = False
                    return

    def _refresh_perp_tickers(self) -> None:
        """Load all available perp tickers from Hyperliquid."""
        global _HL_PERP_TICKERS
        if _HL_PERP_TICKERS:
            return  # Already loaded globally
        try:
            meta = self._execute_api(self._info.meta)
            tickers = set()
            for asset in meta.get("universe", []):
                name = asset.get("name", "")
                if name:
                    tickers.add(name.upper())

            with _HL_TICKER_LOCK:
                _HL_PERP_TICKERS = tickers

            logger.info(f"Hyperliquid: {len(tickers)} perp tickers loaded")
        except Exception as e:
            logger.warning(f"Hyperliquid: failed to load tickers: {e}")

    def _sync_positions(self) -> None:
        """Sync open positions from Hyperliquid account state."""
        try:
            state = self._execute_api(self._info.user_state, self.wallet_address)
            positions = state.get("assetPositions", [])
            for pos in positions:
                p = pos.get("position", {})
                coin = p.get("coin", "")
                szi = float(p.get("szi", 0))
                if szi == 0:
                    continue
                entry_px = float(p.get("entryPx", 0))
                leverage_info = p.get("leverage") or {}
                # FIX (PYTHON-S): leverage_info.get("value") can return None when the key
                # exists with a null value in the HL API response (cross-margin accounts).
                # Use `or self.default_leverage` to guard against None before int().
                raw_lev = leverage_info.get("value")
                lev = int(raw_lev) if raw_lev is not None else self.default_leverage
                unrealized_pnl = float(p.get("unrealizedPnl", 0))

                self.positions[coin] = HLPosition(
                    coin=coin,
                    side="long" if szi > 0 else "short",
                    entry_price=entry_px,
                    size=abs(szi),
                    size_usd=abs(szi) * entry_px,
                    leverage=lev,
                    pnl=unrealized_pnl,
                )
            if self.positions:
                logger.info(f"Hyperliquid: synced {len(self.positions)} open positions")
            # Restore trailing stop state from disk (survives restarts)
            self._load_trailing_state()
        except Exception as e:
            logger.warning(f"Hyperliquid: position sync failed: {e}")

    def _setup_websockets(self) -> None:
        """Setup websocket subscriptions for real-time updates."""
        try:
            self._info.subscribe(
                {"type": "userFills", "user": self.wallet_address},
                self._handle_user_fills
            )
            logger.info("Hyperliquid: Subscribed to userFills websocket")
        except Exception as e:
            logger.error(f"Hyperliquid: Failed to subscribe to websockets: {e}")

    def _handle_user_fills(self, message: dict) -> None:
        """Handle incoming userFills websocket messages."""
        try:
            data = message.get("data", {})
            fills = data.get("fills", [])
            if not fills:
                return
            
            for fill in fills:
                coin = fill.get("coin")
                sz = float(fill.get("sz", 0))
                px = float(fill.get("px", 0))
                side = fill.get("side")
                is_close = fill.get("dir") == "Close Long" or fill.get("dir") == "Close Short"
                
                if is_close and coin in self.positions:
                    logger.info(f"Hyperliquid WS Fill: Closed {sz} {coin} @ {px}")
                    # In a full implementation, we'd partially or fully close the tracked position here.
                    # For now, we rely on the main loop's sync_positions to clean it up,
                    # but we can log the real-time event.
        except Exception as e:
            logger.debug(f"Hyperliquid WS userFills error: {e}")

    def _post_twap(self, symbol: str, is_buy: bool, coin_size: float, minutes: int = 60, randomize: bool = True, reduce_only: bool = False) -> dict:
        """Construct and send a raw TWAP L1 action to Hyperliquid."""
        from hyperliquid.utils.signing import sign_l1_action, get_timestamp_ms
        from hyperliquid.utils.constants import MAINNET_API_URL
        
        asset_index = self._info.name_to_asset(symbol)
        
        twap_action = {
            "type": "twapOrder",
            "twap": {
                "a": asset_index,
                "b": is_buy,
                "s": str(coin_size),
                "r": reduce_only,
                "m": minutes,
                "t": randomize
            }
        }
        
        timestamp = get_timestamp_ms()
        signature = sign_l1_action(
            self._exchange.wallet,
            twap_action,
            self._exchange.vault_address,
            timestamp,
            self._exchange.expires_after,
            self._exchange.base_url == MAINNET_API_URL,
        )
        return self._exchange._post_action(twap_action, signature, timestamp)

    def open_twap(self, symbol: str, side: str, size_usd: float, minutes: int = 60, leverage: Optional[int] = None) -> Optional[dict]:
        """Open a position over time using Hyperliquid's native TWAP to minimize slippage."""
        if not self.is_available():
            return None
            
        sym = _normalize_symbol(symbol)
        if not self.has_perp(sym):
            return None

        actual_size_usd = min(size_usd, self.max_position_usd)
        lev = leverage or self.default_leverage
        
        with self._lock:
            price = self.get_price(sym)
            if not price or price <= 0:
                logger.warning(f"Hyperliquid: no price for {sym} TWAP — skipping")
                return None

            is_cross = True
            self._execute_api(self._exchange.update_leverage, lev, sym, is_cross)

            notional = actual_size_usd * lev
            coin_size = notional / price
            sz_decimals = self._get_sz_decimals(sym)
            coin_size = round(coin_size, sz_decimals)

            if coin_size <= 0:
                return None

            logger.info(f"⏳ Hyperliquid TWAP {side.upper()} {sym} | {minutes} mins | size={coin_size} notional=${notional:.2f}")

            result = self._execute_api(
                self._post_twap,
                sym,
                side == "buy",
                coin_size,
                minutes=minutes,
                randomize=True,
                reduce_only=False
            )
            
            if not result or result.get("status") != "ok":
                logger.error(f"Hyperliquid TWAP failed for {sym}: {result}")
                return None
                
            return {"coin": sym, "size": coin_size, "minutes": minutes, "status": "twap_started"}

    def close_twap(self, symbol: str, minutes: int = 60) -> Optional[dict]:
        """Close an existing position over time using TWAP."""
        if not self.is_available():
            return None
            
        sym = _normalize_symbol(symbol)
        
        with self._lock:
            pos = self.positions.get(sym)
            if not pos:
                logger.warning(f"Hyperliquid: no open position to TWAP close for {sym}")
                return None
                
            logger.info(f"⏳ Hyperliquid TWAP CLOSE {sym} | {minutes} mins | size={pos.size}")
            
            result = self._execute_api(
                self._post_twap,
                sym,
                pos.side == "short", # If long, sell (False) to close. If short, buy (True) to close.
                pos.size,
                minutes=minutes,
                randomize=True,
                reduce_only=True
            )
            
            if not result or result.get("status") != "ok":
                logger.error(f"Hyperliquid TWAP CLOSE failed for {sym}: {result}")
                return None
                
            # Remove position from tracking immediately since TWAP is fully delegated to the exchange
            del self.positions[sym]
            self._save_trailing_state()
            
            return {"coin": sym, "status": "twap_close_started"}

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    def is_available(self) -> bool:
        """Check if executor is ready for trading. Initializes SDK on first call if needed."""
        if not self.enabled:
            return False
        if not self._initialized or self._exchange is None:
            self._initialize_sdk()
        return self.enabled and self._initialized and self._exchange is not None

    @staticmethod
    def has_perp(symbol: str) -> bool:
        """Check if a token has a Hyperliquid perpetual listing."""
        sym = _normalize_symbol(symbol)
        with _HL_TICKER_LOCK:
            return sym in _HL_PERP_TICKERS

    def get_balance(self, force_refresh: bool = False) -> dict:
        """Get account balance and margin info.

        Uses a 30-second TTL class-level cache to prevent burst 429 errors when
        get_balance() is called multiple times per scan cycle (position sizing,
        daily loss limit, and profit sweeper all call it independently).
        Pass force_refresh=True to bypass the cache (e.g., after a trade).

        Handles both Unified and Cross margin accounts.
        Unified accounts store funds in spot clearinghouse (spot_user_state),
        while Cross accounts use the regular user_state endpoint.
        """
        import time as _time
        if not self.is_available():
            return {"error": "not initialized"}

        # Return cached balance if within TTL and not forced
        with HyperliquidExecutor._global_balance_lock:
            now = _time.monotonic()
            if (
                not force_refresh
                and HyperliquidExecutor._global_balance_cache
                and (now - HyperliquidExecutor._global_balance_cache_ts) < HyperliquidExecutor._GLOBAL_BALANCE_CACHE_TTL
            ):
                return dict(HyperliquidExecutor._global_balance_cache)

        try:
            # Try Unified account first (spot_user_state)
            try:
                # 1. Spot user state to check unified balances
                spot_state = self._execute_api(self._info.spot_user_state, self.wallet_address)
                balances = spot_state.get("balances", [])
                usdc_balance = 0.0
                for b in balances:
                    if b.get("coin") in ("USDC", "USDT"):
                        usdc_balance += float(b.get("total", 0)) - float(b.get("hold", 0))
                if usdc_balance > 0:
                    logger.debug(f"Hyperliquid: Unified account balance=${usdc_balance:.2f}")
                    _result = {
                        "account_value": usdc_balance,
                        "total_margin_used": float(sum(float(b.get("hold", 0)) for b in balances)),
                        "withdrawable": usdc_balance,
                        "positions": 0,
                        "mode": "unified",
                    }
                    with HyperliquidExecutor._global_balance_lock:
                        HyperliquidExecutor._global_balance_cache = _result
                        HyperliquidExecutor._global_balance_cache_ts = _time.monotonic()
                    return _result
            except Exception:
                pass  # Fall through to Cross margin check

            # Cross margin fallback
            state = self._execute_api(self._info.user_state, self.wallet_address)
            margin = state.get("marginSummary", {})
            _result = {
                "account_value": float(margin.get("accountValue", 0)),
                "total_margin_used": float(margin.get("totalMarginUsed", 0)),
                "withdrawable": float(margin.get("withdrawable", 0)),
                "positions": len(state.get("assetPositions", [])),
                "mode": "cross",
            }
            with HyperliquidExecutor._global_balance_lock:
                HyperliquidExecutor._global_balance_cache = _result
                HyperliquidExecutor._global_balance_cache_ts = _time.monotonic()
            return _result
        except Exception as e:
            logger.warning(f"Hyperliquid balance check failed: {e}")
            # Return stale cache if available rather than an error dict
            with HyperliquidExecutor._global_balance_lock:
                if HyperliquidExecutor._global_balance_cache:
                    logger.debug("Returning stale balance cache after API failure")
                    return dict(HyperliquidExecutor._global_balance_cache)
            return {"error": str(e)}

    def get_price(self, symbol: str) -> Optional[float]:
        """Get current mid price for a perp.

        Uses a 3-second TTL cache on all_mids to prevent burst 429 errors when
        multiple positions are polled in rapid succession within the same cycle.
        The all_mids call is wrapped in _execute_api for exponential backoff on
        transient rate-limit hits.  If the refresh fails, returns the stale
        cached value instead of None so trailing-stop logic doesn't break.
        """
        if not self.is_available():
            return None
        try:
            sym = _normalize_symbol(symbol)
            now = time.monotonic()
            
            with HyperliquidExecutor._global_mids_lock:
                if now - HyperliquidExecutor._global_mids_cache_ts > HyperliquidExecutor._GLOBAL_MIDS_CACHE_TTL:
                    try:
                        mids = self._execute_api(self._info.all_mids)
                        if mids:
                            HyperliquidExecutor._global_mids_cache = mids
                            HyperliquidExecutor._global_mids_cache_ts = now
                    except Exception as refresh_err:
                        # Rate-limit or transient failure — use stale cache, don't crash
                        logger.warning(f"Hyperliquid mids refresh failed (using stale cache): {refresh_err}")
            
            return float(HyperliquidExecutor._global_mids_cache.get(sym, 0)) or None
        except Exception as e:
            logger.warning(f"Hyperliquid price fetch for {symbol}: {e}")
            return None

    def open_long(
        self,
        symbol: str,
        size_usd: float,
        leverage: Optional[int] = None,
        gem_score: float = 0,
    ) -> Optional[dict]:
        """
        Open a leveraged long position on Hyperliquid.
        
        Args:
            symbol: Token symbol (e.g., "BTC", "ETH", "PEPE")
            size_usd: Position size in USD (before leverage)
            leverage: Override default leverage
            gem_score: Signal strength (for logging)
            
        Returns:
            Fill info dict or None on failure
        """
        return self._open_position(symbol, "buy", size_usd, leverage, gem_score)

    def open_short(
        self,
        symbol: str,
        size_usd: float,
        leverage: Optional[int] = None,
        gem_score: float = 0,
    ) -> Optional[dict]:
        """Open a leveraged short position."""
        return self._open_position(symbol, "sell", size_usd, leverage, gem_score)

    def close_position(self, symbol: str) -> Optional[dict]:
        """Close an open position."""
        if not self.is_available():
            return None

        sym = _normalize_symbol(symbol)

        with self._lock:
            pos = self.positions.get(sym)
            if not pos:
                logger.warning(f"Hyperliquid: no open position for {sym}")
                return None

            try:
                # Cancel stop-loss trigger if exists
                if pos.sl_oid:
                    # _cancel_trigger handles the logic
                    pass

                # Use market_close for clean exit
                result = self._execute_api(self._exchange.market_close, sym)

                if result and result.get("status") == "ok":
                    # Check fills
                    time.sleep(0.5)
                    fills = self._get_recent_fills(sym)
                    close_price = fills[0].get("px", 0) if fills else 0

                    pnl = self._calc_pnl(pos, float(close_price))
                    self.daily_pnl += pnl
                    del self.positions[sym]
                    self._save_trailing_state()  # Ensure deleted position is removed from trailing state

                    logger.info(
                        f"✅ Hyperliquid CLOSE {sym} | "
                        f"entry=${pos.entry_price:.4f} → exit=${close_price} | "
                        f"PnL=${pnl:+.2f} | daily_pnl=${self.daily_pnl:+.2f}"
                    )
                    return {"coin": sym, "close_price": close_price, "pnl": pnl}
                else:
                    logger.error(f"Hyperliquid close failed for {sym}: {result}")
                    return None

            except Exception as e:
                logger.error(f"Hyperliquid close error for {sym}: {e}")
                return None

    # ─────────────────────────────────────────────────────────────────────────
    # Internal
    # ─────────────────────────────────────────────────────────────────────────

    def _open_position(
        self,
        symbol: str,
        side: str,  # "buy" or "sell"
        size_usd: float,
        leverage: Optional[int],
        gem_score: float,
    ) -> Optional[dict]:
        """Core position opening logic with all safety checks."""
        if not self.is_available():
            logger.warning("Hyperliquid: executor not available")
            return None

        sym = _normalize_symbol(symbol)

        # ── Pre-flight Checks ──────────────────────────────────────────────
        if not self.has_perp(sym):
            logger.debug(f"Hyperliquid: {sym} has no perp listing — skip")
            return None

        # ── CAPITAL PROTECTION: gem score gate ─────────────────────────
        if gem_score < self.min_gem_score:
            logger.info(
                f"Hyperliquid: {sym} gem_score={gem_score:.0f} below min {self.min_gem_score} — skip"
            )
            return None

        # ── CAPITAL PROTECTION: daily loss circuit breaker ─────────────
        self._check_daily_reset()
        if self.daily_pnl <= -self.daily_loss_limit:
            logger.warning(
                f"🛑 Hyperliquid CIRCUIT BREAKER: daily PnL ${self.daily_pnl:.2f} "
                f"exceeded limit -${self.daily_loss_limit:.2f} — ALL TRADING HALTED"
            )
            return None

        if len(self.positions) >= self.max_positions:
            logger.warning(f"Hyperliquid: max positions ({self.max_positions}) reached — skip {sym}")
            return None

        # Already have a position in this coin
        if sym in self.positions:
            logger.info(f"Hyperliquid: already positioned in {sym} — skip")
            return None

        # ── CAPITAL PROTECTION: cap position size ──────────────────────
        actual_size_usd = min(size_usd, self.max_position_usd)

        # ── CAPITAL PROTECTION: total exposure limit ───────────────────
        # FIX (PYTHON-S): Guard against None leverage on synced positions.
        # If a position was synced with leverage=None (null from HL API), the
        # multiplication p.size_usd * p.leverage raises TypeError: 'int' * NoneType.
        current_exposure = sum(
            p.size_usd * (p.leverage or self.default_leverage)
            for p in self.positions.values()
        )
        lev = leverage or self.default_leverage
        new_exposure = actual_size_usd * lev
        if current_exposure + new_exposure > self.max_total_exposure:
            logger.warning(
                f"Hyperliquid: exposure cap — current=${current_exposure:.0f} + "
                f"new=${new_exposure:.0f} > max=${self.max_total_exposure:.0f}"
            )
            return None

        # ── CAPITAL PROTECTION: balance check ──────────────────────────
        balance = self.get_balance()
        withdrawable = balance.get("withdrawable", 0)
        account_value = balance.get("account_value", 0)
        balance_mode = balance.get("mode", "unknown")

        # Unified accounts share equity — no Spot→Perps transfer needed.
        # In Unified mode, HL automatically allocates margin from Spot balance.

        if withdrawable < actual_size_usd:
            # Re-check after potential transfer
            balance = self.get_balance()
            withdrawable = balance.get("withdrawable", 0)
            account_value = balance.get("account_value", 0)
            if withdrawable < actual_size_usd:
                logger.warning(
                    f"Hyperliquid: insufficient margin — need ${actual_size_usd:.2f}, "
                    f"available ${withdrawable:.2f}"
                )
                return None

        # ── CAPITAL PROTECTION: never risk >20% of account on one trade ─
        # OVERRIDE: We want to use the full $150 base capital if the Kelly Criterion allows it.
        # We will allow up to 100% of the account value for this specific run.
        if account_value > 0 and actual_size_usd > account_value * 1.0:
            actual_size_usd = round(account_value * 0.95, 2) # Leave 5% for fees/buffer
            logger.info(
                f"Hyperliquid: position capped to 95% of account = ${actual_size_usd:.2f}"
            )
            if actual_size_usd < 5.0:
                logger.warning(f"Hyperliquid: cap too small (${actual_size_usd:.2f}) — skip")
                return None

        # ── CAPITAL PROTECTION: funding rate check ─────────────────────
        if not self._check_funding_rate_safe(sym, side):
            return None

        # ── Execute ────────────────────────────────────────────────────────
        with self._lock:
            try:
                # Use L2 Book to calculate exact execution price and size
                l2 = self._execute_api(self._info.l2_snapshot, sym)
                if not l2 or "levels" not in l2:
                    logger.warning(f"Hyperliquid: no L2 book for {sym} — skipping")
                    return None
                
                bids, asks = l2["levels"]
                levels = asks if side == "buy" else bids
                
                if not levels:
                    logger.warning(f"Hyperliquid: empty L2 book side for {sym} — skipping")
                    return None
                
                # Calculate required coin size by walking the book
                notional_remaining = actual_size_usd * lev
                coin_size = 0.0
                avg_price = 0.0
                
                for level in levels:
                    px = float(level["px"])
                    sz = float(level["sz"])
                    level_notional = px * sz
                    
                    if notional_remaining <= level_notional:
                        # This level fully satisfies the remaining notional
                        coin_size += notional_remaining / px
                        notional_remaining = 0
                        break
                    else:
                        # Consume the whole level
                        coin_size += sz
                        notional_remaining -= level_notional

                if notional_remaining > 0:
                    logger.warning(f"Hyperliquid: insufficient liquidity in L2 book for {sym} (need ${actual_size_usd * lev:.2f})")
                    return None

                # Calculate average execution price
                price = (actual_size_usd * lev) / coin_size
                mid_price = float(bids[0]["px"]) + (float(asks[0]["px"]) - float(bids[0]["px"])) / 2
                
                slippage_pct = abs(price - mid_price) / mid_price
                if slippage_pct > 0.015:
                    logger.warning(f"Hyperliquid: slippage too high for {sym} ({slippage_pct*100:.2f}% > 1.5%) — skipping")
                    return None

                # Set leverage
                is_cross = True  # Cross margin for capital efficiency
                self._exchange.update_leverage(lev, sym, is_cross)

                # Get size decimals for this asset
                sz_decimals = self._get_sz_decimals(sym)
                coin_size = round(coin_size, sz_decimals)

                if coin_size <= 0:
                    logger.warning(f"Hyperliquid: computed size too small for {sym}")
                    return None

                # Place market order
                logger.info(
                    f"🚀 Hyperliquid {side.upper()} {sym} | "
                    f"margin=${actual_size_usd:.2f} × {lev}x = ${notional:.2f} notional | "
                    f"size={coin_size} @ ${price:.4f} | score={gem_score:.0f}"
                )

                result = self._execute_api(
                    self._exchange.market_open,
                    sym,
                    side == "buy",  # is_buy
                    coin_size,
                    slippage=0.015,  # 1.5% slippage tolerance (SDK computes IOC limit price)
                )

                # Log full result for debugging
                logger.info(f"Hyperliquid market_open result for {sym}: {result}")

                if not result or result.get("status") != "ok":
                    logger.error(f"Hyperliquid order failed for {sym}: {result}")
                    return None

                # Check for resting/filled statuses in response
                response = result.get("response", {})
                data = response.get("data", {})
                statuses = data.get("statuses", [])
                if statuses:
                    first_status = statuses[0]
                    if "error" in first_status:
                        error_msg = first_status["error"]
                        # FIX (PYTHON-19 / PYTHON-X): Downgrade known HL API rejections
                        # from logger.error → logger.warning. These are expected outcomes
                        # (illiquid coins, IOC no-match, price deviation) — not code bugs.
                        # logger.error() was flooding Sentry with non-actionable alerts.
                        if any(expected in error_msg for expected in _HL_EXPECTED_REJECTIONS):
                            logger.warning(
                                f"Hyperliquid order rejected for {sym} (expected): {error_msg}"
                            )
                        else:
                            logger.error(
                                f"Hyperliquid order rejected for {sym} (unexpected): {error_msg}"
                            )
                        return None
                    if "resting" not in first_status and "filled" not in first_status:
                        logger.warning(f"Hyperliquid order status unknown for {sym}: {first_status}")

                # Wait for fill confirmation
                time.sleep(1.0)
                fills = self._get_recent_fills(sym)
                if not fills:
                    logger.warning(f"⚠️ Hyperliquid: no fills found for {sym} — order may have been cancelled (IOC)")
                    return None
                fill_price = float(fills[0].get("px", price)) if fills else price
                fill_size = float(fills[0].get("sz", coin_size)) if fills else coin_size

                # Calculate TP/SL prices
                if side == "buy":
                    sl_price = round(fill_price * (1 - self.stop_loss_pct / 100), 2)
                    tp_price = round(fill_price * (1 + self.take_profit_pct / 100), 2)
                else:
                    sl_price = round(fill_price * (1 + self.stop_loss_pct / 100), 2)
                    tp_price = round(fill_price * (1 - self.take_profit_pct / 100), 2)

                # Place TP/SL orders and capture on-chain order IDs
                sl_oid, tp_oid = self._place_tpsl(sym, side, fill_size, sl_price, tp_price)

                # Track position — include trailing state fields
                pos = HLPosition(
                    coin=sym,
                    side="long" if side == "buy" else "short",
                    entry_price=fill_price,
                    size=fill_size,
                    size_usd=actual_size_usd,
                    leverage=lev,
                    stop_loss_price=sl_price,
                    take_profit_price=tp_price,
                    highest_price=fill_price,
                    lowest_price=fill_price,
                    sl_order_id=sl_oid,
                    tp_order_id=tp_oid,
                )
                self.positions[sym] = pos
                # Persist initial trailing state immediately
                self._save_trailing_state()

                direction = "LONG" if side == "buy" else "SHORT"
                logger.info(
                    f"✅ Hyperliquid {direction} FILLED: {sym} | "
                    f"size={fill_size} @ ${fill_price:.4f} | "
                    f"margin=${actual_size_usd:.2f} × {lev}x | "
                    f"SL=${sl_price:.4f} / TP=${tp_price:.4f} | "
                    f"score={gem_score:.0f}"
                )

                return {
                    "coin": sym,
                    "side": direction.lower(),
                    "fill_price": fill_price,
                    "size": fill_size,
                    "margin_usd": actual_size_usd,
                    "leverage": lev,
                    "notional_usd": notional,
                    "stop_loss": sl_price,
                    "take_profit": tp_price,
                }

            except Exception as e:
                logger.error(f"❌ Hyperliquid {side} {sym} error: {e}", exc_info=True)
                return None

    def _place_tpsl(
        self,
        coin: str,
        entry_side: str,
        size: float,
        sl_price: float,
        tp_price: float,
    ) -> tuple[Optional[int], Optional[int]]:
        """Place stop-loss and take-profit trigger orders ON-CHAIN.

        These persist on Hyperliquid's matching engine independent of the bot.
        If the bot crashes, positions are still protected by these orders.

        Returns:
            (sl_order_id, tp_order_id) — integer order IDs from HL, or None on failure.
            Stored in HLPosition so the trailing monitor can cancel/replace the SL.
        """
        sl_order_id: Optional[int] = None
        tp_order_id: Optional[int] = None
        try:
            is_buy = entry_side != "buy"  # Close side is opposite of entry

            # Round prices to reasonable precision
            sl_price = float(sl_price)
            tp_price = float(tp_price)

            # Limit slippage for TP/SL set to 1% to avoid massive wicks on exits
            # If buying to close, worst price is higher. If selling to close, worst price is lower.
            slippage = 0.01
            if is_buy:
                sl_limit_px = round(sl_price * (1 + slippage), 6)
                tp_limit_px = round(tp_price * (1 + slippage), 6)
            else:
                sl_limit_px = round(sl_price * (1 - slippage), 6)
                tp_limit_px = round(tp_price * (1 - slippage), 6)

            # Stop Loss — LIMIT order triggered when price hits SL
            sl_result = self._execute_api(
                self._exchange.order,
                coin,
                is_buy,
                size,
                sl_limit_px,  # limit_px (worst acceptable execution price)
                {"trigger": {"isMarket": False, "triggerPx": sl_price, "tpsl": "sl"}},
                reduce_only=True,
            )
            sl_ok = sl_result and sl_result.get("status") == "ok"
            if sl_ok:
                # Extract order ID from response: response.data.statuses[0].resting.oid
                try:
                    sl_order_id = (
                        sl_result["response"]["data"]["statuses"][0]
                        .get("resting", {})
                        .get("oid")
                    )
                except Exception:
                    pass

            # Take Profit — LIMIT order triggered when price hits TP
            tp_result = self._execute_api(
                self._exchange.order,
                coin,
                is_buy,
                size,
                tp_limit_px,  # limit_px (worst acceptable execution price)
                {"trigger": {"isMarket": False, "triggerPx": tp_price, "tpsl": "tp"}},
                reduce_only=True,
            )
            tp_ok = tp_result and tp_result.get("status") == "ok"
            if tp_ok:
                try:
                    tp_order_id = (
                        tp_result["response"]["data"]["statuses"][0]
                        .get("resting", {})
                        .get("oid")
                    )
                except Exception:
                    pass

            if sl_ok and tp_ok:
                logger.info(
                    f"  ↳ ✅ TP/SL ON-CHAIN for {coin}: "
                    f"SL=${sl_price:.4f} (oid={sl_order_id}) / "
                    f"TP=${tp_price:.4f} (oid={tp_order_id})"
                )
            else:
                logger.warning(
                    f"  ↳ ⚠️ TP/SL partial for {coin}: "
                    f"SL={'✅' if sl_ok else '❌'} ({sl_result}) / "
                    f"TP={'✅' if tp_ok else '❌'} ({tp_result})"
                )

        except Exception as e:
            logger.error(f"❌ Hyperliquid TP/SL placement FAILED for {coin}: {e}", exc_info=True)

        return sl_order_id, tp_order_id

    # ─────────────────────────────────────────────────────────────────────────
    # Trailing Profit-Lock — state persistence & order management
    # ─────────────────────────────────────────────────────────────────────────

    def _save_trailing_state(self) -> None:
        """Persist trailing stop state for all open positions to disk.

        Called after every trailing stop update so a restart can resume
        exactly where it left off without losing peak-price tracking.
        """
        try:
            _TRAILING_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            state = {}
            for coin, pos in self.positions.items():
                state[coin] = {
                    "side": pos.side,
                    "entry_price": pos.entry_price,
                    "highest_price": pos.highest_price,
                    "lowest_price": pos.lowest_price if pos.lowest_price != float("inf") else None,
                    "trailing_stop_active": pos.trailing_stop_active,
                    "sl_order_id": pos.sl_order_id,
                    "tp_order_id": pos.tp_order_id,
                    "stop_loss_price": pos.stop_loss_price,
                }
            _TRAILING_STATE_FILE.write_text(json.dumps(state, indent=2))
        except Exception as e:
            logger.warning(f"Hyperliquid: failed to save trailing state: {e}")

    def _load_trailing_state(self) -> None:
        """Merge persisted trailing state back into freshly-synced HLPosition objects.

        Called at the end of _sync_positions() so that highest_price, sl_order_id,
        and trailing_stop_active survive bot restarts.
        """
        if not _TRAILING_STATE_FILE.exists():
            return
        try:
            raw = json.loads(_TRAILING_STATE_FILE.read_text())
            for coin, saved in raw.items():
                pos = self.positions.get(coin)
                if pos is None:
                    # Position was closed while bot was down — skip
                    continue
                pos.highest_price = float(saved.get("highest_price") or pos.entry_price)
                lp = saved.get("lowest_price")
                pos.lowest_price = float(lp) if lp is not None else pos.entry_price
                pos.trailing_stop_active = bool(saved.get("trailing_stop_active", False))
                pos.sl_order_id = saved.get("sl_order_id")
                pos.tp_order_id = saved.get("tp_order_id")
                # Restore persisted SL price only if it is tighter than what HL returned
                persisted_sl = saved.get("stop_loss_price")
                if persisted_sl is not None:
                    persisted_sl = float(persisted_sl)
                    if pos.side == "long" and persisted_sl > (pos.stop_loss_price or 0):
                        pos.stop_loss_price = persisted_sl
                    elif pos.side == "short" and pos.stop_loss_price and persisted_sl < pos.stop_loss_price:
                        pos.stop_loss_price = persisted_sl
            logger.info(
                f"Hyperliquid: trailing state loaded for "
                f"{len([c for c in raw if c in self.positions])} positions"
            )
        except Exception as e:
            logger.warning(f"Hyperliquid: failed to load trailing state: {e}")

    def _cancel_order(self, coin: str, order_id: int) -> bool:
        """Cancel a single on-chain order by ID.

        Used by the trailing monitor to remove the stale static SL before
        placing the new, tighter trailing stop.
        """
        try:
            result = self._execute_api(self._exchange.cancel, coin, order_id)
            ok = result and result.get("status") == "ok"
            if ok:
                logger.debug(f"Hyperliquid: cancelled order oid={order_id} for {coin}")
            else:
                logger.warning(f"Hyperliquid: cancel order oid={order_id} for {coin} returned: {result}")
            return ok
        except Exception as e:
            logger.warning(f"Hyperliquid: exception cancelling order oid={order_id} for {coin}: {e}")
            return False

    def update_trailing_stop(self, coin: str, new_sl_price: float) -> bool:
        """Cancel the existing on-chain SL and place a new one at new_sl_price.

        Called by the trailing monitor daemon whenever the mark price moves
        far enough that the trailing stop needs to ratchet up (longs) or
        down (shorts).

        Thread-safe — acquires self._lock before mutating position state.
        """
        with self._lock:
            pos = self.positions.get(coin)
            if pos is None:
                logger.warning(f"Hyperliquid update_trailing_stop: no position for {coin}")
                return False

            old_sl = pos.stop_loss_price
            old_oid = pos.sl_order_id

            # Determine close side (opposite of entry)
            entry_side = "buy" if pos.side == "long" else "sell"
            slippage = 0.01
            is_close_buy = pos.side == "short"  # Closing a short = buy
            if is_close_buy:
                sl_limit_px = round(new_sl_price * (1 + slippage), 6)
            else:
                sl_limit_px = round(new_sl_price * (1 - slippage), 6)

            try:
                order_type = {"trigger": {"isMarket": False, "triggerPx": new_sl_price, "tpsl": "sl"}}
                
                if old_oid is not None:
                    # Modify existing order directly
                    sl_result = self._execute_api(
                        self._exchange.modify_order,
                        oid=old_oid,
                        name=coin,
                        is_buy=is_close_buy,
                        sz=pos.size,
                        limit_px=sl_limit_px,
                        order_type=order_type,
                        reduce_only=True,
                    )
                else:
                    # Place a new order
                    sl_result = self._execute_api(
                        self._exchange.order,
                        coin,
                        is_close_buy,
                        pos.size,
                        sl_limit_px,
                        order_type,
                        reduce_only=True,
                    )
                
                sl_ok = sl_result and sl_result.get("status") == "ok"
                new_oid: Optional[int] = None
                if sl_ok:
                    try:
                        new_oid = (
                            sl_result["response"]["data"]["statuses"][0]
                            .get("resting", {})
                            .get("oid")
                        )
                    except Exception:
                        pass

                if sl_ok:
                    pos.stop_loss_price = new_sl_price
                    pos.sl_order_id = new_oid
                    self._save_trailing_state()
                    logger.info(
                        f"🔒 TRAILING STOP RATCHETED | {coin} | "
                        f"old_sl=${old_sl:.4f} (oid={old_oid}) → "
                        f"new_sl=${new_sl_price:.4f} (oid={new_oid})"
                    )
                    return True
                else:
                    # Placement failed — restore old SL state so position isn't orphaned
                    # The old SL order may still be live on-chain if cancel also failed
                    pos.stop_loss_price = old_sl
                    pos.sl_order_id = old_oid
                    err_msg = str(sl_result.get("response", "")) if isinstance(sl_result, dict) else str(sl_result)
                    if "Too many" in err_msg or "rate" in err_msg.lower():
                        logger.warning(
                            f"⚠️ Hyperliquid: rate limited placing trailing SL for {coin} — will retry next cycle"
                        )
                    else:
                        logger.error(
                            f"❌ Hyperliquid: failed to place new trailing SL for {coin}: {sl_result}"
                        )
                    return False

            except Exception as e:
                logger.error(
                    f"❌ Hyperliquid: exception in update_trailing_stop for {coin}: {e}",
                    exc_info=True,
                )
                return False

    def _get_recent_fills(self, coin: str) -> list:
        """Get recent fills for a coin."""
        try:
            fills = self._execute_api(self._info.user_fills, self.wallet_address)
            return [f for f in fills if f.get("coin") == coin][:5]
        except Exception:
            return []

    def _get_sz_decimals(self, coin: str) -> int:
        """Get size decimals for proper rounding."""
        try:
            meta = self._execute_api(self._info.meta)
            for asset in meta.get("universe", []):
                if asset.get("name", "").upper() == coin:
                    # FIX: szDecimals key may exist with null value — guard with int() fallback
                    raw = asset.get("szDecimals")
                    return int(raw) if raw is not None else 4
        except Exception:
            pass
        return 4  # safe default

    def _calc_pnl(self, pos: HLPosition, close_price: float) -> float:
        """Calculate realized PnL for a position."""
        if pos.side == "long":
            pnl_pct = (close_price - pos.entry_price) / pos.entry_price
        else:
            pnl_pct = (pos.entry_price - close_price) / pos.entry_price
        return pos.size_usd * pos.leverage * pnl_pct

    def _check_daily_reset(self) -> None:
        """Reset daily PnL counter at midnight UTC."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if today != self.daily_pnl_reset_date:
            if self.daily_pnl != 0:
                logger.info(f"Hyperliquid: daily PnL reset (was ${self.daily_pnl:+.2f})")
            self.daily_pnl = 0.0
            self.daily_pnl_reset_date = today

    def _check_funding_rate_safe(self, coin: str, side: str) -> bool:
        """
        CAPITAL PROTECTION: Reject trades where funding rate works against us.
        
        - Going LONG with high positive funding = paying to hold = bad
        - Going SHORT with very negative funding = paying to hold = bad
        - Threshold: |funding| > 0.05% per 8h (annualized ~22%) = too expensive
        """
        try:
            meta = self._execute_api(self._info.meta)
            for asset in meta.get("universe", []):
                if asset.get("name", "").upper() == coin:
                    funding_rate = float(asset.get("funding", 0))
                    
                    # Threshold: 0.05% per 8h is expensive
                    threshold = 0.0005
                    
                    if side == "buy" and funding_rate > threshold:
                        logger.info(
                            f"Hyperliquid: {coin} funding rate {funding_rate:.6f} too high "
                            f"for LONG (>{threshold}) — skip (would pay to hold)"
                        )
                        return False
                    elif side == "sell" and funding_rate < -threshold:
                        logger.info(
                            f"Hyperliquid: {coin} funding rate {funding_rate:.6f} too negative "
                            f"for SHORT (<-{threshold}) — skip (would pay to hold)"
                        )
                        return False
                    
                    return True
            return True  # Unknown coin — allow (will fail at order stage)
        except Exception as e:
            logger.warning(f"Hyperliquid: funding rate check failed for {coin}: {e}")
            return True  # Allow on error — TP/SL still protect us

    def withdraw_profit_usd(self, amount_usd: float, destination_address: str) -> bool:
        """
        Withdraw USDC from the Hyperliquid L2 bridge to an L1 Arbitrum address.
        Fee is flat $1 USDC.
        """
        if not self._initialized or not self._exchange:
            logger.error("Hyperliquid: Cannot withdraw — not initialized")
            return False
        
        try:
            logger.info(f"🏦 Hyperliquid: Initiating withdrawal of ${amount_usd:.2f} to {destination_address}")
            result = self._exchange.withdraw_from_bridge(amount_usd, destination_address)
            
            # The SDK returns a dict with status. Check if successful.
            if result and result.get("status") == "ok":
                logger.info(f"✅ Hyperliquid: Successfully withdrew ${amount_usd:.2f} to {destination_address}")
                return True
            else:
                logger.error(f"❌ Hyperliquid: Withdrawal failed. SDK returned: {result}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Hyperliquid: Exception during withdrawal of ${amount_usd:.2f}: {e}", exc_info=True)
            return False

    def get_status(self) -> dict:
        """Comprehensive status for dashboard/logging."""
        balance = self.get_balance() if self.is_available() else {}
        return {
            "enabled": self.enabled,
            "initialized": self._initialized,
            "wallet": self.wallet_address[:10] + "..." if self.wallet_address else "none",
            "testnet": self.use_testnet,
            "leverage": self.default_leverage,
            "open_positions": len(self.positions),
            "max_positions": self.max_positions,
            "daily_pnl": self.daily_pnl,
            "daily_loss_limit": self.daily_loss_limit,
            "account_value": balance.get("account_value", 0),
            "withdrawable": balance.get("withdrawable", 0),
            "perps_available": len(_HL_PERP_TICKERS),
            "positions": {
                coin: {
                    "side": p.side,
                    "entry": p.entry_price,
                    "size_usd": p.size_usd,
                    "leverage": p.leverage,
                    "pnl": p.pnl,
                }
                for coin, p in self.positions.items()
            },
        }


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_symbol(symbol: str) -> str:
    """
    Normalize token symbol for Hyperliquid matching.
    
    On-chain tokens often have different names than their HL perp tickers.
    """
    sym = symbol.upper().strip()
    # Common mappings: on-chain name → Hyperliquid perp name
    MAPPINGS = {
        "WETH": "ETH",
        "WBTC": "BTC",
        "WBNB": "BNB",
        "WAVAX": "AVAX",
        "WMATIC": "POL",
        "WSOL": "SOL",
        "STETH": "ETH",
        "WSTETH": "ETH",
        "RETH": "ETH",
        "CBETH": "ETH",
        "SHIB": "SHIB",
        "1000PEPE": "PEPE",
    }
    return MAPPINGS.get(sym, sym)
