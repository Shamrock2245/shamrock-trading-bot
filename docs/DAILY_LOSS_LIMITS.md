# DAILY LOSS LIMITS — Containing the Damage

## The Rule
> **If you lose 0.5 ETH (or equivalent) in a single day, STOP TRADING for the remainder of that day.**

## Configuration
- **Env var:** `DAILY_LOSS_LIMIT_ETH=0.5`
- **Reset time:** 00:00 UTC daily
- **Measurement:** Sum of all realized losses (closed positions with negative P/L) in the current day

## What Counts as a Loss
| Event | Counts? |
|-------|---------|
| Position closed at stop-loss | ✅ Yes |
| Position closed at hard stop | ✅ Yes |
| Position closed manually at a loss | ✅ Yes |
| Unrealized loss (still open) | ❌ No (not yet realized) |
| Gas fees on winning trades | ❌ No |
| Gas fees on losing trades | ✅ Yes (adds to loss) |

## What Happens When Limit Is Hit
1. **Immediately stop all new trade entries**
2. **Continue monitoring existing positions** (don't abandon open trades)
3. **Execute stop-losses and take-profits normally** on existing positions
4. **Send Slack alert:** "⚠️ Daily loss limit reached: 0.52 ETH lost today. Trading paused until 00:00 UTC."
5. **Resume at midnight UTC** — fresh daily counter

## Scaling the Limit
| Portfolio Size | Recommended Daily Limit |
|----------------|------------------------|
| < $5,000 | 0.2 ETH |
| $5,000–$20,000 | 0.5 ETH |
| $20,000–$100,000 | 1.0 ETH |
| > $100,000 | 2.0 ETH |

## Why This Matters
One bad day should NOT destroy a week of gains. The daily limit forces discipline and prevents tilt (emotional overtrading after losses). You live to trade another day.
