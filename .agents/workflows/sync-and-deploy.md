---
description: How to sync Manus changes and redeploy the trading bot to Hetzner
---

# Sync & Deploy Trading Bot

// turbo-all

## Server Details
- **Trading Bot VPS**: `5.161.126.32` (SSH via `~/.ssh/id_ed25519`)
- **Node-RED VPS**: `178.156.179.237` (SSH via `~/.ssh/id_ed25519`)
- **Bot directory**: `/root/shamrock-trading-bot`
- **Docker services**: `shamrock-bot`, `shamrock-dashboard`, `shamrock-health`, `shamrock-db`
- **Dashboard URL**: `http://5.161.126.32:8501`

## 1. Pull latest code locally

```bash
cd /Users/brendan/Desktop/shamrock-trading-bot
git fetch origin
git diff HEAD..origin/main --stat
# If behind, update HEAD ref directly (workaround for macOS .git/logs permission lock):
# Write the latest SHA to .git/refs/heads/main using filesystem write tool
```

## 2. Review changes

```bash
git log --oneline origin/main -10
```

## 3. Pull and redeploy on Hetzner VPS

```bash
ssh -i ~/.ssh/id_ed25519 root@5.161.126.32 "\
  cd /root/shamrock-trading-bot && \
  git stash && \
  git pull origin main && \
  docker compose build bot && \
  docker compose up -d --no-deps bot && \
  sleep 5 && \
  docker compose logs bot --tail=20"
```

## 4. Verify deployment

```bash
ssh -i ~/.ssh/id_ed25519 root@5.161.126.32 "docker compose -f /root/shamrock-trading-bot/docker-compose.yml ps"
```

## 5. Check bot health via dashboard

Open `http://5.161.126.32:8501/System_Health` in browser.

## Notes
- The `.env` on the server has `MODE=live` — check this is intentional before deploying
- The local repo has a macOS permission lock on `.git/logs/refs` — use `git fetch` + manual ref write as workaround
- To rebuild all services: `docker compose build && docker compose up -d`
