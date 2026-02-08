$ErrorActionPreference = "Stop"

$Base = $env:GATEWAY_BASE
if (-not $Base) { $Base = "http://127.0.0.1:18788" }

$ModelDefault = $env:CODEX_MODEL
if (-not $ModelDefault) { $ModelDefault = "gpt-5.1-codex-max" }

$ExecRoot = $env:EXEC_ROOT
if (-not $ExecRoot) {
  $pkg = Split-Path -Parent $PSScriptRoot
  $repoRoot = Resolve-Path (Join-Path $pkg "..\\..\\..")
  $ExecRoot = Join-Path $repoRoot "opencode-dev"
}

$Name = $env:WORKER_NAME
if (-not $Name) { $Name = "codex-worker" }

$IdleExitSeconds = if ($env:WORKER_IDLE_EXIT_SECONDS) { [int]$env:WORKER_IDLE_EXIT_SECONDS } else { 180 }
$idleSince = $null

function Post-Json($url, $obj) {
  $json = ($obj | ConvertTo-Json -Depth 8 -Compress)
  (Invoke-WebRequest -UseBasicParsing -Method POST -ContentType "application/json" -Body $json -TimeoutSec 30 $url).Content | ConvertFrom-Json
}

$workerId = $null

function Ensure-Worker {
  if ($workerId) { return }
  Write-Host "Registering worker: $Name @ $Base"
  $models = @()
  if ($env:WORKER_MODELS) {
    $models = $env:WORKER_MODELS.Split(',') | ForEach-Object { $_.Trim() } | Where-Object { $_ }
  } else {
    # Safe default: only claim jobs we know we can run
    $models = @("gpt-5.1-codex-max")
  }
  $w = Post-Json "$Base/executor/workers/register" @{ name = $Name; executors = @("codex"); models = $models }
  $script:workerId = $w.id
  Write-Host "workerId=$workerId"
}

while ($true) {
  try {
    Ensure-Worker
    $claimUrl = "$Base/executor/workers/$workerId/claim?executor=codex&waitMs=25000"
    $resp = Invoke-WebRequest -UseBasicParsing -TimeoutSec 35 $claimUrl
    if ($resp.StatusCode -eq 204) {
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
    $timeoutMs = 0
    if ($job.timeoutMs -ne $null) {
      try { $timeoutMs = [int]$job.timeoutMs } catch { $timeoutMs = 0 }
    }

    Post-Json "$Base/executor/workers/$workerId/heartbeat" @{ runningJobId = $jobId } | Out-Null

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = "codex"
    $psi.ArgumentList.Add("exec")
    $psi.ArgumentList.Add("--model"); $psi.ArgumentList.Add($model)
    $psi.ArgumentList.Add("--sandbox"); $psi.ArgumentList.Add("read-only")
    $psi.ArgumentList.Add("--skip-git-repo-check")
    $psi.ArgumentList.Add("--json")
    $psi.ArgumentList.Add("-C"); $psi.ArgumentList.Add($ExecRoot)
    $psi.ArgumentList.Add("--dangerously-bypass-approvals-and-sandbox")
    $psi.RedirectStandardInput = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true

    $p = New-Object System.Diagnostics.Process
    $p.StartInfo = $psi
    [void]$p.Start()
    $p.StandardInput.WriteLine($prompt)
    $p.StandardInput.Close()

    $timedOut = $false
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    while (-not $p.WaitForExit(20000)) {
      if (-not $timedOut -and $timeoutMs -gt 0 -and $sw.ElapsedMilliseconds -gt $timeoutMs) {
        $timedOut = $true
        try { $p.Kill() } catch {}
        break
      }
      try { Post-Json "$Base/executor/workers/$workerId/heartbeat" @{ runningJobId = $jobId } | Out-Null } catch {}
    }
    $stdout = $p.StandardOutput.ReadToEnd()
    $stderr = $p.StandardError.ReadToEnd()
    $code = $p.ExitCode
    if ($timedOut) {
      $code = 124
      $stderr = ($stderr + "`n[worker] timed out after ${timeoutMs}ms").Trim()
    }

    Post-Json "$Base/executor/jobs/$jobId/complete" @{
      workerId = $workerId
      exit_code = $code
      stdout = $stdout
      stderr = $stderr
    } | Out-Null
  } catch {
    # On gateway restart or transient network issues, re-register.
    $script:workerId = $null
    Start-Sleep -Seconds 2
  }
}
