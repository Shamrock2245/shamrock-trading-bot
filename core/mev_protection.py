"""
core/mev_protection.py — Flashbots bundle submission, Jito Solana bundles, and CoW Protocol live signing.

MEV Protection Strategy by Chain:
  - Ethereum:        CoW Protocol (batch auctions) → Flashbots Bundle (private mempool) → 1inch
  - Base/Arbitrum:   Flashbots Protect RPC (private tx, no bundle auth needed) → 1inch
  - Polygon/BSC:     1inch (fast finality, MEV less critical at these sizes)
  - Solana:          Jito Bundle API (private bundle, tip-based priority) → Jupiter standard

UPGRADE LOG (2026-03-30):
  - Fixed _sign_flashbots_request: now uses EIP-191 eth_account signing (not HMAC)
  - Added execute_via_flashbots chain routing: Ethereum=bundle, Base/Arb=Protect RPC
  - Added EIP-1559 gas pricing (maxFeePerGas/maxPriorityFeePerGas) with 15% escalation
  - Added Jito bundle submission for Solana: submit_jito_bundle, execute_solana_via_jito
  - Added submit_via_flashbots_protect for Base/Arbitrum single-tx private relay
  - Added FlashbotsResult.execution_path field for execution audit trail
  - Added JitoResult dataclass
"""

import base64
import json
import logging
import os
import random
import time
from dataclasses import dataclass, field
from typing import Optional

import requests  # kept for exceptions
from data.http_session import get_session
from eth_account import Account
from eth_account.messages import encode_defunct
from web3 import Web3

from config import settings
from config.chains import CHAINS

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────
FLASHBOTS_RELAY_URL = "https://relay.flashbots.net"
FLASHBOTS_PROTECT_RPC = "https://rpc.flashbots.net/fast"

JITO_BLOCK_ENGINE_URL = "https://mainnet.block-engine.jito.wtf/api/v1/bundles"
JITO_TIP_ACCOUNTS = [
    "96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5",
    "HFqU5x63VTqvQss8hp11i4wVV8bD44PvwucfZ2bU7gRe",
    "Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY",
    "ADaUMid9yfUytqMBgopwjb2DTLSokTSzL1zt6iGPaS49",
    "DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh",
    "ADuUkR4vqLUMWXxW9gh6D6L8pMSawimctcNZ5pGwDcEt",
    "DttWaMuVvTiduZRnguLF7jNxTgiMBZ1hyAumKUiL2KRL",
    "3AVi9Tg9Uo68tJfuvoKvqKNWKkC5wPdSSdeBnizKZ6jT",
]

# ─────────────────────────────────────────────────────────────────────────────
# Data Classes
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class FlashbotsResult:
    """Result of a Flashbots bundle or Protect RPC submission."""
    success: bool
    bundle_hash: Optional[str] = None
    block_number: Optional[int] = None
    tx_hash: Optional[str] = None
    error: Optional[str] = None
    simulation_passed: bool = False
    execution_path: str = "flashbots"


@dataclass
class JitoResult:
    """Result of a Jito bundle submission."""
    success: bool
    bundle_id: Optional[str] = None
    tx_signature: Optional[str] = None
    error: Optional[str] = None
    tip_lamports: int = 0


# ─────────────────────────────────────────────────────────────────────────────
# Flashbots — EIP-191 Request Signing (FIXED: was HMAC, now eth_account)
# ─────────────────────────────────────────────────────────────────────────────
def _sign_flashbots_request(body: str, signing_key: str) -> str:
    """
    Sign a Flashbots API request body using EIP-191 personal_sign.
    Flashbots authenticates via keccak256(body) signed with the signing key.
    Returns: "address:0xsignature" header value.
    """
    body_hash = Web3.keccak(text=body)
    message = encode_defunct(body_hash)
    signed = Account.sign_message(message, private_key=signing_key)
    signer_address = Account.from_key(signing_key).address
    return f"{signer_address}:{signed.signature.hex()}"


