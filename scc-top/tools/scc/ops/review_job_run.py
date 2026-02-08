#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple


_REPO_ROOT = Path(__file__).resolve().parents[3]


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _date_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", errors="replace")


def _write_text(path: Path, s: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(s, encoding="utf-8", errors="replace")


def _to_repo_rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(_REPO_ROOT.resolve())).replace("\\", "/")
    except Exception:
        return str(path).replace("\\", "/")


def _run(cmd: list[str], *, env: Dict[str, str]) -> Tuple[int, str, str]:
    p = subprocess.run(cmd, cwd=str(_REPO_ROOT), env=env, capture_output=True, text=True)
    return int(p.returncode), (p.stdout or ""), (p.stderr or "")


def main() -> int:
    ap = argparse.ArgumentParser(description="Run SCC review_job with TaskCode artifacts + mvm-verdict basic.")
    ap.add_argument("--taskcode", default="REVIEW_JOB_V010")
    ap.add_argument("--area", default="control_plane")
    ap.add_argument("--tasks-root", default="artifacts/scc_tasks")
    ap.add_argument("--progress-doc", default="docs/CANONICAL/PROGRESS.md")
    ap.add_argument("--rawb-dir", default="docs/INPUTS/raw-b")
    ap.add_argument("--run-mvm", action="store_true")
    args = ap.parse_args()

    task_code = str(args.taskcode).strip() or "REVIEW_JOB_V010"
    area = str(args.area).strip() or "control_plane"

    artifacts = (_REPO_ROOT / "docs" / "REPORT" / area / "artifacts" / task_code).resolve()
    artifacts.mkdir(parents=True, exist_ok=True)

    env = dict(os.environ)
    env["TASK_CODE"] = task_code
    env["AREA"] = area
    # Avoid writing to tracked `mvm/verdict/verdict.json` on local runs.
    env["MVM_VERDICT_OUT"] = f"docs/REPORT/{area}/artifacts/{task_code}/mvm_verdict.json"

    rc, out, err = _run(
        [
            sys.executable,
            "tools/scc/review_job.py",
            "--tasks-root",
            str(args.tasks_root),
            "--progress-doc",
            str(args.progress_doc),
            "--rawb-dir",
            str(args.rawb_dir),
        ],
        env=env,
    )
    _write_text(artifacts / "review_job_stdout.txt", out)
    _write_text(artifacts / "review_job_stderr.txt", err)

    summary = {
        "ok": rc == 0,
        "task_code": task_code,
        "area": area,
        "ts_utc": _iso_now(),
        "tasks_root": str(args.tasks_root),
        "progress_doc": str(args.progress_doc),
        "rawb_dir": str(args.rawb_dir),
    }
    _write_json(artifacts / "review_job_summary.json", summary)

    evidence_paths = [
        f"docs/REPORT/{area}/artifacts/{task_code}/review_job_summary.json",
        f"docs/REPORT/{area}/artifacts/{task_code}/review_job_stdout.txt",
        f"docs/REPORT/{area}/artifacts/{task_code}/review_job_stderr.txt",
    ]
    subprocess.run(
        [
            sys.executable,
            "tools/scc/ops/evidence_triplet.py",
            "--taskcode",
            task_code,
            "--area",
            area,
            "--exit-code",
            "0" if rc == 0 else "1",
            "--notes",
            "- review_job writes canonical progress into `docs/CANONICAL/PROGRESS.md` and appends a feedback package into `docs/INPUTS/raw-b/`.",
            *sum([["--evidence", p] for p in evidence_paths], []),
        ],
        cwd=str(_REPO_ROOT),
        env=env,
    )

    if rc != 0:
        return rc

    if args.run_mvm:
        p = subprocess.run([sys.executable, "tools/ci/mvm-verdict.py", "--case", "basic"], cwd=str(_REPO_ROOT), env=env)
        if int(p.returncode) != 0:
            return int(p.returncode)
        # Attach mvm output into the same triplet so leader/auditor can find it deterministically.
        evidence_paths2 = evidence_paths + [f"docs/REPORT/{area}/artifacts/{task_code}/mvm_verdict.json"]
        subprocess.run(
            [
                sys.executable,
                "tools/scc/ops/evidence_triplet.py",
                "--taskcode",
                task_code,
                "--area",
                area,
                "--exit-code",
                "0",
                "--notes",
                "- review_job completed and mvm-verdict basic passed.",
                *sum([["--evidence", p] for p in evidence_paths2], []),
            ],
            cwd=str(_REPO_ROOT),
            env=env,
        )
        return 0

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
