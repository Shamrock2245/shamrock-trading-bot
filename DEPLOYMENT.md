# Deployment Guide — Hetzner VPS

This guide covers deploying the Shamrock Trading Bot to the provisioned Hetzner VPS
(`shamrock-trading` project, Ashburn VA datacenter).

---

## Server Details

| Property | Value |
|----------|-------|
| Provider | Hetzner Cloud |
| Project | shamrock-trading |
| Location | Ashburn, VA (ash) |
| Server type | CPX21 (3 vCPU / 4 GB RAM / 80 GB SSD) |
| OS | Ubuntu 22.04 LTS |
| IP | Provisioned via API (check Hetzner console) |

---

## 1. Initial Server Setup

### 1.1 Connect via SSH

```bash
ssh -i ~/.ssh/ssh-key-2026-03-13.key root@<SERVER_IP>
```

### 1.2 Update system and install Docker

```bash
apt update && apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sh
systemctl enable docker
systemctl start docker

# Install Docker Compose
apt install docker-compose-plugin -y

# Verify
docker --version
docker compose version
```

### 1.3 Create a non-root user (recommended)

```bash
adduser shamrock
usermod -aG docker shamrock
usermod -aG sudo shamrock

# Copy SSH key to new user
mkdir -p /home/shamrock/.ssh
cp ~/.ssh/authorized_keys /home/shamrock/.ssh/
chown -R shamrock:shamrock /home/shamrock/.ssh
chmod 700 /home/shamrock/.ssh
chmod 600 /home/shamrock/.ssh/authorized_keys
```

### 1.4 Harden SSH

```bash
# Edit SSH config
nano /etc/ssh/sshd_config

# Set these values:
# PasswordAuthentication no
# PermitRootLogin no
# PubkeyAuthentication yes

systemctl restart sshd
```

### 1.5 Configure firewall

```bash
ufw allow OpenSSH
ufw enable
ufw status
```

---

## 2. Deploy the Bot

### 2.1 Clone the repository

```bash
# Switch to shamrock user
su - shamrock

# Clone repo
git clone https://github.com/Shamrock2245/shamrock-trading-bot.git
cd shamrock-trading-bot
```

### 2.2 Configure environment variables

```bash
# Copy the example env file
cp .env.example .env

# Edit with your actual values
nano .env
```

**Required variables to fill in:**

```bash
# Trading mode — KEEP AS PAPER until fully validated
MODE=paper

# Wallet private keys (NEVER commit these)
WALLET_PRIVATE_KEY_PRIMARY=0x...
WALLET_PRIVATE_KEY_B=0x...
WALLET_PRIVATE_KEY_C=0x...

# RPC URLs (get free ones from Alchemy, Infura, or Ankr)
ETH_RPC_URL=https://eth-mainnet.g.alchemy.com/v2/YOUR_KEY
BASE_RPC_URL=https://base-mainnet.g.alchemy.com/v2/YOUR_KEY
ARBITRUM_RPC_URL=https://arb-mainnet.g.alchemy.com/v2/YOUR_KEY
POLYGON_RPC_URL=https://polygon-mainnet.g.alchemy.com/v2/YOUR_KEY
BSC_RPC_URL=https://bsc-dataseed.binance.org/

# API Keys
ONEINCH_API_KEY=your_key_here
```

> **Security**: The `.env` file should only be readable by the `shamrock` user.
> ```bash
> chmod 600 .env
> ```

### 2.3 Build and start with Docker Compose

```bash
# Build the image
docker compose build

# Start in detached mode
docker compose up -d

# View logs
docker compose logs -f bot
```

### 2.4 Verify the bot is running

```bash
# Check container status
docker compose ps

# Check bot logs
docker compose logs bot --tail=50

# Run a quick balance check
docker compose exec bot python main.py --balances
```

---

## 3. Running Modes

### Paper mode (default — safe)

```bash
# In .env:
MODE=paper

# Restart bot
docker compose restart bot
```

### Live mode (real trades)

> **WARNING**: Only enable live mode after completing the full pre-live checklist in `GUARDRAILS.md`.

```bash
# In .env:
MODE=live

# Restart bot
docker compose restart bot

# Monitor closely
docker compose logs -f bot
```

---

## 4. Useful Commands

### Check wallet balances

```bash
docker compose exec bot python main.py --balances
```

### Run a gem scan

```bash
docker compose exec bot python main.py --scan
```

### Test a specific token snipe (paper mode)

```bash
docker compose exec bot python main.py --snipe 0xTOKEN_ADDRESS base
```

### View output files

```bash
# Balances JSON
docker compose exec bot cat output/balances.json

# Latest gem scan
docker compose exec bot cat output/gem_scan.json

# Snipe example
docker compose exec bot cat output/snipe_example.json
```

### View safety log

```bash
docker compose exec bot tail -f logs/safety.log
```

---

## 5. Log Management

Logs are stored in the `logs/` directory inside the container, which is mounted as a volume.

```bash
# View all logs
ls -la logs/

# Bot activity log
tail -f logs/bot.log

# Safety audit log (all blocked tokens)
tail -f logs/safety.log
```

### Log rotation

Add log rotation to prevent disk fill:

```bash
# On the host server
cat > /etc/logrotate.d/shamrock-bot << 'EOF'
/home/shamrock/shamrock-trading-bot/logs/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
}
EOF
```

---

## 6. Monitoring & Alerts

### Uptime monitoring

Use [Uptime Robot](https://uptimerobot.com) (free) to monitor the server:
1. Create a new monitor → TCP port monitor
2. Set host to `<SERVER_IP>`, port `22`
3. Set check interval to 5 minutes
4. Add email/SMS alerts

### Process monitoring

The Docker container is configured with `restart: unless-stopped`, so it will automatically restart after crashes or server reboots.

```bash
# Verify auto-restart is configured
docker inspect shamrock-trading-bot_bot_1 | grep RestartPolicy
```

---

## 7. Updates

### Pull latest code and redeploy

```bash
cd ~/shamrock-trading-bot
git pull origin main
docker compose build
docker compose up -d
```

### Zero-downtime update

```bash
# Build new image without stopping current
docker compose build bot

# Restart only the bot service
docker compose up -d --no-deps bot
```

---

## 8. Backup

### Backup configuration (not keys)

```bash
# Backup everything except .env (which contains keys)
tar -czf shamrock-bot-backup-$(date +%Y%m%d).tar.gz \
    --exclude='.env' \
    --exclude='logs/' \
    --exclude='output/' \
    ~/shamrock-trading-bot/
```

### Backup output data

```bash
tar -czf shamrock-output-$(date +%Y%m%d).tar.gz ~/shamrock-trading-bot/output/
```

---

## 9. Troubleshooting

### Bot not connecting to RPC

```bash
# Test RPC connectivity
docker compose exec bot python3 -c "
from web3 import Web3
w3 = Web3(Web3.HTTPProvider('YOUR_RPC_URL'))
print('Connected:', w3.is_connected())
print('Block:', w3.eth.block_number)
"
```

### Container keeps restarting

```bash
# Check exit code
docker compose ps
docker compose logs bot --tail=100
```

Common causes:
- Missing required environment variables (check `.env`)
- Python import error (check `requirements.txt` was installed)
- RPC URL invalid or rate-limited

### Out of disk space

```bash
# Check disk usage
df -h

# Clean Docker images
docker system prune -f

# Rotate logs manually
truncate -s 0 logs/bot.log
```

---

*Server provisioned March 2026 | Hetzner Cloud — Ashburn, VA*
