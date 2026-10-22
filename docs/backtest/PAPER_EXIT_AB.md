# Paper exit A/B: structure stop vs 2×ATR stop + 8h loss timeout

**Status:** paper only, started 2026-10-21. Live is untouched.

## Arms
| arm | stop | loss timeout | everything else |
|---|---|---|---|
| `control` | structure/fib SL from the scanner (current) | `WINNING_LOSS_TIMEOUT_HOURS` (4h on the server) | same |
| `atr2x_8h` | entry ∓ `PAPER_EXIT_AB_ATR_MULT` (2.0) × ATR(14) on closed 1h candles | `PAPER_EXIT_AB_ATR_TIMEOUT_HOURS` (8h) | same |

"Everything else" means both arms share the same entry filter, TP, break-even (+0.75% → entry+0.12%), TP1 40% at +2%, trail ladder, 45-min rule (−1.5%), −$15 / −5% hard loss cap, and paper SL/TP trigger enforcement.

## How trades are split
Each trade's arm comes from `sha256("predator-ab-v1|COIN|UTC open hour")`. The low bit picks the arm, so every coin-hour is effectively a coin flip.
- The scanner's R/R check runs on the structure SL **before** the arm is applied, so both arms admit exactly the same signals.
- Why not alternate trades? Within a scan the best-scored signal always opens first, so a global even/odd counter would tie arm to rank. A hash is independent of score, rank, regime and restarts, needs no stored counter, and can be recomputed offline from `trades.json`.
- The expected split is 50/50. Small samples can drift by a few trades.
- If an `atr2x_8h` trade can't fetch candles, it keeps the structure SL, still gets the 8h timeout, and its open row has `ab_atr_fallback: true` so the review can exclude it.

## Where the tags show up
- **Open rows** in `output/trades.json` carry `exit_variant`, `ab_structure_sl` and `stop_loss` (the stop actually used). ATR-arm rows also carry `ab_atr_1h`, `ab_atr_mult`, `ab_loss_timeout_h` and `ab_atr_fallback`.
- **Close rows** (full closes and TP1 partials) carry `exit_variant`.
- **Positions** keep their arm across restarts, via `hl_paper_positions.json` and `hl_trailing_state.json`.
- **Gate:** `data/dashboard/predator_v1.json` → `paper_metrics.by_variant.{control,atr2x_8h,untagged}` holds closed_trades, positions_closed, win_rate, profit_factor, net_pnl and avg_pnl. `untagged` = closes from before the A/B. This is reporting only; the gate thresholds (50 / 50% / 1.30 overall) are unchanged.
- **Logs:** `📄 PAPER A/B <COIN> → <arm> | structure_sl=… | sl=… | atr=…`

## Caveats
- Size is per-trade margin, not risk-based, so the wider ATR stop risks more dollars per stopped trade. The hard cap still limits a single loss to −$15 / −5%.
- Compare the arms on PF and avg PnL per position, not on net PnL alone.

## Settings (Three-File Rule)
`PAPER_EXIT_AB_ENABLED=true`, `PAPER_EXIT_AB_ATR_MULT=2.0`, `PAPER_EXIT_AB_ATR_TIMEOUT_HOURS=8.0`, `PAPER_EXIT_AB_SALT=predator-ab-v1`
