# Simulate TRAE connection to local MCP server
# Test various connection scenarios to identify issues

Write-Host "=== Simulating TRAE Connection to Local MCP ===" -ForegroundColor Green
Write-Host ""

$baseUrl = "http://localhost:18788/mcp"
$headers = @{
    "Content-Type" = "application/json"
    "User-Agent" = "TRAE/1.0"
}

# Test 1: GET request (health check)
Write-Host "Test 1: GET /mcp (health check)" -ForegroundColor Cyan
try {
    $response = Invoke-WebRequest -Uri $baseUrl -Method GET -Headers $headers -ErrorAction Stop
    Write-Host "[OK] GET request succeeded" -ForegroundColor Green
    Write-Host "Status Code: $($response.StatusCode)" -ForegroundColor Yellow
    $response.Content | ConvertFrom-Json | ConvertTo-Json -Depth 3
} catch {
    Write-Host "[FAIL] GET request failed: $_" -ForegroundColor Red
    if ($_.Exception.Response) {
        Write-Host "Status Code: $($_.Exception.Response.StatusCode.value__)" -ForegroundColor Yellow
    }
}
Write-Host ""

# Test 2: initialize request
Write-Host "Test 2: initialize request" -ForegroundColor Cyan
$initBody = @{
    jsonrpc = "2.0"
    id = "init-1"
    method = "initialize"
    params = @{
        protocolVersion = "2024-11-05"
        capabilities = @{}
        clientInfo = @{
            name = "TRAE"
            version = "1.0.0"
        }
    }
} | ConvertTo-Json -Depth 10

try {
    $response = Invoke-RestMethod -Uri $baseUrl -Method POST -Headers $headers -Body $initBody -ErrorAction Stop
    Write-Host "[OK] initialize succeeded" -ForegroundColor Green
    $response | ConvertTo-Json -Depth 5
} catch {
    Write-Host "[FAIL] initialize failed: $_" -ForegroundColor Red
    if ($_.Exception.Response) {
        $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
        $responseBody = $reader.ReadToEnd()
        Write-Host "Response: $responseBody" -ForegroundColor Yellow
    }
}
Write-Host ""

# Test 3: tools/list request
Write-Host "Test 3: tools/list request" -ForegroundColor Cyan
$toolsBody = @{
    jsonrpc = "2.0"
    id = "tools-1"
    method = "tools/list"
    params = @{}
} | ConvertTo-Json -Depth 10

try {
    $response = Invoke-RestMethod -Uri $baseUrl -Method POST -Headers $headers -Body $toolsBody -ErrorAction Stop
    Write-Host "[OK] tools/list succeeded" -ForegroundColor Green
    Write-Host "Tool count: $($response.result.tools.Count)" -ForegroundColor Yellow
    $response.result.tools | ForEach-Object { Write-Host "  - $($_.name)" }
} catch {
    Write-Host "[FAIL] tools/list failed: $_" -ForegroundColor Red
    if ($_.Exception.Response) {
        $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
        $responseBody = $reader.ReadToEnd()
        Write-Host "Response: $responseBody" -ForegroundColor Yellow
    }
}
Write-Host ""

# Test 4: ping tool call
Write-Host "Test 4: ping tool call" -ForegroundColor Cyan
$pingBody = @{
    jsonrpc = "2.0"
    id = "ping-1"
    method = "tools/call"
    params = @{
        name = "ping"
        arguments = @{}
    }
} | ConvertTo-Json -Depth 10

try {
    $response = Invoke-RestMethod -Uri $baseUrl -Method POST -Headers $headers -Body $pingBody -ErrorAction Stop
    Write-Host "[OK] ping call succeeded" -ForegroundColor Green
    $response | ConvertTo-Json -Depth 5
} catch {
    Write-Host "[FAIL] ping call failed: $_" -ForegroundColor Red
    if ($_.Exception.Response) {
        $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
        $responseBody = $reader.ReadToEnd()
        Write-Host "Response: $responseBody" -ForegroundColor Yellow
    }
}
Write-Host ""

# Test 5: Simulate TRAE full connection flow
Write-Host "Test 5: Simulate TRAE full connection flow" -ForegroundColor Cyan
Write-Host "Step 1: GET health check" -ForegroundColor Yellow
try {
    $health = Invoke-WebRequest -Uri $baseUrl -Method GET -ErrorAction Stop
    Write-Host "  [OK] Health check passed" -ForegroundColor Green
} catch {
    Write-Host "  [FAIL] Health check failed: $_" -ForegroundColor Red
}

