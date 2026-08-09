"""
scripts/paper_trade.py — Shamrock Paper Trading Runner.

Runs the full bot loop in paper mode (no real transactions).
Used by the paper-trader Docker container for safe simulation.

Usage:
    python scripts/paper_trade.py
    MODE=paper python scripts/paper_trade.py
"""

import os
import sys

# Force paper mode + lock auto-promotion for the tuning campaign
os.environ["MODE"] = "paper"
os.environ.setdefault("PAPER_MODE_LOCKED", "true")
os.environ.setdefault("PAPER_TUNING_CAMPAIGN_ENABLED", "true")

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import and run the main bot loop
from main import main

if __name__ == "__main__":
    print("☘️  Starting Shamrock Paper Trader (MODE=paper, PAPER_MODE_LOCKED=true)")
    print("    Tuning campaign: real orders disabled — auto-tuner + Optuna may apply params.")
    main()
