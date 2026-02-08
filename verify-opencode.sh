#!/bin/bash

echo "🔍 OpenCode GPT Pro 连接验证脚本"
echo "=================================="

# 检查OpenCode是否安装
if command -v opencode &> /dev/null; then
    echo "✅ OpenCode 已安装: $(opencode --version 2>/dev/null || echo '版本检查失败')"
else
    echo "❌ OpenCode 未安装"
    exit 1
fi

# 检查配置文件
if [ -f "opencode.json" ]; then
    echo "✅ 项目配置文件存在"
    echo "📄 配置内容预览:"
    cat opencode.json | jq '.provider.openai' 2>/dev/null || echo "OpenAI provider配置"
else
    echo "❌ 项目配置文件不存在"
fi

# 检查认证存储
if [ -f "$HOME/.local/share/opencode/auth.json" ]; then
    echo "✅ 认证存储存在"
    echo "🔑 已配置的提供商:"
    cat "$HOME/.local/share/opencode/auth.json" | jq -r 'keys[]' 2>/dev/null || echo "无法解析认证信息"
else
    echo "⚠️  认证存储不存在 - 需要连接"
fi

echo ""
echo "📋 下一步操作指南:"
echo "1. 运行: opencode"
echo "2. 在TUI中输入: /connect"
echo "3. 选择 OpenAI → ChatGPT Plus/Pro"
echo "4. 完成浏览器认证"
echo "5. 验证: /models"

echo ""
echo "🚀 现在可以启动 OpenCode 了!"