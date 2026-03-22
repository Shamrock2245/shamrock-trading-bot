# SLIPPAGE RULES — Don't Give Away Profit to the Pool

## What Is Slippage
Slippage = the difference between the expected price and the actual execution price. On small-cap DEX tokens, slippage can eat your entire profit.

## Slippage Tolerances

### Buy (Entry)
| Pool Liquidity | Max Slippage |
|----------------|-------------|
| > $500K | 1.0% |
| $200K–$500K | 1.5% |
| $100K–$200K | 2.0% |
| $50K–$100K | 2.5% |
| $25K–$50K | 3.0% |
| < $25K | **DO NOT TRADE** |

### Sell (Exit)
| Urgency | Max Slippage |
|---------|-------------|
| Normal exit (take-profit) | Same as buy table |
| Stop-loss trigger | +1% above buy table |
| Hard stop / circuit breaker | 5% (emergency, just get out) |

## Slippage Calculation
```
expected_output = input_amount × price
min_output = expected_output × (1 - slippage_pct / 100)
```

## Pre-Trade Slippage Check
Before submitting ANY trade:
1. Get quote from aggregator (1inch / Jupiter / CoW)
2. Compare quoted output vs. expected output
3. If slippage > tolerance → **REJECT** the trade
4. Log the rejection with slippage amount

## Slippage Protection Strategies
- **Use aggregators** — they route across multiple pools for better prices
- **Split large orders** — break into smaller chunks if position > 5% of pool liquidity
- **Avoid low-liquidity times** — weekends and off-hours have thinner books
- **MEV protection** on Ethereum — prevents sandwich attacks that inflate slippage

## Impact on Profitability
```
$150 position, 3% slippage on buy + 3% on sell = 6% round-trip cost
Need at least 6% gain just to BREAK EVEN
→ This is why we don't trade pools < $25K liquidity
```
