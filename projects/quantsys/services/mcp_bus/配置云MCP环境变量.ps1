# 配置云MCP环境变量（永久设置）
# 用于后台服务和自启动服务

$ErrorActionPreference = "Stop"

Write-Host "=== 配置云MCP环境变量 ===" -ForegroundColor Cyan
Write-Host ""

# 云MCP配置
$cloudMcpUrl = "https://mcp.timquant.tech/mcp"
$cloudMcpToken = ""  # 如果需要token，在这里填写

Write-Host "配置信息:" -ForegroundColor Yellow
Write-Host "  云MCP地址: $cloudMcpUrl" -ForegroundColor Gray
if ($cloudMcpToken) {
    Write-Host "  云MCP Token: [已配置]" -ForegroundColor Gray
} else {
    Write-Host "  云MCP Token: [未配置，使用无认证模式]" -ForegroundColor Gray
}
Write-Host ""

# 设置用户环境变量（永久）
Write-Host "设置用户环境变量..." -ForegroundColor Yellow

try {
    [System.Environment]::SetEnvironmentVariable("UPSTREAM_MCP_URL", $cloudMcpUrl, [System.EnvironmentVariableTarget]::User)
    Write-Host "✅ UPSTREAM_MCP_URL 已设置" -ForegroundColor Green
    
    if ($cloudMcpToken) {
        [System.Environment]::SetEnvironmentVariable("UPSTREAM_AUTH_TOKEN", $cloudMcpToken, [System.EnvironmentVariableTarget]::User)
        Write-Host "✅ UPSTREAM_AUTH_TOKEN 已设置" -ForegroundColor Green
    }
    
    Write-Host ""
    Write-Host "✅ 环境变量配置完成！" -ForegroundColor Green
    Write-Host ""
    Write-Host "注意:" -ForegroundColor Yellow
    Write-Host "  环境变量已永久设置到用户环境变量中" -ForegroundColor Gray
    Write-Host "  新的进程将自动读取这些环境变量" -ForegroundColor Gray
    Write-Host "  如果已有进程在运行，需要重启后才能生效" -ForegroundColor Gray
    Write-Host ""
    
} catch {
    Write-Host "❌ 设置环境变量失败: $_" -ForegroundColor Red
    Write-Host ""
    Write-Host "请尝试以管理员身份运行此脚本" -ForegroundColor Yellow
    exit 1
}
