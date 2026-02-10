#!/usr/bin/env python3
"""
Test script for A2A Hub priority scheduler

This script tests the priority scheduling functionality by:
1. Creating an agent
2. Creating multiple tasks with different priorities
3. Getting tasks using /api/task/next
4. Verifying that tasks are returned in the correct order: high priority first, same priority FIFO
"""

import time
import uuid

import requests

BASE_URL = "http://localhost:18788/api"
TEST_AGENT_ID = "test-agent-" + str(uuid.uuid4())[:8]


def create_agent():
    """Create a test agent"""
    agent_data = {
        "agent_id": TEST_AGENT_ID,
        "owner_role": "TestRole",
        "capabilities": ["test"],
        "allowed_tools": ["test_tool"],
        "online": True,
    }
    response = requests.post(f"{BASE_URL}/agent/register", json=agent_data)
    print(f"Create agent response: {response.status_code} {response.text}")
    return response.status_code == 200


def create_task(task_code, priority, instructions="Test task"):
    """Create a test task with specified priority"""
    task_data = {
        "TaskCode": task_code,
        "instructions": instructions,
        "owner_role": "TestRole",
        "priority": priority,
    }
    response = requests.post(f"{BASE_URL}/task/create", json=task_data)
    print(
        f"Create task {task_code} (priority {priority}) response: {response.status_code} {response.text}"
    )
    return response.json()


def get_next_task():
    """Get next task for the test agent"""
    response = requests.get(f"{BASE_URL}/task/next?agent_id={TEST_AGENT_ID}")
    return response.json()


def main():
    """Main test function"""
    print("=== A2A Priority Scheduler Test ===")

    # 1. Create test agent
    if not create_agent():
        print("Failed to create test agent")
        return 1

    # 2. Create tasks with different priorities
    print("\nCreating test tasks...")

    # Create tasks in this order (should be returned in priority order, then FIFO)
    # Priority 3 first, then priority 2, then priority 1, then priority 0
    # Same priority tasks should be returned in FIFO order
    tasks = [
        ("task-p0-1", 0, "Task with priority 0 - first"),
        ("task-p1-1", 1, "Task with priority 1 - first"),
        ("task-p2-1", 2, "Task with priority 2 - first"),
        ("task-p3-1", 3, "Task with priority 3 - first"),
        ("task-p3-2", 3, "Task with priority 3 - second"),
        ("task-p2-2", 2, "Task with priority 2 - second"),
        ("task-p1-2", 1, "Task with priority 1 - second"),
        ("task-p0-2", 0, "Task with priority 0 - second"),
    ]

    for task_code, priority, instructions in tasks:
        create_task(task_code, priority, instructions)
        time.sleep(0.1)  # Small delay to ensure FIFO ordering

    # 3. Get tasks in order and verify
    print("\nGetting tasks in order...")

    expected_order = [
        "task-p3-1",  # Priority 3, first created
        "task-p3-2",  # Priority 3, second created
        "task-p2-1",  # Priority 2, first created
        "task-p2-2",  # Priority 2, second created
        "task-p1-1",  # Priority 1, first created
        "task-p1-2",  # Priority 1, second created
        "task-p0-1",  # Priority 0, first created
        "task-p0-2",  # Priority 0, second created
    ]

    actual_order = []

    for _ in range(len(expected_order)):
        response = get_next_task()
        if response.get("task"):
            task_code = response["task"]["task_code"]
            priority = response["task"]["priority"]
            actual_order.append(task_code)
            print(f"Got task: {task_code} (priority {priority})")
        else:
            print(f"No more tasks: {response}")
            break

    # 4. Verify order
    print("\n=== Test Results ===")
    print(f"Expected order: {expected_order}")
    print(f"Actual order:   {actual_order}")

    if actual_order == expected_order:
        print("✅ Test PASSED: Tasks returned in correct priority order!")
        return 0
    else:
        print("❌ Test FAILED: Tasks returned in wrong order!")
        return 1


if __name__ == "__main__":
    exit(main())
