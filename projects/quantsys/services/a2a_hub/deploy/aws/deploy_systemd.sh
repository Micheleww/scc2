#!/bin/bash

# A2A Hub AWS Systemd Deployment Script
# Version: v0.1
# Date: 2026-01-16

set -e

echo "=== A2A Hub Systemd Deployment Script ==="
echo ""

# Configuration
REPO_URL="https://github.com/your-repo/quantsys.git"
INSTALL_DIR="/opt/quantsys"
A2A_HUB_DIR="${INSTALL_DIR}/tools/a2a_hub"
SECRET_KEY="$(openssl rand -hex 32)"

# 1. Update system
echo "1. Updating system..."
sudo yum update -y

# 2. Install dependencies
echo "2. Installing dependencies..."
sudo yum install -y python3 python3-pip git openssl

# 3. Clone repository
echo "3. Cloning repository..."
if [ -d "${INSTALL_DIR}" ]; then
    sudo rm -rf "${INSTALL_DIR}"
fi
git clone "${REPO_URL}" "${INSTALL_DIR}"

# 4. Install Python dependencies
echo "4. Installing Python dependencies..."
cd "${A2A_HUB_DIR}"
pip3 install --user -r requirements.txt

# 5. Create state and backup directories
echo "5. Creating state and backup directories..."
sudo mkdir -p "${A2A_HUB_DIR}/state"
sudo mkdir -p "${A2A_HUB_DIR}/backup"
sudo chown -R ec2-user:ec2-user "${A2A_HUB_DIR}"

# 6. Create Systemd service file
echo "6. Creating Systemd service file..."
cat << EOF | sudo tee /etc/systemd/system/a2a-hub.service
[Unit]
Description=A2A Hub Service
After=network.target

[Service]
Type=simple
User=ec2-user
WorkingDirectory=${A2A_HUB_DIR}
ExecStart=/usr/bin/python3 main.py
Restart=always
RestartSec=5
Environment="A2A_HUB_SECRET_KEY=${SECRET_KEY}"
Environment="PYTHONUNBUFFERED=1"

[Install]
WantedBy=multi-user.target
EOF

# 7. Reload Systemd and start service
echo "7. Starting A2A Hub service..."
sudo systemctl daemon-reload
sudo systemctl enable a2a-hub
sudo systemctl start a2a-hub

# 8. Wait for service to start
echo "8. Waiting for service to start..."
sleep 5

# 9. Check service status
echo "9. Checking service status..."
sudo systemctl status a2a-hub --no-pager

# 10. Verify API is accessible
echo "10. Verifying API accessibility..."
if curl -s http://localhost:18788/api > /dev/null; then
    echo "✓ A2A Hub API is accessible"
else
    echo "✗ A2A Hub API is not accessible"
    exit 1
fi

# 11. Create backup script
echo "11. Creating backup script..."
cat << EOF | sudo tee /usr/local/bin/backup_a2a_hub
#!/bin/bash

BACKUP_DIR="${A2A_HUB_DIR}/backup"
TIMESTAMP=$(date +%Y%m%d%H%M%S)

# Create backup directory if it doesn't exist
mkdir -p "${BACKUP_DIR}"

# Backup database
cp "${A2A_HUB_DIR}/state/a2a_hub.db" "${BACKUP_DIR}/a2a_hub.db.${TIMESTAMP}"

# Keep only last 7 days of backups
find "${BACKUP_DIR}" -name "a2a_hub.db.*" -type f -mtime +7 -delete

echo "Backup completed: ${BACKUP_DIR}/a2a_hub.db.${TIMESTAMP}"
EOF

sudo chmod +x /usr/local/bin/backup_a2a_hub

# 12. Create cron job for backups
echo "12. Creating cron job for backups..."
(crontab -l 2>/dev/null; echo "0 * * * * /usr/local/bin/backup_a2a_hub") | sudo crontab -

# 13. Create health check script
echo "13. Creating health check script..."
cat << EOF | sudo tee /usr/local/bin/health_check_a2a_hub
#!/bin/bash

# Check service status
if systemctl is-active --quiet a2a-hub; then
    # Check API response
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:18788/api/health || echo "500")
    if [ "${HTTP_CODE}" -eq 200 ]; then
        echo "OK: A2A Hub is healthy"
        exit 0
    else
        echo "ERROR: A2A Hub API returned HTTP ${HTTP_CODE}"
        exit 1
    fi
else
    echo "ERROR: A2A Hub service is not running"
    exit 1
fi
EOF

sudo chmod +x /usr/local/bin/health_check_a2a_hub

# 14. Create rollback script
echo "14. Creating rollback script..."
cat << EOF | sudo tee /usr/local/bin/rollback_a2a_hub
#!/bin/bash

BACKUP_FILE=\$1

if [ -z "\${BACKUP_FILE}" ]; then
    echo "Usage: \$0 <backup_file>"
    echo "Available backups:"
    ls -la "${A2A_HUB_DIR}/backup/"
    exit 1
fi

if [ ! -f "\${BACKUP_FILE}" ]; then
    echo "ERROR: Backup file not found: \${BACKUP_FILE}"
    exit 1
fi

echo "Rolling back A2A Hub..."

# Stop service
sudo systemctl stop a2a-hub

# Restore database
echo "Restoring database from \${BACKUP_FILE}..."
sudo cp "\${BACKUP_FILE}" "${A2A_HUB_DIR}/state/a2a_hub.db"
sudo chown ec2-user:ec2-user "${A2A_HUB_DIR}/state/a2a_hub.db"

# Start service
sudo systemctl start a2a-hub

# Verify
echo "Verifying rollback..."
sleep 5
sudo systemctl status a2a-hub --no-pager
curl -s http://localhost:18788/api/health

echo "Rollback completed. Please verify all functionality."
EOF

sudo chmod +x /usr/local/bin/rollback_a2a_hub

echo ""
echo "=== Deployment Complete ==="
echo "A2A Hub has been deployed successfully!"
echo ""
echo "Service status:"
sudo systemctl status a2a-hub --no-pager
echo ""
echo "API Health Check:"
curl -s http://localhost:18788/api/health
echo ""
echo "Configuration:"
echo "- Installation Directory: ${A2A_HUB_DIR}"
echo "- Secret Key: ${SECRET_KEY}"
echo "- Service Name: a2a-hub"
echo ""
echo "Useful Commands:"
echo "- Check status: sudo systemctl status a2a-hub"
echo "- View logs: journalctl -u a2a-hub -f"
echo "- Start service: sudo systemctl start a2a-hub"
echo "- Stop service: sudo systemctl stop a2a-hub"
echo "- Restart service: sudo systemctl restart a2a-hub"
echo "- Backup database: sudo /usr/local/bin/backup_a2a_hub"
echo "- Health check: sudo /usr/local/bin/health_check_a2a_hub"
echo "- Rollback: sudo /usr/local/bin/rollback_a2a_hub <backup_file>"
echo ""
echo "Next Steps:"
echo "1. Configure security groups to allow access to port 5001"
echo "2. Set up S3 backup for off-site storage"
echo "3. Configure CloudWatch monitoring"
echo ""
echo "Happy deploying! 🚀"
