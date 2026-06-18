import json
import os
from datetime import datetime

# 1. Episodic Memory
episodic = {
    "what_happened": {
        "skill_used": "trade_execution",
        "task": "Fixing awal rollback bug and docker dependency",
        "outcome": "success"
    },
    "key_insights": {
        "what_went_well": ["Identified the command structure flaw in awal"],
        "what_went_wrong": ["The CLI tool npx awal trade takes token amount as the first argument, not fiat amount. Passing fiat amount would have dumped all held tokens.", "npx wasn't installed in the runtime docker image."],
        "root_cause": "Misunderstanding of the `npx awal trade <amount> <asset1> <asset2>` syntax.",
        "files_modified": ["core/funding_farmer.py", "Dockerfile"]
    }
}
os.makedirs("memory/episodic", exist_ok=True)
with open("memory/episodic/2026-06-18-awal-rollback-bug.json", "w") as f:
    json.dump(episodic, f, indent=2)

# 2. Semantic Memory
with open("memory/semantic-patterns.json", "r") as f:
    semantic = json.load(f)

new_pattern = {
    "id": "awal_trade_amount_syntax",
    "category": "trade_execution",
    "pattern": "When calling `npx awal trade <amount> <from_asset> <to_asset>`, the amount is ALWAYS measured in units of the `<from_asset>`. Never pass a USD volume if the `<from_asset>` is a token like ETH. Calculate `token_amount = usd_volume / token_price` first.",
    "confidence": 0.95,
    "source": "ep-2026-06-18-awal-rollback-bug",
    "added": datetime.utcnow().strftime("%Y-%m-%d")
}

new_pattern_docker = {
    "id": "npx_docker_dependency",
    "category": "deployment",
    "pattern": "If the python bot shells out to `npx` (e.g. for agentic wallets), `nodejs` and `npm` MUST be installed in the runtime Dockerfile.",
    "confidence": 0.95,
    "source": "ep-2026-06-18-awal-rollback-bug",
    "added": datetime.utcnow().strftime("%Y-%m-%d")
}

if "patterns" not in semantic:
    semantic["patterns"] = []

semantic["patterns"].extend([new_pattern, new_pattern_docker])

with open("memory/semantic-patterns.json", "w") as f:
    json.dump(semantic, f, indent=2)
print("Memory updated successfully.")
