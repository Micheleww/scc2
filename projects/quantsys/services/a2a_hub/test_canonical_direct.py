#!/usr/bin/env python3
"""
Direct test script for canonical pack validation in A2A Hub
This script directly calls the validate_canonical_pack function without HTTP API
"""

import os
import sys
import uuid

# Add the project root to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

# Import the validation function from the A2A hub module
from tools.a2a_hub.main import validate_canonical_pack


def test_missing_field():
    """Test that a pack missing a required field is rejected"""
    print("=== Test 1: Missing Required Field ===")

    # Create a pack with missing ruleset_sha256 field
    pack = {
        "task_code": "A2A-RESULT-CANONICAL-PACK-v0.1__20260116",
        "trace_id": str(uuid.uuid4()),
        "status": "PASS",
        "submit_path": "artifacts/TASK-v0.1__20260116/SUBMIT.txt",
        "ata_path": "artifacts/TASK-v0.1__20260116/ata",
        "evidence_paths": ["artifacts/TASK-v0.1__20260116/log.txt"],
        "sha256_map": {
            "artifacts/TASK-v0.1__20260116/SUBMIT.txt": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        },
        # Missing ruleset_sha256
    }

    is_valid, reason_code, message = validate_canonical_pack(pack)
    print(
        f"Result: {'Valid' if is_valid else 'Invalid'}, Reason: {reason_code}, Message: {message}"
    )

    if not is_valid and reason_code == "MISSING_REQUIRED_FIELD":
        print("✅ Test PASSED: Missing field correctly rejected")
        return True
    else:
        print("❌ Test FAILED: Missing field was not rejected")
        return False


