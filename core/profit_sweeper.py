"""
core/profit_sweeper.py — Autonomous Profit Extraction Engine

Executes on-chain transfers of realized profits to an external, 
cold-storage paycheck wallet when daily goals are reached.
Ensures a base capital buffer is maintained in the hot wallet.
"""

import logging
import os
import time
from typing import Optional

from web3 import Web3

from config import settings
from config.chains import CHAINS
from config.wallets import WALLETS, get_wallets_for_chain
from core.wallet_router import get_usdc_balance, get_native_balance
from data.providers.arb_price_feed import STABLECOINS

logger = logging.getLogger(__name__)

# Minimum capital to leave in the hot wallet per chain (gas + working capital)
BUFFER_USD = float(os.getenv("PROFIT_SWEEP_BUFFER_USD", "2000.0"))
MIN_SWEEP_USD = float(os.getenv("PROFIT_SWEEP_MIN_USD", "50.0"))

# Standard ERC-20 transfer ABI
ERC20_ABI = [
    {
        "constant": False,
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function"
    }
]

_last_sweep_time: float = 0.0
SWEEP_COOLDOWN_SECONDS = int(os.getenv("PROFIT_SWEEP_COOLDOWN_SECONDS", str(12 * 3600)))


def execute_sweep() -> bool:
    """
    Sweeps profits from EVM hot wallets to the PAYCHECK_WALLET_ADDRESS.
    Returns True if any sweep was successfully executed.
    """
    global _last_sweep_time
    
    paycheck_wallet = os.getenv("WALLET_ADDRESS_C", "").strip()
    if not paycheck_wallet:
        logger.error("🛑 WALLET_ADDRESS_C not set in environment! Cannot sweep profits.")
        return False
        
    mode = getattr(settings, "MODE", "paper").lower()
    if mode != "live" and mode != "prod":
        logger.warning(f"⚠️ Cannot sweep profits in {mode} mode. Must be 'live'.")
        return False

    if (time.time() - _last_sweep_time) < SWEEP_COOLDOWN_SECONDS:
        logger.info("⏳ Profit sweeper is on cooldown. Skipping.")
        return False

    if not Web3.is_address(paycheck_wallet):
        logger.error(f"🛑 Invalid WALLET_ADDRESS_C: {paycheck_wallet}")
        return False

    paycheck_wallet = Web3.to_checksum_address(paycheck_wallet)
    sweep_executed = False

    for chain in ["base", "arbitrum", "ethereum"]:
        if chain not in CHAINS:
            continue
            
        wallets = get_wallets_for_chain(chain)
        if not wallets:
            continue
            
        primary_wallet = wallets[0]
        wallet_addr = primary_wallet.address
        private_key = os.getenv(primary_wallet.private_key_env)
        
        if not private_key:
            logger.warning(f"⚠️ Missing private key for {wallet_addr} on {chain}. Skipping sweep.")
            continue

        rpc_url = CHAINS[chain].rpc_url
        if not rpc_url:
            continue
            
        w3 = Web3(Web3.HTTPProvider(rpc_url))
        if not w3.is_connected():
            logger.error(f"🔌 Failed to connect to {chain} RPC.")
            continue
            
        # ── 1. Check USDC Balance ──────────────────────────────────────────────
        usdc_addr = STABLECOINS.get(chain)
        if usdc_addr:
            try:
                # We assume USDC has 6 decimals for EVM chains natively.
                # get_usdc_balance returns the float value (e.g. 2150.50).
                balance_usd = get_usdc_balance(chain, wallet_addr)
                
                if balance_usd > (BUFFER_USD + MIN_SWEEP_USD):
                    amount_to_sweep = balance_usd - BUFFER_USD
                    logger.info(f"🧹 Sweeping ${amount_to_sweep:.2f} USDC from {chain} hot wallet...")
                    
                    contract = w3.eth.contract(address=Web3.to_checksum_address(usdc_addr), abi=ERC20_ABI)
                    amount_wei = int(amount_to_sweep * 1e6)  # USDC has 6 decimals
                    
                    tx = contract.functions.transfer(paycheck_wallet, amount_wei).build_transaction({
                        "chainId": CHAINS[chain].chain_id,
                        "gas": 100000,
                        "gasPrice": w3.eth.gas_price,
                        "nonce": w3.eth.get_transaction_count(Web3.to_checksum_address(wallet_addr)),
                    })
                    
                    signed_tx = w3.eth.account.sign_transaction(tx, private_key=private_key)
                    tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
                    logger.info(f"⏳ USDC Sweep tx broadcasted on {chain}: {w3.to_hex(tx_hash)} — waiting for receipt...")
                    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
                    if receipt.status == 1:
                        logger.info(f"✅ USDC Sweep confirmed on {chain}: ${amount_to_sweep:.2f} → {paycheck_wallet[:10]}...")
                        sweep_executed = True
                    else:
                        logger.error(f"❌ USDC Sweep REVERTED on {chain}: {w3.to_hex(tx_hash)} — funds NOT moved")
            except Exception as e:
                logger.error(f"❌ Failed to sweep USDC on {chain}: {e}")

    if sweep_executed:
        _last_sweep_time = time.time()
        
    return sweep_executed
