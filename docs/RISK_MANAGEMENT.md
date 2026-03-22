# RISK MANAGEMENT — How We Protect Capital

## The Golden Rule
> **You cannot compound gains if you blow up your account.**

Risk management is NOT optional. It runs BEFORE, DURING, and AFTER every trade.

## Pre-Trade Risk Checks (`core/risk.py`)

| Check | Threshold | Action on Fail |
|-------|-----------|---------------|
| Portfolio allocation | > 2% of portfolio | **REDUCE size** |
| Concurrent positions | > 10 open | **WAIT** for exit |
| Daily loss limit | > 0.5 ETH lost today | **STOP trading today** |
| Gas price | > 50 gwei (Ethereum) | **DELAY** execution |
| Circuit breaker | Portfolio down > 15% | **CLOSE ALL positions** |
| Min ETH balance | < 0.05 ETH for gas | **ALERT** and pause |

## Position-Level Risk

### Stop-Loss (Mandatory, Always Set)
| Type | Trigger | Purpose |
|------|---------|---------|
| Standard stop | -10% from entry | Normal loss management |
| Hard stop | -25% from entry | Catastrophic failure safety net |
| Trailing stop | Peak - 8% | Lock in profits on winners |

### Take-Profit (Tiered Exits)
| Level | Trigger | Action |
|-------|---------|--------|
| TP1 | +100% (2x) | Sell 50% — secure initial investment |
| TP2 | +400% (5x) | Sell 25% — bank big profit |
| Moon bag | Remaining 25% | Trail with 15% trailing stop |

## Portfolio-Level Risk

### Circuit Breaker
- **Trigger:** Portfolio value drops 15% from peak
- **Action:** Immediately close ALL open positions
- **Cooldown:** 24 hours before resuming trading
- **Override:** Manual only (requires human intervention)

### Correlation Risk
- Maximum 3 positions on the same chain
- Maximum 2 positions in the same token category (e.g., memecoins)
- **Why:** Chain-wide events (bridge hack, RPC outage) could hit all positions simultaneously

## Dynamic Position Sizing

Based on conviction (gem score):
```
Score 80+ → 100% of MAX_POSITION_SIZE (2% of portfolio)
Score 70-79 → 75% of MAX_POSITION_SIZE (1.5% of portfolio)
Score 55-69 → 50% of MAX_POSITION_SIZE (1% of portfolio)
```

## What This Protects Against
- **Rug pulls** → Safety checks + stop-loss limit damage to ≤2% of portfolio
- **Flash crashes** → Hard stop at -25% prevents wipeout
- **Slow bleeds** → Standard stop at -10% cuts losers fast
- **Portfolio meltdown** → Circuit breaker closes everything at -15%
- **Gas drain** → Max gas prevents overpaying on bad deals
- **Overtrading** → Daily loss limit forces discipline
