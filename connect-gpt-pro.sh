#!/bin/bash

echo "🚀 OpenCode GPT Pro 连接助手"
echo "=================================="

# 切换到项目目录
cd C:\scc

echo "📋 当前配置状态:"
if [ -f "opencode.json" ]; then
    echo "✅ 项目配置文件已就绪"
    echo "🤖 配置的模型: $(grep -o '"model": "[^"]*' opencode.json | head -1 | cut -d'"' -f4)"
else
    echo "❌ 配置文件不存在"
fi

echo ""
echo "🔑 当前认证状态:"
opencode auth list

echo ""
echo "🎯 即将启动 OpenCode TUI..."
echo "请在TUI中按以下步骤操作:"
echo ""
echo "1️⃣  输入命令: /connect"
echo "2️⃣ 选择提供商: OpenAI"
echo "3️⃣ 认证方式: ChatGPT Plus/Pro"
echo "4️⃣ 浏览器认证: 登录你的GPT账户"
echo "5️⃣ 验证模型: /models"
echo ""
echo "✨ 连接成功后你将能使用:"
echo "   • gpt-4o (最新模型)"
echo "   • gpt-4o-mini (快速响应)"
echo "   • 你的Pro账户所有可用模型"
echo ""
echo "按任意键启动 OpenCode..."
read -n 1

# 启动 OpenCode
opencode