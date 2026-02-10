#!/usr/bin/env python3
"""A2A Hub 状态恢复脚本

This script restores the A2A Hub SQLite database from a backup file.

Usage:
    python restore_hub.py [--backup-file <file>] [--latest] [--no-verify]

Options:
    --backup-file <file>  Path to backup file
    --latest              Use latest backup file in backup directory
    --no-verify           Skip consistency verification
    --backup-dir <dir>    Backup directory (default: ./backup)
"""

import argparse
import datetime
import os
import shutil
import sqlite3
import sys


def find_latest_backup(backup_dir):
    """Find the latest backup file in the backup directory"""
    backups = []
    for file in os.listdir(backup_dir):
        if file.startswith("a2a_hub_backup_") and file.endswith(".db"):
            backups.append(file)

    if not backups:
        return None

    # Sort backups by timestamp (filename format: a2a_hub_backup_YYYYMMDD_HHMMSS.db)
    backups.sort(reverse=True)
    return os.path.join(backup_dir, backups[0])


def verify_consistency(db_path):
    """Verify consistency of restored database"""
    print("=== 一致性校验 ===")

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 1. Verify tables exist
        print("1. 检查表结构...")
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        table_names = [table[0] for table in tables]

        expected_tables = ["tasks", "agents", "dlq"]
        for expected in expected_tables:
            if expected in table_names:
                print(f"   OK {expected} 表存在")
            else:
                print(f"   ERROR {expected} 表不存在")
                return False

        # 2. Verify tasks table schema完整性
        print("2. 检查tasks表字段完整性...")
        cursor.execute("PRAGMA table_info(tasks);")
        task_columns = [col[1] for col in cursor.fetchall()]

        # 检查核心状态机字段
        expected_task_fields = [
            "id",
            "task_code",
            "instructions",
            "owner_role",
            "status",
            "created_at",
            "updated_at",
            "agent_id",
            "reason_code",
            "last_error",
            "lease_expiry_ts",
            "timeout_seconds",
        ]

        for field in expected_task_fields:
            if field in task_columns:
                print(f"   OK tasks.{field} 字段存在")
            else:
                print(f"   ERROR tasks.{field} 字段缺失")
                return False

        # 3. 检查tasks状态值
        print("3. 检查tasks状态值...")
        cursor.execute("SELECT DISTINCT status FROM tasks;")
        status_values = [row[0] for row in cursor.fetchall()]
        valid_statuses = [
            "PENDING",
            "ASSIGNED",
            "RUNNING",
            "DONE",
            "FAIL",
            "TIMEOUT",
            "RETRYING",
            "CANCELLED",
        ]

        print(f"   发现状态值: {status_values}")
        for status in status_values:
            if status in valid_statuses:
                print(f"   OK 状态 {status} 有效")
            else:
                print(f"   WARNING 状态 {status} 可能无效")

        # 4. 检查DLQ表可查询性
        print("4. 检查DLQ表可查询性...")
        cursor.execute("SELECT COUNT(*) FROM dlq;")
        dlq_count = cursor.fetchone()[0]
        print(f"   OK DLQ 记录数: {dlq_count}")

        # 5. 检查DLQ表字段完整性
        print("5. 检查DLQ表字段完整性...")
        cursor.execute("PRAGMA table_info(dlq);")
        dlq_columns = [col[1] for col in cursor.fetchall()]

        expected_dlq_fields = [
            "id",
            "task_code",
            "trace_id",
            "reason_code",
            "last_error",
            "task_data",
            "created_at",
            "updated_at",
        ]

        for field in expected_dlq_fields:
            if field in dlq_columns:
                print(f"   OK dlq.{field} 字段存在")
            else:
                print(f"   ERROR dlq.{field} 字段缺失")
                return False

        # 6. 检查agents表
        print("6. 检查agents表...")
        cursor.execute("SELECT COUNT(*) FROM agents;")
        agents_count = cursor.fetchone()[0]
        print(f"   OK Agents 记录数: {agents_count}")

        # 7. 检查索引完整性
        print("7. 检查索引完整性...")
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index';")
        indexes = cursor.fetchall()
        index_names = [idx[0] for idx in indexes]

        expected_indexes = ["idx_task_code_unique", "idx_agent_id_unique"]
        for idx in expected_indexes:
            if idx in index_names:
                print(f"   OK 索引 {idx} 存在")
            else:
                print(f"   WARNING 索引 {idx} 缺失")

        conn.close()
        print("OK 所有一致性检查通过")
        return True

    except sqlite3.Error as e:
        print(f"ERROR 一致性检查失败: {e}")
        return False
    except Exception as e:
        print(f"ERROR 一致性检查过程中发生错误: {e}")
        return False


