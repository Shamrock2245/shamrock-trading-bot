"""
main.py — Shamrock Trading Bot entry point.

Usage:
    python main.py                  # Run full bot loop (paper mode by default)
    python main.py --balances       # Fetch and print wallet balances only
    python main.py --scan           # Run one gem scan cycle and print results
    python main.py --snipe <addr> <chain>  # Test gem snipe for a specific token
    python main.py --analyze <addr> <chain>  # Run TA + Fibonacci analysis (no trade)

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
from data.models import GemCandidate
from scanner.gem_scanner import GemScanner
from strategies.gem_snipe import GemSnipeStrategy
from dashboard.state import BotStateWriter


# ─────────────────────────────────────────────────────────────────────────────
# Banner
# ─────────────────────────────────────────────────────────────────────────────

BANNER = """
╔══════════════════════════════════════════════════════════════╗
║          ☘️  SHAMROCK TRADING BOT  ☘️                         ║
║     Multi-Chain Gem Sniper with MEV Protection               ║
║     Chains: ETH | Base | Arbitrum | Polygon | BSC            ║
╚══════════════════════════════════════════════════════════════╝
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
        print(
            f"{i:2}. [{candidate.gem_score:5.1f}] {token.symbol:<12} | "
            f"{token.chain:<10} | liq=${token.liquidity_usd:>10,.0f} | "
            f"vol1h=${token.volume_1h:>8,.0f} | "
            f"age={f'{token.age_hours:.1f}h' if token.age_hours else 'N/A':<8} {boosted}"
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
        slippage_bps=200,  # 2% slippage for new gems
    )
    print(f"  Wallet:         {params.wallet.alias} ({params.wallet.address[:10]}...)")
    print(f"  Chain:          {params.chain}")
    print(f"  Token in:       {params.token_in[:10]}... (native ETH)")
    print(f"  Token out:      {params.token_out[:10]}...")
    print(f"  Amount:         {params.amount_in_wei / 1e18:.6f} ETH")
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


