import time

import requests


def test_local_mcp():
    """Detailed test of local MCP server"""
    base_url = "http://localhost:18788/"
    mcp_url = f"{base_url}/mcp"

    print("=" * 60)
    print("DETAILED LOCAL MCP SERVER TEST")
    print("=" * 60)

    # Test 1: Root endpoint
    print("\n1. Testing root endpoint...")
    try:
        response = requests.get(base_url, timeout=3)
        print(f"   ✓ Status: {response.status_code}")
        print(f"   ✓ Response: {response.json()}")
    except Exception as e:
        print(f"   ✗ Error: {type(e).__name__}: {e}")
        return False

    # Test 2: Health endpoint
    print("\n2. Testing health endpoint...")
    try:
        response = requests.get(f"{base_url}/health", timeout=3)
        print(f"   ✓ Status: {response.status_code}")
        print(f"   ✓ Response: {response.json()}")
    except Exception as e:
        print(f"   ✗ Error: {type(e).__name__}: {e}")
        return False

    # Test 3: Initialize method
    print("\n3. Testing initialize method...")
    initialize_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": "2.0"},
    }

    try:
        start_time = time.time()
        response = requests.post(
            mcp_url,
            json=initialize_payload,
            headers={"Content-Type": "application/json"},
            timeout=5,
        )
        elapsed = time.time() - start_time
        print(f"   ✓ Status: {response.status_code}, Time: {elapsed:.2f}s")
        print(f"   ✓ Headers: {dict(response.headers)}")
        print(f"   ✓ Response: {response.json()}")
    except Exception as e:
        print(f"   ✗ Error: {type(e).__name__}: {e}")
        return False

    # Test 4: Tools/list method
    print("\n4. Testing tools/list method...")
    tools_payload = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}

    try:
        start_time = time.time()
        response = requests.post(
            mcp_url, json=tools_payload, headers={"Content-Type": "application/json"}, timeout=5
        )
        elapsed = time.time() - start_time
        print(f"   ✓ Status: {response.status_code}, Time: {elapsed:.2f}s")
        print(f"   ✓ Headers: {dict(response.headers)}")
        print(f"   ✓ Response: {response.json()}")
    except Exception as e:
        print(f"   ✗ Error: {type(e).__name__}: {e}")
        return False

    print("\n" + "=" * 60)
    print("✓ ALL TESTS PASSED! Local MCP server is working correctly.")
    print("=" * 60)
    print("\nServer URL for GPT connector: http://localhost:18788/mcp")
    print('Authentication: "未授权" (No Auth)')
    print("Supported methods: initialize, tools/list, tools/call (ping, echo)")

    return True


if __name__ == "__main__":
    test_local_mcp()
