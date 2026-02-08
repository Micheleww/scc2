$ErrorActionPreference = "Stop"

$Base = $env:GATEWAY_BASE
if (-not $Base) { $Base = "http://127.0.0.1:18788" }

$ModelDefault = $env:CODEX_MODEL
if (-not $ModelDefault) { $ModelDefault = "gpt-5.3-codex" }

$CodexBin = $env:CODEX_BIN
if (-not $CodexBin) {
  $candidate = Join-Path $env:APPDATA "npm\\codex.cmd"
  if (Test-Path $candidate) { $CodexBin = $candidate } else { $CodexBin = "codex" }
}

$ExecRoot = $env:EXEC_ROOT
if (-not $ExecRoot) {
  $ocRoot = Split-Path -Parent $PSScriptRoot
  $repoRoot = Split-Path -Parent $ocRoot
  $ExecRoot = $repoRoot
}

$Name = $env:WORKER_NAME
if (-not $Name) { $Name = "codex-worker" }

$IdleExitSeconds = if ($env:WORKER_IDLE_EXIT_SECONDS) { [int]$env:WORKER_IDLE_EXIT_SECONDS } else { 180 }
$idleSince = $null
$StallSeconds = if ($env:WORKER_STALL_SECONDS) { [int]$env:WORKER_STALL_SECONDS } else { 240 }

$RequireContextPackV1 = $true
if ($env:CONTEXT_PACK_V1_REQUIRED) {
  $RequireContextPackV1 = ([string]$env:CONTEXT_PACK_V1_REQUIRED).ToLower().Trim() -ne "false"
}

