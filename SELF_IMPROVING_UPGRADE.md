# Shamrock Trading Bot: Self-Improving AI Agent Upgrade

**Date:** July 22, 2026  
**Status:** 🟢 **PRODUCTION READY** (Fully Implemented & Verified)  
**Target:** Automate parameter tuning and close the feedback loop between performance and strategy.

---

## Overview

Following the **OpenAlice** philosophy of "Trading-as-Git" and "Agentic Workspaces," this upgrade introduces the **Self-Improving Agent**. This system ensures the bot doesn't just trade, but *learns* from its own trade history (`output/trades.json`) to stop capital leaks.

---

## Architecture & Capabilities

### 1. **Closed-Loop Feedback** (`core/self_improving_agent.py`)
- **Automated Audit:** Every 24 hours (or on demand), the agent analyzes `output/trades.json` to calculate win rate, total PnL, average win/loss, and trade counts.
- **Failure Mode Detection:** Automatically detects:
  - **Weak Entries:** Small loss trades (< $5 or < -1.5%).
  - **Hope Trades:** Loss trades held > 30 minutes without recovery.
  - **Toxic Zone Leaks:** Loss trades entered between 08:00 and 14:00 EST.
  - **Repeat Loser Coins:** Tokens hitting stop-loss >= 2 times.
- **LLM Reasoning & Deterministic Fallback:** Uses OpenAI (`OPENAI_MODEL`, default `gpt-5-mini`) to propose "Self-Correction" commits. If `OPENAI_API_KEY` is not present, falls back gracefully to a deterministic rule-based audit without blocking execution.
- **Audit Persistence & Cooldown:** Persists audit results to `output/self_improving_audit.json` and enforces a 24-hour cooldown lock via `output/self_improving_lock.json`.
- **Dynamic Blacklisting:** Automatically feeds repeat loser coins into `WinningEntryFilter`'s dynamic blacklist.

### 2. **AI Autotuner Integration** (`core/llm_auto_tuner.py`)
- **Dynamic Trailing Stop Tuning:** Adjusts `positions.json` spot/gem trailing stops based on daily target proximity.
- **30-Minute Cooldown Lock:** Prevents over-tuning via in-memory and file-based locks (`output/auto_tune_lock.json`).

---

## Runtime Integration

- **Position Monitor Loop (`core/position_monitor.py`):** Automatically invokes `improving_agent.run_self_audit()` in the periodic background loop.
- **Standalone Auto-Tuner Service (`scripts/auto_tuner_service.py`):** Invokes `improving_agent.run_self_audit()` alongside XGBoost and Optuna optimization cycles.
- **Settings & Environment Configuration (`config/settings.py` & `.env.example`):**
  ```env
  SELF_IMPROVEMENT_ENABLED=true
  SELF_IMPROVEMENT_INTERVAL_SECONDS=86400  # 24 hours
  OPENAI_MODEL=gpt-5-mini
  ```

---

## Verification & Test Suite

Unit tests in `tests/test_self_improving_agent.py` verify:
- Parsing trades from `trades.json`
- Accurate metric calculation and failure mode detection
- Deterministic fallback when `OPENAI_API_KEY` is missing
- Mocked LLM API call handling & structured JSON parsing
- Dynamic blacklist insertion and audit file output
- Cooldown lock mechanism

Run tests via:
```bash
python3 -m pytest tests/test_self_improving_agent.py -v
```

---

## Monitoring the Agent

Watch logs for "TaG COMMIT" (Trading-as-Git) messages:
```bash
docker compose logs -f shamrock-bot | grep "Self-Improving Agent"
```

Example Output:
`📝 TaG COMMIT (Self-Improving Agent): Adjusted params {'VOLUME_FLOOR_USD': 1500000} | Blacklisted repeat losers ['KAITO']`
