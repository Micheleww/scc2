import json
from datetime import datetime

import requests

BASE_URL = "http://127.0.0.1:18788/"
TOKEN = "test-token-12345"


def print_section(title):
    print(f"\n{'=' * 60}")
    print(f" {title}")
    print(f"{'=' * 60}")


def test_health():
    print_section("Test 1: Health Check")
    response = requests.get(f"{BASE_URL}/health")
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.json()}")
    assert response.status_code == 200
    assert response.json()["ok"] == True
    print("✓ PASS")


def test_tools_list_with_token():
    print_section("Test 2: Tools List (with token)")
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    payload = {"jsonrpc": "2.0", "method": "tools/list"}
    response = requests.post(f"{BASE_URL}/mcp", json=payload, headers=headers)
    print(f"Status Code: {response.status_code}")
    result = response.json()
    tools = result.get("result", {}).get("tools", [])
    print(f"Tools found: {len(tools)}")
    for tool in tools:
        print(f"  - {tool['name']}")
    assert response.status_code == 200
    assert len(tools) == 4
    print("✓ PASS")


def test_tools_list_without_token():
    print_section("Test 3: Tools List (without token - should fail)")
    headers = {"Content-Type": "application/json"}
    payload = {"jsonrpc": "2.0", "method": "tools/list"}
    response = requests.post(f"{BASE_URL}/mcp", json=payload, headers=headers)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.text}")
    assert response.status_code == 401
    print("✓ PASS - Correctly rejected")


def test_inbox_append():
    print_section("Test 4: inbox_append")
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    payload = {
        "date": "2026-01-15",
        "task_code": "TC-MCP-BRIDGE-0003",
        "source": "TestScript",
        "text": "Windows Python verification test",
    }
    response = requests.post(f"{BASE_URL}/api/inbox_append", json=payload, headers=headers)
    print(f"Status Code: {response.status_code}")
    result = response.json()
    print(f"Response: {json.dumps(result, indent=2)}")
    assert response.status_code == 200
    assert result["success"] == True
    print("✓ PASS")


def test_inbox_tail():
    print_section("Test 5: inbox_tail")
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    payload = {"date": "2026-01-15", "n": 10}
    response = requests.post(f"{BASE_URL}/api/inbox_tail", json=payload, headers=headers)
    print(f"Status Code: {response.status_code}")
    result = response.json()
    print(f"Lines returned: {result.get('lines_returned', 0)}")
    print(f"Content preview: {result.get('content', '')[:100]}...")
    assert response.status_code == 200
    assert result["success"] == True
    print("✓ PASS")


def main():
    print("\n" + "=" * 60)
    print(" QCC Bus MCP Server - Windows Self-Test")
    print("=" * 60)
    print(f"\nServer URL: {BASE_URL}")
    print(f"Token: {TOKEN[:20]}...")
    print(f"Timestamp: {datetime.now().isoformat()}")

    try:
        test_health()
        test_tools_list_with_token()
        test_tools_list_without_token()
        test_inbox_append()
        test_inbox_tail()

        print("\n" + "=" * 60)
        print(" All Tests Passed!")
        print("=" * 60)
        print("\nArtifacts:")
        print("  - Inbox file: docs\\REPORT\\inbox\\2026-01-15.md")
        print("  - Audit log: docs\\LOG\\mcp_bus\\2026-01-15.log")
        print("\n" + "=" * 60)

    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        return 1
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
