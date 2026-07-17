# Shamrock Bot — Infrastructure Upgrades (v2.0)

This document describes the six major infrastructure upgrades implemented to scale the bot from
its current $5k starting capital toward 7-figure performance. Each upgrade is production-ready,
fully wired into the existing pipeline, and controlled via environment variables.

---

## Upgrade 1 — MEV & Execution Speed

### Problem
`mev_protection.py` contained a fully-written `execute_via_flashbots()` function that was **never
called** in `executor.py`. Every EVM trade was going through the public 1inch mempool, exposing
every buy to sandwich attacks and front-running. On Solana, Jupiter was submitting to the public
RPC with no MEV protection.

### Solution

**EVM Execution Chain (executor.py)**

| Chain | Primary | Fallback 1 | Fallback 2 |
|---|---|---|---|
| Ethereum | CoW Protocol (batch auction) | Flashbots bundle → `relay.flashbots.net` | 1inch public |
| Base | Flashbots Protect RPC | 1inch public | — |
| Arbitrum | Flashbots Protect RPC | 1inch public | — |
| Polygon / BSC | 1inch public | — | — |

**Solana Execution Chain (solana_executor.py)**

Jito bundle submission is now the **primary** path for all Solana buys. The tip scales
dynamically based on price impact and conviction:

| Scenario | Jito Tip | Approx. Cost |
|---|---|---|
| Routine gem trade | 10,000 lamports | ~$0.001 |
| High conviction (score 80+) | 50,000 lamports | ~$0.005 |
| New launch / congested block | 100,000 lamports | ~$0.015 |

Standard RPC submission is retained as a fallback if Jito fails.

### New Environment Variables
```
FLASHBOTS_SIGNING_KEY=<your_flashbots_signing_key>   # Required for Ethereum bundles
FLASHBOTS_RPC_URL=https://rpc.flashbots.net           # Default — no change needed
JITO_BLOCK_ENGINE_URL=https://mainnet.block-engine.jito.wtf/api/v1/bundles  # Default
JITO_AUTH_KEY=                                         # Optional: Jito priority access key
HELIUS_API_KEY=<your_helius_key>                       # Recommended for Solana data quality
```

---

## Upgrade 2 — Block-0 Sniper & Bundle Detection

### Problem
The bot had no defense against coordinated sniper attacks where multiple wallets acquire a large
percentage of a token's supply in the same block as pool creation (block 0). These tokens are
pre-rigged for a pump-and-dump and represent one of the highest-risk entry patterns in DeFi.

### Solution

**New file: `core/bundle_detector.py`**

The `check_bundle()` function is now wired into `gem_scanner._score_token()` as **Hard Gate #2**
(fires after the Solana age gate, before any scoring begins).

**EVM Detection Logic:**
1. Fetches the pool creation block from the chain's block explorer API (Etherscan / Basescan).
2. Scans all ERC-20 Transfer events in that block from the pool contract.
3. If any single wallet received >5% of supply in block 0, it is flagged as a sniper.
4. If the **combined sniper supply** exceeds `BUNDLE_REJECT_THRESHOLD` (default 20%), the token
   is hard-rejected with reason `"BUNDLE_SNIPER_REJECT"`.

**Solana Detection Logic:**
1. Queries the token's largest accounts via the Solana RPC.
2. If the top-5 holders collectively control >40% of supply AND the token is <6 hours old,
   it is flagged as a likely bundled launch.

### New Environment Variables
```
BUNDLE_DETECTOR_ENABLED=true          # Toggle (default: true)
BUNDLE_REJECT_THRESHOLD=0.20          # Reject if >20% supply sniped in block 0
HELIUS_API_KEY=<your_helius_key>       # Improves Solana bundle detection accuracy
```

---

## Upgrade 3 — ML Feedback Loop (XGBoost Dynamic Weights)

### Problem
The 29-indicator scoring formula used **static, hardcoded weights** that were set at design time
and never updated. As market conditions change (e.g., whale accumulation becomes more predictive
than volume spikes in a bear market), the weights should adapt automatically.

### Solution

**New file: `ml/weight_optimizer.py`**

An XGBoost classifier is trained on the rolling 7-day window of `output/trades.json` to learn
which indicator sub-scores are most predictive of profitable outcomes.

**Training Pipeline:**
1. Loads all closed trades from `trades.json` with a `pnl_pct` outcome.
2. Extracts 10 feature dimensions from each trade record (volume, whale, liquidity, safety,
   momentum, boost, fibonacci, sentiment, age, social sub-scores).
3. Labels each trade as `1` (profitable, PnL > 5%) or `0` (loss/flat).
4. Trains an XGBoost classifier and extracts feature importances as the new weight vector.
5. Normalizes the weight vector to sum to 1.0 and writes it to `output/dynamic_weights.json`.

