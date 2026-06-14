#!/usr/bin/env python3
"""
scripts/deploy_flash_arb_receiver.py — Deploy FlashArbReceiver to all EVM chains
=================================================================================
Compiles contracts/FlashArbReceiver.sol with solc 0.8.20, deploys to each
configured chain, and writes the resulting contract addresses back to the .env
file on the Hetzner VPS (or local .env if running locally).

Usage:
    python3 scripts/deploy_flash_arb_receiver.py [--chains ethereum base arbitrum polygon bsc avalanche]
    python3 scripts/deploy_flash_arb_receiver.py --chains base arbitrum  # deploy subset only

Requirements:
    pip install py-solc-x web3 eth-account python-dotenv

Environment variables required (in .env):
    WALLET_PRIVATE_KEY_PRIMARY — deployer wallet private key
    ETH_RPC_URL, BASE_RPC_URL, ARB_RPC_URL, POLYGON_RPC_URL, BSC_RPC_URL, AVAX_RPC_URL

Output:
    - Prints deployed addresses to stdout
    - Writes FLASH_ARB_RECEIVER_* vars to .env in-place
    - Writes contracts/FlashArbReceiver.abi and contracts/FlashArbReceiver.bin for reference
"""
from __future__ import annotations
import argparse
import json
import logging
import os
import re
import sys
import time
from pathlib import Path

# ── Dependency bootstrap ──────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
except ImportError:
    os.system("sudo pip3 install python-dotenv -q")
    from dotenv import load_dotenv

try:
    import solcx
except ImportError:
    os.system("sudo pip3 install py-solc-x -q")
    import solcx

try:
    from web3 import Web3
    from eth_account import Account
except ImportError:
    os.system("sudo pip3 install web3 eth-account -q")
    from web3 import Web3
    from eth_account import Account

# ── Paths ─────────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACT_PATH = REPO_ROOT / "contracts" / "FlashArbReceiver.sol"
ENV_PATH = REPO_ROOT / ".env"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("deploy_flash_arb")

# ── Chain config ──────────────────────────────────────────────────────────────
# Balancer V2 Vault — same address on all EVM chains
BALANCER_VAULT = "0xBA12222222228d8Ba445958a75a0704d566BF2C8"

CHAIN_CONFIG = {
    "ethereum": {
        "rpc_env": "ETH_RPC_URL",
        "rpc_default": "https://ethereum.publicnode.com",
        "chain_id": 1,
        "aave_pool": "0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2",
        "oneinch_router": "0x1111111254EEB25477B68fb85Ed929f73A960582",
        "env_var": "FLASH_ARB_RECEIVER_ETHEREUM",
        "explorer": "https://etherscan.io/address/",
        "gas_price_gwei": 20,
    },
    "base": {
        "rpc_env": "BASE_RPC_URL",
        "rpc_default": "https://mainnet.base.org",
        "chain_id": 8453,
        "aave_pool": "0xA238Dd80C259a72e81d7e4664a9801593F98d1c5",
        "oneinch_router": "0x1111111254EEB25477B68fb85Ed929f73A960582",
        "env_var": "FLASH_ARB_RECEIVER_BASE",
        "explorer": "https://basescan.org/address/",
        "gas_price_gwei": 1,
    },
    "arbitrum": {
        "rpc_env": "ARB_RPC_URL",
        "rpc_default": "https://arb1.arbitrum.io/rpc",
        "chain_id": 42161,
        "aave_pool": "0x794a61358D6845594F94dc1DB02A252b5b4814aD",
        "oneinch_router": "0x1111111254EEB25477B68fb85Ed929f73A960582",
        "env_var": "FLASH_ARB_RECEIVER_ARBITRUM",
        "explorer": "https://arbiscan.io/address/",
        "gas_price_gwei": 1,
    },
    "polygon": {
        "rpc_env": "POLYGON_RPC_URL",
        "rpc_default": "https://polygon-rpc.com",
        "chain_id": 137,
        "aave_pool": "0x794a61358D6845594F94dc1DB02A252b5b4814aD",
        "oneinch_router": "0x1111111254EEB25477B68fb85Ed929f73A960582",
        "env_var": "FLASH_ARB_RECEIVER_POLYGON",
        "explorer": "https://polygonscan.com/address/",
        "gas_price_gwei": 100,
    },
    "bsc": {
        "rpc_env": "BSC_RPC_URL",
        "rpc_default": "https://bsc-dataseed.binance.org",
        "chain_id": 56,
        "aave_pool": "0x6807dc923806fE8Fd134338EABCA509979a7e0cB",  # Aave V3 on BSC
        "oneinch_router": "0x1111111254EEB25477B68fb85Ed929f73A960582",
        "env_var": "FLASH_ARB_RECEIVER_BSC",
        "explorer": "https://bscscan.com/address/",
        "gas_price_gwei": 3,
    },
    "avalanche": {
        "rpc_env": "AVAX_RPC_URL",
        "rpc_default": "https://api.avax.network/ext/bc/C/rpc",
        "chain_id": 43114,
        "aave_pool": "0x794a61358D6845594F94dc1DB02A252b5b4814aD",  # Aave V3 on Avalanche
        "oneinch_router": "0x1111111254EEB25477B68fb85Ed929f73A960582",
        "env_var": "FLASH_ARB_RECEIVER_AVALANCHE",
        "explorer": "https://snowtrace.io/address/",
        "gas_price_gwei": 25,
    },
}

