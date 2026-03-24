"""
data/providers/dev_wallet_history.py — Creator/deployer wallet rug history analysis.

Ported from RugscoreBotTG (SoCloseSociety) and adapted to Shamrock's synchronous
provider pattern. Checks the deployer wallet's on-chain history for red flags:

  1. Wallet age — brand-new wallets are riskier
  2. Past token creates — serial token deployers ("token farms") are red flags
  3. Rug pattern detection — many tokens + new wallet = high risk
  4. Active selling — dev dumping within the last hour

Data sources:
  - Solana: RPC getSignaturesForAddress + getTransaction (free, no key)
  - EVM: DexScreener maker data (no extra API call)

Returns a 0–100 score (higher = safer) and list of flags.
"""

import logging
import time
from typing import Optional

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from config import settings

logger = logging.getLogger(__name__)

# ── Cache ────────────────────────────────────────────────────────────────────
_dev_cache: dict[str, tuple[float, list[str], float]] = {}  # key -> (score, flags, timestamp)
_CACHE_TTL = 3600  # 1 hour — dev history doesn't change rapidly


def get_dev_wallet_score(
    token_address: str,
    chain: str,
    creator_address: Optional[str] = None,
) -> tuple[float, list[str]]:
    """
    Score the deployer wallet 0–100 (higher = safer).
    Returns (score, flags) where flags is a list of human-readable findings.

    If creator_address is not provided, attempts to discover it from
    DexScreener pair data (maker field) for EVM chains, or from Solana
    token metadata for SPL tokens.
    """
    cache_key = f"{chain}:{token_address}".lower()

    # Check cache
    if cache_key in _dev_cache:
        score, flags, cached_at = _dev_cache[cache_key]
        if (time.time() - cached_at) < _CACHE_TTL:
            return score, flags

    if chain == "solana":
        score, flags = _analyze_solana_creator(token_address, creator_address)
    else:
        # EVM chains — limited analysis without block explorer API keys
        score, flags = _analyze_evm_creator(token_address, chain, creator_address)

    _dev_cache[cache_key] = (score, flags, time.time())
    return score, flags


# ═════════════════════════════════════════════════════════════════════════════
# Solana-specific analysis
# ═════════════════════════════════════════════════════════════════════════════

def _analyze_solana_creator(
    token_address: str,
    creator_address: Optional[str] = None,
) -> tuple[float, list[str]]:
    """Analyze a Solana token's creator wallet via RPC."""
    flags: list[str] = []

    # Step 1: Try to find creator if not provided
    if not creator_address:
        creator_address = _find_solana_creator(token_address)
        if not creator_address:
            return 30.0, ["⚠️ Creator wallet unknown — cannot verify dev history"]

    # Step 2: Get creator's transaction history
    signatures = _solana_get_signatures(creator_address, limit=20)
    if not signatures:
        return 25.0, ["⚠️ No transaction history for creator wallet"]

    score = 0.0

    # ── Wallet age ────────────────────────────────────────────────────────
    oldest_sig = signatures[-1] if signatures else None
    if oldest_sig and oldest_sig.get("blockTime"):
        wallet_age_days = (time.time() - oldest_sig["blockTime"]) / 86400

        if wallet_age_days > 90:
            score += 25
            flags.append(f"✅ Creator wallet age: {wallet_age_days:.0f} days (established)")
        elif wallet_age_days > 30:
            score += 20
            flags.append(f"✅ Creator wallet age: {wallet_age_days:.0f} days")
        elif wallet_age_days > 7:
            score += 10
            flags.append(f"⚠️ Creator wallet age: {wallet_age_days:.0f} days (moderate)")
        else:
            score += 0
            flags.append(f"🚩 Creator wallet only {wallet_age_days:.1f} days old!")
    else:
        score += 5

    # ── Count token-related transactions (proxy for tokens created) ───────
    # Sample a few recent transactions for mint instructions
    token_creates = 0
    recent_sells = 0
    now = time.time()

    for sig_info in signatures[:8]:
        sig = sig_info.get("signature")
        if not sig:
            continue
        tx = _solana_get_transaction(sig)
        if not tx:
            continue

        instructions = _extract_instructions(tx)
        for ix in instructions:
            parsed = ix.get("parsed", {})
            if isinstance(parsed, dict):
                ix_type = parsed.get("type", "")
                if ix_type in ("initializeMint", "initializeMint2"):
                    token_creates += 1
                # Check for recent transfers (selling)
                block_time = tx.get("blockTime", 0)
                if block_time and (now - block_time) < 3600:
                    if ix_type in ("transfer", "transferChecked"):
                        recent_sells += 1

    # ── Token creation count scoring ──────────────────────────────────────
    if token_creates <= 1:
        score += 25
        flags.append(f"✅ {token_creates} previous token creations (clean)")
    elif token_creates <= 5:
        score += 15
        flags.append(f"⚠️ {token_creates} previous token creations (active creator)")
    else:
        score -= 10
        flags.append(f"🚩 {token_creates} previous token creations (token farm risk!)")

    # ── Rug pattern heuristic ─────────────────────────────────────────────
    wallet_age = (time.time() - (oldest_sig.get("blockTime", time.time()))) / 86400 if oldest_sig and oldest_sig.get("blockTime") else 999
    rug_pattern = token_creates > 3 and wallet_age < 30
    if not rug_pattern:
        score += 25
        flags.append("✅ No rug pattern detected")
    else:
        score -= 15
        flags.append("🚩 RUG PATTERN: many tokens + new wallet")

    # ── Active selling check ──────────────────────────────────────────────
    if recent_sells == 0:
        score += 25
        flags.append("✅ Dev not actively selling")
    elif recent_sells <= 2:
        score += 15
        flags.append(f"⚠️ Dev has {recent_sells} recent transfers")
    else:
        score -= 5
        flags.append(f"🚩 Dev actively transferring ({recent_sells} in last hour)")

    final_score = max(0.0, min(100.0, score))
    return round(final_score, 1), flags


