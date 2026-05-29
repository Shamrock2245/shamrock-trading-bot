import sys
import logging
from config import settings

# Force paper mode for safety
settings.MODE = "paper"

logging.basicConfig(level=logging.INFO, stream=sys.stdout)

from core.capital_rotator import CapitalRotator

def main():
    print("Testing Capital Rotator...")
    rotator = CapitalRotator(rotation_threshold=15)
    rotator.try_rotate()
    print("Test complete.")

if __name__ == "__main__":
    main()
