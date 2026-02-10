# Cloudflare Tunnel Deployment for QCC Bus

**Recommended Method** - Cloudflare Tunnel provides free HTTPS tunnels with custom domains.

## Prerequisites

- Cloudflare account (free tier is sufficient)
- `cloudflared` installed on your machine
- Python 3.8+ for MCP Bus server

## Installation

### Install cloudflared

**Windows:**
```powershell
# Download from GitHub releases
# https://github.com/cloudflare/cloudflared/releases/latest

# Or using winget
winget install --id Cloudflare.cloudflared -e
```

**Linux/Mac:**
```bash
# Download and install
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o cloudflared
chmod +x cloudflared
sudo mv cloudflared /usr/local/bin/
```

### Authenticate with Cloudflare

```bash
cloudflared tunnel login
```

This will open a browser for authentication.

## Deployment Steps

### 1. Configure MCP Bus to Bind to Localhost

Edit your MCP Bus configuration to bind to `127.0.0.1` instead of `0.0.0.0`:

**Option A: Environment Variables**
```bash
export MCP_BUS_HOST=127.0.0.1
export MCP_BUS_PORT=8000
export MCP_BUS_TOKEN=your-secure-token-here
export REPO_ROOT=/path/to/quantsys
```

**Option B: .env File (Local Only)**
```bash
cd tools/mcp_bus
cp .env.example .env
# Edit .env with:
# MCP_BUS_HOST=127.0.0.1
# MCP_BUS_TOKEN=your-secure-token-here
```

### 2. Start MCP Bus Server

```bash
cd tools/mcp_bus
uvicorn server.main:app --host 127.0.0.1 --port 8000
```

**Expected Output:**
```
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:18788/ (Press CTRL+C to quit)
```

### 3. Create Cloudflare Tunnel

```bash
# Create a new tunnel
cloudflared tunnel create qcc-bus

# Configure the tunnel
cat <<EOF > config.yml
tunnel: <tunnel-id-from-above>
credentials-file: /path/to/credentials.json

ingress:
  - hostname: qcc-bus.your-domain.com  # Optional: custom domain
    service: http://127.0.0.1:18788/
  - service: http_status:404
EOF

# Start the tunnel
cloudflared tunnel --config config.yml run
```

### 4. Get Public URL

After starting the tunnel, cloudflared will display your public URL:

```
2024-01-15T10:30:00Z INF Your quick Tunnel has been created and is available at: https://qcc-bus.trycloudflare.com
```

**Note:** The URL will be `https://<random-id>.trycloudflare.com` unless you configure a custom domain.

## Health Check

Verify the tunnel is working:

```bash
# Check health endpoint
curl https://qcc-bus.trycloudflare.com/health

# Expected response:
# {"ok": true, "ts": "2024-01-15T10:30:00.000000Z"}

# Check MCP tools list
curl -X POST https://qcc-bus.trycloudflare.com/mcp \
  -H "Authorization: Bearer your-secure-token-here" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "method": "tools/list"}'
```

## Troubleshooting

### Tunnel Not Starting
- Verify cloudflared is authenticated: `cloudflared tunnel list`
- Check port 8000 is not in use
- Ensure MCP Bus server is running on 127.0.0.1:8000

### 404 Errors
- Check tunnel configuration matches local port (8000)
- Verify MCP Bus server is running
- Check cloudflared logs for errors

### Connection Refused
- Ensure MCP Bus server is started
- Check firewall allows localhost connections
- Verify correct port (8000)

## Production Considerations

### Custom Domain
For production use, configure a custom domain:

1. Add CNAME record in Cloudflare DNS
2. Update tunnel configuration with your domain
3. Enable SSL (automatic with Cloudflare)

### Persistent Tunnel
Create a systemd service for auto-start:

```bash
sudo nano /etc/systemd/systemd/cloudflared-qcc-bus.service
```

```ini
[Unit]
Description=Cloudflare Tunnel for QCC Bus
After=network.target

[Service]
Type=simple
User=your-user
ExecStart=/usr/local/bin/cloudflared tunnel --config /path/to/config.yml run
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable cloudflared-qcc-bus
sudo systemctl start cloudflared-qcc-bus
```

## Security Notes

- Cloudflare Tunnel provides automatic HTTPS
- No need to configure SSL certificates
- Tunnel ID should be kept secret
- Use strong Bearer token for MCP Bus authentication
- Monitor tunnel logs for suspicious activity

## References

- [Cloudflare Tunnel Documentation](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/)
- [cloudflared GitHub](https://github.com/cloudflare/cloudflared)
