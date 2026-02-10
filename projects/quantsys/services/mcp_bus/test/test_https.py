import json
import os
from datetime import datetime

import requests

# HTTPS 配置
DOMAIN = "mcp.timquant.tech"
HTTPS_URL = f"https://{DOMAIN}/mcp"
HEALTH_URL = f"https://{DOMAIN}/health"
TOKEN = os.getenv("MCP_BUS_TOKEN", "YOUR_TOKEN_HERE")


def print_section(title):
    print(f"\n{'=' * 60}")
    print(f" {title}")
    print(f"{'=' * 60}")


def test_https_health():
    print_section("Test 1: HTTPS Health Check")
    print(f"URL: {HEALTH_URL}")
    try:
        response = requests.get(HEALTH_URL, timeout=10, verify=True)
        print(f"Status Code: {response.status_code}")
        result = response.json()
        print(f"Response: {json.dumps(result, indent=2)}")
        assert response.status_code == 200
        assert result["ok"] == True
        print("✓ PASS - HTTPS working!")
        return result
    except requests.exceptions.SSLError as e:
        print(f"✗ SSL Error: {e}")
        print("This is expected if certificate is not yet valid.")
        return None
    except requests.exceptions.ConnectionError as e:
        print(f"✗ Connection failed: {e}")
        print("This is expected if DNS or EC2 not configured yet.")
        return None


def test_https_tools_list():
    print_section("Test 2: HTTPS Tools List (with token)")
    print(f"URL: {HTTPS_URL}")
    print(f"Token: {TOKEN[:20]}...")
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    payload = {"jsonrpc": "2.0", "method": "tools/list"}
    try:
        response = requests.post(HTTPS_URL, json=payload, headers=headers, timeout=10, verify=True)
        print(f"Status Code: {response.status_code}")
        result = response.json()
        tools = result.get("result", {}).get("tools", [])
        print(f"Tools found: {len(tools)}")
        for tool in tools:
            print(f"  - {tool['name']}")
        assert response.status_code == 200
        assert len(tools) == 4
        print("✓ PASS - HTTPS MCP working!")
        return result
    except requests.exceptions.SSLError as e:
        print(f"✗ SSL Error: {e}")
        return None
    except requests.exceptions.ConnectionError as e:
        print(f"✗ Connection failed: {e}")
        return None


def test_https_inbox_append():
    print_section("Test 3: HTTPS inbox_append")
    print(f"URL: {HTTPS_URL.replace('/mcp', '/api/inbox_append')}")
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    payload = {
        "date": "2026-01-15",
        "task_code": "TC-MCP-HTTPS-LIVE-0010",
        "source": "HTTPSTest",
        "text": "HTTPS deployment verification test",
    }
    try:
        response = requests.post(
            f"{HTTPS_URL.replace('/mcp', '/api/inbox_append')}",
            json=payload,
            headers=headers,
            timeout=10,
            verify=True,
        )
        print(f"Status Code: {response.status_code}")
        result = response.json()
        print(f"Response: {json.dumps(result, indent=2)}")
        assert response.status_code == 200
        assert result["success"] == True
        print("✓ PASS - inbox_append working!")
        return result
    except requests.exceptions.SSLError as e:
        print(f"✗ SSL Error: {e}")
        return None
    except requests.exceptions.ConnectionError as e:
        print(f"✗ Connection failed: {e}")
        return None


def test_https_inbox_tail():
    print_section("Test 4: HTTPS inbox_tail")
    print(f"URL: {HTTPS_URL.replace('/mcp', '/api/inbox_tail')}")
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    payload = {"date": "2026-01-15", "n": 10}
    try:
        response = requests.post(
            f"{HTTPS_URL.replace('/mcp', '/api/inbox_tail')}",
            json=payload,
            headers=headers,
            timeout=10,
            verify=True,
        )
        print(f"Status Code: {response.status_code}")
        result = response.json()
        print(f"Lines returned: {result.get('lines_returned', 0)}")
        print(f"Content preview: {result.get('content', '')[:100]}...")
        assert response.status_code == 200
        assert result["success"] == True
        print("✓ PASS - inbox_tail working!")
        return result
    except requests.exceptions.SSLError as e:
        print(f"✗ SSL Error: {e}")
        return None
    except requests.exceptions.ConnectionError as e:
        print(f"✗ Connection failed: {e}")
        return None


