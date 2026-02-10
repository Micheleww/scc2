#!/bin/sh
# SCC Backend Entrypoint Script
# scc-bd 作为唯一真本

set -e

echo "=================================="
echo "SCC Backend (scc-bd)"
echo "唯一真本 - 独立完整系统"
echo "=================================="

# 确保日志目录存在
mkdir -p /app/artifacts/scc_state /app/data /app/logs /app/state

# 显示环境信息
echo ""
echo "Environment:"
echo "  NODE_ENV: ${NODE_ENV:-production}"
echo "  GATEWAY_PORT: ${GATEWAY_PORT:-18788}"
echo "  LOG_LEVEL: ${LOG_LEVEL:-info}"
echo "  REPO_ROOT: ${REPO_ROOT:-/app}"
echo ""

# 显示插件配置
echo "Plugin Upstreams:"
echo "  OpenCode: ${OPENCODE_UPSTREAM:-disabled}"
echo "  Clawdbot: ${CLAWDBOT_UPSTREAM:-disabled}"
echo "  SCC Upstream: ${SCC_UPSTREAM:-disabled}"
echo ""

# 验证 Node.js 和 Python
echo "Runtime Versions:"
echo "  Node.js: $(node --version)"
echo "  Python: $(python --version)"
echo ""

# 检查目录权限
echo "Checking directory permissions..."
if [ ! -w "/app/logs" ]; then
    echo "WARNING: /app/logs is not writable"
fi
if [ ! -w "/app/artifacts" ]; then
    echo "WARNING: /app/artifacts is not writable"
fi
echo ""

# ============================================
# 启动方式选择
# ============================================

# 如果传入了命令，执行传入的命令
if [ $# -gt 0 ]; then
    echo "Starting with custom command..."
    echo "Command: $@"
    echo "=================================="
    echo ""
    exec "$@"
fi

# 默认使用 Service Manager 启动所有服务
echo "Starting SCC Service Manager..."
echo "This will start all required services:"
echo "  1. SCC Gateway (port 18788)"
echo "  2. Parent Inbox Watcher"
echo "  3. OLT CLI Server (port 3458, optional)"
echo ""
echo "=================================="
echo ""

exec node L1_code_layer/docker/service-manager.mjs
