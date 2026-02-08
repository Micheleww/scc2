from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _default_patterns() -> List[str]:
    # Conservative: only clearly-generated artifacts and common caches.
    return [
        "artifacts/",
        "site/",
        "__pycache__/",
        ".pytest_cache/",
        ".ruff_cache/",
        "*.log",
        "*.tmp",
        ".venv/",
        "node_modules/",
    ]


def _scc_focus_patterns() -> List[str]:
    """
    Reduce workspace noise for SCC-focused engineering:
    - Keep core code paths visible
    - Hide large report/prompt dumps and extracted repos from git status

    This is local-only (.git/info/exclude) and reversible.
    """
    return [
        # Large doc/report dumps
        "docs/REPORT/",
        "docs/TASKS/",
        "docs/TEST/",
        "docs/log/",
        # Prompt/evidence dumps
        "taskhub/",
        "reports/",
        # Extracted/duplicated repos
        "frequi-main/",
        "freqtrade-strategies-main/",
        "ai_collaboration/",
        "cursor-cli-windows/",
        "shoucuo cursor/",
    ]


def _append_unique(path: Path, lines: List[str]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = set()
    if path.exists():
        try:
            for ln in path.read_text(encoding="utf-8", errors="replace").splitlines():
                existing.add(ln.strip())
        except Exception:
            existing = set()
    out = []
    added = 0
    for ln in lines:
        s = ln.strip()
        if not s or s in existing:
            continue
        existing.add(s)
        out.append(s)
        added += 1
    if added <= 0:
        return 0
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    header = [f"", f"# SCC local exclude ({stamp})"]
    with path.open("a", encoding="utf-8", errors="replace") as f:
        for h in header:
            f.write(h + "\n")
        for ln in out:
            f.write(ln + "\n")
    return added


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=str(_repo_root()))
    ap.add_argument("--include-root-binaries", action="store_true", help="Also exclude *.zip/*.7z/*.msi/*.exe at repo root.")
    ap.add_argument("--scc-focus", action="store_true", help="Add extra patterns to reduce SCC workspace noise.")
    args = ap.parse_args()

    repo_root = Path(args.repo_root).resolve()
    exclude_file = (repo_root / ".git" / "info" / "exclude").resolve()
    patterns = list(_default_patterns())
    if args.include_root_binaries:
        patterns.extend(["*.zip", "*.7z", "*.msi", "*.exe"])
    if args.scc_focus:
        patterns.extend(_scc_focus_patterns())
    added = _append_unique(exclude_file, patterns)
    print(f"[git_local_exclude] file={exclude_file}")
    print(f"[git_local_exclude] added={added}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
