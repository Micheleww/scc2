# 验证桌面快捷方式是否正常工作
# 检查快捷方式配置和脚本路径

$ErrorActionPreference = "Stop"

Write-Host "=== 验证桌面快捷方式 ===" -ForegroundColor Cyan
Write-Host ""

$desktop = [Environment]::GetFolderPath("Desktop")
$repoRoot = "d:\quantsys"

$shortcuts = @(
    @{
        Name = "启动MCP服务器.lnk"
        Script = Join-Path $repoRoot "快速启动本地MCP.ps1"
    },
    @{
        Name = "启动MCP服务器_后台服务.lnk"
        Script = Join-Path $repoRoot "tools\mcp_bus\start_mcp_background_service.ps1"
    }
)

$allValid = $true

foreach ($item in $shortcuts) {
    $shortcutPath = Join-Path $desktop $item.Name
    
    Write-Host "检查: $($item.Name)" -ForegroundColor Yellow
    
    if (-not (Test-Path $shortcutPath)) {
        Write-Host "  ❌ 快捷方式不存在" -ForegroundColor Red
        $allValid = $false
        continue
    }
    
    try {
        $shell = New-Object -ComObject WScript.Shell
        $link = $shell.CreateShortcut($shortcutPath)
        
        Write-Host "  目标: $($link.TargetPath)" -ForegroundColor Gray
        Write-Host "  参数: $($link.Arguments)" -ForegroundColor Gray
        Write-Host "  工作目录: $($link.WorkingDirectory)" -ForegroundColor Gray
        
        # 提取脚本路径
        $scriptMatch = $link.Arguments -match '-File `"([^`"]+)`"'
        if ($scriptMatch) {
            $extractedPath = $matches[1]
            Write-Host "  提取的脚本路径: $extractedPath" -ForegroundColor Gray
            
            if (Test-Path $extractedPath) {
                Write-Host "  ✅ 脚本路径有效" -ForegroundColor Green
            } else {
                Write-Host "  ❌ 脚本路径无效: $extractedPath" -ForegroundColor Red
                $allValid = $false
                
                # 尝试修复
                Write-Host "  尝试修复..." -ForegroundColor Yellow
                $link.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Normal -File `"$($item.Script)`""
                $link.WorkingDirectory = $repoRoot
                $link.Save()
                
                if (Test-Path $item.Script) {
                    Write-Host "  ✅ 已修复" -ForegroundColor Green
                } else {
                    Write-Host "  ❌ 修复失败: 脚本不存在" -ForegroundColor Red
                }
            }
        } else {
            Write-Host "  ❌ 无法解析脚本路径" -ForegroundColor Red
            $allValid = $false
            
            # 尝试修复
            Write-Host "  尝试修复..." -ForegroundColor Yellow
            $link.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Normal -File `"$($item.Script)`""
            $link.WorkingDirectory = $repoRoot
            $link.Save()
            Write-Host "  ✅ 已修复" -ForegroundColor Green
        }
        
        # 检查工作目录
        if ($link.WorkingDirectory -ne $repoRoot) {
            Write-Host "  ⚠️  工作目录不正确，已修复" -ForegroundColor Yellow
            $link.WorkingDirectory = $repoRoot
            $link.Save()
        }
        
    } catch {
        Write-Host "  ❌ 读取快捷方式失败: $_" -ForegroundColor Red
        $allValid = $false
    }
    
    Write-Host ""
}

Write-Host "=== 验证结果 ===" -ForegroundColor Cyan
if ($allValid) {
    Write-Host "✅ 所有快捷方式验证通过！" -ForegroundColor Green
    Write-Host ""
    Write-Host "现在可以双击桌面快捷方式启动服务器了" -ForegroundColor Yellow
} else {
    Write-Host "⚠️  部分快捷方式存在问题，已尝试修复" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "请重新运行此脚本验证" -ForegroundColor Gray
}