async def run_bot_loop():
    """
    Main bot loop — runs continuously until interrupted.
    Cycle: balance check → gem scan → safety filter → risk check → execute
    """
    logger.info(f"Starting bot loop in {settings.MODE.upper()} mode")
    print(BANNER)
    print(f"Mode: {settings.MODE.upper()}")
    print(f"Scan interval: {settings.SCAN_INTERVAL_SECONDS}s")
    print(f"Min gem score: {settings.MIN_GEM_SCORE}")
    print(f"Chains: {', '.join(settings.ACTIVE_CHAINS)}")
    print()

    # Startup notification
    notify_alert(
        "Shamrock Bot Started",
        "Mode: {} | Chains: {} | Interval: {}s".format(
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
    state_writer = BotStateWriter()
    cycle = 0

    while True:
        cycle += 1
        logger.info(f"--- Cycle {cycle} ---")

        try:
            # 1. Fetch balances
            fetcher = BalanceFetcher()

            # 2. Scan for gems
            candidates = scanner.scan()
            logger.info(f"Cycle {cycle}: {len(candidates)} gem candidates found")

            # 3. Process top candidates through strategy
            for candidate in candidates[:settings.MAX_TRADES_PER_CYCLE]:
                token = candidate.token

                # Safety check
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

                # Phase 2: Strategy evaluation (TA + Fibonacci gate)
                if settings.TA_ENABLED:
                    decision = strategy.evaluate(candidate)
                    if decision.action != "buy":
                        logger.info(
                            f"Strategy skipped {token.symbol}: {decision.reason}"
                        )
                        continue
                    logger.info(
                        f"Strategy approved {token.symbol} — "
                        f"confidence={decision.confidence:.0f}, "
                        f"fib_zone={decision.fib_result.current_zone if decision.fib_result else 'N/A'}"
                    )

                # Get wallet balance for this chain
                primary = WALLETS["primary"]
                chain_data = fetcher.fetch_wallet_chain_balances(primary, token.chain)
                native_balance = 0.0
                for t in chain_data.get("tokens", []):
                    if t.get("is_native"):
                        native_balance = t.get("balance", 0.0)
                        break

                # Risk check
                risk = risk_manager.check_trade(
                    primary, native_balance, token.address, token.chain
                )
                if not risk.approved:
                    logger.info(f"Risk blocked {token.symbol}: {risk.reason}")
                    continue

                # Execute
                params = build_gem_snipe_params(
                    wallet=primary,
                    chain=token.chain,
                    token_address=token.address,
                    eth_amount=risk.position_size_eth,
                )
                result = executor.execute_trade(params)

                if result.success:
                    logger.info(
                        f"\u2705 Trade executed: {token.symbol} | {token.chain} | "
                        f"path={result.execution_path} | tx={result.tx_hash}"
                    )
                    risk_manager.record_trade_open(primary.alias)
                    notify_trade(
                        action="BUY",
                        token_symbol=token.symbol,
                        chain=token.chain,
                        amount_eth=risk.position_size_eth,
                        score=candidate.score,
                        mode=settings.MODE,
                        extra="Path: {} | Tx: {}".format(
                            result.execution_path,
                            result.tx_hash or "N/A",
                        ),
                    )
                else:
                    logger.warning(f"\u274c Trade failed: {token.symbol} | {result.error}")
                    notify_trade(
                        action="BUY",
                        token_symbol=token.symbol,
                        chain=token.chain,
                        amount_eth=risk.position_size_eth,
                        score=candidate.score,
                        mode=settings.MODE,
                        extra="\u274c FAILED: {}".format(result.error),
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
                notify_cycle_summary(
                    cycle=cycle,
                    candidates=len(candidates),
                    trades=0,  # TODO: track trades_this_cycle
                    mode=settings.MODE,
                )

        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
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
    else:
        asyncio.run(run_bot_loop())


async def run_token_analysis(token_address: str, chain: str):
    """
    Run complete TA + Fibonacci analysis on a specific token.
    No trade is executed — this is a diagnostic/research tool.
    """
    from data.providers.ohlcv_provider import fetch_ohlcv, get_current_price
    from strategies.signal_scorer import analyze_token, format_analysis_report

    print(f"\n\u2618\ufe0f  Analyzing {token_address} on {chain}...\n")

    # Step 1: Get current price
    print("Step 1: Fetching current price...")
    current_price = get_current_price(token_address, chain)
    if not current_price or current_price <= 0:
        print(f"\u274c Could not fetch price for {token_address} on {chain}")
        return
    print(f"  Current price: ${current_price:.10f}")

    # Step 2: Fetch OHLCV data
    print(f"\nStep 2: Fetching OHLCV data ({settings.OHLCV_LOOKBACK_DAYS}d lookback)...")
    df = fetch_ohlcv(token_address, chain, days=settings.OHLCV_LOOKBACK_DAYS)
    if df is None or len(df) < 3:
        print(f"\u26a0\ufe0f Insufficient OHLCV data ({len(df) if df is not None else 0} candles)")
        print("  Analysis will proceed with limited data.")
        import pandas as pd
        df = pd.DataFrame({
            "open": [current_price],
            "high": [current_price * 1.01],
            "low": [current_price * 0.99],
            "close": [current_price],
            "volume": [0],
        })
    else:
        print(f"  Fetched {len(df)} candles")

    # Step 3: Run safety check
    print("\nStep 3: Safety check...")
    safety = check_token_safety(token_address, chain)
    safe_str = "\u2705 YES" if safety.is_safe else f"\u274c NO — {safety.block_reason}"
    print(f"  Safe: {safe_str}")
    if safety.buy_tax is not None:
        print(f"  Buy tax: {safety.buy_tax:.1%} | Sell tax: {safety.sell_tax:.1%}")

    # Step 4: Run TA + Fibonacci
    print("\nStep 4: Running Technical Analysis + Fibonacci...")
    signal_score, ta_result, fib_result = analyze_token(
        df=df,
        current_price=current_price,
        onchain_score=50.0,  # Default for standalone analysis
        direction="buy",
    )

    # Step 5: Print full report
    report = format_analysis_report(signal_score, ta_result, fib_result, token_address[:10])
    print(report)

    # Step 6: Save to file
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "token_address": token_address,
        "chain": chain,
        "current_price": current_price,
        "composite_score": signal_score.composite,
        "signal": signal_score.signal,
        "fib_aligned": fib_result.aligned,
        "fib_zone": fib_result.current_zone,
        "fib_confidence": fib_result.confidence,
        "trend": fib_result.trend,
        "fibonacci": {
            "swing_high": fib_result.swing_high,
            "swing_low": fib_result.swing_low,
            "nearest_support": fib_result.nearest_support,
            "nearest_resistance": fib_result.nearest_resistance,
            "retracement_levels": {str(k): v for k, v in fib_result.retracement_levels.items()},
            "extension_levels": {str(k): v for k, v in fib_result.extension_levels.items()},
            "take_profit_targets": fib_result.take_profit_targets,
            "stop_loss": fib_result.stop_loss_level,
        },
        "ta": {
            "trend_score": ta_result.trend_score,
            "momentum_score": ta_result.momentum_score,
            "volume_score": ta_result.volume_score,
            "rsi": ta_result.rsi,
            "macd_signal": ta_result.macd_signal,
            "ema_signal": ta_result.ema_signal,
            "bb_signal": ta_result.bb_signal,
            "volume_spike": ta_result.volume_spike,
        },
        "safety": {
            "is_safe": safety.is_safe,
            "block_reason": safety.block_reason,
            "buy_tax": safety.buy_tax,
            "sell_tax": safety.sell_tax,
        },
    }

    output_path = OUTPUT_DIR / "analysis.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\n\u2705 Full analysis saved to {output_path}")


if __name__ == "__main__":
    main()
