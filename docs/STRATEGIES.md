# STRATEGIES — How We Turn $5K Into 6–7 Figures

## The Growth Math
```
Starting Capital: $5,000
Target: $100,000+ (20x) within 12 months

Required compound rate: ~26% per month
That's ~0.85% per DAY — very achievable in crypto if you:
  ✅ Trade frequently (5-15 trades/day across 7 chains)
  ✅ Cut losers fast (-10% nuclear / -20% conservative hard stop)
  ✅ Let winners run (5x/12x/30x TP ladder on nuclear)
  ✅ Add to winners (3-tier pyramid scaling with house money)
  ✅ Compound gains (never withdraw, reinvest everything)
```

## Growth Phases — Adapt as Portfolio Grows

### Phase 1: Seed ($5K–$15K) — "Scrappy Mode"
- **Position size:** 3–5% per trade ($150–$750)
- **Max positions:** 5 concurrent (concentrated bets)
- **Strategy:** High-frequency GemSnipe, prioritize express lane plays
- **Risk:** Slightly higher per-trade risk (3-5%) because $5K can't afford micro-positions
- **Goal:** Compound to $15K in 60 days
- **Key:** Volume of trades matters — you need MANY bets with positive expectancy

### Phase 2: Growth ($15K–$50K) — "Scaling Mode"
- **Position size:** 2–3% per trade ($300–$1,500)
- **Max positions:** 8 concurrent
- **Strategy:** GemSnipe + Momentum continuation trades
- **Risk:** Standard 2% per-trade maximum
- **Goal:** Compound to $50K in 90 days
- **Key:** Start being more selective, raise MIN_GEM_SCORE to 60

### Phase 3: Acceleration ($50K–$250K) — "Alpha Mode"
- **Position size:** 1–2% per trade ($500–$5,000)
- **Max positions:** 10 concurrent
- **Strategy:** Full suite — GemSnipe, Smart Money Follow, Momentum
- **Risk:** Conservative 1-2%, protect the bag
- **Goal:** Cross 6 figures, then push toward $250K
- **Key:** Larger positions = better fills, less slippage impact

### Phase 4: Compounding ($250K+) — "Whale Mode"
- **Position size:** 0.5–1% per trade ($1,250–$2,500)
- **Max positions:** 15 concurrent
- **Strategy:** Diversified — spread across more chains and categories
- **Risk:** Very conservative per-trade, wealth preservation + growth
- **Key:** You're now large enough that your trades move small pools — be careful

---

## Dual-Wallet Strategy Profiles

Both wallets can fire on the **same 85+ token simultaneously** — Primary takes a small conservative position, Wallet B takes a massive nuclear position.

### Primary Wallet — Conservative Profile (`config/wallets.py`)

| Parameter | Value |
|-----------|-------|
| Min gem score | 65.0 |
| Express lane | ≥ 82.0 |
| Max position | **5%** of wallet |
| Kelly clamp | 10% |
| Max concurrent | 5 |
| TP1 | 2x — sell 40% |
| TP2 | 3x — sell 40% of remaining |
| TP3 | Disabled |
| Hard stop | 20% |
| Trailing stop | 15% (fixed after TP1) |
| Slippage | 5% |

### Wallet B — Nuclear Profile (`config/wallets.py`)

| Parameter | Value |
|-----------|-------|
| Min gem score | **82.0** |
| Express lane | **≥ 90.0** |
| Max position | **60%** of wallet |
| Kelly clamp | **70%** |
| Max concurrent | **3** |
| TP1 | **5x — sell 15%** |
| TP2 | **12x — sell 25%** of remaining |
| TP3 | **30x — sell 20%** of remaining |
| Ride | **40% rides** with dynamic trailing stop |
| Hard stop | **10%** |
| Trailing stop | 30% → tightens to **18% at 10x** → then **8% at 20x** |
| Slippage | **8%** (wider for meme launches) |

**Wallet B is the missile.** 60-70% of its capital on a single S-tier setup during expansion.

---