# ── Compiler ──────────────────────────────────────────────────────────────────

def compile_contract() -> tuple[str, str]:
    """Compile FlashArbReceiver.sol and return (abi_json, bytecode_hex)."""
    log.info("Compiling FlashArbReceiver.sol with solc 0.8.20...")
    installed = solcx.get_installed_solc_versions()
    target = solcx.install_solc("0.8.20") if "0.8.20" not in [str(v) for v in installed] else "0.8.20"
    solcx.set_solc_version("0.8.20")

    source = CONTRACT_PATH.read_text()
    compiled = solcx.compile_source(
        source,
        output_values=["abi", "bin"],
        solc_version="0.8.20",
        optimize=True,
        optimize_runs=200,
    )

    # Key format: "<stdin>:ContractName"
    contract_key = next(k for k in compiled if "FlashArbReceiver" in k)
    abi = compiled[contract_key]["abi"]
    bytecode = compiled[contract_key]["bin"]

    # Save artifacts for reference
    abi_path = REPO_ROOT / "contracts" / "FlashArbReceiver.abi"
    bin_path = REPO_ROOT / "contracts" / "FlashArbReceiver.bin"
    abi_path.write_text(json.dumps(abi, indent=2))
    bin_path.write_text(bytecode)
    log.info(f"Artifacts saved: {abi_path}, {bin_path}")

    return json.dumps(abi), bytecode


# ── Deployer ──────────────────────────────────────────────────────────────────

def deploy_to_chain(
    chain_name: str,
    cfg: dict,
    abi_json: str,
    bytecode: str,
    private_key: str,
) -> str | None:
    """Deploy FlashArbReceiver to a single chain. Returns deployed address or None on failure."""
    rpc_url = os.getenv(cfg["rpc_env"], cfg["rpc_default"])
    log.info(f"[{chain_name}] Connecting to {rpc_url}...")

    w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 30}))
    if not w3.is_connected():
        log.error(f"[{chain_name}] RPC connection failed — skipping")
        return None

    account = Account.from_key(private_key)
    deployer_addr = account.address
    balance_wei = w3.eth.get_balance(deployer_addr)
    balance_native = w3.from_wei(balance_wei, "ether")
    log.info(f"[{chain_name}] Deployer: {deployer_addr} | Balance: {balance_native:.6f}")

    if balance_wei == 0:
        log.error(f"[{chain_name}] Zero balance — cannot deploy. Fund {deployer_addr} with gas first.")
        return None

    abi = json.loads(abi_json)
    contract = w3.eth.contract(abi=abi, bytecode=bytecode)

    # Constructor args: (_balancerVault, _aavePool, _oneInchRouter)
    balancer_vault = Web3.to_checksum_address(BALANCER_VAULT)
    aave_pool = Web3.to_checksum_address(cfg["aave_pool"])
    oneinch_router = Web3.to_checksum_address(cfg["oneinch_router"])

    log.info(f"[{chain_name}] Deploying with args: balancer={balancer_vault}, aave={aave_pool}, 1inch={oneinch_router}")

    try:
        # Estimate gas
        gas_estimate = contract.constructor(balancer_vault, aave_pool, oneinch_router).estimate_gas(
            {"from": deployer_addr}
        )
        gas_limit = int(gas_estimate * 1.20)  # 20% buffer

        # Gas price — use current network price or configured minimum
        current_gas_wei = w3.eth.gas_price
        min_gas_wei = w3.to_wei(cfg["gas_price_gwei"], "gwei")
        gas_price_wei = max(current_gas_wei, min_gas_wei)

        gas_cost_eth = w3.from_wei(gas_limit * gas_price_wei, "ether")
        log.info(f"[{chain_name}] Gas estimate: {gas_estimate} | Limit: {gas_limit} | Price: {w3.from_wei(gas_price_wei, 'gwei'):.2f} gwei | Cost: {gas_cost_eth:.6f} ETH")

        nonce = w3.eth.get_transaction_count(deployer_addr)
        tx = contract.constructor(balancer_vault, aave_pool, oneinch_router).build_transaction({
            "from": deployer_addr,
            "gas": gas_limit,
            "gasPrice": gas_price_wei,
            "nonce": nonce,
            "chainId": cfg["chain_id"],
        })

        signed_tx = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        log.info(f"[{chain_name}] TX submitted: {tx_hash.hex()}")

        # Wait for receipt
        log.info(f"[{chain_name}] Waiting for confirmation...")
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)

        if receipt.status != 1:
            log.error(f"[{chain_name}] Deployment FAILED — tx reverted. Hash: {tx_hash.hex()}")
            return None

        contract_addr = receipt.contractAddress
        log.info(f"[{chain_name}] ✅ Deployed at: {contract_addr}")
        log.info(f"[{chain_name}] Explorer: {cfg['explorer']}{contract_addr}")
        return contract_addr

    except Exception as e:
        log.error(f"[{chain_name}] Deployment error: {e}")
        return None


