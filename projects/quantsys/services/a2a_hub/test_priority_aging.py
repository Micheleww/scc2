#!/usr/bin/env python3
"""
Self-test script for A2A Priority Aging functionality

This script tests that low priority tasks are automatically promoted after a configurable
time threshold to prevent starvation.
"""

import sys
import time
import uuid

import requests

# Configuration
BASE_URL = "http://localhost:18788/api"
TIMEOUT_SECONDS = 60  # Total test timeout
CHECK_INTERVAL = 10  # Check interval in seconds
AGING_THRESHOLD = 300  # Expected aging threshold in seconds (should match config)

# Test agent configuration
TEST_AGENT = {
    "agent_id": f"test_agent_{uuid.uuid4()}",
    "owner_role": "test_role",
    "capabilities": ["test_capability"],
    "allowed_tools": ["test_tool"],
    "online": 1,
    "capacity": 1,
    "available_capacity": 1,
}

# Test task configuration
TEST_TASK = {
    "TaskCode": f"TEST_PRIORITY_AGING_{uuid.uuid4()}",
    "instructions": "Test task for priority aging functionality",
    "owner_role": "test_role",
    "priority": 0,  # Lowest priority
}


def register_test_agent():
    """Register the test agent"""
    print("Registering test agent...")
    response = requests.post(f"{BASE_URL}/api/agent/register", json=TEST_AGENT)
    if response.status_code != 200:
        print(f"Failed to register agent: {response.status_code} - {response.text}")
        return False
    print("Test agent registered successfully")
    return True


def create_test_task():
    """Create a low priority test task"""
    print("Creating low priority test task...")
    response = requests.post(f"{BASE_URL}/api/task/create", json=TEST_TASK)
    if response.status_code != 200:
        print(f"Failed to create task: {response.status_code} - {response.text}")
        return False
    task_data = response.json()
    print(f"Test task created successfully: {task_data['task_code']} (ID: {task_data['task_id']})")
    return task_data


def check_task_priority(task_code):
    """Check the current priority of a task"""
    response = requests.get(f"{BASE_URL}/api/task/status", params={"task_code": task_code})
    if response.status_code != 200:
        print(f"Failed to check task status: {response.status_code} - {response.text}")
        return None
    task_data = response.json()
    return task_data["task"]["priority"]


def check_for_task_assignment(agent_id):
    """Check if the agent gets assigned any tasks"""
    response = requests.get(f"{BASE_URL}/api/task/next", params={"agent_id": agent_id})
    if response.status_code != 200:
        print(f"Failed to check for next task: {response.status_code} - {response.text}")
        return None
    result = response.json()
    return result["task"] if result["task"] else None


def complete_task(task_id):
    """Complete a task"""
    response = requests.post(
        f"{BASE_URL}/api/task/result",
        json={"task_id": task_id, "status": "DONE", "result": {"test": "result"}},
    )
    if response.status_code != 200:
        print(f"Failed to complete task: {response.status_code} - {response.text}")
        return False
    print(f"Task {task_id} completed successfully")
    return True


def deregister_test_agent():
    """Deregister the test agent"""
    print("Deregistering test agent...")
    response = requests.delete(f"{BASE_URL}/api/agent/{TEST_AGENT['agent_id']}")
    if response.status_code != 200:
        print(f"Failed to deregister agent: {response.status_code} - {response.text}")
        return False
    print("Test agent deregistered successfully")
    return True


def main():
    """Main test function"""
    print("=== A2A Priority Aging Self-Test ===")
    print(f"Test Agent ID: {TEST_AGENT['agent_id']}")
    print(f"Test Task Code: {TEST_TASK['TaskCode']}")
    print(f"Aging Threshold: {AGING_THRESHOLD} seconds")
    print(f"Test Timeout: {TIMEOUT_SECONDS} seconds")
    print()

    try:
        # Step 1: Register test agent
        if not register_test_agent():
            return 1

        # Step 2: Create low priority task
        task_data = create_test_task()
        if not task_data:
            return 1

        task_code = task_data["task_code"]
        task_id = task_data["task_id"]

        # Step 3: Verify initial priority is low
        initial_priority = check_task_priority(task_code)
        if initial_priority is None:
            return 1
        print(f"✓ Initial task priority: {initial_priority} (expected: 0)")
        if initial_priority != 0:
            print(f"✗ Unexpected initial priority: {initial_priority}, expected: 0")
            return 1

        # Step 4: Wait for priority aging to take effect
        print(
            f"\nWaiting for priority aging to take effect (expected threshold: {AGING_THRESHOLD} seconds)..."
        )
        start_time = time.time()
        priority_increased = False
        assigned_task = None

        while time.time() - start_time < TIMEOUT_SECONDS:
            # Check current priority
            current_priority = check_task_priority(task_code)
            if current_priority is None:
                return 1

            if current_priority > initial_priority:
                priority_increased = True
                print(f"✓ Task priority increased to {current_priority}")
                break

            # Check if task got assigned
            assigned_task = check_for_task_assignment(TEST_AGENT["agent_id"])
            if assigned_task:
                print(f"✓ Task assigned before aging: {assigned_task['task_code']}")
                # Complete the task to clean up
                complete_task(assigned_task["id"])
                priority_increased = True
                break

            elapsed = time.time() - start_time
            print(
                f"  Waiting... {int(elapsed)}s / {AGING_THRESHOLD}s (current priority: {current_priority})"
            )
            time.sleep(CHECK_INTERVAL)

        if not priority_increased:
            print(
                f"✗ Priority aging failed: task still has priority {initial_priority} after {TIMEOUT_SECONDS} seconds"
            )
            return 1

        # Step 5: If task wasn't assigned yet, check assignment after aging
        if not assigned_task:
            print("\nChecking if aged task gets assigned...")
            for _ in range(3):  # Try 3 times
                assigned_task = check_for_task_assignment(TEST_AGENT["agent_id"])
                if assigned_task:
                    print(
                        f"✓ Aged task assigned: {assigned_task['task_code']} (priority: {assigned_task['priority']})"
                    )
                    break
                print("  Waiting for task assignment...")
                time.sleep(CHECK_INTERVAL)

            if not assigned_task:
                print("✗ Aged task not assigned after priority increase")
                return 1

        # Step 6: Complete the assigned task
        if not complete_task(assigned_task["id"]):
            return 1

        # Step 7: Verify task completed successfully
        final_status = None
        for _ in range(3):
            response = requests.get(f"{BASE_URL}/api/task/status", params={"task_code": task_code})
            if response.status_code == 200:
                final_status = response.json()["task"]["status"]
                if final_status == "DONE":
                    break
            time.sleep(CHECK_INTERVAL)

        if final_status != "DONE":
            print(f"✗ Task not completed successfully. Final status: {final_status}")
            return 1

        print(f"✓ Task completed successfully. Final status: {final_status}")

        # Step 8: Cleanup
        print("\nCleaning up test resources...")
        deregister_test_agent()

        print("\n=== Test Results ===")
        print("✓ All tests passed!")
        print("✓ Low priority task created successfully")
        print("✓ Task priority increased after aging threshold")
        print("✓ Aged task got assigned to agent")
        print("✓ Task completed successfully")
        print("\nEXIT_CODE=0")
        return 0

    except Exception as e:
        print(f"\n✗ Test failed with exception: {e}")
        print("EXIT_CODE=1")
        return 1
    finally:
        # Always try to clean up
        try:
            deregister_test_agent()
        except:
            pass


if __name__ == "__main__":
    sys.exit(main())