**Integration in gem_scanner.py:**
- `GemScanner.__init__()` loads `dynamic_weights.json` at startup.
- The final `gem_score` formula uses `self._weights` instead of hardcoded constants.
- If `trades.json` has fewer than `ML_WEIGHT_MIN_TRADES` (default 20) records, the optimizer
  falls back to the static design-time weights — no degradation during early operation.
- The model auto-retrains every `ML_WEIGHT_RETRAIN_HOURS` (default 6) hours.

### New Environment Variables
```
ML_WEIGHT_OPTIMIZER_ENABLED=true      # Toggle (default: true)
ML_WEIGHT_LOOKBACK_DAYS=7             # Rolling training window in days
ML_WEIGHT_MIN_TRADES=20               # Min trades before ML weights activate
ML_WEIGHT_RETRAIN_HOURS=6             # Retraining frequency
DYNAMIC_WEIGHTS_PATH=output/dynamic_weights.json  # Output path for learned weights
```

### Static Fallback Weights (used until 20+ trades are logged)

| Indicator | Static Weight |
|---|---|
| Volume | 22% |
| Whale / Holder | 18% |
| Liquidity | 14% |
| Safety | 12% |
| TA / Momentum | 10% |
| Boost / CTO | 7% |
| Fibonacci | 5% |
| Grok Sentiment | 5% |
| Age | 4% |
| Social | 3% |

---

## Upgrade 4 — Proactive Smart Money Copy-Trading Daemon

### Problem
`data/providers/smart_money.py` was **reactive**: it checked whether known alpha wallets already
held a token being evaluated. It did not actively monitor those wallets for new buys and could
not front-run their entries.

### Solution

**New file: `core/wallet_monitor.py`**

A background daemon (`WalletMonitor`) polls all wallets in `settings.SMART_MONEY_WALLETS` (EVM)
and `settings.ALPHA_WALLETS_SOLANA` (Solana) every 30 seconds. When it detects a coordinated
buy signal, it generates an `AlphaSignal` and injects it into the bot's express lane.

**Signal Tier System:**

| Tier | Trigger | Action |
|---|---|---|
| Tier 1 (Immediate) | 3+ alpha wallets buy same token within 2 min | Bypass scanner, execute immediately |
| Tier 2 (Express) | 2 alpha wallets buy same token within 2 min | Inject into express lane (score 82+) |
| Tier 3 (Watchlist) | 1 alpha wallet buys | Add to watchlist for re-evaluation |

**Copy Trade Sizing:**
- Copy size = `min(alpha_buy_usd × WALLET_MONITOR_COPY_SIZE_PCT, WALLET_MONITOR_MAX_COPY_USD)`
- Default: 50% of the alpha wallet's buy, capped at $500.
- This ensures we never over-commit on a single copy signal.

**EVM Detection:**
- Polls Etherscan/Basescan/Arbiscan/Polygonscan/BSCscan transaction history for each wallet.
- Detects `swap` and `transfer` transactions to known DEX routers.
- Resolves token address and estimates USD value from current price.

**Solana Detection:**
- Polls Solana RPC `getSignaturesForAddress` for recent transactions.
- Parses Jupiter swap instructions to identify token buys.

**Daemon Startup (main.py):**
The `WalletMonitor` is started as a background thread in `run_bot_loop()` alongside the
`PositionMonitor`. A callback fires a Telegram/notification alert on every Tier 1 or Tier 2
signal.

### New Environment Variables
```
WALLET_MONITOR_ENABLED=true           # Toggle (default: true)
WALLET_MONITOR_POLL_INTERVAL=30       # Seconds between wallet polls
WALLET_MONITOR_MIN_BUY_USD=500        # Ignore buys smaller than $500
WALLET_MONITOR_MAX_BUY_AGE=120        # Ignore transactions older than 2 minutes
WALLET_MONITOR_TIER1_COUNT=3          # Wallets needed for Tier 1 (immediate execute)
WALLET_MONITOR_TIER2_COUNT=2          # Wallets needed for Tier 2 (express lane)
WALLET_MONITOR_COPY_SIZE_PCT=0.5      # Copy 50% of alpha wallet's buy size
WALLET_MONITOR_MAX_COPY_USD=500       # Hard cap on copy trade size
```

**To add Solana alpha wallets**, populate `ALPHA_WALLETS_SOLANA` in `settings.py`:
```python
ALPHA_WALLETS_SOLANA: list[str] = [
    "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU",  # example
]
```

---

## Upgrade 5 — Trading-as-Git AI Auto-Tuner

