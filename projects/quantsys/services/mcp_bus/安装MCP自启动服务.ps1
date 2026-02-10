# Install MCP Server AutoStart Service
# Requires Administrator privileges

$ErrorActionPreference = "Continue"

Write-Host "=== Installing MCP Server AutoStart Service ===" -ForegroundColor Cyan
Write-Host ""

# Check administrator privileges
Write-Host "Checking administrator privileges..." -ForegroundColor Yellow
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "ERROR: Administrator privileges required!" -ForegroundColor Red
    Write-Host "Please right-click PowerShell and select 'Run as administrator'" -ForegroundColor Yellow
    exit 1
}
Write-Host "OK: Administrator privileges confirmed" -ForegroundColor Green
Write-Host ""

# Configuration
$taskName = "MCP-Server-AutoStart"
# Use absolute path to avoid encoding issues
$repoRoot = "d:\quantsys"
$mcpBusDir = "$repoRoot\tools\mcp_bus"
$description = "MCP Server Background Service - Auto start on boot"

Write-Host "Configuration:" -ForegroundColor Yellow
Write-Host "  Task Name: $taskName" -ForegroundColor Gray
Write-Host "  Script Directory: $mcpBusDir" -ForegroundColor Gray
Write-Host ""

# Find the background service script using byte comparison (avoids encoding issues)
Write-Host "Searching for background service script..." -ForegroundColor Yellow
$scriptPath = $null

# Target filename
$targetFileName = "启动MCP后台服务.ps1"
$targetBytes = [System.Text.Encoding]::UTF8.GetBytes($targetFileName)

# Enumerate all ps1 files
$allScripts = Get-ChildItem -Path $mcpBusDir -Filter "*.ps1" -ErrorAction SilentlyContinue

foreach ($script in $allScripts) {
    # Use byte-by-byte comparison to avoid encoding issues
    $currentBytes = [System.Text.Encoding]::UTF8.GetBytes($script.Name)
    
    if ($targetBytes.Length -eq $currentBytes.Length) {
        $isMatch = $true
        for ($i = 0; $i -lt $targetBytes.Length; $i++) {
            if ($targetBytes[$i] -ne $currentBytes[$i]) {
                $isMatch = $false
                break
            }
        }
        
        if ($isMatch) {
            $scriptPath = $script.FullName
            Write-Host "  Found script: $($script.Name)" -ForegroundColor Green
            break
        }
    }
}

# Fallback: pattern matching if exact match fails
if (-not $scriptPath) {
    Write-Host "  Exact match failed, trying pattern matching..." -ForegroundColor Gray
    foreach ($script in $allScripts) {
        $name = $script.Name.ToLower()
        $matchCount = 0
        
        # Count matching keywords
        if ($name.Contains("mcp")) { $matchCount++ }
        if ($name.Contains("background") -or $name.Contains("后台")) { $matchCount++ }
        if ($name.Contains("service") -or $name.Contains("服务")) { $matchCount++ }
        if ($name.Contains("start") -or $name.Contains("启动")) { $matchCount++ }
        
        # If 3+ keywords match, likely the right file
        if ($matchCount -ge 3) {
            $scriptPath = $script.FullName
            Write-Host "  Found script by pattern: $($script.Name) (matched $matchCount keywords)" -ForegroundColor Green
            break
        }
    }
}

if (-not $scriptPath) {
    Write-Host "ERROR: Background service script not found!" -ForegroundColor Red
    Write-Host "  Searched in: $mcpBusDir" -ForegroundColor Red
    Write-Host "  Patterns tried: $($patterns -join ', ')" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Available scripts:" -ForegroundColor Yellow
    Get-ChildItem -Path $mcpBusDir -Filter "*.ps1" -ErrorAction SilentlyContinue | ForEach-Object {
        Write-Host "  - $($_.Name)" -ForegroundColor Gray
    }
    exit 1
}

Write-Host "OK: Script file found: $scriptPath" -ForegroundColor Green
Write-Host ""

