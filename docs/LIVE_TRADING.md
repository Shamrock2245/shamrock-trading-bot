# LIVE TRADING — Going Live Safely (Phase 1: $5K)

## ⚠️ READ THIS ENTIRE DOCUMENT BEFORE ENABLING LIVE MODE ⚠️

## Phase 1 Pre-Live Checklist ($5K Starting Capital)

### Wallet Setup
- [ ] Solana wallet funded with SOL for gas + trading capital
- [ ] Base wallet funded with ETH for gas + trading capital
- [ ] Arbitrum wallet funded (if using)
- [ ] BSC wallet funded with BNB for gas (if using)
- [ ] **DO NOT fund Ethereum wallet** in Phase 1 — gas too expensive
- [ ] Private keys in `.env` ONLY — verified gitignored

### Capital Allocation (Recommended for $5K)
| Chain | Allocation | Why |
|-------|-----------|-----|
| **Solana** | $2,000 (40%) | Cheapest gas, most memecoin flow |
| **Base** | $1,500 (30%) | Low fees, growing ecosystem |
| **Arbitrum** | $1,000 (20%) | Solid DeFi, good targets |
| **BSC** | $500 (10%) | Selective plays only |
| Ethereum | $0 (0%) | Too expensive for Phase 1 |

### Environment Configuration
- [ ] `MODE=live` set in `.env`
- [ ] `ACTIVE_CHAINS=solana,base,arbitrum,bsc` (no ethereum)
- [ ] `MAX_POSITION_SIZE_PERCENT=5.0`
- [ ] `MAX_CONCURRENT_POSITIONS=5`
- [ ] `STOP_LOSS_PERCENT=8.0`
- [ ] `HARD_STOP_LOSS_PERCENT=20.0`
- [ ] `CIRCUIT_BREAKER_PERCENT=15.0`
- [ ] `DAILY_LOSS_LIMIT_ETH=0.3`
- [ ] `MAX_GAS_GWEI=30`
- [ ] `SCAN_INTERVAL_SECONDS=15`
- [ ] `MIN_GEM_SCORE=50.0`
- [ ] `MIN_LIQUIDITY_USD=15000`
- [ ] `EXPRESS_LANE_SCORE=80.0`

### API Keys
- [ ] `ONEINCH_API_KEY` — confirmed working
- [ ] `CMC_API_KEY` — confirmed working (or optional)
- [ ] `ETHERSCAN_API_KEY` — confirmed working
- [ ] `TOKENSNIFFER_API_KEY` — confirmed working
- [ ] `MORALIS_API_KEY` — confirmed working (or optional)
- [ ] `LUNARCRUSH_API_KEY` — confirmed working (or optional)
- [ ] `SLACK_WEBHOOK_URL` — notifications flowing

### Safety Verification
- [ ] GoPlus API test: known honeypot → REJECTED ✅
- [ ] GoPlus API test: known safe token → PASSED ✅
- [ ] Honeypot.is test: simulation working
- [ ] Token Sniffer test: scam token scores < 50
- [ ] Blocklist loaded — `config/tokens.py` has entries

### Paper Mode Validation (MANDATORY)
- [ ] 48+ hours of stable paper trading ✅
- [ ] 50+ paper trades executed ✅
- [ ] Win rate tracked and acceptable (> 45%)
- [ ] No crashes or critical errors
- [ ] Heartbeat stable (5-min intervals, no gaps)
- [ ] All active chains producing candidates
- [ ] Stop-losses executing correctly
- [ ] Take-profits triggering correctly

---

## Go-Live Procedure
```
1. Stop paper mode bot
2. Double-check all .env settings above
3. Verify wallet balances on each chain
4. Set MODE=live in .env
5. python main.py
6. Watch first 3 trades CLOSELY in Slack
7. If anything weird → MODE=paper immediately
8. Monitor continuously for first 6 hours
9. Check in every 2 hours for first 48 hours
```

## First 24 Hours: What to Watch
| Check | Expected | Action if Wrong |
|-------|----------|-----------------|
| Safety checks | Rejecting honeypots, passing safe tokens | STOP — safety is broken |
| Position sizing | ~$125-250 per trade | Review PARAMETERS if wrong |
| Stop-losses | Firing at -8% | STOP — critical risk failure |
| Gas costs | < 2% of position on L2s | Increase min position size |
| Win rate | Not terrible (> 35% in 24h) | Normal early, keep watching |
| Heartbeat | Every 5 minutes | Restart if gaps > 10 min |
| Notifications | Slack alerts on every trade | Fix webhook if missing |

## First Week Milestones
| Day | Check |
|-----|-------|
| Day 1 | Bot running stable, all safety checks working |
| Day 2 | First profitable trades, stop-losses tested |
| Day 3 | Reviewed trade journal, no anomalies |
| Day 5 | Portfolio direction: up, flat, or down? |
| Day 7 | Full weekly review — see MODEL_EVALUATION.md |

## Emergency: Something Goes Wrong
| Severity | Action |
|----------|--------|
| Single bad trade | Normal — stop-loss handled it |
| 3+ losses in a row | Check if signal quality is degraded |
| Bug in execution | `MODE=paper` → fix → re-validate → resume |
| Wallet compromise | KILL SWITCH → transfer all funds → new wallet |
| Market crash | Circuit breaker auto-triggers → wait 48h |
