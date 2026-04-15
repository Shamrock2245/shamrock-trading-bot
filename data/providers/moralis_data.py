import os
import time
from data.http_session import get_session
from loguru import logger

MORALIS_API_KEY = os.environ.get("MORALIS_API_KEY", "")
MORALIS_API_BASE = "https://deep-index.moralis.io/api/v2.2"
SOLANA_API_BASE = "https://solana-gateway.moralis.io"

def _get_headers():
    return {
        "accept": "application/json",
        "X-API-Key": MORALIS_API_KEY
    }

def _chain_to_hex(chain: str) -> str:
    """Map internal chain names to Moralis hex."""
    cmap = {
        "ethereum": "0x1",
        "polygon": "0x89",
        "bsc": "0x38",
        "arbitrum": "0xa4b1",
        "optimism": "0xa",
        "base": "0x2105",
        "avalanche": "0xa86a"
    }
    return cmap.get(chain.lower(), "0x1")

def get_token_score(token_address: str, chain: str) -> dict:
    """
    Get token security score.
    https://docs.moralis.com/data-api/evm/reference/get-token-score
    """
    if not MORALIS_API_KEY:
        return {}
    
    try:
        chain_lower = chain.lower()
        if chain_lower == "solana":
            url = f"{SOLANA_API_BASE}/token/mainnet/{token_address}/score"
        else:
            hex_chain = _chain_to_hex(chain_lower)
            url = f"{MORALIS_API_BASE}/erc20/{token_address}/score?chain={hex_chain}"

        res = get_session().get(url, headers=_get_headers(), timeout=4)
        if res.status_code == 200:
            return res.json()
        elif res.status_code == 404:
            # Not found / no score yet
            return {}
        else:
            logger.debug(f"Moralis score error for {token_address}: {res.status_code} - {res.text}")
            return {}
    except Exception as e:
        logger.debug(f"Exception fetching Moralis score for {token_address}: {e}")
        return {}

def get_token_analytics(token_address: str, chain: str) -> dict:
    """
    Get deep token analytics (net buyers, volume USD, experienced buyers).
    https://docs.moralis.com/data-api/evm/reference/get-token-analytics
    """
    if not MORALIS_API_KEY:
        return {}

    try:
        chain_lower = chain.lower()
        if chain_lower == "solana":
            url = f"{SOLANA_API_BASE}/token/mainnet/{token_address}/analytics"
        else:
            hex_chain = _chain_to_hex(chain_lower)
            url = f"{MORALIS_API_BASE}/erc20/{token_address}/analytics?chain={hex_chain}"

        res = get_session().get(url, headers=_get_headers(), timeout=5)
        if res.status_code == 200:
            return res.json()
        elif res.status_code == 404:
            return {}
        else:
            logger.debug(f"Moralis analytics error for {token_address}: {res.status_code} - {res.text}")
            return {}
    except Exception as e:
        logger.debug(f"Exception fetching Moralis analytics for {token_address}: {e}")
        return {}

def get_token_metadata(token_addresses: list, chain: str) -> list:
    """
    Get token metadata (including possible_spam flags).
    https://docs.moralis.com/data-api/evm/reference/get-token-metadata
    """
    if not MORALIS_API_KEY or not token_addresses:
        return []

    try:
        chain_lower = chain.lower()
        if chain_lower == "solana":
            url = f"{SOLANA_API_BASE}/token/mainnet/{token_addresses[0]}/metadata"
            res = get_session().get(url, headers=_get_headers(), timeout=4)
            if res.status_code == 200:
                data = res.json()
                if isinstance(data, dict):
                    return [data]
            return []
        else:
            hex_chain = _chain_to_hex(chain_lower)
            url = f"{MORALIS_API_BASE}/erc20/metadata?chain={hex_chain}"
            for addr in token_addresses:
                url += f"&addresses={addr}"
            
            res = get_session().get(url, headers=_get_headers(), timeout=4)
            if res.status_code == 200:
                return res.json()
            return []
    except Exception as e:
        logger.debug(f"Exception fetching Moralis metadata: {e}")
        return []
