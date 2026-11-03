# Alternative strategy research: mean reversion + funding carry (2026-11-03)

**Verdict: nothing clears the bar robustly. Trading logic is unchanged; this PR is docs + offline scripts only.**
One candidate is worth a frozen-parameter *paper forward test* (1h RSI(14) ≤ 20 long-only
"capitulation buy"). Funding carry and short-side mean reversion fail and should be dropped.

Context: the Fib+TA entry produced 0 signals in ~2,000 scans / 72h; Hyperliquid paper book is
31 closes, WR 32.3%, PF 0.29. Brendan asked for a mean-reversion / funding-carry backtest (t22s10).

## Setup
- Data: Hyperliquid `candleSnapshot` 1h (2026-03-28 → 2026-11-03 10:00 AM ET, ~220 days) and
  `fundingHistory` (hourly) for the 18-coin Predator allowlist + ETH + SOL (BTC is on the allowlist).
  15m: only ~52 days available from the API (5,000-bar cap), so 15m is low-confidence.
- Universes: **all** (20 coins) and **noban** (hard-ban list respected → ETH, SOL dropped; 18 coins).
- Costs: taker 4.5 bps/side (same as `backtest/sim.py`) + 5 bps adverse slippage on **both** entry and
  exit (stricter than `sim.py`, which slips exits only), plus hourly funding paid/received on every
  hour held. P&L shown as $ on a flat $100 notional per trade, 1×, no compounding.
- Execution: signal on 1h bar close → enter next bar open. ATR(14) stop checked intrabar first
  (stop assumed before target in the same bar; gaps fill at the open). One position per coin at a time.
- Walk-forward: rolling 60-day train → 20-day test, 8 folds; OOS = 2026-05-29 → 2026-11-03 ET
  (~158 days). Each fold picks the best variant on its own in-sample data (PF, min 20 IS trades),
  trades it OOS. Bar: **OOS PF ≥ 1.15 with ≥ 40 OOS trades**.
- 15m: same grids with 21-day train / 7-day test.

## Variants tried (small grids)
- **Mean reversion (32 per direction):** signal ∈ {z-score vs 24h SMA ≥ 2 / 2.5σ, z vs 48h SMA ≥ 2 / 2.5σ,
  RSI(14) ≤ 25 / ≤ 20 (≥ 75 / ≥ 80 for shorts), VWAP(24h) deviation ≥ 2 / 3 ATR} × time stop {12h, 24h}
  × ATR stop {2×, 3×}. Exit on reversion (close back through the mean / RSI 50 / VWAP).
  Run long-only, short-only, and both.
- **Funding carry (16 per direction):** short when 3h-avg funding ≥ {0.005%, 0.01%}/h (~44% / ~88% APR);
  long when ≤ −half that. Exit when 8h-avg funding normalises, or max hold {24h, 72h}; ATR stop {none, 3×};
  price filter {off, trend-agrees (close vs 48h SMA)}. Funding payments included in P&L.
- Total: 96 MR + 48 FC variant-direction combos per timeframe per universe
  (**576 backtest configurations** across 1h/15m × all/noban). Plus 4 robustness checks on the one survivor.

## Results — honest walk-forward OOS (1h)

| Strategy | Universe | OOS PF | WR | OOS trades | Net ($100/trade) | Max DD | Trades/wk | Clears bar? |
|---|---|---|---|---|---|---|---|---|
| **MR long-only** | all | **1.18** | 51.3% | 199 | +$47.94 | $91.03 | 8.8 | narrowly (see caveats) |
| **MR long-only** | noban | **1.18** | 52.0% | 173 | +$43.30 | $82.47 | 7.6 | narrowly (see caveats) |
| MR short-only | all | 0.82 | 50.5% | 1,060 | −$305.44 | $477.23 | 46.8 | no |
| MR long+short | all | 0.97 | 50.4% | 1,097 | −$43.07 | $313.04 | 48.5 | no |
| FC short (collect +funding) | all | 0.93 | 52.7% | 146 | −$16.26 (funding +$14.71) | $63.60 | 6.4 | no |
| FC long (collect −funding) | all | 0.94 | 46.3% | 246 | −$16.41 (funding +$18.87) | $74.53 | 10.9 | no |
| FC long+short | all | 0.90 | 48.0% | 423 | −$63.95 (funding +$37.60) | $173.99 | 18.7 | no |
| FC (noban) | noban | 0.93–0.95 | — | 146–239 | −$14 to −$16 | — | — | no |

Grid breadth (full-period, variants with ≥ 40 trades): MR long 31/32 variants PF > 1 (median 1.10);
MR short 0/32 (median 0.86); FC 0/16 in every direction (median ~0.78).

**15m (52 days, low confidence):** MR long 0.81 (n 511); MR short 1.49 (n 221) but only 4/32 variants
are PF > 1 full-period (median 0.90) → looks like luck, not edge; FC short 1.44 on only 20 trades.
Nothing at 15m is credible with this little history.

## The one survivor: 1h oversold long (MR long-only) — caveats
Robustness checks (`robust.py`, `folds.py`, `cap.py`):
1. **Not market drift.** A random-entry long control (same coins, same count, same exits, 200 draws)
   has median PF 0.76, p95 1.35. The RSI ≤ 20 variant beats every draw.
2. **Fold-to-fold unstable.** Honest WF fold PFs: 0.30, 1.92, 0.04, 4.59, (no trades), 0.61, 1.62, 5.99.
   3 of 7 active folds lose. The 09-06 fold picked z48 and lost $48.84 on 72 trades.
3. **Clustered.** 199 trades fall on only 46 distinct days; up to **14 positions open at once**
   (market-wide dumps hit every coin together). One day (2026-06-24) is a third of the fixed variant's profit.
4. **Fails with a realistic position cap.** Capping concurrent MR positions at 3 → honest WF PF **0.93**
   (n 165, −$13.76); at 5 → **0.85**. The uncapped pass depends on buying every coin in a crash.
5. Fixed RSI(14) ≤ 20 / 12h time stop / 3×ATR stop / exit RSI ≥ 50 looks strong (OOS-window PF 3.3, n 88,
   WR 72%, +$140.79, DD $21.20; with cap 3: PF 1.70, n 64) and survives 10 bps slippage (PF 3.1) —
   **but it is a hindsight pick out of 32**, so it is not evidence on its own.

## Recommendation
- **Funding carry: drop.** Funding is collected (+$15–38 OOS) but price moves against crowded
  positions overwhelm it; 0 of 16 variants profitable in any direction. Directional-only carry on HL
  perps doesn't work here (a delta-neutral spot hedge was not tested).
- **Mean reversion shorts: drop.**
- **MR long (capitulation buy): forward test only.** If Brendan wants it, add it in paper behind a
  default-off flag via a tested PR with params **frozen now** (RSI(14) ≤ 20 on 1h close, enter next open,
  exit RSI ≥ 50 or 12h, 3×ATR stop, max 3 concurrent, allowlist minus hard-ban). It must earn the
  normal promote gate (≥ 50 paper closes, WR ≥ 50%, PF ≥ 1.30) on fresh data. Expect ~3 trades/week,
  arriving in bursts on market-wide dumps. No live change, no gate change, no exit A/B change.

## Reproduce
`docs/backtest/alt_strategy_2026-11-03/`: `fetch.py` (public HL info API → `data/`), `alt_bt.py [all|noban]`,
`alt_bt.py 15m [all|noban]`, `robust.py`, `folds.py`, `cap.py`. Offline only; never imported by the bot.
