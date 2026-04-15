"""
core/capital_rotator.py — Arbitrage Trade-Up Module

Periodically compares active holdings (low conviction) against the top
unbought gem candidates. If a holding's score is drastically lower than a
top candidate (delta > ROTATION_SCORE_THRESHOLD), it initiates a liquidation.
The freed capital will natively be picked up by the `WalletRouter` on the 
next scanner cycle to buy the superior gem.
"""

import json
import logging
from pathlib import Path

from config import settings
from config.wallets import WALLETS
from core.executor import TradeExecutor, build_take_profit_params
from core.position_monitor import load_positions

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("output")
GEM_SCAN_FILE = OUTPUT_DIR / "gem_scan.json"

class CapitalRotator:
    def __init__(self, rotation_threshold: float = 15.0):
        self.rotation_threshold = getattr(settings, "ROTATION_SCORE_THRESHOLD", rotation_threshold)

    def try_rotate(self):
        """
        Evaluate and swap out the worst holding for capital to fund the best gem.
        """
        logger.info("♻️  Running Capital Rotator check...")
        
        if not GEM_SCAN_FILE.exists():
            logger.debug("No gem_scan.json available to find top candidates. Skipping rotation.")
            return

        with open(GEM_SCAN_FILE, "r") as f:
            try:
                scan_data = json.load(f)
            except json.JSONDecodeError:
                logger.error("Failed to decode gem_scan.json.")
                return
            
        top_candidates = scan_data.get("top_candidates", [])
        if not top_candidates:
            logger.debug("No top candidates found in gem_scan.json. Skipping rotation.")
            return

        # 2. Evaluate active holdings
        positions = load_positions()
        
        # We only want to look at active positions
        active_positions = [
            p for p in positions 
            if float(p.get("remaining_quantity", 0)) > 0 
        ]
        open_token_addrs = {p.get("token_address", "").lower() for p in active_positions}
        
        if not active_positions:
            logger.info("No active rotatable positions found.")
            return

        # 1. Find best gem candidate not already held (check top 5)
        top_gem = None
        for gem in top_candidates[:5]:
            gem_addr = gem.get("address", "").lower()
            if gem_addr and gem_addr not in open_token_addrs:
                top_gem = gem
                break
        
        if not top_gem:
            logger.debug("All top candidates already held. Skipping rotation.")
            return

        top_gem_score = float(top_gem.get("gem_score", 0))
        top_gem_symbol = top_gem.get("symbol", "UNKNOWN")
        top_gem_address = top_gem.get("address", "").lower()

        # Exclude currently held tokens that are the SAME as the top_gem from worst-holding search
        rotatable = [p for p in active_positions if p.get("token_address", "").lower() != top_gem_address]
        if not rotatable:
            logger.info("No rotatable positions after excluding target gem.")
            return

        # Find the worst holding
        worst_holding = min(rotatable, key=lambda p: float(p.get("gem_score", 0.0)))
        worst_score = float(worst_holding.get("gem_score", 0.0))
        worst_symbol = worst_holding.get("token_symbol", "UNKNOWN")
        
        delta = top_gem_score - worst_score
        
        logger.info(f"Top Candidate: {top_gem_symbol} (Score: {top_gem_score:.1f})")
        logger.info(f"Worst Holding: {worst_symbol} (Score: {worst_score:.1f}) | Delta: {delta:.1f}")

        # 3. Decision Gate
        if delta >= self.rotation_threshold:
            logger.warning(
                f"🚨 ARBITRAGE TRIGGERED: Rotating out of {worst_symbol} "
                f"to fund {top_gem_symbol} (Score Delta: +{delta:.1f})"
            )
            self._liquidate_holding(worst_holding)
        else:
            logger.info(f"Rotation threshold ({self.rotation_threshold}) not met. Holding steady.")

    def _liquidate_holding(self, pos: dict):
        """Execute a 100% take-profit/liquidation on the given position to free capital."""
        chain = pos.get("chain", "ethereum")
        token_address = pos.get("token_address")
        wallet_alias = pos.get("wallet", "primary")
        sell_qty = float(pos.get("remaining_quantity", 0))
        
        if sell_qty <= 0:
            return
            
        logger.info(f"Initiating liquidation of {sell_qty} {pos.get('token_symbol')}")
        
        if pos.get("is_paper", True) or settings.MODE == "paper":
            logger.info(f"PAPER ROTATION: Liquidated {pos.get('token_symbol')} (Paper Mode).")
            # In paper mode, we simply rely on the position_monitor to actually close 
            # the position or we could manually hack it here. 
            # Because this is just executing a rotational check, we'll mimic the executor call:
            return

        # LIVE MODE execution
        wallet = None
        for wk, wv in WALLETS.items():
            if wv.address.lower() == wallet_alias.lower() or wv.alias.lower() == wallet_alias.lower():
                wallet = wv
                break
                
        if not wallet:
            logger.error(f"Cannot liquidate: No wallet found for '{wallet_alias}'")
            return
            
        if chain.lower() == "solana":
            from core.solana_executor import execute_solana_sell
            sol_public_key = wallet.solana_address or wallet.address
            sol_key_env = wallet.solana_private_key_env or wallet.private_key_env
            
            tx_hash = execute_solana_sell(
                token_mint=token_address,
                token_amount=sell_qty,
                wallet_public_key=sol_public_key,
                wallet_private_key_env=sol_key_env,
                slippage_bps=300,
                is_paper=pos.get("is_paper", True) or settings.MODE == "paper"
            )
            success = tx_hash is not None
            error_msg = "Solana execution failed" if not success else ""
        else:
            decimals = int(pos.get("token_decimals", 18))
            token_amount_wei = int(sell_qty * (10 ** decimals))
            
            params = build_take_profit_params(
                wallet=wallet,
                chain=chain,
                token_address=token_address,
                token_amount_wei=token_amount_wei,
                slippage_bps=300,  # 3% slippage for rotation liquidation
            )
            
            executor = TradeExecutor()
            result = executor.execute_trade(params)
            success = result.success
            tx_hash = result.tx_hash
            error_msg = result.error
        
        if success:
            logger.info(f"✅ ROTATION SUCCESS: Liquidated {pos.get('token_symbol')}. Tx: {tx_hash}")
        else:
            logger.error(f"❌ ROTATION FAILED: {pos.get('token_symbol')} - {error_msg}")
