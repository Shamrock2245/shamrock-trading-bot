# SIGNALS — What Tells Us to Trade (and What Makes Money)

## Signal Performance (Track and Optimize)
Not all signals are equal. Track win rate per signal and KILL signals that don't produce profit.

### 🔴 Instant Reject Signals (Any = No Trade)
- GoPlus honeypot detection = TRUE
- Honeypot.is simulation FAIL
- Token Sniffer score < 50
- Token on blocklist (`config/tokens.py`)
- Liquidity < $15,000 (Phase 1) / $25,000 (Phase 2+)
- Buy/sell tax > 10%
- Ownership not renounced AND can mint
- Token already pumped > 20x from initial listing (we're too late)

### 🟢 High-Profit Signals (These Make the Money)
| Signal | Indicator | Expected Win Rate | Avg Return |
|--------|-----------|-------------------|------------|
| **Volume explosion** | 1h vol / 24h avg ≥ 7x | ~60% | +80% avg |
| **Fresh listing + boost** | Age < 6h AND boost > 100 | ~55% | +120% avg |
| **CTO claim** | Community takeover on DexScreener | ~50% | +200% avg |
| **Smart money convergence** | 3+ whale wallets buying | ~65% | +60% avg |
| **Fibonacci exact bounce** | Price hits 0.618 fib and reverses | ~60% | +40% avg |

### 🟡 Supporting Signals (Adds Conviction)
| Signal | What It Means | Score Impact |
|--------|--------------|-------------|
| DexScreener boost ≥ 200 | Community spending money | +8 points |
| DexScreener ad running | Funded team marketing | +5 points |
| Social buzz trending | LunarCrush sentiment spike | +6 points |
| Multiple DEX listings | Token on 3+ DEXs | +4 points |
| Holder count rising fast | Organic distribution | +5 points |
| TVL growth | Protocol value increasing | +3 points |
| Contract verified | Transparent team | +4 points |

### 🔵 Technical Confirmation (Standard Lane Only)
| Indicator | Bullish Signal | Implementation |
|-----------|---------------|----------------|
| RSI (14) | < 35, turning up (oversold bounce) | `strategies/indicators.py` |
| MACD | Bullish crossover (MACD > Signal) | `strategies/indicators.py` |
| Bollinger Bands | Price at lower band, squeezing | `strategies/indicators.py` |
| OBV | Volume confirming price move UP | `strategies/indicators.py` |
| Fibonacci | Price at 0.382, 0.5, or 0.618 support | `strategies/fibonacci.py` |

## Signal Combinations That Print Money

### "The Perfect Storm" (Score 90+)
- Fresh listing (< 3 hours) + Volume 10x+ + Smart money buying + Boost > 200
- **Action:** EXPRESS LANE → Full size → Wide trailing stop (let it moon)
- **Expected:** 5x–20x returns in 24 hours

### "The CTO Revival" (Score 75-85)
- Community takeover + Volume spike + Social buzz increasing
- **Action:** FULL SIZE → 3x take-profit target → -15% stop (CTOs are volatile)
- **Expected:** 3x–50x returns in 24-48 hours (wide range, high variance)

### "The Steady Builder" (Score 60-74)
- Good liquidity + Verified contract + Healthy holder distribution + TA confirmation
- **Action:** STANDARD SIZE → Tiered exits → -8% stop
- **Expected:** 1.5x–3x returns in 24-72 hours

### "The Fade" (Score 55-59, borderline)
- Decent base score but missing key confirmations
- **Action:** HALF SIZE → Quick flip target (1.3x) → -5% tight stop
- **Expected:** Small gains or quick stop-out, limited risk

## Signal Flow
```
DexScreener data → Gem Score (13 signals)
                      │
                 Score ≥ 80? ──YES──▶ EXPRESS LANE
                      │                    │
                     NO (55-79)            ▼
                      │              Full position
                      ▼              Wide trailing stop
              TA Signals                Let it ride
              (RSI, MACD, BB, OBV)
                      │
              Fibonacci Check
                      │
                  Signal Score ≥ 45?
                      │
                YES ──▶ Safety → Execute (conviction-scaled)
                NO  ──▶ Skip (insufficient confirmation)
```

## Signal Decay — When to IGNORE Old Data
- DexScreener boost data > 6 hours old → stale, ignore
- Volume spike > 2 hours old → momentum may have faded
- Social sentiment > 12 hours old → refresh required
- CTO claim > 48 hours old → initial pump likely over
