"""
main.py — Shamrock Trading Bot entry point.

Usage:
    python main.py                  # Run full bot loop (paper mode by default)
    python main.py --balances       # Fetch and print wallet balances only
    python main.py --scan           # Run one gem scan cycle and print results
    python main.py --snipe <addr> <chain>  # Test gem snipe for a specific token
    python main.py --analyze <addr> <chain>  # Run TA + Fibonacci analysis (no trade)
    python main.py --positions      # Show all open positions and PnL

Environment:
    MODE=paper   → Simulate trades (default, safe)
    MODE=live    → Execute real on-chain trades (requires private keys)

⚠️  NEVER set MODE=live without reviewing all safety guardrails first.
    See GUARDRAILS.md for mandatory pre-live checklist.
"""

import argparse
import asyncio
from collections import deque
import json
import logging
import os
from queue import Empty, Queue
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

import requests

from notifications.slack import notify_trade, notify_alert, notify_cycle_summary

# ─────────────────────────────────────────────────────────────────────────────
# Logging setup — must happen before any other imports
# ─────────────────────────────────────────────────────────────────────────────
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

from logging.handlers import RotatingFileHandler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        RotatingFileHandler(
            LOG_DIR / "bot.log", encoding="utf-8",
            maxBytes=50 * 1024 * 1024, backupCount=5,  # 50MB × 5 = 250MB cap
        ),
    ],
)

# Safety-specific logger (separate file for audit trail)
safety_handler = RotatingFileHandler(
    LOG_DIR / "safety.log", encoding="utf-8",
    maxBytes=50 * 1024 * 1024, backupCount=3,  # 50MB × 3 = 150MB cap
)
safety_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
logging.getLogger("safety").addHandler(safety_handler)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Bot imports (after logging setup)
# ─────────────────────────────────────────────────────────────────────────────
from config import settings
from config.wallets import WALLETS
from core.balance_fetcher import BalanceFetcher, fetch_and_print_balances
from core.safety import check_token_safety
from core.executor import TradeExecutor, build_gem_snipe_params
from core.risk import risk_manager
from core.position_monitor import PositionMonitor, register_position, load_positions
from core.wallet_router import route_trade, route_trade_all
from core.signal_engine import SignalEngine
from core.offensive_guardrails import (
    get_offensive_state,
    save_offensive_state,
    record_trade_result,
    get_effective_min_gem_score,
    calculate_offensive_position_size,
    get_express_overdrive_slippage_bps,
    get_momentum_reentry_candidates,
    register_momentum_reentry,
    evaluate_pyramid_scaling,
    evaluate_fast_fail,
    should_skip_tp1,
    get_daily_summary,
    get_gas_bribe_multiplier,
)
from data.models import GemCandidate
from scanner.gem_scanner import GemScanner
from strategies.gem_snipe import GemSnipeStrategy
from scanner.swing_scanner import SwingScanner
from strategies.swing_strategy import SwingStrategy
from core.adaptive_mode import (
    load_mode_state, save_mode_state, update_capital,
    evaluate_mode, apply_mode, should_run_gems, should_run_swing,
    log_mode_banner, get_mode_status,
    record_gem_trade, record_swing_trade,
)
from dashboard.state import (
    BotStateWriter,
    get_force_scan_request,
    clear_force_scan_request,
    get_pending_manual_commands,
    mark_manual_command_processed,
    clear_processed_manual_commands,
)
from core.daily_floor_guardian import DailyFloorGuardian
from core.bluechip_anchor import BluechipAnchor


# ─────────────────────────────────────────────────────────────────────────────
# Banner
# ─────────────────────────────────────────────────────────────────────────────

BANNER = """
╔══════════════════════════════════════════════════════════════════╗
║           ☘️  SHAMROCK TRADING BOT  ☘️                            ║
║     Multi-Chain Gem Sniper with MEV Protection                   ║
║     Chains: ETH | Base | Arbitrum | Polygon | BSC | Solana       ║
╚══════════════════════════════════════════════════════════════════╝
"""


# ─────────────────────────────────────────────────────────────────────────────
# Core workflows
# ─────────────────────────────────────────────────────────────────────────────

async def run_balance_check() -> dict:
    """Fetch and display all wallet balances. Saves to output/balances.json."""
    balances = await fetch_and_print_balances()
    output_path = OUTPUT_DIR / "balances.json"
    with open(output_path, "w") as f:
        json.dump(balances, f, indent=2, default=str)
    logger.info(f"Balances saved to {output_path}")
    return balances


async def run_gem_scan() -> list[GemCandidate]:
    """Run one gem scan cycle and display top candidates."""
    scanner = GemScanner()
    logger.info("Starting gem scan...")
    candidates = scanner.scan()

    print(f"\n{'='*65}")
    print(f"☘️  GEM SCAN RESULTS — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*65}")
    print(f"Found {len(candidates)} candidates above score threshold {settings.MIN_GEM_SCORE}\n")

    for i, candidate in enumerate(candidates[:20], 1):
        token = candidate.token
        boosted = "🚀 BOOSTED" if token.is_boosted else ""
        express = "⚡ EXPRESS" if getattr(candidate, "express_lane", False) else ""
        print(
            f"{i:2}. [{candidate.gem_score:5.1f}] {token.symbol:<12} | "
            f"{token.chain:<10} | liq=${token.liquidity_usd:>10,.0f} | "
            f"vol1h=${token.volume_1h:>8,.0f} | "
            f"age={f'{token.age_hours:.1f}h' if token.age_hours else 'N/A':<8} "
            f"{boosted} {express}"
        )
        if token.dex_url:
            print(f"     {token.dex_url}")

    # Save to JSON
    output_data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "scan_mode": settings.MODE,
        "total_candidates": len(candidates),
        "top_candidates": [
            {
                "rank": i + 1,
                "symbol": c.token.symbol,
                "name": c.token.name,
                "address": c.token.address,
                "chain": c.token.chain,
                "gem_score": c.gem_score,
                "express_lane": getattr(c, "express_lane", False),
                "price_usd": c.token.price_usd,
                "market_cap": c.token.market_cap,
                "liquidity_usd": c.token.liquidity_usd,
                "volume_24h": c.token.volume_24h,
                "volume_1h": c.token.volume_1h,
                "price_change_1h": c.token.price_change_1h,
                "age_hours": c.token.age_hours,
                "is_boosted": c.token.is_boosted,
                "dex_url": c.token.dex_url,
                "scores": {
                    "age": c.age_score,
                    "volume": c.volume_score,
                    "liquidity": c.liquidity_score,
                    "contract": c.contract_score,
                    "holder": c.holder_score,
                    "tax": c.tax_score,
                    "social": c.social_score,
                    "boost": c.boost_score,
                    "smart_money": c.smart_money_score,
                    "tvl": c.tvl_score,
                    "social_sentiment": c.social_sentiment_score,
                    "holder_concentration": c.holder_concentration_score,
                    "unlock_risk": c.unlock_risk_score,
                },
            }
            for i, c in enumerate(candidates[:50])
        ],
    }
    output_path = OUTPUT_DIR / "gem_scan.json"
    with open(output_path, "w") as f:
        json.dump(output_data, f, indent=2)
    logger.info(f"Scan results saved to {output_path}")
    return candidates


async def run_gem_snipe_example(token_address: str, chain: str) -> dict:
    """
    Ready-to-swap example for gem sniping.
    Runs safety checks, fetches balance, builds trade params, and
    shows exactly what would be executed (paper mode by default).
    """
    print(f"\n{'='*65}")
    print(f"☘️  GEM SNIPE EXAMPLE")
    print(f"{'='*65}")
    print(f"Token:  {token_address}")
    print(f"Chain:  {chain}")
    print(f"Mode:   {settings.MODE.upper()}")
    print()

    # ── Step 1: Safety check ──────────────────────────────────────────────────
    print("Step 1: Running safety checks...")
    safety = check_token_safety(token_address, chain)
    print(f"  GoPlus:       {'✅ PASS' if safety.goplus_passed else '❌ FAIL'}")
    print(f"  Honeypot.is:  {'✅ PASS' if safety.honeypot_passed else '❌ FAIL'}")
    print(f"  TokenSniffer: {'✅ PASS' if safety.tokensniffer_passed else '❌ FAIL'}")
    print(f"  Buy tax:      {safety.buy_tax:.1%}")
    print(f"  Sell tax:     {safety.sell_tax:.1%}")

    if not safety.is_safe:
        print(f"\n🚫 TRADE BLOCKED: {safety.block_reason}")
        return {"blocked": True, "reason": safety.block_reason}

    print(f"  Result:       ✅ SAFE TO TRADE\n")

    # ── Step 2: Fetch wallet balance ──────────────────────────────────────────
    print("Step 2: Fetching Primary wallet balance...")
    fetcher = BalanceFetcher()
    primary_wallet = WALLETS["primary"]
    chain_balances = fetcher.fetch_wallet_chain_balances(primary_wallet, chain)
    native_balance = 0.0
    for token_data in chain_balances.get("tokens", []):
        if token_data.get("is_native"):
            native_balance = token_data.get("balance", 0.0)
            break
    print(f"  {primary_wallet.alias}: {native_balance:.6f} ETH on {chain}\n")

    # ── Step 3: Risk check ────────────────────────────────────────────────────
    print("Step 3: Running risk checks...")
    risk = risk_manager.check_trade(primary_wallet, native_balance, token_address, chain)
    print(f"  Approved:       {'✅ YES' if risk.approved else '❌ NO'}")
    print(f"  Position size:  {risk.position_size_eth:.6f} ETH ({risk.position_size_pct:.1f}% of balance)")
    print(f"  Reason:         {risk.reason}\n")

    if not risk.approved:
        print(f"🚫 TRADE BLOCKED BY RISK MANAGER: {risk.reason}")
        return {"blocked": True, "reason": risk.reason}

    # ── Step 4: Build trade params ────────────────────────────────────────────
    print("Step 4: Building trade parameters...")
    params = build_gem_snipe_params(
        wallet=primary_wallet,
        chain=chain,
        token_address=token_address,
        eth_amount=risk.position_size_eth,
        slippage_bps=200,
    )
    print(f"  Wallet:         {params.wallet.alias} ({params.wallet.address[:10]}...)")
    print(f"  Chain:          {params.chain}")
    print(f"  Token in:       {params.token_in[:10]}... (native)")
    print(f"  Token out:      {params.token_out[:10]}...")
    print(f"  Amount:         {params.amount_in_wei / 1e18:.6f}")
    print(f"  Slippage:       {params.slippage_bps / 100:.1f}%")
    print(f"  Deadline:       {params.deadline_seconds}s\n")

    # ── Step 5: Execute (paper mode) ──────────────────────────────────────────
    print("Step 5: Executing trade...")
    executor = TradeExecutor()
    result = executor.execute_trade(params)
    print(f"  Status:         {'✅ SUCCESS' if result.success else '❌ FAILED'}")
    print(f"  Execution path: {result.execution_path}")
    if result.tx_hash:
        print(f"  TX hash:        {result.tx_hash}")
    if result.amount_out > 0:
        print(f"  Amount out:     {result.amount_out:.6f} tokens")
    if result.error:
        print(f"  Error:          {result.error}")

    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": settings.MODE,
        "token_address": token_address,
        "chain": chain,
        "safety": {
            "is_safe": safety.is_safe,
            "buy_tax": safety.buy_tax,
            "sell_tax": safety.sell_tax,
            "goplus_passed": safety.goplus_passed,
            "honeypot_passed": safety.honeypot_passed,
        },
        "wallet": {
            "alias": primary_wallet.alias,
            "address": primary_wallet.address,
            "balance_eth": native_balance,
        },
        "risk": {
            "approved": risk.approved,
            "position_size_eth": risk.position_size_eth,
            "position_size_pct": risk.position_size_pct,
        },
        "trade_params": {
            "token_in": params.token_in,
            "token_out": params.token_out,
            "amount_in_eth": params.amount_in_wei / 1e18,
            "slippage_bps": params.slippage_bps,
        },
        "result": {
            "success": result.success,
            "execution_path": result.execution_path,
            "tx_hash": result.tx_hash,
            "amount_out": result.amount_out,
            "error": result.error,
        },
    }

    output_path = OUTPUT_DIR / "snipe_example.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\n✅ Full output saved to {output_path}")
    return output


