#!/usr/bin/env python3
"""A2A Hub 备份恢复测试脚本

This script tests the backup and restore functionality by:
1. Creating a test task
2. Backing up the database
3. Clearing the state directory
4. Restoring from backup
5. Verifying the task is still present
"""

import os
import sqlite3
import subprocess
import sys


def create_test_task():
    """Create a test task in the A2A Hub database"""
    print("1. 创建测试任务...")

    # Connect to database
    db_path = os.path.join(os.path.dirname(__file__), "state", "a2a_hub.db")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create a test task
    task_data = {
        "id": "test-task-001",
        "task_code": "TEST-TASK-001",
        "instructions": "Test task instructions",
        "owner_role": "test_role",
        "status": "PENDING",
        "created_at": "2026-01-16T00:00:00",
        "updated_at": "2026-01-16T00:00:00",
        "timeout_seconds": 3600,
        "retry_count": 0,
        "max_retries": 3,
        "retry_backoff_sec": 60,
    }

    # Insert task into database
    cursor.execute(
        """
    INSERT OR REPLACE INTO tasks (
        id, task_code, instructions, owner_role, status, 
        created_at, updated_at, timeout_seconds, retry_count, 
        max_retries, retry_backoff_sec
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            task_data["id"],
            task_data["task_code"],
            task_data["instructions"],
            task_data["owner_role"],
            task_data["status"],
            task_data["created_at"],
            task_data["updated_at"],
            task_data["timeout_seconds"],
            task_data["retry_count"],
            task_data["max_retries"],
            task_data["retry_backoff_sec"],
        ),
    )

    conn.commit()
    conn.close()

    print(f"   ✅ 测试任务创建成功: {task_data['task_code']}")
    return task_data["task_code"]


def verify_test_task(task_code):
    """Verify the test task exists in the database"""
    print(f"   验证任务 {task_code} 是否存在...")

    # Connect to database
    db_path = os.path.join(os.path.dirname(__file__), "state", "a2a_hub.db")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if task exists
    cursor.execute("SELECT id, task_code, status FROM tasks WHERE task_code = ?", (task_code,))
    task = cursor.fetchone()
    conn.close()

    if task:
        print(f"   ✅ 任务存在: ID={task[0]}, TaskCode={task[1]}, Status={task[2]}")
        return True
    else:
        print(f"   ❌ 任务不存在: {task_code}")
        return False


def main():
    """Main test function"""
    print("=== A2A Hub 备份恢复测试 ===")

    # Configuration
    state_dir = os.path.join(os.path.dirname(__file__), "state")
    db_path = os.path.join(state_dir, "a2a_hub.db")
    backup_dir = os.path.join(os.path.dirname(__file__), "backup")
    backup_hub_script = os.path.join(os.path.dirname(__file__), "backup_hub.py")
    restore_hub_script = os.path.join(os.path.dirname(__file__), "restore_hub.py")

    # 1. Create test task
    test_task_code = create_test_task()

    # 2. Backup the database
    print("2. 执行备份...")
    backup_result = subprocess.run(
        [sys.executable, backup_hub_script, "--backup-dir", backup_dir],
        cwd=os.path.dirname(__file__),
        capture_output=True,
        text=True,
    )

    if backup_result.returncode == 0:
        print("   OK 备份成功")
        print(f"   备份输出: {backup_result.stdout.strip()}")
    else:
        print(f"   ERROR 备份失败: {backup_result.stderr.strip()}")
        return 1

    # 3. Clear the state directory
    print("3. 清空状态目录...")
    if os.path.exists(db_path):
        os.remove(db_path)
        print(f"   OK 数据库文件已删除: {db_path}")
    else:
        print(f"   WARNING 数据库文件不存在: {db_path}")

    # Verify the task is gone
    print("   验证任务已被清空...")
    if os.path.exists(db_path):
        if not verify_test_task(test_task_code):
            print("   OK 任务已被清空")
        else:
            print("   WARNING 任务仍存在")
    else:
        print("   OK 数据库文件已删除，任务已清空")

    # 4. Restore from backup
    print("4. 从备份恢复...")
    restore_result = subprocess.run(
        [sys.executable, restore_hub_script, "--latest", "--backup-dir", backup_dir],
        cwd=os.path.dirname(__file__),
        capture_output=True,
        text=True,
    )

    if restore_result.returncode == 0:
        print("   OK 恢复成功")
        print(f"   恢复输出: {restore_result.stdout.strip()}")
    else:
        print(f"   ERROR 恢复失败: {restore_result.stderr.strip()}")
        return 1

    # 5. Verify the task is restored
    print("5. 验证任务已恢复...")
    if verify_test_task(test_task_code):
        print("TEST PASSED: 任务已成功恢复")
        return 0
    else:
        print("TEST FAILED: 任务未恢复")
        return 1


if __name__ == "__main__":
    sys.exit(main())
