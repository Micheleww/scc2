#!/bin/bash

echo "=== MCP服务Docker部署脚本 ==="
echo "部署时间: $(date)"
echo ""

# 1. 检查并安装Docker
if ! command -v docker &> /dev/null; then
    echo "1. 安装Docker..."
    sudo apt-get update
    sudo apt-get install -y docker.io docker-compose
    sudo systemctl enable docker
    sudo systemctl start docker
    sudo usermod -aG docker $USER
    newgrp docker
else
    echo "1. Docker已安装"
fi

# 2. 检查并安装Docker Compose
if ! command -v docker-compose &> /dev/null; then
    echo "2. 安装Docker Compose..."
    sudo apt-get update
    sudo apt-get install -y docker-compose
else
    echo "2. Docker Compose已安装"
fi

# 3. 创建部署目录
DEPLOY_DIR="/home/ubuntu/mcp_bus"
echo "3. 创建部署目录: $DEPLOY_DIR"
sudo mkdir -p $DEPLOY_DIR
cd $DEPLOY_DIR

# 4. 复制必要文件
# 注意：此脚本应与项目文件放在同一目录下运行，或通过scp等方式将文件传输到EC2实例
echo "4. 复制项目文件..."
# 如果是从本地运行，需要先将文件上传到EC2实例
# 例如：scp -i "aws_key.pem" Dockerfile docker-compose.yml Caddyfile requirements.txt server/ config/ ubuntu@ec2-instance-ip:/home/ubuntu/mcp_bus/

# 5. 构建Docker镜像
echo "5. 构建Docker镜像..."
docker-compose build

# 6. 停止并移除旧容器
echo "6. 清理旧容器..."
docker-compose down

# 7. 启动服务
echo "7. 启动Docker服务..."
docker-compose up -d

# 8. 等待服务启动
echo "8. 等待服务启动（10秒）..."
sleep 10

# 9. 检查服务状态
echo "9. 检查服务状态..."
docker-compose ps

# 10. 查看日志
echo "10. 查看MCP服务日志（最后20行）..."
docker-compose logs --tail=20 mcp

echo ""
echo "=== 部署完成 ==="
echo "服务地址: http://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4):80"
echo "HTTPS地址: https://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4)"
echo "MCP服务端口: 8000"
echo "健康检查: curl http://localhost:80/health"
echo ""
echo "使用以下命令管理服务:"
echo "  启动服务: docker-compose up -d"
echo "  停止服务: docker-compose down"
echo "  查看日志: docker-compose logs -f"
echo "  检查状态: docker-compose ps"
