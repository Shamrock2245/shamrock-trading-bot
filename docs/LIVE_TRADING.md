# LIVE TRADING — Going Live Safely

## ⚠️ READ THIS ENTIRE DOCUMENT BEFORE ENABLING LIVE MODE ⚠️

## Pre-Live Checklist

### Environment Setup
- [ ] `.env` file has real `WALLET_PRIVATE_KEY_PRIMARY`
- [ ] `.env` file has real `SOLANA_PRIVATE_KEY_PRIMARY`
- [ ] `MODE=live` set in `.env`
- [ ] All API keys populated (1inch, CMC, Etherscan, TokenSniffer, Moralis)
- [ ] `SLACK_WEBHOOK_URL` configured for real-time alerts
- [ ] Private keys are ONLY in `.env` (gitignored) — never in code

### Safety Verification
- [ ] GoPlus API responding correctly
- [ ] Honeypot.is API responding correctly
- [ ] Token Sniffer API responding correctly
- [ ] Blocklist loaded (`config/tokens.py`)
- [ ] Safety pipeline tested with known good AND known bad tokens

### Risk Parameters Confirmed
- [ ] `MAX_POSITION_SIZE_PERCENT` = 2.0 (or lower)
- [ ] `STOP_LOSS_PERCENT` = 10.0
- [ ] `HARD_STOP_LOSS_PERCENT` = 25.0
- [ ] `CIRCUIT_BREAKER_PERCENT` = 15.0
- [ ] `DAILY_LOSS_LIMIT_ETH` = 0.5
- [ ] `MAX_GAS_GWEI` = 50

### Infrastructure
- [ ] All RPC endpoints responding (check each active chain)
- [ ] Wallet has sufficient ETH/SOL for gas
- [ ] Database initialized
- [ ] Logging configured to capture all events
- [ ] Heartbeat monitoring active

### Paper Mode Validation
- [ ] 48+ hours of stable paper trading completed
- [ ] 50+ paper trades executed
- [ ] Win rate acceptable (> 50%)
- [ ] No critical errors in logs

## Go-Live Procedure
1. Stop the paper trading bot
2. Update `.env`: `MODE=live`
3. Double-check wallet balances on all active chains
4. Start the bot: `python main.py`
5. Watch the first 5 trades closely in Slack/Telegram
6. Keep monitoring for the first 24 hours

## First 24 Hours: What to Watch
- Are safety checks passing/failing correctly?
- Are positions being sized correctly?
- Are stop-losses executing?
- Is the heartbeat stable?
- Are notifications arriving?
- Are gas costs reasonable?

## Emergency Procedures
If anything goes wrong:
1. **Set `MODE=paper` immediately** — or use Kill Switch
2. Check open positions manually on chain
3. Close any positions that shouldn't be open
4. Review error logs
5. Fix the issue in paper mode
6. Repeat pre-live checklist before going live again
