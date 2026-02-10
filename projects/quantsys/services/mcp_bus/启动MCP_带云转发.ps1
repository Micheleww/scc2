# 启动本地MCP服务器（带云MCP转发）
# 用于GPT与TRAE文件通信

$ErrorActionPreference = "Stop"

Write-Host "=== 启动本地MCP服务器（带云转发） ===" -ForegroundColor Cyan
Write-Host ""

# 云MCP配置
$cloudMcpUrl = "https://mcp.timquant.tech/mcp"
$cloudMcpToken = ""  # 如果需要token，在这里填写

# 设置环境变量
$env:REPO_ROOT = "d:\quantsys"
$env:MCP_BUS_HOST = "127.0.0.1"
$env:MCP_BUS_PORT = "8000"
$env:AUTH_MODE = "none"
$env:UPSTREAM_MCP_URL = $cloudMcpUrl

if ($cloudMcpToken) {
    $env:UPSTREAM_MCP_TOKEN = $cloudMcpToken
}

Write-Host "环境配置:" -ForegroundColor Yellow
Write-Host "  REPO_ROOT: $env:REPO_ROOT" -ForegroundColor Gray
Write-Host "  本地MCP: http://$($env:MCP_BUS_HOST):$($env:MCP_BUS_PORT)/mcp" -ForegroundColor Cyan
Write-Host "  云MCP转发: $cloudMcpUrl" -ForegroundColor Cyan
Write-Host "  认证模式: 无认证" -ForegroundColor Gray
Write-Host ""

# 切换到MCP目录
$mcpDir = "d:\quantsys\tools\mcp_bus"
if (-not (Test-Path $mcpDir)) {
    Write-Host "❌ MCP目录不存在: $mcpDir" -ForegroundColor Red
    exit 1
}

Set-Location $mcpDir

# 检查依赖
Write-Host "检查依赖..." -ForegroundColor Yellow
try {
    python -c "import fastapi, uvicorn" 2>&1 | Out-Null
    Write-Host "✅ 依赖已安装" -ForegroundColor Green
} catch {
    Write-Host "⚠️  正在安装依赖..." -ForegroundColor Yellow
    pip install -r requirements.txt
}

Write-Host ""
Write-Host "启动MCP服务器..." -ForegroundColor Yellow
Write-Host "  - 本地服务: http://localhost:8000/mcp" -ForegroundColor Gray
Write-Host "  - 云MCP转发: $cloudMcpUrl" -ForegroundColor Gray
Write-Host "  - 自动重载: 已启用" -ForegroundColor Gray
Write-Host "  - 按 Ctrl+C 停止服务器" -ForegroundColor Gray
Write-Host ""

# 启动服务器
try {
    python -m uvicorn server.main:app --host $env:MCP_BUS_HOST --port $env:MCP_BUS_PORT --reload --reload-dir server --reload-dir config
} catch {
    Write-Host "❌ 启动失败: $_" -ForegroundColor Red
    exit 1
}
