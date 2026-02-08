from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import List


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _git_ls_files(repo_root: Path) -> List[str]:
    r = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=str(repo_root),
        capture_output=True,
        timeout=60,
    )
    raw = r.stdout or b""
    out = []
    for part in raw.split(b"\x00"):
        if not part:
            continue
        try:
            out.append(part.decode("utf-8", errors="replace"))
        except Exception:
            continue
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pattern", help="Regex pattern to search (rg syntax).")
    ap.add_argument("--repo-root", default=str(_repo_root()))
    ap.add_argument("--hidden", action="store_true")
    ap.add_argument("--iglob", action="append", default=[])
    args = ap.parse_args()

    repo_root = Path(args.repo_root).resolve()
    files = _git_ls_files(repo_root)
    if not files:
        print("[rg_tracked] no git-tracked files found")
        return 2

    cmd = ["rg", "-n", args.pattern]
    if args.hidden:
        cmd.append("--hidden")
    for g in args.iglob or []:
        cmd.extend(["--iglob", str(g)])
    cmd.append("--")
    cmd.extend(files)

    # Run rg with a capped environment; output is streamed.
    env = dict(os.environ)
    p = subprocess.run(cmd, cwd=str(repo_root), env=env)
    return int(p.returncode)


if __name__ == "__main__":
    raise SystemExit(main())

