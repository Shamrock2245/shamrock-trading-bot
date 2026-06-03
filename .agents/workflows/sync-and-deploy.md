---
description: sync local Manus changes and redeploy the trading bot to Hetzner
---
// turbo-all

# "Get It Right" Deploy Loop
```
preflight → git push → pull on server → rebuild → review → [rollback?]
```
If preflight fails, the deploy is BLOCKED. If review grades FAIL, rollback runs automatically.
Each step writes a structured report to `output/` for the next step to consume.

## Prerequisites
- SSH deploy key exists at `.shamrock_deploy_key` in the project root (already set up)
- Bot repo cloned at `/opt/shamrock-trading-bot` on the server

## SSH Helper
```bash
KEY=/Users/brendan/Desktop/shamrock-trading-bot/.shamrock_deploy_key
SERVER=root@178.156.179.237
REPO=/opt/shamrock-trading-bot
```

---

## 🚦 Phase 1 — PREFLIGHT (local checks — MUST pass before any deploy)

Run syntax check + tests locally. **If this fails, STOP. Do not proceed to Phase 2.**

// turbo
1. Run preflight checks:
```bash
cd /Users/brendan/Desktop/shamrock-trading-bot && python scripts/preflight_check.py --fix-hint
```
> Exit code 0 = proceed. Exit code 1 = fix the failures listed above, then re-run preflight.
> Report written to `output/preflight_report.json`.

---

## 🚀 Phase 2 — DEPLOY (commit → push → pull on server → rebuild → restart)

Only run these steps if Phase 1 passed with exit code 0.

2. Stage and commit all changes:
```bash
cd /Users/brendan/Desktop/shamrock-trading-bot && git add -A && git status --short
```

3. Commit:
```bash
cd /Users/brendan/Desktop/shamrock-trading-bot && git commit -m "deploy: $(date '+%Y-%m-%d %H:%M') — post-preflight"
```

4. Push to GitHub:
```bash
cd /Users/brendan/Desktop/shamrock-trading-bot && git push origin main
```

5. Pull latest on the server:
```bash
ssh -i /Users/brendan/Desktop/shamrock-trading-bot/.shamrock_deploy_key -o StrictHostKeyChecking=no root@178.156.179.237 'cd /opt/shamrock-trading-bot && git pull origin main'
```

6. Stop running containers:
```bash
ssh -i /Users/brendan/Desktop/shamrock-trading-bot/.shamrock_deploy_key -o StrictHostKeyChecking=no root@178.156.179.237 'cd /opt/shamrock-trading-bot && docker compose down'
```

7. Rebuild Docker images (no cache):
```bash
ssh -i /Users/brendan/Desktop/shamrock-trading-bot/.shamrock_deploy_key -o StrictHostKeyChecking=no root@178.156.179.237 'cd /opt/shamrock-trading-bot && docker compose build --no-cache'
```

8. Start containers in detached mode:
```bash
ssh -i /Users/brendan/Desktop/shamrock-trading-bot/.shamrock_deploy_key -o StrictHostKeyChecking=no root@178.156.179.237 'cd /opt/shamrock-trading-bot && docker compose up -d'
```

---

## 🔍 Phase 3 — REVIEW (post-deploy health check)

Run from your local machine. Reviewer SSHes in and grades the deployment.

9. Wait for bot to stabilize then run reviewer:
```bash
cd /Users/brendan/Desktop/shamrock-trading-bot && python scripts/reviewer.py --wait 20 --tail-lines 100
```
> Exit code 0 = pass (done ✅)
> Exit code 1 = warn (monitor — bot is running but has warnings)
> Exit code 2 = fail → proceed to Phase 4 (rollback)
> Report written to `output/review_report.json`.

---

## 🔄 Phase 4 — ROLLBACK (only if Phase 3 exit code = 2)

Only run this if the reviewer returned exit code 2 (FAIL grade).

10. Run rollback agent:
```bash
cd /Users/brendan/Desktop/shamrock-trading-bot && python scripts/rollback.py
```
> Rolls back server to the previous commit, rebuilds, and verifies.
> After rollback: read `output/review_report.json` → fix the reported issues → loop back to Phase 1.

---

## 📊 Report Files (the "context bridge" between iterations)

| File | Written by | Read by |
|------|-----------|---------| 
| `output/preflight_report.json` | `preflight_check.py` | `reviewer.py` |
| `output/review_report.json` | `reviewer.py` | `rollback.py`, AI agent |
| `output/rollback_report.json` | `rollback.py` | Human / AI agent |

---

## 📋 Notes

> **⚠️ CRITICAL: `docker compose restart` does NOT pick up code changes.**
> Source code (`core/`, `main.py`, `scanner/`, etc.) is baked into the Docker image at build time.
> Only `logs/`, `data/`, and `output/` are volume-mounted at runtime.
> **ALWAYS use `docker compose build --no-cache && docker compose up -d` after any code change.**
> Using `restart` alone will run the OLD code and silently appear to work.

- To quick-restart (state files / env changes only — NOT code changes):
  ```bash
  ssh -i /Users/brendan/Desktop/shamrock-trading-bot/.shamrock_deploy_key -o StrictHostKeyChecking=no root@178.156.179.237 'cd /opt/shamrock-trading-bot && docker compose restart bot'
  ```
- To check live bot logs at any time:
  ```bash
  ssh -i /Users/brendan/Desktop/shamrock-trading-bot/.shamrock_deploy_key -o StrictHostKeyChecking=no root@178.156.179.237 'cd /opt/shamrock-trading-bot && docker compose logs --tail=80 bot'
  ```
- To roll back to a specific commit:
  ```bash
  cd /Users/brendan/Desktop/shamrock-trading-bot && python scripts/rollback.py --to <SHA>
  ```
- To dry-run a rollback (see what would happen, no changes made):
  ```bash
  cd /Users/brendan/Desktop/shamrock-trading-bot && python scripts/rollback.py --dry-run
  ```
- If `.shamrock_deploy_key` is ever lost, regenerate with:
  ```bash
  ssh-keygen -q -t ed25519 -N "" -f /Users/brendan/Desktop/shamrock-trading-bot/.shamrock_deploy_key -C "shamrock-deploy"
  cat /Users/brendan/Desktop/shamrock-trading-bot/.shamrock_deploy_key.pub | ssh root@178.156.179.237 'cat >> ~/.ssh/authorized_keys'
  ```
