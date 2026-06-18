import sys
sys.path.append("/Users/brendan/Desktop/shamrock-trading-bot")
from core.hl_perps_scanner import HLPerpsScanner
import logging

logging.basicConfig(level=logging.INFO)
scanner = HLPerpsScanner()
signals = scanner.run_cycle()
print(f"Found {len(signals)} signals")
for s in signals:
    print(s)
