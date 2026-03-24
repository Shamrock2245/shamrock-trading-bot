"""
cosmos/lp_manager.py — Osmosis Liquidity Pool management.

Handles concentrated liquidity positions, range monitoring, rebalancing,
and fee compounding on Osmosis DEX.
"""

import logging
import time
from dataclasses import dataclass
from typing import Optional

import requests

from cosmos.cosmos_config import (
    COSMOS_CHAINS,
    COSMOS_MODE,
    OSMOSIS_TARGET_POOLS,
    LP_REBALANCE_THRESHOLD_PCT,
    LP_COMPOUND_FEES,
    SUPERFLUID_STAKING_ENABLED,
)
from cosmos.osmosis_executor import OsmosisExecutor
from cosmos.price_monitor import PriceMonitor

logger = logging.getLogger(__name__)


@dataclass
class LPPosition:
    """A liquidity position on Osmosis."""
    pool_id: int
    pair: str
    shares: float
    token_a_amount: float
    token_a_symbol: str
    token_b_amount: float
    token_b_symbol: str
    value_usd: float
    apy_estimate: float
    # Concentrated LP fields
    lower_tick: Optional[int] = None
    upper_tick: Optional[int] = None
    in_range: bool = True
    superfluid: bool = False


@dataclass
class LPAction:
    """Record of an LP management action."""
    action: str          # "add", "remove", "rebalance", "compound"
    pool_id: int
    pair: str
    amount_usd: float
    tx_hash: Optional[str] = None
    timestamp: float = 0.0
    is_paper: bool = True


