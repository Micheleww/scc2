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
if (-not $ExecRoot) { $ExecRoot = "C:\\scc" }

$Name = $env:WORKER_NAME
if (-not $Name) { $Name = "codex-worker" }

$IdleExitSeconds = if ($env:WORKER_IDLE_EXIT_SECONDS) { [int]$env:WORKER_IDLE_EXIT_SECONDS } else { 180 }
$idleSince = $null
$StallSeconds = if ($env:WORKER_STALL_SECONDS) { [int]$env:WORKER_STALL_SECONDS } else { 240 }

try { New-Item -ItemType Directory -Force -Path "C:\\scc\\artifacts\\executor_logs\\workers" | Out-Null } catch {}
$WorkerLogFile = Join-Path "C:\\scc\\artifacts\\executor_logs\\workers" ($Name + ".log")
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
    $timeoutMs = 0
    if ($job.timeoutMs -ne $null) {
      try { $timeoutMs = [int]$job.timeoutMs } catch { $timeoutMs = 0 }
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
