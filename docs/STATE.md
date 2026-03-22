# STATE — What the Bot Remembers Between Cycles

## State Files
| File | Location | Purpose |
|------|----------|---------|
| `output/positions.json` | Local JSON | All open positions with entry data |
| `output/trades.json` | Local JSON | Complete trade history |
| `data/shamrock_trading.db` | SQLite | Persistent database (positions, trades, scores) |
| `logs/` | Directory | Timestamped log files |

## Position State Schema
Each open position tracks:
```json
{
  "token_address": "0x...",
  "chain": "base",
  "symbol": "PEPE",
  "entry_price": 0.00001234,
  "entry_time": "2026-03-22T19:00:00Z",
  "amount": 1000000,
  "cost_basis_usd": 150.00,
  "stop_loss_price": 0.00001111,
  "take_profit_1": 0.00002468,
  "take_profit_2": 0.00006170,
  "gem_score": 78.5,
  "tx_hash": "0x...",
  "status": "open"
}
```

## State Persistence Rules
1. **Write after every trade** — entries, exits, partial sells
2. **Write after every position update** — stop-loss adjustments, price updates
3. **Atomic writes** — write to temp file, then rename (prevents corruption)
4. **Backup every hour** — copy state files to `output/backups/`
5. **Recover on crash** — on startup, load last known state from JSON

## What Happens on Restart
1. Load `output/positions.json` — restore open positions
2. Verify on-chain — confirm positions still exist (haven't been sold externally)
3. Resume monitoring — pick up where we left off
4. Log restart event — note any time gap
