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
    # Winning tuning: TP1 partial already taken (50% at +2%)
    tp1_hit: bool = False


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
        # P0 2026-07-09: respect env caps (do NOT force $2500 floor — CSV showed $2.8k GRASS losses).
        self.max_position_usd = float(settings.HYPERLIQUID_MAX_POSITION_USD)
        self.max_total_exposure = float(settings.HYPERLIQUID_MAX_TOTAL_EXPOSURE)
        self.max_positions = settings.HYPERLIQUID_MAX_POSITIONS
        self.stop_loss_pct = settings.HYPERLIQUID_STOP_LOSS_PCT
        self.take_profit_pct = settings.HYPERLIQUID_TAKE_PROFIT_PCT
        self.daily_loss_limit = settings.HYPERLIQUID_DAILY_LOSS_LIMIT
        # Prefer HL_PERPS_EXEC_SCORE (scanner gate) so executor never rejects
        # signals the scanner already approved. Fall back to HYPERLIQUID_MIN_GEM_SCORE.
        # Mismatch (scanner 55 / executor 65) caused 0 trades after 2026-07-17 deploy.
        _exec_score = os.getenv("HL_PERPS_EXEC_SCORE")
        if _exec_score not in (None, ""):
            self.min_gem_score = float(_exec_score)
        else:
            self.min_gem_score = float(getattr(settings, "HYPERLIQUID_MIN_GEM_SCORE", 55))
        self.use_testnet = settings.HYPERLIQUID_USE_TESTNET
        # Hard notional cap (margin × leverage). Prevents Kelly spikes like GRASS $2808.
        self.max_notional_usd = float(os.getenv("HL_PERPS_MAX_NOTIONAL_USD", "350.0"))
        # Max fraction of account equity used as margin on a single trade.
        self.max_margin_equity_pct = float(os.getenv("HL_PERPS_MAX_MARGIN_EQUITY_PCT", "0.15"))
        # Minimum reward/risk after fill when structure SL/TP is provided.
        # MUST match scanner HL_PERPS_MIN_RR (default 1.2). Mismatch caused 49 rapid
        # closes (5-6s): scanner approved R/R=1.1-1.4, executor rejected at 1.5 → market_close.
        self.min_rr_ratio = float(os.getenv("HL_PERPS_MIN_RR", "1.2"))
        # Emergency-close cooldown injected into scanner (minutes).
        # MUST match scanner HL_PERPS_EMERGENCY_COOLDOWN_MIN (default 60).
        self.emergency_cooldown_min = int(os.getenv("HL_PERPS_EMERGENCY_COOLDOWN_MIN", "60"))

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

    # ── Trade journal (output/trades.json) ─────────────────────────────────
    def _log_hl_trade(
        self,
        *,
        action: str,
        coin: str,
        side: str,
        price: float,
        quantity: float,
        value_usd: float,
        entry_price: Optional[float] = None,
        pnl_usd: Optional[float] = None,
        pnl_pct: Optional[float] = None,
        reason: str = "",
        gem_score: float = 0.0,
        leverage: int = 0,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        entry_time: Optional[str] = None,
        mfe_pct: Optional[float] = None,
        mae_pct: Optional[float] = None,
    ) -> None:
        """Append a Hyperliquid fill to output/trades.json for analytics.

        v32 (OpenAlice retrospective): mfe_pct / mae_pct = max favorable /
        adverse excursion over the hold (tracked peak/trough vs entry). The
        self-improving agent uses these to calibrate SL and trail distances
        from realized data instead of guessing.
        """
        try:
            trades_path = Path(os.getenv("TRADES_FILE", "output/trades.json"))
            trades_path.parent.mkdir(parents=True, exist_ok=True)
            trades: list = []
            if trades_path.exists():
                try:
                    raw = json.loads(trades_path.read_text(encoding="utf-8") or "[]")
                    if isinstance(raw, list):
                        trades = raw
                except Exception:
                    trades = []
            record = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "token_address": f"hl:{coin}",
                "token_symbol": coin,
                "chain": "hyperliquid",
                "wallet": "hyperliquid",
                "action": action,
                "reason": reason,
                "quantity": quantity,
                "price_usd": price,
                "value_usd": value_usd,
                "entry_price": entry_price if entry_price is not None else price,
                "pnl_usd": pnl_usd,
                "pnl_pct": pnl_pct,
                "is_paper": False,
                "tx_hash": None,
                "signal_scores": {},
                "gem_score": gem_score,
                "entry_time": entry_time,
                "strategy_profile": "hl_perps",
                "side": side,
                "leverage": leverage,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "mfe_pct": mfe_pct,
                "mae_pct": mae_pct,
            }
            trades.append(record)
            # Keep journal bounded
            if len(trades) > 5000:
                trades = trades[-5000:]
            trades_path.write_text(json.dumps(trades, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Hyperliquid: failed to journal trade for {coin}: {e}")

    @staticmethod
    def _calc_mfe_mae(pos: "HLPosition") -> tuple:
        """v32: max favorable / adverse excursion (%) from tracked peak/trough.

        For longs: MFE = entry→highest_price, MAE = entry→lowest seen (we only
        track highest for longs, so MAE falls back to None when unavailable).
        For shorts: MFE = entry→lowest_price move in our favor.
        Returns (mfe_pct, mae_pct); None where the excursion wasn't tracked.
        """
        try:
            entry = float(pos.entry_price or 0)
            if entry <= 0:
                return None, None
            hi = float(pos.highest_price or 0)
            lo = pos.lowest_price
            lo = float(lo) if lo not in (None, float("inf")) else 0.0
            if pos.side == "long":
                mfe = ((hi - entry) / entry * 100.0) if hi > 0 else None
                mae = ((lo - entry) / entry * 100.0) if lo > 0 else None
            else:
                mfe = ((entry - lo) / entry * 100.0) if lo > 0 else None
                mae = ((entry - hi) / entry * 100.0) if hi > 0 else None
            mfe = round(mfe, 3) if mfe is not None else None
            mae = round(mae, 3) if mae is not None else None
            return mfe, mae
        except Exception:
            return None, None

    def _feed_daily_goal(self, pnl_usd: float, source: str = "scalp_hl_perps") -> None:
        """Record Hyperliquid realized PnL into the daily goal engine ($500+/day ladder)."""
        if not pnl_usd:
            return
        try:
            from core.daily_goal_engine import get_daily_goal_engine
            get_daily_goal_engine().record_profit(float(pnl_usd), source=source)
        except Exception as e:
            logger.debug(f"Hyperliquid: daily goal feed failed: {e}")

    def _inject_scanner_cooldown(
        self,
        coin: str,
        *,
        loss: bool = False,
        emergency: bool = False,
    ) -> None:
        """Push re-entry / loss / emergency cooldowns into the global HL scanner."""
        try:
            import sys
            scanner = None
            if "core.hl_perps_scanner" in sys.modules:
                hl_module = sys.modules["core.hl_perps_scanner"]
                scanner = getattr(hl_module, "_global_scanner", None)
            if not scanner:
                return
            now = time.time()
            if not hasattr(scanner, "reentry_cooldowns"):
                scanner.reentry_cooldowns = {}
            scanner.reentry_cooldowns[coin] = now
            if loss and hasattr(scanner, "loss_cooldowns"):
                scanner.loss_cooldowns[coin] = now
            # Record trade outcome for auto-blacklist win-rate tracking
            if hasattr(scanner, "record_trade_outcome"):
                # emergency closes (SL fail / R/R reject) always count as losses
                won = not loss
                scanner.record_trade_outcome(coin, won=won)
            # Winning dynamic blacklist: feed SL hits (3+ / 24h → ban)
            if loss:
                try:
                    from core.hl_scanner_winning_tuning import winning_entry_filter
                    winning_entry_filter.record_sl_hit(coin)
                except Exception:
                    pass
            if emergency:
                if not hasattr(scanner, "emergency_cooldowns"):
                    scanner.emergency_cooldowns = {}
                scanner.emergency_cooldowns[coin] = now
                logger.info(
                    f"⏱️ Emergency cooldown activated for {coin} "
                    f"({self.emergency_cooldown_min}m)"
                )
            else:
                logger.debug(f"⏱️ Re-entry throttle activated for {coin}")
        except Exception as e:
            logger.error(f"Failed to inject cooldowns for {coin}: {e}")

    @staticmethod
    def _resolve_tpsl_prices(
        side: str,
        fill_price: float,
        stop_loss_pct: float,
        take_profit_pct: float,
        stop_loss_price: Optional[float] = None,
        take_profit_price: Optional[float] = None,
    ) -> tuple[float, float, str]:
        """Prefer structure/Fib levels from the scanner; fall back to fixed %."""
        source = "fixed"
        if side == "buy":
            fixed_sl = fill_price * (1 - stop_loss_pct / 100)
            fixed_tp = fill_price * (1 + take_profit_pct / 100)
            # Structure SL must be below entry for longs
            if stop_loss_price and stop_loss_price < fill_price:
                sl_price = float(stop_loss_price)
                source = "structure"
            else:
                sl_price = fixed_sl
            if take_profit_price and take_profit_price > fill_price:
                tp_price = float(take_profit_price)
                if source == "structure":
                    source = "structure"
                else:
                    source = "structure_tp_only" if stop_loss_price else "fixed"
            else:
                tp_price = fixed_tp
                if source == "structure":
                    source = "structure_sl_only"
        else:
            fixed_sl = fill_price * (1 + stop_loss_pct / 100)
            fixed_tp = fill_price * (1 - take_profit_pct / 100)
            if stop_loss_price and stop_loss_price > fill_price:
                sl_price = float(stop_loss_price)
                source = "structure"
            else:
                sl_price = fixed_sl
            if take_profit_price and take_profit_price < fill_price:
                tp_price = float(take_profit_price)
            else:
                tp_price = fixed_tp
                if source == "structure":
                    source = "structure_sl_only"

        # Cap risk distance: never allow structure SL wider than 2× fixed SL band
        max_sl_dist = (stop_loss_pct / 100) * 2.0
        if side == "buy":
            if (fill_price - sl_price) / fill_price > max_sl_dist:
                sl_price = fill_price * (1 - max_sl_dist)
                source = f"{source}_sl_capped"
        else:
            if (sl_price - fill_price) / fill_price > max_sl_dist:
                sl_price = fill_price * (1 + max_sl_dist)
                source = f"{source}_sl_capped"

        sl_price = float(f"{sl_price:.5g}")
        tp_price = float(f"{tp_price:.5g}")
        return sl_price, tp_price, source

    @staticmethod
    def _rr_ratio(side: str, entry: float, sl: float, tp: float) -> float:
        if side == "buy":
            risk = entry - sl
            reward = tp - entry
        else:
            risk = sl - entry
            reward = entry - tp
        if risk <= 0:
            return 0.0
        return reward / risk

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

    def _exchange_position_size(self, sym: str) -> Optional[float]:
        """Return live szi for coin from HL clearinghouse.

        Returns:
          float size (0.0 = confirmed flat), or None if the live query failed
          (do NOT treat None as flat — avoids purging real positions on 429s).
        """
        try:
            state = self._execute_api(self._info.user_state, self.wallet_address)
            if not isinstance(state, dict):
                return None
            for pos in state.get("assetPositions", []) or []:
                p = pos.get("position", {}) or {}
                if (p.get("coin") or "").upper() == sym.upper():
                    return float(p.get("szi") or 0)
            # Coin not in assetPositions list → flat
            return 0.0
        except Exception as e:
            logger.debug(f"Hyperliquid: live size check failed for {sym}: {e}")
            return None

    def _purge_ghost_position(
        self,
        sym: str,
        reason: str = "flat_on_exchange",
        *,
        already_locked: bool = False,
    ) -> None:
        """Remove a local position that no longer exists on Hyperliquid.

        Critical: without this, closed fills leave ghosts that fill max_positions
        slots, block re-entry, and spam failed Winning timeout closes (→ 429s).

        already_locked=True when caller already holds self._lock (non-reentrant).
        """
        def _do() -> None:
            if sym not in self.positions:
                return
            last = self.positions.pop(sym, None)
            try:
                self._save_trailing_state()
            except Exception:
                pass
            est = float(getattr(last, "pnl", 0.0) or 0.0) if last else 0.0
            logger.warning(
                f"🧹 Hyperliquid GHOST PURGE | {sym} | reason={reason} | "
                f"last_uPnl≈${est:+.2f} | local_slots_now={len(self.positions)}"
            )

        if already_locked:
            _do()
        else:
            with self._lock:
                _do()

    def _sync_positions(self) -> None:
        """Sync open positions from Hyperliquid account state."""
        try:
            state = self._execute_api(self._info.user_state, self.wallet_address)
            positions = state.get("assetPositions", [])
            
            active_coins = set()
            for pos in positions:
                p = pos.get("position", {})
                coin = p.get("coin", "")
                szi = float(p.get("szi", 0))
                if szi == 0:
                    continue
                active_coins.add(coin)
                entry_px = float(p.get("entryPx", 0))
                leverage_info = p.get("leverage") or {}
                # FIX (PYTHON-S): leverage_info.get("value") can return None when the key
                # exists with a null value in the HL API response (cross-margin accounts).
                # Use `or self.default_leverage` to guard against None before int().
                raw_lev = leverage_info.get("value")
                lev = int(raw_lev) if raw_lev is not None else self.default_leverage
                if lev <= 0:
                    lev = self.default_leverage
                unrealized_pnl = float(p.get("unrealizedPnl", 0))

                # size_usd is MARGIN USD everywhere (open path + exposure + PnL).
                # HL API gives coin size × entry = NOTIONAL; convert to margin.
                # Bug (2026-07-17): storing notional here made exposure calc do
                # notional × leverage again → 3× overcount → permanent exposure-cap block.
                notional_usd = abs(szi) * entry_px
                margin_usd = notional_usd / lev

                # Preserve trailing metadata across sync (do not clobber peaks/oids)
                prev = self.positions.get(coin)
                new_pos = HLPosition(
                    coin=coin,
                    side="long" if szi > 0 else "short",
                    entry_price=entry_px,
                    size=abs(szi),
                    size_usd=margin_usd,
                    leverage=lev,
                    pnl=unrealized_pnl,
                )
                if prev is not None:
                    new_pos.opened_at = prev.opened_at
                    new_pos.highest_price = prev.highest_price or entry_px
                    new_pos.lowest_price = prev.lowest_price if prev.lowest_price != float("inf") else entry_px
                    new_pos.trailing_stop_active = prev.trailing_stop_active
                    new_pos.sl_order_id = prev.sl_order_id
                    new_pos.tp_order_id = prev.tp_order_id
                    new_pos.stop_loss_price = prev.stop_loss_price
                    new_pos.take_profit_price = prev.take_profit_price
                    new_pos.tp1_hit = bool(getattr(prev, "tp1_hit", False))
                else:
                    new_pos.highest_price = entry_px
                    new_pos.lowest_price = entry_px
                self.positions[coin] = new_pos
            
            # Identify missing coins (closed passively via TP/SL or liquidation)
            missing_coins = [c for c in list(self.positions.keys()) if c not in active_coins]
            if missing_coins:
                import sys
                import time
                scanner = None
                if "core.hl_perps_scanner" in sys.modules:
                    hl_module = sys.modules["core.hl_perps_scanner"]
                    if hasattr(hl_module, "_global_scanner") and hl_module._global_scanner:
                        scanner = hl_module._global_scanner
                
                for missing_coin in missing_coins:
                    last_pos = self.positions[missing_coin]
                    # last_pos.pnl is last known unrealized — best estimate for passive TP/SL
                    est_pnl = float(getattr(last_pos, "pnl", 0.0) or 0.0)
                    logger.info(
                        f"Hyperliquid: detected passive closure for {missing_coin} "
                        f"(est_pnl=${est_pnl:+.2f}). Cleaning up ghost position."
                    )
                    # Do NOT feed daily_goal for ghosts already closed on-exchange —
                    # realized PnL was booked at fill time. Only inject cooldowns.
                    if scanner:
                        try:
                            # 1. Loss Cooldown Heuristic (if last known PnL was negative)
                            if est_pnl < 0:
                                scanner.loss_cooldowns[missing_coin] = time.time()
                                logger.info(f"⏱️ Loss cooldown injected for passive close on {missing_coin}")
                            # Record outcome for auto-ban
                            if hasattr(scanner, "record_trade_outcome"):
                                scanner.record_trade_outcome(missing_coin, won=(est_pnl > 0))
                            
                            # 2. Universal Re-entry Throttle
                            if not hasattr(scanner, "reentry_cooldowns"):
                                scanner.reentry_cooldowns = {}
                            scanner.reentry_cooldowns[missing_coin] = time.time()
                            logger.debug(f"⏱️ Re-entry throttle injected for passive close on {missing_coin}")
                        except Exception as e:
                            logger.error(f"Failed to inject passive cooldowns for {missing_coin}: {e}")
                    
                    # Remove the ghost position
                    del self.positions[missing_coin]

                # Persist cleaned trailing state so restarts don't re-hydrate ghosts
                try:
                    self._save_trailing_state()
                except Exception:
                    pass

            if self.positions:
                logger.info(f"Hyperliquid: synced {len(self.positions)} open positions")
            else:
                logger.info("Hyperliquid: synced 0 open positions (flat)")
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
                
            # Mark position as closing so it isn't orphaned or re-synced prematurely
            pos.status = "closing"
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
        stop_loss_price: Optional[float] = None,
        take_profit_price: Optional[float] = None,
    ) -> Optional[dict]:
        """
        Open a leveraged long position on Hyperliquid.
        
        Args:
            symbol: Token symbol (e.g., "BTC", "ETH", "PEPE")
            size_usd: Position size in USD (before leverage)
            leverage: Override default leverage
            gem_score: Signal strength (for logging)
            stop_loss_price: Optional structure/Fib SL from scanner (preferred over fixed %)
            take_profit_price: Optional structure/Fib TP from scanner
            
        Returns:
            Fill info dict or None on failure
        """
        return self._open_position(
            symbol, "buy", size_usd, leverage, gem_score,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
        )

    def open_short(
        self,
        symbol: str,
        size_usd: float,
        leverage: Optional[int] = None,
        gem_score: float = 0,
        stop_loss_price: Optional[float] = None,
        take_profit_price: Optional[float] = None,
    ) -> Optional[dict]:
        """Open a leveraged short position."""
        return self._open_position(
            symbol, "sell", size_usd, leverage, gem_score,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
        )

    def close_position(
        self,
        symbol: str,
        size_pct: Optional[float] = None,
    ) -> Optional[dict]:
        """Close an open position.

        Args:
            symbol: Perp coin ticker.
            size_pct: If set (0–100], close only that fraction (Winning TP1).
                      None / >=100 → full close via market_close.
        """
        if not self.is_available():
            return None

        sym = _normalize_symbol(symbol)

        # Partial close path (Winning TP1 front-load)
        if size_pct is not None and 0 < float(size_pct) < 100:
            return self._close_position_partial(sym, float(size_pct))

        with self._lock:
            pos = self.positions.get(sym)
            if not pos:
                logger.warning(f"Hyperliquid: no open position for {sym}")
                return None

            try:
                # Cancel stop-loss trigger if exists
                if pos.sl_order_id:
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
                    self._feed_daily_goal(pnl, source="scalp_hl_perps")
                    # Keep scanner daily_pnl in sync for its circuit breaker
                    try:
                        import sys
                        if "core.hl_perps_scanner" in sys.modules:
                            sc = getattr(sys.modules["core.hl_perps_scanner"], "_global_scanner", None)
                            if sc is not None:
                                sc.daily_pnl = float(getattr(sc, "daily_pnl", 0.0) or 0.0) + pnl
                    except Exception:
                        pass
                    entry_px = pos.entry_price
                    pnl_pct = None
                    if entry_px and float(close_price):
                        if pos.side == "long":
                            pnl_pct = (float(close_price) - entry_px) / entry_px * 100
                        else:
                            pnl_pct = (entry_px - float(close_price)) / entry_px * 100
                    entry_time = (
                        pos.opened_at.isoformat()
                        if getattr(pos, "opened_at", None)
                        else None
                    )
                    del self.positions[sym]
                    self._save_trailing_state()  # Ensure deleted position is removed from trailing state
                    logger.info(
                        f"✅ Hyperliquid CLOSE {sym} | "
                        f"entry=${pos.entry_price:.4f} → exit=${close_price} | "
                        f"PnL=${pnl:+.2f} | daily_pnl=${self.daily_pnl:+.2f}"
                    )

                    _mfe, _mae = self._calc_mfe_mae(pos)
                    self._log_hl_trade(
                        action="SELL",
                        coin=sym,
                        side=pos.side,
                        price=float(close_price) if close_price else 0.0,
                        quantity=pos.size,
                        value_usd=float(close_price or 0) * pos.size,
                        entry_price=entry_px,
                        pnl_usd=pnl,
                        pnl_pct=pnl_pct,
                        reason="manual_or_monitor_close",
                        leverage=pos.leverage,
                        stop_loss=pos.stop_loss_price,
                        take_profit=pos.take_profit_price,
                        entry_time=entry_time,
                        mfe_pct=_mfe,
                        mae_pct=_mae,
                    )
                    self._inject_scanner_cooldown(sym, loss=(pnl < 0))

                    return {"coin": sym, "close_price": close_price, "pnl": pnl}
                else:
                    # Close rejected — often because we are already flat (ghost local state).
                    # Verify live size and purge so we free slots and stop 429 spam.
                    live_sz = self._exchange_position_size(sym)
                    if live_sz is not None and abs(live_sz) < 1e-12:
                        self._purge_ghost_position(
                            sym,
                            reason=f"close_failed_already_flat:{result}",
                            already_locked=True,
                        )
                        return {"coin": sym, "close_price": 0, "pnl": 0.0, "ghost_purged": True}
                    logger.error(f"Hyperliquid close failed for {sym}: {result}")
                    return None

            except Exception as e:
                # Same ghost path for exceptions (e.g. reduce-only / no position)
                try:
                    live_sz = self._exchange_position_size(sym)
                    if live_sz is not None and abs(live_sz) < 1e-12:
                        self._purge_ghost_position(
                            sym,
                            reason=f"close_exception_already_flat:{e}",
                            already_locked=True,
                        )
                        return {"coin": sym, "close_price": 0, "pnl": 0.0, "ghost_purged": True}
                except Exception:
                    pass
                logger.error(f"Hyperliquid close error for {sym}: {e}")
                return None

    def _close_position_partial(self, sym: str, size_pct: float) -> Optional[dict]:
        """Close a fraction of an open position (Winning TP1). Leaves remainder open."""
        with self._lock:
            pos = self.positions.get(sym)
            if not pos:
                logger.warning(f"Hyperliquid: no open position for {sym} (partial)")
                return None
            if pos.size <= 0:
                return None

            close_sz = pos.size * (size_pct / 100.0)
            # HL rejects dust sizes — leave a viable remainder
            remain = pos.size - close_sz
            if remain <= 0 or close_sz <= 0:
                # Degenerate → full close
                pass
            try:
                if remain <= 0 or close_sz <= 0:
                    result = self._execute_api(self._exchange.market_close, sym)
                    partial = False
                else:
                    result = self._execute_api(
                        self._exchange.market_close, sym, sz=close_sz
                    )
                    partial = True

                if not (result and result.get("status") == "ok"):
                    live_sz = self._exchange_position_size(sym)
                    if live_sz is not None and abs(live_sz) < 1e-12:
                        self._purge_ghost_position(
                            sym,
                            reason=f"partial_close_failed_flat:{result}",
                            already_locked=True,
                        )
                        return {
                            "coin": sym,
                            "close_price": 0,
                            "pnl": 0.0,
                            "ghost_purged": True,
                            "partial": False,
                        }
                    logger.error(f"Hyperliquid partial close failed for {sym}: {result}")
                    return None

                time.sleep(0.4)
                fills = self._get_recent_fills(sym)
                close_price = float(fills[0].get("px", 0) or 0) if fills else 0.0

                if not partial:
                    pnl = self._calc_pnl(pos, close_price) if close_price else 0.0
                    self.daily_pnl += pnl
                    self._feed_daily_goal(pnl, source="scalp_hl_perps")
                    del self.positions[sym]
                    self._save_trailing_state()
                    logger.info(
                        f"✅ Hyperliquid FULL CLOSE (via partial path) {sym} | "
                        f"PnL=${pnl:+.2f}"
                    )
                    return {"coin": sym, "close_price": close_price, "pnl": pnl, "partial": False}

                # Scale position size down; realize proportional PnL on closed slice
                frac = close_sz / pos.size if pos.size else 0.0
                full_pnl = self._calc_pnl(pos, close_price) if close_price else 0.0
                pnl = full_pnl * frac
                self.daily_pnl += pnl
                self._feed_daily_goal(pnl, source="scalp_hl_perps_tp1")
                try:
                    import sys
                    if "core.hl_perps_scanner" in sys.modules:
                        sc = getattr(sys.modules["core.hl_perps_scanner"], "_global_scanner", None)
                        if sc is not None:
                            sc.daily_pnl = float(getattr(sc, "daily_pnl", 0.0) or 0.0) + pnl
                except Exception:
                    pass

                pos.size = remain
                pos.size_usd = pos.size_usd * (1.0 - frac) if pos.size_usd else pos.size_usd
                pos.tp1_hit = True
                pos.trailing_stop_active = True
                self._save_trailing_state()
                logger.info(
                    f"💰 Hyperliquid TP1 PARTIAL {sym} | closed {size_pct:.0f}% "
                    f"({close_sz:.6f} coins) @ ${close_price} | realized≈${pnl:+.2f} | "
                    f"remain={remain:.6f}"
                )
                _mfe, _mae = self._calc_mfe_mae(pos)
                self._log_hl_trade(
                    action="SELL",
                    coin=sym,
                    side=pos.side,
                    price=float(close_price) if close_price else 0.0,
                    quantity=close_sz,
                    value_usd=float(close_price or 0) * close_sz,
                    entry_price=pos.entry_price,
                    pnl_usd=pnl,
                    pnl_pct=None,
                    mfe_pct=_mfe,
                    mae_pct=_mae,
                    reason="winning_tp1_partial",
                    leverage=pos.leverage,
                    stop_loss=pos.stop_loss_price,
                    take_profit=pos.take_profit_price,
                    entry_time=(
                        pos.opened_at.isoformat()
                        if getattr(pos, "opened_at", None)
                        else None
                    ),
                )
                return {
                    "coin": sym,
                    "close_price": close_price,
                    "pnl": pnl,
                    "partial": True,
                    "size_pct": size_pct,
                    "remain_size": remain,
                }
            except Exception as e:
                logger.error(f"Hyperliquid partial close error for {sym}: {e}")
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
        stop_loss_price: Optional[float] = None,
        take_profit_price: Optional[float] = None,
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
        lev = leverage or self.default_leverage

        # Hard notional cap: margin × leverage must stay under max_notional_usd
        if lev > 0 and actual_size_usd * lev > self.max_notional_usd:
            actual_size_usd = round(self.max_notional_usd / lev, 2)
            logger.info(
                f"Hyperliquid: notional cap — margin reduced to ${actual_size_usd:.2f} "
                f"(max notional ${self.max_notional_usd:.0f} @ {lev}x)"
            )

        # ── CAPITAL PROTECTION: total exposure limit ───────────────────
        # FIX (PYTHON-S): Guard against None leverage on synced positions.
        # If a position was synced with leverage=None (null from HL API), the
        # multiplication p.size_usd * p.leverage raises TypeError: 'int' * NoneType.
        current_exposure = sum(
            p.size_usd * (p.leverage or self.default_leverage)
            for p in self.positions.values()
        )
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

        # ── CAPITAL PROTECTION: max margin as % of equity (default 15%) ─
        # Restored after CSV audit — 100% Kelly overrides produced oversized losers.
        if account_value > 0:
            max_margin = round(account_value * self.max_margin_equity_pct, 2)
            if actual_size_usd > max_margin:
                actual_size_usd = max_margin
                logger.info(
                    f"Hyperliquid: margin capped to {self.max_margin_equity_pct*100:.0f}% equity "
                    f"= ${actual_size_usd:.2f}"
                )
            if actual_size_usd < 5.0:
                logger.warning(f"Hyperliquid: cap too small (${actual_size_usd:.2f}) — skip")
                return None
            # Re-apply notional cap after equity clamp
            if lev > 0 and actual_size_usd * lev > self.max_notional_usd:
                actual_size_usd = round(self.max_notional_usd / lev, 2)

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
                notional = actual_size_usd * lev
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

                # Prefer structure/Fib SL+TP from scanner; fall back to fixed %
                sl_price, tp_price, tpsl_source = self._resolve_tpsl_prices(
                    side=side,
                    fill_price=fill_price,
                    stop_loss_pct=self.stop_loss_pct,
                    take_profit_pct=self.take_profit_pct,
                    stop_loss_price=stop_loss_price,
                    take_profit_price=take_profit_price,
                )

                # Post-fill R/R guard — reject if structure levels no longer make sense
                rr = self._rr_ratio(side, fill_price, sl_price, tp_price)
                if rr < self.min_rr_ratio:
                    logger.warning(
                        f"Hyperliquid: {sym} post-fill R/R={rr:.2f}x < {self.min_rr_ratio}x "
                        f"(source={tpsl_source}) — emergency close, no trade"
                    )
                    try:
                        self._execute_api(self._exchange.market_close, sym)
                        self._inject_scanner_cooldown(sym, loss=True, emergency=True)
                        self._log_hl_trade(
                            action="SELL",
                            coin=sym,
                            side="long" if side == "buy" else "short",
                            price=fill_price,
                            quantity=fill_size,
                            value_usd=fill_price * fill_size,
                            entry_price=fill_price,
                            pnl_usd=0.0,
                            pnl_pct=0.0,
                            reason=f"post_fill_rr_reject_{rr:.2f}",
                            gem_score=gem_score,
                            leverage=lev,
                            stop_loss=sl_price,
                            take_profit=tp_price,
                        )
                    except Exception as close_err:
                        logger.error(
                            f"🛑 Post-fill R/R reject close FAILED for {sym}: {close_err}"
                        )
                    return None

                # Place TP/SL orders and capture on-chain order IDs
                sl_oid, tp_oid = self._place_tpsl(sym, side, fill_size, sl_price, tp_price)

                # ── RED TEAM PATCH: No-SL = No-Trade rule ─────────────────────
                # If the SL order failed to place, we have an unprotected leveraged
                # position. Immediately close it at market to preserve capital.
                if sl_oid is None:
                    logger.error(
                        f"🛑 RED TEAM GUARD: SL placement FAILED for {sym} — "
                        f"closing position immediately to prevent unprotected exposure"
                    )
                    try:
                        self._execute_api(
                            self._exchange.market_close,
                            sym,
                        )
                        logger.warning(f"🛑 Emergency close executed for {sym} — no capital at risk")
                        # Long cooldown stops the 3–5s AAVE/HMSTR re-entry loop
                        self._inject_scanner_cooldown(sym, loss=True, emergency=True)
                        self._log_hl_trade(
                            action="SELL",
                            coin=sym,
                            side="long" if side == "buy" else "short",
                            price=fill_price,
                            quantity=fill_size,
                            value_usd=fill_price * fill_size,
                            entry_price=fill_price,
                            pnl_usd=0.0,
                            pnl_pct=0.0,
                            reason="emergency_close_sl_place_failed",
                            gem_score=gem_score,
                            leverage=lev,
                        )
                    except Exception as close_err:
                        logger.error(f"🛑 Emergency close FAILED for {sym}: {close_err} — MANUAL INTERVENTION REQUIRED")
                    return None

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
                filled_notional = fill_price * fill_size
                logger.info(
                    f"✅ Hyperliquid {direction} FILLED: {sym} | "
                    f"size={fill_size} @ ${fill_price:.4f} | "
                    f"margin=${actual_size_usd:.2f} × {lev}x | "
                    f"SL=${sl_price:.4f} / TP=${tp_price:.4f} | "
                    f"R/R={rr:.2f}x source={tpsl_source} | score={gem_score:.0f}"
                )

                self._log_hl_trade(
                    action="BUY",
                    coin=sym,
                    side=direction.lower(),
                    price=fill_price,
                    quantity=fill_size,
                    value_usd=filled_notional,
                    entry_price=fill_price,
                    reason=f"hl_open_{tpsl_source}_rr{rr:.2f}",
                    gem_score=gem_score,
                    leverage=lev,
                    stop_loss=sl_price,
                    take_profit=tp_price,
                    entry_time=pos.opened_at.isoformat(),
                )

                return {
                    "coin": sym,
                    "side": direction.lower(),
                    "fill_price": fill_price,
                    "size": fill_size,
                    "margin_usd": actual_size_usd,
                    "leverage": lev,
                    "notional_usd": filled_notional,
                    "stop_loss": sl_price,
                    "take_profit": tp_price,
                    "rr_ratio": rr,
                    "tpsl_source": tpsl_source,
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

        SL placement uses exponential backoff (3 attempts: 1s, 2s, 4s) before
        returning sl_order_id=None, which triggers the RED TEAM GUARD emergency
        close in _open_position. This prevents the 49-rapid-close bug where HL
        rejects ultra-wide (50%) market SL triggers on illiquid altcoins and the
        bot immediately market-closes the freshly opened position.

        Returns:
            (sl_order_id, tp_order_id) — integer order IDs from HL, or None on failure.
            Stored in HLPosition so the trailing monitor can cancel/replace the SL.
        """
        sl_order_id: Optional[int] = None
        tp_order_id: Optional[int] = None
        try:
            is_buy = entry_side != "buy"  # Close side is opposite of entry

            # Round prices to 5 significant figures
            sl_price = float(f"{sl_price:.5g}")
            tp_price = float(f"{tp_price:.5g}")

            # Limit slippage for TP/SL. TP stays tight (1%), but SL MUST be extremely wide (50%)
            # to guarantee a fill during flash crashes (prevents market orders from converting to resting limit orders).
            sl_slippage = 0.50
            tp_slippage = 0.01
            if is_buy:
                sl_limit_px = float(f"{sl_price * (1 + sl_slippage):.5g}")
                tp_limit_px = float(f"{tp_price * (1 + tp_slippage):.5g}")
            else:
                sl_limit_px = float(f"{sl_price * (1 - sl_slippage):.5g}")
                tp_limit_px = float(f"{tp_price * (1 - tp_slippage):.5g}")

            # ── SL Placement with Exponential Backoff ────────────────────────────
            # ROOT CAUSE FIX for the 49-rapid-close bug:
            # HL rejects wide-limit market SL triggers on illiquid altcoins with
            # "Order price cannot be more than 95% away from the reference price".
            # Without retry, sl_order_id stays None → RED TEAM GUARD fires instantly.
            # We now attempt 3 times (1s, 2s, 4s backoff) before giving up.
            # On the 2nd/3rd attempt we fall back to a tighter 10% slippage limit
            # which HL accepts on illiquid coins while still guaranteeing a fill
            # in all but the most extreme gap scenarios.
            _SL_MAX_ATTEMPTS = 3
            sl_ok = False
            for _sl_attempt in range(1, _SL_MAX_ATTEMPTS + 1):
                # Widen slippage on first attempt (50%), fall back to 10% on retries
                # to avoid the 95%-away rejection on illiquid coins.
                _attempt_slippage = sl_slippage if _sl_attempt == 1 else 0.10
                if is_buy:
                    _attempt_limit_px = float(f"{sl_price * (1 + _attempt_slippage):.5g}")
                else:
                    _attempt_limit_px = float(f"{sl_price * (1 - _attempt_slippage):.5g}")

                sl_result = self._execute_api(
                    self._exchange.order,
                    coin,
                    is_buy,
                    size,
                    _attempt_limit_px,  # limit_px (required by SDK, ignored for market trigger)
                    {"trigger": {"isMarket": True, "triggerPx": sl_price, "tpsl": "sl"}},
                    reduce_only=True,
                )
                sl_ok = sl_result and sl_result.get("status") == "ok"
                if sl_ok:
                    try:
                        statuses = sl_result.get("response", {}).get("data", {}).get("statuses", [])
                        if statuses and isinstance(statuses[0], dict):
                            status_obj = statuses[0]
                            if "error" in status_obj:
                                err_txt = status_obj["error"]
                                # Check if this is the 95%-away rejection (illiquid coin)
                                if "95%" in err_txt or "reference price" in err_txt.lower():
                                    logger.warning(
                                        f"Hyperliquid SL attempt {_sl_attempt}/{_SL_MAX_ATTEMPTS} "
                                        f"rejected (price deviation) for {coin}: {err_txt} "
                                        f"— retrying with tighter limit_px"
                                    )
                                    sl_ok = False
                                else:
                                    logger.error(f"Hyperliquid SL placement rejected by exchange: {err_txt}")
                                    sl_ok = False
                            else:
                                sl_order_id = status_obj.get("resting", {}).get("oid")
                    except Exception as e:
                        logger.error(f"Error parsing Hyperliquid SL response: {e}")
                        sl_ok = False

                if sl_ok:
                    if _sl_attempt > 1:
                        logger.info(
                            f"Hyperliquid SL placed for {coin} on attempt "
                            f"{_sl_attempt}/{_SL_MAX_ATTEMPTS} (slippage={_attempt_slippage*100:.0f}%)"
                        )
                    break  # Success — exit retry loop

                if _sl_attempt < _SL_MAX_ATTEMPTS:
                    _backoff = 2 ** (_sl_attempt - 1)  # 1s, 2s
                    logger.warning(
                        f"Hyperliquid SL attempt {_sl_attempt}/{_SL_MAX_ATTEMPTS} failed for {coin} "
                        f"— retrying in {_backoff}s"
                    )
                    time.sleep(_backoff)
                else:
                    logger.error(
                        f"Hyperliquid SL placement FAILED for {coin} after "
                        f"{_SL_MAX_ATTEMPTS} attempts — RED TEAM GUARD will close position"
                    )

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
                    statuses = tp_result.get("response", {}).get("data", {}).get("statuses", [])
                    if statuses and isinstance(statuses[0], dict):
                        status_obj = statuses[0]
                        if "error" in status_obj:
                            logger.error(f"Hyperliquid TP placement rejected by exchange: {status_obj['error']}")
                            tp_ok = False
                        else:
                            tp_order_id = status_obj.get("resting", {}).get("oid")
                except Exception as e:
                    logger.error(f"Error parsing Hyperliquid TP response: {e}")

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
                    "tp1_hit": bool(getattr(pos, "tp1_hit", False)),
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
                pos.tp1_hit = bool(saved.get("tp1_hit", False))
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
            # SL slippage MUST be extremely wide (50%) to guarantee a fill during flash crashes
            sl_slippage = 0.50
            is_close_buy = pos.side == "short"  # Closing a short = buy
            
            new_sl_price = float(f"{new_sl_price:.5g}")
            
            if is_close_buy:
                sl_limit_px = float(f"{new_sl_price * (1 + sl_slippage):.5g}")
            else:
                sl_limit_px = float(f"{new_sl_price * (1 - sl_slippage):.5g}")

            try:
                # RED TEAM FIX: Market trigger ensures trailing SL fills in flash crashes
                order_type = {"trigger": {"isMarket": True, "triggerPx": new_sl_price, "tpsl": "sl"}}
                
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