Write-Host "Step 2: initialize" -ForegroundColor Yellow
try {
    $init = Invoke-RestMethod -Uri $baseUrl -Method POST -Headers $headers -Body $initBody -ErrorAction Stop
    Write-Host "  [OK] initialize succeeded" -ForegroundColor Green
} catch {
    Write-Host "  [FAIL] initialize failed: $_" -ForegroundColor Red
}

Write-Host "Step 3: tools/list" -ForegroundColor Yellow
try {
    $tools = Invoke-RestMethod -Uri $baseUrl -Method POST -Headers $headers -Body $toolsBody -ErrorAction Stop
    Write-Host "  [OK] tools/list succeeded, tool count: $($tools.result.tools.Count)" -ForegroundColor Green
} catch {
    Write-Host "  [FAIL] tools/list failed: $_" -ForegroundColor Red
}

Write-Host ""

# Test 6: Check response format compliance
Write-Host "Test 6: Check response format compliance" -ForegroundColor Cyan
try {
    $response = Invoke-RestMethod -Uri $baseUrl -Method POST -Headers $headers -Body $initBody -ErrorAction Stop
    
    $checks = @{
        "has_jsonrpc" = $response.jsonrpc -eq "2.0"
        "has_id" = $null -ne $response.id
        "has_result" = $null -ne $response.result
        "result_has_protocolVersion" = $null -ne $response.result.protocolVersion
        "result_has_serverInfo" = $null -ne $response.result.serverInfo
        "result_has_capabilities" = $null -ne $response.result.capabilities
    }
    
    Write-Host "Response format check:" -ForegroundColor Yellow
    foreach ($check in $checks.GetEnumerator()) {
        $status = if ($check.Value) { "[OK]" } else { "[FAIL]" }
        $color = if ($check.Value) { "Green" } else { "Red" }
        Write-Host "  $status $($check.Key)" -ForegroundColor $color
    }
} catch {
    Write-Host "[FAIL] Cannot check response format: $_" -ForegroundColor Red
}
Write-Host ""

# Test 7: Check server logs
Write-Host "Test 7: Check server logs" -ForegroundColor Cyan
$today = Get-Date -Format "yyyy-MM-dd"
$logFile = "tools\mcp_bus\docs\LOG\mcp_bus\$today.jsonl"
if (Test-Path $logFile) {
    Write-Host "[OK] Found log file: $logFile" -ForegroundColor Green
    $logs = Get-Content $logFile -Tail 10 | ForEach-Object { $_ | ConvertFrom-Json -ErrorAction SilentlyContinue }
    if ($logs) {
        Write-Host "Recent log entries:" -ForegroundColor Yellow
        $logs | Select-Object -Last 5 | ForEach-Object {
            $statusColor = if ($_.result) { "Green" } else { "Red" }
            Write-Host "  [$($_.timestamp)] $($_.tool) - $($_.result) - $($_.caller)" -ForegroundColor $statusColor
        }
    } else {
        Write-Host "[WARN] Log file is empty or malformed" -ForegroundColor Yellow
    }
} else {
    Write-Host "[WARN] Log file does not exist: $logFile" -ForegroundColor Yellow
    Write-Host "  Possible reasons: Server not logging or log directory missing" -ForegroundColor Yellow
}
Write-Host ""

# Test 8: Check server process
Write-Host "Test 8: Check server process" -ForegroundColor Cyan
$processes = Get-Process | Where-Object { $_.ProcessName -like "*python*" -or $_.ProcessName -like "*uvicorn*" }
if ($processes) {
    Write-Host "[OK] Found Python processes:" -ForegroundColor Green
    $processes | Select-Object ProcessName, Id, StartTime | Format-Table
} else {
    Write-Host "[FAIL] No Python processes found" -ForegroundColor Red
}
Write-Host ""

# Test 9: Check port listening
Write-Host "Test 9: Check port listening" -ForegroundColor Cyan
$listening = netstat -ano | Select-String ":8000.*LISTENING"
if ($listening) {
    Write-Host "[OK] Port 8000 is listening" -ForegroundColor Green
    $listening | ForEach-Object { Write-Host "  $_" }
} else {
    Write-Host "[FAIL] Port 8000 is not listening" -ForegroundColor Red
}
Write-Host ""

Write-Host "=== Test Complete ===" -ForegroundColor Green
