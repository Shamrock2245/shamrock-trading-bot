import requests, socket, base64, time, uuid, json
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

# Force IPv4 on all connections
import urllib3.util.connection as uconn
def _ipv4_create(address, *args, **kwargs):
    host, port = address
    for (af, stype, proto, cn, sa) in socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM):
        s = socket.socket(af, stype, proto)
        s.connect(sa)
        return s
uconn.create_connection = _ipv4_create

API_KEY  = "gmgn_f6acad3ff43f1992a4ca2cd5bdb05912"
PRIV_B64 = "k5f8Yn8YPMJsVtrQ9bWM7gqT/g1oGGJuL0zRTu7YY/s="
BASE     = "https://openapi.gmgn.ai"
raw      = base64.b64decode(PRIV_B64)
priv     = Ed25519PrivateKey.from_private_bytes(raw)

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0 Chrome/123.0", "Accept": "application/json"})

def signed_get(path, params={}):
    ts  = str(int(time.time()))
    cid = str(uuid.uuid4())
    p   = dict(params, timestamp=ts, client_id=cid)
    qs  = "&".join(f"{k}={v}" for k, v in sorted(p.items()))
    sig = base64.b64encode(priv.sign(f"{path}:{qs}::{ts}".encode())).decode()
    session.headers.update({"X-APIKEY": API_KEY, "X-Signature": sig})
    r = session.get(f"{BASE}{path}", params=p, timeout=20)
    return r.status_code, r.json()

# Current alpha wallets to audit
wallets = [
    ("AVAZvHLR2PcWpDf8BXY4rVxNHYRBytycHkcB5z5QNXYm", "Wallet-1"),
    ("4Be9CvxqHW6BYiRAxW9Q3xu1ycTMWaL5z8NX4HR3ha7t", "Wallet-2"),
    ("B6J251t6KbZhh7R6GhHJdwKQGj22dcck83AULtxNPSat", "Wallet-3"),
    ("AMRsSeU5JpqwQWJGNLMpZzRCZSFEwYQYbMnms3dD4311", "Wallet-4"),
]

print("=" * 70)
print("GMGN SMART MONEY WALLET AUDIT -- LIVE DATA")
print("=" * 70)

results = []

for addr, label in wallets:
    print(f"\n{'-'*60}")
    print(f"  {label}: {addr}")

    wallet_result = {
        "label": label,
        "address": addr,
        "total_realized_pnl": 0,
        "win_rate": 0,
        "wins": 0,
        "total_holdings": 0,
        "recent_buys": 0,
        "recent_sells": 0,
        "top_tokens": [],
        "pass": False,
    }

    # Holdings
    code, data = signed_get("/v1/user/wallet_holdings", {
        "chain": "sol", "wallet_address": addr,
        "order_by": "realized_profit", "direction": "desc",
        "limit": "20", "hide_airdrop": "true", "hide_abnormal": "true"
    })
    if data.get("code") == 0:
        items = data["data"].get("list", [])
        total_realized = sum(float(x.get("realized_profit") or 0) for x in items)
        wins = sum(1 for x in items if float(x.get("realized_profit") or 0) > 0)
        win_rate = (wins / len(items) * 100) if items else 0
        wallet_result["total_realized_pnl"] = total_realized
        wallet_result["win_rate"]           = win_rate
        wallet_result["wins"]               = wins
        wallet_result["total_holdings"]     = len(items)
        print(f"  Holdings (top 20) | Realized PnL: ${total_realized:,.0f} | Win rate: {win_rate:.0f}% ({wins}/{len(items)})")
        for x in items[:5]:
            sym  = x.get("token", {}).get("symbol", "?") if isinstance(x.get("token"), dict) else "?"
            pnl  = float(x.get("realized_profit") or 0)
            pnlp = float(x.get("realized_profit_pnl") or 0) * 100
            buys = x.get("history_total_buys", 0)
            sells= x.get("history_total_sells", 0)
            print(f"    {sym:<14} PnL=${pnl:>12,.0f}  ({pnlp:+.0f}%)  buys={buys} sells={sells}")
            wallet_result["top_tokens"].append({"sym": sym, "pnl": pnl, "pct": pnlp})
    else:
        print(f"  Holdings ERR: {data.get('error')} -- {data.get('message', '')}")

    time.sleep(0.4)

    # Activity
    code, data = signed_get("/v1/user/wallet_activity", {
        "chain": "sol", "wallet_address": addr,
        "limit": "30"
    })
    if data.get("code") == 0:
        acts  = data["data"].get("activities", [])
        buys  = [a for a in acts if a.get("type") == "buy"]
        sells = [a for a in acts if a.get("type") == "sell"]
        wallet_result["recent_buys"]  = len(buys)
        wallet_result["recent_sells"] = len(sells)
        print(f"  Activity (last 30) | Buys: {len(buys)} | Sells: {len(sells)}")
        for a in buys[:3]:
            sym  = a.get("token", {}).get("symbol", "?") if isinstance(a.get("token"), dict) else "?"
            amt  = float(a.get("cost_usd") or a.get("amount_usd") or 0)
            print(f"    BUY  {sym:<12}  ~${amt:,.0f}")
    else:
        print(f"  Activity ERR: {data.get('error')} -- {data.get('message', '')}")

    # PASS guardrails: >$10k realized PnL AND >50% win rate
    wallet_result["pass"] = (
        wallet_result["total_realized_pnl"] > 10_000 and
        wallet_result["win_rate"] > 50
    )
    status = "PASS" if wallet_result["pass"] else "FAIL"
    print(f"\n  --> VERDICT: {status}")
    results.append(wallet_result)
    time.sleep(0.4)

print("\n" + "=" * 70)
print("AUDIT SUMMARY")
print("=" * 70)
passing = [r for r in results if r["pass"]]
failing = [r for r in results if not r["pass"]]
print(f"PASSING wallets ({len(passing)}/4): {[r['label'] for r in passing]}")
print(f"FAILING wallets ({len(failing)}/4): {[r['label'] for r in failing]}")
for r in results:
    status = "PASS" if r["pass"] else "FAIL"
    print(f"  {r['label']}: PnL=${r['total_realized_pnl']:,.0f}  WinRate={r['win_rate']:.0f}%  Buys={r['recent_buys']}  [{status}]")
print("=" * 70)