$ocRoot2 = Split-Path -Parent $PSScriptRoot
$repoRoot2 = Split-Path -Parent $ocRoot2
$execLogDir2 = $env:EXEC_LOG_DIR
if (-not $execLogDir2) { $execLogDir2 = Join-Path $repoRoot2 "artifacts\\executor_logs" }
$workersDir = Join-Path $execLogDir2 "workers"
try { New-Item -ItemType Directory -Force -Path $workersDir | Out-Null } catch {}
$WorkerLogFile = Join-Path $workersDir ($Name + ".log")
function Log-Worker([string]$msg) {
  try {
    $line = ("[{0}] {1}" -f (Get-Date).ToString("o"), $msg)
    Add-Content -Encoding UTF8 -Path $WorkerLogFile -Value $line
  } catch {}
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

function Sanitize-ForJson([string]$s) {
  if ($null -eq $s) { return "" }
  $t = [string]$s
  # JSON does not allow raw control chars 0x00-0x1F except \t \n \r.
  return ($t -replace "[\u0000-\u0008\u000B\u000C\u000E-\u001F]", "")
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

$workerId = $null
$lastIdleHeartbeat = $null

function Ensure-Worker {
  if ($workerId) { return }
  Write-Host "Registering worker: $Name @ $Base"
  Log-Worker "register base=$Base name=$Name"
  $models = @()
  if ($env:WORKER_MODELS) {
    $models = $env:WORKER_MODELS.Split(',') | ForEach-Object { $_.Trim() } | Where-Object { $_ }
  } else {
    # Safe default: only claim jobs we know we can run
    $models = @("gpt-5.3-codex","gpt-5.2","gpt-5.1-codex-max")
  }
  $w = Post-Json "$Base/executor/workers/register" @{ name = $Name; executors = @("codex"); models = $models }
  $script:workerId = $w.id
  Write-Host "workerId=$workerId"
  Log-Worker "registered workerId=$workerId models=$($models -join ',')"
}

while ($true) {
  $jobId = $null
  try {
    Ensure-Worker
    $claimUrl = "$Base/executor/workers/$workerId/claim?executor=codex&waitMs=25000"
    $resp = Invoke-WebRequest -UseBasicParsing -TimeoutSec 35 $claimUrl
    if ($resp.StatusCode -eq 204) {
      # Heartbeat while idle so autoscaler doesn't assume we're dead.
      if (-not $lastIdleHeartbeat -or (New-TimeSpan -Start $lastIdleHeartbeat -End (Get-Date)).TotalSeconds -ge 25) {
        try { Post-Json "$Base/executor/workers/$workerId/heartbeat" @{ runningJobId = $null } | Out-Null } catch {}
        $lastIdleHeartbeat = Get-Date
      }
      if ($IdleExitSeconds -gt 0) {
        if (-not $idleSince) { $idleSince = Get-Date }
        if ((New-TimeSpan -Start $idleSince -End (Get-Date)).TotalSeconds -ge $IdleExitSeconds) {
          exit 0
        }
      }
      continue
    }
    $job = $resp.Content | ConvertFrom-Json
    $idleSince = $null
    $jobId = $job.id
    $model = if ($job.model) { [string]$job.model } else { $ModelDefault }
    $prompt = [string]$job.prompt
    $attestationNonce = $null
    if ($job.PSObject.Properties.Name -contains "attestation" -and $job.attestation -and ($job.attestation.PSObject.Properties.Name -contains "nonce")) {
      $attestationNonce = [string]$job.attestation.nonce
    }
    $contextPackV1Id = $null
    if ($job.PSObject.Properties.Name -contains "contextPackV1Id") {
      $contextPackV1Id = [string]$job.contextPackV1Id
    }

    $taskBundleManifestSha256 = $null
    $contextPackV1JsonSha256 = $null
    $taskBundleFilesSha256 = $null
    $contextPackV1JsonAttestSha256 = $null
    $taskBundleFilesAttestSha256 = $null
    try {
      if ($job.PSObject.Properties.Name -contains "taskBundle" -and $job.taskBundle) {
        $manifestUrl = $null
        if ($job.taskBundle.PSObject.Properties.Name -contains "fetch_manifest_raw") {
          $manifestUrl = Resolve-Url $Base ([string]$job.taskBundle.fetch_manifest_raw)
        } elseif ($job.taskBundle.PSObject.Properties.Name -contains "fetch_manifest") {
          $manifestUrl = Resolve-Url $Base ([string]$job.taskBundle.fetch_manifest)
          if ($manifestUrl -and ($manifestUrl -notmatch "format=raw")) { $manifestUrl = $manifestUrl + "?format=raw" }
        }
        $pinsUrl = $null
        if ($job.taskBundle.PSObject.Properties.Name -contains "fetch_pins_raw") { $pinsUrl = Resolve-Url $Base ([string]$job.taskBundle.fetch_pins_raw) }
        elseif ($job.taskBundle.PSObject.Properties.Name -contains "fetch_pins") {
          $pinsUrl = Resolve-Url $Base ([string]$job.taskBundle.fetch_pins)
          if ($pinsUrl -and ($pinsUrl -notmatch "format=raw")) { $pinsUrl = $pinsUrl + "?format=raw" }
        }
        $preUrl = $null
        if ($job.taskBundle.PSObject.Properties.Name -contains "fetch_preflight_raw") { $preUrl = Resolve-Url $Base ([string]$job.taskBundle.fetch_preflight_raw) }
        elseif ($job.taskBundle.PSObject.Properties.Name -contains "fetch_preflight") {
          $preUrl = Resolve-Url $Base ([string]$job.taskBundle.fetch_preflight)
          if ($preUrl -and ($preUrl -notmatch "format=raw")) { $preUrl = $preUrl + "?format=raw" }
        }
        $taskUrl = $null
        if ($job.taskBundle.PSObject.Properties.Name -contains "fetch_task_raw") { $taskUrl = Resolve-Url $Base ([string]$job.taskBundle.fetch_task_raw) }
        elseif ($job.taskBundle.PSObject.Properties.Name -contains "fetch_task") {
          $taskUrl = Resolve-Url $Base ([string]$job.taskBundle.fetch_task)
          if ($taskUrl -and ($taskUrl -notmatch "format=raw")) { $taskUrl = $taskUrl + "?format=raw" }
        }
        $replayUrl = $null
        if ($job.taskBundle.PSObject.Properties.Name -contains "fetch_replay_bundle_raw") { $replayUrl = Resolve-Url $Base ([string]$job.taskBundle.fetch_replay_bundle_raw) }
        elseif ($job.taskBundle.PSObject.Properties.Name -contains "fetch_replay_bundle") {
          $replayUrl = Resolve-Url $Base ([string]$job.taskBundle.fetch_replay_bundle)
          if ($replayUrl -and ($replayUrl -notmatch "format=raw")) { $replayUrl = $replayUrl + "?format=raw" }
        }

        $taskBundleFilesSha256 = @{}
        $taskBundleFilesAttestSha256 = @{}
        if ($manifestUrl) {
          $tmp = Fetch-ToTemp $manifestUrl
          try {
            $taskBundleManifestSha256 = Sha256-File $tmp
            $taskBundleFilesSha256["manifest.json"] = $taskBundleManifestSha256
            $taskBundleFilesAttestSha256["manifest.json"] = (Attest-Sha256 $attestationNonce $tmp)
          } finally { try { if ($tmp) { Remove-Item -Force -ErrorAction SilentlyContinue -LiteralPath $tmp } } catch {} }
        }
        if ($pinsUrl) {
          $tmp = Fetch-ToTemp $pinsUrl
          try {
            $taskBundleFilesSha256["pins.json"] = (Sha256-File $tmp)
            $taskBundleFilesAttestSha256["pins.json"] = (Attest-Sha256 $attestationNonce $tmp)
          } finally { try { if ($tmp) { Remove-Item -Force -ErrorAction SilentlyContinue -LiteralPath $tmp } } catch {} }
        }
        if ($preUrl) {
          $tmp = Fetch-ToTemp $preUrl
          try {
            $taskBundleFilesSha256["preflight.json"] = (Sha256-File $tmp)
            $taskBundleFilesAttestSha256["preflight.json"] = (Attest-Sha256 $attestationNonce $tmp)
          } finally { try { if ($tmp) { Remove-Item -Force -ErrorAction SilentlyContinue -LiteralPath $tmp } } catch {} }
        }
        if ($taskUrl) {
          $tmp = Fetch-ToTemp $taskUrl
          try {
            $taskBundleFilesSha256["task.json"] = (Sha256-File $tmp)
            $taskBundleFilesAttestSha256["task.json"] = (Attest-Sha256 $attestationNonce $tmp)
          } finally { try { if ($tmp) { Remove-Item -Force -ErrorAction SilentlyContinue -LiteralPath $tmp } } catch {} }
        }
        if ($replayUrl) {
          $tmp = Fetch-ToTemp $replayUrl
          try {
            $h = Sha256-File $tmp
            if ($h) { $taskBundleFilesSha256["replay_bundle.json"] = $h }
            $ha = Attest-Sha256 $attestationNonce $tmp
            if ($ha) { $taskBundleFilesAttestSha256["replay_bundle.json"] = $ha }
          } finally { try { if ($tmp) { Remove-Item -Force -ErrorAction SilentlyContinue -LiteralPath $tmp } } catch {} }
        }
      }
    } catch {}
    try {
      if ($job.PSObject.Properties.Name -contains "contextPackV1" -and $job.contextPackV1) {
        $u = $null
        if ($job.contextPackV1.PSObject.Properties.Name -contains "fetch_json_raw") {
          $u = Resolve-Url $Base ([string]$job.contextPackV1.fetch_json_raw)
        } elseif ($job.contextPackV1.PSObject.Properties.Name -contains "fetch_json") {
          $u = Resolve-Url $Base ([string]$job.contextPackV1.fetch_json)
          if ($u -and ($u -notmatch "format=raw")) { $u = $u + "?format=raw" }
        }
        if ($u) {
          $tmp = Fetch-ToTemp $u
          try {
            $contextPackV1JsonSha256 = Sha256-File $tmp
            $contextPackV1JsonAttestSha256 = Attest-Sha256 $attestationNonce $tmp
          } finally {
            try { Remove-Item -Force -ErrorAction SilentlyContinue -LiteralPath $tmp } catch {}
          }
        }
      }
    } catch {}
    $timeoutMs = 0
    if ($job.timeoutMs -ne $null) {
      try { $timeoutMs = [int]$job.timeoutMs } catch { $timeoutMs = 0 }
    }

    if ($RequireContextPackV1 -and (-not $contextPackV1Id -or -not $contextPackV1Id.Trim())) {
      try {
        Post-Json "$Base/executor/jobs/$jobId/complete" @{
          workerId = $workerId
          exit_code = 1
          stdout = ""
          stderr = "[worker] missing contextPackV1Id in claim response (enterprise fail-closed)"
          attestation_nonce = $attestationNonce
          contextPackV1Id = $contextPackV1Id
          task_bundle_manifest_sha256 = $taskBundleManifestSha256
          context_pack_v1_json_sha256 = $contextPackV1JsonSha256
          task_bundle_files_sha256 = $taskBundleFilesSha256
          context_pack_v1_json_attest_sha256 = $contextPackV1JsonAttestSha256
          task_bundle_files_attest_sha256 = $taskBundleFilesAttestSha256
        } | Out-Null
      } catch {}
      continue
    }

    if ($RequireContextPackV1 -and (-not $attestationNonce -or -not $attestationNonce.Trim())) {
      try {
        Post-Json "$Base/executor/jobs/$jobId/complete" @{
          workerId = $workerId
          exit_code = 1
          stdout = ""
          stderr = "[worker] missing attestation nonce in claim response (enterprise fail-closed)"
          attestation_nonce = $attestationNonce
          contextPackV1Id = $contextPackV1Id
          task_bundle_manifest_sha256 = $taskBundleManifestSha256
          context_pack_v1_json_sha256 = $contextPackV1JsonSha256
          task_bundle_files_sha256 = $taskBundleFilesSha256
          context_pack_v1_json_attest_sha256 = $contextPackV1JsonAttestSha256
          task_bundle_files_attest_sha256 = $taskBundleFilesAttestSha256
        } | Out-Null
      } catch {}
      continue
    }

    if ($RequireContextPackV1 -and (-not $taskBundleManifestSha256 -or -not $taskBundleManifestSha256.Trim())) {
      try {
        Post-Json "$Base/executor/jobs/$jobId/complete" @{
          workerId = $workerId
          exit_code = 1
          stdout = ""
          stderr = "[worker] missing taskBundle manifest sha256 (fetch_manifest absent or unreadable; enterprise fail-closed)"
          attestation_nonce = $attestationNonce
          contextPackV1Id = $contextPackV1Id
          task_bundle_manifest_sha256 = $taskBundleManifestSha256
          context_pack_v1_json_sha256 = $contextPackV1JsonSha256
          task_bundle_files_sha256 = $taskBundleFilesSha256
          context_pack_v1_json_attest_sha256 = $contextPackV1JsonAttestSha256
          task_bundle_files_attest_sha256 = $taskBundleFilesAttestSha256
        } | Out-Null
      } catch {}
      continue
    }

    if ($RequireContextPackV1 -and (-not $contextPackV1JsonSha256 -or -not $contextPackV1JsonSha256.Trim())) {
      try {
        Post-Json "$Base/executor/jobs/$jobId/complete" @{
          workerId = $workerId
          exit_code = 1
          stdout = ""
          stderr = "[worker] missing contextPackV1 pack_json sha256 (fetch_json absent or unreadable; enterprise fail-closed)"
          attestation_nonce = $attestationNonce
          contextPackV1Id = $contextPackV1Id
          task_bundle_manifest_sha256 = $taskBundleManifestSha256
          context_pack_v1_json_sha256 = $contextPackV1JsonSha256
          task_bundle_files_sha256 = $taskBundleFilesSha256
          context_pack_v1_json_attest_sha256 = $contextPackV1JsonAttestSha256
          task_bundle_files_attest_sha256 = $taskBundleFilesAttestSha256
        } | Out-Null
      } catch {}
      continue
    }

    if ($RequireContextPackV1 -and (-not $taskBundleFilesSha256 -or -not $taskBundleFilesSha256["pins.json"] -or -not $taskBundleFilesSha256["preflight.json"] -or -not $taskBundleFilesSha256["task.json"] -or -not $taskBundleFilesSha256["manifest.json"])) {
      try {
        Post-Json "$Base/executor/jobs/$jobId/complete" @{
          workerId = $workerId
          exit_code = 1
          stdout = ""
          stderr = "[worker] missing taskBundle files sha256 map (pins/preflight/task/manifest required; enterprise fail-closed)"
          attestation_nonce = $attestationNonce
          contextPackV1Id = $contextPackV1Id
          task_bundle_manifest_sha256 = $taskBundleManifestSha256
          context_pack_v1_json_sha256 = $contextPackV1JsonSha256
          task_bundle_files_sha256 = $taskBundleFilesSha256
          context_pack_v1_json_attest_sha256 = $contextPackV1JsonAttestSha256
          task_bundle_files_attest_sha256 = $taskBundleFilesAttestSha256
        } | Out-Null
      } catch {}
      continue
    }

    if ($RequireContextPackV1 -and (-not $contextPackV1JsonAttestSha256 -or -not $contextPackV1JsonAttestSha256.Trim())) {
      try {
        Post-Json "$Base/executor/jobs/$jobId/complete" @{
          workerId = $workerId
          exit_code = 1
          stdout = ""
          stderr = "[worker] missing contextPackV1 pack_json attestation sha256 (nonce-bound; enterprise fail-closed)"
          attestation_nonce = $attestationNonce
          contextPackV1Id = $contextPackV1Id
          task_bundle_manifest_sha256 = $taskBundleManifestSha256
          context_pack_v1_json_sha256 = $contextPackV1JsonSha256
          task_bundle_files_sha256 = $taskBundleFilesSha256
          context_pack_v1_json_attest_sha256 = $contextPackV1JsonAttestSha256
          task_bundle_files_attest_sha256 = $taskBundleFilesAttestSha256
        } | Out-Null
      } catch {}
      continue
    }
    if ($RequireContextPackV1 -and (-not $taskBundleFilesAttestSha256 -or -not $taskBundleFilesAttestSha256["pins.json"] -or -not $taskBundleFilesAttestSha256["preflight.json"] -or -not $taskBundleFilesAttestSha256["task.json"] -or -not $taskBundleFilesAttestSha256["manifest.json"])) {
      try {
        Post-Json "$Base/executor/jobs/$jobId/complete" @{
          workerId = $workerId
          exit_code = 1
          stdout = ""
          stderr = "[worker] missing taskBundle files attestation sha256 map (nonce-bound; enterprise fail-closed)"
          attestation_nonce = $attestationNonce
          contextPackV1Id = $contextPackV1Id
          task_bundle_manifest_sha256 = $taskBundleManifestSha256
          context_pack_v1_json_sha256 = $contextPackV1JsonSha256
          task_bundle_files_sha256 = $taskBundleFilesSha256
          context_pack_v1_json_attest_sha256 = $contextPackV1JsonAttestSha256
          task_bundle_files_attest_sha256 = $taskBundleFilesAttestSha256
        } | Out-Null
      } catch {}
      continue
    }

    try { Post-Json "$Base/executor/workers/$workerId/heartbeat" @{ runningJobId = $jobId } | Out-Null } catch {}
    Log-Worker "claimed jobId=$jobId model=$model timeoutMs=$timeoutMs promptChars=$($prompt.Length)"

    try {
      $psi = New-Object System.Diagnostics.ProcessStartInfo
      # Windows PowerShell 5.1 (.NET Framework) lacks ProcessStartInfo.ArgumentList; use a single Arguments string.
      # Also run via cmd.exe so codex.cmd works reliably.

      # Feed prompt via cmd.exe input redirection from a UTF-8 temp file.
      $tmpBase = "scc-codex-" + ([Guid]::NewGuid().ToString("n"))
      $promptFile = Join-Path $env:TEMP ($tmpBase + ".prompt.txt")
      $outFile = Join-Path $env:TEMP ($tmpBase + ".stdout.txt")
      $errFile = Join-Path $env:TEMP ($tmpBase + ".stderr.txt")
      try {
        $utf8 = [System.Text.UTF8Encoding]::new($false)
        [System.IO.File]::WriteAllText($promptFile, [string]$prompt + "`n", $utf8)
      } catch {
        throw
      }

      $psi.FileName = "cmd.exe"
      # Use /S to preserve quotes; wrap the whole command in an extra quote pair per cmd.exe rules.
      # Do NOT use `--json` here; JSON event streams can be very large and risk stdout pipe deadlocks.
      $cmd = '"' + $CodexBin + '" exec --model "' + $model + '" --sandbox read-only --skip-git-repo-check -C "' + $ExecRoot + '" --dangerously-bypass-approvals-and-sandbox < "' + $promptFile + '" 1> "' + $outFile + '" 2> "' + $errFile + '"'
      $psi.Arguments = '/S /C "' + $cmd + '"'
      $psi.WorkingDirectory = $ExecRoot
      $psi.RedirectStandardInput = $false
      $psi.RedirectStandardOutput = $false
      $psi.RedirectStandardError = $false
      $psi.UseShellExecute = $false
      $psi.CreateNoWindow = $true

      $p = New-Object System.Diagnostics.Process
      $p.StartInfo = $psi

      [void]$p.Start()
      Log-Worker "started pid=$($p.Id) cmd=cmd.exe args=$($psi.Arguments) cwd=$($psi.WorkingDirectory)"

      $timedOut = $false
      $stalled = $false
      $canceled = $false
      $sw = [System.Diagnostics.Stopwatch]::StartNew()
      $pollMs = 5000
      $lastProgressAt = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
      $lastOutLen = 0
      $lastErrLen = 0
      while (-not $p.WaitForExit($pollMs)) {
        try {
          $snap = Get-Json "$Base/executor/jobs/$jobId"
          if ($snap -and $snap.status -and ([string]$snap.status) -ne "running") {
            $canceled = $true
            Log-Worker "canceled jobId=$jobId pid=$($p.Id) status=$($snap.status); killing"
            try { & taskkill /PID $p.Id /T /F 1>$null 2>$null } catch { try { $p.Kill() } catch {} }
            break
          }
        } catch {}
        if (-not $timedOut -and $timeoutMs -gt 0 -and $sw.ElapsedMilliseconds -ge $timeoutMs) {
          $timedOut = $true
          Log-Worker "timeout jobId=$jobId pid=$($p.Id) elapsedMs=$($sw.ElapsedMilliseconds) timeoutMs=$timeoutMs; killing"
          try { & taskkill /PID $p.Id /T /F 1>$null 2>$null } catch { try { $p.Kill() } catch {} }
          break
        }
        if (-not $stalled -and $StallSeconds -gt 0) {
          try {
            $outLen = 0
            $errLen = 0
            if (Test-Path $outFile) { $outLen = (Get-Item -LiteralPath $outFile -ErrorAction SilentlyContinue).Length }
            if (Test-Path $errFile) { $errLen = (Get-Item -LiteralPath $errFile -ErrorAction SilentlyContinue).Length }
            if ($outLen -ne $lastOutLen -or $errLen -ne $lastErrLen) {
              $lastOutLen = $outLen
              $lastErrLen = $errLen
              $lastProgressAt = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
            } else {
              $nowMs = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
              if (($nowMs - $lastProgressAt) -ge ($StallSeconds * 1000)) {
                $stalled = $true
                Log-Worker "stall jobId=$jobId pid=$($p.Id) no_output_progress_seconds=$StallSeconds; killing"
                try { & taskkill /PID $p.Id /T /F 1>$null 2>$null } catch { try { $p.Kill() } catch {} }
                break
              }
            }
          } catch {}
        }
        try { Post-Json "$Base/executor/workers/$workerId/heartbeat" @{ runningJobId = $jobId } | Out-Null } catch {}
      }
      if ($timedOut -and -not $p.HasExited) {
        try { $p.WaitForExit(5000) } catch {}
      }
      if ($canceled -and -not $p.HasExited) {
        try { $p.WaitForExit(5000) } catch {}
      }
      if ($canceled) {
        try { if ($promptFile) { Remove-Item -Force -ErrorAction SilentlyContinue -LiteralPath $promptFile } } catch {}
        try { if ($outFile) { Remove-Item -Force -ErrorAction SilentlyContinue -LiteralPath $outFile } } catch {}
        try { if ($errFile) { Remove-Item -Force -ErrorAction SilentlyContinue -LiteralPath $errFile } } catch {}
        # Do not call /complete: the gateway already transitioned the job.
        continue
      }
      $code = if ($p.HasExited) { $p.ExitCode } else { 124 }
      $maxChars = 2000000
      $stdout = Read-TextTailUtf8 $outFile $maxChars
      $stderr = Read-TextTailUtf8 $errFile $maxChars
      if ($timedOut) {
        $code = 124
        $stderr = ($stderr + "`n[worker] timed out after ${timeoutMs}ms").Trim()
      }
      if ($stalled) {
        $code = 124
        $stderr = ($stderr + "`n[worker] stalled (no output progress for ${StallSeconds}s)").Trim()
      }
      if ($code -ne 0 -and (-not $stdout) -and (-not $stderr)) {
        $stderr = ("[worker] codex exited non-zero with empty output. exit_code=$code`n" +
          "file=cmd.exe`n" +
          "args=" + $psi.Arguments + "`n" +
          "cwd=" + $psi.WorkingDirectory).Trim()
      }

      # Avoid massive payloads on completion.
      if ($stdout.Length -gt $maxChars) { $stdout = $stdout.Substring($stdout.Length - $maxChars) }
      if ($stderr.Length -gt $maxChars) { $stderr = $stderr.Substring($stderr.Length - $maxChars) }
      $stdout = Sanitize-ForJson $stdout
      $stderr = Sanitize-ForJson $stderr

      Post-Json "$Base/executor/jobs/$jobId/complete" @{
        workerId = $workerId
        exit_code = $code
        stdout = $stdout
        stderr = $stderr
        attestation_nonce = $attestationNonce
        contextPackV1Id = $contextPackV1Id
        task_bundle_manifest_sha256 = $taskBundleManifestSha256
        context_pack_v1_json_sha256 = $contextPackV1JsonSha256
        task_bundle_files_sha256 = $taskBundleFilesSha256
        context_pack_v1_json_attest_sha256 = $contextPackV1JsonAttestSha256
        task_bundle_files_attest_sha256 = $taskBundleFilesAttestSha256
      } | Out-Null
      Log-Worker "completed jobId=$jobId exit_code=$code stdoutChars=$($stdout.Length) stderrChars=$($stderr.Length)"

      try { if ($promptFile) { Remove-Item -Force -ErrorAction SilentlyContinue -LiteralPath $promptFile } } catch {}
      try { if ($outFile) { Remove-Item -Force -ErrorAction SilentlyContinue -LiteralPath $outFile } } catch {}
      try { if ($errFile) { Remove-Item -Force -ErrorAction SilentlyContinue -LiteralPath $errFile } } catch {}
    } catch {
      $err = $_ | Out-String
      Log-Worker "exception jobId=$jobId err=$err"
      try {
        Post-Json "$Base/executor/jobs/$jobId/complete" @{
          workerId = $workerId
          exit_code = 1
          stdout = ""
          stderr = (Sanitize-ForJson ("[worker] exception while running codex:`n" + $err).Trim())
          attestation_nonce = $attestationNonce
          contextPackV1Id = $contextPackV1Id
          task_bundle_manifest_sha256 = $taskBundleManifestSha256
          context_pack_v1_json_sha256 = $contextPackV1JsonSha256
          task_bundle_files_sha256 = $taskBundleFilesSha256
          context_pack_v1_json_attest_sha256 = $contextPackV1JsonAttestSha256
          task_bundle_files_attest_sha256 = $taskBundleFilesAttestSha256
        } | Out-Null
      } catch {}
      try { if ($promptFile) { Remove-Item -Force -ErrorAction SilentlyContinue -LiteralPath $promptFile } } catch {}
      try { if ($outFile) { Remove-Item -Force -ErrorAction SilentlyContinue -LiteralPath $outFile } } catch {}
      try { if ($errFile) { Remove-Item -Force -ErrorAction SilentlyContinue -LiteralPath $errFile } } catch {}
    }
  } catch {
    # On gateway restart or transient network issues, re-register.
    $script:workerId = $null
    Start-Sleep -Seconds 2
  }
}
