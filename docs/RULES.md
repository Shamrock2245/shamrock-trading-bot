# RULES — Non-Negotiable Laws

## The Prime Directive
> **Turn $5,000 into $100,000+. Aggressively. Relentlessly. Without blowing up.**

Every rule below serves this single goal. Safety isn't the opposite of profit — safety IS what enables compounding to work.

## The Profit Rules (Do These or Die Broke)

### 1. COMPOUND EVERYTHING
- Never withdraw profits during growth phases
- Every dollar earned goes back into bigger positions
- Compounding is the ONLY reliable path from $5K to 6 figures
- A 1% daily gain compounds to 37x in a year

### 2. TRADE VOLUME MATTERS
- At $5K you need MANY positive-expectancy bets
- Target 5–15 trades per day across all chains
- Scan every 15 seconds — miss nothing
- Speed beats analysis on express lane plays

### 3. LET WINNERS RUN
- Don't sell everything at 2x — that leaves 5x–20x on the table
- Tiered exits: 50% at 2x, 25% at 5x, trail the last 25%
- One 50x winner pays for 25 stopped-out losers
- The trail stop protects gains while keeping upside open

### 4. CUT LOSERS INSTANTLY
- Stop-loss at -8% is NON-NEGOTIABLE (Phase 1)
- Hard stop at -20% catches failed stop-losses
- A $250 position at -8% = $20 loss. Survivable. Recoverable.
- Average hold time for losers should be < 2 hours

### 5. PRIORITIZE LOW-FEE CHAINS
- Phase 1: Solana > Base > Arbitrum > BSC > (skip Ethereum)
- A $5 gas fee on a $250 position = 2% instant loss
- Solana gas is $0.001 — you can make 100 trades for $0.10

---

## Entry Rules
1. **Never trade a token that fails ANY safety check** — GoPlus, Honeypot.is, TokenSniffer, blocklist
2. **Respect liquidity floors** — $15K min in Phase 1, $25K in Phase 2+
3. **Max position size per phase** — 5% in Phase 1, 3% in Phase 2, 2% in Phase 3
4. **Max concurrent positions** — 5 in Phase 1, 8 in Phase 2, 10 in Phase 3
5. **Max 3 new trades per scan cycle** — quality over FOMO
6. **Express lane (score ≥ 80) gets priority** — these are the money trades
7. **Fibonacci alignment on standard lane** — don't fight the levels
8. **Fresh tokens first** — prioritize < 48h old tokens (most upside potential)

## Exit Rules
9. **Stop-loss at -8% (Phase 1) / -10% (Phase 2+)** — NEVER move a stop DOWN
10. **Hard stop at -20%/-25%** — if regular stop fails, this catches it
11. **Tiered take-profits**: Sell 50% at 2x → 25% at 5x → trail remaining 25%
12. **Trailing stop on winners** — 12% trail from peak (wide enough to ride momentum)
13. **Time stop** — no price action for 48h? Exit. Dead tokens don't moon.
14. **Circuit breaker = close EVERYTHING** — portfolio -15% triggers full liquidation

## Risk Rules
15. **Daily loss limit: 0.3 ETH in Phase 1** — if hit, STOP for the day
16. **Never exceed MAX_GAS_GWEI** — 30 gwei in Phase 1, 50 in Phase 3+
17. **Exact token approvals only** — never approve unlimited spending
18. **Never trade a blocklisted token** — check `config/tokens.py`
19. **Circuit breaker cooldown: 24 hours** — no exceptions

## Operational Rules
20. **Every trade gets journaled** — entry, exit, P/L, score, reasoning
21. **Every error gets alerted** — Slack + log file, no silent failures
22. **Heartbeat every 5 minutes** — dead bot = missed opportunities
23. **Paper mode 48h minimum** before any live mode activation
24. **Private keys in .env ONLY** — never in code, never in logs
25. **Phase transitions after 7-day sustained crossing** — no premature scaling

## Hierarchy of Priorities
```
1. COMPOUND    — Never withdraw, reinvest everything
2. SPEED       — See gems first, execute first
3. SAFETY      — Don't get rugged, hacked, or drained
4. DISCIPLINE  — Follow the rules, always
5. VOLUME      — Many bets with positive expectancy
6. COVERAGE    — Scan all chains, miss nothing
```

## What Overrides What
- Safety always overrides any single trade (but NOT the overall mission to profit)
- Circuit breaker overrides all positions (mandatory)
- Risk limits override conviction score (always)
- Speed overrides deep analysis (only on express lane ≥80)
- Phase rules override gut feeling (always)
