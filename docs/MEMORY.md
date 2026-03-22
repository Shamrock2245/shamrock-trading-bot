# MEMORY — Learning from Past Trades

## What the Bot Remembers

### Trade Memory
- Every token ever traded (address, chain, result)
- Win/loss record per chain
- Average hold time for winners vs losers
- Best/worst performing time windows
- Which signal sources produced the most winners

### Token Memory
- Tokens that failed safety checks → added to blocklist
- Tokens that were rugged → permanent blocklist
- Tokens that generated 5x+ returns → watch for re-entries

### Pattern Memory
- Volume spike patterns that led to profitable trades
- DexScreener boost amounts correlated with outcomes
- CTO tokens: win rate vs normal tokens
- Time-of-day patterns (UTC hours with best results)

## How Memory Influences Decisions

### Positive Reinforcement
- Token previously generated profit → slightly positive bias (+5 score)
- Signal pattern matches a high-win-rate pattern → log it

### Negative Reinforcement
- Token previously failed safety → BLOCK permanently
- Token previously rugged → BLOCK permanently
- Chain had 5 consecutive losses → reduce position size on that chain

## Memory Storage
- **Short-term:** In-memory Python dicts (current session)
- **Long-term:** SQLite database + `output/trades.json`
- **Permanent:** Blocklists in `config/tokens.py`

## Future: ML-Based Learning
Phase 5 (planned): Feed trade journal into a classifier that adjusts signal weights based on actual outcomes. The model learns which signals predict profit and which are noise.
