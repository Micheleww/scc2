#!/usr/bin/env python3
import subprocess
import sys
import tempfile
from pathlib import Path


def test_staged_docs_files():
    print("Testing Case C: Staged docs files exist")
    print("=" * 80)

    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)

        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        docs_dir = repo_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "test.md").write_text("---\ndoc_id: test\nkind: TEST\n---\n\n# Test\n")
        subprocess.run(
            ["git", "add", "docs/test.md"], cwd=repo_path, check=True, capture_output=True
        )

        result = subprocess.run(
            ["python", "tools/docs_governance/check_docs.py"],
            cwd=Path(__file__).parent.parent.parent.parent,
            capture_output=True,
            text=True,
        )

        output = result.stdout + result.stderr

        if "Found 1 staged file(s)" in output:
            print("✓ PASS: Output contains 'Found 1 staged file(s)'")
        else:
            print("✗ FAIL: Output does not contain 'Found 1 staged file(s)'")
            print(f"Output: {output}")
            return False

        if "skip" not in output.lower():
            print("✓ PASS: No skip detected")
        else:
            print("✗ FAIL: Unexpected skip detected")
            return False

    print()
    return True


if __name__ == "__main__":
    success = test_staged_docs_files()
    sys.exit(0 if success else 1)
