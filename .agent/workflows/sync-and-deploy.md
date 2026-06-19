---
description: How to sync Manus changes and redeploy the trading bot to Hetzner
---

# Sync and Deploy to Hetzner VPS

## Prerequisites
- Working directory: `/Users/brendan/Desktop/shamrock-trading-bot`
- Hetzner VPS IP: `46.62.231.43`
- SSH user: `root`
- Docker Compose services: `bot`, `dashboard`, `health`, `db`

## Steps

### 1. Commit and push local changes first
Follow the `/commit-and-push` workflow to get changes on GitHub.

### 2. SSH into Hetzner and pull latest code
// turbo
```bash
ssh root@46.62.231.43 "cd /root/shamrock-trading-bot && git pull origin main"
```

### 3. Rebuild and restart the bot container
```bash
ssh root@46.62.231.43 "cd /root/shamrock-trading-bot && docker compose down bot && docker compose build bot && docker compose up -d bot"
```

### 4. Verify the bot is running
// turbo
```bash
ssh root@46.62.231.43 "docker compose -f /root/shamrock-trading-bot/docker-compose.yml ps --format '{{.Name}} {{.Status}}'"
```

### 5. Check recent logs
// turbo
```bash
ssh root@46.62.231.43 "docker logs shamrock-bot --tail 30"
```

## Rebuild ALL services (if needed)
```bash
ssh root@46.62.231.43 "cd /root/shamrock-trading-bot && docker compose down && docker compose build && docker compose up -d"
```

## Important Notes
- Docker service names are: `bot`, `dashboard`, `health`, `db` (NOT `shamrock-bot`)
- The container names (visible in `docker ps`) are `shamrock-bot`, `shamrock-dashboard`, etc.
- The `version` attribute in `docker-compose.yml` is obsolete but harmless
- If the VPS IP changes, check the Hetzner Console at https://console.hetzner.com/
