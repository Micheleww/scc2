#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Tuple


REPO = Path(__file__).resolve().parents[3]


def _git_ls_files(repo: Path) -> List[str]:
    r = subprocess.run(["git", "ls-files"], cwd=str(repo), text=True, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"git ls-files failed: {r.stderr.strip()}")
    return [ln.strip() for ln in (r.stdout or "").splitlines() if ln.strip()]


def _should_scan(rel: str) -> bool:
    p = rel.replace("\\", "/")
    if p.startswith("docs/") or p.startswith("scc-top/docs/"):
        return False
    if p.startswith("tools/scc/selftest/selfcheck_no_"):
        return False
    if p.endswith(".md") or p.endswith(".jsonl") or p.endswith(".log") or p.endswith(".env"):
        return False
    # Known archives/snapshots often contain historical absolute paths.
    if "/archive/" in p or "/archive_" in p or "/snapshot/" in p:
        return False
    exts = (".py", ".mjs", ".js", ".ts", ".ps1", ".cmd", ".bat", ".sh")
    return p.endswith(exts)


def _read_text(abs_path: Path) -> str:
    try:
        return abs_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _find_hits(rel: str, text: str) -> List[Tuple[int, str]]:
    # Only flag truly hard-coded workspace/user paths in code.
    patterns = [
        r"C:/scc\b",
        r"C:\\\\scc\\\\",
        r"C:\\Users\\",
        r"/home/user/scc2\b",
    ]
    rx = re.compile("|".join(patterns))
    hits: List[Tuple[int, str]] = []
    for i, line in enumerate(text.splitlines(), start=1):
        s = line.strip()
        # Ignore comment-only lines across common languages.
        if s.startswith("#") or s.startswith("//") or s.startswith("/*") or s.startswith("*"):
            continue
        if rx.search(line):
            hits.append((i, line.strip()))
    return hits


def main() -> int:
    files = _git_ls_files(REPO)
    bad: List[str] = []
    for rel in files:
        if not _should_scan(rel):
            continue
        abs_path = (REPO / rel).resolve()
        text = _read_text(abs_path)
        hits = _find_hits(rel, text)
        for ln, src in hits:
            bad.append(f"{rel}:{ln}: {src}")

    if bad:
        print("FAIL: hard-coded absolute paths found (set SCC_REPO_ROOT/EXEC_LOG_DIR/BOARD_DIR or compute relative repo root):")
        for row in bad[:200]:
            print("  " + row)
        if len(bad) > 200:
            print(f"  ... and {len(bad) - 200} more")
        return 2

    print("OK: no hard-coded absolute paths detected in scanned code files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
