"""
Recursive Decision Ledger (ECC Skill: recursive-decision-ledger)
Logs structured reasoning for every trade acceptance or rejection.
Creates an auditable trail for the continuous learning loop to parse.
"""

import os
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

LEDGER_DIR = Path("logs/decision_ledger")
LEDGER_DIR.mkdir(parents=True, exist_ok=True)

class RecursiveDecisionLedger:
    def __init__(self):
        self.ledger_file = LEDGER_DIR / f"ledger_{datetime.now(timezone.utc).strftime('%Y-%m')}.jsonl"

    def record_decision(self, token_symbol: str, token_address: str, chain: str, 
                        decision: str, reason: str, metrics: dict):
        """
        decision: 'ACCEPT' or 'REJECT'
        reason: Plaintext explanation
        metrics: Dictionary of numerical values (gem_score, liquidity, age, etc.)
        """
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "token_symbol": token_symbol,
            "token_address": token_address,
            "chain": chain,
            "decision": decision,
            "reason": reason,
            "metrics": metrics
        }
        
        try:
            with open(self.ledger_file, 'a') as f:
                f.write(json.dumps(entry) + "\n")
            logger.debug(f"Decision ledger updated for {token_symbol} -> {decision}")
        except Exception as e:
            logger.error(f"Failed to write to decision ledger: {e}")

decision_ledger = RecursiveDecisionLedger()
