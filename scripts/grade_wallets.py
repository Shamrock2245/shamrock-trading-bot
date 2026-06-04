#!/usr/bin/env python3
"""
scripts/grade_wallets.py
Uses the Moralis API to backtest the 30-day ROI of all tracked wallets in SMART_MONEY_WALLETS.
Isolates the top 3 most profitable wallets ("The Whales"), saves them to output/whale_tier_wallets.json,
and updates the copy-trading pool dynamically.
"""
import os
import json
import logging
import requests
from pathlib import Path
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("grade_wallets")

# Load environment
_ROOT = Path(__file__).parent.parent
load_dotenv(dotenv_path=_ROOT / ".env")

MORALIS_KEY = os.getenv("MORALIS_API_KEY", "")
BASE_URL = "https://deep-index.moralis.io/api/v2.2"
HEADERS = {
    "X-API-Key": MORALIS_KEY,
    "Accept": "application/json"
}

OUTPUT_FILE = _ROOT / "output" / "whale_tier_wallets.json"
OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

# We can import SMART_MONEY_WALLETS from config.settings
try:
    import sys
    sys.path.append(str(_ROOT))
    from config import settings
    WALLETS = settings.SMART_MONEY_WALLETS
except Exception as e:
    logger.error(f"Failed to import settings: {e}")
    # Fallback list of known wallets if import fails
    WALLETS = [
        "0x8acfbd922faeeccecf6a82492a48957d8fe9e5a0",
        "0x433042a34ec7dcc6826f21d6db55cb292db03499",
        "0x1dd13a22963057075b6bb60957901d41553180a1",
        "0xa56972fe0add34586c911114476827ac6a745f68",
        "0x8ab83d869f2bc250b781d26f6584fd5c562fdd9d",
        "0xaebf847be3c8830ec7e125ef3b4b2ac58d468b81",
        "0xcb5ea117bbb15aa307353ef7a989b4ca03e506e7",
        "0x6cd85f5e8294803b7a60efd0528f03f21848ba41",
        "0x18a83e1d022c9ccf8eef7444d03a0bf53fd88333",
        "0x21152db97be0aedb4e5c3878a39bc734250142a1",
    ]

def get_profitability_summary(address: str) -> dict:
    """Fetch 30-day realized PnL summary from Moralis."""
    url = f"{BASE_URL}/wallets/{address}/profitability/summary"
    try:
        r = requests.get(url, headers=HEADERS, params={"days": "30"}, timeout=12)
        if r.status_code == 200:
            return r.json()
        else:
            logger.warning(f"Failed to fetch profitability for {address}: HTTP {r.status_code}")
            return {}
    except Exception as e:
        logger.error(f"Error fetching profitability for {address}: {e}")
        return {}

def get_net_worth(address: str) -> float:
    """Fetch total wallet net worth in USD across major chains."""
    url = f"{BASE_URL}/wallets/{address}/net-worth"
    try:
        r = requests.get(
            url,
            headers=HEADERS,
            params={"chains[]": ["eth", "base", "bsc", "arbitrum", "polygon", "avalanche"]},
            timeout=12
        )
        if r.status_code == 200:
            return float(r.json().get("total_networth_usd", 0.0))
        return 0.0
    except Exception:
        return 0.0

def main():
    if not MORALIS_KEY:
        logger.error("MORALIS_API_KEY not found in environment. Please set it in .env")
        return

    unique_wallets = list(dict.fromkeys([w.lower() for w in WALLETS]))
    logger.info(f"Auditing {len(unique_wallets)} tracked wallets via Moralis API (30-day window)...")

    graded_wallets = []

    for idx, addr in enumerate(unique_wallets, 1):
        logger.info(f"[{idx}/{len(unique_wallets)}] Auditing {addr}...")
        data = get_profitability_summary(addr)
        
        # Moralis profitability response fields:
        # total_realized_profit_usd, total_win_rate, total_count_of_trades
        realized_pnl = float(data.get("total_realized_profit_usd", 0.0) or 0.0)
        win_rate = float(data.get("total_win_rate", 0.0) or 0.0)
        trade_count = int(data.get("total_count_of_trades", 0) or 0)
        net_worth = get_net_worth(addr)

        graded_wallets.append({
            "address": addr,
            "realized_pnl_usd": realized_pnl,
            "win_rate_pct": win_rate * 100.0,
            "trade_count": trade_count,
            "net_worth_usd": net_worth
        })

    # Sort by realized PnL descending (Drop the losers, focus on highest absolute return)
    graded_wallets.sort(key=lambda x: x["realized_pnl_usd"], reverse=True)

    # Isolate the top 3 "The Whales"
    top_whales = graded_wallets[:3]

    logger.info("=== WHALE AUTO-GRADER RESULTS (TOP 3) ===")
    for rank, whale in enumerate(top_whales, 1):
        logger.info(
            f"Whale #{rank}: {whale['address']} | "
            f"30d PnL: ${whale['realized_pnl_usd']:,.2f} | "
            f"Win Rate: {whale['win_rate_pct']:.1f}% | "
            f"Trades: {whale['trade_count']} | "
            f"Net Worth: ${whale['net_worth_usd']:,.2f}"
        )

    # Save to JSON file
    with open(OUTPUT_FILE, "w") as f:
        json.dump({
            "updated_at": datetime.now(timezone.utc).isoformat() if "datetime" in globals() else "2026-06-04T00:00:00Z",
            "whales": top_whales,
            "all_audited": graded_wallets
        }, f, indent=2)

    logger.info(f"Successfully saved top 3 whales to {OUTPUT_FILE}")

if __name__ == "__main__":
    from datetime import datetime, timezone
    main()
