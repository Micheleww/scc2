param(
  [string]$ReportDir = "",
  [string]$Dsn = ""
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\\..\\..")
$script = Join-Path $repoRoot "tools\\scc\\ops\\oid_validator.py"

$argsList = @()
if ($ReportDir -and $ReportDir.Trim()) { $argsList += @("--report-dir", $ReportDir) }
if ($Dsn -and $Dsn.Trim()) { $argsList += @("--dsn", $Dsn) }

python $script @argsList

