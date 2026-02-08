$ErrorActionPreference = "Stop"

$base = "http://127.0.0.1:18788"
$logPath = "C:\\scc\\docs\\WORKLOG.md"

function Get-Json($url) {
  (Invoke-WebRequest -UseBasicParsing -TimeoutSec 10 $url).Content | ConvertFrom-Json
}

$now = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$leader = Get-Json "$base/executor/leader"
$summary = Get-Json "$base/executor/debug/summary"
$status = Get-Json "$base/status"

$block = @()
$block += "## $now"
$block += ""
$block += "- gateway: $($status.gateway.port)"
$block += "- scc upstream: $($status.scc.upstream) ready=$($status.scc.healthReady) mcp=$($status.scc.mcpHealth)"
$block += "- opencode upstream: $($status.opencode.upstream) health=$($status.opencode.globalHealth)"
$block += ""
$block += "### failures summary (recent)"
$block += ""
$block += "byExecutor:"
($summary.byExecutor.PSObject.Properties | Sort-Object Name) | ForEach-Object { $block += "- $($_.Name): $($_.Value)" }
$block += ""
$block += "byReason:"
($summary.byReason.PSObject.Properties | Sort-Object Name) | ForEach-Object { $block += "- $($_.Name): $($_.Value)" }
$block += ""
$block += "### leader tail (last 20)"
$block += ""
$tail = @($leader.lines | Select-Object -Last 20)
$tail | ForEach-Object { $block += "- $_" }
$block += ""

if (-not (Test-Path $logPath)) {
  @("# WORKLOG", "", "自动写入：update_worklog.ps1", "") | Set-Content -Encoding UTF8 $logPath
}

Add-Content -Encoding UTF8 -Path $logPath -Value ($block -join "`n")
Write-Host "Updated: $logPath"
