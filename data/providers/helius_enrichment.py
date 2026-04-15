"""
data/providers/helius_enrichment.py — Solana Token Enrichment via Helius DAS + Moralis Solana Gateway

Provides rich on-chain metadata for Solana gem candidates that goes beyond what
DexScreener and Moralis Money return. Used by the gem scorer to improve signal
quality for Solana tokens specifically.

Data sources (in priority order):
  1. Helius DAS API  — getAsset, getTokenAccounts, Enhanced Transactions
     Uses HELIUS_API_KEY from settings (already configured for bundle_detector)
  2. Moralis Solana Gateway — token price, metadata, wallet portfolio
     Uses MORALIS_API_KEY (already paid, currently unused for Solana enrichment)
  3. Public Solana RPC — fallback, no key required

Enrichment fields returned:
  - holder_count          : total unique holders
  - top10_holder_pct      : % supply held by top 10 wallets (rug risk signal)
  - creator_address       : token creator/deployer address
  - is_mutable_metadata   : True = creator can rug-pull metadata
  - is_mint_authority_set : True = creator can mint more supply
  - is_freeze_authority   : True = creator can freeze wallets
  - moralis_price_usd     : real-time price from Moralis Solana gateway
  - moralis_price_change  : 24h price change %
  - smart_wallet_count    : # of known smart/sniper wallets holding this token
  - sniper_score_bonus    : score bonus (0-15) based on enrichment signals

All functions are safe to call with no key — they degrade gracefully to None.
Results are cached in memory for 5 minutes to avoid hammering APIs.
"""

from __future__ import annotations

import time
import logging
import threading
from dataclasses import dataclass, field
from typing import Optional

from data.http_session import get_session

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
try:
    from config import settings
    _HELIUS_KEY = getattr(settings, "HELIUS_API_KEY", "") or ""
    _MORALIS_KEY = getattr(settings, "MORALIS_API_KEY", "") or ""
except Exception:
    _HELIUS_KEY = ""
    _MORALIS_KEY = ""

_HELIUS_RPC = (
    f"https://mainnet.helius-rpc.com/?api-key={_HELIUS_KEY}"
    if _HELIUS_KEY
    else "https://api.mainnet-beta.solana.com"
)
_HELIUS_API_BASE = "https://api.helius.xyz/v0"
_MORALIS_SOL_BASE = "https://solana-gateway.moralis.io"

_CACHE_TTL = 300  # 5 minutes
_cache: dict[str, tuple[float, "SolanaTokenEnrichment"]] = {}
_cache_lock = threading.Lock()

# ── Data Model ────────────────────────────────────────────────────────────────
@dataclass
class SolanaTokenEnrichment:
    mint: str
    holder_count: Optional[int] = None
    top10_holder_pct: Optional[float] = None      # 0.0–100.0
    creator_address: Optional[str] = None
    is_mutable_metadata: Optional[bool] = None
    is_mint_authority_set: Optional[bool] = None
    is_freeze_authority: Optional[bool] = None
    moralis_price_usd: Optional[float] = None
    moralis_price_change_24h: Optional[float] = None
    moralis_exchange: Optional[str] = None
    smart_wallet_count: int = 0
    sniper_score_bonus: float = 0.0
    data_source: str = "none"
    fetched_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "mint": self.mint,
            "holder_count": self.holder_count,
            "top10_holder_pct": self.top10_holder_pct,
            "creator_address": self.creator_address,
            "is_mutable_metadata": self.is_mutable_metadata,
            "is_mint_authority_set": self.is_mint_authority_set,
            "is_freeze_authority": self.is_freeze_authority,
            "moralis_price_usd": self.moralis_price_usd,
            "moralis_price_change_24h": self.moralis_price_change_24h,
            "moralis_exchange": self.moralis_exchange,
            "smart_wallet_count": self.smart_wallet_count,
            "sniper_score_bonus": self.sniper_score_bonus,
            "data_source": self.data_source,
        }


# ── Helius DAS: getAsset ──────────────────────────────────────────────────────
def _helius_get_asset(mint: str) -> Optional[dict]:
    """Fetch rich token metadata via Helius DAS getAsset RPC method."""
    if not _HELIUS_KEY:
        return None
    try:
        resp = get_session().post(
            _HELIUS_RPC,
            json={"jsonrpc": "2.0", "id": 1, "method": "getAsset", "params": {"id": mint}},
            timeout=8,
        )
        if resp.status_code == 200:
            result = resp.json().get("result", {})
            return result
    except Exception as e:
        logger.debug(f"Helius getAsset error for {mint}: {e}")
    return None


