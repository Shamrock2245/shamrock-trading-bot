"""
scripts/audit_alpha_wallets.py
Pulls Moralis profitability summaries for all ALPHA_WALLETS_EVM
to rank them by absolute PnL. Run locally with:
  python3 scripts/audit_alpha_wallets.py
"""
import os, requests
from dotenv import load_dotenv

load_dotenv()

MORALIS_KEY = os.getenv("MORALIS_API_KEY", "")
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

HEADERS = {"X-API-Key": MORALIS_KEY, "Accept": "application/json"}
BASE = "https://deep-index.moralis.io/api/v2.2"

def get_profitability(addr):
    """30-day profitability summary from Moralis."""
    try:
        r = requests.get(
            f"{BASE}/wallets/{addr}/profitability/summary",
            headers=HEADERS,
            params={"days": "30"},
            timeout=12,
        )
        if r.status_code != 200:
            return None, f"HTTP {r.status_code}"
        d = r.json()
        return d, None
    except Exception as e:
        return None, str(e)

def get_net_worth(addr):
    """Get total wallet net worth USD."""
    try:
        r = requests.get(
            f"{BASE}/wallets/{addr}/net-worth",
            headers=HEADERS,
            params={"chains[]": ["eth", "base", "bsc", "arbitrum", "polygon", "avalanche"]},
            timeout=12,
        )
        if r.status_code != 200:
            return 0.0
        return float(r.json().get("total_networth_usd", 0))
    except Exception:
        return 0.0

if not MORALIS_KEY:
    print("ERROR: MORALIS_API_KEY not set in .env")
    exit(1)

print(f"Auditing {len(WALLETS)} alpha wallets via Moralis...\n")
print(f"{'Rank':<5} {'Address':<44} {'30d PnL':>12} {'Win%':>7} {'Trades':>7} {'Net Worth':>12}")
print("-" * 95)

results = []
for addr in WALLETS:
    data, err = get_profitability(addr)
    if err or not data:
        results.append((addr, 0, 0, 0, 0, f"ERR: {err}"))
        continue
    pnl = float(data.get("total_realized_profit_usd", 0) or 0)
    winrate = float(data.get("total_win_rate", 0) or 0) * 100
    trades = int(data.get("total_count_of_trades", 0) or 0)
    net = get_net_worth(addr)
    results.append((addr, pnl, winrate, trades, net, None))

# Sort by 30d PnL descending
results.sort(key=lambda x: x[1], reverse=True)

for i, (addr, pnl, wr, trades, net, err) in enumerate(results, 1):
    if err:
        print(f"{i:<5} {addr:<44} {'ERROR':>12}  {err}")
    else:
        pnl_str = f"+${pnl:,.0f}" if pnl >= 0 else f"-${abs(pnl):,.0f}"
        print(f"{i:<5} {addr:<44} {pnl_str:>12} {wr:>6.1f}% {trades:>7} ${net:>11,.0f}")

print()
print("Top 3 wallets to weight HIGHEST in copy-trade stream:")
for i, (addr, pnl, wr, trades, net, err) in enumerate(results[:3], 1):
    if not err:
        print(f"  #{i}: {addr}  |  30d PnL: ${pnl:,.0f}  |  Win%: {wr:.1f}%  |  Trades: {trades}")
