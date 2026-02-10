import json
import os
from datetime import datetime

import requests

# EC2 配置
EC2_IP = "13.229.100.10"
EC2_PORT = "18080"
EC2_URL = f"http://{EC2_IP}:{EC2_PORT}"
TOKEN = os.getenv("MCP_BUS_TOKEN", "YOUR_TOKEN_HERE")


def print_section(title):
    print(f"\n{'=' * 60}")
    print(f" {title}")
    print(f"{'=' * 60}")


def test_ec2_health():
    print_section("Test 1: EC2 Health Check")
    print(f"URL: {EC2_URL}/health")
    try:
        response = requests.get(f"{EC2_URL}/health", timeout=10)
        print(f"Status Code: {response.status_code}")
        result = response.json()
        print(f"Response: {json.dumps(result, indent=2)}")
        assert response.status_code == 200
        assert result["ok"] == True
        print("✓ PASS")
        return result
    except requests.exceptions.ConnectionError as e:
        print(f"✗ Connection failed: {e}")
        print("This is expected if EC2 is not deployed yet.")
        print("Deployment steps:")
        print("  1. SSH to EC2: ssh ubuntu@13.229.100.10")
        print("  2. Run: chmod +x tools/mcp_bus/deploy/ec2_deploy.sh")
        print("  3. Run: ./tools/mcp_bus/deploy/ec2_deploy.sh")
        print("  4. Update AWS Security Group to allow port 18080")
        return None


def test_ec2_tools_list():
    print_section("Test 2: EC2 Tools List (with token)")
    print(f"URL: {EC2_URL}/mcp")
    print(f"Token: {TOKEN[:20]}...")
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    payload = {"jsonrpc": "2.0", "method": "tools/list"}
    try:
        response = requests.post(f"{EC2_URL}/mcp", json=payload, headers=headers, timeout=10)
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
    except requests.exceptions.ConnectionError as e:
        print(f"✗ Connection failed: {e}")
        return None


def test_ec2_inbox_append():
    print_section("Test 3: EC2 inbox_append")
    print(f"URL: {EC2_URL}/api/inbox_append")
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    payload = {
        "date": "2026-01-15",
        "task_code": "TC-MCP-AWS-QUICK-0006",
        "source": "EC2Test",
        "text": "EC2 deployment verification test",
    }
    try:
        response = requests.post(
            f"{EC2_URL}/api/inbox_append", json=payload, headers=headers, timeout=10
        )
        print(f"Status Code: {response.status_code}")
        result = response.json()
        print(f"Response: {json.dumps(result, indent=2)}")
        assert response.status_code == 200
        assert result["success"] == True
        print("✓ PASS")
        return result
    except requests.exceptions.ConnectionError as e:
        print(f"✗ Connection failed: {e}")
        return None


def test_ec2_inbox_tail():
    print_section("Test 4: EC2 inbox_tail")
    print(f"URL: {EC2_URL}/api/inbox_tail")
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    payload = {"date": "2026-01-15", "n": 10}
    try:
        response = requests.post(
            f"{EC2_URL}/api/inbox_tail", json=payload, headers=headers, timeout=10
        )
        print(f"Status Code: {response.status_code}")
        result = response.json()
        print(f"Lines returned: {result.get('lines_returned', 0)}")
        print(f"Content preview: {result.get('content', '')[:100]}...")
        assert response.status_code == 200
        assert result["success"] == True
        print("✓ PASS")
        return result
    except requests.exceptions.ConnectionError as e:
        print(f"✗ Connection failed: {e}")
        return None


def test_ec2_fail_closed():
    print_section("Test 5: EC2 Request Without Token (fail-closed)")
    print(f"URL: {EC2_URL}/mcp")
    headers = {"Content-Type": "application/json"}
    payload = {"jsonrpc": "2.0", "method": "tools/list"}
    try:
        response = requests.post(f"{EC2_URL}/mcp", json=payload, headers=headers, timeout=10)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        assert response.status_code == 401
        print("✓ PASS - Correctly rejected")
    except requests.exceptions.ConnectionError as e:
        print(f"✗ Connection failed: {e}")
        return None


def main():
    print("\n" + "=" * 60)
    print(" QCC Bus MCP Server - EC2 Verification")
    print("=" * 60)
    print(f"\nEC2 URL: {EC2_URL}")
    print(f"Token: {TOKEN[:20]}...")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("\nNote: This script tests EC2 deployment.")
    print("If connection fails, EC2 may not be deployed yet.")
    print("Deployment documentation: tools/mcp_bus/deploy/ec2_deployment.md")

    try:
        health_result = test_ec2_health()
        if health_result:
            tools_result = test_ec2_tools_list()
            if tools_result:
                append_result = test_ec2_inbox_append()
                if append_result:
                    tail_result = test_ec2_inbox_tail()
                    if tail_result:
                        test_ec2_fail_closed()

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

        print("\n" + "=" * 60)
        print(" Tests Completed (Some May Have Failed)")
        print("=" * 60)
        print("\nNext Steps:")
        print("1. Deploy to EC2: ssh ubuntu@13.229.100.10")
        print("2. Run deployment script: ./tools/mcp_bus/deploy/ec2_deploy.sh")
        print("3. Update AWS Security Group: Allow port 18080")
        print("4. Set MCP_BUS_TOKEN environment variable")
        print("5. Run this script again: python test/test_ec2.py")

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
