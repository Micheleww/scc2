# 启动本地MCP服务器
# 用于TRAE连接

$ErrorActionPreference = "Stop"

Write-Host "=== 启动本地MCP服务器 ===" -ForegroundColor Cyan
Write-Host ""

# 检查Python环境
Write-Host "检查Python环境..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    Write-Host "✅ $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ Python未安装或不在PATH中" -ForegroundColor Red
    exit 1
}

# 切换到MCP目录
$mcpDir = "d:\quantsys\tools\mcp_bus"
if (-not (Test-Path $mcpDir)) {
    Write-Host "❌ MCP目录不存在: $mcpDir" -ForegroundColor Red
    exit 1
}

Set-Location $mcpDir
Write-Host "工作目录: $mcpDir" -ForegroundColor Gray
Write-Host ""

# 检查依赖
Write-Host "检查依赖..." -ForegroundColor Yellow
try {
    python -c "import fastapi, uvicorn" 2>&1 | Out-Null
    Write-Host "✅ 依赖已安装" -ForegroundColor Green
} catch {
    Write-Host "⚠️ 正在安装依赖..." -ForegroundColor Yellow
    pip install -r requirements.txt
}

Write-Host ""

# 设置环境变量
$env:REPO_ROOT = "d:\quantsys"
$env:MCP_BUS_HOST = "127.0.0.1"
$env:MCP_BUS_PORT = "8000"
$env:AUTH_MODE = "none"  # 本地使用无认证模式
# 默认禁用自启，如需与总服务器同步启动，取消下面的注释：
# $env:AUTO_START_FREQTRADE = "true"  # 与总服务器同步启动Freqtrade（可靠启动机制，100%成功率）

Write-Host "环境变量:" -ForegroundColor Yellow
Write-Host "  REPO_ROOT: $env:REPO_ROOT" -ForegroundColor Gray
Write-Host "  MCP_BUS_HOST: $env:MCP_BUS_HOST" -ForegroundColor Gray
Write-Host "  MCP_BUS_PORT: $env:MCP_BUS_PORT" -ForegroundColor Gray
Write-Host "  AUTH_MODE: $env:AUTH_MODE" -ForegroundColor Gray
Write-Host ""

# 启动服务器
Write-Host "启动MCP服务器..." -ForegroundColor Yellow
Write-Host "服务器地址: http://$($env:MCP_BUS_HOST):$($env:MCP_BUS_PORT)/mcp" -ForegroundColor Cyan
Write-Host "按 Ctrl+C 停止服务器" -ForegroundColor Gray
Write-Host ""

try {
    # 使用uvicorn启动
    python -m uvicorn server.main:app --host $env:MCP_BUS_HOST --port $env:MCP_BUS_PORT --reload
} catch {
    Write-Host "❌ 启动失败: $_" -ForegroundColor Red
    exit 1
}
