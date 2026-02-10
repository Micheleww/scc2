import json
import traceback

import requests


def test_aws_mcp_server():
    """Test the AWS MCP server connectivity and functionality"""
    base_url = "https://mcp.timquant.tech"
    mcp_url = f"{base_url}/mcp"

    print("Testing AWS MCP Server Connection...")
    print("=" * 50)

    # Test 1: Basic connectivity
    print("\n1. Testing basic server connectivity...")
    try:
        response = requests.get(base_url, timeout=5)
        print(f"   ✓ Status: {response.status_code}")
        print(f"   ✓ Headers: {dict(response.headers)}")
        print(f"   ✓ Content (first 200 chars): {response.text[:200]}...")
    except requests.exceptions.ConnectionError:
        print(f"   ✗ Connection failed: Could not connect to {base_url}")
        print("   This could be due to firewall issues, DNS problems, or the server being down")
        return False
    except requests.exceptions.Timeout:
        print(f"   ✗ Connection timed out: No response from {base_url} in 5 seconds")
        return False
    except Exception as e:
        print(f"   ✗ Error: {type(e).__name__}: {str(e)}")
        traceback.print_exc()
        return False

    # Test 2: Check if the MCP endpoint is accessible
    print("\n2. Testing MCP endpoint accessibility...")
    try:
        # Use OPTIONS to check if the endpoint exists without sending a full request
        response = requests.options(mcp_url, timeout=5)
        print(f"   ✓ OPTIONS request successful: {response.status_code}")
        print(f"   ✓ Allowed methods: {response.headers.get('Allow', 'Not specified')}")
    except Exception as e:
        print(f"   ✗ Error: {type(e).__name__}: {str(e)}")
        traceback.print_exc()
        return False

    # Test 3: Test initialize method (required for GPT connector)
    print("\n3. Testing initialize method...")
    initialize_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": "2.0"},
    }

    try:
        response = requests.post(
            mcp_url,
            json=initialize_payload,
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        print("   ✓ Request sent successfully")
        print(f"   ✓ Status code: {response.status_code}")
        print(f"   ✓ Headers: {dict(response.headers)}")
        print(f"   ✓ Response content: {response.text}")

        # Try to parse JSON
        try:
            json_response = response.json()
            print(f"   ✓ JSON parsed successfully: {json_response}")
        except json.JSONDecodeError:
            print("   ✗ Failed to parse JSON response")
            print(f"   Response is not valid JSON: {response.text}")
            return False

    except Exception as e:
        print(f"   ✗ Request failed: {type(e).__name__}: {str(e)}")
        traceback.print_exc()
        return False

    # Test 4: Test tools/list method (required for GPT connector)
    print("\n4. Testing tools/list method...")
    tools_list_payload = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}

    try:
        response = requests.post(
            mcp_url,
            json=tools_list_payload,
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        print("   ✓ Request sent successfully")
        print(f"   ✓ Status code: {response.status_code}")
        print(f"   ✓ Headers: {dict(response.headers)}")
        print(f"   ✓ Response content: {response.text}")

        # Try to parse JSON
        try:
            json_response = response.json()
            print(f"   ✓ JSON parsed successfully: {json_response}")
        except json.JSONDecodeError:
            print("   ✗ Failed to parse JSON response")
            print(f"   Response is not valid JSON: {response.text}")
            return False

    except Exception as e:
        print(f"   ✗ Request failed: {type(e).__name__}: {str(e)}")
        traceback.print_exc()
        return False

    print("\n" + "=" * 50)
    print("✓ All tests completed successfully!")
    print("The AWS MCP server is accessible and responding correctly.")
    return True


if __name__ == "__main__":
    test_aws_mcp_server()
