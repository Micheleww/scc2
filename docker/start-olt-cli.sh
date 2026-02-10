#!/bin/sh
# OLT CLI 服务器启动脚本
# 在 Docker 容器内启动 OLT CLI 桥接服务器

echo "=================================="
echo "OLT CLI Server Launcher"
echo "=================================="
echo ""

# 设置工作目录
SCC_DIR="/app"
cd "$SCC_DIR"

# 检查 Node.js
if ! command -v node >/dev/null 2>&1; then
    echo "❌ Node.js 未安装"
    exit 1
fi

echo "✅ Node.js 版本: $(node --version)"

# 检查 opencode 和 codex
if command -v opencodecli >/dev/null 2>&1; then
    echo "✅ opencode 版本: $(opencodecli --version)"
else
    echo "⚠️  opencode 未安装"
fi

if command -v codex >/dev/null 2>&1; then
    echo "✅ codex 版本: $(codex --version)"
else
    echo "⚠️  codex 未安装"
fi

# 启动 OLT CLI 服务器
echo ""
echo "🚀 启动 OLT CLI 服务器..."
echo "   端口: 3458"
echo "   端点:"
echo "     - GET  /api/health"
echo "     - GET  /api/olt-cli/health"
echo "     - GET  /api/olt-cli/models"
echo "     - POST /api/olt-cli/chat/completions"
echo "     - POST /api/olt-cli/execute"
echo ""
echo "按 Ctrl+C 停止服务器"
echo "=================================="
echo ""

exec node L6_execution_layer/scc_server_with_olt.mjs
