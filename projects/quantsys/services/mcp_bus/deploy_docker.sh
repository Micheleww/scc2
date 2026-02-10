#!/bin/bash

# Deployment script for MCP Bus to Docker on AWS EC2

# Configuration
EC2_USER="ubuntu"
EC2_HOST="54.179.47.252"
KEY_PATH="D:/quantsys/corefiles/aws_key.pem"
REMOTE_DIR="/home/ubuntu/mcp_bus"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Starting MCP Bus Docker deployment to AWS EC2...${NC}"

# 1. Connect to EC2 and install dependencies if needed
echo -e "${GREEN}1. Checking dependencies on EC2 instance...${NC}"
ssh -i "$KEY_PATH" "$EC2_USER@$EC2_HOST" << 'EOF'
    # Update system packages
    sudo apt-get update -y
    
    # Install Docker if not installed
    if ! command -v docker &> /dev/null; then
        echo "Installing Docker..."
        sudo apt-get install -y apt-transport-https ca-certificates curl software-properties-common
        curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add -
        sudo add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable"
        sudo apt-get update -y
        sudo apt-get install -y docker-ce docker-ce-cli containerd.io
        sudo usermod -aG docker $USER
    fi
    
    # Install Docker Compose if not installed
    if ! command -v docker-compose &> /dev/null; then
        echo "Installing Docker Compose..."
        sudo curl -L "https://github.com/docker/compose/releases/download/1.29.2/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
        sudo chmod +x /usr/local/bin/docker-compose
    fi
    
    # Create remote directory if it doesn't exist
    mkdir -p "$REMOTE_DIR"
EOF

# 2. Copy files to EC2
echo -e "${GREEN}2. Copying files to EC2 instance...${NC}"

# Copy main files
scp -i "$KEY_PATH" -r \
    Dockerfile \
    docker-compose.yml \
    Caddyfile \
    requirements.txt \
    server \
    config \
    "$EC2_USER@$EC2_HOST:$REMOTE_DIR/"

# 3. Deploy and start services on EC2
echo -e "${GREEN}3. Deploying and starting services...${NC}"
ssh -i "$KEY_PATH" "$EC2_USER@$EC2_HOST" << 'EOF'
    cd "$REMOTE_DIR"
    
    # Stop existing services if any
    docker-compose down
    
    # Build and start new services
    docker-compose up -d --build
    
    # Show status
    echo "\nServices status:"
    docker-compose ps
    
    # Show logs for verification
    echo "\nContainer logs (last 20 lines):"
    docker-compose logs --tail=20
EOF

echo -e "${GREEN}4. Deployment completed successfully!${NC}"
echo -e "${YELLOW}You can access the MCP service at:${NC}"
echo -e "   - HTTP: http://$EC2_HOST"
echo -e "   - HTTPS: https://$EC2_HOST"
echo -e "   - Health check: https://$EC2_HOST/health"
echo -e "\n${YELLOW}Useful commands:${NC}"
echo -e "   - Check logs: ssh -i $KEY_PATH $EC2_USER@$EC2_HOST 'cd $REMOTE_DIR && docker-compose logs -f'"
echo -e "   - Restart services: ssh -i $KEY_PATH $EC2_USER@$EC2_HOST 'cd $REMOTE_DIR && docker-compose restart'"
echo -e "   - Update services: ssh -i $KEY_PATH $EC2_USER@$EC2_HOST 'cd $REMOTE_DIR && docker-compose pull && docker-compose up -d'"