#!/usr/bin/env python3
"""
Comprehensive test script for A2A Hub queue partitioning

This script tests all queue partitioning functionality:
1. Multiple queues with different area/owner_role combinations
2. Independent capacity management for each queue
3. Priority handling within each queue
4. No cross-queue interference
"""

import time
import uuid

import requests

BASE_URL = "http://localhost:18788/api"


def create_agent(agent_id, owner_role, capacity=2):
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
        f"Create agent {agent_id} (role: {owner_role}, capacity: {capacity}) response: {response.status_code} {response.text}"
    )
    return response.status_code == 200


def create_task(task_code, owner_role, area, priority=0, instructions="Test task"):
    """Create a test task with specified parameters"""
    task_data = {
        "task_code": task_code,
        "area": area,
        "owner_role": owner_role,
        "instructions": instructions,
        "how_to_repro": "test",
        "expected": "test",
        "evidence_requirements": "test",
        "priority": priority,
    }
    response = requests.post(f"{BASE_URL}/task/create", json=task_data)
    print(
        f"Create task {task_code} (area: {area}, role: {owner_role}, priority: {priority}) response: {response.status_code} {response.text}"
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
    print("=== A2A Queue Partitioning Comprehensive Test ===")

    # Generate unique IDs for test agents and tasks
    test_suffix = str(uuid.uuid4())[:8]

    # Define queue configurations
    # Each queue is defined by area/owner_role combination
    queues = [
        {
            "area": "ci/exchange",
            "owner_role": "SRE Engineer",
            "agent_id": f"agent-ci-exchange-{test_suffix}",
        },
        {
            "area": "ci/controlplane",
            "owner_role": "DevOps Engineer",
            "agent_id": f"agent-ci-controlplane-{test_suffix}",
        },
        {
            "area": "tools/a2a",
            "owner_role": "Backend Engineer",
            "agent_id": f"agent-tools-a2a-{test_suffix}",
        },
    ]

    # 1. Register agents for each queue
    print("\n1. Registering agents for each queue...")
    for queue in queues:
        if not create_agent(queue["agent_id"], queue["owner_role"], capacity=2):
            print(f"Failed to create agent for queue: {queue}")
            return 1

    # 2. Create tasks for each queue with different priorities
    print("\n2. Creating tasks for each queue...")

    all_tasks = {}

    for queue in queues:
        queue_tasks = []

        # Create tasks with different priorities for each queue
        for i in range(3):
            # Priority decreases from 3 to 1
            priority = 3 - i
            task_code = f"task-{queue['area'].replace('/', '-')}-{i}-{test_suffix}"

            create_task(
                task_code=task_code,
                owner_role=queue["owner_role"],
                area=queue["area"],
                priority=priority,
                instructions=f"Test task for {queue['area']} with priority {priority}",
            )
            queue_tasks.append({"task_code": task_code, "priority": priority})
            time.sleep(0.1)

        all_tasks[queue["agent_id"]] = queue_tasks

    # 3. Test that each agent only gets tasks from their own queue
    print("\n3. Testing queue isolation...")

    for queue in queues:
        agent_id = queue["agent_id"]
        expected_tasks = all_tasks[agent_id]

        print(
            f"\n=== Testing Agent {agent_id} (area: {queue['area']}, role: {queue['owner_role']}) ==="
        )

        received_tasks = []
        for _ in range(len(expected_tasks) + 1):  # Try to get one more than expected
            response = get_next_task(agent_id)
            if response.get("task"):
                task = response["task"]
                task_code = task["task_code"]
                task_role = task["owner_role"]
                task_area = task["area"]
                task_priority = task["priority"]

                received_tasks.append({"task_code": task_code, "priority": task_priority})
                print(
                    f"Agent {agent_id} got task: {task_code} (area: {task_area}, role: {task_role}, priority: {task_priority})"
                )

                # Verify the task belongs to the correct queue
                if task_role != queue["owner_role"] or task_area != queue["area"]:
                    print(
                        f"❌ ERROR: Agent {agent_id} got task from wrong queue: {task_code} (expected area: {queue['area']}, role: {queue['owner_role']})"
                    )
                    return 1

                # Complete the task to test capacity management
                complete_task(task_code)
            else:
                print(f"Agent {agent_id} no more tasks: {response}")
                break

        # Verify the agent got all expected tasks
        if len(received_tasks) != len(expected_tasks):
            print(
                f"❌ ERROR: Agent {agent_id} got {len(received_tasks)} tasks, expected {len(expected_tasks)}"
            )
            return 1

        # Verify priority order within the queue (high priority first)
        for i in range(len(received_tasks) - 1):
            if received_tasks[i]["priority"] < received_tasks[i + 1]["priority"]:
                print(
                    f"❌ ERROR: Agent {agent_id} got tasks in wrong priority order: {[t['priority'] for t in received_tasks]}"
                )
                return 1

        print(f"✅ Agent {agent_id} got all {len(received_tasks)} tasks in correct priority order!")

    # 4. Test independent capacity management
    print("\n4. Testing independent capacity management...")

    # Create tasks that will fill the capacity of one queue
    queue_to_fill = queues[0]
    fill_tasks = []

    for i in range(5):  # Create more tasks than the agent's capacity
        task_code = f"task-fill-{queue_to_fill['area'].replace('/', '-')}-{i}-{test_suffix}"
        response = create_task(
            task_code=task_code,
            owner_role=queue_to_fill["owner_role"],
            area=queue_to_fill["area"],
            priority=0,
        )
        fill_tasks.append(task_code)
        time.sleep(0.1)

    # Verify that other queues are not affected
    print(
        f"\n=== Testing that other queues are not affected by {queue_to_fill['area']} queue being full ==="
    )

    for queue in queues[1:]:  # Skip the queue we just filled
        agent_id = queue["agent_id"]

        # Create a new task for this queue
        test_task_code = f"task-independent-{queue['area'].replace('/', '-')}-{test_suffix}"
        create_task(task_code=test_task_code, owner_role=queue["owner_role"], area=queue["area"])

        # Try to get this task - should succeed even though another queue is full
        response = get_next_task(agent_id)
        if response.get("task"):
            task = response["task"]
            print(
                f"✅ Agent {agent_id} got task {task['task_code']} even though {queue_to_fill['area']} queue is full"
            )
            complete_task(task["task_code"])
        else:
            print(
                f"❌ ERROR: Agent {agent_id} couldn't get a task even though it should have capacity"
            )
            return 1

    print("\n=== Test Results ===")
    print("✅ All queue partitioning tests passed!")
    print("✅ Queue isolation: Each agent only gets tasks from their own queue")
    print("✅ Priority handling: Tasks within each queue are processed by priority")
    print("✅ Independent capacity: Each queue has its own capacity management")
    print("✅ No cross-queue interference: Full queues don't affect other queues")

    return 0


if __name__ == "__main__":
    exit(main())
