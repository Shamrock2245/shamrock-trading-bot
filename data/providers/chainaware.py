"""
ChainAware Behavioral Prediction — Deployer Wallet Fraud Scoring
================================================================
Wraps the ChainAware MCP / REST API to score the deployer/owner wallet of
every gem candidate.  Returns a fraud probability (0–1) and 19 forensic
indicators (darkweb, mixer, honeypot interactions, malicious contracts, etc.)

This is a LAYER ON TOP of GoPlus token-level safety — it checks the WALLET
that deployed the token, not the token contract itself.

Hard-reject thresholds (configurable via env / settings):
  CHAINAWARE_FRAUD_HARD_REJECT  = 0.70   # ≥70% fraud probability → block
  CHAINAWARE_MALICIOUS_CONTRACTS = 1     # ≥1 malicious contract created → block

Free tier: 100 checks/day, no credit card required.
API key stored as: CHAINAWARE_API_KEY (optional — graceful no-op if absent)
Supported chains: ETH, BNB, BASE, POLYGON, SOLANA
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
_API_BASE = "https://prediction.mcp.chainaware.ai"
_TIMEOUT = 8  # seconds — don't slow down the scan cycle
_CACHE_TTL = 3600  # 1 hour — deployer fraud status doesn't change
_HARD_REJECT_PROB = float(os.getenv("CHAINAWARE_FRAUD_HARD_REJECT", "0.70"))
_MALICIOUS_CONTRACT_LIMIT = int(os.getenv("CHAINAWARE_MALICIOUS_CONTRACTS", "1"))

# In-memory cache: {(wallet, chain): (timestamp, result)}
_cache: dict[tuple[str, str], tuple[float, "ChainAwareResult"]] = {}

# Chain name → ChainAware network identifier
_CHAIN_MAP = {
    "ethereum": "ETH",
    "base": "BASE",
    "bsc": "BNB",
    "polygon": "POLYGON",
    "solana": "SOLANA",
    "arbitrum": "ETH",  # ChainAware doesn't have Arbitrum — use ETH scoring
}


@dataclass
class ChainAwareResult:
    wallet_address: str
    chain: str
    checked: bool = False           # False if API unavailable / no key
    fraud_probability: float = 0.0  # 0.0–1.0
    fraud_status: str = "unknown"   # "Fraud" | "Not Fraud" | "New Address" | "unknown"
    is_blocked: bool = False
    block_reason: str = ""

    # Forensic indicators (all strings from API, "0" = clean)
    cybercrime: str = "0"
    money_laundering: str = "0"
    malicious_contracts_created: int = 0
    darkweb_transactions: str = "0"
    mixer_use: str = "0"
    honeypot_related: str = "0"
    sanctioned: bool = False
    phishing: str = "0"
    financial_crime: str = "0"
    gas_abuse: str = "0"

    # Wallet profile
    wallet_age_days: int = 0
    total_balance_usd: float = 0.0
    transaction_count: int = 0
    experience_score: int = 0

    error: str = ""

    @property
    def risk_label(self) -> str:
        if not self.checked:
            return "unchecked"
        if self.fraud_probability >= 0.70:
            return "HIGH_RISK"
        if self.fraud_probability >= 0.40:
            return "MEDIUM_RISK"
        return "LOW_RISK"

    def to_score_penalty(self) -> float:
        """
        Convert fraud result to a gem score penalty (0 to -25 points).
        Only applied when ChainAware is available and the check ran.
        """
        if not self.checked or self.is_blocked:
            return 0.0
        penalty = 0.0
        # Fraud probability penalty: up to -20 pts
        penalty += self.fraud_probability * 20.0
        # Malicious contracts: -5 pts each (capped at -15)
        penalty += min(self.malicious_contracts_created * 5.0, 15.0)
        # Mixer use: -3 pts
        if self.mixer_use not in ("0", "", "None", None):
            penalty += 3.0
        # Darkweb: -5 pts
        if self.darkweb_transactions not in ("0", "", "None", None):
            penalty += 5.0
        # Sanctioned: -10 pts
        if self.sanctioned:
            penalty += 10.0
        return min(penalty, 25.0)


def _get_api_key() -> Optional[str]:
    """Return the ChainAware API key from environment, or None if not set."""
    return os.getenv("CHAINAWARE_API_KEY") or None


def _get_cached(wallet: str, chain: str) -> Optional[ChainAwareResult]:
    key = (wallet.lower(), chain)
    entry = _cache.get(key)
    if entry and (time.time() - entry[0]) < _CACHE_TTL:
        return entry[1]
    return None


def _set_cached(wallet: str, chain: str, result: ChainAwareResult) -> None:
    _cache[(wallet.lower(), chain)] = (time.time(), result)


def check_deployer_wallet(
    wallet_address: str,
    chain: str,
    token_symbol: str = "?",
) -> ChainAwareResult:
    """
    Run ChainAware behavioral prediction on a deployer/owner wallet.

    Args:
        wallet_address: The deployer/owner wallet address from GoPlus
        chain: Bot chain name ("ethereum", "base", "bsc", "polygon", "solana")
        token_symbol: For logging only

    Returns:
        ChainAwareResult with fraud probability and forensic indicators.
        If API key is missing or API is unavailable, returns a safe default
        (checked=False) so the pipeline is never blocked by API downtime.
    """
    if not wallet_address or wallet_address in ("", "0x0000000000000000000000000000000000000000"):
        return ChainAwareResult(wallet_address=wallet_address, chain=chain, checked=False,
                                error="No deployer address available")

    wallet_address = wallet_address.lower()

    # Cache check
    cached = _get_cached(wallet_address, chain)
    if cached is not None:
        return cached

    api_key = _get_api_key()
    if not api_key:
        # Graceful no-op — don't block the pipeline if no key configured
        result = ChainAwareResult(wallet_address=wallet_address, chain=chain, checked=False,
                                  error="CHAINAWARE_API_KEY not set")
        return result

    network = _CHAIN_MAP.get(chain, "ETH")
    result = ChainAwareResult(wallet_address=wallet_address, chain=chain)

    try:
        # ── Fraud Detection ───────────────────────────────────────────────────
        fraud_url = f"{_API_BASE}/fraud_detection"
        fraud_resp = requests.post(
            fraud_url,
            json={"apiKey": api_key, "network": network, "walletAddress": wallet_address},
            timeout=_TIMEOUT,
        )
        if fraud_resp.status_code == 200:
            fd = fraud_resp.json()
            result.checked = True
            result.fraud_probability = float(fd.get("probabilityFraud", 0.0))
            result.fraud_status = fd.get("status", "unknown")

            forensics = fd.get("forensic_details", {})
            result.cybercrime = str(forensics.get("cybercrime", "0"))
            result.money_laundering = str(forensics.get("money_laundering", "0"))
            result.malicious_contracts_created = int(
                forensics.get("number_of_malicious_contracts_created", 0) or 0
            )
            result.darkweb_transactions = str(forensics.get("darkweb_transactions", "0"))
            result.mixer_use = str(forensics.get("mixer", "0"))
            result.honeypot_related = str(forensics.get("honeypot_related_address", "0"))
            result.phishing = str(forensics.get("phishing_activities", "0"))
            result.financial_crime = str(forensics.get("financial_crime", "0"))
            result.gas_abuse = str(forensics.get("gas_abuse", "0"))

            # Sanction check
            sanction_data = fd.get("sanctionData", [])
            result.sanctioned = any(
                s.get("isSanctioned", False) for s in sanction_data if isinstance(s, dict)
            )

            # ── Hard reject checks ────────────────────────────────────────────
            if result.fraud_probability >= _HARD_REJECT_PROB:
                result.is_blocked = True
                result.block_reason = (
                    f"ChainAware: deployer fraud probability {result.fraud_probability:.0%} "
                    f"≥ {_HARD_REJECT_PROB:.0%} threshold"
                )
                logger.warning(
                    f"🚫 CHAINAWARE BLOCK [{token_symbol}] deployer {wallet_address[:10]}… "
                    f"fraud_prob={result.fraud_probability:.0%} chain={chain}"
                )
            elif result.malicious_contracts_created >= _MALICIOUS_CONTRACT_LIMIT:
                result.is_blocked = True
                result.block_reason = (
                    f"ChainAware: deployer created {result.malicious_contracts_created} "
                    f"malicious contract(s)"
                )
                logger.warning(
                    f"🚫 CHAINAWARE BLOCK [{token_symbol}] deployer {wallet_address[:10]}… "
                    f"malicious_contracts={result.malicious_contracts_created}"
                )
            elif result.sanctioned:
                result.is_blocked = True
                result.block_reason = "ChainAware: deployer wallet is sanctioned"
                logger.warning(
                    f"🚫 CHAINAWARE BLOCK [{token_symbol}] deployer {wallet_address[:10]}… "
                    f"SANCTIONED"
                )
            else:
                logger.debug(
                    f"✅ ChainAware OK [{token_symbol}] deployer {wallet_address[:10]}… "
                    f"fraud_prob={result.fraud_probability:.0%} risk={result.risk_label}"
                )
        else:
            result.error = f"HTTP {fraud_resp.status_code}"
            logger.debug(f"ChainAware fraud API returned {fraud_resp.status_code} for {wallet_address[:10]}")

        # ── Behavioral Profile (non-blocking — enrichment only) ───────────────
        if result.checked and not result.is_blocked:
            try:
                behav_url = f"{_API_BASE}/behavioral_prediction"
                behav_resp = requests.post(
                    behav_url,
                    json={"apiKey": api_key, "network": network, "walletAddress": wallet_address},
                    timeout=_TIMEOUT,
                )
                if behav_resp.status_code == 200:
                    bd = behav_resp.json()
                    user_details = bd.get("userDetails", {})
                    result.wallet_age_days = int(user_details.get("wallet_age_days", 0) or 0)
                    result.total_balance_usd = float(user_details.get("total_balance_usd", 0.0) or 0.0)
                    result.transaction_count = int(user_details.get("transaction_count", 0) or 0)
                    exp = bd.get("experience", {})
                    result.experience_score = int(exp.get("Value", 0) or 0)
            except Exception as e:
                logger.debug(f"ChainAware behavioral profile failed: {e}")

    except requests.exceptions.Timeout:
        result.error = "timeout"
        logger.debug(f"ChainAware timeout for {wallet_address[:10]}… — skipping")
    except Exception as e:
        result.error = str(e)
        logger.debug(f"ChainAware error for {wallet_address[:10]}…: {e}")

    _set_cached(wallet_address, chain, result)
    return result


def batch_check_deployers(
    wallet_chain_pairs: list[tuple[str, str]],
    token_symbols: Optional[list[str]] = None,
) -> list[ChainAwareResult]:
    """
    Check multiple deployer wallets in sequence.
    Used by sniper_discovery.py to score wallet candidates.
    """
    results = []
    symbols = token_symbols or ["?"] * len(wallet_chain_pairs)
    for (wallet, chain), sym in zip(wallet_chain_pairs, symbols):
        results.append(check_deployer_wallet(wallet, chain, sym))
    return results
