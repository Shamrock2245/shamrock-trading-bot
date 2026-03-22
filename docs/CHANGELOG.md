# CHANGELOG — Version History

## Format
```
## [version] — YYYY-MM-DD
### Added / Changed / Fixed / Removed
- Description of change
```

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
