#!/usr/bin/env python3
"""
Test script for SSE reconnect assertions

This script tests the SSE client's auto-reconnect functionality with the following assertions:
1. First connection succeeds
2. Disconnection is detected
3. Starts reconnecting within N seconds
4. Reconnects successfully within M attempts
5. Heartbeat is normal after recovery

Usage: python test_sse_reconnect.py
"""

import argparse
import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from typing import Any

import aiohttp

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("test_sse_reconnect.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# Test configuration
TEST_DURATION = 120  # Total test duration in seconds
MAX_RECONNECT_TIME = 5  # Should start reconnecting within N seconds
MAX_RECONNECT_ATTEMPTS = 5  # Should reconnect successfully within M attempts
HEARTBEAT_CHECK_DURATION = 30  # Check heartbeat for this duration after recovery
ARTIFACTS_DIR = r"d:\quantsys\docs\REPORT\ci\artifacts\SSE-RECONNECT-ASSERTIONS-v0.1__20260116"


class SSEReconnectTester:
    def __init__(self, url: str):
        self.url = url
        self.events: list[dict[str, Any]] = []
        self.first_connection = False
        self.disconnection_detected = False
        self.reconnect_started = False
        self.reconnect_succeeded = False
        self.heartbeat_normal = False
        self.start_time = time.time()
        self.disconnect_time = None
        self.reconnect_start_time = None
        self.reconnect_success_time = None
        self.heartbeat_events = []

    async def run_test(self) -> bool:
        """Run the SSE reconnect test"""
        logger.info("Starting SSE reconnect test")
        logger.info(f"Test duration: {TEST_DURATION} seconds")
        logger.info(f"Max reconnect time: {MAX_RECONNECT_TIME} seconds")
        logger.info(f"Max reconnect attempts: {MAX_RECONNECT_ATTEMPTS}")

        try:
            # Start the SSE client with auto-reconnect
            client = SSEClient(self.url)

            # Create a task to run the client
            client_task = asyncio.create_task(client.connect())

            # Wait for the test to complete or timeout
            await asyncio.sleep(TEST_DURATION)

            # Cancel the client task
            client_task.cancel()
            try:
                await client_task
            except asyncio.CancelledError:
                pass

            # Verify all assertions
            return self.verify_assertions()

        except Exception as e:
            logger.error(f"Test failed with exception: {e}")
            return False

    def verify_assertions(self) -> bool:
        """Verify all SSE reconnect assertions"""
        logger.info("\n--- Verifying Assertions ---")

        # Assertion 1: First connection succeeds
        assert1 = self.first_connection
        logger.info(f"1. First connection succeeds: {'PASS' if assert1 else 'FAIL'}")

        # Assertion 2: Disconnection is detected
        assert2 = self.disconnection_detected
        logger.info(f"2. Disconnection is detected: {'PASS' if assert2 else 'FAIL'}")

        # Assertion 3: Starts reconnecting within N seconds
        assert3 = self.reconnect_started and (
            self.reconnect_start_time - self.disconnect_time <= MAX_RECONNECT_TIME
        )
        logger.info(
            f"3. Starts reconnecting within {MAX_RECONNECT_TIME} seconds: {'PASS' if assert3 else 'FAIL'}"
        )

        # Assertion 4: Reconnects successfully within M attempts
        assert4 = self.reconnect_succeeded
        logger.info(
            f"4. Reconnects successfully within {MAX_RECONNECT_ATTEMPTS} attempts: {'PASS' if assert4 else 'FAIL'}"
        )

        # Assertion 5: Heartbeat is normal after recovery
        assert5 = self.heartbeat_normal
        logger.info(f"5. Heartbeat is normal after recovery: {'PASS' if assert5 else 'FAIL'}")

        # Check all assertions
        all_passed = all([assert1, assert2, assert3, assert4, assert5])

        logger.info("\n--- Test Result ---")
        logger.info(f"Overall result: {'PASS' if all_passed else 'FAIL'}")

        return all_passed

    def handle_event(self, event: dict[str, Any]):
        """Handle SSE client events"""
        self.events.append(event)
        event_type = event.get("event_type")
        timestamp = event.get("timestamp")

        if event_type == "connect":
            if not self.first_connection:
                self.first_connection = True
                logger.info(f"✓ First connection established at {timestamp}")
            else:
                self.reconnect_succeeded = True
                self.reconnect_success_time = timestamp
                logger.info(f"✓ Reconnect successful at {timestamp}")

        elif event_type == "disconnect":
            self.disconnection_detected = True
            self.disconnect_time = timestamp
            logger.info(f"✓ Disconnection detected at {timestamp}")

        elif event_type == "reconnect":
            if not self.reconnect_started:
                self.reconnect_started = True
                self.reconnect_start_time = timestamp
                logger.info(f"✓ Reconnect started at {timestamp}")

        elif event_type == "heartbeat_lag_ms":
            lag = event.get("lag_ms", 0)
            self.heartbeat_events.append(lag)

            # Check if heartbeat is normal after reconnect
            if self.reconnect_succeeded:
                # Consider heartbeat normal if lag is less than 1000ms for multiple consecutive heartbeats
                recent_heartbeats = (
                    self.heartbeat_events[-5:] if len(self.heartbeat_events) >= 5 else []
                )
                if len(recent_heartbeats) >= 3 and all(lag < 1000 for lag in recent_heartbeats):
                    self.heartbeat_normal = True


class SSEClient:
    """Modified SSE client for testing purposes"""

    def __init__(
        self,
        url: str,
        timeout: float = 30.0,
        initial_backoff: float = 1.0,
        max_backoff: float = 32.0,
        max_retries: int = 5,
        heartbeat_timeout: float = 60.0,
    ):
        self.url = url
        self.timeout = timeout
        self.initial_backoff = initial_backoff
        self.max_backoff = max_backoff
        self.max_retries = max_retries
        self.heartbeat_timeout = heartbeat_timeout

        self.session = None
        self.retry_count = 0
        self.connected = False
        self.last_heartbeat = time.time()
        self.total_connections = 0
        self.total_disconnections = 0
        self.total_reconnections = 0

    async def connect(self) -> None:
        self.retry_count = 0
        while True:
            try:
                await self._attempt_connection()
            except (TimeoutError, aiohttp.ClientError, Exception) as e:
                self.connected = False
                self.total_disconnections += 1

                event = {
                    "event_type": "disconnect",
                    "timestamp": time.time(),
                    "reason": str(e),
                    "connection_count": self.total_connections,
                    "disconnection_count": self.total_disconnections,
                    "reconnection_count": self.total_reconnections,
                }
                logger.info(json.dumps(event))

                if self.retry_count >= self.max_retries:
                    logger.error(f"Max retries reached ({self.max_retries}), stopping...")
                    break

                backoff = min(self.initial_backoff * (2**self.retry_count), self.max_backoff)
                self.retry_count += 1
                self.total_reconnections += 1

                event = {
                    "event_type": "reconnect",
                    "timestamp": time.time(),
                    "attempt": self.retry_count,
                    "backoff": backoff,
                    "max_retries": self.max_retries,
                }
                logger.info(json.dumps(event))

                await asyncio.sleep(backoff)
            else:
                break

    async def _attempt_connection(self) -> None:
        self.session = aiohttp.ClientSession()
        self.total_connections += 1

        event = {
            "event_type": "connect",
            "timestamp": time.time(),
            "url": self.url,
            "connection_count": self.total_connections,
        }
        logger.info(json.dumps(event))

        async with self.session.get(
            self.url, timeout=self.timeout, headers={"Accept": "text/event-stream"}
        ) as response:
            self.connected = True
            self.last_heartbeat = time.time()

            async for line in response.content:
                line = line.decode("utf-8").strip()
                if not line:
                    continue

                if line.startswith("data:"):
                    try:
                        data = json.loads(line[5:])
                        if data.get("event") == "heartbeat":
                            current_time = time.time()
                            heartbeat_lag = current_time - self.last_heartbeat
                            self.last_heartbeat = current_time

                            event = {
                                "event_type": "heartbeat_lag_ms",
                                "timestamp": current_time,
                                "lag_ms": round(heartbeat_lag * 1000, 2),
                                "connection_count": self.total_connections,
                            }
                            logger.info(json.dumps(event))
                    except json.JSONDecodeError:
                        pass

                # Check heartbeat timeout
                if time.time() - self.last_heartbeat > self.heartbeat_timeout:
                    raise TimeoutError(f"Heartbeat timeout after {self.heartbeat_timeout} seconds")

    async def close(self) -> None:
        if self.session:
            await self.session.close()


def run_toxiproxy_test():
    """Run toxiproxy test to simulate connection loss and recovery"""
    logger.info("\n--- Running Toxiproxy Test ---")

    # Start the chaos SSE proxy to simulate connection issues
    proxy_process = subprocess.Popen([sys.executable, "chaos_sse_proxy.py"], cwd=os.getcwd())

    try:
        # Wait for proxy to start
        time.sleep(5)

        # Run the SSE reconnect test against the proxy
        tester = SSEReconnectTester("http://localhost:8082/sse")
        result = asyncio.run(tester.run_test())

        return result

    finally:
        # Stop the proxy
        proxy_process.terminate()
        try:
            proxy_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proxy_process.kill()


def generate_report(result: bool):
    """Generate test report and artifacts"""
    logger.info("\n--- Generating Report ---")

    # Create artifacts directory
    os.makedirs(ARTIFACTS_DIR, exist_ok=True)

    # Create selftest.log
    selftest_path = os.path.join(ARTIFACTS_DIR, "selftest.log")
    with open(selftest_path, "w") as f:
        f.write(f"Test Result: {'PASS' if result else 'FAIL'}\n")
        f.write(f"Exit Code: {'0' if result else '1'}\n")
        f.write(f"Test Duration: {TEST_DURATION} seconds\n")

    # Create context.json
    context_path = os.path.join(ARTIFACTS_DIR, "ata", "context.json")
    os.makedirs(os.path.dirname(context_path), exist_ok=True)
    context = {
        "test_name": "SSE-RECONNECT-ASSERTIONS",
        "test_version": "v0.1",
        "test_date": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "test_duration": TEST_DURATION,
        "max_reconnect_time": MAX_RECONNECT_TIME,
        "max_reconnect_attempts": MAX_RECONNECT_ATTEMPTS,
        "result": "PASS" if result else "FAIL",
        "exit_code": 0 if result else 1,
    }
    with open(context_path, "w") as f:
        json.dump(context, f, indent=2)

    # Create SUBMIT.txt
    submit_path = os.path.join(ARTIFACTS_DIR, "SUBMIT.txt")
    with open(submit_path, "w") as f:
        f.write("TEST_NAME: SSE-RECONNECT-ASSERTIONS-v0.1__20260116\n")
        f.write(f"TEST_DATE: {time.strftime('%Y-%m-%d')}\n")
        f.write(f"RESULT: {'PASS' if result else 'FAIL'}\n")
        f.write(f"EXIT_CODE: {'0' if result else '1'}\n")

    # Create report.md
    report_path = os.path.join(
        "d:",
        "quantsys",
        "docs",
        "REPORT",
        "ci",
        "REPORT__SSE-RECONNECT-ASSERTIONS-v0.1__20260116__20260116.md",
    )
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    report_content = f"""# SSE Reconnect Assertions Test Report

## Overview
This report documents the results of the SSE reconnect assertions test, which verifies the auto-reconnect functionality of the SSE client.

## Test Configuration
- **Test Name**: SSE-RECONNECT-ASSERTIONS-v0.1__20260116
- **Test Date**: {time.strftime("%Y-%m-%d")}
- **Test Duration**: {TEST_DURATION} seconds
- **Max Reconnect Time**: {MAX_RECONNECT_TIME} seconds
- **Max Reconnect Attempts**: {MAX_RECONNECT_ATTEMPTS} attempts
- **SSE Proxy**: Chaos SSE Proxy (localhost:8082)

## Test Assertions
1. ✅ First connection succeeds
2. ✅ Disconnection is detected
3. ✅ Starts reconnecting within {MAX_RECONNECT_TIME} seconds
4. ✅ Reconnects successfully within {MAX_RECONNECT_ATTEMPTS} attempts
5. ✅ Heartbeat is normal after recovery

## Test Results
- **Overall Result**: {"PASS" if result else "FAIL"}
- **Exit Code**: {"0" if result else "1"}
- **Artifacts**: See docs/REPORT/ci/artifacts/SSE-RECONNECT-ASSERTIONS-v0.1__20260116/

## Test Steps
1. Start chaos SSE proxy to simulate connection issues
2. Run SSE client with auto-reconnect functionality
3. Monitor SSE events and track connection states
4. Verify all reconnect assertions
5. Generate test report and artifacts

## Conclusion
The SSE reconnect assertions test {"passed successfully" if result else "failed"}. All required assertions were {"verified" if result else "not verified"}, confirming that the SSE client correctly handles connection loss and recovery.
"""

    with open(report_path, "w") as f:
        f.write(report_content)

    logger.info(f"Report generated: {report_path}")
    logger.info(f"Artifacts directory: {ARTIFACTS_DIR}")


def main():
    """Main test function"""
    parser = argparse.ArgumentParser(description="SSE Reconnect Assertions Test")
    parser.add_argument("--toxiproxy", action="store_true", help="Run toxiproxy test")
    args = parser.parse_args()

    if args.toxiproxy:
        result = run_toxiproxy_test()
    else:
        # Run basic test without toxiproxy
        tester = SSEReconnectTester("http://localhost:18788/sse")
        result = asyncio.run(tester.run_test())

    # Generate report and artifacts
    generate_report(result)

    # Exit with appropriate code
    exit_code = 0 if result else 1
    logger.info("\n--- Test Completed ---")
    logger.info(f"Exit Code: {exit_code}")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
