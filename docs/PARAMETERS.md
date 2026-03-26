# PARAMETERS — Tuning for Maximum Profit

## ⚠️ Phase-Dependent Parameters
These settings MUST change as the portfolio grows. See `STRATEGIES.md` for growth phase definitions.

---

## Phase 1: Seed ($5K–$15K) — CURRENT SETTINGS

### Trading Mode
| Variable | Value | Notes |
|----------|-------|-------|
| `MODE` | `paper` → `live` | Start paper, switch when validated |

### Chain Configuration
| Variable | Value | Notes |
|----------|-------|-------|
| `ACTIVE_CHAINS` | `solana,base,bsc,avalanche` | **Solana-first.** Avalanche added, Ethereum deferred |

### Risk Management (Aggressive for Growth)
| Variable | Value | Why |
|----------|-------|-----|
| `MAX_POSITION_SIZE_PERCENT` | `5.0` | $250 per trade at $5K — big enough to profit after fees |
| `MAX_CONCURRENT_POSITIONS` | `5` | Concentrated bets, focused monitoring |
| `STOP_LOSS_PERCENT` | `8.0` | Tighter than default — cut losers fast with small portfolio |
| `HARD_STOP_LOSS_PERCENT` | `20.0` | Tighter hard stop to protect scarce capital |
| `TAKE_PROFIT_1X` | `2.0` | Bank initial investment at 2x |
| `TAKE_PROFIT_2X` | `5.0` | Take big profits at 5x |
| `CIRCUIT_BREAKER_PERCENT` | `15.0` | $750 max portfolio loss before full stop |
| `DAILY_LOSS_LIMIT_ETH` | `0.3` | ~$600 at current prices — TIGHT |
| `MAX_GAS_GWEI` | `30` | Keep gas low — skip expensive windows |
| `MIN_ETH_BALANCE_ALERT` | `0.03` | Alert early on gas depletion |

### Scanner Settings
| Variable | Value | Why |
|----------|-------|-----|
| `SCAN_INTERVAL_SECONDS` | `60` | Scan every 60s — balanced speed vs. API load |
| `MIN_GEM_SCORE` | `55.0` | Global minimum (nuclear profile overrides to 82.0) |
| `MIN_LIQUIDITY_USD` | `20000` | Minimum pool depth for safe exit |
| `MAX_TOKEN_AGE_HOURS` | `48` | Fresher tokens have more upside |
| `MAX_TRADES_PER_CYCLE` | `3` | Max 3 per cycle to avoid overconcentration |
| `EXPRESS_LANE_SCORE` | `82.0` | Express lane entry for conservative profile |
| `VOLUME_SPIKE_THRESHOLD` | `4.0` | More sensitive to volume spikes |

### Technical Analysis
| Variable | Value | Why |
|----------|-------|-----|
| `TA_ENABLED` | `true` | Full 29-indicator TA for standard lane |
| `REQUIRE_FIB_ALIGNMENT` | `true` | Fibonacci confirmation adds edge |
| `MIN_SIGNAL_SCORE` | `45.0` | Slightly lower bar for TA confirmation |
| `OHLCV_LOOKBACK_DAYS` | `3` | Shorter lookback for new tokens |
| `FIB_PROXIMITY_PCT` | `5.0` | Wider fib zone for volatile tokens |

### Moralis Pro & Enrichment
| Variable | Value | Why |
|----------|-------|-----|
| `MORALIS_API_KEY` | Secret | Moralis Pro tier — 150K CU/day |
| `MORALIS_PRO_ENABLED` | `true` | Enables Moralis trending/filtered discovery |
| `BINANCE_PULSE_ENABLED` | `true` | Enables Binance smart money + social hype |
| `GROK_API_KEY` | Secret | Grok X sentiment analysis (deferred 2nd pass) |

---

## Offensive Guardrail Parameters

### Hot Streak Tracker
| Variable | Value | Notes |
|----------|-------|-------|
| `HOT_STREAK_ENABLED` | `true` | Scales Kelly fraction on win/loss streaks |

