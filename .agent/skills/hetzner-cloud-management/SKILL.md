---
name: hetzner-cloud-management
description: Manage Hetzner Cloud infrastructure for the Shamrock Trading Bot. Use when deploying, scaling, backing up, or troubleshooting the EU server (CX33, Helsinki, 46.62.231.43). Covers API automation, firewall management, snapshot creation, and disaster recovery.
---

# Hetzner Cloud Management Skill

## Quick Reference

| Item | Value |
|------|-------|
| **Server** | shamrock-eu (ID: 142997655) |
| **IP** | 46.62.231.43 |
| **Type** | CX33 (4 vCPU, 8GB RAM, 80GB NVMe) |
| **Location** | Helsinki (hel1-dc2) |
| **Cost** | €8.99/mo + €1.80/mo backups |
| **Firewall** | ID 11161658 |
| **API Token env** | `HCLOUD_TOKEN` |

## SSH Access
```bash
KEY=/Users/brendan/Desktop/shamrock-trading-bot/.shamrock_deploy_key
ssh -i $KEY -o StrictHostKeyChecking=no root@46.62.231.43
```

## API Usage
```bash
# Auth header for all API calls
-H "Authorization: Bearer $HCLOUD_TOKEN"
# Base URL
https://api.hetzner.cloud/v1/
```

## Critical Rules
1. **NEVER add outbound firewall rules** — one rule switches default to deny-all outbound
2. **Always snapshot before major deploys** — automated backups only keep 7 days
3. **Rate limit: 3,600 requests/hour** per project
4. **Powered-off servers still bill** — only DELETE stops charges
5. **`docker compose restart` does NOT reload `.env` changes** — use `down` + `up --build`

## Common Operations

### Take Pre-Deploy Snapshot
```bash
curl -X POST \
  -H "Authorization: Bearer $HCLOUD_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"description": "pre-deploy-$(date +%Y%m%d)", "type": "snapshot"}' \
  https://api.hetzner.cloud/v1/servers/142997655/actions/create_image
```

### Check Server Status
```bash
curl -s -H "Authorization: Bearer $HCLOUD_TOKEN" \
  https://api.hetzner.cloud/v1/servers/142997655 | python3 -c "
import json, sys; s=json.load(sys.stdin)['server']
print(f'{s[\"name\"]}: {s[\"status\"]} | {s[\"server_type\"][\"name\"]} | {s[\"public_net\"][\"ipv4\"][\"ip\"]}')"
```

### Emergency: Reboot Server
```bash
curl -X POST -H "Authorization: Bearer $HCLOUD_TOKEN" \
  https://api.hetzner.cloud/v1/servers/142997655/actions/reboot
```

### Emergency: Rebuild from Snapshot
```bash
curl -X POST \
  -H "Authorization: Bearer $HCLOUD_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"image": SNAPSHOT_ID}' \
  https://api.hetzner.cloud/v1/servers/142997655/actions/rebuild
```

## Firewall Management
```bash
# Add rule
curl -X POST \
  -H "Authorization: Bearer $HCLOUD_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"rules": [{"direction":"in","protocol":"tcp","port":"NEW_PORT","source_ips":["0.0.0.0/0","::/0"]}]}' \
  https://api.hetzner.cloud/v1/firewalls/11161658/actions/set_rules
```

## Full Reference
See artifact: `hetzner_infrastructure_reference.md`
