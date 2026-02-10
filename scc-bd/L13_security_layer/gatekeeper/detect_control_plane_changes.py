#!/usr/bin/env python3
"""
Detect whether a PR touches control-plane paths (gate/CI/workflows/law/docs/ARCH rules).
Fail-closed-friendly: emits key=value lines for GitHub Actions.

Usage:
  python tools/gatekeeper/detect_control_plane_changes.py --base <sha> --head <sha>
"""

from __future__ import annotations

import argparse
import subprocess
import sys

CONTROL_PLANE_PREFIXES = [
    ".github/workflows/",
    ".github/actions/",
    ".github/CODEOWNERS",
    "tools/gatekeeper/",
    "law/QCC-README.md",  # pointer only, still sensitive
    "docs/ARCH/project_navigation__v0.1.0__DRAFT__20260115.md",
    ".trae/rules/project_rules.md",
]


def run(cmd: list[str]) -> str:
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        sys.stderr.write(p.stderr)
        raise SystemExit(p.returncode)
    return p.stdout


def git_diff_names(base: str, head: str) -> list[str]:
    out = run(["git", "diff", "--name-only", f"{base}..{head}"])
    return [line.strip() for line in out.splitlines() if line.strip()]


def is_control_plane(path: str) -> bool:
    # exact file matches included via prefixes list
    for pref in CONTROL_PLANE_PREFIXES:
        if pref.endswith("/") and path.startswith(pref):
            return True
        if path == pref:
            return True
    return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--head", required=True)
    args = ap.parse_args()

    changed = git_diff_names(args.base, args.head)
    touched = [p for p in changed if is_control_plane(p)]

    strict = "true" if touched else "false"
    # GitHub Actions outputs
    print(f"STRICT_MODE={strict}")
    print(f"CONTROL_PLANE_TOUCHED_COUNT={len(touched)}")
    # keep output short, list at most 50
    for p in touched[:50]:
        print(f"CONTROL_PLANE_TOUCHED_FILE={p}")


if __name__ == "__main__":
    main()
