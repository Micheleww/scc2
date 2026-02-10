#!/usr/bin/env pwsh
# SCC Git Hooks 安装脚本
# 功能: 安装 post-commit 和 post-push hooks，实现自动同步到 Docker

$ErrorActionPreference = "Stop"

# 颜色定义
$Green = "`e[32m"
$Cyan = "`e[36m"
$Yellow = "`e[33m"
$Red = "`e[31m"
$Reset = "`e[0m"

function Write-Status($Message) {
    Write-Host "$Cyan$Message$Reset"
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
Write-Status "SCC Git Hooks 安装工具"
Write-Status "=================================="
Write-Status ""

# 获取 SCC 根目录
$SCCRoot = "C:\scc"
$GitHooksDir = "$SCCRoot\.git\hooks"
$HookScript = "$SCCRoot\docker\auto-sync-hook.ps1"

# 检查 Git 仓库
if (-not (Test-Path "$SCCRoot\.git")) {
    Write-Error "未找到 Git 仓库: $SCCRoot\.git"
    exit 1
}

Write-Success "找到 Git 仓库: $SCCRoot"

# 确保 hooks 目录存在
if (-not (Test-Path $GitHooksDir)) {
    New-Item -ItemType Directory -Path $GitHooksDir -Force | Out-Null
    Write-Success "创建 hooks 目录: $GitHooksDir"
}

# 检查 hook 脚本是否存在
if (-not (Test-Path $HookScript)) {
    Write-Error "Hook 脚本不存在: $HookScript"
    exit 1
}

Write-Success "找到 Hook 脚本: $HookScript"

# 创建 post-commit hook
$postCommitHook = @"
#!/bin/sh
# SCC Docker Auto-Sync Hook - post-commit
# 自动生成，请勿手动修改

# 使用 PowerShell 执行同步脚本
powershell.exe -ExecutionPolicy Bypass -File "$HookScript" -HookType "post-commit"
exit `$?
"@

# 创建 post-push hook
$postPushHook = @"
#!/bin/sh
# SCC Docker Auto-Sync Hook - post-push
# 自动生成，请勿手动修改

# 使用 PowerShell 执行同步脚本
powershell.exe -ExecutionPolicy Bypass -File "$HookScript" -HookType "post-push"
exit `$?
"@

# 安装 post-commit hook
$postCommitPath = "$GitHooksDir\post-commit"
try {
    $postCommitHook | Out-File -FilePath $postCommitPath -Encoding UTF8 -NoNewline
    Write-Success "创建 post-commit hook: $postCommitPath"
} catch {
    Write-Error "创建 post-commit hook 失败: $_"
    exit 1
}

# 安装 post-push hook
$postPushPath = "$GitHooksDir\post-push"
try {
    $postPushHook | Out-File -FilePath $postPushPath -Encoding UTF8 -NoNewline
    Write-Success "创建 post-push hook: $postPushPath"
} catch {
    Write-Error "创建 post-push hook 失败: $_"
    exit 1
}

Write-Status ""
Write-Status "📋 安装详情:"
Write-Status "   post-commit: $postCommitPath"
Write-Status "   post-push: $postPushPath"
Write-Status "   同步脚本: $HookScript"

Write-Status ""
Write-Status "🧪 测试 Hook..."

# 测试执行一次同步
& powershell.exe -ExecutionPolicy Bypass -File $HookScript -HookType "test"

if ($LASTEXITCODE -eq 0) {
    Write-Status ""
    Write-Status "=================================="
    Write-Success "Git Hooks 安装成功!"
    Write-Status "=================================="
    Write-Status ""
    Write-Status "现在每次 git commit 或 git push 后，"
    Write-Status "Docker 容器会自动同步最新代码。"
    Write-Status ""
    Write-Status "如需卸载，运行:"
    Write-Status "   Remove-Item '$postCommitPath'"
    Write-Status "   Remove-Item '$postPushPath'"
} else {
    Write-Status ""
    Write-Warning "Hook 安装完成，但测试同步失败"
    Write-Warning "请检查 Docker 容器是否运行: docker ps"
}
