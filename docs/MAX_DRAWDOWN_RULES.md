# MAX DRAWDOWN RULES — Protecting the Bag at Every Phase

## What Is Max Drawdown
Max drawdown = the largest peak-to-trough decline in portfolio value. It measures your worst day/week ever.

**At $5K, a 20% drawdown = $1,000. That's real money that takes REAL trades to earn back.**

## Phase-Specific Drawdown Thresholds

### Phase 1 ($5K–$15K)
| Level | Drawdown | Dollar Loss | Action |
|-------|----------|-------------|--------|
| 🟢 Normal | 0–5% | $0–$250 | Continue trading normally |
| 🟡 Caution | 5–10% | $250–$500 | Reduce positions to 3 max |
| 🟠 Warning | 10–15% | $500–$750 | Stop new trades, monitor only |
| 🔴 Circuit Breaker | > 15% | > $750 | **CLOSE ALL POSITIONS** |

### Phase 2 ($15K–$50K)
| Level | Drawdown | Action |
|-------|----------|--------|
| 🟢 Normal | 0–5% | Full trading |
| 🟡 Caution | 5–8% | Reduce to 6 positions max |
| 🟠 Warning | 8–12% | New trades paused |
| 🔴 Circuit Breaker | > 15% | **CLOSE ALL** |

### Phase 3+ ($50K+)
| Level | Drawdown | Action |
|-------|----------|--------|
| 🟢 Normal | 0–4% | Full trading |
| 🟡 Caution | 4–8% | Reduce position sizes 50% |
| 🟠 Warning | 8–12% | New trades paused |
| 🔴 Circuit Breaker | > 12% | **CLOSE ALL** (tighter at scale) |

## High-Water Mark Tracking
```
peak_value = max(peak_value, current_value)  # Only goes UP
drawdown_pct = (peak_value - current_value) / peak_value * 100

# Example at $5K:
Peak hits $6,200 (from good trades)
Current drops to $5,580 (from some losses)
Drawdown = ($6,200 - $5,580) / $6,200 = 10.0%
→ Action: CAUTION mode — reduce to 3 positions max
```

## Recovery Math — Why Prevention Matters
| Drawdown | Required Gain to Recover | Trades to Recover* |
|----------|------------------------|--------------------|
| -5% | +5.3% | ~5 winning trades |
| -10% | +11.1% | ~11 winning trades |
| -15% | +17.6% | ~18 winning trades |
| -20% | +25.0% | ~25 winning trades |
| -50% | +100.0% | ~100 winning trades |

*Assuming avg win of +1% per trade. Recovery gets EXPONENTIALLY harder.*

## Recovery Protocol After Circuit Breaker
1. **Wait 24 hours** — mandatory cooldown, no exceptions
2. **Review what caused it** — was it market, strategy, or bug?
3. **Paper trade for 4-8 hours** — verify bot is functioning correctly
4. **Resume live at 50% position sizes** for 48 hours
5. **If stable for 48h** → return to full Phase 1 parameters
6. **If circuit breaker triggers AGAIN within 7 days** → stop, major strategy review needed

## Weekly Drawdown Tracking
Every Sunday, log:
- Peak portfolio value this week
- Lowest portfolio value this week
- Max intra-week drawdown
- Current portfolio vs. all-time high

**If max drawdown exceeds 10% for 3 consecutive weeks: RAISE MIN_GEM_SCORE by 10 points.**
