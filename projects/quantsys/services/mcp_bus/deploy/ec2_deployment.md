# AWS EC2 Deployment for QCC Bus

**Target Instance:** 13.229.100.10  
**Port:** 18080  
**Protocol:** HTTP (HTTPS requires domain + Caddy)

## Prerequisites

- AWS EC2 instance running Ubuntu
- SSH access to EC2
- Python 3.8+ installed
- git installed

## Quick Deployment Steps

### 1. SSH to EC2

```bash
ssh ubuntu@13.229.100.10
```

### 2. Clone Repository or Upload tools/mcp_bus

**Option A: Clone Repository (Recommended)**
```bash
cd /home/ubuntu
git clone https://your-repo-url.git qcc-bus
cd qcc-bus
```

**Option B: Upload Only tools/mcp_bus (Faster)**
```bash
cd /home/ubuntu
mkdir -p qcc-bus
cd qcc-bus
mkdir -p tools/mcp_bus
# Upload tools/mcp_bus directory contents via scp
```

### 3. Run Deployment Script

```bash
chmod +x tools/mcp_bus/deploy/ec2_deploy.sh
./tools/mcp_bus/deploy/ec2_deploy.sh
```

**This script will:**
- Generate secure token (32 characters)
- Install Python dependencies
- Create systemd service
- Start MCP Bus server on port 18080

### 4. Update AWS Security Group

**Allow Inbound Traffic:**
- Source: Your public IP (or 0.0.0.0/0 for testing)
- Protocol: TCP
- Port: 18080

**AWS Console:**
1. EC2 → Security Groups
2. Select your instance's security group
3. Inbound Rules → Edit
4. Add Rule: Custom TCP, Port 18080, Source: Your IP

### 5. Verify Deployment

```bash
# Health check
curl http://13.229.100.10:18080/health

# Expected response:
# {"ok": true, "ts": "...", "status": "healthy", "version": "0.1.0"}

# Tools list
curl -X POST http://13.229.100.10:18080/mcp \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "method": "tools/list"}'
```

## Service Management

```bash
# Check status
sudo systemctl status qcc-bus

# View logs
sudo journalctl -u qcc-bus -f

# Restart service
sudo systemctl restart qcc-bus

# Stop service
sudo systemctl stop qcc-bus

# Rotate token
sudo nano /etc/systemd/system/qcc-bus.service
# Update MCP_BUS_TOKEN value
sudo systemctl daemon-reload
sudo systemctl restart qcc-bus
```

## Security Notes

**Current Setup:**
- HTTP only (port 18080)
- Token-based authentication
- Security Group restricts source IP

**Risks:**
- Traffic is unencrypted (HTTP)
- Token in systemd service file (accessible to root)

**Recommendations:**
1. **HTTPS Setup (Recommended):**
   - Get a domain (e.g., qcc-bus.yourdomain.com)
   - Point domain to EC2 IP: 13.229.100.10
   - Install Caddy: `sudo apt install caddy`
   - Configure Caddy reverse proxy to HTTPS
   - Use Let's Encrypt for SSL certificates

2. **Token Management:**
   - Use AWS Secrets Manager for production
   - Rotate tokens every 30 days
   - Monitor audit logs for suspicious activity

3. **Network Security:**
   - Use VPN or bastion host for SSH
   - Restrict Security Group to specific IPs
   - Enable AWS WAF if needed

## Troubleshooting

### Service Not Starting

```bash
# Check if port is in use
sudo netstat -tulpn | grep 18080

# Check service logs
sudo journalctl -u qcc-bus -n 50
```

### Connection Refused

```bash
# Verify service is running
sudo systemctl status qcc-bus

# Check Security Group allows port 18080
# AWS Console → EC2 → Security Groups → Inbound Rules
```

### Health Check Failing

```bash
# Check if server is listening
curl -v http://127.0.0.1:18080/health

# Check Python dependencies
cd /home/ubuntu/qcc-bus/tools/mcp_bus
pip3 list
```

## Client Configuration

### TRAE Configuration

Update `.trae/mcp.json`:
```json
{
  "mcpServers": {
    "qcc-bus": {
      "transport": {
        "type": "http",
        "url": "http://13.229.100.10:18080/mcp"
      },
      "auth": {
        "type": "bearer",
        "token": "YOUR_TOKEN_HERE"
      },
      "description": "QCC Bus - EC2 Deployment",
      "enabled": true
    }
  }
}
```

### ChatGPT Connector

**Note:** ChatGPT requires HTTPS. HTTP will be rejected.

**If HTTPS Available:**
- Settings → Connectors → Add MCP Server
- Server URL: `https://qcc-bus.yourdomain.com/mcp`
- Authentication: Bearer Token
- Token: `YOUR_TOKEN_HERE`

**If HTTP Only (Current Setup):**
- ChatGPT Connector will not work
- Must set up HTTPS first (see Security Notes above)

## References

- [AWS EC2 Documentation](https://docs.aws.amazon.com/ec2/)
- [Systemd Service Documentation](https://www.freedesktop.org/software/systemd/man/systemd.service.html)
- [Caddy Server](https://caddyserver.com/)
