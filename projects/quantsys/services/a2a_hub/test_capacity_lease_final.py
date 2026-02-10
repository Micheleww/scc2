#!/usr/bin/env python3
"""
Final test script for agent capacity lease functionality

This script tests the agent capacity lease feature with proper test isolation:
1. Cleans up old test data
2. Creates a new test agent with capacity=1
3. Creates unique tasks to avoid conflicts
4. Verifies capacity is correctly managed
"""

import json
import uuid

import requests

# A2A Hub API endpoint
hub_url = "http://localhost:18788/api"


def cleanup_test_data():
    """Clean up old test data"""
    print("=== Cleaning up old test data ===")

    # Get all test agents
    response = requests.get(f"{hub_url}/api/agent/list")
    if response.status_code == 200:
        agents = response.json().get("agents", [])
        for agent in agents:
            if agent["agent_id"].startswith("test_agent_"):
                # Delete test agent
                delete_response = requests.delete(f"{hub_url}/api/agent/{agent['agent_id']}")
                print(f"Deleted agent {agent['agent_id']}: {delete_response.status_code}")
    print("=== Cleanup complete ===")


def register_test_agent(capacity=1):
    """Register a test agent with unique ID"""
    agent_id = f"test_agent_{uuid.uuid4().hex[:8]}"
    agent_config = {
        "agent_id": agent_id,
        "owner_role": "test_role",
        "capabilities": ["test_capability"],
        "allowed_tools": ["test_tool"],
        "capacity": capacity,
    }
    response = requests.post(f"{hub_url}/api/agent/register", json=agent_config)
    print(f"=== Registering test agent {agent_id} with capacity={capacity} ===")
    print(f"Response: {response.status_code} {response.text}")
    return agent_id


def create_unique_task():
    """Create a unique test task"""
    task_code = f"test_task_{uuid.uuid4().hex[:8]}"
    task_config = {
        "TaskCode": task_code,
        "instructions": "Test task with test_capability",
        "owner_role": "test_role",
        "timeout_seconds": 300,
        "max_retries": 1,
    }
    print(f"=== Creating unique task {task_code} ===")
    response = requests.post(f"{hub_url}/api/task/create", json=task_config)
    print(f"Response: {response.status_code} {response.text}")
    return task_code, response.json()


def get_next_task(agent_id):
    """Get the next pending task for the agent"""
    print(f"=== Getting next task for agent {agent_id} ===")
    response = requests.get(f"{hub_url}/api/task/next?agent_id={agent_id}")
    print(f"Response: {response.status_code} {response.text}")
    return response.json()


def get_agent_status(agent_id):
    """Get agent status and available capacity"""
    print(f"=== Getting status for agent {agent_id} ===")
    response = requests.get(f"{hub_url}/api/agent/{agent_id}")
    if response.status_code == 200:
        agent_data = response.json()
        print(f"Agent status: {json.dumps(agent_data, indent=2)}")
        return agent_data.get("agent", {}).get("available_capacity", -1)
    print(f"Failed to get agent status: {response.status_code} {response.text}")
    return -1


def complete_task_by_code(task_code):
    """Complete a test task by task_code"""
    print(f"=== Completing task {task_code} ===")
    response = requests.post(
        f"{hub_url}/api/task/result",
        json={"task_code": task_code, "status": "DONE", "result": {"test_key": "test_value"}},
    )
    print(f"Response: {response.status_code} {response.text}")
    return response.status_code == 200


def main():
    """Main test function"""
    print("Starting agent capacity lease test...")

    # Step 1: Clean up old test data
    cleanup_test_data()

    # Step 2: Register new test agent with capacity=1
    agent_id = register_test_agent(capacity=1)

    # Step 3: Get initial agent status - should show available_capacity=1
    available_capacity = get_agent_status(agent_id)
    if available_capacity != 1:
        print(f"Expected available_capacity=1 initially, got {available_capacity}")
        return 1

    # Step 4: Create first unique task - should succeed
    task_code_1, task1_result = create_unique_task()
    if not task1_result.get("success"):
        print("Failed to create first task, exiting")
        return 1

    # Step 5: Get the task - should move to RUNNING state
    next_task_result = get_next_task(agent_id)
    task1_id = next_task_result.get("task", {}).get("id")
    if not task1_id:
        print("Failed to get task_id, exiting")
        return 1

    # Step 6: Check agent capacity after getting task - should be 0
    available_capacity = get_agent_status(agent_id)
    print(f"Available capacity after getting task: {available_capacity}")
    if available_capacity != 0:
        print(f"Expected available_capacity=0 after getting task, got {available_capacity}")
        return 1

    # Step 7: Create second unique task - should fail due to capacity constraints
    task_code_2, task2_result = create_unique_task()
    print(f"Second task creation result: {task2_result}")

    # Step 8: Complete the first task - should release capacity
    if not complete_task_by_code(task_code_1):
        print("Failed to complete first task, exiting")
        return 1

    # Step 9: Check agent capacity after completing task - should be 1 again
    available_capacity = get_agent_status(agent_id)
    print(f"Available capacity after completing task: {available_capacity}")
    if available_capacity != 1:
        print(f"Expected available_capacity=1 after completing task, got {available_capacity}")
        return 1

    print("\n=== All tests passed! ===")
    print("Agent capacity lease functionality is working correctly.")
    return 0


if __name__ == "__main__":
    exit(main())
