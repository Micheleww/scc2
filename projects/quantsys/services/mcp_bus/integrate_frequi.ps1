# Integrate FreqUI into MCP Server
# This script sets up FreqUI to work with the integrated MCP server

$ErrorActionPreference = "Stop"

Write-Host "=== Integrating FreqUI into MCP Server ===" -ForegroundColor Cyan
Write-Host ""

$repoRoot = "d:\quantsys"
$frequiDir = "$repoRoot\frequi-main"
$frequiDist = "$frequiDir\dist"

# Check if FreqUI directory exists
if (-not (Test-Path $frequiDir)) {
    Write-Host "ERROR: FreqUI directory not found: $frequiDir" -ForegroundColor Red
    exit 1
}

Write-Host "Checking FreqUI build..." -ForegroundColor Yellow

# Check if dist directory exists
if (Test-Path $frequiDist) {
    Write-Host "✅ FreqUI dist directory exists" -ForegroundColor Green
} else {
    Write-Host "⚠️  FreqUI dist directory not found" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Building FreqUI..." -ForegroundColor Yellow
    
    Set-Location $frequiDir
    
    # Check if node_modules exists
    if (-not (Test-Path "node_modules")) {
        Write-Host "Installing dependencies..." -ForegroundColor Yellow
        if (Get-Command pnpm -ErrorAction SilentlyContinue) {
            pnpm install
        } elseif (Get-Command npm -ErrorAction SilentlyContinue) {
            npm install
        } else {
            Write-Host "ERROR: pnpm or npm not found. Please install Node.js and pnpm/npm" -ForegroundColor Red
            exit 1
        }
    }
    
    # Build FreqUI
    Write-Host "Building FreqUI..." -ForegroundColor Yellow
    if (Get-Command pnpm -ErrorAction SilentlyContinue) {
        pnpm run build
    } else {
        npm run build
    }
    
    if (-not (Test-Path "dist\index.html")) {
        Write-Host "ERROR: FreqUI build failed" -ForegroundColor Red
        exit 1
    }
    
    Write-Host "✅ FreqUI built successfully" -ForegroundColor Green
}

Write-Host ""
Write-Host "Integration Complete!" -ForegroundColor Green
Write-Host ""
Write-Host "FreqUI will be available at:" -ForegroundColor Yellow
Write-Host "  http://127.0.0.1:18788/frequi" -ForegroundColor Cyan
Write-Host ""
Write-Host "Note: FreqUI needs Freqtrade API server running on port 8080" -ForegroundColor Gray
Write-Host "  Configure via environment variable: FREQTRADE_API_URL" -ForegroundColor Gray
Write-Host "  Default: http://127.0.0.1:18788/" -ForegroundColor Gray
