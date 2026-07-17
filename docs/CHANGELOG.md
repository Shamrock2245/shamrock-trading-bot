# CHANGELOG — Version History

## Format
```
## [version] — YYYY-MM-DD
### Added / Changed / Fixed / Removed
- Description of change
```

---
## [2.7.0] — 2026-07-17
### Tuned: Frequency unstack from trade_history (26).csv
- **Analysis (trade_history 24–26, downloaded Jul 17):** Post-fix (Jul 13+) edge is real — 17 closes, **+$28.76**, 41.2% WR, **3.26× R:R**, avg loss only −$2.25. Rapid closes nearly gone (1 residual CRV 4s on Jul 14). Primary bottleneck is **volume**: ~3.5 opens/day (Jul 16 = 1) vs 15–25 target.
- **Kept (quality working):** `HL_PERPS_MIN_RR=1.2`, `HL_PERPS_LONG_ONLY=true` (shorts ~17% WR all-time), leverage 3×, autoban, RSI sticky veto, SL retry backoff.
- **Changed (Three-File Rule):**

| Variable | Old | New | Why |
|---|---|---|---|
| `HL_PERPS_EXEC_SCORE` | 58 | **55** | Near-miss band 55–58 was blocking volume; goal floor still 52 |
| `HL_PERPS_REENTRY_COOLDOWN_MIN` | 12 | **8** | Autoban handles toxic churn; 12m stacked starvation |
| `HL_PERPS_LOSS_COOLDOWN_MIN` | 15 | **10** | Same |
| `HL_PERPS_EMERGENCY_COOLDOWN_MIN` | 90 | **60** | SL-fail blackout still > reentry; 90 was excess |
| `HYPERLIQUID_MAX_POSITIONS` / `HL_PERPS_MAX_POSITIONS` | 8 | **10** | More concurrent rotation |
| `HL_PERPS_TOXIC_COINS` | …TRB | …TRB,**HYPE** | HYPE 4 trades / 0% WR / −$6.65 |

- **Goal-adaptive catch-up sharpened:** behind-pace / catch-up `exec_score_delta` −4 → **−5**, reentry 8→**6**, loss 10→**8**, size mult 1.10→**1.15** (still floor exec 52).
- Files: `core/hl_perps_scanner.py`, `core/hyperliquid_executor.py` (emergency default sync), `core/daily_goal_engine.py`, `.env.example`, `.github/workflows/ci.yml`.

---
## [2.6.0] — 2026-07-15
### Critical Fix: `.env` Override Trap — Bot Silent for ~23 Hours
- **Root cause:** Hetzner `.env` (copied from `.env.example` at initial setup) contained stale values that silently overrode all code-level gate fixes from v2.1–v2.5. The bot was running with `EXEC_SCORE=65`, `MIN_RR=1.5`, `LONG_ONLY=true`, `REENTRY=30min`, `LOSS=30min`, `EMERGENCY=240min`, `MAX_POSITIONS=6` — completely undoing every volume fix deployed since July 6.
- **Fix:** CI deploy script (`ci.yml`) now patches `.env` via `sed` on every deploy, guaranteeing correct values regardless of what is in the file. Auto-blacklist vars are also injected if missing.
- **`.env.example` updated** with all tuned values and inline rationale comments so future server setups start correctly.
- **New docs added:**
  - `docs/ENV_OVERRIDE_TRAP_POSTMORTEM.md` — Full post-mortem with diagnostic steps
  - `docs/HL_PERPS_RUNBOOK.md` — Operational runbook covering all known failure modes, gate tuning reference, and the Three-File Update Rule

---
## [2.5.0] — 2026-07-14 (auto-blacklist)
### Added
- **Dynamic performance-based auto-blacklist** (`HL_PERPS_AUTOBAN_*`): the scanner now tracks per-coin win/loss stats in `data/dashboard/hl_coin_perf.json`. Any coin with ≥ 5 trades and a win rate below 30% is automatically banned for 48 hours. Bans survive restarts (state is persisted to disk and reloaded on startup). Ban expiry is logged at `INFO` level; ban triggers are logged at `WARNING`.
- **`scripts/seed_autoban.py`**: one-time script that pre-populates `hl_coin_perf.json` with real win/loss stats from the v17 trade history CSV. Immediately bans AAVE (9% WR), HMSTR (0%), BRETT (8%), GRASS (20%), EIGEN (20%), MET (20%), and MEME (0%) for 48 hours without waiting for 5 more losses.
- **New env vars** (all optional, defaults shown):
  - `HL_PERPS_AUTOBAN_ENABLED=true`
  - `HL_PERPS_AUTOBAN_MIN_TRADES=5`
  - `HL_PERPS_AUTOBAN_WR_THRESHOLD=0.30`
  - `HL_PERPS_AUTOBAN_HOURS=48.0`

