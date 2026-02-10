# JSON-RPC调用测试脚本（PowerShell版本）
# 用于测试MCP服务的JSON-RPC端点

# 配置
$SERVER_URL = "https://mcp.timquant.tech/mcp"
$LOG_FILE = "/tmp/mcp_jsonrpc_test_$(Get-Date -Format yyyyMMdd_HHmmss).log"
$EXIT_CODE = 0

Write-Host "=== JSON-RPC调用测试（PowerShell版本） ==="
Write-Host "服务器URL: $SERVER_URL"
Write-Host "日志文件: $LOG_FILE"
Write-Host ""

# 日志函数
function Log {
    param(
        [string]$Message
    )
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logEntry = "[$timestamp] $Message"
    Write-Host $logEntry
    Add-Content -Path $LOG_FILE -Value $logEntry
}

# 通用JSON-RPC调用函数，带超时和默认头
function Invoke-JsonRpcCall {
    param(
        [string]$Method,
        [string]$Id,
        [string]$Params,
        [string]$Desc
    )
    
    Log "执行 $Desc: $Method"
    
    # 构建请求 payload
    $payload = @{jsonrpc = "2.0"; method = $Method }
    if (-not [string]::IsNullOrEmpty($Id)) {
        $payload.id = $Id
    }
    if (-not [string]::IsNullOrEmpty($Params)) {
        $payload.params = ConvertFrom-Json $Params
    }
    
    $jsonPayload = $payload | ConvertTo-Json -Depth 10
    Log "请求: $jsonPayload"
    
    try {
        # 使用 Invoke-RestMethod，设置5秒连接超时，10秒总超时
        $response = Invoke-RestMethod -Uri $SERVER_URL -Method Post -Body $jsonPayload `
            -ContentType "application/json" `
            -Headers @{
                "Accept" = "application/json"
                "Origin" = "https://chatgpt.com"
            } `
            -TimeoutSec 10
        
        $responseJson = $response | ConvertTo-Json -Depth 10
        Log "响应: $responseJson"
        Write-Host "$Desc 响应：$responseJson"
        return $true
    } catch {
        $errorMsg = $_.Exception.Message
        Log "错误：$Desc 请求失败或超时 - $errorMsg"
        Write-Host "错误：$Desc 请求失败或超时 - $errorMsg"
        return $false
    }
}

# 1. Initialize 请求
if (Invoke-JsonRpcCall -Method "initialize" -Id "1" -Params '{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"powershell-test","version":"1.0"}}' -Desc "Initialize") {
    Log "Initialize 请求成功"
} else {
    $EXIT_CODE = 1
}

Write-Host ""

# 2. notifications/initialized 请求
if (Invoke-JsonRpcCall -Method "notifications/initialized" -Id "" -Params '{}' -Desc "Notifications Initialized") {
    Log "Notifications Initialized 请求成功"
} else {
    $EXIT_CODE = 1
}

Write-Host ""

# 3. tools/list 请求
if (Invoke-JsonRpcCall -Method "tools/list" -Id "2" -Params '{}' -Desc "Tools List") {
    Log "Tools List 请求成功"
} else {
    $EXIT_CODE = 1
}

Write-Host ""

# 4. resources/list 请求
if (Invoke-JsonRpcCall -Method "resources/list" -Id "3" -Params '{}' -Desc "Resources List") {
    Log "Resources List 请求成功"
} else {
    $EXIT_CODE = 1
}

Write-Host ""

# 5. prompts/list 请求
if (Invoke-JsonRpcCall -Method "prompts/list" -Id "4" -Params '{}' -Desc "Prompts List") {
    Log "Prompts List 请求成功"
} else {
    $EXIT_CODE = 1
}

Write-Host ""

# 6. tools/call 请求（ping工具）
if (Invoke-JsonRpcCall -Method "tools/call" -Id "5" -Params '{"name":"ping","arguments":{}}' -Desc "Tools Call (ping)") {
    Log "Tools Call (ping) 请求成功"
} else {
    $EXIT_CODE = 1
}

Write-Host ""
Write-Host "=== 测试完成 ==="
Write-Host "EXIT_CODE=$EXIT_CODE"
Add-Content -Path $LOG_FILE -Value "EXIT_CODE=$EXIT_CODE"

# 设置 PowerShell 退出码
exit $EXIT_CODE