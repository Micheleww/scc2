#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple


REPO_ROOT = Path(__file__).resolve().parents[3]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", errors="replace")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", errors="replace")


def _repo_rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve())).replace("\\", "/")
    except Exception:
        return str(path).replace("\\", "/")


def _is_placeholder(text: str) -> Tuple[bool, str]:
    """
    Detect quarantine placeholder files that were moved to isolated_observatory/.
    These files are markdown-ish but have .py extension, which breaks pytest collection.
    """
    head = "\n".join((text or "").splitlines()[:8]).strip()
    if not head:
        return False, ""
    if "索引占位文件" in head and "原始文件已迁移到隔离观察区" in text:
        # try extract original path for message
        m = re.search(r"存储位置:\\s*(.+)$", text, flags=re.MULTILINE)
        orig = (m.group(1).strip() if m else "").replace("\\", "/")
        return True, orig
    return False, ""


def _render_skip_module(*, rel_path: str, original: str) -> str:
    msg = f"placeholder test file: moved to isolated_observatory ({original})" if original else "placeholder test file: moved to isolated_observatory"
    lines = [
        "# Auto-sanitized placeholder test file (SCC).",
        f"# path: {rel_path}",
        f"# note: {msg}",
        "",
        "import pytest",
        "",
        f'pytest.skip("{msg}", allow_module_level=True)',
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Sanitize quarantined placeholder *.py files under tests/ so pytest collection is deterministic.")
    ap.add_argument("--taskcode", default="PYTEST_PLACEHOLDER_SANITIZE_V010")
    ap.add_argument("--area", default=os.environ.get("AREA", "control_plane"))
    ap.add_argument("--tests-root", default="tests")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    taskcode = str(args.taskcode).strip() or "PYTEST_PLACEHOLDER_SANITIZE_V010"
    area = str(args.area).strip() or "control_plane"

    tests_root = Path(str(args.tests_root))
    if not tests_root.is_absolute():
        tests_root = (REPO_ROOT / tests_root).resolve()
    if not tests_root.exists():
        print(json.dumps({"ok": False, "error": "missing_tests_root", "path": _repo_rel(tests_root)}, ensure_ascii=False))
        return 2

    changed: List[str] = []
    scanned = 0
    placeholders = 0
    for p in tests_root.rglob("*.py"):
        if not p.is_file():
            continue
        scanned += 1
        rel = _repo_rel(p)
        txt = _read_text(p)
        ok, orig = _is_placeholder(txt)
        if not ok:
            continue
        placeholders += 1
        new_txt = _render_skip_module(rel_path=rel, original=orig)
        if txt.strip() == new_txt.strip():
            continue
        if not args.dry_run:
            _write_text(p, new_txt)
        changed.append(rel)

    artifacts_dir = (REPO_ROOT / "docs" / "REPORT" / area / "artifacts" / taskcode).resolve()
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "ok": True,
        "ts_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "taskcode": taskcode,
        "area": area,
        "tests_root": _repo_rel(tests_root),
        "scanned_py_files": scanned,
        "placeholder_detected": placeholders,
        "changed": len(changed),
        "dry_run": bool(args.dry_run),
        "changed_paths": changed[:500],
    }
    _write_json(artifacts_dir / "pytest_placeholder_sanitize_summary.json", summary)

    subprocess.run(
        [
            sys.executable,
            "tools/scc/ops/evidence_triplet.py",
            "--taskcode",
            taskcode,
            "--area",
            area,
            "--exit-code",
            "0",
            "--notes",
            "- Converts quarantine placeholder `tests/**/*.py` files into `pytest.skip(...)` modules so pytest collection is deterministic.",
            "--evidence",
            f"docs/REPORT/{area}/artifacts/{taskcode}/pytest_placeholder_sanitize_summary.json",
        ],
        cwd=str(REPO_ROOT),
        env=dict(os.environ),
    )

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

