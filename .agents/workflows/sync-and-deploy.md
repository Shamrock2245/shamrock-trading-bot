---
description: How to sync Manus changes and redeploy the trading bot to Hetzner
---
// turbo-all

## Prerequisites
- SSH access to Hetzner VPS: `ssh root@5.78.100.228`
- Bot repo cloned at `/root/shamrock-trading-bot` on the server
- Docker and docker-compose installed on the server

## Steps

1. SSH into the Hetzner server:
```bash
ssh root@5.78.100.228
```

2. Navigate to the repo directory:
```bash
cd /root/shamrock-trading-bot
```

3. Pull the latest changes from GitHub:
```bash
git pull origin main
```

4. Stop the running Docker containers:
```bash
docker compose down
```

5. Rebuild the Docker images (no cache to pick up all changes):
```bash
docker compose build --no-cache
```

6. Start the containers in detached mode:
```bash
docker compose up -d
```

7. Verify the containers are running:
```bash
docker compose ps
```

8. Check the bot logs to confirm it started correctly:
```bash
docker compose logs -f --tail=50 bot
```

## Notes
- If you only need to rebuild a specific service: `docker compose build --no-cache bot`
- To check if the bot is trading: look for "Cycle" log entries and guardrail messages
- The `.env` file on the server should already have all required API keys configured
- If Docker build fails, check for Python dependency issues in `requirements.txt`
- To quickly restart without rebuilding: `docker compose restart bot`
