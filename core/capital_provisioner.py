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
# How much ETH to keep as gas reserve (never convert below this when going ETH->USDC)
GAS_RESERVE_ETH = float(os.getenv("PROVISION_GAS_RESERVE_ETH", "0.01"))
# Target amount of ETH to provision when gas is low
TARGET_GAS_ETH = float(os.getenv("PROVISION_TARGET_GAS_ETH", "0.05"))
# Trigger auto-gas if ETH drops below this
MIN_GAS_TRIGGER_ETH = float(os.getenv("PROVISION_MIN_GAS_TRIGGER", "0.02"))
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

def _send_1inch_tx(w3: Web3, account: Account, tx_data: dict, chain_id: int) -> bool:
    """Helper to estimate gas, sign and send a 1inch transaction."""
    nonce = w3.eth.get_transaction_count(account.address, "pending")
    gas_price = w3.eth.gas_price

    try:
        raw_tx = {
            "from": account.address,
            "to": Web3.to_checksum_address(tx_data["to"]),
            "data": tx_data["data"],
            "value": int(tx_data.get("value", 0)),
        }
        estimated_gas = w3.eth.estimate_gas(raw_tx)
        gas_limit = int(estimated_gas * 1.3)
    except Exception as e:
        logger.debug(f"Gas estimation failed: {e}. Using fallback gas limit.")
        gas_limit = int(tx_data.get("gas", 500_000))

    transaction = {
        "from": account.address,
        "to": Web3.to_checksum_address(tx_data["to"]),
        "data": tx_data["data"],
        "value": int(tx_data.get("value", 0)),
        "gas": gas_limit,
        "gasPrice": int(gas_price * 1.1),
        "nonce": nonce,
        "chainId": chain_id,
    }

    try:
        signed = account.sign_transaction(transaction)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=90)
        return receipt.status == 1
    except Exception as e:
        logger.error(f"Transaction failed: {e}")
        return False

def swap_usdc_to_eth(
    w3: Web3,
    chain_id: int,
    wallet_address: str,
    private_key: str,
    amount_usdc: float,
    chain_name: str,
) -> bool:
    """Execute a USDC → ETH swap (Auto-Gas) via 1inch on the specified chain."""
    api_key = settings.ONEINCH_API_KEY
    if not api_key:
        logger.error("Cannot provision: ONEINCH_API_KEY not set")
        return False

    usdc_addr = USDC_ADDRESSES.get(chain_name)
    if not usdc_addr:
        return False

    amount_wei = int(amount_usdc * 1e6)  # USDC has 6 decimals
    account = Account.from_key(private_key)
    headers = {"Authorization": f"Bearer {api_key}"}

    # 1. Check Allowance / Approve
    try:
        allowance_url = f"{settings.ONEINCH_API_URL}/{chain_id}/approve/allowance"
        allowance_params = {"tokenAddress": usdc_addr, "walletAddress": wallet_address}
        allowance_resp = get_session().get(allowance_url, headers=headers, params=allowance_params, timeout=10).json()
        
        if int(allowance_resp.get("allowance", 0)) < amount_wei:
            logger.info(f"Approving USDC on {chain_name} for 1inch router...")
            approve_url = f"{settings.ONEINCH_API_URL}/{chain_id}/approve/transaction"
            approve_params = {"tokenAddress": usdc_addr, "amount": str(amount_wei)}
            approve_tx = get_session().get(approve_url, headers=headers, params=approve_params, timeout=10).json()
            if not _send_1inch_tx(w3, account, approve_tx, chain_id):
                logger.error(f"❌ PROVISION: USDC Approval failed on {chain_name}")
                return False
            time.sleep(3) # Wait for RPC to catch up
    except Exception as e:
        logger.error(f"Failed to handle approval: {e}")
        return False

    # 2. Swap
    url = f"{settings.ONEINCH_API_URL}/{chain_id}/swap"
    params = {
        "src": usdc_addr,
        "dst": NATIVE_TOKEN,
        "amount": str(amount_wei),
        "from": wallet_address,
        "slippage": "1",
        "disableEstimate": "false",
    }
    
    try:
        swap_resp = get_session().get(url, headers=headers, params=params, timeout=20)
        if swap_resp.status_code != 200:
            logger.error(f"1inch swap API error ({swap_resp.status_code}): {swap_resp.text[:200]}")
            return False
        swap_data = swap_resp.json().get("tx")
        if not swap_data or "to" not in swap_data:
            return False

        if _send_1inch_tx(w3, account, swap_data, chain_id):
            logger.info(f"✅ AUTO-GAS: Swapped {amount_usdc:.2f} USDC → ETH on {chain_name}")
            return True
        else:
            logger.error(f"❌ AUTO-GAS: Swap reverted on {chain_name}")
            return False
    except Exception as e:
        logger.error(f"Auto-gas swap failed on {chain_name}: {e}")
        return False

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
    account = Account.from_key(private_key)

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
        swap_data = resp.json().get("tx")
        if not swap_data or "to" not in swap_data:
            return False

        if _send_1inch_tx(w3, account, swap_data, chain_id):
            logger.info(f"✅ PROVISION: Swapped {amount_eth:.4f} ETH → USDC on {chain_name}")
            return True
        else:
            logger.error(f"❌ PROVISION: Swap reverted on {chain_name}")
            return False
    except Exception as e:
        logger.error(f"Provision swap failed on {chain_name}: {e}")
        return False


