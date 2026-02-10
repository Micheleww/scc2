# 快速诊断并启动MCP服务器
# 检查服务器状态，如果未运行则启动

$ErrorActionPreference = "Stop"

Write-Host "=== MCP服务器诊断与启动 ===" -ForegroundColor Cyan
Write-Host ""

# 检查端口是否被占用
Write-Host "1. 检查端口 8000..." -ForegroundColor Yellow
$portCheck = netstat -ano | findstr ":8000"
if ($portCheck) {
    Write-Host "   ✅ 端口 8000 已被占用" -ForegroundColor Green
    
    # 尝试访问健康检查端点
    Write-Host "2. 检查服务器健康状态..." -ForegroundColor Yellow
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -TimeoutSec 2 -ErrorAction Stop
        Write-Host "   ✅ 服务器正在运行并响应" -ForegroundColor Green
        Write-Host "   状态码: $($response.StatusCode)" -ForegroundColor Gray
        
        Write-Host ""
        Write-Host "✅ 服务器运行正常！" -ForegroundColor Green
        Write-Host ""
        Write-Host "访问地址:" -ForegroundColor Yellow
        Write-Host "  Web查看器: http://127.0.0.1:8000/viewer" -ForegroundColor Cyan
        Write-Host "  FreqUI: http://127.0.0.1:8000/frequi" -ForegroundColor Cyan
        Write-Host "  MCP服务: http://127.0.0.1:8000/mcp" -ForegroundColor Cyan
        Write-Host "  健康检查: http://127.0.0.1:8000/health" -ForegroundColor Cyan
        exit 0
    } catch {
        Write-Host "   ❌ 端口被占用但服务器不响应" -ForegroundColor Red
        Write-Host "   可能需要先停止占用端口的程序" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "查找占用端口的进程:" -ForegroundColor Yellow
        $processId = ($portCheck | Select-Object -First 1).Split()[-1]
        if ($processId) {
            $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
            if ($process) {
                Write-Host "   进程ID: $processId" -ForegroundColor Gray
                Write-Host "   进程名: $($process.ProcessName)" -ForegroundColor Gray
                Write-Host "   进程路径: $($process.Path)" -ForegroundColor Gray
            }
        }
        exit 1
    }
} else {
    Write-Host "   ❌ 端口 8000 未被占用，服务器未运行" -ForegroundColor Red
    Write-Host ""
    
    # 检查启动脚本
    Write-Host "2. 检查启动脚本..." -ForegroundColor Yellow
    $startScript = "d:\quantsys\快速启动本地MCP.ps1"
    if (-not (Test-Path $startScript)) {
        Write-Host "   ❌ 启动脚本不存在: $startScript" -ForegroundColor Red
        exit 1
    }
    Write-Host "   ✅ 启动脚本存在" -ForegroundColor Green
    Write-Host ""
    
    # 询问是否启动
    Write-Host "是否现在启动服务器? (y/n)" -ForegroundColor Yellow
    $answer = Read-Host
    
    if ($answer -eq "y" -or $answer -eq "Y") {
        Write-Host ""
        Write-Host "正在启动服务器..." -ForegroundColor Yellow
        Write-Host ""
        
        # 启动服务器（在新窗口）
        $psCommand = "Start-Process powershell.exe -ArgumentList '-NoProfile', '-ExecutionPolicy', 'Bypass', '-WindowStyle', 'Normal', '-File', '$startScript'"
        Invoke-Expression $psCommand
        
        Write-Host "✅ 服务器启动命令已执行" -ForegroundColor Green
        Write-Host ""
        Write-Host "等待服务器启动（10秒）..." -ForegroundColor Yellow
        Start-Sleep -Seconds 10
        
        # 再次检查
        Write-Host ""
        Write-Host "3. 验证服务器状态..." -ForegroundColor Yellow
        try {
            $response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -TimeoutSec 5 -ErrorAction Stop
            Write-Host "   ✅ 服务器已成功启动！" -ForegroundColor Green
            Write-Host ""
            Write-Host "访问地址:" -ForegroundColor Yellow
            Write-Host "  Web查看器: http://127.0.0.1:8000/viewer" -ForegroundColor Cyan
            Write-Host "  FreqUI: http://127.0.0.1:8000/frequi" -ForegroundColor Cyan
            Write-Host "  MCP服务: http://127.0.0.1:8000/mcp" -ForegroundColor Cyan
        } catch {
            Write-Host "   ⚠️  服务器可能仍在启动中，请稍候再试" -ForegroundColor Yellow
            Write-Host "   或检查新打开的PowerShell窗口查看错误信息" -ForegroundColor Gray
        }
    } else {
        Write-Host ""
        Write-Host "未启动服务器。" -ForegroundColor Yellow
        Write-Host "可以通过以下方式启动:" -ForegroundColor Gray
        Write-Host "  1. 双击桌面快捷方式: 启动MCP服务器.lnk" -ForegroundColor White
        Write-Host "  2. 运行命令: cd d:\quantsys; .\快速启动本地MCP.ps1" -ForegroundColor White
    }
}
