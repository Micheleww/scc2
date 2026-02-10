#!/usr/bin/env python3
"""
Unit test script for RBAC functionality in A2A Hub
Tests the core RBAC logic directly without HTTP requests
"""

import os
import sys

# Add the current directory to the path so we can import the module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import the RBAC functions from main.py
from main import ROLES, check_permission, get_required_permission


def test_rbac_logic():
    """
    Test the RBAC logic directly
    """
    print("Testing RBAC Logic...")

    # Test cases for check_permission function
    permission_test_cases = [
        # (role, permission, expected_result)
        ("submitter", "create", True),
        ("submitter", "read_all", True),
        ("submitter", "report_result", False),
        ("submitter", "replay_dlq", False),
        ("submitter", "assign", False),
        ("worker", "report_result", True),
        ("worker", "create", False),
        ("worker", "read_all", False),
        ("worker", "replay_dlq", False),
        ("worker", "assign", False),
        ("auditor", "read_all", True),
        ("auditor", "create", False),
        ("auditor", "report_result", False),
        ("auditor", "replay_dlq", False),
        ("auditor", "assign", False),
        ("admin", "create", True),
        ("admin", "read_all", True),
        ("admin", "report_result", True),
        ("admin", "replay_dlq", True),
        ("admin", "assign", True),
        ("invalid_role", "create", False),
        ("invalid_role", "read_all", False),
    ]

    # Test cases for get_required_permission function
    endpoint_test_cases = [
        # (endpoint, method, expected_permission)
        ("/api/task/create", "POST", "create"),
        ("/api/task/status", "GET", "read_all"),
        ("/api/task/result", "POST", "report_result"),
        ("/api/task/next", "GET", "read_all"),
        ("/api/dlq/replay", "POST", "replay_dlq"),
        ("/api/agent/register", "POST", "assign"),
        ("/api/agent/123", "GET", "read_all"),
        ("/api/agent/123", "PUT", "assign"),
        ("/api/agent/123", "DELETE", "assign"),
        ("/api/dlq/123", "GET", "read_all"),
        ("/api/dlq/task/TEST-001", "GET", "read_all"),
    ]

    passed = 0
    failed = 0

    # Test check_permission function
    print("\n1. Testing check_permission function:")
    for role, permission, expected in permission_test_cases:
        result = check_permission(role, permission)
        if result == expected:
            print(
                f"   ✅ PASS: Role {role} {'has' if expected else 'does not have'} permission {permission}"
            )
            passed += 1
        else:
            print(
                f"   ❌ FAIL: Role {role} {'has' if result else 'does not have'} permission {permission}, expected {'has' if expected else 'does not have'}"
            )
            failed += 1

    # Test get_required_permission function
    print("\n2. Testing get_required_permission function:")
    for endpoint, method, expected_perm in endpoint_test_cases:
        result_perm = get_required_permission(endpoint, method)
        if result_perm == expected_perm:
            print(f"   ✅ PASS: {method} {endpoint} requires permission {expected_perm}")
            passed += 1
        else:
            print(
                f"   ❌ FAIL: {method} {endpoint} returned permission {result_perm}, expected {expected_perm}"
            )
            failed += 1

    # Test role definitions
    print("\n3. Testing role definitions:")
    expected_roles = ["submitter", "worker", "auditor", "admin"]
    for role in expected_roles:
        if role in ROLES:
            print(f"   ✅ PASS: Role {role} is defined")
            passed += 1
        else:
            print(f"   ❌ FAIL: Role {role} is not defined")
            failed += 1

    # Print summary
    print("\n\nTest Results:")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Total: {passed + failed}")

    if failed == 0:
        print("\n✅ All tests passed! RBAC logic is working correctly.")
        return True
    else:
        print(f"\n❌ {failed} tests failed. Please check the RBAC implementation.")
        return False


if __name__ == "__main__":
    success = test_rbac_logic()
    sys.exit(0 if success else 1)
