#!/bin/bash

# Deployment script for MCP Bus to Docker on AWS EC2

# Update system packages with sudo
sudo apt-get update -y

# Install Docker if not installed
if ! command -v docker &> /dev/null; then
    echo 'Installing Docker...'
    sudo apt-get install -y apt-transport-https ca-certificates curl software-properties-common
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add -
    sudo add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/ubuntu bionic stable"
    sudo apt-get update -y
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io
    sudo usermod -aG docker $USER
fi

# Install Docker Compose if not installed
if ! command -v docker-compose &> /dev/null; then
    echo 'Installing Docker Compose...'
    sudo curl -L "https://github.com/docker/compose/releases/download/1.29.2/docker-compose-Linux-x86_64" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
fi

# Create and enter mcp_bus directory
mkdir -p /home/ubuntu/mcp_bus
cd /home/ubuntu/mcp_bus

# Clean up old files if any
rm -rf Dockerfile docker-compose.yml Caddyfile requirements.txt server config docs

# Create necessary directories
mkdir -p server
mkdir -p config
mkdir -p docs/REPORT/inbox

# Create Dockerfile
echo 'Creating Dockerfile...'
cat > Dockerfile << 'EOF'
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV REPO_ROOT=/app
ENV MCP_BUS_HOST=0.0.0.0
ENV MCP_BUS_PORT=8000
ENV AUTH_MODE=none

EXPOSE 8000

RUN apt-get update && apt-get install -y curl

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:18788/health || exit 1

CMD ["python", "-m", "uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"]
EOF

# Create docker-compose.yml
echo 'Creating docker-compose.yml...'
cat > docker-compose.yml << 'EOF'
version: '3.8'

services:
  mcp:
    build: .
    container_name: mcp-server
    restart: always
    environment:
      - REPO_ROOT=/app
      - MCP_BUS_HOST=0.0.0.0
      - MCP_BUS_PORT=8000
      - AUTH_MODE=none
    volumes:
      - ./config:/app/config
      - ./docs:/app/docs
      - ./logs:/app/logs
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "5"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:18788/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 5s
    networks:
      - mcp-network

  caddy:
    image: caddy:2-alpine
    container_name: caddy-proxy
    restart: always
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
    depends_on:
      - mcp
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "5"
    networks:
      - mcp-network

volumes:
  caddy_data:
  caddy_config:

networks:
  mcp-network:
    driver: bridge
EOF

# Create Caddyfile
echo 'Creating Caddyfile...'
cat > Caddyfile << 'EOF'
:80 {
    redir https://{host}{uri} permanent
}

:443 {
    tls internal
    
    reverse_proxy mcp:8000 {
        health_check {
            path /health
            interval 30s
            timeout 10s
        }
        
        log {
            output stdout
            format json
            level info
        }
    }
    
    log {
        output stdout
        format json
        level info
    }
}
EOF

# Create requirements.txt
echo 'Creating requirements.txt...'
cat > requirements.txt << 'EOF'
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
pydantic>=2.5.0
python-dotenv>=1.0.0
httpx>=0.25.0
python-jose>=3.3.0
EOF

# Copy server files
echo 'Copying server files...'