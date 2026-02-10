#!/bin/bash

# QCC Bus MCP Server - Caddy HTTPS Setup Script
# Target: EC2 Instance (13.229.100.10)
# Domain: mcp.timquant.tech

set -e

echo "========================================="
echo " QCC Bus MCP Server - Caddy HTTPS Setup"
echo "========================================="
echo ""

# Configuration
DOMAIN="mcp.timquant.tech"
EC2_IP="13.229.100.10"
MCP_PORT="18080"
CADDY_PORT="443"
REPO_ROOT="/home/ubuntu/qcc-bus"
MCP_DIR="$REPO_ROOT/tools/mcp_bus"

# Step 1: Update MCP Bus binding to localhost only
echo "[1/6] Updating MCP Bus to bind to 127.0.0.1:$MCP_PORT..."
echo "This ensures only Caddy exposes to internet (port $CADDY_PORT)"
echo ""

# Update systemd service file
sudo tee /etc/systemd/system/qcc-bus.service > /dev/null <<EOF
[Unit]
Description=QCC Bus MCP Server
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=$MCP_DIR
Environment="MCP_BUS_TOKEN=$TOKEN"
Environment="REPO_ROOT=$REPO_ROOT"
ExecStart=/usr/bin/python3 -m uvicorn server.main:app --host 127.0.0.1 --port $MCP_PORT
Restart=on-failure
RestartSec=10s

[Install]
WantedBy=multi-user.target
EOF

echo "[2/6] Restarting MCP Bus service..."
sudo systemctl daemon-reload
sudo systemctl restart qcc-bus
echo ""

# Step 2: Install Caddy
echo "[3/6] Installing Caddy..."
sudo apt update
sudo apt install -y caddy
echo ""

# Step 3: Create Caddyfile
echo "[4/6] Creating Caddyfile..."
sudo tee /etc/caddy/Caddyfile > /dev/null <<EOF
$DOMAIN {
    tls {
        email admin@timquant.tech
        dns cloudflare
    }
    
    reverse_proxy 127.0.0.1:$MCP_PORT {
        header_up Host {host}
        header_up X-Real-IP {remote_host}
        health_uri /health
        transport http {
            read_timeout 30s
            write_timeout 30s
        }
    }
    
    log {
        output file /var/log/caddy/access.log
        format json
    }
}
EOF

echo "[5/6] Validating Caddyfile..."
sudo caddy validate --config /etc/caddy/Caddyfile
echo ""

# Step 4: Restart Caddy
echo "[6/6] Starting Caddy service..."
sudo systemctl enable caddy
sudo systemctl restart caddy
echo ""

# Step 5: Verify services
echo "[7/6] Verifying services..."
echo ""
echo "MCP Bus Service:"
sudo systemctl status qcc-bus
echo ""
echo "Caddy Service:"
sudo systemctl status caddy
echo ""

# Step 6: Test HTTPS endpoint
echo "[8/6] Testing HTTPS endpoint..."
echo "URL: https://$DOMAIN/health"
curl -v https://$DOMAIN/health
echo ""

echo "========================================="
echo " Setup Complete!"
echo "========================================="
echo ""
echo "Public URL: https://$DOMAIN"
echo "Health Check: curl https://$DOMAIN/health"
echo "MCP Endpoint: https://$DOMAIN/mcp"
echo ""
echo "Next Steps:"
echo "1. Verify health: curl https://$DOMAIN/health"
echo "2. Test tools: curl -X POST https://$DOMAIN/mcp -H 'Authorization: Bearer YOUR_TOKEN' -H 'Content-Type: application/json' -d '{\"jsonrpc\": \"2.0\", \"method\": \"tools/list\"}'"
echo "3. Update TRAE configuration: .trae/mcp.json"
echo "4. Configure ChatGPT Connector: https://$DOMAIN/mcp"
echo "5. Check logs: sudo journalctl -u qcc-bus -f && sudo journalctl -u caddy -f"
echo ""
echo "Rollback Instructions:"
echo "1. Stop Caddy: sudo systemctl stop caddy"
echo "2. Stop MCP Bus: sudo systemctl stop qcc-bus"
echo "3. Restore MCP Bus binding: Edit /etc/systemd/system/qcc-bus.service"
echo "4. Remove Caddyfile: sudo rm /etc/caddy/Caddyfile"
