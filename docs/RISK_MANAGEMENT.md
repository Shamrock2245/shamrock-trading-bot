# RISK MANAGEMENT — Aggressive Protection for Aggressive Growth

## The $5K Mindset
> **You have $5,000. Every dollar is precious. Protect it like your life — but deploy it like a weapon.**

Risk management isn't about being conservative. It's about **surviving long enough for compounding to work**. One blown account and you start over from zero.

## The Goal Progression & Compounding
The bot operates in phased financial goals. As it achieves each milestone, it dynamically scales up its position sizing and profit targets. The system leverages realized gains to increase buying power, allowing exponential compounding.

**Phase 1 ($500/day Target):** Focus on consistency and survival. Capital preservation is priority #1. Position scaling is cautious.
**Phase 2 ($1,000/day Target):** Reached when the portfolio clears the first $10k milestone. Win-streak accelerators take effect faster.
**Phase 3 ($5,000/day Target):** Leverages substantial house money. Nuclear wallet sizing increases, allowing massive leverage on high-conviction signals.
**Phase 4 ($10,000+/day Target):** Compound/Whale mode. Full auto-tune scaling and heavy pyramid compounding to maximize ROI on all profitable trades.

## Pre-Trade Risk Checks (`core/risk.py`)

### Phase 1 ($5K–$15K)
| Check | Threshold | Action on Fail |
|-------|-----------|---------------|
| Portfolio allocation | > 5% of portfolio (Conservative) / 60% (Nuclear) | **REDUCE size** |
| Concurrent positions | > 5 (Conservative) / > 3 (Nuclear) | **WAIT** for exit |
| Daily loss limit | > 0.3 ETH lost today | **STOP trading today** |
| Gas price | > 30 gwei (Ethereum) | **SKIP Ethereum** |
| Circuit breaker | Portfolio down > 15% ($750) | **CLOSE ALL** |
| Gas reserves | < 0.03 ETH for gas | **ALERT** and pause |
| Chain exposure | > 3 positions on same chain | **SKIP chain** |
| Market regime | CHOP detected | **SKIP new entries** |
| Global drawdown | Portfolio down > 20% from ATH | **48h trading halt** |

## Position-Level Risk (Profile-Aware)

### Stop-Loss — Dual Profile System
| Type | Conservative | Nuclear | Purpose |
|------|-------------|---------|---------|
| Hard stop | **-20%** | **-10%** | Emergency backstop |
| Trailing stop (initial) | **-15%** | **-30%** | Lock profits on runners |
| Trailing at 10x | -15% | **-18%** | Tighten as gains grow |
| Trailing at 20x | -15% | **-8%** | Maximum protection at peak |

### Take-Profit — Dual Profile Ladders
**Conservative (Primary Wallet):**
| Level | Trigger | Action |
|-------|---------|--------|
| TP1 | **2x** (+100%) | Sell **40%** |
| TP2 | **3x** (+200%) | Sell **40%** of remaining |
| Ride | Remainder | Trail with 15% trailing stop |

**Nuclear (Wallet B):**
| Level | Trigger | Action |
|-------|---------|--------|
| TP1 | **5x** (+400%) | Sell **15%** |
| TP2 | **12x** (+1,100%) | Sell **25%** of remaining |
| TP3 | **30x** (+2,900%) | Sell **20%** of remaining |
| Ride | **40% rides** | Dynamic trailing: 30% → 18% → 8% |

**God Mode override**: Skip TP1 entirely — hold for TP2 (5x minimum).

## Offensive Risk Controls

### Fast Fail (Capital Recycling)
Dead money is the enemy. These guardrails cut underperformers FAST:

| Trigger | Condition | Action |
|---------|-----------|--------|
| **Momentum Death** | Down > 10% after 2h + volume declining | Sell 100% |
| **Stale Momentum** | Up < 15% after 4h | Sell 100% |
| **Volume Collapse** | Volume dropped > 80% from entry | Sell 100% immediately |

### Loss Streak Protection
| Consecutive Losses | Kelly Multiplier | MIN_GEM_SCORE Effect |
|-------------------|-----------------|---------------------|
| 1 | 0.85x | +2 pts |
| 2 | 0.70x | +4 pts |
| 3+ | **0.50x** (Quarter-Kelly) | +6 pts (capped at +10) |

### Win Streak Acceleration
| Consecutive Wins | Kelly Multiplier | Cascade Effect |
|-----------------|-----------------|---------------|
| 2-3 | 1.25x | -1 pt from MIN_GEM_SCORE |
| 4-5 | 1.5x | -2 pts |
| 6+ | **2.0x** (Full Kelly) | -3 pts (capped at -10) |

## ShamrockGuard & Daily Goal Protection

The `ShamrockGuard` oversees portfolio-level targets, acting to secure profits once the bot is near its daily target (e.g. $500/day).

| Trigger | Condition | Action |
|---------|-----------|--------|
| **Bank-It Mode** | Daily PnL >= 90% of Daily Target ($450) | Restricts new entries, scales Kelly multiplier to 0.2x. Focuses entirely on protecting realized profits. |
| **Daily Drawdown Limit** | Daily PnL <= -20% of Portfolio ($200 on $1k) | Soft halts trading for the remainder of the day. Only extreme nuclear gems allowed. |
| **Max Drawdown Limit** | Portfolio drops 30% from ATH | Pauses trading completely until manual override. |

## Portfolio-Level Risk

### Circuit Breaker
- **Trigger:** Portfolio drops 15% from peak ($750 loss at $5K)
- **Action:** Immediately market-sell ALL positions
- **Cooldown:** 24 hours minimum
- **Recovery:** Restart at 50% position sizes for 48h

### Global Drawdown Sleep
- **Trigger:** Portfolio down > 20% from ATH
- **Action:** 48-hour complete trading halt
- **Recovery:** Auto-resumes after 48h at reduced sizing

### Correlation Protection
| Rule | Limit | Why |
|------|-------|-----|
| Max on same chain | 3 positions | Chain outage = all stuck |
| Max same category | 2 memecoins | Sector rotation = all dump |
| Max same DEX | 3 positions | DEX exploit = all at risk |
| Dedup cooldown | 5 min per token | Prevent duplicate buys |

## Regime-Based Risk Adjustments
| Regime | New Entries | Sizing | Trailing Stop | TP Targets |
|--------|------------|--------|---------------|------------|
| **EXPANSION** | Aggressive | × 1.5 | Wider | Full TP ladder |
| **NORMAL** | Standard | × 1.0 | Standard | Standard |
| **CHOP** | **Blocked** | × 0.3 | Tight | Quick flip 1.3x |

## What Risk Management Protects Against
| Threat | Protection | Max Damage |
|--------|-----------|-----------|
| Rug pull | Safety checks + hard stop | ≤5% of portfolio (Conservative) |
| Flash crash | Hard stop at -10% (Nuclear) / -20% (Conservative) | ≤5% / ≤60% |
| Slow bleed | Fast fail at 2h | ≤10% of position |
| Momentum death | Volume collapse detection | Immediate exit |
| Chain failure | Max 3 per chain | ≤15% of portfolio |
| Full meltdown | Circuit breaker at -15% | 15% then STOP |
| Drawdown spiral | Global drawdown sleep at -20% | 48h halt |
| Gas drain | Max gas gwei limit | Skip expensive txns |
| Overtrading | Daily loss limit + loss streak cooling | Auto-restricts |
| Snipers | Moralis sniper detection (Solana) | Hard block at ≥10 |
| Bot crash | Heartbeat monitoring | Alert and restart |
