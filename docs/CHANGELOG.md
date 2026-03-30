# CHANGELOG — Version History

## Format
```
## [version] — YYYY-MM-DD
### Added / Changed / Fixed / Removed
- Description of change
```

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
