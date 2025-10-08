# Cloudflare Tunnel Setup for Search API

## Overview

This guide shows how to expose your local Search API to OpenAI GPT Actions using Cloudflare Tunnel.

**Architecture:**
```
OpenAI GPT Agent → Cloudflare Tunnel (public HTTPS) → Your Local Server (port 8001)
```

---

## Prerequisites

- Cloudflare account (free tier works)
- Domain managed by Cloudflare (or use trycloudflare.com subdomain)
- `cloudflared` CLI installed

---

## Step 1: Install Cloudflare Tunnel

### Windows
```powershell
# Download cloudflared
Invoke-WebRequest -Uri "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe" -OutFile "cloudflared.exe"

# Move to PATH
Move-Item cloudflared.exe C:\Windows\System32\cloudflared.exe
```

### Linux/Mac
```bash
# Download and install
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o cloudflared
chmod +x cloudflared
sudo mv cloudflared /usr/local/bin/
```

---

## Step 2: Authenticate with Cloudflare

```bash
cloudflared tunnel login
```

This will open a browser window to authenticate with your Cloudflare account.

---

## Step 3: Create a Tunnel

```bash
# Create tunnel named "search-api"
cloudflared tunnel create search-api

# Output:
# Tunnel credentials written to: ~/.cloudflared/<TUNNEL_ID>.json
# Created tunnel search-api with id <TUNNEL_ID>
```

**Save the Tunnel ID** — you'll need it later.

---

## Step 4: Configure Tunnel

Create config file `~/.cloudflared/config.yml`:

```yaml
tunnel: <TUNNEL_ID>
credentials-file: /Users/YOUR_USER/.cloudflared/<TUNNEL_ID>.json

ingress:
  # Route for Search API
  - hostname: search-api.yourdomain.com
    service: http://localhost:8001
    originRequest:
      noTLSVerify: true

  # Catch-all rule (required)
  - service: http_status:404
```

**Replace:**
- `<TUNNEL_ID>` with your actual tunnel ID
- `search-api.yourdomain.com` with your desired hostname
- `/Users/YOUR_USER/` with your actual path

---

## Step 5: Create DNS Record

### Option A: Using Your Domain

```bash
cloudflared tunnel route dns search-api search-api.yourdomain.com
```

This creates a CNAME record pointing to your tunnel.

### Option B: Using trycloudflare.com (Quick Test)

Skip DNS setup and use temporary URL:

```bash
cloudflared tunnel --url http://localhost:8001
```

You'll get a URL like: `https://random-name.trycloudflare.com`

**Note:** This URL changes on every restart. For production, use Option A.

---

## Step 6: Start the Tunnel

### Production (Named Tunnel)
```bash
cloudflared tunnel run search-api
```

### Quick Test (Temporary URL)
```bash
cloudflared tunnel --url http://localhost:8001
```

---

## Step 7: Test the Endpoint

```bash
# Test health endpoint
curl https://search-api.yourdomain.com/health

# Expected response:
{
  "status": "healthy",
  "database": "connected",
  "timestamp": "2025-10-06T12:00:00Z"
}
```

```bash
# Test search endpoint
curl -X POST https://search-api.yourdomain.com/retrieve \
  -H "Content-Type: application/json" \
  -d '{
    "query": "AI regulation",
    "hours": 24,
    "k": 5,
    "filters": {},
    "cursor": null,
    "correlation_id": "test-123"
  }'

# Expected response:
{
  "items": [...],
  "next_cursor": null,
  "coverage": 0.85,
  "freshness_stats": {"median_sec": 86400}
}
```

---

## Step 8: (Optional) Add Cloudflare Access Protection

Protect your API with Cloudflare Access to allow only OpenAI IPs.

### 8.1 Create Service Token

1. Go to **Cloudflare Zero Trust** → **Access** → **Service Auth**
2. Click **Create Service Token**
3. Name: `OpenAI GPT Actions`
4. Copy **Client ID** and **Client Secret**

### 8.2 Create Access Policy

1. Go to **Access** → **Applications**
2. Click **Add an application** → **Self-hosted**
3. Application name: `Search API`
4. Subdomain: `search-api`
5. Domain: `yourdomain.com`

**Policy:**
- Name: `Allow Service Token`
- Action: `Allow`
- Rule type: `Service Auth`
- Service Token: Select the token you created

### 8.3 Update OpenAPI Spec

In `search_openapi.yaml`, the headers are already configured:

```yaml
security:
  - CloudflareServiceToken: []

components:
  securitySchemes:
    CloudflareServiceToken:
      type: apiKey
      in: header
      name: CF-Access-Client-Id
      x-additional-header:
        name: CF-Access-Client-Secret
```

### 8.4 Test with Authentication

```bash
curl -X POST https://search-api.yourdomain.com/retrieve \
  -H "CF-Access-Client-Id: YOUR_CLIENT_ID" \
  -H "CF-Access-Client-Secret: YOUR_CLIENT_SECRET" \
  -H "Content-Type: application/json" \
  -d '{...}'
```

---

## Step 9: Configure OpenAI GPT Actions

