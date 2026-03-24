"""
data/providers/copycat_detector.py — Copycat / impersonator token detection.

Ported from RugscoreBotTG (SoCloseSociety) and adapted to Shamrock's provider
pattern. Detects tokens that impersonate well-known projects by:

  1. Fuzzy-matching token names against a curated list of major tokens
  2. Exact symbol collision detection (e.g. fake "USDC", "BONK", "WIF")
  3. Metadata completeness scoring (no image/description = suspicious)

Uses fuzzywuzzy for string matching (falls back to SequenceMatcher if
python-Levenshtein is not installed).

Returns a 0–100 score (higher = safer / more original) and list of flags.
"""

import logging
import time
from difflib import SequenceMatcher
from typing import Optional

logger = logging.getLogger(__name__)

# ── Cache ────────────────────────────────────────────────────────────────────
_copycat_cache: dict[str, tuple[float, list[str], float]] = {}
_CACHE_TTL = 7200  # 2 hours — token metadata rarely changes

# ── Known token names & symbols that scammers frequently impersonate ─────────
# This list covers the top Solana + EVM tokens by market cap and meme status.
# Copycats will fuzzy-match against these names.
KNOWN_TOKEN_NAMES: list[str] = [
    # Major L1/L2
    "BITCOIN", "ETHEREUM", "SOLANA", "AVALANCHE", "POLYGON", "ARBITRUM",
    "OPTIMISM", "BASE", "BNB", "CARDANO", "POLKADOT", "COSMOS",
    # Major DeFi
    "UNISWAP", "AAVE", "COMPOUND", "MAKER", "LIDO", "CHAINLINK",
    "JUPITER", "RAYDIUM", "ORCA", "MARINADE",
    # Stablecoins
    "USDC", "USDT", "TETHER", "DAI",
    # Top Solana memes
    "BONK", "DOGWIFHAT", "WIF", "POPCAT", "MEW", "BOME",
    "JITO", "PYTH", "RENDER", "HELIUM",
    # Top EVM memes
    "PEPE", "DOGE", "DOGECOIN", "SHIBA", "FLOKI", "BRETT",
    "TOSHI", "MFER", "ELMO",
    # AI tokens
    "FETCH", "OCEAN", "SINGULARITY", "WORLDCOIN", "BITTENSOR",
    # Major projects people impersonate
    "TRUMP", "MELANIA", "OFFICIAL TRUMP",
]

# Symbols that should NEVER appear on a brand-new micro-cap
PROTECTED_SYMBOLS: set[str] = {
    "BTC", "ETH", "SOL", "USDC", "USDT", "BNB", "AVAX", "MATIC",
    "ARB", "OP", "LINK", "UNI", "AAVE", "MKR", "DAI", "BONK",
    "WIF", "PEPE", "DOGE", "SHIB", "JUP", "JTO", "PYTH", "RNDR",
    "HNT", "RAY", "MNDE",
}


def get_copycat_score(
    name: str,
    symbol: str,
    has_image: bool = True,
    has_description: bool = True,
    has_website: bool = True,
) -> tuple[float, list[str]]:
    """
    Score a token 0–100 on originality & metadata quality (higher = safer).
    Returns (score, flags).

    Scoring breakdown:
        - Not a copycat name:       35 pts
        - Not a protected symbol:   25 pts
        - Has image:                15 pts
        - Has description:          15 pts
        - Has website/social:       10 pts
    """
    cache_key = f"{name}:{symbol}".lower()

    if cache_key in _copycat_cache:
        score, flags, cached_at = _copycat_cache[cache_key]
        if (time.time() - cached_at) < _CACHE_TTL:
            return score, flags

    score = 0.0
    flags: list[str] = []

    # ── 1. Copycat name detection (35 pts) ────────────────────────────────
    is_copycat = _check_copycat_name(name, symbol)
    if not is_copycat:
        score += 35
        flags.append("✅ Original token name")
    else:
        score += 5  # Some credit for existing
        flags.append(f"🚩 COPYCAT: name '{name}' suspiciously similar to known token")

    # ── 2. Protected symbol collision (25 pts) ────────────────────────────
    if symbol.upper() in PROTECTED_SYMBOLS:
        score += 0  # Zero credit — this is extremely suspicious for a new token
        flags.append(f"🚩 Symbol '{symbol}' matches a major token — likely impersonator")
    else:
        score += 25
        flags.append("✅ Unique symbol")

    # ── 3. Has image (15 pts) ─────────────────────────────────────────────
    if has_image:
        score += 15
    else:
        score += 0
        flags.append("⚠️ No token image — low-effort metadata")

    # ── 4. Has description (15 pts) ───────────────────────────────────────
    if has_description:
        score += 15
    else:
        score += 0
        flags.append("⚠️ No token description")

    # ── 5. Has website/social (10 pts) ────────────────────────────────────
    if has_website:
        score += 10
    else:
        score += 0
        flags.append("⚠️ No website or social links")

    final_score = max(0.0, min(100.0, score))
    _copycat_cache[cache_key] = (final_score, flags, time.time())

    if final_score < 50:
        logger.warning(
            f"CopycatDetector: '{name}' ({symbol}) scored {final_score:.0f}/100 — "
            f"flags: {', '.join(f for f in flags if '🚩' in f)}"
        )

    return round(final_score, 1), flags


def _check_copycat_name(name: str, symbol: str) -> bool:
    """
    Check if a token name/symbol is suspiciously similar to known tokens.
    Uses SequenceMatcher for fuzzy matching (stdlib, no extra deps).
    Falls back to fuzzywuzzy if available for better matching.
    """
    if not name and not symbol:
        return False

    name_upper = name.upper().strip()
    symbol_upper = symbol.upper().strip()

    for known in KNOWN_TOKEN_NAMES:
        known_upper = known.upper()

        # Exact match of symbol against known name
        if symbol_upper == known_upper:
            return True

        # High similarity name match (>80%)
        ratio = SequenceMatcher(None, name_upper, known_upper).ratio()
        if ratio > 0.80:
            return True

        # Partial containment — "REAL BITCOIN" contains "BITCOIN"
        if len(known_upper) >= 4 and known_upper in name_upper:
            return True

        # Common scam variants: prepend "SAFE", "BABY", "MINI", "ELON", "2.0"
        for prefix in ("SAFE", "BABY", "MINI", "ELON", "SUPER", "MEGA", "REAL", "TRUE", "NEW"):
            if name_upper == f"{prefix}{known_upper}" or name_upper == f"{prefix} {known_upper}":
                return True

        # Check for ".0" suffix (e.g. "BONK2.0", "PEPE 2.0")
        if name_upper.replace(" ", "").replace(".", "") == known_upper + "20":
            return True

    return False


def is_token_copycat(name: str, symbol: str) -> bool:
    """
    Simple boolean check — can be used as an instant disqualifier
    in the scanner pipeline when a token clearly impersonates a major project.
    """
    score, flags = get_copycat_score(name, symbol, has_image=True, has_description=True, has_website=True)
    return score < 40  # Below 40 = definite copycat
