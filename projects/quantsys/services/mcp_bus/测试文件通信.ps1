# 测试GPT与TRAE文件通信功能
# 验证inbox和board工具是否正常工作

$ErrorActionPreference = "Stop"

Write-Host "=== 测试GPT与TRAE文件通信 ===" -ForegroundColor Cyan
Write-Host ""

$baseUrl = "http://localhost:8000/mcp"
$headers = @{
    "Content-Type" = "application/json"
    "User-Agent" = "Test-Script"
}

$today = Get-Date -Format "yyyy-MM-dd"

# 测试1: inbox_append - 写入收件箱
Write-Host "测试1: inbox_append (写入收件箱)" -ForegroundColor Yellow
$appendBody = @{
    jsonrpc = "2.0"
    id = "test-append-1"
    method = "tools/call"
    params = @{
        name = "inbox_append"
        arguments = @{
            date = $today
            task_code = "TC-TEST-001"
            source = "Test-Script"
            text = "这是一条测试消息，用于验证文件通信功能。"
        }
    }
} | ConvertTo-Json -Depth 10

try {
    $response = Invoke-RestMethod -Uri $baseUrl -Method POST -Headers $headers -Body $appendBody -ErrorAction Stop
    Write-Host "[OK] Write successful" -ForegroundColor Green
    $response | ConvertTo-Json -Depth 5
} catch {
    Write-Host "[FAIL] Write failed: $_" -ForegroundColor Red
    if ($_.Exception.Response) {
        $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
        $responseBody = $reader.ReadToEnd()
        Write-Host "响应: $responseBody" -ForegroundColor Yellow
    }
}
Write-Host ""

# 测试2: inbox_tail - 读取收件箱
Write-Host "测试2: inbox_tail (读取收件箱)" -ForegroundColor Yellow
$tailBody = @{
    jsonrpc = "2.0"
    id = "test-tail-1"
    method = "tools/call"
    params = @{
        name = "inbox_tail"
        arguments = @{
            date = $today
            n = 50
        }
    }
} | ConvertTo-Json -Depth 10

try {
    $response = Invoke-RestMethod -Uri $baseUrl -Method POST -Headers $headers -Body $tailBody -ErrorAction Stop
    Write-Host "✅ 读取成功" -ForegroundColor Green
    $content = $response.result.content[0].text
    Write-Host "内容预览:" -ForegroundColor Cyan
    $content.Substring(0, [Math]::Min(200, $content.Length))
    if ($content.Length -gt 200) {
        Write-Host "... (共 $($content.Length) 字符)" -ForegroundColor Gray
    }
} catch {
    Write-Host "❌ 读取失败: $_" -ForegroundColor Red
}
Write-Host ""

# 测试3: board_set_status - 更新程序板
Write-Host "测试3: board_set_status (更新程序板)" -ForegroundColor Yellow
$boardSetBody = @{
    jsonrpc = "2.0"
    id = "test-board-set-1"
    method = "tools/call"
    params = @{
        name = "board_set_status"
        arguments = @{
            task_code = "TC-TEST-001"
            status = "in_progress"
            artifacts = "docs/REPORT/artifacts/TC-TEST-001/"
        }
    }
} | ConvertTo-Json -Depth 10

try {
    $response = Invoke-RestMethod -Uri $baseUrl -Method POST -Headers $headers -Body $boardSetBody -ErrorAction Stop
    Write-Host "[OK] Update successful" -ForegroundColor Green
    $response | ConvertTo-Json -Depth 5
} catch {
    Write-Host "[FAIL] Update failed: $_" -ForegroundColor Red
}
Write-Host ""

# 测试4: board_get - 读取程序板
Write-Host "测试4: board_get (读取程序板)" -ForegroundColor Yellow
$boardGetBody = @{
    jsonrpc = "2.0"
    id = "test-board-get-1"
    method = "tools/call"
    params = @{
        name = "board_get"
        arguments = @{}
    }
} | ConvertTo-Json -Depth 10

try {
    $response = Invoke-RestMethod -Uri $baseUrl -Method POST -Headers $headers -Body $boardGetBody -ErrorAction Stop
    Write-Host "✅ 读取成功" -ForegroundColor Green
    $content = $response.result.content[0].text
    Write-Host "内容预览:" -ForegroundColor Cyan
    $content.Substring(0, [Math]::Min(300, $content.Length))
    if ($content.Length -gt 300) {
        Write-Host "... (共 $($content.Length) 字符)" -ForegroundColor Gray
    }
} catch {
    Write-Host "❌ 读取失败: $_" -ForegroundColor Red
}
Write-Host ""

# 测试5: 验证文件是否存在
Write-Host "测试5: 验证文件系统" -ForegroundColor Yellow
$inboxFile = "docs\REPORT\inbox\$today.md"
$boardFile = "docs\REPORT\QCC-PROGRAM-BOARD-v0.1.md"

if (Test-Path $inboxFile) {
    Write-Host "[OK] Inbox file exists: $inboxFile" -ForegroundColor Green
    $fileSize = (Get-Item $inboxFile).Length
    Write-Host "   File size: $fileSize bytes" -ForegroundColor Gray
} else {
    Write-Host "[WARN] Inbox file not found: $inboxFile" -ForegroundColor Yellow
}

if (Test-Path $boardFile) {
    Write-Host "[OK] Board file exists: $boardFile" -ForegroundColor Green
    $fileSize = (Get-Item $boardFile).Length
    Write-Host "   File size: $fileSize bytes" -ForegroundColor Gray
} else {
    Write-Host "[WARN] Board file not found: $boardFile" -ForegroundColor Yellow
}
Write-Host ""

Write-Host "=== 测试完成 ===" -ForegroundColor Green
Write-Host ""
Write-Host "下一步:" -ForegroundColor Yellow
Write-Host "  1. 在TRAE中测试工具调用" -ForegroundColor White
Write-Host "  2. 在GPT中测试工具调用" -ForegroundColor White
Write-Host "  3. 验证双向通信" -ForegroundColor White
