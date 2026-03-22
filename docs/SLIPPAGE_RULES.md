# SLIPPAGE RULES — Don't Give Profits to the Pool

## The $5K Slippage Reality
At $250 positions, slippage is a PERCENTAGE game. 3% slippage on a $250 trade = $7.50 lost. That's tolerable. But 3% slippage on BOTH entry AND exit = 6% round-trip cost, which means you need a 6% gain just to break even.

## Phase 1 Slippage Tolerances ($5K Portfolio, $250 Positions)

### Buy (Entry)
| Pool Liquidity | Max Slippage | Your Impact | Realistic Cost |
|----------------|-------------|-------------|----------------|
| > $500K | 1.0% | Negligible | $2.50 |
| $200K–$500K | 1.5% | Tiny | $3.75 |
| $100K–$200K | 2.0% | Small | $5.00 |
| $50K–$100K | 2.5% | Moderate | $6.25 |
| $25K–$50K | 3.0% | Noticeable | $7.50 |
| $15K–$25K | 3.5% | Significant | $8.75 |
| < $15K | **DO NOT TRADE** | — | — |

### Sell (Exit)
| Urgency | Slippage Above Buy Table | Why |
|---------|-------------------------|-----|
| Normal take-profit | Same as buy | No rush, get good price |
| Stop-loss trigger | +1.0% wider | Speed > price |
| Hard stop / circuit breaker | Up to 5.0% | **JUST GET OUT** |
| Liquidity emergency (LP removing) | Up to 8.0% | **GET OUT NOW** (something > nothing) |

## Slippage Pre-Check (Every Trade)
```python
# Before EVERY trade submission:
quote = get_aggregator_quote(token, amount)
expected = amount * current_price
actual_slippage = abs(quote - expected) / expected * 100

if actual_slippage > max_allowed_slippage:
    log(f"SLIPPAGE REJECTED: {actual_slippage:.1f}% > {max_allowed:.1f}%")
    skip_trade()
```

## Round-Trip Slippage Budget
| Pool Size | Buy Slip | Sell Slip | Total | Min Gain to Profit |
|-----------|----------|-----------|-------|-------------------|
| $500K+ | 1% | 1% | 2% | Need +3% to profit |
| $100K | 2% | 2% | 4% | Need +5% to profit |
| $25K | 3% | 3% | 6% | Need +7% to profit |
| $15K | 3.5% | 3.5% | 7% | Need +8% to profit |

**At Phase 1 targets (avg win +40%), even 7% round-trip slippage is easily covered.**

## Slippage Reduction Strategies
1. **Use aggregators (1inch/Jupiter)** — route across multiple pools
2. **Avoid thin liquidity hours** — weekends + 2-6AM UTC
3. **Don't trade > 5% of pool** — your order is too big for the pool
4. **MEV protection on ETH** — prevents sandwich attacks (Phase 2+)
5. **Split large orders** — if position > 3% of pool, split into 2-3 txns

## Phase 2+ Adjustments
As positions grow ($450-$1,500), tighten slippage:
- Raise `MIN_LIQUIDITY_USD` to $25,000
- Reduce max slippage by 0.5% across all tiers
- Only trade pools where your position is < 2% of liquidity
