#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path


def test_staged_no_docs_files():
    print("Testing Case B: Staged files exist but none are docs-related")
    print("=" * 80)

    result = subprocess.run(
        ["python", "tools/docs_governance/check_docs.py"],
        cwd=Path(__file__).parent.parent.parent.parent,
        capture_output=True,
        text=True,
    )

    output = result.stdout + result.stderr

    if "no docs files, skip" in output:
        print("✓ PASS: Output contains 'no docs files, skip'")
    else:
        print("✗ FAIL: Output does not contain 'no docs files, skip'")
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
    success = test_staged_no_docs_files()
    sys.exit(0 if success else 1)
