# MARKET REGIMES — Adapt or Die

## Why Regime Detection Matters for $5K→$100K
The bot MUST adapt to market conditions. Running the same parameters in a bear market as a bull market is how accounts get blown up.

## Implemented Regime Filter (`core/regime_filter.py`)

The bot runs a **pseudo-ADX regime filter** before every scan cycle using ETH + SOL price data:

```
ETH price change (4h) → pseudo_adx = |change| * amplifier
SOL price change (4h) → volume_ratio = change_magnitude / mean_price
Combined → Regime classification
```

### Active Regimes (Production)
| Regime | Pseudo-ADX | Vol Ratio | Sizing Effect | Discovery Effect |
|--------|-----------|-----------|---------------|-----------------|
| **EXPANSION** 🟢 | ≥ 35 | ≥ 0.04 | Nuclear × 1.5 | Lower MIN_GEM_SCORE, increase scan frequency |
| **NORMAL** 🟡 | 20–35 | 0.03–0.04 | Standard × 1.0 | Standard thresholds |
| **CHOP** 🔴 | < 20 | < 0.03 | Skip new entries, × 0.3 if forced | Raise MIN_GEM_SCORE, reduce frequency |

### How Regime Affects Each Subsystem

#### Scanner (`scanner/gem_scanner.py`)
| Regime | MIN_GEM_SCORE | Scan Interval | Max Trades/Cycle |
|--------|--------------|---------------|-----------------|
| EXPANSION | Lowered (cascade boost accelerates) | 60s | 3 |
| NORMAL | Phase default | 60s | 3 |
| CHOP | Raised (loss cooling accelerates) | 120s | 1 |

#### Position Sizing (`core/wallet_router.py`)
| Regime | Conservative Profile | Nuclear Profile |
|--------|---------------------|----------------|
| EXPANSION | Standard 5% | 60% × 1.5 = 90% (capped at 60%) |
| NORMAL | Standard 5% | 60% |
| CHOP | 50% reduction → 2.5% | **No new entries** |

#### Position Monitor (`core/position_monitor.py`)
| Regime | Trailing Stops | TP Targets | Pyramid |
|--------|---------------|------------|---------|
| EXPANSION | Wider (let it run) | Standard TP ladder | Aggressive — all 3 tiers |
| NORMAL | Standard | Standard | Standard — T1 + T2 |
| CHOP | Tighter (lock gains fast) | Quick flip (1.3x) | Disabled |

### CRASH Mode (Manual Override)
| Trigger | Action |
|---------|--------|
| BTC drops > 10% in 24h | Circuit breaker triggers → close ALL positions |
| Exchange outage detected | Halt all new trades |
| **Recovery:** | Wait 48h minimum, restart at 50% sizes |

## Regime Detection Signals (Future Enhancement)
| Signal | Bull | Neutral | Bear | Crash |
|--------|------|---------|------|-------|
| BTC vs 20-day MA | Above | At | Below | Far below |
| DexScreener new listings/day | > 200 | 100-200 | < 100 | < 50 |
| Average gem score | > 65 | 55-65 | < 55 | < 45 |
| Daily trade win rate (7d avg) | > 60% | 45-60% | < 45% | N/A |

## Money-Making Insight
Most of your annual returns will come from **2-3 EXPANSION months**. The rest of the year is about:
1. Not losing money in CHOP/bear periods
2. Being positioned to GO HARD when EXPANSION returns
3. Compounding small gains in NORMAL periods
4. Surviving crashes with capital intact

**The traders who make millions are the ones who are ALIVE and LIQUID when EXPANSION starts.**