### God Mode
| Variable | Value | Notes |
|----------|-------|-------|
| `GOD_MODE_ENABLED` | `true` | Activates on daily PnL threshold |
| `GOD_MODE_DAILY_PNL_THRESHOLD_USD` | `200.0` | Min daily profit to trigger |
| `GOD_MODE_KELLY_MULTIPLIER` | `2.0` | Full Kelly (from Half-Kelly baseline) |
| `GOD_MODE_TRAILING_STOP_PCT` | `8.0` | Tighter stops in God Mode |
| `GOD_MODE_SKIP_TP1` | `true` | Hold for TP2 (5x) instead of selling at 2x |
| `GOD_MODE_MAX_DRAWDOWN_FROM_PEAK_USD` | `200.0` | Deactivation ceiling |

### House Money Protocol
| Variable | Value | Notes |
|----------|-------|-------|
| `HOUSE_MONEY_ENABLED` | `true` | Pool wins for reinvestment |
| `HOUSE_MONEY_REINVEST_PCT` | `30.0` | % of win contributed to pool |
| `HOUSE_MONEY_MAX_POOL_USD` | `2000.0` | Pool cap |
| `HOUSE_MONEY_MIN_DEPLOY_USD` | `50.0` | Min pool amount to deploy |
| `HOUSE_MONEY_MAX_DEPLOY_PCT` | `50.0` | Max % of pool per trade |
| `HOUSE_MONEY_MAX_POSITION_MULT` | `2.0` | Max multiple of base position |

### Pyramid Scaling (3 Tiers)
| Variable | Value | Notes |
|----------|-------|-------|
| `PYRAMID_SCALING_ENABLED` | `true` | Master toggle |
| `PYRAMID_TIER1_GAIN_PCT` | `30.0` | +30% gain → first add |
| `PYRAMID_TIER1_ADD_PCT` | `50.0` | 50% of original position |
| `PYRAMID_TIER1_TRAILING_STOP_PCT` | `20.0` | New trailing stop after T1 |
| `PYRAMID_TIER2_GAIN_PCT` | `100.0` | +100% gain → second add |
| `PYRAMID_TIER2_ADD_PCT` | `25.0` | 25% of original (house money) |
| `PYRAMID_TIER2_TRAILING_STOP_PCT` | `15.0` | Tighter trailing |
| `PYRAMID_TIER3_GAIN_PCT` | `300.0` | +300% gain → third add |
| `PYRAMID_TIER3_ADD_PCT` | `10.0` | 10% of original |
| `PYRAMID_TIER3_TRAILING_STOP_PCT` | `10.0` | Tightest trailing |

### Fast Fail
| Variable | Value | Notes |
|----------|-------|-------|
| `FAST_FAIL_ENABLED` | `true` | Master toggle |
| `FAST_FAIL_HOURS` | `2.0` | Hours before momentum death check |
| `FAST_FAIL_DOWN_PCT` | `10.0` | Down > 10% = momentum dead |
| `FAST_FAIL_STALL_HOURS` | `4.0` | Hours before stall check |
| `FAST_FAIL_STALL_PCT` | `15.0` | Must be up > 15% in 4h |
| `FAST_FAIL_VOLUME_COLLAPSE_PCT` | `80.0` | Volume drops > 80% from entry → exit |

### Cascade & Loss Cooling
| Variable | Value | Notes |
|----------|-------|-------|
| `CASCADE_BOOST_ENABLED` | `true` | Wins lower MIN_GEM_SCORE |
| `CASCADE_BOOST_PER_WIN` | `0.5` | -0.5 pts per win |
| `CASCADE_BOOST_MAX_REDUCTION` | `10.0` | Max -10 pts reduction |
| `CASCADE_BOOST_FLOOR_SCORE` | `40.0` | Never below 40 |
| `LOSS_STREAK_COOLING_ENABLED` | `true` | Losses raise MIN_GEM_SCORE |
| `LOSS_STREAK_SCORE_PENALTY` | `2.0` | +2 pts per consecutive loss |
| `LOSS_STREAK_MAX_PENALTY` | `10.0` | Max +10 pts penalty |

