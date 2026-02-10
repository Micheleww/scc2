#!/usr/bin/env python3
"""
Basic test script for agent capacity lease functionality

This script tests the agent capacity lease feature by:
1. Registering an agent with capacity=1
2. Creating a task - should succeed and reduce capacity to 0
3. Getting the task - should move to RUNNING state
4. Creating another task immediately - should fail due to capacity constraints
5. Completing the first task - releases capacity
6. Creating a third task - should succeed again
"""

import requests

# A2A Hub API endpoint
hub_url = "http://localhost:18788/api"

# Test agent configuration
agent_config = {
    "agent_id": "test_agent_001",
    "owner_role": "test_role",
    "capabilities": ["test_capability"],
    "allowed_tools": ["test_tool"],
    "capacity": 1,
}

# Test task configuration
task_config = {
    "TaskCode": "",
    "instructions": "Test task with test_capability",
    "owner_role": "test_role",
    "timeout_seconds": 300,
    "max_retries": 1,
}


def register_agent():
    """Register the test agent using unified registration tool"""
    print("=== Registering test agent with capacity=1 ===")
    try:
        # 导入统一注册工具
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from tools.register_agent import AgentRegistrar
        
        # 创建注册器实例
        registrar = AgentRegistrar()
        
        # 调用统一注册方法
        result = registrar.register_a2a_hub(
            agent_id=agent_config["agent_id"],
            name=agent_config["agent_id"],
            owner_role=agent_config["owner_role"],
            capabilities=agent_config["capabilities"],
            worker_type="Shell",
            capacity=agent_config["capacity"],
            retry_count=3
        )
        
        print(f"Response: {result}")
        return result["success"]
    except Exception as e:
        print(f"Unexpected error in unified registration: {e}")
        # 回退到原始注册方法
        print("Falling back to original registration method...")
        response = requests.post(f"{hub_url}/api/agent/register", json=agent_config)
        print(f"Response: {response.status_code} {response.text}")
        return response.status_code == 200


def create_task(task_code):
    """Create a test task"""
    config = task_config.copy()
    config["TaskCode"] = task_code
    print(f"=== Creating task {task_code} ===")
    response = requests.post(f"{hub_url}/api/task/create", json=config)
    print(f"Response: {response.status_code} {response.text}")
    return response.status_code == 200, response.json()


def get_next_task(agent_id):
    """Get the next pending task for the agent"""
    print(f"=== Getting next task for agent {agent_id} ===")
    response = requests.get(f"{hub_url}/api/task/next?agent_id={agent_id}")
    print(f"Response: {response.status_code} {response.text}")
    return response.status_code == 200, response.json()


def get_agent_status():
    """Get agent status and available capacity"""
    print("=== Getting agent status ===")
    response = requests.get(f"{hub_url}/api/agent/{agent_config['agent_id']}")
    if response.status_code == 200:
        agent_data = response.json()
        print(f"Agent status: {agent_data}")
        return agent_data.get("agent", {}).get("available_capacity", -1)
    print(f"Failed to get agent status: {response.status_code} {response.text}")
    return -1


def complete_task(task_id):
    """Complete a test task"""
    print(f"=== Completing task {task_id} ===")
    response = requests.post(
        f"{hub_url}/api/task/result",
        json={
            "task_code": f"test_task_{task_id}",
            "status": "DONE",
            "result": {"test_key": "test_value"},
        },
    )
    print(f"Response: {response.status_code} {response.text}")
    return response.status_code == 200


def complete_task_by_id(task_id):
    """Complete a test task by ID"""
    print(f"=== Completing task by ID {task_id} ===")
    # First get the task details to get the task_code
    response = requests.get(f"{hub_url}/api/task/status?task_id={task_id}")
    if response.status_code != 200:
        print(f"Failed to get task details: {response.status_code} {response.text}")
        return False

    task_code = response.json().get("task", {}).get("task_code")
    if not task_code:
        print("Failed to get task_code from task details")
        return False

    # Now complete the task using task_code
    complete_response = requests.post(
        f"{hub_url}/api/task/result",
        json={"task_code": task_code, "status": "DONE", "result": {"test_key": "test_value"}},
    )
    print(f"Response: {complete_response.status_code} {complete_response.text}")
    return complete_response.status_code == 200


def main():
    """Main test function"""
    print("Starting agent capacity lease test...")

    # Step 1: Register agent
    if not register_agent():
        print("Failed to register agent, exiting")
        return 1

    # Get initial agent status
    get_agent_status()

    # Step 2: Create first task - should succeed
    success, task1_result = create_task("test_task_001")
    if not success:
        print("Failed to create first task, exiting")
        return 1

    # Step 3: Get the task - should move to RUNNING state
    success, next_task_result = get_next_task(agent_config["agent_id"])
    if not success:
        print("Failed to get next task, exiting")
        return 1

    task_id = next_task_result.get("task", {}).get("id")
    if not task_id:
        print("Failed to get task_id, exiting")
        return 1

    # Get agent status after getting task - should show available_capacity=0
    print("\n=== Checking agent capacity after getting task ===")
    available_capacity = get_agent_status()
    if available_capacity != 0:
        print(f"Expected available_capacity=0 after getting task, got {available_capacity}")
        return 1

    # Step 4: Create second task - should fail due to capacity constraints
    success, task2_result = create_task("test_task_002")
    # Check if task creation failed or was rejected due to capacity
    if success and task2_result.get("success"):
        print(
            "Second task creation succeeded when it should have failed due to capacity constraints"
        )
        return 1

    # Step 5: Complete the first task - releases capacity
    if not complete_task_by_id(task_id):
        print("Failed to complete first task, exiting")
        return 1

    # Get agent status after completing task - should show available_capacity=1
    print("\n=== Checking agent capacity after completing task ===")
    available_capacity = get_agent_status()
    if available_capacity != 1:
        print(f"Expected available_capacity=1 after completing task, got {available_capacity}")
        return 1

    # Step 6: Create third task - should succeed again
    success, task3_result = create_task("test_task_003")
    if not success:
        print("Failed to create third task after capacity release, exiting")
        return 1

    # Clean up: Complete the third task
    success, next_task_result = get_next_task(agent_config["agent_id"])
    if success:
        task3_id = next_task_result.get("task", {}).get("id")
        if task3_id:
            complete_task_by_id(task3_id)

    print("\n=== All tests passed! ===")
    print("Agent capacity lease functionality is working correctly.")
    return 0


if __name__ == "__main__":
    exit(main())
