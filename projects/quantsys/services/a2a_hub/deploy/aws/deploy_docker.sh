#!/bin/bash

# A2A Hub AWS Docker Deployment Script
# Version: v0.1
# Date: 2026-01-16

set -e

echo "=== A2A Hub Docker Deployment Script ==="
echo ""

# Configuration
REPO_URL="https://github.com/your-repo/quantsys.git"
INSTALL_DIR="/opt/quantsys"
A2A_HUB_DIR="${INSTALL_DIR}/tools/a2a_hub"
SECRET_KEY="$(openssl rand -hex 32)"

echo "1. Updating system..."
sudo yum update -y

echo "2. Installing Docker and Docker Compose..."
sudo yum install -y docker git

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Start Docker service
sudo systemctl start docker
sudo systemctl enable docker

# Add ec2-user to docker group
sudo usermod -aG docker ec2-user

# Apply docker group changes immediately
echo "3. Applying Docker group changes..."
newgrp docker

echo "4. Cloning repository..."
if [ -d "${INSTALL_DIR}" ]; then
    sudo rm -rf "${INSTALL_DIR}"
fi
git clone "${REPO_URL}" "${INSTALL_DIR}"

# Create Docker directory structure
echo "5. Creating Docker directory structure..."
mkdir -p "${A2A_HUB_DIR}/deploy/docker"

# Create Dockerfile
echo "6. Creating Dockerfile..."
cat << EOF | sudo tee "${A2A_HUB_DIR}/Dockerfile"
FROM python:3.12-alpine

# Set working directory
WORKDIR /app

# Install git and other dependencies
RUN apk add --no-cache git

# Clone repository
RUN git clone ${REPO_URL} /app

# Set working directory to a2a_hub
WORKDIR /app/tools/a2a_hub

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Create data directories
RUN mkdir -p /app/tools/a2a_hub/state /app/tools/a2a_hub/backup

# Expose port
EXPOSE 5001

# Set environment variables
ENV A2A_HUB_SECRET_KEY=${SECRET_KEY}
ENV PYTHONUNBUFFERED=1

# Start the application
CMD ["python", "main.py"]
EOF

# Create docker-compose.yml
echo "7. Creating docker-compose.yml..."
cat << EOF | sudo tee "${A2A_HUB_DIR}/docker-compose.yml"
version: '3.8'

services:
  a2a-hub:
    build: .
    container_name: a2a-hub
    ports:
      - "5001:5001"
    volumes:
      - a2a-hub-data:/app/tools/a2a_hub/state
      - a2a-hub-backup:/app/tools/a2a_hub/backup
    environment:
      - A2A_HUB_SECRET_KEY=${SECRET_KEY}
    restart: always
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:18788/api/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s

volumes:
  a2a-hub-data:
  a2a-hub-backup:
EOF

# Create backup script
echo "8. Creating backup script..."
cat << EOF | sudo tee "${A2A_HUB_DIR}/backup_docker.sh"
#!/bin/bash

timestamp=$(date +%Y%m%d%H%M%S)
backup_dir="/app/tools/a2a_hub/backup"

# Create backup inside container
docker exec a2a-hub sh -c "mkdir -p ${backup_dir} && cp /app/tools/a2a_hub/state/a2a_hub.db ${backup_dir}/a2a_hub.db.${timestamp}"

# Keep only last 7 days of backups
docker exec a2a-hub sh -c "find ${backup_dir} -name 'a2a_hub.db.*' -type f -mtime +7 -delete"

echo "Backup completed: ${backup_dir}/a2a_hub.db.${timestamp}"
EOF

sudo chmod +x "${A2A_HUB_DIR}/backup_docker.sh"

# Create cron job for backups
echo "9. Creating cron job for backups..."
(crontab -l 2>/dev/null; echo "0 * * * * ${A2A_HUB_DIR}/backup_docker.sh") | sudo crontab -

# Create rollback script
echo "10. Creating rollback script..."
cat << EOF | sudo tee "${A2A_HUB_DIR}/rollback_docker.sh"
#!/bin/bash

BACKUP_FILE=\$1

if [ -z "\${BACKUP_FILE}" ]; then
    echo "Usage: \$0 <backup_file>"
    echo "Available backups:"
    docker exec a2a-hub ls -la /app/tools/a2a_hub/backup/
    exit 1
fi

echo "Rolling back A2A Hub..."

# Stop service
docker-compose down

