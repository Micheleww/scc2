#!/usr/bin/env python3
"""
Simple test script for heartbeat API

This script directly tests the heartbeat API and lease mechanism.
"""

import json
import os
import sqlite3
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta

# Configuration
DEFAULT_LEASE_SECONDS = 10  # Short lease for testing
DB_PATH = os.path.join(os.path.dirname(__file__), "state", "a2a_hub.db")


def start_hub():
    """Start the hub in a background process"""
    print("Starting A2A Hub...")
    env = os.environ.copy()
    env["A2A_HUB_SECRET_KEY"] = "test-secret"

    main_py_path = os.path.join(os.path.dirname(__file__), "main.py")
    hub_process = subprocess.Popen(
        [sys.executable, main_py_path],
        env=env,
        cwd=os.path.dirname(__file__),
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


def create_test_task():
    """Create a test task directly in the database"""
    print("Creating test task directly in database...")

    # Ensure database file exists
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Create tasks table if it doesn't exist
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tasks (
        id TEXT PRIMARY KEY,
        task_code TEXT NOT NULL,
        instructions TEXT NOT NULL,
        owner_role TEXT NOT NULL,
        deadline TEXT,
        status TEXT DEFAULT 'PENDING',
        result TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        timeout_seconds INTEGER DEFAULT 3600,
        retry_count INTEGER DEFAULT 0,
        max_retries INTEGER DEFAULT 3,
        agent_id TEXT,
        next_retry_ts TEXT,
        retry_backoff_sec INTEGER DEFAULT 60,
        reason_code TEXT,
        last_error TEXT,
        lease_expiry_ts TEXT,
        lease_seconds INTEGER DEFAULT 60
    )
    """)

    # Create a test agent
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS agents (
        id TEXT PRIMARY KEY,
        agent_id TEXT NOT NULL,
        owner_role TEXT NOT NULL,
        capabilities TEXT NOT NULL,
        online INTEGER DEFAULT 1,
        last_seen TEXT NOT NULL,
        allowed_tools TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """)

    # Insert test agent if not exists
    cursor.execute(
        "INSERT OR IGNORE INTO agents (id, agent_id, owner_role, capabilities, online, last_seen, allowed_tools, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "test-agent-id",
            "test-agent",
            "execution_engine",
            json.dumps(["task_execution"]),
            1,
            datetime.utcnow().isoformat() + "Z",
            json.dumps(["echo"]),
            datetime.utcnow().isoformat() + "Z",
            datetime.utcnow().isoformat() + "Z",
        ),
    )

    # Insert test task
    task_id = "test-task-" + str(int(time.time()))
    task_code = "TEST-HEARTBEAT-API-001"
    now = datetime.utcnow().isoformat() + "Z"

    cursor.execute(
        """
    INSERT INTO tasks (id, task_code, instructions, owner_role, status, created_at, updated_at, agent_id, lease_expiry_ts, lease_seconds)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            task_id,
            task_code,
            'echo "test"',
            "execution_engine",
            "RUNNING",
            now,
            now,
            "test-agent",
            (datetime.utcnow() + timedelta(seconds=DEFAULT_LEASE_SECONDS)).isoformat() + "Z",
            DEFAULT_LEASE_SECONDS,
        ),
    )

    conn.commit()
    conn.close()

    print(f"Created test task: {task_id}")
    return task_id


def test_heartbeat_api():
    """Test the heartbeat API"""
    import requests

    HUB_URL = "http://localhost:18788/api"

    # Create test task
    task_id = create_test_task()

    # Test 1: Send a heartbeat
    print("\n=== Test 1: Send Heartbeat ===")
    response = requests.post(
        f"{HUB_URL}/api/task/heartbeat",
        json={"task_id": task_id},
        headers={"Content-Type": "application/json"},
    )

    if response.status_code == 200:
        print("✓ Heartbeat API returned 200 OK")
        result = response.json()
        print(f"   Response: {json.dumps(result, indent=2)}")
    else:
        print(f"✗ Heartbeat API failed: {response.status_code} - {response.text}")
        return False

    # Test 2: Check if lease was extended
    print("\n=== Test 2: Check Lease Extension ===")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT lease_expiry_ts FROM tasks WHERE id = ?", (task_id,))
    result = cursor.fetchone()
    conn.close()

    if result and result[0]:
        lease_expiry = datetime.fromisoformat(result[0].replace("Z", "+00:00"))
        now = datetime.now(UTC)  # Use timezone-aware datetime
        if lease_expiry > now:
            print("✓ Lease was successfully extended")
            print(f"   Current time: {now}")
            print(f"   Lease expiry: {lease_expiry}")
        else:
            print("✗ Lease was not extended properly")
            return False
    else:
        print("✗ Failed to get lease expiry")
        return False

    # Test 3: Wait for lease to expire (25 seconds to ensure lease checker runs)
    print("\n=== Test 3: Wait for Lease Expiry (25 seconds) ===")
    time.sleep(25)  # Longer wait to ensure lease expiration checker runs

    # Check if task status changed to PENDING
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM tasks WHERE id = ?", (task_id,))
    result = cursor.fetchone()
    conn.close()

    if result and result[0] == "PENDING":
        print("✓ Task status changed to PENDING after lease expiry")
        return True
    else:
        print(
            f"✗ Task status not PENDING after lease expiry: {result[0] if result else 'Not found'}"
        )
        return False


def main():
    """Main test function"""
    print("Testing Heartbeat API and Lease Mechanism")

    # Clean up any existing database
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print(f"Removed existing database: {DB_PATH}")

    # Start hub
    hub_process = start_hub()

    try:
        # Run test
        test_passed = test_heartbeat_api()

        # Print summary
        print("\n=== Test Summary ===")
        print(f"Heartbeat API Test: {'PASS' if test_passed else 'FAIL'}")

        return 0 if test_passed else 1

    finally:
        # Stop hub
        stop_hub(hub_process)


if __name__ == "__main__":
    sys.exit(main())