def test_invalid_order():
    """Test that a pack with invalid field order is rejected"""
    print("\n=== Test 2: Invalid Field Order ===")

    # Create a pack with fields in wrong order
    # Note: In Python, dictionaries preserve insertion order since Python 3.7
    pack = {
        "status": "PASS",  # Wrong order - should be third field
        "task_code": "A2A-RESULT-CANONICAL-PACK-v0.1__20260116",
        "trace_id": str(uuid.uuid4()),
        "submit_path": "artifacts/TASK-v0.1__20260116/SUBMIT.txt",
        "ata_path": "artifacts/TASK-v0.1__20260116/ata",
        "evidence_paths": ["artifacts/TASK-v0.1__20260116/log.txt"],
        "sha256_map": {
            "artifacts/TASK-v0.1__20260116/SUBMIT.txt": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        },
        "ruleset_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    }

    is_valid, reason_code, message = validate_canonical_pack(pack)
    print(
        f"Result: {'Valid' if is_valid else 'Invalid'}, Reason: {reason_code}, Message: {message}"
    )

    if not is_valid and reason_code == "INVALID_FIELD_ORDER":
        print("✅ Test PASSED: Invalid field order correctly rejected")
        return True
    else:
        print("❌ Test FAILED: Invalid field order was not rejected")
        return False


def test_valid_pack():
    """Test that a valid pack is accepted"""
    print("\n=== Test 3: Valid Canonical Pack ===")

    # Create a valid pack with all required fields in correct order
    pack = {
        "task_code": "A2A-RESULT-CANONICAL-PACK-v0.1__20260116",
        "trace_id": str(uuid.uuid4()),
        "status": "PASS",
        "submit_path": "artifacts/TASK-v0.1__20260116/SUBMIT.txt",
        "ata_path": "artifacts/TASK-v0.1__20260116/ata",
        "evidence_paths": [
            "artifacts/TASK-v0.1__20260116/log.txt",
            "artifacts/TASK-v0.1__20260116/results.json",
        ],
        "sha256_map": {
            "artifacts/TASK-v0.1__20260116/SUBMIT.txt": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            "artifacts/TASK-v0.1__20260116/results.json": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        },
        "ruleset_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    }

    is_valid, reason_code, message = validate_canonical_pack(pack)
    print(
        f"Result: {'Valid' if is_valid else 'Invalid'}, Reason: {reason_code}, Message: {message}"
    )

    if is_valid:
        print("✅ Test PASSED: Valid pack correctly accepted")
        return True
    else:
        print("❌ Test FAILED: Valid pack was rejected")
        return False


def test_invalid_uuid():
    """Test that a pack with invalid UUID is rejected"""
    print("\n=== Test 4: Invalid UUID ===")

    # Create a pack with invalid UUID
    pack = {
        "task_code": "A2A-RESULT-CANONICAL-PACK-v0.1__20260116",
        "trace_id": "invalid-uuid",  # Invalid UUID
        "status": "PASS",
        "submit_path": "artifacts/TASK-v0.1__20260116/SUBMIT.txt",
        "ata_path": "artifacts/TASK-v0.1__20260116/ata",
        "evidence_paths": ["artifacts/TASK-v0.1__20260116/log.txt"],
        "sha256_map": {
            "artifacts/TASK-v0.1__20260116/SUBMIT.txt": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        },
        "ruleset_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    }

    is_valid, reason_code, message = validate_canonical_pack(pack)
    print(
        f"Result: {'Valid' if is_valid else 'Invalid'}, Reason: {reason_code}, Message: {message}"
    )

    if not is_valid and reason_code == "INVALID_UUID":
        print("✅ Test PASSED: Invalid UUID correctly rejected")
        return True
    else:
        print("❌ Test FAILED: Invalid UUID was not rejected")
        return False


def test_invalid_status():
    """Test that a pack with invalid status is rejected"""
    print("\n=== Test 5: Invalid Status ===")

    # Create a pack with invalid status
    pack = {
        "task_code": "A2A-RESULT-CANONICAL-PACK-v0.1__20260116",
        "trace_id": str(uuid.uuid4()),
        "status": "INVALID_STATUS",  # Invalid status
        "submit_path": "artifacts/TASK-v0.1__20260116/SUBMIT.txt",
        "ata_path": "artifacts/TASK-v0.1__20260116/ata",
        "evidence_paths": ["artifacts/TASK-v0.1__20260116/log.txt"],
        "sha256_map": {
            "artifacts/TASK-v0.1__20260116/SUBMIT.txt": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        },
        "ruleset_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    }

    is_valid, reason_code, message = validate_canonical_pack(pack)
    print(
        f"Result: {'Valid' if is_valid else 'Invalid'}, Reason: {reason_code}, Message: {message}"
    )

    if not is_valid and reason_code == "INVALID_STATUS":
        print("✅ Test PASSED: Invalid status correctly rejected")
        return True
    else:
        print("❌ Test FAILED: Invalid status was not rejected")
        return False


def test_invalid_sha256():
    """Test that a pack with invalid SHA256 is rejected"""
    print("\n=== Test 6: Invalid SHA256 ===")

    # Create a pack with invalid SHA256
    pack = {
        "task_code": "A2A-RESULT-CANONICAL-PACK-v0.1__20260116",
        "trace_id": str(uuid.uuid4()),
        "status": "PASS",
        "submit_path": "artifacts/TASK-v0.1__20260116/SUBMIT.txt",
        "ata_path": "artifacts/TASK-v0.1__20260116/ata",
        "evidence_paths": ["artifacts/TASK-v0.1__20260116/log.txt"],
        "sha256_map": {
            "artifacts/TASK-v0.1__20260116/SUBMIT.txt": "invalid-sha256"  # Invalid SHA256
        },
        "ruleset_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    }

    is_valid, reason_code, message = validate_canonical_pack(pack)
    print(
        f"Result: {'Valid' if is_valid else 'Invalid'}, Reason: {reason_code}, Message: {message}"
    )

    if not is_valid and reason_code == "INVALID_SHA256":
        print("✅ Test PASSED: Invalid SHA256 correctly rejected")
        return True
    else:
        print("❌ Test FAILED: Invalid SHA256 was not rejected")
        return False


def main():
    """Run all tests"""
    print("Running A2A Result Canonical Pack Direct Tests...\n")

    tests = [
        test_missing_field,
        test_invalid_order,
        test_valid_pack,
        test_invalid_uuid,
        test_invalid_status,
        test_invalid_sha256,
    ]

    passed = 0
    total = len(tests)

    for test in tests:
        if test():
            passed += 1

    print("\n=== Test Results ===")
    print(f"Passed: {passed}/{total}")

    if passed == total:
        print("🎉 All tests PASSED!")
        exit(0)
    else:
        print("💥 Some tests FAILED!")
        exit(1)


if __name__ == "__main__":
    main()
