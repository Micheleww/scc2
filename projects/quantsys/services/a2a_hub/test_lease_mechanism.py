#!/usr/bin/env python3
"""
Direct test script for lease mechanism

This script directly tests the lease mechanism without requiring a full agent.
"""

import os
import subprocess
import sys
import time

import requests

# Configuration
HUB_URL = "http://localhost:18788/api"
TEST_TASK_CODE = "TEST-LEASE-MECHANISM-001"
DEFAULT_LEASE_SECONDS = 10  # Short lease for testing


def start_hub():
    """Start the hub in a background process"""
    print("Starting A2A Hub...")
    env = os.environ.copy()
    env["A2A_HUB_SECRET_KEY"] = "test-secret"

    hub_process = subprocess.Popen(
        [sys.executable, "tools/a2a_hub/main.py"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    # Wait for hub to start
    time.sleep(2)

    return hub_process


def stop_hub(hub_process):
    """Stop the hub process"""
    print("Stopping A2A Hub...")
    hub_process.terminate()
    hub_process.wait()


def test_lease_mechanism():
    """Test the lease mechanism directly"""
    print("=== Testing Lease Mechanism ===")

    # Step 1: Create a task
    print("1. Creating task...")
    payload = {
        "TaskCode": TEST_TASK_CODE,
        "instructions": "echo 'test'",
        "owner_role": "execution_engine",
        "area": "test",
        "how_to_repro": "test",
        "expected": "test",
        "evidence_requirements": "test",
    }

    response = requests.post(
        f"{HUB_URL}/api/task/create", json=payload, headers={"Content-Type": "application/json"}
    )

    if response.status_code != 200:
        print(f"Failed to create task: {response.status_code} - {response.text}")
        return False

    task = response.json()
    task_id = task["task_id"]
    print(f"Task created successfully: {task_id}")

    # Step 2: Manually update task to RUNNING with lease
    print("2. Updating task to RUNNING with lease...")
    now = time.time()
    lease_expiry = now + DEFAULT_LEASE_SECONDS
    lease_expiry_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(lease_expiry))

    # Direct database access to bypass agent requirement
    import sqlite3

    from tools.a2a_hub.main import DB_PATH

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Update task status and set lease
    cursor.execute(
        """
    UPDATE tasks 
    SET status = ?, lease_expiry_ts = ?, lease_seconds = ? 
    WHERE id = ?
    """,
        ("RUNNING", lease_expiry_ts, DEFAULT_LEASE_SECONDS, task_id),
    )

    conn.commit()
    conn.close()

    # Step 3: Check initial status
    print("3. Checking task status...")
    response = requests.get(f"{HUB_URL}/api/task/status?task_id={task_id}")
    if response.status_code != 200:
        print(f"Failed to get task status: {response.status_code} - {response.text}")
        return False

    task_status = response.json()
    if task_status["task"]["status"] != "RUNNING":
        print(f"Task not in RUNNING status: {task_status}")
        return False

    print(f"Task is in RUNNING status with lease expiry: {task_status['task']['lease_expiry_ts']}")

    # Step 4: Test heartbeat extension
    print("4. Testing heartbeat extension...")
    response = requests.post(
        f"{HUB_URL}/api/task/heartbeat",
        json={"task_id": task_id},
        headers={"Content-Type": "application/json"},
    )

    if response.status_code != 200:
        print(f"Failed to send heartbeat: {response.status_code} - {response.text}")
        return False

    heartbeat_result = response.json()
    print(f"Heartbeat successful, new lease expiry: {heartbeat_result['new_lease_expiry']}")

    # Step 5: Wait for lease to expire
    print(f"5. Waiting {DEFAULT_LEASE_SECONDS + 5} seconds for lease to expire...")
    time.sleep(DEFAULT_LEASE_SECONDS + 5)

    # Step 6: Check if task status changed to PENDING
    print("6. Checking task status after lease expiry...")
    response = requests.get(f"{HUB_URL}/api/task/status?task_id={task_id}")
    if response.status_code != 200:
        print(f"Failed to get task status: {response.status_code} - {response.text}")
        return False

    task_status = response.json()
    if task_status["task"]["status"] == "PENDING":
        print("✓ SUCCESS: Task status changed to PENDING after lease expiry!")
        return True
    else:
        print(
            f"✗ FAILURE: Task status not PENDING after lease expiry: {task_status['task']['status']}"
        )
        return False


def main():
    """Main test function"""
    print("Starting direct lease mechanism test...")

    # Start hub
    hub_process = start_hub()

    try:
        # Run test
        test_passed = test_lease_mechanism()

        # Print summary
        print("\n=== Test Result ===")
        print(f"Lease Mechanism Test: {'PASS' if test_passed else 'FAIL'}")

        return 0 if test_passed else 1

    finally:
        # Stop hub
        stop_hub(hub_process)


if __name__ == "__main__":
    sys.exit(main())
