"""
data/providers/oneinch.py — 1inch Aggregation API wrapper.

Provides best-price swap routing across all supported DEXes on each chain.
Used by core/executor.py for trade execution.

API docs: https://portal.1inch.dev/documentation/swap/swagger
Rate limit: 1 req/sec on free tier.
"""

import logging
import time
from typing import Optional

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from config import settings

logger = logging.getLogger(__name__)

_last_request_time = 0.0
_MIN_INTERVAL = 1.1  # 1inch free tier: ~1 req/sec


def _rate_limit():
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)
    _last_request_time = time.time()


def _headers() -> dict:
    return {"Authorization": f"Bearer {settings.ONEINCH_API_KEY}"}


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def get_quote(
    chain_id: int,
    token_in: str,
    token_out: str,
    amount_wei: int,
) -> Optional[dict]:
    """
    Get a swap quote from 1inch.

    Args:
        chain_id: EVM chain ID (1=ETH, 8453=Base, etc.)
        token_in: Source token address
        token_out: Destination token address
        amount_wei: Amount to swap in wei

    Returns:
        Quote dict with dstAmount, gas, protocols used
    """
    if not settings.ONEINCH_API_KEY:
        logger.warning("ONEINCH_API_KEY not configured — skipping quote")
        return None

    _rate_limit()
    url = f"{settings.ONEINCH_API_URL}/{chain_id}/quote"
    params = {
        "src": token_in,
        "dst": token_out,
        "amount": str(amount_wei),
        "includeProtocols": "true",
        "includeGas": "true",
    }
    try:
        resp = requests.get(url, headers=_headers(), params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except requests.HTTPError as e:
        logger.error(f"1inch quote HTTP error {e.response.status_code}: {e.response.text[:200]}")
        return None
    except Exception as e:
        logger.error(f"1inch quote error: {e}")
        return None


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def get_swap_data(
    chain_id: int,
    token_in: str,
    token_out: str,
    amount_wei: int,
    from_address: str,
    slippage_pct: float = 1.0,
) -> Optional[dict]:
    """
    Get swap transaction data from 1inch (ready to sign and broadcast).

    Args:
        chain_id: EVM chain ID
        token_in: Source token address
        token_out: Destination token address
        amount_wei: Amount in wei
        from_address: Wallet address executing the swap
        slippage_pct: Maximum slippage percentage (e.g., 1.0 = 1%)

    Returns:
        Dict with 'tx' key containing to, data, value, gas fields
    """
    if not settings.ONEINCH_API_KEY:
        return None

    _rate_limit()
    url = f"{settings.ONEINCH_API_URL}/{chain_id}/swap"
    params = {
        "src": token_in,
        "dst": token_out,
        "amount": str(amount_wei),
        "from": from_address,
        "slippage": slippage_pct,
        "disableEstimate": "false",
        "allowPartialFill": "false",
    }
    try:
        resp = requests.get(url, headers=_headers(), params=params, timeout=20)
        resp.raise_for_status()
        return resp.json()
    except requests.HTTPError as e:
        logger.error(f"1inch swap HTTP error {e.response.status_code}: {e.response.text[:300]}")
        return None
    except Exception as e:
        logger.error(f"1inch swap data error: {e}")
        return None


def get_token_allowance(
    chain_id: int, token_address: str, wallet_address: str
) -> Optional[int]:
    """Check current token allowance for 1inch router."""
    if not settings.ONEINCH_API_KEY:
        return None
    _rate_limit()
    url = f"{settings.ONEINCH_API_URL}/{chain_id}/approve/allowance"
    params = {"tokenAddress": token_address, "walletAddress": wallet_address}
    try:
        resp = requests.get(url, headers=_headers(), params=params, timeout=10)
        resp.raise_for_status()
        return int(resp.json().get("allowance", 0))
    except Exception as e:
        logger.error(f"1inch allowance check error: {e}")
        return None


def get_approve_calldata(chain_id: int, token_address: str) -> Optional[dict]:
    """Get calldata for approving 1inch router to spend a token."""
    if not settings.ONEINCH_API_KEY:
        return None
    _rate_limit()
    url = f"{settings.ONEINCH_API_URL}/{chain_id}/approve/transaction"
    params = {"tokenAddress": token_address}
    try:
        resp = requests.get(url, headers=_headers(), params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"1inch approve calldata error: {e}")
        return None
