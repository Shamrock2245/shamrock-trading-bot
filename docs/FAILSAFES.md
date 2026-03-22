# FAILSAFES — What Catches Us When Things Go Wrong

## Failsafe Hierarchy (innermost to outermost)

```
Trade Level:  Stop-Loss → Hard Stop → Position Timeout
  ↓
Portfolio:    Daily Loss Limit → Circuit Breaker
  ↓
System:       Heartbeat Monitor → Kill Switch
  ↓
Human:        Manual Override → Pull the plug
```

## Trade-Level Failsafes

| Failsafe | Trigger | Action |
|----------|---------|--------|
| Stop-loss | Position drops 10% | Sell entire position |
| Hard stop | Position drops 25% | Force sell (catches missed stops) |
| Position timeout | No price movement for 48h | Alert for review |
| Slippage guard | Sell slippage > 5% | Alert — possible honeypot, force sell anyway |

## Portfolio-Level Failsafes

| Failsafe | Trigger | Action |
|----------|---------|--------|
| Daily loss limit | 0.5 ETH lost in one day | Stop all new trades for 24h |
| Circuit breaker | Portfolio value drops 15% | **CLOSE ALL POSITIONS** |
| Max positions | 10 concurrent positions | Block new entries until one closes |
| Max per-cycle | 3 trades per scan cycle | Queue excess for next cycle |

## System-Level Failsafes

| Failsafe | Trigger | Action |
|----------|---------|--------|
| Heartbeat timeout | No heartbeat for 10 minutes | Alert via Slack — system may be down |
| RPC failure | 3 consecutive RPC errors | Switch to backup RPC |
| API rate limit | 429/503 responses | Back off exponentially, requeue |
| Database corruption | Write error | Log, switch to in-memory state, alert |
| Disk full | Log directory > 1GB | Rotate logs, alert |

## Human Overrides
- **Kill switch** — See `KILL_SWITCH.md`
- **Manual position close** — Operator can close any position via dashboard
- **Mode switch** — `MODE=paper` instantly disables live trading

## Cross-References
- `GUARDRAILS.md` — Expanded safety rules
- `KILL_SWITCH.md` — Emergency shutdown procedures
- `ERRORS_AND_RECOVERY.md` — Error handling details
