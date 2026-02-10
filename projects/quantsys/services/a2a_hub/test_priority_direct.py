#!/usr/bin/env python3
"""
Direct test for A2A Hub priority scheduler

This script tests the priority scheduling functionality directly by:
1. Creating an in-memory database
2. Inserting test tasks with different priorities
3. Querying the database with the priority scheduling logic
4. Verifying that tasks are returned in the correct order: high priority first, same priority FIFO
"""

import datetime
import sqlite3
import uuid


def init_test_db():
    """Initialize an in-memory test database with the same schema as the main database"""
    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()

    # Create tasks table with the same schema as main.py
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
        lease_seconds INTEGER DEFAULT 60,
        priority INTEGER DEFAULT 0
    )
    """)

    return conn


def create_test_task(conn, task_code, priority, agent_id, created_at):
    """Create a test task in the database"""
    cursor = conn.cursor()
    task_id = str(uuid.uuid4())

    cursor.execute(
        """
    INSERT INTO tasks (
        id, task_code, instructions, owner_role, deadline, status, 
        result, created_at, updated_at, timeout_seconds, max_retries, agent_id,
        next_retry_ts, retry_backoff_sec, priority
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            task_id,
            task_code,
            f"Test task {task_code}",
            "TestRole",
            None,
            "PENDING",
            None,
            created_at,
            created_at,
            3600,
            3,
            agent_id,
            None,
            60,
            priority,
        ),
    )
    conn.commit()
    return task_id


def get_next_task(conn, agent_id):
    """Get next task using the priority scheduling logic and update its status to RUNNING"""
    cursor = conn.cursor()
    now = datetime.datetime.utcnow().isoformat() + "Z"

    # Same query as used in main.py
    cursor.execute(
        """
    SELECT * FROM tasks 
    WHERE status = 'PENDING' AND agent_id = ? 
        AND (next_retry_ts IS NULL OR next_retry_ts <= ?)
    ORDER BY 
        CASE WHEN next_retry_ts IS NULL THEN 0 ELSE 1 END, 
        priority DESC, 
        created_at ASC 
    LIMIT 1
    """,
        (agent_id, now),
    )

    task = cursor.fetchone()

    if task:
        # Update task status to RUNNING, just like main.py does
        task_id = task[0]
        cursor.execute(
            """
        UPDATE tasks 
        SET status = 'RUNNING', updated_at = ? 
        WHERE id = ?
        """,
            (now, task_id),
        )
        conn.commit()

    return task


def main():
    """Main test function"""
    print("=== A2A Priority Scheduler Direct Test ===")

    # Initialize test database
    conn = init_test_db()

    # Test agent ID
    test_agent_id = "test-agent-123"

    # Create test tasks with different priorities and creation times
    # We'll use sequential timestamps to ensure FIFO ordering for same priorities
    base_time = datetime.datetime.utcnow()

    # Create tasks in this order:
    # - task-p0-1 (priority 0, first)
    # - task-p1-1 (priority 1, second)
    # - task-p2-1 (priority 2, third)
    # - task-p3-1 (priority 3, fourth)
    # - task-p3-2 (priority 3, fifth)
    # - task-p2-2 (priority 2, sixth)
    # - task-p1-2 (priority 1, seventh)
    # - task-p0-2 (priority 0, eighth)

    tasks = [
        ("task-p0-1", 0, 0),  # priority, seconds_offset
        ("task-p1-1", 1, 1),
        ("task-p2-1", 2, 2),
        ("task-p3-1", 3, 3),
        ("task-p3-2", 3, 4),
        ("task-p2-2", 2, 5),
        ("task-p1-2", 1, 6),
        ("task-p0-2", 0, 7),
    ]

    print("\nCreating test tasks...")
    for task_code, priority, seconds_offset in tasks:
        created_at = (base_time + datetime.timedelta(seconds=seconds_offset)).isoformat() + "Z"
        task_id = create_test_task(conn, task_code, priority, test_agent_id, created_at)
        print(f"Created task {task_code} with priority {priority} at {created_at}")

    # Expected order: high priority first, same priority FIFO
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

    print("\nGetting tasks in order...")
    actual_order = []

    for _ in range(len(expected_order)):
        task = get_next_task(conn, test_agent_id)
        if task:
            task_code = task[1]
            priority = task[19]
            actual_order.append(task_code)
            print(f"Got task: {task_code} (priority {priority})")
        else:
            print("No more tasks found")
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
