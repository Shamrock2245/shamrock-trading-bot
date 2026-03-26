"""
core/reconciliation.py — On-chain position reconciliation.

Compares the bot's internal position state (positions.json) against
on-chain swap history from Moralis Solana API. Flags mismatches
where the bot thinks it holds tokens but on-chain data disagrees.

Usage:
    from core.reconciliation import reconcile_solana_positions
    mismatches = reconcile_solana_positions("your_solana_wallet_address")

Currently Solana-only. EVM reconciliation can follow the same pattern
using Moralis Wallet API's get_wallet_token_balances().
"""

import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


def reconcile_solana_positions(wallet_address: str) -> List[Dict[str, Any]]:
    """
    Reconcile bot positions against on-chain Solana swap history.

    1. Fetch recent swaps via Moralis Solana get_wallet_swaps()
    2. Load open Solana positions from positions.json
    3. Compare: for each position, check if on-chain net flow is consistent
    4. Fire Slack alerts for mismatches

    Returns list of mismatch dicts:
        [{"token": str, "token_address": str, "expected": str,
          "onchain_status": str, "mismatch_type": str}]
    """
    if not wallet_address:
        logger.debug("Reconciliation skipped: no Solana wallet address")
        return []

    mismatches: List[Dict[str, Any]] = []

    # Load open Solana positions
    try:
        from core.position_monitor import load_positions
        all_positions = load_positions()
        sol_positions = [
            p for p in all_positions
            if p.get("chain") == "solana" and p.get("status") == "open"
        ]
    except Exception as e:
        logger.error(f"Reconciliation: failed to load positions: {e}")
        return []

    if not sol_positions:
        logger.debug("Reconciliation: no open Solana positions to check")
        return []

    # Fetch on-chain swap history
    try:
        from data.providers.moralis_solana import get_wallet_swaps
        swaps_data = get_wallet_swaps(wallet_address, limit=200)
        swaps = swaps_data.get("result", []) if isinstance(swaps_data, dict) else []
    except ImportError:
        logger.warning("Reconciliation: moralis_solana not available")
        return []
    except Exception as e:
        logger.error(f"Reconciliation: failed to fetch swaps: {e}")
        return []

    # Build net flow map: {token_mint_lower: net_tokens}
    # Positive = net buy, Negative = net sell
    net_flows: Dict[str, float] = {}
    for swap in swaps:
        # Moralis swap format: each swap has tokenIn/tokenOut with amounts
        for direction, sign in [("tokenIn", -1), ("tokenOut", 1)]:
            token = swap.get(direction, {})
            mint = (token.get("mint") or token.get("address") or "").lower()
            if not mint or mint == "so11111111111111111111111111111111111111111111":
                continue  # Skip native SOL
            try:
                amount = float(token.get("amount", 0))
                decimals = int(token.get("decimals", 0))
                human_amount = amount / (10 ** decimals) if decimals > 0 else amount
                net_flows[mint] = net_flows.get(mint, 0) + (sign * human_amount)
            except (ValueError, TypeError):
                continue

    # Compare positions against on-chain flows
    for pos in sol_positions:
        token_addr = (pos.get("token_address") or "").lower()
        token_sym = pos.get("token_symbol", "???")
        bot_qty = float(pos.get("quantity", 0))

        if not token_addr:
            continue

        onchain_net = net_flows.get(token_addr, None)

        if onchain_net is None:
            # Token never appeared in swap history — possible if bought before
            # our swap window. Not necessarily a mismatch.
            logger.debug(
                f"Reconciliation: {token_sym} ({token_addr[:8]}...) "
                f"not found in recent swap history"
            )
            continue

        # If on-chain net flow is <= 0, the wallet has net-sold this token
        if onchain_net <= 0 and bot_qty > 0:
            mismatch = {
                "token": token_sym,
                "token_address": token_addr,
                "expected": f"holding {bot_qty:.4f}",
                "onchain_status": f"net flow = {onchain_net:.4f} (sold out)",
                "mismatch_type": "phantom_position",
            }
            mismatches.append(mismatch)
            logger.warning(
                f"⚠️ POSITION MISMATCH: {token_sym} — "
                f"bot says holding {bot_qty:.4f} but on-chain net flow = {onchain_net:.4f}"
            )

    # Fire Slack alerts
    if mismatches:
        try:
            from notifications.slack import notify_alert
            lines = [
                f"• **{m['token']}**: {m['expected']} → {m['onchain_status']}"
                for m in mismatches
            ]
            notify_alert(
                "⚠️ Position Reconciliation Mismatch",
                f"{len(mismatches)} Solana position(s) don't match on-chain data:\n"
                + "\n".join(lines),
                level="warning",
            )
        except Exception as e:
            logger.error(f"Reconciliation: Slack alert failed: {e}")

    return mismatches


def reconcile_evm_positions(wallet_address: str, chain: str = "eth") -> List[Dict[str, Any]]:
    """
    Reconcile bot EVM positions against on-chain token balances via Moralis.
    Complements reconcile_solana_positions() for EVM chains.

    1. Fetch current token balances via moralis_wallet.get_wallet_token_balances()
    2. Load open EVM positions from positions.json
    3. Compare: for each position, check if on-chain balance > 0
    4. Fire Slack alerts for mismatches

    Returns list of mismatch dicts: [{token, address, chain, expected, onchain_status}]
    """
    mismatches: List[Dict[str, Any]] = []
    if not wallet_address:
        logger.debug("EVM reconciliation skipped: no wallet address")
        return mismatches
    try:
        from data.providers.moralis_wallet import get_wallet_token_balances
        from core.position_monitor import load_positions

        on_chain = get_wallet_token_balances(wallet_address, chain=chain)
        if not on_chain:
            logger.warning(f"EVM reconciliation: no on-chain data for {wallet_address} on {chain}")
            return mismatches

        held_addresses = set()
        for token in on_chain:
            addr = (token.get("token_address") or "").lower()
            balance = float(token.get("balance") or 0)
            if addr and balance > 0:
                held_addresses.add(addr)

        positions = load_positions()
        evm_positions = [
            p for p in positions
            if p.get("chain", "").lower() == chain.lower()
            and p.get("wallet_address", "").lower() == wallet_address.lower()
            and p.get("status") == "open"
        ]

        for pos in evm_positions:
            token_addr = (pos.get("token_address") or "").lower()
            token_sym = pos.get("token_symbol", token_addr[:8])
            if token_addr and token_addr not in held_addresses:
                mismatches.append({
                    "token": token_sym,
                    "address": token_addr,
                    "chain": chain,
                    "expected": "held",
                    "onchain_status": "zero_balance",
                })
                logger.warning(
                    f"EVM reconciliation mismatch: {token_sym} on {chain} "
                    f"— bot has open position but on-chain balance is 0"
                )

    except Exception as e:
        logger.error(f"EVM reconciliation error for {wallet_address} on {chain}: {e}")

    if mismatches:
        try:
            from notifications.slack import notify_alert
            lines = [
                f"• **{m['token']}** ({m['chain']}): {m['expected']} → {m['onchain_status']}"
                for m in mismatches
            ]
            notify_alert(
                "⚠️ EVM Position Reconciliation Mismatch",
                f"{len(mismatches)} EVM position(s) don't match on-chain data:\n"
                + "\n".join(lines),
                level="warning",
            )
        except Exception as e:
            logger.error(f"EVM reconciliation: Slack alert failed: {e}")

    return mismatches
