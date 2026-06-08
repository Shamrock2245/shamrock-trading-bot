"""
Capital Provisioner — Auto-converts native ETH → USDC on L2 chains
when USDC balance is below trading threshold.

Runs at bot startup and periodically to ensure wallets always have
enough USDC to execute trades on Base and Arbitrum.
"""
import os
import time
import logging
from web3 import Web3
from eth_account import Account
from data.http_session import get_session
from config import settings
from config.chains import CHAINS

logger = logging.getLogger(__name__)

# Minimum USDC we want in each wallet for trading
TARGET_USDC_BALANCE = float(os.getenv("PROVISION_TARGET_USDC", "100.0"))
# How much ETH to keep as gas reserve (never convert below this)
GAS_RESERVE_ETH = float(os.getenv("PROVISION_GAS_RESERVE_ETH", "0.01"))
# Max single conversion (never convert more than this in one go)
MAX_CONVERT_USD = float(os.getenv("PROVISION_MAX_CONVERT_USD", "500.0"))

NATIVE_TOKEN = "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"

# USDC addresses per chain
USDC_ADDRESSES = {
    "base": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    "arbitrum": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
}

ERC20_BALANCE_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function",
    }
]


def get_usdc_balance(w3: Web3, wallet_address: str, chain: str) -> float:
    """Fetch USDC balance for a wallet on a chain."""
    usdc_addr = USDC_ADDRESSES.get(chain)
    if not usdc_addr:
        return 0.0
    try:
        contract = w3.eth.contract(
            address=Web3.to_checksum_address(usdc_addr), abi=ERC20_BALANCE_ABI
        )
        raw = contract.functions.balanceOf(
            Web3.to_checksum_address(wallet_address)
        ).call()
        return raw / 1e6  # USDC has 6 decimals
    except Exception as e:
        logger.warning(f"USDC balance check failed on {chain}: {e}")
        return 0.0


def get_eth_price_usd() -> float:
    """Fetch current ETH price from CoinGecko."""
    try:
        resp = get_session().get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": "ethereum", "vs_currencies": "usd"},
            timeout=10,
        )
        return float(resp.json()["ethereum"]["usd"])
    except Exception:
        return 2500.0  # Safe fallback


def swap_eth_to_usdc(
    w3: Web3,
    chain_id: int,
    wallet_address: str,
    private_key: str,
    amount_eth: float,
    chain_name: str,
) -> bool:
    """Execute an ETH → USDC swap via 1inch on the specified chain."""
    api_key = settings.ONEINCH_API_KEY
    if not api_key:
        logger.error("Cannot provision: ONEINCH_API_KEY not set")
        return False

    usdc_addr = USDC_ADDRESSES.get(chain_name)
    if not usdc_addr:
        logger.error(f"No USDC address configured for {chain_name}")
        return False

    amount_wei = int(amount_eth * 1e18)

    # 1. Get swap data from 1inch
    url = f"{settings.ONEINCH_API_URL}/{chain_id}/swap"
    headers = {"Authorization": f"Bearer {api_key}"}
    params = {
        "src": NATIVE_TOKEN,
        "dst": usdc_addr,
        "amount": str(amount_wei),
        "from": wallet_address,
        "slippage": "1",  # 1% slippage for stablecoin conversion
        "disableEstimate": "false",
    }

    try:
        resp = get_session().get(url, headers=headers, params=params, timeout=20)
        if resp.status_code != 200:
            logger.error(
                f"1inch swap API error ({resp.status_code}): {resp.text[:200]}"
            )
            return False
        swap_data = resp.json()
    except Exception as e:
        logger.error(f"1inch API call failed: {e}")
        return False

    tx_data = swap_data.get("tx", swap_data)
    if "to" not in tx_data:
        logger.error(f"Invalid swap response: no 'to' field")
        return False

    # 2. Build transaction
    account = Account.from_key(private_key)
    nonce = w3.eth.get_transaction_count(account.address, "pending")
    gas_price = w3.eth.gas_price

    # Use 1inch gas estimate or estimate ourselves
    try:
        raw_tx = {
            "from": account.address,
            "to": Web3.to_checksum_address(tx_data["to"]),
            "data": tx_data["data"],
            "value": int(tx_data.get("value", amount_wei)),
        }
        estimated_gas = w3.eth.estimate_gas(raw_tx)
        gas_limit = int(estimated_gas * 1.3)
    except Exception:
        gas_limit = int(tx_data.get("gas", 300_000))

    transaction = {
        "from": account.address,
        "to": Web3.to_checksum_address(tx_data["to"]),
        "data": tx_data["data"],
        "value": int(tx_data.get("value", amount_wei)),
        "gas": gas_limit,
        "gasPrice": int(gas_price * 1.1),
        "nonce": nonce,
        "chainId": chain_id,
    }

    # 3. Sign and send
    try:
        signed = account.sign_transaction(transaction)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=90)

        if receipt.status == 1:
            logger.info(
                f"✅ PROVISION: Swapped {amount_eth:.4f} ETH → USDC on {chain_name} | "
                f"tx={tx_hash.hex()[:16]}..."
            )
            return True
        else:
            logger.error(
                f"❌ PROVISION: Swap reverted on {chain_name} | tx={tx_hash.hex()[:16]}..."
            )
            return False
    except Exception as e:
        logger.error(f"Provision swap failed on {chain_name}: {e}")
        return False


