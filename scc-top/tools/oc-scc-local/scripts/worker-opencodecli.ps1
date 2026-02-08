$ErrorActionPreference = "Stop"

$Base = $env:GATEWAY_BASE
if (-not $Base) { $Base = "http://127.0.0.1:18788" }

$ModelDefault = $env:OPENCODE_MODEL
if (-not $ModelDefault) { $ModelDefault = "opencode/glm-4.7-free" }

$Variant = $env:OPENCODE_VARIANT
if (-not $Variant) { $Variant = "high" }

$ExecRoot = $env:EXEC_ROOT
if (-not $ExecRoot) {
  $pkg = Split-Path -Parent $PSScriptRoot
  $repoRoot = Resolve-Path (Join-Path $pkg "..\\..\\..")
  $ExecRoot = Join-Path $repoRoot "opencode-dev"
}

$Bin = $env:OPENCODE_CLI_PATH
if (-not $Bin) {
  $pkg2 = Split-Path -Parent $PSScriptRoot
  $repoRoot2 = Resolve-Path (Join-Path $pkg2 "..\\..\\..")
  $Bin = Join-Path $repoRoot2 "OpenCode\\opencode-cli.exe"
}

$Name = $env:WORKER_NAME
if (-not $Name) { $Name = "opencodecli-worker" }

$IdleExitSeconds = if ($env:WORKER_IDLE_EXIT_SECONDS) { [int]$env:WORKER_IDLE_EXIT_SECONDS } else { 0 }
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
  try {
    Ensure-Worker
    $claimUrl = "$Base/executor/workers/$workerId/claim?executor=opencodecli&waitMs=25000"
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
    $psi.FileName = $Bin
    $psi.ArgumentList.Add("run")
    $psi.ArgumentList.Add("--format"); $psi.ArgumentList.Add("json")
    $psi.ArgumentList.Add("--model"); $psi.ArgumentList.Add($model)
    $psi.ArgumentList.Add("--variant"); $psi.ArgumentList.Add($Variant)
    $psi.ArgumentList.Add($prompt)
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.WorkingDirectory = $ExecRoot

    $psi.Environment["OPENCODE_DISABLE_PROJECT_CONFIG"] = "true"
    $psi.Environment["OPENCODE_CONFIG_CONTENT"] = '{"$schema":"https://opencode.ai/config.json","plugin":[]}'

    $p = New-Object System.Diagnostics.Process
    $p.StartInfo = $psi
    [void]$p.Start()
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
    $script:workerId = $null
    Start-Sleep -Seconds 2
  }
}
