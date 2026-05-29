"""
scripts/avax_rebalancer.py — Avalanche Portfolio Rebalancer

This script reads the current holdings of Wallet B on Avalanche via public RPC,
scores each position based on liquidity, volume, and momentum, and generates
a liquidation plan for underperforming assets (like BEAM) while preserving
dust that isn't worth the gas to sell.

It outputs a JSON plan that the main bot execution engine can consume to
perform the actual swaps once private keys are loaded.
"""

import json
import os
import time
import logging
from datetime import datetime, timezone
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("avax_rebalancer")

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────
WALLET_B = "0x0835eb8447f3ac90351951bb5d22e77afd9b81c0"
AVAX_RPC = os.getenv("AVAX_RPC_URL", "https://api.avax.network/ext/bc/C/rpc")

# Known tokens from previous scan
TOKENS = {
    "0xb97ef9ef8734c71904d8002f8b6bc66dd9c48a6e": ("USDC", 6),
    "0x6b6c18fb6c11bc7877f1b061e638640fab4bc898": ("MILK", 18),
    "0x15a262f376e328354aae7232d55f1c8906d6869f": ("GORC", 18),
    "0xd19f0fd139d78a56d4d427061af5f7929cdc0a3b": ("BLOB", 18),
    "0x675a32a03066176bbd874a25f142e580ea37cae2": ("BKG", 18),
    "0x5eb540dcabff763e714b9d4a4c1f2d34171bb768": ("DARKCOQ", 18),
    "0x921f10d157d6dfff4ddcf72a12b53c2effefbb90": ("LFG", 18),
    "0x420fca0121dc280391978ef9b585c4a0c1e6b3e8": ("COQ", 18),
    "0x184ff13b3ebcb25be44e860163a5d8391dd568c1": ("KIMBO", 18),
    "0x20450fb0cfe8ddc608396805e02407ccb97bfe91": ("CATCOQ", 18),
    "0x7979871595b80433183950ab6c6457752b585805": ("SECOND", 18),
    "0xd83156f54e20741040b251c329e5cece53b25e59": ("MOOO", 18),
    "0x3377aca4c0bfd021be6bd762b5f594975e77f9cf": ("CATWIF", 18),
    "0xd5d053d5b769383e860d1520da7a908e00919f36": ("JUICE", 18),
    "0x11055a34d29a2fb3a2c016c76820a9fb7a402551": ("MINIKIMBO", 18),
    "0x62d0a8458ed7719fdaf978fe5929c6d342b0bfce": ("BEAM", 18),
}

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def rpc_call(method: str, params: list) -> str:
    try:
        r = requests.post(
            AVAX_RPC,
            json={"jsonrpc": "2.0", "method": method, "params": params, "id": 1},
            timeout=10
        )
        r.raise_for_status()
        return r.json().get("result", "0x0")
    except Exception as e:
        logger.error(f"RPC error {method}: {e}")
        return "0x0"

def get_native_balance(wallet: str) -> float:
    raw = rpc_call("eth_getBalance", [wallet, "latest"])
    if raw and raw != "0x":
        return int(raw, 16) / 1e18
    return 0.0

def get_erc20_balance(token_addr: str, wallet: str, decimals: int) -> float:
    # balanceOf(address) = 0x70a08231
    data = "0x70a08231" + wallet[2:].lower().zfill(64)
    raw = rpc_call("eth_call", [{"to": token_addr, "data": data}, "latest"])
    if raw and raw != "0x" and raw != "0x0":
        return int(raw, 16) / (10**decimals)
    return 0.0

def get_avax_price() -> float:
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price?ids=avalanche-2&vs_currencies=usd",
            timeout=10
        )
        return r.json().get("avalanche-2", {}).get("usd", 25.0)
    except Exception:
        return 25.0

def get_token_market_data(token_addr: str) -> dict:
    """Fetch price, liquidity, and volume from DexScreener."""
    try:
        r = requests.get(
            f"https://api.dexscreener.com/tokens/v1/avalanche/{token_addr}",
            headers={"accept": "application/json"},
            timeout=10
        )
        if r.status_code == 200:
            data = r.json()
            pairs = data if isinstance(data, list) else [data]
            avax_pairs = [p for p in pairs if p.get("chainId", "").lower() in ("avalanche", "avax")]
            if avax_pairs:
                # Sort by liquidity
                avax_pairs.sort(key=lambda p: float(p.get("liquidity", {}).get("usd", 0) or 0), reverse=True)
                p = avax_pairs[0]
                return {
                    "price_usd": float(p.get("priceUsd", 0) or 0),
                    "liquidity_usd": float(p.get("liquidity", {}).get("usd", 0) or 0),
                    "volume_24h": float(p.get("volume", {}).get("h24", 0) or 0),
                    "price_change_24h": float(p.get("priceChange", {}).get("h24", 0) or 0),
                }
    except Exception as e:
        logger.debug(f"DexScreener error for {token_addr}: {e}")
    
    return {"price_usd": 0.0, "liquidity_usd": 0.0, "volume_24h": 0.0, "price_change_24h": 0.0}

