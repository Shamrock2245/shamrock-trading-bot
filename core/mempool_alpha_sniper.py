"""
core/mempool_alpha_sniper.py — Mempool Alpha-Sniper (ECC Skill: mempool-alpha-sniper)

Intercepts Moralis Streams webhook events for elite smart-money wallets (sniper_score > 90),
calculates position sizing using a Kelly Criterion scaled to the whale's conviction,
runs fast honeypot/rug safety guardrails, and routes execution through private RPCs
(Jito for Solana, Flashbots/CoW for EVM) to achieve same-block execution.

Integration points:
  - Stream:    Hooked into MoralisStreamsServer.on_swap_event and on_solana_alpha_event
               callbacks in main.py — fires on every unconfirmed alpha-wallet buy
  - Scoring:   Reads sniper_leaderboard.json (written by core/sniper_discovery.py)
               to gate on elite wallets with sniper_score > 90
  - Sizing:    Uses wallet_router.calculate_kelly_position_pct() scaled by whale conviction
               (whale_trade_usd / whale_net_worth) to mirror proportional bet sizing
  - Safety:    Calls core/safety.check_token_safety() for honeypot/tax/rug fast-check
  - Execution: Routes through core/executor.execute_trade() (EVM → CoW → Flashbots)
               and core/solana_executor.execute_solana_buy() (Solana → Jito bundle)
  - Async:     All execution runs in background threads so the webhook handler
               returns 200 immediately and never blocks Moralis stream delivery
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from config import settings
from data.models import GemCandidate, Token  # noqa: F401 — used in type hints for _register()

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Configuration knobs (all env-overridable)
# ─────────────────────────────────────────────────────────────────────────────
ELITE_SCORE_THRESHOLD = float(getattr(settings, "MEMPOOL_SNIPER_ELITE_SCORE", 90.0))
MAX_COPY_USD          = float(getattr(settings, "MEMPOOL_SNIPER_MAX_USD", 250.0))
MIN_COPY_USD          = float(getattr(settings, "MEMPOOL_SNIPER_MIN_USD", 10.0))
# Baseline whale conviction (1% of net worth) — below this we scale down
BASELINE_CONVICTION   = float(getattr(settings, "MEMPOOL_SNIPER_BASELINE_CONVICTION", 0.01))
# Max scaling factor applied to Kelly (capped to avoid over-sizing)
MAX_CONVICTION_MULT   = float(getattr(settings, "MEMPOOL_SNIPER_MAX_CONVICTION_MULT", 3.0))
# Dedup window — how many tx hashes to remember
DEDUP_WINDOW          = 1000

# Sniper leaderboard path (written by core/sniper_discovery.py)
_LEADERBOARD_FILE = Path("data/dashboard/sniper_leaderboard.json")
_ACTIVE_SNIPERS_FILE = Path("data/dashboard/sniper_wallets_active.json")


# ─────────────────────────────────────────────────────────────────────────────
# Sniper Wallet Cache — loaded once, refreshed every 5 minutes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class _WalletEntry:
    address: str
    sniper_score: float
    win_rate: float
    total_realized_pnl_usd: float
    net_worth_usd: float  # Best-effort estimate


class _SniperWalletCache:
    """
    Thin in-memory cache of sniper_leaderboard.json.
    Refreshes every 5 minutes so the sniper always uses fresh scores
    without hitting disk on every webhook event.
    """
    _TTL = 300  # seconds

    def __init__(self):
        self._wallets: Dict[str, _WalletEntry] = {}
        self._last_load: float = 0.0
        self._lock = threading.Lock()

    def _load(self) -> None:
        """Load leaderboard from disk into the in-memory dict."""
        wallets: Dict[str, _WalletEntry] = {}

        # 1. Load from sniper_leaderboard.json (primary source)
        if _LEADERBOARD_FILE.exists():
            try:
                with open(_LEADERBOARD_FILE) as f:
                    data = json.load(f)
                for entry in data:
                    addr = (entry.get("address") or "").lower()
                    if not addr:
                        continue
                    wallets[addr] = _WalletEntry(
                        address=addr,
                        sniper_score=float(entry.get("sniper_score", 0.0)),
                        win_rate=float(entry.get("win_rate", 0.0)),
                        total_realized_pnl_usd=float(entry.get("total_realized_pnl_usd", 0.0)),
                        net_worth_usd=float(entry.get("net_worth_usd", 50_000.0)),
                    )
            except Exception as e:
                logger.debug(f"MempoolSniper: Could not load leaderboard: {e}")

        # 2. Supplement with active snipers file (may have wallets not yet in leaderboard)
        if _ACTIVE_SNIPERS_FILE.exists():
            try:
                with open(_ACTIVE_SNIPERS_FILE) as f:
                    active = json.load(f)
                for entry in active.get("wallets", []):
                    addr = (entry.get("address") or "").lower()
                    if addr and addr not in wallets:
                        wallets[addr] = _WalletEntry(
                            address=addr,
                            sniper_score=float(entry.get("sniper_score", 85.0)),
                            win_rate=float(entry.get("win_rate", 0.5)),
                            total_realized_pnl_usd=float(entry.get("total_realized_pnl_usd", 0.0)),
                            net_worth_usd=float(entry.get("net_worth_usd", 50_000.0)),
                        )
            except Exception as e:
                logger.debug(f"MempoolSniper: Could not load active snipers: {e}")

        # 3. Seed with statically configured smart-money wallets as high-baseline entries
        #    (these are in the Moralis stream so they will fire webhooks)
        for addr in getattr(settings, "SMART_MONEY_WALLETS", []):
            a = addr.lower()
            if a not in wallets:
                wallets[a] = _WalletEntry(
                    address=a,
                    sniper_score=92.0,  # Trusted tracked wallet — treat as elite
                    win_rate=0.60,
                    total_realized_pnl_usd=0.0,
                    net_worth_usd=50_000.0,
                )
        for addr in getattr(settings, "ALPHA_WALLETS_SOLANA", []):
            a = addr.lower()
            if a not in wallets:
                wallets[a] = _WalletEntry(
                    address=a,
                    sniper_score=92.0,
                    win_rate=0.60,
                    total_realized_pnl_usd=0.0,
                    net_worth_usd=50_000.0,
                )

        self._wallets = wallets
        self._last_load = time.time()
        logger.debug(f"MempoolSniper: Wallet cache refreshed — {len(wallets)} entries")

    def get(self, wallet_address: str) -> Optional[_WalletEntry]:
        """Return wallet entry if known, refreshing cache if stale."""
        with self._lock:
            if time.time() - self._last_load > self._TTL:
                self._load()
            return self._wallets.get(wallet_address.lower())

    def get_score(self, wallet_address: str) -> float:
        """Return sniper_score for a wallet, or 0.0 if unknown."""
        entry = self.get(wallet_address)
        return entry.sniper_score if entry else 0.0


_wallet_cache = _SniperWalletCache()


# ─────────────────────────────────────────────────────────────────────────────
# Conviction Sizing
# ─────────────────────────────────────────────────────────────────────────────

def _conviction_multiplier(wallet_entry: _WalletEntry, alpha_buy_usd: float) -> float:
    """
    Scale our Kelly fraction by how much of the whale's net worth they are betting.

    If the whale bets 5% of their net worth, that is 5× our baseline of 1%.
    We scale our Kelly up by that ratio, capped at MAX_CONVICTION_MULT.

    Args:
        wallet_entry: Sniper wallet metadata (includes net_worth_usd).
        alpha_buy_usd: USD value of the whale's buy.

    Returns:
        Scaling multiplier in [0.5, MAX_CONVICTION_MULT].
    """
    net_worth = max(wallet_entry.net_worth_usd, 1_000.0)  # floor at $1k
    conviction = alpha_buy_usd / net_worth
    conviction = max(0.0001, min(conviction, 0.50))  # cap at 50% of net worth
    mult = conviction / BASELINE_CONVICTION
    return max(0.5, min(mult, MAX_CONVICTION_MULT))


# ─────────────────────────────────────────────────────────────────────────────
# Main Sniper Class
# ─────────────────────────────────────────────────────────────────────────────

class MempoolAlphaSniper:
    """
    Intercepts Moralis Streams swap events for elite wallets and mirrors
    their trades via Jito (Solana) or Flashbots (EVM) private execution.

    Lifecycle:
        sniper = MempoolAlphaSniper(is_paper=True)
        # Wire into MoralisStreamsServer:
        #   on_swap_event     → sniper.on_evm_swap_event
        #   on_solana_alpha   → sniper.on_solana_alpha_event
    """

    def __init__(self, is_paper: bool = True):
        self.is_paper = is_paper
        self.enabled = getattr(settings, "MEMPOOL_SNIPER_ENABLED", True)
        self._seen_txs: set[str] = set()
        self._seen_lock = threading.Lock()

    # ── Dedup guard ──────────────────────────────────────────────────────────

    def _is_duplicate(self, tx_hash: str) -> bool:
        """Return True if this tx was already processed; otherwise record it."""
        key = tx_hash.lower()
        with self._seen_lock:
            if key in self._seen_txs:
                return True
            self._seen_txs.add(key)
            # Bound memory
            if len(self._seen_txs) > DEDUP_WINDOW:
                self._seen_txs.pop()
        return False

    # ── Public webhook callbacks ─────────────────────────────────────────────

    def on_evm_swap_event(self, wallet_address: str, swap: Dict[str, Any]) -> None:
        """
        Callback wired to MoralisStreamsServer.on_swap_event.

        Called synchronously from the webhook background thread.
        Immediately returns after spawning a daemon thread for execution,
        so the webhook handler is never blocked.
        """
        if not self.enabled:
            return

        tx_hash = swap.get("tx_hash", "")
        if not tx_hash or self._is_duplicate(tx_hash):
            return

        # Score gate — only act on elite wallets
        score = _wallet_cache.get_score(wallet_address)
        if score < ELITE_SCORE_THRESHOLD:
            logger.debug(
                f"MempoolSniper: Skip EVM wallet {wallet_address[:10]}… "
                f"score={score:.1f} < {ELITE_SCORE_THRESHOLD}"
            )
            return

        logger.info(
            f"🔥 MEMPOOL ELITE EVM SIGNAL: {wallet_address[:10]}… "
            f"(score={score:.1f}) bought {swap.get('token_symbol','?')} "
            f"on {swap.get('chain','?')} tx={tx_hash[:12]}…"
        )

        threading.Thread(
            target=self._execute_evm_snipe,
            args=(wallet_address, swap, score),
            name=f"MempoolSniper-EVM-{tx_hash[:8]}",
            daemon=True,
        ).start()

    def on_solana_alpha_event(self, wallet_address: str, swap: Dict[str, Any]) -> None:
        """
        Callback wired to MoralisStreamsServer.on_solana_alpha_event.
        """
        if not self.enabled:
            return

        tx_hash = swap.get("tx_hash", swap.get("signature", ""))
        if not tx_hash or self._is_duplicate(tx_hash):
            return

        score = _wallet_cache.get_score(wallet_address)
        if score < ELITE_SCORE_THRESHOLD:
            logger.debug(
                f"MempoolSniper: Skip Solana wallet {wallet_address[:10]}… "
                f"score={score:.1f} < {ELITE_SCORE_THRESHOLD}"
            )
            return

        logger.info(
            f"🔥 MEMPOOL ELITE SOLANA SIGNAL: {wallet_address[:10]}… "
            f"(score={score:.1f}) bought {swap.get('token_symbol','?')} "
            f"sig={tx_hash[:12]}…"
        )

        threading.Thread(
            target=self._execute_solana_snipe,
            args=(wallet_address, swap, score),
            name=f"MempoolSniper-SOL-{tx_hash[:8]}",
            daemon=True,
        ).start()

    # ── EVM execution ────────────────────────────────────────────────────────

    def _execute_evm_snipe(
        self,
        wallet_address: str,
        swap: Dict[str, Any],
        wallet_score: float,
    ) -> None:
        """
        Full EVM copy-trade pipeline:
          1. Safety check (honeypot / tax / rug)
          2. Kelly sizing scaled by whale conviction
          3. route_trade() to select our wallet + allocation
          4. execute_trade() → CoW → Flashbots private relay
          5. register_position()
        """
        token_address = swap.get("token_address", "").lower()
        chain = swap.get("chain", "").lower()
        token_symbol = swap.get("token_symbol", "UNKNOWN")

        if not token_address or not chain:
            return

        # 1. Safety guardrail
        try:
            from core.safety import check_token_safety
            safety = check_token_safety(token_address, chain)
            if not safety.is_safe:
                logger.info(
                    f"⛔ MempoolSniper EVM REJECTED {token_symbol} [{chain}]: "
                    f"{safety.block_reason}"
                )
                return
        except Exception as e:
            logger.warning(f"MempoolSniper: Safety check failed for {token_symbol}: {e}")
            return

        # 2. Kelly sizing with conviction scaling
        from data.models import Token, GemCandidate
        from core.wallet_router import calculate_kelly_position_pct, route_trade, get_native_price_usd

        token_obj = Token(
            address=token_address,
            symbol=token_symbol,
            name=swap.get("token_name", token_symbol),
            chain=chain,
            price_usd=float(swap.get("price_usd", 0.0)),
            liquidity_usd=float(swap.get("liquidity_usd", 20_000.0)),
            volume_24h=float(swap.get("volume_24h", 50_000.0)),
        )
        candidate = GemCandidate(
            token=token_obj,
            gem_score=wallet_score,
            is_safe=True,
            safety_passed=True,
            smart_money_score=wallet_score,
            express_lane=True,
        )
        candidate.strategy_tag = "mempool_alpha_sniper"

        base_kelly = calculate_kelly_position_pct(gem_score=wallet_score, candidate=candidate)

        wallet_entry = _wallet_cache.get(wallet_address)
        alpha_buy_usd = float(
            swap.get("buy_value_usd", 0.0)
            or swap.get("value_with_decimals", 0.0)
            or 500.0
        )
        conv_mult = _conviction_multiplier(wallet_entry, alpha_buy_usd) if wallet_entry else 1.0

        logger.info(
            f"🧠 MempoolSniper EVM Sizing [{token_symbol}]: "
            f"base_kelly={base_kelly:.2%} | conviction_mult={conv_mult:.2f}x | "
            f"alpha_buy=${alpha_buy_usd:,.0f}"
        )

        # 3. Wallet routing
        allocation = route_trade(
            chain=chain,
            gem_score=wallet_score,
            strategy="gem_snipe",
            is_express=True,
            candidate=candidate,
        )
        if not allocation:
            logger.info(f"MempoolSniper: No wallet route for {token_symbol} on {chain}")
            return

        # Scale position by conviction multiplier (capped by allocation max)
        native_price = get_native_price_usd(allocation.chain.native_token)
        scaled_usd = min(
            allocation.position_size_usd * conv_mult,
            MAX_COPY_USD,
        )
        if scaled_usd < MIN_COPY_USD:
            logger.info(
                f"MempoolSniper: Position too small (${scaled_usd:.2f}) for "
                f"{token_symbol} — skipping"
            )
            return

        scaled_native = scaled_usd / max(native_price, 0.001)
        wallet = allocation.wallet

        # 4. Execute via Flashbots / CoW private relay
        if self.is_paper:
            logger.info(
                f"📝 [PAPER] MempoolSniper EVM: {token_symbol} [{chain}] "
                f"${scaled_usd:.2f} via {wallet.alias}"
            )
            tx_hash = f"paper_mempool_evm_{int(time.time())}"
            success = True
        else:
            try:
                from core.executor import TradeExecutor, build_gem_snipe_params
                executor = TradeExecutor()
                params = build_gem_snipe_params(
                    wallet=wallet,
                    chain=chain,
                    token_address=token_address,
                    eth_amount=scaled_native,
                    gem_score=wallet_score,
                )
                res = executor.execute_trade(params)
                success = res.success
                tx_hash = res.tx_hash or ""
                if not success:
                    logger.error(
                        f"❌ MempoolSniper EVM execution failed for {token_symbol}: "
                        f"{res.error}"
                    )
                    return
                logger.info(
                    f"✅ FLASHBOTS LANDED! MempoolSniper: {token_symbol} [{chain}] "
                    f"${scaled_usd:.2f} tx={tx_hash[:16]}… path={res.execution_path}"
                )
            except Exception as e:
                logger.error(f"MempoolSniper: EVM execution error for {token_symbol}: {e}", exc_info=True)
                return

        # 5. Register position
        self._register(wallet, token_obj, scaled_usd, tx_hash, candidate)

    # ── Solana execution ─────────────────────────────────────────────────────

    def _execute_solana_snipe(
        self,
        wallet_address: str,
        swap: Dict[str, Any],
        wallet_score: float,
    ) -> None:
        """
        Full Solana copy-trade pipeline:
          1. Safety check
          2. Kelly sizing scaled by whale conviction
          3. route_trade() for Solana wallet allocation
          4. execute_solana_buy() → Jupiter V6 + Jito bundle
          5. register_position()
        """
        token_mint = swap.get("token_address", "").lower()
        token_symbol = swap.get("token_symbol", "UNKNOWN")

        if not token_mint:
            return

        # 1. Safety check
        try:
            from core.safety import check_token_safety
            safety = check_token_safety(token_mint, "solana")
            if not safety.is_safe:
                logger.info(
                    f"⛔ MempoolSniper Solana REJECTED {token_symbol}: "
                    f"{safety.block_reason}"
                )
                return
        except Exception as e:
            logger.warning(f"MempoolSniper: Solana safety check failed for {token_symbol}: {e}")
            return

        # 2. Kelly sizing with conviction scaling
        from data.models import Token, GemCandidate
        from core.wallet_router import calculate_kelly_position_pct, route_trade, get_native_price_usd

        token_obj = Token(
            address=token_mint,
            symbol=token_symbol,
            name=swap.get("token_name", token_symbol),
            chain="solana",
            price_usd=float(swap.get("price_usd", 0.0)),
            liquidity_usd=float(swap.get("liquidity_usd", 10_000.0)),
            volume_24h=float(swap.get("volume_24h", 20_000.0)),
        )
        candidate = GemCandidate(
            token=token_obj,
            gem_score=wallet_score,
            is_safe=True,
            safety_passed=True,
            smart_money_score=wallet_score,
            express_lane=True,
        )
        candidate.strategy_tag = "mempool_alpha_sniper_sol"

        base_kelly = calculate_kelly_position_pct(gem_score=wallet_score, candidate=candidate)

        wallet_entry = _wallet_cache.get(wallet_address)
        alpha_buy_usd = float(
            swap.get("buy_value_usd", 0.0)
            or swap.get("value_with_decimals", 0.0)
            or 200.0
        )
        conv_mult = _conviction_multiplier(wallet_entry, alpha_buy_usd) if wallet_entry else 1.0

        logger.info(
            f"🧠 MempoolSniper SOL Sizing [{token_symbol}]: "
            f"base_kelly={base_kelly:.2%} | conviction_mult={conv_mult:.2f}x | "
            f"alpha_buy=${alpha_buy_usd:,.0f}"
        )

        # 3. Wallet routing
        allocation = route_trade(
            chain="solana",
            gem_score=wallet_score,
            strategy="gem_snipe",
            is_express=True,
            candidate=candidate,
        )
        if not allocation:
            logger.info(f"MempoolSniper: No Solana wallet route for {token_symbol}")
            return

        sol_price = get_native_price_usd("SOL")
        scaled_usd = min(allocation.position_size_usd * conv_mult, MAX_COPY_USD)
        if scaled_usd < MIN_COPY_USD:
            logger.info(f"MempoolSniper: Solana position too small (${scaled_usd:.2f}) — skipping")
            return

        sol_amount = scaled_usd / max(sol_price, 0.001)
        wallet = allocation.wallet

        # 4. Execute via Jito bundle
        if self.is_paper:
            logger.info(
                f"📝 [PAPER] MempoolSniper SOL: {token_symbol} "
                f"{sol_amount:.4f} SOL (${scaled_usd:.2f}) via {wallet.alias}"
            )
            tx_hash = f"paper_mempool_sol_{int(time.time())}"
        else:
            try:
                from core.solana_executor import execute_solana_buy
                sol_public_key = wallet.solana_address or wallet.address
                sol_key_env = wallet.solana_private_key_env or wallet.private_key_env
                tx_hash = execute_solana_buy(
                    token_mint=token_mint,
                    sol_amount=sol_amount,
                    wallet_public_key=sol_public_key,
                    wallet_private_key_env=sol_key_env,
                    slippage_bps=allocation.slippage_bps,
                    is_paper=False,
                    gem_score=wallet_score,
                )
                if not tx_hash:
                    logger.error(f"❌ MempoolSniper Solana execution failed for {token_symbol}")
                    return
                logger.info(
                    f"✅ JITO BUNDLE LANDED! MempoolSniper: {token_symbol} "
                    f"{sol_amount:.4f} SOL tx={tx_hash[:16]}…"
                )
            except Exception as e:
                logger.error(f"MempoolSniper: Solana execution error for {token_symbol}: {e}", exc_info=True)
                return

        # 5. Register position
        self._register(wallet, token_obj, scaled_usd, tx_hash, candidate)

    # ── Position registration ────────────────────────────────────────────────

    def _register(
        self,
        wallet,
        token: "Token",
        size_usd: float,
        tx_hash: str,
        candidate: "GemCandidate",
    ) -> None:
        """Register the executed position in the position monitor."""
        try:
            from core.position_monitor import register_position
            register_position(
                token_address=token.address,
                token_symbol=token.symbol,
                chain=token.chain,
                wallet=wallet.alias.lower().replace(" ", "_"),
                entry_price=token.price_usd or 0.0,
                quantity=0.0,  # Populated by position monitor on next sync
                pair_address="",
                tx_hash=tx_hash or "",
                gem_score=candidate.gem_score,
                signal_scores={},
                is_paper=self.is_paper,
                entry_value_usd=size_usd,
                strategy_profile="mempool_alpha_sniper",
            )
            logger.info(
                f"📌 MempoolSniper: Position registered — {token.symbol} [{token.chain}] "
                f"${size_usd:.2f} wallet={wallet.alias} tx={tx_hash[:16]}…"
            )
        except Exception as e:
            logger.error(f"MempoolSniper: Failed to register position for {token.symbol}: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Module-level singleton
# ─────────────────────────────────────────────────────────────────────────────

mempool_sniper = MempoolAlphaSniper(
    is_paper=(getattr(settings, "MODE", "paper") != "live")
)
