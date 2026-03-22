# SIGNALS — What Tells Us to Trade

## Signal Categories

### 🔴 Instant Reject Signals (Any = No Trade)
- GoPlus honeypot detection = TRUE
- Honeypot.is simulation FAIL
- Token Sniffer score < 50
- Token on blocklist (`config/tokens.py`)
- Liquidity < $25,000
- Buy/sell tax > 10%
- Ownership not renounced AND can mint

### 🟢 Strong Buy Signals
| Signal | Indicator | Threshold |
|--------|-----------|-----------|
| Volume spike | 1h vol / 24h avg | ≥ 5x |
| Fresh listing | Token age | < 6 hours |
| Smart money buying | Whale wallet overlap | ≥ 2 wallets |
| CTO claim | Community takeover on DexScreener | Present |
| DexScreener boost | Boost amount | ≥ 200 |
| Fibonacci support | Price near fib level | Within 3% |
| RSI oversold bounce | RSI(14) | < 35, turning up |
| MACD bullish cross | MACD line crosses signal | Confirmed |
| OBV rising | On-balance volume trend | Increasing |

### 🟡 Moderate Signals ( Adds to conviction)
| Signal | What It Means |
|--------|--------------|
| Social buzz rising | LunarCrush sentiment up |
| Multiple DEX listings | Token on 3+ DEXs |
| Ad running on DexScreener | Team is spending on marketing |
| Holder count rising | Organic distribution |
| TVL growth | Protocol value increasing |

### 🔵 Technical Confirmation (Standard lane only)
| Indicator | Implementation | File |
|-----------|---------------|------|
| RSI (14) | Relative Strength Index | `strategies/indicators.py` |
| MACD | Moving Average Convergence Divergence | `strategies/indicators.py` |
| Bollinger Bands | Volatility + mean reversion | `strategies/indicators.py` |
| OBV | On-Balance Volume | `strategies/indicators.py` |
| Fibonacci Retracement | 0.236, 0.382, 0.5, 0.618, 0.786 levels | `strategies/fibonacci.py` |
| Signal Score | Composite TA score (0–100) | `strategies/signal_scorer.py` |

## Signal Flow
```
DexScreener data → Gem Score (13 signals)
                      │
                 Score ≥ 82? ──YES──▶ EXPRESS LANE → Safety → Execute
                      │
                     NO (55-81)
                      │
                      ▼
              TA Signals (RSI, MACD, BB, OBV)
                      │
              Fibonacci Alignment Check
                      │
                  Signal Score ≥ 50?
                      │
                YES ──▶ Safety → Execute
                NO  ──▶ Skip (wait for better entry)
```
