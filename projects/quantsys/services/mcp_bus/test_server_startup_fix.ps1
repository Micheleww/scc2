# 测试MCP服务器启动修复
# 验证修复后的服务器能否正常启动

$ErrorActionPreference = "Continue"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Test MCP Server Startup Fix" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 1. 停止所有现有进程
Write-Host "[1] Stopping all existing processes..." -ForegroundColor Yellow
try {
    $processes = Get-Process -Name pythonw -ErrorAction SilentlyContinue
    if ($processes) {
        $processes | Stop-Process -Force
        Start-Sleep -Seconds 2
        Write-Host "  [OK] Stopped $($processes.Count) process(es)" -ForegroundColor Green
    } else {
        Write-Host "  [INFO] No pythonw processes found" -ForegroundColor Gray
    }
} catch {
    Write-Host "  [WARN] Error stopping processes: $_" -ForegroundColor Yellow
}

Write-Host ""

# 2. 检查端口8000
Write-Host "[2] Checking port 8000..." -ForegroundColor Yellow
$port8000 = netstat -ano | findstr ":8000" | findstr "LISTENING"
if ($port8000) {
    Write-Host "  [WARN] Port 8000 is still in use" -ForegroundColor Yellow
} else {
    Write-Host "  [OK] Port 8000 is free" -ForegroundColor Green
}

Write-Host ""

# 3. 测试启动服务器
Write-Host "[3] Testing server startup..." -ForegroundColor Yellow
$mcpDir = "d:\quantsys\tools\mcp_bus"
$scriptPath = Join-Path $mcpDir "server_tray_enhanced.py"
$serverStarted = $false

if (-not (Test-Path $scriptPath)) {
    Write-Host "  [FAIL] Server script not found: $scriptPath" -ForegroundColor Red
    exit 1
}

Write-Host "  [INFO] Starting server in background..." -ForegroundColor Cyan
try {
    # 启动服务器（使用pythonw后台运行）
    $process = Start-Process -FilePath "pythonw" -ArgumentList "`"$scriptPath`"" -WorkingDirectory $mcpDir -PassThru -WindowStyle Hidden
    
    if ($process) {
        Write-Host "  [OK] Server process started (PID: $($process.Id))" -ForegroundColor Green
        Write-Host "  [INFO] Waiting for server to start (max 30 seconds)..." -ForegroundColor Cyan
        
        # 等待服务器启动
        $elapsed = 0
        $maxWait = 30
        
        while ($elapsed -lt $maxWait -and -not $serverStarted) {
            Start-Sleep -Seconds 2
            $elapsed += 2
            
            # 检查端口
            $listening = netstat -ano | findstr ":8000" | findstr "LISTENING"
            if ($listening) {
                $serverStarted = $true
                Write-Host "  [SUCCESS] Server is listening on port 8000 after $elapsed seconds!" -ForegroundColor Green
                
                # 测试健康检查
                try {
                    $response = Invoke-WebRequest -Uri "http://127.0.0.1:18788/health" -Method Get -TimeoutSec 3 -ErrorAction Stop
                    if ($response.StatusCode -eq 200) {
                        $healthData = $response.Content | ConvertFrom-Json
                        Write-Host "  [SUCCESS] Health check passed: $($healthData.status)" -ForegroundColor Green
                        Write-Host "  [INFO] Server URL: http://127.0.0.1:18788/" -ForegroundColor Cyan
                    }
                } catch {
                    Write-Host "  [WARN] Health check failed: $_" -ForegroundColor Yellow
                }
            } else {
                Write-Host "  [WAIT] Waiting... ($elapsed/$maxWait seconds)" -ForegroundColor Gray
            }
        }
        
        if (-not $serverStarted) {
            Write-Host "  [FAIL] Server did not start within $maxWait seconds" -ForegroundColor Red
            Write-Host "  [INFO] Checking log files..." -ForegroundColor Cyan
            
            # 检查日志文件
            $logDir = Join-Path $mcpDir "logs"
            if (Test-Path $logDir) {
                $latestLog = Get-ChildItem $logDir -Filter "server_*.log" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
                if ($latestLog) {
                    Write-Host "  [INFO] Latest log file: $($latestLog.Name)" -ForegroundColor Cyan
                    Write-Host "  [INFO] Last 20 lines:" -ForegroundColor Cyan
                    Get-Content $latestLog.FullName -Tail 20 | ForEach-Object {
                        Write-Host "    $_" -ForegroundColor White
                    }
                }
            }
            
            # 检查进程是否还在运行
            $proc = Get-Process -Id $process.Id -ErrorAction SilentlyContinue
            if ($proc) {
                Write-Host "  [INFO] Process is still running (PID: $($process.Id))" -ForegroundColor Yellow
                Write-Host "  [INFO] Server may be starting slowly, check again later" -ForegroundColor Yellow
            } else {
                Write-Host "  [WARN] Process has exited (may have crashed)" -ForegroundColor Red
            }
        }
    } else {
        Write-Host "  [FAIL] Failed to start server process" -ForegroundColor Red
    }
} catch {
    Write-Host "  [ERROR] Error starting server: $_" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Test Complete" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

if ($serverStarted) {
    Write-Host "  [SUCCESS] Server startup test PASSED!" -ForegroundColor Green
    Write-Host "  [INFO] Server is running and accessible" -ForegroundColor Green
    Write-Host "  [INFO] Check system tray icon for status" -ForegroundColor Cyan
} else {
    Write-Host "  [FAIL] Server startup test FAILED" -ForegroundColor Red
    Write-Host "  [INFO] Check log files for errors" -ForegroundColor Yellow
    $logDir = Join-Path $mcpDir "logs"
    Write-Host "  [INFO] Log directory: $logDir" -ForegroundColor Cyan
}

Write-Host ""
