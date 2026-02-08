$ErrorActionPreference = "Stop"

$openCodeCli = $env:OPENCODE_CLI_PATH
if (-not $openCodeCli) {
  $repo = Split-Path -Parent $PSScriptRoot
  $repoRoot = Resolve-Path (Join-Path $repo "..\\..\\..")
  $openCodeCli = Join-Path $repoRoot "OpenCode\\opencode-cli.exe"
}
if (-not (Test-Path $openCodeCli)) {
  throw "OpenCode CLI not found: $openCodeCli (set OPENCODE_CLI_PATH to override)"
}

$port = $env:OPENCODE_PORT
if (-not $port) { $port = "18790" }

$hostname = $env:OPENCODE_HOSTNAME
# IMPORTANT:
# - The unified_server runs in Docker and reaches the Windows host via `host.docker.internal`.
# - If OpenCode binds only to 127.0.0.1, the container cannot connect.
# Default to 0.0.0.0 for a "single port" integrated experience.
if (-not $hostname) { $hostname = "0.0.0.0" }

Write-Host "Starting OpenCode server: $openCodeCli serve --hostname $hostname --port $port"
Write-Host "Upstream will be: http://$hostname`:$port"

# Use cmd.exe to start in background (more resilient in restricted environments)
cmd /c "start """" /b ""$openCodeCli"" serve --hostname $hostname --port $port" | Out-Null
