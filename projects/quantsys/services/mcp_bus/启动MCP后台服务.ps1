# MCP服务器后台服务启动脚本
# 用于开机自启动和常驻后台运行

$ErrorActionPreference = "Stop"

# 配置
$mcpDir = "d:\quantsys\tools\mcp_bus"
$logDir = "d:\quantsys\logs"
$logFile = "$logDir\mcp_server.log"
$pidFile = "$logDir\mcp_server.pid"

# 创建日志目录
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

# 切换到MCP目录
if (-not (Test-Path $mcpDir)) {
    Write-Error "MCP目录不存在: $mcpDir"
    exit 1
}

Set-Location $mcpDir

# 设置环境变量
$env:REPO_ROOT = "d:\quantsys"
$env:MCP_BUS_HOST = "127.0.0.1"
$env:MCP_BUS_PORT = "8000"
$env:AUTH_MODE = "none"

# 云MCP转发配置（如果配置了）
$upstreamUrl = "https://mcp.timquant.tech/mcp"
if ($env:UPSTREAM_MCP_URL) {
    $upstreamUrl = $env:UPSTREAM_MCP_URL
}
$env:UPSTREAM_MCP_URL = $upstreamUrl
if ($env:UPSTREAM_AUTH_TOKEN) {
    $env:UPSTREAM_AUTH_MODE = "bearer"
    $env:UPSTREAM_AUTH_VALUE = $env:UPSTREAM_AUTH_TOKEN
}

# 日志函数
function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logMessage = "[$timestamp] [$Level] $Message"
    Add-Content -Path $logFile -Value $logMessage
    if ($Level -eq "ERROR") {
        Write-Host $logMessage -ForegroundColor Red
    } elseif ($Level -eq "WARN") {
        Write-Host $logMessage -ForegroundColor Yellow
    } else {
        Write-Host $logMessage -ForegroundColor Green
    }
}

# 检查端口是否被占用
function Test-Port {
    param([int]$Port)
    $connection = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    return $null -ne $connection
}

# 停止现有进程
function Stop-ExistingServer {
    $existingPid = $null
    if (Test-Path $pidFile) {
        $existingPid = Get-Content $pidFile -ErrorAction SilentlyContinue
    }
    
    if ($existingPid) {
        try {
            $process = Get-Process -Id $existingPid -ErrorAction SilentlyContinue
            if ($process) {
                Write-Log "停止现有进程 (PID: $existingPid)" "WARN"
                Stop-Process -Id $existingPid -Force -ErrorAction SilentlyContinue
                Start-Sleep -Seconds 2
            }
        } catch {
            Write-Log "无法停止进程: $_" "WARN"
        }
    }
    
    # 检查端口占用
    if (Test-Port -Port 8000) {
        Write-Log "端口8000被占用，尝试释放..." "WARN"
        $processes = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | 
                     Select-Object -ExpandProperty OwningProcess -Unique
        foreach ($pid in $processes) {
            try {
                Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
                Write-Log "已停止占用端口的进程 (PID: $pid)" "WARN"
            } catch {
                Write-Log "无法停止进程 $pid: $_" "WARN"
            }
        }
        Start-Sleep -Seconds 2
    }
}

