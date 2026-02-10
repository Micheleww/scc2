#!/usr/bin/env python3
"""
Direct test for server_stdio.py - test components directly without subprocess
"""

import asyncio
import json
import os
import sys
from pathlib import Path

# Add repo root to path
repo_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(repo_root))

# Set environment variables
os.environ["REPO_ROOT"] = str(repo_root)
os.environ["MCP_BUS_HOST"] = "127.0.0.1"
os.environ["MCP_BUS_PORT"] = "8000"
os.environ["AUTH_MODE"] = "none"


async def test_server_direct():
    """Test server components directly"""
    print("=" * 60)
    print("Testing server_stdio.py components directly...")
    print("=" * 60)

    try:
        from tools.mcp_bus.server_stdio import StdioMCPServer

        # Create server instance
        print("\n[1] Creating server instance...")
        server = StdioMCPServer()
        print("  [OK] Server created")

        # Initialize server
        print("\n[2] Initializing server...")
        await server.initialize()
        print("  [OK] Server initialized")

        # Test 1: Initialize request
        print("\n[3] Testing initialize request...")
        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1.0.0"},
            },
        }
        response = await server.handle_request(init_request)
        print(f"  Response: {json.dumps(response, indent=2)}")
        if response.get("result") and "protocolVersion" in response.get("result", {}):
            print("  [PASS] Initialize request handled correctly")
        else:
            print("  [FAIL] Invalid initialize response")
            return False

        # Test 2: Tools list
        print("\n[4] Testing tools/list request...")
        tools_request = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
        response = await server.handle_request(tools_request)
        print(f"  Response keys: {list(response.keys())}")
        if "result" in response and "tools" in response.get("result", {}):
            tools = response["result"]["tools"]
            print(f"  [PASS] Tools list successful - Found {len(tools)} tools")
            if len(tools) > 0:
                tool_names = [t.get("name", "?") for t in tools[:5]]
                print(f"  Sample tools: {', '.join(tool_names)}")
        else:
            print("  [FAIL] Invalid tools list response")
            print(f"  Full response: {json.dumps(response, indent=2)}")
            return False

        # Test 3: Ping tool
        print("\n[5] Testing ping tool call...")
        ping_request = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "ping", "arguments": {}},
        }
        response = await server.handle_request(ping_request)
        print(f"  Response: {json.dumps(response, indent=2)}")
        if "result" in response and "error" not in response:
            print("  [PASS] Ping tool call successful")
        else:
            error = response.get("error", {})
            print(f"  [FAIL] Ping failed: {error.get('message', 'Unknown error')}")
            return False

        # Test 4: Echo tool
        print("\n[6] Testing echo tool call...")
        echo_request = {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "echo", "arguments": {"text": "Hello from direct test!"}},
        }
        response = await server.handle_request(echo_request)
        print(f"  Response: {json.dumps(response, indent=2)}")
        if "result" in response and "error" not in response:
            print("  [PASS] Echo tool call successful")
        else:
            error = response.get("error", {})
            print(f"  [FAIL] Echo failed: {error.get('message', 'Unknown error')}")
            return False

        # Test 5: Invalid method
        print("\n[7] Testing invalid method...")
        invalid_request = {"jsonrpc": "2.0", "id": 5, "method": "invalid/method"}
        response = await server.handle_request(invalid_request)
        print(f"  Response: {json.dumps(response, indent=2)}")
        if "error" in response and response["error"].get("code") == -32601:
            print("  [PASS] Invalid method correctly rejected")
        else:
            print("  [FAIL] Invalid method not properly handled")
            return False

        print("\n" + "=" * 60)
        print("[SUCCESS] All direct tests passed!")
        print("=" * 60)
        return True

    except Exception as e:
        print(f"\n[FAIL] Test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_server_direct())
    sys.exit(0 if success else 1)
