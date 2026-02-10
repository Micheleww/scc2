#!/bin/bash

# 简化的MCP服务部署脚本
# 直接在EC2实例上执行，避免复杂的配置和依赖问题

# 定义日志文件
LOG_FILE="/tmp/mcp_simple_deploy_$(date +%Y%m%d_%H%M%S).log"

# 日志记录函数 - 将stdout和stderr同时输出到终端和日志文件
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1"
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

# 初始化日志
log "开始执行MCP服务部署脚本"

# 定义变量
EC2_HOST="54.179.47.252"
KEY_PATH="D:/quantsys/corefiles/aws_key.pem"
REMOTE_DIR="/home/ubuntu/mcp_bus"

# 设置默认EXIT_CODE
export EXIT_CODE=0

# 创建临时目录存放部署文件
temp_dir=$(mktemp -d)
log "使用临时目录: $temp_dir"

# 创建所有必要的部署文件

# 1. Dockerfile
log "创建Dockerfile..."
cat > "$temp_dir/Dockerfile" << 'EOF'
FROM python:3.11-slim

WORKDIR /app

# 复制依赖文件
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY server server/
COPY config config/
COPY docs docs/

# 设置环境变量
ENV REPO_ROOT=/app
ENV AUTH_MODE=none

# 安装curl用于健康检查
RUN apt-get update && apt-get install -y curl

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:18788/health || exit 1

# 运行应用
CMD python -m uvicorn server.main:app --host 0.0.0.0 --port 8000 --log-level info
EOF

# 2. 复制配置文件
log "复制配置文件..."
mkdir -p "$temp_dir/config"
cp -f config/config.example.json "$temp_dir/config/"

# 3. 复制依赖文件
log "复制依赖文件..."
cp -f requirements.txt "$temp_dir/"

# 4. 复制服务器代码
log "复制服务器代码..."
mkdir -p "$temp_dir/server"
cp -r server/* "$temp_dir/server/"

# 5. 创建部署脚本
log "创建部署脚本..."
cat > "$temp_dir/ec2_deploy.sh" << 'EOF'
#!/bin/bash

echo "=== 开始部署MCP服务 ==="

# 切换到工作目录
cd /home/ubuntu/mcp_bus

# 清理旧资源
echo "清理旧资源..."
docker stop mcp-server 2>/dev/null || true
docker rm mcp-server 2>/dev/null || true
docker rmi mcp-server 2>/dev/null || true

# 构建镜像
echo "构建Docker镜像..."
docker build -t mcp-server .

# 运行容器
echo "运行Docker容器..."
docker run -d --name mcp-server \
  -p 18080:8000 \
  --restart always \
  mcp-server

# 等待服务启动
echo "等待服务启动..."
sleep 5

# 检查部署结果
echo "=== 部署结果 ==="
echo "容器状态："
docker ps -a | grep mcp-server

# 检查日志
echo "\n最近日志："
docker logs --tail=10 mcp-server

# 测试服务
    echo "\n健康检查："
    curl -s -w "状态码: %{http_code}\n" --connect-timeout 5 --max-time 10 -H "Accept: application/json" http://localhost:18080/health || echo "连接失败"
    echo "\n服务地址：http://$(curl -s --connect-timeout 5 --max-time 10 http://169.254.169.254/latest/meta-data/public-ipv4):18080"
echo "=== 部署完成 ==="
EOF
chmod +x "$temp_dir/ec2_deploy.sh"

# 将所有文件复制到EC2实例
log "\n将文件复制到EC2实例..."
# 添加超时包装，5分钟超时
if timeout 300 ssh -i "$KEY_PATH" "ubuntu@$EC2_HOST" "mkdir -p $REMOTE_DIR"; then
    log "成功创建远程目录"
else
    log "错误：创建远程目录超时或失败"
    EXIT_CODE=1
fi

if [ $EXIT_CODE -eq 0 ]; then
    if timeout 300 scp -i "$KEY_PATH" -r "$temp_dir/*" "ubuntu@$EC2_HOST:$REMOTE_DIR/"; then
        log "成功复制文件到EC2实例"
    else
        log "错误：复制文件到EC2实例超时或失败"
        EXIT_CODE=1
    fi
fi

# 在EC2实例上执行部署脚本
if [ $EXIT_CODE -eq 0 ]; then
    log "\n在EC2实例上执行部署脚本..."
    if timeout 600 ssh -i "$KEY_PATH" "ubuntu@$EC2_HOST" "cd $REMOTE_DIR && ./ec2_deploy.sh"; then
        log "成功执行部署脚本"
    else
        log "错误：执行部署脚本超时或失败"
        EXIT_CODE=1
    fi
fi

# 清理临时目录
log "\n清理临时目录..."
rm -rf "$temp_dir"

log "\n部署完成！"

# 输出EXIT_CODE
echo "EXIT_CODE=$EXIT_CODE"
echo "EXIT_CODE=$EXIT_CODE" >> "$LOG_FILE"

# 将日志复制到指定位置
mkdir -p "docs/REPORT/ops/artifacts/HANG_GUARD"
cp "$LOG_FILE" "docs/REPORT/ops/artifacts/HANG_GUARD/selftest.log"

exit $EXIT_CODE
