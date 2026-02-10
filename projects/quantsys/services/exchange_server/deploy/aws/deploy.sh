#!/bin/bash

# deploy.sh - Exchange Server AWS部署脚本

set -e

echo "=== Exchange Server AWS部署脚本 ==="

# 1. 安装Docker和Docker Compose
echo "1. 安装Docker和Docker Compose..."
yum update -y
yum install -y docker
systemctl start docker
systemctl enable docker

# 安装Docker Compose
curl -L "https://github.com/docker/compose/releases/download/v2.23.3/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

# 2. 克隆代码库
echo "2. 克隆代码库..."
git clone https://github.com/your-org/quantsys.git /opt/quantsys
cd /opt/quantsys

# 3. 创建配置目录和日志目录
echo "3. 创建配置目录和日志目录..."
mkdir -p /opt/quantsys/tools/exchange_server/config
mkdir -p /opt/quantsys/tools/exchange_server/logs

# 4. 构建和启动服务
echo "4. 构建和启动服务..."
docker-compose -f tools/exchange_server/deploy/aws/docker-compose.yml up -d --build

# 5. 验证服务状态
echo "5. 验证服务状态..."
sleep 15
docker-compose -f tools/exchange_server/deploy/aws/docker-compose.yml ps

echo "6. 检查服务日志..."
docker-compose -f tools/exchange_server/deploy/aws/docker-compose.yml logs -n 20 exchange-server

# 6. 配置日志转发到CloudWatch
echo "7. 配置日志转发到CloudWatch..."
# 安装CloudWatch代理
wget https://s3.amazonaws.com/amazoncloudwatch-agent/amazon_linux/amd64/latest/amazon-cloudwatch-agent.rpm
rpm -U ./amazon-cloudwatch-agent.rpm

# 配置CloudWatch代理
cat > /opt/aws/amazon-cloudwatch-agent/bin/config.json << EOF
{
  "agent": {
    "metrics_collection_interval": 60,
    "run_as_user": "root"
  },
  "logs": {
    "logs_collected": {
      "files": {
        "collect_list": [
          {
            "file_path": "/opt/quantsys/tools/exchange_server/logs/exchange_server.log",
            "log_group_name": "/aws/ecs/exchange-server",
            "log_stream_name": "{instance_id}",
            "retention_in_days": 30
          }
        ]
      }
    }
  }
}
EOF

# 启动CloudWatch代理
/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -a fetch-config -m ec2 -s -c file:/opt/aws/amazon-cloudwatch-agent/bin/config.json

echo "=== 部署完成 ==="
echo "Exchange Server已成功部署在端口8080"
echo "可通过以下命令访问：curl http://localhost:18788/healthcheck"
echo "公网访问地址：http://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4)"
