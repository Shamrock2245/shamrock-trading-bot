# Entry-signal research — selective entries, walk-forward (2026-10-26)

**Verdict: nothing ships.** No candidate met the bar (OOS PF ≥ 1.15, reasonable
trade count, full-period PF > 1.0). Trading logic is unchanged; this PR is docs only.

## Setup
- Window: 2026-05-28 → 2026-10-21 (ET), HL perps allowlist, long signals only.
- Signal pool: 18,220 allowlist long signals from the live scanner logic, replayed
  on 1h candles with the current paper exit (TP1 partial + trail) and an emulation
  of the live autoban.
- Walk-forward: 60-day train, then 4 out-of-sample folds of 20 days each.
  Filters/thresholds were chosen on in-sample data only; OOS PF is the judge.
- Candidates tested: **16 this round + 27 in the previous round = 43 total.**
  With that many tries, an OOS PF just above 1.0 would be expected by luck alone —
  hence the 1.15 bar.

## Results (OOS = the 4 out-of-sample folds pooled)

| Candidate | Fire rate | OOS PF | OOS n | Full PF |
|---|---|---|---|---|
| **Baseline (all signals)** | 100% | **0.88** | 461 | **0.89** |
| Vol contraction → expansion breakout | 1.9% | 0.59 | 79 | 0.46 |
| Bollinger squeeze breakout | 6.7% | 0.66 | 175 | 0.61 |
| Contraction OR squeeze | — | 0.72 | 194 | 0.62 |
| Relative volume > 2× | 13.9% | 0.90 | 326 | 0.82 |
| Relative volume > 3× | 7.2% | 0.97 | 279 | 0.89 |
| Rel-vol > 2× + green candle | — | 0.87 | — | 0.78 |
| MTF trend 1h + 4h | 85% | 0.80 | — | 0.71 |
| MTF trend 1h + 4h + 1d | 69% | 0.81 | — | 0.78 |
| MTF + rel-vol > 2× | — | 0.85 | — | 0.67 |
| MTF + green candle | — | 0.93 | 411 | 0.85 |
| MTF 4h + 1d + contraction/squeeze | — | 0.70 | — | 0.72 |
| Rel-vol + contraction/squeeze | — | 0.69 | — | 0.75 |
| MTF + score ≥ 64 | — | 0.77 | — | 0.75 |
| Coin-select: trailing PF > 1.0 | — | 0.71 | — | 0.71 |
| Coin-select: trailing PF > 1.3 | — | 0.87 | 167 | 0.89 |
| Coin-select + MTF | — | 0.70 | — | 0.81 |

**Honest walk-forward selection** (each fold picks the best candidate on its own
in-sample data, then trades it OOS — picks were rel-vol>3×, rel-vol>3×, squeeze,
MTF+green): **OOS PF 0.71, n = 287.** Worse than baseline; the in-sample winners
did not hold up.

## Not testable yet
- **Funding rate / open interest filters.** The candle recorder only began writing
  `asset_ctxs.csv` on 2026-10-21 9:51 PM ET (~6k rows, 55 coins), after the end of
  the signal window. Revisit once there are ~6–8 weeks of funding/OI history.

## Takeaways
- The best single filter (rel-vol > 3×, OOS PF 0.97) still loses money; no
  volatility-breakout or multi-timeframe filter turns the entry into an edge.
- Coin selection by trailing PF does not persist out of sample.
- The entry signal itself is the weak link; filtering it harder only shrinks the
  sample. Next candidates: funding/OI once data exists, and exit-side work
  (already under the paper exit A/B, which this research did not touch).

Scripts: `/workspace/bt_entry/entry_exp.py`, `entry_exp2.py` (research box, not in repo).
