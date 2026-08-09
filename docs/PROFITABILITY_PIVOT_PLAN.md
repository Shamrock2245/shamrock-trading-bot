# Shamrock Profitability Pivot Plan

**Date:** 2026-08-08  
**Status:** Proposal — execute only after owner approval on Phase 0 kill switches  
**Goal:** Stop the wash, cut burn, prove one real edge, then scale what compounds

---

## 0. Brutal truth (measured, not aspirational)

### Live Hyperliquid performance (source of truth: `output/hl_paired_trades.json`)

| Metric | Value |
|--------|------:|
| Closed paired trades | 530 |
| Net realized PnL | **−$339.47** |
| Fees paid | **$84.97** |
| Win rate | **37.0%** |
| Profit factor (gross wins / \|gross losses\|) | **~0.68** |
| Avg win / avg loss | $3.76 / −$3.22 |
| Best / worst trade | +$30.91 / −$94.24 |
| Days positive | 17 / 34 trading days |
| Avg day | **−$9.98** |
| Sample window | 2026-06-17 → 2026-07-26 |

Largest coin drains: **TRB (−$200)**, **GRASS (−$164)**.  
Winners exist (AAVE +$71, MON +$60) but cannot outrun the bleed.

`trades.json` live HL sells: **251 stop_loss vs 117 take_profit** — classic negative-expectancy scalp pattern.

### Fantasy vs reality

| Metric file | Claims | Reality |
|-------------|--------|---------|
| `capital_compounder_state.json` | $158k capital, $153k realized | **Synthetic / paper contamination** — not exchange equity |
| `daily_goal_state.json` | $500/day target, one $620 “hit” | Goal is **~30%/day** on ~$1.7k equity — gambling, not trading |
| `WINNING_v31_NOTES.md` | Account ~$1,735 | Matches HL wallet scale; use this class of number only |
| `review_report.json` | SSH to VPS refused | Bot may be **down** while costs still run |

### Architecture diagnosis

Shamrock is a **feature factory**, not a profit engine:

- `main.py` ~4,250 lines, 50+ daemon threads/paths
- 60+ `core/` modules, Moralis streams, gem sniping, MEV, nuclear wallets, 29 indicators, LLM auto-tuner
- Strategy lock **documented as default ON**, coded as **default OFF**:
  ```python
  # main.py — comment says default true; code defaults false
  STRATEGY_LOCK_ACTIVE = os.getenv('STRATEGY_LOCK_ACTIVE', 'false').lower() == 'true'
  ```
- Locked “low risk” strategies (stat arb, funding farmer, coinbase arb) have almost **no live PnL ledger** — only paper arb CSV rows and the bleeding HL book
- OpenAlice-style “self-improving agent / TaG” was bolted on; it **tunes a losing process**, it does not create edge

**Cost structure problem:** Moralis Pro + multi-service Hetzner + always-on scanners burn hundreds/month against a strategy with negative expectancy. Fixed cost > edge = guaranteed net loss even on flat trading days.

---

## 1. What successful open repos actually do (and do not)

### OpenAlice (`TraderAlice/OpenAlice`, ~6.5k stars)

**What it is:** A local *trading workspace* for coding agents — issues, tracked entities, inbox, market tools, **Trading-as-Git** with **human approval gates**.

**What it is not:** A proven automated money printer. Their own README treats broker execution as **beta** and pushes paper/demo first.

**Steal from Alice (process, not hype):**

| Alice primitive | Shamrock gap | Action |
|-----------------|--------------|--------|
| Research → Issue → Schedule → Inbox | Chatty auto-tuner mutates params without attributable thesis | Agents produce *reports + staged parameter commits*, never silent live retunes |
| Trading-as-Git (stage / commit / push) | Orders fire from scanners | Stage HL/arb intents; auto-push only if strategy is certified |
| File-backed single ledger | Multiple conflicting PnL files | One equity source of truth from exchange APIs |
| Skills + AGENTS.md with domain owners | 40+ docs + sprawling main loop | One `AGENTS.md` + skill files for Research / Risk / Execution / Ops |
| UTA-style unified account | Fragmented wallets + ghost positions | Single equity + positions sync every cycle |
| Lite mode without paid data | Moralis required for half the tree | Zero-Moralis path for HL + funding strategies |

### Freqtrade (+ Hyperliquid forks)

**Steal:**

