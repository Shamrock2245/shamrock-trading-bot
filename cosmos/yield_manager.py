"""
cosmos/yield_manager.py — Automated staking & liquid staking engine.

Handles:
- Liquid staking ATOM via Stride → stATOM (18% APY)
- Native TIA staking on Celestia (14% APY)
- OSMO staking / superfluid staking on Osmosis (10%+ APY)
- Auto-compounding rewards across all chains
"""

import logging
import time
from dataclasses import dataclass
from typing import Optional

import requests

from cosmos.cosmos_config import (
    COSMOS_CHAINS,
    COSMOS_ADDRESSES,
    COSMOS_MODE,
    YIELD_AUTO_COMPOUND_INTERVAL_HOURS,
    STRIDE_LIQUID_STAKE_ENABLED,
    NATIVE_STAKE_TIA,
    NATIVE_STAKE_OSMO,
)
from cosmos.cosmos_wallet import CosmosWallet, CosmosTxResult

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Top validators (by uptime + commission — hand-picked for reliability)
# ─────────────────────────────────────────────────────────────────────────────

TOP_VALIDATORS = {
    "cosmoshub": [
        # Cosmos Hub — low commission, high uptime validators
        "cosmosvaloper1clpqr4nrk4khgkxj78fcwwh6dl3ual4tzqj2cy",  # Cosmostation (1%)
        "cosmosvaloper1sjllsnramtg3ewt0qpq9qyq34zp5etfs5nf5v9",  # Stakecito (5%)
    ],
    "celestia": [
        "celestiavaloper1z59gvs5mfxg3d7xrdp7x2kmpqk58kxe0wjg6x",  # Stakecito
        "celestiavaloper1qxx28qfg7uq6qynq0qn3szfqf2ypxu0n70pld",  # Polkachu
    ],
    "osmosis": [
        "osmovaloper1clpqr4nrk4khgkxj78fcwwh6dl3ual4t3jells",  # Cosmostation
        "osmovaloper1cyw4vw20el8e7ez8080md0r8psg25n0cq98a9nm",  # Stakecito
    ],
}


@dataclass
class StakingPosition:
    """A staking position on any Cosmos chain."""
    chain: str
    validator: str
    amount: float
    denom: str
    rewards_pending: float
    apy_estimate: float
    is_liquid: bool = False  # True if stATOM/stTIA via Stride


@dataclass
class YieldAction:
    """Record of a yield management action taken."""
    action: str         # "stake", "unstake", "claim", "compound", "liquid_stake"
    chain: str
    amount: float
    denom: str
    validator: Optional[str] = None
    tx_hash: Optional[str] = None
    timestamp: float = 0.0
    is_paper: bool = True


