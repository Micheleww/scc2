#!/usr/bin/env python3
"""
A2A Artifact Signing and Verification Test
Tests the artifact signing and verification functionality with various scenarios
"""

import hashlib
import hmac
import json
import os
import sys
from datetime import datetime, timedelta

# Configuration
ARTIFACTS_DIR = "D:/quantsys/docs/REPORT/a2a/artifacts/A2A-ARTIFACT-SIGN-VERIFY-v0.1__20260115"
LOG_FILE = os.path.join(ARTIFACTS_DIR, "selftest.log")

# Ensure artifacts directory exists
os.makedirs(ARTIFACTS_DIR, exist_ok=True)

# Import the verification function from main.py
sys.path.insert(0, "D:/quantsys/tools/a2a_hub")
from main import verify_artifact_signature

# Test secret key (must match the one in main.py)
TEST_SECRET_KEY = "default-test-key-for-development"


# Log function
def log(message):
    """Log message to console and file"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] {message}"
    print(log_entry)
    with open(LOG_FILE, "a") as f:
        f.write(log_entry + "\n")


# Sign artifact function
def sign_artifact(artifact, secret_key):
    """Sign an artifact pointer package"""
    # Add required fields
    artifact["signed_at"] = datetime.utcnow().isoformat() + "Z"
    artifact["signing_algorithm"] = "HMAC-SHA256"

    # Create copy without signature fields
    artifact_copy = artifact.copy()
    for field in ["signature", "signed_at", "signing_algorithm"]:
        if field in artifact_copy:
            del artifact_copy[field]

    # Generate canonical JSON
    canonical_json = json.dumps(
        artifact_copy, separators=(",", ":"), sort_keys=True, ensure_ascii=False
    )

    # Compute signature
    signature = hmac.new(
        secret_key.encode(), canonical_json.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    # Add signature to artifact
    artifact["signature"] = signature
    return artifact


# Test Case 1: Valid Signature
def test_valid_signature():
    """Test valid artifact signature verification"""
    log("=== Test Case 1: Valid Signature ===")

    # Create test artifact
    test_artifact = {
        "pointers": [
            {
                "type": "report",
                "path": "docs/REPORT/test.md",
                "sha256": "abc1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcd",
            }
        ],
        "metadata": {"version": "1.0", "author": "test"},
    }

    # Sign the artifact
    signed_artifact = sign_artifact(test_artifact, TEST_SECRET_KEY)

    # Verify the artifact
    is_valid, reason_code, message = verify_artifact_signature(signed_artifact)

    if is_valid:
        log("PASS: Valid signature verification")
        log(f"Message: {message}")
        return True
    else:
        log("FAIL: Valid signature verification failed")
        log(f"Reason: {reason_code}, Message: {message}")
        return False


# Test Case 2: Tampered Artifact
def test_tampered_artifact():
    """Test tampered artifact signature verification"""
    log("\n=== Test Case 2: Tampered Artifact ===")

    # Create test artifact
    test_artifact = {
        "pointers": [
            {
                "type": "report",
                "path": "docs/REPORT/test.md",
                "sha256": "abc1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcd",
            }
        ]
    }

    # Sign the artifact
    signed_artifact = sign_artifact(test_artifact, TEST_SECRET_KEY)

    # Tamper with the artifact
    signed_artifact["pointers"][0]["sha256"] = (
        "tamperedhash1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcd"
    )

    # Verify the artifact
    is_valid, reason_code, message = verify_artifact_signature(signed_artifact)

    if not is_valid and reason_code == "ARTIFACT_SIGNATURE_INVALID":
        log("PASS: Tampered artifact correctly detected")
        log(f"Reason: {reason_code}, Message: {message}")
        return True
    else:
        log("FAIL: Tampered artifact not detected correctly")
        log(f"Reason: {reason_code}, Message: {message}")
        return False


# Test Case 3: Missing Signature Fields
def test_missing_signature_fields():
    """Test artifact with missing signature fields"""
    log("\n=== Test Case 3: Missing Signature Fields ===")

    # Create artifact without signature fields
    test_artifact = {
        "pointers": [
            {
                "type": "report",
                "path": "docs/REPORT/test.md",
                "sha256": "abc1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcd",
            }
        ],
        # Missing signature, signed_at, signing_algorithm
    }

    # Verify the artifact
    is_valid, reason_code, message = verify_artifact_signature(test_artifact)

    if not is_valid and reason_code == "ARTIFACT_SIGNATURE_MISSING":
        log("PASS: Missing signature fields correctly detected")
        log(f"Reason: {reason_code}, Message: {message}")
        return True
    else:
        log("FAIL: Missing signature fields not detected correctly")
        log(f"Reason: {reason_code}, Message: {message}")
        return False


# Test Case 4: Expired Signature
def test_expired_signature():
    """Test expired signature verification"""
    log("\n=== Test Case 4: Expired Signature ===")

    # Create test artifact
    test_artifact = {
        "pointers": [
            {
                "type": "report",
                "path": "docs/REPORT/test.md",
                "sha256": "abc1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcd",
            }
        ]
    }

    # Add required fields but with expired timestamp
    expired_time = datetime.utcnow() - timedelta(minutes=6)
    test_artifact["signed_at"] = expired_time.isoformat() + "Z"
    test_artifact["signing_algorithm"] = "HMAC-SHA256"

    # Create copy without signature fields for signing
    artifact_copy = test_artifact.copy()
    del artifact_copy["signed_at"]
    del artifact_copy["signing_algorithm"]

    # Generate canonical JSON
    canonical_json = json.dumps(
        artifact_copy, separators=(",", ":"), sort_keys=True, ensure_ascii=False
    )

    # Compute signature
    signature = hmac.new(
        TEST_SECRET_KEY.encode(), canonical_json.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    test_artifact["signature"] = signature

    # Verify the artifact
    is_valid, reason_code, message = verify_artifact_signature(test_artifact)

    if not is_valid and reason_code == "ARTIFACT_SIGNATURE_EXPIRED":
        log("PASS: Expired signature correctly detected")
        log(f"Reason: {reason_code}, Message: {message}")
        return True
    else:
        log("FAIL: Expired signature not detected correctly")
        log(f"Reason: {reason_code}, Message: {message}")
        return False


# Test Case 5: Invalid Algorithm
def test_invalid_algorithm():
    """Test artifact with invalid signing algorithm"""
    log("\n=== Test Case 5: Invalid Algorithm ===")

    # Create test artifact
    test_artifact = {
        "pointers": [
            {
                "type": "report",
                "path": "docs/REPORT/test.md",
                "sha256": "abc1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcd",
            }
        ]
    }

    # Sign with invalid algorithm
    test_artifact["signed_at"] = datetime.utcnow().isoformat() + "Z"
    test_artifact["signing_algorithm"] = "INVALID-ALGORITHM"

    # Create copy without signature fields for signing
    artifact_copy = test_artifact.copy()
    del artifact_copy["signed_at"]
    del artifact_copy["signing_algorithm"]

    # Generate canonical JSON
    canonical_json = json.dumps(
        artifact_copy, separators=(",", ":"), sort_keys=True, ensure_ascii=False
    )

    # Compute signature
    signature = hmac.new(
        TEST_SECRET_KEY.encode(), canonical_json.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    test_artifact["signature"] = signature

    # Verify the artifact
    is_valid, reason_code, message = verify_artifact_signature(test_artifact)

    if not is_valid and reason_code == "ARTIFACT_SIGNATURE_ALGORITHM_INVALID":
        log("PASS: Invalid algorithm correctly detected")
        log(f"Reason: {reason_code}, Message: {message}")
        return True
    else:
        log("FAIL: Invalid algorithm not detected correctly")
        log(f"Reason: {reason_code}, Message: {message}")
        return False


# Main test function
def main():
    """Run all test cases"""
    # Start with clean log file
    open(LOG_FILE, "w").close()

    log("=== A2A Artifact Signing and Verification Test ===")
    log(f"Test Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"Test Secret Key: {TEST_SECRET_KEY}")

    # Run all test cases
    test_results = {
        "valid_signature": test_valid_signature(),
        "tampered_artifact": test_tampered_artifact(),
        "missing_fields": test_missing_signature_fields(),
        "expired_signature": test_expired_signature(),
        "invalid_algorithm": test_invalid_algorithm(),
    }

    # Generate summary
    log("\n=== Test Summary ===")
    passed = sum(1 for result in test_results.values() if result)
    total = len(test_results)

    for test_name, result in test_results.items():
        status = "PASS" if result else "FAIL"
        log(f"{status}: {test_name.replace('_', ' ').title()}")

    log(f"\nOverall: {passed}/{total} tests passed")

    # Write exit code to log
    if passed == total:
        log("\nEXIT_CODE=0")
        log("All tests passed successfully!")
        return 0
    else:
        log("\nEXIT_CODE=1")
        log(f"{total - passed} test(s) failed!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