1. **One strategy file** with clear entry/exit, not 12 intertwined guardrails  
2. **Backtest → dry-run (weeks) → live** gates with hard metrics  
3. **Walk-forward / CPCV** — ban live if only in-sample Optuna looks good  
4. **Pairlist discipline** — trade few liquid pairs, not “every coin on HL”  
5. **Hyperopt on costs** (fees, slippage), not vanity win rate  

### Structural-edge bots (funding-rate / basis / MM)

Repos that *can* scale with low drama:

- **Funding rate farm** (delta-neutral: short high funding + long spot hedge)
- **Basis / stat arb** (perp premium mean-reversion with hard fee model)
- **Liquidation cascades** only with proven fill model (usually not retail-latency friendly)

Directional TA scalps on mid-cap perps are where **retail bots die** — that is currently Shamrock’s primary live book.

---

## 2. Root causes of the wash

1. **Negative EV primary strategy** — HL directional, 37% WR, PF 0.68  
2. **Overtrading** — 530 closes in ~5 weeks on ~$1.7k; fees alone ~$85  
3. **Fat-tail losers** — multi-hour holds on toxic names (TRB/GRASS) dominate  
4. **Goals force size** — $500/day on small equity → spray + leverage psychology  
5. **Measurement lies** — compounder / paper rows inflate “wins” and hide bleed  
6. **Cost base > edge** — Moralis + fat VPS for unused gem/MEV surface  
7. **No promotion gate** — live without paper PF ≥ 1.2 and walk-forward pass  
8. **Agent layer optimizes wrong objective** — tunes thresholds instead of killing bad strategies  
9. **Complexity tax** — bugs (ghost positions, strategy lock default, SSH down) cost more than indicators help  

---

## 3. New north star (honest math)

With **~$1.5–2k** equity:

| Horizon | Target | Meaning |
|---------|--------|---------|
| Week 1 | **$0 trading loss + costs cut ≥50%** | Survival |
| Weeks 2–4 | Paper PF ≥ 1.3, max DD ≤ 8% on one strategy | Proof |
| Month 2 | Live micro-size ($25–50 risk/trade), **net green after fees** | Validation |
| Month 3+ | Compound only the certified strategy; scale size with equity | Growth |

**Kill the $500/day goal until equity supports it.**  
Realistic: **0.5–2% of equity/day** *if* edge exists → on $2k that is **$10–40/day**.  
“Parabolic” comes from **compounding a real edge + adding capital**, not from 29 indicators and nuclear 60% bags.

Path to large numbers (order of magnitude):

```
Prove edge @ $2k  →  reinvest + deposit  →  $10k  →  $50k
Only then: expand strategies, raise size, optional gem sleeve as lottery (≤5% capital)
```

There is no ethical shortcut where a wash bot “turns parabolic” by enabling more scanners.

---

## 4. Strategy stack (what we run, in order)

### Tier S — Structural (build first; should work without Moralis)

| Strategy | Module | Edge hypothesis | Success metric (14d paper) |
|----------|--------|-----------------|----------------------------|
| **Funding farmer** | `core/funding_farmer.py` | Collect extreme funding, hedge spot | Net ≥ +0.3%/day equity, max DD ≤ 5%, hedge failure rate = 0 |
| **Stat / basis arb** | `core/stat_arb.py` | Perp premium → short perp + long spot | Net ≥ fees×2, hold time distribution matches decay |
| **Coinbase / CEX-DEX arb** | `arb_executor` + scanner | Cross-venue mispricing after fees+latency | Only live if fill sim shows positive after 50bps buffer |

### Tier A — Directional (only after certification)

| Strategy | Module | Gate to enable live |
|----------|--------|---------------------|
| **HL majors only** | `hl_perps_scanner` | BTC/ETH/SOL only; paper PF≥1.3; ≤3 trades/day; hard ban all mid-caps until proven |
| **Copy-trade alpha wallets** | moralis/alpha paths | Top wallets with 90d track record; size decay with signal age; hard max 1% risk |

### Tier Z — Disabled until $10k equity **and** Tier S profitable 30d

- Gem sniping, nuclear wallet, moonshot, MEV sandwich/JIT, spray multi-chain discovery  
- These are lottery tickets that currently fund Moralis burn  

### Explicit kill list (now)

- HL coins with historical PF < 0.9 and n ≥ 5 (extend hard ban from v31)  
- Any strategy without a **ledger row** (strategy_id, fees, hedge status)  
- Auto-tuner live parameter writes without human commit  
- Daily goal pyramids above 2% of equity  

