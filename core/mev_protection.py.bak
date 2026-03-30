"""
core/mev_protection.py — Flashbots bundle submission and CoW Protocol live signing.

This module fills the "not yet implemented" gaps in executor.py:
  1. Flashbots: Submit private transaction bundles to avoid front-running
  2. CoW Protocol: Full EIP-712 order signing for live execution

MEV Protection Strategy by Chain:
  - Ethereum: CoW Protocol (batch auctions) → Flashbots (private mempool) → 1inch
  - Base/Arbitrum/Polygon/BSC: 1inch (fast finality, MEV less of a concern)
  - Solana: Jupiter (MEV protection built-in via priority fees)

Flashbots:
  - Sends tx as a private bundle to Flashbots relay
  - Bundle is only included if profitable for the block builder
  - Completely invisible to mempool scanners — no front-running possible
  - Requires FLASHBOTS_SIGNING_KEY (separate from wallet key — just for auth)

CoW Protocol:
  - Off-chain order matching in batch auctions
  - Orders are matched peer-to-peer before on-chain settlement
  - Best price + MEV protection for Ethereum mainnet
  - Requires EIP-712 signature of order struct
"""

import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass
from typing import Optional

import requests
from eth_account import Account
from eth_account.messages import encode_defunct
from web3 import Web3

from config import settings
from config.chains import CHAINS

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Flashbots Bundle Submission
# ─────────────────────────────────────────────────────────────────────────────

FLASHBOTS_RELAY_URL = "https://relay.flashbots.net"
FLASHBOTS_PROTECT_RPC = "https://rpc.flashbots.net"


@dataclass
class FlashbotsResult:
    """Result of a Flashbots bundle submission."""
    success: bool
    bundle_hash: Optional[str] = None
    block_number: Optional[int] = None
    tx_hash: Optional[str] = None
    error: Optional[str] = None
    simulation_passed: bool = False


def _sign_flashbots_request(body: str, signing_key: str) -> str:
    """
    Sign a Flashbots API request body with the signing key.
    Flashbots uses HMAC-SHA256 of the body for authentication.
    """
    signature = hmac.new(
        signing_key.encode("utf-8"),
        body.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"0x{signature}"


def submit_flashbots_bundle(
    signed_txs: list[str],
    target_block: int,
    signing_key: str,
    simulate: bool = True,
) -> FlashbotsResult:
    """
    Submit a transaction bundle to the Flashbots relay.

    Args:
        signed_txs: List of signed raw transactions (hex strings)
        target_block: Target block number for inclusion
        signing_key: Flashbots signing key (NOT wallet private key)
        simulate: Whether to simulate the bundle first

    Returns:
        FlashbotsResult with bundle hash or error
    """
    if not signing_key:
        return FlashbotsResult(
            success=False,
            error="FLASHBOTS_SIGNING_KEY not configured",
        )

    if settings.IS_PAPER:
        logger.info(f"[PAPER] Flashbots bundle: {len(signed_txs)} txs → block {target_block}")
        return FlashbotsResult(
            success=True,
            bundle_hash="0x" + "0" * 64,
            block_number=target_block,
            simulation_passed=True,
        )

    # Step 1: Simulate the bundle (optional but recommended)
    if simulate:
        sim_result = _simulate_flashbots_bundle(signed_txs, target_block, signing_key)
        if not sim_result:
            logger.warning("Flashbots simulation failed — submitting anyway")
        else:
            logger.info(f"Flashbots simulation passed: {sim_result}")

    # Step 2: Submit the bundle
    bundle_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "eth_sendBundle",
        "params": [
            {
                "txs": signed_txs,
                "blockNumber": hex(target_block),
                "minTimestamp": 0,
                "maxTimestamp": int(time.time()) + 120,  # 2 min window
            }
        ],
    }

    body = json.dumps(bundle_payload)
    signature = _sign_flashbots_request(body, signing_key)

    headers = {
        "Content-Type": "application/json",
        "X-Flashbots-Signature": f"flashbots:{signature}",
    }

    try:
        resp = requests.post(
            FLASHBOTS_RELAY_URL,
            data=body,
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()

        if "error" in result:
            return FlashbotsResult(
                success=False,
                error=f"Flashbots error: {result['error']}",
            )

        bundle_hash = result.get("result", {}).get("bundleHash", "")
        logger.info(f"Flashbots bundle submitted: {bundle_hash} → block {target_block}")

        return FlashbotsResult(
            success=True,
            bundle_hash=bundle_hash,
            block_number=target_block,
            simulation_passed=simulate,
        )

    except Exception as e:
        logger.error(f"Flashbots submission error: {e}")
        return FlashbotsResult(success=False, error=str(e))


def _simulate_flashbots_bundle(
    signed_txs: list[str],
    target_block: int,
    signing_key: str,
) -> Optional[dict]:
    """Simulate a Flashbots bundle to check for reverts before submission."""
    sim_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "eth_callBundle",
        "params": [
            {
                "txs": signed_txs,
                "blockNumber": hex(target_block),
                "stateBlockNumber": "latest",
            }
        ],
    }

    body = json.dumps(sim_payload)
    signature = _sign_flashbots_request(body, signing_key)
    headers = {
        "Content-Type": "application/json",
        "X-Flashbots-Signature": f"flashbots:{signature}",
    }

    try:
        resp = requests.post(
            FLASHBOTS_RELAY_URL,
            data=body,
            headers=headers,
            timeout=20,
        )
        resp.raise_for_status()
        result = resp.json()
        return result.get("result")
    except Exception as e:
        logger.debug(f"Flashbots simulation error: {e}")
        return None


