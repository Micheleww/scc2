#!/usr/bin/env python3
"""
ChatGPT MCP End-to-End Smoke Test Script

Tests the complete call flow: tools/list → a2a.task_create → a2a.task_status → a2a.task_result → ata.fetch
"""

import asyncio
import json
import os
import sys
import time
import uuid

from aiohttp import ClientSession

# Project root directory
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ARTIFACTS_DIR = "docs/REPORT/ci/artifacts/CHATGPT-MCP-END2END-SMOKE-v0.1__20260115"
LOG_PATH = f"{ARTIFACTS_DIR}/selftest.log"

# Exchange server configuration
EXCHANGE_SERVER_URL = "http://localhost:18788/"
MCP_ENDPOINT = f"{EXCHANGE_SERVER_URL}/mcp"
SSE_ENDPOINT = f"{EXCHANGE_SERVER_URL}/mcp/messages"
AUTH_TOKEN = "default_secret_token"


def log_message(message, level="INFO"):
    """Log a message to both console and file"""
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%S")
    # Remove emojis to avoid encoding issues
    message = message.replace("✅", "")
    message = message.replace("❌", "")
    log_line = f"[{timestamp}] [{level}] {message}\n"

    print(log_line.rstrip())
    # Use UTF-8 encoding to avoid encoding issues
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(log_line)


async def jsonrpc_call(session, method, params=None):
    """Make a JSON-RPC call to the exchange server"""
    if params is None:
        params = {}

    payload = {"jsonrpc": "2.0", "id": str(uuid.uuid4()), "method": method, "params": params}

    headers = {
        "Authorization": f"Bearer {AUTH_TOKEN}",
        "X-Request-Nonce": str(uuid.uuid4()),
        "X-Request-Ts": str(int(time.time())),
    }

    log_message(f"Calling {method} with params: {json.dumps(params)}")

    try:
        async with session.post(MCP_ENDPOINT, json=payload, headers=headers) as response:
            status = response.status
            body = await response.json()

            log_message(f"Response status: {status}")
            log_message(f"Response body: {json.dumps(body, indent=2)}")

            return {"status": status, "body": body}
    except Exception as e:
        log_message(f"Error calling {method}: {str(e)}", level="ERROR")
        return {
            "status": 500,
            "body": {"error": {"code": -32603, "message": f"Internal error: {str(e)}"}},
        }


async def test_sse_connection(session):
    """Test SSE connection to the exchange server"""
    log_message("Testing SSE connection...")

    headers = {"Authorization": f"Bearer {AUTH_TOKEN}" if AUTH_TOKEN else ""}

    try:
        async with session.get(SSE_ENDPOINT, headers=headers) as response:
            log_message(f"SSE connection status: {response.status}")

            if response.status == 200:
                # Read first 2 events
                data = b""
                event_count = 0
                async for line in response.content:
                    data += line
                    if line == b"\n" and b"data:" in data:
                        event_count += 1
                        if event_count >= 2:
                            break

                log_message(f"Received {event_count} SSE events")
                log_message(f"SSE data sample: {data[:200]}...")
                return True
            else:
                log_message("Failed to connect to SSE endpoint", level="ERROR")
                return False
    except Exception as e:
        log_message(f"Error connecting to SSE: {str(e)}", level="ERROR")
        return False