### Express Overdrive & Blitz Mode
| Variable | Value | Notes |
|----------|-------|-------|
| `EXPRESS_OVERDRIVE_ENABLED` | `true` | 1.5x–2.0x sizing on express trades |
| `EXPRESS_OVERDRIVE_EXTRA_SLIPPAGE_BPS` | `100` | +1% slippage buffer |
| `BLITZ_MODE_ENABLED` | `true` | Synergy bonus for 3+ aligned conditions |
| `BLITZ_MODE_MULTIPLIER` | `1.25` | Additional multiplier |

### Momentum Reentry
| Variable | Value | Notes |
|----------|-------|-------|
| `MOMENTUM_REENTRY_ENABLED` | `true` | Re-enter after TP1 if vol surging |
| `MOMENTUM_REENTRY_VOLUME_MULT` | `3.0` | Volume must be 3x hourly average |
| `MOMENTUM_REENTRY_MAX_AGE_MINUTES` | `60.0` | Window to re-enter |
| `MOMENTUM_REENTRY_SIZE_MULT` | `1.25` | 1.25x normal size |

### Absolute Caps
| Variable | Value | Notes |
|----------|-------|-------|
| `OFFENSIVE_MAX_POSITION_USD` | `5000.0` | Hard cap on any single trade |
| `OFFENSIVE_MAX_POSITION_WALLET_PCT` | `30.0` | % of wallet balance cap |
| `AUTO_COMPOUND_PCT` | `50.0` | % of Wallet B TP profits → Primary |
| `GAS_BRIBE_PREMIUM_PCT` | `15.0` | Gas premium for God Signal (score ≥ 85) |

---

## Phase Progression

### Phase 2: Growth ($15K–$50K) — Changes
```diff
- ACTIVE_CHAINS=solana,base,bsc,avalanche
+ ACTIVE_CHAINS=ethereum,solana,base,arbitrum,polygon,bsc,avalanche
- MIN_GEM_SCORE=55.0
+ MIN_GEM_SCORE=55.0
- MAX_POSITION_SIZE_PERCENT=5.0
+ MAX_POSITION_SIZE_PERCENT=3.0
- MAX_CONCURRENT_POSITIONS=5
+ MAX_CONCURRENT_POSITIONS=8
```

### Phase 3: Acceleration ($50K–$250K) — Changes
```diff
- MAX_POSITION_SIZE_PERCENT=3.0
+ MAX_POSITION_SIZE_PERCENT=2.0
- MAX_CONCURRENT_POSITIONS=8
+ MAX_CONCURRENT_POSITIONS=10
- MIN_GEM_SCORE=55.0
+ MIN_GEM_SCORE=60.0
```

### Phase 4: Whale ($250K+) — Changes
```diff
- MAX_POSITION_SIZE_PERCENT=2.0
+ MAX_POSITION_SIZE_PERCENT=1.0
- MAX_CONCURRENT_POSITIONS=10
+ MAX_CONCURRENT_POSITIONS=15
- MIN_GEM_SCORE=60.0
+ MIN_GEM_SCORE=65.0
- MIN_LIQUIDITY_USD=20000
+ MIN_LIQUIDITY_USD=50000
```

---

## When to Advance Phases
| Trigger | Action |
|---------|--------|
| Portfolio crosses $15K sustained for 7 days | → Phase 2 |
| Portfolio crosses $50K sustained for 7 days | → Phase 3 |
| Portfolio crosses $250K sustained for 7 days | → Phase 4 |
| Circuit breaker triggers | → Drop one phase (tighten risk) |

## Quick-Tune Cheatsheet
| Want to... | Change |
|-----------|--------|
| **More trades** | Lower `MIN_GEM_SCORE` by 5 |
| **Higher quality** | Raise `MIN_GEM_SCORE` by 5 |
| **More aggressive sizing** | Enable `BLITZ_MODE_ENABLED` + `EXPRESS_OVERDRIVE_ENABLED` |
| **Bigger positions** | Raise `MAX_POSITION_SIZE_PERCENT` by 1 |
| **Tighter risk** | Lower `FAST_FAIL_HOURS` to 1.0 |
| **More chains** | Add to `ACTIVE_CHAINS` |
| **Faster capital recycling** | Lower `FAST_FAIL_STALL_HOURS` to 3.0 |
| **Wider express lane** | Lower `EXPRESS_LANE_SCORE` to 78 |
