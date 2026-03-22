# MODEL EVALUATION — Measuring What Matters

## Core Performance Metrics

### Win Rate
```
Win Rate = Winning Trades / Total Trades × 100
Target: > 55%
Minimum: > 45% (with avg win > 2x avg loss)
```

### Profit Factor
```
Profit Factor = Total Gross Profit / Total Gross Loss
Target: > 2.5
Minimum: > 1.5
Below 1.0 = Losing money
```

### Sharpe Ratio
```
Sharpe = (Average Return - Risk Free Rate) / Standard Deviation of Returns
Target: > 2.0
Minimum: > 1.0 (above 1.0 = acceptable risk-adjusted return)
```

### Sortino Ratio
```
Sortino = (Average Return - Risk Free Rate) / Downside Deviation
Target: > 2.5
Better than Sharpe because it only penalizes downside volatility
```

### Expectancy
```
Expectancy = (Win Rate × Avg Win) - (Loss Rate × Avg Loss)
Must be POSITIVE — otherwise the strategy is net negative
Target: > $5 per trade
```

## Signal Quality Metrics

### Per-Signal ROI
Track return on investment by signal source:
| Signal Source | Win Rate | Avg Return | Grade |
|--------------|----------|------------|-------|
| DexScreener profiles | ? | ? | TBD |
| Latest boosts | ? | ? | TBD |
| Top boosts | ? | ? | TBD |
| Community takeovers | ? | ? | TBD |
| DexScreener ads | ? | ? | TBD |

### Express Lane vs Standard Performance
| Path | Win Rate | Avg Hold Time | Avg Return |
|------|----------|--------------|------------|
| Express (≥82) | ? | ? | ? |
| Standard (55-81) | ? | ? | ? |

## Evaluation Schedule
| Frequency | What to Review |
|-----------|---------------|
| Daily | P/L, win rate, drawdown |
| Weekly | Sharpe ratio, profit factor, signal quality |
| Monthly | Full strategy audit, parameter optimization |
| Quarterly | Major strategy review, consider new strategies |

## When to Adjust Parameters
| Signal | Possible Adjustment |
|--------|-------------------|
| Win rate < 45% for 7 days | Raise MIN_GEM_SCORE by 5 |
| Average hold time > 48h | Tighten stop-loss by 2% |
| Express lane underperforming standard | Raise EXPRESS_LANE_SCORE threshold |
| One chain consistently losing | Remove from ACTIVE_CHAINS |
| Slippage eating > 3% avg | Raise MIN_LIQUIDITY_USD |
| Gas costs > 5% of avg trade | Reduce Ethereum activity |

## Automated Reporting
- **Daily:** P/L summary → Slack `#shamrock-trades`
- **Weekly:** Performance report with all metrics → Slack `#shamrock-alerts`
- **Monthly:** Full audit document → saved to `output/reports/`

## Future: ML Model Training
When sufficient trade data exists (500+ trades):
1. Feed features (13 signal scores) + outcomes (P/L) into classifier
2. Train model to predict win probability
3. Use predicted probability to adjust position sizing
4. Continuously retrain on new data (online learning)
5. A/B test: ML-adjusted weights vs. static weights
