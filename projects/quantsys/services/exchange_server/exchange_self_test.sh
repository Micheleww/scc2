#!/bin/bash

# exchange_self_test.sh - 公网连通自检脚本

set -e

echo "=== Exchange Server 公网连通自检脚本 ==="

# 配置
EXCHANGE_URL="${1:-http://localhost:80}"
TIMEOUT=30
echo "测试目标URL: $EXCHANGE_URL"

# 1. 测试 /mcp 端点
echo -e "\n1. 测试 /mcp 端点..."
response=$(curl -s -o /dev/null -w "%{http_code}" -X GET "$EXCHANGE_URL/mcp" -H "Content-Type: application/json" -H "Authorization: Bearer dummy-token" -m $TIMEOUT)

echo "   HTTP状态码: $response"
if [[ $response == "200" || $response == "401" ]]; then
    echo "   ✅ /mcp 端点访问成功（预期状态码：200或401）"
else
    echo "   ❌ /mcp 端点访问失败，状态码：$response"
    exit 1
fi

# 2. 测试 /sse 端点（持续心跳）
echo -e "\n2. 测试 /sse 端点（持续心跳，$TIMEOUT秒）..."

# 创建临时文件保存输出
temp_file=$(mktemp)

# 运行curl命令，捕获输出和状态
curl -s -N -X GET "$EXCHANGE_URL/sse" -H "Content-Type: text/event-stream" -m $TIMEOUT > $temp_file &
curl_pid=$!

# 等待curl命令完成或超时
sleep $TIMEOUT

# 检查curl是否仍在运行
if ps -p $curl_pid > /dev/null; then
    kill $curl_pid 2>/dev/null || true
    wait $curl_pid 2>/dev/null || true
fi

# 检查输出是否包含心跳
echo "   检查SSE心跳..."
heartbeat_count=$(grep -c "heartbeat" $temp_file || true)
echo "   收到心跳次数: $heartbeat_count"

if [[ $heartbeat_count -ge 1 ]]; then
    echo "   ✅ /sse 端点心跳正常"
    success=true
else
    echo "   ❌ /sse 端点未收到心跳"
    echo "   输出内容:"
    cat $temp_file
    success=false
fi

# 清理临时文件
rm -f $temp_file

echo -e "\n=== 自检结果 ==="
if $success; then
    echo "✅ 所有测试通过"
    exit 0
else
    echo "❌ 测试失败"
    exit 1
fi
