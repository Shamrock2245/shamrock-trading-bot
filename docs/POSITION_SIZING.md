# POSITION SIZING — Bet Smart, Bet to Win

## The $5K Reality
With $5,000 starting capital, micro-positions ($50) don't work — gas fees eat them alive on Ethereum. We need to be CONCENTRATED but SMART.

## Dual-Wallet Sizing Architecture

Two wallets, two profiles, both can fire on the same token:

| Wallet | Profile | Max Position | Kelly Clamp | Max Concurrent | Min Score |
|--------|---------|-------------|-------------|----------------|-----------|
| **Primary** | Conservative | 5% of wallet | 10% | 5 | 65.0 |
| **Wallet B** | Nuclear | **60%** of wallet | **70%** | **3** | **82.0** |

Wallet B is the missile — one massive bet on an S-tier setup during expansion regime.

## Phase-Based Sizing (Conservative Profile)

### Phase 1: Seed ($5K–$15K)
| Setting | Value | Reasoning |
|---------|-------|-----------|
| `MAX_POSITION_SIZE_PERCENT` | **5.0%** | $250 per trade — big enough to matter after fees |
| `MAX_CONCURRENT_POSITIONS` | **5** | Total exposure: 25% max |

**Chain allocation for $5K:**
| Chain | Priority | Why |
|-------|----------|-----|
| **Solana** | 🥇 #1 | Lowest fees ($0.001), fastest execution, massive memecoin flow |
| **Base** | 🥈 #2 | Very low fees ($0.01), growing ecosystem |
| **Avalanche** | 🥉 #3 | Low fees ($0.03), fast C-Chain |
| BSC | 📊 Selective | Only high-conviction plays |
| Ethereum | ⚠️ Avoid | Gas fees ($5-50) eat into $250 positions |

### Phase 2–4 Sizing
| Phase | Max Position % | Max Concurrent | Position Range |
|-------|---------------|----------------|---------------|
| Growth ($15K–$50K) | 3.0% | 8 | $450–$1,500 |
| Acceleration ($50K–$250K) | 2.0% | 10 | $1,000–$5,000 |
| Whale ($250K+) | 1.0% | 15 | $2,500–$5,000 |

## Conviction-Based Scaling

| Gem Score | Conviction | Multiplier | At $5K | At $50K |
|-----------|-----------|------------|--------|---------|
| 90–100 | 🚀 Nuclear Express | 1.0x (Wallet B: 60%) | $250/$3,000 | $1,000/$30,000 |
| 82–89 | 🔥 Nuclear | 1.0x (Wallet B) | $250/$3,000 | $1,000/$30,000 |
| 65–81 | ✅ Conservative | 0.75x | $187 | $750 |
| 45–64 | ⚠️ Standard (TA req) | 0.50x | $125 | $500 |
| < 45 | ❌ No trade | 0x | $0 | $0 |

## Offensive Sizing Multipliers

Applied in order via `calculate_offensive_position_size()`:

| # | Multiplier | Range | Stacks |
|---|-----------|-------|--------|
| 1 | Hot Streak Kelly | 0.5x – 2.0x | ✅ |
| 2 | God Mode Kelly | 1.0x or 2.0x | ✅ |
| 3 | Express Overdrive | 1.5x – 2.0x | ✅ |
| 4 | Profit Boost | 1.25x – 1.75x | ✅ |
| 5 | Momentum Reentry | 1.25x | ✅ |
| 6 | Blitz Mode Synergy | 1.25x (3+ conditions) | ✅ |
| 7 | House Money Bonus | +$USD (additive) | ✅ |

**Absolute cap**: `OFFENSIVE_MAX_POSITION_USD` ($5,000) prevents runaway sizing.

## Pyramid Scaling on Winners (3-Tier System)

| Tier | Trigger | Add Size | New Trailing Stop | Source |
|------|---------|----------|-------------------|--------|
| **T1** | +30% gain | 50% of original | 20% | Offensive guardrails |
| **T2** | +100% gain | 25% of original | 15% | House money pool |
| **T3** | +300% gain | 10% of original | 10% | House money pool |

**Rules:**
- Max **3 scale-ins** per position (one per tier)
- Each add tightens trailing stop to lock gains
- Pyramid adds use house money pool — no new capital at risk
- Never pyramid a loser (only triggered on unrealized gains)

## Market Regime Sizing Multiplier

| Regime | Sizing Effect | Discovery Effect |
|--------|--------------|-----------------|
| **EXPANSION** | × 1.5 (Nuclear profile) | Lower MIN_GEM_SCORE |
| **NORMAL** | × 1.0 | Standard |
| **CHOP** | × 0.3 | Skip new entries |

## Gas-Aware Minimum Positions
```
Rule: Gas must be < 2% of position size
```

| Chain | Typical Gas | Min Position |
|-------|------------|-------------|
| Solana | $0.001 | $10 |
| Base | $0.01–0.05 | $25 |
| Avalanche | $0.03 | $25 |
| BSC | $0.10–0.30 | $25 |
| Arbitrum | $0.05–0.20 | $25 |
| Ethereum | $5–50 | $500 (Phase 2+) |

## Anti-Sizing Rules
- **NEVER** bet more than MAX_POSITION_SIZE_PERCENT per position (per-profile)
- **NEVER** average down on a loser
- **NEVER** increase size after a loss streak (loss cooling auto-handles this)
- **ALWAYS** reduce sizes by 50% after a circuit breaker for 48 hours
- **ALWAYS** compound — reinvest every dollar of profit
