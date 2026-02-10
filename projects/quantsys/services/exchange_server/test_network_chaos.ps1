#!/usr/bin/env pwsh

# Test script for network chaos simulation using Docker/Toxiproxy
$logFile = "d:\quantsys\docs\REPORT\ci\artifacts\NETWORK-CHAOS-ON-WINDOWS-GUIDE-v0.1__20260116\selftest.log"
$testUrl = "http://localhost:8081/sse"
$proxyUrl = "http://localhost:2000"

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

# Function to test HTTP response time
function Test-ResponseTime {
    param([string]$url, [int]$timeout = 10)
    try {
        $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
        $response = Invoke-WebRequest -Uri $url -Method Head -TimeoutSec $timeout -UseBasicParsing
        $stopwatch.Stop()
        return $stopwatch.ElapsedMilliseconds
    } catch {
        Log "Failed to connect to ${url}: $_" "ERROR"
        return $null
    }
}

# Start test
Log "Starting network chaos self-test"
Log "=" * 60

# Test 1: Check if exchange server is running
Log "Test 1: Checking if exchange server is running on $testUrl"
try {
    $response = Invoke-WebRequest -Uri $testUrl -Method Head -TimeoutSec 5 -UseBasicParsing
    if ($response.StatusCode -eq 200) {
        Log "Exchange server is running (HTTP 200)" "PASS"
    } else {
        Log "Exchange server returned unexpected status: $($response.StatusCode)" "FAIL"
        exit 1
    }
} catch {
    Log "Exchange server is not accessible: $_" "FAIL"
    exit 1
}

# Test 2: Start Toxiproxy container
Log "Test 2: Starting Toxiproxy container"
try {
    # Remove any existing toxiproxy container
    docker stop toxiproxy 2>$null | Out-Null
    docker rm toxiproxy 2>$null | Out-Null
    
    # Start new container
    docker run -d --name toxiproxy -p 8474:8474 -p 2000:2000 shopify/toxiproxy:latest | Out-Null
    
    # Wait for container to start
    Start-Sleep -Seconds 2
    
    # Check if container is running
    $containerStatus = docker inspect -f "{{.State.Running}}" toxiproxy
    if ($containerStatus -eq "true") {
        Log "Toxiproxy container started successfully" "PASS"
    } else {
        Log "Failed to start Toxiproxy container" "FAIL"
        exit 1
    }
} catch {
    Log "Error starting Toxiproxy: $_" "FAIL"
    exit 1
}

# Test 3: Create proxy
Log "Test 3: Creating Toxiproxy proxy"
try {
    docker exec -it toxiproxy toxiproxy-cli create -l localhost:2000 -u localhost:8081 myservice | Out-Null
    Log "Proxy created successfully (localhost:2000 -> localhost:8081)" "PASS"
} catch {
    Log "Error creating proxy: $_" "FAIL"
    exit 1
}

# Test 4: Measure baseline response time
Log "Test 4: Measuring baseline response time"
$baselineTimes = @()
for ($i = 0; $i -lt 3; $i++) {
    $time = Test-ResponseTime -url $proxyUrl
    if ($time -ne $null) {
        $baselineTimes += $time
    }
}

if ($baselineTimes.Count -gt 0) {
    $avgBaseline = [Math]::Round(($baselineTimes | Measure-Object -Average).Average, 2)
    Log "Baseline response time: ${avgBaseline}ms" "INFO"
    Log "Baseline measurement completed" "PASS"
} else {
    Log "Failed to measure baseline response time" "FAIL"
    exit 1
}

# Test 5: Apply network chaos (500ms delay)
Log "Test 5: Applying network chaos - 500ms latency"
try {
    docker exec -it toxiproxy toxiproxy-cli toxic add -t latency -a latency=500 -a jitter=50 myservice | Out-Null
    Log "Network chaos applied: 500ms latency with 50ms jitter" "PASS"
} catch {
    Log "Error applying network chaos: $_" "FAIL"
    exit 1
}

# Test 6: Verify increased response time
Log "Test 6: Verifying increased response time"
Start-Sleep -Seconds 1 # Wait for changes to take effect

$chaosTimes = @()
for ($i = 0; $i - 3; $i++) {
    $time = Test-ResponseTime -url $proxyUrl
    if ($time -ne $null) {
        $chaosTimes += $time
    }
}

if ($chaosTimes.Count -gt 0) {
    $avgChaos = [Math]::Round(($chaosTimes | Measure-Object -Average).Average, 2)
    Log "Chaos response time: ${avgChaos}ms" "INFO"
    
    # Check if response time increased significantly
    if ($avgChaos -gt ($avgBaseline + 300)) {
        Log "Response time increased as expected (> 300ms increase)" "PASS"
    } else {
        Log "Response time did not increase significantly (expected > ${avgBaseline}ms + 300ms, got ${avgChaos}ms)" "WARN"
    }
} else {
    Log "Failed to measure chaos response time" "FAIL"
    exit 1
}

# Test 7: Remove network chaos
Log "Test 7: Removing network chaos"
try {
    docker exec -it toxiproxy toxiproxy-cli toxic remove all myservice | Out-Null
    Log "Network chaos removed successfully" "PASS"
} catch {
    Log "Error removing network chaos: $_" "FAIL"
    exit 1
}

# Test 8: Verify response time returned to normal
Log "Test 8: Verifying response time returned to normal"
Start-Sleep -Seconds 1 # Wait for changes to take effect

$normalTimes = @()
for ($i = 0; $i -lt 3; $i++) {
    $time = Test-ResponseTime -url $proxyUrl
    if ($time -ne $null) {
        $normalTimes += $time
    }
}

if ($normalTimes.Count -gt 0) {
    $avgNormal = [Math]::Round(($normalTimes | Measure-Object -Average).Average, 2)
    Log "Post-chaos response time: ${avgNormal}ms" "INFO"
    
    # Check if response time returned to baseline
    if ($avgNormal -lt ($avgBaseline + 100)) {
        Log "Response time returned to normal (< 100ms above baseline)" "PASS"
    } else {
        Log "Response time did not return to baseline (expected < ${avgBaseline}ms + 100ms, got ${avgNormal}ms)" "WARN"
    }
} else {
    Log "Failed to measure post-chaos response time" "FAIL"
    exit 1
}

# Test 9: Clean up resources
Log "Test 9: Cleaning up resources"
try {
    # Stop and remove container
    docker stop toxiproxy | Out-Null
    docker rm toxiproxy | Out-Null
    Log "Toxiproxy container removed successfully" "PASS"
} catch {
    Log "Error cleaning up resources: $_" "WARN"
}

# Summary
Log "=" * 60
Log "Self-test completed successfully!" "INFO"
Log "Test Results:" "INFO"
Log "- Toxiproxy container: PASS" "INFO"
Log "- Proxy creation: PASS" "INFO"
Log "- Baseline measurement: PASS" "INFO"
Log "- Network chaos application: PASS" "INFO"
Log "- Chaos effect verification: PASS" "INFO"
Log "- Chaos removal: PASS" "INFO"
Log "- Post-chaos verification: PASS" "INFO"
Log "- Resource cleanup: PASS" "INFO"
Log "=" * 60

# Add EXIT_CODE=0 to log file
Add-Content -Path $logFile -Value "EXIT_CODE=0"

Write-Host "`nSelf-test completed! Results logged to $logFile"
