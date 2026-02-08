Param(
  [int]$Port = 18788,
  [int]$TimeoutSec = 180
)

$ErrorActionPreference = "Stop"

function Repo-Root {
  $here = $PSScriptRoot
  if (-not $here) {
    try { $here = Split-Path -Parent $MyInvocation.MyCommand.Path } catch { $here = "" }
  }
  if (-not $here) { $here = (Get-Location).Path }
  return (Resolve-Path (Join-Path $here "..\\..\\..")).Path
}

function Test-Docker {
  try {
    & docker version --format '{{.Server.Version}}' 2>$null | Out-Null
    return $true
  } catch {
    Write-Host "ERR: Docker Desktop not running / no engine access."
    return $false
  }
}

function Wait-Ready([int]$Port, [int]$TimeoutSec) {
  $deadline = (Get-Date).AddSeconds($TimeoutSec)
  while ((Get-Date) -lt $deadline) {
    try {
      $r = Invoke-RestMethod -TimeoutSec 2 -Uri ("http://127.0.0.1:{0}/health/ready" -f $Port)
      if ($r.status -eq "ready") { return $true }
    } catch {}
    Start-Sleep -Milliseconds 800
  }
  return $false
}

function Test-Url([string]$Url) {
  try {
    $resp = Invoke-WebRequest -UseBasicParsing -TimeoutSec 8 -Uri $Url
    return [pscustomobject]@{ url=$Url; status=$resp.StatusCode; len=($resp.Content.Length) }
  } catch {
    return [pscustomobject]@{ url=$Url; status="ERR"; len=0; err=$_.Exception.Message }
  }
}

if (-not (Test-Docker)) { exit 2 }

$root = Repo-Root
Write-Host ("repo_root: {0}" -f $root)

Write-Host "stage docker context..."
& $env:ComSpec /c (Join-Path $root 'tools\\unified_server\\docker\\stage_context.cmd') | Out-Host

Write-Host "docker compose up..."
Push-Location $root
try {
  & docker compose -f docker-compose.scc.yml up -d --build | Out-Host
  & docker compose -f docker-compose.scc.yml ps | Out-Host
} finally {
  Pop-Location
}

Write-Host ("wait ready: {0}s" -f $TimeoutSec)
if (-not (Wait-Ready -Port $Port -TimeoutSec $TimeoutSec)) {
  Write-Host "READY=false"
  exit 3
}
Write-Host "READY=true"

$base = "http://127.0.0.1:{0}" -f $Port
$urls = @(
  "$base/",
  "$base/desktop",
  "$base/client-config",
  "$base/scc",
  "$base/dashboard",
  "$base/viewer"
)

$urls | ForEach-Object { Test-Url $_ } | Format-Table -AutoSize | Out-Host

Write-Host "MCP tools/list..."
try {
  $body = @{ jsonrpc="2.0"; id=1; method="tools/list"; params=@{} } | ConvertTo-Json -Depth 6
  $m = Invoke-RestMethod -TimeoutSec 12 -Method Post -Uri "$base/mcp" -ContentType "application/json" -Body $body
  $count = 0
  if ($m.result -and $m.result.tools) { $count = $m.result.tools.Count }
  Write-Host ("MCP tools/list OK tools={0}" -f $count)
} catch {
  Write-Host ("MCP tools/list ERR: {0}" -f $_.Exception.Message)
  exit 4
}

Write-Host "OK"
exit 0

