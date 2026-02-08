param(
  [string]$ReportDir = "docs\\REPORT\\control_plane\\artifacts\\OID_REGISTRY_BOOTSTRAP_V010",
  [string]$Dsn = ""
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\\..\\..")).Path
Set-Location $repoRoot | Out-Null

if (-not $Dsn) {
  $Dsn = $env:SCC_OID_PG_DSN
}
if (-not $Dsn) {
  throw "missing DSN: set env SCC_OID_PG_DSN (password must be provided via env PGPASSWORD)"
}
if (-not $env:PGPASSWORD) {
  throw "missing env PGPASSWORD (do NOT hardcode secrets in repo)"
}

python -u tools\\scc\\ops\\oid_registry_bootstrap.py --dsn $Dsn --report-dir $ReportDir
exit $LASTEXITCODE

