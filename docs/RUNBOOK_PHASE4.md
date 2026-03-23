# Shamrock Trading Bot — Phase 4 Operational Runbook

This document summarizes the final code gaps filled in Phase 4 and provides the exact steps to run the bot in production. The bot is now fully aligned with the Alex Becker playbook, featuring Kelly Criterion position sizing, Flashbots MEV protection, and CTO (Community Takeover) detection.

## 1. What Was Built in Phase 4

### 🧠 Kelly Criterion & Phase-Based Sizing (`core/wallet_router.py`)
The bot no longer uses static percentage sizing. It now dynamically calculates position sizes based on:
- **Capital Phase:** Seed ($0-$15K) → Growth ($15K-$50K) → Acceleration ($50K-$250K) → Whale ($250K+)
- **Kelly Criterion:** Bet size is proportional to the edge (win rate × win/loss ratio). Higher gem scores = higher win rate assumption = larger position size.
- **Chain-Aware Slippage:** Base/Solana new tokens get 150-300 bps slippage; Ethereum gets 50 bps.

### 🛡️ Flashbots & CoW Protocol MEV Protection (`core/mev_protection.py`)
The "not yet implemented" stubs in the executor have been replaced with full production code:
- **Flashbots:** Ethereum transactions are bundled and sent directly to block builders via `rpc.flashbots.net`, completely bypassing the public mempool to prevent sandwich attacks.
- **CoW Protocol:** Full EIP-712 structured data signing is implemented for CoW batch auctions, ensuring the best possible execution price on Ethereum mainnet.

### 🚀 CTO (Community Takeover) Detection (`scanner/gem_scanner.py`)
- The scanner now explicitly flags CTOs from DexScreener.
- CTOs receive an automatic **+8 point score bonus** and are tagged with the `cto_revival` strategy.
- CTOs with a score ≥ 75 bypass the TA pipeline and enter the **Express Lane** for immediate execution.
- **Signal Decay:** CTO signals older than 48 hours are automatically ignored.

### 🐳 Docker & pandas-ta Fix (`Dockerfile` & `vendor/README.md`)
- The Dockerfile has been upgraded to **Python 3.12-slim**.
- This resolves the `pandas-ta` installation failure (which requires Python 3.12+ for f-string syntax).
- The manual fallback indicators in `strategies/indicators.py` remain fully functional for local Python 3.11 testing.

### ⏱️ Safety API Caching (`core/safety.py`)
- GoPlus and Honeypot.is API results are now cached in memory for **5 minutes**.
- This prevents rate-limit bans when the scanner evaluates the same token multiple times across different pairs or chains.

---

## 2. How to Run the Bot

### Prerequisites
Ensure your `.env` file is fully populated. New required variables for Phase 4:
```env
# Required for Ethereum MEV protection
FLASHBOTS_SIGNING_KEY=your_flashbots_auth_key_here
COW_API_URL=https://api.cow.fi/mainnet

# Required for Solana execution
SOLANA_RPC_URL=https://api.mainnet-beta.solana.com
JUPITER_API_URL=https://quote-api.jup.ag/v6
```

### Running via Docker (Recommended for Production)
The Docker image is now fully optimized and includes the `pandas-ta` library.

```bash
# Build the image
docker-compose build

# Run in detached mode
docker-compose up -d

# View live logs
docker-compose logs -f bot
```

### Running Locally (Development/Paper Trading)
If running locally on Python 3.11, the bot will automatically use the manual indicator fallbacks.

```bash
# Install dependencies
pip install -r requirements.txt

# Run the health check to verify API keys
python scripts/health_check.py

# Run the bot in paper trading mode
MODE=paper python main.py
```

---

## 3. Monitoring & Analytics

- **Dashboard:** Run `streamlit run dashboard/Home.py` to view the live portfolio, open positions, and recent trades.
- **Logs:** Check `logs/shamrock.log` for detailed routing decisions, Kelly sizing calculations, and MEV bundle submissions.
- **Positions:** Open positions are persisted in `output/positions.json`. The background monitor will automatically execute take-profits (2x, 5x, 10x) and trailing stops.

---
*Document produced by Manus AI — Mar 22, 2026*
