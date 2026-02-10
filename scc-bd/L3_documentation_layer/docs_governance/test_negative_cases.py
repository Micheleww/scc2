#!/usr/bin/env python3
"""
Negative Test Cases Generator for Docs Unique Entry Guard
Creates failure scenarios to validate the validator's behavior
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

# Constants
PROJECT_ROOT = Path(os.getcwd())
ARTIFACTS_DIR = (
    PROJECT_ROOT
    / "docs"
    / "REPORT"
    / "docs_gov"
    / "artifacts"
    / "HARDEN-DOCS-UNIQUE-ENTRY-GUARD-v0.1"
)
VALIDATOR_SCRIPT = PROJECT_ROOT / "tools" / "docs_governance" / "unique_entry_guard.py"
ARCH_INDEX_FILE = PROJECT_ROOT / "docs" / "ARCH" / "00_index.md"

# Create artifacts directory if it doesn't exist
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)


def test_case_1_incorrect_link():
    """Test Case 1: Incorrect first link in 00_index.md"""
    print("\n=== Test Case 1: Incorrect first link in 00_index.md ===")

    # Backup original file
    backup_file = ARCH_INDEX_FILE.with_suffix(".md.bak")
    shutil.copy2(ARCH_INDEX_FILE, backup_file)

    try:
        # Read original content
        with open(ARCH_INDEX_FILE, encoding="utf-8") as f:
            content = f.read()

        # Find first link and replace it with incorrect link
        import re

        lines = content.split("\n")
        modified_lines = []
        found = False

        for line in lines:
            if not found and re.search(r"\[.*?\]\(([^#]+?)\)", line):
                # Replace first link with incorrect one
                modified_line = re.sub(
                    r"\[.*?\]\(([^#]+?)\)", "[Incorrect Link](wrong_navigation.md)", line, 1
                )
                modified_lines.append(modified_line)
                found = True
            else:
                modified_lines.append(line)

        # Write modified content
        with open(ARCH_INDEX_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(modified_lines))

        # Run validator
        result = subprocess.run(
            [sys.executable, str(VALIDATOR_SCRIPT)], capture_output=True, text=True
        )

        # Save output
        output_file = ARTIFACTS_DIR / "test_case_1_output.txt"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write("STDOUT:\n")
            f.write(result.stdout)
            f.write("\nSTDERR:\n")
            f.write(result.stderr)
            f.write(f"\nEXIT CODE: {result.returncode}\n")

        print(f"Test output saved to {output_file.relative_to(PROJECT_ROOT)}")
        print(f"Exit code: {result.returncode} (expected: 1)")

        return result.returncode == 1

    finally:
        # Restore original file
        shutil.copy2(backup_file, ARCH_INDEX_FILE)
        backup_file.unlink()


def test_case_2_suspicious_file():
    """Test Case 2: Suspicious entry file exists"""
    print("\n=== Test Case 2: Suspicious entry file exists ===")

    # Create a suspicious file
    suspicious_file = PROJECT_ROOT / "docs" / "ARCH" / "suspicious_navigation.md"

    try:
        # Create suspicious file
        with open(suspicious_file, "w", encoding="utf-8") as f:
            f.write("# Suspicious Navigation File\n\nThis file should be detected as suspicious.\n")

        # Run validator
        result = subprocess.run(
            [sys.executable, str(VALIDATOR_SCRIPT)], capture_output=True, text=True
        )

        # Save output
        output_file = ARTIFACTS_DIR / "test_case_2_output.txt"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write("STDOUT:\n")
            f.write(result.stdout)
            f.write("\nSTDERR:\n")
            f.write(result.stderr)
            f.write(f"\nEXIT CODE: {result.returncode}\n")

        print(f"Test output saved to {output_file.relative_to(PROJECT_ROOT)}")
        print(f"Exit code: {result.returncode} (expected: 1)")

        return result.returncode == 1

    finally:
        # Remove suspicious file
        if suspicious_file.exists():
            suspicious_file.unlink()


def main():
    """Run all negative test cases"""
    print("=== Docs Unique Entry Guard Negative Test Cases ===")

    # Run test cases
    test1_result = test_case_1_incorrect_link()
    test2_result = test_case_2_suspicious_file()

    # Write summary
    summary_file = ARTIFACTS_DIR / "negative_test_summary.txt"
    with open(summary_file, "w", encoding="utf-8") as f:
        f.write("=== Negative Test Cases Summary ===\n")
        f.write(f"Test Case 1 (Incorrect Link): {'PASS' if test1_result else 'FAIL'}\n")
        f.write(f"Test Case 2 (Suspicious File): {'PASS' if test2_result else 'FAIL'}\n")
        f.write(f"Overall Result: {'PASS' if test1_result and test2_result else 'FAIL'}\n")

    print(f"\nSummary saved to {summary_file.relative_to(PROJECT_ROOT)}")
    print("\n=== Negative Test Results ===")
    print(f"Test Case 1: {'PASS' if test1_result else 'FAIL'} - Incorrect link detection")
    print(f"Test Case 2: {'PASS' if test2_result else 'FAIL'} - Suspicious file detection")
    print(f"Overall: {'PASS' if test1_result and test2_result else 'FAIL'}")

    return 0 if test1_result and test2_result else 1


if __name__ == "__main__":
    sys.exit(main())
