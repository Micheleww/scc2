# 测试Freqtrade自动启动功能
# 验证桌面快捷键启动总服务器时，freqtrade服务器是否保持启动

$ErrorActionPreference = "Continue"

Write-Host "=== 测试Freqtrade自动启动功能 ===" -ForegroundColor Cyan
Write-Host ""

# 设置环境变量（模拟桌面快捷方式启动）
$env:REPO_ROOT = "d:\quantsys"
$env:MCP_BUS_HOST = "127.0.0.1"
$env:MCP_BUS_PORT = "8000"
$env:AUTH_MODE = "none"
$env:AUTO_START_FREQTRADE = "true"

Write-Host "环境变量配置:" -ForegroundColor Yellow
Write-Host "  REPO_ROOT: $env:REPO_ROOT" -ForegroundColor Gray
Write-Host "  MCP_BUS_HOST: $env:MCP_BUS_HOST" -ForegroundColor Gray
Write-Host "  MCP_BUS_PORT: $env:MCP_BUS_PORT" -ForegroundColor Gray
Write-Host "  AUTO_START_FREQTRADE: $env:AUTO_START_FREQTRADE" -ForegroundColor Green
Write-Host ""

# 检查MCP服务器是否运行
Write-Host "1. 检查MCP服务器状态..." -ForegroundColor Yellow
try {
    $mcpResponse = Invoke-WebRequest -Uri "http://127.0.0.1:18788/health" -TimeoutSec 5 -ErrorAction Stop
    if ($mcpResponse.StatusCode -eq 200) {
        Write-Host "  ✅ MCP服务器正在运行" -ForegroundColor Green
    } else {
        Write-Host "  ⚠️ MCP服务器响应异常: $($mcpResponse.StatusCode)" -ForegroundColor Yellow
    }
} catch {
    Write-Host "  ❌ MCP服务器未运行或无法访问" -ForegroundColor Red
    Write-Host "  错误: $_" -ForegroundColor Red
    Write-Host ""
    Write-Host "请先启动MCP服务器（使用桌面快捷方式）" -ForegroundColor Yellow
    exit 1
}

Write-Host ""

# 检查Freqtrade状态
Write-Host "2. 检查Freqtrade服务状态..." -ForegroundColor Yellow
try {
    $token = $null
    # 尝试从localStorage获取token（如果已登录）
    # 这里我们直接测试API，如果启用认证则需要token
    
    $headers = @{}
    if ($token) {
        $headers["Authorization"] = "Bearer $token"
    }
    
    $freqtradeStatusUrl = "http://127.0.0.1:18788/api/freqtrade/status"
    $freqtradeStatus = Invoke-RestMethod -Uri $freqtradeStatusUrl -Method Get -Headers $headers -TimeoutSec 5 -ErrorAction Stop
    
    Write-Host "  Freqtrade状态:" -ForegroundColor Gray
    Write-Host "    WebServer运行: $($freqtradeStatus.webserver.running)" -ForegroundColor $(if ($freqtradeStatus.webserver.running) { "Green" } else { "Red" })
    Write-Host "    Trade进程运行: $($freqtradeStatus.trade.running)" -ForegroundColor $(if ($freqtradeStatus.trade.running) { "Green" } else { "Yellow" })
    
    if ($freqtradeStatus.webserver.running) {
        Write-Host "    WebServer PID: $($freqtradeStatus.webserver.pid)" -ForegroundColor Gray
        Write-Host "    API URL: $($freqtradeStatus.webserver.api_url)" -ForegroundColor Gray
        if ($freqtradeStatus.webserver.uptime_seconds) {
            Write-Host "    运行时间: $([math]::Round($freqtradeStatus.webserver.uptime_seconds, 0))秒" -ForegroundColor Gray
        }
    }
    
    Write-Host ""
    
    # 测试Freqtrade API连接
    Write-Host "3. 测试Freqtrade API连接..." -ForegroundColor Yellow
    $freqtradeApiUrl = $freqtradeStatus.webserver.api_url
    if ($freqtradeApiUrl) {
        try {
            $pingUrl = "$freqtradeApiUrl/api/v1/ping"
            $pingResponse = Invoke-RestMethod -Uri $pingUrl -Method Get -TimeoutSec 5 -ErrorAction Stop
            Write-Host "  ✅ Freqtrade API连接正常" -ForegroundColor Green
            Write-Host "    响应: $($pingResponse | ConvertTo-Json -Compress)" -ForegroundColor Gray
        } catch {
            Write-Host "  ⚠️ Freqtrade API连接失败: $_" -ForegroundColor Yellow
            Write-Host "    这可能是因为Freqtrade WebServer刚启动，需要等待几秒钟" -ForegroundColor Gray
        }
    } else {
        Write-Host "  ⚠️ Freqtrade WebServer未运行，无法测试API" -ForegroundColor Yellow
    }
    
    Write-Host ""
    
    # 检查FreqUI是否可访问
    Write-Host "4. 检查FreqUI是否可访问..." -ForegroundColor Yellow
    try {
        $frequiUrl = "http://127.0.0.1:18788/frequi"
        $frequiResponse = Invoke-WebRequest -Uri $frequiUrl -TimeoutSec 5 -ErrorAction Stop
        if ($frequiResponse.StatusCode -eq 200) {
            Write-Host "  ✅ FreqUI可访问" -ForegroundColor Green
        } else {
            Write-Host "  ⚠️ FreqUI响应异常: $($frequiResponse.StatusCode)" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "  ⚠️ FreqUI无法访问: $_" -ForegroundColor Yellow
    }
    
    Write-Host ""
    
    # 总结
    Write-Host "=== 测试总结 ===" -ForegroundColor Cyan
    if ($freqtradeStatus.webserver.running) {
        Write-Host "✅ Freqtrade WebServer已自动启动并保持运行" -ForegroundColor Green
        Write-Host "   可以通过以下方式访问:" -ForegroundColor Gray
        Write-Host "   - FreqUI: http://127.0.0.1:18788/frequi" -ForegroundColor Cyan
        Write-Host "   - Freqtrade API: $freqtradeApiUrl" -ForegroundColor Cyan
    } else {
        Write-Host "❌ Freqtrade WebServer未运行" -ForegroundColor Red
        Write-Host "   可能的原因:" -ForegroundColor Yellow
        Write-Host "   1. AUTO_START_FREQTRADE环境变量未设置" -ForegroundColor Gray
        Write-Host "   2. Freqtrade命令未找到（需要安装freqtrade）" -ForegroundColor Gray
        Write-Host "   3. 配置文件路径错误" -ForegroundColor Gray
        Write-Host ""
        Write-Host "   可以手动启动:" -ForegroundColor Yellow
        Write-Host "   POST http://127.0.0.1:18788/api/freqtrade/webserver/start" -ForegroundColor Cyan
    }
    
} catch {
    Write-Host "  ❌ 无法获取Freqtrade状态" -ForegroundColor Red
    Write-Host "  错误: $_" -ForegroundColor Red
    Write-Host ""
    Write-Host "可能的原因:" -ForegroundColor Yellow
    Write-Host "  1. MCP服务器未启动" -ForegroundColor Gray
    Write-Host "  2. API端点需要认证（需要登录）" -ForegroundColor Gray
    Write-Host "  3. Freqtrade服务模块未正确加载" -ForegroundColor Gray
}

Write-Host ""
Write-Host "测试完成！" -ForegroundColor Cyan
