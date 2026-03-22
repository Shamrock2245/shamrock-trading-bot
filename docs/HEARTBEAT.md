# HEARTBEAT — Proof of Life

## What It Is
The heartbeat is a periodic signal that confirms the bot is alive and operating normally. If the heartbeat stops, something is wrong.

## Heartbeat Interval
- **Frequency:** Every 5 minutes
- **Channel:** Slack `#shamrock-alerts` + log file
- **Content:** Status summary

## Heartbeat Payload
```
🍀 SHAMROCK HEARTBEAT — 2026-03-22 19:15:00 UTC
Mode: paper | live
Uptime: 4h 32m
Cycle #: 548

Portfolio:
  Total Value: $10,234.56
  Open Positions: 4/10
  Today P/L: +$87.23 (+0.86%)

Last Scan:
  Candidates Found: 3
  Express Lane: 1
  Trades Executed: 1

Health:
  RPCs: ✅ 6/6 chains responding
  APIs: ✅ All data providers online
  Disk: ✅ 2.3GB free
  Memory: ✅ 412MB used
  
Alerts: None
```

## Missing Heartbeat Protocol
| Duration | Severity | Action |
|----------|----------|--------|
| 5-10 min | ⚠️ Warning | Log — could be a slow cycle |
| 10-30 min | 🟠 Escalate | Slack alert to operator |
| 30+ min | 🔴 Critical | Assume bot is dead, investigate |

## What a Healthy Heartbeat Looks Like
- Consistent 5-minute intervals (± 30 seconds)
- No error count increase
- RPC/API health all green
- Position count stable or decreasing (not orphaned)

## What a Sick Heartbeat Looks Like
- Irregular intervals (> 7 minutes between beats)
- Error count climbing
- RPCs dropping (< 6/6)
- Memory usage climbing continuously (memory leak)
- Disk space shrinking fast (log flood)
