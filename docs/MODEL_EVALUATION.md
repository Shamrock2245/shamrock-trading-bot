# MODEL EVALUATION — Are We Actually Making Money?

## The Only Metric That Matters
> **Is the portfolio growing?**

Everything else (win rate, Sharpe, profit factor) are diagnostic tools to understand WHY it's growing or not.

## Core Performance Metrics

### Portfolio Growth Rate (THE metric)
```
Daily growth = (Portfolio Today - Portfolio Yesterday) / Portfolio Yesterday
Weekly CAGR = Portfolio growth over 7 days, annualized
Monthly CAGR = Portfolio growth over 30 days

Target daily growth: 0.85% ($5K → $100K pace)
Acceptable daily growth: 0.5% ($5K → $45K pace)
Alarm: negative growth for 5 consecutive days
```

### Win Rate
```
Win Rate = Winning Trades / Total Trades × 100

Target: > 55%
Acceptable: > 45% (if avg win >> avg loss)
Action if <45%: Raise MIN_GEM_SCORE by 5, review signal weights
```

### Win/Loss Ratio
```
W/L Ratio = Average Win Amount / Average Loss Amount

Target: > 3.0x (avg win is 3x avg loss)
Minimum: > 1.5x
Action if <1.5x: Tighten stop-losses by 2%, widen take-profit targets
```

### Profit Factor
```
Profit Factor = Total Gross Profit / Total Gross Loss

Target: > 3.0
Acceptable: > 1.5
Below 1.0 = LOSING MONEY — stop and re-evaluate
```

### Expectancy Per Trade
```
Expectancy = (Win% × Avg Win) - (Loss% × Avg Loss)

Target: > $30 per trade (at $250 position size)
Minimum: > $10 per trade
Negative = STOP TRADING — strategy is net negative
```

### Sharpe Ratio
```
Sharpe = (Avg Return - Risk Free Rate) / Std Dev of Returns

Target: > 2.0
Minimum: > 1.0
Below 0.5 = Risk-adjusted returns are terrible
```

## Signal Quality Tracking

### Per-Signal Hit Rate
Track EVERY signal source and its contribution to winning trades:
| Signal Source | Trades | Wins | Win% | Avg P/L | Grade | Action |
|--------------|--------|------|------|---------|-------|--------|
| DexScreener profiles | — | — | — | — | TBD | — |
| Latest boosts | — | — | — | — | TBD | — |
| Top boosts | — | — | — | — | TBD | — |
| Community takeovers | — | — | — | — | TBD | — |
| DexScreener ads | — | — | — | — | TBD | — |

**Kill any signal source with < 40% win rate after 50+ trades.**
**Double down on signal sources with > 60% win rate.**

### Express Lane vs Standard Performance
| Path | Trades | Wins | Win% | Avg Return | Avg Hold | Grade |
|------|--------|------|------|------------|----------|-------|
| Express (≥80) | — | — | — | — | — | TBD |
| Standard (55-79) | — | — | — | — | — | TBD |

**If express lane win% < standard: Raise EXPRESS_LANE_SCORE threshold**
**If express lane avg return > 3x standard: Consider lowering threshold**

### Chain Performance
| Chain | Trades | Win% | Avg Return | Gas Cost % | Net Profit | Grade |
|-------|--------|------|------------|-----------|------------|-------|
| Solana | — | — | — | — | — | TBD |
| Base | — | — | — | — | — | TBD |
| Arbitrum | — | — | — | — | — | TBD |
| BSC | — | — | — | — | — | TBD |
| Polygon | — | — | — | — | — | TBD |
| Ethereum | — | — | — | — | — | TBD |

**Drop any chain with negative Net Profit after 30+ trades.**

## Evaluation Schedule
| Frequency | What to Review | Who Acts |
|-----------|---------------|----------|
| **Daily** | P/L, portfolio growth, drawdown | Bot (auto-log) |
| **3 days** | Win rate trend, signal quality | Human review |
| **Weekly** | All metrics, chain performance, signal kill/scale | Human adjust params |
| **Monthly** | Phase assessment, parameter optimization | Human major review |

## Automated Alerts
| Condition | Alert |
|-----------|-------|
| Portfolio crosses phase boundary ($15K, $50K, $250K) | 🎉 "PHASE UPGRADE — Review PARAMETERS.md" |
| Daily growth negative for 3 days | ⚠️ "Growth stalling — review signals" |
| Win rate drops below 40% (7-day rolling) | 🔴 "Win rate critical — pause and analyze" |
| Expectancy goes negative (7-day rolling) | 🚨 "STRATEGY IS LOSING MONEY — switch to paper" |
| Single trade hits 10x+ | 🌙 "MOON BAG HIT — journal what worked" |

## Continuous Improvement Loop
```
Trade → Journal → Weekly Review → Identify Pattern → Adjust Parameter → Test in Paper → Deploy
                                                                              ↑
                                                                     Never skip this step
```

## Future: ML Model (Phase 5)
When trade count exceeds 500:
1. Train classifier: features (13 signals) → outcome (profitable or not)
2. Use model confidence to adjust position sizing
3. A/B test: ML weights vs static weights over 2 weeks
4. Adopt winner, retrain monthly
5. Expected improvement: +5-10% win rate from better signal weighting
