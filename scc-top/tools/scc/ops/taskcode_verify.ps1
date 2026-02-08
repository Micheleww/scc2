param(
  [Parameter(Mandatory = $true)][string]$TaskCode,
  [Parameter(Mandatory = $true)][string]$Area,
  [string]$Commit = "HEAD"
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\\..\\..")).Path
Set-Location $repoRoot | Out-Null

python tools\\ci\\skill_call_guard.py --taskcode $TaskCode --area $Area --commit $Commit

