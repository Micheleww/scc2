#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from tools.scc.lib.utils import load_json
from tools.scc.validators.contract_validator import validate_release_record_v1

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]


def _now_id() -> str:
    return datetime.now(timezone.utc).strftime("rel-%Y%m%d-%H%M%S")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: pathlib.Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Release integration MVP: promote task artifacts to a release record + PR bundle.")
    ap.add_argument("--source-task-id", required=True, help="Task id that produced artifacts/<task>/submit.json + patch.diff")
    ap.add_argument("--release-id", default="", help="Release id (default: rel-YYYYMMDD-HHMMSS)")
    ap.add_argument("--labels", default="release", help="Comma-separated PR bundle labels")
    ap.add_argument("--out-dir", default="releases", help="Releases root directory")
    ap.add_argument("--apply-git", action="store_true", help="If repo is a git repo, apply patch+commit on new branch (delegates to pr_bundle_create)")
    ap.add_argument("--merge-to", default="", help="If set, merge branch to target (git only; ff-only).")
    args = ap.parse_args()

    task_id = str(args.source_task_id).strip()
    if not task_id:
        print("FAIL: missing source-task-id")
        return 2

    submit_path = (REPO_ROOT / "artifacts" / task_id / "submit.json").resolve()
    patch_path = (REPO_ROOT / "artifacts" / task_id / "patch.diff").resolve()
    if not submit_path.exists():
        print(f"FAIL: missing {submit_path}")
        return 2
    if not patch_path.exists():
        print(f"FAIL: missing {patch_path}")
        return 2

    # Gate: strict CI gates for the source submit must PASS (fail-closed).
    r = subprocess.run(
        ["python", "tools/scc/gates/run_ci_gates.py", "--strict", "--submit", str(submit_path.relative_to(REPO_ROOT)).replace("\\", "/")],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=240,
    )
    strict_passed = r.returncode == 0
    if not strict_passed:
        print("FAIL: source strict gates did not PASS")
        if r.stderr:
            print(r.stderr.strip()[-2000:])
        return 1

    release_id = str(args.release_id or "").strip() or _now_id()
    out_root = (REPO_ROOT / str(args.out_dir)).resolve()
    release_dir = (out_root / release_id).resolve()
    release_dir.mkdir(parents=True, exist_ok=True)

    # Create offline PR bundle for the patch.diff (deterministic).
    pr_bundle_rel = f"artifacts/{task_id}/pr_bundle.json"
    pr_cmd = [
        "python",
        "tools/scc/ops/pr_bundle_create.py",
        "--repo-root",
        str(REPO_ROOT),
        "--task-id",
        task_id,
        "--patch",
        str(patch_path.relative_to(REPO_ROOT)).replace("\\", "/"),
        "--labels",
        str(args.labels or ""),
        "--out",
        pr_bundle_rel,
    ]
    if args.apply_git:
        pr_cmd.append("--apply-git")
    if str(args.merge_to or "").strip():
        pr_cmd += ["--merge-to", str(args.merge_to).strip()]

    subprocess.run(pr_cmd, cwd=str(REPO_ROOT), check=False, capture_output=True, text=True, timeout=240)
    pr_bundle_path = (REPO_ROOT / pr_bundle_rel).resolve()
    pr_bundle_ref: Optional[str] = pr_bundle_rel if pr_bundle_path.exists() else None

    record = {
        "schema_version": "scc.release_record.v1",
        "release_id": release_id,
        "created_at": _now_iso(),
        "sources": [
            {
                "task_id": task_id,
                "submit_json": str(submit_path.relative_to(REPO_ROOT)).replace("\\", "/"),
                "patch_diff": str(patch_path.relative_to(REPO_ROOT)).replace("\\", "/"),
                "pr_bundle": pr_bundle_ref,
            }
        ],
        "artifacts": {
            "release_dir": str(release_dir.relative_to(REPO_ROOT)).replace("\\", "/") + "/",
            "release_record_json": str((release_dir / "release.json").relative_to(REPO_ROOT)).replace("\\", "/"),
        },
        "verification": {"strict_gates_passed": True, "notes": None},
        "notes": "MVP release record: offline PR bundle + strict-gated source artifacts.",
    }
    errors = validate_release_record_v1(record)
    if errors:
        print("FAIL: generated release record failed validation")
        for e in errors[:50]:
            print(f"- {e}")
        return 1
    _write_json(release_dir / "release.json", record)
    print("OK")
    print(str((release_dir / "release.json").relative_to(REPO_ROOT)).replace("\\", "/"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
