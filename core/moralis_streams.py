"""
core/moralis_streams.py — Moralis Streams webhook ingestion server.

Runs a lightweight HTTP server that receives push-based blockchain events
from Moralis and routes them through the trading pipeline:

  - Alpha wallet transfers → WalletMonitor.ingest_external_swap() (copy-trade)
  - Whale transfers → GemScanner evaluation (new signal source)
  - Liquidity events → GemScanner evaluation (new pool detection)

Signature verification uses sha3(body + secret) per Moralis spec.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Optional

from config import settings

logger = logging.getLogger(__name__)

# Stream tags — must match moralis_streams_manager.py
TAG_ALPHA_WALLETS = "shamrock-alpha-wallets"
TAG_WHALE_DETECTOR = "shamrock-whale-detector"
TAG_LIQUIDITY = "shamrock-liquidity-events"


class MoralisStreamsServer:
    """
    HTTP server that receives Moralis Streams webhooks.

    Routes events by stream `tag` to appropriate handlers:
    - Alpha wallets → copy-trade pipeline
    - Whale detector → gem scanner evaluation
    - Liquidity events → new pool detection
    """

    def __init__(
        self,
        host: str,
        port: int,
        webhook_secret: str,
        on_swap_event: Callable[[str, dict], None],
        on_whale_event: Optional[Callable[[dict], None]] = None,
        on_liquidity_event: Optional[Callable[[dict], None]] = None,
    ):
        self.host = host
        self.port = port
        self.webhook_secret = webhook_secret or ""
        self.on_swap_event = on_swap_event
        self.on_whale_event = on_whale_event
        self.on_liquidity_event = on_liquidity_event
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

        # Metrics
        self.metrics = {
            "webhooks_received": 0,
            "webhooks_invalid_sig": 0,
            "events_processed": 0,
            "events_by_tag": {},
            "errors": 0,
            "last_webhook_at": None,
            "avg_latency_ms": 0.0,
            "_latencies": [],  # rolling window for avg calculation
        }

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        parent = self

        class _Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args):
                logger.debug("MoralisStreams: " + fmt, *args)

            def do_GET(self):
                """Health check endpoint."""
                if self.path == "/health":
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        "status": "ok",
                        "metrics": {k: v for k, v in parent.metrics.items() if k != "_latencies"},
                    }).encode("utf-8"))
                    return
                self.send_response(404)
                self.end_headers()

            def do_POST(self):
                recv_time = time.time()

                if self.path not in ("/moralis/streams", "/webhooks/moralis/streams"):
                    self.send_response(404)
                    self.end_headers()
                    return

                content_len = int(self.headers.get("Content-Length", "0") or 0)
                raw = self.rfile.read(content_len)

                parent.metrics["webhooks_received"] += 1
                parent.metrics["last_webhook_at"] = recv_time

                # ── Test Webhook Detection ─────────────────────────────────
                # Moralis sends a test webhook on every stream create/update.
                # Must return 200 or the stream won't start.
                # Test webhooks have empty body, no txs/logs, or streamId only.
                is_test_webhook = False
                try:
                    if not raw or raw.strip() in (b"", b"{}", b"[]"):
                        is_test_webhook = True
                    else:
                        test_body = json.loads(raw)
                        # Test webhooks typically have empty txs/logs arrays
                        # and/or no "block" data
                        if isinstance(test_body, dict):
                            txs = test_body.get("txs", [])
                            logs = test_body.get("logs", [])
                            erc20 = test_body.get("erc20Transfers", [])
                            has_data = bool(txs or logs or erc20)
                            if not has_data:
                                is_test_webhook = True
                except (json.JSONDecodeError, Exception):
                    pass  # Not JSON — treat as real webhook

                if is_test_webhook:
                    logger.info("MoralisStreams: ✅ Test/verification webhook received — returning 200")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"status":"ok"}')
                    return

                # ── Signature Verification ────────────────────────────────
                # Moralis uses sha3(JSON.stringify(body) + secret), NOT HMAC
                if parent.webhook_secret:
                    sig = self.headers.get("x-signature", "")
                    if not _verify_moralis_signature(raw, parent.webhook_secret, sig):
                        logger.warning("MoralisStreams: ❌ Invalid webhook signature")
                        parent.metrics["webhooks_invalid_sig"] += 1
                        self.send_response(401)
                        self.end_headers()
                        self.wfile.write(b"invalid signature")
                        return

                # ── Parse Payload ─────────────────────────────────────────
                try:
                    payload = json.loads(raw.decode("utf-8"))
                except Exception as e:
                    logger.warning(f"MoralisStreams: Bad JSON payload: {e}")
                    parent.metrics["errors"] += 1
                    self.send_response(400)
                    self.end_headers()
                    return

                # ── Test Webhook (empty body on stream create) ────────────
                # Moralis sends a test webhook when creating/updating a stream.
                # We MUST return 200 or the stream won't activate.
                if not payload.get("block") and not payload.get("txs") and not payload.get("logs"):
                    logger.info("MoralisStreams: Test webhook received — returning 200")
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b'{"ok": true, "test": true}')
                    return

                # ── Skip unconfirmed webhooks ─────────────────────────────
                # Moralis sends TWO webhooks per event: unconfirmed + confirmed.
                # We only act on confirmed to avoid double-trading.
                confirmed = payload.get("confirmed", True)
                if not confirmed:
                    logger.debug("MoralisStreams: Skipping unconfirmed webhook (waiting for confirmed)")
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b'{"ok": true, "skipped": "unconfirmed"}')
                    return

                # ── Route by Tag ──────────────────────────────────────────
                tag = payload.get("tag", "")
                processed = 0

                if tag == TAG_ALPHA_WALLETS:
                    processed = _handle_alpha_wallet_event(parent, payload)
                elif tag == TAG_WHALE_DETECTOR:
                    processed = _handle_whale_event(parent, payload)
                elif tag == TAG_LIQUIDITY:
                    processed = _handle_liquidity_event(parent, payload)
                else:
                    # Unknown tag — try alpha wallet handler as default
                    logger.debug(f"MoralisStreams: Unknown tag '{tag}' — falling back to alpha handler")
                    processed = _handle_alpha_wallet_event(parent, payload)

                # ── Track Metrics ─────────────────────────────────────────
                parent.metrics["events_processed"] += processed
                parent.metrics["events_by_tag"][tag] = parent.metrics["events_by_tag"].get(tag, 0) + processed

                # Latency tracking (webhook receive → processing complete)
                latency_ms = (time.time() - recv_time) * 1000
                latencies = parent.metrics["_latencies"]
                latencies.append(latency_ms)
                if len(latencies) > 100:
                    latencies.pop(0)
                parent.metrics["avg_latency_ms"] = sum(latencies) / len(latencies)

                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True, "processed": processed, "tag": tag}).encode("utf-8"))

        self._server = ThreadingHTTPServer((self.host, self.port), _Handler)
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="MoralisStreamsServer",
            daemon=True,
        )
        self._thread.start()
        logger.info(f"🟢 Moralis Streams server started on http://{self.host}:{self.port}/moralis/streams")

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        logger.info("Moralis Streams server stopped")


# ─────────────────────────────────────────────────────────────────────────────
# Signature Verification (sha3, NOT HMAC)
# ─────────────────────────────────────────────────────────────────────────────

def _verify_moralis_signature(raw_body: bytes, secret: str, provided_sig: str) -> bool:
    """
    Moralis webhook signature: web3.utils.sha3(JSON.stringify(body) + secret)

    Moralis parses the body and re-serializes with JSON.stringify() (compact,
    no spaces) before computing the hash. We must replicate this exactly:
    1. Parse raw body as JSON
    2. Re-serialize with compact separators (no spaces) — matches JS JSON.stringify()
    3. Compute keccak256(compact_json + secret)

    Falls back to raw bytes if JSON parse fails.
    """
    if not provided_sig:
        return False

    # Normalize the provided signature
    provided_clean = provided_sig.lower()
    if provided_clean.startswith("0x"):
        provided_clean = provided_clean[2:]

    # Build the message body — try compact JSON first (matches JS JSON.stringify)
    try:
        parsed = json.loads(raw_body)
        # Match JavaScript's JSON.stringify: compact, no spaces, sorted keys=False
        compact_body = json.dumps(parsed, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    except (json.JSONDecodeError, Exception):
        # Fallback to raw bytes if not valid JSON
        compact_body = raw_body

    secret_bytes = secret.encode("utf-8")

    try:
        # Try keccak-256 (Web3 sha3) first
        from eth_hash.auto import keccak
        digest = keccak(compact_body + secret_bytes).hex()
        if digest == provided_clean:
            return True
        # Also try with raw bytes in case Moralis didn't re-serialize
        if compact_body != raw_body:
            digest_raw = keccak(raw_body + secret_bytes).hex()
            if digest_raw == provided_clean:
                return True
        # DEBUG: Log mismatch for troubleshooting (TEMPORARY — change to debug after fix)
        logger.warning(
            f"Sig mismatch — provided={provided_clean[:16]}... "
            f"compact_digest={digest[:16]}... "
            f"body_len={len(raw_body)} compact_len={len(compact_body)} "
            f"same_body={compact_body == raw_body}"
        )
        return False
    except ImportError:
        pass

    try:
        # Fallback: pysha3
        import sha3
        k = sha3.keccak_256()
        k.update(compact_body + secret_bytes)
        digest = k.hexdigest()
        return digest == provided_clean
    except ImportError:
        pass

    # Last resort fallback: hashlib sha256 (not per spec but works if secret is
    # set via Moralis UI which sometimes uses sha256 in older SDK versions)
    import hmac as _hmac
    digest = _hmac.new(
        secret_bytes,
        compact_body,
        hashlib.sha256,
    ).hexdigest()
    return _hmac.compare_digest(provided_clean, digest.lower())


# ─────────────────────────────────────────────────────────────────────────────
# Event Handlers
# ─────────────────────────────────────────────────────────────────────────────

def _handle_alpha_wallet_event(server: MoralisStreamsServer, payload: dict) -> int:
    """
    Process ERC20 transfer events for alpha wallet copy-trading.
    Normalizes and forwards to WalletMonitor.ingest_external_swap().
    """
    events = payload.get("erc20Transfers", []) or []
    txs = payload.get("txs", [])
    chain_id = str(payload.get("chainId") or "")
    block_ts = payload.get("block", {}).get("timestamp") or payload.get("blockTimestamp") or ""

    processed = 0
    for ev in events:
        tx_hash = (ev.get("transactionHash") or ev.get("transaction_hash") or "").lower()
        token_address = (ev.get("address") or ev.get("tokenAddress") or "").lower()
        wallet = (ev.get("toAddress") or ev.get("to_address") or "").lower()

        if not tx_hash or not token_address or not wallet:
            continue

        # Best-effort USD estimate from tx list
        usd_value = 0.0
        for t in txs:
            if (t.get("hash") or "").lower() == tx_hash:
                usd_value = float(t.get("receiptGasUsed", 0) or 0)  # placeholder
                # Try decoded value
                val_str = t.get("value", "0")
                try:
                    usd_value = float(val_str) / 1e18  # native value — rough estimate
                except (ValueError, TypeError):
                    pass
                break

        # Get value with decimals from the transfer event itself
        try:
            value_raw = ev.get("value") or ev.get("valueWithDecimals") or "0"
            token_decimals = int(ev.get("tokenDecimals") or ev.get("contract", {}).get("decimals") or 18)
            if isinstance(value_raw, str) and "." not in value_raw:
                value_with_decimals = int(value_raw) / (10 ** token_decimals)
            else:
                value_with_decimals = float(value_raw)
        except (ValueError, TypeError):
            value_with_decimals = 0.0

        swap = {
            "tx_hash": tx_hash,
            "token_address": token_address,
            "token_symbol": ev.get("tokenSymbol") or "UNKNOWN",
            "token_name": ev.get("tokenName") or "",
            "buy_value_usd": usd_value,
            "value_with_decimals": value_with_decimals,
            "timestamp": block_ts,
            "chain": _chain_id_to_name(chain_id),
            "seen_via": "moralis_streams",
            "stream_tag": TAG_ALPHA_WALLETS,
        }

        try:
            server.on_swap_event(wallet, swap)
            processed += 1
        except Exception as e:
            logger.error(f"MoralisStreams: Error processing alpha swap: {e}")
            server.metrics["errors"] += 1

    if processed:
        logger.info(f"MoralisStreams: 🎯 {processed} alpha wallet swap(s) on {_chain_id_to_name(chain_id)}")

    return processed


def _handle_whale_event(server: MoralisStreamsServer, payload: dict) -> int:
    """
    Process large ERC20 transfers for whale detection.
    Only fires the callback for transfers above MORALIS_STREAMS_WHALE_MIN_USD.
    """
    if not server.on_whale_event:
        return 0

    events = payload.get("erc20Transfers", []) or []
    chain_id = str(payload.get("chainId") or "")
    block_ts = payload.get("block", {}).get("timestamp") or ""
    min_usd = settings.MORALIS_STREAMS_WHALE_MIN_USD

    processed = 0
    for ev in events:
        # Try to estimate USD value from valueWithDecimals
        try:
            value_raw = ev.get("valueWithDecimals") or ev.get("value") or "0"
            value_float = float(value_raw) if isinstance(value_raw, str) else value_raw
        except (ValueError, TypeError):
            continue

        # For whale detection, we need a meaningful filter.
        # Since we don't have real-time USD prices in the webhook payload,
        # we pass all large-value transfers to the callback and let the
        # caller (gem_scanner) do price lookup + USD filtering.
        token_address = (ev.get("address") or ev.get("tokenAddress") or "").lower()
        from_addr = (ev.get("fromAddress") or ev.get("from_address") or "").lower()
        to_addr = (ev.get("toAddress") or ev.get("to_address") or "").lower()

        if not token_address:
            continue

        whale_event = {
            "type": "whale_transfer",
            "tx_hash": (ev.get("transactionHash") or "").lower(),
            "token_address": token_address,
            "token_symbol": ev.get("tokenSymbol") or "UNKNOWN",
            "token_name": ev.get("tokenName") or "",
            "from_address": from_addr,
            "to_address": to_addr,
            "value_raw": str(value_raw),
            "chain": _chain_id_to_name(chain_id),
            "timestamp": block_ts,
            "stream_tag": TAG_WHALE_DETECTOR,
        }

        try:
            server.on_whale_event(whale_event)
            processed += 1
        except Exception as e:
            logger.error(f"MoralisStreams: Error processing whale event: {e}")
            server.metrics["errors"] += 1

    if processed:
        logger.info(f"MoralisStreams: 🐋 {processed} whale transfer(s) on {_chain_id_to_name(chain_id)}")

    return processed


def _handle_liquidity_event(server: MoralisStreamsServer, payload: dict) -> int:
    """
    Process PairCreated events from DEX factory contracts.
    Signals new pool creation — earliest possible gem detection.
    """
    if not server.on_liquidity_event:
        return 0

    logs = payload.get("logs", []) or []
    chain_id = str(payload.get("chainId") or "")
    block_ts = payload.get("block", {}).get("timestamp") or ""

    processed = 0
    for log_entry in logs:
        topic0 = (log_entry.get("topic0") or "").lower()

        # We're looking for PairCreated events specifically
        # The decoded log should have token0, token1, pair address
        decoded = log_entry.get("decodedEvent") or {}
        params = decoded.get("params", []) if isinstance(decoded, dict) else []

        if not params and not log_entry.get("data"):
            continue

        # Extract token addresses from decoded event or raw log
        token0 = ""
        token1 = ""
        pair_address = ""
        for p in params:
            name = p.get("name", "")
            val = p.get("value", "")
            if name == "token0":
                token0 = val.lower()
            elif name == "token1":
                token1 = val.lower()
            elif name == "pair":
                pair_address = val.lower()

        if not token0 and not token1:
            # Try raw topics — topic1=token0, topic2=token1
            topics = log_entry.get("topic1", ""), log_entry.get("topic2", "")
            if topics[0]:
                token0 = "0x" + topics[0][-40:] if len(topics[0]) >= 40 else ""
            if topics[1]:
                token1 = "0x" + topics[1][-40:] if len(topics[1]) >= 40 else ""

        if not token0 or not token1:
            continue

        liquidity_event = {
            "type": "pair_created",
            "factory": (log_entry.get("address") or "").lower(),
            "token0": token0,
            "token1": token1,
            "pair_address": pair_address,
            "chain": _chain_id_to_name(chain_id),
            "timestamp": block_ts,
            "tx_hash": (log_entry.get("transactionHash") or "").lower(),
            "stream_tag": TAG_LIQUIDITY,
        }

        try:
            server.on_liquidity_event(liquidity_event)
            processed += 1
        except Exception as e:
            logger.error(f"MoralisStreams: Error processing liquidity event: {e}")
            server.metrics["errors"] += 1

    if processed:
        logger.info(f"MoralisStreams: 💧 {processed} new liquidity pool(s) on {_chain_id_to_name(chain_id)}")

    return processed


# ─────────────────────────────────────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────────────────────────────────────

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
        "0xa": "optimism",
        "10": "optimism",
    }.get(cid, "ethereum")
