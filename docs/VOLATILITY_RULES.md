# VOLATILITY RULES — Riding the Waves, Not Drowning in Them

## Volatility as Opportunity
Volatility is where the money is made. The bot WANTS volatility — but controlled, profitable volatility.

## Volatility Thresholds

### Entry Conditions
| Metric | Threshold | Action |
|--------|-----------|--------|
| 5m price change > +10% | Momentum spike | ✅ Enter (if score qualifies) |
| 1h price change > +50% | Already pumped | ⚠️ Be cautious — may be late |
| 1h price change > +100% | Parabolic | ❌ DO NOT ENTER — chasing |
| 1h price change < -20% | Crashing | ❌ DO NOT ENTER — falling knife |

### Exit Conditions
| Metric | Threshold | Action |
|--------|-----------|--------|
| Price drops 10% from entry | Stop-loss | 🔴 EXIT immediately |
| Price drops 25% from entry | Hard stop | 🔴 FORCE EXIT |
| Price drops 5% from peak (on a winner) | Start trailing | 🟡 Tighten stop |
| Volatility spike (5min candle > 15%) | Instability | ⚠️ Check position health |

## Volume Spike Detection
The bot uses volume ratios to detect breakouts:
```
volume_spike_ratio = volume_1h / (volume_24h / 24)

ratio ≥ 10x → EXPLOSIVE (score 100)
ratio ≥ 5x  → STRONG (score 85)
ratio ≥ 3x  → MODERATE (score 70)
ratio ≥ 2x  → MILD (score 50)
ratio < 2x  → NORMAL (score 20)
```

## Bollinger Band Signals
Used in TA pipeline (`strategies/indicators.py`):
- **Price touches lower band:** Potential reversal entry
- **Price breaks upper band:** Momentum continuation OR exhaustion
- **Bands squeezing:** Low volatility → breakout incoming → be ready
- **Bands expanding:** High volatility → active trend → ride it

## Volatility-Adjusted Position Sizing (Future)
Higher volatility → smaller position sizes to maintain constant risk:
```
adjusted_size = base_size × (target_volatility / current_volatility)
```
- If current vol is 2x target → position is halved
- If current vol is 0.5x target → position is doubled (up to max)
