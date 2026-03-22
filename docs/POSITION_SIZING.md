# POSITION SIZING — How Much to Bet

## Core Formula
```
Position Size = Portfolio Value × MAX_POSITION_PCT × Conviction Multiplier
```

## Defaults
- `MAX_POSITION_SIZE_PERCENT` = 2.0% of total portfolio
- `MAX_CONCURRENT_POSITIONS` = 10
- Maximum total exposure = 20% of portfolio (10 × 2%)

## Conviction-Based Scaling

| Gem Score | Conviction | Multiplier | Effective Size |
|-----------|-----------|------------|---------------|
| 82–100 | 🔥 Express lane | 1.0x | 2.0% of portfolio |
| 70–81 | ✅ High | 0.75x | 1.5% of portfolio |
| 55–69 | ⚠️ Moderate | 0.50x | 1.0% of portfolio |
| < 55 | ❌ Below threshold | 0x | NO TRADE |

## Example with $10,000 Portfolio
| Gem Score | Multiplier | Position Size |
|-----------|-----------|--------------|
| 90 | 1.0x | $200 |
| 75 | 0.75x | $150 |
| 60 | 0.50x | $100 |
| 50 | N/A | $0 (no trade) |

## Kelly Criterion Guidance
For advanced sizing (future implementation):
```
Kelly % = Win Rate - (Loss Rate / Avg Win/Loss Ratio)
```
- Only use fractional Kelly (25-50%) to reduce volatility
- Never exceed MAX_POSITION_SIZE_PERCENT regardless of Kelly

## Chain-Specific Adjustments
| Chain | Gas Cost | Position Floor |
|-------|----------|---------------|
| Ethereum | High ($5-50) | Min $100 (otherwise gas eats profits) |
| Base | Low ($0.01) | Min $25 |
| Arbitrum | Low ($0.05) | Min $25 |
| Solana | Tiny ($0.001) | Min $10 |
| BSC | Low ($0.10) | Min $25 |

## Anti-Sizing Rules
- **NEVER** bet more than 2% per position
- **NEVER** average down (don't increase losing position size)
- **NEVER** size up after a loss streak (emotional compensation)
- **ALWAYS** reduce size after circuit breaker (restart at 50% max)
