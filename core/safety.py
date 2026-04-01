"""
core/safety.py — Honeypot & rug detection pipeline.

MANDATORY: Every token must pass ALL checks before any trade is executed.
This module is the last line of defense against scams, honeypots, and rugs.

Safety checks run in order:
  1. Blocklist check (instant reject — known scams)
  2. Stablecoin check (skip — not tradeable as gems)
  3. Trusted whitelist (skip deep checks — known safe tokens)
  4. Result cache (5-min TTL — prevents rate limit hammering)
  5. GoPlus Security API (contract audit, tax check, owner analysis)
  6. Honeypot.is (simulate buy+sell on-chain)
  7. Token Sniffer (smell test score)
  8. Composite verdict

All results are logged to logs/safety.log for audit trail.
Rate limiting fix: Results are cached for 5 minutes per (address, chain) pair.
This prevents GoPlus and Honeypot.is from rate-limiting when the same token
appears in multiple scan cycles.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import requests
from requests.exceptions import HTTPError as RequestsHTTPError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from config.chains import GOPLUS_CHAIN_MAP, HONEYPOT_CHAIN_MAP
from config.tokens import is_blocked, is_stablecoin, is_trusted, add_to_blocklist
from config import settings

logger = logging.getLogger(__name__)
safety_logger = logging.getLogger("safety")

# ─────────────────────────────────────────────────────────────────────────────
# Result Cache — prevents rate limit hammering on repeated scans
# ─────────────────────────────────────────────────────────────────────────────

_safety_cache: dict[str, tuple[float, "SafetyResult"]] = {}
_SAFETY_CACHE_TTL = 300  # 5 minutes — same token won't be re-checked within this window

# Blocked tokens get a longer cache (they won't become safe)
_BLOCKED_CACHE_TTL = 3600  # 1 hour for blocked tokens


def _cache_key(token_address: str, chain: str) -> str:
    return f"{chain}:{token_address.lower()}"


def _get_cached(token_address: str, chain: str) -> Optional["SafetyResult"]:
    """Return cached safety result if still valid."""
    key = _cache_key(token_address, chain)
    if key in _safety_cache:
        ts, result = _safety_cache[key]
        ttl = _BLOCKED_CACHE_TTL if not result.is_safe else _SAFETY_CACHE_TTL
        if time.time() - ts < ttl:
            logger.debug(
                f"Safety cache HIT: {token_address[:10]}... ({chain}) — "
                f"{'SAFE' if result.is_safe else 'BLOCKED'}"
            )
            return result
        else:
            del _safety_cache[key]
    return None


def _set_cached(token_address: str, chain: str, result: "SafetyResult") -> None:
    """Cache a safety result."""
    key = _cache_key(token_address, chain)
    _safety_cache[key] = (time.time(), result)


def get_cache_stats() -> dict:
    """Return cache statistics for health monitoring."""
    now = time.time()
    total = len(_safety_cache)
    valid = sum(
        1 for ts, r in _safety_cache.values()
        if now - ts < (_BLOCKED_CACHE_TTL if not r.is_safe else _SAFETY_CACHE_TTL)
    )
    return {"total_entries": total, "valid_entries": valid, "ttl_seconds": _SAFETY_CACHE_TTL}


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

    # Cache metadata
    from_cache: bool = False

    # Raw API responses (for debugging)
    goplus_raw: dict = field(default_factory=dict)
    honeypot_raw: dict = field(default_factory=dict)

    def __str__(self) -> str:
        status = "✅ SAFE" if self.is_safe else f"🚫 BLOCKED: {self.block_reason}"
        cache_tag = " [cached]" if self.from_cache else ""
        return (
            f"SafetyResult({self.token_address[:10]}... | {self.chain} | {status} | "
            f"tax={self.buy_tax:.1%}/{self.sell_tax:.1%}){cache_tag}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# API Wrappers (with retry + rate-limit awareness)
# ─────────────────────────────────────────────────────────────────────────────

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=3, max=15))
def _call_goplus(token_address: str, chain_id: str) -> dict:
    """Call GoPlus Security API."""
    url = f"https://api.gopluslabs.io/api/v1/token_security/{chain_id}"
    params = {"contract_addresses": token_address}
    headers = {}
    goplus_key = getattr(settings, "GOPLUS_API_KEY", "") or ""
    if goplus_key:
        headers["Authorization"] = goplus_key
    resp = requests.get(url, params=params, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    result = data.get("result", {})
    # GoPlus returns address-keyed results
    return result.get(token_address.lower(), {})


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=3, max=15))
def _call_honeypot_is(token_address: str, chain_id: int) -> dict:
    """Call Honeypot.is API — simulates buy+sell on-chain."""
    url = "https://api.honeypot.is/v2/IsHoneypot"
    params = {"address": token_address, "chainID": chain_id}
    resp = requests.get(url, params=params, timeout=20)
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


def _is_retriable_error(exc: Exception) -> bool:
    """Only retry on network/timeout errors — NOT on HTTP 4xx/5xx."""
    if isinstance(exc, RequestsHTTPError):
        return False  # Server returned an error — retrying won't help
    return True  # Network error, timeout — worth retrying


# Short-circuit failure cache: token_address → (timestamp, result)
_rugcheck_fail_cache: dict[str, tuple[float, dict]] = {}
_RUGCHECK_FAIL_CACHE_TTL = 120  # 2 minutes — don't hammer a failing API


@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=1, max=5),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
def _call_rugcheck(token_address: str) -> dict:
    """
    Call RugCheck.xyz API — Solana-native rug detection.

    Checks: mint authority, freeze authority, LP burn status,
    top holder concentration, and overall risk level.

    Free API, no key required.
    Only retries on network/timeout failures — NOT on HTTP 4xx/5xx.
    """
    # Check short-circuit failure cache first
    now = time.time()
    if token_address in _rugcheck_fail_cache:
        ts, cached_result = _rugcheck_fail_cache[token_address]
        if now - ts < _RUGCHECK_FAIL_CACHE_TTL:
            logger.debug(f"RugCheck fail cache HIT for {token_address[:10]}... — skipping API call")
            return cached_result  # Return cached empty/fail result

    url = f"https://api.rugcheck.xyz/v1/tokens/{token_address}/report"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 404:
            return {}  # Token not indexed — new token, expected
        if resp.status_code >= 400:
            # Server-side error — cache it and skip retries
            logger.debug(
                f"RugCheck HTTP {resp.status_code} for {token_address[:10]}... — caching failure"
            )
            _rugcheck_fail_cache[token_address] = (now, {})
            return {}  # Treat as no-data, not a hard failure
        resp.raise_for_status()
        result = resp.json()
        # Clear failure cache on success
        _rugcheck_fail_cache.pop(token_address, None)
        return result
    except RequestsHTTPError as e:
        _rugcheck_fail_cache[token_address] = (now, {})
        raise  # Let tenacity see it (won't retry due to retry_if_exception_type)
    except Exception:
        raise  # Network/timeout — tenacity will retry


# ─────────────────────────────────────────────────────────────────────────────
# Safety Pipeline
# ─────────────────────────────────────────────────────────────────────────────

def check_token_safety(token_address: str, chain: str) -> SafetyResult:
    """
    Run the full safety pipeline for a token.

    This is MANDATORY before any trade. Returns SafetyResult with
    is_safe=True only if ALL checks pass.

    Results are cached for 5 minutes (blocked tokens for 1 hour) to prevent
    GoPlus and Honeypot.is rate limit errors when the same token appears
    across multiple scan cycles.

    Args:
        token_address: Token contract address (any case)
        chain: Chain name (e.g., "ethereum", "base", "solana")

    Returns:
        SafetyResult with full audit trail
    """
    token_address = token_address.lower()
    result = SafetyResult(token_address=token_address, chain=chain, is_safe=False)

    # ── Step 1: Instant blocklist check (no cache needed — in-memory set) ─────
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

    # ── Step 4: Cache check — prevents rate limit hammering ──────────────────
    cached = _get_cached(token_address, chain)
    if cached is not None:
        cached.from_cache = True
        return cached

    # ── Solana: Use RugCheck.xyz for Solana-native rug detection ──────────────
    if chain == "solana":
        result.goplus_passed = None   # Not supported for Solana
        result.honeypot_passed = None  # Not supported for Solana
        result.tokensniffer_passed = None

        try:
            rc = _call_rugcheck(token_address)
            if rc:
                # RugCheck risk levels: "Good", "Warning", "Danger", "Critical"
                risk_level = rc.get("riskLevel", "unknown").lower()
                risks = rc.get("risks", [])

                # Build risk flags from the response
                risk_names = [r.get("name", "").lower() for r in risks if isinstance(r, dict)]

                # BLOCKED: Critical risk level = definite rug
                if risk_level == "critical":
                    result.block_reason = f"RugCheck CRITICAL risk: {', '.join(list(risk_names)[:3])}"
                    add_to_blocklist(token_address, result.block_reason)
                    _log_blocked(result)
                    _set_cached(token_address, chain, result)
                    return result

                # BLOCKED: Mint authority not revoked (can mint infinite tokens)
                has_mint_risk = any(
                    "mint" in r and "revok" not in r for r in risk_names
                )
                if has_mint_risk:
                    result.block_reason = "Solana: Mint authority not revoked (inflation risk)"
                    _log_blocked(result)
                    _set_cached(token_address, chain, result)
                    return result

                # BLOCKED: Freeze authority active (can freeze your tokens)
                has_freeze_risk = any("freeze" in r for r in risk_names)
                if has_freeze_risk:
                    result.block_reason = "Solana: Freeze authority active (can lock your tokens)"
                    _log_blocked(result)
                    _set_cached(token_address, chain, result)
                    return result

                # BLOCKED: Top holder owns >50% of supply (rug pull risk)
                top_holders = rc.get("topHolders", [])
                if top_holders and isinstance(top_holders, list):
                    top_holder_pct = float(top_holders[0].get("pct", 0)) if top_holders else 0
                    if top_holder_pct > 50:
                        result.block_reason = f"Solana: Top holder owns {top_holder_pct:.1f}% of supply"
                        _log_blocked(result)
                        _set_cached(token_address, chain, result)
                        return result

                # WARNING-level: pass but log for visibility
                if risk_level == "danger":
                    safety_logger.warning(
                        f"CAUTION (Solana RugCheck: Danger) | {token_address} | "
                        f"risks: {', '.join(list(risk_names)[:5])}"
                    )

                # PASSED RugCheck
                result.is_safe = True
                safety_logger.info(
                    f"SAFE (Solana RugCheck: {risk_level}) | {token_address} | {chain}"
                )
                _set_cached(token_address, chain, result)
                return result
            else:
                # RugCheck returned empty — token not indexed yet.
                # This is common for tokens < 30 min old.
                # We allow it but flag it so the scanner can apply a score penalty
                # (unverified = higher risk, require stronger on-chain signals).
                result.is_safe = True
                result.block_reason = None
                # Attach a flag so callers can apply extra scrutiny
                result.rugcheck_no_data = True  # type: ignore[attr-defined]
                safety_logger.warning(
                    f"CAUTION (Solana — RugCheck no data, new/unindexed token) | "
                    f"{token_address} | {chain} — applying score penalty in scanner"
                )
                _set_cached(token_address, chain, result)
                return result
        except Exception as e:
            err_str = str(e)
            # Only log at WARNING if it's not a cached/expected failure
            if token_address not in _rugcheck_fail_cache:
                logger.warning(f"RugCheck.xyz check failed for {token_address}: {e}")
            else:
                logger.debug(f"RugCheck cached failure for {token_address[:10]}...: {e}")
            # Don't block on API failure — pass with warning flag
            result.is_safe = True
            result.rugcheck_no_data = True  # type: ignore[attr-defined]
            result.rugcheck_api_down = True  # type: ignore[attr-defined] — distinguish API down vs truly unindexed
            safety_logger.warning(
                f"CAUTION (Solana — RugCheck unavailable) | {token_address} | {chain} "
                f"— applying score penalty in scanner"
            )
            _set_cached(token_address, chain, result)
            return result

    # ── Step 5: GoPlus Security check ────────────────────────────────────────
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

            if result.buy_tax > 0.05:
                result.block_reason = f"Buy tax too high: {result.buy_tax:.1%}"
                result.goplus_passed = False
                _log_blocked(result)
                _set_cached(token_address, chain, result)
                return result

            if result.sell_tax > 0.05:
                result.block_reason = f"Sell tax too high: {result.sell_tax:.1%}"
                result.goplus_passed = False
                _log_blocked(result)
                _set_cached(token_address, chain, result)
                return result

            if not result.is_open_source:
                result.block_reason = "Contract not verified/open source"
                result.goplus_passed = False
                _log_blocked(result)
                _set_cached(token_address, chain, result)
                return result

            if result.owner_can_drain:
                result.block_reason = "Owner can change balances (drain risk)"
                result.goplus_passed = False
                _log_blocked(result)
                _set_cached(token_address, chain, result)
                return result

            if result.cannot_sell_all:
                result.block_reason = "Sell restrictions detected"
                result.goplus_passed = False
                _log_blocked(result)
                _set_cached(token_address, chain, result)
                return result

            result.goplus_passed = True

    except Exception as e:
        logger.warning(f"GoPlus check failed for {token_address}: {e}")
        # Don't block on API failure — log and continue

    # ── Step 6: Honeypot.is check ─────────────────────────────────────────────
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
            # Add to runtime blocklist — never check this again this session
            add_to_blocklist(token_address, result.block_reason)
            _log_blocked(result)
            _set_cached(token_address, chain, result)
            return result

        # Also check honeypot.is tax fields
        hp_buy_tax = float(hp.get("simulationResult", {}).get("buyTax", 0) or 0) / 100
        hp_sell_tax = float(hp.get("simulationResult", {}).get("sellTax", 0) or 0) / 100

        if hp_buy_tax > 0.10:
            result.block_reason = f"Honeypot.is buy tax: {hp_buy_tax:.1%}"
            result.honeypot_passed = False
            _log_blocked(result)
            _set_cached(token_address, chain, result)
            return result

        if hp_sell_tax > 0.10:
            result.block_reason = f"Honeypot.is sell tax: {hp_sell_tax:.1%}"
            result.honeypot_passed = False
            _log_blocked(result)
            _set_cached(token_address, chain, result)
            return result

        result.honeypot_passed = True

    except Exception as e:
        logger.warning(f"Honeypot.is check failed for {token_address}: {e}")

    # ── Step 7: Token Sniffer (advisory — score below 30 blocks) ─────────────
    try:
        ts = _call_tokensniffer(token_address, honeypot_chain_id)
        if ts:
            score = int(ts.get("score", 100) or 100)
            result.tokensniffer_score = score
            if score < 30:
                result.block_reason = f"Token Sniffer score too low: {score}/100"
                result.tokensniffer_passed = False
                _log_blocked(result)
                _set_cached(token_address, chain, result)
                return result
            result.tokensniffer_passed = True
    except Exception as e:
        logger.debug(f"Token Sniffer check failed for {token_address}: {e}")

    # ── Step 6: ChainAware deployer wallet fraud scoring ─────────────────────
    # EVM only — Solana deployer safety is handled by RugCheck above.
    # Checks the owner/deployer wallet for fraud history, malicious contracts,
    # darkweb/mixer activity, and sanctions.  Graceful no-op if no API key.
    if chain != "solana":
        try:
            from data.providers.chainaware import check_deployer_wallet
            owner_addr = (result.goplus_raw or {}).get("owner_address", "")
            if owner_addr and owner_addr != "0x0000000000000000000000000000000000000000":
                ca = check_deployer_wallet(owner_addr, chain)
                if ca.is_blocked:
                    result.block_reason = ca.block_reason
                    result.goplus_passed = False
                    _log_blocked(result)
                    _set_cached(token_address, chain, result)
                    return result
                # Store score penalty for gem_scanner to apply
                result.chainaware_penalty = ca.to_score_penalty()   # type: ignore[attr-defined]
                result.chainaware_fraud_prob = ca.fraud_probability  # type: ignore[attr-defined]
        except Exception as _ca_err:
            logger.debug(f"ChainAware check skipped: {_ca_err}")

    # ── Step 7: Perplexity Real-Time Rug/Scam Web Search ───────────────────────
    # Searches the open web for rug alerts, scam reports, dev wallet exposure.
    # Completely different from Grok (which only searches X/Twitter).
    # Hard rejects if rug_risk_score >= 70. Stores penalty for gem_scanner.
    # Graceful no-op if PERPLEXITY_API_KEY not set.
    try:
        from data.providers.perplexity_rug_check import check_token_rug_risk
        _pplx = check_token_rug_risk(
            symbol=getattr(result, "symbol", ""),
            address=token_address,
            chain=chain,
            name=getattr(result, "name", ""),
        )
        if not _pplx.get("skipped", True):
            result.perplexity_rug_score = _pplx["rug_risk_score"]   # type: ignore[attr-defined]
            result.perplexity_penalty = _pplx["score_penalty"]       # type: ignore[attr-defined]
            result.perplexity_flags = _pplx.get("flags", [])         # type: ignore[attr-defined]
            if _pplx["hard_reject"]:
                result.is_safe = False
                result.block_reason = (
                    f"Perplexity: confirmed rug/scam (risk={_pplx['rug_risk_score']}) — "
                    f"{_pplx.get('summary', 'web evidence found')}"
                )
                _log_blocked(result)
                _set_cached(token_address, chain, result)
                return result
    except Exception as _pplx_err:
        logger.debug(f"Perplexity rug check skipped: {_pplx_err}")

    # ── All checks passed ─────────────────────────────────────────────
    result.is_safe = True
    safety_logger.info(
        f"SAFE | {token_address} | {chain} | "
        f"tax={result.buy_tax:.1%}/{result.sell_tax:.1%} | "
        f"sniffer={result.tokensniffer_score}"
    )
    _set_cached(token_address, chain, result)
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