def run_show_positions():
    """Display all open positions and their current PnL."""
    positions = load_positions()
    open_pos = [p for p in positions if p.get("status") == "open"]
    closed_pos = [p for p in positions if p.get("status") == "closed"]

    print(f"\n{'='*75}")
    print(f"☘️  OPEN POSITIONS ({len(open_pos)})")
    print(f"{'='*75}")

    if not open_pos:
        print("  No open positions.")
    else:
        for pos in open_pos:
            entry = float(pos.get("entry_price", 0))
            current = float(pos.get("current_price", entry))
            pnl_pct = pos.get("unrealized_pnl_pct", 0)
            pnl_sign = "+" if pnl_pct >= 0 else ""
            tp1 = "✅" if pos.get("tp1_hit") else "⬜"
            tp2 = "✅" if pos.get("tp2_hit") else "⬜"
            tp3 = "✅" if pos.get("tp3_hit") else "⬜"
            print(
                f"  {pos.get('token_symbol','?'):<12} | {pos.get('chain','?'):<10} | "
                f"entry=${entry:.6f} | now=${current:.6f} | "
                f"PnL={pnl_sign}{pnl_pct:.1f}% | "
                f"TP1={tp1} TP2={tp2} TP3={tp3} | "
                f"wallet={pos.get('wallet','?')}"
            )

    print(f"\n{'='*75}")
    print(f"CLOSED POSITIONS (last 10): {len(closed_pos)} total")
    print(f"{'='*75}")
    for pos in closed_pos[-10:]:
        realized = float(pos.get("realized_pnl_usd", 0))
        sign = "+" if realized >= 0 else ""
        print(
            f"  {pos.get('token_symbol','?'):<12} | {pos.get('chain','?'):<10} | "
            f"PnL={sign}${realized:.2f} | reason={pos.get('last_sell_at','?')[:10]}"
        )