### Problem
Trailing stops and take-profit ladders were entirely static and rules-based. The bot couldn't reason about when a meme coin was showing a momentary dip versus a structural trend reversal.

### Solution

**New file: `core/llm_auto_tuner.py`**

The `LLMAutoTuner` operates as an asynchronous agent using the "Trading-as-Git" methodology.

**Tuning Pipeline:**
1. Polls every 15 minutes.
2. Extracts live active positions and relevant metrics.
3. Packages the metrics and submits them to `gpt-5.6` (override with `OPENAI_MODEL`) with a specific prompt (derived from the `OpenAlice` concept).
4. The LLM provides a JSON payload "commit" of parameter adjustments (e.g. tightening trailing stops).
5. The tuner applies the commit to the active positions to lock in gains or give winning trades more room to breathe.

### New Environment Variables
```
OPENAI_API_KEY=<your_openai_api_key>      # Required for Auto-Tuner
OPENAI_MODEL=gpt-5.6                     # Optional; gpt-5.6-sol | terra | luna also valid
```

---

## Upgrade 6 — ShamrockGuard & Hourly Reports

### Problem
The bot could hit a major home run (e.g., $800 profit), but standard position sizing and rules-based stop losses might risk giving back substantial portions of those gains during later choppy conditions. There was no overarching daily profit targeting. Also, the user had no way to monitor status without logging into the dashboard.

### Solution

**New files: `core/shamrock_guard.py` & `core/hourly_report.py`**

**ShamrockGuard Logic:**
1. Allows setting a `DAILY_PROFIT_TARGET` (default $500).
2. Constantly checks portfolio PnL.
3. If PnL hits ≥ 90% of the target, triggers **Bank-It Mode**, throttling position sizing (e.g., 0.2x multiplier) to secure profits.
4. If Daily PnL hits ≤ -20% of portfolio, halts new entries for the rest of the day.

**Hourly Reports Logic:**
1. Integrated into `PositionMonitor`.
2. Every 60 minutes, compiles metrics: current daily PnL, active positions, and active regime.
3. Dispatches reports via Slack and Telegram.

### New Environment Variables
```
DAILY_PROFIT_TARGET_USD=500           # Target to hit Bank-It Mode
```

---

## Summary of Modified Files

| File | Change |
|---|---|
| `core/mev_protection.py` | **Rewritten** — Flashbots bundle, Protect RPC, Jito bundle, CoW live execution |
| `core/executor.py` | **Upgraded** — `_execute_via_flashbots()` added; routing chain updated |
| `core/solana_executor.py` | **Upgraded** — Jito bundle submission as primary path with dynamic tip scaling |
| `core/bundle_detector.py` | **New** — Block-0 sniper detection for EVM and Solana |
| `core/wallet_monitor.py` | **New** — Proactive copy-trading daemon with tier system |
| `ml/weight_optimizer.py` | **New** — XGBoost dynamic weight optimizer |
| `scanner/gem_scanner.py` | **Upgraded** — Bundle gate wired in; ML dynamic weights in scoring formula |
| `main.py` | **Upgraded** — WalletMonitor daemon started in `run_bot_loop()` |
| `core/llm_auto_tuner.py` | **New** — AI Auto-Tuner with gpt-5.6 (OPENAI_MODEL) |
| `core/shamrock_guard.py` | **New** — Daily targets and Bank-it mode |
| `core/hourly_report.py` | **New** — Status reporting every 60m |
| `config/settings.py` | **Upgraded** — All new env vars documented with safe defaults |

---

## Required `.env` Additions

Add these to your `.env` file on the Hetzner VPS:

```bash
# Upgrade 1: MEV
FLASHBOTS_SIGNING_KEY=<generate with eth_account.Account.create()>
JITO_AUTH_KEY=                          # Optional
HELIUS_API_KEY=<get from helius.dev>    # Strongly recommended

# Upgrade 2: Bundle Detector
BUNDLE_DETECTOR_ENABLED=true
BUNDLE_REJECT_THRESHOLD=0.20

# Upgrade 3: ML Weights
ML_WEIGHT_OPTIMIZER_ENABLED=true
ML_WEIGHT_MIN_TRADES=20

# Upgrade 4: Wallet Monitor
WALLET_MONITOR_ENABLED=true
WALLET_MONITOR_COPY_SIZE_PCT=0.5
WALLET_MONITOR_MAX_COPY_USD=500

# Upgrade 5 & 6: AI Auto-Tuning & Protection
OPENAI_API_KEY=<your_openai_key>
DAILY_PROFIT_TARGET_USD=500
```

---

*Last updated: 2026-06-11 | Branch: feature/ai-auto-tuner-and-guard*
