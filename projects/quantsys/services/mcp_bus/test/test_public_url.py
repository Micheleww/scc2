import json
import os
from datetime import datetime

import requests

# 配置（模拟公网 URL）
# 实际部署时，替换为真实的 cloudflared 或 ngrok URL
PUBLIC_URL = os.getenv("MCP_PUBLIC_URL", "https://qcc-bus-mock.trycloudflare.com")
TOKEN = os.getenv("MCP_BUS_TOKEN", "test-token-12345")


def print_section(title):
    print(f"\n{'=' * 60}")
    print(f" {title}")
    print(f"{'=' * 60}")


def test_public_health():
    print_section("Test 1: Public Health Check")
    response = requests.get(f"{PUBLIC_URL}/health", timeout=10)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.json()}")
    assert response.status_code == 200
    assert response.json()["ok"] == True
    print("✓ PASS")
    return response.json()


def test_public_tools_list():
    print_section("Test 2: Public Tools List (with token)")
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    payload = {"jsonrpc": "2.0", "method": "tools/list"}
    response = requests.post(f"{PUBLIC_URL}/mcp", json=payload, headers=headers, timeout=10)
    print(f"Status Code: {response.status_code}")
    result = response.json()
    tools = result.get("result", {}).get("tools", [])
    print(f"Tools found: {len(tools)}")
    for tool in tools:
        print(f"  - {tool['name']}")
    assert response.status_code == 200
    assert len(tools) == 4
    print("✓ PASS")
    return result


def test_public_inbox_append():
    print_section("Test 3: Public inbox_append")
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    payload = {
        "date": "2026-01-15",
        "task_code": "TC-MCP-BRIDGE-0004",
        "source": "PublicTest",
        "text": "Public URL verification test",
    }
    response = requests.post(
        f"{PUBLIC_URL}/api/inbox_append", json=payload, headers=headers, timeout=10
    )
    print(f"Status Code: {response.status_code}")
    result = response.json()
    print(f"Response: {json.dumps(result, indent=2)}")
    assert response.status_code == 200
    assert result["success"] == True
    print("✓ PASS")
    return result


def test_public_inbox_tail():
    print_section("Test 4: Public inbox_tail")
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    payload = {"date": "2026-01-15", "n": 10}
    response = requests.post(
        f"{PUBLIC_URL}/api/inbox_tail", json=payload, headers=headers, timeout=10
    )
    print(f"Status Code: {response.status_code}")
    result = response.json()
    print(f"Lines returned: {result.get('lines_returned', 0)}")
    print(f"Content preview: {result.get('content', '')[:100]}...")
    assert response.status_code == 200
    assert result["success"] == True
    print("✓ PASS")
    return result


def test_public_fail_closed():
    print_section("Test 5: Public Request Without Token (fail-closed)")
    headers = {"Content-Type": "application/json"}
    payload = {"jsonrpc": "2.0", "method": "tools/list"}
    response = requests.post(f"{PUBLIC_URL}/mcp", json=payload, headers=headers, timeout=10)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.text}")
    assert response.status_code == 401
    print("✓ PASS - Correctly rejected")


def main():
    print("\n" + "=" * 60)
    print(" QCC Bus MCP Server - Public URL Verification")
    print("=" * 60)
    print(f"\nPublic URL: {PUBLIC_URL}")
    print(f"Token: {TOKEN[:20]}...")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("\nNote: This is a simulated public URL test.")
    print("For actual deployment, install cloudflared or ngrok:")
    print(
        "  - cloudflared: https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/"
    )
    print("  - ngrok: https://ngrok.com/download")

    try:
        health_result = test_public_health()
        tools_result = test_public_tools_list()
        append_result = test_public_inbox_append()
        tail_result = test_public_inbox_tail()
        test_public_fail_closed()

        print("\n" + "=" * 60)
        print(" All Tests Passed!")
        print("=" * 60)
        print("\nEvidence:")
        print("  - Health check: ✓")
        print("  - Tools list: ✓")
        print("  - inbox_append: ✓")
        print("  - inbox_tail: ✓")
        print("  - Fail-closed: ✓")
        print("\n" + "=" * 60)

        return 0

    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        return 1
    except requests.exceptions.ConnectionError as e:
        print(f"\n✗ Connection failed: {e}")
        print("This is expected if PUBLIC_URL is not reachable.")
        print("For actual deployment:")
        print("  1. Install cloudflared: winget install --id Cloudflare.cloudflared")
        print("  2. Install ngrok: choco install ngrok")
        print(
            "  3. Start MCP Server: cd tools/mcp_bus && uvicorn server.main:app --host 127.0.0.1 --port 8000"
        )
        print("  4. Start tunnel: cloudflared tunnel run (or ngrok http 8000)")
        print("  5. Update PUBLIC_URL in this script to the actual tunnel URL")
        return 1
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
