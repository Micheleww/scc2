# Shared worker utilities for SCC executors
# This module contains common functions used by both codex and opencodecli workers

$ErrorActionPreference = "Stop"

# Environment setup helpers
function Get-EnvOrDefault([string]$name, [string]$default) {
    $val = [Environment]::GetEnvironmentVariable($name)
    if ($val) { return $val }
    return $default
}

function Get-EnvOrDefaultInt([string]$name, [int]$default) {
    $val = [Environment]::GetEnvironmentVariable($name)
    if ($val -and [int]::TryParse($val, [ref]$null)) { return [int]$val }
    return $default
}

function Get-EnvBool([string]$name, [bool]$default) {
    $val = [Environment]::GetEnvironmentVariable($name)
    if ($val) {
        return ([string]$val).ToLower().Trim() -ne "false"
    }
    return $default
}

# Path resolution
function Get-ExecRoot([string]$scriptRoot) {
    $envExecRoot = [Environment]::GetEnvironmentVariable("EXEC_ROOT")
    if ($envExecRoot) { return $envExecRoot }
    $ocRoot = Split-Path -Parent $scriptRoot
    $repoRoot = Split-Path -Parent $ocRoot
    return $repoRoot
}

# HTTP helpers
function Resolve-Url([string]$base, [string]$u) {
    if (-not $u) { return $null }
    $s = [string]$u
    if ($s.StartsWith("/")) { return $base.TrimEnd("/") + $s }
    return $s
}

function Fetch-ToTemp([string]$url) {
    if (-not $url) { return $null }
    $tmp = Join-Path $env:TEMP ("scc-fetch-" + ([Guid]::NewGuid().ToString("n")) + ".tmp")
    Invoke-WebRequest -UseBasicParsing -Method GET -TimeoutSec 20 -OutFile $tmp $url | Out-Null
    return $tmp
}

function Post-Json($url, $obj) {
    $json = ($obj | ConvertTo-Json -Depth 8 -Compress)
    $utf8 = [System.Text.UTF8Encoding]::new($false)
    $bytes = $utf8.GetBytes([string]$json)
    (Invoke-WebRequest -UseBasicParsing -Method POST -ContentType "application/json; charset=utf-8" -Body $bytes -TimeoutSec 30 $url).Content | ConvertFrom-Json
}

function Get-Json($url) {
    try {
        (Invoke-WebRequest -UseBasicParsing -Method GET -TimeoutSec 20 $url).Content | ConvertFrom-Json
    } catch {
        $null
    }
}

