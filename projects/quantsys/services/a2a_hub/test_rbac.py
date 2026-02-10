#!/usr/bin/env python3
"""
Test script for RBAC functionality in A2A Hub
"""

import json

import requests

# Test configuration
BASE_URL = "http://localhost:18788/api"

# Test tasks
test_task = {
    "task_code": "TEST-RBAC-001",
    "area": "test",
    "owner_role": "test",
    "instructions": "Test task for RBAC",
    "how_to_repro": "Run the test",
    "expected": "Success",
    "evidence_requirements": "None",
}


def test_rbac():
    """
    Test RBAC functionality by sending requests with different roles
    """
    print("Testing RBAC functionality...")

    # Test cases: (role, endpoint, method, data, expected_success)
    test_cases = [
        # Test task creation permissions
        ("submitter", "/api/task/create", "POST", test_task, True),
        ("worker", "/api/task/create", "POST", test_task, False),
        ("auditor", "/api/task/create", "POST", test_task, False),
        ("admin", "/api/task/create", "POST", test_task, True),
        # Test task status permissions
        ("submitter", "/api/task/status", "GET", None, True),
        ("worker", "/api/task/status", "GET", None, False),
        ("auditor", "/api/task/status", "GET", None, True),
        ("admin", "/api/task/status", "GET", None, True),
        # Test DLQ replay permissions
        ("submitter", "/api/dlq/replay", "POST", {"dlq_id": "test"}, False),
        ("worker", "/api/dlq/replay", "POST", {"dlq_id": "test"}, False),
        ("auditor", "/api/dlq/replay", "POST", {"dlq_id": "test"}, False),
        (
            "admin",
            "/api/dlq/replay",
            "POST",
            {"dlq_id": "test"},
            False,
        ),  # Will fail due to invalid dlq_id but not due to ACL
        # Test agent registration permissions
        (
            "submitter",
            "/api/agent/register",
            "POST",
            {
                "agent_id": "test-agent",
                "owner_role": "test",
                "capabilities": ["test"],
                "allowed_tools": ["test"],
            },
            False,
        ),
        (
            "worker",
            "/api/agent/register",
            "POST",
            {
                "agent_id": "test-agent",
                "owner_role": "test",
                "capabilities": ["test"],
                "allowed_tools": ["test"],
            },
            False,
        ),
        (
            "auditor",
            "/api/agent/register",
            "POST",
            {
                "agent_id": "test-agent",
                "owner_role": "test",
                "capabilities": ["test"],
                "allowed_tools": ["test"],
            },
            False,
        ),
        (
            "admin",
            "/api/agent/register",
            "POST",
            {
                "agent_id": "test-agent",
                "owner_role": "test",
                "capabilities": ["test"],
                "allowed_tools": ["test"],
            },
            True,
        ),
    ]

    passed = 0
    failed = 0

    for role, endpoint, method, data, expected_success in test_cases:
        url = f"{BASE_URL}{endpoint}"
        headers = {
            "Content-Type": "application/json",
            "X-A2A-Role": role,
            "X-A2A-Token": f"test-token-{role}",
        }

        print(f"\nTesting {method} {endpoint} with role {role}...")

        try:
            if method == "GET":
                response = requests.get(url, headers=headers, params=data)
            else:
                response = requests.post(url, headers=headers, json=data)

            response_data = response.json()
            success = response_data.get("success", False)
            reason_code = response_data.get("reason_code", "")

            print(f"  Status: {response.status_code}")
            print(f"  Response: {json.dumps(response_data, indent=2)}")

            # Check if the request was successful as expected
            if expected_success:
                if success:
                    print("  ✅ PASS: Request succeeded as expected")
                    passed += 1
                else:
                    print("  ❌ FAIL: Request failed unexpectedly")
                    failed += 1
            else:
                if not success and reason_code == "acl_denied":
                    print("  ✅ PASS: Request was denied with acl_denied as expected")
                    passed += 1
                else:
                    print("  ❌ FAIL: Request was not denied with acl_denied as expected")
                    failed += 1

        except Exception as e:
            print(f"  ❌ FAIL: Request failed with exception: {e}")
            failed += 1

    print("\n\nTest Results:")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Total: {passed + failed}")

    if failed == 0:
        print("\n✅ All tests passed! RBAC functionality is working correctly.")
        return True
    else:
        print(f"\n❌ {failed} tests failed. Please check the RBAC implementation.")
        return False


if __name__ == "__main__":
    test_rbac()
