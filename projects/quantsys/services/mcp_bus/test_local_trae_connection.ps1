# 测试本地MCP服务器与TRAE连接

$ErrorActionPreference = "Stop"

Write-Host "=== 测试本地MCP服务器与TRAE连接 ===" -ForegroundColor Cyan
Write-Host ""

# 测试1: 健康检查
Write-Host "1. 测试健康检查..." -ForegroundColor Yellow
try {
    $response = Invoke-RestMethod -Uri "http://localhost:18788/health" -Method Get -ErrorAction Stop
    Write-Host "   ✅ 健康检查通过" -ForegroundColor Green
    Write-Host "   状态: $($response.status)" -ForegroundColor Gray
} catch {
    Write-Host "   ❌ 健康检查失败: $_" -ForegroundColor Red
    Write-Host "   提示: 请先启动本地MCP服务器 (运行 start_local_mcp.ps1)" -ForegroundColor Yellow
    exit 1
}

Write-Host ""

# 测试2: 工具列表
Write-Host "2. 测试工具列表..." -ForegroundColor Yellow
try {
    $body = @{
        jsonrpc = "2.0"
        id = "tools-list"
        method = "tools/list"
        params = @{}
    } | ConvertTo-Json -Depth 10
    
    $response = Invoke-RestMethod -Uri "http://localhost:18788/mcp" -Method Post -Headers @{"Content-Type"="application/json"} -Body $body -ErrorAction Stop
    
    if ($response.result -and $response.result.tools) {
        Write-Host "   ✅ 工具列表获取成功" -ForegroundColor Green
        Write-Host "   可用工具数量: $($response.result.tools.Count)" -ForegroundColor Gray
        foreach ($tool in $response.result.tools) {
            Write-Host "      - $($tool.name): $($tool.description)" -ForegroundColor Gray
        }
    } else {
        Write-Host "   ❌ 工具列表格式错误" -ForegroundColor Red
    }
} catch {
    Write-Host "   ❌ 工具列表获取失败: $_" -ForegroundColor Red
}

Write-Host ""

# 测试3: Ping工具
Write-Host "3. 测试Ping工具..." -ForegroundColor Yellow
try {
    $body = @{
        jsonrpc = "2.0"
        id = "ping-test"
        method = "tools/call"
        params = @{
            name = "ping"
            arguments = @{}
        }
    } | ConvertTo-Json -Depth 10
    
    $response = Invoke-RestMethod -Uri "http://localhost:18788/mcp" -Method Post -Headers @{"Content-Type"="application/json"} -Body $body -ErrorAction Stop
    
    if ($response.result -and $response.result.content) {
        Write-Host "   ✅ Ping工具调用成功" -ForegroundColor Green
        $text = $response.result.content[0].text
        Write-Host "   响应: $text" -ForegroundColor Gray
    } else {
        Write-Host "   ❌ Ping工具调用失败" -ForegroundColor Red
    }
} catch {
    Write-Host "   ❌ Ping工具调用失败: $_" -ForegroundColor Red
}

Write-Host ""

# 测试4: 收件箱工具
Write-Host "4. 测试收件箱工具..." -ForegroundColor Yellow
try {
    $today = Get-Date -Format "yyyy-MM-dd"
    
    # 测试inbox_tail
    $body = @{
        jsonrpc = "2.0"
        id = "inbox-tail-test"
        method = "tools/call"
        params = @{
            name = "inbox_tail"
            arguments = @{
                date = $today
                n = 10
            }
        }
    } | ConvertTo-Json -Depth 10
    
    $response = Invoke-RestMethod -Uri "http://localhost:18788/mcp" -Method Post -Headers @{"Content-Type"="application/json"} -Body $body -ErrorAction Stop
    
    if ($response.result) {
        Write-Host "   ✅ 收件箱读取成功" -ForegroundColor Green
        Write-Host "   日期: $today" -ForegroundColor Gray
    } else {
        Write-Host "   ⚠️ 收件箱可能为空或文件不存在" -ForegroundColor Yellow
    }
} catch {
    Write-Host "   ❌ 收件箱读取失败: $_" -ForegroundColor Red
}

Write-Host ""

# 测试5: 程序板工具
Write-Host "5. 测试程序板工具..." -ForegroundColor Yellow
try {
    $body = @{
        jsonrpc = "2.0"
        id = "board-get-test"
        method = "tools/call"
        params = @{
            name = "board_get"
            arguments = @{}
        }
    } | ConvertTo-Json -Depth 10
    
    $response = Invoke-RestMethod -Uri "http://localhost:18788/mcp" -Method Post -Headers @{"Content-Type"="application/json"} -Body $body -ErrorAction Stop
    
    if ($response.result) {
        Write-Host "   ✅ 程序板读取成功" -ForegroundColor Green
    } else {
        Write-Host "   ⚠️ 程序板可能为空" -ForegroundColor Yellow
    }
} catch {
    Write-Host "   ❌ 程序板读取失败: $_" -ForegroundColor Red
}

Write-Host ""
Write-Host "=== 测试完成 ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "TRAE配置信息:" -ForegroundColor Cyan
Write-Host "  配置文件: .trae/mcp.json" -ForegroundColor White
Write-Host "  服务器URL: http://localhost:18788/mcp" -ForegroundColor White
Write-Host "  认证方式: 无认证" -ForegroundColor White
Write-Host ""
