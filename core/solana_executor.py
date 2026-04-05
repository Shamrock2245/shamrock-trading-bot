"""
core/solana_executor.py — Solana trade execution via Jupiter aggregator.

Handles all Solana-specific trade execution:
  - Quote fetching from Jupiter Swap API v1
  - Swap transaction building and signing
  - Transaction submission with retry logic
  - Paper trading simulation

Jupiter is the primary DEX aggregator on Solana, routing through
Raydium, Orca, Meteora, and 20+ other AMMs for best execution.

Security:
  - Private keys loaded ONLY from environment variables
  - Never logged, stored, or transmitted in plaintext
  - Paper mode: all logic runs but transactions are NOT broadcast

Signing (solders 0.21+):
  - VersionedTransaction has NO .sign() method — it is immutable after
    deserialization from bytes.
  - CORRECT pattern (verified against real Jupiter transactions):
      tx = VersionedTransaction.from_bytes(tx_bytes)
      signed_tx = VersionedTransaction(tx.message, [keypair])
  - Fallback pattern (if constructor rejects keypair list):
      sig = keypair.sign_message(bytes(tx.message))
      signed_tx = VersionedTransaction.populate(tx.message, [sig])

Jupiter API:
  - Primary:  https://api.jup.ag/swap/v1  (requires API key)
  - Fallback: https://lite-api.jup.ag/swap/v1  (free, no key needed)
  - The bot automatically falls back to lite-api if primary returns 401.

Dependencies:
  - solders (Solana Python SDK)
  - solana-py
  Install: pip install solders solana base58
"""

import base64
import json
import logging
import os
import time
from typing import Optional

import requests

from config import settings
from config.chains import CHAINS
from core.mev_protection import execute_solana_via_jito

logger = logging.getLogger(__name__)

# Jito tip tiers (lamports) — scales with urgency and price impact
JITO_TIP_STANDARD = 10_000        # ~$0.001 — routine gem trade
JITO_TIP_HIGH_CONVICTION = 50_000  # ~$0.005 — score 80+ or God Signal
JITO_TIP_SNIPE = 100_000           # ~$0.015 — new launch / congested block

# Jupiter API endpoints — primary (keyed) and lite (free fallback)
_JUPITER_PRIMARY_URL = settings.JUPITER_API_URL          # https://api.jup.ag/swap/v1
_JUPITER_LITE_URL = "https://lite-api.jup.ag/swap/v1"   # Always available, no key needed
JUPITER_API_KEY = settings.JUPITER_API_KEY
SOLANA_RPC_URL = settings.SOLANA_RPC_URL

# USDC mint on Solana (for profit-taking)
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
# Wrapped SOL mint
WSOL_MINT = "So11111111111111111111111111111111111111112"


def _jupiter_base_url() -> str:
    """
    Return the active Jupiter base URL.
    Uses primary (api.jup.ag) if JUPITER_API_KEY is set, otherwise lite-api.
    """
    if JUPITER_API_KEY:
        return _JUPITER_PRIMARY_URL
    return _JUPITER_LITE_URL


def _jupiter_headers() -> dict:
    """Build headers for Jupiter API requests."""
    headers = {"Content-Type": "application/json"}
    if JUPITER_API_KEY:
        headers["x-api-key"] = JUPITER_API_KEY
    return headers


def get_jupiter_quote(
    input_mint: str,
    output_mint: str,
    amount_lamports: int,
    slippage_bps: int = 100,  # 1% default slippage
) -> Optional[dict]:
    """
    Get a swap quote from Jupiter Swap API v1.

    Automatically falls back to lite-api.jup.ag if primary returns 401.

    Args:
        input_mint: Input token mint address
        output_mint: Output token mint address
        amount_lamports: Amount in smallest unit (lamports for SOL, or token decimals)
        slippage_bps: Slippage tolerance in basis points (100 = 1%)

    Returns:
        Quote dict from Jupiter, or None on failure
    """
    params = {
        "inputMint": input_mint,
        "outputMint": output_mint,
        "amount": str(amount_lamports),
        "slippageBps": str(slippage_bps),
        "onlyDirectRoutes": "false",
        "asLegacyTransaction": "false",
    }

    # Try primary URL first, fall back to lite if 401
    urls_to_try = [_jupiter_base_url()]
    if urls_to_try[0] != _JUPITER_LITE_URL:
        urls_to_try.append(_JUPITER_LITE_URL)

    for base_url in urls_to_try:
        try:
            url = f"{base_url}/quote"
            resp = requests.get(url, params=params, headers=_jupiter_headers(), timeout=15)
            if resp.status_code == 401 and base_url != _JUPITER_LITE_URL:
                logger.warning(f"Jupiter primary API returned 401 — falling back to lite-api")
                continue
            resp.raise_for_status()
            data = resp.json()
            if "outAmount" in data:
                logger.debug(f"Jupiter quote via {base_url}: {data['outAmount']} out")
                return data
            logger.warning(f"Jupiter quote missing outAmount: {data}")
            return None
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401 and base_url != _JUPITER_LITE_URL:
                logger.warning("Jupiter primary 401 — trying lite-api")
                continue
            logger.error(f"Jupiter quote HTTP error ({base_url}): {e}")
            return None
        except Exception as e:
            logger.error(f"Jupiter quote failed ({base_url}): {e}")
            if base_url != _JUPITER_LITE_URL:
                continue
            return None

    logger.error("All Jupiter quote endpoints failed")
    return None


