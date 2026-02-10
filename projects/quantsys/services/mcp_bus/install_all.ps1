# 一键安装：开机自启动 + 桌面快捷方式 + 托盘程序
# 完整设置MCP服务器的启动方式

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  MCP服务器完整安装脚本" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 检查管理员权限
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Red
    Write-Host "  需要管理员权限" -ForegroundColor Red
    Write-Host "========================================" -ForegroundColor Red
    Write-Host ""
    Write-Host "开机自启动功能需要管理员权限" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "请使用以下方法之一：" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "方法1：使用批处理文件（推荐）" -ForegroundColor Green
    Write-Host "  1. 找到文件：以管理员身份安装.bat" -ForegroundColor White
    Write-Host "  2. 右键点击该文件" -ForegroundColor White
    Write-Host "  3. 选择'以管理员身份运行'" -ForegroundColor White
    Write-Host ""
    Write-Host "方法2：使用PowerShell" -ForegroundColor Green
    Write-Host "  1. 按 Win+X 键" -ForegroundColor White
    Write-Host "  2. 选择'Windows PowerShell (管理员)'" -ForegroundColor White
    Write-Host "  3. 执行: cd d:\quantsys\tools\mcp_bus" -ForegroundColor White
    Write-Host "  4. 执行: .\install_all.ps1" -ForegroundColor White
    Write-Host ""
    Write-Host "方法3：继续安装（仅创建快捷方式）" -ForegroundColor Green
    Write-Host "  桌面快捷方式可以正常创建（不需要管理员权限）" -ForegroundColor White
    Write-Host "  开机自启动功能将被跳过" -ForegroundColor Yellow
    Write-Host ""
    $continue = Read-Host "是否继续安装（仅创建快捷方式）？(Y/N)"
    if ($continue -ne "Y" -and $continue -ne "y") {
        Write-Host ""
        Write-Host "安装已取消" -ForegroundColor Yellow
        Write-Host "请使用管理员权限重新运行" -ForegroundColor Yellow
        exit 0
    }
}

Write-Host ""

# 1. 创建桌面快捷方式
Write-Host "[1/3] 创建桌面快捷方式..." -ForegroundColor Yellow
try {
    & "$PSScriptRoot\create_desktop_shortcut_tray.ps1"
    Write-Host "✅ 桌面快捷方式创建完成" -ForegroundColor Green
} catch {
    Write-Host "❌ 创建桌面快捷方式失败: $_" -ForegroundColor Red
}
Write-Host ""

# 2. 设置开机自启动
Write-Host "[2/3] 设置开机自启动..." -ForegroundColor Yellow
if ($isAdmin) {
    try {
        & "$PSScriptRoot\setup_autostart_tray.ps1"
        Write-Host "✅ 开机自启动设置完成" -ForegroundColor Green
    } catch {
        Write-Host "❌ 设置开机自启动失败: $_" -ForegroundColor Red
    }
} else {
    Write-Host "⚠️ 跳过开机自启动（需要管理员权限）" -ForegroundColor Yellow
    Write-Host "   请以管理员身份运行此脚本以启用开机自启动" -ForegroundColor Yellow
}
Write-Host ""

# 3. 检查依赖
Write-Host "[3/3] 检查依赖..." -ForegroundColor Yellow
try {
    python -c "import pystray, PIL" 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "安装 pystray 和 pillow..." -ForegroundColor Yellow
        pip install pystray pillow 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✅ 依赖安装成功" -ForegroundColor Green
        } else {
            Write-Host "⚠️ 依赖安装失败，托盘图标可能不可用" -ForegroundColor Yellow
            Write-Host "   可以手动安装: pip install pystray pillow" -ForegroundColor Yellow
        }
    } else {
        Write-Host "✅ 依赖已安装" -ForegroundColor Green
    }
} catch {
    Write-Host "⚠️ 依赖检查失败" -ForegroundColor Yellow
}
Write-Host ""

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  安装完成！" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "使用说明:" -ForegroundColor Yellow
Write-Host "1. 双击桌面快捷方式启动服务器" -ForegroundColor White
Write-Host "2. 服务器在后台运行，查看系统托盘图标" -ForegroundColor White
Write-Host "3. 右键点击托盘图标访问菜单" -ForegroundColor White
Write-Host "4. 服务器会在开机时自动启动（如果已设置）" -ForegroundColor White
Write-Host ""
Write-Host "托盘图标颜色说明:" -ForegroundColor Yellow
Write-Host "  🟢 绿色: 服务器正常运行，所有服务正常" -ForegroundColor Green
Write-Host "  🟡 黄色: 服务器运行但部分服务异常" -ForegroundColor Yellow
Write-Host "  🔴 红色: 服务器无法访问或严重错误" -ForegroundColor Red
Write-Host "  ⚪ 灰色: 服务器启动中或状态未知" -ForegroundColor Gray
Write-Host ""
Write-Host "管理命令:" -ForegroundColor Yellow
Write-Host "  查看自启动任务: Get-ScheduledTask -TaskName 'MCP Bus Server (Tray)'" -ForegroundColor Gray
Write-Host "  删除自启动任务: Unregister-ScheduledTask -TaskName 'MCP Bus Server (Tray)' -Confirm:`$false" -ForegroundColor Gray
Write-Host ""
