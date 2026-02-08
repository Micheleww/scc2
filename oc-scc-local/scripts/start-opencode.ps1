$ErrorActionPreference = "Stop"

$openCodeCli = $env:OPENCODE_CLI_PATH
if (-not $openCodeCli) {
  $repo = Split-Path -Parent $PSScriptRoot
  $repoRoot = Split-Path -Parent $repo
  $openCodeCli = Join-Path $repoRoot "OpenCode\\opencode-cli.exe"
}
if (-not (Test-Path $openCodeCli)) {
  throw "OpenCode CLI not found: $openCodeCli (set OPENCODE_CLI_PATH to override)"
}

$port = $env:OPENCODE_PORT
if (-not $port) { $port = "18790" }

$hostname = $env:OPENCODE_HOSTNAME
if (-not $hostname) { $hostname = "127.0.0.1" }

Write-Host "Starting OpenCode server: $openCodeCli serve --hostname $hostname --port $port"
Write-Host "Upstream will be: http://$hostname`:$port"

# Use cmd.exe to start in background (more resilient in restricted environments)
cmd /c "start """" /b ""$openCodeCli"" serve --hostname $hostname --port $port" | Out-Null