async def run_bot_loop():
    """
    Main bot loop — runs continuously until interrupted.
    Cycle: balance check → gem scan → safety filter → signal check → risk check → execute
    Position monitor runs in a background thread.
    """
    is_paper = settings.MODE != "live"
    logger.info(f"Starting bot loop in {settings.MODE.upper()} mode")
    print(BANNER)
    print(f"Mode:          {settings.MODE.upper()}")
    print(f"Scan interval: {settings.SCAN_INTERVAL_SECONDS}s")
    print(f"Min gem score: {settings.MIN_GEM_SCORE}")
    print(f"Express lane:  ≥{settings.EXPRESS_LANE_SCORE}")
    print(f"Chains:        {', '.join(settings.ACTIVE_CHAINS)}")
    print()

    # ── Persistent BalanceFetcher (reuses Web3 connections across cycles) ──────
    balance_fetcher = BalanceFetcher()

    # ── Start position monitor in background thread ───────────────────────────
    monitor = PositionMonitor(is_paper=is_paper)
    monitor_thread = threading.Thread(
        target=monitor.run_forever,
        name="PositionMonitor",
        daemon=True,
    )
    monitor_thread.start()
    logger.info("Position monitor started in background thread")

    # ── Start proactive smart money copy-trading daemon ───────────────────────────
    # Monitors alpha wallets every 30s and injects copy trades into the
    # express lane when 2+ wallets buy the same token within 2 minutes.
    copy_trade_queue = deque(maxlen=settings.WALLET_MONITOR_FASTLANE_QUEUE_MAX)
    copy_trade_lock = threading.Lock()
    fastlane_queue: Queue = Queue(maxsize=settings.WALLET_MONITOR_FASTLANE_QUEUE_MAX)
    fastlane_seen: set[str] = set()
    fastlane_seen_lock = threading.Lock()
    fastlane_stop = threading.Event()

    # ── Hyperliquid perps executor (zero-gas leveraged trading fallback) ───────
    hl_executor = None
    if settings.HYPERLIQUID_ENABLED:
        try:
            from core.hyperliquid_executor import HyperliquidExecutor
            hl_executor = HyperliquidExecutor()
            if hl_executor.is_available():
                bal = hl_executor.get_balance()
                logger.info(
                    f"🟢 Hyperliquid ready | balance=${bal.get('account_value', 0):.2f} | "
                    f"withdrawable=${bal.get('withdrawable', 0):.2f} | "
                    f"leverage={hl_executor.default_leverage}x"
                )
            else:
                logger.warning("Hyperliquid enabled but not available — check wallet/key config")
                hl_executor = None
        except Exception as e:
            logger.warning(f"Hyperliquid init failed: {e}")
            hl_executor = None

    def _latency_seconds(ts_start) -> float:
        return max(0.0, (datetime.now(timezone.utc) - ts_start).total_seconds())

    def _delay_risk_multiplier(delay_s: float) -> float:
        start = float(settings.COPYTRADE_DELAY_REDUCTION_START_SECONDS)
        reject_at = float(settings.COPYTRADE_MAX_DELAY_REJECT_SECONDS)
        if delay_s >= reject_at:
            return 0.0
        if delay_s <= start:
            return 1.0
        span = max(1.0, reject_at - start)
        # Linear decay down to 20% size before rejection
        return max(0.2, 1.0 - ((delay_s - start) / span) * 0.8)

    def _enqueue_fastlane(candidate, signal) -> None:
        idem_key = f"{signal.tx_hash.lower()}:{signal.token_address.lower()}:{signal.wallet_address.lower()}"
        with fastlane_seen_lock:
            if idem_key in fastlane_seen:
                return
            fastlane_seen.add(idem_key)
        try:
            fastlane_queue.put_nowait((candidate, signal, idem_key))
        except Exception:
            logger.warning("Fastlane queue full — dropping copy-trade candidate")

    def _execute_fastlane_candidate(candidate, signal) -> None:
        token = candidate.token
        signal.candidate_built_at = datetime.now(timezone.utc)

        # Mandatory safety gate
        safety = check_token_safety(token.address, token.chain)
        if not safety.is_safe:
            logger.info(f"Fastlane skip {token.symbol}: {safety.block_reason}")
            return

        # Dedup against existing open positions
        for p in load_positions():
            if p.get("status") == "open" and (p.get("token_address", "").lower() == token.address.lower()):
                logger.info(f"Fastlane dedup skip {token.symbol}: already open")
                return

        allocation = route_trade(chain=token.chain, gem_score=candidate.gem_score, is_express=True)
        if not allocation:
            # ── Hyperliquid fallback: zero-gas leveraged perp ──────────────
            if hl_executor and hl_executor.is_available() and hl_executor.has_perp(token.symbol):
                copy_usd = float(getattr(candidate, "copy_trade_size_usd", 0.0)) or 25.0
                logger.info(
                    f"🔄 Fastlane → Hyperliquid fallback: {token.symbol} "
                    f"(no on-chain route for {token.chain}) | ${copy_usd:.2f}"
                )
                hl_result = hl_executor.open_long(
                    symbol=token.symbol,
                    size_usd=copy_usd,
                    gem_score=candidate.gem_score,
                )
                if hl_result:
                    register_position(
                        token_address=token.address,
                        token_symbol=token.symbol,
                        chain="hyperliquid",
                        wallet="hyperliquid_perp",
                        entry_price=hl_result["fill_price"],
                        quantity=hl_result["size"],
                        pair_address="",
                        tx_hash="",
                        gem_score=candidate.gem_score,
                        is_paper=is_paper,
                        entry_value_usd=hl_result["margin_usd"],
                        strategy_profile="hyperliquid_perp",
                    )
                    logger.info(
                        f"✅ Hyperliquid LONG: {token.symbol} | "
                        f"${hl_result['margin_usd']:.2f} × {hl_result['leverage']}x | "
                        f"fill=${hl_result['fill_price']:.4f} | "
                        f"SL=${hl_result['stop_loss']:.4f} / TP=${hl_result['take_profit']:.4f}"
                    )
                    return
                else:
                    logger.info(f"Hyperliquid fallback skipped for {token.symbol}")
            logger.info(f"Fastlane skip {token.symbol}: no wallet route")
            return
        wallet = allocation.wallet

        # Freshness/risk coupling
        delay_s = _latency_seconds(signal.timestamp)
        size_mult = _delay_risk_multiplier(delay_s)
        if size_mult <= 0:
            logger.info(f"Fastlane reject {token.symbol}: stale signal ({delay_s:.1f}s)")
            return

        # Use position size from allocation (already Kelly-sized), scaled by delay
        position_native = allocation.position_size_native * size_mult
        position_usd = max(allocation.position_size_usd, float(getattr(candidate, "copy_trade_size_usd", 0.0))) * size_mult
        risk = risk_manager.check_trade(
            position_size_native=position_native,
            position_size_usd=position_usd,
            wallet=wallet,
            wallet_balance_native=allocation.native_balance,
            token_address=token.address,
            chain=token.chain,
            usdc_balance=0.0,
        )
        if not risk.approved:
            logger.info(f"Fastlane risk blocked {token.symbol}: {risk.reason}")
            return
        signal.risk_passed_at = datetime.now(timezone.utc)

        if token.chain == "solana":
            from core.solana_executor import execute_solana_buy
            sol_public_key = wallet.solana_address or wallet.address
            sol_key_env = wallet.solana_private_key_env or wallet.private_key_env
            tx_hash = execute_solana_buy(
                token_mint=token.address,
                sol_amount=max(risk.position_size_eth, position_native),
                wallet_public_key=sol_public_key,
                wallet_private_key_env=sol_key_env,
                slippage_bps=allocation.slippage_bps,
                is_paper=is_paper,
            )
            success = tx_hash is not None
            execution_path = "jupiter_fastlane"
            amount_out = 0.0
            err = None if success else "Solana fastlane execution failed"
        else:
            params = build_gem_snipe_params(
                wallet=wallet,
                chain=token.chain,
                token_address=token.address,
                eth_amount=risk.position_size_eth,
                use_usdc=risk.use_usdc,
                usdc_amount=risk.position_size_usdc,
            )
            res = executor.execute_trade(params)
            success = res.success
            tx_hash = res.tx_hash
            execution_path = res.execution_path
            amount_out = res.amount_out
            err = res.error

        if not success:
            # ── On-chain failed → Hyperliquid second-chance ────────────────
            if hl_executor and hl_executor.is_available() and hl_executor.has_perp(token.symbol):
                copy_usd = position_usd or 25.0
                logger.info(
                    f"🔄 On-chain failed → Hyperliquid: {token.symbol} "
                    f"(err={err}) | ${copy_usd:.2f}"
                )
                hl_result = hl_executor.open_long(
                    symbol=token.symbol,
                    size_usd=copy_usd,
                    gem_score=candidate.gem_score,
                )
                if hl_result:
                    register_position(
                        token_address=token.address,
                        token_symbol=token.symbol,
                        chain="hyperliquid",
                        wallet="hyperliquid_perp",
                        entry_price=hl_result["fill_price"],
                        quantity=hl_result["size"],
                        pair_address="",
                        tx_hash="",
                        gem_score=candidate.gem_score,
                        is_paper=is_paper,
                        entry_value_usd=hl_result["margin_usd"],
                        strategy_profile="hyperliquid_perp",
                    )
                    logger.info(
                        f"✅ Hyperliquid rescue LONG: {token.symbol} | "
                        f"${hl_result['margin_usd']:.2f} × {hl_result['leverage']}x"
                    )
                    return
            logger.warning(f"Fastlane trade failed {token.symbol}: {err}")
            return

        signal.broadcasted_at = datetime.now(timezone.utc)
        total_latency = _latency_seconds(signal.timestamp)
        if total_latency > settings.COPYTRADE_LATENCY_SLO_SECONDS:
            notify_alert(
                "⚠️ Copy-trade latency SLO breached",
                f"{token.symbol} {token.chain} latency={total_latency:.1f}s "
                f"(SLO={settings.COPYTRADE_LATENCY_SLO_SECONDS:.1f}s)",
                level="warning",
            )

        register_position(
            token_address=token.address,
            token_symbol=token.symbol,
            chain=token.chain,
            wallet=wallet.alias.lower().replace(" ", "_"),
            entry_price=token.price_usd,
            quantity=amount_out if amount_out > 0 else 0.0,
            pair_address=token.pair_address,
            tx_hash=tx_hash or "",
            gem_score=candidate.gem_score,
            is_paper=is_paper,
            entry_value_usd=position_usd,
            strategy_profile=getattr(wallet.strategy_profile, "name", ""),
        )
        logger.info(
            f"✅ Fastlane copy trade: {token.symbol} [{token.chain}] tx={tx_hash} "
            f"wallet={wallet.alias} size=${position_usd:.2f} "
            f"latency={total_latency:.1f}s source={getattr(signal, 'source', 'polling')}"
        )

    def _fastlane_worker():
        while not fastlane_stop.is_set():
            try:
                candidate, signal, idem_key = fastlane_queue.get(timeout=1.0)
            except Empty:
                continue
            try:
                _execute_fastlane_candidate(candidate, signal)
            except Exception as e:
                logger.error(f"Fastlane worker error: {e}", exc_info=True)
            finally:
                with fastlane_seen_lock:
                    fastlane_seen.discard(idem_key)
                fastlane_queue.task_done()

    try:
        from core.wallet_monitor import start_monitor as _start_wallet_monitor
        def _on_copy_trade_signal(candidate, signal):
            """Callback: enqueue copy-trade candidates for execution in main loop."""
            with copy_trade_lock:
                copy_trade_queue.append((candidate, signal))
            if settings.WALLET_MONITOR_FASTLANE_ENABLED:
                _enqueue_fastlane(candidate, signal)
            logger.info(
                f"🔥 COPY TRADE SIGNAL: {signal.token_symbol} [{signal.chain}] "
                f"Tier {signal.tier} | {len(signal.confirming_wallets)} alpha wallets | "
                f"buy=${signal.buy_value_usd:.0f}"
            )
            try:
                notify_alert(
                    f"🔥 Copy Trade Signal: {signal.token_symbol}",
                    f"Chain: {signal.chain} | Tier {signal.tier} | "
                    f"{len(signal.confirming_wallets)} alpha wallets confirmed | "
                    f"Alpha buy: ${signal.buy_value_usd:.0f}",
                    level="info",
                )
            except Exception:
                pass
        _wallet_monitor = _start_wallet_monitor(on_signal_callback=_on_copy_trade_signal)
        logger.info(
            f"✅ Wallet monitor daemon started: "
            f"{len(getattr(settings, 'SMART_MONEY_WALLETS', []))} alpha wallets tracked"
        )
    except Exception as _wm_err:
        logger.warning(f"Wallet monitor failed to start: {_wm_err}")

    # Optional Moralis Streams webhook server (push-based copy-detection source)
    streams_server = None
    streams_manager = None
    try:
        if settings.MORALIS_STREAMS_ENABLED:
            from core.moralis_streams import MoralisStreamsServer
            from core.wallet_monitor import get_monitor as _get_wallet_monitor
            wm = _get_wallet_monitor()

            # Stable/wrapped tokens that should never be treated as gem candidates
            _STREAM_IGNORED_SYMBOLS = {
                "WETH", "WBTC", "WBNB", "WMATIC", "WAVAX", "USDT", "USDC",
                "USDC.E", "DAI", "BUSD", "USDBC", "STETH", "WSTETH",
            }

            def _stream_evaluate_token(token_address: str, chain: str, source_tag: str) -> None:
                """
                Fast-path gem evaluation triggered by a Moralis Streams event.
                Runs scoring in a short-lived thread so it never blocks the webhook.
                Token is injected into the normal signal pipeline if it scores well.
                """
                import threading as _threading

                def _do_eval():
                    try:
                        from data.providers.dexscreener import get_token_pairs, extract_gem_signals
                        pairs = get_token_pairs(token_address) or []
                        if not pairs:
                            logger.debug(f"Streams eval: no pairs found for {token_address[:10]}...")
                            return
                        pair = pairs[0]
                        signals = extract_gem_signals(pair)
                        signals["is_boosted"] = True
                        signals["boost_amount"] = 150   # Stream event = strong real-money signal
                        token_obj = _gem_scanner._signals_to_token(signals, chain)
                        if not token_obj:
                            return
                        candidate = _gem_scanner._score_token(token_obj, is_boosted=True)
                        if candidate is None:
                            return
                        candidate.strategy_tag = source_tag
                        effective_min = float(getattr(settings, "MIN_GEM_SCORE", 65))
                        if candidate.gem_score >= effective_min:
                            logger.info(
                                f"🚨 STREAM GEM: {token_obj.symbol} [{chain}] "
                                f"scored {candidate.gem_score:.1f} from {source_tag} "
                                f"| liq=${token_obj.liquidity_usd:,.0f}"
                            )
                            # Inject directly into the express queue used by the main loop
                            if hasattr(_gem_scanner, "_stream_candidates"):
                                _gem_scanner._stream_candidates.append(candidate)
                        else:
                            logger.debug(
                                f"Streams eval: {token_obj.symbol} scored {candidate.gem_score:.1f} "
                                f"(below {effective_min:.0f}) — skipped"
                            )
                    except Exception as _ev_err:
                        logger.debug(f"Stream token eval error ({source_tag}): {_ev_err}")

                _threading.Thread(target=_do_eval, name=f"StreamEval-{source_tag}", daemon=True).start()

            # Whale event callback — forward large ERC-20 transfers to gem scorer
            def _on_whale_event(event: dict):
                """Evaluate whale-moved tokens as potential gem candidates."""
                try:
                    token_addr = event.get("token_address", "")
                    chain = event.get("chain", "")
                    token_symbol = (event.get("token_symbol") or "").upper()
                    if not token_addr or not chain:
                        return
                    if token_symbol in _STREAM_IGNORED_SYMBOLS:
                        return
                    logger.info(
                        f"🐋 Whale transfer detected: {token_symbol or token_addr[:10]} "
                        f"on {chain} (tx: {event.get('tx_hash', '?')[:16]}...) "
                        f"— evaluating as gem candidate"
                    )
                    _stream_evaluate_token(token_addr, chain, "whale_stream")
                except Exception as e:
                    logger.debug(f"Whale event handler error: {e}")

            # Liquidity event callback — new DEX pool creation (earliest possible alpha)
            def _on_liquidity_event(event: dict):
                """Evaluate the non-WETH/USDC token in a new pool as a gem candidate."""
                try:
                    chain = event.get("chain", "")
                    # Identify the new token (the non-native side of the pair)
                    token0 = event.get("token0", "")
                    token1 = event.get("token1", "")
                    sym0 = (event.get("symbol0") or "").upper()
                    sym1 = (event.get("symbol1") or "").upper()
                    # The gem is whichever side is NOT a wrapped/stable base asset
                    if sym0 in _STREAM_IGNORED_SYMBOLS and token1:
                        gem_addr, gem_sym = token1, sym1
                    elif sym1 in _STREAM_IGNORED_SYMBOLS and token0:
                        gem_addr, gem_sym = token0, sym0
                    elif token0:
                        gem_addr, gem_sym = token0, sym0
                    else:
                        return
                    logger.info(
                        f"💧 New pool: {sym0 or token0[:6]}/{sym1 or token1[:6]} on {chain} "
                        f"(factory: {event.get('factory', '?')[:12]}...) "
                        f"— evaluating {gem_sym or gem_addr[:8]} as gem candidate"
                    )
                    _stream_evaluate_token(gem_addr, chain, "new_pool_stream")
                except Exception as e:
                    logger.debug(f"Liquidity event handler error: {e}")

            streams_server = MoralisStreamsServer(
                host=settings.MORALIS_STREAMS_HOST,
                port=settings.MORALIS_STREAMS_PORT,
                webhook_secret=settings.MORALIS_STREAMS_WEBHOOK_SECRET,
                on_swap_event=wm.ingest_external_swap,
                on_whale_event=_on_whale_event if settings.MORALIS_STREAMS_WHALE_ENABLED else None,
                on_liquidity_event=_on_liquidity_event if settings.MORALIS_STREAMS_LIQUIDITY_ENABLED else None,
            )
            streams_server.start()

            # Start the Streams Manager (auto-creates streams on Moralis, health checks)
            try:
                from core.moralis_streams_manager import MoralisStreamsManager
                streams_manager = MoralisStreamsManager()
                streams_manager.start()
                logger.info(
                    "✅ Moralis Streams fully activated — "
                    f"webhook server on :{settings.MORALIS_STREAMS_PORT}, "
                    f"manager syncing alpha wallets"
                )
            except Exception as mgr_err:
                logger.warning(f"Moralis Streams Manager failed to start: {mgr_err}")

            # Activate hybrid mode: extend poll interval since streams provide primary signals
            try:
                wm.activate_hybrid_mode()
            except Exception:
                pass  # hybrid mode is a nice-to-have, don't fail on it
    except Exception as stream_err:
        logger.warning(f"Moralis Streams server failed to start: {stream_err}")

    # ── Sniper Discovery Daemon (proactive microcap whale wallet discovery) ───────────────
    _sniper_discovery_daemon = None
    try:
        from core.sniper_discovery import start_discovery as _start_sniper_discovery
        _sniper_discovery_daemon = _start_sniper_discovery(run_immediately=True)
        logger.info(
            "✅ Sniper Discovery daemon started — "
            "proactively harvesting high-PnL microcap wallets from gems "
            "(Moralis profitability/summary + stats + top-traders)"
        )
    except Exception as _sd_err:
        logger.warning(f"Sniper Discovery daemon failed to start: {_sd_err}")

    # ── RL Position Sizer: background training daemon ─────────────────────────────────────────────────────────────────────────────────────
    def _rl_training_daemon():
        """Background thread: trains RL position sizer every 24h."""
        import time as _time
        _time.sleep(60)  # Wait 60s for bot to fully initialize before first training attempt
        while True:
            try:
                from ml.rl_position_sizer import train_rl_agent
                train_rl_agent(force=False)
            except Exception as _rl_daemon_err:
                logger.debug(f"RL training daemon cycle error: {_rl_daemon_err}")
            _time.sleep(3600)  # Check every hour (train_rl_agent enforces 24h interval internally)

    _rl_thread = threading.Thread(target=_rl_training_daemon, daemon=True, name="rl-position-sizer")
    _rl_thread.start()
    logger.info(
        "✅ RL Position Sizer daemon started — "
        "trains PPO agent on completed trades every 24h (neutral 1.0x until 50 trades)"
    )

    # ── Check for Base USDC deployment plan ─────────────────────────────────────────────────────────────────────────────────────
    try:
        if os.path.exists("reports/base_deploy_plan.json"):
            with open("reports/base_deploy_plan.json", "r") as f:
                base_plan = json.load(f)
                if base_plan.get("trades"):
                    logger.info(f"Found Base USDC deployment plan with {len(base_plan['trades'])} trades pending.")
    except Exception as e:
        logger.debug(f"Failed to load Base deploy plan: {e}")

    # Startup notification
    notify_alert(
        "Shamrock Bot Started",
        "Mode: {} | Chains: {} | Interval: {}s | PositionMonitor: ON".format(
            settings.MODE.upper(),
            ", ".join(settings.ACTIVE_CHAINS),
            settings.SCAN_INTERVAL_SECONDS,
        ),
        level="info",
    )

    if settings.MODE == "live":
        logger.warning("=" * 60)
        logger.warning("⚠️  LIVE MODE ACTIVE — REAL TRADES WILL BE EXECUTED")
        logger.warning("=" * 60)

    scanner = GemScanner()
    executor = TradeExecutor()
    strategy = GemSnipeStrategy()
    signal_engine = SignalEngine()
    fastlane_thread = threading.Thread(target=_fastlane_worker, name="CopyTradeFastlane", daemon=True)
    fastlane_thread.start()
    state_writer = BotStateWriter()
    cycle = 0
    trades_this_session = 0
    # Failed-trade cooldown: {token_addr_lower: cycle_num} — skip for 5 cycles after failure
    failed_trade_cooldown: dict[str, int] = {}

    # ── Offensive guardrails state (persistent, survives restarts) ─────────────
    offensive_state = get_offensive_state()
    logger.info(
        f"Offensive state loaded: streak={offensive_state.consecutive_wins}W/"
        f"{offensive_state.consecutive_losses}L | "
        f"daily_pnl=${offensive_state.daily_realized_pnl_usd:.2f} | "
        f"god_mode={'ON ⚡' if offensive_state.god_mode_active else 'off'} | "
        f"house_money=${offensive_state.house_money_pool_usd:.2f}"
    )
    # Legacy profit boost counter (now managed inside offensive_state)
    profit_boost_remaining = offensive_state.profit_boost_remaining

    # ── Adaptive Mode Controller ── load persistent state ──────────────────
    adaptive_state = load_mode_state()
    logger.info(f"Adaptive Mode: loaded state — mode={adaptive_state.mode}, HWM=${adaptive_state.high_water_mark_usd:.0f}")
    # ── Daily Floor Guardian — ensures portfolio never drops over 24h ─────────
    floor_guardian = DailyFloorGuardian()
    # ── Blue-Chip Anchor — always hold % of capital in strongest blue chip ────
    bluechip_anchor = BluechipAnchor()
    # ── Daily PnL Digest Timer — posts structured summary to Slack every 24h ──
    import time as _time_module
    _last_daily_digest_ts: float = _time_module.time()  # reset on bot start

    while True:
        cycle += 1
        trades_this_cycle = 0
        logger.info(f"--- Cycle {cycle} ---")

        try:
            # ── Execute Base USDC Deployment Plan (if exists) ─────────────────
            try:
                if os.path.exists("reports/base_deploy_plan.json"):
                    with open("reports/base_deploy_plan.json", "r") as f:
                        base_plan = json.load(f)
                        
                    if base_plan.get("trades"):
                        logger.info(f"🚀 Executing Base USDC deployment plan: {len(base_plan['trades'])} trades")
                        for trade in base_plan["trades"]:
                            logger.info(f"Deploying ${trade['size_usdc']} USDC into {trade['token_symbol']} on Base")
                            
                            # Execute via EVM path
                            params = build_gem_snipe_params(
                                wallet=WALLETS["primary"],
                                chain="base",
                                token_address=trade["token_address"],
                                eth_amount=0.0,
                                use_usdc=True,
                                usdc_amount=trade["size_usdc"],
                                slippage_bps=trade.get("slippage_bps", 300)
                            )
                            
                            # Apply gas bribe for God Signals
                            if trade.get("score", 0) >= 85.0:
                                params.gas_price_multiplier = 1.5
                                
                            result = executor.execute_trade(params)
                            if result.success:
                                logger.info(f"✅ Base deploy success: {trade['token_symbol']} | tx: {result.tx_hash}")
                                register_position(
                                    token_address=trade["token_address"],
                                    token_symbol=trade["token_symbol"],
                                    chain="base",
                                    wallet=WALLETS["primary"].alias,
                                    pair_address="", # Will be updated by monitor
                                    entry_price=result.amount_out / trade["size_usdc"] if result.amount_out > 0 else 0,
                                    quantity=result.amount_out,
                                    tx_hash=result.tx_hash,
                                    gem_score=trade["score"],
                                    is_paper=is_paper,
                                    entry_value_usd=trade["size_usdc"]
                                )
                            else:
                                logger.error(f"❌ Base deploy failed for {trade['token_symbol']}: {result.error}")
                                
                        # Clear the plan after execution
                        os.remove("reports/base_deploy_plan.json")
                        logger.info("Base deployment plan executed and cleared.")
            except Exception as e:
                logger.error(f"Error executing Base deploy plan: {e}")

            # ── Circuit breaker check ─────────────────────────────────────────
            if risk_manager.is_circuit_breaker_tripped:
                logger.warning("🚨 Circuit breaker is tripped — skipping cycle")
                await asyncio.sleep(settings.SCAN_INTERVAL_SECONDS)
                continue

            # ── Global drawdown sleep check (−20% portfolio → 48h halt) ─────────
            if risk_manager.is_global_sleep_active:
                logger.warning(
                    f"💤 GLOBAL DRAWDOWN SLEEP ACTIVE — skipping cycle. "
                    f"Reason: {risk_manager.global_sleep_reason}"
                )
                await asyncio.sleep(settings.SCAN_INTERVAL_SECONDS)
                continue

            # Check portfolio drawdown from open positions
            all_positions = load_positions()
            open_positions = [p for p in all_positions if p.get("status") == "open"]
            closed_positions = [p for p in all_positions if p.get("status") == "closed"]

            # ── Adaptive Mode: update capital and evaluate mode ──────────────
            try:
                _total_deployed = sum(float(p.get("entry_value_usd", 0)) for p in open_positions)
                _total_unrealized = sum(float(p.get("current_value_usd", 0)) for p in open_positions)
                _portfolio_estimate = max(_total_unrealized, _total_deployed) if open_positions else 0
                update_capital(adaptive_state, _portfolio_estimate)
                recommended_mode = evaluate_mode(adaptive_state)
                mode_changed = apply_mode(adaptive_state, recommended_mode)
                if mode_changed:
                    save_mode_state(adaptive_state)
                log_mode_banner(adaptive_state)
            except Exception as _mode_err:
                logger.debug(f"Adaptive mode check failed (non-blocking): {_mode_err}")

            # ── Daily Floor Guardian + Blue-Chip Anchor ────────────────────────
            _preservation_active = False
            try:
                _total_deployed = sum(float(p.get("entry_value_usd", 0)) for p in open_positions)
                _total_unrealized = sum(float(p.get("current_value_usd", 0)) for p in open_positions)
                _portfolio_usd = max(_total_unrealized, _total_deployed) if open_positions else _total_deployed

                _floor_result = floor_guardian.update(_portfolio_usd)
                _preservation_active = _floor_result["mode"] == "preservation"

                if _floor_result["entered_preservation"]:
                    notify_alert(
                        "🛡️ CAPITAL PRESERVATION MODE ACTIVATED",
                        f"Portfolio ${_portfolio_usd:,.2f} breached daily floor "
                        f"${_floor_result['floor_usd']:,.2f} by {_floor_result['breach_pct']:.1f}%. "
                        f"New entries BLOCKED. Rotating to blue-chip anchor.",
                        level="warning",
                    )
                    # Force anchor rebalance with freed capital
                    _anchor_result = bluechip_anchor.evaluate(
                        portfolio_usd=_portfolio_usd, force_rebalance=True
                    )
                    logger.info(f"🛡️ Anchor rebalance: {_anchor_result['reason']}")

                elif _floor_result["exited_preservation"]:
                    notify_alert(
                        "✅ Capital Preservation Mode Deactivated",
                        f"Portfolio ${_portfolio_usd:,.2f} recovered above floor "
                        f"${_floor_result['floor_usd']:,.2f}. Normal trading resumed.",
                        level="info",
                    )

                # Run anchor evaluation every 6 cycles (not every cycle to avoid rate limits)
                if cycle % 6 == 0:
                    _anchor_result = bluechip_anchor.evaluate(portfolio_usd=_portfolio_usd)
                    if _anchor_result["needs_rebalance"] and not _preservation_active:
                        logger.info(
                            f"⚓ ANCHOR REBALANCE: {_anchor_result['action'].upper()} "
                            f"{_anchor_result['recommended_symbol']} | "
                            f"delta=${_anchor_result['delta_usd']:,.0f} | "
                            f"{_anchor_result['reason']}"
                        )

            except Exception as _guardian_err:
                logger.debug(f"Floor guardian/anchor check failed (non-blocking): {_guardian_err}")

            if open_positions:
                total_entry = sum(float(p.get("entry_value_usd", 0)) for p in open_positions)
                total_current = sum(float(p.get("current_value_usd", 0)) for p in open_positions)

                # Only check if we have meaningful entry data AND current prices are populated
                # When current_value_usd is 0 for all positions, it means prices haven't
                # been refreshed yet — NOT a real 100% loss
                if total_entry > 10 and total_current > 0:
                    portfolio_change_pct = ((total_current - total_entry) / total_entry) * 100
                    if risk_manager.check_circuit_breaker(portfolio_change_pct):
                        notify_alert(
                            "🚨 CIRCUIT BREAKER TRIPPED",
                            f"Portfolio dropped {abs(portfolio_change_pct):.1f}% "
                            f"(threshold: {settings.CIRCUIT_BREAKER_PERCENT}%). "
                            f"All trading halted. Manual reset required.",
                            level="critical",
                        )
                        await asyncio.sleep(settings.SCAN_INTERVAL_SECONDS)
                        continue
                    # Global drawdown sleep: −20% → 48h halt on new entries
                    if risk_manager.check_global_drawdown_sleep(portfolio_change_pct):
                        notify_alert(
                            "💤 GLOBAL DRAWDOWN SLEEP ENGAGED",
                            f"Portfolio dropped {abs(portfolio_change_pct):.1f}% "
                            f"(threshold: {risk_manager.GLOBAL_DRAWDOWN_SLEEP_PCT}%). "
                            f"All new entries halted for "
                            f"{risk_manager.GLOBAL_DRAWDOWN_SLEEP_HOURS:.0f}h. "
                            f"Existing positions continue to be monitored.",
                            level="critical",
                        )
                        await asyncio.sleep(settings.SCAN_INTERVAL_SECONDS)
                        continue
                elif total_entry > 10 and total_current == 0:
                    logger.debug(
                        f"Circuit breaker check skipped: current values are stale "
                        f"(entry=${total_entry:.2f}, current=$0.00)"
                    )

            # ── Build dedup sets (O(1) lookups in candidate loop) ─────────────
            open_token_keys = {
                p["token_address"].lower()
                for p in open_positions
                if p.get("token_address")
            }

            # Build cooldown set: tokens closed within COOLDOWN_HOURS
            cooldown_token_keys = set()
            if settings.COOLDOWN_HOURS > 0:
                now_ts = datetime.now(timezone.utc).timestamp()
                cooldown_window = settings.COOLDOWN_HOURS * 3600
                for p in closed_positions:
                    closed_at = p.get("closed_at")
                    if closed_at:
                        try:
                            closed_ts = datetime.fromisoformat(
                                str(closed_at).replace("Z", "+00:00")
                            ).timestamp()
                            if now_ts - closed_ts < cooldown_window:
                                addr = p.get("token_address", "").lower()
                                if addr:
                                    cooldown_token_keys.add(addr)
                        except Exception:
                            pass

            # ── Sync offensive state with recently closed positions ──────────────
            # Reload offensive state each cycle to pick up any changes
            offensive_state = get_offensive_state()
            profit_boost_remaining = offensive_state.profit_boost_remaining

            # Process newly closed positions: update streak, PnL, house money, etc.
            for p in closed_positions:
                closed_at = p.get("closed_at")
                if not closed_at:
                    continue
                # Only process positions closed since last cycle (within 2x scan interval)
                try:
                    closed_ts = datetime.fromisoformat(
                        str(closed_at).replace("Z", "+00:00")
                    ).timestamp()
                    if now_ts - closed_ts > settings.SCAN_INTERVAL_SECONDS * 2:
                        continue  # Too old — already processed
                except Exception:
                    continue

                # Skip if we've already recorded this close
                pos_id = p.get("id", "")
                if not pos_id or p.get("_offensive_recorded"):
                    continue

                realized_pnl_usd = float(p.get("realized_pnl_usd", 0))
                token_symbol = p.get("token_symbol", "?")
                offensive_state = record_trade_result(
                    offensive_state, realized_pnl_usd, token_symbol
                )
                profit_boost_remaining = offensive_state.profit_boost_remaining

                # Check for momentum reentry (TP1 hit with volume still surging)
                if p.get("tp1_hit") and settings.MOMENTUM_REENTRY_ENABLED:
                    volume_1h = float(p.get("volume_1h", 0))
                    volume_24h = float(p.get("volume_24h", 0))
                    register_momentum_reentry(
                        offensive_state,
                        token_address=p.get("token_address", ""),
                        token_symbol=token_symbol,
                        chain=p.get("chain", ""),
                        tp1_price=float(p.get("last_sell_price", 0)),
                        gem_score=float(p.get("gem_score", 0)),
                        volume_1h=volume_1h,
                        volume_24h=volume_24h,
                    )

            # Effective MIN_GEM_SCORE (lowered by cascade boost on winning streaks)
            effective_min_score = get_effective_min_gem_score(offensive_state)

            # Get momentum reentry candidates (tokens to re-enter after TP1)
            reentry_candidates = get_momentum_reentry_candidates(offensive_state)
            if reentry_candidates:
                logger.info(
                    f"🔄 Momentum reentry candidates: "
                    f"{[c['token_symbol'] for c in reentry_candidates]}"
                )

            # Log God Mode status
            if offensive_state.god_mode_active:
                logger.info(
                    f"⚡⚡⚡ GOD MODE ACTIVE ⚡⚡⚡ "
                    f"daily_pnl=${offensive_state.daily_realized_pnl_usd:.2f} | "
                    f"Full Kelly sizing | TP1 {'skipped' if settings.GOD_MODE_SKIP_TP1 else 'active'}"
                )
            # 1. Fetch balances
            fetcher = balance_fetcher  # Reuse persistent instance

            # 1.5 Process any pending scaling signals from the PositionMonitor
            try:
                positions = load_positions()
                scaling_dirty = False  # track if we need to save
                for p in positions:
                    scaling_signal = p.get("_scaling_signal")
                    if not scaling_signal or p.get("status") != "open":
                        continue

                    token_sym = p.get("token_symbol", "???")
                    chain = p.get("chain", scaling_signal.get("chain", ""))
                    add_size_usd = float(scaling_signal.get("add_size_usd", 0))
                    tier = scaling_signal.get("tier", "?")
                    new_trailing = scaling_signal.get("new_trailing_stop_pct")

                    logger.info(
                        f"📈 Pyramid tier {tier} scale-in for {token_sym} — "
                        f"${add_size_usd:.2f} on {chain}"
                    )

                    # Guard: nothing to buy
                    if add_size_usd <= 0:
                        logger.warning(f"Pyramid signal for {token_sym} has add_size_usd={add_size_usd}, skipping")
                        p["_scaling_signal"] = None
                        scaling_dirty = True
                        continue

                    # Guard: don't exceed max position size
                    max_pos = float(getattr(settings, "OFFENSIVE_MAX_POSITION_USD", 500))
                    current_value = float(p.get("entry_value_usd", 0))
                    if current_value + add_size_usd > max_pos:
                        logger.warning(
                            f"Pyramid for {token_sym} would exceed max (${current_value:.0f}+${add_size_usd:.0f} > ${max_pos:.0f}), capping"
                        )
                        add_size_usd = max(0, max_pos - current_value)
                        if add_size_usd < 5:  # too small to bother
                            p["_scaling_signal"] = None
                            scaling_dirty = True
                            continue

                    # Resolve wallet config from address stored on position
                    wallet_addr = p.get("wallet", "")
                    wallet_conf = None
                    for wk, wv in WALLETS.items():
                        if (wv.address.lower() == wallet_addr.lower()
                                or wv.solana_address == wallet_addr
                                or wk == wallet_addr.lower()
                                or wv.alias.lower() == wallet_addr.lower()):
                            wallet_conf = wv
                            break

                    if not wallet_conf:
                        logger.error(f"Pyramid: no wallet found for address {wallet_addr}, skipping")
                        p["_scaling_signal"] = None
                        scaling_dirty = True
                        continue

                    # Execute the buy
                    executed = False
                    tx_hash = None
                    try:
                        if chain.lower() == "solana":
                            from core.solana_executor import execute_solana_buy
                            # Convert USD → SOL using CoinGecko
                            try:
                                sol_price_resp = requests.get(
                                    "https://api.coingecko.com/api/v3/simple/price",
                                    params={"ids": "solana", "vs_currencies": "usd"},
                                    timeout=10,
                                )
                                sol_price = sol_price_resp.json().get("solana", {}).get("usd", 0)
                            except Exception:
                                sol_price = 0
                            if sol_price <= 0:
                                logger.error("Cannot fetch SOL price for pyramid — skipping")
                                p["_scaling_signal"] = None
                                scaling_dirty = True
                                continue
                            sol_amount = add_size_usd / sol_price
                            sol_public_key = wallet_conf.solana_address or wallet_conf.address
                            sol_key_env = wallet_conf.solana_private_key_env or wallet_conf.private_key_env
                            tx_hash = execute_solana_buy(
                                token_mint=p.get("token_address", ""),
                                sol_amount=sol_amount,
                                wallet_public_key=sol_public_key,
                                wallet_private_key_env=sol_key_env,
                                slippage_bps=150,
                                is_paper=is_paper,
                            )
                            executed = tx_hash is not None
                        else:
                            # EVM chain — buy with USDC via build_gem_snipe_params
                            scale_executor = TradeExecutor(is_paper=is_paper)
                            params = build_gem_snipe_params(
                                wallet=wallet_conf,
                                chain=chain,
                                token_address=p.get("token_address", ""),
                                eth_amount=0.0,  # not using native — using USDC
                                use_usdc=True,
                                usdc_amount=add_size_usd,
                            )
                            result = scale_executor.execute_trade(params)
                            executed = result.success
                            tx_hash = result.tx_hash
                    except Exception as ex:
                        logger.error(f"Pyramid execution failed for {token_sym}: {ex}")
                        executed = False

                    # Update position metadata only on success
                    if executed:
                        p["scale_in_count"] = int(p.get("scale_in_count", 0)) + 1
                        p["entry_value_usd"] = current_value + add_size_usd
                        if new_trailing is not None:
                            p["trailing_stop_pct"] = new_trailing
                        logger.info(
                            f"✅ Pyramid scale-in SUCCESS: {token_sym} tier {tier} "
                            f"+${add_size_usd:.2f} (total invested: ${p['entry_value_usd']:.2f}, "
                            f"scale-ins: {p['scale_in_count']})"
                        )
                    else:
                        logger.warning(f"❌ Pyramid scale-in FAILED for {token_sym} — no metadata update")

                    # Always clear signal to prevent re-processing
                    p["_scaling_signal"] = None
                    scaling_dirty = True

                # Save once after processing all signals
                if scaling_dirty:
                    from core.position_monitor import save_positions
                    save_positions(positions)

            except Exception as e:
                logger.error(f"Error processing scaling signals: {e}", exc_info=True)

            # 1.9 Global regime gate — check market regime before scanning
            # CHOP (pseudo-ADX < 20, low volume): skip new entries this cycle
            # EXPANSION: full nuclear sizing active on Wallet B
            # NORMAL: standard sizing on both wallets
            _regime_skip_new_entries = False
            try:
                from core.regime_filter import get_regime, Regime
                _regime_state = get_regime()
                logger.info(f"📊 Market Regime [cycle {cycle}]: {_regime_state.details}")
                if _regime_state.regime == Regime.CHOP:
                    logger.warning(
                        "😴 CHOP REGIME — skipping new entries this cycle. "
                        "Both wallets operating at 30% sizing. "
                        f"Details: {_regime_state.details}"
                    )
                    _regime_skip_new_entries = True
                elif _regime_state.regime == Regime.EXPANSION:
                    logger.info(
                        "🚀 EXPANSION REGIME — Wallet B nuclear sizing ACTIVE (+50% mult). "
                        "Primary at standard sizing."
                    )
            except Exception as _regime_err:
                logger.debug(f"Regime check failed (non-blocking): {_regime_err}")
                _regime_skip_new_entries = False

            # ── Force-Scan Trigger: check if dashboard requested an immediate scan ─────
            _force_scan_req = get_force_scan_request()
            if _force_scan_req.get("requested"):
                logger.info(
                    f"⚡ FORCE SCAN REQUESTED from dashboard — "
                    f"reason={_force_scan_req.get('reason', 'manual')} "
                    f"requested_at={_force_scan_req.get('requested_at', '')}"
                )
                clear_force_scan_request()
                _force_scan_this_cycle = True
            else:
                _force_scan_this_cycle = False

            # ── Manual Intervention Commands: process dashboard-queued buy/sell/close ──
            # These bypass score gates but NEVER bypass safety/honeypot checks.
            # Processed at the top of every cycle so response latency ≤ 1 cycle.
            try:
                _manual_cmds = get_pending_manual_commands()
                if _manual_cmds:
                    logger.info(f"🎮 MANUAL COMMANDS: {len(_manual_cmds)} pending — processing now")
                    _positions_for_manual = load_positions()
                    _positions_dirty = False

                    for _cmd in _manual_cmds:
                        _cmd_type = _cmd.get("type", "")
                        _cmd_ts = _cmd.get("requested_at", "")
                        _cmd_chain = _cmd.get("chain", "")
                        _cmd_addr = _cmd.get("token_address", "").lower()
                        _cmd_sym = _cmd.get("symbol", "?")

                        try:
                            if _cmd_type in ("manual_sell", "manual_close"):
                                _sell_pct = float(_cmd.get("sell_pct", 100.0)) / 100.0
                                # Find matching open position
                                _target_pos = None
                                for _p in _positions_for_manual:
                                    if (
                                        _p.get("token_address", "").lower() == _cmd_addr
                                        and _p.get("chain", "") == _cmd_chain
                                        and _p.get("status", "open") == "open"
                                    ):
                                        _target_pos = _p
                                        break

                                if not _target_pos:
                                    logger.warning(
                                        f"🎮 Manual sell: no open position found for "
                                        f"{_cmd_sym} ({_cmd_addr[:10]}...) on {_cmd_chain}"
                                    )
                                    mark_manual_command_processed(_cmd_ts, result="no_position_found")
                                    continue

                                # Fetch current price from DexScreener
                                try:
                                    _ds_resp = requests.get(
                                        f"https://api.dexscreener.com/latest/dex/tokens/{_cmd_addr}",
                                        timeout=8,
                                    )
                                    _ds_data = _ds_resp.json()
                                    _pairs = _ds_data.get("pairs") or []
                                    _current_price = float(
                                        _pairs[0].get("priceUsd", 0) if _pairs else 0
                                    )
                                except Exception:
                                    _current_price = float(_target_pos.get("current_price", 0))

                                if _current_price <= 0:
                                    _current_price = float(_target_pos.get("entry_price", 0))

                                from core.position_monitor import execute_sell
                                _sell_action = {
                                    "sell_pct": _sell_pct,
                                    "reason": _cmd.get("reason", "manual_intervention"),
                                    "urgency": "immediate",
                                }
                                _updated_pos = execute_sell(
                                    _target_pos, _sell_action, _current_price, is_paper=is_paper
                                )
                                if _updated_pos is None:
                                    # Fully closed
                                    _positions_for_manual = [
                                        _p for _p in _positions_for_manual
                                        if _p.get("token_address", "").lower() != _cmd_addr
                                        or _p.get("chain", "") != _cmd_chain
                                    ]
                                else:
                                    for _i, _p in enumerate(_positions_for_manual):
                                        if (
                                            _p.get("token_address", "").lower() == _cmd_addr
                                            and _p.get("chain", "") == _cmd_chain
                                        ):
                                            _positions_for_manual[_i] = _updated_pos
                                            break
                                _positions_dirty = True
                                logger.info(
                                    f"🎮 Manual sell executed: {_cmd_sym} "
                                    f"{_sell_pct*100:.0f}% @ ${_current_price:.8f} "
                                    f"chain={_cmd_chain} reason={_cmd.get('reason')}"
                                )
                                mark_manual_command_processed(_cmd_ts, result="executed")

                            elif _cmd_type == "manual_buy":
                                _usd_amount = float(_cmd.get("usd_amount", 0))
                                _wallet_alias = _cmd.get("wallet", "primary")
                                if _usd_amount <= 0:
                                    logger.warning(f"🎮 Manual buy: invalid usd_amount={_usd_amount}")
                                    mark_manual_command_processed(_cmd_ts, result="invalid_amount")
                                    continue

                                # Safety check first — NEVER bypass this
                                _safety = check_token_safety(_cmd_addr, _cmd_chain)
                                if not _safety.is_safe:
                                    logger.warning(
                                        f"🎮 Manual buy BLOCKED by safety: "
                                        f"{_cmd_sym} — {_safety.block_reason}"
                                    )
                                    mark_manual_command_processed(
                                        _cmd_ts, result=f"safety_blocked:{_safety.block_reason}"
                                    )
                                    continue

                                _buy_wallet = WALLETS.get(_wallet_alias) or WALLETS.get("primary")
                                if not _buy_wallet:
                                    logger.error(f"🎮 Manual buy: wallet '{_wallet_alias}' not found")
                                    mark_manual_command_processed(_cmd_ts, result="wallet_not_found")
                                    continue

                                _executed_buy = False
                                _buy_tx = None
                                try:
                                    if _cmd_chain == "solana":
                                        from core.solana_executor import execute_solana_buy
                                        try:
                                            _sol_price_r = requests.get(
                                                "https://api.coingecko.com/api/v3/simple/price",
                                                params={"ids": "solana", "vs_currencies": "usd"},
                                                timeout=10,
                                            )
                                            _sol_price = _sol_price_r.json().get("solana", {}).get("usd", 0)
                                        except Exception:
                                            _sol_price = 0
                                        if _sol_price > 0:
                                            _sol_amt = _usd_amount / _sol_price
                                            _buy_tx = execute_solana_buy(
                                                token_mint=_cmd_addr,
                                                sol_amount=_sol_amt,
                                                wallet_public_key=_buy_wallet.solana_address or _buy_wallet.address,
                                                wallet_private_key_env=_buy_wallet.solana_private_key_env or _buy_wallet.private_key_env,
                                                slippage_bps=200,
                                                is_paper=is_paper,
                                            )
                                            _executed_buy = _buy_tx is not None
                                        else:
                                            logger.error("🎮 Manual buy: cannot fetch SOL price")
                                    else:
                                        _manual_executor = TradeExecutor(is_paper=is_paper)
                                        _params = build_gem_snipe_params(
                                            wallet=_buy_wallet,
                                            chain=_cmd_chain,
                                            token_address=_cmd_addr,
                                            eth_amount=0.0,
                                            use_usdc=True,
                                            usdc_amount=_usd_amount,
                                        )
                                        _result = _manual_executor.execute_trade(_params)
                                        _executed_buy = _result.success
                                        _buy_tx = _result.tx_hash
                                except Exception as _buy_err:
                                    logger.error(f"🎮 Manual buy execution error: {_buy_err}")

                                _result_str = f"executed:tx={_buy_tx}" if _executed_buy else "execution_failed"
                                logger.info(
                                    f"🎮 Manual buy {'SUCCESS' if _executed_buy else 'FAILED'}: "
                                    f"{_cmd_sym} ${_usd_amount:.2f} on {_cmd_chain} "
                                    f"wallet={_wallet_alias} tx={_buy_tx}"
                                )
                                mark_manual_command_processed(_cmd_ts, result=_result_str)

                        except Exception as _cmd_err:
                            logger.error(f"🎮 Manual command error ({_cmd_type}): {_cmd_err}", exc_info=True)
                            mark_manual_command_processed(_cmd_ts, result=f"error:{_cmd_err}")

                    if _positions_dirty:
                        from core.position_monitor import save_positions
                        save_positions(_positions_for_manual)

                    # Housekeeping: purge old processed commands every 100 cycles
                    if cycle % 100 == 0:
                        clear_processed_manual_commands()

            except Exception as _manual_err:
                logger.error(f"Manual command processing error: {_manual_err}", exc_info=True)

            # 2. Scan for gems (adaptive: every cycle in NORMAL, every 3rd in RECOVERY)
            candidates = []
            if _force_scan_this_cycle or should_run_gems(adaptive_state, cycle):
                candidates = scanner.scan()
                label = " [⚡ FORCE SCAN]" if _force_scan_this_cycle else ""
                logger.info(f"Cycle {cycle}: {len(candidates)} gem candidates found{label}")
            else:
                logger.info(f"Cycle {cycle}: ⏭️ Skipping gem scan (RECOVERY mode — gems every {adaptive_state.gem_frequency} cycles)")

            # Inject copy-trade signals from wallet monitor (highest priority).
            # This turns the monitor from "alert-only" into actionable execution:
            # detected alpha buys are processed in the same cycle trade loop.
            with copy_trade_lock:
                queued_copy_signals = list(copy_trade_queue)
                copy_trade_queue.clear()
            if queued_copy_signals:
                copy_candidates = [item[0] for item in queued_copy_signals]
                candidates = copy_candidates + candidates
                logger.info(
                    f"🔥 Injected {len(copy_candidates)} copy-trade candidate(s) "
                    f"from WalletMonitor into cycle {cycle}"
                )

            # Drain Moralis Streams real-time gem candidates (highest-conviction alpha —
            # these arrived between scan cycles directly from whale & new-pool events).
            if scanner._stream_candidates:
                stream_batch = []
                while scanner._stream_candidates:
                    stream_batch.append(scanner._stream_candidates.popleft())
                # Sort by score descending; prepend so they get priority processing
                stream_batch.sort(key=lambda c: c.gem_score, reverse=True)
                candidates = stream_batch + candidates
                logger.info(
                    f"⚡ Injected {len(stream_batch)} real-time stream candidate(s) "
                    f"from Moralis Streams into cycle {cycle} "
                    f"(top score: {stream_batch[0].gem_score:.1f} via {stream_batch[0].strategy_tag})"
                )

            # 3. Process candidates (iterate all, but cap successful trades)
            # ── PRESERVATION MODE GATE: block all new entries if floor breached ─────
            if _preservation_active:
                logger.warning(
                    f"🛡️ CAPITAL PRESERVATION MODE: skipping all {len(candidates)} candidates. "
                    f"Floor=${floor_guardian.floor_usd:,.2f} | "
                    f"Current=${floor_guardian.state.current_portfolio_usd:,.2f} | "
                    f"Daily P&L={floor_guardian.daily_gain_pct:+.1f}%"
                )
                candidates = []  # Block all entries

            for candidate in candidates:
                # ── GUARD 0: Symbol pre-filter — NEVER trade wrapped natives, stables, LSDs ──
                # Check before any expensive safety/TA calls.
                _BLOCKED_SYMBOLS = {
                    "USDT", "USDC", "USDC.E", "DAI", "BUSD", "TUSD", "FRAX", "LUSD", "PYUSD",
                    "USDP", "GUSD", "SUSD", "MIM", "EUSD", "USDD", "FDUSD", "USDBC",
                    "WETH", "WBTC", "WBNB", "WMATIC", "WAVAX", "WFTM", "WSOL", "ETH",
                    "STETH", "WSTETH", "RETH", "CBETH", "SETH2",
                    "BNB", "MATIC", "AVAX", "SOL", "BTC",
                }
                if candidate.token.symbol.upper() in _BLOCKED_SYMBOLS:
                    logger.debug(
                        f"🚫 Symbol pre-filter: {candidate.token.symbol} is a wrapped/native/stable — skipping"
                    )
                    continue

                # ── Per-cycle trade cap (enforced on SUCCESSFUL trades) ────────
                if trades_this_cycle >= settings.MAX_TRADES_PER_CYCLE:
                    logger.info(
                        f"Trade cap reached ({trades_this_cycle}/{settings.MAX_TRADES_PER_CYCLE}) "
                        f"— stopping candidate processing"
                    )
                    break

                token = candidate.token
                is_express = getattr(candidate, "express_lane", False)
                token_addr_lower = token.address.lower()

                # ── GUARD 0.5: Regime CHOP gate — skip new entries in choppy market ─
                if _regime_skip_new_entries:
                    logger.debug(
                        f"😴 Regime CHOP: skipping {token.symbol} — no new entries in chop"
                    )
                    continue

                # ── GUARD 0: Failed-trade cooldown — skip recently failed tokens ─
                if token_addr_lower in failed_trade_cooldown:
                    fail_cycle = failed_trade_cooldown[token_addr_lower]
                    if cycle - fail_cycle < 5:  # 5-cycle cooldown (~5 min)
                        continue  # Silent skip — already logged at failure time
                    else:
                        del failed_trade_cooldown[token_addr_lower]  # Cooldown expired

                # ── GUARD 1: Dedup — skip tokens with open positions ──────────
                if settings.DEDUP_GUARD_ENABLED and token_addr_lower in open_token_keys:
                    logger.info(
                        f"🛡️ Dedup guard: skipping {token.symbol} — already have open position"
                    )
                    continue

                # ── GUARD 2: Cooldown — skip recently closed tokens ───────────
                if token_addr_lower in cooldown_token_keys:
                    logger.info(
                        f"🛡️ Cooldown guard: skipping {token.symbol} — "
                        f"closed within last {settings.COOLDOWN_HOURS}h"
                    )
                    continue

                # ── GUARD 3: Exposure cap — skip if portfolio is over-deployed ─
                if settings.MAX_PORTFOLIO_EXPOSURE_PCT < 100.0 and open_positions:
                    try:
                        total_deployed = sum(
                            float(p.get("entry_value_usd", 0)) for p in open_positions
                        )
                        # Rough portfolio estimate: deployed + available balance
                        # Use entry values as proxy (conservative)
                        total_portfolio = total_deployed * (100.0 / max(
                            len(open_positions) * (settings.MAX_POSITION_SIZE_PERCENT or 2.0), 1.0
                        ))
                        exposure_pct = (total_deployed / total_portfolio * 100) if total_portfolio > 0 else 0
                        if exposure_pct >= settings.MAX_PORTFOLIO_EXPOSURE_PCT:
                            logger.info(
                                f"🛡️ Exposure cap: skipping {token.symbol} — "
                                f"portfolio {exposure_pct:.0f}% deployed "
                                f"(cap: {settings.MAX_PORTFOLIO_EXPOSURE_PCT}%)"
                            )
                            continue
                    except Exception:
                        pass  # Don't block trading on calc failure

                # Safety check (mandatory — no bypass even for express lane)
                safety = check_token_safety(token.address, token.chain)
                if not safety.is_safe:
                    logger.info(f"Skipping {token.symbol}: {safety.block_reason}")
                    continue

                candidate.is_safe = True
                candidate.safety_details = {
                    "buy_tax": safety.buy_tax,
                    "sell_tax": safety.sell_tax,
                    "goplus_passed": safety.goplus_passed,
                    "honeypot_passed": safety.honeypot_passed,
                }

                # ── RugCheck no-data penalty (Solana only) ────────────────────
                # If RugCheck has no data on this token, it's unindexed/brand new.
                # Require a higher gem score to compensate for missing safety data.
                #
                # Two cases:
                #   rugcheck_api_down=True  → API is unreachable (503/timeout). Don't
                #     penalize the token for an infrastructure problem. Apply a minimal
                #     floor (48) just to filter junk, but allow strong signals through.
                #   rugcheck_no_data=True (not api_down) → token genuinely unindexed.
                #     Apply the full 55.0 floor (missing data = higher risk).
                RUGCHECK_NO_DATA_SCORE_FLOOR = float(os.getenv("RUGCHECK_NO_DATA_SCORE_FLOOR", "55.0"))
                RUGCHECK_API_DOWN_SCORE_FLOOR = float(os.getenv("RUGCHECK_API_DOWN_SCORE_FLOOR", "48.0"))
                rugcheck_api_down = getattr(safety, "rugcheck_api_down", False)
                if (
                    token.chain == "solana"
                    and getattr(safety, "rugcheck_no_data", False)
                ):
                    floor = RUGCHECK_API_DOWN_SCORE_FLOOR if rugcheck_api_down else RUGCHECK_NO_DATA_SCORE_FLOOR
                    floor_label = "API_DOWN" if rugcheck_api_down else "UNINDEXED"
                    if candidate.gem_score < floor:
                        logger.warning(
                            f"⚠️ {token.symbol}: RugCheck {floor_label} — "
                            f"gem_score={candidate.gem_score:.1f} < {floor:.1f} floor — skipping"
                        )
                        continue
                    else:
                        logger.debug(
                            f"ℹ️ {token.symbol}: RugCheck {floor_label} but "
                            f"gem_score={candidate.gem_score:.1f} >= {floor:.1f} — proceeding"
                        )

                # Phase 2: Signal engine (TA + momentum)
                # Express lane tokens skip full TA — they already scored ≥82
                if settings.TA_ENABLED and not is_express:
                    signal = signal_engine.analyze(
                        token_symbol=token.symbol,
                        chain=token.chain,
                        pair_address=token.pair_address,
                        gem_score=candidate.gem_score,
                        price_change_1h=token.price_change_1h,
                        price_change_24h=token.price_change_24h,
                        volume_1h=token.volume_1h,
                        volume_24h=token.volume_24h,
                        buys_1h=getattr(token, "buys_1h", 0),
                        sells_1h=getattr(token, "sells_1h", 0),
                        # Enrichment data from gem scanner
                        holder_concentration_score=getattr(candidate, "holder_concentration_score", 0.0),
                        smart_money_score=getattr(candidate, "smart_money_score", 0.0),
                        unlock_risk_score=getattr(candidate, "unlock_risk_score", 0.0),
                        grok_sentiment_score=getattr(candidate, "grok_sentiment_score", 0.0),
                        age_hours=getattr(token, "age_hours", None),
                        safety_passed=candidate.is_safe,
                    )

                    if not signal.is_buy_signal:
                        logger.info(
                            f"Signal engine skipped {token.symbol}: "
                            f"composite={signal.composite:.1f} "
                            f"(rsi={signal.rsi}, macd={signal.macd_signal}, "
                            f"bb={signal.bb_signal})"
                        )
                        continue

                    rsi_str = f"{signal.rsi:.1f}" if signal.rsi is not None else "N/A"
                    logger.info(
                        f"Signal approved {token.symbol}: "
                        f"composite={signal.composite:.1f} | "
                        f"fib={signal.fib_zone} | "
                        f"rsi={rsi_str}"
                    )

                    # Store signal on candidate so strategy can reuse it
                    candidate.signal_score = signal

                    # Strategy evaluation (Fibonacci gate)
                    decision = strategy.evaluate(candidate)
                    if decision.action != "buy":
                        logger.info(
                            f"Strategy skipped {token.symbol}: {decision.reason}"
                        )
                        continue

                elif is_express:
                    logger.info(
                        f"⚡ EXPRESS LANE: {token.symbol} score={candidate.gem_score:.0f} "
                        f"— executing immediately"
                    )

                # ── Wallet routing (DUAL-WALLET: both Primary + Wallet B can fire) ──

                allocations = route_trade_all(
                    chain=token.chain,
                    gem_score=candidate.gem_score,
                    strategy="gem_snipe",
                    is_express=is_express,
                )

                if not allocations:
                    logger.info(f"No wallet available for {token.symbol} on {token.chain}")
                    continue

                # Execute on each eligible wallet (Primary + Wallet B in parallel)
                for allocation in allocations:

                    wallet = allocation.wallet
                    native_balance = allocation.native_balance
                    # ── OFFENSIVE: Apply all offensive multipliers to position sizing ──────
                    is_momentum_reentry = any(
                        r["address"] == token_addr_lower for r in reentry_candidates
                    )
                    base_position_usd = allocation.position_size_usd
                    final_position_usd, sizing_reason = calculate_offensive_position_size(
                        base_position_usd=base_position_usd,
                        gem_score=candidate.gem_score,
                        is_express=is_express,
                        state=offensive_state,
                        is_momentum_reentry=is_momentum_reentry,
                        moralis_exp_net_buyers_1w=getattr(candidate, "moralis_exp_net_buyers_1w", 0),
                        is_accumulation_zone=getattr(candidate, "is_accumulation_zone", False),
                    )
                    save_offensive_state(offensive_state)  # Save after boost consumption
                    profit_boost_remaining = offensive_state.profit_boost_remaining

                    # ── RL Position Sizer: apply learned multiplier on top of Kelly/offensive ──
                    # Neutral (1.0x) until 50 completed trades are available for training.
                    try:
                        from ml.rl_position_sizer import get_position_multiplier as _rl_size
                        from core.macro_filter import get_current_regime as _get_regime
                        _macro_r = _get_regime()
                        _rl_mult, _rl_reason = _rl_size(
                            gem_score=candidate.gem_score,
                            macro_regime=_macro_r.regime,
                            win_streak=offensive_state.consecutive_wins,
                            loss_streak=offensive_state.consecutive_losses,
                            capital_phase=getattr(offensive_state, "capital_phase", 0),
                            chain=token.chain,
                            timesfm_direction=getattr(candidate, "timesfm_direction", "FLAT"),
                            chainaware_risk=getattr(candidate, "chainaware_risk", 0.0),
                            perplexity_risk=getattr(candidate, "perplexity_risk", 0.0),
                            is_express=is_express,
                        )
                        if _rl_mult != 1.0:
                            final_position_usd = round(final_position_usd * _rl_mult, 2)
                            sizing_reason = f"{sizing_reason} | {_rl_reason}"
                            logger.info(
                                f"🤖 RL sizer: {token.symbol} {_rl_mult:.2f}x → ${final_position_usd:.2f}"
                            )
                    except Exception as _rl_err:
                        logger.debug(f"RL sizer skipped: {_rl_err}")

                    if final_position_usd != base_position_usd:
                        scale_factor = final_position_usd / base_position_usd if base_position_usd > 0 else 1.0
                        allocation.position_size_usd = final_position_usd
                        allocation.position_size_native *= scale_factor

                    # Express Lane Overdrive: wider slippage to guarantee entry
                    if is_express and settings.EXPRESS_OVERDRIVE_ENABLED:
                        from core.wallet_router import get_chain_slippage_bps
                        base_slippage = get_chain_slippage_bps(token.chain, is_express=True)
                        allocation.slippage_bps = get_express_overdrive_slippage_bps(
                            is_express=True, base_slippage_bps=base_slippage
                        )

                    # ── USDC balance check ────────────────────────────────────
                    usdc_balance = 0.0
                    try:
                        from config.chains import CHAINS
                        chain_cfg = CHAINS.get(token.chain)
                        if chain_cfg and chain_cfg.usdc_address and not chain_cfg.is_solana:
                            from web3 import Web3
                            w3 = Web3(Web3.HTTPProvider(chain_cfg.rpc_url))
                            erc20_abi = [{"constant":True,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],"type":"function"}]
                            usdc_contract = w3.eth.contract(
                                address=Web3.to_checksum_address(chain_cfg.usdc_address),
                                abi=erc20_abi,
                            )
                            raw_balance = usdc_contract.functions.balanceOf(
                                Web3.to_checksum_address(wallet.address)
                            ).call()
                            usdc_balance = raw_balance / 1e6
                            if usdc_balance > 1.0:
                                logger.info(f"USDC balance on {token.chain}: ${usdc_balance:.2f}")
                    except Exception as e:
                        logger.debug(f"USDC balance check failed: {e}")

                    # ── Risk check ────────────────────────────────────────────
                    risk = risk_manager.check_trade(
                        position_size_native=allocation.position_size_native,
                        position_size_usd=allocation.position_size_usd,
                        wallet=wallet, 
                        wallet_balance_native=native_balance, 
                        token_address=token.address, 
                        chain=token.chain,
                        usdc_balance=usdc_balance,
                    )
                    if not risk.approved:
                        logger.info(f"Risk blocked {token.symbol} on {wallet.alias}: {risk.reason}")
                        continue

                    # ── Solana execution path ──────────────────────────────────
                    if token.chain == "solana":
                        from core.solana_executor import execute_solana_buy
                        sol_amount = allocation.position_size_native
                        # Use Solana-specific address and key env for Solana chain
                        sol_public_key = wallet.solana_address or wallet.address
                        sol_key_env = wallet.solana_private_key_env or wallet.private_key_env
                        tx_hash = execute_solana_buy(
                            token_mint=token.address,
                            sol_amount=sol_amount,
                            wallet_public_key=sol_public_key,
                            wallet_private_key_env=sol_key_env,
                            slippage_bps=150,
                            is_paper=is_paper,
                        )
                        success = tx_hash is not None
                        execution_path = "jupiter"
                        amount_display = f"{sol_amount:.4f} SOL"
                        amount_out = 0.0
                        error = None if success else "Solana execution failed"
                    else:
                        # ── EVM execution path ─────────────────────────────────
                        params = build_gem_snipe_params(
                            wallet=wallet,
                            chain=token.chain,
                            token_address=token.address,
                            eth_amount=risk.position_size_eth,
                            use_usdc=risk.use_usdc,
                            usdc_amount=risk.position_size_usdc,
                        )
                        # MEV Protection: apply gas bribe for God Signal tokens
                        gas_multiplier = get_gas_bribe_multiplier(candidate.gem_score)
                        if gas_multiplier > 1.0:
                            params.gas_price_multiplier = gas_multiplier
                        result = executor.execute_trade(params)
                        success = result.success
                        tx_hash = result.tx_hash
                        execution_path = result.execution_path
                        amount_out = result.amount_out
                        error = result.error
                        amount_display = (
                            f"${risk.position_size_usdc:.2f} USDC"
                            if risk.use_usdc
                            else f"{risk.position_size_eth:.4f} ETH"
                        )

                    if success:
                        trades_this_cycle += 1
                        trades_this_session += 1

                        # Increment daily trade counter (for MAX_TRADES_PER_DAY enforcement)
                        from core.wallet_router import increment_daily_trade_count
                        daily_count = increment_daily_trade_count()
                        logger.debug(
                            f"Daily trade count: {daily_count}/{settings.MAX_TRADES_PER_DAY}"
                        )

                        # Decrement profit boost counter
                        if profit_boost_remaining > 0:
                            profit_boost_remaining -= 1
                            logger.info(
                                f"🔥 Profit boost trades remaining: {profit_boost_remaining}"
                            )

                        # Add to dedup set so we don't re-buy this cycle
                        open_token_keys.add(token_addr_lower)

                        logger.info(
                            f"✅ Trade executed: {token.symbol} | {token.chain} | "
                            f"{wallet.alias} | {amount_display} | path={execution_path} | tx={tx_hash}"
                        )
                        risk_manager.record_trade_open(wallet.alias)

                        # ── Register position for auto-sell monitoring ─────────
                        # Resolve strategy profile name from wallet config
                        _reg_profile = ""
                        if hasattr(wallet, "strategy_profile") and wallet.strategy_profile:
                            _reg_profile = wallet.strategy_profile.name
                        register_position(
                            token_address=token.address,
                            token_symbol=token.symbol,
                            chain=token.chain,
                            wallet=wallet.alias.lower().replace(" ", "_"),
                            entry_price=token.price_usd,
                            quantity=amount_out if amount_out > 0 else (
                                allocation.position_size_usd / token.price_usd
                                if token.price_usd > 0 else 0
                            ),
                            pair_address=token.pair_address,
                            tx_hash=tx_hash or "",
                            gem_score=candidate.gem_score,
                            is_paper=is_paper,
                            entry_value_usd=allocation.position_size_usd,
                            strategy_profile=_reg_profile,
                        )

                        notify_trade(
                            action="BUY",
                            token_symbol=token.symbol,
                            chain=token.chain,
                            amount_eth=risk.position_size_eth,
                            score=candidate.gem_score,
                            mode=settings.MODE,
                            extra="Capital: {} | Wallet: {} | Path: {} | Tx: {} | Express: {}".format(
                                amount_display,
                                wallet.alias,
                                execution_path,
                                tx_hash or "N/A",
                                "YES ⚡" if is_express else "no",
                            ),
                        )
                        # ── Adaptive mode: record gem trade open (not yet profitable)
                        # We record it as a trade event; profitability is determined at close.
                        # For drought detection, we track the open — wins are recorded in
                        # position_monitor when a TP sell fires. Here we just increment count.
                        record_gem_trade(adaptive_state, profitable=False)  # open, not yet profitable
                    else:
                        logger.warning(f"❌ Trade failed: {token.symbol} on {wallet.alias} | {error}")
                        failed_trade_cooldown[token_addr_lower] = cycle  # 5-cycle cooldown
                        notify_trade(
                            action="BUY",
                            token_symbol=token.symbol,
                            chain=token.chain,
                            amount_eth=risk.position_size_eth,
                            score=candidate.gem_score,
                            mode=settings.MODE,
                            extra=f"❌ FAILED on {wallet.alias}: {error}",
                        )


            # ────────────────────────────────────────────────────────────────
            # 4. OFFENSIVE MODULES (Rebalance → Fib Hunt → Moonshot Spray)
            # ────────────────────────────────────────────────────────────────
            moonshot_mode = os.getenv("MOONSHOT_MODE", "false").lower() in ("true", "1", "yes")

            if moonshot_mode:
                # 4a. Portfolio Rebalancer (every 6h per wallet/chain)
                try:
                    from core.portfolio_rebalancer import run_rebalance_cycle
                    is_paper = settings.MODE != "live"
                    rebalance_plans = run_rebalance_cycle(dry_run=is_paper)
                    if rebalance_plans:
                        total_recovery = sum(p.estimated_recovery_usd for p in rebalance_plans)
                        logger.info(
                            f"🔄 Rebalanced {len(rebalance_plans)} wallet/chain combos "
                            f"(est. recovery: ${total_recovery:.2f})"
                        )
                except Exception as e:
                    logger.error(f"Rebalancer error: {e}", exc_info=True)

                # 4b. Fibonacci Entry Hunter
                try:
                    from core.fib_hunter import run_fib_hunt_sweep
                    fib_signals = run_fib_hunt_sweep()
                    for fib_sig in fib_signals:
                        if trades_this_cycle >= settings.MAX_TRADES_PER_CYCLE:
                            break
                        logger.info(
                            f"🎯 Fib entry: {fib_sig.symbol} on {fib_sig.chain} "
                            f"at {fib_sig.fib_zone} (conf={fib_sig.fib_confidence:.0f}%)"
                        )
                        # Route through existing wallet router
                        try:
                            allocation = route_trade(
                                chain=fib_sig.chain,
                                gem_score=fib_sig.gem_score or 60.0,
                                strategy="fib_entry",
                            )
                            if allocation:
                                wallet = allocation.wallet
                                risk = risk_manager.check_trade(
                                    position_size_native=allocation.position_size_native,
                                    position_size_usd=allocation.position_size_usd,
                                    wallet=wallet,
                                    wallet_balance_native=allocation.native_balance,
                                    token_address=fib_sig.token_address,
                                    chain=fib_sig.chain,
                                )
                                if risk.approved:
                                    if fib_sig.chain == "solana":
                                        from core.solana_executor import execute_solana_buy
                                        sol_key = wallet.solana_address or wallet.address
                                        sol_pk = wallet.solana_private_key_env or wallet.private_key_env
                                        tx_hash = execute_solana_buy(
                                            token_mint=fib_sig.token_address,
                                            sol_amount=allocation.position_size_native,
                                            wallet_public_key=sol_key,
                                            wallet_private_key_env=sol_pk,
                                            is_paper=is_paper,
                                        )
                                    else:
                                        fib_executor = TradeExecutor(is_paper=is_paper)
                                        params = build_gem_snipe_params(
                                            wallet=wallet,
                                            chain=fib_sig.chain,
                                            token_address=fib_sig.token_address,
                                            eth_amount=allocation.position_size_native,
                                        )
                                        result = fib_executor.execute_trade(params)
                                        tx_hash = result.tx_hash if result.success else None

                                    if tx_hash:
                                        trades_this_cycle += 1
                                        trades_this_session += 1
                                        register_position(
                                            token_address=fib_sig.token_address,
                                            token_symbol=fib_sig.symbol,
                                            chain=fib_sig.chain,
                                            wallet=wallet.alias.lower().replace(" ", "_"),
                                            entry_price=fib_sig.current_price,
                                            quantity=allocation.position_size_usd / fib_sig.current_price
                                                if fib_sig.current_price > 0 else 0,
                                            pair_address="",
                                            tx_hash=tx_hash or "",
                                            gem_score=fib_sig.gem_score or 60.0,
                                            is_paper=is_paper,
                                            entry_value_usd=allocation.position_size_usd,
                                        )
                                        notify_trade(
                                            action="BUY",
                                            token_symbol=fib_sig.symbol,
                                            chain=fib_sig.chain,
                                            amount_eth=allocation.position_size_native,
                                            score=fib_sig.gem_score or 60.0,
                                            mode=settings.MODE,
                                            extra=f"🎯 FIB ENTRY: {fib_sig.fib_zone} "
                                                  f"conf={fib_sig.fib_confidence:.0f}%",
                                        )
                                        logger.info(f"✅ Fib entry executed: {fib_sig.symbol}")
                                else:
                                    logger.debug(f"Fib entry risk blocked: {risk.reason}")
                        except Exception as fib_exec_err:
                            logger.error(f"Fib entry execution error: {fib_exec_err}")
                except Exception as e:
                    logger.error(f"Fib Hunter error: {e}", exc_info=True)

                # 4c. Moonshot Spray Allocator
                try:
                    from core.moonshot_allocator import run_moonshot_spray
                    spray_result = run_moonshot_spray(dry_run=(settings.MODE != "live"))
                    if spray_result.positions_opened > 0:
                        logger.info(
                            f"🚀 Moonshot Spray opened {spray_result.positions_opened} positions "
                            f"(${spray_result.total_allocated_usd:.2f} allocated)"
                        )
                except Exception as e:
                    logger.error(f"Moonshot Spray error: {e}", exc_info=True)

                # 4d. Capital Recovery Swing Scanner (adaptive frequency)
                if should_run_swing(adaptive_state, cycle):
                    try:
                        swing_scanner = SwingScanner(chains=settings.ACTIVE_CHAINS)
                        swing_strategy = SwingStrategy()
                        swing_candidates = swing_scanner.scan()
                        swing_entries = [c for c in swing_candidates if c.entry_signal]
                        _max_swing = adaptive_state.max_swing_entries_per_cycle

                        for sc in swing_entries[:_max_swing]:  # Dynamic cap from adaptive mode
                            decision = swing_strategy.evaluate(sc)
                            if decision.action != "buy":
                                continue

                            # Check if we already have a position in this token
                            sc_key = sc.address.lower()
                            if sc_key in open_token_keys:
                                logger.debug(f"Swing: already in position for {sc.symbol}")
                                continue

                            # Calculate position size using live wallet balance
                            try:
                                from core.wallet_router import get_wallet_balance_usd
                                _swing_wallet = routed[0] if routed else None
                                _swing_bal = get_wallet_balance_usd(_swing_wallet) if _swing_wallet else 500.0
                            except Exception:
                                _swing_bal = 500.0
                            pos_size_usd = swing_strategy.calculate_position_size(
                                wallet_balance_usd=_swing_bal,
                                decision=decision,
                            )
                            if pos_size_usd < 10.0:
                                logger.debug(f"Swing: position too small for {sc.symbol} (${pos_size_usd:.2f})")
                                continue

                            # Route to best wallet
                            routed = route_trade_all(
                                token_address=sc.address,
                                chain=sc.chain,
                                gem_score=decision.ta_composite,
                                is_express=False,
                                candidate=None,
                            )
                            if not routed:
                                logger.debug(f"Swing: no wallet route for {sc.symbol}/{sc.chain}")
                                continue

                            wallet_conf, pos_size_native = routed[0], routed[1]

                            logger.info(
                                f"🔄 SWING TRADE: {sc.symbol}/{sc.chain} — "
                                f"composite={decision.ta_composite:.1f} | "
                                f"TP1=${decision.tp1_price:.4f} | SL=${decision.stop_loss_price:.4f}"
                            )

                            # Build trade params
                            params = build_gem_snipe_params(
                                wallet=wallet_conf,
                                chain=sc.chain,
                                token_address=sc.address,
                                eth_amount=pos_size_native,
                                slippage_bps=100,  # Tight slippage for liquid tokens
                            )
                            result = executor.execute_trade(params)

                            if result.success:
                                register_position(
                                    token_address=sc.address,
                                    token_symbol=sc.symbol,
                                    chain=sc.chain,
                                    wallet=wallet_conf.alias,
                                    pair_address=sc.pair_address,
                                    entry_price=decision.entry_price,
                                    quantity=result.amount_out if result.amount_out else 0,
                                    tx_hash=result.tx_hash,
                                    gem_score=decision.ta_composite,
                                    is_paper=is_paper,
                                    entry_value_usd=pos_size_usd,
                                    strategy_profile="swing",
                                )
                                trades_this_cycle += 1
                                trades_this_session += 1
                                notify_trade(
                                    action="SWING_BUY",
                                    symbol=sc.symbol,
                                    chain=sc.chain,
                                    amount=pos_size_usd,
                                    price=decision.entry_price,
                                    tx_hash=result.tx_hash,
                                    mode=settings.MODE,
                                    extra=f"🔄 SWING: {decision.reason} | "
                                          f"TP1=+3% SL=-2.5%",
                                )
                                logger.info(f"✅ Swing entry: {sc.symbol}/{sc.chain} | tx: {result.tx_hash}")
                                # Adaptive mode: record swing trade open
                                record_swing_trade(adaptive_state, profitable=False)  # open, not yet profitable
                            else:
                                logger.warning(f"❌ Swing entry failed: {sc.symbol} — {result.error}")

                    except Exception as swing_err:
                        logger.error(f"Swing scanner error: {swing_err}", exc_info=True)

            # Write dashboard state
            try:
                state_writer.write_cycle(
                    candidates=candidates,
                    chains_scanned=settings.ACTIVE_CHAINS,
                )
            except Exception as state_err:
                logger.debug(f"Dashboard state write failed: {state_err}")

            # Periodic cycle summary (every 10 cycles)
            if cycle % 10 == 0:
                open_count = len([p for p in load_positions() if p.get("status") == "open"])
                notify_cycle_summary(
                    cycle=cycle,
                    candidates=len(candidates),
                    trades=trades_this_session,
                    mode=settings.MODE,
                )
                logger.info(
                    f"Session summary: {trades_this_session} trades | "
                    f"{open_count} open positions"
                )

            # ── 24h Daily PnL Digest ── posts to Slack once every 24 hours ──
            _now_ts = _time_module.time()
            if _now_ts - _last_daily_digest_ts >= 86400:  # 24 × 3600 = 86400s
                _last_daily_digest_ts = _now_ts
                try:
                    offensive_state = get_offensive_state()
                    _ds = get_daily_summary(offensive_state)
                    _pnl = _ds.get("realized_pnl_usd", 0)
                    _wr = _ds.get("win_rate_pct", 0)
                    _trades = _ds.get("trades", 0)
                    _wins = _ds.get("wins", 0)
                    _losses = _ds.get("losses", 0)
                    _cw = _ds.get("consecutive_wins", 0)
                    _cl = _ds.get("consecutive_losses", 0)
                    _god = _ds.get("god_mode_active", False)
                    _house = _ds.get("house_money_pool_usd", 0)
                    _pnl_emoji = "🟢" if _pnl >= 0 else "🔴"
                    _digest_msg = (
                        f"*☘️ Shamrock Daily PnL Digest* | {_ds.get('date', 'unknown')}\n"
                        f"{_pnl_emoji} *Realized PnL:* ${_pnl:+,.2f}\n"
                        f"📊 *Trades:* {_trades} ({_wins}W / {_losses}L) | "
                        f"*Win Rate:* {_wr:.0f}%\n"
                        f"🔥 *Streak:* {_cw}W / {_cl}L consecutive\n"
                        f"⚡ *God Mode:* {'ACTIVE' if _god else 'Standby'} | "
                        f"💰 *House Money Pool:* ${_house:,.2f}\n"
                        f"🤖 *Mode:* {settings.MODE} | "
                        f"📈 *Positions open:* {len([p for p in load_positions() if p.get('status') == 'open'])}"
                    )
                    from notifications.slack import send_slack_message
                    send_slack_message(_digest_msg)
                    logger.info(f"📊 Daily PnL digest sent: PnL=${_pnl:+,.2f} | WR={_wr:.0f}% | {_trades} trades")
                except Exception as _digest_err:
                    logger.debug(f"Daily digest error: {_digest_err}")

                # On-chain position reconciliation (Solana)
                try:
                    from core.reconciliation import reconcile_solana_positions
                    # Find first wallet with a Solana address
                    sol_addr = ""
                    for _wk, _wv in WALLETS.items():
                        if getattr(_wv, "solana_address", ""):
                            sol_addr = _wv.solana_address
                            break
                    if sol_addr:
                        recon_mismatches = reconcile_solana_positions(sol_addr)
                        if recon_mismatches:
                            logger.warning(
                                f"⚠️ Reconciliation found {len(recon_mismatches)} mismatch(es)"
                            )
                except Exception as recon_err:
                    logger.debug(f"Reconciliation error: {recon_err}")

                # On-chain position reconciliation (EVM — every 10 cycles)
                if cycle % 10 == 0:
                    try:
                        from core.reconciliation import reconcile_evm_positions
                        for _wk, _wv in WALLETS.items():
                            if _wv.is_cold_storage:
                                continue
                            evm_addr = getattr(_wv, 'address', '')
                            if evm_addr:
                                for _chain in ['eth', 'base']:
                                    reconcile_evm_positions(evm_addr, chain=_chain)
                    except Exception as evm_recon_err:
                        logger.debug(f'EVM reconciliation error: {evm_recon_err}')

        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
            monitor.stop()
            fastlane_stop.set()
            if streams_server:
                streams_server.stop()
            break
        except Exception as e:
            logger.error(f"Cycle {cycle} error: {e}", exc_info=True)
            try:
                state_writer.write_cycle(
                    candidates=[],
                    chains_scanned=settings.ACTIVE_CHAINS,
                    errors=[str(e)],
                )
            except Exception:
                pass

        logger.info(f"Cycle {cycle} complete. Sleeping {settings.SCAN_INTERVAL_SECONDS}s...")
        await asyncio.sleep(settings.SCAN_INTERVAL_SECONDS)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print(BANNER)
    parser = argparse.ArgumentParser(
        description="☘️  Shamrock Trading Bot — Multi-Chain Gem Sniper"
    )
    parser.add_argument("--balances", action="store_true", help="Fetch wallet balances only")
    parser.add_argument("--scan", action="store_true", help="Run one gem scan cycle")
    parser.add_argument("--snipe", nargs=2, metavar=("TOKEN_ADDRESS", "CHAIN"),
                        help="Test gem snipe for a specific token address and chain")
    parser.add_argument("--analyze", nargs=2, metavar=("TOKEN_ADDRESS", "CHAIN"),
                        help="Run TA + Fibonacci analysis on a token (no trade executed)")
    parser.add_argument("--positions", action="store_true",
                        help="Show all open positions and PnL")
    args = parser.parse_args()

    if args.balances:
        asyncio.run(run_balance_check())
    elif args.scan:
        asyncio.run(run_gem_scan())
    elif args.snipe:
        token_address, chain = args.snipe
        asyncio.run(run_gem_snipe_example(token_address, chain))
    elif args.analyze:
        token_address, chain = args.analyze
        asyncio.run(run_token_analysis(token_address, chain))
    elif args.positions:
        run_show_positions()
    else:
        asyncio.run(run_bot_loop())


