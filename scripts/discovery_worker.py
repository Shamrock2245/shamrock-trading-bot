"""Run the alpha discovery worker. `--once` prints the top candidates and exits."""
import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import alpha_discovery as ad  # noqa: E402

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    if "--once" in sys.argv:
        pl = ad.run_discovery_cycle()
        for c in pl["top"][:15]:
            print(f"{c['coin']:>10} {c['score']:6.1f} {c['route']:<18} vetoes={c['vetoes']}")
        print(json.dumps({"predator_queue": pl["predator_queue"], "proposals": pl["promotion_proposals"]}))
    else:
        ad.start_worker()
        while True:
            time.sleep(3600)
