#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path


def test_skip_policy():
    print("Testing Skip Policy: Self-check for silent skips")
    print("=" * 80)

    result = subprocess.run(
        ["python", "-m", "pytest", "-q", "tools/docs_governance/tests", "-rs"],
        cwd=Path(__file__).parent.parent.parent.parent,
        capture_output=True,
        text=True,
    )

    output = result.stdout + result.stderr

    print(f"Pytest exit code: {result.returncode}")
    print()
    print("Pytest output:")
    print(output)
    print()

    if result.returncode == 0:
        print("✓ PASS: All tests passed (0 skipped)")
        return True
    else:
        print("✗ FAIL: Some tests failed or were skipped")
        return False


if __name__ == "__main__":
    success = test_skip_policy()
    sys.exit(0 if success else 1)
