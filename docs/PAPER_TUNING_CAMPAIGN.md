# Paper Tuning Campaign (2–3 Weeks)

## Direct answer

**Yes — while the bot is tuned, everything must stay in paper mode.**  
Tuning (Optuna, ML weight optimizer, LLM auto-tuner, self-improving agent) only mutates **parameters** and journals **simulated** trades. It must **never** place real Hyperliquid, Jupiter, or 1inch orders.

| Layer | Paper behavior |
|-------|----------------|
| Spot / gem executor | `TradeExecutor(is_paper=True)` → `PAPER_TX` |
| Solana buy/sell | Early return `PAPER_TX` |
| Hyperliquid perps | Simulated open/close + blocked signed SDK calls |
| Auto-tuner / Optuna | Replays history; writes `output/optuna_best_params.json` |
| Paper→live promoter | **Blocked** while `PAPER_MODE_LOCKED=true` and campaign active |

## What was wrong before

`main.py` previously **forced `MODE=live` for Hyperliquid** even when the rest of the bot was paper. That is fixed: HL respects global `MODE`.

## Campaign defaults

```env
MODE=paper
PAPER_MODE_LOCKED=true
PAPER_TUNING_CAMPAIGN_ENABLED=true
PAPER_TUNING_CAMPAIGN_DAYS=21
ML_WEIGHT_OPTIMIZER_ENABLED=true
OPTUNA_ENABLED=true
OPTUNA_AUTO_APPLY=true
WINNING_RISK_MANAGER_ENABLED=true
WINNING_ENTRY_FILTER_ENABLED=true
```

On first run, `output/paper_tuning_campaign.json` records the start timestamp.  
Auto-promotion cannot fire until:

1. **≥ campaign days** have elapsed (default **21** ≈ 3 weeks), **and**
2. **`PAPER_MODE_LOCKED=false`** is set deliberately, **and**
3. Paper journal metrics meet floors (default ≥50 closes, WR ≥50%, PF ≥1.30), **and**
4. Gas + keys checks in `core/paper_to_live_promoter.py` pass.

## Honest expectation (parabolic gains)

Paper tuning **improves parameters** and **measures** expectancy. It does **not** guarantee “parabolic” live returns.

- Historical HL book (see `docs/PROFITABILITY_PIVOT_PLAN.md`) was **negative expectancy** (WR ~37%, PF ~0.68).
- A successful campaign means: **paper PF ≥ 1.3**, controlled drawdown, stable process — *then* consider micro-size live.
- “Parabolic” equity curves come from **compounding a real edge + capital**, not from enabling more scanners.

## How to run (paper only)

```bash
# Local
MODE=paper PAPER_MODE_LOCKED=true python main.py
# or
python scripts/paper_trade.py

# Docker (paper locked by compose defaults)
docker compose up -d bot auto-tuner dashboard health
# Optional dedicated paper profile:
docker compose --profile paper up -d
```

Confirm logs:

```text
Mode: PAPER
📄 HL Perps PAPER mode — real orders disabled
📄 PAPER MODE: blocked Hyperliquid signed call ...
🤖 Auto-Tuning Service ... PAPER_MODE_LOCKED=True
```

## After 2–3 weeks (manual unlock checklist)

1. Review `output/trades.json` / `output/hl_paired_trades.json` / Optuna best params.
2. Confirm PF / WR / DD gates in this doc.
3. Set `PAPER_MODE_LOCKED=false` and `MODE=live` **only if** you accept real risk.
4. Redeploy with a **small** `HYPERLIQUID_MAX_POSITION_USD` / notional caps.
5. Never force-live HL in code again.

## Related

- `docs/PAPER_TRADING.md` — paper pipeline behavior  
- `docs/LIVE_TRADING.md` — pre-live checklist  
- `docs/PROFITABILITY_PIVOT_PLAN.md` — measured reality vs hype  
- `scripts/auto_tuner_service.py` — hourly XGBoost + Optuna + self-audit  
