import json
import sys
import time

import requests


def test_local_mcp():
    print("Testing local MCP server...")
    print(f"Python version: {sys.version}")
    print(f"Requests version: {requests.__version__}")

    # Test connection to the server first
    base_url = "http://localhost:18788/"
    mcp_url = f"{base_url}/mcp"

    print(f"\n1. Testing connection to {base_url}")
    try:
        start_time = time.time()
        response = requests.get(f"{base_url}/docs", timeout=2)
        elapsed = time.time() - start_time
        print(f"   ✓ Connection successful! Status: {response.status_code}, Time: {elapsed:.2f}s")
    except requests.exceptions.ConnectionError:
        print(f"   ✗ Connection failed: Could not connect to {base_url}")
        print("   Make sure the server is running on port 8000")
        return False
    except requests.exceptions.Timeout:
        print(f"   ✗ Connection timed out: No response from {base_url} in 2 seconds")
        return False
    except Exception as e:
        print(f"   ✗ Connection error: {type(e).__name__}: {e}")
        return False

    # Test initialize method
    print(f"\n2. Testing initialize method at {mcp_url}")
    initialize_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": "2.0"},
    }

    try:
        start_time = time.time()
        response = requests.post(mcp_url, json=initialize_payload, timeout=5)
        elapsed = time.time() - start_time
        print(f"   ✓ Request sent successfully! Time: {elapsed:.2f}s")
        print(f"   Response status: {response.status_code}")
        print(f"   Response headers: {dict(response.headers)}")
        print(f"   Response content: {response.text}")

        # Try to parse JSON
        try:
            json_response = response.json()
            print(f"   ✓ JSON parsed successfully: {json_response}")
        except json.JSONDecodeError:
            print("   ✗ Failed to parse JSON response")

    except Exception as e:
        print(f"   ✗ Request failed: {type(e).__name__}: {e}")

    # Test tools/list method
    print(f"\n3. Testing tools/list method at {mcp_url}")
    tools_payload = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}

    try:
        start_time = time.time()
        response = requests.post(mcp_url, json=tools_payload, timeout=5)
        elapsed = time.time() - start_time
        print(f"   ✓ Request sent successfully! Time: {elapsed:.2f}s")
        print(f"   Response status: {response.status_code}")
        print(f"   Response headers: {dict(response.headers)}")
        print(f"   Response content: {response.text}")

        # Try to parse JSON
        try:
            json_response = response.json()
            print(f"   ✓ JSON parsed successfully: {json_response}")
        except json.JSONDecodeError:
            print("   ✗ Failed to parse JSON response")

    except Exception as e:
        print(f"   ✗ Request failed: {type(e).__name__}: {e}")

    return True


if __name__ == "__main__":
    test_local_mcp()
    print("\nTest completed!")
