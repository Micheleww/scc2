#!/bin/bash

# Deployment script for AWS MCP Server
# This script copies the local server code to the AWS EC2 instance and restarts the service

# Configuration
EC2_IP="18.136.163.228"
EC2_USER="ubuntu"
EC2_KEY="d:/quantsys/aws-key/timquant-aws-1.pem"
REMOTE_DIR="/home/ubuntu/mcp_bus"
LOCAL_DIR="d:/quantsys/tools/mcp_bus"

# Colors for output
GREEN="\033[0;32m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
NC="\033[0m" # No Color

echo -e "${GREEN}Starting AWS MCP Server Deployment...${NC}"
echo -e "${GREEN}======================================${NC}"

# 1. Check if local directory exists
if [ ! -d "$LOCAL_DIR" ]; then
    echo -e "${RED}Error: Local directory $LOCAL_DIR does not exist${NC}"
    exit 1
fi

# 2. Copy server code to EC2 instance
echo -e "\n${YELLOW}2. Copying server code to EC2 instance...${NC}"
scp -i "$EC2_KEY" -r "$LOCAL_DIR/server" "$EC2_USER@$EC2_IP:$REMOTE_DIR/"

if [ $? -ne 0 ]; then
    echo -e "${RED}Error: Failed to copy server code to EC2 instance${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Server code copied successfully${NC}"

# 3. Copy other necessary files
echo -e "\n${YELLOW}3. Copying other necessary files...${NC}"
scp -i "$EC2_KEY" "$LOCAL_DIR/requirements.txt" "$EC2_USER@$EC2_IP:$REMOTE_DIR/"
scp -i "$EC2_KEY" "$LOCAL_DIR/.env.example" "$EC2_USER@$EC2_IP:$REMOTE_DIR/.env"

if [ $? -ne 0 ]; then
    echo -e "${RED}Error: Failed to copy necessary files to EC2 instance${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Necessary files copied successfully${NC}"

# 4. SSH into EC2 instance and restart the service
echo -e "\n${YELLOW}4. Restarting MCP Server on EC2 instance...${NC}"
ssh -i "$EC2_KEY" "$EC2_USER@$EC2_IP" << 'EOF'
    cd /home/ubuntu/mcp_bus
    
    # Create .env file if it doesn't exist
    if [ ! -f ".env" ]; then
        echo "Creating .env file..."
        cp .env.example .env
    fi
    
    # Set AUTH_MODE to none for GPT connector compatibility
    echo "Setting AUTH_MODE=none..."
    sed -i 's/AUTH_MODE=.*/AUTH_MODE=none/' .env
    
    # Stop any existing uvicorn processes
    echo "Stopping existing uvicorn processes..."
    pkill -f uvicorn || true
    
    # Start the server in the background with AUTH_MODE=none
    echo "Starting MCP Server with AUTH_MODE=none..."
    AUTH_MODE=none nohup uvicorn server.main:app --host 0.0.0.0 --port 443 --ssl-keyfile /etc/letsencrypt/live/mcp.timquant.tech/privkey.pem --ssl-certfile /etc/letsencrypt/live/mcp.timquant.tech/fullchain.pem > mcp_server.log 2>&1 &
    
    echo "MCP Server started successfully!"
    echo "Check logs: tail -f mcp_server.log"
EOF

echo -e "\n${GREEN}======================================${NC}"
echo -e "${GREEN}Deployment completed successfully!${NC}"
echo -e "${GREEN}AWS MCP Server should now be running with the latest code.${NC}"
echo -e "${GREEN}Check the server status with: ssh -i $EC2_KEY $EC2_USER@$EC2_IP 'tail -f mcp_bus/mcp_server.log'${NC}"
