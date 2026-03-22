# STRATEGIES — How We Turn $5K Into 6–7 Figures

## The Growth Math
```
Starting Capital: $5,000
Target: $100,000+ (20x) within 12 months

Required compound rate: ~26% per month
That's ~0.85% per DAY — very achievable in crypto if you:
  ✅ Trade frequently (5-15 trades/day across 6 chains)
  ✅ Cut losers fast (-8% stop)
  ✅ Let winners run (trail to 5x–10x on moonshots)
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

## Strategy 1: GemSnipe (Primary — `strategies/gem_snipe.py`)

### The Playbook (How It Actually Makes Money)
The edge is **SPEED + SCORING**. We see tokens within minutes of listing, score them instantly, and enter before retail notices. The lifecycle of a gem:

```
Hour 0-1:   Token listed → Bot detects → Score → Safety check → BUY
Hour 1-6:   Word spreads on CT/Telegram → Retail starts buying → Price 2-5x
Hour 6-24:  Peak FOMO → Price 5-20x from our entry → SELL tiers hit
Hour 24-48: Retail exhaustion → Price corrects → We're already out
```

### Why We Win
1. **We're early** — DexScreener profiles appear within minutes of first trade
2. **We're fast** — Express lane executes in seconds
3. **We're disciplined** — Stop-loss cuts losers, takes profits on winners
4. **We never hold bags** — If it doesn't move in 24-48h, we exit

### Signal Weights (Total = 100%)
| Signal | Weight | Why This Weight |
|--------|--------|-----------------|
| **Volume spike** | **17%** | Strongest predictor of imminent price action |
| **Liquidity depth** | **13%** | Can we get in AND out without drowning |
| **Token age** | **12%** | Newer = more upside potential |
| **Contract verified** | 8% | Basic scam filter |
| **Holder distribution** | 8% | Distributed = less dump risk |
| **Buy/sell tax** | 8% | High tax = exit cost |
| **Social signals** | 8% | Buzz precedes pumps |
| **TVL** | 5% | Protocol value backing |
| **Social sentiment** | 5% | LunarCrush momentum |
| **DexScreener boost** | 4% | Community spending = conviction |
| **Smart money** | 4% | Whales know things |
| **Holder concentration** | 4% | Top 10 holders < 50% |
| **Unlock/dilution risk** | 4% | No upcoming dumps |

### Express Lane (Score ≥ 82) — THE MONEY MAKER
- These are the trades that produce 5x–20x returns
- Skip TA — pure momentum play, speed is everything
- Full position size (conviction 1.0x)
- Set wider trailing stop (let it RUN)
- Historical expectation: 30% of express lane trades hit 3x+

### Standard Lane (Score 55–81)
- TA confirmation required (RSI, MACD, BB, Fibonacci)
- Reduced position size (0.5x–0.75x)
- Tighter stops (-8%)
- Bread-and-butter trades — consistent small gains that compound

## Strategy 2: CTO Flip (New — Community Takeover Plays)
Community takeovers on DexScreener are **goldmines**:
- Abandoned token → New community takes over → Rebrands → New hype cycle
- CTOs often pump 5-50x in the first 24-48 hours after claim
- **Entry:** Immediately on CTO detection (Source 4 in scanner)
- **Size:** Full conviction (treat as express lane)
- **Exit:** Tiered — 50% at 3x, 25% at 5x, trail rest
- **Stop:** -15% (CTOs are volatile, need wider stop)

## Strategy 3: Boost Momentum Surfing
When a token gets **heavy boosts** (≥500 total boost amount):
- The DexScreener homepage drives massive retail attention
- Entry: On boost detection when volume is spiking simultaneously
- Size: 75% conviction
- Exit: 50% at 2x, 50% within 6 hours (boost attention fades fast)
- Stop: -10%

## Strategy 4: Smart Money Follow (Planned — Phase 4)
- Mirror buys from tracked whale wallets
- Enter after whale accumulation detected (2+ wallets buying same token)
- Size: 50% conviction (following, not leading)
- Exit: When whales exit (distribution detection)

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
