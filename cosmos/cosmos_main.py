"""
cosmos/cosmos_main.py — Main orchestration loop for Cosmos autotrading.

Runs as a standalone Docker service alongside the gem sniper bot.
Orchestrates all four profit strategies:
  1. Yield staking (Stride + native)
  2. Osmosis LP management
  3. IBC arbitrage
  4. Price monitoring
"""

import logging
import os
import signal
import sys
import time
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cosmos.cosmos_config import (
    COSMOS_CHAINS,
    COSMOS_ADDRESSES,
    COSMOS_MODE,
    ARB_SCAN_INTERVAL_SECONDS,
    YIELD_AUTO_COMPOUND_INTERVAL_HOURS,
)
from cosmos.cosmos_wallet import CosmosWallet, scan_all_balances, get_total_portfolio_usd
from cosmos.yield_manager import YieldManager
from cosmos.lp_manager import LPManager
from cosmos.arb_engine import ArbEngine
from cosmos.price_monitor import PriceMonitor
from cosmos.ibc_transfer import IBCTransferEngine

# ─────────────────────────────────────────────────────────────────────────────
# Logging setup
# ─────────────────────────────────────────────────────────────────────────────

LOG_DIR = os.getenv("LOG_DIR", "./logs")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(LOG_DIR, "cosmos_bot.log")),
    ],
)
logger = logging.getLogger("cosmos_main")

# ─────────────────────────────────────────────────────────────────────────────
# Slack notifications (reuse existing infrastructure)
# ─────────────────────────────────────────────────────────────────────────────

