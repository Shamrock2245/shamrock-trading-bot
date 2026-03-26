# SIGNALS — What Tells Us to Trade (and What Makes Money)

## Signal Architecture (Two-Layer System)

The bot uses a **two-layer signal system**:

1. **Scanner Layer** — 14 weighted signals in `gem_scanner.py` produce a **gem_score** (0–100)
2. **TA Layer** — 29-indicator technical analysis in `signal_engine.py` produces a **composite score** that blends with the gem_score

```
Discovery Sources (9)
    ↓
Scanner: 14 Signals → gem_score (0–100)
    ↓
Enrichment: Moralis + Binance Pulse + Dev Wallet + Copycat
    ↓
Nuclear Bonuses: buying pressure +18, whale +20%, dev reject -30
    ↓
Signal Engine: 29-Indicator TA blend → composite_score
    ↓
Strategy Gate → Safety → Execute
```

---

## Layer 1: Scanner Signals (14 Signals, Weights Sum to 100%)

Source: `scanner/gem_scanner.py` → `_score_token()`

| # | Signal | Weight | Source | Notes |
|---|--------|--------|--------|-------|
| 1 | **Volume spike** | **15%** | DexScreener | 1h vol / (24h vol / 24) — strongest predictor |
| 2 | **Liquidity depth** | **13%** | DexScreener | Min $20K, ideal > $200K |
| 3 | **Token age** | **12%** | DexScreener | < 24h = 100, < 48h = 75, trending gets leniency |
| 4 | **Contract verified** | 8% | GoPlus | Default 70, updated by safety check |
| 5 | **Holder distribution** | 8% | DexScreener / Moralis | ≥ 1000 holders = 100 |
| 6 | **Buy/sell tax** | 8% | DexScreener | > 5% = penalized, > 10% = zero |
| 7 | **Social signals** | 6% | LunarCrush + CoinGecko + DexScreener | Real social scoring via `social_scoring.py` |
| 8 | **TVL** | 5% | Moralis (liquidity_locked_pct) | Replaced DefiLlama — now Moralis-native |
| 9 | **Social sentiment** | 5% | Moralis (on_chain_strength) | Replaced LunarCrush — now Moralis-native |
| 10 | **DexScreener boost** | 4% | DexScreener | ≥ 500 boost = 100, neutral 50 if unboosted |
| 11 | **Smart money** | 4% | `smart_money.py` + Moralis wallet stats | Wallet overlap scoring |
| 12 | **Holder concentration** | 4% | Moralis pair stats / Solana top holders | Top 10 > 80% = 10 score (rug risk) |
| 13 | **Unlock/dilution risk** | 4% | Moralis | Neutral 50 for micro-caps |
| 14 | **Grok X sentiment** | 4% | Grok AI (deferred 2nd pass) | Real-time X/Twitter analysis |

**Honeypot check** is PASS/FAIL (instant disqualify — not a scored signal).

### Solana-Specific Signals (Applied on top)
| Signal | Source | Effect |
|--------|--------|--------|
| Sniper detection | `moralis_solana.py` | ≥ 10 snipers or critical risk = **HARD BLOCK** |
| Holder concentration | `moralis_solana.py` | Overrides EVM holder conc with Solana-native data |

---

## Post-Scanner Enrichment Bonuses

These fire **after** the 14-signal base score for candidates scoring ≥ 45:

| Bonus | Trigger | Effect | Source |
|-------|---------|--------|--------|
| **Moralis Buying Pressure** | > 70% buy pressure in 1h | **+18 points** to gem_score | `moralis_money.py` |
| **Whale Accumulation** | netExperiencedBuyers > threshold | **+20% bonus weight** | `moralis_money.py` |
| **Moralis Security Score** | Low security score | Penalizes contract_score | `moralis_money.py` |
| **Enhanced Metadata** | FDV/spam/social links | Enriches contract + social scores | `moralis_wallet.py` |
| **Binance Pulse** | Smart money confirmed | Score boost via unified rank | `binance_pulse.py` |
| **CTO Revival** | Community takeover detected | **+8 points** | DexScreener Source 4 |
| **Dev Wallet Reject** | Serial deployer (< 48h, > 3 tokens) | **−30 points** | `dev_wallet_history.py` |
| **Copycat Reject** | Fuzzy match against 50+ tokens | **Instant reject** (dropped before enrichment) | `copycat_detector.py` |