### Changed
- `_inject_scanner_cooldown()` in `hyperliquid_executor.py` now calls `scanner.record_trade_outcome(coin, won)` on every close, feeding the auto-blacklist with live data.
- `_is_on_cooldown()` in `hl_perps_scanner.py` checks the auto-blacklist as gate #0 (before emergency/reentry/loss cooldowns).

---
## [2.4.0] — 2026-07-14
### Fixed
- **PYTHON-RR-SYNC:** Synced `HL_PERPS_MIN_RR` default in `hyperliquid_executor.py` from `1.5` → `1.1` to match `hl_perps_scanner.py`. The mismatch was the root cause of 49 rapid closes (5–6s): scanner pre-approved signals at R/R=1.1–1.4, but the executor's post-fill guard rejected them at 1.5, triggering an immediate `market_close`.
- **PYTHON-EC-SYNC:** Synced `HL_PERPS_EMERGENCY_COOLDOWN_MIN` default in executor from `240` → `60` minutes to match scanner. 4-hour blackout was too punishing for SL placement failures on illiquid coins.
- See `docs/HL_PERPS_RAPID_CLOSE_POSTMORTEM.md` for full root cause analysis.

---
## [2.3.0] — 2026-07-13 (CI/CD disk fix)
### Fixed
- **CI disk exhaustion:** `docker system prune -f` (dangling only) replaced with `docker system prune -af --volumes && docker builder prune -af` in `.github/workflows/ci.yml`. Previous builds accumulated 10–30 GB of stale image layers, causing `no space left on device` failures during `docker compose build --no-cache`. Free disk space is now logged before every build.

---
## [2.2.0] — 2026-07-13 (trade volume fix)
### Changed
- **`HL_PERPS_EXEC_SCORE` default:** 65 → 58. Most real setups score 50–62; RSI veto + macro filter still hard-block bad entries.
- **`HL_PERPS_MIN_RR` default:** 1.5 → 1.1 in scanner. Still ensures positive EV at 50% WR.
- **`HL_PERPS_REENTRY_COOLDOWN_MIN` default:** 30 → 5 minutes.
- **`HL_PERPS_LOSS_COOLDOWN_MIN` default:** 30 → 10 minutes.
- **`HL_PERPS_EMERGENCY_COOLDOWN_MIN` default:** 240 → 60 minutes.
- **`HL_PERPS_LONG_ONLY` default:** `true` → `false`. Shorts re-enabled with RSI veto guard.
- **`HL_PERPS_MAX_POSITIONS` default:** 6 → 10.
- **Scan cap:** 100 → 150 coins per cycle.
- **RSI dead zones:** RSI 35–40 and 60–65 now use proportional scoring instead of 0 points.
- **Fib proximity:** 1% → 2% window.
- **`fib_382`/`fib_786`** added to `buy_zones` with +10 score boost each.
- **Retracement sniper:** Removed 1-hour parking delay; signals execute immediately.

