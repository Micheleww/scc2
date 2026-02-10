<#
.SYNOPSIS
    启动 OpenCode 执行器作为 SCC 系统的执行组件

.DESCRIPTION
    此脚本配置并启动 OpenCode CLI 作为 SCC 系统的执行器，
    支持任务执行、代码生成和验证功能。

.PARAMETER ConfigPath
    OpenCode 配置文件路径

.PARAMETER WorkingDirectory
    工作目录

.PARAMETER Test
    运行健康检查测试

.EXAMPLE
    .\start-opencode.ps1
    
    .\start-opencode.ps1 -Test
#>

param(
    [string]$ConfigPath = "C:\scc\scc-bd\config\opencode.config.json",
    [string]$WorkingDirectory = "C:\scc",
    [switch]$Test
)

$ErrorActionPreference = "Stop"

# 颜色输出
function Write-Info { param($Message) Write-Host "[INFO] $Message" -ForegroundColor Cyan }
function Write-Success { param($Message) Write-Host "[SUCCESS] $Message" -ForegroundColor Green }
function Write-Warning { param($Message) Write-Host "[WARNING] $Message" -ForegroundColor Yellow }
function Write-Error { param($Message) Write-Host "[ERROR] $Message" -ForegroundColor Red }

Write-Info "Starting OpenCode Executor for SCC System"
Write-Info "Config: $ConfigPath"
Write-Info "Working Directory: $WorkingDirectory"

# 检查 OpenCode 二进制文件
$OpenCodeBinary = "C:\scc\plugin\opencode\opencode.exe"
if (-not (Test-Path $OpenCodeBinary)) {
    # 尝试从源码构建
    Write-Warning "OpenCode binary not found at $OpenCodeBinary"
    Write-Info "Attempting to build from source..."
    
    $SourcePath = "C:\scc\plugin\opencode"
    if (Test-Path $SourcePath) {
        Push-Location $SourcePath
        try {
            # 检查 Go 环境
            $goVersion = go version 2>$null
            if ($LASTEXITCODE -eq 0) {
                Write-Info "Building OpenCode with Go..."
                go build -o opencode.exe
                if ($LASTEXITCODE -eq 0) {
                    Write-Success "OpenCode built successfully"
                } else {
                    throw "Failed to build OpenCode"
                }
            } else {
                throw "Go not found. Please install Go 1.24 or higher"
            }
        } finally {
            Pop-Location
        }
    } else {
        throw "OpenCode source not found at $SourcePath"
    }
} else {
    Write-Success "OpenCode binary found: $OpenCodeBinary"
}

# 检查配置文件
if (-not (Test-Path $ConfigPath)) {
    Write-Warning "Config file not found: $ConfigPath"
    Write-Info "Using default configuration"
} else {
    Write-Success "Config file found: $ConfigPath"
}

# 检查环境变量
Write-Info "Checking environment variables..."
$requiredEnvVars = @(
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GEMINI_API_KEY"
)

$missingVars = @()
foreach ($var in $requiredEnvVars) {
    $value = [Environment]::GetEnvironmentVariable($var)
    if ([string]::IsNullOrEmpty($value)) {
        $missingVars += $var
        Write-Warning "Environment variable not set: $var"
    } else {
        Write-Success "Environment variable set: $var"
    }
}

if ($missingVars.Count -gt 0) {
    Write-Warning "Some API keys are not configured. OpenCode may not function properly."
    Write-Info "Please set the following environment variables:"
    $missingVars | ForEach-Object { Write-Host "  - $_" }
}

# 创建工作目录
if (-not (Test-Path $WorkingDirectory)) {
    New-Item -ItemType Directory -Path $WorkingDirectory -Force | Out-Null
    Write-Success "Created working directory: $WorkingDirectory"
}

# 创建日志目录
$LogDir = "C:\scc\scc-bd\artifacts\executor_logs\opencode"
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
    Write-Success "Created log directory: $LogDir"
}

# 运行健康检查
if ($Test) {
    Write-Info "Running health check..."
    
    try {
        $testOutput = & $OpenCodeBinary -h 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Success "OpenCode CLI is working"
        } else {
            throw "OpenCode CLI health check failed"
        }
    } catch {
        Write-Error "Health check failed: $_"
        exit 1
    }
}

# 显示配置信息
Write-Info "OpenCode Executor Configuration:"
Write-Host "  Binary: $OpenCodeBinary"
Write-Host "  Config: $ConfigPath"
Write-Host "  Working Directory: $WorkingDirectory"
Write-Host "  Log Directory: $LogDir"

Write-Success "OpenCode Executor is ready"
Write-Info "To use OpenCode in SCC:"
Write-Host "  1. Set executor to 'opencode' in task configuration"
Write-Host "  2. Or use the default executor (automatically selected)"
Write-Host "  3. Run tasks through SCC gateway or orchestrator"

# 返回配置对象
return @{
    Binary = $OpenCodeBinary
    ConfigPath = $ConfigPath
    WorkingDirectory = $WorkingDirectory
    LogDirectory = $LogDir
    Status = "ready"
}
