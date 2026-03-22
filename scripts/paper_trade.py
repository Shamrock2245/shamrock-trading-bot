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

# Force paper mode
os.environ["MODE"] = "paper"

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import and run the main bot loop
from main import main

if __name__ == "__main__":
    print("☘️  Starting Shamrock Paper Trader (MODE=paper)")
    main()