# ─────────────────────────────────────────────────────────────────────────────
# Flashbots — Bundle Simulation
# ─────────────────────────────────────────────────────────────────────────────
def _simulate_flashbots_bundle(
    signed_txs: list,
    target_block: int,
    signing_key: str,
) -> Optional[dict]:
    """Simulate a Flashbots bundle to check for reverts before submission."""
    sim_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "eth_callBundle",
        "params": [{
            "txs": signed_txs,
            "blockNumber": hex(target_block),
            "stateBlockNumber": "latest",
        }],
    }
    body = json.dumps(sim_payload)
    signature = _sign_flashbots_request(body, signing_key)
    headers = {
        "Content-Type": "application/json",
        "X-Flashbots-Signature": signature,
    }
    try:
        resp = get_session().post(FLASHBOTS_RELAY_URL, data=body, headers=headers, timeout=20)
        resp.raise_for_status()
        result = resp.json()
        if "error" in result:
            logger.warning(f"Flashbots simulation error: {result['error']}")
            return None
        return result.get("result")
    except Exception as e:
        logger.debug(f"Flashbots simulation failed: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Flashbots — Bundle Submission (Ethereum mainnet)
# ─────────────────────────────────────────────────────────────────────────────
def submit_flashbots_bundle(
    signed_txs: list,
    target_block: int,
    signing_key: str,
    simulate: bool = True,
) -> FlashbotsResult:
    """
    Submit a transaction bundle to the Flashbots relay (Ethereum mainnet).
    The bundle is completely invisible to the public mempool.
    """
    if not signing_key:
        return FlashbotsResult(success=False, error="FLASHBOTS_SIGNING_KEY not configured")

    if settings.IS_PAPER:
        logger.info(f"[PAPER] Flashbots bundle: {len(signed_txs)} txs -> block {target_block}")
        return FlashbotsResult(
            success=True,
            bundle_hash="0x" + "0" * 64,
            block_number=target_block,
            simulation_passed=True,
        )

    if simulate:
        sim_result = _simulate_flashbots_bundle(signed_txs, target_block, signing_key)
        if sim_result:
            logger.info(f"Flashbots simulation passed: {sim_result}")
        else:
            logger.warning("Flashbots simulation failed — submitting anyway (may revert)")

    bundle_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "eth_sendBundle",
        "params": [{
            "txs": signed_txs,
            "blockNumber": hex(target_block),
            "minTimestamp": 0,
            "maxTimestamp": int(time.time()) + 120,
        }],
    }
    body = json.dumps(bundle_payload)
    signature = _sign_flashbots_request(body, signing_key)
    headers = {
        "Content-Type": "application/json",
        "X-Flashbots-Signature": signature,
    }
    try:
        resp = get_session().post(FLASHBOTS_RELAY_URL, data=body, headers=headers, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        if "error" in result:
            return FlashbotsResult(success=False, error=f"Flashbots relay error: {result['error']}")
        bundle_hash = result.get("result", {}).get("bundleHash", "")
        logger.info(f"Flashbots bundle submitted: {bundle_hash} -> block {target_block}")
        return FlashbotsResult(
            success=True,
            bundle_hash=bundle_hash,
            block_number=target_block,
            simulation_passed=simulate,
        )
    except Exception as e:
        logger.error(f"Flashbots bundle submission error: {e}")
        return FlashbotsResult(success=False, error=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# Flashbots Protect RPC — Single-tx private relay (Base / Arbitrum / Ethereum)
# ─────────────────────────────────────────────────────────────────────────────
def submit_via_flashbots_protect(
    signed_raw_tx: str,
    rpc_url: str = FLASHBOTS_PROTECT_RPC,
) -> FlashbotsResult:
    """
    Submit a single signed transaction via Flashbots Protect RPC.
    Lightweight path for Base and Arbitrum — no bundle signing needed.
    The tx is forwarded to builders privately, bypassing the public mempool.
    """
    if settings.IS_PAPER:
        logger.info("[PAPER] Flashbots Protect RPC: simulated private tx submission")
        return FlashbotsResult(success=True, tx_hash="0x" + "0" * 64, execution_path="flashbots_protect")

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "eth_sendRawTransaction",
        "params": [signed_raw_tx],
    }
    try:
        resp = get_session().post(rpc_url, json=payload, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        if "error" in result:
            return FlashbotsResult(
                success=False,
                error=f"Flashbots Protect error: {result['error']}",
                execution_path="flashbots_protect",
            )
        tx_hash = result.get("result", "")
        logger.info(f"Flashbots Protect tx submitted: {tx_hash[:16]}...")
        return FlashbotsResult(success=True, tx_hash=tx_hash, execution_path="flashbots_protect")
    except Exception as e:
        logger.error(f"Flashbots Protect RPC error: {e}")
        return FlashbotsResult(success=False, error=str(e), execution_path="flashbots_protect")


# ─────────────────────────────────────────────────────────────────────────────
# execute_via_flashbots — Full EVM Flashbots execution (called by executor.py)
# ─────────────────────────────────────────────────────────────────────────────
def execute_via_flashbots(
    w3: Web3,
    private_key: str,
    signing_key: str,
    to: str,
    data: str,
    value: int,
    gas: int,
    chain_id: int = 1,
    chain: str = "ethereum",
    gem_score: Optional[float] = None,
) -> FlashbotsResult:
    """
    Execute a transaction via Flashbots MEV protection.

    Routing:
      - Ethereum (chain_id=1): Full Flashbots bundle -> relay.flashbots.net
        Targets next 3 blocks with 15% gas escalation per attempt.
      - Base / Arbitrum:       Flashbots Protect RPC (single-tx private relay)
        No bundle signing needed.

    Args:
        w3:          Web3 instance connected to the target chain
        private_key: Wallet private key (from env var — NEVER hardcoded)
        signing_key: FLASHBOTS_SIGNING_KEY (auth key — separate from wallet)
        to:          Contract address to call
        data:        Encoded calldata (hex string)
        value:       ETH/native value in wei
        gas:         Gas limit
        chain_id:    EVM chain ID
        chain:       Chain name string (ethereum, base, arbitrum, etc.)
    """
    if settings.IS_PAPER:
        logger.info(f"[PAPER] Flashbots tx: chain={chain} to={to[:10]}... value={value/1e18:.4f}")
        return FlashbotsResult(
            success=True,
            tx_hash="0x" + "0" * 64,
            simulation_passed=True,
            execution_path="flashbots_paper",
        )

    try:
        account = Account.from_key(private_key)

        # EIP-1559 gas pricing
        try:
            latest = w3.eth.get_block("latest")
            base_fee = latest.get("baseFeePerGas", w3.eth.gas_price)
            priority_fee = Web3.to_wei(5 if chain == "ethereum" else 2, "gwei")
            max_fee = int(base_fee * 1.25) + priority_fee
            base_gas_price = int(base_fee * 1.25)  # Fallback for non-1559 code paths
            use_eip1559 = True
        except Exception:
            base_gas_price = w3.eth.gas_price
            priority_fee = Web3.to_wei(2, "gwei")
            max_fee = base_gas_price
            use_eip1559 = False

        nonce = w3.eth.get_transaction_count(account.address, "pending")

        # Base / Arbitrum: Flashbots Protect RPC
        if chain in ("base", "arbitrum"):
            # Apply Institutional Priority Fee multiplier if score >= 90
            p_fee = priority_fee
            m_fee = max_fee
            b_gas = base_gas_price
            
            if gem_score is not None and gem_score >= 90.0:
                p_fee = int(priority_fee * 3.0)
                m_fee = int(max_fee * 3.0)
                b_gas = int(base_gas_price * 3.0)
                logger.info(
                    f"🚀 INSTITUTIONAL PRIORITY SNIPE (EVM/Protect): gem_score={gem_score:.1f} ≥ 90! "
                    f"Escalating priority fee x3.0 for immediate next-block inclusion."
                )

            tx = {
                "from": account.address,
                "to": Web3.to_checksum_address(to),
                "data": data,
                "value": value,
                "gas": gas,
                "nonce": nonce,
                "chainId": chain_id,
            }
            if use_eip1559:
                tx["maxFeePerGas"] = m_fee
                tx["maxPriorityFeePerGas"] = p_fee
            else:
                tx["gasPrice"] = b_gas
            signed = account.sign_transaction(tx)
            raw_tx = signed.raw_transaction.hex()
            if not raw_tx.startswith("0x"):
                raw_tx = "0x" + raw_tx
            result = submit_via_flashbots_protect(raw_tx)
            if result.success:
                result.tx_hash = signed.hash.hex()
                logger.info(
                    f"Flashbots Protect ({chain}): {result.tx_hash[:16]}... "
                    f"| gas={gas:,} | value={value/1e18:.4f}"
                )
            return result

        # Ethereum: Full Flashbots bundle with multi-block retry + gas escalation
        if not signing_key:
            logger.warning("FLASHBOTS_SIGNING_KEY not set — falling back to Protect RPC")
            tx = {
                "from": account.address,
                "to": Web3.to_checksum_address(to),
                "data": data,
                "value": value,
                "gas": gas,
                "nonce": nonce,
                "chainId": chain_id,
            }
            if use_eip1559:
                tx["maxFeePerGas"] = max_fee
                tx["maxPriorityFeePerGas"] = priority_fee
            else:
                tx["gasPrice"] = base_gas_price
            signed = account.sign_transaction(tx)
            raw_tx = signed.raw_transaction.hex()
            if not raw_tx.startswith("0x"):
                raw_tx = "0x" + raw_tx
            return submit_via_flashbots_protect(raw_tx)

        current_block = w3.eth.block_number

        for attempt, target_block in enumerate(range(current_block + 1, current_block + 4)):
            gas_mult = 1.0 + (0.15 * attempt)
            
            # Apply Institutional Priority Fee multiplier if score >= 90 on Ethereum bundle
            score_mult = 1.0
            if gem_score is not None and gem_score >= 90.0:
                score_mult = 3.0
                if attempt == 0:
                    logger.info(
                        f"🚀 INSTITUTIONAL PRIORITY SNIPE (EVM/Bundle): gem_score={gem_score:.1f} ≥ 90! "
                        f"Escalating Ethereum bundle priority fee x3.0 for immediate block inclusion."
                    )

            tx = {
                "from": account.address,
                "to": Web3.to_checksum_address(to),
                "data": data,
                "value": value,
                "gas": int(gas * gas_mult),
                "nonce": nonce,
                "chainId": chain_id,
            }
            if use_eip1559:
                tx["maxFeePerGas"] = int(max_fee * gas_mult * score_mult)
                tx["maxPriorityFeePerGas"] = int(priority_fee * gas_mult * score_mult)
            else:
                tx["gasPrice"] = int(base_gas_price * gas_mult * score_mult)

            signed = account.sign_transaction(tx)
            raw_tx = signed.raw_transaction.hex()
            if not raw_tx.startswith("0x"):
                raw_tx = "0x" + raw_tx

            result = submit_flashbots_bundle(
                signed_txs=[raw_tx],
                target_block=target_block,
                signing_key=signing_key,
                simulate=(attempt == 0),
            )
            if result.success:
                result.tx_hash = signed.hash.hex()
                result.execution_path = "flashbots_bundle"
                logger.info(
                    f"Flashbots bundle submitted: {result.tx_hash[:16]}... "
                    f"-> block {target_block} | gas x{gas_mult:.2f}"
                )
                return result
            logger.warning(f"Flashbots bundle attempt {attempt+1}/3 failed: {result.error}")

        return FlashbotsResult(
            success=False,
            error="Flashbots bundle failed after 3 block attempts",
            execution_path="flashbots_bundle",
        )

    except Exception as e:
        logger.error(f"execute_via_flashbots error: {e}", exc_info=True)
        return FlashbotsResult(success=False, error=str(e), execution_path="flashbots_error")


# ─────────────────────────────────────────────────────────────────────────────
# Jito Bundle Submission (Solana)
# ─────────────────────────────────────────────────────────────────────────────
def submit_jito_bundle(
    signed_transactions_b64: list,
    tip_lamports: int = 10_000,
) -> JitoResult:
    """
    Submit a Jito bundle to the Jito Block Engine.
    Bypasses the public Solana mempool — no sandwich attacks possible.

    Args:
        signed_transactions_b64: List of base64-encoded signed VersionedTransactions
        tip_lamports:            Tip amount in lamports (10,000 = ~$0.001 at $150 SOL)

    Returns:
        JitoResult with bundle_id or error
    """
    if settings.IS_PAPER:
        logger.info(f"[PAPER] Jito bundle: {len(signed_transactions_b64)} txs, tip={tip_lamports} lamports")
        return JitoResult(
            success=True,
            bundle_id="paper_jito_bundle_" + str(int(time.time())),
            tip_lamports=tip_lamports,
        )

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "sendBundle",
        "params": [signed_transactions_b64],
    }
    headers = {"Content-Type": "application/json"}

    # Optional: Jito auth keypair for higher rate limits
    jito_auth_key = os.getenv("JITO_AUTH_KEYPAIR", "")
    if jito_auth_key:
        try:
            import base58
            from solders.keypair import Keypair  # type: ignore
            auth_keypair = Keypair.from_bytes(base58.b58decode(jito_auth_key))
            body_bytes = json.dumps(payload).encode()
            auth_sig = auth_keypair.sign_message(body_bytes)
            headers["x-jito-auth"] = base64.b64encode(bytes(auth_sig)).decode()
            headers["x-jito-pubkey"] = str(auth_keypair.pubkey())
        except Exception as e:
            logger.debug(f"Jito auth signing failed (proceeding without auth): {e}")

    try:
        resp = get_session().post(JITO_BLOCK_ENGINE_URL, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        if "error" in result:
            err = result["error"]
            err_msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
            logger.error(f"Jito bundle error: {err_msg}")
            return JitoResult(success=False, error=err_msg)
        bundle_id = result.get("result", "")
        logger.info(f"Jito bundle submitted: {bundle_id} | tip={tip_lamports:,} lamports")
        return JitoResult(success=True, bundle_id=bundle_id, tip_lamports=tip_lamports)
    except requests.exceptions.HTTPError as e:
        logger.error(f"Jito HTTP error: {e.response.status_code} — {e.response.text[:200]}")
        return JitoResult(success=False, error=str(e))
    except Exception as e:
        logger.error(f"Jito bundle submission error: {e}")
        return JitoResult(success=False, error=str(e))


def execute_solana_via_jito(
    serialized_tx_b64: str,
    wallet_public_key: str,
    tip_lamports: int = 10_000,
) -> JitoResult:
    """
    Submit a pre-signed Solana transaction via Jito bundle for MEV protection.
    Wraps a single Jupiter swap transaction in a Jito bundle.

    Tip guidance:
      - Standard gem trade:      10,000 lamports (~$0.001)
      - High-conviction / busy:  50,000 lamports (~$0.005)
      - God Signal / snipe:     100,000 lamports (~$0.015)

    Args:
        serialized_tx_b64: Base64-encoded signed VersionedTransaction from Jupiter
        wallet_public_key: Wallet public key (for logging)
        tip_lamports:      Jito tip in lamports
    """
    if settings.IS_PAPER:
        logger.info(f"[PAPER] Jito execute: wallet={wallet_public_key[:8]}... tip={tip_lamports}")
        return JitoResult(
            success=True,
            bundle_id="paper_jito_" + str(int(time.time())),
            tip_lamports=tip_lamports,
        )

    logger.info(
        f"Submitting Jito bundle: wallet={wallet_public_key[:8]}... "
        f"tip={tip_lamports:,} lamports"
    )
    return submit_jito_bundle([serialized_tx_b64], tip_lamports=tip_lamports)


# ─────────────────────────────────────────────────────────────────────────────
# CoW Protocol Live Signing (Ethereum)
# ─────────────────────────────────────────────────────────────────────────────
COW_DOMAIN_SEPARATOR_MAINNET = "0xc078f884a2676e1345748b1feace7b0abee5d00ecadb6e574dcdd109a63e8943"
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
    sell_amount_wei: int,
    wallet_address: str,
    chain: str = "ethereum",
) -> Optional[dict]:
    """Get a price quote from the CoW Protocol API."""
    cow_url = settings.COW_API_URL
    payload = {
        "sellToken": sell_token,
        "buyToken": buy_token,
        "receiver": wallet_address,
        "sellAmountBeforeFee": str(sell_amount_wei),
        "from": wallet_address,
        "kind": "sell",
        "partiallyFillable": False,
        "sellTokenBalance": "erc20",
        "buyTokenBalance": "erc20",
    }
    try:
        resp = get_session().post(f"{cow_url}/api/v1/quote", json=payload, timeout=20)
        if resp.status_code in (200, 201):
            return resp.json()
        logger.warning(f"CoW quote failed: {resp.status_code} {resp.text[:200]}")
        return None
    except Exception as e:
        logger.error(f"CoW quote error: {e}")
        return None


def sign_cow_order(
    order: CowOrder,
    private_key: str,
    chain_id: int = 1,
) -> Optional[str]:
    """Sign a CoW Protocol order using EIP-712."""
    try:
        cow_settlement = "0x9008D19f58AAbD9eD0D60971565AA8510560ab41"
        domain = {
            "name": "Gnosis Protocol",
            "version": "v2",
            "chainId": chain_id,
            "verifyingContract": cow_settlement,
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
        account = Account.from_key(private_key)
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
    """Submit a signed CoW order to the CoW Protocol API. Returns order UID on success."""
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
        resp = get_session().post(f"{cow_url}/api/v1/orders", json=order_payload, timeout=20)
        if resp.status_code in (200, 201):
            order_uid = resp.json()
            logger.info(f"CoW order submitted: {order_uid}")
            return order_uid
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
    1. Get quote -> 2. Build order -> 3. Sign (EIP-712) -> 4. Submit to CoW API
    Returns order UID on success, None on failure.
    """
    if settings.IS_PAPER:
        logger.info(
            f"[PAPER] CoW order: {sell_token[:10]}... -> {buy_token[:10]}... "
            f"amount={sell_amount_wei/1e18:.4f}"
        )
        return "paper_order_uid_" + str(int(time.time()))

    quote_resp = get_cow_quote(sell_token, buy_token, sell_amount_wei, wallet_address, chain)
    if not quote_resp:
        logger.warning("CoW quote failed — cannot execute live order")
        return None

    quote = quote_resp.get("quote", {})
    buy_amount = int(quote.get("buyAmount", 0))
    fee_amount = int(quote.get("feeAmount", 0))
    if buy_amount <= 0:
        logger.warning("CoW quote returned zero buy amount")
        return None

    min_buy_amount = int(buy_amount * (1 - slippage_bps / 10000))
    order = CowOrder(
        sell_token=sell_token,
        buy_token=buy_token,
        receiver=wallet_address,
        sell_amount=sell_amount_wei - fee_amount,
        buy_amount=min_buy_amount,
        valid_to=int(time.time()) + 1800,
        fee_amount=fee_amount,
    )

    chain_config = CHAINS.get(chain)
    chain_id = chain_config.chain_id if chain_config else 1
    signature = sign_cow_order(order, private_key, chain_id)
    if not signature:
        logger.error("CoW order signing failed")
        return None

    order_uid = submit_cow_order(order, signature, chain)
    if order_uid:
        logger.info(
            f"CoW live order submitted: {order_uid} | "
            f"sell={sell_amount_wei/1e18:.4f} -> min_buy={min_buy_amount/1e18:.6f}"
        )
    return order_uid
