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

from notifications.slack import notify_trade, notify_alert, notify_cycle_summary

# ─────────────────────────────────────────────────────────────────────────────
# Logging setup — must happen before any other imports
# ─────────────────────────────────────────────────────────────────────────────
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_DIR / "bot.log", encoding="utf-8"),
    ],
)

# Safety-specific logger (separate file for audit trail)
safety_handler = logging.FileHandler(LOG_DIR / "safety.log", encoding="utf-8")
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
from core.wallet_router import route_trade
from core.signal_engine import SignalEngine
from data.models import GemCandidate
from scanner.gem_scanner import GemScanner
from strategies.gem_snipe import GemSnipeStrategy
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

    # ── Start position monitor in background thread ───────────────────────────
    monitor = PositionMonitor(is_paper=is_paper)
    monitor_thread = threading.Thread(
        target=monitor.run_forever,
        name="PositionMonitor",
        daemon=True,
    )
    monitor_thread.start()
    logger.info("Position monitor started in background thread")

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

    while True:
        cycle += 1
        trades_this_cycle = 0
        logger.info(f"--- Cycle {cycle} ---")

        try:
            # 1. Fetch balances
            fetcher = BalanceFetcher()

            # 2. Scan for gems (all chains including Solana)
            candidates = scanner.scan()
            logger.info(f"Cycle {cycle}: {len(candidates)} gem candidates found")

            # 3. Process top candidates through strategy
            for candidate in candidates[:settings.MAX_TRADES_PER_CYCLE]:
                token = candidate.token
                is_express = getattr(candidate, "express_lane", False)

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
                    )

                    if not signal.is_buy_signal:
                        logger.info(
                            f"Signal engine skipped {token.symbol}: "
                            f"composite={signal.composite:.1f} "
                            f"(rsi={signal.rsi}, macd={signal.macd_signal}, "
                            f"bb={signal.bb_signal})"
                        )
                        continue

                    logger.info(
                        f"Signal approved {token.symbol}: "
                        f"composite={signal.composite:.1f} | "
                        f"fib={signal.fib_zone} | "
                        f"rsi={signal.rsi:.1f if signal.rsi else 'N/A'}"
                    )

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

                # ── Wallet routing (multi-wallet, conviction-based sizing) ──────
                allocation = route_trade(
                    chain=token.chain,
                    gem_score=candidate.gem_score,
                    strategy="gem_snipe",
                )

                if not allocation:
                    logger.info(f"No wallet available for {token.symbol} on {token.chain}")
                    continue

                wallet = allocation.wallet
                native_balance = allocation.native_balance

                # ── USDC balance check ────────────────────────────────────────
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

                # ── Risk check ────────────────────────────────────────────────
                risk = risk_manager.check_trade(
                    wallet, native_balance, token.address, token.chain,
                    usdc_balance=usdc_balance,
                )
                if not risk.approved:
                    logger.info(f"Risk blocked {token.symbol}: {risk.reason}")
                    continue

                # ── Solana execution path ─────────────────────────────────────
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
                    # ── EVM execution path ────────────────────────────────────
                    params = build_gem_snipe_params(
                        wallet=wallet,
                        chain=token.chain,
                        token_address=token.address,
                        eth_amount=risk.position_size_eth,
                        use_usdc=risk.use_usdc,
                        usdc_amount=risk.position_size_usdc,
                    )
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
                    logger.info(
                        f"✅ Trade executed: {token.symbol} | {token.chain} | "
                        f"{amount_display} | path={execution_path} | tx={tx_hash}"
                    )
                    risk_manager.record_trade_open(wallet.alias)

                    # ── Register position for auto-sell monitoring ────────────
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
                    )

                    notify_trade(
                        action="BUY",
                        token_symbol=token.symbol,
                        chain=token.chain,
                        amount_eth=risk.position_size_eth,
                        score=candidate.gem_score,
                        mode=settings.MODE,
                        extra="Capital: {} | Path: {} | Tx: {} | Express: {}".format(
                            amount_display,
                            execution_path,
                            tx_hash or "N/A",
                            "YES ⚡" if is_express else "no",
                        ),
                    )
                else:
                    logger.warning(f"❌ Trade failed: {token.symbol} | {error}")
                    notify_trade(
                        action="BUY",
                        token_symbol=token.symbol,
                        chain=token.chain,
                        amount_eth=risk.position_size_eth,
                        score=candidate.gem_score,
                        mode=settings.MODE,
                        extra=f"❌ FAILED: {error}",
                    )

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
