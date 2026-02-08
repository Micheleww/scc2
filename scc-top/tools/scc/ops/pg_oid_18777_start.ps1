param(
  [string]$PgBin = "C:\\Program Files\\PostgreSQL\\16\\bin",
  [string]$DataDir = "artifacts\\pg_oid\\data_18777",
  [string]$LogFile = "artifacts\\pg_oid\\pg_18777.log",
  [int]$Port = 18777
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\\..\\..")
$data = Join-Path $repoRoot $DataDir
$log = Join-Path $repoRoot $LogFile

New-Item -ItemType Directory -Force -Path $data | Out-Null
New-Item -ItemType File -Force -Path $log | Out-Null

$pgCtl = Join-Path $PgBin "pg_ctl.exe"
$initDb = Join-Path $PgBin "initdb.exe"

if (-not (Test-Path $pgCtl)) { throw "pg_ctl not found: $pgCtl" }
if (-not (Test-Path $initDb)) { throw "initdb not found: $initDb" }

# Init (trust) only if missing PG_VERSION
if (-not (Test-Path (Join-Path $data "PG_VERSION"))) {
  & $initDb -D $data -U postgres -A trust --encoding=UTF8 --no-locale | Out-Host
}

# Start
& $pgCtl -D $data -l $log -o "-p $Port -h 127.0.0.1" start | Out-Host
Write-Host "ok: started oid postgres on 127.0.0.1:$Port"
Write-Host ("log_tail: " + (Get-Content $log -Tail 10 | Out-String))

