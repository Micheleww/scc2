#!/bin/bash

# QCC Bus MCP Server - EC2 Quick Deployment Script
# Target: AWS EC2 Instance (13.229.100.10)
# Port: 18080

set -e

echo "========================================="
echo " QCC Bus MCP Server - EC2 Deployment"
echo "========================================="
echo ""

# Configuration
EC2_IP="13.229.100.10"
EC2_PORT="18080"
REPO_ROOT="/home/ubuntu/qcc-bus"
MCP_DIR="$REPO_ROOT/tools/mcp_bus"

# Generate secure token (32 characters)
echo "[1/5] Generating secure token..."
TOKEN=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
echo "Token generated: ${TOKEN:0:20}..."
echo ""

# Create repository directory
echo "[2/5] Setting up repository..."
mkdir -p $REPO_ROOT
cd $REPO_ROOT

# Option A: Clone repository (recommended)
# git clone https://your-repo-url.git .

# Option B: Upload only tools/mcp_bus directory (faster)
# Create minimal structure
mkdir -p $MCP_DIR

# Create systemd service file
echo "[3/5] Creating systemd service..."
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
ExecStart=/usr/bin/python3 -m uvicorn server.main:app --host 0.0.0.0 --port $EC2_PORT
Restart=on-failure
RestartSec=10s

[Install]
WantedBy=multi-user.target
EOF

echo "[4/5] Installing dependencies..."
cd $MCP_DIR
pip3 install -r requirements.txt

echo "[5/5] Starting service..."
sudo systemctl daemon-reload
sudo systemctl enable qcc-bus
sudo systemctl start qcc-bus

echo ""
echo "========================================="
echo " Deployment Complete!"
echo "========================================="
echo ""
echo "Service Status:"
sudo systemctl status qcc-bus
echo ""
echo "Public URL: http://$EC2_IP:$EC2_PORT"
echo "Health Check: curl http://$EC2_IP:$EC2_PORT/health"
echo ""
echo "Next Steps:"
echo "1. Verify health: curl http://$EC2_IP:$EC2_PORT/health"
echo "2. Check logs: sudo journalctl -u qcc-bus -f"
echo "3. Update AWS Security Group to allow port $EC2_PORT"
echo "4. (Optional) Set up HTTPS with Caddy + Let's Encrypt"
echo ""
echo "Token stored in: /etc/systemd/system/qcc-bus.service"
echo "To rotate token: Edit service file and run: sudo systemctl daemon-reload && sudo systemctl restart qcc-bus"
