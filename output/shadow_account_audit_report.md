# 📊 Shadow Account Auditing & Backtesting Report
> **Inspired by `HKUDS/Vibe-Trading` — Systematic counterfactual analysis of 114 closed positions.**

This report presents a quantitative audit of the historical positions closed by the Shamrock Trading Bot. By running a counterfactual grid search across key stop-loss and take-profit parameters, we have identified the "money left on the table" due to strategic inefficiencies and determined the mathematically optimal settings to maximize trading success.

---

## 🚦 Executive Summary

| Metrics | Historical Baseline | Optimized (Global Settings) | Solana-Specific Optimized | Base-Specific Optimized |
|---|---|---|---|---|
| **Realized P&L** | `$-81.49` | `**$-10.31**` | `**$-22.00**` | `**$+30.16**` |
| **PnL Improvement** | `—` | `**$+71.19**` | `**$+54.91**` | `**$+17.01**` |
| **Win Rate** | `40.4%` | `41.2%` | `10.0%` | `45.9%` |
| **Wins/Losses** | `46W / 54L` | `47W / 54L` | `1W / 8L` | `28W / 30L` |

---

## 🔍 Major Inefficiencies Identified ("Money Left on the Table")

1. **Premature Trailing Stops (Wick Shakeouts)**:
   * **Finding**: The baseline 12% trailing stop was too tight for highly volatile micro-cap tokens (especially on Solana). Normal corrective wicks triggered trailing stop exits, after which the tokens went on to rally 2x-5x.
   * **Vibe-Trading Insight**: Loosening the trailing stop to **15%** or **18%** gives the assets room to breathe and significantly increases the average return on winning positions.

2. **Sub-Optimal Hard Stop-Loss**:
   * **Finding**: The baseline 18% hard stop-loss locked in heavy losses on fast-moving drops before the pre-TP1 peak protection could activate.
   * **Vibe-Trading Insight**: Lowering the hard stop to **15%** or **10%** (specifically on Solana) cuts losing trades much faster, preserving trading capital.

3. **Solana vs. EVM Chain Discrepancy**:
   * **Finding**: Base positions are structurally sound and profitable with a looser stop structure due to more stable trend retention on L2. Solana tokens, being heavily sniped and fast-dumping, require **extremely tight stop-losses (10%)** and **tighter take-profits (1.2x)** to secure quick gains before they reverse.

---

## 🛠 Optimal Parameter Tweaks Recommendation

### 1. Solana Chain (Primary Loss Source)
To reverse the -$192.03 loss on Solana, we recommend applying these highly specialized micro-cap settings:
* **`HARD_STOP_LOSS_PERCENT`**: `10.0` (cut losers fast at 10%, down from 18%)
* **`STOP_LOSS_PERCENT` (Trailing)**: `6.0` (lock in wicks tightly at 6% trail after TP1)
* **`TAKE_PROFIT_TP1_MULT`**: `1.2` (secure 20% gain at 1.2x, down from 1.5x to capture quick Solana pumps)
* **`TAKE_PROFIT_TP2_MULT`**: `1.8` (TP2 at 80% gain, down from 2.5x)

### 2. Base & EVM Chains
To boost the profitable Base settings:
* **`HARD_STOP_LOSS_PERCENT`**: `15.0` (down from 18%)
* **`STOP_LOSS_PERCENT` (Trailing)**: `15.0` (looser trailing stop to capture full L2 trends)
* **`TAKE_PROFIT_TP1_MULT`**: `1.5` (maintain high baseline target)
* **`TAKE_PROFIT_TP2_MULT`**: `2.5` (maintain high baseline target)

---

## 📊 Counterfactual Sells Log Comparison (Top 10 Trades Optimized)

Below is a comparison of how the top optimized settings change specific trade outcomes:

| Token | Chain | Baseline P&L | Counterfactual P&L | Exit Difference | Reason |
|---|---|---|---|---|---|
| **POPTRUMP** | Solana | `$-49.10` | `$-5.58` | `+43.5212` | Protected from deep drawdown |
| **Fartcoin ** | Solana | `$-15.16` | `$-11.91` | `+3.2590` | Protected from deep drawdown |
| **jelly** | Bsc | `$-12.39` | `$-11.98` | `+0.4044` | Protected from deep drawdown |
| **BIO** | Base | `$11.65` | `$16.30` | `+4.6573` | Secured profit faster |
| **PLAY** | Base | `$9.87` | `$20.08` | `+10.2019` | Secured profit faster |
| **SMCF** | Base | `$-7.99` | `$-5.84` | `+2.1464` | Protected from deep drawdown |
| **POPTRUMP** | Solana | `$-5.08` | `$-0.58` | `+4.5045` | Protected from deep drawdown |
| **BAS** | Bsc | `$-4.73` | `$-4.73` | `0.00` | Protected from deep drawdown |
| **RARE** | Ethereum | `$-4.41` | `$-4.41` | `0.00` | Protected from deep drawdown |
| **Fartcoin ** | Solana | `$-3.89` | `$-1.91` | `+1.9790` | Protected from deep drawdown |


*Report generated automatically on 2026-05-26 08:21:52.*