## Strategy 1: GemSnipe (Primary — `strategies/gem_snipe.py`)

### The Playbook (How It Actually Makes Money)
```
Hour 0-1:   Token listed → Bot detects → Score → Safety check → BUY
Hour 1-6:   Word spreads on CT/Telegram → Retail starts buying → Price 2-5x
Hour 6-24:  Peak FOMO → Price 5-20x from our entry → SELL tiers hit
Hour 24-48: Retail exhaustion → Price corrects → We're already out
```

### Why We Win
1. **We're early** — 9 discovery sources catch tokens within minutes
2. **We're enriched** — Moralis + Binance Pulse data no one else has
3. **We're fast** — Express lane executes in seconds
4. **We're disciplined** — Stop-loss cuts losers, takes profits on winners
5. **We never hold bags** — If it doesn't move in 12-48h, we exit

### Express Lane (Score ≥ 82 Conservative / ≥ 90 Nuclear)
- Skip TA — pure momentum play, speed is everything
- Full position size (conviction 1.0x)
- Set wider trailing stop (let it RUN)
- God Signal (≥ 85): 1.5x gas bribe for next-block inclusion

### Standard Lane (Score 45–81)
- TA confirmation required (29-indicator engine)
- Fibonacci alignment on entry
- Reduced position size (0.5x–0.75x)
- Tighter stops

---

## Pyramid Scaling — Adding to Winners with House Money

After TP1 is hit, the bot adds to winning positions at three tiers using **realized profits only**:

| Tier | Trigger | Add Size | New Trailing Stop |
|------|---------|----------|-------------------|
| **Tier 1** | +30% gain | 50% of original position | 20% |
| **Tier 2** | +100% gain | 25% of original position | 15% |
| **Tier 3** | +300% gain | 10% of original position | 10% |

**Rules:**
- Pyramid adds are funded from the **house money pool** — no new capital at risk
- Each add **tightens** the trailing stop to lock in more of the gain
- Max **3 scale-ins** per position (one per tier)
- Entry volume is captured at open for Fast Fail guardrail comparison

---

## Offensive Guardrails (`core/offensive_guardrails.py`)

All 12 guardrails are individually toggleable via environment variables. State persists in `output/offensive_state.json`.

| # | Guardrail | Env Toggle | Trigger | Effect |
|---|-----------|-----------|---------|--------|
| 1 | **Hot Streak Tracker** | `HOT_STREAK_ENABLED` | Win/loss streak tracking | Kelly multiplier: 2W=1.25x, 4W=1.5x, 6W=2.0x (Full Kelly). Losses: 1L=0.85x, 2L=0.70x, 3L+=0.50x |
| 2 | **God Mode** | `GOD_MODE_ENABLED` | Daily PnL > threshold ($200) | Full Kelly sizing (2.0x), skip TP1 (hold for 5x), tighter trailing stops. Deactivates on $200 drawdown from peak |
| 3 | **House Money Protocol** | `HOUSE_MONEY_ENABLED` | Wins contribute % of profit to pool | Additive USD bonus on next high-conviction trade. Pool capped. Funds pyramid adds |
| 4 | **Tiered Pyramiding** | `PYRAMID_SCALING_ENABLED` | Position at +30%/+100%/+300% gain | Add 50%/25%/10% of original size. Trailing stop tightens per tier (20%→15%→10%) |
| 5 | **Fast Fail** | `FAST_FAIL_ENABLED` | Three triggers: | A) Momentum death (down >10% after 2h + vol declining) → sell all |
|   |   |   |   | B) Stale momentum (< +15% after 4h) → sell all |
|   |   |   |   | C) Volume collapse (vol drops 80% from entry) → immediate sell |
| 6 | **Express Lane Overdrive** | `EXPRESS_OVERDRIVE_ENABLED` | Score ≥ EXPRESS_LANE_SCORE | 1.5x–2.0x position sizing + extra slippage (+100bps) to guarantee entry |
| 7 | **Momentum Reentry** | `MOMENTUM_REENTRY_ENABLED` | After TP1 hit, volume still ≥ 3x avg | Re-enters same token at 1.25x size within 60min window |
| 8 | **Profit Boost** | `PROFIT_BOOST_ENABLED` | Win ≥ $50 | Next N trades at boost multiplier. Large wins (≥$500) → 1.75x for 5 trades |
| 9 | **Cascade Score Boost** | `CASCADE_BOOST_ENABLED` | Each win | MIN_GEM_SCORE reduced by 0.5 per win (max -10pts, floor 40). Each loss recovers +1pt |
| 10 | **Loss Streak Cooling** | `LOSS_STREAK_COOLING_ENABLED` | Consecutive losses | +2pts to MIN_GEM_SCORE per loss (max +10pts). Forces pickier discovery |
| 11 | **Blitz Mode** | `BLITZ_MODE_ENABLED` | ≥ 3 offensive conditions active simultaneously | 1.25x synergy multiplier stacks on top of other bonuses |
| 12 | **MEV Gas Bribe** | `GAS_BRIBE_PREMIUM_PCT` | Gem score ≥ 85 (God Signal) | Gas price multiplied by (1 + premium%) for next-block inclusion |