---
## [2.1.1] — 2026-07-06 (SL placement fix)
### Fixed
- **SL retry backoff:** `_place_tpsl` now retries SL placement 3 times (1s, 2s backoff). Attempt 1 uses 50% slippage; attempts 2–3 fall back to 10% slippage which HL accepts on illiquid coins. RED TEAM GUARD only fires after all 3 attempts fail.
- **RSI sticky veto:** RSI veto in `_score_signal` is now sticky — downstream EMA/MACD/volume/BB cannot add points back after a veto. Score is clamped to 0.0 before the trend filter.
- **Balance key mismatch:** Scanner `_bal.get("accountValue")` corrected to `_bal.get("account_value")` (matches executor's normalized output dict). Kelly sizing and daily loss limit now use live equity instead of falling back to `HL_PERPS_BASE_CAPITAL`.
- **Aggressive Mode block deleted** from `.env` (restored `HL_PERPS_EXEC_SCORE` to 65.0 default, `HYPERLIQUID_DEFAULT_LEVERAGE` to 3, `HYPERLIQUID_STOP_LOSS_PCT` to 2.5).
- **Trailing stop env vars** added: `HL_TRAILING_ROE_TRIGGER_PCT=10.0`, `HL_TRAILING_DISTANCE_PCT=1.0`.

---
## [2.1.0] — 2026-06-11
### Added
- **LLM Auto-Tuner (Trading-as-Git):** Added `core/llm_auto_tuner.py` which polls on a 30-minute cycle to quant-tune trailing stops (`OPENAI_MODEL`, default `gpt-5-mini` for free daily mini-class usage).
- **ShamrockGuard:** Added `core/shamrock_guard.py` to enforce daily profit goals (e.g. $500/day) using "Bank-It Mode" and strict daily drawdown caps.
- **Hourly Reports:** Added `core/hourly_report.py` to compile metrics (PnL, position counts, active regimes) and dispatch them hourly via Slack and Telegram.

---
## [2.0.0] — 2026-03-30
### Added
- **Upgrade 1 (MEV):** Wired `execute_via_flashbots()` into `executor.py` as primary path for Ethereum/Base/Arbitrum. Routing: CoW -> Flashbots bundle -> 1inch for Ethereum; Flashbots Protect RPC -> 1inch for Base/Arbitrum.
- **Upgrade 1 (Jito):** Added Jito bundle submission to `solana_executor.py` as primary Solana execution path with dynamic tip scaling (10k/50k/100k lamports by conviction).
- **Upgrade 2 (Bundle Detector):** New `core/bundle_detector.py` — Block-0 sniper detection for EVM and Solana. Hard-rejects tokens where >20% of supply was sniped at launch. Wired as Hard Gate #2 in `gem_scanner._score_token()`.
- **Upgrade 3 (ML Weights):** New `ml/weight_optimizer.py` — XGBoost classifier trained on rolling 7-day trades.json. Dynamically adjusts all 29 indicator weights. Auto-retrains every 6 hours. Falls back to static weights until 20+ trades logged.
- **Upgrade 4 (Copy-Trading):** New `core/wallet_monitor.py` — proactive alpha wallet daemon. Polls SMART_MONEY_WALLETS (EVM) + ALPHA_WALLETS_SOLANA every 30s. Tier 1 (3+ wallets) = immediate execute; Tier 2 (2 wallets) = express lane. Started in main.py alongside PositionMonitor.
- New `docs/UPGRADES.md` with full architecture notes and env var reference.
- New settings blocks in `config/settings.py` for Jito, Helius, Bundle Detector, ML Optimizer, Wallet Monitor.
### Changed
- `core/mev_protection.py`: Rewritten with Flashbots bundle relay, Protect RPC, Jito bundles, and live CoW execution.
- `scanner/gem_scanner.py`: Bundle gate added as Hard Gate #2; gem_score formula uses ML dynamic weights.
- `main.py`: WalletMonitor daemon started alongside PositionMonitor in run_bot_loop().

---

## [0.4.0] — 2026-03-22
### Added
- Full DexScreener API coverage (11 endpoints)
- Community takeovers (CTO) as gem scanner Source 4
- DexScreener ads as gem scanner Source 5
- Batch token lookup by chain (`get_tokens_by_chain`)
- Token orders endpoint (`get_token_orders`)
- Chain-specific pool lookup (`get_token_pools_by_chain`)
- 31 behavioral documentation files in `docs/`
- Commit-and-push workflow (`.agent/workflows/commit-and-push.md`)

### Fixed
- Plotly `legend` TypeError across all dashboard pages
- `PERMANENT_BLOCKLIST` type error (empty dict → empty set)

## [0.3.0] — 2026-03-22
### Added
- Phase 3 signal enrichment (TVL, social sentiment, holder concentration, unlock risk)
- GeckoTerminal OHLCV data source
- Solana support (Jupiter executor, SOL tokens, stablecoin lists)
- `DEXSCREENER_CHAIN_MAP` in `config/chains.py`

### Fixed
- Duplicate `SignalScore` class definition
- Circuit breaker logic for portfolio drawdown
- Token approvals set to exact amounts (no unlimited)

## [0.2.0] — 2026-03-20
### Added
- GemSnipe strategy with TA + Fibonacci pipeline
- 30+ technical indicators (`strategies/indicators.py`)
- Fibonacci retracement engine (`strategies/fibonacci.py`)
- Signal scorer (`strategies/signal_scorer.py`)
- Smart money wallet tracking
- Social scoring (LunarCrush + CoinGecko + DexScreener)

## [0.1.0] — 2026-03-18
### Added
- Initial bot framework (main loop, scanner, executor)
- DexScreener integration (profiles, boosts, search)
- Multi-chain support (ETH, Base, ARB, POLY, BSC)
- Core safety pipeline (GoPlus, Honeypot.is, Token Sniffer)
- Risk management (stop-loss, circuit breaker, daily limits)
- Streamlit dashboard with 5 pages
- Paper trading mode
- Slack notifications
