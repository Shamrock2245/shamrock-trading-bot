# ERRORS & RECOVERY — Handling Every Failure Mode

## Error Categories

### 🔴 Critical (Stop Trading Immediately)
| Error | Cause | Recovery |
|-------|-------|----------|
| Private key invalid | Misconfigured `.env` | Fix key, restart |
| Wallet drained | Compromise / bug | KILL SWITCH, investigate |
| Circuit breaker triggered | Portfolio -15% | Close all, 24h cooldown |
| Database corruption | Disk failure | Restore from backup |

### 🟠 Severe (Pause and Fix)
| Error | Cause | Recovery |
|-------|-------|----------|
| All RPCs down | Provider outage | Switch to backup RPCs, wait |
| Safety APIs all down | GoPlus/Honeypot outage | Pause new trades, keep monitoring |
| Wallet balance zero | Gas depleted | Refill wallet, resume |

### 🟡 Warning (Log and Continue)
| Error | Cause | Recovery |
|-------|-------|----------|
| Single RPC timeout | Network congestion | Retry with exponential backoff |
| API rate limited | Too many requests | Back off, respect rate limits |
| TX reverted | Slippage / timing | Log, skip this trade |
| Price feed stale | API delay | Use cached price, flag position |

### 🟢 Info (Expected)
| Error | Cause | Recovery |
|-------|-------|----------|
| No candidates found | Normal during quiet markets | Wait for next cycle |
| Token failed safety | Working as designed | Log and skip |
| Score below threshold | Normal filtering | Continue scanning |

## Retry Policy
```
Attempt 1: Immediate
Attempt 2: Wait 2 seconds
Attempt 3: Wait 4 seconds
Attempt 4: Wait 15 seconds
After 4 failures: Log error, skip, alert via Slack
```

## Recovery Procedures

### 1. Bot Crashes Mid-Trade
- On restart: Check `output/positions.json` for any partial states
- Verify on-chain: Does the wallet hold the tokens?
- If YES → re-create position record
- If NO → mark trade as failed, log the discrepancy

### 2. Stuck Transaction
- Check tx hash on explorer
- If pending > 5 min → allow time for confirmation
- If dropped → log and mark as cancelled
- NEVER submit duplicate transactions

### 3. API Key Expired
- Symptom: 401/403 errors from data providers
- Fix: Update key in `.env`, restart
- Prevention: Set calendar reminders for key expiry

### 4. Disk Full
- Symptom: Write errors in logs
- Fix: Rotate logs (`logs/` > 500MB → archive old files)
- Prevention: Automated log rotation every 24h