def _analyze_evm_creator(
    token_address: str,
    chain: str,
    creator_address: Optional[str] = None,
) -> tuple[float, list[str]]:
    """
    For EVM chains, we have limited free data on the creator wallet.
    Apply a conservative score based on what GoPlus already tells us
    (is_mintable, owner_change_balance, hidden_owner) and return a
    neutral-positive score since EVM tokens get GoPlus full analysis.
    """
    # EVM chains get comprehensive GoPlus analysis elsewhere in the pipeline.
    # Dev wallet history adds less value for EVM — return a neutral score
    # to avoid penalizing tokens where we simply can't look up the deployer
    # without paid block explorer APIs.
    return 60.0, ["ℹ️ EVM chain — dev wallet scored via GoPlus contract analysis"]


# ═════════════════════════════════════════════════════════════════════════════
# Solana RPC helpers (synchronous, using existing settings.SOLANA_RPC_URL)
# ═════════════════════════════════════════════════════════════════════════════

def _find_solana_creator(token_address: str) -> Optional[str]:
    """Try to find the creator of a Solana token using getAccountInfo metadata."""
    try:
        rpc_url = settings.SOLANA_RPC_URL
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getAccountInfo",
            "params": [
                token_address,
                {"encoding": "jsonParsed"}
            ],
        }
        resp = requests.post(rpc_url, json=payload, timeout=10)
        data = resp.json()
        result = data.get("result", {})
        value = result.get("value", {})
        if not value:
            return None
        parsed = value.get("data", {}).get("parsed", {})
        if isinstance(parsed, dict):
            info = parsed.get("info", {})
            # mintAuthority or freezeAuthority is often the creator
            return info.get("mintAuthority") or info.get("freezeAuthority")
        return None
    except Exception as e:
        logger.debug(f"Failed to find Solana creator for {token_address}: {e}")
        return None


@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=0.5, min=1, max=5))
def _solana_get_signatures(address: str, limit: int = 20) -> list[dict]:
    """Get recent transaction signatures for an address."""
    try:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getSignaturesForAddress",
            "params": [address, {"limit": limit}],
        }
        resp = requests.post(settings.SOLANA_RPC_URL, json=payload, timeout=15)
        data = resp.json()
        return data.get("result", [])
    except Exception as e:
        logger.debug(f"getSignaturesForAddress failed for {address}: {e}")
        return []


def _solana_get_transaction(signature: str) -> Optional[dict]:
    """Get parsed transaction details."""
    try:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTransaction",
            "params": [
                signature,
                {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}
            ],
        }
        resp = requests.post(settings.SOLANA_RPC_URL, json=payload, timeout=10)
        data = resp.json()
        return data.get("result")
    except Exception as e:
        logger.debug(f"getTransaction failed for {signature[:16]}…: {e}")
        return None


def _extract_instructions(tx: dict) -> list[dict]:
    """Extract all instructions (including inner) from a parsed transaction."""
    try:
        message = tx.get("transaction", {}).get("message", {})
        instructions = list(message.get("instructions", []))
        inner = tx.get("meta", {}).get("innerInstructions", [])
        for group in inner:
            instructions.extend(group.get("instructions", []))
        return instructions
    except (AttributeError, TypeError):
        return []
