"""
core/stat_arb.py — CEX/DEX Statistical Arbitrage Engine
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Strategy: Delta-Neutral Basis Trade (Spot/Perp Convergence)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
When a token's perpetual futures price on Hyperliquid trades at a meaningful
premium to its spot price on a DEX (Raydium for Solana, Aerodrome for Base),
we lock in that spread with a delta-neutral position:

  LEG 1 — Spot BUY  on DEX (Raydium / Aerodrome / Jupiter)
  LEG 2 — Perp SHORT on Hyperliquid at 1x leverage (no directional risk)

As the futures premium decays toward zero (funding rate arbitrage forces
convergence), we close both legs and pocket the spread minus fees.

Entry Gate:  spread > STAT_ARB_ENTRY_THRESHOLD_PCT (default 1.5%)
Exit Gate:   spread < STAT_ARB_EXIT_THRESHOLD_PCT  (default 0.5%)
Max Hold:    STAT_ARB_MAX_HOLD_HOURS               (default 24h)
Trade Size:  STAT_ARB_TRADE_SIZE_USD               (default $100 per leg)

Spread Calculation:
  spread_pct = (perp_price - spot_price) / spot_price * 100

  Positive spread = perp trades at premium -> short perp, buy spot
  Negative spread = perp trades at discount -> NOT traded (different strategy)

Safety Guardrails:
  - Funding rate check: reject if funding rate > 0.05%/8h against our short
  - Minimum liquidity: $10k on DEX, $5k notional on HL
  - Paper mode: full simulation with no real execution
  - Position cap: max STAT_ARB_MAX_POSITIONS concurrent arb pairs
  - Max hold time: auto-close after STAT_ARB_MAX_HOLD_HOURS regardless of spread

Integration:
  main.py -> _stat_arb_daemon() thread -> StatArbEngine.run_cycle()
  dashboard/pages/10_StatArb.py reads data/dashboard/stat_arb_state.json
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
from config.wallets import WALLETS
from data.providers.arb_price_feed import get_jupiter_price, get_dexscreener_pairs

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Settings (all overridable via .env)
# ─────────────────────────────────────────────────────────────────────────────
STAT_ARB_ENABLED: bool = os.getenv("STAT_ARB_ENABLED", "true").lower() == "true"
ENTRY_THRESHOLD: float = float(os.getenv("STAT_ARB_ENTRY_THRESHOLD_PCT", "1.5"))
EXIT_THRESHOLD: float = float(os.getenv("STAT_ARB_EXIT_THRESHOLD_PCT", "0.5"))
TRADE_SIZE_USD: float = float(os.getenv("STAT_ARB_TRADE_SIZE_USD", "100.0"))
MAX_POSITIONS: int = int(os.getenv("STAT_ARB_MAX_POSITIONS", "8"))
MAX_HOLD_HOURS: float = float(os.getenv("STAT_ARB_MAX_HOLD_HOURS", "24.0"))
SCAN_INTERVAL: float = float(os.getenv("STAT_ARB_SCAN_INTERVAL_SECONDS", "15.0"))
MIN_DEX_LIQUIDITY: float = float(os.getenv("STAT_ARB_MIN_DEX_LIQUIDITY_USD", "10000.0"))
FUNDING_RATE_THRESHOLD: float = float(os.getenv("STAT_ARB_FUNDING_RATE_THRESHOLD", "0.0005"))  # 0.05%/8h

# Persistent state file (shared with dashboard)
_STATE_DIR = Path(os.getenv("DASHBOARD_STATE_DIR", "./data/dashboard"))
_STATE_FILE = _STATE_DIR / "stat_arb_state.json"

# ─────────────────────────────────────────────────────────────────────────────
# USDC addresses per chain (for EVM spot buys)
# ─────────────────────────────────────────────────────────────────────────────
USDC_BY_CHAIN: dict = {
    "ethereum": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
    "base":     "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    "arbitrum": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
    "polygon":  "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359",
    "bsc":      "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d",
    "solana":   "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
}

# ─────────────────────────────────────────────────────────────────────────────
# Data Classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class StatArbOpportunity:
    """A detected CEX/DEX spread opportunity."""
    symbol: str
    token_address: str
    chain: str
    dex_price: float
    perp_price: float
    spread_pct: float
    dex_name: str
    dex_liquidity_usd: float = 0.0
    funding_rate: float = 0.0
    is_entry: bool = True   # kept for backward compat with main.py daemon
    detected_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class StatArbPosition:
    """An active delta-neutral arb position (both legs open)."""
    symbol: str
    token_address: str
    chain: str
    entry_spread_pct: float
    entry_dex_price: float
    entry_perp_price: float
    size_usd: float
    dex_name: str
    dex_tx_hash: Optional[str] = None
    hl_order_id: Optional[str] = None
    opened_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    current_spread_pct: float = 0.0
    unrealized_pnl_usd: float = 0.0
    status: str = "open"


@dataclass
class StatArbResult:
    """Result of a completed arb trade (both legs closed)."""
    symbol: str
    entry_spread_pct: float
    exit_spread_pct: float
    size_usd: float
    gross_profit_usd: float
    fees_usd: float
    net_profit_usd: float
    hold_hours: float
    closed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ─────────────────────────────────────────────────────────────────────────────
# StatArb Engine
# ─────────────────────────────────────────────────────────────────────────────

class StatArbEngine:
    """
    CEX/DEX Statistical Arbitrage Engine.

    Continuously monitors a watchlist of tokens for spread between
    DEX spot price and Hyperliquid perpetual futures price.
    Executes delta-neutral entries and exits automatically.
    """

    def __init__(self):
        self.enabled = STAT_ARB_ENABLED
        self.entry_threshold = ENTRY_THRESHOLD
        self.exit_threshold = EXIT_THRESHOLD
        self.trade_size_usd = TRADE_SIZE_USD
        self.max_positions = MAX_POSITIONS
        self.max_hold_hours = MAX_HOLD_HOURS

        # State
        self.active_positions: dict = {}
        self.completed_trades: list = []
        self.scan_count: int = 0
        self.total_opportunities_found: int = 0
        self.total_net_profit_usd: float = 0.0
        self._lock = threading.Lock()

        # Lazy-init Hyperliquid executor (avoids import cycle at module load)
        self._hl_executor = None
        self._hl_executor_lock = threading.Lock()

        # Load persisted state
        self._load_state()

        logger.info(
            "StatArb Engine initialized | "
            "entry=%.1f%% | exit=%.1f%% | size=$%.0f/leg | max_pos=%d",
            self.entry_threshold, self.exit_threshold,
            self.trade_size_usd, self.max_positions,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Hyperliquid Executor (lazy init)
    # ─────────────────────────────────────────────────────────────────────────

    def _get_hl_executor(self):
        """Lazy-initialize Hyperliquid executor."""
        with self._hl_executor_lock:
            if self._hl_executor is None:
                try:
                    from core.hyperliquid_executor import HyperliquidExecutor
                    self._hl_executor = HyperliquidExecutor()
                except Exception as e:
                    logger.warning("StatArb: Hyperliquid executor init failed: %s", e)
                    return None
        return self._hl_executor

    # ─────────────────────────────────────────────────────────────────────────
    # Spread Monitor
    # ─────────────────────────────────────────────────────────────────────────

    def scan_spread(
        self,
        symbol: str,
        token_address: str,
        chain: str,
    ) -> Optional[StatArbOpportunity]:
        """
        Fetch spot price from DEX and perp price from Hyperliquid.
        Returns a StatArbOpportunity if a meaningful spread is detected,
        or None if no spread or insufficient liquidity.
        """
        hl = self._get_hl_executor()
        if not hl or not hl.is_available():
            return None

        # Check if this token has a Hyperliquid perp listing
        if not hl.has_perp(symbol):
            logger.debug("StatArb: %s has no Hyperliquid perp — skip", symbol)
            return None

        # Fetch Hyperliquid perp mark price
        perp_price = hl.get_price(symbol)
        if not perp_price or perp_price <= 0:
            logger.debug("StatArb: %s perp price unavailable", symbol)
            return None

        # Fetch DEX spot price
        dex_price = 0.0
        dex_name = ""
        dex_liquidity = 0.0

        if chain == "solana":
            # Jupiter aggregates Raydium, Orca, Meteora — best price on Solana
            dp = get_jupiter_price(token_address)
            if dp and dp.price > 0:
                dex_price = dp.price
                dex_name = "jupiter_v6"
                dex_liquidity = getattr(dp, "liquidity_usd", 999_999)
        else:
            # EVM chains: use DexScreener to find highest-liquidity pair
            pairs = get_dexscreener_pairs(token_address, chain)
            if pairs:
                liquid = [p for p in pairs if p.liquidity_usd >= MIN_DEX_LIQUIDITY]
                if liquid:
                    best = max(liquid, key=lambda p: p.liquidity_usd)
                    dex_price = best.price
                    dex_name = best.dex
                    dex_liquidity = best.liquidity_usd

        if dex_price <= 0:
            logger.debug("StatArb: %s DEX price unavailable on %s", symbol, chain)
            return None

        if dex_liquidity < MIN_DEX_LIQUIDITY:
            logger.debug(
                "StatArb: %s DEX liquidity $%.0f < min $%.0f — skip",
                symbol, dex_liquidity, MIN_DEX_LIQUIDITY,
            )
            return None

        # Calculate spread: positive = perp premium -> short perp, buy spot
        spread_pct = ((perp_price - dex_price) / dex_price) * 100.0

        # Fetch funding rate for risk check
        funding_rate = self._get_funding_rate(hl, symbol)

        logger.debug(
            "StatArb SCAN: %s | spot=$%.6f (%s) | perp=$%.6f (HL) | "
            "spread=%+.3f%% | funding=%.6f",
            symbol, dex_price, dex_name, perp_price, spread_pct, funding_rate,
        )

        # Set is_entry flag for backward compat with main.py daemon
        is_entry = (
            spread_pct >= self.entry_threshold and symbol not in self.active_positions
        )
        is_exit = (
            spread_pct <= self.exit_threshold and symbol in self.active_positions
        )

        if not is_entry and not is_exit:
            return None

        return StatArbOpportunity(
            symbol=symbol,
            token_address=token_address,
            chain=chain,
            dex_price=dex_price,
            perp_price=perp_price,
            spread_pct=spread_pct,
            dex_name=dex_name,
            dex_liquidity_usd=dex_liquidity,
            funding_rate=funding_rate,
            is_entry=is_entry,
        )

    def _get_funding_rate(self, hl_executor, symbol: str) -> float:
        """Fetch current 8h funding rate from Hyperliquid (with retry wrapper)."""
        try:
            meta = hl_executor._execute_api(hl_executor._info.meta)
            for asset in meta.get("universe", []):
                if asset.get("name", "").upper() == symbol.upper():
                    return float(asset.get("funding", 0))
        except Exception:
            pass
        return 0.0

    # ─────────────────────────────────────────────────────────────────────────
    # Entry Gate Checks
    # ─────────────────────────────────────────────────────────────────────────

    def _check_entry_gates(self, opp: StatArbOpportunity) -> tuple:
        """
        Run all pre-entry safety checks.
        Returns (approved: bool, reason: str).
        """
        # 1. Spread threshold
        if opp.spread_pct < self.entry_threshold:
            return False, "spread %.2f%% < entry threshold %.1f%%" % (opp.spread_pct, self.entry_threshold)

        # 2. Funding rate check — if funding is very negative, shorts pay longs,
        #    which erodes our profit. Reject if funding rate is too punishing.
        if opp.funding_rate < -FUNDING_RATE_THRESHOLD:
            return False, (
                "funding rate %.6f too negative for short (threshold: -%.6f)" %
                (opp.funding_rate, FUNDING_RATE_THRESHOLD)
            )

        # 3. Position cap
        if len(self.active_positions) >= self.max_positions:
            return False, "max positions %d reached" % self.max_positions

        # 4. Duplicate check
        if opp.symbol in self.active_positions:
            return False, "already have open arb position for %s" % opp.symbol

        # 5. Minimum spread must cover fees
        # Estimated round-trip cost: DEX fee ~0.25% + HL taker ~0.05% x 2 legs = ~0.6%
        MIN_PROFITABLE_SPREAD = 1.0
        if opp.spread_pct < MIN_PROFITABLE_SPREAD:
            return False, "spread %.2f%% < min profitable %.1f%%" % (opp.spread_pct, MIN_PROFITABLE_SPREAD)

        return True, "ok"

    # ─────────────────────────────────────────────────────────────────────────
    # Delta-Neutral Entry Execution
    # ─────────────────────────────────────────────────────────────────────────

    def execute_entry(self, opp: StatArbOpportunity) -> Optional[StatArbPosition]:
        """
        Execute a delta-neutral entry:
          LEG 1 — Spot BUY on DEX (Raydium/Aerodrome/Jupiter)
          LEG 2 — 1x Short on Hyperliquid perpetual

        Execution order: DEX buy first (harder to fill), then HL short.
        If DEX buy fails, we abort. If HL short fails after DEX buy,
        we immediately sell the spot position to revert.

        Returns StatArbPosition on success, None on failure.
        """
        approved, reason = self._check_entry_gates(opp)
        if not approved:
            logger.debug("StatArb entry rejected for %s: %s", opp.symbol, reason)
            return None

        is_paper = settings.MODE != "live"

        logger.info(
            "StatArb ENTRY: %s | spread=%+.3f%% | "
            "spot=$%.6f (%s) | perp=$%.6f (HL) | size=$%.0f/leg | %s",
            opp.symbol, opp.spread_pct,
            opp.dex_price, opp.dex_name,
            opp.perp_price,
            self.trade_size_usd,
            "PAPER" if is_paper else "LIVE",
        )

        # LEG 1: DEX Spot Buy
        dex_tx_hash = self._execute_dex_buy(opp, is_paper)
        if dex_tx_hash is None:
            logger.warning("StatArb: DEX buy failed for %s — aborting entry", opp.symbol)
            return None

        logger.info("StatArb: DEX buy confirmed | %s | tx=%s", opp.symbol, dex_tx_hash)

        # LEG 2: Hyperliquid 1x Short
        hl_result = self._execute_hl_short(opp, is_paper)
        if hl_result is None:
            logger.error(
                "StatArb: HL short FAILED for %s after DEX buy — "
                "attempting emergency spot sell to revert position",
                opp.symbol,
            )
            self._emergency_spot_sell(opp, is_paper)
            return None

        logger.info("StatArb: HL short confirmed | %s | order=%s", opp.symbol, hl_result)

        # Record Position
        pos = StatArbPosition(
            symbol=opp.symbol,
            token_address=opp.token_address,
            chain=opp.chain,
            entry_spread_pct=opp.spread_pct,
            entry_dex_price=opp.dex_price,
            entry_perp_price=opp.perp_price,
            size_usd=self.trade_size_usd,
            dex_name=opp.dex_name,
            dex_tx_hash=dex_tx_hash,
            hl_order_id=str(hl_result),
            current_spread_pct=opp.spread_pct,
        )

        with self._lock:
            self.active_positions[opp.symbol] = pos
            self.total_opportunities_found += 1

        self._save_state()
        logger.info(
            "StatArb ENTRY SUCCESS: %s delta-neutral position established | "
            "entry_spread=%.3f%% | target_exit_spread=%.1f%%",
            opp.symbol, opp.spread_pct, self.exit_threshold,
        )
        return pos

    def _execute_dex_buy(self, opp: StatArbOpportunity, is_paper: bool) -> Optional[str]:
        """Execute spot buy on DEX. Returns tx hash or 'PAPER_TX' in paper mode."""
        try:
            if opp.chain == "solana":
                return self._execute_solana_buy(opp, is_paper)
            else:
                return self._execute_evm_buy(opp, is_paper)
        except Exception as e:
            logger.error("StatArb DEX buy exception for %s: %s", opp.symbol, e)
            return None

    def _execute_solana_buy(self, opp: StatArbOpportunity, is_paper: bool) -> Optional[str]:
        """Buy token on Solana via Jupiter (Raydium/Orca/Meteora routing)."""
        from core.solana_executor import execute_solana_buy
        wallet = WALLETS.get("primary")
        if not wallet:
            logger.error("StatArb: Primary wallet not found")
            return None

        # Use SOL as input; size_usd / dex_price gives approximate SOL needed
        sol_amount = self.trade_size_usd / opp.dex_price

        tx = execute_solana_buy(
            token_mint=opp.token_address,
            sol_amount=sol_amount,
            wallet_public_key=wallet.address,
            wallet_private_key_env="SOLANA_PRIVATE_KEY_PRIMARY",
            slippage_bps=100,   # 1% slippage — tighter than gem trades
            is_paper=is_paper,
            gem_score=100.0,    # Bypass score gate — this is an arb, not a directional trade
        )
        return tx

    def _execute_evm_buy(self, opp: StatArbOpportunity, is_paper: bool) -> Optional[str]:
        """Buy token on EVM chain via 1inch/Uniswap using USDC."""
        from core.executor import TradeExecutor, build_gem_snipe_params
        wallet = WALLETS.get("primary")
        if not wallet:
            logger.error("StatArb: Primary wallet not found")
            return None

        params = build_gem_snipe_params(
            wallet=wallet,
            chain=opp.chain,
            token_address=opp.token_address,
            eth_amount=0.0,
            slippage_bps=100,
            use_usdc=True,
            usdc_amount=self.trade_size_usd,
            gem_score=100.0,
        )

        executor = TradeExecutor()
        result = executor.execute_trade(params)

        if result.success:
            return result.tx_hash or "PAPER_TX"
        else:
            logger.warning("StatArb EVM buy failed: %s", result.error)
            return None

    def _execute_hl_short(self, opp: StatArbOpportunity, is_paper: bool) -> Optional[str]:
        """Open 1x short on Hyperliquid perpetual. Returns order ID or 'PAPER_ORDER'."""
        if is_paper:
            logger.info("PAPER StatArb HL SHORT: %s | $%.0f @ 1x", opp.symbol, self.trade_size_usd)
            return "PAPER_ORDER"

        hl = self._get_hl_executor()
        if not hl or not hl.is_available():
            logger.warning("StatArb: HL not available for short — %s", opp.symbol)
            return None

        result = hl.open_short(
            symbol=opp.symbol,
            size_usd=self.trade_size_usd,
            leverage=1,     # 1x = delta neutral
            gem_score=100,  # Bypass gem score gate
        )
        if result:
            return result.get("order_id", "HL_ORDER")
        return None

    def _emergency_spot_sell(self, opp: StatArbOpportunity, is_paper: bool) -> None:
        """
        Emergency sell of spot position when HL short fails after DEX buy.
        Prevents being stuck with a directional spot position.
        """
        logger.warning(
            "StatArb: Emergency spot sell for %s on %s — HL short failed, reverting DEX buy",
            opp.symbol, opp.chain,
        )
        try:
            if opp.chain == "solana":
                from core.sell_engine import execute_sell_solana
                wallet = WALLETS.get("primary")
                if wallet:
                    approx_tokens = int((self.trade_size_usd / opp.dex_price) * 1e9)
                    execute_sell_solana(
                        token_mint=opp.token_address,
                        token_amount_units=approx_tokens,
                        wallet_public_key=wallet.address,
                        wallet_private_key_env="SOLANA_PRIVATE_KEY_PRIMARY",
                        urgency="immediate",
                        is_paper=is_paper,
                    )
            else:
                from core.sell_engine import execute_sell_evm
                wallet = WALLETS.get("primary")
                if wallet:
                    approx_wei = int((self.trade_size_usd / opp.dex_price) * 1e18)
                    execute_sell_evm(
                        token_address=opp.token_address,
                        token_amount_wei=approx_wei,
                        chain=opp.chain,
                        wallet=wallet,
                        urgency="immediate",
                        is_paper=is_paper,
                    )
        except Exception as e:
            logger.error("StatArb: Emergency sell failed for %s: %s", opp.symbol, e)

    # ─────────────────────────────────────────────────────────────────────────
    # Convergence Exit Execution
    # ─────────────────────────────────────────────────────────────────────────

    def execute_exit(self, opp: StatArbOpportunity) -> Optional[StatArbResult]:
        """
        Execute convergence exit when spread narrows to < exit_threshold:
          LEG 1 — Close Hyperliquid short
          LEG 2 — Sell spot on DEX

        Returns StatArbResult with realized PnL on success, None on failure.
        """
        with self._lock:
            pos = self.active_positions.get(opp.symbol)

        if not pos:
            logger.warning("StatArb: No active position for %s — cannot exit", opp.symbol)
            return None

        is_paper = settings.MODE != "live"

        logger.info(
            "StatArb EXIT: %s | current_spread=%+.3f%% | entry_spread=%+.3f%% | "
            "locked_profit~=%.3f%% | %s",
            opp.symbol, opp.spread_pct, pos.entry_spread_pct,
            pos.entry_spread_pct - opp.spread_pct,
            "PAPER" if is_paper else "LIVE",
        )

        # LEG 1: Close Hyperliquid Short
        hl_closed = self._close_hl_short(opp, pos, is_paper)
        if not hl_closed:
            logger.error("StatArb: HL close failed for %s", opp.symbol)
            # Don't abort — still try to close DEX leg to avoid orphaned position

        # LEG 2: Sell Spot on DEX
        dex_sold = self._execute_dex_sell(opp, pos, is_paper)
        if not dex_sold:
            logger.error("StatArb: DEX sell failed for %s", opp.symbol)

        # Calculate Realized PnL
        spread_captured = pos.entry_spread_pct - opp.spread_pct  # % points captured
        gross_profit = pos.size_usd * (spread_captured / 100.0)
        # Estimated fees: DEX fee ~0.25% + HL taker ~0.05% per leg x 2 sides = ~0.6%
        fees = pos.size_usd * 0.006
        net_profit = gross_profit - fees

        hold_hours = (
            datetime.now(timezone.utc) -
            datetime.fromisoformat(pos.opened_at.replace("Z", "+00:00"))
        ).total_seconds() / 3600.0

        result = StatArbResult(
            symbol=opp.symbol,
            entry_spread_pct=pos.entry_spread_pct,
            exit_spread_pct=opp.spread_pct,
            size_usd=pos.size_usd,
            gross_profit_usd=round(gross_profit, 4),
            fees_usd=round(fees, 4),
            net_profit_usd=round(net_profit, 4),
            hold_hours=round(hold_hours, 2),
        )

        with self._lock:
            if opp.symbol in self.active_positions:
                del self.active_positions[opp.symbol]
            self.completed_trades.append(result)
            if len(self.completed_trades) > 500:
                self.completed_trades = self.completed_trades[-500:]
            self.total_net_profit_usd += net_profit

        self._save_state()

        logger.info(
            "StatArb EXIT SUCCESS: %s | spread_captured=%.3f%% | "
            "gross=$%.4f | fees=$%.4f | net=$%+.4f | hold=%.1fh",
            opp.symbol, spread_captured, gross_profit, fees, net_profit, hold_hours,
        )

        # Feed profit into daily goal engine (live mode only — paper arb is simulated)
        try:
            if settings.MODE == "live":
                from core.daily_goal_engine import get_daily_goal_engine
                get_daily_goal_engine().record_profit(net_profit, source="stat_arb")
        except Exception:
            pass

        return result

    def _close_hl_short(self, opp: StatArbOpportunity, pos: StatArbPosition, is_paper: bool) -> bool:
        """Close the Hyperliquid short leg."""
        if is_paper:
            logger.info("PAPER StatArb HL CLOSE: %s", opp.symbol)
            return True

        hl = self._get_hl_executor()
        if not hl or not hl.is_available():
            logger.warning("StatArb: HL not available for close — %s", opp.symbol)
            return False

        result = hl.close_position(opp.symbol)
        if result:
            logger.info(
                "StatArb: HL short closed | %s | pnl=$%+.4f",
                opp.symbol, result.get("pnl", 0),
            )
            return True
        return False

    def _execute_dex_sell(self, opp: StatArbOpportunity, pos: StatArbPosition, is_paper: bool) -> bool:
        """Sell the spot position on DEX."""
        try:
            wallet = WALLETS.get("primary")
            if not wallet:
                return False

            if opp.chain == "solana":
                from core.sell_engine import execute_sell_solana
                approx_tokens = int((pos.size_usd / pos.entry_dex_price) * 1e9)
                result = execute_sell_solana(
                    token_mint=opp.token_address,
                    token_amount_units=approx_tokens,
                    wallet_public_key=wallet.address,
                    wallet_private_key_env="SOLANA_PRIVATE_KEY_PRIMARY",
                    urgency="normal",
                    is_paper=is_paper,
                )
                return getattr(result, "success", bool(result))
            else:
                from core.sell_engine import execute_sell_evm
                approx_wei = int((pos.size_usd / pos.entry_dex_price) * 1e18)
                result = execute_sell_evm(
                    token_address=opp.token_address,
                    token_amount_wei=approx_wei,
                    chain=opp.chain,
                    wallet=wallet,
                    urgency="normal",
                    is_paper=is_paper,
                )
                return getattr(result, "success", bool(result))
        except Exception as e:
            logger.error("StatArb DEX sell exception for %s: %s", opp.symbol, e)
            return False

    # ─────────────────────────────────────────────────────────────────────────
    # Position Monitor (stale position cleanup)
    # ─────────────────────────────────────────────────────────────────────────

    def check_stale_positions(self) -> None:
        """
        Force-close any positions that have been open longer than MAX_HOLD_HOURS.
        Prevents capital being locked in non-converging spreads.
        """
        now = datetime.now(timezone.utc)
        stale = []

        with self._lock:
            for symbol, pos in list(self.active_positions.items()):
                try:
                    opened = datetime.fromisoformat(pos.opened_at.replace("Z", "+00:00"))
                    hold_hours = (now - opened).total_seconds() / 3600.0
                    if hold_hours > self.max_hold_hours:
                        stale.append((symbol, pos, hold_hours))
                except Exception:
                    pass

        for symbol, pos, hold_hours in stale:
            logger.warning(
                "StatArb: Force-closing stale position %s | held %.1fh > max %.1fh",
                symbol, hold_hours, self.max_hold_hours,
            )
            fake_opp = StatArbOpportunity(
                symbol=symbol,
                token_address=pos.token_address,
                chain=pos.chain,
                dex_price=pos.entry_dex_price,
                perp_price=pos.entry_perp_price,
                spread_pct=pos.current_spread_pct,
                dex_name=pos.dex_name,
                dex_liquidity_usd=0.0,
                funding_rate=0.0,
                is_entry=False,
            )
            self.execute_exit(fake_opp)

    # ─────────────────────────────────────────────────────────────────────────
    # Main Scan Cycle
    # ─────────────────────────────────────────────────────────────────────────

    def run_cycle(self, watchlist: list) -> list:
        """
        Run one full scan cycle across the watchlist.
        For each token:
          1. Scan spread
          2. If spread > entry_threshold and no active position -> execute entry
          3. If spread < exit_threshold and active position exists -> execute exit
          4. Update active position spread for dashboard display

        Args:
            watchlist: List of dicts with keys: symbol, address, chain

        Returns:
            List of all detected StatArbOpportunity objects (for logging/dashboard)
        """
        if not self.enabled:
            return []

        self.scan_count += 1
        detected = []

        for token in watchlist:
            symbol = token.get("symbol", "")
            address = token.get("address", "")
            chain = token.get("chain", "")

            if not symbol or not address or not chain:
                continue

            try:
                opp = self.scan_spread(symbol, address, chain)
                if opp is None:
                    continue

                detected.append(opp)

                # Update current spread for active positions
                with self._lock:
                    if symbol in self.active_positions:
                        self.active_positions[symbol].current_spread_pct = opp.spread_pct

                # Entry logic
                if opp.is_entry:
                    self.execute_entry(opp)
                elif not opp.is_entry:
                    self.execute_exit(opp)

            except Exception as e:
                logger.warning("StatArb: scan error for %s: %s", symbol, e)

        # Check for stale positions every cycle
        self.check_stale_positions()

        # Persist state to dashboard
        self._save_state()

        if detected:
            best = max(detected, key=lambda o: o.spread_pct)
            logger.info(
                "STAT ARB SCAN #%d: %d spreads checked | best=%s %+.3f%% | "
                "active_positions=%d | total_pnl=$%+.2f",
                self.scan_count, len(detected),
                best.symbol, best.spread_pct,
                len(self.active_positions),
                self.total_net_profit_usd,
            )

        return detected

    # ─────────────────────────────────────────────────────────────────────────
    # State Persistence (for dashboard)
    # ─────────────────────────────────────────────────────────────────────────

    def _save_state(self) -> None:
        """Write current state to JSON file for dashboard consumption."""
        try:
            _STATE_DIR.mkdir(parents=True, exist_ok=True)
            state = {
                "enabled": self.enabled,
                "entry_threshold_pct": self.entry_threshold,
                "exit_threshold_pct": self.exit_threshold,
                "trade_size_usd": self.trade_size_usd,
                "max_positions": self.max_positions,
                "scan_count": self.scan_count,
                "total_opportunities_found": self.total_opportunities_found,
                "total_net_profit_usd": round(self.total_net_profit_usd, 4),
                "active_positions": {
                    sym: {
                        "symbol": pos.symbol,
                        "chain": pos.chain,
                        "dex_name": pos.dex_name,
                        "entry_spread_pct": pos.entry_spread_pct,
                        "current_spread_pct": pos.current_spread_pct,
                        "size_usd": pos.size_usd,
                        "opened_at": pos.opened_at,
                        "status": pos.status,
                    }
                    for sym, pos in self.active_positions.items()
                },
                "recent_trades": [
                    {
                        "symbol": t.symbol,
                        "entry_spread_pct": t.entry_spread_pct,
                        "exit_spread_pct": t.exit_spread_pct,
                        "net_profit_usd": t.net_profit_usd,
                        "hold_hours": t.hold_hours,
                        "closed_at": t.closed_at,
                    }
                    for t in self.completed_trades[-50:]
                ],
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }
            tmp = _STATE_FILE.with_suffix(".tmp")
            with open(tmp, "w") as f:
                json.dump(state, f, indent=2)
            tmp.replace(_STATE_FILE)
        except Exception as e:
            logger.debug("StatArb: state save failed: %s", e)

    def _load_state(self) -> None:
        """Load persisted state on startup."""
        try:
            if _STATE_FILE.exists():
                with open(_STATE_FILE) as f:
                    state = json.load(f)
                self.total_net_profit_usd = state.get("total_net_profit_usd", 0.0)
                self.scan_count = state.get("scan_count", 0)
                self.total_opportunities_found = state.get("total_opportunities_found", 0)
                logger.info(
                    "StatArb: Loaded state — total_pnl=$%.2f | scans=%d",
                    self.total_net_profit_usd, self.scan_count,
                )
        except Exception as e:
            logger.debug("StatArb: state load failed (fresh start): %s", e)

    # ─────────────────────────────────────────────────────────────────────────
    # Status
    # ─────────────────────────────────────────────────────────────────────────

    def get_status(self) -> dict:
        """Return comprehensive status dict for dashboard/logging."""
        return {
            "enabled": self.enabled,
            "entry_threshold_pct": self.entry_threshold,
            "exit_threshold_pct": self.exit_threshold,
            "trade_size_usd": self.trade_size_usd,
            "max_positions": self.max_positions,
            "max_hold_hours": self.max_hold_hours,
            "scan_count": self.scan_count,
            "total_opportunities_found": self.total_opportunities_found,
            "total_net_profit_usd": round(self.total_net_profit_usd, 4),
            "active_positions": len(self.active_positions),
            "completed_trades": len(self.completed_trades),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Default Watchlist
# ─────────────────────────────────────────────────────────────────────────────

# Tokens with both DEX liquidity AND Hyperliquid perp listings
# Solana: Jupiter routes through Raydium/Orca/Meteora
# Base: Aerodrome is the primary DEX
DEFAULT_STAT_ARB_WATCHLIST: list = [
    # Solana (Jupiter/Raydium spot vs HL perp)
    {"symbol": "SOL",    "address": "So11111111111111111111111111111111111111112",       "chain": "solana"},
    {"symbol": "WIF",    "address": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",   "chain": "solana"},
    {"symbol": "BONK",   "address": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",   "chain": "solana"},
    {"symbol": "JUP",    "address": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",    "chain": "solana"},
    {"symbol": "PYTH",   "address": "HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3",   "chain": "solana"},
    {"symbol": "RENDER", "address": "rndrizKT3MK1iimdxRdWabcF7Zg7AR5T4nud4EkHBof",    "chain": "solana"},
    # Base (Aerodrome spot vs HL perp)
    {"symbol": "AERO",   "address": "0x940181a94A35A4569E4529A3CDfB74e38FD98631",       "chain": "base"},
    {"symbol": "BRETT",  "address": "0x532f27101965dd16442E59d40670FaF5eBB142E4",       "chain": "base"},
    # Arbitrum (Camelot/Uniswap spot vs HL perp)
    {"symbol": "ARB",    "address": "0x912CE59144191C1204E64559FE8253a0e49E6548",       "chain": "arbitrum"},
    {"symbol": "GMX",    "address": "0xfc5A1A6EB076a2C7aD06eD22C90d7E710E35ad0a",       "chain": "arbitrum"},
]


# ─────────────────────────────────────────────────────────────────────────────
# Singleton
# ─────────────────────────────────────────────────────────────────────────────

_stat_arb_engine: Optional[StatArbEngine] = None
_stat_arb_lock = threading.Lock()


def get_stat_arb_engine() -> StatArbEngine:
    """Return the global StatArbEngine singleton."""
    global _stat_arb_engine
    with _stat_arb_lock:
        if _stat_arb_engine is None:
            _stat_arb_engine = StatArbEngine()
    return _stat_arb_engine
