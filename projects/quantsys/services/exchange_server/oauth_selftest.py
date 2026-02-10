#!/usr/bin/env python3
"""
Exchange Server OAuth2 Self-Test Script

Tests OAuth2 authentication for SSE endpoints:
1. No token - should fail with 401
2. Valid token - should succeed with 200
3. Expired token - should fail with 401
"""

import asyncio
import os
import subprocess
import sys
import time

from aiohttp import ClientSession

# Project root directory
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SELTEST_LOG_PATH = "docs/REPORT/ci/artifacts/OAUTH-REAL-IMPLEMENT-v0.1__20260115/selftest.log"


async def run_command(cmd):
    """Run a command and return its output"""
    process = await asyncio.create_subprocess_shell(
        cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()
    return {"stdout": stdout.decode(), "stderr": stderr.decode(), "returncode": process.returncode}


async def test_sse_no_token(session):
    """Test SSE without token - should fail"""
    url = "http://localhost:18788/sse"

    try:
        async with session.get(url, timeout=5) as response:
            return {
                "status": response.status,
                "success": response.status == 401,  # Expected to fail with 401
            }
    except Exception as e:
        return {"status": "error", "success": False, "error": str(e)}


async def test_sse_valid_token(session):
    """Test SSE with valid token - should succeed"""
    url = "http://localhost:18788/sse"
    headers = {"Authorization": "Bearer valid_token"}

    try:
        async with session.get(url, headers=headers, timeout=5) as response:
            return {
                "status": response.status,
                "success": response.status == 200,  # Expected to succeed with 200
            }
    except Exception as e:
        return {"status": "error", "success": False, "error": str(e)}


async def test_sse_expired_token(session):
    """Test SSE with expired token - should fail"""
    url = "http://localhost:18788/sse"
    headers = {"Authorization": "Bearer expired_token"}

    try:
        async with session.get(url, headers=headers, timeout=5) as response:
            return {
                "status": response.status,
                "success": response.status == 401,  # Expected to fail with 401
            }
    except Exception as e:
        return {"status": "error", "success": False, "error": str(e)}


async def main():
    """Main self-test function"""
    # Create artifacts directory if it doesn't exist
    os.makedirs(os.path.dirname(SELTEST_LOG_PATH), exist_ok=True)

    # Clear previous log
    open(SELTEST_LOG_PATH, "w").close()

    def log(message):
        """Log a message to selftest.log"""
        print(message)
        with open(SELTEST_LOG_PATH, "a") as f:
            f.write(f"{message}\n")

    log("# Exchange Server OAuth2 Self-Test")
    log(f"TIMESTAMP={time.strftime('%Y-%m-%dT%H:%M:%S')}")
    log("")

    # Start the server in the background with OAuth2 mode enabled
    log("## Starting Exchange Server with OAuth2 mode...")
    server_cmd = f"set EXCHANGE_SSE_AUTH_MODE=oauth2&& set EXCHANGE_OAUTH2_TOKENS=valid_token|0,expired_token|{int(time.time() - 3600)}&& python -m tools.exchange_server.main"
    server_process = subprocess.Popen(
        server_cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=os.environ.copy(),
    )

    # Wait for server to start
    time.sleep(3)

    try:
        log("## Testing OAuth2 Authentication")

        async with ClientSession() as session:
            # Test 1: No token
            log("\n### 1. Testing SSE without token")
            result = await test_sse_no_token(session)
            log(f"Status: {result['status']}")

            if result["success"]:
                log("PASS: No token correctly returned 401")
            else:
                log(f"FAIL: No token test failed: {result.get('error', 'Unexpected status')}")
                return 1

            # Test 2: Valid token
            log("\n### 2. Testing SSE with valid token")
            result = await test_sse_valid_token(session)
            log(f"Status: {result['status']}")

            if result["success"]:
                log("PASS: Valid token correctly returned 200")
            else:
                log(f"FAIL: Valid token test failed: {result.get('error', 'Unexpected status')}")
                return 1

            # Test 3: Expired token
            log("\n### 3. Testing SSE with expired token")
            result = await test_sse_expired_token(session)
            log(f"Status: {result['status']}")

            if result["success"]:
                log("PASS: Expired token correctly returned 401")
            else:
                log(f"FAIL: Expired token test failed: {result.get('error', 'Unexpected status')}")
                return 1

        # All tests passed
        log("\n## All OAuth2 Tests PASSED!")
        log("EXIT_CODE=0")
        return 0

    finally:
        # Stop the server
        server_process.terminate()
        try:
            server_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_process.kill()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
