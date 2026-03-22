# TRADE JOURNAL — Every Trade Gets Recorded

## Why Journal
- **Accountability** — know exactly what happened and why
- **Learning** — identify what works and what doesn't
- **Debugging** — trace back any issue to its trade
- **Tax compliance** — complete transaction records

## Journal Entry Format
Each trade records:
```
Trade #: 00142
Timestamp: 2026-03-22T19:15:00Z
Mode: paper | live
Chain: base
Token: PEPE (0x6982508...)
Pair: PEPE/WETH (0xabc123...)
Direction: BUY
Gem Score: 84.2 (Express Lane ✅)
Signal Sources: DexScreener boost, volume spike 7.3x, smart money hit

Entry:
  Price: $0.00001234
  Amount: 1,200,000 PEPE
  Cost: $150.00
  Gas: $0.03
  TX: 0xdef456...

Exit (if closed):
  Price: $0.00002468
  Amount Sold: 600,000 PEPE (50% at TP1)
  Proceeds: $148.08
  Gas: $0.02
  TX: 0xghi789...

Result:
  P/L: +$98.05 (+65.4%)
  Hold Time: 4h 32m
  Exit Reason: Take-profit-1 hit

Scoring Breakdown:
  Age: 95 | Volume: 85 | Liquidity: 70 | Contract: 80 | 
  Holder: 60 | Tax: 100 | Social: 75 | Boost: 80 |
  Smart Money: 65 | TVL: 40 | Sentiment: 55 | 
  Holder Conc: 50 | Unlock Risk: 70
```

## Journal Storage
- **Primary:** `output/trades.json` (machine-readable)
- **Database:** SQLite `data/shamrock_trading.db`
- **Logs:** `logs/` directory (human-readable)

## Analysis Queries (Run Periodically)
- Win rate by chain
- Win rate by gem score range
- Average hold time for winners vs losers
- P/L by signal source
- Best/worst time windows (UTC)
- Express lane vs standard lane performance
