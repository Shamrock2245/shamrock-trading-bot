#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# Shamrock Trading Bot — Postiz SSL Setup Script
# Configures Nginx reverse proxy + Let's Encrypt SSL for Postiz on port 5200
#
# Run on the Hetzner VPS as root:
#   bash setup_postiz_ssl.sh
#
# Prerequisites:
#   - DNS A record: social.shamrockbailbonds.biz → 5.161.126.32
#   - Port 80 and 443 open in Hetzner firewall
#   - Postiz container running on port 5200
# ═══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

DOMAIN="social.shamrockbailbonds.biz"
EMAIL="admin@shamrockbailbonds.biz"    # Change to your real email for cert expiry notices
POSTIZ_PORT="5200"
REPO_DIR="/root/shamrock-trading-bot"
COMPOSE_FILE="$REPO_DIR/docker-compose.yml"
NGINX_CONF="/etc/nginx/sites-available/${DOMAIN}.conf"
NGINX_ENABLED="/etc/nginx/sites-enabled/${DOMAIN}.conf"

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  🍀 SHAMROCK — Postiz SSL Setup                             ║"
echo "║  Domain: $DOMAIN                    ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# ── Step 1: Install Nginx and Certbot ─────────────────────────────────────────
echo "📦 Step 1/6 — Installing Nginx and Certbot..."
apt-get update -qq
apt-get install -y -qq nginx certbot python3-certbot-nginx
echo "   ✅ Nginx and Certbot installed"
echo ""

# ── Step 2: Write the initial HTTP-only Nginx config (for ACME challenge) ─────
echo "📝 Step 2/6 — Writing initial Nginx config (HTTP only)..."
cat > "$NGINX_CONF" << 'NGINX_HTTP_ONLY'
# Postiz reverse proxy — HTTP only (pre-SSL)
# Certbot will upgrade this to HTTPS automatically
server {
    listen 80;
    listen [::]:80;
    server_name social.shamrockbailbonds.biz;

    # Let's Encrypt ACME challenge
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    # Temporary proxy (will be replaced by HTTPS redirect after certbot)
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
NGINX_HTTP_ONLY

# Enable the site
ln -sf "$NGINX_CONF" "$NGINX_ENABLED"

# Remove default site if it exists and would conflict
rm -f /etc/nginx/sites-enabled/default

# Create certbot webroot directory
mkdir -p /var/www/certbot

# Test and reload Nginx
nginx -t
systemctl reload nginx
echo "   ✅ Nginx HTTP config active"
echo ""

# ── Step 3: Obtain SSL certificate via Certbot ────────────────────────────────
echo "🔐 Step 3/6 — Obtaining Let's Encrypt SSL certificate..."
echo "   Domain: $DOMAIN"
echo "   Email:  $EMAIL"
echo ""

certbot --nginx \
    --non-interactive \
    --agree-tos \
    --email "$EMAIL" \
    --domains "$DOMAIN" \
    --redirect \
    --hsts \
    --staple-ocsp

echo "   ✅ SSL certificate obtained and Nginx updated"
echo ""

# ── Step 4: Write the final hardened Nginx config ─────────────────────────────
echo "📝 Step 4/6 — Writing final hardened Nginx config with WebSocket support..."
cat > "$NGINX_CONF" << 'NGINX_FINAL'
# ─────────────────────────────────────────────────────────────────────────────
# Nginx reverse proxy — social.shamrockbailbonds.biz → Postiz (port 5200)
# Managed by Certbot for SSL termination
# ─────────────────────────────────────────────────────────────────────────────

# HTTP → HTTPS redirect
server {
    listen 80;
    listen [::]:80;
    server_name social.shamrockbailbonds.biz;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}

# HTTPS — main proxy block
server {
    listen 443 ssl;
    listen [::]:443 ssl;
    http2 on;
    server_name social.shamrockbailbonds.biz;

    # SSL certificates (managed by Certbot)
    ssl_certificate     /etc/letsencrypt/live/social.shamrockbailbonds.biz/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/social.shamrockbailbonds.biz/privkey.pem;
    include             /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam         /etc/letsencrypt/ssl-dhparams.pem;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options           "SAMEORIGIN"                          always;
    add_header X-Content-Type-Options    "nosniff"                             always;
    add_header Referrer-Policy           "strict-origin-when-cross-origin"     always;

    # Proxy to Postiz container on port 5200
    location / {
        proxy_pass         http://127.0.0.1:5200;
        proxy_http_version 1.1;

        # WebSocket support (Postiz uses Socket.IO / real-time features)
        proxy_set_header   Upgrade    $http_upgrade;
        proxy_set_header   Connection "upgrade";

        # Standard proxy headers
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;

        # Timeouts — generous for social media API calls
        proxy_connect_timeout  60s;
        proxy_send_timeout     120s;
        proxy_read_timeout     120s;

        # Buffer settings
        proxy_buffer_size          128k;
        proxy_buffers              4 256k;
        proxy_busy_buffers_size    256k;

        # Disable buffering for SSE / streaming responses
        proxy_buffering off;
    }

    # Static asset caching
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
        proxy_pass         http://127.0.0.1:5200;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Forwarded-Proto $scheme;
        expires            7d;
        add_header         Cache-Control "public, immutable";
    }
}
NGINX_FINAL

