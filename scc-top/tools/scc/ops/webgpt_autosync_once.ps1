param(
  [string]$BaseUrl = "http://127.0.0.1:18788",
  [int]$BackfillLimit = 200,
  [int]$ScrollSteps = 30,
  [int]$SidebarScrollSteps = 120,
  [int]$ScrollDelayMs = 240,
  [int]$PerConvWaitMs = 18000,
  [int]$ExportAllLimit = 2000,
  # Use 1/0 so `-File` invocation stays stable (argv after -File are strings).
  [int]$CaptureMemory = 1
)

$ErrorActionPreference = "Stop"

function PostJson($url, $obj) {
  $body = ($obj | ConvertTo-Json -Depth 20)
  return Invoke-RestMethod -Method Post -Uri $url -ContentType "application/json" -Body $body
}

function GetJson($url) {
  return Invoke-RestMethod -Method Get -Uri $url
}

function Wait-ServerReady([int]$Seconds = 60) {
  Write-Host "[webgpt_autosync_once] waiting for server ready..."
  $deadline = (Get-Date).AddSeconds([Math]::Max(5, $Seconds))
  while ((Get-Date) -lt $deadline) {
    try {
      $r = GetJson "$BaseUrl/health/ready"
      if ($r.status -eq "ready") { return }
    } catch {}
    Start-Sleep -Milliseconds 500
  }
  throw "server_not_ready: $BaseUrl"
}

function Ensure-BrowserRunning() {
  $st = GetJson "$BaseUrl/scc/browser/status"
  if (-not $st.running) {
    Write-Host "[webgpt_autosync_once] starting SCC browser (keeps login in persist:scc-chatgpt)..."
    PostJson "$BaseUrl/scc/browser/start" @{ url = "https://chatgpt.com/"; home_url = "https://chatgpt.com/" } | Out-Null
    Start-Sleep -Seconds 2
  } else {
    Write-Host "[webgpt_autosync_once] browser already running; will NOT restart (to keep login stable)."
  }
}

function Enqueue-Command([string]$Cmd, [hashtable]$CmdArgs = @{}) {
  $id = (Get-Date).ToUniversalTime().ToString("yyyyMMdd_HHmmss") + "_" + $Cmd + "_" + ([guid]::NewGuid().ToString("N").Substring(0, 8))
  $r = PostJson "$BaseUrl/scc/browser/command" @{ id = $id; cmd = $Cmd; args = $CmdArgs }
  return @{ id = $r.id; queue_path = $r.queue_path }
}

function Get-RepoRootFromHere() {
  # This script lives in <repo>\tools\scc\ops\.
  $here = Split-Path -Parent $PSCommandPath
  return (Resolve-Path (Join-Path $here "..\\..\\..")).Path
}

function Wait-ForAck([string]$CmdId, [int]$TimeoutSeconds = 1800) {
  $repo = Get-RepoRootFromHere
  $ack = Join-Path $repo "artifacts\\scc_state\\browser_commands_ack.jsonl"
  $deadline = (Get-Date).AddSeconds([Math]::Max(5, $TimeoutSeconds))
  while ((Get-Date) -lt $deadline) {
    if (Test-Path $ack) {
      try {
        $lines = Get-Content $ack -Tail 4000
        foreach ($ln in [array]::Reverse($lines)) {
          if (-not $ln) { continue }
          $obj = $ln | ConvertFrom-Json -ErrorAction Stop
          if ($obj.id -eq $CmdId) { return $obj }
        }
      } catch {}
    }
    Start-Sleep -Milliseconds 600
  }
  return $null
}

Wait-ServerReady -Seconds 90
Ensure-BrowserRunning

Write-Host "[webgpt_autosync_once] ensure chatgpt.com open (no other domains)..."
$c1 = Enqueue-Command -Cmd "open_url" -CmdArgs @{ url = "https://chatgpt.com/" }
$ack1 = Wait-ForAck -CmdId $c1.id -TimeoutSeconds 20
if (-not $ack1) { Write-Host "[webgpt_autosync_once] warn: open_url ack timeout (continuing)" }

Write-Host "[webgpt_autosync_once] enqueue backfill..."
$c2 = Enqueue-Command -Cmd "webgpt_backfill_start" -CmdArgs @{
  limit = [Math]::Max(1, $BackfillLimit)
  scroll_steps = [Math]::Max(0, $ScrollSteps)
  sidebar_scroll_steps = [Math]::Max(10, $SidebarScrollSteps)
  scroll_delay_ms = [Math]::Max(60, $ScrollDelayMs)
  per_conv_wait_ms = [Math]::Max(2000, $PerConvWaitMs)
}

# Backfill is long-running; wait for the "start" ack, then sleep and rely on export_all for convergence.
$ack2 = Wait-ForAck -CmdId $c2.id -TimeoutSeconds 20
if (-not $ack2) { Write-Host "[webgpt_autosync_once] warn: backfill_start ack timeout (continuing)" }
Write-Host "[webgpt_autosync_once] backfill started; waiting a bit for progress..."
Start-Sleep -Seconds 15

if ([int]$CaptureMemory -ne 0) {
  Write-Host "[webgpt_autosync_once] capture personalization memory..."
  $m1 = Enqueue-Command -Cmd "open_url" -CmdArgs @{ url = "https://chatgpt.com/#settings/Personalization" }
  $ackm1 = Wait-ForAck -CmdId $m1.id -TimeoutSeconds 20
  if (-not $ackm1) { Write-Host "[webgpt_autosync_once] warn: open_url(personalization) ack timeout (continuing)" }
  $m2 = Enqueue-Command -Cmd "webgpt_capture_memory" -CmdArgs @{}
  $ackm2 = Wait-ForAck -CmdId $m2.id -TimeoutSeconds 45
  if (-not $ackm2) { Write-Host "[webgpt_autosync_once] warn: capture_memory ack timeout (continuing)" }
}

Write-Host "[webgpt_autosync_once] export_all (exports changed conversations + refreshes index)..."
PostJson "$BaseUrl/scc/webgpt/export_all" @{ limit = [Math]::Max(1, $ExportAllLimit) } | Out-Null

$ws = GetJson "$BaseUrl/scc/webgpt/status"
Write-Host "[webgpt_autosync_once] done. conversations=$($ws.counts.conversations) messages=$($ws.counts.messages)"
Write-Host "[webgpt_autosync_once] docs: d:\\quantsys\\docs\\INPUTS\\WEBGPT"
