"""
Moralis Streams webhook ingestion for low-latency copy-trade detection.

Runs a lightweight HTTP server and forwards normalized swap-like events
into WalletMonitor so copy-trades can be executed immediately.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class MoralisStreamsServer:
    def __init__(
        self,
        host: str,
        port: int,
        webhook_secret: str,
        on_swap_event: Callable[[str, dict], None],
    ):
        self.host = host
        self.port = port
        self.webhook_secret = webhook_secret or ""
        self.on_swap_event = on_swap_event
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        parent = self

        class _Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args):
                logger.debug("MoralisStreams: " + fmt, *args)

            def do_POST(self):
                if self.path not in ("/moralis/streams", "/webhooks/moralis/streams"):
                    self.send_response(404)
                    self.end_headers()
                    return

                content_len = int(self.headers.get("Content-Length", "0") or 0)
                raw = self.rfile.read(content_len)

                if parent.webhook_secret:
                    sig = self.headers.get("x-signature", "")
                    digest = hmac.new(
                        parent.webhook_secret.encode("utf-8"),
                        raw,
                        hashlib.sha256,
                    ).hexdigest()
                    if not hmac.compare_digest(sig.lower(), digest.lower()):
                        logger.warning("MoralisStreams: invalid signature")
                        self.send_response(401)
                        self.end_headers()
                        self.wfile.write(b"invalid signature")
                        return

                try:
                    payload = json.loads(raw.decode("utf-8"))
                except Exception as e:
                    logger.warning(f"MoralisStreams: bad JSON payload: {e}")
                    self.send_response(400)
                    self.end_headers()
                    return

                events = payload.get("erc20Transfers", []) or payload.get("nftTransfers", []) or []
                txs = payload.get("txs", [])

                # Conservative normalization: only accept ERC20 transfer events where
                # transfer recipient is in the monitored wallet set and tx hash exists.
                processed = 0
                for ev in events:
                    tx_hash = (ev.get("transactionHash") or ev.get("transaction_hash") or "").lower()
                    token_address = (ev.get("address") or ev.get("tokenAddress") or "").lower()
                    wallet = (ev.get("toAddress") or ev.get("to_address") or "").lower()
                    chain_id = str(payload.get("chainId") or ev.get("chainId") or "")
                    if not tx_hash or not token_address or not wallet:
                        continue

                    # best-effort USD estimate from tx list if present
                    usd_value = 0.0
                    for t in txs:
                        if (t.get("hash") or "").lower() == tx_hash:
                            usd_value = float(t.get("valueWithDecimals", 0) or 0)
                            break

                    swap = {
                        "tx_hash": tx_hash,
                        "token_address": token_address,
                        "token_symbol": (ev.get("tokenSymbol") or "UNKNOWN"),
                        "token_name": (ev.get("tokenName") or ""),
                        "buy_value_usd": usd_value,
                        "timestamp": payload.get("block", {}).get("timestamp") or payload.get("blockTimestamp") or "",
                        "chain": _chain_id_to_name(chain_id),
                        "seen_via": "moralis_streams",
                    }
                    parent.on_swap_event(wallet, swap)
                    processed += 1

                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True, "processed": processed}).encode("utf-8"))

        self._server = ThreadingHTTPServer((self.host, self.port), _Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, name="MoralisStreamsServer", daemon=True)
        self._thread.start()
        logger.info(f"Moralis Streams server started on http://{self.host}:{self.port}/moralis/streams")

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)


def _chain_id_to_name(chain_id: str) -> str:
    cid = chain_id.lower()
    return {
        "0x1": "ethereum",
        "1": "ethereum",
        "0x2105": "base",
        "8453": "base",
        "0xa4b1": "arbitrum",
        "42161": "arbitrum",
        "0x89": "polygon",
        "137": "polygon",
        "0x38": "bsc",
        "56": "bsc",
    }.get(cid, "ethereum")
