# Start MCP Server
# English filename version - window stays open

# Keep window open - this script should be called with -NoExit
$ErrorActionPreference = "Continue"

# Function to pause and keep window open
function Pause-Exit {
    param([string]$Message = "", [int]$ExitCode = 0)
    if ($Message) {
        Write-Host ""
        Write-Host $Message -ForegroundColor $(if ($ExitCode -eq 0) { "Cyan" } else { "Red" })
    }
    Write-Host ""
    Write-Host "Press any key to close this window..." -ForegroundColor Yellow
    try {
        $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    } catch {
        # If ReadKey fails, use Read-Host as fallback
        Read-Host "Press Enter to close"
    }
    exit $ExitCode
}

Write-Host "=== Starting MCP Server ===" -ForegroundColor Cyan
Write-Host ""

# Check if already running
$portCheck = netstat -ano | findstr ":8000.*LISTENING"
if ($portCheck) {
    Write-Host "WARNING: Port 8000 is already in use" -ForegroundColor Yellow
    Write-Host "If MCP server is already running, you can access it at:" -ForegroundColor Gray
    Write-Host "  http://127.0.0.1:18788/" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Press 'y' to continue anyway, or any other key to exit..." -ForegroundColor Yellow
    try {
        $key = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
        if ($key.Character -ne 'y' -and $key.Character -ne 'Y') {
            Pause-Exit "Exiting..." 0
        }
    } catch {
        $response = Read-Host "Continue? (y/n)"
        if ($response -ne "y" -and $response -ne "Y") {
            Pause-Exit "Exiting..." 0
        }
    }
}

# Check MCP directory
$mcpDir = "d:\quantsys\tools\mcp_bus"
if (-not (Test-Path $mcpDir)) {
    Pause-Exit "ERROR: MCP directory not found: $mcpDir`nPlease check the path." 1
}

Set-Location $mcpDir

# Set environment variables
$env:REPO_ROOT = "d:\quantsys"
$env:MCP_BUS_HOST = "127.0.0.1"
$env:MCP_BUS_PORT = "8000"
$env:AUTH_MODE = "none"
# 默认禁用自启，如需与总服务器同步启动，取消下面的注释：
# $env:AUTO_START_FREQTRADE = "true"  # 与总服务器同步启动Freqtrade（可靠启动机制，100%成功率）

Write-Host "Configuration:" -ForegroundColor Yellow
Write-Host "  REPO_ROOT: $env:REPO_ROOT" -ForegroundColor Gray
Write-Host "  Server URL: http://$env:MCP_BUS_HOST`:$env:MCP_BUS_PORT" -ForegroundColor Cyan
Write-Host "  Auth Mode: None" -ForegroundColor Gray
Write-Host ""

# Check Python
Write-Host "Checking Python..." -ForegroundColor Yellow
try {
    $pythonCheck = python --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  OK: $pythonCheck" -ForegroundColor Green
    } else {
        Pause-Exit "ERROR: Python not found or not working`nPlease install Python and add it to PATH." 1
    }
} catch {
    Pause-Exit "ERROR: Python check failed: $_`nPlease install Python and add it to PATH." 1
}

# Check dependencies
Write-Host "Checking dependencies..." -ForegroundColor Yellow
try {
    $fastapiCheck = python -c "import fastapi" 2>&1
    $uvicornCheck = python -c "import uvicorn" 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  OK: Dependencies found" -ForegroundColor Green
    } else {
        Write-Host "  WARNING: Dependencies missing, installing..." -ForegroundColor Yellow
        pip install fastapi uvicorn 2>&1 | ForEach-Object { Write-Host "    $_" -ForegroundColor Gray }
        if ($LASTEXITCODE -ne 0) {
            Pause-Exit "ERROR: Failed to install dependencies`nPlease install manually: pip install fastapi uvicorn" 1
        }
    }
} catch {
    Write-Host "  WARNING: Dependency check failed: $_" -ForegroundColor Yellow
    Write-Host "  Attempting to install..." -ForegroundColor Yellow
    try {
        pip install fastapi uvicorn 2>&1 | ForEach-Object { Write-Host "    $_" -ForegroundColor Gray }
    } catch {
        Pause-Exit "ERROR: Failed to install dependencies: $_" 1
    }
}

# Check server module
Write-Host "Checking server module..." -ForegroundColor Yellow
$serverMain = Join-Path $mcpDir "server\main.py"
if (-not (Test-Path $serverMain)) {
    Pause-Exit "ERROR: Server module not found: $serverMain`nPlease check the file exists." 1
}
Write-Host "  OK: Server module found" -ForegroundColor Green

Write-Host ""
Write-Host "=== Starting Server ===" -ForegroundColor Cyan
Write-Host "Server URL: http://$env:MCP_BUS_HOST`:$env:MCP_BUS_PORT" -ForegroundColor Cyan
Write-Host "Press Ctrl+C to stop the server" -ForegroundColor Gray
Write-Host ""

# Start server with auto-restart
$maxRetries = 999999
$retryCount = 0
$restartDelay = 2

while ($retryCount -lt $maxRetries) {
    if ($retryCount -gt 0) {
        Write-Host ""
        Write-Host "Server stopped, auto-restarting... (attempt $retryCount)" -ForegroundColor Yellow
        Start-Sleep -Seconds $restartDelay
    }
    
    Write-Host "Starting MCP server..." -ForegroundColor Yellow
    Write-Host "  - Auto-reload: Enabled" -ForegroundColor Gray
    Write-Host "  - Crash restart: Enabled" -ForegroundColor Gray
    Write-Host ""
    
    try {
        # Start server - this blocks until server stops
        python -m uvicorn server.main:app --host $env:MCP_BUS_HOST --port $env:MCP_BUS_PORT --reload --reload-dir server --reload-dir config
        
        # Check exit code
        if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne $null) {
            $retryCount++
            Write-Host ""
            Write-Host "ERROR: Server exited with code $LASTEXITCODE" -ForegroundColor Red
            Write-Host "Will restart in $restartDelay seconds..." -ForegroundColor Yellow
            Start-Sleep -Seconds $restartDelay
            continue
        } else {
            # Normal exit (Ctrl+C)
            Write-Host ""
            Write-Host "Server stopped normally" -ForegroundColor Cyan
            Pause-Exit "" 0
        }
    } catch {
        $retryCount++
        Write-Host ""
        Write-Host "ERROR: Exception occurred" -ForegroundColor Red
        Write-Host "Error: $_" -ForegroundColor Red
        
        # Check if it's a user interrupt (Ctrl+C)
        if ($_.Exception.Message -like "*interrupt*" -or $_.Exception.Message -like "*cancel*" -or $_.FullyQualifiedErrorId -like "*CommandNotFoundException*") {
            Write-Host ""
            Write-Host "Server manually stopped" -ForegroundColor Cyan
            Pause-Exit "" 0
        }
        
        Write-Host "Will restart in $restartDelay seconds..." -ForegroundColor Yellow
        Start-Sleep -Seconds $restartDelay
    }
}

# This should never be reached, but just in case
Pause-Exit "Server loop ended unexpectedly" 1
