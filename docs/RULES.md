# RULES — Non-Negotiable Laws

## The Prime Directive
> **Make money aggressively. Protect capital absolutely.**

## Trading Rules

### Entry Rules
1. **Never trade a token that fails ANY safety check** — GoPlus, Honeypot.is, TokenSniffer, blocklist
2. **Never trade a token with < $25,000 liquidity** — exit slippage will eat profits
3. **Never enter more than 2% of portfolio per position** — one bad trade cannot ruin you
4. **Maximum 10 concurrent positions** — focus beats diversification at our scale
5. **Maximum 3 new trades per scan cycle** — quality over quantity
6. **Express lane (score ≥ 82) gets priority execution** — speed is alpha on high-conviction plays
7. **Require Fibonacci alignment when TA is enabled** — don't fight the levels

### Exit Rules
8. **Stop-loss at -10% is NON-NEGOTIABLE** — never hold a position losing more than 10%
9. **Hard stop at -25%** — if stop-loss somehow fails, hard stop catches it
10. **Tiered take-profits**: Sell 50% at 2x, 25% at 5x, trail the remaining 25%
11. **Never hold through a circuit breaker** — if portfolio drops 15%, close EVERYTHING

### Risk Rules
12. **Daily loss limit: 0.5 ETH equivalent** — if hit, stop trading for the day
13. **Never exceed MAX_GAS_GWEI (50 gwei)** — high gas = bad risk/reward
14. **Never approve unlimited token spending** — exact amounts only
15. **Never trade a blocklisted token** — ever

### Operational Rules
16. **Every trade gets journaled** — entry, exit, P/L, score, reasoning
17. **Every error gets logged and alerted** — silent failures kill bots
18. **Heartbeat every 5 minutes** — if the heartbeat dies, something is wrong
19. **Paper mode for 48 hours minimum** on any new chain/strategy before live
20. **Private keys NEVER appear in logs, code, or any file except .env**

## Hierarchy of Priorities
```
1. SAFETY      — Don't get rugged, hacked, or drained
2. CAPITAL     — Don't lose money on net
3. PROFIT      — Maximize gains on winning trades
4. SPEED       — Beat other bots to new listings
5. COVERAGE    — Scan all chains, miss nothing
```

## What Overrides What
- Safety overrides profit (always)
- Circuit breaker overrides all open positions (always)
- Risk limits override conviction score (always)
- Speed overrides deep analysis (only on express lane scores ≥82)
