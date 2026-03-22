# BACKTESTING — Validating Strategies Before Risking Capital

## Purpose
Every strategy MUST be backtested before going live. Backtesting proves the strategy works on historical data before risking real money.

## Backtesting Checklist
- [ ] Define the strategy logic in code
- [ ] Collect historical OHLCV data (GeckoTerminal / DexScreener)
- [ ] Run against 30+ days of data per chain
- [ ] Track win rate, average P/L, max drawdown, Sharpe ratio
- [ ] Compare against buy-and-hold ETH/SOL baseline
- [ ] Identify edge decay — does the strategy degrade over time?

## Key Metrics
| Metric | Target | Minimum |
|--------|--------|---------|
| Win rate | > 60% | > 50% |
| Average win / Average loss | > 2.0 | > 1.5 |
| Max drawdown | < 10% | < 15% |
| Sharpe ratio | > 2.0 | > 1.0 |
| Profit factor | > 2.5 | > 1.5 |
| Total trades | 100+ | 50+ |

## Backtesting Rules
1. **No look-ahead bias** — only use data available at the time of the decision
2. **Include fees and slippage** — real trades cost money
3. **Include gas costs** — especially on Ethereum
4. **Test across multiple market regimes** — bull, bear, and choppy
5. **Test across multiple chains** — what works on Base may not work on BSC

## Tools
- Historical OHLCV: GeckoTerminal API, DexScreener pair data
- Analysis: Python (pandas, numpy, matplotlib)
- Framework: Custom backtesting engine in `scripts/` (planned)

## When to Backtest
- Before deploying any new strategy
- After changing signal weights
- After adding/removing a signal source
- Every 30 days as a sanity check