def execute_via_flashbots(
    w3: Web3,
    private_key: str,
    signing_key: str,
    to: str,
    data: str,
    value: int,
    gas: int,
    chain_id: int = 1,
) -> FlashbotsResult:
    """
    Execute a transaction via Flashbots private mempool.

    Builds, signs, and submits a transaction as a Flashbots bundle.
    The transaction is invisible to mempool scanners — no front-running.

    Args:
        w3: Web3 instance connected to Ethereum
        private_key: Wallet private key (from env var)
        signing_key: Flashbots signing key (FLASHBOTS_SIGNING_KEY env var)
        to: Contract address to call
        data: Encoded calldata
        value: ETH value in wei
        gas: Gas limit
        chain_id: Chain ID (1 for Ethereum mainnet)

    Returns:
        FlashbotsResult with tx hash or error
    """
    if settings.IS_PAPER:
        logger.info(f"[PAPER] Flashbots tx: to={to[:10]}... value={value/1e18:.4f} ETH")
        return FlashbotsResult(
            success=True,
            tx_hash="0x" + "0" * 64,
            simulation_passed=True,
        )

    try:
        account = Account.from_key(private_key)
        nonce = w3.eth.get_transaction_count(account.address)
        gas_price = w3.eth.gas_price

        transaction = {
            "from": account.address,
            "to": Web3.to_checksum_address(to),
            "data": data,
            "value": value,
            "gas": gas,
            "gasPrice": gas_price,
            "nonce": nonce,
            "chainId": chain_id,
        }

        signed = account.sign_transaction(transaction)
        raw_tx = signed.raw_transaction.hex()
        if not raw_tx.startswith("0x"):
            raw_tx = "0x" + raw_tx

        # Target the next 3 blocks for inclusion
        current_block = w3.eth.block_number
        for target_block in range(current_block + 1, current_block + 4):
            result = submit_flashbots_bundle(
                signed_txs=[raw_tx],
                target_block=target_block,
                signing_key=signing_key,
                simulate=(target_block == current_block + 1),  # Only simulate first attempt
            )
            if result.success:
                result.tx_hash = signed.hash.hex()
                logger.info(
                    f"Flashbots tx submitted: {result.tx_hash[:10]}... "
                    f"→ block {target_block}"
                )
                return result

        return FlashbotsResult(
            success=False,
            error="Failed to submit to Flashbots after 3 block attempts",
        )

    except Exception as e:
        logger.error(f"Flashbots execution error: {e}")
        return FlashbotsResult(success=False, error=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# CoW Protocol Live Signing
# ─────────────────────────────────────────────────────────────────────────────

# CoW Protocol EIP-712 domain and type hashes
COW_DOMAIN_SEPARATOR_MAINNET = "0xc078f884a2676e1345748b1feace7b0abee5d00ecadb6e574dcdd109a63e8943"

# Order type hash (keccak256 of the Order struct)
COW_ORDER_TYPE_HASH = "0xd5a25ba2e97094ad7d83dc28a6572da797d6b3e7fc6663bd93efb789fc17e489"


@dataclass
class CowOrder:
    """CoW Protocol order structure."""
    sell_token: str
    buy_token: str
    receiver: str
    sell_amount: int
    buy_amount: int
    valid_to: int
    app_data: str = "0x" + "0" * 64
    fee_amount: int = 0
    kind: str = "sell"
    partially_fillable: bool = False
    sell_token_balance: str = "erc20"
    buy_token_balance: str = "erc20"


def get_cow_quote(
    sell_token: str,
    buy_token: str,
    sell_amount: int,
    from_address: str,
    chain: str = "ethereum",
) -> Optional[dict]:
    """
    Get a quote from CoW Protocol.

    Returns the quote dict with buyAmount, feeAmount, etc.
    """
    cow_url = settings.COW_API_URL
    if chain != "ethereum":
        # CoW is only on Ethereum mainnet + Gnosis Chain
        return None

    payload = {
        "sellToken": sell_token,
        "buyToken": buy_token,
        "sellAmountBeforeFee": str(sell_amount),
        "from": from_address,
        "kind": "sell",
        "partiallyFillable": False,
        "signingScheme": "eip712",
        "onchainOrder": False,
    }

    try:
        resp = requests.post(
            f"{cow_url}/api/v1/quote",
            json=payload,
            timeout=15,
        )
        if resp.status_code != 200:
            logger.warning(f"CoW quote failed: {resp.status_code} {resp.text[:200]}")
            return None
        return resp.json()
    except Exception as e:
        logger.error(f"CoW quote error: {e}")
        return None


def sign_cow_order(order: CowOrder, private_key: str, chain_id: int = 1) -> Optional[str]:
    """
    Sign a CoW Protocol order using EIP-712 structured data signing.

    Returns the hex signature string, or None on failure.
    """
    try:
        # Build EIP-712 structured data
        domain = {
            "name": "Gnosis Protocol",
            "version": "v2",
            "chainId": chain_id,
            "verifyingContract": "0x9008D19f58AAbD9eD0D60971565AA8510560ab41",  # CoW settlement
        }

        order_types = {
            "Order": [
                {"name": "sellToken", "type": "address"},
                {"name": "buyToken", "type": "address"},
                {"name": "receiver", "type": "address"},
                {"name": "sellAmount", "type": "uint256"},
                {"name": "buyAmount", "type": "uint256"},
                {"name": "validTo", "type": "uint32"},
                {"name": "appData", "type": "bytes32"},
                {"name": "feeAmount", "type": "uint256"},
                {"name": "kind", "type": "bytes32"},
                {"name": "partiallyFillable", "type": "bool"},
                {"name": "sellTokenBalance", "type": "bytes32"},
                {"name": "buyTokenBalance", "type": "bytes32"},
            ]
        }

        order_data = {
            "sellToken": order.sell_token,
            "buyToken": order.buy_token,
            "receiver": order.receiver,
            "sellAmount": order.sell_amount,
            "buyAmount": order.buy_amount,
            "validTo": order.valid_to,
            "appData": order.app_data,
            "feeAmount": order.fee_amount,
            "kind": Web3.keccak(text=order.kind).hex(),
            "partiallyFillable": order.partially_fillable,
            "sellTokenBalance": Web3.keccak(text=order.sell_token_balance).hex(),
            "buyTokenBalance": Web3.keccak(text=order.buy_token_balance).hex(),
        }

        from eth_account.structured_data.hashing import hash_domain, hash_message
        from eth_account._utils.structured_data.hashing import hash_domain

        account = Account.from_key(private_key)

        # Use eth_account's sign_typed_data for EIP-712
        structured_data = {
            "types": {
                "EIP712Domain": [
                    {"name": "name", "type": "string"},
                    {"name": "version", "type": "string"},
                    {"name": "chainId", "type": "uint256"},
                    {"name": "verifyingContract", "type": "address"},
                ],
                **order_types,
            },
            "domain": domain,
            "primaryType": "Order",
            "message": order_data,
        }

        signed = account.sign_typed_data(
            domain_data=domain,
            message_types=order_types,
            message_data=order_data,
        )
        return signed.signature.hex()

    except Exception as e:
        logger.error(f"CoW order signing error: {e}")
        return None


def submit_cow_order(
    order: CowOrder,
    signature: str,
    chain: str = "ethereum",
) -> Optional[str]:
    """
    Submit a signed CoW order to the CoW Protocol API.

    Returns the order UID (string) on success, None on failure.
    """
    cow_url = settings.COW_API_URL

    order_payload = {
        "sellToken": order.sell_token,
        "buyToken": order.buy_token,
        "receiver": order.receiver,
        "sellAmount": str(order.sell_amount),
        "buyAmount": str(order.buy_amount),
        "validTo": order.valid_to,
        "appData": order.app_data,
        "feeAmount": str(order.fee_amount),
        "kind": order.kind,
        "partiallyFillable": order.partially_fillable,
        "signature": signature,
        "signingScheme": "eip712",
        "from": order.receiver,
    }

    try:
        resp = requests.post(
            f"{cow_url}/api/v1/orders",
            json=order_payload,
            timeout=20,
        )
        if resp.status_code in (200, 201):
            order_uid = resp.json()
            logger.info(f"CoW order submitted: {order_uid}")
            return order_uid
        else:
            logger.warning(f"CoW order submission failed: {resp.status_code} {resp.text[:200]}")
            return None
    except Exception as e:
        logger.error(f"CoW order submission error: {e}")
        return None


def execute_via_cow_live(
    sell_token: str,
    buy_token: str,
    sell_amount_wei: int,
    wallet_address: str,
    private_key: str,
    slippage_bps: int = 50,
    chain: str = "ethereum",
) -> Optional[str]:
    """
    Full CoW Protocol live execution:
    1. Get quote
    2. Build order with min buy amount (quote - slippage)
    3. Sign order (EIP-712)
    4. Submit to CoW API

    Returns order UID on success, None on failure.
    """
    if settings.IS_PAPER:
        logger.info(
            f"[PAPER] CoW order: {sell_token[:10]}... → {buy_token[:10]}... "
            f"amount={sell_amount_wei/1e18:.4f}"
        )
        return "paper_order_uid_" + str(int(time.time()))

    # Step 1: Get quote
    quote_resp = get_cow_quote(sell_token, buy_token, sell_amount_wei, wallet_address, chain)
    if not quote_resp:
        logger.warning("CoW quote failed — cannot execute live order")
        return None

    quote = quote_resp.get("quote", {})
    buy_amount = int(quote.get("buyAmount", 0))
    fee_amount = int(quote.get("feeAmount", 0))

    if buy_amount <= 0:
        logger.warning(f"CoW quote returned zero buy amount")
        return None

    # Apply slippage to minimum buy amount
    min_buy_amount = int(buy_amount * (1 - slippage_bps / 10000))

    # Step 2: Build order
    order = CowOrder(
        sell_token=sell_token,
        buy_token=buy_token,
        receiver=wallet_address,
        sell_amount=sell_amount_wei - fee_amount,
        buy_amount=min_buy_amount,
        valid_to=int(time.time()) + 1800,  # 30 min validity
        fee_amount=fee_amount,
    )

    # Step 3: Sign order
    chain_config = CHAINS.get(chain)
    chain_id = chain_config.chain_id if chain_config else 1
    signature = sign_cow_order(order, private_key, chain_id)
    if not signature:
        logger.error("CoW order signing failed")
        return None

    # Step 4: Submit
    order_uid = submit_cow_order(order, signature, chain)
    if order_uid:
        logger.info(
            f"CoW live order submitted: {order_uid} | "
            f"sell={sell_amount_wei/1e18:.4f} → min_buy={min_buy_amount/1e18:.6f}"
        )
    return order_uid
