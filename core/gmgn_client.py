"""
GMGN.ai API Client — Solana Smart Money Intelligence
=====================================================
Auth: Ed25519 asymmetric signing per GMGN OpenAPI spec.
  message = "{sub_path}:{sorted_query_string}:{body}:{timestamp}"
  X-Signature: base64(Ed25519Sign(privateKey, message))
  X-APIKEY: <api_key>

Scope: Read-only wallet intelligence (no trading execution).
  - /v1/user/wallet_holdings   — token PnL per wallet
  - /v1/user/wallet_activity   — recent buy/sell trades
  - /v1/user/info              — bound wallet balances
"""

import base64
import logging
import os
import socket
import threading
import time
import uuid

from data.http_session import get_session
import urllib3.util.connection as _uconn
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption

logger = logging.getLogger(__name__)

# ── Correct API gateway (not gmgn.ai frontend) ──────────────────────────────
GMGN_BASE_URL = "https://openapi.gmgn.ai"

# ── Force IPv4 globally — GMGN API rejects IPv6 connections ─────────────────
# The Hetzner VPS resolves openapi.gmgn.ai to an IPv6 address by default,
# but GMGN's Cloudflare-fronted API returns 403 "does not support IPv6".
# Monkey-patch urllib3 to always prefer AF_INET.
_orig_create_connection = _uconn.create_connection


def _ipv4_only_create_connection(address, *args, **kwargs):
    host, port = address
    try:
        infos = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)
        for (af, stype, proto, _cn, sa) in infos:
            sock = socket.socket(af, stype, proto)
            sock.connect(sa)
            return sock
    except socket.gaierror:
        pass
    # Fallback to original if IPv4 unavailable
    return _orig_create_connection(address, *args, **kwargs)


_uconn.create_connection = _ipv4_only_create_connection


