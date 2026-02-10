# MCP Server Background Service Startup Script
# For auto-start and background service

$ErrorActionPreference = "Stop"

# Configuration
$mcpDir = "d:\quantsys\tools\mcp_bus"
$logDir = "d:\quantsys\logs"
$logFile = "$logDir\mcp_server.log"
$pidFile = "$logDir\mcp_server.pid"

# Create log directory
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

# Switch to MCP directory
if (-not (Test-Path $mcpDir)) {
    Write-Error "MCP directory not found: $mcpDir"
    exit 1
}

Set-Location $mcpDir

# Set environment variables
$env:REPO_ROOT = "d:\quantsys"
$env:MCP_BUS_HOST = "127.0.0.1"
$env:MCP_BUS_PORT = "8000"
$env:AUTH_MODE = "none"
# 默认禁用自启，如需与总服务器同步启动，取消下面的注释：
# $env:AUTO_START_FREQTRADE = "true"  # 与总服务器同步启动Freqtrade（可靠启动机制，100%成功率）

# Cloud MCP forwarding configuration (if configured)
$upstreamUrl = "https://mcp.timquant.tech/mcp"
if ($env:UPSTREAM_MCP_URL) {
    $upstreamUrl = $env:UPSTREAM_MCP_URL
}
$env:UPSTREAM_MCP_URL = $upstreamUrl
if ($env:UPSTREAM_AUTH_TOKEN) {
    $env:UPSTREAM_AUTH_MODE = "bearer"
    $env:UPSTREAM_AUTH_VALUE = $env:UPSTREAM_AUTH_TOKEN
}

# Logging function
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

# Check if port is in use
function Test-Port {
    param([int]$Port)
    $connection = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    return $null -ne $connection
}

# Stop existing process
function Stop-ExistingServer {
    $existingPid = $null
    if (Test-Path $pidFile) {
        $existingPid = Get-Content $pidFile -ErrorAction SilentlyContinue
    }
    
    if ($existingPid) {
        try {
            $process = Get-Process -Id $existingPid -ErrorAction SilentlyContinue
            if ($process) {
                Write-Log "Stopping existing process (PID: $existingPid)" "WARN"
                Stop-Process -Id $existingPid -Force -ErrorAction SilentlyContinue
                Start-Sleep -Seconds 2
            }
        } catch {
            Write-Log "Unable to stop process: $_" "WARN"
        }
    }
    
    # Check port usage
    if (Test-Port -Port 8000) {
        Write-Log "Port 8000 is in use, attempting to release..." "WARN"
        $processes = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | 
                     Select-Object -ExpandProperty OwningProcess -Unique
        foreach ($pid in $processes) {
            try {
                Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
                Write-Log "Stopped process using port (PID: $pid)" "WARN"
            } catch {
                Write-Log "Unable to stop process $pid: $_" "WARN"
            }
        }
        Start-Sleep -Seconds 2
    }
}

# Start server
function Start-Server {
    Write-Log "=== Starting MCP Server ===" "INFO"
    Write-Log "Working directory: $mcpDir" "INFO"
    Write-Log "Server address: http://$($env:MCP_BUS_HOST):$($env:MCP_BUS_PORT)/mcp" "INFO"
    
    # Check dependencies
    try {
        python -c "import fastapi, uvicorn" 2>&1 | Out-Null
        Write-Log "Dependencies check passed" "INFO"
    } catch {
        Write-Log "Dependencies check failed, attempting to install..." "WARN"
        pip install -r requirements.txt 2>&1 | Out-File -Append $logFile
    }
    
    # Start server (background, no window)
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
    
    # Save PID
    $process.Id | Out-File -FilePath $pidFile -Encoding ASCII
    
    Write-Log "Server started (PID: $($process.Id))" "INFO"
    return $process
}

# Scheduled restart function
$lastRestartTime = Get-Date
$restartInterval = [TimeSpan]::FromHours(24)  # Restart every 24 hours

