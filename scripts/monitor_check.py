#!/usr/bin/env python3
"""
Shamrock Trading Bot — Automated Health & Profit Monitor
Runs inside the Docker container via `docker compose exec`.
Checks: positions, P&L, trade activity, errors, wallet balances.
"""
import json
import os
import time
from pathlib import Path
from datetime import datetime, timezone

POSITIONS_FILE = Path("/app/output/positions.json")
TRADES_FILE = Path("/app/output/trades.json")

def load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return []

def get_wallet_balances():
    """Fetch on-chain balances for all wallets across Base and Arbitrum."""
    try:
        from web3 import Web3
        wallets = {
            "Primary": os.getenv("WALLET_ADDRESS_PRIMARY"),
            "B": os.getenv("WALLET_ADDRESS_B"),
            "C": os.getenv("WALLET_ADDRESS_C"),
        }
        rpcs = {
            "base": os.getenv("BASE_RPC_URL"),
            "arbitrum": os.getenv("ARBITRUM_RPC_URL"),
        }
        usdc = {
            "base": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
            "arbitrum": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
        }
        erc20_abi = [{"constant":True,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"","type":"uint256"}],"type":"function"}]
        
        results = {}
        total_usd = 0.0
        for chain, rpc in rpcs.items():
            if not rpc:
                continue
            try:
                w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 10}))
                for name, addr in wallets.items():
                    if not addr:
                        continue
                    eth_bal = float(w3.from_wei(w3.eth.get_balance(Web3.to_checksum_address(addr)), "ether"))
                    try:
                        tok = w3.eth.contract(address=Web3.to_checksum_address(usdc[chain]), abi=erc20_abi)
                        usdc_val = tok.functions.balanceOf(Web3.to_checksum_address(addr)).call() / 1e6
                    except:
                        usdc_val = 0
                    key = f"{chain}_{name}"
                    results[key] = {"eth": eth_bal, "usdc": usdc_val}
                    total_usd += usdc_val
            except Exception as e:
                results[f"{chain}_error"] = str(e)
        
        results["total_usdc"] = total_usd
        return results
    except Exception as e:
        return {"error": str(e)}

def analyze():
    now = datetime.now(timezone.utc)
    report = {"timestamp": now.isoformat(), "status": "OK", "alerts": [], "actions": []}
    
    # 1. Positions
    positions = load_json(POSITIONS_FILE)
    open_pos = [p for p in positions if p.get("status") == "open"]
    closed_pos = [p for p in positions if p.get("status") == "closed"]
    report["positions"] = {
        "total": len(positions),
        "open": len(open_pos),
        "closed": len(closed_pos),
    }
    
    # Analyze open positions
    open_details = []
    total_unrealized_pnl = 0.0
    for p in open_pos:
        symbol = p.get("token_symbol", "???")
        chain = p.get("chain", "???")
        entry = p.get("entry_price", 0)
        current = p.get("last_check_price", p.get("current_price", 0))
        entry_value = p.get("entry_value_usd", 0)
        
        if entry and current and entry > 0:
            pnl_pct = ((current - entry) / entry) * 100
        else:
            pnl_pct = 0
        
        age_hours = 0
        opened_at = p.get("opened_at", 0)
        if opened_at:
            age_hours = (time.time() - opened_at) / 3600
        
        detail = {
            "symbol": symbol,
            "chain": chain,
            "entry_price": entry,
            "current_price": current,
            "pnl_pct": round(pnl_pct, 2),
            "entry_value_usd": round(entry_value, 2),
            "age_hours": round(age_hours, 1),
            "tp1_hit": p.get("tp1_hit", False),
        }
        open_details.append(detail)
        
        # Alert on positions losing > 15%
        if pnl_pct < -15:
            report["alerts"].append(f"⚠️ {symbol} on {chain} is DOWN {pnl_pct:.1f}% — consider stop-loss")
        
        # Alert on stale positions (>12h and flat)
        if age_hours > 12 and abs(pnl_pct) < 5:
            report["alerts"].append(f"🕐 {symbol} on {chain} is STALE ({age_hours:.0f}h, {pnl_pct:+.1f}%) — consider rotation")
        
        # Celebrate winners
        if pnl_pct > 20:
            report["alerts"].append(f"🚀 {symbol} on {chain} is UP {pnl_pct:.1f}% — let it run!")
    
    report["open_positions"] = open_details
    
    # 2. Recent trades (last 30 minutes)
    trades = load_json(TRADES_FILE)
    
    def parse_ts(t):
        """Extract unix timestamp from trade, handling both float and ISO string."""
        ts = t.get("timestamp", 0)
        if isinstance(ts, (int, float)):
            return float(ts)
        if isinstance(ts, str):
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                return dt.timestamp()
            except:
                return 0
        return 0
    
    recent_cutoff = time.time() - (30 * 60)  # last 30 min
    recent_trades = [t for t in trades if parse_ts(t) > recent_cutoff]
    
    # Last 24h trades
    daily_cutoff = time.time() - (24 * 3600)
    daily_trades = [t for t in trades if parse_ts(t) > daily_cutoff]
    daily_buys = [t for t in daily_trades if t.get("side") == "buy"]
    daily_sells = [t for t in daily_trades if t.get("side") == "sell"]
    
    # Calculate daily P&L from completed sells
    daily_pnl = 0.0
    for t in daily_sells:
        pnl = t.get("realized_pnl_usd", t.get("pnl_usd", 0))
        if pnl:
            daily_pnl += pnl
    
    report["trades"] = {
        "recent_30m": len(recent_trades),
        "daily_total": len(daily_trades),
        "daily_buys": len(daily_buys),
        "daily_sells": len(daily_sells),
        "daily_realized_pnl": round(daily_pnl, 2),
    }
    
    if len(daily_trades) == 0:
        report["alerts"].append("📊 ZERO trades in 24h — bot may not be finding opportunities")
    
    # 3. Wallet balances
    balances = get_wallet_balances()
    report["balances"] = balances
    
    # 4. Overall assessment
    if len(report["alerts"]) == 0:
        report["alerts"].append("✅ All systems nominal — no issues detected")
    
    return report

if __name__ == "__main__":
    report = analyze()
    print(json.dumps(report, indent=2, default=str))
