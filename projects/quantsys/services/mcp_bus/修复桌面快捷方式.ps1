# 修复并重新创建MCP服务器桌面快捷方式
# 确保所有快捷方式都能正常工作

$ErrorActionPreference = "Stop"

Write-Host "=== 修复MCP服务器桌面快捷方式 ===" -ForegroundColor Cyan
Write-Host ""

# 获取桌面路径
$desktopPath = [Environment]::GetFolderPath("Desktop")
$repoRoot = "d:\quantsys"

# 启动脚本路径
$startScript = Join-Path $repoRoot "快速启动本地MCP.ps1"
$backgroundScript = Join-Path $repoRoot "tools\mcp_bus\start_mcp_background_service.ps1"

# 检查脚本是否存在
if (-not (Test-Path $startScript)) {
    Write-Host "❌ 启动脚本不存在: $startScript" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $backgroundScript)) {
    Write-Host "⚠️  后台服务脚本不存在: $backgroundScript" -ForegroundColor Yellow
    Write-Host "   将只创建普通启动快捷方式" -ForegroundColor Gray
}

Write-Host "桌面路径: $desktopPath" -ForegroundColor Gray
Write-Host "启动脚本: $startScript" -ForegroundColor Gray
Write-Host ""

# 删除旧的快捷方式
Write-Host "清理旧的快捷方式..." -ForegroundColor Yellow
$oldShortcuts = Get-ChildItem $desktopPath -Filter "*MCP*" -ErrorAction SilentlyContinue
foreach ($old in $oldShortcuts) {
    try {
        Remove-Item $old.FullName -Force
        Write-Host "  删除: $($old.Name)" -ForegroundColor Gray
    } catch {
        Write-Host "  无法删除: $($old.Name) - $_" -ForegroundColor Yellow
    }
}

Write-Host ""

# 创建新的快捷方式
$shortcuts = @(
    @{
        Name = "启动MCP服务器.lnk"
        Script = $startScript
        Description = "启动MCP服务器（普通模式，窗口可见）"
        WindowStyle = "Normal"
    }
)

# 如果后台脚本存在，也创建后台服务快捷方式
if (Test-Path $backgroundScript) {
    $shortcuts += @{
        Name = "启动MCP服务器_后台服务.lnk"
        Script = $backgroundScript
        Description = "启动MCP服务器（后台服务模式，常驻后台）"
        WindowStyle = "Normal"
    }
}

$created = 0
$failed = 0

foreach ($item in $shortcuts) {
    $shortcutPath = Join-Path $desktopPath $item.Name
    
    try {
        # 创建快捷方式
        $WScriptShell = New-Object -ComObject WScript.Shell
        $Shortcut = $WScriptShell.CreateShortcut($shortcutPath)
        $Shortcut.TargetPath = "powershell.exe"
        
        # 构建参数
        $args = @(
            "-NoProfile"
            "-ExecutionPolicy"
            "Bypass"
            "-WindowStyle"
            $item.WindowStyle
            "-File"
            "`"$($item.Script)`""
        )
        $Shortcut.Arguments = $args -join " "
        
        $Shortcut.WorkingDirectory = $repoRoot
        $Shortcut.Description = $item.Description
        $Shortcut.IconLocation = "powershell.exe,0"
        $Shortcut.Save()
        
        Write-Host "✅ 创建成功: $($item.Name)" -ForegroundColor Green
        $created++
        
        # 验证快捷方式
        if (Test-Path $shortcutPath) {
            $verifyLink = $WScriptShell.CreateShortcut($shortcutPath)
            $scriptPath = $verifyLink.Arguments -replace '.*-File `"([^`"]+)`".*', '$1'
            if (Test-Path $scriptPath) {
                Write-Host "   ✅ 验证通过: 脚本路径正确" -ForegroundColor Green
            } else {
                Write-Host "   ⚠️  警告: 脚本路径可能不正确: $scriptPath" -ForegroundColor Yellow
            }
        }
    } catch {
        Write-Host "❌ 创建失败: $($item.Name) - $_" -ForegroundColor Red
        $failed++
    }
    Write-Host ""
}

Write-Host "=== 完成 ===" -ForegroundColor Cyan
Write-Host "  创建成功: $created 个" -ForegroundColor Green
Write-Host "  创建失败: $failed 个" -ForegroundColor $(if ($failed -eq 0) { 'Green' } else { 'Red' })
Write-Host ""
Write-Host "快捷方式位置: $desktopPath" -ForegroundColor Cyan
Write-Host ""

# 测试快捷方式
if ($created -gt 0) {
    Write-Host "是否测试快捷方式? (y/n)" -ForegroundColor Yellow
    $test = Read-Host
    
    if ($test -eq "y" -or $test -eq "Y") {
        Write-Host ""
        Write-Host "测试第一个快捷方式..." -ForegroundColor Yellow
        $firstShortcut = Join-Path $desktopPath $shortcuts[0].Name
        if (Test-Path $firstShortcut) {
            Write-Host "✅ 快捷方式文件存在" -ForegroundColor Green
            Write-Host "   双击桌面快捷方式即可启动服务器" -ForegroundColor Cyan
        }
    }
}

Write-Host ""
Write-Host "使用说明:" -ForegroundColor Yellow
Write-Host "  1. 双击桌面快捷方式启动服务器" -ForegroundColor White
Write-Host "  2. 等待服务器启动（约5-10秒）" -ForegroundColor White
Write-Host "  3. 访问: http://127.0.0.1:8000" -ForegroundColor White
Write-Host ""
