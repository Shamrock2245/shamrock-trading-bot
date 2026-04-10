"""
core/gas_manager.py — Gas Token Auto-Replenishment System

Monitors native gas token balances across all active wallets and chains.
When gas drops below a threshold, automatically swaps a small amount of
USDC → native token (ETH, BNB, MATIC, SOL, AVAX) to ensure the bot
can always execute trades.

Runs at the top of each scan cycle via `check_and_replenish_gas()`.

Design principles:
  - Only swap when USDC balance is sufficient (don't drain trading capital)
  - Only replenish to a target level (don't over-buy gas)
  - Cooldown per wallet+chain to prevent spam
  - Full logging for auditability
  - Graceful failure — never blocks the main loop
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from config import settings
from config.chains import CHAINS, ChainConfig
from config.wallets import WalletConfig, get_active_trading_wallets

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Configuration (env-overridable)
# ─────────────────────────────────────────────────────────────────────────────

# Enable/disable the gas manager
GAS_MANAGER_ENABLED = os.getenv("GAS_MANAGER_ENABLED", "true").lower() == "true"

# Minimum gas balance thresholds per native token (below this → replenish)
# These are conservative: enough for ~20-50 transactions on each chain
GAS_MIN_THRESHOLDS: dict[str, float] = {
    "ETH": float(os.getenv("GAS_MIN_ETH", "0.003")),      # ~$5 — covers ~10 swaps on Ethereum
    "BNB": float(os.getenv("GAS_MIN_BNB", "0.005")),      # ~$3 — covers ~50 swaps on BSC
    "MATIC": float(os.getenv("GAS_MIN_MATIC", "1.0")),     # ~$0.85 — covers ~200 swaps on Polygon
    "SOL": float(os.getenv("GAS_MIN_SOL", "0.01")),        # ~$1.75 — covers ~100 swaps on Solana
    "AVAX": float(os.getenv("GAS_MIN_AVAX", "0.05")),      # ~$1.75 — covers ~50 swaps on Avalanche
}

# Target gas balance after replenishment (fill up to this level)
GAS_TARGET_THRESHOLDS: dict[str, float] = {
    "ETH": float(os.getenv("GAS_TARGET_ETH", "0.01")),     # ~$17 — good for ~30+ swaps
    "BNB": float(os.getenv("GAS_TARGET_BNB", "0.02")),     # ~$12 — good for ~200 swaps
    "MATIC": float(os.getenv("GAS_TARGET_MATIC", "5.0")),   # ~$4.25 — good for ~1000 swaps
    "SOL": float(os.getenv("GAS_TARGET_SOL", "0.05")),      # ~$8.75 — good for ~500 swaps
    "AVAX": float(os.getenv("GAS_TARGET_AVAX", "0.15")),    # ~$5.25 — good for ~150 swaps
}

# Minimum USDC balance to keep (don't drain below this for gas)
GAS_MIN_USDC_RESERVE = float(os.getenv("GAS_MIN_USDC_RESERVE", "10.0"))

# Maximum USDC to spend on a single gas replenishment
GAS_MAX_REPLENISH_USD = float(os.getenv("GAS_MAX_REPLENISH_USD", "20.0"))

# Cooldown between replenishment attempts per wallet+chain (seconds)
GAS_REPLENISH_COOLDOWN = int(os.getenv("GAS_REPLENISH_COOLDOWN", "600"))  # 10 minutes


# ─────────────────────────────────────────────────────────────────────────────
# State tracking
# ─────────────────────────────────────────────────────────────────────────────

_STATE_FILE = Path(os.environ.get(
    "GAS_MANAGER_STATE",
    os.path.join(os.path.dirname(__file__), "..", "output", "gas_manager_state.json"),
))

# In-memory cooldown tracker: {f"{wallet_alias}_{chain}": last_replenish_timestamp}
_cooldowns: dict[str, float] = {}


@dataclass
class GasReplenishRecord:
    """Record of a gas replenishment event."""
    wallet_alias: str
    chain: str
    native_token: str
    usdc_spent: float
    native_received: float
    gas_before: float
    gas_after: float
    timestamp: float
    tx_hash: str = ""
    success: bool = True
    error: str = ""


def _load_state() -> list[dict]:
    """Load replenishment history from disk."""
    try:
        if _STATE_FILE.exists():
            with open(_STATE_FILE) as f:
                return json.load(f)
    except Exception as e:
        logger.debug(f"Gas manager: failed to load state: {e}")
    return []


def _save_state(records: list[dict]) -> None:
    """Persist replenishment history to disk (keep last 100 records)."""
    try:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_STATE_FILE, "w") as f:
            json.dump(records[-100:], f, indent=2)
    except Exception as e:
        logger.debug(f"Gas manager: failed to save state: {e}")


def _is_on_cooldown(wallet_alias: str, chain: str) -> bool:
    """Check if a wallet+chain pair is on cooldown."""
    key = f"{wallet_alias}_{chain}"
    last_attempt = _cooldowns.get(key, 0)
    return (time.time() - last_attempt) < GAS_REPLENISH_COOLDOWN


def _set_cooldown(wallet_alias: str, chain: str) -> None:
    """Set cooldown for a wallet+chain pair."""
    _cooldowns[f"{wallet_alias}_{chain}"] = time.time()


# ─────────────────────────────────────────────────────────────────────────────
# Core logic
# ─────────────────────────────────────────────────────────────────────────────

def check_gas_levels(
    wallets: list[WalletConfig] | None = None,
) -> list[dict]:
    """
    Check gas levels across all active wallets and chains.

    Returns a list of {wallet, chain, native_token, balance, threshold, needs_gas}
    entries for monitoring/dashboard display.
    """
    from core.wallet_router import get_native_balance

    if wallets is None:
        wallets = get_active_trading_wallets()

    results = []
    for wallet in wallets:
        for chain_name in wallet.chains:
            chain_config = CHAINS.get(chain_name)
            if not chain_config:
                continue

            native_token = chain_config.native_token
            threshold = GAS_MIN_THRESHOLDS.get(native_token, 0.01)

            # Get the right address for this chain
            if chain_config.is_solana:
                if not wallet.solana_address:
                    continue
                address = wallet.solana_address
            else:
                address = wallet.address

            try:
                balance = get_native_balance(address, chain_name)
            except Exception:
                balance = 0.0

            results.append({
                "wallet": wallet.alias,
                "chain": chain_name,
                "native_token": native_token,
                "balance": balance,
                "threshold": threshold,
                "target": GAS_TARGET_THRESHOLDS.get(native_token, threshold * 3),
                "needs_gas": balance < threshold,
            })

    return results


def _replenish_gas_evm(
    wallet: WalletConfig,
    chain_name: str,
    chain_config: ChainConfig,
    usdc_amount: float,
) -> Optional[GasReplenishRecord]:
    """
    Swap USDC → native gas token on an EVM chain via 1inch.

    Uses the same 1inch infrastructure the executor uses for trading,
    but swaps USDC → native (ETH address 0xeee...).
    """
    import requests
    from web3 import Web3

    native_address = "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"
    usdc_address = chain_config.usdc_address

    if not usdc_address:
        logger.warning(f"Gas manager: no USDC address configured for {chain_name}")
        return None

    if not settings.ONEINCH_API_KEY:
        logger.warning("Gas manager: 1inch API key required for gas replenishment")
        return None

    private_key = wallet.private_key
    if not private_key:
        logger.warning(f"Gas manager: no private key for {wallet.alias}")
        return None

    amount_wei = int(usdc_amount * 1e6)  # USDC has 6 decimals

    try:
        # Get Web3 connection
        from core.executor import TradeExecutor
        executor = TradeExecutor()
        w3 = executor._get_web3(chain_config)
        if not w3:
            return None

        # Ensure USDC approval for 1inch
        if not executor._ensure_token_approval(
            w3, chain_config.chain_id, usdc_address,
            wallet.address, private_key, amount_wei,
        ):
            logger.error(f"Gas manager: USDC approval failed for {wallet.alias} on {chain_name}")
            return None

        # Get swap data from 1inch
        url = f"{settings.ONEINCH_API_URL}/{chain_config.chain_id}/swap"
        headers = {"Authorization": f"Bearer {settings.ONEINCH_API_KEY}"}
        swap_params = {
            "src": usdc_address,
            "dst": native_address,
            "amount": str(amount_wei),
            "from": wallet.address,
            "slippage": "3",  # 3% slippage — we're not price-sensitive for gas
            "disableEstimate": "false",
        }

        resp = requests.get(url, headers=headers, params=swap_params, timeout=20)
        if resp.status_code != 200:
            logger.error(f"Gas manager: 1inch swap failed ({resp.status_code}): {resp.text[:200]}")
            return None

        swap_data = resp.json()
        tx = swap_data.get("tx", {})
        dst_amount = int(swap_data.get("dstAmount", 0))

        if settings.IS_PAPER:
            native_received = dst_amount / (10 ** chain_config.native_token_decimals)
            logger.info(
                f"⛽ GAS REPLENISH (paper): {wallet.alias} on {chain_name} | "
                f"${usdc_amount:.2f} USDC → {native_received:.6f} {chain_config.native_token}"
            )
            return GasReplenishRecord(
                wallet_alias=wallet.alias,
                chain=chain_name,
                native_token=chain_config.native_token,
                usdc_spent=usdc_amount,
                native_received=native_received,
                gas_before=0.0,
                gas_after=native_received,
                timestamp=time.time(),
                tx_hash="paper_mode",
                success=True,
            )

        # Live execution
        from eth_account import Account
        account = Account.from_key(private_key)
        nonce = executor._get_nonce(w3, account.address)

        transaction = {
            "from": account.address,
            "to": Web3.to_checksum_address(tx["to"]),
            "data": tx.get("data", "0x"),
            "value": int(tx.get("value", 0)),
            "gas": int(int(tx.get("gas", 300000)) * 1.2),
            "gasPrice": int(w3.eth.gas_price * 1.1),
            "nonce": nonce,
            "chainId": chain_config.chain_id,
        }

        signed = account.sign_transaction(transaction)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

        native_received = dst_amount / (10 ** chain_config.native_token_decimals)

        if receipt.status == 1:
            logger.info(
                f"⛽ GAS REPLENISHED: {wallet.alias} on {chain_name} | "
                f"${usdc_amount:.2f} USDC → {native_received:.6f} {chain_config.native_token} | "
                f"tx={tx_hash.hex()[:16]}..."
            )
            return GasReplenishRecord(
                wallet_alias=wallet.alias,
                chain=chain_name,
                native_token=chain_config.native_token,
                usdc_spent=usdc_amount,
                native_received=native_received,
                gas_before=0.0,
                gas_after=native_received,
                timestamp=time.time(),
                tx_hash=tx_hash.hex(),
                success=True,
            )
        else:
            logger.error(f"⛽ Gas replenish tx reverted: {tx_hash.hex()}")
            executor._release_nonce(account.address)
            return GasReplenishRecord(
                wallet_alias=wallet.alias,
                chain=chain_name,
                native_token=chain_config.native_token,
                usdc_spent=0.0,
                native_received=0.0,
                gas_before=0.0,
                gas_after=0.0,
                timestamp=time.time(),
                tx_hash=tx_hash.hex(),
                success=False,
                error="Transaction reverted",
            )

    except Exception as e:
        logger.error(f"⛽ Gas replenish error ({wallet.alias} on {chain_name}): {e}")
        return GasReplenishRecord(
            wallet_alias=wallet.alias,
            chain=chain_name,
            native_token=chain_config.native_token,
            usdc_spent=0.0,
            native_received=0.0,
            gas_before=0.0,
            gas_after=0.0,
            timestamp=time.time(),
            success=False,
            error=str(e),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point — call from main loop
# ─────────────────────────────────────────────────────────────────────────────

def check_and_replenish_gas() -> list[GasReplenishRecord]:
    """
    Check all active wallets across all chains and replenish gas where needed.

    Call this at the top of each scan cycle. It will:
    1. Check gas balance for every wallet+chain combo
    2. If below threshold AND not on cooldown AND USDC available → swap
    3. Log every action and persist state

    Returns list of GasReplenishRecord for the cycle (may be empty).
    """
    if not GAS_MANAGER_ENABLED:
        return []

    from core.wallet_router import get_native_balance, get_usdc_balance

    wallets = get_active_trading_wallets()
    records: list[GasReplenishRecord] = []
    history = _load_state()

    for wallet in wallets:
        for chain_name in wallet.chains:
            chain_config = CHAINS.get(chain_name)
            if not chain_config:
                continue

            # Skip Solana for now — gas replenishment uses a different path
            if chain_config.is_solana:
                continue

            native_token = chain_config.native_token
            min_threshold = GAS_MIN_THRESHOLDS.get(native_token, 0.01)
            target = GAS_TARGET_THRESHOLDS.get(native_token, min_threshold * 3)

            # Get current gas balance
            try:
                gas_balance = get_native_balance(wallet.address, chain_name)
            except Exception:
                gas_balance = 0.0

            if gas_balance >= min_threshold:
                continue  # Gas is fine

            # Check cooldown
            wallet_key = wallet.alias.lower().replace(" ", "_")
            if _is_on_cooldown(wallet_key, chain_name):
                logger.debug(
                    f"⛽ Gas low on {wallet.alias}/{chain_name} "
                    f"({gas_balance:.6f} {native_token}) but on cooldown"
                )
                continue

            # Check USDC balance on this chain
            try:
                usdc_balance = get_usdc_balance(wallet.address, chain_name)
            except Exception:
                usdc_balance = 0.0

            if usdc_balance < GAS_MIN_USDC_RESERVE:
                logger.warning(
                    f"⛽ Gas low on {wallet.alias}/{chain_name} "
                    f"({gas_balance:.6f} {native_token}) but USDC too low "
                    f"(${usdc_balance:.2f} < ${GAS_MIN_USDC_RESERVE:.2f} reserve)"
                )
                continue

            # Calculate how much USDC to swap
            # We need (target - current) worth of native token
            from core.wallet_router import get_native_price_usd
            native_price = get_native_price_usd(native_token)
            deficit_native = target - gas_balance
            deficit_usd = deficit_native * native_price
            # Clamp: don't spend more than max or more than (usdc - reserve)
            usdc_to_swap = min(
                deficit_usd * 1.1,  # 10% buffer for slippage
                GAS_MAX_REPLENISH_USD,
                usdc_balance - GAS_MIN_USDC_RESERVE,
            )

            if usdc_to_swap < 1.0:
                logger.debug(f"⛽ Gas deficit too small to replenish on {chain_name}")
                continue

            logger.info(
                f"⛽ GAS LOW: {wallet.alias} on {chain_name} — "
                f"{gas_balance:.6f} {native_token} < {min_threshold} threshold | "
                f"Replenishing ${usdc_to_swap:.2f} USDC → {native_token}"
            )

            # Execute the swap
            record = _replenish_gas_evm(wallet, chain_name, chain_config, usdc_to_swap)
            if record:
                record.gas_before = gas_balance
                records.append(record)
                history.append(asdict(record))
                _set_cooldown(wallet_key, chain_name)

                if record.success:
                    logger.info(
                        f"⛽ ✅ Gas replenished: {wallet.alias}/{chain_name} | "
                        f"{gas_balance:.6f} → +{record.native_received:.6f} {native_token}"
                    )
                else:
                    logger.error(
                        f"⛽ ❌ Gas replenish failed: {wallet.alias}/{chain_name} | {record.error}"
                    )

    if history:
        _save_state(history)

    return records


def get_gas_status_summary() -> str:
    """Return a human-readable gas status summary for logging."""
    try:
        levels = check_gas_levels()
        if not levels:
            return "No wallets configured"

        low = [l for l in levels if l["needs_gas"]]
        if not low:
            return f"⛽ All {len(levels)} wallet/chain combos have sufficient gas"

        lines = [f"⛽ {len(low)}/{len(levels)} wallet/chain combos need gas:"]
        for l in low:
            lines.append(
                f"  ⚠️  {l['wallet']}/{l['chain']}: "
                f"{l['balance']:.6f} {l['native_token']} (min: {l['threshold']})"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"⛽ Gas check error: {e}"
