#!/usr/bin/env python3
"""
DAG Workflow Test Script for A2A Hub

Tests the DAG workflow functionality with the following scenarios:
1. Two-node DAG (A → B): B should only execute after A is done
2. Failure propagation: B should be blocked when A fails
3. Task status verification: Verify task status transitions

Exit Code: 0 if all tests pass, 1 otherwise
"""

import sys
import time

import requests

# Configuration
HUB_URL = "http://localhost:18788/api"
AGENT_ID = "test-agent-dag"
AGENT_OWNER_ROLE = "Backend Engineer"
AGENT_CAPABILITIES = ["test", "execute"]
AGENT_ALLOWED_TOOLS = ["python", "bash"]

# Test timeout in seconds
TEST_TIMEOUT = 30


def register_test_agent():
    """
    Register a test agent with the A2A hub
    """
    url = f"{HUB_URL}/api/agent/register"
    payload = {
        "agent_id": AGENT_ID,
        "owner_role": AGENT_OWNER_ROLE,
        "capabilities": AGENT_CAPABILITIES,
        "allowed_tools": AGENT_ALLOWED_TOOLS,
        "capacity": 10,
    }

    try:
        response = requests.post(url, json=payload, timeout=5)
        return response.json()
    except Exception as e:
        print(f"❌ Error registering agent: {e}")
        return None


def create_test_task(task_code, instructions, dependencies=None, agent_id=AGENT_ID):
    """
    Create a test task with optional dependencies
    """
    url = f"{HUB_URL}/api/task/create"
    payload = {
        "task_code": task_code,
        "area": "a2a/hub",
        "owner_role": AGENT_OWNER_ROLE,
        "instructions": instructions,
        "how_to_repro": "Run test",
        "expected": "Success",
        "evidence_requirements": "test",
        "agent_id": agent_id,
    }

    if dependencies:
        payload["dependencies"] = dependencies

    try:
        response = requests.post(url, json=payload, timeout=5)
        return response.json()
    except Exception as e:
        print(f"❌ Error creating task {task_code}: {e}")
        return None


def get_task_status(task_code):
    """
    Get the status of a task
    """
    url = f"{HUB_URL}/api/task/status?task_code={task_code}"
    try:
        response = requests.get(url, timeout=5)
        data = response.json()
        if data.get("success"):
            return data["task"]["status"]
        return None
    except Exception as e:
        print(f"❌ Error getting task status for {task_code}: {e}")
        return None


def get_next_task(agent_id=AGENT_ID):
    """
    Get the next task for an agent
    """
    url = f"{HUB_URL}/api/task/next?agent_id={agent_id}"
    try:
        response = requests.get(url, timeout=5)
        return response.json()
    except Exception as e:
        print(f"❌ Error getting next task for agent {agent_id}: {e}")
        return None


def submit_task_result(task_code, status="DONE", result=None, reason_code=None, last_error=None):
    """
    Submit a task result
    """
    url = f"{HUB_URL}/api/task/result"
    payload = {"task_code": task_code, "status": status}

    if result:
        payload["result"] = result
    if reason_code:
        payload["reason_code"] = reason_code
    if last_error:
        payload["last_error"] = last_error

    try:
        response = requests.post(url, json=payload, timeout=5)
        return response.json()
    except Exception as e:
        print(f"❌ Error submitting result for {task_code}: {e}")
        return None


def test_dag_workflow_success():
    """
    Test case 1: Two-node DAG (A → B) where both tasks succeed
    Expected behavior: B should only execute after A is done
    """
    print("\n=== Test 1: Two-node DAG Success ===")

    # Create test tasks with DAG dependency
    task_a_code = "TEST-DAG-A-001"
    task_b_code = "TEST-DAG-B-001"

    # Create task A (no dependencies)
    result_a = create_test_task(task_a_code, "Test task A")
    if not result_a or not result_a.get("success"):
        print(f"❌ Failed to create task A: {result_a}")
        return False
    task_a_id = result_a["task_id"]
    print(f"✅ Created task A: {task_a_id} (task_code: {task_a_code})")

    # Create task B with dependency on task A
    result_b = create_test_task(task_b_code, "Test task B", dependencies=[task_a_id])
    if not result_b or not result_b.get("success"):
        print(f"❌ Failed to create task B: {result_b}")
        return False
    task_b_id = result_b["task_id"]
    print(
        f"✅ Created task B: {task_b_id} (task_code: {task_b_code}) with dependency on {task_a_id}"
    )

    # Initially, only task A should be available for execution
    next_task = get_next_task()
    if not next_task or not next_task.get("task"):
        print("❌ No task available when only task A should be ready")
        return False
    if next_task["task"]["task_code"] != task_a_code:
        print(f"❌ Expected task A ({task_a_code}), got {next_task['task']['task_code']}")
        return False
    print("✅ Correctly got task A as next task")

    # Submit success result for task A
    result = submit_task_result(task_a_code, "DONE", {"message": "Task A completed successfully"})
    if not result or not result.get("success"):
        print(f"❌ Failed to submit result for task A: {result}")
        return False
    print("✅ Submitted success result for task A")

    # Now task B should be available for execution
    time.sleep(1)  # Give hub time to process
    next_task = get_next_task()
    if not next_task or not next_task.get("task"):
        print("❌ No task available when task B should be ready")
        return False
    if next_task["task"]["task_code"] != task_b_code:
        print(f"❌ Expected task B ({task_b_code}), got {next_task['task']['task_code']}")
        return False
    print("✅ Correctly got task B as next task after task A completed")

    # Submit success result for task B
    result = submit_task_result(task_b_code, "DONE", {"message": "Task B completed successfully"})
    if not result or not result.get("success"):
        print(f"❌ Failed to submit result for task B: {result}")
        return False
    print("✅ Submitted success result for task B")

    # Verify both tasks are DONE
    status_a = get_task_status(task_a_code)
    status_b = get_task_status(task_b_code)

    if status_a != "DONE":
        print(f"❌ Task A status should be DONE, got {status_a}")
        return False
    if status_b != "DONE":
        print(f"❌ Task B status should be DONE, got {status_b}")
        return False

    print("✅ Test 1 passed: Two-node DAG executed successfully")
    return True


