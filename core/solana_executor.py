"""
core/solana_executor.py — Solana trade execution via Jupiter aggregator.

Handles all Solana-specific trade execution:
  - Quote fetching from Jupiter v6 API
  - Swap transaction building and signing
  - Transaction submission with retry logic
  - Paper trading simulation

Jupiter is the primary DEX aggregator on Solana, routing through
Raydium, Orca, Meteora, and 20+ other AMMs for best execution.

Security:
  - Private keys loaded ONLY from environment variables
  - Never logged, stored, or transmitted in plaintext
  - Paper mode: all logic runs but transactions are NOT broadcast

Dependencies:
  - solders (Solana Python SDK)
  - solana-py
  Install: pip install solders solana
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

logger = logging.getLogger(__name__)

JUPITER_API_URL = settings.JUPITER_API_URL
SOLANA_RPC_URL = settings.SOLANA_RPC_URL

# USDC mint on Solana (for profit-taking)
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
# Wrapped SOL mint
WSOL_MINT = "So11111111111111111111111111111111111111112"


def get_jupiter_quote(
    input_mint: str,
    output_mint: str,
    amount_lamports: int,
    slippage_bps: int = 100,  # 1% default slippage
) -> Optional[dict]:
    """
    Get a swap quote from Jupiter v6 API.

    Args:
        input_mint: Input token mint address
        output_mint: Output token mint address
        amount_lamports: Amount in smallest unit (lamports for SOL, or token decimals)
        slippage_bps: Slippage tolerance in basis points (100 = 1%)

    Returns:
        Quote dict from Jupiter, or None on failure
    """
    try:
        url = f"{JUPITER_API_URL}/quote"
        params = {
            "inputMint": input_mint,
            "outputMint": output_mint,
            "amount": str(amount_lamports),
            "slippageBps": str(slippage_bps),
            "onlyDirectRoutes": "false",
            "asLegacyTransaction": "false",
        }
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"Jupiter quote failed: {e}")
        return None


def get_jupiter_swap_transaction(
    quote: dict,
    user_public_key: str,
    wrap_and_unwrap_sol: bool = True,
    compute_unit_price_micro_lamports: int = 1000,  # Priority fee
) -> Optional[str]:
    """
    Get a serialized swap transaction from Jupiter.

    Returns base64-encoded transaction string, or None on failure.
    """
    try:
        url = f"{JUPITER_API_URL}/swap"
        payload = {
            "quoteResponse": quote,
            "userPublicKey": user_public_key,
            "wrapAndUnwrapSol": wrap_and_unwrap_sol,
            "computeUnitPriceMicroLamports": compute_unit_price_micro_lamports,
            "dynamicComputeUnitLimit": True,
            "prioritizationFeeLamports": "auto",
        }
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return data.get("swapTransaction")
    except Exception as e:
        logger.error(f"Jupiter swap transaction failed: {e}")
        return None


def sign_and_send_transaction(
    serialized_tx_b64: str,
    private_key_b58: str,
    rpc_url: str = SOLANA_RPC_URL,
    max_retries: int = 3,
) -> Optional[str]:
    """
    Sign and broadcast a Solana transaction.

    Args:
        serialized_tx_b64: Base64-encoded transaction from Jupiter
        private_key_b58: Base58-encoded private key (from env var)
        rpc_url: Solana RPC endpoint
        max_retries: Number of retry attempts

    Returns:
        Transaction signature (hash) on success, None on failure
    """
    try:
        from solders.keypair import Keypair  # type: ignore
        from solders.transaction import VersionedTransaction  # type: ignore
        import base58

        # Load keypair from base58 private key
        private_key_bytes = base58.b58decode(private_key_b58)
        keypair = Keypair.from_bytes(private_key_bytes)

        # Deserialize transaction
        tx_bytes = base64.b64decode(serialized_tx_b64)
        tx = VersionedTransaction.from_bytes(tx_bytes)

        # Sign transaction
        tx.sign([keypair])

        # Serialize signed transaction
        signed_tx_bytes = bytes(tx)
        signed_tx_b64 = base64.b64encode(signed_tx_bytes).decode("utf-8")

        # Send transaction with retries
        for attempt in range(max_retries):
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
                resp = requests.post(rpc_url, json=payload, timeout=30)
                result = resp.json()

                if "error" in result:
                    logger.error(f"Transaction error (attempt {attempt+1}): {result['error']}")
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)
                    continue

                signature = result.get("result")
                if signature:
                    logger.info(f"Solana tx broadcast: {signature}")
                    return signature

            except Exception as e:
                logger.error(f"Send attempt {attempt+1} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)

        return None

    except ImportError:
        logger.error(
            "solders/solana packages not installed. "
            "Run: pip install solders solana base58"
        )
        return None
    except Exception as e:
        logger.error(f"Sign and send failed: {e}")
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
        f"{'PAPER' if is_paper else 'LIVE'} Solana BUY: "
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
        f"Jupiter quote: {sol_amount:.4f} SOL → {out_amount} tokens | "
        f"price impact: {price_impact:.2f}%"
    )

    # Reject if price impact is too high
    if price_impact > 5.0:
        logger.warning(f"Price impact too high: {price_impact:.2f}% — skipping")
        return None

    if is_paper:
        logger.info(f"PAPER MODE: Simulated buy of {token_mint[:8]}... for {sol_amount:.4f} SOL")
        return "PAPER_TX"

    # Live execution
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

    # Sign and send
    signature = sign_and_send_transaction(
        serialized_tx_b64=swap_tx,
        private_key_b58=private_key,
    )

    if signature:
        logger.info(f"Solana buy executed: {signature}")
    else:
        logger.error(f"Solana buy failed for {token_mint}")

    return signature


def execute_solana_sell(
    token_mint: str,
    token_amount: int,  # In token's smallest unit
    wallet_public_key: str,
    wallet_private_key_env: str,
    output_mint: str = WSOL_MINT,  # Default: sell back to SOL
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
        output_mint: Token to receive (default: WSOL)
        slippage_bps: Slippage tolerance (200 = 2%)
        is_paper: If True, simulate but don't broadcast

    Returns:
        Transaction signature on success, "PAPER_TX" in paper mode, None on failure
    """
    logger.info(
        f"{'PAPER' if is_paper else 'LIVE'} Solana SELL: "
        f"{token_amount} units of {token_mint[:8]}..."
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
    logger.info(
        f"Jupiter sell quote: {token_amount} tokens → {out_amount/1e9:.4f} SOL | "
        f"price impact: {price_impact:.2f}%"
    )

    if is_paper:
        logger.info(f"PAPER MODE: Simulated sell of {token_mint[:8]}...")
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

    return sign_and_send_transaction(
        serialized_tx_b64=swap_tx,
        private_key_b58=private_key,
    )
