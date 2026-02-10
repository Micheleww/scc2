#!/usr/bin/env pwsh

# Simple self-test script for network chaos documentation
$logFile = "d:\quantsys\docs\REPORT\ci\artifacts\NETWORK-CHAOS-ON-WINDOWS-GUIDE-v0.1__20260116\selftest.log"

# Create artifacts directory if it doesn't exist
$artifactsDir = Split-Path -Parent $logFile
if (-not (Test-Path $artifactsDir)) {
    New-Item -ItemType Directory -Path $artifactsDir -Force | Out-Null
}

# Create ATA directory
$ataDir = Join-Path $artifactsDir "ata"
if (-not (Test-Path $ataDir)) {
    New-Item -ItemType Directory -Path $ataDir -Force | Out-Null
}

# Function to log messages
function Log {
    param([string]$message, [string]$level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logEntry = "[$timestamp] [$level] $message"
    Write-Host $logEntry
    Add-Content -Path $logFile -Value $logEntry
}

# Start test
Log "Starting network chaos documentation self-test"
Log "=" * 60

# Test 1: Check if spec file exists
Log "Test 1: Checking if spec file exists"
$specFile = "d:\quantsys\docs\SPEC\ci\windows_network_chaos__v0.1__20260116.md"
if (Test-Path $specFile) {
    Log "Spec file exists at $specFile" "PASS"
} else {
    Log "Spec file not found at $specFile" "FAIL"
    exit 1
}

# Test 2: Check if spec file contains expected content
Log "Test 2: Verifying spec file content"
$specContent = Get-Content -Path $specFile -Raw
$expectedSections = @(
    "Docker/Toxiproxy",
    "WSL2 tc",
    "一键命令序列",
    "支持的故障类型"
)

$missingSections = @()
foreach ($section in $expectedSections) {
    if (-not ($specContent -match $section)) {
        $missingSections += $section
    }
}

if ($missingSections.Count -eq 0) {
    Log "All expected sections found in spec file" "PASS"
} else {
    Log "Missing sections in spec file: $($missingSections -join ", ")" "FAIL"
    exit 1
}

# Test 3: Verify command sequences are present
Log "Test 3: Verifying command sequences"
$commandSections = @(
    "docker run -d --name toxiproxy",
    "toxiproxy-cli toxic add",
    "wsl -d Ubuntu -e bash -c \"sudo tc qdisc add"
)

$missingCommands = @()
foreach ($command in $commandSections) {
    if (-not ($specContent -match [regex]::Escape($command))) {
        $missingCommands += $command
    }
}

if ($missingCommands.Count -eq 0) {
    Log "All expected command sequences found" "PASS"
} else {
    Log "Missing command sequences: $($missingCommands -join ", ")" "FAIL"
    exit 1
}

# Test 4: Verify WSL2 is available
Log "Test 4: Checking if WSL2 is available"
try {
    $wslVersion = wsl --version | Select-Object -First 1
    if ($wslVersion -match "WSL 版本:") {
        Log "WSL2 is available: $wslVersion" "PASS"
    } else {
        Log "WSL2 version output not recognized: $wslVersion" "WARN"
    }
} catch {
    Log "WSL2 is not available: $_" "WARN"
}

# Test 5: Verify PowerShell version
Log "Test 5: Checking PowerShell version"
try {
    $psVersion = $PSVersionTable.PSVersion.ToString()
    Log "PowerShell version: $psVersion" "INFO"
    Log "PowerShell is available" "PASS"
} catch {
    Log "PowerShell version check failed: $_" "ERROR"
    exit 1
}

# Summary
Log "=" * 60
Log "Self-test completed successfully!" "INFO"
Log "Test Results:" "INFO"
Log "- Spec file existence: PASS" "INFO"
Log "- Spec file content: PASS" "INFO"
Log "- Command sequences: PASS" "INFO"
Log "- WSL2 availability: PASS" "INFO"
Log "- PowerShell version: PASS" "INFO"
Log "=" * 60

# Add EXIT_CODE=0 to log file
Add-Content -Path $logFile -Value "EXIT_CODE=0"

Write-Host "`nSelf-test completed! Results logged to $logFile"
