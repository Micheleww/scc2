#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Local smoke test: SCC patch pipeline preview + apply (in a temp git repo under artifacts/).

Notes:
- Uses git apply under a throwaway repo so it won't touch the main workspace.
- Requires git in PATH.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path


def run(argv: list[str], cwd: Path) -> None:
    p = subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"cmd failed: {argv}\nstdout:\n{p.stdout}\nstderr:\n{p.stderr}")


def main() -> int:
    os.environ["PYTHONIOENCODING"] = "utf-8"

    repo_root = Path(__file__).resolve().parent.parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from tools.scc.capabilities.patch_pipeline import apply_patch_text, preview_patch

    tmp = (repo_root / "artifacts" / "patch_smoke_repo").resolve()
    if tmp.exists():
        shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True, exist_ok=True)

    run(["git", "init"], cwd=tmp)
    (tmp / "a.txt").write_text("old\n", encoding="utf-8")

    patch = (
        "diff --git a/a.txt b/a.txt\n"
        "--- a/a.txt\n"
        "+++ b/a.txt\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
    )

    prev = preview_patch(repo_path=tmp, patch_text=patch)
    if not prev.files or prev.total_additions < 1 or prev.total_deletions < 1:
        raise RuntimeError("preview stats unexpected")

    # Check-only should work without enabling apply gate.
    chk = apply_patch_text(repo_path=tmp, patch_text=patch, check_only=True)
    if not chk.ok or chk.exit_code != 0:
        raise RuntimeError("check_only failed")

    # Apply requires gate.
    os.environ["SCC_PATCH_APPLY_ENABLED"] = "true"
    res = apply_patch_text(repo_path=tmp, patch_text=patch, check_only=False)
    if not res.ok:
        raise RuntimeError(f"apply failed: {res.error}")

    content = (tmp / "a.txt").read_text(encoding="utf-8")
    if "new" not in content:
        raise RuntimeError("expected patched content")

    print("PATCH_PIPELINE_SMOKE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
