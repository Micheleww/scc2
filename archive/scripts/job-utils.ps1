# SCC Job Utilities
# Consolidated from: poll_jobs.ps1, poll_one_occli.ps1, count_jobs.ps1, dump_jobs.ps1, list_jobs.ps1

$script:BaseUrl = "http://127.0.0.1:18788"

function Get-AllJobs {
    $resp = Invoke-WebRequest -UseBasicParsing "$script:BaseUrl/executor/jobs" -TimeoutSec 10
    return $resp.Content | ConvertFrom-Json
}

function Get-JobStatus {
    param([string]$JobId)
    $all = Get-AllJobs
    return $all | Where-Object { $_.id -eq $JobId }
}

function Watch-Jobs {
    param([int]$Iterations = 9, [int]$IntervalSeconds = 10)
    for ($i = 0; $i -lt $Iterations; $i++) {
        $all = Get-AllJobs
        $running = $all | Where-Object { $_.status -eq 'running' }
        $done = $all | Where-Object { $_.status -ne 'running' }
        Write-Host ("running=" + $running.Count + " done=" + $done.Count)
        $done | Select-Object -First 8 id, executor, status, exit_code | Format-Table
        Start-Sleep -Seconds $IntervalSeconds
    }
}

function Watch-Job {
    param([string]$JobId, [int]$MaxIterations = 12, [int]$IntervalSeconds = 10)
    $done = $false
    for ($i = 0; $i -lt $MaxIterations -and -not $done; $i++) {
        $job = Get-JobStatus -JobId $JobId
        Write-Host ("status=" + $job.status + " lastUpdate=" + $job.lastUpdate)
        if ($job.status -ne 'running') {
            $done = $true
            $job | Select-Object id, status, exit_code | Format-Table
            if ($job.stdout) {
                $job.stdout.Substring(0, [Math]::Min(800, $job.stdout.Length))
            }
        }
        Start-Sleep -Seconds $IntervalSeconds
    }
}

function Get-JobCount {
    $all = Get-AllJobs
    $running = $all | Where-Object { $_.status -eq 'running' }
    $queued = $all | Where-Object { $_.status -eq 'queued' }
    $done = $all | Where-Object { $_.status -eq 'done' -or $_.status -eq 'failed' }
    return [PSCustomObject]@{
        running = $running.Count
        queued = $queued.Count
        done = $done.Count
    }
}

function Get-JobDump {
    param([int]$First = 2)
    $all = Get-AllJobs
    return $all | Select-Object -First $First | ConvertTo-Json -Depth 6
}

function Get-JobList {
    $all = Get-AllJobs
    return $all | Sort-Object createdAt | ForEach-Object {
        [PSCustomObject]@{
            id = $_.id
            executor = $_.executor
            status = $_.status
            model = $_.model
            prompt = ($_.prompt.Substring(0, [Math]::Min(70, $_.prompt.Length)))
