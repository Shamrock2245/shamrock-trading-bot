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
| `ACTIVE_CHAINS` | `solana,base,arbitrum,bsc` | **Drop Ethereum in Phase 1** — gas kills small positions |

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

### Scanner Settings (Aggressive Scanning)
| Variable | Value | Why |
|----------|-------|-----|
| `SCAN_INTERVAL_SECONDS` | `15` | Scan every 15s — speed is alpha |
| `MIN_GEM_SCORE` | `50.0` | Slightly lower bar — need volume of trades |
| `MIN_LIQUIDITY_USD` | `15000` | Lower liquidity floor for small-cap gems |
| `MAX_TOKEN_AGE_HOURS` | `48` | Fresher tokens have more upside |
| `MAX_TRADES_PER_CYCLE` | `3` | Max 3 per cycle to avoid overconcentration |
| `EXPRESS_LANE_SCORE` | `80.0` | Slightly lower express bar — more fast entries |
| `VOLUME_SPIKE_THRESHOLD` | `4.0` | More sensitive to volume spikes |

### Technical Analysis
| Variable | Value | Why |
|----------|-------|-----|
| `TA_ENABLED` | `true` | Full TA for standard lane |
| `REQUIRE_FIB_ALIGNMENT` | `true` | Fibonacci confirmation adds edge |
| `MIN_SIGNAL_SCORE` | `45.0` | Slightly lower bar for TA confirmation |
| `OHLCV_LOOKBACK_DAYS` | `3` | Shorter lookback for new tokens |
| `FIB_PROXIMITY_PCT` | `5.0` | Wider fib zone for volatile tokens |

### Conviction Multipliers
| Variable | Value |
|----------|-------|
| `CONVICTION_HIGH_THRESHOLD` | `78.0` |
| `CONVICTION_MID_THRESHOLD` | `65.0` |
| `CONVICTION_HIGH_MULTIPLIER` | `1.0` |
| `CONVICTION_MID_MULTIPLIER` | `0.75` |
| `CONVICTION_LOW_MULTIPLIER` | `0.50` |

---

## Phase 2: Growth ($15K–$50K)

### Changes from Phase 1
```diff
- MAX_POSITION_SIZE_PERCENT=5.0
+ MAX_POSITION_SIZE_PERCENT=3.0
- MAX_CONCURRENT_POSITIONS=5
+ MAX_CONCURRENT_POSITIONS=8
- ACTIVE_CHAINS=solana,base,arbitrum,bsc
+ ACTIVE_CHAINS=ethereum,solana,base,arbitrum,polygon,bsc
- MIN_GEM_SCORE=50.0
+ MIN_GEM_SCORE=55.0
- DAILY_LOSS_LIMIT_ETH=0.3
+ DAILY_LOSS_LIMIT_ETH=0.75
- MAX_GAS_GWEI=30
+ MAX_GAS_GWEI=40
- MIN_LIQUIDITY_USD=15000
+ MIN_LIQUIDITY_USD=25000
```

---

## Phase 3: Acceleration ($50K–$250K)

### Changes from Phase 2
```diff
- MAX_POSITION_SIZE_PERCENT=3.0
+ MAX_POSITION_SIZE_PERCENT=2.0
- MAX_CONCURRENT_POSITIONS=8
+ MAX_CONCURRENT_POSITIONS=10
- MIN_GEM_SCORE=55.0
+ MIN_GEM_SCORE=60.0
- DAILY_LOSS_LIMIT_ETH=0.75
+ DAILY_LOSS_LIMIT_ETH=1.5
- MAX_GAS_GWEI=40
+ MAX_GAS_GWEI=50
- EXPRESS_LANE_SCORE=80.0
+ EXPRESS_LANE_SCORE=82.0
```

---

## Phase 4: Whale ($250K+)

### Changes from Phase 3
```diff
- MAX_POSITION_SIZE_PERCENT=2.0
+ MAX_POSITION_SIZE_PERCENT=1.0
- MAX_CONCURRENT_POSITIONS=10
+ MAX_CONCURRENT_POSITIONS=15
- MIN_GEM_SCORE=60.0
+ MIN_GEM_SCORE=65.0
- DAILY_LOSS_LIMIT_ETH=1.5
+ DAILY_LOSS_LIMIT_ETH=3.0
- MIN_LIQUIDITY_USD=25000
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
| **Faster scanning** | Lower `SCAN_INTERVAL_SECONDS` to 10 |
| **Bigger positions** | Raise `MAX_POSITION_SIZE_PERCENT` by 1 |
| **Tighter risk** | Lower `STOP_LOSS_PERCENT` by 2 |
| **More chains** | Add to `ACTIVE_CHAINS` |
| **Drop a losing chain** | Remove from `ACTIVE_CHAINS` |
| **Catch more spikes** | Lower `VOLUME_SPIKE_THRESHOLD` to 3 |
| **Wider express lane** | Lower `EXPRESS_LANE_SCORE` to 78 |
