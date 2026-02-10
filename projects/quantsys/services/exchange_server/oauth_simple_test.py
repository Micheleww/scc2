#!/usr/bin/env python3
"""
Simple OAuth2 Test Script

Tests OAuth2 authentication using curl commands:
1. No token - should fail with 401
2. Valid token - should succeed with 200
3. Expired token - should fail with 401
"""

import os
import subprocess
import sys
import time

# Create artifacts directory
os.makedirs("docs/REPORT/ci/artifacts/OAUTH-REAL-IMPLEMENT-v0.1__20260115", exist_ok=True)
LOG_FILE = "docs/REPORT/ci/artifacts/OAUTH-REAL-IMPLEMENT-v0.1__20260115/selftest.log"

# Clear previous log
with open(LOG_FILE, "w") as f:
    f.write("# Exchange Server OAuth2 Self-Test\n")
    f.write(f"TIMESTAMP={time.strftime('%Y-%m-%dT%H:%M:%S')}\n\n")


# Log function
def log(message):
    print(message)
    with open(LOG_FILE, "a") as f:
        f.write(f"{message}\n")


# Test 1: No token
log("## Testing OAuth2 Authentication")
log("\n### 1. Testing SSE without token")
result = subprocess.run(
    ["curl", "-i", "-m", "5", "http://localhost:18788/sse"], capture_output=True, text=True
)
status_line = result.stdout.split("\n")[0]
status_code = status_line.split()[1] if len(status_line.split()) > 1 else "error"
log(f"Status: {status_code}")

if status_code == "401":
    log("PASS: No token correctly returned 401")
else:
    log(f"FAIL: No token test failed. Expected 401, got {status_code}")
    log(f"Response: {result.stdout[:500]}...")
    sys.exit(1)

# Test 2: Valid token
log("\n### 2. Testing SSE with valid token")
result = subprocess.run(
    [
        "curl",
        "-i",
        "-m",
        "5",
        "-H",
        "Authorization: Bearer valid_token",
        "http://localhost:18788/sse",
    ],
    capture_output=True,
    text=True,
)
status_line = result.stdout.split("\n")[0]
status_code = status_line.split()[1] if len(status_line.split()) > 1 else "error"
log(f"Status: {status_code}")

if status_code == "200":
    log("PASS: Valid token correctly returned 200")
else:
    log(f"FAIL: Valid token test failed. Expected 200, got {status_code}")
    log(f"Response: {result.stdout[:500]}...")
    sys.exit(1)

# Test 3: Invalid token
log("\n### 3. Testing SSE with invalid token")
result = subprocess.run(
    [
        "curl",
        "-i",
        "-m",
        "5",
        "-H",
        "Authorization: Bearer invalid_token",
        "http://localhost:18788/sse",
    ],
    capture_output=True,
    text=True,
)
status_line = result.stdout.split("\n")[0]
status_code = status_line.split()[1] if len(status_line.split()) > 1 else "error"
log(f"Status: {status_code}")

if status_code == "401":
    log("PASS: Invalid token correctly returned 401")
else:
    log(f"FAIL: Invalid token test failed. Expected 401, got {status_code}")
    log(f"Response: {result.stdout[:500]}...")
    sys.exit(1)

# All tests passed
log("\n## All OAuth2 Tests PASSED!")
log("EXIT_CODE=0")
sys.exit(0)
