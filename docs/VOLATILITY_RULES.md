# VOLATILITY RULES — Ride the Waves, Don't Drown

## Volatility = OPPORTUNITY
At $5K, we WANT volatile tokens. A token that moves ±1% daily won't make us rich. A token that moves ±50% daily is where $250 turns into $2,500.

**Our edge: We have stop-losses. Retail doesn't.**

## Entry Volatility Filters

### 🟢 ENTER — High Probability Setups
| Pattern | Indicator | Action |
|---------|-----------|--------|
| Fresh breakout | 5m price +5-15% with volume spike | ✅ Express lane if score qualifies |
| Momentum continuation | 1h price +10-30%, volume sustained | ✅ Enter on pullback to support |
| Fibonacci bounce | Price hits 0.618 fib with RSI < 40 | ✅ Standard lane entry |
| CTO pump initiation | CTO claimed + first volume spike | ✅ Full conviction enter |

### 🟡 CAUTION — Enter with Reduced Size
| Pattern | Indicator | Action |
|---------|-----------|--------|
| Extended run | 1h price +30-50% | ⚠️ Half position, tight stop |
| High volatility chop | 5m candles swinging 5%+ repeatedly | ⚠️ Wait for directional clarity |

### 🔴 DO NOT ENTER — Missed or Dangerous
| Pattern | Indicator | Action |
|---------|-----------|--------|
| Already parabolic | 1h price +100%+ | ❌ You're too late — chasing |
| Free fall | 1h price -20%+ | ❌ Falling knife — wait for floor |
| Dead token | 24h volume < $5K | ❌ No one's buying — neither should you |
| Extreme whipsaw | 50%+ swings in both directions in 1h | ❌ Untradeable chaos |

## Volume Spike Detection (THE Best Entry Signal)
```
volume_ratio = volume_1h / (volume_24h / 24)

ratio ≥ 10x → 🔥 EXPLOSIVE — score 100, express lane candidate
ratio ≥ 7x  → 🟢 STRONG — score 90, high priority
ratio ≥ 5x  → 🟢 GOOD — score 80, standard entry
ratio ≥ 3x  → 🟡 MODERATE — score 65, needs TA confirmation
ratio ≥ 2x  → ⚪ MILD — score 40, likely not enough momentum
ratio < 2x  → ⚫ FLAT — score 15, skip unless other signals strong
```

## Exit Volatility Rules

### Trailing Stop Behavior
| Position P/L | Trailing Distance | Rationale |
|-------------|-------------------|-----------|
| +5% to +50% | 12% from peak | Give early runners room to breathe |
| +50% to +200% | 10% from peak | Tighter trail, locking serious gains |
| +200% to +500% | 8% from peak | Protect big winners |
| +500%+ | 15% from peak (WIDEN) | Moon bag territory — let it RUN |

### Volatility Spike on Open Position
| Event | Action |
|-------|--------|
| Position suddenly drops 5% in 5 minutes | Check: Is it market-wide? If yes → hold. If token-specific → tighten stop |
| Position suddenly pumps 20% in 5 minutes | Move stop to break-even + 10%, let it run |
| Volume drops to near zero on held token | Time stop approaching — prepare to exit at market |

## Bollinger Band Signals (TA Pipeline)
| Signal | Meaning | Trade Action |
|--------|---------|-------------|
| Price below lower band + turning up | Oversold reversal | BUY signal (standard lane) |
| Price above upper band + volume rising | Momentum breakout | HOLD / ADD (if pyramiding) |
| Price above upper band + volume fading | Exhaustion | Tighten trailing stop, prepare exit |
| Bands squeezing tight (< 2% width) | Breakout incoming | Alert — prepare for express entry |
| Bands expanding rapidly | Trend accelerating | Ride it with trailing stop |

## Volatility-Adjusted Sizing (Future Enhancement)
When implemented, high-volatility tokens get smaller positions to maintain constant dollar-risk:
```
adjusted_size = base_size × (target_volatility / actual_volatility)

Example:
  Base size: $250
  Target volatility: 10% daily
  Actual volatility: 30% daily
  Adjusted size: $250 × (10/30) = $83

This keeps dollar-at-risk constant regardless of volatility.
```
**Not yet implemented — currently using fixed sizes per conviction level.**
