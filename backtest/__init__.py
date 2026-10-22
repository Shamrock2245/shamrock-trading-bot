"""Offline research tooling — NOT imported by the live bot.

backtest/hl_data.py         Hyperliquid candle + funding history (API, paged, cached)
backtest/candle_recorder.py Records our own 1h/15m candles + asset ctxs going forward
backtest/replay.py          Replays the bot's own HLPerpsScanner.scan_coin over history
backtest/sim.py             Exit simulation mirroring Winning v32 rules (+ paper fixes)
backtest/walk_forward.py    vectorbt-split walk-forward over parameter grids → report

Proposals only: nothing here writes .env, settings, or live state.
"""
