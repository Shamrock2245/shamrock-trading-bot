---
description: sync local Manus changes and redeploy the trading bot to Hetzner
---
// turbo-all

## Prerequisites
- SSH deploy key exists at `.shamrock_deploy_key` in the project root (already set up)
- Bot repo cloned at `/root/shamrock-trading-bot` on the server

## SSH Helper
All commands use the project-level deploy key. No password required.
```bash
KEY=/Users/brendan/Desktop/shamrock-trading-bot/.shamrock_deploy_key
SERVER=root@5.161.126.32
REPO=/root/shamrock-trading-bot
```

## Steps

1. Pull latest changes on the server:
```bash
ssh -i /Users/brendan/Desktop/shamrock-trading-bot/.shamrock_deploy_key -o StrictHostKeyChecking=no root@5.161.126.32 'cd /root/shamrock-trading-bot && git pull origin main'
```

2. Stop the running containers:
```bash
ssh -i /Users/brendan/Desktop/shamrock-trading-bot/.shamrock_deploy_key -o StrictHostKeyChecking=no root@5.161.126.32 'cd /root/shamrock-trading-bot && docker compose down'
```

3. Rebuild Docker images (no cache):
```bash
ssh -i /Users/brendan/Desktop/shamrock-trading-bot/.shamrock_deploy_key -o StrictHostKeyChecking=no root@5.161.126.32 'cd /root/shamrock-trading-bot && docker compose build --no-cache'
```

4. Start containers in detached mode:
```bash
ssh -i /Users/brendan/Desktop/shamrock-trading-bot/.shamrock_deploy_key -o StrictHostKeyChecking=no root@5.161.126.32 'cd /root/shamrock-trading-bot && docker compose up -d'
```

5. Verify all containers are running:
```bash
ssh -i /Users/brendan/Desktop/shamrock-trading-bot/.shamrock_deploy_key -o StrictHostKeyChecking=no root@5.161.126.32 'cd /root/shamrock-trading-bot && docker compose ps'
```

6. Check bot logs to confirm healthy startup:
```bash
ssh -i /Users/brendan/Desktop/shamrock-trading-bot/.shamrock_deploy_key -o StrictHostKeyChecking=no root@5.161.126.32 'cd /root/shamrock-trading-bot && docker compose logs --tail=60 bot'
```

## Notes
- Deploy key is at `.shamrock_deploy_key` (gitignored — never committed)
- All steps are `// turbo` — fully automated, no password prompts
- To quick-restart without rebuilding: 
  ```bash
  ssh -i /Users/brendan/Desktop/shamrock-trading-bot/.shamrock_deploy_key -o StrictHostKeyChecking=no root@5.161.126.32 'cd /root/shamrock-trading-bot && docker compose restart bot'
  ```
- To check live bot logs at any time:
  ```bash
  ssh -i /Users/brendan/Desktop/shamrock-trading-bot/.shamrock_deploy_key -o StrictHostKeyChecking=no root@5.161.126.32 'cd /root/shamrock-trading-bot && docker compose logs --tail=80 bot'
  ```
- If `.shamrock_deploy_key` is ever lost, regenerate with:
  ```bash
  ssh-keygen -q -t ed25519 -N "" -f /Users/brendan/Desktop/shamrock-trading-bot/.shamrock_deploy_key -C "shamrock-deploy"
  cat /Users/brendan/Desktop/shamrock-trading-bot/.shamrock_deploy_key.pub | ssh root@5.161.126.32 'cat >> ~/.ssh/authorized_keys'
  ```