def get_jupiter_swap_transaction(
    quote: dict,
    user_public_key: str,
    wrap_and_unwrap_sol: bool = True,
) -> Optional[str]:
    """
    Get a serialized swap transaction from Jupiter.

    Uses the same URL that successfully returned the quote (primary or lite).
    Returns base64-encoded transaction string, or None on failure.
    """
    payload = {
        "quoteResponse": quote,
        "userPublicKey": user_public_key,
        "wrapAndUnwrapSol": wrap_and_unwrap_sol,
        "dynamicComputeUnitLimit": True,
        "prioritizationFeeLamports": "auto",
        # NOTE: Do NOT set computeUnitPriceMicroLamports when using
        # prioritizationFeeLamports — they conflict and Jupiter will error.
    }

    urls_to_try = [_jupiter_base_url()]
    if urls_to_try[0] != _JUPITER_LITE_URL:
        urls_to_try.append(_JUPITER_LITE_URL)

    for base_url in urls_to_try:
        try:
            url = f"{base_url}/swap"
            resp = requests.post(url, json=payload, headers=_jupiter_headers(), timeout=20)
            if resp.status_code == 401 and base_url != _JUPITER_LITE_URL:
                logger.warning("Jupiter swap primary 401 — trying lite-api")
                continue
            if resp.status_code != 200:
                logger.error(f"Jupiter swap error {resp.status_code} ({base_url}): {resp.text[:500]}")
                if base_url != _JUPITER_LITE_URL:
                    continue
                return None
            data = resp.json()
            tx = data.get("swapTransaction")
            if tx:
                return tx
            logger.error(f"Jupiter swap missing swapTransaction field: {data}")
            return None
        except Exception as e:
            logger.error(f"Jupiter swap transaction failed ({base_url}): {e}")
            if base_url != _JUPITER_LITE_URL:
                continue
            return None

    return None


def _poll_tx_confirmation(
    signature: str,
    rpc_url: str,
    timeout: int = 30,
    poll_interval: float = 2.0,
) -> bool:
    """
    Poll Solana RPC for transaction confirmation.
    Returns True if the transaction reaches 'confirmed' commitment within timeout.
    """
    start = time.time()
    while time.time() - start < timeout:
        try:
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getSignatureStatuses",
                "params": [[signature], {"searchTransactionHistory": False}],
            }
            resp = requests.post(rpc_url, json=payload, timeout=10)
            result = resp.json()
            statuses = result.get("result", {}).get("value", [])
            if statuses and statuses[0] is not None:
                status = statuses[0]
                confirmation_status = status.get("confirmationStatus", "")
                if confirmation_status in ("confirmed", "finalized"):
                    return True
                if status.get("err") is not None:
                    logger.warning(f"Solana tx failed on-chain: {status['err']}")
                    return False
        except Exception as e:
            logger.debug(f"Confirmation poll error: {e}")
        time.sleep(poll_interval)
    return False


