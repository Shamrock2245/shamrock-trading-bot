# Postiz SSL Setup Guide — `social.shamrockbailbonds.biz`

## Problem Being Solved

Postiz was accessed over a raw HTTP IP address (`http://5.161.126.32:5200`). Chrome and other modern browsers **disable the Web Crypto API** (`crypto.randomUUID`, `crypto.subtle`, etc.) on insecure (non-HTTPS) origins. This causes the `crypto.randomUUID is not a function` error in the Postiz frontend.

**Fix:** Route traffic through an Nginx reverse proxy with a valid TLS certificate, giving the browser a **Secure Context** (`https://`).

---

## Architecture After This Setup

```
Browser (HTTPS)
    │
    ▼
Nginx :443  ← TLS terminated here (Let's Encrypt cert)
    │
    ▼  proxy_pass http://127.0.0.1:5200
Postiz container (port 5200 on host / 5000 inside container)
```

---

## Prerequisites — Do These First

### 1. DNS A Record

Add an A record in your DNS provider (Cloudflare, Namecheap, etc.):

| Type | Name   | Value          | TTL  |
|------|--------|----------------|------|
| A    | social | 5.161.126.32   | Auto |

This creates `social.shamrockbailbonds.biz → 5.161.126.32`.

**Verify DNS propagation before running the script:**
```bash
dig social.shamrockbailbonds.biz +short
# Should return: 5.161.126.32
```

### 2. Hetzner Firewall Rules

Ensure ports **80** and **443** are open inbound in your Hetzner Cloud firewall:

- Go to [console.hetzner.cloud](https://console.hetzner.cloud)
- Select your server → **Firewalls** → Add rules:
  - TCP port 80 (HTTP — needed for ACME challenge)
  - TCP port 443 (HTTPS — needed for Postiz access)

### 3. Postiz Container Running

Confirm Postiz is already running on port 5200:
```bash
docker ps | grep postiz
# Should show: 0.0.0.0:5200->5000/tcp
```

---

## Option A: One-Command Remote Deploy (Recommended)

From your **local machine** where `.shamrock_deploy_key` lives:

```bash
cd ~/Desktop/shamrock-trading-bot
bash nginx/run_on_server.sh
```

This will:
1. Upload the setup script to the VPS
2. Install Nginx + Certbot
3. Obtain the Let's Encrypt certificate
4. Write the hardened Nginx config with WebSocket support
5. Update `docker-compose.yml` with the HTTPS URLs
6. Restart the Postiz container

---

## Option B: Manual Steps on the VPS

SSH into the server:
```bash
ssh -i .shamrock_deploy_key root@5.161.126.32
```

Then run each step manually:

### Step 1 — Install Nginx and Certbot
```bash
apt-get update && apt-get install -y nginx certbot python3-certbot-nginx
```

### Step 2 — Write the Nginx config
```bash
cat > /etc/nginx/sites-available/social.shamrockbailbonds.biz.conf << 'EOF'
server {
    listen 80;
    listen [::]:80;
    server_name social.shamrockbailbonds.biz;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        proxy_pass         http://127.0.0.1:5200;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade    $http_upgrade;
        proxy_set_header   Connection "upgrade";
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }
}
EOF

ln -sf /etc/nginx/sites-available/social.shamrockbailbonds.biz.conf \
       /etc/nginx/sites-enabled/
mkdir -p /var/www/certbot
nginx -t && systemctl reload nginx
```

### Step 3 — Obtain SSL certificate
```bash
certbot --nginx \
    --non-interactive \
    --agree-tos \
    --email admin@shamrockbailbonds.biz \
    --domains social.shamrockbailbonds.biz \
    --redirect \
    --hsts \
    --staple-ocsp
```

Certbot will automatically:
- Obtain the certificate from Let's Encrypt
- Modify the Nginx config to add SSL and the HTTP→HTTPS redirect
- Reload Nginx

### Step 4 — Update docker-compose.yml

Edit `/root/shamrock-trading-bot/docker-compose.yml` and update the Postiz service environment:

```yaml
# BEFORE (causes crypto.randomUUID error):
MAIN_URL: 'http://5.161.126.32:5200'
FRONTEND_URL: 'http://5.161.126.32:5200'
NEXT_PUBLIC_BACKEND_URL: 'http://5.161.126.32:5200/api'

# AFTER (HTTPS = Secure Context = Web Crypto API works):
MAIN_URL: 'https://social.shamrockbailbonds.biz'
FRONTEND_URL: 'https://social.shamrockbailbonds.biz'
NEXT_PUBLIC_BACKEND_URL: 'https://social.shamrockbailbonds.biz/api'
```

Or use sed:
```bash
cd /root/shamrock-trading-bot
sed -i \
    -e "s|MAIN_URL:.*|MAIN_URL: 'https://social.shamrockbailbonds.biz'|g" \
    -e "s|FRONTEND_URL:.*|FRONTEND_URL: 'https://social.shamrockbailbonds.biz'|g" \
    -e "s|NEXT_PUBLIC_BACKEND_URL:.*|NEXT_PUBLIC_BACKEND_URL: 'https://social.shamrockbailbonds.biz/api'|g" \
    docker-compose.yml
```

### Step 5 — Restart Postiz
```bash
cd /root/shamrock-trading-bot
docker compose --profile social up -d postiz
```

---

## Verification

After setup, verify everything is working:

```bash
# 1. Check Nginx is running and config is valid
nginx -t && systemctl status nginx

# 2. Check SSL certificate
curl -I https://social.shamrockbailbonds.biz
# Should return: HTTP/2 200 (or 301 redirect from HTTP)

# 3. Check certificate details
certbot certificates

# 4. Test auto-renewal (dry run — no actual renewal)
certbot renew --dry-run

# 5. Check Postiz container
docker ps | grep postiz
docker logs postiz --tail=30
```

---

## SSL Auto-Renewal

Certbot installs a systemd timer that auto-renews certificates before expiry. Verify it's active:

```bash
systemctl status certbot.timer
# Should show: active (waiting)
```

Certificates renew automatically every 60 days (Let's Encrypt certs expire after 90 days).

---

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| `certbot: domain not resolving` | DNS not propagated | Wait 5–15 min, re-run certbot |
| `502 Bad Gateway` | Postiz container not running | `docker compose --profile social up -d postiz` |
| `crypto.randomUUID` still failing | Browser cached HTTP URL | Hard refresh (Ctrl+Shift+R) or clear cache |
| `WebSocket connection failed` | Missing Upgrade headers | Verify Nginx config has `proxy_set_header Upgrade` |
| Port 80/443 refused | Hetzner firewall | Add inbound rules in Hetzner Cloud Console |

---

## Files in This Directory

| File | Purpose |
|------|---------|
| `setup_postiz_ssl.sh` | Main setup script — runs on the VPS |
| `run_on_server.sh` | Wrapper — runs from your local machine |
| `social.shamrockbailbonds.biz.conf` | Final hardened Nginx config |
| `postiz_docker_compose_patch.yml` | docker-compose service block reference |
| `POSTIZ_SSL_SETUP_GUIDE.md` | This guide |
