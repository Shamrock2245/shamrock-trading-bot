# Walk-forward results (offline, proposals only)

Generated 2026-10-21T21:11:27.385856-04:00 · window 2026-05-27T22:20 → 2026-10-21T20:20 ET
Coins replayed: 55 · returns are % of notional, unlevered, net of 0.09% fees + 5 bps stop slippage

## Full period (allowlist coins)

- Current paper baseline: n=822 · WR 25% · PF 0.77 · avg -0.145% · avgR -0.10 · Σ -118.9% · maxDD -136.9% · 5.6/day
- Pre-fix config (BE 0.05, stretched kept): n=828 · WR 26% · PF 0.75 · avg -0.163% · avgR -0.12 · Σ -134.9% · maxDD -135.5% · 5.64/day
- Pre-fix + no paper SL/TP enforcement (old paper): n=402 · WR 29% · PF 0.98 · avg -0.025% · avgR +0.09 · Σ -10.1% · maxDD -105.3% · 2.74/day

Baseline exit mix: hard_loss_cap 1 (-5.1%), loss_timeout 72 (-41.9%), sl_hit 275 (-403.6%), tp_hit 54 (+132.2%), trail_stop 420 (+199.6%)

## One factor at a time (vs baseline)

| factor | value | result |
|---|---|---|
| exec_bar | 52 | n=826 · WR 26% · PF 0.77 · avg -0.148% · avgR -0.10 · Σ -121.9% · maxDD -134.5% · 5.62/day |
| exec_bar | 56 (baseline) | n=822 · WR 25% · PF 0.77 · avg -0.145% · avgR -0.10 · Σ -118.9% · maxDD -136.9% · 5.6/day |
| exec_bar | 60 | n=814 · WR 26% · PF 0.79 · avg -0.133% · avgR -0.09 · Σ -108.5% · maxDD -125.2% · 5.54/day |
| exec_bar | 64 | n=789 · WR 25% · PF 0.72 · avg -0.197% · avgR -0.13 · Σ -155.3% · maxDD -162.6% · 5.37/day |
| exec_bar | 68 | n=741 · WR 25% · PF 0.7 · avg -0.221% · avgR -0.15 · Σ -163.9% · maxDD -170.1% · 5.04/day |
| shorts | False (baseline) | n=822 · WR 25% · PF 0.77 · avg -0.145% · avgR -0.10 · Σ -118.9% · maxDD -136.9% · 5.6/day |
| shorts | True | n=872 · WR 24% · PF 0.74 · avg -0.164% · avgR -0.12 · Σ -143.1% · maxDD -168.1% · 5.94/day |
| toxic_block | True (baseline) | n=822 · WR 25% · PF 0.77 · avg -0.145% · avgR -0.10 · Σ -118.9% · maxDD -136.9% · 5.6/day |
| toxic_block | False | n=831 · WR 25% · PF 0.75 · avg -0.161% · avgR -0.12 · Σ -134.1% · maxDD -148.5% · 5.66/day |
| be_buffer | 0.05 | n=822 · WR 26% · PF 0.79 · avg -0.135% · avgR -0.09 · Σ -110.6% · maxDD -126.2% · 5.6/day |
| be_buffer | 0.12 (baseline) | n=822 · WR 25% · PF 0.77 · avg -0.145% · avgR -0.10 · Σ -118.9% · maxDD -136.9% · 5.6/day |
| stretched | keep | n=828 · WR 25% · PF 0.72 · avg -0.179% · avgR -0.12 · Σ -148.5% · maxDD -149.1% · 5.64/day |
| stretched | demote10 (baseline) | n=822 · WR 25% · PF 0.77 · avg -0.145% · avgR -0.10 · Σ -118.9% · maxDD -136.9% · 5.6/day |
| stretched | reject | n=799 · WR 24% · PF 0.73 · avg -0.176% · avgR -0.12 · Σ -140.3% · maxDD -157.6% · 5.44/day |
| timeout_h | 2.5 | n=822 · WR 24% · PF 0.74 · avg -0.158% · avgR -0.11 · Σ -130.2% · maxDD -141.5% · 5.6/day |
| timeout_h | 4.0 (baseline) | n=822 · WR 25% · PF 0.77 · avg -0.145% · avgR -0.10 · Σ -118.9% · maxDD -136.9% · 5.6/day |
| timeout_h | 8.0 | n=822 · WR 26% · PF 0.82 · avg -0.112% · avgR -0.08 · Σ -92.0% · maxDD -114.7% · 5.6/day |

## Entry hour (ET), baseline without toxic block

