"""
cosmos/osmosis_executor.py — Osmosis DEX execution engine.

Handles swaps, LP operations, and pool queries on Osmosis.
Uses Osmosis REST API for queries and builds TX messages for execution.
"""

import logging
import time
from dataclasses import dataclass
from typing import Optional

import requests

from cosmos.cosmos_config import (
    COSMOS_CHAINS,
    COSMOS_ADDRESSES,
    OSMOSIS_IBC_DENOMS,
    COSMOS_MODE,
)
from cosmos.cosmos_wallet import CosmosWallet, CosmosTxResult

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

OSMOSIS_REST = COSMOS_CHAINS["osmosis"].rest_url
OSMOSIS_NUMIA_API = "https://api-osmosis.imperator.co"


@dataclass
class SwapRoute:
    """A single-hop or multi-hop swap route on Osmosis."""
    pool_id: int
    token_in_denom: str
    token_out_denom: str


@dataclass
class OsmosisSwapResult:
    """Result of an Osmosis swap."""
    success: bool
    amount_in: float = 0.0
    amount_out: float = 0.0
    token_in_symbol: str = ""
    token_out_symbol: str = ""
    tx_hash: Optional[str] = None
    error: Optional[str] = None
    is_paper: bool = True


class OsmosisExecutor:
    """
    Execute swaps and LP operations on Osmosis DEX.
    """
    
    def __init__(self):
        self.wallet = CosmosWallet("osmosis")
        self.is_paper = COSMOS_MODE != "live"
        self._session = requests.Session()
    
    # ── Pool & Price Queries ─────────────────────────────────────────────────
    
    def get_pool_info(self, pool_id: int) -> dict:
        """Fetch pool details from Osmosis."""
        try:
            url = f"{OSMOSIS_REST}/osmosis/gamm/v1beta1/pools/{pool_id}"
            resp = self._session.get(url, timeout=15)
            resp.raise_for_status()
            return resp.json().get("pool", {})
        except Exception as e:
            logger.error(f"Failed to fetch pool {pool_id}: {e}")
            return {}
    
    def get_pool_spot_price(self, pool_id: int, base_denom: str, quote_denom: str) -> float:
        """Get spot price from a pool."""
        try:
            url = (
                f"{OSMOSIS_REST}/osmosis/gamm/v2/pools/{pool_id}/prices"
                f"?base_asset_denom={base_denom}&quote_asset_denom={quote_denom}"
            )
            resp = self._session.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            return float(data.get("spot_price", 0))
        except Exception as e:
            logger.debug(f"Spot price query failed for pool {pool_id}: {e}")
            return 0.0
    
    def get_all_pool_prices(self) -> dict:
        """Fetch token prices from Osmosis aggregator API."""
        try:
            url = f"{OSMOSIS_NUMIA_API}/tokens/v2/all"
            resp = self._session.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            
            prices = {}
            for token in data:
                symbol = token.get("symbol", "")
                price = float(token.get("price", 0))
                denom = token.get("denom", "")
                if symbol and price > 0:
                    prices[symbol] = {"price": price, "denom": denom}
            
            return prices
        except Exception as e:
            logger.error(f"Failed to fetch Osmosis token prices: {e}")
            return {}
    
    def estimate_swap_out(
        self,
        pool_id: int,
        token_in_denom: str,
        token_in_amount: int,
        token_out_denom: str,
    ) -> int:
        """Estimate output amount for a swap."""
        try:
            url = (
                f"{OSMOSIS_REST}/osmosis/gamm/v1beta1/{pool_id}"
                f"/estimate/swap_exact_amount_in"
            )
            params = {
                "token_in": f"{token_in_amount}{token_in_denom}",
                "routes": [
                    {
                        "pool_id": str(pool_id),
                        "token_out_denom": token_out_denom,
                    }
                ],
            }
            resp = self._session.get(url, params={"token_in": f"{token_in_amount}{token_in_denom}"}, timeout=15)
            
            if resp.status_code == 200:
                return int(resp.json().get("token_out_amount", 0))
            
            return 0
        except Exception as e:
            logger.debug(f"Swap estimate failed: {e}")
            return 0
    
    # ── Swap Execution ───────────────────────────────────────────────────────
    
    def build_swap_msg(
        self,
        pool_id: int,
        token_in_denom: str,
        token_in_amount: int,
        token_out_denom: str,
        token_out_min_amount: int = 1,
    ) -> dict:
        """Build a MsgSwapExactAmountIn for Osmosis."""
        return {
            "@type": "/osmosis.gamm.v1beta1.MsgSwapExactAmountIn",
            "sender": self.wallet.address,
            "routes": [
                {
                    "pool_id": str(pool_id),
                    "token_out_denom": token_out_denom,
                }
            ],
            "token_in": {
                "denom": token_in_denom,
                "amount": str(token_in_amount),
            },
            "token_out_min_amount": str(token_out_min_amount),
        }
    
    def execute_swap(
        self,
        pool_id: int,
        token_in_denom: str,
        token_in_amount: int,
        token_out_denom: str,
        slippage_pct: float = 1.0,
    ) -> OsmosisSwapResult:
        """
        Execute a swap on Osmosis.
        
        In paper mode: simulates the swap and logs results.
        In live mode: signs and broadcasts the TX.
        """
        # Resolve symbols for logging
        token_in_symbol = self._denom_to_symbol(token_in_denom)
        token_out_symbol = self._denom_to_symbol(token_out_denom)
        
        human_in = token_in_amount / 1e6
        
        # Estimate output
        estimated_out = self.estimate_swap_out(
            pool_id, token_in_denom, token_in_amount, token_out_denom
        )
        human_out = estimated_out / 1e6
        
        # Calculate min output with slippage
        min_out = int(estimated_out * (1 - slippage_pct / 100))
        
        logger.info(
            f"Osmosis swap: {human_in:.4f} {token_in_symbol} → "
            f"~{human_out:.4f} {token_out_symbol} "
            f"(pool {pool_id}, slippage {slippage_pct}%)"
        )
        
        if self.is_paper:
            logger.info(f"📄 PAPER MODE — swap simulated, not executed")
            return OsmosisSwapResult(
                success=True,
                amount_in=human_in,
                amount_out=human_out,
                token_in_symbol=token_in_symbol,
                token_out_symbol=token_out_symbol,
                tx_hash="paper_" + str(int(time.time())),
                is_paper=True,
            )
        
        # Live execution
        msg = self.build_swap_msg(
            pool_id=pool_id,
            token_in_denom=token_in_denom,
            token_in_amount=token_in_amount,
            token_out_denom=token_out_denom,
            token_out_min_amount=max(1, min_out),
        )
        
        # For live TX signing, we need cosmospy or similar
        # This is a placeholder for the signing + broadcast flow
        logger.warning("Live Osmosis swap requires cosmospy signing — not yet wired")
        return OsmosisSwapResult(
            success=False,
            error="Live signing not yet implemented — use cosmospy",
            is_paper=False,
        )
    
    # ── LP Operations ────────────────────────────────────────────────────────
    
    def build_join_pool_msg(
        self,
        pool_id: int,
        token_in_maxs: list,
        share_out_amount: str = "0",
    ) -> dict:
        """Build a MsgJoinPool for Osmosis LP."""
        return {
            "@type": "/osmosis.gamm.v1beta1.MsgJoinPool",
            "sender": self.wallet.address,
            "pool_id": str(pool_id),
            "token_in_maxs": token_in_maxs,
            "share_out_amount": share_out_amount,
        }
    
    def build_exit_pool_msg(
        self,
        pool_id: int,
        share_in_amount: str,
        token_out_mins: list,
    ) -> dict:
        """Build a MsgExitPool for removing LP."""
        return {
            "@type": "/osmosis.gamm.v1beta1.MsgExitPool",
            "sender": self.wallet.address,
            "pool_id": str(pool_id),
            "share_in_amount": share_in_amount,
            "token_out_mins": token_out_mins,
        }
    
    def get_user_pool_shares(self, pool_id: int) -> float:
        """Get user's share of a specific pool."""
        try:
            balances = self.wallet.get_balance()
            share_denom = f"gamm/pool/{pool_id}"
            share_info = balances.get(share_denom, {})
            return share_info.get("amount", 0.0)
        except Exception:
            return 0.0
    
    # ── Helpers ──────────────────────────────────────────────────────────────
    
    def _denom_to_symbol(self, denom: str) -> str:
        """Convert an IBC or native denom to human-readable symbol."""
        native_map = {"uosmo": "OSMO", "uatom": "ATOM", "utia": "TIA"}
        if denom in native_map:
            return native_map[denom]
        
        ibc_info = OSMOSIS_IBC_DENOMS.get(denom)
        if ibc_info:
            return ibc_info["symbol"]
        
        return denom[:12] + "..."
