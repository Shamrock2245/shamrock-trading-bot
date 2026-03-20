"""
core/safety.py — Honeypot & rug detection pipeline.

MANDATORY: Every token must pass ALL checks before any trade is executed.
This module is the last line of defense against scams, honeypots, and rugs.

Safety checks run in order:
  1. Blocklist check (instant reject — known scams)
  2. Stablecoin check (skip — not tradeable as gems)
  3. GoPlus Security API (contract audit, tax check, owner analysis)
  4. Honeypot.is (simulate buy+sell on-chain)
  5. Token Sniffer (smell test score)
  6. Composite verdict

All results are logged to logs/safety.log for audit trail.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from config.chains import GOPLUS_CHAIN_MAP, HONEYPOT_CHAIN_MAP
from config.tokens import is_blocked, is_stablecoin, is_trusted, add_to_blocklist
from config import settings

logger = logging.getLogger(__name__)
safety_logger = logging.getLogger("safety")

# ─────────────────────────────────────────────────────────────────────────────
# Data Classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SafetyResult:
    """Result of the full safety pipeline for a token."""
    token_address: str
    chain: str
    is_safe: bool
    block_reason: Optional[str] = None

    # Individual check results
    goplus_passed: Optional[bool] = None
    honeypot_passed: Optional[bool] = None
    tokensniffer_passed: Optional[bool] = None

    # Key metrics
    buy_tax: float = 0.0
    sell_tax: float = 0.0
    is_honeypot: bool = False
    is_open_source: bool = True
    owner_can_drain: bool = False
    cannot_sell_all: bool = False
    holder_count: int = 0
    tokensniffer_score: int = 100

    # Raw API responses (for debugging)
    goplus_raw: dict = field(default_factory=dict)
    honeypot_raw: dict = field(default_factory=dict)

    def __str__(self) -> str:
        status = "✅ SAFE" if self.is_safe else f"🚫 BLOCKED: {self.block_reason}"
        return (
            f"SafetyResult({self.token_address[:10]}... | {self.chain} | {status} | "
            f"tax={self.buy_tax:.1%}/{self.sell_tax:.1%})"
        )


# ─────────────────────────────────────────────────────────────────────────────
# API Wrappers
# ─────────────────────────────────────────────────────────────────────────────

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _call_goplus(token_address: str, chain_id: str) -> dict:
    """Call GoPlus Security API."""
    url = f"https://api.gopluslabs.io/api/v1/token_security/{chain_id}"
    params = {"contract_addresses": token_address}
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    result = data.get("result", {})
    # GoPlus returns address-keyed results
    return result.get(token_address.lower(), {})


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _call_honeypot_is(token_address: str, chain_id: int) -> dict:
    """Call Honeypot.is API — simulates buy+sell on-chain."""
    url = "https://api.honeypot.is/v2/IsHoneypot"
    params = {"address": token_address, "chainID": chain_id}
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=8))
def _call_tokensniffer(token_address: str, chain_id: int) -> dict:
    """Call Token Sniffer API."""
    api_key = settings.TOKEN_SNIFFER_API_KEY
    if not api_key:
        return {}
    url = f"https://tokensniffer.com/api/v2/tokens/{chain_id}/{token_address}"
    headers = {"x-api-key": api_key}
    resp = requests.get(url, headers=headers, timeout=15)
    if resp.status_code == 404:
        return {}  # Token not indexed yet — not a blocker
    resp.raise_for_status()
    return resp.json()


# ─────────────────────────────────────────────────────────────────────────────
# Safety Pipeline
# ─────────────────────────────────────────────────────────────────────────────

def check_token_safety(token_address: str, chain: str) -> SafetyResult:
    """
    Run the full safety pipeline for a token.

    This is MANDATORY before any trade. Returns SafetyResult with
    is_safe=True only if ALL checks pass.

    Args:
        token_address: Token contract address (any case)
        chain: Chain name (e.g., "ethereum", "base")

    Returns:
        SafetyResult with full audit trail
    """
    token_address = token_address.lower()
    result = SafetyResult(token_address=token_address, chain=chain, is_safe=False)

    # ── Step 1: Instant blocklist check ──────────────────────────────────────
    if is_blocked(token_address):
        result.block_reason = "On permanent blocklist"
        _log_blocked(result)
        return result

    # ── Step 2: Stablecoin check ──────────────────────────────────────────────
    if is_stablecoin(token_address):
        result.block_reason = "Stablecoin — not a gem target"
        _log_blocked(result)
        return result

    # ── Step 3: Trusted whitelist — skip deep checks ──────────────────────────
    if is_trusted(token_address):
        result.is_safe = True
        result.goplus_passed = True
        result.honeypot_passed = True
        result.tokensniffer_passed = True
        logger.debug(f"Token {token_address[:10]}... is whitelisted — skipping checks")
        return result

    # ── Step 4: GoPlus Security check ────────────────────────────────────────
    goplus_chain_id = GOPLUS_CHAIN_MAP.get(chain, "1")
    try:
        gp = _call_goplus(token_address, goplus_chain_id)
        result.goplus_raw = gp

        if gp:
            result.buy_tax = float(gp.get("buy_tax", 0) or 0)
            result.sell_tax = float(gp.get("sell_tax", 0) or 0)
            result.is_open_source = gp.get("is_open_source", "1") == "1"
            result.owner_can_drain = gp.get("owner_change_balance", "0") == "1"
            result.cannot_sell_all = gp.get("cannot_sell_all", "0") == "1"
            result.holder_count = int(gp.get("holder_count", 0) or 0)

            # GoPlus failure conditions
            if result.buy_tax > 0.05:
                result.block_reason = f"Buy tax too high: {result.buy_tax:.1%}"
                result.goplus_passed = False
                _log_blocked(result)
                return result

            if result.sell_tax > 0.05:
                result.block_reason = f"Sell tax too high: {result.sell_tax:.1%}"
                result.goplus_passed = False
                _log_blocked(result)
                return result

            if not result.is_open_source:
                result.block_reason = "Contract not verified/open source"
                result.goplus_passed = False
                _log_blocked(result)
                return result

            if result.owner_can_drain:
                result.block_reason = "Owner can change balances (drain risk)"
                result.goplus_passed = False
                _log_blocked(result)
                return result

            if result.cannot_sell_all:
                result.block_reason = "Sell restrictions detected"
                result.goplus_passed = False
                _log_blocked(result)
                return result

            result.goplus_passed = True

    except Exception as e:
        logger.warning(f"GoPlus check failed for {token_address}: {e}")
        # Don't block on API failure — log and continue to next check

    # ── Step 5: Honeypot.is check ─────────────────────────────────────────────
    honeypot_chain_id = HONEYPOT_CHAIN_MAP.get(chain, 1)
    try:
        hp = _call_honeypot_is(token_address, honeypot_chain_id)
        result.honeypot_raw = hp

        is_hp = hp.get("isHoneypot", False)
        result.is_honeypot = is_hp

        if is_hp:
            reason = hp.get("honeypotReason", "Unknown honeypot pattern")
            result.block_reason = f"HONEYPOT DETECTED: {reason}"
            result.honeypot_passed = False
            # Add to runtime blocklist so we never check this again
            add_to_blocklist(token_address, result.block_reason)
            _log_blocked(result)
            return result

        # Also check honeypot.is tax fields
        hp_buy_tax = float(hp.get("simulationResult", {}).get("buyTax", 0) or 0) / 100
        hp_sell_tax = float(hp.get("simulationResult", {}).get("sellTax", 0) or 0) / 100

        if hp_buy_tax > 0.10:
            result.block_reason = f"Honeypot.is buy tax: {hp_buy_tax:.1%}"
            result.honeypot_passed = False
            _log_blocked(result)
            return result

        if hp_sell_tax > 0.10:
            result.block_reason = f"Honeypot.is sell tax: {hp_sell_tax:.1%}"
            result.honeypot_passed = False
            _log_blocked(result)
            return result

        result.honeypot_passed = True

    except Exception as e:
        logger.warning(f"Honeypot.is check failed for {token_address}: {e}")

    # ── Step 6: Token Sniffer (advisory — score below 30 blocks) ─────────────
    try:
        ts = _call_tokensniffer(token_address, honeypot_chain_id)
        if ts:
            score = int(ts.get("score", 100) or 100)
            result.tokensniffer_score = score
            if score < 30:
                result.block_reason = f"Token Sniffer score too low: {score}/100"
                result.tokensniffer_passed = False
                _log_blocked(result)
                return result
            result.tokensniffer_passed = True
    except Exception as e:
        logger.debug(f"Token Sniffer check failed for {token_address}: {e}")

    # ── All checks passed ─────────────────────────────────────────────────────
    result.is_safe = True
    safety_logger.info(
        f"SAFE | {token_address} | {chain} | "
        f"tax={result.buy_tax:.1%}/{result.sell_tax:.1%} | "
        f"sniffer={result.tokensniffer_score}"
    )
    return result


def _log_blocked(result: SafetyResult) -> None:
    """Log a blocked token to the safety log."""
    safety_logger.warning(
        f"BLOCKED | {result.token_address} | {result.chain} | {result.block_reason}"
    )


def is_safe_to_trade(token_address: str, chain: str) -> bool:
    """
    Simple boolean wrapper for the safety pipeline.
    Use check_token_safety() for full audit details.
    """
    return check_token_safety(token_address, chain).is_safe
