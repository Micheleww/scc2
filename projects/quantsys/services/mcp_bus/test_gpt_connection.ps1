# GPT连接AWS MCP服务器测试脚本
# 用途：测试MCP服务器连接和认证

param(
    [string]$ServerUrl = "http://54.179.47.252:18080",
    [string]$Token = "",
    [switch]$GetToken = $false
)

$ErrorActionPreference = "Stop"

Write-Host "=== GPT连接AWS MCP服务器测试 ===" -ForegroundColor Cyan
Write-Host ""

# 如果请求获取token
if ($GetToken) {
    Write-Host "正在从服务器获取token..." -ForegroundColor Yellow
    $sshKey = "D:\quantsys\corefiles\aws_key.pem"
    $sshHost = "ubuntu@54.179.47.252"
    
    if (-not (Test-Path $sshKey)) {
        Write-Host "错误: SSH密钥文件不存在: $sshKey" -ForegroundColor Red
        exit 1
    }
    
    try {
        $token = ssh -i $sshKey -p 22 $sshHost "sudo systemctl show qcc-bus --property=Environment | grep -o 'MCP_BUS_TOKEN=[^ ]*' | cut -d= -f2" 2>&1
        
        if ($LASTEXITCODE -eq 0 -and $token) {
            Write-Host "Token获取成功!" -ForegroundColor Green
            Write-Host "Token: $token" -ForegroundColor Cyan
            Write-Host ""
            Write-Host "请复制上面的token值，在GPT配置中使用" -ForegroundColor Yellow
            $script:Token = $token.Trim()
        } else {
            Write-Host "警告: 无法获取token，可能服务未配置token或认证模式为none" -ForegroundColor Yellow
            Write-Host "输出: $token" -ForegroundColor Gray
        }
    } catch {
        Write-Host "错误: 无法连接到服务器获取token" -ForegroundColor Red
        Write-Host "错误信息: $_" -ForegroundColor Red
        exit 1
    }
}

# 如果没有提供token，提示用户
if (-not $Token) {
    Write-Host "未提供token，尝试从服务器获取..." -ForegroundColor Yellow
    $script:Token = ""
    # 尝试获取token
    $sshKey = "D:\quantsys\corefiles\aws_key.pem"
    $sshHost = "ubuntu@54.179.47.252"
    
    if (Test-Path $sshKey) {
        try {
            $token = ssh -i $sshKey -p 22 $sshHost "sudo systemctl show qcc-bus --property=Environment | grep -o 'MCP_BUS_TOKEN=[^ ]*' | cut -d= -f2" 2>&1
            if ($LASTEXITCODE -eq 0 -and $token) {
                $script:Token = $token.Trim()
                Write-Host "Token获取成功!" -ForegroundColor Green
            }
        } catch {
            Write-Host "无法自动获取token，将尝试无认证连接..." -ForegroundColor Yellow
        }
    }
}

# 测试1: 健康检查
Write-Host "测试1: 健康检查..." -ForegroundColor Yellow
try {
    $healthUrl = "$ServerUrl/health"
    $response = Invoke-RestMethod -Uri $healthUrl -Method Get -ErrorAction Stop
    Write-Host "✓ 健康检查通过" -ForegroundColor Green
    Write-Host "  状态: $($response.status)" -ForegroundColor Gray
    Write-Host "  版本: $($response.version)" -ForegroundColor Gray
} catch {
    Write-Host "✗ 健康检查失败" -ForegroundColor Red
    Write-Host "  错误: $_" -ForegroundColor Red
    exit 1
}

Write-Host ""

# 测试2: OAuth元数据端点
Write-Host "测试2: OAuth元数据端点..." -ForegroundColor Yellow
try {
    $oauthUrl = "$ServerUrl/.well-known/oauth-protected-resource"
    $response = Invoke-RestMethod -Uri $oauthUrl -Method Get -ErrorAction Stop
    Write-Host "✓ OAuth元数据端点正常" -ForegroundColor Green
    Write-Host "  资源: $($response.resource)" -ForegroundColor Gray
} catch {
    Write-Host "✗ OAuth元数据端点失败" -ForegroundColor Red
    Write-Host "  错误: $_" -ForegroundColor Red
}

Write-Host ""

