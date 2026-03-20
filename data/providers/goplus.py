"""
data/providers/goplus.py — GoPlus Security API wrapper.

GoPlus provides on-chain token security analysis:
  - Honeypot detection
  - Buy/sell tax analysis
  - Contract ownership analysis
  - Holder distribution
  - Proxy contract detection
  - Mint function detection

API: https://gopluslabs.io/
Rate limit: ~20 req/min on free tier.
"""

import logging
from typing import Optional

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

GOPLUS_BASE = "https://api.gopluslabs.io/api/v1"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=15))
def get_token_security(token_address: str, chain_id: str) -> Optional[dict]:
    """
    GET /token_security/{chain_id}?contract_addresses={address}

    Returns comprehensive security analysis for a token.
    chain_id: GoPlus chain ID string (e.g., "1" for Ethereum, "8453" for Base)
    """
    try:
        url = f"{GOPLUS_BASE}/token_security/{chain_id}"
        params = {"contract_addresses": token_address.lower()}
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") != 1:
            logger.warning(f"GoPlus non-success code: {data.get('message')}")
            return None

        result = data.get("result", {})
        return result.get(token_address.lower())

    except Exception as e:
        logger.error(f"GoPlus security check error for {token_address}: {e}")
        return None


def parse_security_result(gp: dict) -> dict:
    """
    Parse a GoPlus result dict into normalized safety signals.
    Returns a flat dict of all key risk indicators.
    """
    if not gp:
        return {"error": "No GoPlus data"}

    return {
        "is_honeypot": gp.get("is_honeypot", "0") == "1",
        "buy_tax": float(gp.get("buy_tax", 0) or 0),
        "sell_tax": float(gp.get("sell_tax", 0) or 0),
        "is_open_source": gp.get("is_open_source", "1") == "1",
        "is_proxy": gp.get("is_proxy", "0") == "1",
        "is_mintable": gp.get("is_mintable", "0") == "1",
        "owner_address": gp.get("owner_address", ""),
        "owner_change_balance": gp.get("owner_change_balance", "0") == "1",
        "can_take_back_ownership": gp.get("can_take_back_ownership", "0") == "1",
        "hidden_owner": gp.get("hidden_owner", "0") == "1",
        "selfdestruct": gp.get("selfdestruct", "0") == "1",
        "external_call": gp.get("external_call", "0") == "1",
        "cannot_sell_all": gp.get("cannot_sell_all", "0") == "1",
        "cannot_buy": gp.get("cannot_buy", "0") == "1",
        "trading_cooldown": gp.get("trading_cooldown", "0") == "1",
        "transfer_pausable": gp.get("transfer_pausable", "0") == "1",
        "blacklist_function": gp.get("blacklist_function", "0") == "1",
        "whitelist_function": gp.get("whitelist_function", "0") == "1",
        "anti_whale_modifiable": gp.get("anti_whale_modifiable", "0") == "1",
        "holder_count": int(gp.get("holder_count", 0) or 0),
        "total_supply": gp.get("total_supply", "0"),
        "lp_holder_count": int(gp.get("lp_holder_count", 0) or 0),
        "lp_total_supply": gp.get("lp_total_supply", "0"),
        "is_in_dex": gp.get("is_in_dex", "0") == "1",
        "dex": gp.get("dex", []),
        "holders": gp.get("holders", []),
        "lp_holders": gp.get("lp_holders", []),
    }


def get_top_holder_concentration(gp_parsed: dict) -> float:
    """
    Calculate the % of supply held by top 10 wallets.
    Returns 0.0–1.0 (e.g., 0.65 = 65% concentrated in top 10).
    """
    holders = gp_parsed.get("holders", [])
    if not holders:
        return 0.0
    top_10 = holders[:10]
    total_pct = sum(float(h.get("percent", 0) or 0) for h in top_10)
    return total_pct
