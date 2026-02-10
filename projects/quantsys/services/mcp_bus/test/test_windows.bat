@echo off
setlocal enabledelayedexpansion

echo Testing MCP Bus - Health Check...
curl -s http://127.0.0.1:18788/health
echo.

echo Testing MCP Bus - Tools List (with token)...
curl -s -X POST http://127.0.0.1:18788/mcp -H "Authorization: Bearer test-token-12345" -H "Content-Type: application/json" -d "{\"jsonrpc\": \"2.0\", \"method\": \"tools/list\"}"
echo.

echo Testing MCP Bus - inbox_append...
curl -s -X POST http://127.0.0.1:18788/api/inbox_append -H "Authorization: Bearer test-token-12345" -H "Content-Type: application/json" -d "{\"date\": \"2026-01-15\", \"task_code\": \"TC-MCP-BRIDGE-0003\", \"source\": \"TestScript\", \"text\": \"Windows PowerShell verification test\"}"
echo.

echo Testing MCP Bus - inbox_tail...
curl -s -X POST http://127.0.0.1:18788/api/inbox_tail -H "Authorization: Bearer test-token-12345" -H "Content-Type: application/json" -d "{\"date\": \"2026-01-15\", \"n\": 10}"
echo.

echo Testing MCP Bus - Tools List (without token - should fail)...
curl -s -X POST http://127.0.0.1:18788/mcp -H "Content-Type: application/json" -d "{\"jsonrpc\": \"2.0\", \"method\": \"tools/list\"}"
echo.

echo.
echo All tests completed!
echo.
echo Check:
echo   - Inbox file: docs\REPORT\inbox\2026-01-15.md
echo   - Audit log: docs\LOG\mcp_bus\2026-01-15.log
pause