### 9.1 Create GPT

1. Go to https://platform.openai.com/
2. Navigate to **Assistants** (or use ChatGPT GPT builder)
3. Create new Assistant/GPT

### 9.2 Add Action

1. Click **Add Action**
2. **Authentication:** API Key (if using Cloudflare Access) or None
3. **Schema:** Paste contents of `search_openapi.yaml`
4. **Replace** `YOUR_HOSTNAME.trycloudflare.com` with your actual hostname

### 9.3 Configure API Key (if using Cloudflare Access)

**Auth Type:** Custom Header

**Headers:**
```
CF-Access-Client-Id: YOUR_CLIENT_ID
CF-Access-Client-Secret: YOUR_CLIENT_SECRET
```

### 9.4 Add System Prompt

Paste the SearchAgent system prompt (see `SEARCH_SYSTEM_PROMPT.md`)

---

## Running in Production

### Option 1: Run as Background Process

```bash
# Linux/Mac
nohup cloudflared tunnel run search-api > tunnel.log 2>&1 &

# Windows (PowerShell)
Start-Process cloudflared -ArgumentList "tunnel","run","search-api" -WindowStyle Hidden
```

### Option 2: Run as System Service

Create systemd service (Linux):

```bash
sudo nano /etc/systemd/system/cloudflared-search-api.service
```

```ini
[Unit]
Description=Cloudflare Tunnel for Search API
After=network.target

[Service]
Type=simple
User=youruser
ExecStart=/usr/local/bin/cloudflared tunnel run search-api
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable cloudflared-search-api
sudo systemctl start cloudflared-search-api
sudo systemctl status cloudflared-search-api
```

---

## Monitoring

### View Tunnel Status

```bash
# List all tunnels
cloudflared tunnel list

# Check tunnel info
cloudflared tunnel info search-api
```

### View Logs

```bash
# If running as service
sudo journalctl -u cloudflared-search-api -f

# If running in background
tail -f tunnel.log
```

### Cloudflare Dashboard

Go to **Cloudflare Zero Trust** → **Access** → **Tunnels** to view:
- Active connections
- Request metrics
- Traffic analytics

---

## Troubleshooting

### Tunnel Not Connecting

```bash
# Check tunnel status
cloudflared tunnel info search-api

# Test local service first
curl http://localhost:8001/health

# Check credentials file exists
ls ~/.cloudflared/<TUNNEL_ID>.json
```

### 502 Bad Gateway

**Causes:**
- Local service (port 8001) not running
- Firewall blocking localhost connections
- Wrong port in config.yml

**Solution:**
```bash
# Check if service is running
netstat -an | grep 8001

# Start Search API
cd d:\Программы\rss\rssnews
python api/search_api.py
```

### 403 Forbidden (with Cloudflare Access)

**Causes:**
- Wrong Client ID/Secret
- Service Token not in Access Policy

**Solution:**
- Verify headers: `CF-Access-Client-Id` and `CF-Access-Client-Secret`
- Check Access Policy includes Service Token

### DNS Not Resolving

```bash
# Check DNS record
nslookup search-api.yourdomain.com

# If using Cloudflare DNS, ensure CNAME exists:
# search-api.yourdomain.com -> <TUNNEL_ID>.cfargotunnel.com
```

---

## Security Best Practices

### 1. Use Service Tokens
Always use Cloudflare Access Service Tokens in production to restrict access.

### 2. Rate Limiting
Add rate limiting in Cloudflare dashboard:
- **Security** → **WAF** → **Rate Limiting Rules**
- Rule: 60 requests per minute per IP

### 3. IP Allowlist (Optional)
Restrict to OpenAI IP ranges:
- **Security** → **WAF** → **Custom Rules**
- Action: Block if IP not in [OpenAI IP ranges]

### 4. Rotate Tokens
Rotate Service Tokens every 90 days.

### 5. Monitor Logs
Enable logging in Cloudflare Access to track all requests.

---

## Complete Startup Script

Create `start_search_api.sh`:

```bash
#!/bin/bash

# Start Search API
cd /path/to/rssnews
source venv/bin/activate
python api/search_api.py &

# Wait for API to start
sleep 3

# Start Cloudflare Tunnel
cloudflared tunnel run search-api &

echo "Search API and Tunnel started"
echo "Access at: https://search-api.yourdomain.com"
```

Make executable:
```bash
chmod +x start_search_api.sh
./start_search_api.sh
```

---

## Summary

**Setup Checklist:**
- [x] Install `cloudflared`
- [x] Authenticate with Cloudflare
- [x] Create tunnel
- [x] Configure `config.yml`
- [x] Create DNS record
- [x] Start tunnel
- [x] Test endpoint
- [x] (Optional) Add Cloudflare Access
- [x] Configure OpenAI GPT Actions
- [x] Add system prompt

**Your URLs:**
- Production: `https://search-api.yourdomain.com`
- Quick test: `https://random-name.trycloudflare.com`

**Next Step:** Configure SearchAgent in OpenAI (see `SEARCH_GPT_AGENT_SETUP.md`)
