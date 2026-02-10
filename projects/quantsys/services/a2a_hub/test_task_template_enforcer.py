#!/usr/bin/env python3
"""
Test script for A2A Task Template Enforcer functionality
Verifies that task creation fails when required fields are missing
and succeeds when all required fields are provided.
"""

import sys

import requests

# A2A Hub base URL
BASE_URL = "http://localhost:18788/api"


def test_create_task_missing_fields():
    """Test that creating a task with missing required fields fails."""
    print("\n1. Testing missing required fields...")

    # Test case 1: Missing all required fields (except task_code and owner_role)
    test_task = {
        "TaskCode": "TEST-TASK-MISSING-FIELDS__20260116",
        "owner_role": "Backend Engineer",
        # Missing: area, instructions, how_to_repro, expected, evidence_requirements
    }

    try:
        response = requests.post(f"{BASE_URL}/api/task/create", json=test_task, timeout=5)
        response_data = response.json()

        print(f"   Status: {response.status_code}")
        print(f"   Response: {response_data}")

        # Verify it fails with the correct reason code
        if (
            response.status_code == 400
            and response_data.get("reason_code") == "invalid_task_template"
        ):
            print("   ✅ PASS: Correctly rejected missing fields")
            return True
        else:
            print("   ❌ FAIL: Did not reject missing fields correctly")
            return False
    except Exception as e:
        print(f"   ❌ FAIL: Exception occurred: {e}")
        return False


def test_create_task_with_empty_fields():
    """Test that creating a task with empty required fields fails."""
    print("\n2. Testing empty required fields...")

    test_task = {
        "TaskCode": "TEST-TASK-EMPTY-FIELDS__20260116",
        "area": "a2a/hub",
        "owner_role": "Backend Engineer",
        "instructions": "",  # Empty field
        "how_to_repro": "1. Step 1\n2. Step 2",
        "expected": "Expected result",
        "evidence_requirements": "Evidence required",
    }

    try:
        response = requests.post(f"{BASE_URL}/api/task/create", json=test_task, timeout=5)
        response_data = response.json()

        print(f"   Status: {response.status_code}")
        print(f"   Response: {response_data}")

        # Verify it fails with the correct reason code
        if (
            response.status_code == 400
            and response_data.get("reason_code") == "invalid_task_template"
        ):
            print("   ✅ PASS: Correctly rejected empty fields")
            return True
        else:
            print("   ❌ FAIL: Did not reject empty fields correctly")
            return False
    except Exception as e:
        print(f"   ❌ FAIL: Exception occurred: {e}")
        return False


def test_create_task_all_fields_complete():
    """Test that creating a task with all required fields passes template validation."""
    print("\n3. Testing complete task template...")

    test_task = {
        "TaskCode": "TEST-TASK-COMPLETE__20260116",
        "area": "a2a/hub",
        "owner_role": "Backend Engineer",
        "instructions": "Test task template completeness",
        "how_to_repro": "1. Send create request with all fields\n2. Verify response is success\n3. Check task is created",
        "expected": "Task created successfully",
        "evidence_requirements": "Response contains success=true and task_id",
        "priority": 0,
    }

    try:
        response = requests.post(f"{BASE_URL}/api/task/create", json=test_task, timeout=5)
        response_data = response.json()

        print(f"   Status: {response.status_code}")
        print(f"   Response: {response_data}")

        # Verify it passes template validation (reason_code is not invalid_task_template)
        if response_data.get("reason_code") != "invalid_task_template":
            print("   ✅ PASS: Correctly passed template validation")
            return True
        else:
            print("   ❌ FAIL: Failed template validation unexpectedly")
            return False
    except Exception as e:
        print(f"   ❌ FAIL: Exception occurred: {e}")
        return False


def test_create_task_new_field_names():
    """Test that creating a task with new field names passes template validation."""
    print("\n4. Testing new field names...")

    test_task = {
        "task_code": "TEST-TASK-NEW-FIELDS__20260116",
        "area": "a2a/hub",
        "owner_role": "Backend Engineer",
        "instructions": "Test task with new field names",
        "how_to_repro": "1. Use task_code instead of TaskCode\n2. Send request\n3. Verify success",
        "expected": "Task created successfully",
        "evidence_requirements": "Response contains success=true",
        "priority": 1,
    }

    try:
        response = requests.post(f"{BASE_URL}/api/task/create", json=test_task, timeout=5)
        response_data = response.json()

        print(f"   Status: {response.status_code}")
        print(f"   Response: {response_data}")

        # Verify it passes template validation (reason_code is not invalid_task_template)
        if response_data.get("reason_code") != "invalid_task_template":
            print("   ✅ PASS: Correctly passed template validation with new field names")
            return True
        else:
            print("   ❌ FAIL: Failed template validation unexpectedly with new field names")
            return False
    except Exception as e:
        print(f"   ❌ FAIL: Exception occurred: {e}")
        return False


def main():
    """Run all tests and return exit code."""
    print("=== A2A Task Template Enforcer Test ===")
    print("Verifying task creation validation...")

    tests = [
        test_create_task_missing_fields,
        test_create_task_with_empty_fields,
        test_create_task_all_fields_complete,
        test_create_task_new_field_names,
    ]

    passed_tests = 0
    total_tests = len(tests)

    for test in tests:
        if test():
            passed_tests += 1

    print("\n=== Test Summary ===")
    print(f"Total Tests: {total_tests}")
    print(f"Passed Tests: {passed_tests}")
    print(f"Failed Tests: {total_tests - passed_tests}")

    if passed_tests == total_tests:
        print("✅ All tests passed!")
        print("EXIT_CODE=0")
        return 0
    else:
        print("❌ Some tests failed!")
        print("EXIT_CODE=1")
        return 1


if __name__ == "__main__":
    sys.exit(main())
