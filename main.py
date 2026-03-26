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
import json
import logging
import os
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
from dashboard.state import BotStateWriter


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

    # ── Check for Base USDC deployment plan ───────────────────────────────────
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

            # 2. Scan for gems (all chains including Solana)
            candidates = scanner.scan()
            logger.info(f"Cycle {cycle}: {len(candidates)} gem candidates found")

            # 3. Process candidates (iterate all, but cap successful trades)
            for candidate in candidates:
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
                # This directly addresses the Solana meme coin loss pattern.
                RUGCHECK_NO_DATA_SCORE_FLOOR = float(os.getenv("RUGCHECK_NO_DATA_SCORE_FLOOR", "55.0"))
                if (
                    token.chain == "solana"
                    and getattr(safety, "rugcheck_no_data", False)
                    and candidate.gem_score < RUGCHECK_NO_DATA_SCORE_FLOOR
                ):
                    logger.warning(
                        f"⚠️ {token.symbol}: RugCheck has no data (unindexed token) and "
                        f"gem_score={candidate.gem_score:.1f} < {RUGCHECK_NO_DATA_SCORE_FLOOR} floor "
                        f"— skipping until score improves or RugCheck indexes it"
                    )
                    continue

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
                    )
                    save_offensive_state(offensive_state)  # Save after boost consumption
                    profit_boost_remaining = offensive_state.profit_boost_remaining

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

                # 4d. Capital Recovery Swing Scanner (every 3rd cycle)
                if cycle % 3 == 0:
                    try:
                        swing_scanner = SwingScanner(chains=settings.ACTIVE_CHAINS)
                        swing_strategy = SwingStrategy()
                        swing_candidates = swing_scanner.scan()
                        swing_entries = [c for c in swing_candidates if c.entry_signal]

                        for sc in swing_entries[:3]:  # Max 3 swing entries per cycle
                            decision = swing_strategy.evaluate(sc)
                            if decision.action != "buy":
                                continue

                            # Check if we already have a position in this token
                            sc_key = sc.address.lower()
                            if sc_key in open_token_keys:
                                logger.debug(f"Swing: already in position for {sc.symbol}")
                                continue

                            # Calculate position size
                            pos_size_usd = swing_strategy.calculate_position_size(
                                wallet_balance_usd=500.0,  # Conservative starting balance reference
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
