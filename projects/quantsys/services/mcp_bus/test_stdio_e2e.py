#!/usr/bin/env python3
"""
End-to-end test for server_stdio.py

This test simulates a real MCP client connecting via stdio.
"""

import json
import subprocess
import sys
import threading
import time
from pathlib import Path


def read_output(process, output_list):
    """Read stdout from process"""
    try:
        for line in iter(process.stdout.readline, ""):
            if not line:
                break
            output_list.append(line.strip())
    except Exception as e:
        output_list.append(f"ERROR: {e}")


def test_stdio_e2e():
    """End-to-end test of stdio server"""
    server_path = Path(__file__).parent / "server_stdio.py"
    repo_root = Path(__file__).parent.parent.parent

    # Set up environment
    env = os.environ.copy()
    env["REPO_ROOT"] = str(repo_root)
    env["MCP_BUS_HOST"] = "127.0.0.1"
    env["MCP_BUS_PORT"] = "8000"
    env["AUTH_MODE"] = "none"
    env["PYTHONUNBUFFERED"] = "1"

    print("=" * 60)
    print("Starting stdio server E2E test...")
    print("=" * 60)

    # Start the server process
    process = subprocess.Popen(
        [sys.executable, str(server_path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        cwd=str(repo_root),
        bufsize=0,  # Unbuffered
    )

    output_lines = []
    error_lines = []

    # Start thread to read stdout
    stdout_thread = threading.Thread(target=read_output, args=(process, output_lines))
    stdout_thread.daemon = True
    stdout_thread.start()

    # Start thread to read stderr
    stderr_thread = threading.Thread(target=read_output, args=(process, error_lines))
    stderr_thread.daemon = True
    stderr_thread.start()

    try:
        # Wait a bit for server to start
        time.sleep(0.5)

        # Test 1: Initialize
        print("\n[TEST 1] Initialize request")
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
        request_json = json.dumps(init_request) + "\n"
        print(f"  Sending: {request_json.strip()}")
        process.stdin.write(request_json)
        process.stdin.flush()

        # Wait for response
        time.sleep(0.5)
        if output_lines:
            response_line = output_lines.pop(0)
            print(f"  Received: {response_line}")
            try:
                response = json.loads(response_line)
                if response.get("result") and "protocolVersion" in response.get("result", {}):
                    print("  [PASS] Initialize successful")
                else:
                    print(f"  [FAIL] Invalid response: {response}")
                    return False
            except json.JSONDecodeError as e:
                print(f"  [FAIL] Invalid JSON: {e}")
                return False
        else:
            print("  [FAIL] No response received")
            return False

        # Test 2: Tools list
        print("\n[TEST 2] Tools list request")
        tools_request = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
        request_json = json.dumps(tools_request) + "\n"
        print(f"  Sending: {request_json.strip()}")
        process.stdin.write(request_json)
        process.stdin.flush()

        time.sleep(0.5)
        if output_lines:
            response_line = output_lines.pop(0)
            print(f"  Received: {response_line[:200]}...")  # Truncate long output
            try:
                response = json.loads(response_line)
                if "result" in response and "tools" in response.get("result", {}):
                    tools = response["result"]["tools"]
                    print(f"  [PASS] Tools list successful - Found {len(tools)} tools")
                    if len(tools) > 0:
                        print(
                            f"  Sample tools: {', '.join([t.get('name', '?') for t in tools[:5]])}"
                        )
                else:
                    print("  [FAIL] Invalid response structure")
                    print(f"  Response keys: {list(response.keys())}")
                    return False
            except json.JSONDecodeError as e:
                print(f"  [FAIL] Invalid JSON: {e}")
                return False
        else:
            print("  [FAIL] No response received")
            return False

        # Test 3: Ping tool
        print("\n[TEST 3] Ping tool call")
        ping_request = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "ping", "arguments": {}},
        }
        request_json = json.dumps(ping_request) + "\n"
        print(f"  Sending: {request_json.strip()}")
        process.stdin.write(request_json)
        process.stdin.flush()

        time.sleep(0.5)
        if output_lines:
            response_line = output_lines.pop(0)
            print(f"  Received: {response_line}")
            try:
                response = json.loads(response_line)
                if "result" in response and "error" not in response:
                    print("  [PASS] Ping successful")
                else:
                    print(f"  [FAIL] Error in response: {response.get('error')}")
                    return False
            except json.JSONDecodeError as e:
                print(f"  [FAIL] Invalid JSON: {e}")
                return False
        else:
            print("  [FAIL] No response received")
            return False

        # Test 4: Echo tool
        print("\n[TEST 4] Echo tool call")
        echo_request = {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "echo", "arguments": {"text": "Hello from test!"}},
        }
        request_json = json.dumps(echo_request) + "\n"
        print(f"  Sending: {request_json.strip()}")
        process.stdin.write(request_json)
        process.stdin.flush()

        time.sleep(0.5)
        if output_lines:
            response_line = output_lines.pop(0)
            print(f"  Received: {response_line}")
            try:
                response = json.loads(response_line)
                if "result" in response and "error" not in response:
                    print("  [PASS] Echo successful")
                else:
                    print(f"  [FAIL] Error in response: {response.get('error')}")
                    return False
            except json.JSONDecodeError as e:
                print(f"  [FAIL] Invalid JSON: {e}")
                return False
        else:
            print("  [FAIL] No response received")
            return False

        print("\n" + "=" * 60)
        print("[SUCCESS] All E2E tests passed!")
        print("=" * 60)
        return True

    except Exception as e:
        print(f"\n[FAIL] Test failed with error: {e}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        # Clean up
        print("\nCleaning up...")
        if process.stdin:
            try:
                process.stdin.close()
            except:
                pass

        # Wait a bit for threads
        time.sleep(0.5)

        # Terminate process
        try:
            process.terminate()
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()

        # Print any remaining output
        if output_lines:
            print(f"\nRemaining stdout ({len(output_lines)} lines):")
            for line in output_lines[:10]:  # Show first 10
                print(f"  {line}")

        # Print stderr if any
        if error_lines:
            print(f"\nStderr output ({len(error_lines)} lines):")
            for line in error_lines[:20]:  # Show first 20
                print(f"  {line}")


if __name__ == "__main__":
    import os

    success = test_stdio_e2e()
    sys.exit(0 if success else 1)