def notify_slack(message: str):
    """Send a Slack notification about Cosmos bot activity."""
    try:
        from notifications.slack import send_slack_message
        send_slack_message(f"☘️🌌 *Cosmos Bot* | {message}")
    except Exception as e:
        logger.debug(f"Slack notification failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Main Bot Class
# ─────────────────────────────────────────────────────────────────────────────

class CosmosBot:
    """
    Main Cosmos autotrading bot.
    
    Orchestrates all strategies on a configurable loop:
    - Every 30s: Check for arb opportunities
    - Every 5m: Scan LP positions, check rebalancing
    - Every 24h: Auto-compound staking rewards
    - On startup: Deploy idle assets to yield
    """
    
    def __init__(self):
        self.mode = COSMOS_MODE
        self.is_paper = self.mode != "live"
        self.running = False
        self.cycle = 0
        
        # Strategy engines
        self.yield_mgr = YieldManager()
        self.lp_mgr = LPManager()
        self.arb_engine = ArbEngine()
        self.price_monitor = PriceMonitor()
        self.ibc_engine = IBCTransferEngine()
        
        # Timing
        self._arb_interval = ARB_SCAN_INTERVAL_SECONDS
        self._lp_check_interval = 300        # 5 minutes
        self._portfolio_scan_interval = 600  # 10 minutes
        self._last_lp_check = 0.0
        self._last_portfolio_scan = 0.0
        
        # Stats
        self._startup_time = time.time()
        self._total_arb_profit = 0.0
        self._total_yield_earned = 0.0
    
    def startup_banner(self):
        """Print startup banner."""
        mode_badge = "📄 PAPER" if self.is_paper else "🔴 LIVE"
        
        banner = f"""
╔══════════════════════════════════════════════════╗
║          ☘️ SHAMROCK COSMOS BOT ☘️               ║
║          {mode_badge} MODE                               ║
╠══════════════════════════════════════════════════╣
║  Chains: {', '.join(COSMOS_ADDRESSES.keys()):39s} ║
║  Strategies: Yield | LP | Arbitrage             ║
║  Arb Interval: {self._arb_interval}s                             ║
║  Compound Interval: {YIELD_AUTO_COMPOUND_INTERVAL_HOURS}h                          ║
╚══════════════════════════════════════════════════╝
        """
        logger.info(banner)
    
    def initial_portfolio_scan(self) -> dict:
        """Scan all chains for current holdings on startup."""
        logger.info("=" * 60)
        logger.info("INITIAL PORTFOLIO SCAN")
        logger.info("=" * 60)
        
        all_balances = scan_all_balances()
        
        for chain_name, chain_data in all_balances.items():
            addr_short = chain_data["address"][:15] + "..."
            logger.info(f"\n{'─' * 40}")
            logger.info(f"Chain: {COSMOS_CHAINS[chain_name].name} ({addr_short})")
            
            if chain_data["balances"]:
                for denom, bal in chain_data["balances"].items():
                    logger.info(f"  Balance: {bal['amount']:.6f} {denom}")
            else:
                logger.info("  No balances")
            
            if chain_data["delegations"]:
                for d in chain_data["delegations"]:
                    logger.info(
                        f"  Staked: {d['amount']:.6f} {d['denom']} "
                        f"→ {d['validator'][:20]}..."
                    )
            
            if chain_data["pending_rewards"]:
                for denom, amount in chain_data["pending_rewards"].items():
                    logger.info(f"  Rewards: {amount:.6f} {denom}")
        
        # Total USD value
        total_usd = get_total_portfolio_usd()
        logger.info(f"\n{'═' * 60}")
        logger.info(f"TOTAL PORTFOLIO VALUE: ${total_usd:,.2f}")
        logger.info(f"{'═' * 60}")
        
        notify_slack(
            f"Bot started in {self.mode} mode | "
            f"Portfolio: ${total_usd:,.2f} | "
            f"Chains: {len(all_balances)}"
        )
        
        self._last_portfolio_scan = time.time()
        return all_balances
    
    def deploy_idle_assets(self):
        """Deploy all idle assets to yield-generating strategies."""
        logger.info("Deploying idle assets to yield strategies...")
        
        actions = self.yield_mgr.deploy_all_idle_assets()
        
        for action in actions:
            notify_slack(
                f"{action.action.upper()}: {action.amount:.4f} {action.denom} "
                f"on {action.chain} | TX: {action.tx_hash or 'pending'}"
            )
        
        logger.info(f"Deployed {len(actions)} yield positions")
    
    def run_arb_cycle(self):
        """Execute one arbitrage scanning cycle."""
        results = self.arb_engine.run_arb_cycle()
        
        for result in results:
            if result.success and result.opportunity:
                self._total_arb_profit += result.actual_profit_usd
                notify_slack(
                    f"ARB: {result.opportunity.symbol} | "
                    f"spread={result.opportunity.spread_pct:.2f}% | "
                    f"profit=${result.actual_profit_usd:.2f}"
                )
    
    def run_lp_cycle(self):
        """Check and manage LP positions."""
        if time.time() - self._last_lp_check < self._lp_check_interval:
            return
        
        self._last_lp_check = time.time()
        
        # Scan positions
        positions = self.lp_mgr.scan_positions()
        
        # Check for rebalancing needs
        needs_rebalance = self.lp_mgr.check_rebalance_needed()
        for pos in needs_rebalance:
            actions = self.lp_mgr.rebalance_position(pos)
            for action in actions:
                notify_slack(
                    f"LP REBALANCE: pool {action.pool_id} ({action.pair})"
                )
        
        # Compound fees
        compound_actions = self.lp_mgr.compound_lp_fees()
    
    def run_yield_cycle(self):
        """Check for auto-compounding needs."""
        if self.yield_mgr.should_compound():
            logger.info("Running auto-compound cycle...")
            actions = self.yield_mgr.claim_and_compound()
            
            for action in actions:
                notify_slack(
                    f"COMPOUND: {action.amount:.6f} {action.denom} "
                    f"on {action.chain}"
                )
    
    def run_portfolio_scan(self):
        """Periodic portfolio value update."""
        if time.time() - self._last_portfolio_scan < self._portfolio_scan_interval:
            return
        
        self._last_portfolio_scan = time.time()
        total_usd = get_total_portfolio_usd()
        
        arb_summary = self.arb_engine.get_daily_summary()
        yield_summary = self.yield_mgr.get_yield_summary()
        lp_summary = self.lp_mgr.get_lp_summary()
        
        logger.info(
            f"Portfolio: ${total_usd:,.2f} | "
            f"Arb PnL: ${arb_summary['daily_pnl_usd']:.2f} | "
            f"Staked: ${yield_summary['total_staked_usd']:.2f} | "
            f"LP: ${lp_summary['total_value_usd']:.2f}"
        )
    
    def run(self):
        """Main bot loop."""
        self.running = True
        self.startup_banner()
        
        # Signal handling for graceful shutdown
        def handle_signal(signum, frame):
            logger.info("Shutdown signal received, stopping...")
            self.running = False
        
        signal.signal(signal.SIGTERM, handle_signal)
        signal.signal(signal.SIGINT, handle_signal)
        
        # ── Phase 1: Initial scan ────────────────────────────────────────────
        try:
            portfolio = self.initial_portfolio_scan()
        except Exception as e:
            logger.error(f"Initial scan failed: {e}")
            portfolio = {}
        
        # ── Phase 2: Deploy idle assets ──────────────────────────────────────
        try:
            self.deploy_idle_assets()
        except Exception as e:
            logger.error(f"Asset deployment failed: {e}")
        
        # ── Phase 3: Main loop ───────────────────────────────────────────────
        logger.info(f"Entering main loop (interval: {self._arb_interval}s)")
        
        while self.running:
            self.cycle += 1
            cycle_start = time.time()
            
            try:
                # Arb scanning (every cycle)
                self.run_arb_cycle()
                
                # LP management (every 5 min)
                self.run_lp_cycle()
                
                # Yield compounding (every 24h)
                self.run_yield_cycle()
                
                # Portfolio scan (every 10 min)
                self.run_portfolio_scan()
                
            except Exception as e:
                logger.error(f"Cycle {self.cycle} error: {e}", exc_info=True)
                notify_slack(f"⚠️ Error in cycle {self.cycle}: {str(e)[:100]}")
            
            # Log cycle summary (every 10 cycles)
            if self.cycle % 10 == 0:
                elapsed = time.time() - self._startup_time
                hours = elapsed / 3600
                logger.info(
                    f"Cycle {self.cycle} | "
                    f"Uptime: {hours:.1f}h | "
                    f"Arb profit: ${self._total_arb_profit:.2f}"
                )
            
            # Sleep until next cycle
            cycle_duration = time.time() - cycle_start
            sleep_time = max(0, self._arb_interval - cycle_duration)
            
            if sleep_time > 0 and self.running:
                time.sleep(sleep_time)
        
        # Shutdown
        logger.info("Cosmos bot shutting down gracefully")
        notify_slack(
            f"Bot stopped | Cycles: {self.cycle} | "
            f"Total arb profit: ${self._total_arb_profit:.2f}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    """Entry point for Cosmos bot."""
    # Validate configuration
    mnemonic = os.getenv("COSMOS_MNEMONIC", "")
    if not mnemonic:
        logger.warning(
            "⚠️  COSMOS_MNEMONIC not set — running in read-only mode. "
            "Set COSMOS_MNEMONIC in .env for full functionality."
        )
    
    bot = CosmosBot()
    bot.run()


if __name__ == "__main__":
    main()
