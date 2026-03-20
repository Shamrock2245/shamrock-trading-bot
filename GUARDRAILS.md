# ☘️ Shamrock Trading Bot — Guardrails & Safety System

> **This document is mandatory reading before enabling live trading.**
> Every guardrail described here is enforced in code. This document explains
> the *why* behind each rule so operators understand what they are overriding
> if they ever modify these thresholds.

---

## Table of Contents

1. [Operating Modes](#1-operating-modes)
2. [Pre-Trade Safety Pipeline](#2-pre-trade-safety-pipeline)
3. [Risk Management Rules](#3-risk-management-rules)
4. [Circuit Breaker](#4-circuit-breaker)
5. [MEV Protection](#5-mev-protection)
6. [Private Key Security](#6-private-key-security)
7. [Pre-Live Checklist](#7-pre-live-checklist)
8. [Incident Response](#8-incident-response)

---

## 1. Operating Modes

The bot operates in one of two modes, controlled by the `MODE` environment variable.

| Mode | Behavior | Real Funds at Risk |
|------|----------|-------------------|
| `paper` | Simulates all trades — no on-chain transactions | **No** |
| `live` | Executes real on-chain swaps | **Yes** |

**Default mode is `paper`.** The bot will never execute a real trade unless `MODE=live` is explicitly set in the environment. This is enforced in `config/settings.py` and checked in `core/executor.py` before every trade.

> **Rule**: Always run in `paper` mode for at least 48 hours on a new chain or strategy before switching to `live`.

---

## 2. Pre-Trade Safety Pipeline

Every token must pass **all** of the following checks before any buy order is placed. A single failure immediately blocks the trade and logs the reason to `logs/safety.log`.

### 2.1 Blocklist Check (Instant Reject)

The permanent blocklist in `config/tokens.py` contains known scam and rug-pull contract addresses. Any token on this list is rejected before any API call is made. Confirmed scams discovered at runtime are added to the in-memory blocklist via `add_to_blocklist()`.

### 2.2 GoPlus Security API

GoPlus performs static and dynamic analysis of the token contract. The following conditions **immediately block** a trade:

| Condition | Threshold | Reason |
|-----------|-----------|--------|
| Buy tax | > 5% | High taxes are a common rug mechanism |
| Sell tax | > 5% | Sell-side taxes trap investors |
| Contract unverified | `is_open_source == 0` | Cannot audit unverified contracts |
| Owner can drain | `owner_change_balance == 1` | Owner can zero out holder balances |
| Sell restrictions | `cannot_sell_all == 1` | Classic honeypot pattern |

### 2.3 Honeypot.is Simulation

Honeypot.is **simulates an actual buy and sell transaction** against the contract on-chain (without spending real funds). This catches dynamic honeypots that pass static analysis but fail at execution time.

- If `isHoneypot == true` → **BLOCKED** and address added to runtime blocklist
- If simulated buy tax > 10% → **BLOCKED**
- If simulated sell tax > 10% → **BLOCKED**

### 2.4 Token Sniffer Score

Token Sniffer's "smell test" assigns a 0–100 score based on 50+ scam pattern checks. Tokens scoring below **30/100** are blocked. This is an advisory check — API failures do not block trades.

### 2.5 Safety Check Flow

```
Token Address
     │
     ▼
[Blocklist?] ──YES──► BLOCKED
     │ NO
     ▼
[Stablecoin?] ──YES──► SKIP (not a gem target)
     │ NO
     ▼
[Whitelisted?] ──YES──► SAFE (skip deep checks)
     │ NO
     ▼
[GoPlus API] ──FAIL──► BLOCKED + reason logged
     │ PASS
     ▼
[Honeypot.is] ──FAIL──► BLOCKED + added to blocklist
     │ PASS
     ▼
[Token Sniffer] ──score < 30──► BLOCKED
     │ PASS
     ▼
   SAFE ✅
```

---

## 3. Risk Management Rules

All risk parameters are set via environment variables and enforced by `core/risk.py`.

### 3.1 Position Sizing

| Parameter | Default | Description |
|-----------|---------|-------------|
| `MAX_POSITION_SIZE_PCT` | 5% | Maximum % of wallet balance per trade |
| `MIN_ETH_BALANCE_ALERT` | 0.05 ETH | Minimum ETH to keep for gas |

The bot **never** spends more than 90% of the available balance in a single trade, regardless of the position size setting. This ensures gas fees can always be paid.

### 3.2 Daily Loss Limit

Each wallet has a daily loss limit (configurable per wallet in `config/wallets.py`). Once the cumulative realized loss for the day reaches this limit, **no new trades are opened** for that wallet until the next UTC day.

| Wallet | Default Daily Loss Limit |
|--------|--------------------------|
| Primary | 0.5 ETH |
| Wallet B | 0.3 ETH |
| Wallet C | 0.1 ETH (reserve — conservative) |

### 3.3 Concurrent Positions

Each wallet has a maximum number of simultaneously open positions. This prevents over-concentration during volatile market conditions.

| Wallet | Default Max Positions |
|--------|-----------------------|
| Primary | 5 |
| Wallet B | 3 |
| Wallet C | 1 |

### 3.4 Stop-Loss Rules

| Rule | Default | Trigger |
|------|---------|---------|
| Trailing stop | 10% from peak | Sell when price drops 10% from highest point since entry |
| Hard stop | 25% from entry | Sell immediately if position is down 25% |

---

## 4. Circuit Breaker

The circuit breaker is a **portfolio-level emergency stop** that halts all trading if the total portfolio value drops more than a configured threshold within a 24-hour window.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `CIRCUIT_BREAKER_PERCENT` | 15% | Portfolio drop threshold to trip breaker |

**When tripped:**
- All new trade execution is blocked
- An alert is logged at `CRITICAL` level to `logs/bot.log`
- The bot continues running (scanning and monitoring) but executes no trades
- Manual reset required via `risk_manager.reset_circuit_breaker()` — this is intentional

**To reset:** An operator must explicitly call the reset function. This forces a human review before trading resumes.

---

## 5. MEV Protection

Maximal Extractable Value (MEV) attacks — front-running, sandwich attacks, and back-running — can cause significant losses on DEX trades. The bot uses two layers of protection:

### 5.1 CoW Protocol (Ethereum — Primary)

CoW Protocol uses **batch auctions** to match orders off-chain before settling on-chain. Because orders are matched in batches rather than sequentially in the mempool, front-running is structurally impossible. CoW is the preferred execution path for all Ethereum trades.

### 5.2 1inch Aggregation with Private RPC

For non-Ethereum chains (Base, Arbitrum, Polygon, BSC), trades are routed through 1inch with the option to use private RPC endpoints (Flashbots-compatible nodes where available). This reduces mempool visibility of pending transactions.

### 5.3 Slippage Configuration

Default slippage for gem snipes is **2%** (`slippage_bps=200`). This is intentionally higher than blue-chip swaps to account for new token volatility, but low enough to prevent excessive sandwich attack losses.

---

## 6. Private Key Security

> **CRITICAL: Private keys must NEVER appear in source code, configuration files, or logs.**

### Mandatory Rules

1. **Environment variables only** — Keys are loaded exclusively from environment variables (`WALLET_PRIVATE_KEY_PRIMARY`, `WALLET_PRIVATE_KEY_B`, `WALLET_PRIVATE_KEY_C`).
2. **`.env` file is gitignored** — The `.env` file is listed in `.gitignore`. Never commit it.
3. **No logging of keys** — The codebase contains no `logger.info(private_key)` or similar statements. This is enforced by code review.
4. **Vault integration** — For production deployments, use AWS Secrets Manager or HashiCorp Vault instead of `.env` files. See `DEPLOYMENT.md` for setup instructions.
5. **Key rotation** — If a key is ever exposed (e.g., accidentally committed to git), rotate it immediately and transfer funds to a new wallet before the compromised key can be exploited.

### What the Code Does

- `config/wallets.py` reads keys from `os.environ` — never from files
- `WalletConfig.private_key` returns `None` in paper mode even if the key is set
- The `has_private_key` property returns a boolean without exposing the key value
- All trade execution checks for key presence before attempting to sign

---

## 7. Pre-Live Checklist

Complete **every item** on this checklist before setting `MODE=live`.

### Environment Setup
- [ ] All three wallet private keys set as environment variables (not in `.env` for production)
- [ ] RPC URLs configured for all active chains
- [ ] 1inch API key configured
- [ ] GoPlus API key configured (if using paid tier)
- [ ] Token Sniffer API key configured

### Safety Verification
- [ ] Run `python main.py --scan` in paper mode — confirm safety checks are running
- [ ] Manually test a known honeypot address — confirm it is blocked
- [ ] Confirm `logs/safety.log` is being written
- [ ] Review blocklist in `config/tokens.py` — add any known local scams

### Risk Parameters
- [ ] Review `MAX_POSITION_SIZE_PCT` — is 5% appropriate for current balance?
- [ ] Review daily loss limits per wallet
- [ ] Review `CIRCUIT_BREAKER_PERCENT` — 15% is the recommended minimum
- [ ] Confirm `MIN_ETH_BALANCE_ALERT` is set high enough to cover gas

### Infrastructure
- [ ] Server is running 24/7 (Hetzner VPS or equivalent)
- [ ] Docker container configured with `restart: unless-stopped`
- [ ] Log rotation configured (see `DEPLOYMENT.md`)
- [ ] Monitoring/alerting set up (Grafana, Uptime Robot, or similar)
- [ ] Backup of wallet addresses (not keys) documented

### Paper Mode Validation
- [ ] Bot ran in paper mode for minimum 48 hours without errors
- [ ] Gem scan producing reasonable candidates
- [ ] Safety pipeline blocking test scam tokens
- [ ] Risk manager correctly calculating position sizes
- [ ] Output JSON files (`output/balances.json`, `output/gem_scan.json`) look correct

---

## 8. Incident Response

### Suspected Compromise

If you suspect a wallet private key has been exposed:

1. **Immediately** transfer all funds from the compromised wallet to a new, secure wallet
2. Revoke all token approvals on the compromised wallet using [Revoke.cash](https://revoke.cash)
3. Rotate the environment variable with the new wallet's key
4. Update `config/wallets.py` with the new wallet address
5. Review `logs/bot.log` for any unauthorized transactions

### Bot Executing Unexpected Trades

1. Set `MODE=paper` immediately (restart the bot with the updated env var)
2. Review `logs/bot.log` and `logs/safety.log` for the last 24 hours
3. Check if the circuit breaker was tripped
4. Review open positions and manually close any that are outside risk parameters

### RPC Node Failure

The balance fetcher and executor both implement automatic fallback to secondary RPC URLs. If all RPCs for a chain fail:
- The bot logs an error and skips that chain for the current cycle
- No trades are executed on the failed chain
- The bot continues operating on other chains

---

*Last updated: March 2026 | Maintained by Shamrock2245*