class GMGNClient:
    """Authenticated GMGN.ai API client for Solana wallet intelligence."""

    def __init__(self):
        api_key = os.getenv("GMGN_API_KEY", "")
        private_key_b64 = os.getenv("GMGN_PRIVATE_KEY", "")
        self.client_id = os.getenv("GMGN_CLIENT_ID", "shamrock-trading-bot")

        if not api_key or not private_key_b64:
            raise ValueError("GMGN_API_KEY and GMGN_PRIVATE_KEY must be set in .env")

        self.api_key = api_key

        # Load Ed25519 private key from raw base64 bytes
        raw_bytes = base64.b64decode(private_key_b64)
        self._private_key = Ed25519PrivateKey.from_private_bytes(raw_bytes)
        logger.info("✅ GMGN client initialized with Ed25519 key pair")

    def _sign(self, sub_path: str, query_params: dict, body: str = "") -> tuple[dict, dict]:
        """
        Build auth headers + signed query params per GMGN spec.

        message = "{sub_path}:{sorted_query_string}:{body}:{timestamp}"
        """
        timestamp = str(int(time.time()))  # Unix seconds (GMGN validates epoch)
        # Use registered client_id + unique suffix to satisfy both
        # GMGN's client registration check AND replay-prevention nonce.
        client_id = f"{self.client_id}_{uuid.uuid4().hex[:8]}"

        # Merge auth params into query
        all_params = dict(query_params)
        all_params["timestamp"] = timestamp
        all_params["client_id"] = client_id

        # Sorted query string (alphabetical by key)
        sorted_qs = "&".join(f"{k}={v}" for k, v in sorted(all_params.items()))

        # Build message
        message = f"{sub_path}:{sorted_qs}:{body}:{timestamp}"

        # Sign with Ed25519
        signature_bytes = self._private_key.sign(message.encode("utf-8"))
        signature_b64 = base64.b64encode(signature_bytes).decode("utf-8")

        headers = {
            "X-APIKEY": self.api_key,
            "X-Signature": signature_b64,
            "Content-Type": "application/json",
        }

        return headers, all_params

    def _get(self, path: str, params: dict = None) -> dict:
        """Execute a signed GET request."""
        params = params or {}
        headers, signed_params = self._sign(path, params)

        url = f"{GMGN_BASE_URL}{path}"
        resp = get_session().get(url, headers=headers, params=signed_params, timeout=15)

        if resp.status_code != 200:
            logger.error(f"GMGN API error {resp.status_code}: {resp.text[:300]}")
            resp.raise_for_status()

        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"GMGN API returned error: {data}")

        return data.get("data", {})

    # ─── High-Level Methods ───────────────────────────────────────────────────

    def get_wallet_holdings(self, wallet_address: str, chain: str = "sol",
                            order_by: str = "realized_profit",
                            hide_closed: bool = False, limit: int = 50) -> list:
        """
        Get all token holdings + PnL for a wallet.
        Returns list of WalletHoldingItem dicts sorted by realized_profit desc.
        """
        path = "/v1/user/wallet_holdings"
        params = {
            "chain": chain,
            "wallet_address": wallet_address,
            "order_by": order_by,
            "direction": "desc",
            "limit": str(limit),
            "hide_closed": "true" if hide_closed else "false",
            "hide_airdrop": "true",
            "hide_abnormal": "false",
        }
        data = self._get(path, params)
        return data.get("list", [])

    def get_wallet_activity(self, wallet_address: str, chain: str = "sol",
                            limit: int = 20, activity_type: str = None) -> list:
        """
        Get recent buy/sell activity for a wallet.
        activity_type: None (all), 'buy', or 'sell'
        """
        path = "/v1/user/wallet_activity"
        params = {
            "chain": chain,
            "wallet_address": wallet_address,
            "limit": str(limit),
        }
        if activity_type:
            params["type"] = activity_type
        data = self._get(path, params)
        return data.get("activities", [])

    def get_user_info(self) -> dict:
        """Get bound wallets and balances for the current API key."""
        path = "/v1/user/info"
        return self._get(path, {})

    def audit_wallet(self, wallet_address: str, chain: str = "sol") -> dict:
        """
        Full audit of a wallet: PnL summary + recent activity.
        Returns structured audit dict ready for decision-making.
        """
        logger.info(f"🔍 Auditing {wallet_address[:8]}... on {chain.upper()}")

        try:
            holdings = self.get_wallet_holdings(wallet_address, chain, hide_closed=False, limit=100)
        except Exception as e:
            logger.warning(f"Holdings fetch failed for {wallet_address[:8]}: {e}")
            holdings = []

        try:
            activity = self.get_wallet_activity(wallet_address, chain, limit=30)
        except Exception as e:
            logger.warning(f"Activity fetch failed for {wallet_address[:8]}: {e}")
            activity = []

        # Compute aggregate PnL
        total_realized = sum(float(h.get("realized_profit") or 0) for h in holdings)
        total_unrealized = sum(float(h.get("unrealized_profit") or 0) for h in holdings)
        total_trades = sum(
            int(h.get("history_total_buys") or 0) + int(h.get("history_total_sells") or 0)
            for h in holdings
        )
        profitable_positions = sum(1 for h in holdings if float(h.get("realized_profit") or 0) > 0)
        total_positions = len([h for h in holdings if int(h.get("history_total_buys") or 0) > 0])
        win_rate = (profitable_positions / total_positions * 100) if total_positions > 0 else 0

        # Top winners
        top_winners = sorted(
            [h for h in holdings if float(h.get("realized_profit") or 0) > 0],
            key=lambda x: float(x.get("realized_profit") or 0),
            reverse=True
        )[:5]

        # Recent activity summary
        recent_buys = [a for a in activity if a.get("type") == "buy"]
        last_active = max(
            (a.get("timestamp") for a in activity if a.get("timestamp")),
            default=None
        )

        return {
            "address": wallet_address,
            "chain": chain,
            "total_realized_pnl_usd": round(total_realized, 2),
            "total_unrealized_pnl_usd": round(total_unrealized, 2),
            "total_pnl_usd": round(total_realized + total_unrealized, 2),
            "win_rate_pct": round(win_rate, 1),
            "total_positions": total_positions,
            "profitable_positions": profitable_positions,
            "total_trades": total_trades,
            "recent_buy_count": len(recent_buys),
            "last_active_ts": last_active,
            "top_winners": [
                {
                    "symbol": h.get("token", {}).get("symbol", "?"),
                    "realized_profit": round(float(h.get("realized_profit") or 0), 2),
                    "pnl_pct": round(float(h.get("realized_profit_pnl") or 0) * 100, 1),
                }
                for h in top_winners
            ],
            "holdings_count": len(holdings),
        }


