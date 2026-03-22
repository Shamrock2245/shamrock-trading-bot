# LIQUIDITY FILTERS — Only Trade Where You Can Exit

## The Rule
> **If you can't sell, it doesn't matter how cheap you bought.**

## Minimum Liquidity Requirements

| Filter | Threshold | Env Var |
|--------|-----------|---------|
| Pool liquidity | ≥ $25,000 | `MIN_LIQUIDITY_USD=25000` |
| 24h volume | ≥ $10,000 | Checked in scoring |
| Buy/sell ratio | ≥ 0.3 | Checked in safety |

## Why $25,000 Minimum
```
Your position: $150
Pool liquidity: $25,000
Your % of pool: 0.6%
Expected slippage: ~1-2%
→ Acceptable

Your position: $150
Pool liquidity: $5,000
Your % of pool: 3%
Expected slippage: ~5-10%
→ Unacceptable — you'd lose 10% just entering
```

## Liquidity Quality Checks

### Red Flags (Instant Reject)
- Only 1 liquidity provider → rug pull risk (LP can remove all liquidity)
- Liquidity added in last 1 hour → possible bait
- Liquidity unlocked → LP can pull at any time
- Volume-to-liquidity ratio > 10:1 → suspicious wash trading

### Green Flags (Score Boost)
- Multiple LPs providing liquidity
- Liquidity locked for > 6 months
- Healthy volume-to-liquidity ratio (1:1 to 5:1)
- Liquidity growing over time

## Liquidity Scoring (Part of Gem Score — 13% Weight)

| Liquidity | Score |
|-----------|-------|
| ≥ $500K | 100 |
| $200K–$500K | 85 |
| $100K–$200K | 70 |
| $50K–$100K | 50 |
| $25K–$50K | 25 |
| < $25K | 0 (rejected) |

## Exit Liquidity Check
Before selling, verify:
1. Pool still has sufficient liquidity
2. Estimated slippage is within tolerance
3. If liquidity has dropped significantly since entry → alert and force exit ASAP
