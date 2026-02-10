# ngrok Deployment for QCC Bus

**Alternative Method** - ngrok provides quick HTTPS tunnels for development and testing.

## Prerequisites

- ngrok account (free tier available)
- `ngrok` installed on your machine
- Python 3.8+ for MCP Bus server

## Installation

### Install ngrok

**Windows:**
```powershell
# Download from https://ngrok.com/download
# Or using chocolatey
choco install ngrok
```

**Linux/Mac:**
```bash
# Download and install
curl -s https://ngrok-agent.s3.amazonaws.com/ngrok.asc | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null
curl -s https://ngrok-agent.s3.amazonaws.com/ngrok.asc | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null

# Or using Homebrew
brew install ngrok/ngrok
```

### Authenticate with ngrok

```bash
ngrok config add-authtoken <your-ngrok-authtoken>
```

Get your authtoken from: https://dashboard.ngrok.com/get-started/your-authtoken

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

### 3. Start ngrok Tunnel

```bash
# Start tunnel for port 8000
ngrok http 8000
```

**Expected Output:**
```
ngrok by @inconshreveable

Session Status                online
Account                       your-account (plan: Free)
Version                       3.x.x
Region                        us (United States)
Forwarding                    https://abc123.ngrok-free.app -> http://localhost:18788/
Web Interface                 http://127.0.0.1:4040
Connections                   ttl     opn     rt1     rt5     p50p     p50
0                             0       0       0.00    0.00    0.00
```

**Important:** Note the `Forwarding` URL, e.g., `https://abc123.ngrok-free.app`

### 4. Get Public URL

The ngrok output shows your public HTTPS URL:
- **Forwarding URL:** `https://<random-id>.ngrok-free.app`
- **Web Interface:** `http://127.0.0.1:4040` (for monitoring)

## Health Check

Verify the tunnel is working:

```bash
# Check health endpoint
curl https://abc123.ngrok-free.app/health

# Expected response:
# {"ok": true, "ts": "2024-01-15T10:30:00.000000Z"}

# Check MCP tools list
curl -X POST https://abc123.ngrok-free.app/mcp \
  -H "Authorization: Bearer your-secure-token-here" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "method": "tools/list"}'
```

## Advanced Configuration

### Custom Domain (Paid Plans)

With ngrok paid plans, you can use custom domains:

```bash
ngrok http 8000 --domain=your-custom-domain.com
```

### Reserved Domain (Free Tier)

Reserve a subdomain for consistent URLs:

```bash
# Reserve a domain
ngrok api reserved-domains create qcc-bus

# Use reserved domain
ngrok http 8000 --domain=qcc-bus
```

### Configuration File

Create `ngrok.yml` for persistent configuration:

```yaml
version: "2"
authtoken: your-authtoken

tunnels:
  qcc-bus:
    addr: 8000
    proto: http
    bind_tls: true
    inspect: false
    web_addr: 127.0.0.1:4040
```

Start with:
```bash
ngrok start --all
```

## Troubleshooting

### Tunnel Not Starting
- Verify ngrok is authenticated: `ngrok config check`
- Check port 8000 is not in use
- Ensure MCP Bus server is running on 127.0.0.1:8000

### 404 Errors
- Check ngrok is forwarding to correct port (8000)
- Verify MCP Bus server is running
- Check ngrok web interface for errors

### Connection Refused
- Ensure MCP Bus server is started
- Check firewall allows localhost connections
- Verify correct port (8000)

### Session Expired
- Free ngrok sessions expire after 8 hours
- Restart ngrok to get new URL
- Consider reserved domain for consistent URL

## Production Considerations

### Limitations of Free Tier
- Random URL changes on each restart
- 8-hour session limit
- Bandwidth and connection limits
- No custom domains

### When to Use Paid Plan
- Need consistent URL (reserved domain)
- Longer sessions
- Custom domains
- Higher bandwidth limits
- Advanced features (IP restrictions, etc.)

### Security Notes
- ngrok provides automatic HTTPS
- No need to configure SSL certificates
- Authtoken should be kept secret
- Use strong Bearer token for MCP Bus authentication
- Monitor ngrok web interface for connections

## Comparison: Cloudflare Tunnel vs ngrok

| Feature | Cloudflare Tunnel | ngrok |
|----------|-------------------|--------|
| Free Tier | Yes (unlimited) | Yes (limited) |
| Custom Domain | Yes | Paid only |
| Session Limit | No | 8 hours (free) |
| URL Consistency | Yes | No (free) |
| Setup Complexity | Medium | Low |
| Performance | Better | Good |

**Recommendation:** Use Cloudflare Tunnel for production, ngrok for quick testing.

## References

- [ngrok Documentation](https://ngrok.com/docs)
- [ngrok Dashboard](https://dashboard.ngrok.com/)
- [ngrok Agent Download](https://ngrok.com/download)
