# ⚔️ Shamrock Trading Bot: Offensive Playbook

> **Status:** NUCLEAR DEPLOYED — this document reflects live code in `config/wallets.py`,
> `core/regime_filter.py`, `core/position_monitor.py`, and `core/offensive_guardrails.py`.
> Last updated: 2026-03-25

---

## 1. The Alpha Edge: Data Confluence

We do not rely on a single data source. Our edge comes from cross-referencing on-chain realities
with market momentum in the **first 3–5 minutes of accumulation** — before retail FOMO.

### Primary Data Sources

| Source | Role | Weight in Score |
|--------|------|----------------|
| **Moralis Money** | Buying pressure, experienced net buyers, on-chain strength | **20%** (primary signal) |
| **DexScreener** | Real-time volume spikes, liquidity depth, community boosts | 7–15% (multi-signal) |
| **GeckoTerminal** | Trending pool validation, OHLCV fallback | Secondary |
| **GoPlus Security** | Honeypot detection, tax check, contract audit | Pass/Fail gate |
| **Grok / LunarCrush** | Social sentiment delta | 2–4% |

### The Nuclear Bonus: Moralis Buying Pressure > 70%

When Moralis confirms >70% buy pressure in the 1h window, a **+18 point bonus** is applied
directly to the composite gem score. This rockets high-base-score tokens into express lane
territory (>=90) and is the single most powerful signal in the pipeline.

```python
# scanner/gem_scanner.py
if moralis_buy_pressure > 0.70:
    candidate.gem_score = min(100.0, round(candidate.gem_score + 18.0, 2))
```

### The Dev Reject: Serial Deployer Penalty

If a token's dev wallet is **<48h old AND has launched >3 tokens**, a **-30 point penalty**
is applied. This eliminates serial rug deployers before they reach the execution pipeline.

```python
if dev_is_fresh and dev_serial:
    candidate.gem_score = max(0.0, round(candidate.gem_score - 30.0, 2))
```

---

## 2. Scoring System (14 Signals, Weights Sum to 1.00)

| Signal | Weight | Notes |
|--------|--------|-------|
| Moralis enrichment | **20%** | PRIMARY — doubled from v1 |
| Volume score | 7% | 1h spike vs 24h average |
| Age score | 7% | <24h = high score |
| Buy pressure score | 7% | Buy/sell ratio from DexScreener |
| Liquidity score | 6% | Minimum $25K, ideal >$200K |
| Tax score | 6% | >5% buy or sell = penalized |
| Contract score | 5% | GoPlus verification |
| Holder score | 5% | Holder count growth |
| Social score | 5% | Twitter/TG mentions |
| Social sentiment | 4% | Grok/LunarCrush delta |
| TVL score | 4% | DeFiLlama protocol TVL |
| Sniper score | 4% | Solana sniper detection |
| Boost score | 4% | DexScreener paid boost signal |
| Smart money | 3% | Known whale wallet overlap |
| Holder concentration | 3% | Top-10 wallet % |
| Dev wallet | 3% | Dev history / rug patterns |
| Copycat | 3% | Name/symbol clone detection |
| Unlock risk | 2% | Token unlock schedule |
| Grok sentiment | 2% | X/Twitter AI sentiment |

### Score Thresholds

| Threshold | Meaning |
|-----------|---------|
| >= 65 | Minimum entry (global fallback, conservative profile) |
| >= 82 | Nuclear profile (Wallet B) minimum entry |
| >= 90 | Express lane — instant market buy, skip full TA pipeline |
| >= 85 | God Signal — 1.5x gas bribe, God Mode eligible |

---

## 3. Market Regime Filter (Global Gate — Every Cycle)

The regime filter runs **before scanning** every cycle. It uses a pseudo-ADX derived from ETH
and SOL 24h price range, volatility, and volume/market-cap ratio.

| Regime | Condition | Effect |
|--------|-----------|--------|
| **EXPANSION** | pseudo-ADX >= 35, vol_ratio >= 0.04 | Wallet B nuclear sizing x1.5 multiplier |
| **NORMAL** | Between CHOP and EXPANSION | Standard sizing on both wallets |
| **CHOP** | pseudo-ADX < 20, vol_ratio < 0.03 | **Both wallets skip new entries this cycle.** Sizing at 30% if entries occur. |

```python
# core/regime_filter.py
def get_sizing_multiplier(regime: Regime, profile_name: str = "conservative") -> float:
    if regime == Regime.EXPANSION:
        return 1.5 if profile_name == "nuclear" else 1.0
    elif regime == Regime.CHOP:
        return 0.3  # Both wallets reduce 70%
    else:
        return 1.0
```

**CHOP kills the bleed.** No new entries in choppy markets — the bot waits for expansion.

---

## 4. Dual-Wallet Strategy Profiles

Both wallets can fire on the **same 85+ token simultaneously** — Primary takes a small
conservative position, Wallet B takes a massive nuclear position.

### Primary Wallet — Conservative Profile

| Parameter | Value |
|-----------|-------|
| Min gem score | 65.0 |
| Express lane | >= 82.0 |
| Max position | **5%** of wallet |
| Kelly clamp | 10% |
| Max concurrent | 5 |
| TP1 | 2x — sell 40% |
| TP2 | 3x — sell 40% of remaining |
| TP3 | Disabled |
| Hard stop | 20% |
| Trailing stop | 15% (fixed after TP1) |
| Slippage | 5% |

