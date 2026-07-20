#!/usr/bin/env python3
"""
scripts/seed_autoban.py

Seeds data/dashboard/hl_coin_perf.json with real win/loss stats from the
trade_history CSV analysis (v17, Jun 16 – Jul 14 2026).

Run once after deploying the auto-blacklist feature to immediately ban the
known toxic coins rather than waiting for them to accumulate 5 more losses.

Usage:
    python3 scripts/seed_autoban.py [--dry-run]
"""
import json
import os
import sys
import time
from pathlib import Path

# ── Known toxic coin stats from live trade history (v17 CSV analysis) ─────────
# Only coins with >= 5 trades and WR < 30% are eligible for immediate ban.
# Source: analyze_v17.py output, Jun 16 – Jul 14 2026.
TOXIC_COIN_STATS = {
    "AAVE":     {"wins": 2,  "losses": 20},  # WR=9%   (22 trades)
    "HMSTR":    {"wins": 0,  "losses": 10},  # WR=0%   (10 trades)
    "BRETT":    {"wins": 1,  "losses": 12},  # WR=8%  (13 trades)
    "GRASS":    {"wins": 1,  "losses": 4},   # WR=20%  (5 trades)
    "EIGEN":    {"wins": 1,  "losses": 4},   # WR=20%  (5 trades)
    "APE":      {"wins": 2,  "losses": 4},   # WR=33%  (6 trades) — borderline
    "MET":      {"wins": 1,  "losses": 4},   # WR=20%  (5 trades)
    "HYPE":     {"wins": 0,  "losses": 4},   # WR=0%   (4 trades) — below min but pattern clear
    "MEME":     {"wins": 0,  "losses": 5},   # WR=0%   (5 trades)
    "FARTCOIN": {"wins": 0,  "losses": 3},   # WR=0%   (3 trades) — below min but pattern clear
    # trade_history (28) last 7d: 7 trades, 14% WR, −$30.57 (worst coin)
    "KAITO":    {"wins": 1,  "losses": 6},   # WR=14%  (7 trades)
}

# Ban threshold config (must match HL_PERPS_AUTOBAN_* env vars)
AUTOBAN_WR_THRESHOLD = float(os.getenv("HL_PERPS_AUTOBAN_WR_THRESHOLD", "0.30"))
AUTOBAN_MIN_TRADES   = int(os.getenv("HL_PERPS_AUTOBAN_MIN_TRADES", "5"))
AUTOBAN_HOURS        = float(os.getenv("HL_PERPS_AUTOBAN_HOURS", "48.0"))
STATE_DIR            = Path(os.getenv("DASHBOARD_STATE_DIR", "./data/dashboard"))
COIN_PERF_FILE       = STATE_DIR / "hl_coin_perf.json"

DRY_RUN = "--dry-run" in sys.argv


def main():
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    # Load existing state (if any)
    existing: dict = {"coin_perf": {}, "autoban_until": {}}
    if COIN_PERF_FILE.exists():
        try:
            existing = json.loads(COIN_PERF_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"⚠️  Could not load existing state: {e} — starting fresh")

    coin_perf    = existing.get("coin_perf", {})
    autoban_until = existing.get("autoban_until", {})
    now           = time.time()
    ban_expires   = now + AUTOBAN_HOURS * 3600

    print(f"\n{'[DRY RUN] ' if DRY_RUN else ''}Seeding auto-blacklist from live trade history...\n")
    print(f"  Threshold : WR < {AUTOBAN_WR_THRESHOLD*100:.0f}% with >= {AUTOBAN_MIN_TRADES} trades")
    print(f"  Ban length: {AUTOBAN_HOURS:.0f} hours\n")

    banned_count = 0
    skipped_count = 0

    for coin, stats in TOXIC_COIN_STATS.items():
        wins   = stats["wins"]
        losses = stats["losses"]
        total  = wins + losses
        wr     = wins / total if total > 0 else 0.0

        # Merge with existing stats (don't overwrite if already tracked)
        if coin not in coin_perf:
            coin_perf[coin] = {
                "wins": wins,
                "losses": losses,
                "last_updated": now,
            }
        else:
            # Keep the higher of existing vs seeded (don't regress history)
            existing_total = coin_perf[coin]["wins"] + coin_perf[coin]["losses"]
            if total > existing_total:
                coin_perf[coin]["wins"]   = wins
                coin_perf[coin]["losses"] = losses
                coin_perf[coin]["last_updated"] = now

        # Apply ban if eligible
        should_ban = total >= AUTOBAN_MIN_TRADES and wr < AUTOBAN_WR_THRESHOLD
        already_banned = coin in autoban_until and autoban_until[coin] > now

        if should_ban and not already_banned:
            autoban_until[coin] = ban_expires
            remaining_h = AUTOBAN_HOURS
            print(f"  🚫 BANNED  {coin:10s} | trades={total:2d} | WR={wr*100:.0f}% | ban={remaining_h:.0f}h")
            banned_count += 1
        elif already_banned:
            remaining_h = (autoban_until[coin] - now) / 3600
            print(f"  ⏳ ALREADY {coin:10s} | trades={total:2d} | WR={wr*100:.0f}% | {remaining_h:.1f}h remaining")
            skipped_count += 1
        else:
            print(f"  ✅ SKIP    {coin:10s} | trades={total:2d} | WR={wr*100:.0f}% (below min trades or above threshold)")
            skipped_count += 1

    print(f"\n  Summary: {banned_count} newly banned, {skipped_count} skipped")

    if not DRY_RUN:
        COIN_PERF_FILE.write_text(
            json.dumps({"coin_perf": coin_perf, "autoban_until": autoban_until}, indent=2),
            encoding="utf-8",
        )
        print(f"\n  ✅ State written to {COIN_PERF_FILE}")
    else:
        print("\n  [DRY RUN] No files written.")


if __name__ == "__main__":
    main()
