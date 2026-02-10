#!/usr/bin/env pwsh
# SCC Git 自动同步 Hook 脚本
# 安装: 将此脚本复制到 .git/hooks/post-commit 和 post-push
# 功能: 在 git commit 或 push 后自动同步到 Docker 容器

param(
    [string]$HookType = "post-commit"
)

$ErrorActionPreference = "Continue"
$ContainerName = "scc-server"
$SyncScript = "/usr/local/bin/scc-sync"

# 颜色定义
$Green = "`e[32m"
$Cyan = "`e[36m"
$Yellow = "`e[33m"
$Red = "`e[31m"
$Reset = "`e[0m"

function Write-Status($Message, $Color = $Cyan) {
    Write-Host "$Color$Message$Reset"
}

function Write-Success($Message) {
    Write-Host "$Green✅ $Message$Reset"
}

function Write-Warning($Message) {
    Write-Host "$Yellow⚠️  $Message$Reset"
}

function Write-Error($Message) {
    Write-Host "$Red❌ $Message$Reset"
}

Write-Status "=================================="
Write-Status "SCC Docker 自动同步 Hook"
Write-Status "触发类型: $HookType"
Write-Status "=================================="
Write-Status ""

# 检查 Docker 是否运行
$dockerInfo = docker ps --filter "name=$ContainerName" --format "{{.Names}}" 2>$null
if ($dockerInfo -ne $ContainerName) {
    Write-Error "Docker 容器 '$ContainerName' 未运行"
    Write-Warning "请先启动容器: docker-compose up -d"
    exit 1
}

Write-Success "Docker 容器 '$ContainerName' 运行正常"

# 获取当前 Git 信息
$commitHash = git rev-parse --short HEAD
$commitMsg = git log -1 --pretty=%B
$branch = git rev-parse --abbrev-ref HEAD

Write-Status ""
Write-Status "📋 提交信息:"
Write-Status "   分支: $branch"
Write-Status "   提交: $commitHash"
Write-Status "   消息: $commitMsg"

# 执行同步
Write-Status ""
Write-Status "🔄 正在同步到 Docker 容器..."

try {
    $syncOutput = docker exec $ContainerName $SyncScript 2>&1
    $exitCode = $LASTEXITCODE
    
    if ($exitCode -eq 0) {
        Write-Success "同步成功!"
        Write-Status ""
        Write-Status "输出:"
        $syncOutput | ForEach-Object { Write-Status "   $_" }
    } else {
        Write-Error "同步失败 (退出码: $exitCode)"
        Write-Status ""
        Write-Status "错误输出:"
        $syncOutput | ForEach-Object { Write-Error "   $_" }
        exit 1
    }
} catch {
    Write-Error "同步过程中发生错误: $_"
    exit 1
}

Write-Status ""
Write-Status "=================================="
Write-Success "自动同步完成"
Write-Status "=================================="
