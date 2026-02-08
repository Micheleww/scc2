#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path


def test_no_staged_files():
    print("Testing Case A: No staged files")
    print("=" * 80)

    result = subprocess.run(
        ["python", "tools/docs_governance/check_docs.py"],
        cwd=Path(__file__).parent.parent.parent.parent,
        capture_output=True,
        text=True,
    )

    output = result.stdout + result.stderr

    if "No staged files found, skip" in output:
        print("✓ PASS: Output contains 'No staged files found, skip'")
    else:
        print("✗ FAIL: Output does not contain 'No staged files found, skip'")
        print(f"Output: {output}")
        return False

    if result.returncode == 0:
        print("✓ PASS: Return code is 0")
    else:
        print(f"✗ FAIL: Return code is {result.returncode}, expected 0")
        return False

    if "full check" not in output.lower():
        print("✓ PASS: No fallback to full check")
    else:
        print("✗ FAIL: Fallback to full check detected")
        return False

    print()
    return True


if __name__ == "__main__":
    success = test_no_staged_files()
    sys.exit(0 if success else 1)
