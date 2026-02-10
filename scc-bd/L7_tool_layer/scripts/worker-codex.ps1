$ErrorActionPreference = "Stop"

# Import shared worker utilities
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$utilsPath = Join-Path $scriptDir "lib\worker-utils.ps1"
if (Test-Path $utilsPath) {
    . $utilsPath
} else {
    throw "worker-utils.ps1 not found at $utilsPath"
}

# Worker-specific configuration
$Base = Get-EnvOrDefault "GATEWAY_BASE" "http://127.0.0.1:18788"
$ModelDefault = Get-EnvOrDefault "CODEX_MODEL" "gpt-5.3-codex"
$Name = Get-EnvOrDefault "WORKER_NAME" "codex-worker"
$IdleExitSeconds = Get-EnvOrDefaultInt "WORKER_IDLE_EXIT_SECONDS" 180
$StallSeconds = Get-EnvOrDefaultInt "WORKER_STALL_SECONDS" 240
$RequireContextPackV1 = Get-EnvBool "CONTEXT_PACK_V1_REQUIRED" $true

# Codex binary path resolution
$CodexBin = $env:CODEX_BIN
if (-not $CodexBin) {
  $candidate = Join-Path $env:APPDATA "npm\codex.cmd"
  if (Test-Path $candidate) { $CodexBin = $candidate } else { $CodexBin = "codex" }
}

# Execution root
$ExecRoot = $env:EXEC_ROOT
if (-not $ExecRoot) { $ExecRoot = Get-ExecRoot $PSScriptRoot }

# Initialize logging
$WorkerLogFile = Initialize-WorkerLog $Name
function Log-Local([string]$msg) { Log-Worker $WorkerLogFile $msg }

# Worker state
$workerId = $null
$lastIdleHeartbeat = $null
$idleSince = $null

function Ensure-Worker {
  if ($workerId) { return }
  Write-Host "Registering worker: $Name @ $Base"
  Log-Local "register base=$Base name=$Name"
  $models = @()
  if ($env:WORKER_MODELS) {
    $models = $env:WORKER_MODELS.Split(',') | ForEach-Object { $_.Trim() } | Where-Object { $_ }
  } else {
    $models = @("gpt-5.3-codex","gpt-5.2","gpt-5.1-codex-max")
  }
  $w = Post-Json "$Base/executor/workers/register" @{ name = $Name; executors = @("codex"); models = $models }
  $script:workerId = $w.id
  Write-Host "workerId=$workerId"
  Log-Local "registered workerId=$workerId models=$($models -join ',')"
}

