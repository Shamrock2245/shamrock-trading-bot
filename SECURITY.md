# Security Policy

## Supported Versions

This project is under active development. Security fixes are applied to the `main` branch only.

| Version | Supported |
|---------|-----------|
| `main` (latest) | ✅ Yes |
| Older branches | ❌ No |

---

## Reporting a Vulnerability

If you discover a security vulnerability in this repository — particularly one that could lead to loss of funds — **do not open a public GitHub issue**.

Please report vulnerabilities privately to the repository owner via GitHub's private security advisory feature:
**Settings → Security → Advisories → New draft security advisory**

Include:
- A clear description of the vulnerability
- Steps to reproduce
- Potential impact (e.g., fund loss, key exposure)
- Any suggested mitigations

We will acknowledge receipt within 48 hours and aim to resolve critical issues within 7 days.

---

## Security Architecture

### Private Key Handling

Private keys are **never** stored in source code or configuration files. They are loaded exclusively from environment variables at runtime:

```
WALLET_PRIVATE_KEY_PRIMARY
WALLET_PRIVATE_KEY_B
WALLET_PRIVATE_KEY_C
```

In `paper` mode (the default), the executor will not attempt to sign transactions even if keys are present.

### Pre-Trade Safety Pipeline

Every token undergoes a mandatory multi-layer safety check before any trade:

1. **Permanent blocklist** — instant rejection of known scam addresses
2. **GoPlus Security API** — contract audit, tax analysis, ownership checks
3. **Honeypot.is** — on-chain buy/sell simulation
4. **Token Sniffer** — pattern-based scam detection

See `GUARDRAILS.md` for the complete safety pipeline documentation.

### MEV Protection

- **Ethereum**: CoW Protocol batch auctions (front-running structurally impossible)
- **All chains**: 1inch aggregation with configurable private RPC support
- **Slippage limits**: Enforced per-trade to cap sandwich attack losses

### Dependency Security

- All Python dependencies are pinned to specific versions in `requirements.txt`
- Run `pip audit` regularly to check for known CVEs in dependencies
- The `web3` and `eth-account` packages are the most security-critical dependencies

---

## Known Limitations

1. **Social signal scoring** is currently a placeholder. The social score component does not yet query Twitter/Telegram APIs. This means the social score is conservative and may miss some genuine gems or fail to flag some coordinated pump-and-dump schemes.

2. **Smart money wallet tracking** is not yet implemented. The smart money score component is currently zero for all tokens. Full implementation requires a curated list of tracked wallets and on-chain event monitoring.

3. **Token Sniffer API failures** do not block trades. If the Token Sniffer API is unavailable, the check is skipped (not failed). This is intentional to avoid false positives from API downtime.

4. **Paper mode does not simulate gas costs**. In paper mode, gas costs are not deducted from the simulated balance. Live mode P&L will be lower than paper mode P&L due to gas.

---

## Security Checklist for Operators

Before deploying to a live server:

- [ ] Private keys stored in environment variables, not in `.env` files committed to git
- [ ] `.env` file is in `.gitignore` and has never been committed
- [ ] Server access restricted to SSH key authentication (password auth disabled)
- [ ] SSH key is protected with a passphrase
- [ ] Server firewall allows only necessary ports (SSH, HTTPS)
- [ ] Docker container runs as non-root user
- [ ] Log files do not contain private keys (verify with `grep -r "0x[0-9a-fA-F]\{64\}" logs/`)
- [ ] Wallet approvals reviewed and minimized on all chains

---

*This project handles real cryptocurrency funds. Security is a first-class concern.*
