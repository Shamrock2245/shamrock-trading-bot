# Shamrock Trading Bot: Self-Improving AI Agent Upgrade

**Date:** July 22, 2026  
**Status:** Implementation Ready  
**Target:** Automate parameter tuning and close the feedback loop between performance and strategy.

---

## Overview

Following the **OpenAlice** philosophy of "Trading-as-Git" and "Agentic Workspaces," this upgrade introduces the **Self-Improving Agent**. This system ensures the bot doesn't just trade, but *learns* from its own trade history to stop capital leaks.

---

## New Capabilities

### 1. **Closed-Loop Feedback** (`core/self_improving_agent.py`)
- **Automated Audit:** Every 24 hours, the agent analyzes the `trade_history.csv` to identify parameter drift.
- **Failure Mode Detection:** Automatically detects "Death by a thousand cuts" (weak entries) and "Hope Trades" (long-duration losses).
- **LLM Reasoning:** Uses OpenAI to propose "Self-Correction" commits to the bot's tuning configuration.

### 2. **AI Autotuner Integration** (`core/llm_auto_tuner.py`)
- **Dynamic Parameter Scaling:** Automatically adjusts `VOLUME_FLOOR_USD`, `FAST_BREAK_EVEN_PCT`, and `TRAILING_STOP_PCT` based on the agent's findings.
- **30-Minute Cooldown:** Prevents over-tuning by enforcing a strict 30-minute interval between self-corrections.

---

## Integration Plan

### Step 1: Deploy the Self-Improving Agent
```bash
# Added to core/:
# - core/self_improving_agent.py
```

### Step 2: Configure the Feedback Loop
Add the agent to the main trading loop in `core/executor.py`:
```python
from core.self_improving_agent import improving_agent

def daily_maintenance():
    """Run daily self-improvement audit."""
    improving_agent.run_self_audit()
    logger.info("Self-Improving Agent: Daily audit complete.")
```

### Step 3: Update `.env`
Enable the self-improving features:
```env
SELF_IMPROVEMENT_ENABLED=true
AUTO_TUNE_INTERVAL=86400  # 24 hours
OPENAI_MODEL=gpt-5-mini
```

---

## Expected Impact

- **Zero Manual Tuning:** The bot will automatically tighten its own filters if it detects a leak.
- **Adaptive Strategy:** If market conditions become choppy (as seen in the 08:00-14:00 EST toxic zone), the agent will automatically reduce position sizes or increase the convergence gate.
- **Capital Protection:** By identifying coins that hit SL 3+ times (e.g., AAVE, GRASS), the agent will dynamically update the blacklist without human intervention.

---

## Monitoring the Agent

Watch the logs for "TaG COMMIT" (Trading-as-Git) messages:
```bash
docker compose logs -f shamrock-bot | grep "Self-Correction"
```

Example Output:
`📝 Self-Correction Commit: Tightening volume floor to $1.5M to eliminate weak entries in choppy market.`

---

## Next Steps

1. **Merge this PR** to `main`.
2. **Deploy** the updated Docker container.
3. **Monitor the first audit cycle** (triggered 24h after deployment).
4. **Scale capital** once the agent confirms a stable Profit Factor > 1.5.
