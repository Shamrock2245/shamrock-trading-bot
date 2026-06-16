#!/usr/bin/env python3
"""Seed the immutable trade ledger from existing trades.json.

Run once to backfill historical trades into the JSONL ledger.
Safe to re-run — checks if ledger already exists and has content.
"""
import json
import os
from pathlib import Path

TRADES_FILE = Path("/app/output/trades.json")
LEDGER_FILE = Path("/app/output/trade_ledger.jsonl")

def seed():
    if LEDGER_FILE.exists() and LEDGER_FILE.stat().st_size > 0:
        with open(LEDGER_FILE) as f:
            line_count = sum(1 for _ in f)
        print(f"Ledger already has {line_count} entries. Skipping seed.")
        return

    if not TRADES_FILE.exists():
        print("No trades.json found. Nothing to seed.")
        return

    with open(TRADES_FILE) as f:
        trades = json.load(f)

    print(f"Seeding ledger with {len(trades)} historical trades...")

    running_pnl = 0.0
    with open(LEDGER_FILE, "w") as f:
        for i, trade in enumerate(trades):
            pnl = float(trade.get("pnl_usd", 0) or 0)
            running_pnl += pnl
            record = {
                **trade,
                "running_total_pnl_usd": round(running_pnl, 4),
                "ledger_seq": i,
            }
            f.write(json.dumps(record, default=str) + "\n")

    print(f"Done. Wrote {len(trades)} records to {LEDGER_FILE}")
    print(f"Running P&L total: ${running_pnl:.2f}")

if __name__ == "__main__":
    seed()