async def run_token_analysis(token_address: str, chain: str):
    """
    Run complete TA + Fibonacci analysis on a specific token.
    No trade is executed — this is a diagnostic/research tool.
    """
    from data.providers.ohlcv_provider import fetch_ohlcv, get_current_price
    from strategies.signal_scorer import analyze_token, format_analysis_report

    print(f"\n☘️  Analyzing {token_address} on {chain}...\n")

    # Step 1: Get current price
    print("Step 1: Fetching current price...")
    current_price = get_current_price(token_address, chain)
    print(f"  Current price: ${current_price:.8f}" if current_price else "  Price unavailable")

    # Step 2: Fetch OHLCV
    print("Step 2: Fetching OHLCV data...")
    candles = fetch_ohlcv(token_address, chain, timeframe="1h", limit=100)
    print(f"  Fetched {len(candles)} hourly candles")

    if not candles:
        print("  ⚠️  No OHLCV data available — cannot run full TA")
        return

    # Step 3: Run analysis
    print("Step 3: Running TA + Fibonacci analysis...")
    analysis = analyze_token(candles, current_price)
    report = format_analysis_report(analysis, token_address, chain)
    print(report)

    # Save report
    output_path = OUTPUT_DIR / f"analysis_{token_address[:8]}_{chain}.txt"
    with open(output_path, "w") as f:
        f.write(report)
    print(f"\n✅ Analysis saved to {output_path}")


if __name__ == "__main__":
    main()