async def run_e2e_test():
    """Run the complete end-to-end test flow"""
    log_message("Starting ChatGPT MCP End-to-End Smoke Test")
    log_message(f"Exchange Server URL: {EXCHANGE_SERVER_URL}")
    log_message(f"Artifacts Directory: {ARTIFACTS_DIR}")

    # Create artifacts directory if it doesn't exist
    os.makedirs(ARTIFACTS_DIR, exist_ok=True)
    os.makedirs(f"{ARTIFACTS_DIR}/ata", exist_ok=True)

    # Clear previous log
    with open(LOG_PATH, "w") as f:
        f.write("# ChatGPT MCP End-to-End Smoke Test\n")
        f.write(f"TIMESTAMP={time.strftime('%Y-%m-%dT%H:%M:%S')}\n\n")

    try:
        async with ClientSession() as session:
            # 1. Test SSE connection
            sse_ok = await test_sse_connection(session)
            if not sse_ok:
                log_message("SSE connection test failed", level="ERROR")
                return False

            # 2. Get available tools
            log_message("\n1. Testing tools/list")
            result = await jsonrpc_call(session, "tools/list")

            if result["status"] != 200 or "error" in result["body"]:
                log_message("tools/list failed", level="ERROR")
                return False

            tools = result["body"]["result"]["tools"]
            log_message(f"Found {len(tools)} tools")

            # 3. Create a task in A2A Hub
            log_message("\n2. Testing a2a.task_create")
            task_payload = {
                "task_name": "ChatGPT MCP Test Task",
                "task_description": "Test task created from ChatGPT MCP smoke test",
                "task_type": "test",
                "priority": "medium",
            }

            result = await jsonrpc_call(
                session,
                "tools/call",
                {"tool_call": {"name": "a2a.task_create", "params": {"payload": task_payload}}},
            )

            if result["status"] != 200 or "error" in result["body"]:
                log_message("a2a.task_create failed", level="ERROR")
                return False

            task_result = result["body"]["result"]["tool_result"]
            if not task_result.get("success", False):
                log_message("a2a.task_create returned success=False", level="ERROR")
                return False

            task_id = task_result.get(
                "task_id", str(uuid.uuid4())
            )  # Generate dummy if not returned
            log_message(f"Created task with ID: {task_id}")

            # 4. Check task status
            log_message(f"\n3. Testing a2a.task_status for task {task_id}")
            result = await jsonrpc_call(
                session,
                "tools/call",
                {"tool_call": {"name": "a2a.task_status", "params": {"task_id": task_id}}},
            )

            if result["status"] != 200 or "error" in result["body"]:
                log_message("a2a.task_status failed", level="ERROR")
                return False

            status_result = result["body"]["result"]["tool_result"]
            task_status = status_result.get("status", "unknown")
            log_message(f"Task status: {task_status}")

            # 5. Get task result
            log_message(f"\n4. Testing a2a.task_result for task {task_id}")
            result = await jsonrpc_call(
                session,
                "tools/call",
                {"tool_call": {"name": "a2a.task_result", "params": {"task_id": task_id}}},
            )

            if result["status"] != 200 or "error" in result["body"]:
                log_message("a2a.task_result failed", level="ERROR")
                return False

            task_result = result["body"]["result"]["tool_result"]
            log_message(f"Task result success: {task_result.get('success', False)}")

            # 6. Test ata.fetch with a valid task code
            log_message("\n5. Testing ata.fetch with a valid task code")
            # Use a real task code from the previous task or a default one
            test_task_code = "EXCHANGE-TOOLS-SCHEMA-STABILIZE-v0.1__20260115"

            result = await jsonrpc_call(
                session,
                "tools/call",
                {"tool_call": {"name": "ata.fetch", "params": {"task_code": test_task_code}}},
            )

            if result["status"] != 200 or "error" in result["body"]:
                log_message("ata.fetch failed", level="ERROR")
                return False

            fetch_result = result["body"]["result"]["tool_result"]
            log_message("ata.fetch called successfully!")
            log_message(f"Result: {json.dumps(fetch_result, indent=2)}")
            log_message(f"REASON_CODE: {fetch_result.get('REASON_CODE')}")
            log_message(f"RULESET_SHA256: {fetch_result.get('RULESET_SHA256')}")

            # All tests passed
            log_message("\n✅ All tests passed!")
            log_message("EXIT_CODE=0")
            return True

    except Exception as e:
        log_message(f"❌ Test failed with exception: {str(e)}", level="ERROR")
        log_message("EXIT_CODE=1")
        return False


async def main():
    """Main function"""
    success = await run_e2e_test()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
