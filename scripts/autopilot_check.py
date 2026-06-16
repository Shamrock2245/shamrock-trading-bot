#!/usr/bin/env python3
"""
Autopilot Optimization Loop — runs on the remote server every 60 min.
Checks P&L, trade velocity, win rate, strategy performance, and system health.
Outputs actionable findings for the next iteration.
"""
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

LEDGER = Path("/app/output/trade_ledger.jsonl")
TRADES = Path("/app/output/trades.json")
POSITIONS = Path("/app/output/positions.json")
HL_STATE = Path("/app/data/dashboard/hl_perps_state.json")
CB_STATE = Path("/app/data/dashboard/coinbase_arb_state.json")

def load_ledger():
    if not LEDGER.exists():
        return []
    return [json.loads(l) for l in LEDGER.read_text().strip().split("\n") if l.strip()]

def main():
    now = datetime.now(timezone.utc)
    print(f"\n{'='*60}")
    print(f"  SHAMROCK AUTOPILOT CHECK — {now.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*60}\n")

    # ── Ledger Analysis
    ledger = load_ledger()
    if not ledger:
        print("⚠️  No ledger data found!")
        return

    total = len(ledger)
    running_pnl = float(ledger[-1].get("running_total_pnl_usd", 0))
    print(f"📊 LEDGER: {total} total trades | Running P&L: ${running_pnl:.2f}")

    # Last hour
    cutoff_1h = (now - timedelta(hours=1)).isoformat()
    recent_1h = [t for t in ledger if t.get("timestamp", "") > cutoff_1h]
    
    # Last 6 hours
    cutoff_6h = (now - timedelta(hours=6)).isoformat()
    recent_6h = [t for t in ledger if t.get("timestamp", "") > cutoff_6h]

    for label, recent in [("1 HOUR", recent_1h), ("6 HOURS", recent_6h)]:
        if recent:
            sells = [t for t in recent if t.get("action") == "SELL"]
            pnl_sum = sum(float(t.get("pnl_usd", 0) or 0) for t in sells)
            wins = [t for t in sells if float(t.get("pnl_usd", 0) or 0) > 0]
            losses = [t for t in sells if float(t.get("pnl_usd", 0) or 0) < 0]
            win_rate = len(wins) / len(sells) * 100 if sells else 0
            avg_win = sum(float(t.get("pnl_usd", 0)) for t in wins) / len(wins) if wins else 0
            avg_loss = sum(float(t.get("pnl_usd", 0)) for t in losses) / len(losses) if losses else 0
            
            print(f"\n📈 LAST {label}:")
            print(f"   Trades: {len(recent)} ({len(sells)} sells)")
            print(f"   P&L:    ${pnl_sum:+.2f}")
            print(f"   Wins:   {len(wins)} | Losses: {len(losses)} | Win Rate: {win_rate:.0f}%")
            print(f"   Avg Win: ${avg_win:.4f} | Avg Loss: ${avg_loss:.4f}")
        else:
            print(f"\n📈 LAST {label}: No trades")

    # ── Open Positions
    if POSITIONS.exists():
        try:
            positions = json.load(open(POSITIONS))
            print(f"\n📌 OPEN POSITIONS: {len(positions)}")
        except:
            pass

    # ── HL Perps Status
    if HL_STATE.exists():
        try:
            hl = json.loads(HL_STATE.read_text())
            print(f"\n🔮 HL PERPS: scans={hl.get('scan_count', 0)} signals={hl.get('signals_generated', 0)} trades={hl.get('trades_executed', 0)} daily_pnl=${hl.get('daily_pnl', 0):.2f}")
        except:
            pass

    # ── Coinbase Arb Status
    if CB_STATE.exists():
        try:
            cb = json.loads(CB_STATE.read_text())
            spreads = cb.get("spreads", [])
            opps = cb.get("opportunities", [])
            print(f"\n💱 CB ARB: {len(spreads)} spreads | {len(opps)} actionable (>1%)")
            if spreads:
                print(f"   Best: {spreads[0]['symbol']} {spreads[0]['spread_pct']:+.3f}%")
        except:
            pass

    # ── Bottleneck Analysis
    print(f"\n🔧 ISSUES:")
    if len(recent_1h) == 0:
        print("   ⚠️  ZERO trades last hour — scanner too selective")
    sells_1h = [t for t in recent_1h if t.get("action") == "SELL"]
    if recent_1h and not sells_1h:
        print("   ⚠️  No sells — positions holding too long")

if __name__ == "__main__":
    main()
