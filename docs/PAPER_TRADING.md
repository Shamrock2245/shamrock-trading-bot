# PAPER TRADING — Practice Mode

## What It Is
Paper trading simulates all trade execution without touching real funds. The bot goes through the ENTIRE pipeline — scan, score, safety check, size, execute — but records the trade in a local journal instead of submitting a blockchain transaction.

## When to Use Paper Mode
- **First deployment** — always start in paper mode
- **New chain added** — 48 hours minimum in paper
- **New strategy deployed** — validate scoring + entry/exit logic
- **After major code changes** — confirm nothing is broken
- **After circuit breaker triggers** — validate recovery before going live again

## Configuration
```env
MODE=paper
```

## What Paper Mode Does
| Step | Paper Behavior | Live Behavior |
|------|---------------|--------------|
| Scanning | ✅ Real DexScreener data | ✅ Same |
| Scoring | ✅ Real scoring pipeline | ✅ Same |
| Safety checks | ✅ Real API calls | ✅ Same |
| Size calculation | ✅ Real portfolio math | ✅ Same |
| Trade execution | 📝 Logged only, no tx | 🔗 Real blockchain tx |
| Position monitoring | ✅ Tracks paper positions | ✅ Same |
| Stop-loss/TP | 📝 Simulated exits | 🔗 Real sell tx |
| Notifications | ✅ Sent (tagged [PAPER]) | ✅ Same |

## Paper Trade Validation Criteria
Before switching to live, paper trading must demonstrate:
- [ ] 50+ paper trades completed
- [ ] Win rate > 50%
- [ ] Average win > 1.5x average loss
- [ ] No safety check bypasses
- [ ] No unexpected errors or crashes
- [ ] Heartbeat stable for 48+ continuous hours
- [ ] All chains producing valid candidates

## Paper → Live Transition
See `LIVE_TRADING.md` for the full pre-live checklist.
