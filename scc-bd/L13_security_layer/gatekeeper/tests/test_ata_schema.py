#!/usr/bin/env python3
"""
ATA Schema Validation Test Script

Tests the ATA context schema validation with various scenarios:
1. Valid v0.2 schema (should PASS)
2. Invalid v0.2 schema with missing fields (should FAIL)
3. Valid v0.1 schema for backward compatibility (should PASS with warning)

Exit Code: 0 if all tests pass as expected, 1 otherwise
"""

import os
import subprocess
import sys

# Get the project root directory
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def run_validation_test(test_file, expected_exit_code, test_name):
    """
    Run validation on a test file and check the exit code.

    Args:
        test_file (str): Path to the test JSON file
        expected_exit_code (int): Expected exit code (0 for pass, 1 for fail)
        test_name (str): Name of the test case

    Returns:
        bool: True if test passed as expected, False otherwise
    """
    print(f"\n=== Running Test: {test_name} ===")
    print(f"Test file: {test_file}")
    print(f"Expected exit code: {expected_exit_code}")

    # Run the validation script
    cmd = [
        sys.executable,
        os.path.join(PROJECT_ROOT, "tools", "gatekeeper", "commands", "validate_ata.py"),
        "--path",
        test_file,
    ]

    try:
        result = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True, check=False)

        actual_exit_code = result.returncode

        print(f"Actual exit code: {actual_exit_code}")
        print(f"STDOUT:\n{result.stdout}")
        if result.stderr:
            print(f"STDERR:\n{result.stderr}")

        if actual_exit_code == expected_exit_code:
            print(f"✅ Test PASSED: {test_name}")
            return True
        else:
            print(f"❌ Test FAILED: {test_name}")
            print(f"   Expected exit code {expected_exit_code}, got {actual_exit_code}")
            return False

    except Exception as e:
        print(f"❌ Test ERROR: {test_name}")
        print(f"   Exception: {e}")
        return False


def main():
    """
    Main test function
    """
    print("🚀 ATA Schema Validation Test Suite")
    print("=" * 50)

    # Test cases definition
    test_cases = [
        {
            "test_file": "tools/gatekeeper/tests/ata_test_cases/valid_v0.2.json",
            "expected_exit_code": 0,
            "test_name": "Valid v0.2 Schema",
        },
        {
            "test_file": "tools/gatekeeper/tests/ata_test_cases/invalid_missing_fields.json",
            "expected_exit_code": 1,
            "test_name": "Invalid v0.2 Schema (Missing Fields)",
        },
        {
            "test_file": "tools/gatekeeper/tests/ata_test_cases/valid_v0.1.json",
            "expected_exit_code": 0,
            "test_name": "Valid v0.1 Schema (Backward Compatibility)",
        },
    ]

    # Run all tests
    passed_tests = 0
    total_tests = len(test_cases)

    for test_case in test_cases:
        if run_validation_test(
            test_case["test_file"], test_case["expected_exit_code"], test_case["test_name"]
        ):
            passed_tests += 1

    print("\n" + "=" * 50)
    print(f"📊 Test Results: {passed_tests}/{total_tests} tests passed")

    if passed_tests == total_tests:
        print("🎉 All tests passed! Validation is working correctly.")
        return 0
    else:
        print("💥 Some tests failed! Please check the validation implementation.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
