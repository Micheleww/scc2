#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import List, Tuple


REPO = Path(__file__).resolve().parents[3]


def _git_ls_files(repo: Path) -> List[str]:
    r = subprocess.run(["git", "ls-files"], cwd=str(repo), text=True, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"git ls-files failed: {r.stderr.strip()}")
    return [ln.strip() for ln in (r.stdout or "").splitlines() if ln.strip()]


def _read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def main() -> int:
    rx = re.compile(r"\bshell\s*=\s*True\b")
    bad: List[Tuple[str, int, str]] = []
    for rel in _git_ls_files(REPO):
        if not rel.endswith(".py"):
            continue
        if rel.startswith("docs/") or rel.startswith("scc-top/docs/"):
            continue
        text = _read_text((REPO / rel).resolve())
        for i, line in enumerate(text.splitlines(), start=1):
            if rx.search(line):
                bad.append((rel, i, line.strip()))

    if bad:
        print("FAIL: shell=True found (command injection risk). Use argv list + shell=False.")
        for rel, ln, src in bad[:200]:
            print(f"  {rel}:{ln}: {src}")
        if len(bad) > 200:
            print(f"  ... and {len(bad) - 200} more")
        return 2

    print("OK: no shell=True found in tracked python files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

