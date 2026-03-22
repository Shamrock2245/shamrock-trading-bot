# MARKET REGIMES — Adapt or Die

## Why Regime Detection Matters for $5K→$100K
The bot MUST adapt to market conditions. Running the same parameters in a bear market as a bull market is how accounts get blown up.

## Regime Types & Bot Behavior

### 🟢 BULL / Risk-On (This Is Where We Get Rich)
**Indicators:** BTC trending up, DexScreener new listings exploding, overall crypto market cap rising
- **Scanner:** AGGRESSIVE — lower `MIN_GEM_SCORE` to 48
- **Position size:** Full allocation (1.0x multiplier on all tiers)
- **Take profits:** WIDER — let winners run to 10x+ before trailing
- **Trailing stop:** 15% from peak (give runners room)
- **Stop-loss:** Standard -8%
- **Scan frequency:** Every 10 seconds (maximum aggression)
- **Max positions:** +2 above phase default (7 in Phase 1)
- **Priority:** Get as many bets on the table as possible — rising tide lifts all boats
- **Expected daily return:** 1-3%

### 🟡 NEUTRAL / Choppy (Bread and Butter)
**Indicators:** BTC ranging, moderate DexScreener activity
- **Scanner:** Standard — keep `MIN_GEM_SCORE` at phase default
- **Position size:** Standard allocation
- **Take profits:** Standard tiered exits
- **Stop-loss:** Standard -8%
- **Scan frequency:** Every 15 seconds
- **Max positions:** Phase default
- **Priority:** Selective picks, rely on TA confirmation
- **Expected daily return:** 0.3-1%

### 🔴 BEAR / Risk-Off (Survival Mode)
**Indicators:** BTC falling, low DexScreener volumes, high fear index
- **Scanner:** CONSERVATIVE — raise `MIN_GEM_SCORE` to 70
- **Position size:** 50% of phase allocation
- **Take profits:** TIGHT — take quick 30-50% gains, don't hold
- **Trailing stop:** 5% from peak (lock profits fast)
- **Stop-loss:** Tighter -5%
- **Scan frequency:** Every 30 seconds (less noise)
- **Max positions:** Half of phase default (2-3 in Phase 1)
- **Priority:** Capital preservation. SURVIVE to trade the next bull.
- **Expected daily return:** -0.5% to +0.3%

### ⚫ CRASH / Emergency (Duck and Cover)
**Indicators:** BTC drops > 10% in 24h, exchange outages, regulatory news
- **Scanner:** DISABLED — no new trades
- **Existing positions:** Circuit breaker triggers → close ALL
- **Action:** Wait for recovery signal (48h minimum)
- **Priority:** SURVIVE. Your $5K is better than $0.
- **Expected daily return:** N/A (not trading)

## Regime Detection Signals (Phase 4 Implementation)
| Signal | Bull | Neutral | Bear | Crash |
|--------|------|---------|------|-------|
| BTC vs 20-day MA | Above | At | Below | Far below |
| DexScreener new listings/day | > 200 | 100-200 | < 100 | < 50 |
| Average gem score | > 65 | 55-65 | < 55 | < 45 |
| Daily trade win rate (7d avg) | > 60% | 45-60% | < 45% | N/A |

## Money-Making Insight
Most of your annual returns will come from **2-3 bull months**. The rest of the year is about:
1. Not losing money in bear/neutral periods
2. Being positioned to GO HARD when the bull returns
3. Compounding small gains in neutral periods
4. Surviving crashes with capital intact

**The traders who make millions are the ones who are ALIVE and LIQUID when the bull starts.**
