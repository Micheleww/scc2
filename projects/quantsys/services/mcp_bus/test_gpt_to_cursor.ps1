# Test GPT sending message to Cursor via ATA
# This script simulates GPT sending a message to Cursor

$ErrorActionPreference = "Stop"

Write-Host "=== Test GPT to Cursor ATA Communication ===" -ForegroundColor Cyan
Write-Host ""

# MCP server endpoint
$mcpUrl = "http://127.0.0.1:18788/mcp"

# Generate unique task code and message ID
$timestamp = Get-Date -Format "yyyyMMddHHmmss"
$taskCode = "TC-GPT-TO-CURSOR-$timestamp"
$msgId = "ATA-MSG-GPT-$timestamp"

Write-Host "Test Configuration:" -ForegroundColor Yellow
Write-Host "  Task Code: $taskCode" -ForegroundColor Gray
Write-Host "  Message ID: $msgId" -ForegroundColor Gray
Write-Host "  From: ChatGPT" -ForegroundColor Gray
Write-Host "  To: Cursor" -ForegroundColor Gray
Write-Host ""

# Prepare ATA message JSON-RPC request
$requestBody = @{
    jsonrpc = "2.0"
    id = "test-gpt-cursor-001"
    method = "tools/call"
    params = @{
        name = "ata_send"
        arguments = @{
            taskcode = $taskCode
            from_agent = "ChatGPT"
            to_agent = "Cursor"
            kind = "request"
            payload = @{
                action = "test_message"
                message = "Hello from GPT! This is a test message to verify ATA communication."
                timestamp = (Get-Date -Format "o")
                test_data = @{
                    sender = "ChatGPT (via MCP)"
                    receiver = "Cursor (via MCP)"
                    purpose = "Testing ATA message delivery"
                }
            }
        }
    }
} | ConvertTo-Json -Depth 10

Write-Host "Sending ATA message..." -ForegroundColor Yellow
try {
    $response = Invoke-RestMethod -Uri $mcpUrl -Method Post -Body $requestBody -ContentType "application/json" -ErrorAction Stop
    
    Write-Host ""
    if ($response.result.success) {
        Write-Host "SUCCESS: Message sent successfully!" -ForegroundColor Green
        Write-Host ""
        Write-Host "Response:" -ForegroundColor Yellow
        Write-Host ($response | ConvertTo-Json -Depth 10) -ForegroundColor Gray
        
        Write-Host ""
        Write-Host "Message Details:" -ForegroundColor Yellow
        Write-Host "  Message ID: $($response.result.message_id)" -ForegroundColor Gray
        Write-Host "  Task Code: $taskCode" -ForegroundColor Gray
        Write-Host "  File Path: $($response.result.file_path)" -ForegroundColor Gray
        Write-Host "  SHA256: $($response.result.sha256)" -ForegroundColor Gray
        
        Write-Host ""
        Write-Host "Message file location:" -ForegroundColor Cyan
        $msgFile = $response.result.file_path
        if ($msgFile) {
            Write-Host "  $msgFile" -ForegroundColor White
            if (Test-Path $msgFile) {
                Write-Host ""
                Write-Host "Message content:" -ForegroundColor Yellow
                Get-Content $msgFile -Raw | ConvertFrom-Json | ConvertTo-Json -Depth 10 | Write-Host -ForegroundColor Gray
            }
        }
        
        Write-Host ""
        Write-Host "Next step - Test receiving message in Cursor:" -ForegroundColor Cyan
        Write-Host "  Use ata_receive tool in Cursor with:" -ForegroundColor White
        Write-Host "    from_agent: 'ChatGPT'" -ForegroundColor Gray
        Write-Host "    to_agent: 'Cursor'" -ForegroundColor Gray
        Write-Host "    taskcode: '$taskCode'" -ForegroundColor Gray
        
    } else {
        Write-Host "ERROR: Failed to send message" -ForegroundColor Red
        Write-Host "Error: $($response.result.error)" -ForegroundColor Red
    }
} catch {
    Write-Host ""
    Write-Host "ERROR: Failed to send message" -ForegroundColor Red
    Write-Host "Error: $_" -ForegroundColor Red
    
    if ($_.Exception.Response) {
        $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
        $responseBody = $reader.ReadToEnd()
        Write-Host "Response body: $responseBody" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "=== Test Complete ===" -ForegroundColor Cyan
