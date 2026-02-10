# Caddy HTTPS Setup for QCC Bus MCP Server

**Domain:** mcp.timquant.tech  
**EC2 IP:** 13.229.100.10  
**MCP Bus Port:** 18080 (internal)  
**Caddy Port:** 443 (external HTTPS)

## Architecture

```
Internet → Caddy (443/HTTPS) → MCP Bus (127.0.0.1:18080/HTTP)
```

**Key Benefits:**
- Automatic HTTPS with Let's Encrypt
- No manual certificate management
- Simple configuration
- Automatic certificate renewal
- Reverse proxy to internal service

## Prerequisites

- DNS A record: `mcp.timquant.tech → 13.229.100.10` (already configured)
- EC2 instance: 13.229.100.10 (already running)
- Domain: timquant.tech (already owned)
- SSH access to EC2

## AWS Security Group Configuration

### Required Inbound Rules

**Rule 1: HTTP (for ACME)**
- **Type:** Custom TCP
- **Port:** 80
- **Source:** 0.0.0.0/0 (anywhere, required for Let's Encrypt)
- **Description:** Allow Let's Encrypt ACME challenges

**Rule 2: HTTPS (for external access)**
- **Type:** Custom TCP
- **Port:** 443
- **Source:** Your public IP (or restrict to specific IPs)
- **Description:** Allow HTTPS access to Caddy

**Note:** Do NOT open port 18080 to the internet. Only Caddy (443) should be accessible externally.

### Security Group Setup Steps

1. **AWS Console → EC2 → Security Groups**
2. **Select your instance's security group**
3. **Inbound Rules → Edit → Add Rule**
4. **Add Rule 1:**
   - Type: Custom TCP
   - Port: 80
   - Source: 0.0.0.0/0
   - Description: "Let's Encrypt ACME"
5. **Add Rule 2:**
   - Type: Custom TCP
   - Port: 443
   - Source: Your public IP (or 0.0.0.0/0 for testing)
   - Description: "HTTPS to Caddy"

## Caddy Installation

### On Ubuntu/Debian

```bash
# Update package list
sudo apt update

# Install Caddy
sudo apt install -y caddy

# Verify installation
caddy version

# Expected output:
# v2.x.x h1
```

### Systemd Service

Caddy is automatically installed as a systemd service.

**Check status:**
```bash
sudo systemctl status caddy
```

**Enable auto-start:**
```bash
sudo systemctl enable caddy
```

## Caddy Configuration

### Caddyfile Location

```
/etc/caddy/Caddyfile
```

### Minimal Configuration

```caddy
mcp.timquant.tech {
    # Reverse proxy to MCP Bus
    reverse_proxy 127.0.0.1:18080 {
        # Preserve original host header
        header_up Host {host}
        
        # Add real IP header for debugging
        header_up X-Real-IP {remote_host}
        
        # Health check endpoint
        health_uri /health
        
        # Timeouts
        transport http {
            read_timeout 30s
            write_timeout 30s
        }
    }
    
    # Logging
    log {
        output file /var/log/caddy/access.log
        format json
    }
}
```

### Full Configuration (with ACME)

```caddy
mcp.timquant.tech {
    # Automatic HTTPS with Let's Encrypt
    tls {
        # Email for certificate expiration notices
        email admin@timquant.tech
        
        # ACME challenge type
        dns cloudflare
        
        # Or use HTTP challenge (requires port 80 open)
        # dns cloudflare
    }
    
    # Reverse proxy to MCP Bus
    reverse_proxy 127.0.0.1:18080 {
        # Preserve original host header
        header_up Host {host}
        
        # Add real IP header for debugging
        header_up X-Real-IP {remote_host}
        
        # Health check endpoint
        health_uri /health
        
        # Timeouts
        transport http {
            read_timeout 30s
            write_timeout 30s
        }
    }
    
    # Logging
    log {
        output file /var/log/caddy/access.log
        format json
    }
}
```

## Deployment Steps

### Step 1: Update MCP Bus Binding

**Important:** If MCP Bus is currently bound to `0.0.0.0:18080`, it MUST be changed to `127.0.0.1:18080` so only Caddy exposes to the internet.

**Option A: Edit systemd service file**
```bash
ssh ubuntu@13.229.100.10

# Edit service file
sudo nano /etc/systemd/system/qcc-bus.service

# Change this line:
# ExecStart=/usr/bin/python3 -m uvicorn server.main:app --host 0.0.0.0 --port 18080
# To this:
# ExecStart=/usr/bin/python3 -m uvicorn server.main:app --host 127.0.0.1 --port 18080

# Save and restart
sudo systemctl daemon-reload
sudo systemctl restart qcc-bus
```

**Option B: Update deployment script**
Modify `tools/mcp_bus/deploy/ec2_deploy.sh` to use `127.0.0.1` instead of `0.0.0.0`.

### Step 2: Create Caddyfile

```bash
ssh ubuntu@13.229.100.10

# Create Caddyfile
sudo nano /etc/caddy/Caddyfile

# Paste the configuration from above
# Save with Ctrl+O, Exit with Ctrl+X
```

### Step 3: Test Caddy Configuration

```bash
# Validate configuration
sudo caddy validate --config /etc/caddy/Caddyfile

# Expected output:
# OK (configuration is valid)
```

### Step 4: Restart Caddy

```bash
# Reload Caddy configuration
sudo systemctl reload caddy

# Or restart
sudo systemctl restart caddy

# Check status
sudo systemctl status caddy
```

### Step 5: Verify HTTPS

```bash
# Test health endpoint
curl https://mcp.timquant.tech/health

# Expected response:
# {
#   "ok": true,
#   "ts": "...",
#   "status": "healthy",
#   "version": "0.1.0"
# }

# Check certificate
curl -Iv https://mcp.timquant.tech

# Expected output includes:
# * TLSv1.3 (TLS 1.3)
# * Server certificate
# * subject: CN=mcp.timquant.tech
# * issuer: C=US, O=Let's Encrypt...
```

## Certificate Management

### Automatic Renewal

Caddy automatically renews Let's Encrypt certificates before expiration.

**Check certificate status:**
```bash
sudo caddy list-certificates
```

**Manual renewal (if needed):**
```bash
sudo caddy renew --force
```

### Certificate Storage

Certificates are stored in:
```
/var/lib/caddy/.local/share/caddy/certificates/
```

## Troubleshooting

### Caddy Not Starting

**Check:**
```bash
sudo systemctl status caddy
sudo journalctl -u caddy -n 50
```

**Common Issues:**
- Port 443 already in use
- Configuration syntax error
- Permission denied on Caddyfile

### Certificate Issues

**Check:**
```bash
# View certificate details
sudo caddy list-certificates

# Check ACME logs
sudo journalctl -u caddy -f | grep ACME
```

**Common Issues:**
- DNS not propagated
- Port 80 blocked (ACME challenge fails)
- Rate limiting from Let's Encrypt

### Proxy Issues

**Check:**
```bash
# Test direct access to MCP Bus
curl http://127.0.0.1:18080/health

# Test through Caddy
curl https://mcp.timquant.tech/health

# Both should return same result
```

**Common Issues:**
- MCP Bus not binding to 127.0.0.1
- MCP Bus service not running
- Firewall blocking internal traffic

## Security Notes

### Network Security

1. **External Access:** Only port 443 (Caddy) is exposed
2. **Internal Access:** MCP Bus (127.0.0.1:18080) is not accessible externally
3. **DNSSEC:** Enable DNSSEC if supported
4. **Rate Limiting:** Consider adding rate limiting to Caddy

### Certificate Security

1. **Automatic Renewal:** Caddy handles this automatically
2. **Email Alerts:** Set email in Caddyfile for expiration notices
3. **Strong Ciphers:** Caddy uses modern, secure defaults

### Application Security

1. **Token Authentication:** MCP Bus still requires Bearer token
2. **Fail-Closed:** Unauthorized requests are rejected
3. **Audit Logging:** All calls are logged

## Monitoring

### Caddy Logs

```bash
# View access logs
sudo journalctl -u caddy -f

# View log file
sudo tail -f /var/log/caddy/access.log
```

### MCP Bus Logs

```bash
# View MCP Bus logs
sudo journalctl -u qcc-bus -f

# View audit logs
sudo tail -f /home/ubuntu/qcc-bus/docs/LOG/mcp_bus/$(date +%Y-%m-%d).log
```

## Performance Tuning

### Caddy Performance

```caddy
mcp.timquant.tech {
    reverse_proxy 127.0.0.1:18080 {
        # Enable HTTP/2 and HTTP/3
        transport http {
            versions h2c 2
        }
        
        # Connection pooling
        transport http {
            dial_timeout 10s
            response_header_timeout 10s
        }
        
        # Buffer sizes
        transport http {
            max_response_header_size 8192
        }
    }
}
```

## References

- [Caddy Documentation](https://caddyserver.com/docs/)
- [Caddy Quick Start](https://caddyserver.com/docs/quick-starts)
- [Let's Encrypt](https://letsencrypt.org/)
- [ACME Protocol](https://tools.ietf.org/html/rfc8555)
