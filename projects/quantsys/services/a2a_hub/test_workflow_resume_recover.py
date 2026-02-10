#!/usr/bin/env python3

import sqlite3
import sys

import requests

BASE_URL = "http://localhost:18788/api"
DB_PATH = "D:\\quantsys\\tools\\a2a_hub\\state\\a2a_hub.db"


def cleanup_db():
    """Clean up the database by deleting all tasks and workflows."""
    print("Cleaning up database...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Delete from workflows table
    cursor.execute("DELETE FROM workflows")

    # Delete from tasks table
    cursor.execute("DELETE FROM tasks")

    conn.commit()
    conn.close()
    print("Database cleanup completed.")


def create_test_tasks():
    """Create test tasks with dependencies."""
    print("Creating test tasks...")

    # Task 1: No dependencies, PENDING
    task1 = {
        "task_code": "TEST-TASK-001",
        "instructions": "Test task 1",
        "owner_role": "Test Engineer",
        "area": "test",
        "priority": 0,
        "dependencies": [],
    }

    # Task 2: Depends on task1, PENDING
    task2 = {
        "task_code": "TEST-TASK-002",
        "instructions": "Test task 2",
        "owner_role": "Test Engineer",
        "area": "test",
        "priority": 0,
        "dependencies": ["TEST-TASK-001"],
    }

    # Task 3: Depends on task2, RUNNING with invalid lease
    task3 = {
        "task_code": "TEST-TASK-003",
        "instructions": "Test task 3",
        "owner_role": "Test Engineer",
        "area": "test",
        "priority": 0,
        "dependencies": ["TEST-TASK-002"],
    }

    # Task 4: Depends on task3, DONE (inconsistent)
    task4 = {
        "task_code": "TEST-TASK-004",
        "instructions": "Test task 4",
        "owner_role": "Test Engineer",
        "area": "test",
        "priority": 0,
        "dependencies": ["TEST-TASK-003"],
    }

    # Create tasks via API
    create_task(task1)
    create_task(task2)
    create_task(task3)
    create_task(task4)

    # Manually update task3 to RUNNING with invalid lease
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Set task3 to RUNNING with invalid lease (past timestamp)
    cursor.execute("""
    UPDATE tasks
    SET status = "RUNNING", lease_expiry_ts = "2025-01-01T00:00:00Z"
    WHERE task_code = "TEST-TASK-003"
    """)

    # Set task4 to DONE (inconsistent because task3 is RUNNING)
    cursor.execute("""
    UPDATE tasks
    SET status = "DONE"
    WHERE task_code = "TEST-TASK-004"
    """)

    conn.commit()
    conn.close()

    print("Test tasks created successfully.")


def create_task(task_data):
    """Create a task via API."""
    url = f"{BASE_URL}/api/task/create"
    response = requests.post(url, json=task_data)
    if response.status_code != 200:
        print(f"Failed to create task {task_data['task_code']}: {response.text}")
        sys.exit(1)
    print(f"Created task {task_data['task_code']}: {response.json()['success']}")


def get_workflow_status():
    """Get workflow status."""
    url = f"{BASE_URL}/api/workflow/status"
    response = requests.get(url)
    if response.status_code != 200:
        print(f"Failed to get workflow status: {response.text}")
        return None
    return response.json()


def test_workflow_recover():
    """Test workflow recovery."""
    print("\n=== Testing Workflow Recovery ===")

    # Step 1: Get initial workflow status
    print("Step 1: Getting initial workflow status...")
    status_before = get_workflow_status()
    print(f"Task counts before recovery: {status_before['task_counts']}")

    # Step 2: Trigger workflow recovery
    print("Step 2: Triggering workflow recovery...")
    url = f"{BASE_URL}/api/workflow/recover"
    response = requests.post(url)
    if response.status_code != 200:
        print(f"Failed to trigger workflow recovery: {response.text}")
        return False

    recovery_result = response.json()
    print(f"Recovery success: {recovery_result['success']}")
    print(f"Recovery message: {recovery_result['message']}")

    if recovery_result["recovered_tasks"]:
        print(f"Recovered tasks: {len(recovery_result['recovered_tasks'])}")
        for task in recovery_result["recovered_tasks"]:
            print(f"  - {task['task_code']}: {task['old_status']} -> {task['new_status']}")

    if recovery_result["inconsistent_tasks"]:
        print(f"Inconsistent tasks: {len(recovery_result['inconsistent_tasks'])}")
        for task in recovery_result["inconsistent_tasks"]:
            print(f"  - {task['task_code']}: {task['reason_code']} - {task['description']}")

    # Step 3: Get workflow status after recovery
    print("Step 3: Getting workflow status after recovery...")
    status_after = get_workflow_status()
    print(f"Task counts after recovery: {status_after['task_counts']}")

    # Step 4: Verify recovery results
    print("Step 4: Verifying recovery results...")

    # Check if task3 was recovered from RUNNING to PENDING
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('SELECT status FROM tasks WHERE task_code = "TEST-TASK-003"')
    task3_status = cursor.fetchone()[0]

    cursor.execute('SELECT status FROM tasks WHERE task_code = "TEST-TASK-004"')
    task4_status = cursor.fetchone()[0]

    conn.close()

    print(f"Task3 status after recovery: {task3_status}")
    print(f"Task4 status after recovery: {task4_status}")

    # Validate results
    if task3_status == "PENDING":
        print("✅ Task3 was correctly recovered from RUNNING to PENDING")
    else:
        print("❌ Task3 was not correctly recovered")
        return False

    # Task4 should still be DONE, but this is inconsistent with task3 being PENDING
    # The recovery process should detect this inconsistency but not automatically fix it
    print("✅ Workflow recovery test completed successfully")
    return True


def main():
    """Main test function."""
    print("=== A2A Workflow Resume/Recover Test ===")

    try:
        # Cleanup database
        cleanup_db()

        # Create test tasks
        create_test_tasks()

        # Test workflow recovery
        if test_workflow_recover():
            print("\n🎉 All tests passed!")
            return True
        else:
            print("\n❌ Tests failed!")
            return False
    except Exception as e:
        print(f"\n❌ Test failed with exception: {e}")
        return False
    finally:
        # Cleanup database again
        cleanup_db()


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