| hour | result |
|---|---|
| 0 | n=352 · WR 25% · PF 0.75 · avg -0.163% · avgR -0.10 · Σ -57.5% · maxDD -77.7% |
| 1 | n=76 · WR 28% · PF 0.88 · avg -0.084% · avgR -0.08 · Σ -6.3% · maxDD -17.3% |
| 2 | n=105 · WR 32% · PF 1.12 · avg +0.063% · avgR -0.01 · Σ +6.7% · maxDD -11.8% |
| 3 | n=72 · WR 26% · PF 0.87 · avg -0.083% · avgR -0.10 · Σ -5.9% · maxDD -18.5% |
| 4 | n=46 · WR 15% · PF 0.56 · avg -0.255% · avgR -0.10 · Σ -11.7% · maxDD -12.2% |
| 5 | n=41 · WR 7% · PF 0.16 · avg -0.575% · avgR -0.41 · Σ -23.6% · maxDD -23.6% |
| 6 | n=26 · WR 15% · PF 0.34 · avg -0.396% · avgR -0.28 · Σ -10.3% · maxDD -10.3% |
| 7 | n=21 · WR 29% · PF 0.82 · avg -0.103% · avgR -0.12 · Σ -2.2% · maxDD -7.3% |
| 8 | n=15 · WR 20% · PF 0.31 · avg -0.693% · avgR -0.33 · Σ -10.4% · maxDD -10.4% |
| 9 | n=14 · WR 43% · PF 1.72 · avg +0.372% · avgR +0.02 · Σ +5.2% · maxDD -4.0% |
| 10 | n=13 · WR 8% · PF 0.18 · avg -0.776% · avgR -0.58 · Σ -10.1% · maxDD -12.4% |
| 11 | n=12 · WR 8% · PF 0.42 · avg -0.405% · avgR -0.55 · Σ -4.9% · maxDD -6.8% |
| 12 | n=7 · WR 43% · PF 1.95 · avg +0.452% · avgR +0.16 · Σ +3.2% · maxDD -1.7% |
| 13 | n=4 · WR 50% · PF 3.75 · avg +0.697% · avgR +0.39 · Σ +2.8% · maxDD -1.0% |
| 14 | n=4 · WR 25% · PF 1.5 · avg +0.175% · avgR +0.04 · Σ +0.7% · maxDD -1.4% |
| 15 | n=6 · WR 17% · PF 0.22 · avg -1.350% · avgR -0.28 · Σ -8.1% · maxDD -10.4% |
| 16 | n=5 · WR 40% · PF 1.74 · avg +0.330% · avgR +0.44 · Σ +1.6% · maxDD -2.0% |
| 17 | n=3 · WR 0% · PF 0.0 · avg -1.581% · avgR -0.90 · Σ -4.7% · maxDD -4.7% |
| 18 | n=1 · WR 0% · PF 0.0 · avg -1.264% · avgR -1.12 · Σ -1.3% · maxDD -1.3% |
| 19 | n=2 · WR 100% · PF 999.0 · avg +1.749% · avgR +1.02 · Σ +3.5% · maxDD 0.0% |
| 20 | n=1 · WR 100% · PF 999.0 · avg +3.392% · avgR +1.12 · Σ +3.4% · maxDD 0.0% |
| 21 | n=2 · WR 0% · PF 0.0 · avg -0.772% · avgR -0.43 · Σ -1.5% · maxDD -1.5% |
| 22 | n=1 · WR 0% · PF 0.0 · avg -1.639% · avgR -0.61 · Σ -1.6% · maxDD -1.6% |
| 23 | n=2 · WR 0% · PF 0.0 · avg -0.530% · avgR -0.29 · Σ -1.1% · maxDD -1.1% |

## Allowlist out-of-sample (after 2026-07-27, when it was formed)

- Allowlist: n=518 · WR 27% · PF 0.94 · avg -0.033% · avgR -0.04 · Σ -17.0% · maxDD -46.0% · 5.96/day
- Hard-banned: n=510 · WR 28% · PF 0.74 · avg -0.192% · avgR -0.06 · Σ -98.0% · maxDD -102.4% · 5.87/day
- Others: n=325 · WR 27% · PF 0.79 · avg -0.133% · avgR -0.03 · Σ -43.4% · maxDD -53.5% · 3.74/day

## Walk-forward (train → pick best config → unseen test)

- OOS selected configs: n=241 · WR 28% · PF 0.85 · avg -0.099% · avgR -0.11 · Σ -23.8% · maxDD -34.8% · 3.01/day
- OOS fixed baseline: n=489 · WR 26% · PF 0.89 · avg -0.059% · avgR -0.07 · Σ -28.9% · maxDD -47.7% · 6.11/day

| train | test | chosen | train | test | baseline test |
|---|---|---|---|---|---|
| 2026-05-28→2026-07-26 | 2026-07-27→2026-08-15 | none (no config with ≥20 trades and +expectancy) | 0 trades | 0 trades | n=124 · WR 22% · PF 0.78 · avg -0.105% · avgR -0.10 · Σ -13.1% · maxDD -22.3% · 6.2/day |
| 2026-06-20→2026-08-18 | 2026-08-19→2026-09-07 | none (no config with ≥20 trades and +expectancy) | 0 trades | 0 trades | n=126 · WR 30% · PF 1.09 · avg +0.049% · avgR +0.03 · Σ +6.2% · maxDD -17.1% · 6.3/day |
| 2026-07-12→2026-09-09 | 2026-09-10→2026-09-29 | bar60|L+S|tox|be0.05|demote10|to8.0 | n=364 · WR 29% · PF 1.05 · avg +0.029% · avgR -0.03 · Σ +10.5% · maxDD -36.9% | n=121 · WR 27% · PF 0.73 · avg -0.182% · avgR -0.18 · Σ -22.1% · maxDD -33.4% · 6.05/day | n=119 · WR 25% · PF 0.74 · avg -0.171% · avgR -0.15 · Σ -20.3% · maxDD -32.7% · 5.95/day |
| 2026-08-04→2026-10-02 | 2026-10-03→2026-10-22 | bar60|L|noTox|be0.12|demote10|to8.0 | n=360 · WR 31% · PF 1.18 · avg +0.092% · avgR +0.01 · Σ +33.3% · maxDD -34.4% | n=120 · WR 29% · PF 0.98 · avg -0.015% · avgR -0.03 · Σ -1.8% · maxDD -16.8% · 6.0/day | n=120 · WR 28% · PF 0.97 · avg -0.015% · avgR -0.04 · Σ -1.8% · maxDD -14.9% · 6.0/day |

Limitations: 1h bars (conservative intrabar order), no historical OI/dVol ctxs, no Predator regime classifier / expectancy gate / hot streak / sizing; correlation guard off. Use for relative comparisons.
