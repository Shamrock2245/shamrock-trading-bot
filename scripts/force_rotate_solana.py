import sys
import json
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Add parent directory to path so we can import from core
parent_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(parent_dir))

from config import settings
from config.wallets import WALLETS
from core.executor import TradeExecutor, build_take_profit_params
from core.position_monitor import load_positions, save_positions

def force_rotate_solana():
    """
    Finds all active Solana positions and liquidates them to recycle capital.
    """
    logger.info("♻️  Starting forceful capital rotation for Solana positions...")
    positions = load_positions()
    
    active_sol_positions = [
        p for p in positions 
        if float(p.get("remaining_quantity", 0)) > 0 
        and p.get("chain", "").lower() == "solana"
        and p.get("status", "open") != "closed"
    ]
    
    if not active_sol_positions:
        logger.info("✅ No active Solana positions to recycle. Capital is already freed up!")
        return
        
    logger.info(f"🔍 Found {len(active_sol_positions)} active Solana positions to liquidate.")
    
    executor = TradeExecutor()
    positions_updated = False
    
    for pos in active_sol_positions:
        symbol = pos.get("token_symbol", "UNKNOWN")
        chain = pos.get("chain", "solana")
        token_address = pos.get("token_address")
        wallet_alias = pos.get("wallet", "primary")
        sell_qty = float(pos.get("remaining_quantity", 0))
        pnl_pct = float(pos.get("unrealized_pnl_pct", 0.0)) * 100  # assuming it's a fraction or percentage, just for logging
        
        logger.info(f"🔄 Liquidating {sell_qty} {symbol} on {wallet_alias} (Current PnL: {pnl_pct:.2f}%)...")
        
        if pos.get("is_paper", True) or settings.MODE == "paper":
            logger.info(f"📝 PAPER MODE: Mocking liquidation for {symbol}.")
            # Hack closed
            pos["status"] = "closed"
            pos["remaining_quantity"] = 0.0
            positions_updated = True
            continue

        wallet = None
        for wk, wv in WALLETS.items():
            if wv.address.lower() == wallet_alias.lower() or wv.alias.lower() == wallet_alias.lower():
                wallet = wv
                break
                
        if not wallet:
            logger.error(f"❌ Cannot liquidate {symbol}: No wallet found for '{wallet_alias}'")
            continue
            
        decimals = int(pos.get("token_decimals", 6)) # Sol usually 6
        token_amount_wei = int(sell_qty * (10 ** decimals))
        
        params = build_take_profit_params(
            wallet=wallet,
            chain=chain,
            token_address=token_address,
            token_amount_wei=token_amount_wei,
            slippage_bps=500,  # 5% slippage to guarantee execution on struggling assets
        )
        
        try:
            result = executor.execute_trade(params)
            
            if result.success:
                logger.info(f"✅ SUCCESSFULLY LIQUIDATED {symbol}. Tx: {result.tx_hash}")
                pos["status"] = "closed"
                pos["remaining_quantity"] = 0.0
                positions_updated = True
            else:
                logger.error(f"❌ FAILED to liquidate {symbol}: {result.error}")
        except Exception as e:
            logger.error(f"⚠️ Exception liquidating {symbol}: {e}")

    if positions_updated:
        save_positions(positions)
        logger.info("💾 Saved updated positions to disk.")

if __name__ == "__main__":
    force_rotate_solana()
