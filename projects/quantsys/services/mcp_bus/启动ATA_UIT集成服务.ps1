# ATA与UI-TARS集成服务启动脚本

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "ATA与UI-TARS集成服务" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "功能: 当user_ai收到ATA消息时，自动发送UI-TARS提醒" -ForegroundColor Yellow
Write-Host ""
Write-Host "按 Ctrl+C 停止服务" -ForegroundColor Gray
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# 切换到脚本目录
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

# 获取项目根目录（上一级的上一级）
$repoRoot = (Get-Item $scriptDir).Parent.Parent.FullName

# 运行服务
python ata_uit_integration.py --repo-root $repoRoot --check-interval 30
