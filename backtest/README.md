# Offline walk-forward backtester (research only)

Nothing in `backtest/` is imported by the live bot. vectorbt is an offline-only dependency.

```bash
pip install -r requirements-ci.txt -r backtest/requirements.txt   # Python 3.11/3.12
python -m backtest.walk_forward --out reports/backtest --cache data/candles      # all 55 coins, ~45 min
python -m backtest.walk_forward --coins BTC,INJ --days 120 --out /tmp/bt          # quick run
```

- `hl_data.py`: public Hyperliquid info API (candleSnapshot, fundingHistory) plus a CSV cache.
- `candle_recorder.py`: the `candle-recorder` compose service. It records 1h and 15m candles and funding/OI snapshots to `data/candles/` every hour, because HL only serves the latest 5000 bars. It runs with no `.env` and no keys.
- `replay.py`: replays history bar by bar through the real `HLPerpsScanner` scoring.
- `sim.py`: exit simulation that mirrors the Winning v32 monitor (BE, TP1, trail ladder, 45-min rule, loss timeout, hard cap).
- `walk_forward.py`: config grid, portfolio caps, one-factor tables, hour profile, allowlist OOS, and vectorbt `rolling_split` walk-forward (train 60d → test 20d).

Results are **proposals only**. Any setting change still goes through a paper PR and the Predator gate (≥50 closes, WR ≥50%, PF ≥1.30).