function Should-RestartScheduled {
    $now = Get-Date
    $timeSinceLastRestart = $now - $lastRestartTime
    if ($timeSinceLastRestart -ge $restartInterval) {
        Write-Log "Scheduled restart time reached (last restart was $([math]::Round($timeSinceLastRestart.TotalHours, 1)) hours ago)" "INFO"
        return $true
    }
    return $false
}

# Health check
function Test-ServerHealth {
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:18788/health" -TimeoutSec 5 -ErrorAction Stop
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

# Main loop
function Main-Loop {
    $maxRetries = 999999
    $retryCount = 0
    $restartDelay = 5
    $healthCheckInterval = 300  # Check every 5 minutes (300 seconds)
    $processCheckInterval = 30  # Check process every 30 seconds
    $lastHealthCheck = Get-Date
    $lastProcessCheck = Get-Date
    $process = $null
    
    while ($retryCount -lt $maxRetries) {
        try {
            if ($retryCount -gt 0) {
                Write-Log "Server stopped, waiting $restartDelay seconds before restart... (attempt $retryCount)" "WARN"
                Start-Sleep -Seconds $restartDelay
            }
            
            # Stop existing process
            Stop-ExistingServer
            
            # Start server
            $process = Start-Server
            
            # Wait for server to start
            Start-Sleep -Seconds 3
            
            # Verify server started correctly
            $maxWaitTime = 30
            $waited = 0
            while ($waited -lt $maxWaitTime) {
                $portOpen = Test-Port -Port 8000
                if ($portOpen) {
                    if (Test-ServerHealth) {
                        Write-Log "Server health check passed" "INFO"
                        break
                    }
                }
                Start-Sleep -Seconds 2
                $waited += 2
            }
            
            if ($waited -ge $maxWaitTime) {
                Write-Log "Server health check failed after startup, will restart" "WARN"
                if ($process) {
                    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
                }
                $retryCount++
                continue
            }
            
            # Update start time
            $script:lastRestartTime = Get-Date
            $lastHealthCheck = Get-Date
            $lastProcessCheck = Get-Date
            $retryCount = 0  # Reset retry count (successful start)
            
            # Monitoring loop - check every 30 seconds, health check every 5 minutes
            while ($true) {
                Start-Sleep -Seconds $processCheckInterval
                
                $now = Get-Date
                
                # Check if process is still running (every 30 seconds)
                $processRunning = $false
                if ($process) {
                    try {
                        $proc = Get-Process -Id $process.Id -ErrorAction Stop
                        $processRunning = $true
                    } catch {
                        $processRunning = $false
                    }
                }
                
                # Check if port is still open
                $portOpen = Test-Port -Port 8000
                
                # If process or port is down, restart immediately
                if (-not $processRunning -or -not $portOpen) {
                    Write-Log "Server is down (process: $processRunning, port: $portOpen), restarting immediately" "WARN"
                    if ($process) {
                        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
                    }
                    $retryCount++
                    break
                }
                
                # Periodic health check (every 5 minutes)
                if (($now - $lastHealthCheck).TotalSeconds -ge $healthCheckInterval) {
                    $lastHealthCheck = $now
                    Write-Log "Performing health check..." "INFO"
                    if (-not (Test-ServerHealth)) {
                        Write-Log "Health check failed, will restart server" "WARN"
                        if ($process) {
                            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
                        }
                        $retryCount++
                        break
                    } else {
                        Write-Log "Health check passed" "INFO"
                    }
                }
                
                # Check scheduled restart
                if (Should-RestartScheduled) {
                    Write-Log "Performing scheduled restart..." "INFO"
                    if ($process) {
                        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
                    }
                    $retryCount++
                    break
                }
            }
            
        } catch {
            $retryCount++
            Write-Log "Startup failed: $_" "ERROR"
            Write-Log "Will retry in $restartDelay seconds..." "WARN"
            if ($process) {
                Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
            }
            Start-Sleep -Seconds $restartDelay
        }
    }
}

# Execute main loop
Main-Loop
