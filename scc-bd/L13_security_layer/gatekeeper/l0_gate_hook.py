#!/usr/bin/env python3
"""
L0 Gate Custom Hook
TaskCode: HARDEN-L0-PRECOMMIT-v0.1

This hook performs the following checks:
1. 禁删检测（git diff --name-status）
2. 绝对路径检测（Windows 盘符与 \\ UNC）
3. 法源反复制检测（出现疑似 law 正文片段则 fail，允许引用 law/QCC-README.md）
"""

import os
import re
import subprocess
import sys


def check_file_deletions():
    """Check for file deletions using git diff --name-status"""
    print("Checking for file deletions...")
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-status"], capture_output=True, text=True, check=True
        )

        deleted_files = []
        for line in result.stdout.strip().split("\n"):
            if line.startswith("D"):
                deleted_files.append(line.split("\t")[1])

        if deleted_files:
            print(f"ERROR: File deletion detected: {', '.join(deleted_files)}")
            print("MIGRATE+CRUD 禁删")
            return False

        print("✓ No file deletions detected")
        return True
    except subprocess.CalledProcessError as e:
        print(f"ERROR: Failed to check git diff: {e}")
        return False


def check_absolute_paths():
    """Check for absolute paths in staged files"""
    print("Checking for absolute paths...")

    # Get staged files
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"], capture_output=True, text=True, check=True
        )
        staged_files = result.stdout.strip().split("\n")
    except subprocess.CalledProcessError as e:
        print(f"ERROR: Failed to get staged files: {e}")
        return False

    absolute_path_patterns = [
        # Windows absolute paths (C:\, D:\, etc.)
        r"[A-Za-z]:[\\/]",
        # UNC paths (\\server\\share)
        r"\\\\[A-Za-z0-9_.-]+\\[A-Za-z0-9_.-]+",
    ]

    has_absolute_paths = False

    for file_path in staged_files:
        if not os.path.exists(file_path):
            continue

        try:
            with open(file_path, encoding="utf-8", errors="ignore") as f:
                content = f.read()

            for pattern in absolute_path_patterns:
                matches = re.findall(pattern, content)
                if matches:
                    print(f"ERROR: Absolute path detected in {file_path}: {matches[0]}")
                    has_absolute_paths = True
                    break
        except Exception as e:
            print(f"ERROR: Failed to check {file_path}: {e}")
            continue

    if has_absolute_paths:
        print("路径只用 repo_root 相对路径")
        return False

    print("✓ No absolute paths detected")
    return True


def check_law_duplication():
    """Check for law content duplication"""
    print("Checking for law content duplication...")

    # Get staged files
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"], capture_output=True, text=True, check=True
        )
        staged_files = result.stdout.strip().split("\n")
    except subprocess.CalledProcessError as e:
        print(f"ERROR: Failed to get staged files: {e}")
        return False

    # Read law files to check for duplication
    law_files = [f for f in os.listdir("law") if f.endswith(".md") and f != "QCC-README.md"]
    law_contents = []

    for law_file in law_files:
        law_path = os.path.join("law", law_file)
        try:
            with open(law_path, encoding="utf-8") as f:
                content = f.read()
                # Split into chunks to check for partial duplication
                chunks = [
                    content[i : i + 200]
                    for i in range(0, len(content), 100)
                    if len(content[i : i + 200]) >= 100
                ]
                law_contents.extend(chunks)
        except Exception as e:
            print(f"ERROR: Failed to read law file {law_path}: {e}")
            continue

    has_law_duplication = False

    for file_path in staged_files:
        if file_path.startswith("law/"):
            continue

        if not os.path.exists(file_path):
            continue

        try:
            with open(file_path, encoding="utf-8", errors="ignore") as f:
                content = f.read()

            for chunk in law_contents:
                if chunk in content:
                    print(f"ERROR: Law content duplication detected in {file_path}")
                    print("禁止复制法源正文")
                    has_law_duplication = True
                    break
        except Exception as e:
            print(f"ERROR: Failed to check {file_path}: {e}")
            continue

    if has_law_duplication:
        return False

    print("✓ No law content duplication detected")
    return True


def main():
    """Main function to run all checks"""
    print("Running L0 Gate Custom Hook...")

    checks = [check_file_deletions, check_absolute_paths, check_law_duplication]

    all_passed = True

    for check in checks:
        if not check():
            all_passed = False
        print()

    if all_passed:
        print("✓ All L0 Gate checks passed")
        return 0
    else:
        print("✗ Some L0 Gate checks failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
