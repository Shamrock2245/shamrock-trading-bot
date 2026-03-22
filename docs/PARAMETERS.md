# PARAMETERS — All Tunable Settings

## Environment Variables (`.env`)

### Trading Mode
| Variable | Default | Description |
|----------|---------|-------------|
| `MODE` | `paper` | `paper` or `live` |

### Chain Configuration
| Variable | Default | Description |
|----------|---------|-------------|
| `ACTIVE_CHAINS` | `ethereum,base,arbitrum,polygon,bsc,solana` | Comma-separated active chains |

### Risk Management
| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_POSITION_SIZE_PERCENT` | `2.0` | Max % of portfolio per position |
| `MAX_CONCURRENT_POSITIONS` | `10` | Max open positions |
| `STOP_LOSS_PERCENT` | `10.0` | Standard stop-loss |
| `HARD_STOP_LOSS_PERCENT` | `25.0` | Emergency hard stop |
| `TAKE_PROFIT_1X` | `2.0` | First take-profit multiplier |
| `TAKE_PROFIT_2X` | `5.0` | Second take-profit multiplier |
| `CIRCUIT_BREAKER_PERCENT` | `15.0` | Portfolio drawdown to trigger shutdown |
| `DAILY_LOSS_LIMIT_ETH` | `0.5` | Max daily loss in ETH |
| `MAX_GAS_GWEI` | `50` | Max gas price for Ethereum |
| `MIN_ETH_BALANCE_ALERT` | `0.05` | Alert when ETH balance drops below |

### Scanner Settings
| Variable | Default | Description |
|----------|---------|-------------|
| `SCAN_INTERVAL_SECONDS` | `30` | Time between scan cycles |
| `MIN_GEM_SCORE` | `55.0` | Minimum score to consider |
| `MIN_LIQUIDITY_USD` | `25000` | Minimum pool liquidity |
| `MAX_TOKEN_AGE_HOURS` | `168` | Max token age (7 days) |
| `MAX_TRADES_PER_CYCLE` | `3` | Max new trades per scan |
| `EXPRESS_LANE_SCORE` | `82.0` | Score for instant execution |
| `VOLUME_SPIKE_THRESHOLD` | `5.0` | Multiplier vs 24h avg for breakout |

### Technical Analysis
| Variable | Default | Description |
|----------|---------|-------------|
| `TA_ENABLED` | `true` | Enable/disable TA pipeline |
| `REQUIRE_FIB_ALIGNMENT` | `true` | Require Fibonacci support |
| `MIN_SIGNAL_SCORE` | `50.0` | Min TA signal score |
| `OHLCV_LOOKBACK_DAYS` | `7` | Days of candle data for TA |
| `FIB_PROXIMITY_PCT` | `3.0` | Max distance from fib level |

### Conviction Multipliers
| Variable | Default | Description |
|----------|---------|-------------|
| `CONVICTION_HIGH_THRESHOLD` | `80.0` | Score threshold for high conviction |
| `CONVICTION_MID_THRESHOLD` | `70.0` | Score threshold for mid conviction |
| `CONVICTION_HIGH_MULTIPLIER` | `1.0` | Size multiplier for high conviction |
| `CONVICTION_MID_MULTIPLIER` | `0.75` | Size multiplier for mid conviction |
| `CONVICTION_LOW_MULTIPLIER` | `0.50` | Size multiplier for low conviction |

### MEV Protection
| Variable | Default | Description |
|----------|---------|-------------|
| `FLASHBOTS_RPC_URL` | `https://rpc.flashbots.net` | Flashbots RPC |
| `COW_API_URL` | `https://api.cow.fi/mainnet` | CoW Protocol API |

### Notifications
| Variable | Default | Description |
|----------|---------|-------------|
| `SLACK_WEBHOOK_URL` | `` | Slack webhook for alerts |
| `TELEGRAM_BOT_TOKEN` | `` | Telegram bot token |
| `TELEGRAM_CHAT_ID` | `` | Telegram chat for alerts |

### Logging
| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | `INFO` | Python log level |
| `LOG_DIR` | `./logs` | Log output directory |

## Tuning Guide
- **Want more trades?** Lower `MIN_GEM_SCORE` (but expect lower win rate)
- **Want higher quality?** Raise `MIN_GEM_SCORE` to 65+ (fewer but better)
- **Want faster scanning?** Lower `SCAN_INTERVAL_SECONDS` to 15
- **Want bigger positions?** Raise `MAX_POSITION_SIZE_PERCENT` (max recommended: 3%)
- **Want tighter risk?** Lower `STOP_LOSS_PERCENT` to 5-8%
