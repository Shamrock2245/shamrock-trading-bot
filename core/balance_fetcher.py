"""
core/balance_fetcher.py — Multi-chain wallet balance fetcher.

Dynamically fetches current ETH (native token) and ERC-20 token balances
for all three managed wallets across Ethereum, Base, Arbitrum, Polygon,
and BSC using web3.py with public RPC endpoints.

Usage:
    from core.balance_fetcher import BalanceFetcher
    fetcher = BalanceFetcher()
    balances = await fetcher.fetch_all_balances()
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from web3 import Web3
from web3.exceptions import ContractLogicError

from config.chains import CHAINS, ChainConfig
from config.wallets import WALLETS, WalletConfig

logger = logging.getLogger(__name__)

# Minimal ERC-20 ABI — only what we need for balance checks
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "symbol",
        "outputs": [{"name": "", "type": "string"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "name",
        "outputs": [{"name": "", "type": "string"}],
        "type": "function",
    },
]

# Common tokens to check on each chain (address per chain)
TOKENS_TO_CHECK: dict[str, dict[str, str]] = {
    "USDC": {
        "ethereum": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        "base":     "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
        "arbitrum": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
        "polygon":  "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",
        "bsc":      "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d",
    },
    "USDT": {
        "ethereum": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
        "arbitrum": "0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9",
        "polygon":  "0xc2132D05D31c914a87C6611C10748AEb04B58e8F",
        "bsc":      "0x55d398326f99059fF775485246999027B3197955",
    },
    "WETH": {
        "ethereum": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
        "base":     "0x4200000000000000000000000000000000000006",
        "arbitrum": "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
        "polygon":  "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619",
    },
}


class BalanceFetcher:
    """
    Fetches native token (ETH/MATIC/BNB) and ERC-20 balances for all
    managed wallets across all configured chains.
    """

    def __init__(self):
        self._web3_cache: dict[str, Web3] = {}

    def _get_web3(self, chain: ChainConfig) -> Optional[Web3]:
        """
        Get a Web3 connection for a chain, with automatic fallback to
        secondary RPC if the primary is unavailable.
        """
        if chain.name in self._web3_cache:
            return self._web3_cache[chain.name]

        for rpc_url in [chain.rpc_url, chain.rpc_fallback]:
            if not rpc_url:
                continue
            try:
                w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 10}))
                if w3.is_connected():
                    self._web3_cache[chain.name] = w3
                    logger.debug(f"Connected to {chain.name} via {rpc_url}")
                    return w3
            except Exception as e:
                logger.warning(f"RPC {rpc_url} failed for {chain.name}: {e}")

        logger.error(f"All RPCs failed for {chain.name}")
        return None

    def _fetch_native_balance(
        self, w3: Web3, address: str, chain: ChainConfig
    ) -> dict:
        """Fetch native token (ETH/MATIC/BNB) balance."""
        try:
            checksum_addr = Web3.to_checksum_address(address)
            raw_balance = w3.eth.get_balance(checksum_addr)
            balance_eth = float(w3.from_wei(raw_balance, "ether"))
            return {
                "token": chain.native_token,
                "address": "native",
                "balance_raw": str(raw_balance),
                "balance": balance_eth,
                "decimals": 18,
                "is_native": True,
            }
        except Exception as e:
            logger.error(f"Native balance error on {chain.name} for {address}: {e}")
            return {
                "token": chain.native_token,
                "address": "native",
                "balance": 0.0,
                "error": str(e),
                "is_native": True,
            }

    def _fetch_token_balance(
        self, w3: Web3, wallet_address: str, token_address: str,
        token_symbol: str, chain: ChainConfig
    ) -> Optional[dict]:
        """Fetch ERC-20 token balance."""
        try:
            checksum_wallet = Web3.to_checksum_address(wallet_address)
            checksum_token = Web3.to_checksum_address(token_address)
            contract = w3.eth.contract(address=checksum_token, abi=ERC20_ABI)

            raw_balance = contract.functions.balanceOf(checksum_wallet).call()
            if raw_balance == 0:
                return None  # Skip zero balances

            decimals = contract.functions.decimals().call()
            balance = raw_balance / (10 ** decimals)

            return {
                "token": token_symbol,
                "address": token_address,
                "balance_raw": str(raw_balance),
                "balance": balance,
                "decimals": decimals,
                "is_native": False,
            }
        except ContractLogicError:
            return None
        except Exception as e:
            logger.debug(f"Token {token_symbol} balance error on {chain.name}: {e}")
            return None

    def fetch_wallet_chain_balances(
        self, wallet: WalletConfig, chain_name: str
    ) -> dict:
        """
        Fetch all balances for one wallet on one chain.
        Returns a dict with native + token balances.
        """
        chain = CHAINS[chain_name]
        w3 = self._get_web3(chain)

        result = {
            "wallet_alias": wallet.alias,
            "wallet_address": wallet.address,
            "chain": chain.name,
            "chain_id": chain.chain_id,
            "tokens": [],
            "connected": w3 is not None,
            "error": None,
        }

        if not w3:
            result["error"] = f"Could not connect to {chain.name} RPC"
            return result

        # Native balance
        native = self._fetch_native_balance(w3, wallet.address, chain)
        result["tokens"].append(native)

        # ERC-20 token balances
        for symbol, chain_addresses in TOKENS_TO_CHECK.items():
            if chain_name in chain_addresses:
                token_data = self._fetch_token_balance(
                    w3, wallet.address,
                    chain_addresses[chain_name],
                    symbol, chain
                )
                if token_data:
                    result["tokens"].append(token_data)

        return result

    async def fetch_all_balances(self) -> dict:
        """
        Fetch balances for ALL wallets across ALL their configured chains.
        Runs chain fetches concurrently per wallet.
        Returns a structured dict ready for JSON serialization.
        """
        loop = asyncio.get_event_loop()
        output = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "wallets": {},
            "summary": {},
        }

        for wallet_key, wallet in WALLETS.items():
            wallet_data = {
                "alias": wallet.alias,
                "address": wallet.address,
                "role": wallet.role,
                "chains": {},
                "total_native_eth_equivalent": 0.0,
            }

            # Fetch each chain (run in thread pool since web3.py is sync)
            tasks = []
            for chain_name in wallet.chains:
                tasks.append(
                    loop.run_in_executor(
                        None,
                        self.fetch_wallet_chain_balances,
                        wallet, chain_name
                    )
                )

            chain_results = await asyncio.gather(*tasks, return_exceptions=True)

            for chain_name, result in zip(wallet.chains, chain_results):
                if isinstance(result, Exception):
                    wallet_data["chains"][chain_name] = {"error": str(result)}
                else:
                    wallet_data["chains"][chain_name] = result

            output["wallets"][wallet_key] = wallet_data

        # Build summary
        output["summary"] = self._build_summary(output["wallets"])
        return output

    def _build_summary(self, wallets: dict) -> dict:
        """Build a high-level summary of all balances."""
        summary = {
            "total_wallets": len(wallets),
            "total_chains_monitored": len(CHAINS),
            "wallet_summaries": {},
        }

        for wallet_key, wallet_data in wallets.items():
            native_totals = {}
            token_totals = {}

            for chain_name, chain_data in wallet_data.get("chains", {}).items():
                if "error" in chain_data and not chain_data.get("tokens"):
                    continue
                for token in chain_data.get("tokens", []):
                    symbol = token.get("token", "UNKNOWN")
                    balance = token.get("balance", 0.0)
                    if balance > 0:
                        if token.get("is_native"):
                            native_totals[f"{symbol} ({chain_name})"] = round(balance, 6)
                        else:
                            key = f"{symbol} ({chain_name})"
                            token_totals[key] = round(balance, 4)

            summary["wallet_summaries"][wallet_key] = {
                "alias": wallet_data["alias"],
                "address": wallet_data["address"],
                "native_balances": native_totals,
                "token_balances": token_totals,
                "has_private_key": WALLETS[wallet_key].has_private_key,
            }

        return summary


async def fetch_and_print_balances() -> dict:
    """Convenience function: fetch all balances and print a formatted summary."""
    fetcher = BalanceFetcher()
    print("\n🔍 Fetching balances for all wallets across all chains...")
    balances = await fetcher.fetch_all_balances()

    print(f"\n{'='*60}")
    print(f"☘️  SHAMROCK TRADING BOT — WALLET BALANCES")
    print(f"{'='*60}")
    print(f"Timestamp: {balances['timestamp']}\n")

    for wallet_key, wallet_data in balances["wallets"].items():
        print(f"📍 {wallet_data['alias']} ({wallet_data['address'][:10]}...)")
        print(f"   Role: {wallet_data['role']}")

        for chain_name, chain_data in wallet_data["chains"].items():
            if chain_data.get("error") and not chain_data.get("tokens"):
                print(f"   ⚠️  {chain_name}: {chain_data['error']}")
                continue
            print(f"   ├─ {chain_data.get('chain', chain_name)}:")
            for token in chain_data.get("tokens", []):
                balance = token.get("balance", 0)
                symbol = token.get("token", "?")
                if balance > 0:
                    print(f"   │   {symbol}: {balance:.6f}")
        print()

    return balances


if __name__ == "__main__":
    result = asyncio.run(fetch_and_print_balances())
    # Save to output/balances.json
    import os
    os.makedirs("output", exist_ok=True)
    with open("output/balances.json", "w") as f:
        json.dump(result, f, indent=2)
    print(f"✅ Balances saved to output/balances.json")