def test_failure_propagation():
    """
    Test case 2: Failure propagation in DAG
    Expected behavior: B should be blocked when A fails
    """
    print("\n=== Test 2: Failure Propagation ===")

    # Create test tasks with DAG dependency
    task_a_code = "TEST-DAG-A-002"
    task_b_code = "TEST-DAG-B-002"

    # Create task A (no dependencies)
    result_a = create_test_task(task_a_code, "Test task A (will fail)")
    if not result_a or not result_a.get("success"):
        print(f"❌ Failed to create task A: {result_a}")
        return False
    task_a_id = result_a["task_id"]
    print(f"✅ Created task A: {task_a_id} (task_code: {task_a_code})")

    # Create task B with dependency on task A
    result_b = create_test_task(
        task_b_code, "Test task B (will be blocked)", dependencies=[task_a_id]
    )
    if not result_b or not result_b.get("success"):
        print(f"❌ Failed to create task B: {result_b}")
        return False
    task_b_id = result_b["task_id"]
    print(
        f"✅ Created task B: {task_b_id} (task_code: {task_b_code}) with dependency on {task_a_id}"
    )

    # Get task A and fail it
    next_task = get_next_task()
    if not next_task or not next_task.get("task") or next_task["task"]["task_code"] != task_a_code:
        print(
            f"❌ Expected task A ({task_a_code}), got {next_task['task']['task_code'] if next_task and next_task.get('task') else 'None'}"
        )
        return False

    # Submit failure result for task A
    result = submit_task_result(
        task_a_code, "FAIL", reason_code="TASK_FAILED", last_error="Test failure for DAG workflow"
    )
    if not result or not result.get("success"):
        print(f"❌ Failed to submit failure for task A: {result}")
        return False
    print("✅ Submitted failure result for task A")

    # Wait for failure propagation
    time.sleep(2)  # Give hub time to propagate failure

    # Check task B status - should be BLOCKED
    status_b = get_task_status(task_b_code)
    if status_b != "BLOCKED":
        print(f"❌ Task B status should be BLOCKED, got {status_b}")
        return False

    # Check reason code - should be dep_failed
    url = f"{HUB_URL}/api/task/status?task_code={task_b_code}"
    response = requests.get(url, timeout=5)
    task_b_data = response.json()["task"]
    if task_b_data["reason_code"] != "dep_failed":
        print(f"❌ Task B reason_code should be 'dep_failed', got '{task_b_data['reason_code']}'")
        return False

    print("✅ Task B correctly marked as BLOCKED with reason_code=dep_failed")
    print("✅ Test 2 passed: Failure propagation works correctly")
    return True


def main():
    """
    Main test function
    """
    print("🚀 Starting DAG Workflow Tests for A2A Hub")
    print("=" * 50)

    # Register test agent
    print(f"🔍 Registering test agent: {AGENT_ID}")
    agent_result = register_test_agent()
    if not agent_result or not agent_result.get("success"):
        print(f"❌ Failed to register agent: {agent_result}")
        return 1
    print("✅ Agent registered successfully")

    # Run tests
    tests = [test_dag_workflow_success, test_failure_propagation]

    passed = 0
    total = len(tests)

    for test in tests:
        if test():
            passed += 1

    print("\n" + "=" * 50)
    print(f"📊 Test Results: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All tests passed! DAG workflow functionality is working correctly.")
        return 0
    else:
        print("💥 Some tests failed! Please check the implementation.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
