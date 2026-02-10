#!/usr/bin/env python3
"""
Test script for A2A Hub queue partitioning

This script tests the queue partitioning functionality by:
1. Registering two agents with different owner_roles
2. Creating tasks with different owner_roles
3. Verifying that each agent only gets tasks with their own owner_role
4. Verifying that capacity is managed independently for each queue
"""

import time
import uuid

import requests

BASE_URL = "http://localhost:18788/api"


def create_agent(agent_id, owner_role, capacity=1):
    """Create a test agent"""
    agent_data = {
        "agent_id": agent_id,
        "owner_role": owner_role,
        "capabilities": ["test"],
        "allowed_tools": ["test_tool"],
        "online": True,
        "capacity": capacity,
    }
    response = requests.post(f"{BASE_URL}/agent/register", json=agent_data)
    print(
        f"Create agent {agent_id} (role: {owner_role}) response: {response.status_code} {response.text}"
    )
    return response.status_code == 200


def create_task(task_code, owner_role, area="test_area", instructions="Test task"):
    """Create a test task with specified owner_role"""
    task_data = {
        "task_code": task_code,
        "area": area,
        "owner_role": owner_role,
        "instructions": instructions,
        "how_to_repro": "test",
        "expected": "test",
        "evidence_requirements": "test",
    }
    response = requests.post(f"{BASE_URL}/task/create", json=task_data)
    print(
        f"Create task {task_code} (role: {owner_role}) response: {response.status_code} {response.text}"
    )
    return response.json()


def get_next_task(agent_id):
    """Get next task for the test agent"""
    response = requests.get(f"{BASE_URL}/task/next?agent_id={agent_id}")
    return response.json()


def complete_task(task_code, status="DONE"):
    """Complete a test task"""
    result_data = {"task_code": task_code, "status": status, "result": {"test": "result"}}
    response = requests.post(f"{BASE_URL}/task/result", json=result_data)
    print(f"Complete task {task_code} response: {response.status_code} {response.text}")
    return response.status_code == 200


def main():
    """Main test function"""
    print("=== A2A Queue Partitioning Test ===")

    # Generate unique IDs for test agents and tasks
    test_suffix = str(uuid.uuid4())[:8]
    agent1_id = f"agent-role1-{test_suffix}"
    agent2_id = f"agent-role2-{test_suffix}"

    # 1. Create two agents with different owner_roles
    print("\n1. Creating test agents...")
    if not create_agent(agent1_id, "Role1", capacity=1):
        print("Failed to create agent 1")
        return 1

    if not create_agent(agent2_id, "Role2", capacity=1):
        print("Failed to create agent 2")
        return 1

    # 2. Create tasks with different owner_roles
    print("\n2. Creating test tasks...")

    # Create tasks for Role1
    role1_tasks = [f"task-role1-{i}-{test_suffix}" for i in range(2)]
    for task_code in role1_tasks:
        create_task(task_code, "Role1", area="test_area")
        time.sleep(0.1)

    # Create tasks for Role2
    role2_tasks = [f"task-role2-{i}-{test_suffix}" for i in range(2)]
    for task_code in role2_tasks:
        create_task(task_code, "Role2", area="test_area")
        time.sleep(0.1)

    # 3. Verify that each agent only gets tasks with their own owner_role
    print("\n3. Testing queue partitioning...")

    # Test agent 1 (Role1) gets only Role1 tasks
    print("\n=== Testing Agent 1 (Role1) ===")
    agent1_tasks = []
    for _ in range(3):  # Try to get more tasks than available for Role1
        response = get_next_task(agent1_id)
        if response.get("task"):
            task = response["task"]
            task_code = task["task_code"]
            task_role = task["owner_role"]
            agent1_tasks.append(task_code)
            print(f"Agent 1 got task: {task_code} (role: {task_role})")

            # Complete the task to release capacity
            complete_task(task_code)
        else:
            print(f"Agent 1 no more tasks: {response}")
            break

    # Verify agent 1 only got Role1 tasks
    for task_code in agent1_tasks:
        if task_code not in role1_tasks:
            print(f"❌ ERROR: Agent 1 got unexpected task: {task_code}")
            return 1

    # Test agent 2 (Role2) gets only Role2 tasks
    print("\n=== Testing Agent 2 (Role2) ===")
    agent2_tasks = []
    for _ in range(3):  # Try to get more tasks than available for Role2
        response = get_next_task(agent2_id)
        if response.get("task"):
            task = response["task"]
            task_code = task["task_code"]
            task_role = task["owner_role"]
            agent2_tasks.append(task_code)
            print(f"Agent 2 got task: {task_code} (role: {task_role})")

            # Complete the task to release capacity
            complete_task(task_code)
        else:
            print(f"Agent 2 no more tasks: {response}")
            break

    # Verify agent 2 only got Role2 tasks
    for task_code in agent2_tasks:
        if task_code not in role2_tasks:
            print(f"❌ ERROR: Agent 2 got unexpected task: {task_code}")
            return 1

    # 4. Verify that capacity is managed independently for each queue
    print("\n4. Testing independent capacity management...")

    # Create another set of tasks
    role1_tasks_new = [f"task-role1-new-{i}-{test_suffix}" for i in range(2)]
    role2_tasks_new = [f"task-role2-new-{i}-{test_suffix}" for i in range(2)]

    for task_code in role1_tasks_new:
        create_task(task_code, "Role1", area="test_area")

    for task_code in role2_tasks_new:
        create_task(task_code, "Role2", area="test_area")

    # Agent 1 takes one task (should use its capacity)
    response = get_next_task(agent1_id)
    if response.get("task"):
        task = response["task"]
        print(f"Agent 1 got task: {task['task_code']} (capacity used)")

    # Agent 2 should still be able to get tasks (independent capacity)
    response = get_next_task(agent2_id)
    if response.get("task"):
        task = response["task"]
        print(f"Agent 2 got task: {task['task_code']} (independent capacity works)")
    else:
        print("❌ ERROR: Agent 2 couldn't get a task despite having independent capacity")
        return 1

    # Clean up
    complete_task(task["task_code"])

    print("\n=== Test Results ===")
    print(f"Agent 1 (Role1) got {len(agent1_tasks)} Role1 tasks")
    print(f"Agent 2 (Role2) got {len(agent2_tasks)} Role2 tasks")
    print("✅ Test PASSED: Queue partitioning works correctly!")
    print("✅ Test PASSED: Each agent only gets tasks with their own owner_role!")
    print("✅ Test PASSED: Capacity is managed independently for each queue!")
    return 0


if __name__ == "__main__":
    exit(main())