def main():
    """Main function for restore script"""
    parser = argparse.ArgumentParser(description="A2A Hub State Restore Script")
    parser.add_argument("--backup-file", type=str, help="Path to backup file")
    parser.add_argument("--latest", action="store_true", help="Use latest backup file")
    parser.add_argument("--no-verify", action="store_true", help="Skip consistency verification")
    parser.add_argument("--backup-dir", type=str, default="./backup", help="Backup directory")
    args = parser.parse_args()

    # Configuration
    state_dir = os.path.join(os.path.dirname(__file__), "state")
    db_path = os.path.join(state_dir, "a2a_hub.db")
    backup_dir = args.backup_dir
    backup_file = args.backup_file

    print("=== A2A Hub 状态恢复脚本 ===")

    # Find backup file if latest is specified
    if args.latest:
        if backup_file:
            print("WARNING: --latest 和 --backup-file 同时指定，将使用--latest")

        backup_file = find_latest_backup(backup_dir)
        if not backup_file:
            print(f"ERROR: 在 {backup_dir} 中未找到备份文件")
            return 1
        print(f"使用最新备份: {backup_file}")

    # Check if backup file is specified and exists
    if not backup_file:
        print("ERROR: 必须指定 --backup-file 或 --latest")
        return 1

    if not os.path.exists(backup_file):
        print(f"ERROR: 备份文件不存在 {backup_file}")
        return 1

    print(f"恢复源: {backup_file}")
    print(f"恢复目标: {db_path}")

    try:
        # Ensure state directory exists
        os.makedirs(state_dir, exist_ok=True)

        # Create a rollback backup of current state
        print("创建当前状态的回滚备份...")
        if os.path.exists(db_path):
            rollback_timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            rollback_path = os.path.join(state_dir, f"a2a_hub_rollback_{rollback_timestamp}.db")
            shutil.copy2(db_path, rollback_path)
            print(f"   OK 回滚备份创建成功: {rollback_path}")

        # Restore from backup
        print("开始恢复...")
        shutil.copy2(backup_file, db_path)

        # Verify restore
        if os.path.exists(db_path):
            # Check if restored file is valid SQLite database
            try:
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                tables = cursor.fetchall()
                conn.close()

                print("RESTORE SUCCESS")
                print(f"RESTORE FILE: {db_path}")
                print(f"DATABASE TABLES: {[table[0] for table in tables]}")

                # Run consistency verification unless skipped
                if not args.no_verify:
                    if verify_consistency(db_path):
                        print("CONSISTENCY CHECK PASSED")
                    else:
                        print("CONSISTENCY CHECK FAILED")
                        return 1
                else:
                    print("WARNING: 一致性校验已跳过")

                return 0
            except sqlite3.Error as e:
                print(f"ERROR: 恢复文件无效 - {e}")
                # Restore from rollback if available
                if "rollback_path" in locals():
                    print("恢复回滚备份...")
                    shutil.copy2(rollback_path, db_path)
                return 1
        else:
            print("ERROR: 恢复文件未创建")
            return 1

    except Exception as e:
        print(f"ERROR: 恢复失败: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
