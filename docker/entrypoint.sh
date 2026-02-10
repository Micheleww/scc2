#!/bin/sh
# SCC Backend Entrypoint Script
# 17层分层架构 - 唯一真本

set -e

echo "=================================="
echo "SCC Backend (scc-bd)"
echo "17层分层架构 - 唯一真本"
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

# 显示17层结构
echo "17层架构:"
echo "  L1: 代码层 (Gateway)"
echo "  L2: 任务层 (Context Pack, Contracts)"
echo "  L3: 文档层 (SSOT)"
echo "  L4: 提示词层 (Skills, Roles)"
echo "  L5: 模型层 (Models)"
echo "  L6: Agent层 (Orchestrators)"
echo "  L7: 工具层 (Capabilities)"
echo "  L8: 证据层 (Verdict)"
echo "  L9: 状态层 (State Stores)"
echo "  L10: 工作空间层"
echo "  L11: 路由层 (Router)"
echo "  L12: 成本层"
echo "  L13: 安全层 (Gates)"
echo "  L14: 质量层 (Validators)"
echo "  L15: 变更层 (Playbooks)"
echo "  L16: 观测层 (Logging)"
echo "  L17: 本体层 (Map, OID)"
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

# 执行传入的命令
echo "Starting SCC Backend..."
echo "Command: $@"
echo "=================================="
echo ""

exec "$@"
