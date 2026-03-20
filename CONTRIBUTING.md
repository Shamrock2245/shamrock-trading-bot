# Contributing to Shamrock Trading Bot

This document describes the development workflow, code standards, and contribution
guidelines for the Shamrock Trading Bot project.

---

## Development Setup

### Prerequisites

- Python 3.11+
- Docker and Docker Compose
- Git

### Local Setup

```bash
# Clone the repo
git clone https://github.com/Shamrock2245/shamrock-trading-bot.git
cd shamrock-trading-bot

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Copy and configure env
cp .env.example .env
# Edit .env — set MODE=paper, add RPC URLs (no private keys needed for dev)
```

### Running Locally

```bash
# Fetch balances (no keys needed in paper mode)
python main.py --balances

# Run gem scan
python main.py --scan

# Test snipe example
python main.py --snipe 0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48 ethereum
```

---

## Project Structure

```
shamrock-trading-bot/
├── main.py                     # Entry point — CLI + bot loop
├── config/
│   ├── chains.py               # Chain configs, RPC URLs, router addresses
│   ├── wallets.py              # Wallet definitions (addresses, strategies)
│   ├── settings.py             # All env-var-backed settings
│   └── tokens.py               # Stablecoins, blocklist, whitelist
├── core/
│   ├── balance_fetcher.py      # Multi-chain ETH + ERC-20 balance fetcher
│   ├── safety.py               # Honeypot + rug detection pipeline
│   ├── executor.py             # Trade execution (CoW, 1inch, Flashbots)
│   └── risk.py                 # Position sizing, circuit breaker, stop-loss
├── data/
│   ├── models.py               # Token, GemCandidate, Trade, Position, SignalScore
│   └── providers/
│       ├── dexscreener.py      # DexScreener API wrapper
│       ├── goplus.py           # GoPlus Security API wrapper
│       ├── oneinch.py          # 1inch Aggregation API wrapper
│       └── coingecko.py        # CoinGecko API wrapper
├── scanner/
│   └── gem_scanner.py          # Gem discovery + scoring engine (0–100)
├── logs/                       # Runtime logs (gitignored)
├── output/                     # JSON output files (gitignored)
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── GUARDRAILS.md               # Safety rules + pre-live checklist
├── SECURITY.md                 # Security policy
├── DEPLOYMENT.md               # Hetzner VPS deployment guide
└── CONTRIBUTING.md             # This file
```

---

## Code Standards

### Python Style

- Follow **PEP 8** with a line length of 100 characters
- Use **type hints** on all function signatures
- Use **dataclasses** for data transfer objects (see `data/models.py`)
- Use **async/await** for I/O-bound operations where possible
- Use **tenacity** for retry logic on all external API calls

### Docstrings

Every module, class, and public function must have a docstring. Use the following format:

```python
def check_token_safety(token_address: str, chain: str) -> SafetyResult:
    """
    Run the full safety pipeline for a token.

    This is MANDATORY before any trade. Returns SafetyResult with
    is_safe=True only if ALL checks pass.

    Args:
        token_address: Token contract address (any case)
        chain: Chain name (e.g., "ethereum", "base")

    Returns:
        SafetyResult with full audit trail
    """
```

### Security Rules (Non-Negotiable)

1. **Never log private keys** — no `logger.info(key)` or `print(key)` anywhere
2. **Never hardcode addresses as constants** — use `config/wallets.py` and `config/chains.py`
3. **Never skip safety checks** — `check_token_safety()` must be called before every trade
4. **Never commit `.env`** — it is gitignored; keep it that way
5. **Always check `settings.IS_PAPER`** before executing real transactions

### Error Handling

- Use `try/except` with specific exception types — never bare `except:`
- Log errors with `logger.error(f"...", exc_info=True)` for stack traces
- API failures should log a warning and return `None` or an empty list — never crash the bot
- Use `tenacity` `@retry` decorators on all external API calls

---

## Adding a New Chain

1. Add chain config to `config/chains.py`:
   ```python
   "newchain": ChainConfig(
       name="newchain",
       chain_id=12345,
       rpc_url=os.environ.get("NEWCHAIN_RPC_URL", ""),
       native_token="ETH",
       max_gas_gwei=50,
       ...
   )
   ```

2. Add GoPlus chain ID mapping to `GOPLUS_CHAIN_MAP` in `config/chains.py`
3. Add Honeypot.is chain ID mapping to `HONEYPOT_CHAIN_MAP`
4. Add DexScreener chain ID mapping to `DEXSCREENER_CHAIN_MAP`
5. Add RPC URL env var to `.env.example`
6. Add chain to wallet configs in `config/wallets.py` if applicable
7. Test with `python main.py --balances` to verify connectivity

---

## Adding a New Data Provider

1. Create `data/providers/newprovider.py`
2. Implement rate limiting using the `_rate_limit()` pattern
3. Wrap all API calls with `@retry(stop=stop_after_attempt(3), ...)`
4. Return empty lists/None on failure — never raise exceptions to callers
5. Add API key to `.env.example` and `config/settings.py`
6. Document the provider's rate limits and cost in the module docstring

---

## Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Run with coverage
python -m pytest tests/ --cov=. --cov-report=html

# Test a specific module
python -m pytest tests/test_safety.py -v
```

**Minimum test coverage requirements:**
- `core/safety.py`: 90%+ (this is the most critical module)
- `core/risk.py`: 85%+
- `config/`: 80%+

---

## Git Workflow

```bash
# Create a feature branch
git checkout -b feature/add-technical-analysis

# Make changes, then commit
git add .
git commit -m "feat: add RSI and MACD indicators to signal scorer"

# Push and open PR
git push origin feature/add-technical-analysis
```

### Commit Message Format

```
type: short description (max 72 chars)

Optional longer description explaining the why, not the what.
```

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`

---

## Roadmap

### Phase 2 — Technical Analysis (Next)
- [ ] Implement RSI, MACD, EMA crossovers using `pandas-ta`
- [ ] Connect `SignalScore` to real OHLCV data from GeckoTerminal
- [ ] Add Bollinger Band squeeze detection
- [ ] Wire signal scores into gem scoring composite

### Phase 3 — Advanced Execution
- [ ] Implement full CoW Protocol order signing
- [ ] Add Flashbots bundle submission for Ethereum
- [ ] Implement trailing stop-loss automation
- [ ] Add position management loop (monitor open positions)

### Phase 4 — Monitoring Dashboard
- [ ] Build read-only web dashboard (portfolio, trades, P&L)
- [ ] Add Telegram bot alerts for trades and circuit breaker
- [ ] Integrate Grafana + Prometheus metrics

### Phase 5 — Smart Money Tracking
- [ ] Build wallet tracker for known alpha wallets
- [ ] Wire smart money score into gem scanner
- [ ] Add whale accumulation detection

---

*Maintained by Shamrock2245 | GitHub: https://github.com/Shamrock2245/shamrock-trading-bot*