### Wallet B — Nuclear Profile

| Parameter | Value |
|-----------|-------|
| Min gem score | **82.0** |
| Express lane | **>= 90.0** |
| Max position | **60%** of wallet |
| Kelly clamp | **70%** |
| Max concurrent | **3** |
| TP1 | **5x — sell 15%** |
| TP2 | **12x — sell 25%** of remaining |
| TP3 | **30x — sell 20%** of remaining |
| Ride | **40% rides** with dynamic trailing stop |
| Hard stop | **10%** |
| Trailing stop | 30% tightens to **18% at 10x** then **8% at 20x** |
| Slippage | **8%** (wider for meme launches) |

**Wallet B is the missile.** 60-70% of its capital on a single S-tier setup during expansion.
The TP ladder locks in house money early (5x) while letting the 40% runner compound to 30x+.

---

## 5. Pyramid Scaling (Adding to Winners with House Money)

After TP1 is hit, the bot adds to winning positions at three tiers using realized profits:

| Tier | Trigger | Add Size | New Trailing Stop |
|------|---------|----------|------------------|
| Tier 1 | +30% gain | 50% of original position | 20% |
| Tier 2 | +100% gain | 25% of original position | 15% |
| Tier 3 | +300% gain | 10% of original position | 10% |

Pyramid adds are funded from the house money pool — **no new capital at risk**. Each add
tightens the trailing stop to lock in more of the gain.

---

## 6. Exit Rules

### Nuclear TP Ladder (Wallet B)

1. **5x (400% gain):** Sell 15% — lock in initial capital, start house money pool
2. **12x (1100% gain):** Sell 25% of remaining — compound the pool
3. **30x (2900% gain):** Sell 20% of remaining — massive realized gain
4. **Ride 40%** with dynamic trailing stop (30% then 18% at 10x then 8% at 20x)

### Conservative TP Ladder (Primary)

1. **2x (100% gain):** Sell 40% — recover capital
2. **3x (200% gain):** Sell 40% of remaining
3. **Ride 20%** with 15% fixed trailing stop

### Stop Loss Rules

| Rule | Conservative | Nuclear |
|------|-------------|---------|
| Hard stop | -20% | -10% |
| Trailing stop (post-TP1) | 15% fixed | 30% then 18% then 8% dynamic |
| Fast fail | -10% in 2h | -15% in 1.5h |
| Time exit | Flat +/-5% for 12h | Flat +/-5% for 12h |
| Liquidity drain | Pool -30% in 1h | Pool -30% in 1h |

---

## 7. Global Risk Gates

### Circuit Breaker
Portfolio drops >= **15%** — **all trading halted, manual reset required.**

### Global Drawdown Sleep
Portfolio drops >= **20%** — **all new entries halted for 48 hours.** Existing positions
continue to be monitored and exited per normal rules. Auto-resumes after 48h.

### Regime CHOP Gate
Market enters CHOP regime — **all new entries skipped this cycle.** Both wallets operate
at 30% sizing if entries do occur (e.g., from watchlist promotions).

---

## 8. Execution and MEV Protection

### Routing Strategy

| Chain | Primary Router | MEV Protection |
|-------|---------------|----------------|
| Ethereum | CoW Protocol / 1inch | Flashbots private mempool |
| Base | Aerodrome / Uniswap V3 | MEV-Blocker RPC |
| Arbitrum | Camelot / Uniswap V3 | Private RPC |
| BSC | PancakeSwap V3 | Standard slippage control |
| Solana | Jupiter | Jupiter MEV protection |

### Slippage Rules

- Conservative entries: **5%** max slippage
- Nuclear entries (Wallet B): **8%** max slippage — wider tolerance for meme launches
- Express lane (score >= 90): Immediate market buy with gas bribe (1.5x base fee)
- God Signal (score >= 85): 1.5x gas bribe for next-block inclusion

---

## 9. Nuclear Entry Checklist

For Wallet B to fire, **ALL** of these must be true:

1. Gem score >= 82 (or >= 90 for express lane)
2. Honeypot check: PASS (GoPlus + Honeypot.is)
3. Buy/sell tax <= 5% on both sides
4. Contract verified on block explorer
5. Regime is NORMAL or EXPANSION (CHOP = skip)
6. No global drawdown sleep active (portfolio not down >= 20%)
7. Max 3 concurrent positions on Wallet B not exceeded
8. Dev wallet not flagged as serial deployer (<48h + >3 tokens)

When all 8 conditions align on a score >= 90 token during EXPANSION: **this is the nuclear launch.**

---

## 10. Continuous Portfolio Management

- **Dust sweeping:** Tokens worth <$5 with low liquidity are ignored (gas cost exceeds value)
- **Underperformer rotation:** Flat positions (+/-5% for 12h) are closed to free capital
- **USDC deployment:** Idle stablecoins are pushed into top-scoring gems — cash is trash
- **Profit sweep:** Realized profits above threshold are swept to Wallet C (cold storage)
- **Auto-compound:** 50% of nuclear TP profits rebuild the house money pool; 50% compounds