def provision_wallet(chain_name: str, wallet_address: str, private_key: str) -> bool:
    """
    Check if wallet needs USDC provisioning or Native Gas provisioning on the given chain.
    If Gas < MIN_GAS_TRIGGER_ETH, swap USDC -> ETH.
    If USDC < TARGET_USDC_BALANCE, swap ETH -> USDC.
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

    usdc_bal = get_usdc_balance(w3, wallet_address, chain_name)
    eth_bal = float(w3.from_wei(w3.eth.get_balance(Web3.to_checksum_address(wallet_address)), "ether"))
    eth_price = get_eth_price_usd()

    provisioned_anything = False

    # ── CHECK 1: Auto-Gas Provisioning (USDC → ETH) ──
    if eth_bal < MIN_GAS_TRIGGER_ETH:
        logger.warning(f"⚠️ {chain_name}: Low gas detected! {eth_bal:.4f} < {MIN_GAS_TRIGGER_ETH} ETH")
        needed_eth = TARGET_GAS_ETH - eth_bal
        needed_usdc_for_gas = needed_eth * eth_price * 1.02 # 2% slippage buffer
        
        # Do we have enough USDC to convert to gas? We need to leave at least some USDC for trading if possible,
        # but gas is strictly necessary to do anything. We will convert up to the needed amount.
        if usdc_bal > 5.0:  # Need at least $5 to bother swapping
            convert_usdc = min(needed_usdc_for_gas, usdc_bal)
            logger.info(
                f"🔄 AUTO-GAS {chain_name}: Converting {convert_usdc:.2f} USDC → ETH "
                f"| target_gas={TARGET_GAS_ETH:.4f} ETH | current gas={eth_bal:.4f} ETH"
            )
            success = swap_usdc_to_eth(w3, chain_config.chain_id, wallet_address, private_key, convert_usdc, chain_name)
            if success:
                provisioned_anything = True
                # Refresh balances after swap
                time.sleep(5)
                usdc_bal = get_usdc_balance(w3, wallet_address, chain_name)
                eth_bal = float(w3.from_wei(w3.eth.get_balance(Web3.to_checksum_address(wallet_address)), "ether"))
        else:
            logger.warning(f"⚠️ {chain_name}: Cannot auto-gas. Not enough USDC ({usdc_bal:.2f})")

    # ── CHECK 2: Capital Provisioning (ETH → USDC) ──
    if usdc_bal < TARGET_USDC_BALANCE:
        available_eth = eth_bal - GAS_RESERVE_ETH
        if available_eth > 0.001:
            needed_usdc = TARGET_USDC_BALANCE - usdc_bal
            needed_eth = (needed_usdc / eth_price) * 1.02
            max_eth_for_usd = MAX_CONVERT_USD / eth_price
            convert_eth = min(needed_eth, available_eth, max_eth_for_usd)
            
            if convert_eth >= 0.001:
                expected_usdc = convert_eth * eth_price
                logger.info(
                    f"🔄 PROVISIONING {chain_name}: Converting {convert_eth:.4f} ETH "
                    f"(~${expected_usdc:.0f}) → USDC | current USDC=${usdc_bal:.2f} | "
                    f"target=${TARGET_USDC_BALANCE:.0f}"
                )
                success = swap_eth_to_usdc(w3, chain_config.chain_id, wallet_address, private_key, convert_eth, chain_name)
                if success:
                    provisioned_anything = True
        else:
            logger.debug(f"⚠️ {chain_name}: Not enough ETH for USDC provisioning (bal={eth_bal:.4f}, reserve={GAS_RESERVE_ETH})")
    else:
        logger.info(f"💰 {chain_name}: USDC=${usdc_bal:.2f} ≥ target=${TARGET_USDC_BALANCE:.0f} — no USDC provisioning needed")

    return provisioned_anything


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
