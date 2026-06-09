"""
core/sell_engine.py — Aggressive, Fault-Tolerant Sell Execution Engine

This module is the single source of truth for ALL sell-side execution.
It was created to fix the root causes of missed sells on Solana and Base:

ROOT CAUSES FIXED:
  1. Solana sells bypassed Jito — now uses Jito for ALL sells (not just buys)
  2. Slippage too tight on exits — dynamic slippage: 200bps → 500bps → 1500bps → 3000bps
  3. sell_qty=0 when quantity not registered — fallback to on-chain balance fetch
  4. Sell failures not retried aggressively — 4-attempt retry with escalating slippage
  5. EVM approval blocking exits — approval bypass for sell-side (token→native)
  6. No Jito on sell path — Jito now used for EVERY Solana sell
  7. Confluence gate blocking profitable exits — hard reversal override enforced

SELL PRIORITY ORDER:
  Solana: Jito bundle → standard RPC (3 retries, escalating slippage)
  EVM:    1inch direct (no approval needed for token→ETH) → Flashbots fallback

SLIPPAGE ESCALATION:
  Attempt 1: 200bps (2%)    — normal market
  Attempt 2: 500bps (5%)    — first retry
  Attempt 3: 1500bps (15%)  — urgent exit
  Attempt 4: 3000bps (30%)  — nuclear exit (rug/dump protection)
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


def _get_sol_price_usd() -> float:
    """Fetch live SOL/USD price; falls back to a safe estimate on failure."""
    try:
        from core.wallet_router import get_native_price_usd as _gnp
        price = _gnp("SOL")
        if price and price > 0:
            return price
    except Exception:
        pass
    logger.warning("SOL price lookup failed — using fallback $150 estimate for proceeds_usd")
    return 150.0  # FALLBACK: clearly labelled, only used when live fetch fails


def _get_eth_price_usd() -> float:
    """Fetch live ETH/USD price; falls back to a safe estimate on failure."""
    try:
        from core.wallet_router import get_native_price_usd as _gnp
        price = _gnp("ETH")
        if price and price > 0:
            return price
    except Exception:
        pass
    logger.warning("ETH price lookup failed — using fallback $3000 estimate for proceeds_usd")
    return 3000.0  # FALLBACK: clearly labelled, only used when live fetch fails

# Slippage escalation ladder (basis points)
SLIPPAGE_LADDER = [200, 500, 1500, 3000]

# Max sell attempts before giving up
MAX_SELL_ATTEMPTS = 4

# Jito tip for sells (higher than buys — exits are time-critical)
JITO_TIP_SELL_NORMAL = 100_000      # ~$0.014 — standard sell
JITO_TIP_SELL_URGENT = 500_000      # ~$0.070 — trailing stop / TP hit
JITO_TIP_SELL_NUCLEAR = 1_500_000   # ~$0.21  — hard stop / rug detection


@dataclass
class SellResult:
    """Result of a sell execution attempt."""
    success: bool
    tx_hash: Optional[str] = None
    amount_sold: float = 0.0
    proceeds_usd: float = 0.0
    slippage_bps_used: int = 0
    attempts: int = 0
    execution_path: str = ""
    error: Optional[str] = None
    gas_prohibitive: bool = False


def execute_sell_solana(
    token_mint: str,
    token_amount_units: int,
    wallet_public_key: str,
    wallet_private_key_env: str,
    urgency: str = "normal",      # "normal", "immediate", "nuclear"
    is_paper: bool = True,
    prior_failures: int = 0,
) -> SellResult:
    """
    Execute a Solana sell with Jito-first routing and aggressive retry logic.

    ALWAYS tries Jito first (unlike the old execute_solana_sell which used
    standard RPC only for sells). Falls back to standard RPC with escalating
    slippage on each retry.

    Args:
        token_mint: Token mint address to sell
        token_amount_units: Amount in token's smallest unit (lamports/decimals)
        wallet_public_key: Wallet public key
        wallet_private_key_env: Env var name holding the private key
        urgency: "normal" | "immediate" | "nuclear" — controls Jito tip + slippage
        is_paper: If True, simulate but don't broadcast

    Returns:
        SellResult with success status and execution details
    """
    from data.http_session import get_session
    from core.solana_executor import (
        get_jupiter_quote,
        get_jupiter_swap_transaction,
        sign_and_send_transaction,
        WSOL_MINT,
        USDC_MINT,
    )
    from core.mev_protection import execute_solana_via_jito
    from config import settings

    if token_amount_units <= 0:
        return SellResult(
            success=False,
            error=f"Invalid token_amount_units={token_amount_units} — cannot sell 0 tokens",
        )

    logger.info(
        f"{'📄 PAPER' if is_paper else '🔴 LIVE'} Solana SELL ENGINE: "
        f"{token_amount_units:,} units of {token_mint[:8]}... | urgency={urgency}"
    )


    # -- PAPER MODE SHORT-CIRCUIT ------------------------------------------
    # Return immediately in paper mode without making any Jupiter API calls.
    if is_paper:
        logger.info(
            f"PAPER: Simulated Solana sell {token_mint[:8]}... "
            f"({token_amount_units:,} units) | urgency={urgency}"
        )
        return SellResult(
            success=True,
            tx_hash="PAPER_TX",
            amount_sold=token_amount_units,
            proceeds_usd=0.0,
            slippage_bps_used=200,
            attempts=1,
            execution_path="paper",
        )

    # Jito tip based on urgency
    tip_map = {
        "normal":    JITO_TIP_SELL_NORMAL,
        "immediate": JITO_TIP_SELL_URGENT,
        "nuclear":   JITO_TIP_SELL_NUCLEAR,
    }
    jito_tip = tip_map.get(urgency, JITO_TIP_SELL_NORMAL)

    # Sell to SOL (native) — feeds directly back into next buy
    output_mint = WSOL_MINT

    # Skip lower tiers if we've failed before (escalate slippage across monitor cycles)
    start_tier = min(prior_failures, len(SLIPPAGE_LADDER) - 1)
    for attempt in range(start_tier, MAX_SELL_ATTEMPTS):
        slippage_bps = SLIPPAGE_LADDER[min(attempt, len(SLIPPAGE_LADDER) - 1)]

        logger.info(
            f"Solana sell attempt {attempt + 1}/{MAX_SELL_ATTEMPTS} | "
            f"slippage={slippage_bps}bps | tip={jito_tip:,} lamports"
        )

        # Get Jupiter quote
        quote = get_jupiter_quote(
            input_mint=token_mint,
            output_mint=output_mint,
            amount_lamports=token_amount_units,
            slippage_bps=slippage_bps,
        )

        if not quote:
            logger.warning(f"Jupiter quote failed (attempt {attempt + 1}) — retrying")
            time.sleep(1.0)
            continue

        out_amount = int(quote.get("outAmount", 0))
        price_impact = float(quote.get("priceImpactPct", 0))
        out_sol = out_amount / 1e9

        logger.info(
            f"Jupiter sell quote: {token_amount_units:,} tokens → {out_sol:.4f} SOL | "
            f"impact={price_impact:.2f}% | slippage={slippage_bps}bps"
        )

        # For sells: NEVER block on price impact — we must exit even rugs
        # If impact > 20%, escalate to wider slippage automatically
        if price_impact > 20.0 and slippage_bps < 3000:
            logger.warning(
                f"⚠️ Very high sell impact {price_impact:.1f}% — forcing 3000bps slippage"
            )
            slippage_bps = 3000
            quote = get_jupiter_quote(
                input_mint=token_mint,
                output_mint=output_mint,
                amount_lamports=token_amount_units,
                slippage_bps=slippage_bps,
            ) or quote

        if is_paper:
            logger.info(f"📄 PAPER: Simulated Solana sell {token_mint[:8]}... → {out_sol:.4f} SOL")
            return SellResult(
                success=True,
                tx_hash="PAPER_TX",
                amount_sold=token_amount_units,
                proceeds_usd=out_sol * _get_sol_price_usd(),  # Live SOL price (fallback: $150)
                slippage_bps_used=slippage_bps,
                attempts=attempt + 1,
                execution_path="paper",
            )

        # Get private key
        private_key = os.getenv(wallet_private_key_env)
        if not private_key:
            return SellResult(
                success=False,
                error=f"Private key not found in env var: {wallet_private_key_env}",
            )

        # Get swap transaction
        swap_tx = get_jupiter_swap_transaction(
            quote=quote,
            user_public_key=wallet_public_key,
        )

        if not swap_tx:
            logger.warning(f"Jupiter swap tx failed (attempt {attempt + 1}) — retrying")
            time.sleep(1.5)
            continue

        # ── Sign transaction ──────────────────────────────────────────────────
        signed_tx_b64 = None
        try:
            import base64
            import base58
            from solders.keypair import Keypair  # type: ignore
            from solders.transaction import VersionedTransaction  # type: ignore

            pk_bytes = base58.b58decode(private_key)
            keypair = Keypair.from_bytes(pk_bytes)
            tx_bytes = base64.b64decode(swap_tx)
            tx = VersionedTransaction.from_bytes(tx_bytes)
            try:
                signed_tx = VersionedTransaction(tx.message, [keypair])
            except (TypeError, Exception):
                sig = keypair.sign_message(bytes(tx.message))
                signed_tx = VersionedTransaction.populate(tx.message, [sig])
            signed_tx_b64 = base64.b64encode(bytes(signed_tx)).decode()
        except ImportError:
            logger.warning("solders not available — falling back to standard RPC submission")
        except Exception as sign_err:
            logger.error(f"Solana sign error (attempt {attempt + 1}): {sign_err}")

        # ── Jito bundle (PRIMARY path for sells — MEV protected, priority) ────
        if signed_tx_b64:
            try:
                jito_result = execute_solana_via_jito(
                    serialized_tx_b64=signed_tx_b64,
                    wallet_public_key=wallet_public_key,
                    tip_lamports=jito_tip,
                )
                if jito_result.success:
                    logger.info(
                        f"✅ Solana SELL via Jito: bundle={jito_result.bundle_id} | "
                        f"tip={jito_tip:,} | slippage={slippage_bps}bps | "
                        f"{token_mint[:8]}... → {out_sol:.4f} SOL"
                    )
                    return SellResult(
                        success=True,
                        tx_hash=jito_result.bundle_id or "jito_bundle_submitted",
                        amount_sold=token_amount_units,
                        proceeds_usd=out_sol * _get_sol_price_usd(),  # Live SOL price (fallback: $150)
                        slippage_bps_used=slippage_bps,
                        attempts=attempt + 1,
                        execution_path="jito",
                    )
                else:
                    logger.warning(
                        f"Jito sell bundle failed ({jito_result.error}) — "
                        f"falling back to standard RPC"
                    )
            except Exception as jito_err:
                logger.warning(f"Jito sell error: {jito_err} — falling back to standard RPC")

        # ── Standard RPC fallback ─────────────────────────────────────────────
        try:
            logger.info(f"Attempting standard RPC fallback for {token_mint[:8]}...")
            signature = sign_and_send_transaction(
                serialized_tx_b64=swap_tx,
                private_key_b58=private_key,
                rpc_url=settings.SOLANA_RPC_URL,
                max_retries=2,
            )
            if signature:
                logger.info(
                    f"✅ Solana SELL via standard RPC: {signature} | "
                    f"slippage={slippage_bps}bps | attempt={attempt + 1}"
                )
                return SellResult(
                    success=True,
                    tx_hash=signature,
                    amount_sold=token_amount_units,
                    proceeds_usd=out_sol * _get_sol_price_usd(),  # Live SOL price (fallback: $150)
                    slippage_bps_used=slippage_bps,
                    attempts=attempt + 1,
                    execution_path="standard_rpc",
                )
            else:
                logger.warning(
                    f"Standard RPC sell failed (attempt {attempt + 1}) — "
                    f"will retry with wider slippage"
                )
        except Exception as rpc_err:
            logger.error(f"Standard RPC sell error (attempt {attempt + 1}): {rpc_err}")

        # Exponential backoff before retry
        wait = 2.0 * (attempt + 1)
        logger.info(f"Waiting {wait:.0f}s before retry...")
        time.sleep(wait)

    # All attempts exhausted
    logger.error(
        f"❌ ALL SELL ATTEMPTS FAILED for {token_mint[:8]}... | "
        f"tried {MAX_SELL_ATTEMPTS} attempts with slippage up to "
        f"{SLIPPAGE_LADDER[min(MAX_SELL_ATTEMPTS - 1, len(SLIPPAGE_LADDER) - 1)]}bps"
    )
    return SellResult(
        success=False,
        attempts=MAX_SELL_ATTEMPTS,
        error=f"All {MAX_SELL_ATTEMPTS} sell attempts failed",
    )


# Low-gas L2 chains where the gas economics guard is unnecessary
_LOW_GAS_CHAINS = frozenset({"base", "arbitrum", "polygon", "avalanche", "bsc"})


def execute_sell_evm(
    token_address: str,
    token_amount_wei: int,
    chain: str,
    wallet,
    urgency: str = "normal",
    is_paper: bool = True,
    prior_failures: int = 0,
    position_value_usd: float = 0,
) -> SellResult:
    """
    Execute an EVM sell with aggressive retry and approval bypass.

    FIXES (v2 — May 2026):
      1. Always fetches on-chain balanceOf() — stored quantity drifts from
         actual balance due to float→int rounding, causing "Not enough balance"
      2. Waits for approval tx confirmation before retrying swap
      3. Detects balance mismatch errors and auto-retries with real amount

    Args:
        token_address: Token contract address to sell
        token_amount_wei: Amount in wei (token smallest unit)
        chain: Chain name (e.g., "base", "ethereum")
        wallet: WalletConfig object
        urgency: "normal" | "immediate" | "nuclear"
        is_paper: If True, simulate but don't broadcast

    Returns:
        SellResult with success status and execution details
    """
    from config.chains import CHAINS
    from data.http_session import get_session
    from config import settings

    if token_amount_wei <= 0:
        return SellResult(
            success=False,
            error=f"Invalid token_amount_wei={token_amount_wei} — cannot sell 0 tokens",
        )

    # ── FIX #1: Always use on-chain balance for EVM sells ─────────────────
    # The stored remaining_quantity → int conversion drifts by a few wei,
    # causing 1inch to reject with "Not enough balance".
    if not is_paper:
        try:
            from web3 import Web3
            wallet_addr = wallet.address or ""
            on_chain_bal = get_evm_token_balance(wallet_addr, token_address, chain)
            if on_chain_bal > 0:
                if on_chain_bal != token_amount_wei:
                    logger.info(
                        f"🔧 Balance correction: stored={token_amount_wei} → "
                        f"on-chain={on_chain_bal} (Δ={on_chain_bal - token_amount_wei})"
                    )
                token_amount_wei = on_chain_bal
            elif on_chain_bal == 0:
                logger.warning(
                    f"⚠️ On-chain balance is 0 for {token_address[:10]}... — "
                    f"token may already be sold or is a honeypot"
                )
                return SellResult(
                    success=False,
                    error=f"On-chain balance is 0 — nothing to sell",
                )
        except Exception as bal_err:
            logger.warning(f"On-chain balance fetch failed, using stored amount: {bal_err}")

    logger.info(
        f"{'📄 PAPER' if is_paper else '🔴 LIVE'} EVM SELL ENGINE: "
        f"{token_amount_wei} wei of {token_address[:10]}... on {chain} | urgency={urgency}"
    )

    chain_config = CHAINS.get(chain)
    if not chain_config:
        return SellResult(success=False, error=f"Unknown chain: {chain}")

    # ── GAS ECONOMICS GUARD ───────────────────────────────────────────────
    # On expensive L1 chains (Ethereum mainnet), skip sells where gas would
    # eat >25% of the position value. L2s (Base, Arb, etc.) are exempt.
    if not is_paper and chain not in _LOW_GAS_CHAINS and position_value_usd > 0:
        try:
            w3_gas = _get_web3(chain_config)
            if w3_gas:
                gas_price_wei = w3_gas.eth.gas_price
                gas_price_gwei = gas_price_wei / 1e9
                eth_price_usd = _get_eth_price_usd()
                est_gas_cost_usd = 300_000 * (gas_price_gwei * 1e-9) * eth_price_usd
                if est_gas_cost_usd > position_value_usd * 0.25:
                    logger.warning(
                        f"⛽ Gas cost prohibitive: ~${est_gas_cost_usd:.2f} gas vs "
                        f"${position_value_usd:.2f} position ({est_gas_cost_usd / position_value_usd:.0%}) "
                        f"— skipping sell for {token_address[:10]}... on {chain}"
                    )
                    return SellResult(
                        success=False,
                        error="gas_cost_prohibitive",
                        gas_prohibitive=True,
                    )
                logger.debug(
                    f"Gas check OK: ~${est_gas_cost_usd:.2f} gas vs "
                    f"${position_value_usd:.2f} position ({est_gas_cost_usd / position_value_usd:.0%})"
                )
        except Exception as gas_err:
            logger.warning(f"Gas economics check failed (proceeding with sell): {gas_err}")

    # Native token address (sell destination — ETH/BNB/MATIC)
    NATIVE_TOKEN = "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"

    # ── 1INCH QUOTE PRE-CHECK ─────────────────────────────────────────────
    # Cheap quote-only call to detect no-liquidity or dust before building
    # full swap calldata (which is more expensive and rate-limited).
    if not is_paper and settings.ONEINCH_API_KEY:
        try:
            quote_url = f"{settings.ONEINCH_API_URL}/{chain_config.chain_id}/quote"
            quote_headers = {"Authorization": f"Bearer {settings.ONEINCH_API_KEY}"}
            quote_params = {
                "src": token_address,
                "dst": "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE",
                "amount": str(token_amount_wei),
            }
            quote_resp = get_session().get(
                quote_url, headers=quote_headers, params=quote_params, timeout=15
            )
            if quote_resp.status_code != 200:
                logger.warning(
                    f"1inch quote pre-check failed ({quote_resp.status_code}): "
                    f"{quote_resp.text[:200]} — no liquidity for {token_address[:10]}..."
                )
                return SellResult(
                    success=False,
                    error="quote_failed_no_liquidity",
                )
            quote_data = quote_resp.json()
            dst_amount_raw = int(quote_data.get("dstAmount", 0))
            dst_amount_native = dst_amount_raw / 1e18
            dst_amount_usd = dst_amount_native * _get_eth_price_usd()
            if dst_amount_usd < 0.10:
                logger.info(
                    f"💨 Dust position: quote returned ~${dst_amount_usd:.4f} "
                    f"for {token_address[:10]}... — not worth selling"
                )
                return SellResult(
                    success=False,
                    error="dust_value_unsellable",
                )
            logger.debug(
                f"Quote pre-check OK: ~${dst_amount_usd:.2f} for {token_address[:10]}..."
            )
        except Exception as quote_err:
            logger.warning(f"1inch quote pre-check error (proceeding): {quote_err}")

    # Skip lower tiers if we've failed before (escalate slippage across monitor cycles)
    start_tier = min(prior_failures, len(SLIPPAGE_LADDER) - 1)
    for attempt in range(start_tier, MAX_SELL_ATTEMPTS):
        slippage_bps = SLIPPAGE_LADDER[min(attempt, len(SLIPPAGE_LADDER) - 1)]
        slippage_pct = slippage_bps / 100

        logger.info(
            f"EVM sell attempt {attempt + 1}/{MAX_SELL_ATTEMPTS} | "
            f"slippage={slippage_pct}% | chain={chain}"
        )

        if is_paper:
            logger.info(
                f"📄 PAPER: Simulated EVM sell {token_address[:10]}... "
                f"on {chain} | slippage={slippage_pct}%"
            )
            return SellResult(
                success=True,
                tx_hash="0x" + "0" * 64,
                amount_sold=token_amount_wei,
                slippage_bps_used=slippage_bps,
                attempts=attempt + 1,
                execution_path="paper",
            )

        private_key = wallet.private_key
        if not private_key:
            return SellResult(success=False, error="No private key for wallet")

        if not settings.ONEINCH_API_KEY:
            return SellResult(success=False, error="1inch API key required for EVM sells")

        # ── PRE-EMPTIVE APPROVAL (FIX: SafeTransferFromFailed) ────────────
        # ALWAYS ensure the 1inch router has approval BEFORE requesting swap
        # data. Previously, approval only fired reactively on 400 errors,
        # but 1inch sometimes returns 200 (builds calldata assuming approval)
        # and then the on-chain tx reverts with SafeTransferFromFailed.
        if not is_paper:
            try:
                _approve_token_for_1inch(
                    token_address=token_address,
                    wallet_address=wallet.address,
                    private_key=private_key,
                    chain_id=chain_config.chain_id,
                    chain=chain,
                    token_amount_wei=token_amount_wei,
                )
            except Exception as pre_approve_err:
                logger.warning(
                    f"Pre-emptive approval failed (will retry in-loop): {pre_approve_err}"
                )

        try:
            from web3 import Web3
            from eth_account import Account

            # Get 1inch swap data
            url = f"{settings.ONEINCH_API_URL}/{chain_config.chain_id}/swap"
            headers = {"Authorization": f"Bearer {settings.ONEINCH_API_KEY}"}
            account = Account.from_key(private_key)

            swap_params = {
                "src": token_address,
                "dst": NATIVE_TOKEN,
                "amount": str(token_amount_wei),
                "from": account.address,
                "slippage": slippage_pct,
                "disableEstimate": "false",      # Let 1inch estimate gas properly
                "allowPartialFill": "false",      # Full fill or revert
                "includeTokensInfo": "false",
                "includeProtocols": "false",
            }

            # Update amount in params to use corrected balance
            swap_params["amount"] = str(token_amount_wei)

            resp = get_session().get(url, headers=headers, params=swap_params, timeout=20)

            if resp.status_code == 400:
                err_data = resp.json()
                err_msg = err_data.get("description", resp.text[:200])

                # ── FIX #3: Balance mismatch — re-fetch and retry ─────────
                if "not enough" in err_msg.lower() and "balance" in err_msg.lower():
                    logger.warning(
                        f"Balance mismatch on {token_address[:10]}... — "
                        f"re-fetching on-chain balance"
                    )
                    try:
                        real_bal = get_evm_token_balance(
                            account.address, token_address, chain
                        )
                        if real_bal > 0 and real_bal != token_amount_wei:
                            logger.info(
                                f"🔧 Corrected: {token_amount_wei} → {real_bal}"
                            )
                            token_amount_wei = real_bal
                            swap_params["amount"] = str(real_bal)
                            resp = get_session().get(
                                url, headers=headers, params=swap_params, timeout=20
                            )
                        elif real_bal == 0:
                            return SellResult(
                                success=False,
                                error="On-chain balance is 0 after re-check",
                                attempts=attempt + 1,
                            )
                    except Exception as bal_err:
                        logger.error(f"Balance re-fetch failed: {bal_err}")

                # ── FIX #2: Allowance — approve then WAIT before retry ────
                if resp.status_code == 400:  # Re-check after balance fix
                    err_data = resp.json() if resp.status_code == 400 else {}
                    err_msg = err_data.get("description", resp.text[:200])
                    if "allowance" in err_msg.lower() or "approve" in err_msg.lower():
                        logger.warning(
                            f"1inch requires approval for {token_address[:10]}... — "
                            f"sending ERC-20 approve tx"
                        )
                        try:
                            _approve_token_for_1inch(
                                token_address=token_address,
                                wallet_address=account.address,
                                private_key=private_key,
                                chain_id=chain_config.chain_id,
                                chain=chain,
                                token_amount_wei=token_amount_wei,
                            )
                            # FIX: Wait for approval to propagate (1-2 blocks)
                            logger.info("⏳ Waiting 5s for approval tx to confirm...")
                            time.sleep(5.0)
                            # Retry swap with fresh nonce awareness
                            resp = get_session().get(
                                url, headers=headers, params=swap_params, timeout=20
                            )
                        except Exception as approve_err:
                            logger.error(f"Approval failed: {approve_err}")
                            if attempt == MAX_SELL_ATTEMPTS - 1:
                                return SellResult(
                                    success=False,
                                    error=f"Approval failed: {approve_err}",
                                    attempts=attempt + 1,
                                )
                            time.sleep(2.0)
                            continue

            if resp.status_code != 200:
                logger.warning(
                    f"1inch swap error {resp.status_code} (attempt {attempt + 1}): "
                    f"{resp.text[:200]}"
                )
                time.sleep(2.0 * (attempt + 1))
                continue

            swap_data = resp.json()
            tx_data = swap_data.get("tx", {})
            dst_amount = int(swap_data.get("dstAmount", 0))

            # Build and send transaction
            w3 = _get_web3(chain_config)
            if not w3:
                logger.error(f"No Web3 connection for {chain}")
                time.sleep(2.0)
                continue

            nonce = w3.eth.get_transaction_count(account.address, "pending")
            base_gas = w3.eth.gas_price
            gas_multiplier = 1.0 + (0.5 * attempt)  # +50% gas per retry (was 30%)

            # ── Gas estimation: use 1inch estimate → eth.estimate_gas → 800K default
            oneinch_gas = int(tx_data.get("gas", 0))
            raw_tx = {
                "from": account.address,
                "to": Web3.to_checksum_address(tx_data["to"]),
                "data": tx_data["data"],
                "value": int(tx_data.get("value", 0)),
            }

            # Try eth.estimate_gas for accurate gas limit
            try:
                estimated_gas = w3.eth.estimate_gas(raw_tx)
                gas_limit = int(estimated_gas * 1.5)  # 50% safety buffer
                logger.info(f"Gas estimated: {estimated_gas} → using {gas_limit} (1.5x buffer)")
            except Exception as gas_err:
                # Fallback: use 1inch estimate or 800K default
                gas_limit = max(oneinch_gas, 800_000)
                logger.warning(
                    f"Gas estimation failed ({gas_err}), using fallback: {gas_limit}"
                )

            transaction = {
                "from": account.address,
                "to": Web3.to_checksum_address(tx_data["to"]),
                "data": tx_data["data"],
                "value": int(tx_data.get("value", 0)),
                "gas": int(gas_limit * gas_multiplier),
                "gasPrice": int(base_gas * gas_multiplier),
                "nonce": nonce,
                "chainId": chain_config.chain_id,
            }

            # ── eth_call SIMULATION (FIX: catch SafeTransferFromFailed before wasting gas) ──
            try:
                w3.eth.call({
                    "from": transaction["from"],
                    "to": transaction["to"],
                    "data": transaction["data"],
                    "value": transaction["value"],
                })
                logger.info("✅ Sell simulation passed (eth_call)")
            except Exception as sim_err:
                sim_msg = str(sim_err).lower()
                logger.warning(f"⚠️ Sell simulation reverted: {sim_err}")
                # If SafeTransferFrom or allowance issue — try re-approving
                if "safetransferfrom" in sim_msg or "allowance" in sim_msg or "transfer" in sim_msg:
                    logger.info("🔧 Re-approving token after simulation failure...")
                    try:
                        _approve_token_for_1inch(
                            token_address=token_address,
                            wallet_address=account.address,
                            private_key=private_key,
                            chain_id=chain_config.chain_id,
                            chain=chain,
                            token_amount_wei=token_amount_wei,
                        )
                        time.sleep(5.0)  # Wait for approval to propagate
                        # Re-simulate after approval
                        try:
                            w3.eth.call({
                                "from": transaction["from"],
                                "to": transaction["to"],
                                "data": transaction["data"],
                                "value": transaction["value"],
                            })
                            logger.info("✅ Sell simulation passed after re-approval")
                        except Exception as sim_err2:
                            logger.error(f"❌ Sell still reverts after re-approval: {sim_err2}")
                            # Don't waste gas — skip to next attempt with wider slippage
                            time.sleep(2.0 * (attempt + 1))
                            continue
                    except Exception as reapprove_err:
                        logger.error(f"Re-approval failed: {reapprove_err}")
                        time.sleep(2.0 * (attempt + 1))
                        continue
                elif "insufficient funds" in sim_msg:
                    # Can't fix — not enough ETH for gas
                    return SellResult(
                        success=False,
                        error=f"Insufficient ETH for gas: {sim_err}",
                        attempts=attempt + 1,
                    )
                else:
                    # Unknown revert — could be honeypot, skip to wider slippage
                    logger.warning("Unknown revert — trying wider slippage on next attempt")
                    time.sleep(2.0 * (attempt + 1))
                    continue

            signed = account.sign_transaction(transaction)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

            if receipt.status == 1:
                proceeds = dst_amount / 1e18
                logger.info(
                    f"✅ EVM SELL: {token_address[:10]}... on {chain} | "
                    f"tx={tx_hash.hex()[:16]}... | "
                    f"proceeds={proceeds:.4f} ETH | slippage={slippage_pct}%"
                )
                return SellResult(
                    success=True,
                    tx_hash=tx_hash.hex(),
                    amount_sold=token_amount_wei,
                    proceeds_usd=proceeds * _get_eth_price_usd(),  # Live ETH price (fallback: $3000)
                    slippage_bps_used=slippage_bps,
                    attempts=attempt + 1,
                    execution_path=f"1inch_live{'_retry' if attempt > 0 else ''}",
                )
            else:
                logger.warning(
                    f"EVM sell tx reverted (attempt {attempt + 1}): {tx_hash.hex()}"
                )

        except Exception as e:
            error_str = str(e).lower()
            if "intrinsic gas too low" in error_str:
                # DEGEN Bug Fix: Boost gas multiplier significantly for the next attempt
                gas_multiplier = gas_multiplier * 2.5
                logger.warning(f"Gas boost: {gas_limit * gas_multiplier} for intrinsic gas too low on {token_address[:10]}...")
                
                # If we've failed twice with intrinsic gas, try splitting the sell amount
                if attempt >= 1 and token_amount_wei > 1000:
                    logger.warning(f"Splitting {token_amount_wei} wei into smaller chunk to avoid gas limits")
                    token_amount_wei = int(token_amount_wei / 3)
                    
            logger.error(f"EVM sell error (attempt {attempt + 1}): {e}")

        time.sleep(2.0 * (attempt + 1))

    return SellResult(
        success=False,
        attempts=MAX_SELL_ATTEMPTS,
        error=f"All {MAX_SELL_ATTEMPTS} EVM sell attempts failed",
    )


def _get_web3(chain_config):
    """Get a Web3 connection for a chain."""
    try:
        from web3 import Web3
        from web3.middleware import ExtraDataToPOAMiddleware
        w3 = Web3(Web3.HTTPProvider(chain_config.rpc_url, request_kwargs={"timeout": 30}))
        if chain_config.chain_id in (56, 137, 8453):  # BSC, Polygon, Base
            w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        return w3 if w3.is_connected() else None
    except Exception as e:
        logger.error(f"Web3 connection failed: {e}")
        return None


def _approve_token_for_1inch(
    token_address: str,
    wallet_address: str,
    private_key: str,
    chain_id: int,
    chain: str,
    token_amount_wei: int = 0,
) -> bool:
    """
    Approve 1inch router to spend token (required for ERC-20 sells).
    Uses 1inch approve API to get the correct spender address.
    Uses bounded approval (2x sell amount) instead of unlimited for security.
    """
    from data.http_session import get_session
    from config import settings
    from web3 import Web3
    from eth_account import Account

    headers = {"Authorization": f"Bearer {settings.ONEINCH_API_KEY}"}

    # Get spender address from 1inch
    spender_url = f"{settings.ONEINCH_API_URL}/{chain_id}/approve/spender"
    resp = get_session().get(spender_url, headers=headers, timeout=10)
    resp.raise_for_status()
    spender = resp.json().get("address")
    if not spender:
        raise ValueError("Could not get 1inch spender address")

    # ── CHECK EXISTING ALLOWANCE FIRST (avoid wasting gas on redundant approvals) ──
    needed_amount = token_amount_wei * 2 if token_amount_wei > 0 else 2**256 - 1
    try:
        allowance_url = f"{settings.ONEINCH_API_URL}/{chain_id}/approve/allowance"
        allow_resp = get_session().get(
            allowance_url,
            headers=headers,
            params={"tokenAddress": token_address, "walletAddress": wallet_address},
            timeout=10,
        )
        if allow_resp.status_code == 200:
            current_allowance = int(allow_resp.json().get("allowance", "0"))
            if current_allowance >= needed_amount:
                logger.debug(
                    f"Token {token_address[:10]}... already approved "
                    f"(allowance={current_allowance} >= needed={needed_amount})"
                )
                return True  # Already approved — skip on-chain tx
            logger.info(
                f"Allowance insufficient: {current_allowance} < {needed_amount} — sending approve tx"
            )
    except Exception as allow_err:
        logger.debug(f"Allowance check failed (proceeding with approval): {allow_err}")

    # Build approve transaction
    from config.chains import CHAINS
    chain_config = CHAINS[chain]
    w3 = _get_web3(chain_config)
    if not w3:
        raise RuntimeError(f"No Web3 connection for {chain}")

    ERC20_APPROVE_ABI = [{
        "constant": False,
        "inputs": [
            {"name": "spender", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
    }]

    contract = w3.eth.contract(
        address=Web3.to_checksum_address(token_address),
        abi=ERC20_APPROVE_ABI,
    )
    account = Account.from_key(private_key)
    nonce = w3.eth.get_transaction_count(account.address, "pending")

    # Bounded approval: 2x the sell amount to cover slippage retries
    # without leaving unlimited spend allowance (security best practice)
    approval_amount = needed_amount
    logger.info(f"Approving {'bounded' if token_amount_wei > 0 else 'unlimited'} spend for 1inch")

    approve_tx = contract.functions.approve(
        Web3.to_checksum_address(spender),
        approval_amount,
    ).build_transaction({
        "from": account.address,
        "nonce": nonce,
        "gas": 100_000,
        "gasPrice": int(w3.eth.gas_price * 1.2),
        "chainId": chain_id,
    })

    signed = account.sign_transaction(approve_tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)

    if receipt.status == 1:
        logger.info(f"✅ Token approval confirmed: {tx_hash.hex()[:16]}...")
        return True
    else:
        raise RuntimeError(f"Approval transaction reverted: {tx_hash.hex()}")


def get_solana_token_balance(
    wallet_public_key: str,
    token_mint: str,
    rpc_url: str = None,
) -> int:
    """
    Fetch actual on-chain token balance for a Solana wallet.
    Used as fallback when position.remaining_quantity is 0 or unreliable.

    Returns token amount in smallest units (lamports/decimals), or 0 on error.
    """
    from config import settings
    rpc = rpc_url or settings.SOLANA_RPC_URL
    from data.http_session import get_session

    try:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTokenAccountsByOwner",
            "params": [
                wallet_public_key,
                {"mint": token_mint},
                {"encoding": "jsonParsed"},
            ],
        }
        resp = get_session().post(rpc, json=payload, timeout=15)
        result = resp.json().get("result", {})
        accounts = result.get("value", [])
        if not accounts:
            return 0
        # Sum all token accounts for this mint
        total = 0
        for acct in accounts:
            info = acct.get("account", {}).get("data", {}).get("parsed", {}).get("info", {})
            amount_str = info.get("tokenAmount", {}).get("amount", "0")
            total += int(amount_str)
        return total
    except Exception as e:
        logger.error(f"Failed to fetch Solana token balance for {token_mint[:8]}...: {e}")
        return 0


def get_evm_token_balance(
    wallet_address: str,
    token_address: str,
    chain: str,
) -> int:
    """
    Fetch actual on-chain ERC-20 token balance.
    Used as fallback when position.remaining_quantity is 0 or unreliable.

    Returns token amount in wei, or 0 on error.
    """
    from config.chains import CHAINS
    ERC20_BALANCE_ABI = [{
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function",
    }]

    try:
        chain_config = CHAINS.get(chain)
        if not chain_config:
            return 0
        w3 = _get_web3(chain_config)
        if not w3:
            return 0
        from web3 import Web3
        contract = w3.eth.contract(
            address=Web3.to_checksum_address(token_address),
            abi=ERC20_BALANCE_ABI,
        )
        balance = contract.functions.balanceOf(
            Web3.to_checksum_address(wallet_address)
        ).call()
        return int(balance)
    except Exception as e:
        logger.error(f"Failed to fetch EVM token balance for {token_address[:10]}...: {e}")
        return 0


def resolve_sell_quantity(
    pos: dict,
    sell_pct: float,
) -> tuple[float, int]:
    """
    Resolve the actual sell quantity, with on-chain fallback if stored
    remaining_quantity is 0 or suspiciously small.

    Returns:
        (sell_qty_tokens, sell_qty_units) where units = smallest denomination
    """
    remaining_qty = float(pos.get("remaining_quantity", pos.get("quantity", 0)))
    chain = pos.get("chain", "")
    token_address = pos.get("token_address", "")
    token_decimals = int(pos.get("token_decimals", 6 if chain == "solana" else 18))

    # If remaining_quantity is 0 or very small, fetch on-chain balance
    if remaining_qty <= 0 or remaining_qty < 1e-9:
        logger.warning(
            f"⚠️ remaining_quantity={remaining_qty} for {pos.get('token_symbol')} "
            f"— fetching on-chain balance as fallback"
        )
        wallet_alias = pos.get("wallet", "primary")
        try:
            from config.wallets import WALLETS
            wallet = WALLETS.get(wallet_alias)
            if wallet:
                if chain == "solana":
                    wallet_addr = wallet.solana_address or ""
                    on_chain_units = get_solana_token_balance(wallet_addr, token_address)
                    if on_chain_units > 0:
                        remaining_qty = on_chain_units / (10 ** token_decimals)
                        logger.info(
                            f"✅ On-chain balance recovered: {remaining_qty:.6f} tokens "
                            f"({on_chain_units:,} units)"
                        )
                else:
                    wallet_addr = wallet.address or ""
                    on_chain_units = get_evm_token_balance(wallet_addr, token_address, chain)
                    if on_chain_units > 0:
                        remaining_qty = on_chain_units / (10 ** token_decimals)
                        logger.info(
                            f"✅ On-chain balance recovered: {remaining_qty:.6f} tokens "
                            f"({on_chain_units:,} units)"
                        )
        except Exception as e:
            logger.error(f"On-chain balance fetch failed: {e}")

    if remaining_qty <= 0:
        logger.error(
            f"❌ Cannot resolve sell quantity for {pos.get('token_symbol')} — "
            f"remaining_qty={remaining_qty} and on-chain fetch failed"
        )
        return 0.0, 0

    sell_qty = remaining_qty * sell_pct
    sell_qty_units = int(sell_qty * (10 ** token_decimals))

    logger.debug(
        f"Sell quantity resolved: {sell_qty:.6f} tokens ({sell_qty_units:,} units) | "
        f"remaining={remaining_qty:.6f} | sell_pct={sell_pct:.0%}"
    )

    return sell_qty, sell_qty_units