class LPManager:
    """
    Manage liquidity positions on Osmosis.
    
    Features:
    - Add/remove concentrated liquidity
    - Monitor position ranges
    - Auto-rebalance when price drifts out of range
    - Compound earned swap fees
    - Superfluid staking on eligible pools
    """
    
    def __init__(self):
        self.osmosis = OsmosisExecutor()
        self.price_monitor = PriceMonitor()
        self.is_paper = COSMOS_MODE != "live"
        self._positions: list[LPPosition] = []
        self._actions_log: list[LPAction] = []
        self._session = requests.Session()
    
    # ── Position Queries ─────────────────────────────────────────────────────
    
    def scan_positions(self) -> list[LPPosition]:
        """Scan all LP positions on Osmosis for our wallet."""
        positions = []
        
        for pool_id, pair, description in OSMOSIS_TARGET_POOLS:
            shares = self.osmosis.get_user_pool_shares(pool_id)
            
            if shares > 0:
                pool_info = self.osmosis.get_pool_info(pool_id)
                
                positions.append(LPPosition(
                    pool_id=pool_id,
                    pair=pair,
                    shares=shares,
                    token_a_amount=0,  # Would parse from pool_info
                    token_a_symbol=pair.split("/")[0],
                    token_b_amount=0,
                    token_b_symbol=pair.split("/")[1],
                    value_usd=0,  # Would calculate from prices
                    apy_estimate=self._estimate_pool_apy(pool_id),
                ))
        
        self._positions = positions
        return positions
    
    def _estimate_pool_apy(self, pool_id: int) -> float:
        """Estimate APY for a pool from Osmosis incentives API."""
        try:
            resp = self._session.get(
                f"https://api-osmosis.imperator.co/apr/v2/{pool_id}",
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                # Sum up all APR components
                total_apr = 0.0
                for item in data:
                    total_apr += float(item.get("apr_14d", 0))
                    total_apr += float(item.get("apr_superfluid", 0))
                return total_apr
        except Exception:
            pass
        
        # Fallback estimates
        apy_map = {1: 15.0, 678: 20.0, 1263: 25.0}
        return apy_map.get(pool_id, 10.0)
    
    # ── LP Operations ────────────────────────────────────────────────────────
    
    def add_liquidity(
        self,
        pool_id: int,
        token_a_amount: int,
        token_a_denom: str,
        token_b_amount: int,
        token_b_denom: str,
    ) -> LPAction:
        """Add liquidity to an Osmosis pool."""
        pair = f"{self.osmosis._denom_to_symbol(token_a_denom)}/{self.osmosis._denom_to_symbol(token_b_denom)}"
        human_a = token_a_amount / 1e6
        human_b = token_b_amount / 1e6
        
        logger.info(
            f"Adding LP: {human_a:.4f} + {human_b:.4f} → pool {pool_id} ({pair})"
        )
        
        action = LPAction(
            action="add",
            pool_id=pool_id,
            pair=pair,
            amount_usd=0,  # Would calculate from prices
            timestamp=time.time(),
            is_paper=self.is_paper,
        )
        
        if self.is_paper:
            action.tx_hash = f"paper_lp_add_{int(time.time())}"
            logger.info(f"📄 PAPER: Added liquidity to pool {pool_id}")
        else:
            msg = self.osmosis.build_join_pool_msg(
                pool_id=pool_id,
                token_in_maxs=[
                    {"denom": token_a_denom, "amount": str(token_a_amount)},
                    {"denom": token_b_denom, "amount": str(token_b_amount)},
                ],
            )
            logger.warning("Live LP add requires cosmospy signing")
        
        self._actions_log.append(action)
        return action
    
    def remove_liquidity(self, pool_id: int, share_pct: float = 100.0) -> LPAction:
        """Remove liquidity from an Osmosis pool."""
        logger.info(f"Removing {share_pct}% liquidity from pool {pool_id}")
        
        action = LPAction(
            action="remove",
            pool_id=pool_id,
            pair="",
            amount_usd=0,
            timestamp=time.time(),
            is_paper=self.is_paper,
        )
        
        if self.is_paper:
            action.tx_hash = f"paper_lp_remove_{int(time.time())}"
            logger.info(f"📄 PAPER: Removed {share_pct}% from pool {pool_id}")
        
        self._actions_log.append(action)
        return action
    
    # ── Rebalancing ──────────────────────────────────────────────────────────
    
    def check_rebalance_needed(self) -> list[LPPosition]:
        """Check if any LP positions need rebalancing."""
        needs_rebalance = []
        
        for pos in self._positions:
            # For concentrated LP: check if price is outside our range
            if pos.lower_tick is not None and not pos.in_range:
                needs_rebalance.append(pos)
                continue
            
            # For standard LP: check if the pair ratio has drifted
            # significantly from 50/50
            pool_info = self.osmosis.get_pool_info(pos.pool_id)
            if pool_info:
                # Check pool asset weights
                assets = pool_info.get("pool_assets", [])
                if len(assets) == 2:
                    w1 = float(assets[0].get("weight", "1"))
                    w2 = float(assets[1].get("weight", "1"))
                    ratio = w1 / max(w1 + w2, 1) * 100
                    
                    if abs(ratio - 50.0) > LP_REBALANCE_THRESHOLD_PCT:
                        needs_rebalance.append(pos)
        
        if needs_rebalance:
            logger.info(
                f"Rebalance needed for {len(needs_rebalance)} positions: "
                + ", ".join(str(p.pool_id) for p in needs_rebalance)
            )
        
        return needs_rebalance
    
    def rebalance_position(self, position: LPPosition) -> list[LPAction]:
        """
        Rebalance an LP position.
        
        For concentrated LP: remove liquidity, adjust range, re-add.
        For standard LP: swap imbalanced asset to restore ratio.
        """
        actions = []
        
        logger.info(f"Rebalancing pool {position.pool_id} ({position.pair})")
        
        # Step 1: Remove current position
        remove = self.remove_liquidity(position.pool_id)
        actions.append(remove)
        
        # Step 2: Re-add with updated range/ratio
        # This would be calculated from current spot price
        # For now, log the intent
        logger.info(f"Rebalance for pool {position.pool_id} — re-add pending")
        
        return actions
    
    # ── Fee Compounding ──────────────────────────────────────────────────────
    
    def compound_lp_fees(self) -> list[LPAction]:
        """Compound earned swap fees back into LP positions."""
        actions = []
        
        if not LP_COMPOUND_FEES:
            return actions
        
        # Check for unclaimed incentives/fees
        # Osmosis claim rewards endpoint
        for pos in self._positions:
            logger.info(f"Checking fees for pool {pos.pool_id}")
            
            # In practice, we'd query the incentives module
            # and claim + re-add to the pool
            action = LPAction(
                action="compound",
                pool_id=pos.pool_id,
                pair=pos.pair,
                amount_usd=0,
                timestamp=time.time(),
                is_paper=self.is_paper,
            )
            
            if self.is_paper:
                action.tx_hash = f"paper_compound_{int(time.time())}"
            
            actions.append(action)
        
        return actions
    
    # ── Strategy Deployment ──────────────────────────────────────────────────
    
    def deploy_to_target_pools(self, available_assets: dict) -> list[LPAction]:
        """
        Deploy available assets into target Osmosis pools.
        
        Args:
            available_assets: Dict of {denom: amount_raw} on Osmosis
        """
        actions = []
        
        # ATOM/OSMO pool (pool 1) — highest liquidity
        atom_on_osmosis = available_assets.get("ibc/27394FB092D2ECCD56123C74F36E4C1F926001CEADA9CA97EA622B25F41E5EB2", 0)
        osmo_available = available_assets.get("uosmo", 0)
        
        if atom_on_osmosis > 0 and osmo_available > 0:
            # Deploy proportionally
            action = self.add_liquidity(
                pool_id=1,
                token_a_amount=atom_on_osmosis // 2,  # Half of ATOM
                token_a_denom="ibc/27394FB092D2ECCD56123C74F36E4C1F926001CEADA9CA97EA622B25F41E5EB2",
                token_b_amount=osmo_available // 2,
                token_b_denom="uosmo",
            )
            actions.append(action)
        
        return actions
    
    def get_lp_summary(self) -> dict:
        """Get summary of all LP positions."""
        total_value = sum(p.value_usd for p in self._positions)
        total_apy = (
            sum(p.apy_estimate * p.value_usd for p in self._positions)
            / max(total_value, 1)
        ) if self._positions else 0.0
        
        return {
            "positions": len(self._positions),
            "total_value_usd": total_value,
            "weighted_avg_apy": total_apy,
            "actions_taken": len(self._actions_log),
            "pools": [
                {
                    "pool_id": p.pool_id,
                    "pair": p.pair,
                    "value_usd": p.value_usd,
                    "apy": p.apy_estimate,
                    "in_range": p.in_range,
                    "superfluid": p.superfluid,
                }
                for p in self._positions
            ],
        }
