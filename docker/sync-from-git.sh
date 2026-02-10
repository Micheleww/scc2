#!/bin/sh
# SCC Docker Git 同步脚本
# 用于从 GitHub 同步最新代码到容器

echo "=================================="
echo "SCC Git 同步工具"
echo "=================================="
echo ""

# 设置 Git 目录
SCC_DIR="/app"
cd "$SCC_DIR"

# 检查远程仓库
echo "📡 检查远程仓库..."
git remote -v

# 获取最新代码
echo ""
echo "📥 从 GitHub 拉取最新代码..."
git fetch origin

# 检查是否有更新
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main 2>/dev/null || git rev-parse origin/master 2>/dev/null)

if [ "$LOCAL" != "$REMOTE" ]; then
    echo ""
    echo "🔄 发现更新，正在同步..."
    git reset --hard origin/main 2>/dev/null || git reset --hard origin/master 2>/dev/null
    echo "✅ 同步完成！"
else
    echo ""
    echo "✅ 已经是最新版本"
fi

# 显示当前版本
echo ""
echo "📋 当前版本："
git log -1 --oneline

echo ""
echo "=================================="
echo "同步完成"
echo "=================================="
