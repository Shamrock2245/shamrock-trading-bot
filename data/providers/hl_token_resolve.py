"""
data/providers/hl_token_resolve.py — HL perp ticker → on-chain contract resolve

Hyperliquid signals use coin symbols (VVV, GMX, AAVE). Moralis Token Score and
related Data API endpoints require contract addresses. This module:

1. Checks a static map of well-known HL perps → (chain, address)
2. Falls back to Moralis Token Search (Data API) across eth/base/arb/bsc/avax/sol
3. Caches results in-process to protect CU budget

Used by core/hl_perps_scanner before get_token_score().
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)

# In-process cache: symbol → resolve dict | None
_RESOLVE_CACHE: dict[str, tuple[float, Optional[dict]]] = {}
_CACHE_TTL_SEC = float(os.getenv("HL_TOKEN_RESOLVE_TTL_SEC", "3600"))

# Static map for common HL perps (checksum-insensitive; Moralis accepts either).
# Prefer the chain where the token is most liquid / "canonical".
_STATIC: dict[str, dict] = {
    "AAVE": {"chain": "ethereum", "address": "0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9"},
    "UNI": {"chain": "ethereum", "address": "0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984"},
    "LINK": {"chain": "ethereum", "address": "0x514910771AF9Ca656af840dff83E8264EcF986CA"},
    "LTC": {"chain": "ethereum", "address": ""},  # no useful ERC20 — skip
    "GMX": {"chain": "arbitrum", "address": "0xfc5A1A6EB076a2C7aD06eD22C90d7E710E35ad0a"},
    "ARB": {"chain": "arbitrum", "address": "0x912CE59144191C1204E64559FE8253a0e49E6548"},
    "OP": {"chain": "optimism", "address": "0x4200000000000000000000000000000000000042"},
    "APE": {"chain": "ethereum", "address": "0x4d224452801ACEd8B2F0aebE155379bb5D594381"},
    "CRV": {"chain": "ethereum", "address": "0xD533a949740bb3306d119CC777fa900bA034cd52"},
    "LDO": {"chain": "ethereum", "address": "0x5A98FcBEA516Cf06857215779Fd812CA3beF1B32"},
    "MKR": {"chain": "ethereum", "address": "0x9f8F72aA9304c8B593d555F12eF6589cC3A579A2"},
    "SNX": {"chain": "ethereum", "address": "0xC011a73ee8576Fb46F5E1c5751cA3B9Fe0af2a6F"},
    "COMP": {"chain": "ethereum", "address": "0xc00e94Cb662C3520282E6f5717214004A7f26888"},
    "PENDLE": {"chain": "ethereum", "address": "0x808507121B80c02388fAd14726482e061B8da827"},
    "ENA": {"chain": "ethereum", "address": "0x57e114B691Db790C35207b2e685D4A43181e6061"},
    "ONDO": {"chain": "ethereum", "address": ""},  # resolve via Moralis search
    "WIF": {"chain": "solana", "address": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm"},
    "JUP": {"chain": "solana", "address": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN"},
    "PYTH": {"chain": "solana", "address": "HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3"},
    "BONK": {"chain": "solana", "address": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"},
    "W": {"chain": "solana", "address": "85VBFQZC9TZkfaptBWjvUw7YbZjy52A6mjtPGjstQAmQ"},
    "RENDER": {"chain": "solana", "address": "rndrizKT3MK1iimdxRdWabcF7Zg7AR5T4nud4EkHBof"},
    "INJ": {"chain": "ethereum", "address": "0xe28b3B32B6c345A34Ff64674606124Dd5Aceca30"},
    "TIA": {"chain": "ethereum", "address": ""},
    "SUI": {"chain": "ethereum", "address": ""},
    "SEI": {"chain": "ethereum", "address": ""},
    "APT": {"chain": "ethereum", "address": ""},
    "DOT": {"chain": "ethereum", "address": ""},
    "ATOM": {"chain": "ethereum", "address": ""},
    "NEAR": {"chain": "ethereum", "address": ""},
    "AVAX": {"chain": "avalanche", "address": "0xB31f66AA3C1e785363F0875A1B74E27b85FD66c7"},  # WAVAX
    "BNB": {"chain": "bsc", "address": "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c"},  # WBNB
    "SOL": {"chain": "solana", "address": "So11111111111111111111111111111111111111112"},
    "ETH": {"chain": "ethereum", "address": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"},  # WETH
    "BTC": {"chain": "ethereum", "address": "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599"},  # WBTC
    "kPEPE": {"chain": "ethereum", "address": "0x6982508145454cE325dDbE47a25d4ec3d2311933"},
    "kSHIB": {"chain": "ethereum", "address": "0x95aD61b0a150d79219dCF64E1E6Cc01f0B64C4cE"},
    "BRETT": {"chain": "base", "address": "0x532f27101965dd16442E59d40670FaF5eBB142E4"},
    "AERO": {"chain": "base", "address": "0x940181a94A35A4569E4529A3CDfB74e38FD98631"},
    "HYPE": {"chain": "ethereum", "address": ""},  # native HL — no useful EVM map
    "VVV": {"chain": "base", "address": ""},  # resolve via search
    "STBL": {"chain": "ethereum", "address": ""},
    "XMR": {"chain": "ethereum", "address": ""},
    "MON": {"chain": "ethereum", "address": ""},
    "TNSR": {"chain": "solana", "address": "TNSRxcUxoT9xBG3de7PiJyTDYu7kskLqcpddxnEJAS6"},
    "DYDX": {"chain": "ethereum", "address": "0x92D6C1e31e14520e676a687F0a93788B716BEff5"},
    "EIGEN": {"chain": "ethereum", "address": "0xec53bF9167f50cDEB3Ae105f56099aaaB9061F83"},
    "MORPHO": {"chain": "ethereum", "address": "0x58D97B57BB95320F9a05dC918Aef65434969c2B2"},
    "KAITO": {"chain": "base", "address": ""},
    "TRB": {"chain": "ethereum", "address": "0x88dF592F8eb5D7Bd38bFeF7dEb0fBc02cf3778a0"},
    "GRASS": {"chain": "solana", "address": "Grass7B4RdKfBCjTKgSqnXkqjwiGvQyFbuSCUJr3XXjs"},
}

_SEARCH_CHAINS = ("ethereum", "base", "arbitrum", "bsc", "avalanche", "solana")


def _norm_symbol(symbol: str) -> str:
    s = (symbol or "").strip().upper()
    # HL prefixes for 1000x units
    if s.startswith("K") and len(s) > 1 and s[1:].isalpha():
        # keep kPEPE style as stored
        pass
    return s


def resolve_hl_token(symbol: str, use_search: bool = True) -> Optional[dict]:
    """
    Resolve an HL perp ticker to {symbol, chain, address, source}.

    Returns None when no reliable contract is found (caller should stay neutral).
    """
    sym = _norm_symbol(symbol)
    if not sym:
        return None

    now = time.time()
    cached = _RESOLVE_CACHE.get(sym)
    if cached and (now - cached[0]) < _CACHE_TTL_SEC:
        return cached[1]

    result: Optional[dict] = None

    static = _STATIC.get(sym) or _STATIC.get(sym.lstrip("K") if sym.startswith("K") else sym)
    if static and static.get("address"):
        result = {
            "symbol": sym,
            "chain": static["chain"],
            "address": static["address"],
            "source": "static",
        }
    elif use_search:
        try:
            from config import settings as _ms
            _moralis_ok = bool(getattr(_ms, "MORALIS_ENABLED", False) and getattr(_ms, "MORALIS_API_KEY", ""))
        except Exception:
            _moralis_ok = False
        if _moralis_ok:
            result = _search_moralis(sym)

    _RESOLVE_CACHE[sym] = (now, result)
    return result


def _search_moralis(symbol: str) -> Optional[dict]:
    """Best-effort Moralis Token Search across supported chains."""
    try:
        from data.providers.moralis_intelligence import search_tokens
    except Exception as e:
        logger.debug(f"hl_token_resolve: search import failed: {e}")
        return None

    best: Optional[dict] = None
    best_vol = -1.0
    for chain in _SEARCH_CHAINS:
        try:
            hits = search_tokens(symbol, chain=chain, limit=5) or []
        except Exception:
            continue
        for h in hits:
            addr = (h.get("address") or "").strip()
            h_sym = (h.get("symbol") or "").upper()
            if not addr or h_sym != symbol.upper():
                # allow exact symbol match only to avoid wrong token
                if h_sym != symbol.upper():
                    continue
            if not addr:
                continue
            vol = float(h.get("volume_24h") or 0)
            if vol > best_vol:
                best_vol = vol
                best = {
                    "symbol": symbol.upper(),
                    "chain": h.get("chain") or chain,
                    "address": addr,
                    "source": "moralis_search",
                    "volume_24h": vol,
                    "security_score": h.get("security_score"),
                }
    if best:
        logger.info(
            f"hl_token_resolve: {symbol} → {best['chain']}:{best['address'][:10]}… "
            f"(search, vol24h=${best.get('volume_24h', 0):,.0f})"
        )
    return best


def moralis_score_for_hl_coin(symbol: str) -> Optional[dict]:
    """
    Resolve HL coin then fetch Moralis token score.

    Returns score dict with extra keys: resolved_chain, resolved_address, resolve_source.
    None if unresolved or API failure (caller should not hard-block).
    """
    resolved = resolve_hl_token(symbol)
    if not resolved or not resolved.get("address"):
        logger.debug(f"hl_token_resolve: no contract for {symbol} — skip Moralis score")
        return None

    chain = resolved["chain"]
    # normalize chain aliases for moralis_money CHAIN_MAP
    chain_map = {
        "eth": "ethereum",
        "ethereum": "ethereum",
        "base": "base",
        "arbitrum": "arbitrum",
        "arb": "arbitrum",
        "bsc": "bsc",
        "binance": "bsc",
        "avalanche": "avalanche",
        "avax": "avalanche",
        "solana": "solana",
        "sol": "solana",
        "optimism": "optimism",
        "op": "optimism",
        "polygon": "polygon",
    }
    chain = chain_map.get(str(chain).lower(), str(chain).lower())

    try:
        from data.providers.moralis_money import get_token_score

        score = get_token_score(resolved["address"], chain=chain)
        if not score:
            return None
        out = dict(score)
        out["resolved_chain"] = chain
        out["resolved_address"] = resolved["address"]
        out["resolve_source"] = resolved.get("source")
        return out
    except Exception as e:
        logger.debug(f"hl_token_resolve: score failed for {symbol}: {e}")
        return None
