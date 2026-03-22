# SECRETS HANDLING — Protecting the Keys to the Kingdom

## The Cardinal Rule
> **Private keys and API secrets NEVER appear in code, logs, commit history, or any file except `.env`.**

## Where Secrets Live
| Secret | Storage | Access |
|--------|---------|--------|
| Wallet private keys | `.env` file (gitignored) | `os.getenv()` via `config/settings.py` |
| API keys | `.env` file (gitignored) | `os.getenv()` via `config/settings.py` |
| RPC URLs | `.env` file | `config/chains.py` |

## `.env` Security
- `.env` is in `.gitignore` — NEVER committed
- `.env.example` exists with placeholder values — safe to commit
- File permissions: `chmod 600 .env` (owner read/write only)

## What Gets Logged (and What Doesn't)
| Item | Logged? | Example |
|------|---------|---------|
| Trade amounts | ✅ Yes | "Bought 1M PEPE for $150" |
| Token addresses | ✅ Yes | "0x6982508..." |
| TX hashes | ✅ Yes | "0xabc123..." |
| Wallet addresses | ✅ Yes | "0x742d35..." |
| Private keys | ❌ NEVER | — |
| API keys | ❌ NEVER | — |
| RPC URLs with keys | ❌ NEVER | — |

## Production Upgrades (When Scaling)
| Level | Tool | When |
|-------|------|------|
| Dev/Test | `.env` file | Now |
| Production | AWS Secrets Manager | When running on cloud |
| Enterprise | HashiCorp Vault | Multi-operator setup |

## If a Key Is Compromised
1. **Immediately** revoke the key at the provider
2. Generate a new key
3. Update `.env`
4. Restart the bot
5. If a wallet private key: Transfer all funds to a NEW wallet IMMEDIATELY
6. Audit all transactions since the suspected compromise
7. Update the new wallet key in `.env`

## Cross-Reference
See `SECURITY.md` at root for additional security practices.
