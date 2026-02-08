param(
  [string]$RepoRoot = "d:\\quantsys"
)

$ErrorActionPreference = "Stop"

Set-Location $RepoRoot
python tools\\scc\\ops\\docflow_audit.py --repo-root $RepoRoot