def sign_and_send_transaction(
    serialized_tx_b64: str,
    private_key_b58: str,
    rpc_url: str = SOLANA_RPC_URL,
    max_retries: int = 3,
) -> Optional[str]:
    """
    Sign and broadcast a Solana VersionedTransaction.

    Signing strategy (verified against solders 0.21+ with real Jupiter txns):
      1. Deserialize: tx = VersionedTransaction.from_bytes(tx_bytes)
      2. Sign:        signed_tx = VersionedTransaction(tx.message, [keypair])
         - This constructs a new VersionedTransaction with the keypair signing
           the message. The keypair list is used directly as signers.
      3. Fallback:    If Pattern 1 raises TypeError, use populate():
           sig = keypair.sign_message(bytes(tx.message))
           signed_tx = VersionedTransaction.populate(tx.message, [sig])

    Args:
        serialized_tx_b64: Base64-encoded transaction from Jupiter
        private_key_b58: Base58-encoded private key (from env var)
        rpc_url: Solana RPC endpoint
        max_retries: Number of retry attempts on RPC errors

    Returns:
        Transaction signature (hash) on success, None on failure
    """
    try:
        from solders.keypair import Keypair  # type: ignore
        from solders.transaction import VersionedTransaction  # type: ignore
        import base58

        # ── Load keypair ──────────────────────────────────────────────────────
        private_key_bytes = base58.b58decode(private_key_b58)
        keypair = Keypair.from_bytes(private_key_bytes)
        logger.debug(f"Loaded keypair: {keypair.pubkey()}")

        # ── Deserialize transaction ───────────────────────────────────────────
        tx_bytes = base64.b64decode(serialized_tx_b64)
        tx = VersionedTransaction.from_bytes(tx_bytes)
        logger.debug(f"Deserialized tx, message version: {tx.version}")

        # ── Sign transaction (Pattern 1 — verified working) ───────────────────
        # VersionedTransaction(message, signers) constructs a signed tx.
        # The signers list must contain Keypair objects (not Signature objects).
        try:
            signed_tx = VersionedTransaction(tx.message, [keypair])
            logger.debug("Signing Pattern 1 (VersionedTransaction constructor) succeeded")
        except (TypeError, Exception) as e1:
            logger.warning(f"Pattern 1 failed ({e1}), trying Pattern 2 (populate)")
            # Pattern 2: sign_message → Signature → populate
            try:
                sig = keypair.sign_message(bytes(tx.message))
                signed_tx = VersionedTransaction.populate(tx.message, [sig])
                logger.debug("Signing Pattern 2 (populate) succeeded")
            except Exception as e2:
                logger.error(f"Both signing patterns failed. P1: {e1} | P2: {e2}")
                return None

        # ── Verify signature is non-zero ──────────────────────────────────────
        sigs = signed_tx.signatures
        if not sigs:
            logger.error("Signed transaction has no signatures")
            return None
        zero_sig = "1" * 88  # base58-encoded zero signature
        if str(sigs[0]).startswith("111111111111111111111111"):
            logger.error("Signature is zero — signing failed silently")
            return None
        logger.debug(f"Signature verified non-zero: {str(sigs[0])[:16]}...")

        # ── Serialize signed transaction ──────────────────────────────────────
        signed_tx_bytes = bytes(signed_tx)
        signed_tx_b64 = base64.b64encode(signed_tx_bytes).decode("utf-8")

        # ── Send with retries ─────────────────────────────────────────────────
        rpc_urls = [rpc_url]
        if hasattr(settings, "SOLANA_RPC_FALLBACK") and settings.SOLANA_RPC_FALLBACK:
            rpc_urls.append(settings.SOLANA_RPC_FALLBACK)

        for attempt in range(max_retries):
            active_rpc = rpc_urls[min(attempt, len(rpc_urls) - 1)]
            try:
                payload = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "sendTransaction",
                    "params": [
                        signed_tx_b64,
                        {
                            "encoding": "base64",
                            "skipPreflight": False,
                            "preflightCommitment": "confirmed",
                            "maxRetries": 3,
                        },
                    ],
                }
                resp = requests.post(active_rpc, json=payload, timeout=30)
                result = resp.json()

                if "error" in result:
                    err = result["error"]
                    err_msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
                    logger.error(f"RPC error (attempt {attempt+1}/{max_retries}): {err_msg}")
                    # Blockhash expired — no point retrying same tx
                    if "BlockhashNotFound" in err_msg or "block height exceeded" in err_msg.lower():
                        logger.error("Blockhash expired — transaction must be rebuilt")
                        return None
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)
                    continue

                signature = result.get("result")
                if signature:
                    logger.info(f"✅ Solana tx broadcast: {signature}")
                    # Poll for confirmation (up to 30s)
                    confirmed = _poll_tx_confirmation(signature, active_rpc, timeout=30)
                    if confirmed:
                        logger.info(f"✅ Solana tx confirmed: {signature}")
                        return signature
                    else:
                        logger.warning(f"⚠️ Solana tx broadcast but NOT confirmed after 30s: {signature}")
                        # Still return signature — position monitor will reconcile
                        return signature

                logger.error(f"Unexpected RPC response: {result}")

            except Exception as e:
                logger.error(f"Send attempt {attempt+1} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)

        logger.error(f"Transaction failed after {max_retries} attempts")
        return None

    except ImportError:
        logger.error(
            "solders/base58 packages not installed. "
            "Run: pip install solders solana base58"
        )
        return None
    except Exception as e:
        logger.error(f"sign_and_send_transaction failed: {e}", exc_info=True)
        return None


def execute_solana_buy(
    token_mint: str,
    sol_amount: float,
    wallet_public_key: str,
    wallet_private_key_env: str,
    slippage_bps: int = 150,
    is_paper: bool = True,
) -> Optional[str]:
    """
    Execute a buy on Solana via Jupiter.

    Args:
        token_mint: Target token mint address
        sol_amount: Amount of SOL to spend
        wallet_public_key: Wallet's public key
        wallet_private_key_env: Name of env var holding the private key
        slippage_bps: Slippage tolerance (150 = 1.5%)
        is_paper: If True, simulate but don't broadcast

    Returns:
        Transaction signature on success, "PAPER_TX" in paper mode, None on failure
    """
    lamports = int(sol_amount * 1_000_000_000)

    logger.info(
        f"{'📄 PAPER' if is_paper else '🔴 LIVE'} Solana BUY: "
        f"{sol_amount:.4f} SOL → {token_mint[:8]}..."
    )

    # Get quote
    quote = get_jupiter_quote(
        input_mint=WSOL_MINT,
        output_mint=token_mint,
        amount_lamports=lamports,
        slippage_bps=slippage_bps,
    )

    if not quote:
        logger.error(f"No Jupiter quote for {token_mint}")
        return None

    out_amount = int(quote.get("outAmount", 0))
    price_impact = float(quote.get("priceImpactPct", 0))

    logger.info(
        f"Jupiter quote: {sol_amount:.4f} SOL → {out_amount:,} tokens | "
        f"price impact: {price_impact:.3f}%"
    )

    # Reject if price impact is too high
    if price_impact > 5.0:
        logger.warning(f"Price impact too high: {price_impact:.2f}% — skipping")
        return None

    if is_paper:
        logger.info(
            f"📄 PAPER MODE: Simulated buy of {token_mint[:8]}... "
            f"for {sol_amount:.4f} SOL → {out_amount:,} tokens"
        )
        return "PAPER_TX"

    # ── Live execution ────────────────────────────────────────────────────────
    private_key = os.getenv(wallet_private_key_env)
    if not private_key:
        logger.error(f"Private key not found in env var: {wallet_private_key_env}")
        return None

    # Get swap transaction
    swap_tx = get_jupiter_swap_transaction(
        quote=quote,
        user_public_key=wallet_public_key,
    )

    if not swap_tx:
        logger.error("Failed to get swap transaction from Jupiter")
        return None

    # ── Sign the transaction ──────────────────────────────────────────────────
    signed_tx_b64 = None
    try:
        from solders.keypair import Keypair  # type: ignore
        from solders.transaction import VersionedTransaction  # type: ignore
        import base58 as _base58
        import base64 as _base64

        _pk_bytes = _base58.b58decode(private_key)
        _keypair = Keypair.from_bytes(_pk_bytes)
        _tx_bytes = _base64.b64decode(swap_tx)
        _tx = VersionedTransaction.from_bytes(_tx_bytes)
        try:
            _signed_tx = VersionedTransaction(_tx.message, [_keypair])
        except (TypeError, Exception):
            _sig = _keypair.sign_message(bytes(_tx.message))
            _signed_tx = VersionedTransaction.populate(_tx.message, [_sig])
        signed_tx_b64 = _base64.b64encode(bytes(_signed_tx)).decode()
    except ImportError:
        logger.warning("solders not available — falling back to standard submission")

    # ── Jito bundle submission (primary — MEV protected) ──────────────────────
    if signed_tx_b64:
        # Scale tip by price impact: higher impact = more competitive block needed
        if price_impact > 2.0:
            tip = JITO_TIP_SNIPE
        elif price_impact > 0.5:
            tip = JITO_TIP_HIGH_CONVICTION
        else:
            tip = JITO_TIP_STANDARD

        jito_result = execute_solana_via_jito(
            serialized_tx_b64=signed_tx_b64,
            wallet_public_key=wallet_public_key,
            tip_lamports=tip,
        )
        if jito_result.success:
            logger.info(
                f"✅ Solana buy via Jito bundle: {jito_result.bundle_id} "
                f"| tip={tip:,} lamports | {token_mint[:8]}..."
            )
            return jito_result.bundle_id or "jito_bundle_submitted"
        else:
            logger.warning(
                f"Jito bundle failed ({jito_result.error}) — falling back to standard RPC"
            )

    # ── Standard RPC fallback ─────────────────────────────────────────────────
    signature = sign_and_send_transaction(
        serialized_tx_b64=swap_tx,
        private_key_b58=private_key,
    )

    if signature:
        logger.info(f"✅ Solana buy executed (standard RPC): https://solscan.io/tx/{signature}")
    else:
        logger.error(f"❌ Solana buy failed for {token_mint}")

    return signature


def execute_solana_sell(
    token_mint: str,
    token_amount: int,  # In token's smallest unit
    wallet_public_key: str,
    wallet_private_key_env: str,
    output_mint: str = WSOL_MINT,  # Sell back to SOL (native base pair — feeds next buy directly)
    slippage_bps: int = 200,
    is_paper: bool = True,
) -> Optional[str]:
    """
    Execute a sell on Solana via Jupiter.

    Args:
        token_mint: Token to sell
        token_amount: Amount in token's smallest unit
        wallet_public_key: Wallet's public key
        wallet_private_key_env: Name of env var holding the private key
        output_mint: Token to receive (default: WSOL — SOL is native base pair, 1-hop on Jupiter,
                     feeds directly back into execute_solana_buy(). Pass USDC_MINT to lock profit.)
        slippage_bps: Slippage tolerance (200 = 2%)
        is_paper: If True, simulate but don't broadcast

    Returns:
        Transaction signature on success, "PAPER_TX" in paper mode, None on failure
    """
    logger.info(
        f"{'📄 PAPER' if is_paper else '🔴 LIVE'} Solana SELL: "
        f"{token_amount:,} units of {token_mint[:8]}..."
    )

    quote = get_jupiter_quote(
        input_mint=token_mint,
        output_mint=output_mint,
        amount_lamports=token_amount,
        slippage_bps=slippage_bps,
    )

    if not quote:
        logger.error(f"No Jupiter quote for selling {token_mint}")
        return None

    out_amount = int(quote.get("outAmount", 0))
    price_impact = float(quote.get("priceImpactPct", 0))
    out_label = "USDC" if output_mint == USDC_MINT else ("SOL" if output_mint == WSOL_MINT else output_mint[:8])
    out_divisor = 1e6 if output_mint == USDC_MINT else 1e9
    logger.info(
        f"Jupiter sell quote: {token_amount:,} tokens → {out_amount/out_divisor:.4f} {out_label} | "
        f"price impact: {price_impact:.3f}%"
    )

    # For sells, NEVER block on price impact — we must be able to exit even rugs.
    # High impact just means low liquidity; log a warning and widen slippage instead.
    if price_impact > 10.0:
        logger.warning(
            f"⚠️ High sell price impact {price_impact:.1f}% for {token_mint[:8]}... "
            f"— widening slippage to 500bps to force exit"
        )
        slippage_bps = max(slippage_bps, 500)
        # Re-fetch quote with wider slippage
        quote = get_jupiter_quote(
            input_mint=token_mint,
            output_mint=output_mint,
            amount_lamports=token_amount,
            slippage_bps=slippage_bps,
        ) or quote  # Fall back to original quote if re-fetch fails

    if is_paper:
        logger.info(f"📄 PAPER MODE: Simulated sell of {token_mint[:8]}...")
        return "PAPER_TX"

    private_key = os.getenv(wallet_private_key_env)
    if not private_key:
        logger.error(f"Private key not found in env var: {wallet_private_key_env}")
        return None

    swap_tx = get_jupiter_swap_transaction(
        quote=quote,
        user_public_key=wallet_public_key,
    )

    if not swap_tx:
        return None

    signature = sign_and_send_transaction(
        serialized_tx_b64=swap_tx,
        private_key_b58=private_key,
    )

    if signature:
        logger.info(f"✅ Solana sell executed: https://solscan.io/tx/{signature}")
    else:
        logger.error(f"❌ Solana sell failed for {token_mint}")

    return signature