---

## Layer 2: Technical Analysis (29 Indicators)

Source: `strategies/indicators.py` → `core/signal_engine.py`

### Full TA Path (≥ 24 OHLCV candles)

| Category | Indicators | Weight in Composite |
|----------|-----------|-------------------|
| **Trend** | EMA(9/21/50/200) crossovers, ADX trend strength, Ichimoku Cloud, Parabolic SAR, SuperTrend, HMA slope | ~30% |
| **Momentum** | RSI(14), MACD histogram, Stochastic %K/%D, Williams %R, CCI(20), CMF(20), ROC(12), PPO, TSI | ~25% |
| **Volatility** | Bollinger Bands %B + squeeze, ATR(14), Keltner Channels, Donchian Channels | ~15% |
| **Volume** | OBV slope, VWAP deviation, A/D Line, MFI(14), Volume Price Trend | ~15% |
| **Divergence** | RSI divergence, MACD divergence, OBV divergence detection | ~15% |

### Micro-Cap Path (< 24 candles)
Uses **gem_score + enrichment composite** across 5 axes:
- Trend (from available price data)
- Momentum (volume acceleration)
- Volume (spike ratio)
- On-chain (holder growth, smart money, Moralis enrichment)
- Sentiment (social + Grok)

**Critical design**: Missing indicators default to **neutral (50.0)** — zero data never penalizes a micro-cap gem.

---

## 🔴 Instant Reject Signals (Any = No Trade)
- GoPlus honeypot detection = TRUE
- Honeypot.is simulation FAIL
- Token Sniffer score < 50
- Token on blocklist (`config/tokens.py`)
- Liquidity < $20,000
- Buy/sell tax > 10%
- Ownership not renounced AND can mint
- Copycat detection match (fuzzy + Unicode homoglyphs)
- Solana sniper risk = critical (≥ 10 snipers)
- Dev wallet serial deployer + fresh (< 48h, > 3 tokens)

## 🟢 High-Profit Signal Combos
| Combo | Signals | Expected Win Rate | Avg Return |
|-------|---------|-------------------|------------|
| **"Nuclear Launch"** | Score ≥ 90 + EXPANSION regime + buying pressure > 70% | ~65% | +200% avg |
| **"The Perfect Storm"** | Fresh (< 3h) + Volume 10x+ + Smart money + Boost > 200 | ~60% | +100% avg |
| **"Whale Accumulation"** | netExperiencedBuyers rising + holder growth + smart money | ~60% | +80% avg |
| **"CTO Revival"** | CTO + Volume spike + Social buzz | ~50% | +200% avg |
| **"Steady Builder"** | Good liquidity + Verified + TA confirmation | ~55% | +40% avg |

## Score Thresholds
| Threshold | Profile | Effect |
|-----------|---------|--------|
| ≥ 90 | Nuclear | Express lane — instant buy, skip TA, 1.5x gas |
| ≥ 85 | Nuclear | God Signal — 1.5x gas bribe for priority |
| ≥ 82 | Nuclear | Wallet B minimum entry |
| ≥ 65 | Conservative | Primary wallet minimum entry |
| 45–64 | Standard | Requires full TA + Fibonacci confirmation |
| < 45 | — | No enrichment, no trade |

## Signal Decay — When to IGNORE Old Data
- DexScreener boost data > 6 hours old → stale, ignore
- Volume spike > 2 hours old → momentum may have faded
- Social sentiment > 12 hours old → refresh required
- CTO claim > 48 hours old → initial pump likely over
- Moralis buying pressure > 1 hour old → refresh on next cycle