# ── Helius DAS: getTokenAccounts ──────────────────────────────────────────────
def _helius_get_token_accounts(mint: str, limit: int = 20) -> list[dict]:
    """Fetch top token holder accounts via Helius DAS getTokenAccounts."""
    if not _HELIUS_KEY:
        return []
    try:
        resp = get_session().post(
            _HELIUS_RPC,
            json={
                "jsonrpc": "2.0", "id": 1,
                "method": "getTokenAccounts",
                "params": {"mint": mint, "limit": limit},
            },
            timeout=8,
        )
        if resp.status_code == 200:
            result = resp.json().get("result", {})
            return result.get("token_accounts", [])
    except Exception as e:
        logger.debug(f"Helius getTokenAccounts error for {mint}: {e}")
    return []


# ── Helius Enhanced Transactions ──────────────────────────────────────────────
def _helius_get_wallet_transactions(wallet: str, limit: int = 10) -> list[dict]:
    """
    Fetch enriched transaction history for a wallet via Helius Enhanced Transactions API.
    Returns parsed swap/transfer events — much richer than raw RPC transactions.
    Used by sniper_discovery to understand wallet trading patterns.
    """
    if not _HELIUS_KEY:
        return []
    try:
        resp = get_session().get(
            f"{_HELIUS_API_BASE}/addresses/{wallet}/transactions",
            params={"api-key": _HELIUS_KEY, "limit": limit, "type": "SWAP"},
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json() if isinstance(resp.json(), list) else []
    except Exception as e:
        logger.debug(f"Helius enhanced transactions error for {wallet}: {e}")
    return []


# ── Moralis Solana Gateway ────────────────────────────────────────────────────
def _moralis_solana_price(mint: str) -> Optional[dict]:
    """Fetch real-time Solana token price from Moralis Solana Gateway."""
    if not _MORALIS_KEY:
        return None
    try:
        resp = get_session().get(
            f"{_MORALIS_SOL_BASE}/token/mainnet/{mint}/price",
            headers={"X-API-Key": _MORALIS_KEY},
            timeout=8,
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        logger.debug(f"Moralis Solana price error for {mint}: {e}")
    return None


def _moralis_solana_metadata(mint: str) -> Optional[dict]:
    """Fetch Solana token metadata from Moralis Solana Gateway."""
    if not _MORALIS_KEY:
        return None
    try:
        resp = get_session().get(
            f"{_MORALIS_SOL_BASE}/token/mainnet/{mint}/metadata",
            headers={"X-API-Key": _MORALIS_KEY},
            timeout=8,
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        logger.debug(f"Moralis Solana metadata error for {mint}: {e}")
    return None


def _moralis_solana_wallet_portfolio(wallet: str) -> Optional[dict]:
    """
    Fetch Solana wallet portfolio from Moralis Solana Gateway.
    Used by sniper_discovery to check what tokens a sniper wallet holds.
    """
    if not _MORALIS_KEY:
        return None
    try:
        resp = get_session().get(
            f"{_MORALIS_SOL_BASE}/account/mainnet/{wallet}/portfolio",
            headers={"X-API-Key": _MORALIS_KEY},
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        logger.debug(f"Moralis Solana portfolio error for {wallet}: {e}")
    return None


def _moralis_solana_token_pairs(mint: str) -> list[dict]:
    """Fetch Solana token trading pairs from Moralis Solana Gateway."""
    if not _MORALIS_KEY:
        return []
    try:
        resp = get_session().get(
            f"{_MORALIS_SOL_BASE}/token/mainnet/{mint}/pairs",
            headers={"X-API-Key": _MORALIS_KEY},
            timeout=8,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("pairs", []) if isinstance(data, dict) else []
    except Exception as e:
        logger.debug(f"Moralis Solana pairs error for {mint}: {e}")
    return []


# ── Public RPC Fallback ───────────────────────────────────────────────────────
def _public_rpc_largest_accounts(mint: str) -> list[dict]:
    """Fallback: fetch largest token accounts via public Solana RPC."""
    try:
        resp = get_session().post(
            "https://api.mainnet-beta.solana.com",
            json={
                "jsonrpc": "2.0", "id": 1,
                "method": "getTokenLargestAccounts",
                "params": [mint],
            },
            timeout=8,
        )
        if resp.status_code == 200:
            result = resp.json().get("result", {})
            return result.get("value", [])
    except Exception as e:
        logger.debug(f"Public RPC largest accounts error for {mint}: {e}")
    return []


def _public_rpc_supply(mint: str) -> Optional[int]:
    """Fallback: fetch total token supply via public Solana RPC."""
    try:
        resp = get_session().post(
            "https://api.mainnet-beta.solana.com",
            json={
                "jsonrpc": "2.0", "id": 1,
                "method": "getTokenSupply",
                "params": [mint],
            },
            timeout=8,
        )
        if resp.status_code == 200:
            result = resp.json().get("result", {})
            amount = result.get("value", {}).get("amount")
            return int(amount) if amount else None
    except Exception as e:
        logger.debug(f"Public RPC supply error for {mint}: {e}")
    return None


# ── Score Bonus Calculator ────────────────────────────────────────────────────
def _calculate_score_bonus(enrich: SolanaTokenEnrichment) -> float:
    """
    Calculate a gem score bonus (0–15 points) based on enrichment signals.

    Positive signals:
      + Immutable metadata (creator can't rug metadata)     → +3
      + No mint authority (supply is fixed)                  → +3
      + No freeze authority (can't freeze wallets)           → +2
      + Top10 holder % < 20% (well distributed)             → +3
      + Top10 holder % < 30%                                → +1.5
      + Holder count > 500                                   → +2
      + Holder count > 200                                   → +1
      + Smart wallet count >= 3                              → +2
      + Smart wallet count >= 1                              → +1

    Negative signals (deductions):
      - Top10 holder % > 50% (whale concentration)          → -5
      - Top10 holder % > 40%                                → -3
      - Mutable metadata                                     → -2
      - Mint authority still set                             → -3
      - Freeze authority set                                 → -2
    """
    bonus = 0.0

    # Metadata safety
    if enrich.is_mutable_metadata is False:
        bonus += 3.0
    elif enrich.is_mutable_metadata is True:
        bonus -= 2.0

    # Mint authority (supply inflation risk)
    if enrich.is_mint_authority_set is False:
        bonus += 3.0
    elif enrich.is_mint_authority_set is True:
        bonus -= 3.0

    # Freeze authority (wallet freeze risk)
    if enrich.is_freeze_authority is False:
        bonus += 2.0
    elif enrich.is_freeze_authority is True:
        bonus -= 2.0

    # Holder concentration
    if enrich.top10_holder_pct is not None:
        if enrich.top10_holder_pct > 50:
            bonus -= 5.0
        elif enrich.top10_holder_pct > 40:
            bonus -= 3.0
        elif enrich.top10_holder_pct < 20:
            bonus += 3.0
        elif enrich.top10_holder_pct < 30:
            bonus += 1.5

    # Holder count (distribution health)
    if enrich.holder_count is not None:
        if enrich.holder_count > 500:
            bonus += 2.0
        elif enrich.holder_count > 200:
            bonus += 1.0

    # Smart wallet presence
    if enrich.smart_wallet_count >= 3:
        bonus += 2.0
    elif enrich.smart_wallet_count >= 1:
        bonus += 1.0

    return max(-10.0, min(15.0, bonus))


# ── Main Enrichment Function ──────────────────────────────────────────────────
def enrich_solana_token(
    mint: str,
    known_sniper_wallets: Optional[list[str]] = None,
) -> SolanaTokenEnrichment:
    """
    Fetch rich on-chain data for a Solana token mint address.

    Tries Helius DAS first (most data), then Moralis Solana Gateway for price,
    then falls back to public RPC for basic holder concentration.

    Args:
        mint: Solana token mint address
        known_sniper_wallets: Optional list of known high-PnL wallet addresses
                              to check for presence in holder list

    Returns:
        SolanaTokenEnrichment with all available fields populated
    """
    # Check cache
    with _cache_lock:
        if mint in _cache:
            ts, cached = _cache[mint]
            if time.time() - ts < _CACHE_TTL:
                return cached

    enrich = SolanaTokenEnrichment(mint=mint)
    sources_used = []

    # ── Step 1: Helius DAS getAsset ───────────────────────────────────────────
    asset = _helius_get_asset(mint)
    if asset:
        sources_used.append("helius_das")
        token_info = asset.get("token_info", {})
        supply = token_info.get("supply", 0)
        holder_count = token_info.get("associated_token_address_count")
        if holder_count:
            enrich.holder_count = int(holder_count)

        # Authorities
        mint_ext = asset.get("mint_extensions", {})
        authorities = asset.get("authorities", [])
        ownership = asset.get("ownership", {})

        # Check mint authority
        enrich.is_mint_authority_set = bool(
            mint_ext.get("mint_close_authority") or
            any(a.get("scopes", []) == ["mint"] for a in authorities)
        )

        # Check freeze authority
        enrich.is_freeze_authority = bool(
            mint_ext.get("permanent_delegate") or
            any("freeze" in str(a.get("scopes", [])).lower() for a in authorities)
        )

        # Check metadata mutability
        content = asset.get("content", {})
        metadata = content.get("metadata", {})
        enrich.is_mutable_metadata = asset.get("mutable", None)

        # Creator address
        creators = asset.get("creators", [])
        if creators:
            enrich.creator_address = creators[0].get("address")

        logger.debug(f"Helius DAS enriched {mint}: holders={enrich.holder_count}, "
                     f"mutable={enrich.is_mutable_metadata}, mint_auth={enrich.is_mint_authority_set}")

    # ── Step 2: Helius getTokenAccounts (holder concentration) ───────────────
    token_accounts = _helius_get_token_accounts(mint, limit=20)
    if token_accounts:
        sources_used.append("helius_accounts")
        # Calculate top-10 concentration
        amounts = []
        for acct in token_accounts[:10]:
            amt = acct.get("amount", 0)
            if isinstance(amt, str):
                try:
                    amt = int(amt)
                except ValueError:
                    amt = 0
            amounts.append(amt)

        total_supply = _public_rpc_supply(mint)
        if total_supply and total_supply > 0 and amounts:
            top10_sum = sum(amounts)
            enrich.top10_holder_pct = (top10_sum / total_supply) * 100

        # Check for sniper wallets in holders
        if known_sniper_wallets:
            holder_owners = {acct.get("owner", "") for acct in token_accounts}
            matches = sum(1 for w in known_sniper_wallets if w in holder_owners)
            enrich.smart_wallet_count = matches

    # ── Step 3: Moralis Solana Gateway — price ────────────────────────────────
    price_data = _moralis_solana_price(mint)
    if price_data:
        sources_used.append("moralis_solana_price")
        enrich.moralis_price_usd = price_data.get("usdPrice")
        enrich.moralis_price_change_24h = price_data.get("24hrPercentChange")
        enrich.moralis_exchange = price_data.get("exchangeName")
        logger.debug(f"Moralis Solana price for {mint}: ${enrich.moralis_price_usd}")

    # ── Step 4: Public RPC fallback for holder concentration ─────────────────
    if enrich.top10_holder_pct is None:
        largest = _public_rpc_largest_accounts(mint)
        if largest:
            sources_used.append("public_rpc")
            total_supply = _public_rpc_supply(mint)
            if total_supply and total_supply > 0:
                top10_sum = sum(
                    int(acct.get("amount", 0))
                    for acct in largest[:10]
                    if acct.get("amount")
                )
                enrich.top10_holder_pct = (top10_sum / total_supply) * 100

    # ── Step 5: Calculate score bonus ────────────────────────────────────────
    enrich.sniper_score_bonus = _calculate_score_bonus(enrich)
    enrich.data_source = "+".join(sources_used) if sources_used else "none"

    # Cache result
    with _cache_lock:
        _cache[mint] = (time.time(), enrich)

    logger.info(
        f"Solana enrichment for {mint[:8]}…: "
        f"holders={enrich.holder_count}, top10={enrich.top10_holder_pct:.1f}% "
        f"mutable={enrich.is_mutable_metadata}, bonus={enrich.sniper_score_bonus:+.1f} "
        f"source={enrich.data_source}"
        if enrich.top10_holder_pct is not None
        else f"Solana enrichment for {mint[:8]}…: bonus={enrich.sniper_score_bonus:+.1f} source={enrich.data_source}"
    )
    return enrich


# ── Wallet Portfolio (for Sniper Discovery) ───────────────────────────────────
def get_solana_wallet_tokens(wallet: str) -> list[dict]:
    """
    Get all token positions for a Solana wallet using Moralis Solana Gateway.
    Returns list of {mint, symbol, amount_usd, amount_tokens} dicts.
    Used by sniper_discovery to understand what tokens a sniper wallet holds.
    """
    portfolio = _moralis_solana_wallet_portfolio(wallet)
    if not portfolio:
        return []

    tokens = []
    for t in portfolio.get("tokens", []):
        mint = t.get("mint", "")
        symbol = t.get("symbol", "UNKNOWN")
        amount = float(t.get("amount", 0) or 0)
        decimals = int(t.get("decimals", 9) or 9)
        amount_tokens = amount / (10 ** decimals) if decimals else amount

        # Try to get USD value
        usd_value = 0.0
        price_data = _moralis_solana_price(mint) if mint else None
        if price_data and price_data.get("usdPrice"):
            usd_value = amount_tokens * float(price_data["usdPrice"])

        tokens.append({
            "mint": mint,
            "symbol": symbol,
            "amount_tokens": amount_tokens,
            "amount_usd": usd_value,
        })

    return sorted(tokens, key=lambda x: x["amount_usd"], reverse=True)


# ── Wallet Enhanced Transactions (for Sniper Discovery) ──────────────────────
def get_wallet_swap_history(wallet: str, limit: int = 20) -> list[dict]:
    """
    Get enriched swap history for a wallet via Helius Enhanced Transactions.
    Returns parsed swap events with token in/out, amounts, and timestamps.
    Used by sniper_discovery to calculate wallet PnL and trading patterns.
    """
    txs = _helius_get_wallet_transactions(wallet, limit=limit)
    swaps = []
    for tx in txs:
        if tx.get("type") != "SWAP":
            continue
        events = tx.get("events", {})
        swap_event = events.get("swap", {})
        if not swap_event:
            continue

        token_in = swap_event.get("tokenInputs", [{}])[0] if swap_event.get("tokenInputs") else {}
        token_out = swap_event.get("tokenOutputs", [{}])[0] if swap_event.get("tokenOutputs") else {}

        swaps.append({
            "signature": tx.get("signature", ""),
            "timestamp": tx.get("timestamp", 0),
            "token_in_mint": token_in.get("mint", ""),
            "token_in_amount": token_in.get("rawTokenAmount", {}).get("tokenAmount", 0),
            "token_out_mint": token_out.get("mint", ""),
            "token_out_amount": token_out.get("rawTokenAmount", {}).get("tokenAmount", 0),
            "source": tx.get("source", ""),
            "fee": tx.get("fee", 0),
        })

    return swaps


# ── Batch Enrichment ──────────────────────────────────────────────────────────
def batch_enrich_solana_tokens(
    mints: list[str],
    known_sniper_wallets: Optional[list[str]] = None,
    max_concurrent: int = 5,
) -> dict[str, SolanaTokenEnrichment]:
    """
    Enrich multiple Solana tokens in sequence (rate-limit safe).
    Returns dict of mint → SolanaTokenEnrichment.
    """
    import time as _time
    results = {}
    for i, mint in enumerate(mints):
        try:
            results[mint] = enrich_solana_token(mint, known_sniper_wallets)
            if i < len(mints) - 1:
                _time.sleep(0.3)  # 300ms between calls to respect rate limits
        except Exception as e:
            logger.warning(f"Batch enrichment error for {mint}: {e}")
            results[mint] = SolanaTokenEnrichment(mint=mint)
    return results


# ── Availability Check ────────────────────────────────────────────────────────
def get_enrichment_status() -> dict:
    """Return status of available enrichment sources for the health dashboard."""
    return {
        "helius_das": bool(_HELIUS_KEY),
        "helius_enhanced_tx": bool(_HELIUS_KEY),
        "moralis_solana_price": bool(_MORALIS_KEY),
        "moralis_solana_portfolio": bool(_MORALIS_KEY),
        "public_rpc_fallback": True,
        "helius_key_configured": bool(_HELIUS_KEY),
        "moralis_key_configured": bool(_MORALIS_KEY),
    }
