#!/bin/bash

# JSON-RPC调用测试脚本（Bash版本）
# 用于测试MCP服务的JSON-RPC端点

# 配置
SERVER_URL="https://mcp.timquant.tech/mcp"
LOG_FILE="/tmp/mcp_jsonrpc_test_$(date +%Y%m%d_%H%M%S).log"

echo "=== JSON-RPC调用测试（Bash版本） ==="
echo "服务器URL: $SERVER_URL"
echo "日志文件: $LOG_FILE"
echo ""

# 日志函数
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1"
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

# 设置默认EXIT_CODE
export EXIT_CODE=0

# 通用curl函数，带超时和默认头
jsonrpc_call() {
    local method="$1"
    local id="$2"
    local params="$3"
    local desc="$4"
    
    log "执行 $desc: $method"
    
    local payload="{\"jsonrpc\":\"2.0\",\"method\":\"$method\""}
    if [ -n "$id" ]; then
        payload="$payload,\"id\":$id"
    fi
    if [ -n "$params" ]; then
        payload="$payload,\"params\":$params"
    fi
    payload="$payload}"
    
    echo "请求: $payload" >> "$LOG_FILE"
    
    response=$(curl -s --connect-timeout 5 --max-time 10 \
        -H "Content-Type: application/json" \
        -H "Accept: application/json" \
        -H "Origin: https://chatgpt.com" \
        -X POST \
        --data "$payload" \
        "$SERVER_URL")
    
    echo "响应: $response" >> "$LOG_FILE"
    
    if [ $? -ne 0 ]; then
        log "错误：$desc 请求失败或超时"
        EXIT_CODE=1
        return 1
    fi
    
    # 检查响应是否为有效的JSON
    if echo "$response" | jq . > /dev/null 2>&1; then
        log "成功：$desc 响应为有效的JSON"
        echo "$desc 响应：$response"
        return 0
    else
        log "错误：$desc 响应不是有效的JSON"
        echo "$desc 响应：$response"
        EXIT_CODE=1
        return 1
    fi
}

# 1. Initialize 请求
jsonrpc_call "initialize" "1" '{\"protocolVersion\":\"2025-03-26\",\"capabilities\":{},\"clientInfo\":{\"name\":\"bash-test\",\"version\":\"1.0\"}}' "Initialize"

echo ""

# 2. notifications/initialized 请求
jsonrpc_call "notifications/initialized" "" '{}' "Notifications Initialized"

echo ""

# 3. tools/list 请求
jsonrpc_call "tools/list" "2" '{}' "Tools List"

echo ""

# 4. resources/list 请求
jsonrpc_call "resources/list" "3" '{}' "Resources List"

echo ""

# 5. prompts/list 请求
jsonrpc_call "prompts/list" "4" '{}' "Prompts List"

echo ""

# 6. tools/call 请求（ping工具）
jsonrpc_call "tools/call" "5" '{\"name\":\"ping\",\"arguments\":{}}' "Tools Call (ping)"

echo ""
echo "=== 测试完成 ==="
echo "EXIT_CODE=$EXIT_CODE"
echo "EXIT_CODE=$EXIT_CODE" >> "$LOG_FILE"

exit $EXIT_CODE