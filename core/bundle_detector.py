"""
core/bundle_detector.py — Block-0 Sniper & Bundle Detection

Hard-reject gate that fires BEFORE a token enters the scoring pipeline.
Detects coordinated sniper attacks where multiple wallets acquire a
disproportionate share of supply in the SAME block as pool creation.

Why this matters:
  - Bundled snipers typically acquire 20–60% of supply at launch.
  - They immediately become the dominant sellers at any price uptick.
  - No amount of TA or whale scoring can overcome this structural overhang.
  - The only correct response is a hard REJECT before capital is deployed.

Detection logic:
  1. Fetch the pool creation block from the chain's RPC or DexScreener.
  2. Pull all token transfers in that block (or first N blocks).
  3. Identify wallets that received tokens in block 0.
  4. If any single wallet or coordinated cluster holds > BUNDLE_THRESHOLD
     of total supply from block-0 transfers, REJECT.

Supported chains:
  - EVM (Ethereum, Base, Arbitrum, Polygon, BSC): via Web3 + Etherscan/Basescan
  - Solana: via Helius RPC (getTokenLargestAccounts + transaction history)

Settings (config/settings.py):
  BUNDLE_DETECT_ENABLED         = True
  BUNDLE_THRESHOLD_PCT          = 20.0   # Reject if block-0 snipers hold >20% supply
  BUNDLE_CLUSTER_THRESHOLD_PCT  = 35.0   # Reject if top-N cluster holds >35%
  BUNDLE_CLUSTER_WALLET_COUNT   = 5      # Number of wallets to consider a cluster
  BUNDLE_HELIUS_API_KEY         = ""     # Helius API key for Solana analysis
  BUNDLE_ETHERSCAN_API_KEY      = ""     # Etherscan/Basescan/Arbiscan key
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from data.http_session import get_session

from config import settings

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Config defaults (override in settings.py)
# ─────────────────────────────────────────────────────────────────────────────
BUNDLE_DETECT_ENABLED = getattr(settings, "BUNDLE_DETECT_ENABLED", True)
BUNDLE_THRESHOLD_PCT = getattr(settings, "BUNDLE_THRESHOLD_PCT", 20.0)
BUNDLE_CLUSTER_THRESHOLD_PCT = getattr(settings, "BUNDLE_CLUSTER_THRESHOLD_PCT", 35.0)
BUNDLE_CLUSTER_WALLET_COUNT = getattr(settings, "BUNDLE_CLUSTER_WALLET_COUNT", 5)
HELIUS_API_KEY = getattr(settings, "BUNDLE_HELIUS_API_KEY", "") or getattr(settings, "HELIUS_API_KEY", "")
ETHERSCAN_API_KEY = getattr(settings, "BUNDLE_ETHERSCAN_API_KEY", "") or getattr(settings, "ETHERSCAN_API_KEY", "")

# Etherscan-compatible API base URLs per chain
_EXPLORER_APIS = {
    "ethereum": "https://api.etherscan.io/api",
    "base": "https://api.basescan.org/api",
    "arbitrum": "https://api.arbiscan.io/api",
    "polygon": "https://api.polygonscan.com/api",
    "bsc": "https://api.bscscan.com/api",
}

# Helius RPC for Solana
_HELIUS_RPC = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}" if HELIUS_API_KEY else "https://api.mainnet-beta.solana.com"


# ─────────────────────────────────────────────────────────────────────────────
# Result dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class BundleDetectionResult:
    """Result of a bundle/sniper detection check."""
    is_bundled: bool = False
    reject_reason: str = ""
    # Detailed findings
    block_0_wallets: int = 0
    block_0_supply_pct: float = 0.0
    cluster_supply_pct: float = 0.0
    top_sniper_wallet: str = ""
    top_sniper_pct: float = 0.0
    # Metadata
    chain: str = ""
    token_address: str = ""
    detection_method: str = ""   # "etherscan", "helius", "dexscreener", "skipped"
    error: Optional[str] = None

    def __str__(self) -> str:
        if self.is_bundled:
            return (
                f"BundleDetect(🚨 BUNDLED | {self.reject_reason} | "
                f"block0={self.block_0_supply_pct:.1f}% | "
                f"cluster={self.cluster_supply_pct:.1f}%)"
            )
        return (
            f"BundleDetect(✅ CLEAN | block0={self.block_0_supply_pct:.1f}% | "
            f"method={self.detection_method})"
        )


# ─────────────────────────────────────────────────────────────────────────────
# EVM Bundle Detection (Etherscan-compatible APIs)
# ─────────────────────────────────────────────────────────────────────────────

def _get_erc20_transfers_block0(
    token_address: str,
    chain: str,
    max_results: int = 200,
) -> list[dict]:
    """
    Fetch the earliest ERC-20 transfer events for a token using Etherscan API.
    Returns transfers sorted by block number ascending.
    """
    api_url = _EXPLORER_APIS.get(chain)
    if not api_url or not ETHERSCAN_API_KEY:
        return []

    try:
        params = {
            "module": "account",
            "action": "tokentx",
            "contractaddress": token_address,
            "page": 1,
            "offset": max_results,
            "sort": "asc",
            "apikey": ETHERSCAN_API_KEY,
        }
        resp = get_session().get(api_url, params=params, timeout=15)
        data = resp.json()
        if data.get("status") == "1" and data.get("result"):
            return data["result"]
        logger.debug(f"Etherscan no transfers for {token_address[:10]}...: {data.get('message')}")
        return []
    except Exception as e:
        logger.warning(f"Etherscan transfer fetch failed: {e}")
        return []


def _analyze_evm_bundle(
    token_address: str,
    chain: str,
) -> BundleDetectionResult:
    """
    Analyze EVM token for block-0 sniper bundles using Etherscan API.

    Strategy:
      1. Fetch first 200 transfers sorted by block ascending.
      2. Identify the creation block (block of first transfer).
      3. Sum all tokens received in that block per wallet.
      4. Calculate each wallet's % of total block-0 supply received.
      5. Reject if any single wallet > BUNDLE_THRESHOLD_PCT or
         top-N cluster > BUNDLE_CLUSTER_THRESHOLD_PCT.
    """
    result = BundleDetectionResult(
        chain=chain,
        token_address=token_address,
        detection_method="etherscan",
    )

    transfers = _get_erc20_transfers_block0(token_address, chain)
    if not transfers:
        result.detection_method = "skipped_no_data"
        return result

    # Find creation block (first transfer block)
    creation_block = int(transfers[0]["blockNumber"])

    # Aggregate block-0 receipts by wallet
    block0_receipts: dict[str, int] = {}
    total_block0_tokens = 0

    for tx in transfers:
        if int(tx["blockNumber"]) != creation_block:
            break  # Transfers are sorted ascending; stop at first non-creation block
        recipient = tx.get("to", "").lower()
        value = int(tx.get("value", 0))
        if recipient and value > 0:
            block0_receipts[recipient] = block0_receipts.get(recipient, 0) + value
            total_block0_tokens += value

    if total_block0_tokens == 0:
        result.detection_method = "skipped_zero_supply"
        return result

    # Calculate percentages
    wallet_pcts = {
        wallet: (tokens / total_block0_tokens) * 100
        for wallet, tokens in block0_receipts.items()
    }
    sorted_wallets = sorted(wallet_pcts.items(), key=lambda x: x[1], reverse=True)

    result.block_0_wallets = len(block0_receipts)
    result.block_0_supply_pct = sum(wallet_pcts.values())  # % of supply received in block 0

    if sorted_wallets:
        result.top_sniper_wallet = sorted_wallets[0][0]
        result.top_sniper_pct = sorted_wallets[0][1]

    # Cluster analysis: top N wallets combined
    top_n = sorted_wallets[:BUNDLE_CLUSTER_WALLET_COUNT]
    result.cluster_supply_pct = sum(pct for _, pct in top_n)

    # ── Hard reject conditions ────────────────────────────────────────────────
    if result.top_sniper_pct > BUNDLE_THRESHOLD_PCT:
        result.is_bundled = True
        result.reject_reason = (
            f"Single sniper wallet acquired {result.top_sniper_pct:.1f}% "
            f"of supply in block {creation_block} "
            f"(threshold: {BUNDLE_THRESHOLD_PCT}%)"
        )
        logger.warning(
            f"🚨 BUNDLE DETECTED [{chain}] {token_address[:10]}...: "
            f"{result.reject_reason}"
        )
        return result

    if result.cluster_supply_pct > BUNDLE_CLUSTER_THRESHOLD_PCT:
        result.is_bundled = True
        result.reject_reason = (
            f"Sniper cluster ({len(top_n)} wallets) acquired "
            f"{result.cluster_supply_pct:.1f}% of supply in block {creation_block} "
            f"(threshold: {BUNDLE_CLUSTER_THRESHOLD_PCT}%)"
        )
        logger.warning(
            f"🚨 BUNDLE CLUSTER DETECTED [{chain}] {token_address[:10]}...: "
            f"{result.reject_reason}"
        )
        return result

    logger.debug(
        f"✅ Bundle check CLEAN [{chain}] {token_address[:10]}...: "
        f"block0={result.block_0_supply_pct:.1f}% | "
        f"top_sniper={result.top_sniper_pct:.1f}% | "
        f"cluster={result.cluster_supply_pct:.1f}%"
    )
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Solana Bundle Detection (Helius RPC)
# ─────────────────────────────────────────────────────────────────────────────

def _get_solana_largest_accounts(token_mint: str) -> list[dict]:
    """Fetch the largest token holders via Solana RPC."""
    try:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTokenLargestAccounts",
            "params": [token_mint, {"commitment": "confirmed"}],
        }
        resp = get_session().post(_HELIUS_RPC, json=payload, timeout=15)
        result = resp.json()
        return result.get("result", {}).get("value", [])
    except Exception as e:
        logger.warning(f"Solana largest accounts fetch failed: {e}")
        return []


def _get_solana_token_supply(token_mint: str) -> int:
    """Fetch total token supply in smallest unit."""
    try:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTokenSupply",
            "params": [token_mint],
        }
        resp = get_session().post(_HELIUS_RPC, json=payload, timeout=15)
        result = resp.json()
        amount = result.get("result", {}).get("value", {}).get("amount", "0")
        return int(amount)
    except Exception as e:
        logger.warning(f"Solana token supply fetch failed: {e}")
        return 0


def _analyze_solana_bundle(token_mint: str) -> BundleDetectionResult:
    """
    Analyze Solana token for sniper concentration using current holder distribution.

    For Solana we use current largest accounts as a proxy for block-0 snipers.
    Pump.fun graduates are especially vulnerable — bundled snipers often hold
    20–60% of supply from the bonding curve phase.

    Note: This is a concentration check, not a true block-0 analysis.
    True block-0 analysis on Solana requires Helius enhanced transactions API
    (getAssetsByOwner + transaction history) which is rate-limited.
    We use holder concentration as a fast, reliable proxy.
    """
    result = BundleDetectionResult(
        chain="solana",
        token_address=token_mint,
        detection_method="helius_concentration",
    )

    total_supply = _get_solana_token_supply(token_mint)
    if total_supply == 0:
        result.detection_method = "skipped_no_supply"
        return result

    largest_accounts = _get_solana_largest_accounts(token_mint)
    if not largest_accounts:
        result.detection_method = "skipped_no_holders"
        return result

    # Calculate concentration for top N wallets
    top_n = largest_accounts[:BUNDLE_CLUSTER_WALLET_COUNT]
    cluster_amount = sum(int(acc.get("amount", 0)) for acc in top_n)
    cluster_pct = (cluster_amount / total_supply) * 100

    top_holder_amount = int(largest_accounts[0].get("amount", 0)) if largest_accounts else 0
    top_holder_pct = (top_holder_amount / total_supply) * 100

    result.block_0_wallets = len(top_n)
    result.block_0_supply_pct = top_holder_pct  # Proxy: top holder % as block-0 signal
    result.cluster_supply_pct = cluster_pct
    result.top_sniper_wallet = largest_accounts[0].get("address", "") if largest_accounts else ""
    result.top_sniper_pct = top_holder_pct

    # ── Hard reject conditions ────────────────────────────────────────────────
    if top_holder_pct > BUNDLE_THRESHOLD_PCT:
        result.is_bundled = True
        result.reject_reason = (
            f"Top holder controls {top_holder_pct:.1f}% of supply "
            f"(threshold: {BUNDLE_THRESHOLD_PCT}%) — likely bundled sniper"
        )
        logger.warning(
            f"🚨 SOLANA BUNDLE DETECTED {token_mint[:8]}...: {result.reject_reason}"
        )
        return result

    if cluster_pct > BUNDLE_CLUSTER_THRESHOLD_PCT:
        result.is_bundled = True
        result.reject_reason = (
            f"Top-{len(top_n)} holder cluster controls {cluster_pct:.1f}% of supply "
            f"(threshold: {BUNDLE_CLUSTER_THRESHOLD_PCT}%)"
        )
        logger.warning(
            f"🚨 SOLANA CLUSTER DETECTED {token_mint[:8]}...: {result.reject_reason}"
        )
        return result

    logger.debug(
        f"✅ Solana bundle check CLEAN {token_mint[:8]}...: "
        f"top={top_holder_pct:.1f}% | cluster={cluster_pct:.1f}%"
    )
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def check_bundle(token_address: str, chain: str) -> BundleDetectionResult:
    """
    Main entry point for bundle/sniper detection.

    Called from gem_scanner._score_token() BEFORE the scoring pipeline runs.
    Returns a BundleDetectionResult; if result.is_bundled is True, the caller
    MUST reject the token immediately.

    Args:
        token_address: Token contract address (EVM) or mint address (Solana)
        chain:         Chain name (e.g., "base", "solana", "ethereum")

    Returns:
        BundleDetectionResult with is_bundled flag and full diagnostic data
    """
    if not BUNDLE_DETECT_ENABLED:
        return BundleDetectionResult(
            chain=chain,
            token_address=token_address,
            detection_method="disabled",
        )

    try:
        if chain == "solana":
            return _analyze_solana_bundle(token_address)
        elif chain in _EXPLORER_APIS:
            return _analyze_evm_bundle(token_address, chain)
        else:
            # Unknown chain — skip gracefully, don't block
            logger.debug(f"Bundle detection skipped for unsupported chain: {chain}")
            return BundleDetectionResult(
                chain=chain,
                token_address=token_address,
                detection_method="skipped_unsupported_chain",
            )
    except Exception as e:
        logger.error(f"Bundle detection error for {token_address[:10]}... on {chain}: {e}")
        # On error, return clean result — don't block trades due to detection failures
        return BundleDetectionResult(
            chain=chain,
            token_address=token_address,
            detection_method="error",
            error=str(e),
        )
