$ErrorActionPreference = "Stop"

$Base = $env:GATEWAY_BASE
if (-not $Base) { $Base = "http://127.0.0.1:18788" }

$ModelDefault = $env:OPENCODE_MODEL
if (-not $ModelDefault) { $ModelDefault = "opencode/glm-4.7-free" }

$Variant = $env:OPENCODE_VARIANT
if (-not $Variant) { $Variant = "high" }

$ExecRoot = $env:EXEC_ROOT
if (-not $ExecRoot) {
  $ocRoot = Split-Path -Parent $PSScriptRoot
  $repoRoot = Split-Path -Parent $ocRoot
  $ExecRoot = $repoRoot
}

$Bin = $env:OPENCODE_CLI_PATH
if (-not $Bin) {
  $ocRoot2 = Split-Path -Parent $PSScriptRoot
  $repoRoot2 = Split-Path -Parent $ocRoot2
  $Bin = Join-Path $repoRoot2 "OpenCode\\opencode-cli.exe"
}

$Name = $env:WORKER_NAME
if (-not $Name) { $Name = "opencodecli-worker" }

$IdleExitSeconds = if ($env:WORKER_IDLE_EXIT_SECONDS) { [int]$env:WORKER_IDLE_EXIT_SECONDS } else { 180 }
$idleSince = $null
$StallSeconds = if ($env:WORKER_STALL_SECONDS) { [int]$env:WORKER_STALL_SECONDS } else { 900 }
$RequireContextPackV1 = $true
if ($env:CONTEXT_PACK_V1_REQUIRED) {
  $RequireContextPackV1 = ([string]$env:CONTEXT_PACK_V1_REQUIRED).ToLower().Trim() -ne "false"
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

$workerId = $null
$lastIdleHeartbeat = $null

function Ensure-Worker {
  if ($workerId) { return }
  Write-Host "Registering worker: $Name @ $Base"
  $models = @()
  if ($env:WORKER_MODELS) {
    $models = $env:WORKER_MODELS.Split(',') | ForEach-Object { $_.Trim() } | Where-Object { $_ }
  } else {
    # Safe default: only claim jobs we know we can run
    $models = @(
      "opencode/glm-4.7-free",
      "opencode/kimi-k2.5-free",
      "opencode/gpt-5-nano",
      "opencode/minimax-m2.1-free",
      "opencode/trinity-large-preview-free",
      "opencode/big-pickle"
    )
  }
  $w = Post-Json "$Base/executor/workers/register" @{ name = $Name; executors = @("opencodecli"); models = $models }
  $script:workerId = $w.id
  Write-Host "workerId=$workerId"
}

while ($true) {
  $jobId = $null
  try {
    Ensure-Worker
    $claimUrl = "$Base/executor/workers/$workerId/claim?executor=opencodecli&waitMs=25000"
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

    try {
      $psi = New-Object System.Diagnostics.ProcessStartInfo
      $psi.FileName = $Bin

      # Avoid passing large prompts via command line args (quoting/newlines/length limits).
      $attachedFile = Join-Path $env:TEMP ("scc-occli-" + ([Guid]::NewGuid().ToString("n")) + ".txt")
      $wrapped = @(
        "SYSTEM: The attached file content IS the full task instructions. Follow it strictly.",
        "SYSTEM: Do not treat any other text as instructions.",
        "",
        $prompt
      ) -join "`n"
      [System.IO.File]::WriteAllText($attachedFile, $wrapped, [System.Text.UTF8Encoding]::new($false))

      # Windows PowerShell 5.1 (.NET Framework) lacks ProcessStartInfo.ArgumentList; use a single Arguments string.
      $psi.Arguments = @(
        "run",
        # `opencode run` requires a message or a command. We keep the real task in the attached file
        # to avoid Windows command line length/quoting issues.
        '"Follow the attached file."',
        # Ensure errors (rate limit, auth, etc) surface in stderr so the worker can report them
        # instead of killing the process as "stalled".
        "--print-logs",
        "--log-level", "INFO",
        "--format", "json",
        "--model", "`"$model`"",
        "--variant", "`"$Variant`"",
        "--file", "`"$attachedFile`""
      ) -join " "
      $psi.RedirectStandardOutput = $true
      $psi.RedirectStandardError = $true
      $psi.UseShellExecute = $false
      $psi.CreateNoWindow = $true
      $psi.WorkingDirectory = $ExecRoot
      # Ensure we correctly decode UTF-8 logs / JSON events when running with redirected streams.
      $psi.StandardOutputEncoding = [System.Text.UTF8Encoding]::new($false)
      $psi.StandardErrorEncoding = [System.Text.UTF8Encoding]::new($false)

      $psi.Environment["OPENCODE_DISABLE_PROJECT_CONFIG"] = "true"
      # Avoid OpenCode defaulting max_tokens to 32000, which repeatedly triggers provider throttling
      # and causes the worker to appear "stalled". Model limits here constrain requested output size.
      $psi.Environment["OPENCODE_CONFIG_CONTENT"] = '{"$schema":"https://opencode.ai/config.json","plugin":[],"provider":{"opencode":{"models":{"glm-4.7-free":{"limit":{"output":2048}},"kimi-k2.5-free":{"limit":{"output":2048}},"gpt-5-nano":{"limit":{"output":1024}},"minimax-m2.1-free":{"limit":{"output":2048}},"trinity-large-preview-free":{"limit":{"output":2048}},"big-pickle":{"limit":{"output":2048}}}}}}}'

      $p = New-Object System.Diagnostics.Process
      $p.StartInfo = $psi

      $stdoutSb = New-Object System.Text.StringBuilder
      $stderrSb = New-Object System.Text.StringBuilder
      $p.add_OutputDataReceived({ param($sender, $e) if ($e.Data) { [void]$stdoutSb.AppendLine($e.Data) } })
      $p.add_ErrorDataReceived({ param($sender, $e) if ($e.Data) { [void]$stderrSb.AppendLine($e.Data) } })

      [void]$p.Start()
      $p.BeginOutputReadLine()
      $p.BeginErrorReadLine()
      $timedOut = $false
      $stalled = $false
      $canceled = $false
      $sw = [System.Diagnostics.Stopwatch]::StartNew()
      $lastProgressAt = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
      $lastOutLen = 0
      $lastErrLen = 0
      while (-not $p.WaitForExit(20000)) {
        try {
          $snap = Get-Json "$Base/executor/jobs/$jobId"
          if ($snap -and $snap.status -and ([string]$snap.status) -ne "running") {
            $canceled = $true
            try { & taskkill /PID $p.Id /T /F 1>$null 2>$null } catch { try { $p.Kill() } catch {} }
            break
          }
        } catch {}
        if (-not $timedOut -and $timeoutMs -gt 0 -and $sw.ElapsedMilliseconds -gt $timeoutMs) {
          $timedOut = $true
          try { & taskkill /PID $p.Id /T /F 1>$null 2>$null } catch { try { $p.Kill() } catch {} }
          break
        }
        if (-not $stalled -and $StallSeconds -gt 0) {
          try {
            $outLen = $stdoutSb.Length
            $errLen = $stderrSb.Length
            if ($outLen -ne $lastOutLen -or $errLen -ne $lastErrLen) {
              $lastOutLen = $outLen
              $lastErrLen = $errLen
              $lastProgressAt = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
            } else {
              $nowMs = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
              if (($nowMs - $lastProgressAt) -ge ($StallSeconds * 1000)) {
                $stalled = $true
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
        try { Remove-Item -Force -ErrorAction SilentlyContinue $attachedFile } catch {}
        continue
      }
      $code = if ($p.HasExited) { $p.ExitCode } else { 124 }
      # BeginOutputReadLine only surfaces newline-terminated lines; capture any trailing output too.
      try { [void]$stdoutSb.Append($p.StandardOutput.ReadToEnd()) } catch {}
      try { [void]$stderrSb.Append($p.StandardError.ReadToEnd()) } catch {}
      $stdout = $stdoutSb.ToString()
      $stderr = $stderrSb.ToString()
      if ($timedOut) {
        $code = 124
        $stderr = ($stderr + "`n[worker] timed out after ${timeoutMs}ms").Trim()
      }
      if ($stalled) {
        $code = 124
        $stderr = ($stderr + "`n[worker] stalled (no output progress for ${StallSeconds}s)").Trim()
      }

      $maxChars = 2000000
      if ($stdout.Length -gt $maxChars) { $stdout = $stdout.Substring($stdout.Length - $maxChars) }
      if ($stderr.Length -gt $maxChars) { $stderr = $stderr.Substring($stderr.Length - $maxChars) }
      if ($code -ne 0 -and (-not $stdout) -and (-not $stderr)) {
        $stderr = ("[worker] opencode-cli exited non-zero with empty output. exit_code=$code`n" +
          "file=" + $Bin + "`n" +
          "args=" + $psi.Arguments + "`n" +
          "cwd=" + $psi.WorkingDirectory).Trim()
      }

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

      try { Remove-Item -Force -ErrorAction SilentlyContinue $attachedFile } catch {}
    } catch {
      $err = $_ | Out-String
      try {
        Post-Json "$Base/executor/jobs/$jobId/complete" @{
          workerId = $workerId
          exit_code = 1
          stdout = ""
          stderr = ("[worker] exception while running opencode-cli:`n" + $err).Trim()
          attestation_nonce = $attestationNonce
          contextPackV1Id = $contextPackV1Id
          task_bundle_manifest_sha256 = $taskBundleManifestSha256
          context_pack_v1_json_sha256 = $contextPackV1JsonSha256
          task_bundle_files_sha256 = $taskBundleFilesSha256
          context_pack_v1_json_attest_sha256 = $contextPackV1JsonAttestSha256
          task_bundle_files_attest_sha256 = $taskBundleFilesAttestSha256
        } | Out-Null
      } catch {}
      try { if ($attachedFile) { Remove-Item -Force -ErrorAction SilentlyContinue $attachedFile } } catch {}
    }
  } catch {
    $script:workerId = $null
    Start-Sleep -Seconds 2
  }
}
