"""
cosmos/ibc_transfer.py — IBC cross-chain transfer engine.

Handles moving assets between Cosmos chains via IBC protocol.
"""

import logging
import time
from dataclasses import dataclass
from typing import Optional

import requests

from cosmos.cosmos_config import COSMOS_CHAINS, COSMOS_ADDRESSES, COSMOS_MODE
from cosmos.cosmos_wallet import CosmosWallet, CosmosTxResult

logger = logging.getLogger(__name__)


@dataclass
class IBCTransferResult:
    """Result of an IBC transfer."""
    success: bool
    source_chain: str = ""
    dest_chain: str = ""
    amount: float = 0.0
    denom: str = ""
    tx_hash: Optional[str] = None
    error: Optional[str] = None
    is_paper: bool = True


class IBCTransferEngine:
    """
    Execute IBC transfers between Cosmos chains.
    """
    
    def __init__(self):
        self.is_paper = COSMOS_MODE != "live"
    
    def build_ibc_transfer_msg(
        self,
        source_chain: str,
        dest_chain: str,
        denom: str,
        amount: int,
        timeout_minutes: int = 10,
    ) -> dict:
        """
        Build an IBC MsgTransfer message.
        
        Args:
            source_chain: Source chain key (e.g., "cosmoshub")
            dest_chain: Destination chain key (e.g., "osmosis")
            denom: Token denom on source chain
            amount: Amount in raw denomination
            timeout_minutes: IBC transfer timeout
        """
        source_cfg = COSMOS_CHAINS[source_chain]
        source_addr = COSMOS_ADDRESSES[source_chain]
        dest_addr = COSMOS_ADDRESSES[dest_chain]
        
        # Get IBC channel from source → dest
        channel = source_cfg.ibc_channels.get(dest_chain)
        if not channel:
            raise ValueError(
                f"No IBC channel configured from {source_chain} → {dest_chain}"
            )
        
        # Timeout timestamp (nanoseconds from now)
        timeout_ns = int((time.time() + timeout_minutes * 60) * 1e9)
        
        return {
            "@type": "/ibc.applications.transfer.v1.MsgTransfer",
            "source_port": "transfer",
            "source_channel": channel,
            "token": {
                "denom": denom,
                "amount": str(amount),
            },
            "sender": source_addr,
            "receiver": dest_addr,
            "timeout_height": {"revision_number": "0", "revision_height": "0"},
            "timeout_timestamp": str(timeout_ns),
            "memo": "",
        }
    
    def transfer(
        self,
        source_chain: str,
        dest_chain: str,
        denom: str,
        amount: int,
    ) -> IBCTransferResult:
        """
        Execute an IBC transfer between chains.
        
        Paper mode: logs the transfer without executing.
        Live mode: Signs and broadcasts the TX.
        """
        source_cfg = COSMOS_CHAINS[source_chain]
        human_amount = amount / (10 ** source_cfg.decimals)
        
        logger.info(
            f"IBC transfer: {human_amount:.4f} {denom} "
            f"from {source_chain} → {dest_chain}"
        )
        
        # Validate channel exists
        channel = source_cfg.ibc_channels.get(dest_chain)
        if not channel:
            return IBCTransferResult(
                success=False,
                source_chain=source_chain,
                dest_chain=dest_chain,
                error=f"No IBC channel from {source_chain} → {dest_chain}",
            )
        
        if self.is_paper:
            logger.info(f"📄 PAPER MODE — IBC transfer simulated")
            return IBCTransferResult(
                success=True,
                source_chain=source_chain,
                dest_chain=dest_chain,
                amount=human_amount,
                denom=denom,
                tx_hash=f"paper_ibc_{int(time.time())}",
                is_paper=True,
            )
        
        # Build and broadcast
        try:
            msg = self.build_ibc_transfer_msg(
                source_chain, dest_chain, denom, amount
            )
            wallet = CosmosWallet(source_chain)
            
            # Live signing placeholder
            logger.warning("Live IBC transfer requires cosmospy signing")
            return IBCTransferResult(
                success=False,
                source_chain=source_chain,
                dest_chain=dest_chain,
                error="Live signing not yet implemented",
                is_paper=False,
            )
        except Exception as e:
            return IBCTransferResult(
                success=False,
                source_chain=source_chain,
                dest_chain=dest_chain,
                error=str(e),
            )
    
    def transfer_all_to_osmosis(self) -> list:
        """
        Transfer all assets from other chains to Osmosis for trading.
        This is the first step in the aggressive strategy —
        concentrate everything on Osmosis.
        """
        results = []
        
        # ATOM from Cosmos Hub → Osmosis
        cosmos_wallet = CosmosWallet("cosmoshub")
        atom_balance = cosmos_wallet.get_native_balance()
        if atom_balance > 0.01:
            atom_raw = int(atom_balance * 1e6)
            # Keep tiny amount for gas
            gas_reserve = int(0.05 * 1e6)  # 0.05 ATOM for gas
            transfer_amount = max(0, atom_raw - gas_reserve)
            
            if transfer_amount > 0:
                result = self.transfer(
                    "cosmoshub", "osmosis", "uatom", transfer_amount
                )
                results.append(result)
                logger.info(
                    f"ATOM transfer: {transfer_amount / 1e6:.4f} ATOM → Osmosis"
                )
        
        # TIA from Celestia → Osmosis
        celestia_wallet = CosmosWallet("celestia")
        tia_balance = celestia_wallet.get_native_balance()
        if tia_balance > 0.01:
            tia_raw = int(tia_balance * 1e6)
            gas_reserve = int(0.05 * 1e6)
            transfer_amount = max(0, tia_raw - gas_reserve)
            
            if transfer_amount > 0:
                result = self.transfer(
                    "celestia", "osmosis", "utia", transfer_amount
                )
                results.append(result)
                logger.info(
                    f"TIA transfer: {transfer_amount / 1e6:.4f} TIA → Osmosis"
                )
        
        return results
    
    def check_ibc_transfer_status(
        self, tx_hash: str, chain: str
    ) -> Optional[str]:
        """Check if an IBC transfer has been acknowledged."""
        try:
            cfg = COSMOS_CHAINS[chain]
            url = f"{cfg.rest_url}/cosmos/tx/v1beta1/txs/{tx_hash}"
            resp = requests.get(url, timeout=15)
            
            if resp.status_code == 200:
                data = resp.json()
                tx_response = data.get("tx_response", {})
                code = int(tx_response.get("code", -1))
                
                if code == 0:
                    return "success"
                return f"failed: code={code}"
            
            return "pending"
        except Exception:
            return "unknown"