---

## 5. Agent / instruction redesign (OpenAlice-shaped, profit-shaped)

Do **not** bolt another auto-trader. Give agents **jobs that improve expectancy**.

### New agent roster

| Agent | Role | Cadence | Outputs | Can trade? |
|-------|------|---------|---------|------------|
| **Researcher** | Funding tables, basis spreads, regime, news risk | Hourly / on schedule | Inbox report + ranked opportunities | No |
| **Risk Officer** | Equity sync, DD, concentration, fee drag | Every cycle | Block list, size caps | Veto only |
| **Execution Agent** | Places only **certified** strategy intents | Continuous | Fills, slippage log | Yes, gated |
| **Auditor** | Daily PnL vs exchange; fantasy-state detection | Daily | Diff report; fail if drift > $5 | No |
| **Tuner** | Suggests param changes from ledger | Weekly | PR-style `params.diff` | No (stage only) |

### Instruction files to add/replace

1. **`AGENTS.md`** (root) — always-loaded contract: evidence required, no silent retunes, equity from exchange only  
2. **`skills/research-funding/SKILL.md`** — how to score funding opportunities  
3. **`skills/risk-gate/SKILL.md`** — promotion criteria paper → live  
4. **`skills/ledger-truth/SKILL.md`** — which files are truth, which are decorative  
5. **Deprecate** autonomous `self_improving_agent` live writes; keep as **suggestion engine**

### Trading-as-Git for Shamrock

```
intent.json staged  →  risk pre-commit checks  →  human or cert-auto approve  →  execute  →  fill journal commit
```

Auto-approve only if:

- Strategy in `CERTIFIED_STRATEGIES`  
- Risk officer green  
- Daily loss < 2% equity  
- Exchange equity synced < 60s ago  

---

## 6. Cost cut (stop funding a losing product)

| Line item | Action | Target |
|-----------|--------|--------|
| Moralis Pro | **Downgrade or pause** until Tier Z re-enabled; HL funding/stat arb does not need streams | −$50–200/mo |
| Moralis Streams | Disable whale/liquidity streams | −CU burn |
| VPS | Single container bot only; kill dashboard+db if unused; or move to $5–10 VPS / local Mac mini | −50–70% |
| OpenAI auto-tuner | Weekly batch only, not continuous | −API $ |
| Chains | Drop multi-chain gem scan; keep SOL/Base only if any on-chain hedge needed | −RPC $ |

**Rule:** Monthly infra cost must be **≤ 20% of average monthly gross edge**. If edge is $0, infra target is **near $0** (pause live).

---

## 7. Measurement system (one truth)

### Single equity ledger

Every hour write `output/equity_truth.json`:

```json
{
  "as_of": "ISO-8601",
  "hl_account_value_usd": 0,
  "spot_wallets_usd": 0,
  "open_unrealized_usd": 0,
  "total_equity_usd": 0,
  "source": "hyperliquid_api+rpc"
}
```

### Single trade journal

Every closed trade must include:

`strategy_id, venue, symbol, side, notional, fee, pnl, hold_s, entry_reason, exit_reason, hedge_ok`

### Kill fantasy writers

- Stop treating `capital_compounder_state` as display equity until wired to `equity_truth`  
- Dashboard home shows **only** exchange-synced equity  
- Daily goal engine reads equity_truth; caps target at `min(configured, 0.02 * equity)`  

### Promotion gate (code, not vibes)

```
paper_days >= 14
AND profit_factor >= 1.3
AND max_drawdown_pct <= 8
AND trades >= 40
AND fees_modeled == true
AND walk_forward_pass == true
→ strategy marked CERTIFIED
else → cannot open live size
```

---

## 8. Phased execution plan

### Phase 0 — Stop the bleed (Day 0–1) 🚨

1. Confirm VPS state; if down, **do not restart full stack**  
2. Set live **flat**: no new HL opens; close/flatten orphans  
3. Env hard switches:
   - `HL_PERPS_ENABLED=false` (or max opens/day = 0)  
   - `STRATEGY_LOCK_ACTIVE=true` (fix default bug)  
   - `GEM_SNIPE_ENABLED=false`, Moralis streams off  
   - `SELF_IMPROVEMENT_ENABLED=false` for live writes  
4. Snapshot true balances (HL + wallets) → `equity_truth.json`  
5. Cancel / pause Moralis plan if not used this week  

**Exit criteria:** Flat account, known equity, infra bill cut plan approved.

