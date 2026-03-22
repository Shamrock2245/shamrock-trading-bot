# POSITION SIZING — Bet Smart, Bet to Win

## The $5K Reality
With $5,000 starting capital, micro-positions ($50) don't work — gas fees eat them alive on Ethereum. We need to be CONCENTRATED but SMART.

## Phase-Based Sizing

### Phase 1: Seed ($5K–$15K)
| Setting | Value | Reasoning |
|---------|-------|-----------|
| `MAX_POSITION_SIZE_PERCENT` | **5.0%** | $250 per trade — big enough to matter after fees |
| `MAX_CONCURRENT_POSITIONS` | **5** | Total exposure: 25% max |
| `CONVICTION_HIGH_MULTIPLIER` | 1.0 | Full $250 on high-conviction |
| `CONVICTION_MID_MULTIPLIER` | 0.75 | $187 on mid-conviction |
| `CONVICTION_LOW_MULTIPLIER` | 0.50 | $125 on low-conviction |

**Chain allocation for $5K:**
| Chain | Priority | Why |
|-------|----------|-----|
| **Solana** | 🥇 #1 | Lowest fees ($0.001), fastest execution, massive memecoin flow |
| **Base** | 🥈 #2 | Very low fees ($0.01), growing ecosystem |
| **Arbitrum** | 🥉 #3 | Low fees, solid DeFi |
| Ethereum | ⚠️ Avoid | Gas fees ($5-50) eat into $250 positions |
| BSC | 📊 Selective | Only high-conviction plays |

### Phase 2: Growth ($15K–$50K)
| Setting | Value |
|---------|-------|
| `MAX_POSITION_SIZE_PERCENT` | **3.0%** |
| `MAX_CONCURRENT_POSITIONS` | **8** |
| Effective position size | $450–$1,500 |
| Total max exposure | 24% |

### Phase 3: Acceleration ($50K–$250K)
| Setting | Value |
|---------|-------|
| `MAX_POSITION_SIZE_PERCENT` | **2.0%** |
| `MAX_CONCURRENT_POSITIONS` | **10** |
| Effective position size | $1,000–$5,000 |
| Total max exposure | 20% |

### Phase 4: Whale ($250K+)
| Setting | Value |
|---------|-------|
| `MAX_POSITION_SIZE_PERCENT` | **1.0%** |
| `MAX_CONCURRENT_POSITIONS` | **15** |
| Effective position size | $2,500–$5,000 |
| Total max exposure | 15% |

## Conviction-Based Scaling

| Gem Score | Conviction | Multiplier | At $5K | At $50K |
|-----------|-----------|------------|--------|---------|
| 82–100 | 🔥 Express | 1.0x | $250 | $1,000 |
| 70–81 | ✅ High | 0.75x | $187 | $750 |
| 55–69 | ⚠️ Moderate | 0.50x | $125 | $500 |
| < 55 | ❌ No trade | 0x | $0 | $0 |

## Gas-Aware Minimum Positions
Gas fees determine if a trade is even WORTH making:
```
Rule: Gas must be < 2% of position size
Otherwise the trade is not profitable enough to take
```

| Chain | Typical Gas | Min Position Size |
|-------|------------|------------------|
| Solana | $0.001 | $10 (no floor issues) |
| Base | $0.01–0.05 | $25 |
| Arbitrum | $0.05–0.20 | $25 |
| Polygon | $0.01–0.10 | $25 |
| BSC | $0.10–0.30 | $25 |
| Ethereum | $5–50 | $500 (ONLY for high-conviction in Phase 2+) |

## Position Scaling on Winners (Pyramiding)
When a position is already UP and showing strength:
- At +50% unrealized: MAY add 50% more (pyramid)
- Move stop-loss to break-even on total position
- Only pyramid ONCE per position
- Never pyramid a loser

## The Math: Why 5% Position Size at $5K
```
$5,000 portfolio, 5% position = $250 per trade
Win rate: 55%, Average win: +40%, Average loss: -8%

Per 100 trades:
  55 wins × $250 × 0.40 = $5,500 profit
  45 losses × $250 × 0.08 = $900 loss
  Net: +$4,600 per 100 trades (92% return)

At 5-10 trades/day = 100 trades in ~15 days
→ Nearly doubling every 2 weeks in ideal conditions
```

## Anti-Sizing Rules
- **NEVER** bet more than MAX_POSITION_SIZE_PERCENT per position
- **NEVER** average down on a loser
- **NEVER** increase size after a loss streak (tilt protection)
- **ALWAYS** reduce sizes by 50% after a circuit breaker for 48 hours
- **ALWAYS** compound — reinvest every dollar of profit
