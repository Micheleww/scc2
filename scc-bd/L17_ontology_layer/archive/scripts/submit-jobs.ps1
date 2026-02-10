# SCC Job Submission Utilities
# Consolidated from: submit_jobs.ps1, submit_jobs2.ps1, submit_jobs_A.ps1, submit_jobs_B.ps1, submit_jobs_C.ps1, submit_one_occli.ps1

$ErrorActionPreference = "Stop"
$script:BaseUrl = "http://127.0.0.1:18788"

function Submit-Job {
    param(
        [Parameter(Mandatory=$true)][string]$Prompt,
        [Parameter(Mandatory=$false)][string]$Executor = "codex",
        [Parameter(Mandatory=$false)][string]$Model = $null,
        [Parameter(Mandatory=$false)][string]$TaskType = "atomic"
    )

    $body = @{
        prompt = $Prompt
        executor = $Executor
        taskType = $TaskType
    }
    if ($Model) { $body.model = $Model }

    $json = ($body | ConvertTo-Json -Compress)
    $resp = Invoke-WebRequest -UseBasicParsing -Method POST -Body $json -ContentType "application/json" "$script:BaseUrl/executor/jobs" -TimeoutSec 30
    return $resp.Content | ConvertFrom-Json
}

function Submit-AtomicJob {
    param(
        [Parameter(Mandatory=$true)][string]$Goal,
        [Parameter(Mandatory=$false)][string[]]$Files = @(),
        [Parameter(Mandatory=$false)][string]$Executor = "codex",
        [Parameter(Mandatory=$false)][string]$Model = $null,
        [Parameter(Mandatory=$false)][int]$TimeoutMs = 0,
        [Parameter(Mandatory=$false)][string]$TaskType = "atomic",
        [Parameter(Mandatory=$false)][string]$Runner = "external"
    )

    $body = @{
        goal = $Goal
        files = $Files
        executor = $Executor
        taskType = $TaskType
        runner = $Runner
    }
    if ($Model) { $body.model = $Model }
    if ($TimeoutMs -gt 0) { $body.timeoutMs = $TimeoutMs }

    $json = ($body | ConvertTo-Json -Depth 6 -Compress)
    $resp = Invoke-WebRequest -UseBasicParsing -Method POST -Body $json -ContentType "application/json" "$script:BaseUrl/executor/jobs/atomic" -TimeoutSec 30
    return $resp.Content | ConvertFrom-Json
}

function Submit-JobsBatch {
    param([array]$Jobs)

    $result = @()
    foreach ($job in $Jobs) {
        $body = ($job | ConvertTo-Json -Compress)
        $resp = Invoke-WebRequest -UseBasicParsing -Method POST -Body $body -ContentType "application/json" "$script:BaseUrl/executor/jobs" -TimeoutSec 30
        $result += ($resp.Content | ConvertFrom-Json)
    }
    return $result | Select-Object id, executor, status, model
}

# Example usage:
<#
$jobs = @(
    @{prompt='Task 1 description'; executor='codex'},
    @{prompt='Task 2 description'; executor='opencodecli'}
)
Submit-JobsBatch -Jobs $jobs

Submit-Job -Prompt "Single task" -Executor "codex"

Submit-AtomicJob -Goal "Complex task" -Files @("file1.ts", "file2.ts") -Model "gpt-5.1-codex-max"
#>

Export-ModuleMember -Function Submit-Job, Submit-AtomicJob, Submit-JobsBatch
