# DAILY LOSS LIMITS — Containing the Damage Per Phase

## The Rule
> **If you lose more than the daily limit, STOP TRADING for the rest of the day.**

One bad day should NEVER destroy a week of compounding gains.

## Phase-Specific Daily Limits

| Phase | Portfolio | Daily Loss Limit | As % of Portfolio | Env Var Value |
|-------|----------|-----------------|-------------------|---------------|
| **Phase 1** | $5K–$15K | **0.3 ETH (~$600)** | ~6-12% | `0.3` |
| **Phase 2** | $15K–$50K | **0.75 ETH (~$1,500)** | ~3-10% | `0.75` |
| **Phase 3** | $50K–$250K | **1.5 ETH (~$3,000)** | ~1-6% | `1.5` |
| **Phase 4** | $250K+ | **3.0 ETH (~$6,000)** | ~1-2% | `3.0` |

## Why 0.3 ETH for Phase 1
```
Portfolio: $5,000
Daily limit: 0.3 ETH ≈ $600 ≈ 12% of portfolio

Worst case: 3 positions hit stop-loss (-8% each)
  3 × $250 × 0.08 = $60 total loss
  
Daily limit gives you room for 10 stop-outs before forced pause.
That's extremely unlikely (would need 10 from 5 positions closing and re-entering).

In practice, the daily limit is a safety net for CATASTOPHIC days,
not normal trading losses.
```

## What Counts as a Loss
| Event | Counts? | Amount Counted |
|-------|---------|---------------|
| Position closed at stop-loss | ✅ Yes | Full realized loss |
| Position closed at hard stop | ✅ Yes | Full realized loss |
| Manual close at a loss | ✅ Yes | Full realized loss |
| Unrealized loss (still open) | ❌ No | Not yet realized |
| Gas fees on failed tx | ✅ Yes | Gas cost |
| Gas fees on profitable trades | ❌ No | Cost of doing business |
| Slippage above expected | ✅ Yes | Excess slippage amount |

## What Happens When Limit Is Hit
1. **Block ALL new trade entries immediately**
2. **Continue monitoring existing positions** — don't abandon open trades
3. **Execute stop-losses and take-profits normally** on existing
4. **Send Slack alert:** 
   ```
   🔴 DAILY LOSS LIMIT HIT
   Lost: 0.32 ETH ($640)
   Limit: 0.30 ETH ($600)
   Trading paused until 00:00 UTC
   Open positions: 3 (still monitoring)
   ```
5. **Resume at midnight UTC** — fresh daily counter

## Psychological Value
The daily loss limit protects against **tilt** — the emotional state where you keep trading to "make back" losses, which always makes it worse. The bot doesn't have emotions, but the RULES enforce the discipline that humans would need:
- After losses, the bot might be scanning garbage market conditions
- Forcing a pause prevents compounding bad-market losses
- A fresh start tomorrow with clear signals is smarter

## Daily Limit Reset
- **Time:** 00:00 UTC daily
- **Counter resets to 0** — full trading resumes
- **No carry-over** — yesterday's losses don't count today
- **Exception:** If circuit breaker triggered, 24h cooldown overrides daily reset