### Phase 1 — Truth + cost (Day 1–3)

1. Implement equity sync + journal schema  
2. Fix strategy lock default to `true`  
3. Strip dashboard claims that show $158k  
4. Downsize compose: bot-only profile  
5. Report: last 30d real PnL by strategy (HL only until others log)

**Exit criteria:** One number for equity that matches exchange UI within $1.

### Phase 2 — Structural paper engines (Week 1–3)

1. **Funding farmer**
   - Fix hedge path (abort if hedge fails — already partial)  
   - Paper every extreme funding event for 14 days  
   - Log funding received vs hedge PnL  
2. **Stat arb**
   - Harden fee model (spot fee + HL fee + slippage ≥ 30bps)  
   - Paper only pairs with deep liquidity  
3. Daily Auditor agent report to Telegram: edge candidates, no auto-trade  

**Exit criteria:** One strategy hits promotion gate in paper.

### Phase 3 — Micro live (Week 3–6)

1. Live size: **$25–50** risk, 1 strategy only  
2. Max daily loss: **2% equity** hard stop → pause rest of day  
3. Human review of every loser > $10 for 7 days  
4. If live PF < 1.0 after 40 trades → **disable**, return to paper  

**Exit criteria:** Net green after fees for 14 calendar days.

### Phase 4 — Compound (Month 2+)

1. Raise size with equity (Kelly fraction capped 10% of bankroll per idea)  
2. Deposit more capital only after Phase 3 pass  
3. Optional: re-enable **majors-only** HL trend with same gate  
4. Gem/MEV remains off until $10k equity + 30d Tier S profit  

### Phase 5 — Optional Alice-grade desk (parallel, not blocking profit)

1. `AGENTS.md` + skills  
2. Issue board for research tasks  
3. Staging queue for trades  
4. Only after Phase 3 — do not block profitability work on UI polish  

---

## 9. What “parabolic” actually requires

Parabolic equity curves in crypto usually come from **one** of:

1. **Structural yield** (funding/basis) compounded with leverage *and* hedge discipline  
2. **A few correct high-convexity bets** (gems) — lottery; cannot be the core engine  
3. **More capital into a proven small edge**  

Shamrock has been optimizing (2) and (complexity) while bleeding on low-quality (directional) trades.

**New product definition:**

> Shamrock is a **certified structural-edge execution system** with agent research and hard promotion gates — not a 24/7 multi-chain casino.

---

## 10. Immediate decisions needed from owner

1. **Flatten live HL now?** (recommended: yes)  
2. **Pause/downgrade Moralis this billing cycle?** (recommended: yes until Tier Z)  
3. **Accept goal rewrite:** max daily target = 2% of true equity until $10k?  
4. **Which Tier S to prioritize first:** Funding farmer vs Stat arb? (recommended: **Funding farmer** — clearer edge, less latency race)  
5. **VPS:** restart minimal bot-only, or pause entirely until paper cert?  

---

## 11. Success scoreboard (post in Telegram daily)

```
Equity (exchange): $X
Day PnL: $Y (Z%)
Fees today: $F
Open risk: $R
Strategy: funding|stat|off
Certified?: yes/no
Infra burn MTD: $I
Net after infra (MTD): equity_delta - I
```

If net after infra is negative for 14 days with no certified strategy in paper → **shut down paid services** and research offline. That is professional, not failure.

---

## Appendix A — Code fixes already identified

| Bug / smell | File | Fix |
|-------------|------|-----|
| Strategy lock defaults false | `main.py:167` | Default `'true'` |
| Fantasy capital | `capital_compounder` | Bind to equity_truth or hide from UI |
| Ghost HL positions | notes in WINNING_v31 | Keep sync purge; unit test it |
| No fee-aware PF gate before live | scanner / promoter | Implement certification module |
| Auto-tuner live writes | `self_improving_agent` | Suggestions only |

## Appendix B — Competitive takeaways one-liner

| Project | Lesson |
|---------|--------|
| OpenAlice | Agents need workspace + approval, not unbounded order spam |
| Freqtrade | Backtest → dry-run → live; one strategy; measure costs |
| Funding arb repos | Delta-neutral yield is the boring path that can actually pay |
| Shamrock today | Overbuilt directional scalp with fake equity dashboard |

---

*This plan prioritizes capital preservation and proof of edge over feature velocity. Parabolic returns, if they come, come after a green, certified core — not before.*