class YieldManager:
    """
    Automated yield management across Cosmos chains.
    
    Maximizes staking returns by:
    1. Liquid staking ATOM via Stride (keeps liquidity for LP/arb)
    2. Native staking TIA on Celestia
    3. Staking/superfluid staking OSMO on Osmosis
    4. Auto-compounding all rewards on a schedule
    """
    
    def __init__(self):
        self.is_paper = COSMOS_MODE != "live"
        self._last_compound = 0.0
        self._actions_log: list[YieldAction] = []
        self._wallets = {}
        
        for chain_name in COSMOS_CHAINS:
            if chain_name in COSMOS_ADDRESSES:
                self._wallets[chain_name] = CosmosWallet(chain_name)
    
    # ── Position Scanning ────────────────────────────────────────────────────
    
    def get_all_staking_positions(self) -> list[StakingPosition]:
        """Scan all chains for current staking positions."""
        positions = []
        
        apy_estimates = {
            "cosmoshub": 18.0,  # via Stride liquid staking
            "celestia": 14.0,   # native staking
            "osmosis": 10.0,    # native/superfluid staking
        }
        
        for chain_name, wallet in self._wallets.items():
            delegations = wallet.get_delegations()
            rewards = wallet.get_rewards()
            
            total_rewards = sum(rewards.values()) if rewards else 0.0
            
            for delegation in delegations:
                positions.append(StakingPosition(
                    chain=chain_name,
                    validator=delegation["validator"],
                    amount=delegation["amount"],
                    denom=delegation["denom"],
                    rewards_pending=total_rewards / max(len(delegations), 1),
                    apy_estimate=apy_estimates.get(chain_name, 5.0),
                ))
        
        return positions
    
    def get_unstaked_balances(self) -> dict:
        """Get all unstaked (liquid) balances across chains."""
        unstaked = {}
        
        for chain_name, wallet in self._wallets.items():
            balance = wallet.get_native_balance()
            if balance > 0.01:
                unstaked[chain_name] = {
                    "amount": balance,
                    "denom": COSMOS_CHAINS[chain_name].display_denom,
                }
        
        return unstaked
    
    # ── Staking Operations ───────────────────────────────────────────────────
    
    def stake_atom_via_stride(self, amount: float) -> YieldAction:
        """
        Liquid stake ATOM via Stride protocol.
        
        1. IBC transfer ATOM to Stride
        2. Liquid stake → receive stATOM
        3. IBC transfer stATOM back to Osmosis for LP use
        """
        logger.info(f"Liquid staking {amount:.4f} ATOM via Stride")
        
        # Build Stride liquid staking message
        stride_msg = {
            "@type": "/stride.stakeibc.MsgLiquidStake",
            "creator": COSMOS_ADDRESSES.get("stride", ""),
            "amount": str(int(amount * 1e6)),
            "host_denom": "uatom",
        }
        
        action = YieldAction(
            action="liquid_stake",
            chain="stride",
            amount=amount,
            denom="ATOM→stATOM",
            timestamp=time.time(),
            is_paper=self.is_paper,
        )
        
        if self.is_paper:
            action.tx_hash = f"paper_lstake_{int(time.time())}"
            logger.info(f"📄 PAPER: Liquid staked {amount:.4f} ATOM → stATOM via Stride")
        else:
            logger.warning("Live Stride liquid staking requires full signing pipeline")
        
        self._actions_log.append(action)
        return action
    
    def stake_native(self, chain_name: str, amount: float) -> YieldAction:
        """
        Native stake tokens on a chain.
        
        Distributes across top validators for decentralization.
        """
        validators = TOP_VALIDATORS.get(chain_name, [])
        denom = COSMOS_CHAINS[chain_name].display_denom
        
        logger.info(f"Native staking {amount:.4f} {denom} on {chain_name}")
        
        if not validators:
            logger.error(f"No validators configured for {chain_name}")
            return YieldAction(
                action="stake",
                chain=chain_name,
                amount=0,
                denom=denom,
                timestamp=time.time(),
            )
        
        # Split across validators
        per_validator = amount / len(validators)
        raw_amount = int(per_validator * 1e6)
        
        action = YieldAction(
            action="stake",
            chain=chain_name,
            amount=amount,
            denom=denom,
            timestamp=time.time(),
            is_paper=self.is_paper,
        )
        
        if self.is_paper:
            for v in validators:
                short_v = v[:20] + "..."
                logger.info(
                    f"📄 PAPER: Staked {per_validator:.4f} {denom} "
                    f"→ {short_v} on {chain_name}"
                )
            action.tx_hash = f"paper_stake_{int(time.time())}"
        else:
            # Build and broadcast delegate messages
            wallet = self._wallets.get(chain_name)
            if wallet:
                for v in validators:
                    msg = wallet.build_delegate_msg(v, raw_amount)
                    logger.info(f"Built delegate msg for {v[:20]}...")
                    # Signing + broadcast would happen here
            
            logger.warning("Live staking requires cosmospy signing")
        
        self._actions_log.append(action)
        return action
    
    # ── Auto-compound ────────────────────────────────────────────────────────
    
    def claim_and_compound(self) -> list[YieldAction]:
        """
        Claim all pending staking rewards and re-stake them.
        
        Called on a schedule (default: every 24 hours).
        """
        actions = []
        
        for chain_name, wallet in self._wallets.items():
            delegations = wallet.get_delegations()
            rewards = wallet.get_rewards()
            
            if not delegations or not rewards:
                continue
            
            total_rewards = sum(rewards.values())
            if total_rewards < 0.001:
                continue
            
            denom = COSMOS_CHAINS[chain_name].display_denom
            
            logger.info(
                f"Claiming {total_rewards:.6f} {denom} "
                f"rewards on {chain_name}"
            )
            
            # Claim rewards from each validator
            claim_action = YieldAction(
                action="claim",
                chain=chain_name,
                amount=total_rewards,
                denom=denom,
                timestamp=time.time(),
                is_paper=self.is_paper,
            )
            
            if self.is_paper:
                claim_action.tx_hash = f"paper_claim_{int(time.time())}"
                logger.info(
                    f"📄 PAPER: Claimed {total_rewards:.6f} {denom} on {chain_name}"
                )
            else:
                for d in delegations:
                    msg = wallet.build_claim_rewards_msg(d["validator"])
                    # Signing + broadcast here
            
            actions.append(claim_action)
            
            # Re-stake the claimed rewards
            if total_rewards > 0.01:
                compound_action = self.stake_native(chain_name, total_rewards)
                compound_action.action = "compound"
                actions.append(compound_action)
        
        self._last_compound = time.time()
        return actions
    
    def should_compound(self) -> bool:
        """Check if it's time to auto-compound."""
        interval = YIELD_AUTO_COMPOUND_INTERVAL_HOURS * 3600
        return (time.time() - self._last_compound) >= interval
    
    # ── Full deployment ──────────────────────────────────────────────────────
    
    def deploy_all_idle_assets(self) -> list[YieldAction]:
        """
        Deploy ALL unstaked assets into yield-generating positions.
        
        This is the aggressive strategy — put everything to work:
        1. ATOM → Stride liquid staking (stATOM)
        2. TIA → Native staking on Celestia
        3. OSMO → Native staking on Osmosis
        """
        actions = []
        unstaked = self.get_unstaked_balances()
        
        # ATOM → Stride liquid staking
        atom_info = unstaked.get("cosmoshub")
        if atom_info and atom_info["amount"] > 0.1:
            amount = atom_info["amount"] - 0.05  # Keep gas reserve
            if STRIDE_LIQUID_STAKE_ENABLED:
                action = self.stake_atom_via_stride(amount)
            else:
                action = self.stake_native("cosmoshub", amount)
            actions.append(action)
        
        # TIA → Native staking
        tia_info = unstaked.get("celestia")
        if tia_info and tia_info["amount"] > 0.1 and NATIVE_STAKE_TIA:
            amount = tia_info["amount"] - 0.05
            action = self.stake_native("celestia", amount)
            actions.append(action)
        
        # OSMO → Native staking
        osmo_info = unstaked.get("osmosis")
        if osmo_info and osmo_info["amount"] > 0.1 and NATIVE_STAKE_OSMO:
            amount = osmo_info["amount"] - 1.0  # Keep 1 OSMO for gas (needed for swaps)
            action = self.stake_native("osmosis", amount)
            actions.append(action)
        
        return actions
    
    def get_yield_summary(self) -> dict:
        """Get summary of all yield positions and pending rewards."""
        positions = self.get_all_staking_positions()
        unstaked = self.get_unstaked_balances()
        
        total_staked_usd = 0.0
        total_rewards_usd = 0.0
        
        # Rough prices for USD calc
        prices = {"ATOM": 8.0, "OSMO": 0.50, "TIA": 3.50}
        
        for p in positions:
            denom = COSMOS_CHAINS.get(p.chain, None)
            if denom:
                symbol = denom.display_denom
                price = prices.get(symbol, 0)
                total_staked_usd += p.amount * price
                total_rewards_usd += p.rewards_pending * price
        
        return {
            "positions": len(positions),
            "total_staked_usd": total_staked_usd,
            "total_rewards_pending_usd": total_rewards_usd,
            "unstaked_chains": unstaked,
            "last_compound": self._last_compound,
            "actions_taken": len(self._actions_log),
        }