# 启动服务器
function Start-Server {
    Write-Log "=== 启动MCP服务器 ===" "INFO"
    Write-Log "工作目录: $mcpDir" "INFO"
    Write-Log "服务器地址: http://$($env:MCP_BUS_HOST):$($env:MCP_BUS_PORT)/mcp" "INFO"
    
    # 检查依赖
    try {
        python -c "import fastapi, uvicorn" 2>&1 | Out-Null
        Write-Log "依赖检查通过" "INFO"
    } catch {
        Write-Log "依赖检查失败，尝试安装..." "WARN"
        pip install -r requirements.txt 2>&1 | Out-File -Append $logFile
    }
    
    # 启动服务器（后台运行，不显示窗口）
    $process = Start-Process -FilePath "python" `
        -ArgumentList "-m", "uvicorn", "server.main:app", `
                      "--host", $env:MCP_BUS_HOST, `
                      "--port", $env:MCP_BUS_PORT, `
                      "--log-level", "info" `
        -WorkingDirectory $mcpDir `
        -WindowStyle Hidden `
        -PassThru `
        -RedirectStandardOutput "$logDir\mcp_stdout.log" `
        -RedirectStandardError "$logDir\mcp_stderr.log"
    
    # 保存PID
    $process.Id | Out-File -FilePath $pidFile -Encoding ASCII
    
    Write-Log "服务器已启动 (PID: $($process.Id))" "INFO"
    return $process
}

# 定时重启功能
$lastRestartTime = Get-Date
$restartInterval = [TimeSpan]::FromHours(24)  # 每24小时重启一次

function Should-RestartScheduled {
    $now = Get-Date
    $timeSinceLastRestart = $now - $lastRestartTime
    if ($timeSinceLastRestart -ge $restartInterval) {
        Write-Log "定时重启时间到达（距离上次重启已 $([math]::Round($timeSinceLastRestart.TotalHours, 1)) 小时）" "INFO"
        return $true
    }
    return $false
}

# 健康检查
function Test-ServerHealth {
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -TimeoutSec 5 -ErrorAction Stop
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

# 主循环
function Main-Loop {
    $maxRetries = 999999
    $retryCount = 0
    $restartDelay = 5
    $healthCheckInterval = 300  # 每5分钟检查一次健康状态
    $lastHealthCheck = Get-Date
    
    while ($retryCount -lt $maxRetries) {
        try {
            if ($retryCount -gt 0) {
                Write-Log "服务器已停止，等待 $restartDelay 秒后重启... (第 $retryCount 次)" "WARN"
                Start-Sleep -Seconds $restartDelay
            }
            
            # 停止现有进程
            Stop-ExistingServer
            
            # 启动服务器
            $process = Start-Server
            
            # 等待进程启动
            Start-Sleep -Seconds 3
            
            # 验证服务器是否正常启动
            $maxWaitTime = 30
            $waited = 0
            while ($waited -lt $maxWaitTime) {
                $portOpen = Test-Port -Port 8000
                if ($portOpen) {
                    if (Test-ServerHealth) {
                        Write-Log "服务器健康检查通过" "INFO"
                        break
                    }
                }
                Start-Sleep -Seconds 2
                $waited += 2
            }
            
            if ($waited -ge $maxWaitTime) {
                Write-Log "服务器启动后健康检查失败，将重启" "WARN"
                Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
                $retryCount++
                continue
            }
            
            # 更新启动时间
            $script:lastRestartTime = Get-Date
            $lastHealthCheck = Get-Date
            $retryCount = 0  # 重置重试计数（因为启动成功）
            
            # 监控循环
            while ($true) {
                Start-Sleep -Seconds 30
                
                # 检查进程是否还在运行
                try {
                    $proc = Get-Process -Id $process.Id -ErrorAction Stop
                } catch {
                    Write-Log "服务器进程已退出，将重启" "WARN"
                    $retryCount++
                    break
                }
                
                # 定期健康检查
                $now = Get-Date
                if (($now - $lastHealthCheck).TotalSeconds -ge $healthCheckInterval) {
                    $lastHealthCheck = $now
                    if (-not (Test-ServerHealth)) {
                        Write-Log "健康检查失败，将重启服务器" "WARN"
                        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
                        $retryCount++
                        break
                    }
                }
                
                # 检查定时重启
                if (Should-RestartScheduled) {
                    Write-Log "执行定时重启..." "INFO"
                    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
                    $retryCount++
                    break
                }
            }
            
        } catch {
            $retryCount++
            Write-Log "启动失败: $_" "ERROR"
            Write-Log "将在 $restartDelay 秒后重试..." "WARN"
            Start-Sleep -Seconds $restartDelay
        }
    }
}

# 执行主循环
Main-Loop