# Cryptography helpers
function Sha256-File([string]$path) {
    if (-not $path -or -not (Test-Path $path)) { return $null }
    try {
        $h = (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash.ToLower()
        return "sha256:$h"
    } catch {
        return $null
    }
}

function Attest-Sha256([string]$nonce, [string]$path) {
    if (-not $nonce -or -not $path -or -not (Test-Path $path)) { return $null }
    try {
        $sha = [System.Security.Cryptography.SHA256]::Create()
        try {
            $nbytes = [System.Text.Encoding]::UTF8.GetBytes([string]$nonce)
            [void]$sha.TransformBlock($nbytes, 0, $nbytes.Length, $null, 0)
            $fs = [System.IO.File]::OpenRead($path)
            try {
                $buf = New-Object byte[] 65536
                while (($read = $fs.Read($buf, 0, $buf.Length)) -gt 0) {
                    [void]$sha.TransformBlock($buf, 0, $read, $null, 0)
                }
            } finally {
                try { $fs.Dispose() } catch {}
            }
            [void]$sha.TransformFinalBlock([byte[]]@(), 0, 0)
            $hex = -join ($sha.Hash | ForEach-Object { $_.ToString("x2") })
            return "sha256:$hex"
        } finally {
            try { $sha.Dispose() } catch {}
        }
    } catch {
        return $null
    }
}

# Worker registration
function Register-Worker([string]$base, [string]$name, [string]$executor, [array]$models) {
    Write-Host "Registering worker: $name @ $base"
    $w = Post-Json "$base/executor/workers/register" @{ name = $name; executors = @($executor); models = $models }
    Write-Host "workerId=$($w.id)"
    return $w.id
}

# Logging
function Initialize-WorkerLog([string]$name) {
    $ocRoot = Split-Path -Parent $PSScriptRoot
    $repoRoot = Split-Path -Parent $ocRoot
    $execLogDir = Get-EnvOrDefault "EXEC_LOG_DIR" (Join-Path $repoRoot "artifacts\executor_logs")
    $workersDir = Join-Path $execLogDir "workers"
    try { New-Item -ItemType Directory -Force -Path $workersDir | Out-Null } catch {}
    return Join-Path $workersDir ($name + ".log")
}

function Log-Worker([string]$logFile, [string]$msg) {
    try {
        $line = ("[{0}] {1}" -f (Get-Date).ToString("o"), $msg)
        Add-Content -Encoding UTF8 -Path $logFile -Value $line
    } catch {}
}

# Text processing
function Sanitize-ForJson([string]$s) {
    if ($null -eq $s) { return "" }
    $t = [string]$s
    # JSON does not allow raw control chars 0x00-0x1F except 	 
 .
    return ($t -replace "[\u0000-\u0008\u000B\u000C\u000E-\u001F]", "")
}

function Read-TextTailUtf8([string]$path, [int]$maxChars) {
    try {
        if (-not $path) { return "" }
        if (-not (Test-Path $path)) { return "" }
        $enc = [System.Text.UTF8Encoding]::new($false)
        $fi = Get-Item -LiteralPath $path -ErrorAction SilentlyContinue
        if (-not $fi) { return "" }
        $maxBytes = [int64]([math]::Max(4096, [math]::Min([int64]($maxChars * 4), [int64]20000000)))
        if ($fi.Length -le $maxBytes) {
            return [System.IO.File]::ReadAllText($path, $enc)
        }
        $fs = [System.IO.File]::Open($path, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
        try {
            [void]$fs.Seek(-$maxBytes, [System.IO.SeekOrigin]::End)
            $buf = New-Object byte[] $maxBytes
            $read = $fs.Read($buf, 0, $buf.Length)
            return $enc.GetString($buf, 0, $read)
        } finally {
            try { $fs.Dispose() } catch {}
        }
    } catch {
        return ""
    }
}

# Task bundle helpers
function Fetch-TaskBundleFiles($job, [string]$base, [string]$attestationNonce) {
    $result = @{
        manifestSha256 = $null
        contextPackV1JsonSha256 = $null
        filesSha256 = @{}
        attestSha256 = @{}
    }

    try {
        if ($job.PSObject.Properties.Name -contains "taskBundle" -and $job.taskBundle) {
            $manifestUrl = $null
            if ($job.taskBundle.PSObject.Properties.Name -contains "fetch_manifest_raw") {
                $manifestUrl = Resolve-Url $base ([string]$job.taskBundle.fetch_manifest_raw)
            } elseif ($job.taskBundle.PSObject.Properties.Name -contains "fetch_manifest") {
                $manifestUrl = Resolve-Url $base ([string]$job.taskBundle.fetch_manifest)
                if ($manifestUrl -and ($manifestUrl -notmatch "format=raw")) { $manifestUrl = $manifestUrl + "?format=raw" }
            }
            $pinsUrl = $null
            if ($job.taskBundle.PSObject.Properties.Name -contains "fetch_pins_raw") { $pinsUrl = Resolve-Url $base ([string]$job.taskBundle.fetch_pins_raw) }
            elseif ($job.taskBundle.PSObject.Properties.Name -contains "fetch_pins") {
                $pinsUrl = Resolve-Url $base ([string]$job.taskBundle.fetch_pins)
                if ($pinsUrl -and ($pinsUrl -notmatch "format=raw")) { $pinsUrl = $pinsUrl + "?format=raw" }
            }
            $preUrl = $null
            if ($job.taskBundle.PSObject.Properties.Name -contains "fetch_preflight_raw") { $preUrl = Resolve-Url $base ([string]$job.taskBundle.fetch_preflight_raw) }
            elseif ($job.taskBundle.PSObject.Properties.Name -contains "fetch_preflight") {
                $preUrl = Resolve-Url $base ([string]$job.taskBundle.fetch_preflight)
                if ($preUrl -and ($preUrl -notmatch "format=raw")) { $preUrl = $preUrl + "?format=raw" }
            }
            $taskUrl = $null
            if ($job.taskBundle.PSObject.Properties.Name -contains "fetch_task_raw") { $taskUrl = Resolve-Url $base ([string]$job.taskBundle.fetch_task_raw) }
            elseif ($job.taskBundle.PSObject.Properties.Name -contains "fetch_task") {
                $taskUrl = Resolve-Url $base ([string]$job.taskBundle.fetch_task)
                if ($taskUrl -and ($taskUrl -notmatch "format=raw")) { $taskUrl = $taskUrl + "?format=raw" }
            }
            $replayUrl = $null
            if ($job.taskBundle.PSObject.Properties.Name -contains "fetch_replay_bundle_raw") { $replayUrl = Resolve-Url $base ([string]$job.taskBundle.fetch_replay_bundle_raw) }
            elseif ($job.taskBundle.PSObject.Properties.Name -contains "fetch_replay_bundle") {
                $replayUrl = Resolve-Url $base ([string]$job.taskBundle.fetch_replay_bundle)
                if ($replayUrl -and ($replayUrl -notmatch "format=raw")) { $replayUrl = $replayUrl + "?format=raw" }
            }

            if ($manifestUrl) {
                $tmp = Fetch-ToTemp $manifestUrl
                try {
                    $result.manifestSha256 = Sha256-File $tmp
                    $result.filesSha256["manifest.json"] = $result.manifestSha256
                    $result.attestSha256["manifest.json"] = (Attest-Sha256 $attestationNonce $tmp)
                } finally { try { if ($tmp) { Remove-Item -Force -ErrorAction SilentlyContinue -LiteralPath $tmp } } catch {} }
            }
            if ($pinsUrl) {
                $tmp = Fetch-ToTemp $pinsUrl
                try {
                    $result.filesSha256["pins.json"] = (Sha256-File $tmp)
                    $result.attestSha256["pins.json"] = (Attest-Sha256 $attestationNonce $tmp)
                } finally { try { if ($tmp) { Remove-Item -Force -ErrorAction SilentlyContinue -LiteralPath $tmp } } catch {} }
            }
            if ($preUrl) {
                $tmp = Fetch-ToTemp $preUrl
                try {
                    $result.filesSha256["preflight.json"] = (Sha256-File $tmp)
                    $result.attestSha256["preflight.json"] = (Attest-Sha256 $attestationNonce $tmp)
                } finally { try { if ($tmp) { Remove-Item -Force -ErrorAction SilentlyContinue -LiteralPath $tmp } } catch {} }
            }
            if ($taskUrl) {
                $tmp = Fetch-ToTemp $taskUrl
                try {
                    $result.filesSha256["task.json"] = (Sha256-File $tmp)
                    $result.attestSha256["task.json"] = (Attest-Sha256 $attestationNonce $tmp)
                } finally { try { if ($tmp) { Remove-Item -Force -ErrorAction SilentlyContinue -LiteralPath $tmp } } catch {} }
            }
            if ($replayUrl) {
                $tmp = Fetch-ToTemp $replayUrl
                try {
                    $h = Sha256-File $tmp
                    if ($h) { $result.filesSha256["replay_bundle.json"] = $h }
                    $ha = Attest-Sha256 $attestationNonce $tmp
                    if ($ha) { $result.attestSha256["replay_bundle.json"] = $ha }
                } finally { try { if ($tmp) { Remove-Item -Force -ErrorAction SilentlyContinue -LiteralPath $tmp } } catch {} }
            }
        }
    } catch {}

    return $result
}

function Fetch-ContextPackV1($job, [string]$base, [string]$attestationNonce) {
    $result = @{
        id = $null
        jsonSha256 = $null
        attestSha256 = $null
    }

    if ($job.PSObject.Properties.Name -contains "contextPackV1Id") {
        $result.id = [string]$job.contextPackV1Id
    }

    try {
        if ($job.PSObject.Properties.Name -contains "contextPackV1" -and $job.contextPackV1) {
            $u = $null
            if ($job.contextPackV1.PSObject.Properties.Name -contains "fetch_json_raw") {
                $u = Resolve-Url $base ([string]$job.contextPackV1.fetch_json_raw)
            } elseif ($job.contextPackV1.PSObject.Properties.Name -contains "fetch_json") {
                $u = Resolve-Url $base ([string]$job.contextPackV1.fetch_json)
                if ($u -and ($u -notmatch "format=raw")) { $u = $u + "?format=raw" }
            }
            if ($u) {
                $tmp = Fetch-ToTemp $u
                try {
                    $result.jsonSha256 = Sha256-File $tmp
                    $result.attestSha256 = Attest-Sha256 $attestationNonce $tmp
                } finally {
                    try { Remove-Item -Force -ErrorAction SilentlyContinue -LiteralPath $tmp } catch {}
                }
            }
        }
    } catch {}

    return $result
}

# Validation helpers
function Test-ContextPackV1Required($job, [string]$base, [string]$workerId, [bool]$requireContextPackV1) {
    if (-not $requireContextPackV1) { return @{ valid = $true } }

    $attestationNonce = $null
    if ($job.PSObject.Properties.Name -contains "attestation" -and $job.attestation -and ($job.attestation.PSObject.Properties.Name -contains "nonce")) {
        $attestationNonce = [string]$job.attestation.nonce
    }

    $contextPackV1Id = $null
    if ($job.PSObject.Properties.Name -contains "contextPackV1Id") {
        $contextPackV1Id = [string]$job.contextPackV1Id
    }

    if (-not $contextPackV1Id -or -not $contextPackV1Id.Trim()) {
        return @{
            valid = $false
            error = "[worker] missing contextPackV1Id in claim response (enterprise fail-closed)"
            attestation_nonce = $attestationNonce
            contextPackV1Id = $contextPackV1Id
        }
    }

    if (-not $attestationNonce -or -not $attestationNonce.Trim()) {
        return @{
            valid = $false
            error = "[worker] missing attestation nonce in claim response (enterprise fail-closed)"
            attestation_nonce = $attestationNonce
            contextPackV1Id = $contextPackV1Id
        }
    }

    return @{
        valid = $true
        attestation_nonce = $attestationNonce
        contextPackV1Id = $contextPackV1Id
    }
}

# Export all functions
Export-ModuleMember -Function @(
    'Get-EnvOrDefault',
    'Get-EnvOrDefaultInt',
    'Get-EnvBool',
    'Get-ExecRoot',
    'Resolve-Url',
    'Fetch-ToTemp',
    'Post-Json',
    'Get-Json',
    'Sha256-File',
    'Attest-Sha256',
    'Register-Worker',
    'Initialize-WorkerLog',
    'Log-Worker',
    'Sanitize-ForJson',
    'Read-TextTailUtf8',
    'Fetch-TaskBundleFiles',
    'Fetch-ContextPackV1',
    'Test-ContextPackV1Required'
)