# Remove existing task if exists
Write-Host "Checking existing task..." -ForegroundColor Yellow
$existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existingTask) {
    Write-Host "Existing task found, removing..." -ForegroundColor Yellow
    try {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction Stop
        Write-Host "OK: Existing task removed" -ForegroundColor Green
        Start-Sleep -Seconds 2
    } catch {
        Write-Host "ERROR: Failed to remove existing task: $_" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "OK: No existing task found" -ForegroundColor Green
}
Write-Host ""

# Create scheduled task
Write-Host "Creating scheduled task..." -ForegroundColor Yellow

# Task action
Write-Host "  Creating task action..." -ForegroundColor Gray
try {
    $action = New-ScheduledTaskAction `
        -Execute "powershell.exe" `
        -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`""
    Write-Host "  OK: Task action created" -ForegroundColor Green
} catch {
    Write-Host "  ERROR: Failed to create task action: $_" -ForegroundColor Red
    exit 1
}

# Task triggers
Write-Host "  Creating triggers..." -ForegroundColor Gray
try {
    $trigger1 = New-ScheduledTaskTrigger -AtStartup
    $trigger2 = New-ScheduledTaskTrigger -Daily -At "03:00AM"
    $trigger = @($trigger1, $trigger2)
    Write-Host "  OK: Triggers created" -ForegroundColor Green
} catch {
    Write-Host "  ERROR: Failed to create triggers: $_" -ForegroundColor Red
    exit 1
}

# Task settings
Write-Host "  Creating task settings..." -ForegroundColor Gray
try {
    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -RunOnlyIfNetworkAvailable:$false `
        -RestartCount 999 `
        -RestartInterval (New-TimeSpan -Minutes 1) `
        -ExecutionTimeLimit (New-TimeSpan -Hours 0) `
        -MultipleInstances IgnoreNew
    Write-Host "  OK: Task settings created" -ForegroundColor Green
} catch {
    Write-Host "  ERROR: Failed to create task settings: $_" -ForegroundColor Red
    exit 1
}

# Task principal
Write-Host "  Creating task principal..." -ForegroundColor Gray
try {
    $principal = New-ScheduledTaskPrincipal `
        -UserId "$env:USERDOMAIN\$env:USERNAME" `
        -LogonType Interactive `
        -RunLevel Highest
    Write-Host "  OK: Task principal created" -ForegroundColor Green
} catch {
    Write-Host "  ERROR: Failed to create task principal: $_" -ForegroundColor Red
    exit 1
}

# Register task
Write-Host "  Registering scheduled task..." -ForegroundColor Gray
try {
    Register-ScheduledTask `
        -TaskName $taskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Principal $principal `
        -Description $description | Out-Null
    
    Write-Host ""
    Write-Host "SUCCESS: Scheduled task created!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Task Information:" -ForegroundColor Yellow
    Write-Host "  Task Name: $taskName" -ForegroundColor Gray
    Write-Host "  Description: $description" -ForegroundColor Gray
    Write-Host "  Triggers: At startup + Daily at 3:00 AM" -ForegroundColor Gray
    Write-Host "  Run Level: Highest" -ForegroundColor Gray
    Write-Host ""
    Write-Host "MCP server will start automatically on next boot" -ForegroundColor Green
    Write-Host ""
    Write-Host "Management Commands:" -ForegroundColor Yellow
    Write-Host "  View task: Get-ScheduledTask -TaskName '$taskName'" -ForegroundColor White
    Write-Host "  Start task: Start-ScheduledTask -TaskName '$taskName'" -ForegroundColor White
    Write-Host "  Stop task: Stop-ScheduledTask -TaskName '$taskName'" -ForegroundColor White
    Write-Host "  Delete task: Unregister-ScheduledTask -TaskName '$taskName' -Confirm:`$false" -ForegroundColor White
    Write-Host ""
    Write-Host "To start server now (optional):" -ForegroundColor Cyan
    Write-Host "  Start-ScheduledTask -TaskName '$taskName'" -ForegroundColor White
    Write-Host ""
    
} catch {
    Write-Host ""
    Write-Host "ERROR: Failed to register scheduled task: $_" -ForegroundColor Red
    $errorMsg = $_.Exception.Message
    Write-Host "Error details: $errorMsg" -ForegroundColor Red
    if ($_.Exception.InnerException) {
        $innerMsg = $_.Exception.InnerException.Message
        Write-Host "Inner error: $innerMsg" -ForegroundColor Red
    }
    exit 1
}