def provision_wallet(chain_name: str, wallet_address: str, private_key: str) -> bool:
    """
    Check if wallet needs USDC provisioning on the given chain.
    If USDC < target, convert just enough ETH → USDC to reach the target.
    """
    chain_config = CHAINS.get(chain_name)
    if not chain_config:
        return False

    rpc_url = chain_config.rpc_url
    if not rpc_url:
        return False

    try:
        w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 15}))
        if not w3.is_connected():
            logger.warning(f"Cannot connect to {chain_name} RPC for provisioning")
            return False
    except Exception as e:
        logger.warning(f"Web3 init failed for {chain_name}: {e}")
        return False

    # Check current USDC balance
    usdc_bal = get_usdc_balance(w3, wallet_address, chain_name)
    if usdc_bal >= TARGET_USDC_BALANCE:
        logger.info(
            f"💰 {chain_name}: USDC=${usdc_bal:.2f} ≥ target=${TARGET_USDC_BALANCE:.0f} — no provisioning needed"
        )
        return True

    # Check ETH balance
    eth_bal = float(w3.from_wei(w3.eth.get_balance(Web3.to_checksum_address(wallet_address)), "ether"))
    available_eth = eth_bal - GAS_RESERVE_ETH
    if available_eth <= 0.001:
        logger.warning(
            f"⚠️ {chain_name}: Not enough ETH for provisioning "
            f"(bal={eth_bal:.4f}, reserve={GAS_RESERVE_ETH})"
        )
        return False

    # Calculate how much USDC we need
    needed_usdc = TARGET_USDC_BALANCE - usdc_bal
    eth_price = get_eth_price_usd()

    # Convert needed USDC to ETH amount (with 2% buffer for slippage)
    needed_eth = (needed_usdc / eth_price) * 1.02

    # Cap at available ETH and max conversion
    max_eth_for_usd = MAX_CONVERT_USD / eth_price
    convert_eth = min(needed_eth, available_eth, max_eth_for_usd)

    if convert_eth < 0.001:
        logger.info(f"Conversion amount too small on {chain_name}: {convert_eth:.6f} ETH")
        return False

    expected_usdc = convert_eth * eth_price
    logger.info(
        f"🔄 PROVISIONING {chain_name}: Converting {convert_eth:.4f} ETH "
        f"(~${expected_usdc:.0f}) → USDC | current USDC=${usdc_bal:.2f} | "
        f"target=${TARGET_USDC_BALANCE:.0f} | ETH bal={eth_bal:.4f}"
    )

    return swap_eth_to_usdc(
        w3, chain_config.chain_id, wallet_address, private_key, convert_eth, chain_name
    )


def provision_all_wallets():
    """
    Run provisioning across all wallets on Base and Arbitrum.
    Called at startup and periodically by the bot.
    """
    logger.info("💰 Capital Provisioner: checking wallet USDC levels...")

    wallets = [
        ("Primary", os.getenv("WALLET_ADDRESS_PRIMARY"), os.getenv("WALLET_PRIVATE_KEY_PRIMARY")),
        ("Wallet B", os.getenv("WALLET_ADDRESS_B"), os.getenv("WALLET_PRIVATE_KEY_B")),
    ]

    chains = ["base", "arbitrum"]
    provisioned = 0

    for wallet_name, address, pk in wallets:
        if not address or not pk:
            continue
        for chain in chains:
            try:
                result = provision_wallet(chain, address, pk)
                if result:
                    provisioned += 1
            except Exception as e:
                logger.error(f"Provision error for {wallet_name} on {chain}: {e}")

    logger.info(f"💰 Capital Provisioner complete: {provisioned} wallets checked/provisioned")
    return provisioned
