# SCC Git Auto-Sync Hook (Simplified)
param([string]$HookType = "post-commit")

$ContainerName = "scc-server"
$SyncScript = "/usr/local/bin/scc-sync"

function Write-Status($msg) {
    Write-Host $msg
}

Write-Status "=================================="
Write-Status "SCC Docker Auto-Sync Hook"
Write-Status "Hook Type: $HookType"
Write-Status "=================================="

# Check Docker
$dockerInfo = docker ps --filter "name=$ContainerName" --format "{{.Names}}" 2>$null
if ($dockerInfo -ne $ContainerName) {
    Write-Status "[ERROR] Docker container '$ContainerName' not running"
    exit 1
}

Write-Status "[OK] Docker container is running"

# Get git info
$commitHash = git rev-parse --short HEAD
$commitMsg = git log -1 --pretty=%B
Write-Status "Commit: $commitHash"
Write-Status "Message: $commitMsg"

# Sync
Write-Status "Syncing to Docker..."
$syncOutput = docker exec $ContainerName $SyncScript 2>&1
$exitCode = $LASTEXITCODE

if ($exitCode -eq 0) {
    Write-Status "[OK] Sync successful!"
    Write-Status $syncOutput
} else {
    Write-Status "[ERROR] Sync failed: $syncOutput"
    exit 1
}

Write-Status "=================================="
Write-Status "Auto-sync complete"
Write-Status "=================================="
