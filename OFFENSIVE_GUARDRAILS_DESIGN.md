# Shamrock Trading Bot: Robust Offensive Guardrails Design

## Goal
Accelerate portfolio growth toward a seven-figure goal by maximizing exposure to winning trades, aggressively compounding profits, and ruthlessly cutting dead money.

## Current State (Antigravity's Implementation)
- **Winner Scaling**: Adds to positions up >30% (max 1 add).
- **Smart DCA**: Buys dips (15% down) on high-conviction picks.
- **Profit Reinvestment**: Boosts position size by 25% for the next 3 trades after a 50% win.
- **Volume Surge Exit**: Sells 25% on a 10x volume spike (blowoff top protection).
- **Underperformer Rotation**: Closes flat positions (±5%) after 12 hours.

## New Robust Enhancements

### 1. Aggressive Profit Compounding (The "House Money" Protocol)
Instead of just a flat 25% boost for 3 trades, we implement a dynamic streak multiplier.
- **Hot Streak Multiplier**: If the last 3 closed trades were profitable, increase base Kelly fraction from 0.5 (Half-Kelly) to 0.75 (Three-Quarter Kelly) or 1.0 (Full Kelly).
- **House Money Sizing**: If the daily realized PnL is > $500, allocate 50% of those "house money" profits directly into the next high-conviction trade, bypassing standard phase limits.

### 2. Ruthless Capital Rotation (The "Up or Out" Rule)
The current 12-hour flat rotation is too slow for micro-caps.
- **Fast Fail**: If a token is down >10% after 2 hours and volume is dropping, cut it immediately. Don't wait for the 25% hard stop.
- **Momentum Requirement**: If a token hasn't moved +15% within 4 hours of a "Gem Snipe", cut it. Micro-caps should pump immediately; if they don't, the momentum is dead.

### 3. Hyper-Scaling Winners (The "Pyramid" Strategy)
The current winner scaling only adds once at +30%. We need to pyramid into massive runners.
- **Tiered Pyramiding**:
  - +30%: Add 50% of original position size.
  - +100% (after TP1 locks in initial capital): Add 25% of original size using the locked-in capital (pure house money ride).
  - +300%: Add 10% of original size.
- **Trailing Stop Tightening**: As we pyramid, the trailing stop tightens from 20% to 15% to 10% to protect the massive unrealized gains.

### 4. Express Lane Overdrive
Currently, Express Lane (score ≥82) just skips TA. We need to hit these harder.
- **Express Sizing**: Express Lane tokens automatically get a 1.5x multiplier on their Kelly position size.
- **Express Slippage**: Increase slippage tolerance to 300bps (3%) for Express Lane to ensure we don't miss the entry on a fast-moving candle.

### 5. The "God Mode" Circuit Breaker
If the portfolio is up >20% in a single day, activate "God Mode".
- **God Mode**: All new trades use Full Kelly sizing. Stop-losses are tightened to 15% (from 25%) to protect the daily gain, but winners are allowed to run with no TP1 (skip the 2x sell, hold everything for 5x).

## Implementation Plan
1. **`config/settings.py`**: Add the new aggressive thresholds and toggles.
2. **`core/wallet_router.py`**: Update `calculate_kelly_position_pct` to accept a `streak_multiplier` and `house_money_bonus`.
3. **`core/position_monitor.py`**: Overhaul `evaluate_underperformer_exit` for Fast Fail, and `check_winner_scaling` for Tiered Pyramiding.
4. **`main.py`**: Implement the Hot Streak tracker, Daily PnL tracker, and God Mode toggle in the main loop.
