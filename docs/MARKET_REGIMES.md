# MARKET REGIMES — Adapting to Market Conditions

## Regime Detection
The bot should adapt its behavior based on the current market regime. Not all markets are equal — what works in a bull market kills you in a bear.

## Regime Types & Bot Behavior

### 🟢 BULL / Risk-On
**Indicators:** BTC > 20-day MA, ETH > 20-day MA, DexScreener boost count high
- **Scanner:** Aggressive — lower `MIN_GEM_SCORE` to 50
- **Position size:** Full allocation (1.0x multiplier on all tiers)
- **Take profits:** Widen — let winners run longer (trail 20%)
- **Stop-loss:** Standard -10%
- **Scan frequency:** Every 15 seconds
- **Max positions:** 10

### 🟡 NEUTRAL / Choppy
**Indicators:** BTC ranging, low volume across DexScreener
- **Scanner:** Standard — keep `MIN_GEM_SCORE` at 55
- **Position size:** Moderate (0.75x multiplier)
- **Take profits:** Standard tiered exits
- **Stop-loss:** Tighter -8%
- **Scan frequency:** Every 30 seconds
- **Max positions:** 7

### 🔴 BEAR / Risk-Off
**Indicators:** BTC < 20-day MA and falling, high fear index
- **Scanner:** Conservative — raise `MIN_GEM_SCORE` to 70
- **Position size:** Small (0.5x multiplier)
- **Take profits:** Aggressive — take quick profits, don't hold
- **Stop-loss:** Very tight -5%
- **Scan frequency:** Every 60 seconds
- **Max positions:** 3

### ⚫ CRASH / Emergency
**Indicators:** BTC drops > 10% in 24h, multiple tokens dumping
- **Scanner:** DISABLED — no new trades
- **Existing positions:** Circuit breaker triggers, close ALL
- **Action:** Wait for recovery signal (24h cooldown minimum)

## Future Implementation
Market regime detection is planned for Phase 4. Currently the bot operates in NEUTRAL mode by default. Regime-adaptive behavior will be implemented in `core/market_regime.py`.
