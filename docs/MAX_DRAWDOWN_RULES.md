# MAX DRAWDOWN RULES — Protecting Against Catastrophic Loss

## What Is Max Drawdown
Max drawdown = the largest peak-to-trough decline in portfolio value. It measures the worst-case scenario.

## Drawdown Thresholds

| Level | Drawdown | Action |
|-------|----------|--------|
| 🟢 Normal | 0–5% | Continue trading normally |
| 🟡 Caution | 5–10% | Reduce position sizes by 50% |
| 🟠 Warning | 10–15% | Stop new trades, monitor existing |
| 🔴 Circuit Breaker | > 15% | **CLOSE ALL POSITIONS** |

## Circuit Breaker Details
- **Env var:** `CIRCUIT_BREAKER_PERCENT=15.0`
- **Measurement:** Current portfolio value vs. peak value (rolling high-water mark)
- **Trigger:** Portfolio drops below `peak × (1 - CIRCUIT_BREAKER_PERCENT / 100)`
- **Action:** Sell all open positions at market
- **Cooldown:** 24 hours minimum before resuming
- **Resume:** Manual approval required — set `MODE=live` again after review

## High-Water Mark
```
peak_value = max(peak_value, current_value)  # Only goes UP
drawdown_pct = (peak_value - current_value) / peak_value * 100
```

## Recovery Protocol
After circuit breaker triggers:
1. Wait 24 hours (mandatory cooldown)
2. Review what caused the drawdown
3. Check if market conditions have stabilized
4. Restart in paper mode for at least 4 hours
5. If paper mode is stable, switch back to live
6. Reduce position sizes by 50% for the first 48 hours after recovery

## Weekly Drawdown Tracking
Log maximum drawdown weekly for trend analysis. If max drawdown is consistently > 10%, the strategy parameters need adjustment.