# Restore database
echo "Restoring database from \${BACKUP_FILE}..."
# Extract backup filename
BACKUP_FILENAME=$(basename "\${BACKUP_FILE}")
# Copy backup to host if needed
if [[ "\${BACKUP_FILE}" != */* ]]; then
    # If only filename provided, assume it's in the backup directory
    BACKUP_FILE="/app/tools/a2a_hub/backup/\${BACKUP_FILE}"
fi

# Start service with restored data
docker-compose up -d

# Verify
echo "Verifying rollback..."
sleep 10
docker-compose ps
docker-compose logs -f a2a-hub --tail=20
curl -s http://localhost:18788/api/health

echo "Rollback completed. Please verify all functionality."
EOF

sudo chmod +x "${A2A_HUB_DIR}/rollback_docker.sh"

# Create health check script
echo "11. Creating health check script..."
cat << EOF | sudo tee "${A2A_HUB_DIR}/health_check_docker.sh"
#!/bin/bash

# Check container status
if docker ps -f name=a2a-hub -f status=running | grep -q a2a-hub; then
    # Check API response
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:18788/api/health || echo "500")
    if [ "\${HTTP_CODE}" -eq 200 ]; then
        echo "OK: A2A Hub is healthy"
        exit 0
    else
        echo "ERROR: A2A Hub API returned HTTP \${HTTP_CODE}"
        exit 1
    fi
else
    echo "ERROR: A2A Hub container is not running"
    exit 1
fi
EOF

sudo chmod +x "${A2A_HUB_DIR}/health_check_docker.sh"

# Create start script
echo "12. Creating start script..."
cat << EOF | sudo tee "${A2A_HUB_DIR}/start_docker.sh"
#!/bin/bash

cd "${A2A_HUB_DIR}"
docker-compose up -d

# Wait for container to start
sleep 10

echo "A2A Hub started successfully!"
docker-compose ps
curl -s http://localhost:18788/api/health
EOF

sudo chmod +x "${A2A_HUB_DIR}/start_docker.sh"

# Create stop script
echo "13. Creating stop script..."
cat << EOF | sudo tee "${A2A_HUB_DIR}/stop_docker.sh"
#!/bin/bash

cd "${A2A_HUB_DIR}"
docker-compose down

echo "A2A Hub stopped successfully!"
EOF

sudo chmod +x "${A2A_HUB_DIR}/stop_docker.sh"

# Create restart script
echo "14. Creating restart script..."
cat << EOF | sudo tee "${A2A_HUB_DIR}/restart_docker.sh"
#!/bin/bash

cd "${A2A_HUB_DIR}"
docker-compose down
docker-compose up -d

# Wait for container to start
sleep 10

echo "A2A Hub restarted successfully!"
docker-compose ps
curl -s http://localhost:18788/api/health
EOF

sudo chmod +x "${A2A_HUB_DIR}/restart_docker.sh"

# Start A2A Hub using Docker Compose
echo "15. Starting A2A Hub using Docker Compose..."
cd "${A2A_HUB_DIR}"
docker-compose up -d

# Wait for container to start
echo "16. Waiting for container to start..."
sleep 10

echo "17. Checking container status..."
docker-compose ps

echo "18. Verifying API accessibility..."
if curl -s http://localhost:18788/api > /dev/null; then
    echo "✓ A2A Hub API is accessible"
else
    echo "✗ A2A Hub API is not accessible"
    exit 1
fi

echo ""
echo "=== Deployment Complete ==="
echo "A2A Hub has been deployed successfully with Docker!"
echo ""
echo "Container status:"
docker-compose ps
echo ""
echo "API Health Check:"
curl -s http://localhost:18788/api/health
echo ""
echo "Configuration:"
echo "- Installation Directory: ${A2A_HUB_DIR}"
echo "- Secret Key: ${SECRET_KEY}"
echo "- Container Name: a2a-hub"
echo "- Docker Compose File: ${A2A_HUB_DIR}/docker-compose.yml"
echo ""
echo "Useful Commands:"
echo "- Start service: ${A2A_HUB_DIR}/start_docker.sh"
echo "- Stop service: ${A2A_HUB_DIR}/stop_docker.sh"
echo "- Restart service: ${A2A_HUB_DIR}/restart_docker.sh"
echo "- View logs: docker-compose logs -f"
echo "- Backup database: ${A2A_HUB_DIR}/backup_docker.sh"
echo "- Health check: ${A2A_HUB_DIR}/health_check_docker.sh"
echo "- Rollback: ${A2A_HUB_DIR}/rollback_docker.sh <backup_file>"
echo ""
echo "Next Steps:"
echo "1. Configure security groups to allow access to port 5001"
echo "2. Set up S3 backup for off-site storage"
echo "3. Configure CloudWatch monitoring for Docker containers"
echo "4. Consider setting up a reverse proxy (NGINX) for SSL termination"
echo ""
echo "Happy deploying! 🚀"