# ── Module-level singleton ──────────────────────────────────────────────────────────────────────
# Each GMGNClient instantiation loads the Ed25519 private key from env and
# performs base64 decoding. With 5+ call sites (alpha_wallet_discovery,
# sniper_discovery, wallet_monitor, dashboard) this was creating a new key
# object on every function call. The singleton pattern ensures one instance
# per process lifetime, saving ~3ms per call and preventing key-material churn.
_gmgn_singleton: "GMGNClient | None" = None
_gmgn_singleton_lock = threading.Lock()


def get_gmgn_client() -> "GMGNClient":
    """
    Return the process-wide GMGNClient singleton.
    Thread-safe via double-checked locking.
    Raises ValueError if GMGN_API_KEY / GMGN_PRIVATE_KEY are not set.
    """
    global _gmgn_singleton
    if _gmgn_singleton is None:
        with _gmgn_singleton_lock:
            if _gmgn_singleton is None:  # double-checked locking
                _gmgn_singleton = GMGNClient()
    return _gmgn_singleton


def run_solana_audit():
    """
    Audit all Solana alpha wallets configured in .env.
    Prints a ranked summary table and flags any underperformers.
    """
    from dotenv import load_dotenv

    load_dotenv()

    wallets_raw = os.getenv("ALPHA_WALLETS_SOLANA", "")
    wallets = [w.strip() for w in wallets_raw.split(",") if w.strip()]

    if not wallets:
        print("❌ No ALPHA_WALLETS_SOLANA found in .env")
        return

    print(f"\n{'='*70}")
    print(f"  GMGN.ai SOLANA WALLET AUDIT — {len(wallets)} wallets")
    print(f"{'='*70}\n")

    try:
        client = GMGNClient()
    except Exception as e:
        print(f"❌ GMGN client init failed: {e}")
        return

    results = []
    for addr in wallets:
        result = client.audit_wallet(addr, chain="sol")
        results.append(result)

        pnl = result["total_realized_pnl_usd"]
        wr = result["win_rate_pct"]
        trades = result["total_trades"]
        flag = "🔴 REVIEW" if (pnl < 10_000 or wr < 50) else "✅ KEEP"

        print(f"  Wallet: {addr[:12]}...")
        print(f"    Realized PnL : ${pnl:>12,.2f}")
        print(f"    Win Rate     : {wr:>6.1f}%")
        print(f"    Total Trades : {trades:>6}")
        print(f"    Last Active  : {result['last_active_ts']}")
        print(f"    Status       : {flag}")
        if result["top_winners"]:
            print(f"    Top Winner   : {result['top_winners'][0]['symbol']} +${result['top_winners'][0]['realized_profit']:,.0f}")
        print()

    # Rank by realized PnL
    ranked = sorted(results, key=lambda x: x["total_realized_pnl_usd"], reverse=True)
    print(f"\n{'─'*70}")
    print("  📊 RANKED BY REALIZED PnL:")
    for i, r in enumerate(ranked, 1):
        print(f"  #{i}  {r['address'][:16]}...  ${r['total_realized_pnl_usd']:>12,.0f}  WR:{r['win_rate_pct']}%")

    # Flag underperformers  
    duds = [r for r in results if r["total_realized_pnl_usd"] < 10_000 or r["win_rate_pct"] < 50]
    if duds:
        print(f"\n  ⚠️  {len(duds)} wallet(s) below threshold — recommend replacement:")
        for d in duds:
            print(f"    ✗ {d['address']}")
    else:
        print(f"\n  ✅ All {len(wallets)} wallets pass minimum thresholds")

    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    run_solana_audit()