# ─────────────────────────────────────────────────────────────────────────────
# Main Rebalance Logic
# ─────────────────────────────────────────────────────────────────────────────
def generate_rebalance_plan():
    logger.info(f"Starting AVAX portfolio rebalance scan for {WALLET_B}...")
    
    avax_price = get_avax_price()
    avax_bal = get_native_balance(WALLET_B)
    avax_usd = avax_bal * avax_price
    
    logger.info(f"AVAX Price: ${avax_price:.2f}")
    logger.info(f"Native Balance: {avax_bal:.4f} AVAX (${avax_usd:.2f})")
    
    holdings = []
    for addr, (sym, dec) in TOKENS.items():
        bal = get_erc20_balance(addr, WALLET_B, dec)
        if bal > 0:
            market = get_token_market_data(addr)
            usd_val = bal * market["price_usd"]
            
            # Special case for USDC
            if sym == "USDC":
                usd_val = bal  # Force 1:1 for stablecoin
                market["price_usd"] = 1.0
            
            holdings.append({
                "symbol": sym,
                "address": addr,
                "balance": bal,
                "price_usd": market["price_usd"],
                "value_usd": usd_val,
                "liquidity_usd": market["liquidity_usd"],
                "volume_24h": market["volume_24h"],
                "price_change_24h": market["price_change_24h"],
            })
            time.sleep(0.2)  # Rate limit

    # Sort by value
    holdings.sort(key=lambda x: x["value_usd"], reverse=True)
    
    plan = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "wallet": WALLET_B,
        "capital": {
            "avax_balance": avax_bal,
            "avax_usd_value": avax_usd,
            "usdc_balance": 0.0,
            "total_deployable_usd": avax_usd,
        },
        "actions": {
            "liquidate": [],
            "monitor": [],
            "ignore_dust": [],
        }
    }
    
    print("\n" + "=" * 90)
    print(f"  AVALANCHE PORTFOLIO REBALANCE PLAN")
    print("=" * 90)
    print(f"  {'SYMBOL':<10} {'BALANCE':>12} {'VALUE':>10} {'LIQ':>10} {'VOL24H':>10} {'24H%':>7}  ACTION")
    print("-" * 90)
    
    for h in holdings:
        sym = h["symbol"]
        val = h["value_usd"]
        liq = h["liquidity_usd"]
        vol = h["volume_24h"]
        pc = h["price_change_24h"]
        
        action = ""
        reason = ""
        
        if sym == "USDC":
            plan["capital"]["usdc_balance"] = h["balance"]
            plan["capital"]["total_deployable_usd"] += h["balance"]
            action = "💵 DEPLOY"
            reason = "Stablecoin ready for sniping"
        elif val < 5.0:
            action = "🗑️  IGNORE"
            reason = "Dust value < $5, gas cost exceeds return"
            plan["actions"]["ignore_dust"].append(h)
        elif liq < 30000 or (pc < -20 and vol < 10000):
            action = "❌ LIQUIDATE"
            reason = "Low liquidity or dead momentum"
            plan["actions"]["liquidate"].append(h)
        else:
            action = "🟡 MONITOR"
            reason = "Holding value, monitor for exit"
            plan["actions"]["monitor"].append(h)
            
        bal_str = f"{h['balance']:.2f}" if h['balance'] < 1e6 else f"{h['balance']:.2e}"
        print(f"  {sym:<10} {bal_str:>12} ${val:>9.2f} ${liq:>9,.0f} ${vol:>9,.0f} {pc:>+7.1f}%  {action}")
        if action == "❌ LIQUIDATE":
            print(f"      └─ Reason: {reason}")

    print("\n" + "=" * 90)
    print(f"  SUMMARY")
    print("-" * 90)
    print(f"  Total Deployable Capital: ${plan['capital']['total_deployable_usd']:,.2f}")
    print(f"  USDC Ready:               ${plan['capital']['usdc_balance']:,.2f}")
    print(f"  AVAX Ready:               {plan['capital']['avax_balance']:.4f} AVAX")
    print(f"  Tokens to Liquidate:      {len(plan['actions']['liquidate'])} (Est. value: ${sum(t['value_usd'] for t in plan['actions']['liquidate']):.2f})")
    print("=" * 90 + "\n")
    
    # Save plan
    os.makedirs("reports", exist_ok=True)
    with open("reports/avax_rebalance_plan.json", "w") as f:
        json.dump(plan, f, indent=2)
    logger.info("Rebalance plan saved to reports/avax_rebalance_plan.json")
    
    return plan

if __name__ == "__main__":
    generate_rebalance_plan()
