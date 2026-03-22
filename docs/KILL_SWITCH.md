# KILL SWITCH — Emergency Shutdown

## What It Is
The kill switch is the **nuclear option** — it immediately stops ALL trading activity and closes all open positions.

## How to Trigger

### Method 1: Change Mode (Recommended)
```bash
# In .env file:
MODE=paper
```
Then restart the bot. All new trades are blocked. Existing positions continue to be monitored but no new entries occur.

### Method 2: Stop the Process
```bash
# Docker
docker compose stop shamrock-bot

# Direct Python
pkill -f "python main.py"
# or Ctrl+C in terminal
```

### Method 3: Circuit Breaker (Automatic)
Triggered automatically when portfolio drops > 15%. Closes ALL positions.

### Method 4: Dashboard (Future)
One-click PANIC button on the Operations page of the Streamlit dashboard.

## Kill Switch Behavior
When triggered:
1. **Stop all scanners** — no new candidates
2. **Cancel pending orders** — nothing waiting to execute
3. **Close all open positions** — market sell everything
4. **Send emergency Slack alert** — "🚨 KILL SWITCH ACTIVATED"
5. **Log the event** — timestamp, trigger reason, portfolio snapshot
6. **Enter cooldown mode** — no trading for 24 hours minimum

## After Kill Switch

### Assessment Checklist
- [ ] What triggered the kill switch?
- [ ] Was it a bug, market crash, or compromise?
- [ ] Are all positions actually closed? (verify on-chain)
- [ ] Are wallet balances consistent with expected values?
- [ ] Is the bot code intact and unmodified?
- [ ] Are API keys still valid and uncompromised?

### Recovery Procedure
1. Identify and fix the root cause
2. Paper trade for at least 4 hours
3. Verify all safety checks pass
4. Resume with **50% position sizes** for first 48 hours
5. Graduate back to full sizes after 48 hours of stable performance

## When to Use Kill Switch
| Situation | Kill Switch? |
|-----------|-------------|
| Single losing trade | ❌ No — stop-loss handles it |
| 3 consecutive losses | ❌ No — daily loss limit handles it |
| Portfolio -15% | ✅ Yes — circuit breaker auto-triggers |
| Suspected wallet compromise | ✅ Yes — immediately |
| Bug in execution logic | ✅ Yes — fix first |
| Market-wide crash (BTC -15%) | ✅ Yes — wait for stability |
| RPC outage | ⚠️ Maybe — bot can't trade anyway |
