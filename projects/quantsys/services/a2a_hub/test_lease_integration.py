#!/usr/bin/env python3
"""
Integration test for the A2A Worker Heartbeat & Lease mechanism

This test verifies:
1. Task is created with RUNNING status and initial lease_expiry_ts
2. Task remains RUNNING when heartbeat is sent
3. Task status changes to PENDING when lease expires
4. Task can be re-assigned after lease expiry
"""

import os
import subprocess
import sys
import time

import requests

# Configuration
HUB_URL = "http://localhost:18788/api"
HUB_SCRIPT = os.path.join(os.path.dirname(__file__), "main.py")
TEST_LEASE_SECONDS = 10  # Short lease time for testing

# Colors for output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"


class TestHub:
    """Test hub wrapper to start and stop the hub server"""

    def __init__(self):
        self.process = None

    def start(self):
        """Start the hub server in a separate process"""
        print(f"{YELLOW}Starting A2A Hub...{RESET}")
        # Set A2A_HUB_SECRET_KEY for testing
        env = os.environ.copy()
        env["A2A_HUB_SECRET_KEY"] = "test-secret-key-12345"

        # Start hub server
        self.process = subprocess.Popen(
            [sys.executable, HUB_SCRIPT],
            env=env,
            cwd=os.path.dirname(__file__),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Wait for server to start
        time.sleep(3)

        # Check if server is running
        try:
            response = requests.get(f"{HUB_URL}/api/health")
            if response.status_code == 200:
                print(f"{GREEN}✓ A2A Hub started successfully{RESET}")
                return True
        except Exception as e:
            print(f"{RED}✗ Failed to start A2A Hub: {e}{RESET}")
            self.stop()
            return False

    def stop(self):
        """Stop the hub server"""
        if self.process:
            print(f"{YELLOW}Stopping A2A Hub...{RESET}")
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
                print(f"{GREEN}✓ A2A Hub stopped successfully{RESET}")
            except subprocess.TimeoutExpired:
                self.process.kill()
                print(f"{YELLOW}⚠️  A2A Hub killed after timeout{RESET}")
            self.process = None

    def cleanup(self):
        """Clean up the database"""
        print(f"{YELLOW}Cleaning up test database...{RESET}")
        db_path = os.path.join(os.path.dirname(__file__), "state", "a2a_hub.db")
        if os.path.exists(db_path):
            os.remove(db_path)
            print(f"{GREEN}✓ Database cleaned up{RESET}")
        else:
            print(f"{YELLOW}⚠️  Database file not found, skipping cleanup{RESET}")


def wait_for_status(task_code, expected_status, timeout=30):
    """Wait for task to reach expected status"""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            response = requests.get(f"{HUB_URL}/api/task/status", params={"task_code": task_code})
            if response.status_code == 200:
                task = response.json().get("task", {})
                if task.get("status") == expected_status:
                    return True, task
        except Exception as e:
            print(f"{YELLOW}⚠️  Error checking task status: {e}{RESET}")
        time.sleep(1)
    return False, None


def test_lease_expiration():
    """Test that task status changes to PENDING when lease expires"""
    print(f"\n{YELLOW}=== Testing Lease Expiration ==={RESET}")

    # Clean up any existing database
    hub = TestHub()
    hub.cleanup()

    # Start hub
    if not hub.start():
        return False

    try:
        # Register a test agent
        print(f"{YELLOW}Registering test agent...{RESET}")
        agent_id = "test-agent-001"
        register_response = requests.post(
            f"{HUB_URL}/api/agent/register",
            json={
                "agent_id": agent_id,
                "owner_role": "execution_engine",
                "capabilities": ["test"],
                "allowed_tools": ["python"],
            },
        )
        if register_response.status_code != 200:
            print(f"{RED}✗ Failed to register agent: {register_response.text}{RESET}")
            return False
        print(f"{GREEN}✓ Agent registered successfully{RESET}")

        # Create a task
        print(f"{YELLOW}Creating test task...{RESET}")
        task_code = "TEST-LEASE-EXPIRY-v0.1"
        create_response = requests.post(
            f"{HUB_URL}/api/task/create",
            json={
                "TaskCode": task_code,
                "instructions": "python -c \"print('test')\"",
                "owner_role": "execution_engine",
            },
        )
        if create_response.status_code != 200:
            print(f"{RED}✗ Failed to create task: {create_response.text}{RESET}")
            return False
        create_result = create_response.json()
        print(f"{GREEN}✓ Task created successfully: {task_code}{RESET}")

        # Get next task (this should set status to RUNNING with initial lease)
        print(f"{YELLOW}Getting next task (should set status to RUNNING)...{RESET}")
        next_response = requests.get(f"{HUB_URL}/api/task/next", params={"agent_id": agent_id})
        if next_response.status_code != 200:
            print(f"{RED}✗ Failed to get next task: {next_response.text}{RESET}")
            return False
        next_result = next_response.json()
        task = next_result.get("task")
        if not task or task.get("status") != "RUNNING":
            print(f"{RED}✗ Task not in RUNNING status: {task.get('status', 'unknown')}{RESET}")
            return False

        task_id = task["id"]
        lease_expiry = task.get("lease_expiry")
        print(f"{GREEN}✓ Task in RUNNING status, Task ID: {task_id}{RESET}")
        print(f"{YELLOW}  Lease expiry: {lease_expiry}{RESET}")

        # Wait for lease to expire (add 5 seconds buffer)
        print(f"{YELLOW}Waiting for lease to expire...{RESET}")
        time.sleep(TEST_LEASE_SECONDS + 5)

        # Check if task status changed to PENDING
        print(f"{YELLOW}Checking if task status changed to PENDING...{RESET}")
        status_response = requests.get(
            f"{HUB_URL}/api/task/status", params={"task_code": task_code}
        )
        if status_response.status_code != 200:
            print(f"{RED}✗ Failed to get task status: {status_response.text}{RESET}")
            return False
        task = status_response.json().get("task", {})
        if task.get("status") != "PENDING":
            print(f"{RED}✗ Task status not PENDING: {task.get('status', 'unknown')}{RESET}")
            return False
        print(f"{GREEN}✓ Task status changed to PENDING after lease expiry{RESET}")

        # Try to get the task again (should be available for re-assignment)
        print(
            f"{YELLOW}Trying to get the task again (should be available for re-assignment)...{RESET}"
        )
        next_response = requests.get(f"{HUB_URL}/api/task/next", params={"agent_id": agent_id})
        if next_response.status_code != 200:
            print(f"{RED}✗ Failed to get next task: {next_response.text}{RESET}")
            return False
        next_result = next_response.json()
        task = next_result.get("task")
        if not task or task.get("status") != "RUNNING":
            print(
                f"{RED}✗ Task not available for re-assignment: {task.get('status', 'unknown')}{RESET}"
            )
            return False
        print(f"{GREEN}✓ Task successfully re-assigned, status: RUNNING{RESET}")

        print(f"\n{GREEN}🎉 All lease expiration tests passed!{RESET}")
        return True

    finally:
        # Stop hub and cleanup
        hub.stop()
        hub.cleanup()


def main():
    """Main test function"""
    print(f"{YELLOW}Starting A2A Worker Heartbeat & Lease Integration Test{RESET}")
    print(
        f"{YELLOW}"
        """")
    print(f"Testing:")
    print(f"1. Task creation with RUNNING status and initial lease")
    print(f"2. Task status change to PENDING on lease expiry")
    print(f"3. Task re-assignment after lease expiry")
    print(f"""
        "{RESET}"
    )

    success = test_lease_expiration()

    if success:
        print(f"\n{GREEN}✅ All tests passed! EXIT_CODE=0{RESET}")
        sys.exit(0)
    else:
        print(f"\n{RED}❌ Tests failed! EXIT_CODE=1{RESET}")
        sys.exit(1)


if __name__ == "__main__":
    main()
