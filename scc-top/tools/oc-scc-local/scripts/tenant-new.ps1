$ErrorActionPreference = "Stop"

param(
  [Parameter(Mandatory = $true)][string]$Name,
  [Parameter(Mandatory = $false)][int]$Port = 0,
  [Parameter(Mandatory = $false)][string]$Root = ""
)

function Write-FileUtf8([string]$path, [string]$text) {
  $dir = Split-Path -Parent $path
  if ($dir) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
  Set-Content -Encoding UTF8 -Path $path -Value $text
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\\..\\..\\..")
if (-not $Root) {
  $Root = Join-Path $repoRoot "tenants"
}

$tenantRoot = Join-Path $Root $Name
if (Test-Path $tenantRoot) { throw "Tenant already exists: $tenantRoot" }

New-Item -ItemType Directory -Force -Path $tenantRoot | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $tenantRoot "artifacts\\executor_logs") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $tenantRoot "artifacts\\taskboard") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $tenantRoot "docs") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $tenantRoot "exec_root") | Out-Null

if ($Port -le 0) {
  # Default port allocation strategy for manual use: 18788 + hash mod 1000
  $hash = [Math]::Abs(($Name.GetHashCode()))
  $Port = 18788 + ($hash % 1000)
}

$now = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()

$runtimeEnv = @"
# tenant runtime.env (B-mode defaults)
# generated_at_ms=$now

GATEWAY_PORT=$Port
EXEC_ROOT=$tenantRoot/exec_root
EXEC_LOG_DIR=$tenantRoot/artifacts/executor_logs
BOARD_DIR=$tenantRoot/artifacts/taskboard
DOCS_ROOT=$tenantRoot/docs
RUNTIME_ENV_FILE=$tenantRoot/runtime.env

# Throughput (max 10 total recommended on typical desktops)
EXEC_CONCURRENCY_CODEX=6
EXEC_CONCURRENCY_OPENCODE=4
DESIRED_RATIO_CODEX=6
DESIRED_RATIO_OPENCODECLI=4
EXTERNAL_MAX_CODEX=6
EXTERNAL_MAX_OPENCODECLI=4

# B-mode: keep chain short, avoid governance overreach
AUTO_PUMP=true
AUTO_FLOW_CONTROLLER=true
FLOW_MANAGER_HOOK_ENABLED=true
FEEDBACK_HOOK_ENABLED=false

# CI hard gate (all NEW tasks from now on)
CI_GATE_ENABLED=true
CI_GATE_STRICT=true
CI_GATE_ALLOW_ALL=false
CI_GATE_TIMEOUT_MS=1200000
CI_GATE_CWD=$repoRoot
CI_ENFORCE_SINCE_MS=$now
AUTO_DEFAULT_ALLOWED_TESTS=true

# CI auto-fixup loop
CI_FIXUP_ENABLED=true
CI_FIXUP_MAX_PER_TASK=2
CI_FIXUP_ROLE=qa
CI_FIXUP_ALLOWED_EXECUTORS=codex
CI_FIXUP_ALLOWED_MODELS=gpt-5.2
CI_FIXUP_TIMEOUT_MS=1200000
"@

Write-FileUtf8 -path (Join-Path $tenantRoot "runtime.env") -text $runtimeEnv

Write-Host "OK"
Write-Host "  tenant: $tenantRoot"
Write-Host "  port:   $Port"
Write-Host "  next:   powershell -ExecutionPolicy Bypass -File $(Join-Path $repoRoot 'scc-top\\tools\\oc-scc-local\\scripts\\tenant-start.ps1') -TenantRoot `"$tenantRoot`""

