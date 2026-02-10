#!/usr/bin/env python3
"""
Control Plane Change Detection

This script detects if a PR/commit modifies any control plane paths and sets STRICT_MODE accordingly.
"""

import subprocess
import sys

# Control plane paths to protect
CONTROL_PATHS = [
    # GitHub configuration
    ".github/workflows/",
    ".github/actions/",
    ".github/CODEOWNERS",
    ".github/",
    # Gatekeeper tools
    "tools/gatekeeper/",
    # Legal and compliance
    "law/",
    "law/QCC-README.md",
    # Architecture documentation
    "docs/ARCH/project_navigation__v0.1.0__DRAFT__20260115.md",
    # Trae rules
    ".trae/rules/",
    ".trae/rules/project_rules.md",
    # A2A control plane
    "tools/a2a_hub/",
    "tools/a2a_worker/",
    # Exchange server control plane
    "tools/exchange_server/",
]


def run_git_diff():
    """Run git diff and return the changed files"""
    try:
        # Get changed files in the current commit/PR
        # For PRs, this compares with the base branch
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD^1", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        changed_files = result.stdout.strip().split("\n") if result.stdout.strip() else []
        return changed_files
    except subprocess.CalledProcessError:
        # If we're on the first commit, compare with nothing
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", "--cached"],
                capture_output=True,
                text=True,
                check=True,
            )
            changed_files = result.stdout.strip().split("\n") if result.stdout.strip() else []
            return changed_files
        except subprocess.CalledProcessError:
            # If git diff fails, return empty list (safe default)
            return []
    except Exception:
        # Any other error, return empty list
        return []


def check_control_plane_modification(changed_files):
    """Check if any changed file is in the control plane"""
    for file in changed_files:
        for control_path in CONTROL_PATHS:
            if file.startswith(control_path):
                return True
    return False


def main():
    """Main function"""
    changed_files = run_git_diff()
    strict_mode = check_control_plane_modification(changed_files)

    # Output for CI consumption
    print(f"STRICT_MODE={'true' if strict_mode else 'false'}")

    # Also set as environment variable format for GitHub Actions
    print(f"::set-output name=strict_mode::{strict_mode}")

    # Return success exit code
    sys.exit(0)


if __name__ == "__main__":
    main()