**Absolute position cap**: `OFFENSIVE_MAX_POSITION_USD` ($5,000 default) prevents runaway sizing even on a 6-win streak in God Mode.

---

## Strategy 2: CTO Flip (Community Takeover Plays)
- CTOs often pump 5-50x in the first 24-48 hours after claim
- **Entry:** Immediately on CTO detection (Source 4 in scanner, +8 score bonus)
- **Size:** Full conviction (treat as express lane if score ≥ 75)
- **Exit:** Tiered — 50% at 3x, 25% at 5x, trail rest
- **Stop:** -15% (CTOs are volatile, need wider stop)

## Strategy 3: Boost Momentum Surfing
- Entry: On boost detection when volume is spiking simultaneously (≥ 500 boost amount)
- Size: 75% conviction
- Exit: 50% at 2x, 50% within 6 hours (boost attention fades fast)
- Stop: -10%

## Strategy 4: Whale Accumulation Follow
- Monitor `netExperiencedBuyers` via Moralis Discovery API
- Entry: When experienced buyer count is rising AND holder count growing
- Size: Full conviction with +20% score bonus
- Exit: Standard TP ladder per profile
- **Key Advantage:** Institutional accumulation is the strongest signal

## Anti-Strategies (NEVER Do These)
- ❌ **Revenge trade** — lost on a token? NEVER re-enter immediately
- ❌ **FOMO chase** — if it already pumped 10x from listing, you MISSED IT
- ❌ **Average down** — NEVER add to a losing position
- ❌ **Ignore stops** — stop-loss hit = EXIT. No exceptions.
- ❌ **Overtrade** — max 3 entries per scan cycle (prevents desperation)
- ❌ **Trade the narrative** — we trade NUMBERS not stories
- ❌ **Hold through a dump** — cut losses, find the next gem
- ❌ **Withdraw profits early** — COMPOUND. Every dollar withdrawn is a dollar not growing.

## The Compound Effect (Why Discipline = Wealth)
```
Month 1:  $5,000 × 1.26 = $6,300
Month 2:  $6,300 × 1.26 = $7,938
Month 3:  $7,938 × 1.26 = $10,002    ← doubled in 3 months
Month 4:  $10,002 × 1.26 = $12,603
Month 5:  $12,603 × 1.26 = $15,879
Month 6:  $15,879 × 1.26 = $20,008   ← 4x in 6 months
Month 7:  $20,008 × 1.26 = $25,210
Month 8:  $25,210 × 1.26 = $31,764
Month 9:  $31,764 × 1.26 = $40,023   ← 8x in 9 months
Month 10: $40,023 × 1.26 = $50,429
Month 11: $50,429 × 1.26 = $63,540
Month 12: $63,540 × 1.26 = $80,061   ← 16x in 12 months

Even 20% monthly gets you to $45K. One big month pushes to 6 figures.
A single 50x gem trade at the right time = instant $100K+
```
