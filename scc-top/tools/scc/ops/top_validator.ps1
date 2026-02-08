param(
  [string]$Registry = "docs/ssot/registry.json",
  [string]$OutDir = "artifacts/scc_state/top_validator"
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\\..\\..")).Path
Set-Location $repoRoot | Out-Null

python -u tools\\scc\\ops\\top_validator.py --registry $Registry --out-dir $OutDir
exit $LASTEXITCODE

