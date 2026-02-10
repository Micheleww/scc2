#!/usr/bin/env python3
"""
Test script for server_stdio.py

This script tests the stdio MCP server by simulating JSON-RPC requests.
"""

import json
import subprocess
import sys
from pathlib import Path


def test_stdio_server():
    """Test the stdio server with basic requests"""
    server_path = Path(__file__).parent / "server_stdio.py"
    repo_root = Path(__file__).parent.parent.parent

    # Set up environment
    env = os.environ.copy()
    env["REPO_ROOT"] = str(repo_root)
    env["MCP_BUS_HOST"] = "127.0.0.1"
    env["MCP_BUS_PORT"] = "8000"
    env["AUTH_MODE"] = "none"

    # Start the server process
    print("Starting stdio server...")
    process = subprocess.Popen(
        [sys.executable, str(server_path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        cwd=str(repo_root),
    )

    try:
        # Test 1: Initialize
        print("\nTest 1: Initialize")
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
        process.stdin.write(json.dumps(init_request) + "\n")
        process.stdin.flush()

        # Read response
        response_line = process.stdout.readline()
        if response_line:
            response = json.loads(response_line.strip())
            print(f"Response: {json.dumps(response, indent=2)}")
            if response.get("result") and "protocolVersion" in response.get("result", {}):
                print("✅ Initialize test passed")
            else:
                print("❌ Initialize test failed")
                return False

        # Test 2: Tools list
        print("\nTest 2: Tools list")
        tools_request = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
        process.stdin.write(json.dumps(tools_request) + "\n")
        process.stdin.flush()

        response_line = process.stdout.readline()
        if response_line:
            response = json.loads(response_line.strip())
            print(f"Response keys: {list(response.keys())}")
            if "result" in response and "tools" in response.get("result", {}):
                tools = response["result"]["tools"]
                print(f"✅ Tools list test passed - Found {len(tools)} tools")
            else:
                print("❌ Tools list test failed")
                print(f"Response: {json.dumps(response, indent=2)}")
                return False

        # Test 3: Ping tool
        print("\nTest 3: Ping tool")
        ping_request = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "ping", "arguments": {}},
        }
        process.stdin.write(json.dumps(ping_request) + "\n")
        process.stdin.flush()

        response_line = process.stdout.readline()
        if response_line:
            response = json.loads(response_line.strip())
            print(f"Response: {json.dumps(response, indent=2)}")
            if "result" in response and "error" not in response:
                print("✅ Ping test passed")
            else:
                print("❌ Ping test failed")
                return False

        print("\n✅ All tests passed!")
        return True

    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        # Clean up
        process.stdin.close()
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()

        # Print stderr if any
        stderr_output = process.stderr.read()
        if stderr_output:
            print(f"\nStderr output:\n{stderr_output}")


if __name__ == "__main__":
    import os

    success = test_stdio_server()
    sys.exit(0 if success else 1)