# ── .env writer ───────────────────────────────────────────────────────────────

def update_env_file(env_var: str, value: str, env_path: Path) -> None:
    """Update or append a variable in the .env file."""
    if not env_path.exists():
        log.warning(f".env not found at {env_path} — creating new file")
        env_path.write_text(f"{env_var}={value}\n")
        return

    content = env_path.read_text()
    pattern = rf"^{re.escape(env_var)}=.*$"
    replacement = f"{env_var}={value}"

    if re.search(pattern, content, flags=re.MULTILINE):
        new_content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
    else:
        # Append
        new_content = content.rstrip("\n") + f"\n{replacement}\n"

    env_path.write_text(new_content)
    log.info(f"Updated .env: {env_var}={value}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Deploy FlashArbReceiver to EVM chains")
    parser.add_argument(
        "--chains",
        nargs="+",
        default=["ethereum", "base", "arbitrum", "polygon", "bsc", "avalanche"],
        choices=list(CHAIN_CONFIG.keys()),
        help="Chains to deploy to (default: all 6)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compile only — do not deploy",
    )
    args = parser.parse_args()

    # Load environment
    if ENV_PATH.exists():
        load_dotenv(ENV_PATH)
        log.info(f"Loaded .env from {ENV_PATH}")
    else:
        log.warning(f".env not found at {ENV_PATH} — relying on system environment")

    private_key = os.getenv("WALLET_PRIVATE_KEY_PRIMARY")
    if not private_key and not args.dry_run:
        log.error("WALLET_PRIVATE_KEY_PRIMARY not set in environment — cannot deploy")
        sys.exit(1)

    # Compile
    abi_json, bytecode = compile_contract()
    log.info(f"Bytecode size: {len(bytecode) // 2} bytes")

    if args.dry_run:
        log.info("Dry run — skipping deployment")
        return

    # Deploy
    deployed: dict[str, str] = {}
    failed: list[str] = []

    for chain_name in args.chains:
        cfg = CHAIN_CONFIG[chain_name]
        log.info(f"\n{'='*60}")
        log.info(f"Deploying to: {chain_name.upper()}")
        log.info(f"{'='*60}")

        # Check if already deployed
        existing = os.getenv(cfg["env_var"], "")
        if existing and existing != "":
            log.info(f"[{chain_name}] Already deployed at {existing} — skipping. Use --force to redeploy.")
            deployed[chain_name] = existing
            continue

        addr = deploy_to_chain(chain_name, cfg, abi_json, bytecode, private_key)
        if addr:
            deployed[chain_name] = addr
            update_env_file(cfg["env_var"], addr, ENV_PATH)
        else:
            failed.append(chain_name)

        # Brief pause between deployments to avoid nonce issues
        time.sleep(2)

    # Summary
    print("\n" + "="*60)
    print("DEPLOYMENT SUMMARY")
    print("="*60)
    for chain, addr in deployed.items():
        env_var = CHAIN_CONFIG[chain]["env_var"]
        explorer = CHAIN_CONFIG[chain]["explorer"]
        print(f"✅ {chain:<12} {addr}")
        print(f"   Explorer: {explorer}{addr}")
        print(f"   Env var:  {env_var}")
    if failed:
        print(f"\n❌ Failed chains: {', '.join(failed)}")
        print("   Check RPC connectivity and wallet balance on failed chains.")
    print("="*60)

    if deployed:
        print("\n📋 Add these to your Hetzner .env:")
        for chain, addr in deployed.items():
            env_var = CHAIN_CONFIG[chain]["env_var"]
            print(f"{env_var}={addr}")

    print("\n✅ Deploy complete. Restart the bot to activate flash arb on deployed chains.")
    print("   docker compose down && docker compose up -d")


if __name__ == "__main__":
    main()