nginx -t
systemctl reload nginx
echo "   ✅ Final hardened Nginx config active"
echo ""

# ── Step 5: Update docker-compose.yml with HTTPS URLs ─────────────────────────
echo "🐳 Step 5/6 — Updating docker-compose.yml with HTTPS URLs..."

if [ ! -f "$COMPOSE_FILE" ]; then
    echo "   ⚠️  docker-compose.yml not found at $COMPOSE_FILE"
    echo "   Please update the Postiz service environment variables manually:"
    echo "     MAIN_URL: 'https://$DOMAIN'"
    echo "     FRONTEND_URL: 'https://$DOMAIN'"
    echo "     NEXT_PUBLIC_BACKEND_URL: 'https://$DOMAIN/api'"
else
    # Use sed to replace the URL values in the Postiz service block
    # These patterns match both quoted and unquoted YAML values
    sed -i \
        -e "s|MAIN_URL:.*http://.*|MAIN_URL: 'https://$DOMAIN'|g" \
        -e "s|MAIN_URL:.*https://.*localhost.*|MAIN_URL: 'https://$DOMAIN'|g" \
        -e "s|FRONTEND_URL:.*http://.*|FRONTEND_URL: 'https://$DOMAIN'|g" \
        -e "s|FRONTEND_URL:.*https://.*localhost.*|FRONTEND_URL: 'https://$DOMAIN'|g" \
        -e "s|NEXT_PUBLIC_BACKEND_URL:.*http://.*|NEXT_PUBLIC_BACKEND_URL: 'https://$DOMAIN/api'|g" \
        -e "s|NEXT_PUBLIC_BACKEND_URL:.*https://.*localhost.*|NEXT_PUBLIC_BACKEND_URL: 'https://$DOMAIN/api'|g" \
        "$COMPOSE_FILE"

    echo "   ✅ docker-compose.yml updated"
    echo ""
    echo "   Verifying changes:"
    grep -n "MAIN_URL\|FRONTEND_URL\|NEXT_PUBLIC_BACKEND_URL" "$COMPOSE_FILE" | head -10
fi
echo ""

# ── Step 6: Restart Postiz container ──────────────────────────────────────────
echo "🚀 Step 6/6 — Restarting Postiz container..."
cd "$REPO_DIR"

# Start with the social profile
docker compose --profile social up -d postiz

echo ""
echo "   Waiting 15 seconds for Postiz to initialize..."
sleep 15

echo ""
echo "   📊 Container status:"
docker compose --profile social ps postiz 2>/dev/null || docker ps --filter "name=postiz" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

echo ""
echo "   📜 Recent Postiz logs:"
docker logs postiz --tail=20 2>/dev/null || docker compose --profile social logs --tail=20 postiz

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  ✅ SETUP COMPLETE"
echo ""
echo "  🌐 Postiz is now accessible at:"
echo "     https://$DOMAIN"
echo ""
echo "  🔐 SSL certificate auto-renews via Certbot cron"
echo "     (verify: certbot renew --dry-run)"
echo ""
echo "  🐛 crypto.randomUUID error should be resolved"
echo "     (HTTPS = Secure Context = Web Crypto API enabled)"
echo "═══════════════════════════════════════════════════════════════"