# 测试3: Initialize请求
Write-Host "测试3: Initialize请求..." -ForegroundColor Yellow
try {
    $mcpUrl = "$ServerUrl/mcp"
    $headers = @{
        "Content-Type" = "application/json"
    }
    
    if ($Token) {
        $headers["Authorization"] = "Bearer $Token"
        Write-Host "  使用Bearer Token认证" -ForegroundColor Gray
    } else {
        Write-Host "  无认证模式" -ForegroundColor Gray
    }
    
    $body = @{
        jsonrpc = "2.0"
        id = "test-1"
        method = "initialize"
        params = @{
            protocolVersion = "2.0"
            clientInfo = @{
                name = "test-client"
                version = "1.0.0"
            }
        }
    } | ConvertTo-Json -Depth 10
    
    $response = Invoke-RestMethod -Uri $mcpUrl -Method Post -Headers $headers -Body $body -ErrorAction Stop
    Write-Host "✓ Initialize请求成功" -ForegroundColor Green
    Write-Host "  协议版本: $($response.result.protocolVersion)" -ForegroundColor Gray
    Write-Host "  服务器名称: $($response.result.serverInfo.name)" -ForegroundColor Gray
    Write-Host "  服务器版本: $($response.result.serverInfo.version)" -ForegroundColor Gray
} catch {
    Write-Host "✗ Initialize请求失败" -ForegroundColor Red
    $errorDetails = $_.Exception.Response
    if ($errorDetails) {
        Write-Host "  状态码: $($errorDetails.StatusCode.value__)" -ForegroundColor Red
        try {
            $reader = New-Object System.IO.StreamReader($errorDetails.GetResponseStream())
            $responseBody = $reader.ReadToEnd()
            Write-Host "  响应: $responseBody" -ForegroundColor Red
        } catch {
            Write-Host "  错误: $_" -ForegroundColor Red
        }
    } else {
        Write-Host "  错误: $_" -ForegroundColor Red
    }
    exit 1
}

Write-Host ""

# 测试4: 工具列表
Write-Host "测试4: 获取工具列表..." -ForegroundColor Yellow
try {
    $headers = @{
        "Content-Type" = "application/json"
    }
    
    if ($Token) {
        $headers["Authorization"] = "Bearer $Token"
    }
    
    $body = @{
        jsonrpc = "2.0"
        id = "test-2"
        method = "tools/list"
        params = @{}
    } | ConvertTo-Json -Depth 10
    
    $response = Invoke-RestMethod -Uri $mcpUrl -Method Post -Headers $headers -Body $body -ErrorAction Stop
    Write-Host "✓ 工具列表获取成功" -ForegroundColor Green
    $tools = $response.result.tools
    Write-Host "  可用工具数量: $($tools.Count)" -ForegroundColor Gray
    foreach ($tool in $tools) {
        Write-Host "    - $($tool.name): $($tool.description)" -ForegroundColor Gray
    }
} catch {
    Write-Host "✗ 工具列表获取失败" -ForegroundColor Red
    Write-Host "  错误: $_" -ForegroundColor Red
}

Write-Host ""

# 测试5: Ping工具调用
Write-Host "测试5: Ping工具调用..." -ForegroundColor Yellow
try {
    $headers = @{
        "Content-Type" = "application/json"
    }
    
    if ($Token) {
        $headers["Authorization"] = "Bearer $Token"
    }
    
    $body = @{
        jsonrpc = "2.0"
        id = "test-3"
        method = "tools/call"
        params = @{
            name = "ping"
            arguments = @{}
        }
    } | ConvertTo-Json -Depth 10
    
    $response = Invoke-RestMethod -Uri $mcpUrl -Method Post -Headers $headers -Body $body -ErrorAction Stop
    Write-Host "✓ Ping工具调用成功" -ForegroundColor Green
    $content = $response.result.content[0].text
    Write-Host "  响应: $content" -ForegroundColor Gray
} catch {
    Write-Host "✗ Ping工具调用失败" -ForegroundColor Red
    Write-Host "  错误: $_" -ForegroundColor Red
}

Write-Host ""
Write-Host "=== 测试完成 ===" -ForegroundColor Cyan
Write-Host ""

# 显示GPT配置信息
Write-Host "GPT配置信息:" -ForegroundColor Cyan
Write-Host "  MCP服务器URL: $ServerUrl/mcp" -ForegroundColor White
if ($Token) {
    Write-Host "  认证方式: Bearer Token" -ForegroundColor White
    Write-Host "  Token: $Token" -ForegroundColor White
} else {
    Write-Host "  认证方式: 无认证" -ForegroundColor White
}
Write-Host ""