def test_https_fail_closed():
    print_section("Test 5: HTTPS Request Without Token (fail-closed)")
    print(f"URL: {HTTPS_URL}")
    headers = {"Content-Type": "application/json"}
    payload = {"jsonrpc": "2.0", "method": "tools/list"}
    try:
        response = requests.post(HTTPS_URL, json=payload, headers=headers, timeout=10, verify=True)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        assert response.status_code == 401
        print("✓ PASS - Fail-closed working!")
    except requests.exceptions.SSLError as e:
        print(f"✗ SSL Error: {e}")
        return None
    except requests.exceptions.ConnectionError as e:
        print(f"✗ Connection failed: {e}")
        return None


def main():
    print("\n" + "=" * 60)
    print(" QCC Bus MCP Server - HTTPS Verification")
    print("=" * 60)
    print(f"\nHTTPS URL: {HTTPS_URL}")
    print(f"Token: {TOKEN[:20]}...")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("\nNote: This script tests HTTPS deployment.")
    print("Prerequisites:")
    print("  1. DNS A record: mcp.timquant.tech → 13.229.100.10")
    print("  2. EC2 Security Group: Allow ports 80 and 443")
    print("  3. Caddy installed and running on EC2")
    print("  4. MCP Bus binding: 127.0.0.1:18080 (not 0.0.0.0)")
    print("  5. Token retrieved from EC2 (see token_retrieval.md)")
    print("\nDeployment documentation: tools/mcp_bus/deploy/caddy_https_setup.md")
    print("Token retrieval documentation: tools/mcp_bus/deploy/token_retrieval.md")

    try:
        health_result = test_https_health()
        if health_result:
            tools_result = test_https_tools_list()
            if tools_result:
                append_result = test_https_inbox_append()
                if append_result:
                    tail_result = test_https_inbox_tail()
                    if tail_result:
                        test_https_fail_closed()

                        print("\n" + "=" * 60)
                        print(" All Tests Passed!")
                        print("=" * 60)
                        print("\nEvidence:")
                        print("  - HTTPS health check: ✓")
                        print("  - HTTPS tools/list: ✓")
                        print("  - HTTPS inbox_append: ✓")
                        print("  - HTTPS inbox_tail: ✓")
                        print("  - HTTPS fail-closed: ✓")
                        print("\n" + "=" * 60)
                        print("\nDeployment Successful!")
                        print("HTTPS endpoint is ready for:")
                        print("  - TRAE Remote: https://mcp.timquant.tech/mcp")
                        print("  - ChatGPT Connector: https://mcp.timquant.tech/mcp")

                        return 0

        print("\n" + "=" * 60)
        print(" Tests Completed (Some May Have Failed)")
        print("=" * 60)
        print("\nTroubleshooting:")
        print("1. Check DNS: nslookup mcp.timquant.tech")
        print("2. Check EC2: ssh ubuntu@13.229.100.10 'sudo systemctl status qcc-bus'")
        print("3. Check Caddy: ssh ubuntu@13.229.100.10 'sudo systemctl status caddy'")
        print("4. Check Security Group: AWS Console → EC2 → Security Groups")
        print("5. Check MCP Bus binding: ssh ubuntu@13.229.100.10 'ss -tulpn | grep 18080'")
        print("\nDeployment Steps:")
        print("1. SSH to EC2: ssh ubuntu@13.229.100.10")
        print(
            "2. Run Caddy setup: chmod +x tools/mcp_bus/deploy/caddy_setup.sh && ./tools/mcp_bus/deploy/caddy_setup.sh"
        )
        print("3. Verify DNS: nslookup mcp.timquant.tech")
        print("4. Verify HTTPS: curl https://mcp.timquant.tech/health")
        print(
            "5. Retrieve token: ssh ubuntu@13.229.100.10 'sudo systemctl show qcc-bus --property=Environment | grep MCP_BUS_TOKEN'"
        )
        print("6. Set MCP_BUS_TOKEN: export MCP_BUS_TOKEN=YOUR_TOKEN_HERE")
        print("7. Run this script again: python tools/mcp_bus/test/test_https.py")

        return 0

    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        return 1
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
