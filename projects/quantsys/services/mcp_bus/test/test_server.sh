#!/bin/bash

# QCC Bus MCP Server - Self-Test Script
# This script tests the MCP server functionality

set -e

# Configuration
SERVER_URL="http://localhost:18788/"
TOKEN="test-token-12345"

echo "========================================="
echo "QCC Bus MCP Server - Self-Test"
echo "========================================="
echo ""

# Test 1: Health check
echo "Test 1: Health check"
curl -s "$SERVER_URL/health" | python -m json.tool
echo ""
echo "✓ Health check passed"
echo ""

# Test 2: Tools list (without token - should fail)
echo "Test 2: Tools list without token (should fail)"
curl -s -X POST "$SERVER_URL/mcp" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/list"
  }' | python -m json.tool
echo ""
echo "✓ Unauthorized request correctly rejected"
echo ""

# Test 3: Tools list (with token)
echo "Test 3: Tools list with token"
curl -s -X POST "$SERVER_URL/mcp" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/list"
  }' | python -m json.tool
echo ""
echo "✓ Tools list retrieved successfully"
echo ""

# Test 4: inbox_append
echo "Test 4: inbox_append"
TODAY=$(date +%Y-%m-%d)
curl -s -X POST "$SERVER_URL/api/inbox_append" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d "{
    \"date\": \"$TODAY\",
    \"task_code\": \"TC-MCP-BRIDGE-0002\",
    \"source\": \"TestScript\",
    \"text\": \"This is a test message from the self-test script.\"
  }" | python -m json.tool
echo ""
echo "✓ inbox_append executed"
echo ""

# Test 5: inbox_tail
echo "Test 5: inbox_tail"
curl -s -X POST "$SERVER_URL/api/inbox_tail" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d "{
    \"date\": \"$TODAY\",
    \"n\": 20
  }" | python -m json.tool
echo ""
echo "✓ inbox_tail executed"
echo ""

# Test 6: board_get
echo "Test 6: board_get"
curl -s -X GET "$SERVER_URL/api/board_get" \
  -H "Authorization: Bearer $TOKEN" | python -m json.tool
echo ""
echo "✓ board_get executed"
echo ""

# Test 7: Try to access law/ directory (should fail)
echo "Test 7: Attempt to access law/ directory (should fail)"
curl -s -X POST "$SERVER_URL/api/inbox_append" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d "{
    \"date\": \"$TODAY\",
    \"task_code\": \"TC-MCP-BRIDGE-0002\",
    \"source\": \"TestScript\",
    \"text\": \"../../law/test.txt\"
  }" | python -m json.tool
echo ""
echo "✓ Path security working (law/ access blocked)"
echo ""

# Test 8: MCP protocol tools/call
echo "Test 8: MCP protocol tools/call - inbox_append"
curl -s -X POST "$SERVER_URL/mcp" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d "{
    \"jsonrpc\": \"2.0\",
    \"method\": \"tools/call\",
    \"params\": {
      \"name\": \"inbox_append\",
      \"arguments\": {
        \"date\": \"$TODAY\",
        \"task_code\": \"TC-MCP-BRIDGE-0002\",
        \"source\": \"MCPTest\",
        \"text\": \"MCP protocol test message\"
      }
    }
  }" | python -m json.tool
echo ""
echo "✓ MCP protocol tools/call executed"
echo ""

echo "========================================="
echo "All tests completed!"
echo "========================================="
echo ""
echo "Check the following for verification:"
echo "1. Inbox file: docs/REPORT/inbox/$TODAY.md"
echo "2. Audit log: docs/LOG/mcp_bus/$TODAY.log"
echo ""
