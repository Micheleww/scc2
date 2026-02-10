# Start MCP Server with Debug Mode
# Keeps window open and shows detailed error messages

$ErrorActionPreference = "Continue"

# Set console encoding to UTF-8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "=== Starting MCP Server (Debug Mode) ===" -ForegroundColor Cyan
Write-Host ""

# Function to pause on error
function Pause-OnError {
    param([string]$Message)
    Write-Host ""
    Write-Host "ERROR: $Message" -ForegroundColor Red
    Write-Host ""
    Write-Host "Press any key to exit..." -ForegroundColor Yellow
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    exit 1
}

# Check Python
Write-Host "1. Checking Python..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "   ✅ Python found: $pythonVersion" -ForegroundColor Green
    } else {
        Pause-OnError "Python not found or not in PATH"
    }
} catch {
    Pause-OnError "Python check failed: $_"
}

# Check MCP directory
Write-Host "2. Checking MCP directory..." -ForegroundColor Yellow
$mcpDir = "d:\quantsys\tools\mcp_bus"
if (Test-Path $mcpDir) {
    Write-Host "   ✅ Directory exists: $mcpDir" -ForegroundColor Green
    Set-Location $mcpDir
} else {
    Pause-OnError "MCP directory not found: $mcpDir"
}

# Check server module
Write-Host "3. Checking server module..." -ForegroundColor Yellow
$serverMain = Join-Path $mcpDir "server\main.py"
if (Test-Path $serverMain) {
    Write-Host "   ✅ Server module exists" -ForegroundColor Green
} else {
    Pause-OnError "Server module not found: $serverMain"
}

# Check dependencies
Write-Host "4. Checking dependencies..." -ForegroundColor Yellow
try {
    $fastapiCheck = python -c "import fastapi" 2>&1
    $uvicornCheck = python -c "import uvicorn" 2>&1
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "   ✅ Dependencies OK" -ForegroundColor Green
    } else {
        Write-Host "   ⚠️  Dependencies missing, installing..." -ForegroundColor Yellow
        pip install fastapi uvicorn 2>&1 | ForEach-Object { Write-Host "   $_" -ForegroundColor Gray }
    }
} catch {
    Write-Host "   ⚠️  Dependency check failed: $_" -ForegroundColor Yellow
    Write-Host "   Attempting to install..." -ForegroundColor Yellow
    pip install fastapi uvicorn 2>&1 | ForEach-Object { Write-Host "   $_" -ForegroundColor Gray }
}

# Set environment variables
Write-Host "5. Setting environment variables..." -ForegroundColor Yellow
$env:REPO_ROOT = "d:\quantsys"
$env:MCP_BUS_HOST = "127.0.0.1"
$env:MCP_BUS_PORT = "8000"
$env:AUTH_MODE = "none"
Write-Host "   ✅ Environment variables set" -ForegroundColor Green

Write-Host ""
Write-Host "=== Starting Server ===" -ForegroundColor Cyan
Write-Host "Server URL: http://$env:MCP_BUS_HOST`:$env:MCP_BUS_PORT" -ForegroundColor Cyan
Write-Host "Press Ctrl+C to stop" -ForegroundColor Gray
Write-Host ""

# Start server
try {
    python -m uvicorn server.main:app --host $env:MCP_BUS_HOST --port $env:MCP_BUS_PORT --reload --reload-dir server --reload-dir config
} catch {
    Write-Host ""
    Write-Host "ERROR: Server failed to start" -ForegroundColor Red
    Write-Host "Error: $_" -ForegroundColor Red
    Write-Host "Exception: $($_.Exception.GetType().FullName)" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Press any key to exit..." -ForegroundColor Yellow
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    exit 1
}

# If we get here, server stopped
Write-Host ""
Write-Host "Server stopped" -ForegroundColor Cyan
Write-Host "Press any key to exit..." -ForegroundColor Yellow
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
