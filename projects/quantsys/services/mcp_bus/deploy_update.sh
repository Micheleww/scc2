#!/bin/bash

# 部署更新脚本 - 用于更新服务器上的MCP代码和重新构建容器

# 创建服务器目录结构
mkdir -p /home/ubuntu/mcp_bus/server

# 从本地复制文件到服务器
scp -i "D:/quantsys/corefiles/aws_key.pem" d:/quantsys/tools/mcp_bus/server/main.py ubuntu@54.179.47.252:/home/ubuntu/mcp_bus/server/
scp -i "D:/quantsys/corefiles/aws_key.pem" d:/quantsys/tools/mcp_bus/server/tools.py ubuntu@54.179.47.252:/home/ubuntu/mcp_bus/server/
scp -i "D:/quantsys/corefiles/aws_key.pem" d:/quantsys/tools/mcp_bus/server/security.py ubuntu@54.179.47.252:/home/ubuntu/mcp_bus/server/
scp -i "D:/quantsys/corefiles/aws_key.pem" d:/quantsys/tools/mcp_bus/server/audit.py ubuntu@54.179.47.252:/home/ubuntu/mcp_bus/server/
scp -i "D:/quantsys/corefiles/aws_key.pem" d:/quantsys/tools/mcp_bus/server/__init__.py ubuntu@54.179.47.252:/home/ubuntu/mcp_bus/server/

# 在服务器上执行部署操作
ssh -i "D:/quantsys/corefiles/aws_key.pem" "ubuntu@54.179.47.252" "
# 重新构建Docker镜像并运行容器
echo '=== 重新构建Docker镜像 ==='
cd /home/ubuntu/mcp_bus
docker-compose down --remove-orphans
docker-compose build
docker-compose up -d

# 等待服务启动
echo '=== 等待服务启动 ==='
sleep 10

# 检查部署结果
echo '=== 部署结果 ==='
echo '容器状态:'
docker ps -a | grep mcp
echo '
服务日志（最后20行）:'
docker logs mcp-server --tail=20
echo '
健康检查:'
curl -i http://localhost:18080/health
echo '
测试GET请求:'
curl -i https://mcp.timquant.tech/mcp
echo '
=== 测试完成 ==='
"
