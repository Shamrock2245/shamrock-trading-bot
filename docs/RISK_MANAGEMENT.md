# RISK MANAGEMENT — Aggressive Protection for Aggressive Growth

## The $5K Mindset
> **You have $5,000. Every dollar is precious. Protect it like your life — but deploy it like a weapon.**

Risk management isn't about being conservative. It's about **surviving long enough for compounding to work**. One blown account and you start over from zero.

## Pre-Trade Risk Checks (`core/risk.py`)

### Phase 1 ($5K–$15K)
| Check | Threshold | Action on Fail |
|-------|-----------|---------------|
| Portfolio allocation | > 5% of portfolio ($250) | **REDUCE size** |
| Concurrent positions | > 5 open | **WAIT** for exit |
| Daily loss limit | > 0.3 ETH lost today | **STOP trading today** |
| Gas price | > 30 gwei (Ethereum) | **SKIP Ethereum** |
| Circuit breaker | Portfolio down > 15% ($750) | **CLOSE ALL** |
| Gas reserves | < 0.03 ETH for gas | **ALERT** and pause |
| Chain exposure | > 3 positions on same chain | **SKIP chain** |

### Phase 2+ (Loosened as Portfolio Grows)
| Check | Phase 2 | Phase 3 | Phase 4 |
|-------|---------|---------|---------|
| Max position % | 3% | 2% | 1% |
| Max positions | 8 | 10 | 15 |
| Daily loss limit | 0.75 ETH | 1.5 ETH | 3.0 ETH |
| Max gas gwei | 40 | 50 | 50 |
| Circuit breaker | 15% | 15% | 12% |

## Position-Level Risk

### Stop-Loss (Tighter in Phase 1)
| Type | Phase 1 | Phase 2+ | Purpose |
|------|---------|----------|---------|
| Standard stop | **-8%** | -10% | Cut losers fast |
| Hard stop | **-20%** | -25% | Emergency backstop |
| Trailing stop | Peak **-12%** | Peak -10% | Lock in profits on runners |

### Take-Profit (Tiered — Maximize Winners)
| Level | Trigger | Action | Why |
|-------|---------|--------|-----|
| TP1 | +100% (2x) | Sell 50% | **Recover initial investment** — house money from here |
| TP2 | +400% (5x) | Sell 25% | **Bank life-changing profit** |
| Moon bag | Remaining 25% | Trail with 12% trailing stop | **Let it ride** — this is where 20x–100x happens |

### The "Moon Bag" Philosophy
After TP1 and TP2, the remaining 25% is FREE MONEY (you already recovered your investment + profit). Let it ride with a wide trailing stop. These moon bags are what turn $5K into $100K:
```
Position: $250 entry
At 2x ($500): Sell $250 → Break even on the trade
At 5x ($1,250): Sell $312 → $312 pure profit banked
Remaining: $312 worth of tokens trailing at 12%
If token hits 50x: That $312 moon bag = $6,250
If token hits 100x: $312 → $12,500 from one trade
```

## Portfolio-Level Risk

### Circuit Breaker
- **Trigger:** Portfolio drops 15% from peak ($750 loss at $5K)
- **Action:** Immediately market-sell ALL positions
- **Cooldown:** 24 hours minimum
- **Recovery:** Restart at 50% position sizes for 48h
- **Don't override this.** The circuit breaker exists because humans make bad decisions when stressed.

### Correlation Protection
| Rule | Limit | Why |
|------|-------|-----|
| Max on same chain | 3 positions | Chain outage = all stuck |
| Max same category | 2 memecoins | Sector rotation = all dump |
| Max same DEX | 3 positions | DEX exploit = all at risk |

## The Risk Math: Why -8% Stop-Loss is Optimal

```
Win rate: 55%   Avg win: +40%   Avg loss: -8%

Expected value per $250 trade:
  0.55 × $100 (win) - 0.45 × $20 (loss) = $55 - $9 = +$46

Per 10 trades: +$460 net profit
Per 100 trades: +$4,600 net profit (92% return on starting capital)

With 8% stops: Need 5 consecutive losses to drop 2.8% portfolio
With 10% stops: Need 5 consecutive losses to drop 3.5% portfolio  
With 15% stops: Need 5 consecutive losses to drop 5.3% portfolio → TOO MUCH
```

## What Risk Management Protects Against
| Threat | Protection | Max Damage |
|--------|-----------|-----------|
| Rug pull | Safety checks + stop-loss | ≤5% of portfolio |
| Flash crash | Hard stop at -20% | ≤5% of portfolio |
| Slow bleed | Standard stop at -8% | ≤5% of portfolio |
| Chain failure | Max 3 per chain | ≤15% of portfolio |
| Full meltdown | Circuit breaker at -15% | 15% then STOP |
| Gas drain | Max gas gwei limit | Skip expensive txns |
| Overtrading | Daily loss limit | Stop for the day |
| Bot crash | Heartbeat monitoring | Alert and restart |