while ($true) {
  $jobId = $null
  try {
    Ensure-Worker
    $claimUrl = "$Base/executor/workers/$workerId/claim?executor=codex&waitMs=25000"
    $resp = Invoke-WebRequest -UseBasicParsing -TimeoutSec 35 $claimUrl
    if ($resp.StatusCode -eq 204) {
      if (-not $lastIdleHeartbeat -or (New-TimeSpan -Start $lastIdleHeartbeat -End (Get-Date)).TotalSeconds -ge 25) {
        try { Post-Json "$Base/executor/workers/$workerId/heartbeat" @{ runningJobId = $null } | Out-Null } catch {}
        $lastIdleHeartbeat = Get-Date
      }
      if ($IdleExitSeconds -gt 0) {
        if (-not $idleSince) { $idleSince = Get-Date }
        if ((New-TimeSpan -Start $idleSince -End (Get-Date)).TotalSeconds -ge $IdleExitSeconds) { exit 0 }
      }
      continue
    }
    
    $job = $resp.Content | ConvertFrom-Json
    $idleSince = $null
    $jobId = $job.id
    $model = if ($job.model) { [string]$job.model } else { $ModelDefault }
    $prompt = [string]$job.prompt
    
    # Get attestation and context pack info
    $attestationNonce = $null
    if ($job.PSObject.Properties.Name -contains "attestation" -and $job.attestation -and ($job.attestation.PSObject.Properties.Name -contains "nonce")) {
      $attestationNonce = [string]$job.attestation.nonce
    }
    $contextPackV1Id = if ($job.PSObject.Properties.Name -contains "contextPackV1Id") { [string]$job.contextPackV1Id } else { $null }
    
    # Fetch task bundle files
    $bundleResult = Fetch-TaskBundleFiles $job $Base $attestationNonce
    $taskBundleManifestSha256 = $bundleResult.manifestSha256
    $taskBundleFilesSha256 = $bundleResult.filesSha256
    $taskBundleFilesAttestSha256 = $bundleResult.attestSha256
    
    # Fetch context pack v1
    $cpResult = Fetch-ContextPackV1 $job $Base $attestationNonce
    $contextPackV1JsonSha256 = $cpResult.jsonSha256
    $contextPackV1JsonAttestSha256 = $cpResult.attestSha256
    
    # Validate context pack v1 requirements
    $validation = Test-ContextPackV1Required $job $Base $workerId $RequireContextPackV1
    if (-not $validation.valid) {
      Post-Json "$Base/executor/jobs/$jobId/complete" @{
        workerId = $workerId; exit_code = 1; stdout = ""; stderr = $validation.error
        attestation_nonce = $attestationNonce; contextPackV1Id = $contextPackV1Id
        task_bundle_manifest_sha256 = $taskBundleManifestSha256
        context_pack_v1_json_sha256 = $contextPackV1JsonSha256
        task_bundle_files_sha256 = $taskBundleFilesSha256
        context_pack_v1_json_attest_sha256 = $contextPackV1JsonAttestSha256
        task_bundle_files_attest_sha256 = $taskBundleFilesAttestSha256
      } | Out-Null
      continue
    }
    
    $timeoutMs = if ($job.timeoutMs -ne $null) { [int]$job.timeoutMs } else { 0 }
    try { Post-Json "$Base/executor/workers/$workerId/heartbeat" @{ runningJobId = $jobId } | Out-Null } catch {}
    Log-Local "claimed jobId=$jobId model=$model timeoutMs=$timeoutMs promptChars=$($prompt.Length)"
    
    # Execute codex
    try {
      $tmpBase = "scc-codex-" + ([Guid]::NewGuid().ToString("n"))
      $promptFile = Join-Path $env:TEMP ($tmpBase + ".prompt.txt")
      $outFile = Join-Path $env:TEMP ($tmpBase + ".stdout.txt")
      $errFile = Join-Path $env:TEMP ($tmpBase + ".stderr.txt")
      
      $utf8 = [System.Text.UTF8Encoding]::new($false)
      [System.IO.File]::WriteAllText($promptFile, [string]$prompt + "`n", $utf8)
      
      $psi = New-Object System.Diagnostics.ProcessStartInfo
      $psi.FileName = "cmd.exe"
      $cmd = '"' + $CodexBin + '" exec --model "' + $model + '" --sandbox read-only --skip-git-repo-check -C "' + $ExecRoot + '" --dangerously-bypass-approvals-and-sandbox < "' + $promptFile + '" 1> "' + $outFile + '" 2> "' + $errFile + '"'
      $psi.Arguments = '/S /C "' + $cmd + '"'
      $psi.WorkingDirectory = $ExecRoot
      $psi.UseShellExecute = $false
      $psi.CreateNoWindow = $true
      
      $p = New-Object System.Diagnostics.Process
      $p.StartInfo = $psi
      [void]$p.Start()
      Log-Local "started pid=$($p.Id)"
      
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
            Log-Local "canceled jobId=$jobId"
            try { & taskkill /PID $p.Id /T /F 1>$null 2>$null } catch { try { $p.Kill() } catch {} }
            break
          }
        } catch {}
        
        if (-not $timedOut -and $timeoutMs -gt 0 -and $sw.ElapsedMilliseconds -ge $timeoutMs) {
          $timedOut = $true
          Log-Local "timeout jobId=$jobId"
          try { & taskkill /PID $p.Id /T /F 1>$null 2>$null } catch { try { $p.Kill() } catch {} }
          break
        }
        
        if (-not $stalled -and $StallSeconds -gt 0) {
          try {
            $outLen = if (Test-Path $outFile) { (Get-Item -LiteralPath $outFile -ErrorAction SilentlyContinue).Length } else { 0 }
            $errLen = if (Test-Path $errFile) { (Get-Item -LiteralPath $errFile -ErrorAction SilentlyContinue).Length } else { 0 }
            if ($outLen -ne $lastOutLen -or $errLen -ne $lastErrLen) {
              $lastOutLen = $outLen; $lastErrLen = $errLen
              $lastProgressAt = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
            } elseif (([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() - $lastProgressAt) -ge ($StallSeconds * 1000)) {
              $stalled = $true
              Log-Local "stall jobId=$jobId"
              try { & taskkill /PID $p.Id /T /F 1>$null 2>$null } catch { try { $p.Kill() } catch {} }
              break
            }
          } catch {}
        }
        try { Post-Json "$Base/executor/workers/$workerId/heartbeat" @{ runningJobId = $jobId } | Out-Null } catch {}
      }
      
      if ($canceled) {
        try { Remove-Item -Force -ErrorAction SilentlyContinue -LiteralPath $promptFile, $outFile, $errFile } catch {}
        continue
      }
      
      $code = if ($p.HasExited) { $p.ExitCode } else { 124 }
      $maxChars = 2000000
      $stdout = Read-TextTailUtf8 $outFile $maxChars
      $stderr = Read-TextTailUtf8 $errFile $maxChars
      
      if ($timedOut) { $code = 124; $stderr = ($stderr + "`n[worker] timed out after ${timeoutMs}ms").Trim() }
      if ($stalled) { $code = 124; $stderr = ($stderr + "`n[worker] stalled (no output progress for ${StallSeconds}s)").Trim() }
      
      $stdout = Sanitize-ForJson $stdout
      $stderr = Sanitize-ForJson $stderr
      
      Post-Json "$Base/executor/jobs/$jobId/complete" @{
        workerId = $workerId; exit_code = $code; stdout = $stdout; stderr = $stderr
        attestation_nonce = $attestationNonce; contextPackV1Id = $contextPackV1Id
        task_bundle_manifest_sha256 = $taskBundleManifestSha256
        context_pack_v1_json_sha256 = $contextPackV1JsonSha256
        task_bundle_files_sha256 = $taskBundleFilesSha256
        context_pack_v1_json_attest_sha256 = $contextPackV1JsonAttestSha256
        task_bundle_files_attest_sha256 = $taskBundleFilesAttestSha256
      } | Out-Null
      Log-Local "completed jobId=$jobId exit_code=$code"
      
      try { Remove-Item -Force -ErrorAction SilentlyContinue -LiteralPath $promptFile, $outFile, $errFile } catch {}
    } catch {
      $err = $_ | Out-String
      Log-Local "exception jobId=$jobId err=$err"
      try {
        Post-Json "$Base/executor/jobs/$jobId/complete" @{
          workerId = $workerId; exit_code = 1; stdout = ""; stderr = (Sanitize-ForJson $err)
          attestation_nonce = $attestationNonce; contextPackV1Id = $contextPackV1Id
          task_bundle_manifest_sha256 = $taskBundleManifestSha256
          context_pack_v1_json_sha256 = $contextPackV1JsonSha256
          task_bundle_files_sha256 = $taskBundleFilesSha256
          context_pack_v1_json_attest_sha256 = $contextPackV1JsonAttestSha256
          task_bundle_files_attest_sha256 = $taskBundleFilesAttestSha256
        } | Out-Null
      } catch {}
      try { Remove-Item -Force -ErrorAction SilentlyContinue -LiteralPath $promptFile, $outFile, $errFile } catch {}
    }
  } catch {
    $script:workerId = $null
    Start-Sleep -Seconds 2
  }
}
