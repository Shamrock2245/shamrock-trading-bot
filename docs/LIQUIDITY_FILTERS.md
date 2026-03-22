# LIQUIDITY FILTERS — Only Trade Where the Exit Door Is Open

## The Golden Rule
> **If you can't sell, it doesn't matter how cheap you bought. Liquidity IS the exit.**

## Phase-Specific Liquidity Floors

| Phase | Min Liquidity | Env Var | Why |
|-------|-------------|---------|-----|
| **Phase 1** ($5K) | **$15,000** | `MIN_LIQUIDITY_USD=15000` | Smaller positions can handle lower liquidity |
| **Phase 2** ($15K) | **$25,000** | `MIN_LIQUIDITY_USD=25000` | Standard protection |
| **Phase 3** ($50K) | **$50,000** | `MIN_LIQUIDITY_USD=50000` | Larger positions need deeper pools |
| **Phase 4** ($250K) | **$100,000** | `MIN_LIQUIDITY_USD=100000` | Whale-grade liquidity needed |

## Why $15,000 Min in Phase 1
```
Your position: $250 (5% of $5K)
Pool liquidity: $15,000
Your % of pool: 1.67%
Expected buy slippage: ~2-3%
Expected sell slippage: ~2-3%
Round-trip slippage cost: ~5% ($12.50)

→ Need 5% gain just to break even
→ But gems regularly do 100-1000% 
→ The 5% slippage cost is noise compared to potential 100x

Compare: $25K minimum would filter OUT many of the best early gems
that are still building liquidity. At $250 position size, $15K 
liquidity is MORE than adequate.
```

## Liquidity Quality Checks

### 🔴 Red Flags (Instant Reject)
| Flag | Why | Danger |
|------|-----|--------|
| Only 1 LP | Single point of failure | LP can rug 100% |
| Liquidity added < 1 hour ago | Bait trap | Remove → rug |
| Liquidity unlocked | Can be removed at any time | Exit disappears |
| Volume/Liquidity > 15:1 | Wash trading | Fake demand |
| Liquidity dropping fast | People pulling out | Exit shrinking |

### 🟢 Green Flags (Score Boost)
| Flag | Score Bonus | Why |
|------|------------|-----|
| 5+ LPs providing liquidity | +5 | Distributed = safer |
| Liquidity locked > 6 months | +8 | Team can't rug |
| Healthy V/L ratio (1:1 to 5:1) | +3 | Organic activity |
| Liquidity growing over time | +5 | Healthy ecosystem |
| Cross-DEX liquidity | +4 | Multiple exit routes |

## Liquidity Scoring (13% of Gem Score)
| Liquidity | Score | Phase 1 Action |
|-----------|-------|----------------|
| ≥ $500K | 100 | 🟢 Large cap — safe to trade |
| $200K–$500K | 85 | 🟢 Good liquidity |
| $100K–$200K | 70 | 🟢 Solid |
| $50K–$100K | 55 | 🟡 Moderate — watch closely |
| $25K–$50K | 35 | 🟡 Low but acceptable at $250 positions |
| $15K–$25K | 15 | ⚠️ Minimum — only on high conviction |
| < $15K | 0 | 🔴 **REJECTED** |

## Exit Liquidity Monitor
Once you're IN a position, keep watching liquidity:
1. Check liquidity on every position monitor cycle (30s)
2. If liquidity drops below 50% of entry level → **ALERT**
3. If liquidity drops below 25% of entry level → **EMERGENCY SELL** regardless of P/L
4. If LP is being removed → **SELL IMMEDIATELY** (rug in progress)

## Liquidity by Chain (Typical Ranges)
| Chain | Average New Token Liquidity | Best Gems Range |
|-------|---------------------------|-----------------|
| Solana | $5K–$500K | $20K–$200K |
| Base | $10K–$1M | $30K–$500K |
| BSC | $5K–$200K | $15K–$100K |
| Arbitrum | $20K–$2M | $50K–$500K |
| Ethereum | $50K–$10M | $100K–$2M |
