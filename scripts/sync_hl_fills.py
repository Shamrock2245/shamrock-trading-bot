#!/usr/bin/env python3
"""
scripts/sync_hl_fills.py — Pull Hyperliquid userFills into local OpenAlice ledger.

Writes:
  output/hl_fills.jsonl     append-only raw fills (deduped by tid/time/coin/px/sz)
  output/hl_paired_trades.json  FIFO-paired closes for self_improving_agent

Usage:
  python scripts/sync_hl_fills.py
  python scripts/sync_hl_fills.py --wallet 0x...
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

HL_INFO = "https://api.hyperliquid.xyz/info"
OUT_DIR = ROOT / "output"
FILLS_JSONL = OUT_DIR / "hl_fills.jsonl"
PAIRED_JSON = OUT_DIR / "hl_paired_trades.json"


def fetch_fills(wallet: str) -> list:
    r = requests.post(HL_INFO, json={"type": "userFills", "user": wallet}, timeout=45)
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, list) else []


def fill_key(f: dict) -> str:
    return "|".join(
        str(x)
        for x in (
            f.get("tid") or f.get("hash") or "",
            f.get("time"),
            f.get("coin"),
            f.get("px"),
            f.get("sz"),
            f.get("dir"),
            f.get("closedPnl"),
        )
    )


def load_seen_keys() -> set:
    seen = set()
    if not FILLS_JSONL.exists():
        return seen
    with FILLS_JSONL.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                seen.add(rec.get("_key") or fill_key(rec))
            except Exception:
                continue
    return seen


def pair_trades(fills: list) -> list:
    """FIFO pair Open→Close per coin (same logic as CSV40 paired analysis)."""
    from collections import defaultdict

    by_coin: dict = defaultdict(list)
    for f in sorted(fills, key=lambda x: int(x.get("time") or 0)):
        by_coin[f.get("coin") or "?"].append(f)

    trades = []
    for coin, rows in by_coin.items():
        stack = []
        for row in rows:
            d = str(row.get("dir") or "")
            if d.startswith("Open"):
                stack.append(row)
            elif d.startswith("Close"):
                open_row = stack.pop(0) if stack else None
                t_close = int(row.get("time") or 0)
                t_open = int(open_row.get("time") or t_close) if open_row else t_close
                dur_sec = max(0.0, (t_close - t_open) / 1000.0)
                pnl = float(row.get("closedPnl") or 0)
                fee = float(row.get("fee") or 0) + (
                    float(open_row.get("fee") or 0) if open_row else 0.0
                )
                trades.append(
                    {
                        "token_symbol": coin,
                        "coin": coin,
                        "action": "SELL",
                        "side": "long" if "Long" in d else "short",
                        "dir": d,
                        "pnl_usd": pnl,
                        "closedPnl": pnl,
                        "realized_pnl": pnl,
                        "fee": fee,
                        "price_usd": float(row.get("px") or 0),
                        "entry_price": float(open_row.get("px") or 0) if open_row else None,
                        "quantity": float(row.get("sz") or 0),
                        "value_usd": float(row.get("ntl") or 0),
                        "holding_duration_seconds": dur_sec,
                        "hold_time": dur_sec,
                        "timestamp": datetime.fromtimestamp(
                            t_close / 1000.0, tz=timezone.utc
                        ).isoformat(),
                        "entry_time": datetime.fromtimestamp(
                            t_open / 1000.0, tz=timezone.utc
                        ).isoformat(),
                        "chain": "hyperliquid",
                        "strategy_profile": "hl_perps",
                        "reason": "hl_fill_sync",
                        "rapid_close": dur_sec <= 10.0,
                    }
                )
    return trades


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--wallet",
        default=os.getenv("HYPERLIQUID_WALLET_ADDRESS", ""),
        help="HL wallet address",
    )
    args = ap.parse_args()
    wallet = (args.wallet or "").strip()
    if not wallet:
        print("ERROR: set HYPERLIQUID_WALLET_ADDRESS or pass --wallet", file=sys.stderr)
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fills = fetch_fills(wallet)
    seen = load_seen_keys()
    new = 0
    with FILLS_JSONL.open("a") as fh:
        for f in fills:
            k = fill_key(f)
            if k in seen:
                continue
            rec = dict(f)
            rec["_key"] = k
            rec["_synced_at"] = datetime.now(timezone.utc).isoformat()
            fh.write(json.dumps(rec) + "\n")
            seen.add(k)
            new += 1

    # Rebuild paired from full jsonl for SSoT
    all_fills = []
    with FILLS_JSONL.open() as fh:
        for line in fh:
            try:
                all_fills.append(json.loads(line))
            except Exception:
                pass
    paired = pair_trades(all_fills)
    PAIRED_JSON.write_text(json.dumps(paired, indent=2), encoding="utf-8")

    closes = [t for t in paired if t.get("action") == "SELL"]
    net = sum(float(t.get("pnl_usd") or 0) for t in closes)
    rapid = sum(1 for t in closes if t.get("rapid_close"))
    wins = sum(1 for t in closes if float(t.get("pnl_usd") or 0) > 0)
    n = len(closes)
    print(f"wallet={wallet[:6]}…{wallet[-4:]}")
    print(f"fills_api={len(fills)} new_appended={new} ledger_lines={len(all_fills)}")
    print(f"paired_closes={n} net_pnl=${net:.2f} wr={100*wins/n:.1f}%" if n else "paired_closes=0")
    print(f"rapid_closes_le_10s={rapid} ({100*rapid/n:.1f}% of closes)" if n else "")
    print(f"wrote {FILLS_JSONL} and {PAIRED_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
