Param(
  [string]$OutDir = "",
  [switch]$Clean
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

$root = Repo-Root
if (-not $OutDir) {
  $OutDir = Join-Path $root "_docker_ctx_scc"
}

Write-Host ("[stage_context] repo_root: {0}" -f $root)
Write-Host ("[stage_context] out_dir:  {0}" -f $OutDir)

if ($Clean -and (Test-Path $OutDir)) {
  Write-Host "[stage_context] cleaning out_dir..."
  Remove-Item -Recurse -Force -Path $OutDir -ErrorAction SilentlyContinue
}

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

function Copy-Dir([string]$srcRel, [string]$dstRel) {
  $src = Join-Path $root $srcRel
  $dst = Join-Path $OutDir $dstRel
  if (-not (Test-Path $src)) {
    Write-Host ("[stage_context] skip missing dir: {0}" -f $srcRel)
    return
  }
  New-Item -ItemType Directory -Force -Path $dst | Out-Null
  # Robocopy is resilient and fast on Windows.
  $cmd = @(
    "robocopy",
    "`"$src`"",
    "`"$dst`"",
    "/MIR",
    "/NFL","/NDL","/NJH","/NJS","/NP",
    "/R:1","/W:1"
  ) -join " "
  cmd /c $cmd | Out-Null
}

function Copy-File([string]$srcRel, [string]$dstRel) {
  $src = Join-Path $root $srcRel
  $dst = Join-Path $OutDir $dstRel
  if (-not (Test-Path $src)) {
    Write-Host ("[stage_context] skip missing file: {0}" -f $srcRel)
    return
  }
  $dstParent = Split-Path -Parent $dst
  if ($dstParent) { New-Item -ItemType Directory -Force -Path $dstParent | Out-Null }
  Copy-Item -Force -Path $src -Destination $dst
}

# Minimal runtime tree for unified_server (keep readiness stable via docker-compose env).
Copy-Dir "tools\\unified_server" "tools\\unified_server"
Copy-Dir "tools\\scc" "tools\\scc"
Copy-Dir "tools\\mcp_bus" "tools\\mcp_bus"
Copy-Dir "tools\\a2a_hub" "tools\\a2a_hub"
Copy-Dir "tools\\exchange_server" "tools\\exchange_server"
Copy-Dir "tools\\yme" "tools\\yme"
Copy-Dir "tools\\chatgpt_chat_archive_mvp" "tools\\chatgpt_chat_archive_mvp"
# UI dist only (avoid staging node_modules)
Copy-Dir "tools\\scc_ui\\dist" "tools\\scc_ui\\dist"
Copy-File "tools\\scc_ui\\NOTICE.md" "tools\\scc_ui\\NOTICE.md"

# Shared roots used by the app factory.
Copy-Dir "src" "src"
Copy-Dir "configs" "configs"
Copy-Dir "contracts" "contracts"

# LangGraph deps manifest (even if LANGGRAPH_ENABLED=false by default).
Copy-File "requirements-langgraph.txt" "requirements-langgraph.txt"

# Offline wheelhouse (prepared by user).
Copy-Dir "_wheelhouse" "_wheelhouse"

# Ensure build context has a dockerignore. This keeps `docker build` fast even if
# large reports/logs exist under the repo root.
$dockerignorePath = Join-Path $OutDir ".dockerignore"
@'
# Keep Docker build context small (especially on Windows where tarring is slow).
# Generated reports that can be huge
tools/unified_server/PORT_SCAN_REPORT.md

# Git / tooling
.git
.gitignore
.github
.pytest_cache
__pycache__
.mypy_cache
.ruff_cache
.venv
venv
env
node_modules

# Artifacts / logs / backups
artifacts
logs
data
_backups
*.log
*.tmp
*.bak
*.db
'@ | Set-Content -Encoding UTF8 -NoNewline -Path $dockerignorePath

Write-Host "[stage_context] done"
