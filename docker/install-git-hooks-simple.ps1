#!/usr/bin/env pwsh
# SCC Git Hooks 安装脚本 (简化版)

$ErrorActionPreference = "Stop"

Write-Host "==================================" -ForegroundColor Cyan
Write-Host "SCC Git Hooks 安装工具" -ForegroundColor Cyan
Write-Host "==================================" -ForegroundColor Cyan
Write-Host ""

$SCCRoot = "C:\scc"
$GitHooksDir = "$SCCRoot\.git\hooks"
$HookScript = "$SCCRoot\docker\auto-sync-hook.ps1"

# 检查 Git 仓库
if (-not (Test-Path "$SCCRoot\.git")) {
    Write-Host "未找到 Git 仓库: $SCCRoot\.git" -ForegroundColor Red
    exit 1
}

Write-Host "找到 Git 仓库: $SCCRoot" -ForegroundColor Green

# 确保 hooks 目录存在
if (-not (Test-Path $GitHooksDir)) {
    New-Item -ItemType Directory -Path $GitHooksDir -Force | Out-Null
    Write-Host "创建 hooks 目录: $GitHooksDir" -ForegroundColor Green
}

# 检查 hook 脚本是否存在
if (-not (Test-Path $HookScript)) {
    Write-Host "Hook 脚本不存在: $HookScript" -ForegroundColor Red
    exit 1
}

Write-Host "找到 Hook 脚本: $HookScript" -ForegroundColor Green

# 创建 post-commit hook
$postCommitContent = @"
#!/bin/sh
# SCC Docker Auto-Sync Hook - post-commit
powershell.exe -ExecutionPolicy Bypass -File "$HookScript" -HookType "post-commit"
exit `$?
"@

# 创建 post-push hook  
$postPushContent = @"
#!/bin/sh
# SCC Docker Auto-Sync Hook - post-push
powershell.exe -ExecutionPolicy Bypass -File "$HookScript" -HookType "post-push"
exit `$?
"@

# 安装 post-commit hook
$postCommitPath = "$GitHooksDir\post-commit"
$postCommitContent | Out-File -FilePath $postCommitPath -Encoding UTF8 -NoNewline
Write-Host "创建 post-commit hook: $postCommitPath" -ForegroundColor Green

# 安装 post-push hook
$postPushPath = "$GitHooksDir\post-push"
$postPushContent | Out-File -FilePath $postPushPath -Encoding UTF8 -NoNewline
Write-Host "创建 post-push hook: $postPushPath" -ForegroundColor Green

Write-Host ""
Write-Host "安装详情:" -ForegroundColor Cyan
Write-Host "   post-commit: $postCommitPath"
Write-Host "   post-push: $postPushPath"
Write-Host "   同步脚本: $HookScript"

Write-Host ""
Write-Host "==================================" -ForegroundColor Green
Write-Host "Git Hooks 安装成功!" -ForegroundColor Green
Write-Host "==================================" -ForegroundColor Green
Write-Host ""
Write-Host "现在每次 git commit 或 git push 后，" -ForegroundColor Cyan
Write-Host "Docker 容器会自动同步最新代码。" -ForegroundColor Cyan
Write-Host ""
Write-Host "如需卸载，运行:" -ForegroundColor Yellow
Write-Host "   Remove-Item '$postCommitPath'" -ForegroundColor Yellow
Write-Host "   Remove-Item '$postPushPath'" -ForegroundColor Yellow
