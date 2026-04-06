"""
scripts/check_wallet_swaps.py
Check ACTUAL recent DEX swap activity for alpha wallets using Moralis token swaps API.
"""
import os, requests
from dotenv import load_dotenv

load_dotenv()

MORALIS_KEY = os.getenv("MORALIS_API_KEY", "")
HEADERS = {"X-API-Key": MORALIS_KEY, "Accept": "application/json"}
BASE = "https://deep-index.moralis.io/api/v2.2"

# Only check the wallets with meaningful net worth (>$10K)
WALLETS = [
    ("0x8ab83d869f2bc250b781d26f6584fd5c562fdd9d", "$1.9M"),
    ("0x8acfbd922faeeccecf6a82492a48957d8fe9e5a0", "$1.2M"),
    ("0x18a83e1d022c9ccf8eef7444d03a0bf53fd88333", "$396K"),
    ("0xaebf847be3c8830ec7e125ef3b4b2ac58d468b81", "$95K"),
    ("0x21152db97be0aedb4e5c3878a39bc734250142a1", "$119K"),
    ("0xa56972fe0add34586c911114476827ac6a745f68", "$15K"),
]

def get_swaps(addr, chain="eth", limit=5):
    """Get recent DEX swaps for a wallet."""
    try:
        r = requests.get(
            f"{BASE}/wallets/{addr}/swaps",
            headers=HEADERS,
            params={"chain": chain, "limit": limit, "order": "DESC"},
            timeout=12,
        )
        if r.status_code != 200:
            return [], f"HTTP {r.status_code}: {r.text[:100]}"
        data = r.json()
        return data.get("result", []), None
    except Exception as e:
        return [], str(e)

def get_erc20_transfers(addr, chain="eth", limit=10):
    """Fallback: check ERC20 transfers to infer activity."""
    try:
        r = requests.get(
            f"{BASE}/{addr}/erc20/transfers",
            headers=HEADERS,
            params={"chain": chain, "limit": limit},
            timeout=12,
        )
        if r.status_code != 200:
            return [], f"HTTP {r.status_code}"
        return r.json().get("result", []), None
    except Exception as e:
        return [], str(e)

print(f"Checking recent DEX swap activity for top-wealth alpha wallets...\n")

for addr, net_worth in WALLETS:
    print(f"\n{'='*70}")
    print(f"Wallet: {addr}  (net worth: {net_worth})")

    # Try swaps on ETH and Base
    for chain in ["eth", "base"]:
        swaps, err = get_swaps(addr, chain=chain, limit=3)
        if err:
            print(f"  [{chain}] swaps error: {err}")
        elif swaps:
            print(f"  [{chain}] Last {len(swaps)} swaps:")
            for s in swaps:
                ts = s.get("block_timestamp", "")[:10]
                bought = s.get("bought", {})
                sold = s.get("sold", {})
                b_sym = bought.get("symbol", "?")
                b_usd = float(bought.get("usd_amount", 0) or 0)
                s_sym = sold.get("symbol", "?")
                s_usd = float(sold.get("usd_amount", 0) or 0)
                print(f"    {ts}  SOLD ${s_usd:>8.0f} {s_sym:<8} → BOUGHT ${b_usd:>8.0f} {b_sym}")
        else:
            # Fallback to ERC20 transfers
            transfers, err2 = get_erc20_transfers(addr, chain=chain, limit=5)
            if transfers:
                print(f"  [{chain}] No direct swaps found — last ERC20 transfers:")
                for t in transfers[:3]:
                    ts = t.get("block_timestamp", "")[:10]
                    sym = t.get("token_symbol", "?")
                    val = float(t.get("value_formatted", 0) or 0)
                    direction = "IN " if t.get("to_address", "").lower() == addr.lower() else "OUT"
                    print(f"    {ts}  {direction} {val:.4f} {sym}")
            else:
                print(f"  [{chain}] No activity found")
