param(
  [string]$PgBin = "C:\\Program Files\\PostgreSQL\\16\\bin",
  [string]$DataDir = "artifacts\\pg_oid\\data_18777"
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\\..\\..")
$data = Join-Path $repoRoot $DataDir
$pgCtl = Join-Path $PgBin "pg_ctl.exe"
if (-not (Test-Path $pgCtl)) { throw "pg_ctl not found: $pgCtl" }
if (-not (Test-Path $data)) { throw "data dir not found: $data" }

& $pgCtl -D $data stop -m fast | Out-Host
Write-Host "ok: stopped oid postgres"

