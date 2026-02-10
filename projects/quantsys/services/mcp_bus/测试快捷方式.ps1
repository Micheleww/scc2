# 测试桌面快捷方式是否能正常工作
# 记录详细证据

$ErrorActionPreference = "Continue"

$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "启动MCP服务器.lnk"

$report = @()
$report += "========================================"
$report += "桌面快捷方式测试报告"
$report += "========================================"
$report += ""
$report += "测试时间: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
$report += "快捷方式路径: $shortcutPath"
$report += ""

# 1. 检查快捷方式是否存在
$report += "1. 快捷方式文件检查"
if (Test-Path $shortcutPath) {
    $report += "   ✅ 快捷方式文件存在"
} else {
    $report += "   ❌ 快捷方式文件不存在"
    $report | Out-File "快捷方式测试报告.txt" -Encoding UTF8
    $report
    exit 1
}

# 2. 读取快捷方式信息
$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut($shortcutPath)

$report += ""
$report += "2. 快捷方式配置"
$report += "   目标程序: $($link.TargetPath)"
$report += "   参数: $($link.Arguments)"
$report += "   工作目录: $($link.WorkingDirectory)"
$report += "   描述: $($link.Description)"

# 3. 检查目标程序是否存在
$report += ""
$report += "3. 目标程序检查"
if (Test-Path $link.TargetPath) {
    $report += "   ✅ 目标程序存在: $($link.TargetPath)"
} else {
    $report += "   ❌ 目标程序不存在: $($link.TargetPath)"
}

# 4. 提取并检查脚本路径
$report += ""
$report += "4. 脚本路径检查"
$scriptPath = $null
if ($link.Arguments -match '-File `"([^`"]+)`"') {
    $scriptPath = $matches[1]
    $report += "   提取的脚本路径: $scriptPath"
} else {
    # 尝试其他方式提取
    if ($link.Arguments -match '`"([^`"]*快速启动[^`"]*)`"') {
        $scriptPath = $matches[1]
        $report += "   备用提取方式: $scriptPath"
    } else {
        $report += "   ❌ 无法提取脚本路径"
        $report += "   完整参数: $($link.Arguments)"
    }
}

if ($scriptPath) {
    if (Test-Path $scriptPath) {
        $report += "   ✅ 脚本文件存在"
    } else {
        $report += "   ❌ 脚本文件不存在"
    }
}

# 5. 检查工作目录
$report += ""
$report += "5. 工作目录检查"
if (Test-Path $link.WorkingDirectory) {
    $report += "   ✅ 工作目录存在: $($link.WorkingDirectory)"
} else {
    $report += "   ❌ 工作目录不存在: $($link.WorkingDirectory)"
}

# 6. 测试执行命令
$report += ""
$report += "6. 执行测试"
$report += "   构建的命令: $($link.TargetPath) $($link.Arguments)"

# 尝试直接执行
if ($scriptPath -and (Test-Path $scriptPath)) {
    $report += "   尝试直接执行脚本..."
    
    try {
        # 测试语法检查
        $syntaxErrors = $null
        $null = [System.Management.Automation.PSParser]::Tokenize((Get-Content $scriptPath -Raw), [ref]$syntaxErrors)
        
        if ($syntaxErrors.Count -eq 0) {
            $report += "   ✅ 脚本语法检查通过"
        } else {
            $report += "   ❌ 脚本语法错误:"
            $syntaxErrors | ForEach-Object {
                $report += "      $($_.Message)"
            }
        }
    } catch {
        $report += "   ⚠️  语法检查失败: $_"
    }
    
    # 尝试执行（但不等待）
    try {
        $processInfo = New-Object System.Diagnostics.ProcessStartInfo
        $processInfo.FileName = $link.TargetPath
        $processInfo.Arguments = $link.Arguments
        $processInfo.WorkingDirectory = $link.WorkingDirectory
        $processInfo.UseShellExecute = $false
        $processInfo.RedirectStandardOutput = $true
        $processInfo.RedirectStandardError = $true
        $processInfo.CreateNoWindow = $false
        
        $process = New-Object System.Diagnostics.Process
        $process.StartInfo = $processInfo
        
        $report += "   尝试启动进程..."
        $started = $process.Start()
        
        if ($started) {
            $report += "   ✅ 进程启动成功 (PID: $($process.Id))"
            Start-Sleep -Seconds 2
            
            if ($process.HasExited) {
                $report += "   ⚠️  进程已退出，退出码: $($process.ExitCode)"
                $stdout = $process.StandardOutput.ReadToEnd()
                $stderr = $process.StandardError.ReadToEnd()
                if ($stdout) {
                    $report += "   标准输出: $($stdout.Substring(0, [Math]::Min(500, $stdout.Length)))"
                }
                if ($stderr) {
                    $report += "   错误输出: $($stderr.Substring(0, [Math]::Min(500, $stderr.Length)))"
                }
            } else {
                $report += "   ✅ 进程仍在运行"
            }
        } else {
            $report += "   ❌ 进程启动失败"
        }
    } catch {
        $report += "   ❌ 执行异常: $_"
        $report += "   异常类型: $($_.Exception.GetType().FullName)"
        $report += "   堆栈跟踪: $($_.ScriptStackTrace)"
    }
} else {
    $report += "   ❌ 无法执行测试（脚本路径无效）"
}

# 7. 验证服务器是否启动
$report += ""
$report += "7. 服务器状态检查"
Start-Sleep -Seconds 5
try {
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -TimeoutSec 2 -ErrorAction Stop
    $report += "   ✅ 服务器正在运行（状态码: $($response.StatusCode)）"
} catch {
    $report += "   ❌ 服务器未运行或无法访问"
    $report += "   错误: $($_.Exception.Message)"
}

$report += ""
$report += "========================================"
$report += "测试完成"
$report += "========================================"

# 输出报告
$report | Out-File "快捷方式测试报告.txt" -Encoding UTF8

# 显示报告
$report | ForEach-Object { Write-Host $_ }
