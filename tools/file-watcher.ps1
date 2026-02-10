# SCC File Watcher - 文件变更监控脚本
# 废弃 git hook，直接使用文件系统监控
# 当关键文件变更时自动重启 Docker 服务

param(
    [string]$ContainerName = "scc-server",
    [int]$DebounceSeconds = 2
)

$WatchPath = "C:\scc\scc-bd"
$LastEventTime = Get-Date

function Write-Status($msg, $color = "White") {
    Write-Host "[FileWatcher] $msg" -ForegroundColor $color
}

function Restart-SCCService {
    Write-Status "检测到关键文件变更，准备重启服务..." "Yellow"
    
    # 检查容器是否运行
    $container = docker ps --filter "name=$ContainerName" --format "{{.Names}}" 2>$null
    if ($container -eq $ContainerName) {
        Write-Status "重启容器 $ContainerName..." "Cyan"
        docker restart $ContainerName
        if ($LASTEXITCODE -eq 0) {
            Write-Status "✅ 服务重启成功" "Green"
        } else {
            Write-Status "❌ 服务重启失败" "Red"
        }
    } else {
        Write-Status "⚠️ 容器 $ContainerName 未运行" "Yellow"
    }
}

Write-Status "==================================" "Cyan"
Write-Status "SCC 文件监控启动" "Cyan"
Write-Status "监控路径: $WatchPath" "White"
Write-Status "防抖时间: ${DebounceSeconds}秒" "White"
Write-Status "==================================" "Cyan"
Write-Status "按 Ctrl+C 停止监控" "Gray"

# 创建文件系统监控器
$Watcher = New-Object System.IO.FileSystemWatcher
$Watcher.Path = $WatchPath
$Watcher.IncludeSubdirectories = $true
$Watcher.EnableRaisingEvents = $true

# 监控所有文件类型
$Watcher.Filter = "*.*"

# 定义事件处理
$Action = {
    $now = Get-Date
    $timeDiff = ($now - $script:LastEventTime).TotalSeconds
    
    # 防抖处理：避免短时间内多次触发
    if ($timeDiff -gt $script:DebounceSeconds) {
        $script:LastEventTime = $now
        $path = $Event.SourceEventArgs.FullPath
        $changeType = $Event.SourceEventArgs.ChangeType
        
        # 忽略日志文件和临时文件
        if ($path -match "\.(log|tmp|temp|swp|swo)$") { return }
        if ($path -match "node_modules") { return }
        if ($path -match "\.git") { return }
        
        Write-Status "检测到变更: $changeType - $(Split-Path $path -Leaf)" "Gray"
        
        # 检查是否为关键文件（.mjs, .js, .json 配置文件）
        if ($path -match "\.(mjs|js|json)$") {
            Restart-SCCService
        }
    }
}

# 注册事件
$handlers = @()
$handlers += Register-ObjectEvent -InputObject $Watcher -EventName "Changed" -Action $Action
$handlers += Register-ObjectEvent -InputObject $Watcher -EventName "Created" -Action $Action
$handlers += Register-ObjectEvent -InputObject $Watcher -EventName "Renamed" -Action $Action

Write-Status "✅ 文件监控已启动，等待变更..." "Green"

# 保持运行
try {
    while ($true) {
        Start-Sleep -Seconds 1
    }
} finally {
    Write-Status "`n停止文件监控..." "Yellow"
    $handlers | ForEach-Object { Unregister-Event -SubscriptionId $_.Id }
    $Watcher.Dispose()
    Write-Status "✅ 已清理资源" "Green"
}
