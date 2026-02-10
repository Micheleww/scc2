#!/usr/bin/env python3
"""A2A Hub 状态备份脚本

This script backs up the A2A Hub SQLite database to a specified directory.

Usage:
    python backup_hub.py [--backup-dir <directory>]

Options:
    --backup-dir <directory>  Backup directory (default: ./backup)
"""

import argparse
import datetime
import os
import shutil
import sqlite3
import sys


def main():
    """Main function for backup script"""
    parser = argparse.ArgumentParser(description="A2A Hub State Backup Script")
    parser.add_argument("--backup-dir", type=str, default="./backup", help="Backup directory")
    args = parser.parse_args()

    # Configuration
    state_dir = os.path.join(os.path.dirname(__file__), "state")
    db_path = os.path.join(state_dir, "a2a_hub.db")
    backup_dir = args.backup_dir

    # Ensure backup directory exists
    os.makedirs(backup_dir, exist_ok=True)

    # Generate backup filename with timestamp
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"a2a_hub_backup_{timestamp}.db"
    backup_path = os.path.join(backup_dir, backup_filename)

    print("=== A2A Hub 状态备份脚本 ===")
    print(f"备份源: {db_path}")
    print(f"备份目录: {backup_dir}")
    print(f"备份文件名: {backup_filename}")

    try:
        # Check if database exists
        if not os.path.exists(db_path):
            print(f"ERROR: 数据库文件不存在 {db_path}")
            return 1

        # Perform backup
        print("开始备份...")
        # Use shutil.copy2 to preserve metadata
        shutil.copy2(db_path, backup_path)

        # Verify backup
        if os.path.exists(backup_path):
            # Check if backup is valid SQLite database
            try:
                conn = sqlite3.connect(backup_path)
                cursor = conn.cursor()
                # Try to read tables to verify integrity
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                tables = cursor.fetchall()
                conn.close()

                print("BACKUP SUCCESS")
                print(f"BACKUP FILE: {backup_path}")
                print(f"DATABASE TABLES: {[table[0] for table in tables]}")
                print(f"BACKUP SIZE: {os.path.getsize(backup_path) / 1024:.2f} KB")

                # Create backup manifest
                manifest_path = os.path.join(backup_dir, f"backup_manifest_{timestamp}.json")
                manifest = {
                    "timestamp": datetime.datetime.now().isoformat(),
                    "backup_path": backup_path,
                    "backup_filename": backup_filename,
                    "database_path": db_path,
                    "tables": [table[0] for table in tables],
                    "size_bytes": os.path.getsize(backup_path),
                    "backup_tool": "backup_hub.py",
                    "version": "v0.1",
                }

                with open(manifest_path, "w") as f:
                    import json

                    json.dump(manifest, f, indent=2)

                print(f"BACKUP MANIFEST: {manifest_path}")

                return 0
            except sqlite3.Error as e:
                print(f"ERROR: 备份文件无效 - {e}")
                # Clean up invalid backup
                os.remove(backup_path)
                return 1
        else:
            print("ERROR: 备份文件未创建")
            return 1

    except Exception as e:
        print(f"ERROR: 备份失败: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
