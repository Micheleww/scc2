#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple


_REPO_ROOT = Path(__file__).resolve().parents[3]


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8", errors="replace") or "{}")


def _iter_task_ids(tree: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    epics = tree.get("epics") if isinstance(tree.get("epics"), list) else []
    for e in epics:
        if not isinstance(e, dict):
            continue
        caps = e.get("capabilities") if isinstance(e.get("capabilities"), list) else []
        for c in caps:
            if not isinstance(c, dict):
                continue
            tasks = c.get("tasks") if isinstance(c.get("tasks"), list) else []
            for t in tasks:
                if not isinstance(t, dict):
                    continue
                tid = str(t.get("task_id") or "").strip()
                if tid:
                    out.append(tid)
    # stable de-dupe
    seen = set()
    return [x for x in out if not (x in seen or seen.add(x))]


def _run(args: List[str], *, env: Dict[str, str]) -> Tuple[int, str]:
    p = subprocess.run(args, cwd=str(_REPO_ROOT), env=env)
    return int(p.returncode), " ".join(args)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="CONTRACTIZE_PIPELINE (v0.1.0): task_tree -> contracts -> harden -> sync -> (optional) run contract checks (deterministic)."
    )
    ap.add_argument("--task-tree", default="docs/DERIVED/task_tree.json")
    ap.add_argument("--contracts-dir", default="docs/ssot/04_contracts/generated")
    ap.add_argument("--tasks-root", default="artifacts/scc_tasks")
    ap.add_argument("--area", default="control_plane")
    ap.add_argument("--taskcode", default="CONTRACTIZE_PIPELINE_V010")
    ap.add_argument("--limit", type=int, default=10, help="How many tasks/contracts to process for this run (default: 10).")
    ap.add_argument("--sample-run", type=int, default=2, help="How many tasks to run via run_contract_task.py after harden (default: 2).")
    ap.add_argument("--run-mvm", action="store_true", help="Run mvm-verdict basic at the end (requires guard/evidence setup).")
    args = ap.parse_args()

    area = str(args.area).strip() or "control_plane"
    taskcode = str(args.taskcode).strip() or "CONTRACTIZE_PIPELINE_V010"
    limit = int(args.limit or 0)
    sample_run = max(0, int(args.sample_run or 0))

    env = dict(os.environ)
    env["AREA"] = area
    env["TASK_CODE"] = taskcode

    tree_path = Path(str(args.task_tree))
    if not tree_path.is_absolute():
        tree_path = (_REPO_ROOT / tree_path).resolve()
    if not tree_path.exists():
        subprocess.run(
            [
                sys.executable,
                "tools/scc/ops/evidence_triplet.py",
                "--taskcode",
                taskcode,
                "--area",
                area,
                "--exit-code",
                "1",
                "--notes",
                f"- error: missing task_tree\\n- path: `{str(tree_path).replace('\\\\','/')}`",
            ],
            cwd=str(_REPO_ROOT),
            env=env,
        )
        return 2

    tree = _read_json(tree_path)
    all_task_ids = _iter_task_ids(tree)
    picked_task_ids = all_task_ids[:limit] if limit > 0 else all_task_ids

    # Subtask codes (each shows up in leader board and has its own triplet)
    sync_pre = f"{taskcode}__SYNC_PRE"
    sync_post = f"{taskcode}__SYNC_POST"
    harden_code = f"{taskcode}__HARDEN"

    executed: List[Dict[str, Any]] = []
    rc_all = 0

    # 1) Sync task_tree -> artifacts/scc_tasks (contract_ref may be empty at this stage)
    rc, cmd = _run(
        [
            sys.executable,
            "tools/scc/ops/sync_task_tree_to_scc_tasks.py",
            "--task-tree",
            str(tree_path),
            "--tasks-root",
            str(args.tasks_root),
            "--emit-report",
            "--taskcode",
            sync_pre,
            "--area",
            area,
        ],
        env=env,
    )
    executed.append({"step": "sync_pre", "rc": rc, "cmd": cmd})
    rc_all = rc_all or rc

    # 2) Contractize (mint OIDs + write per-task contract json) and optionally write contract_ref back into task_tree.
    rc, cmd = _run(
        [
            sys.executable,
            "tools/scc/ops/contractize_job.py",
            "--task-tree",
            str(tree_path),
            "--out-dir",
            str(args.contracts_dir),
            "--area",
            area,
            "--taskcode",
            taskcode,
            "--update-task-tree",
            "--limit",
            str(limit if limit > 0 else 0),
        ],
        env=env,
    )
    executed.append({"step": "contractize", "rc": rc, "cmd": cmd})
    rc_all = rc_all or rc

    # 3) Re-sync so each task.json gets the updated contract_ref.
    rc, cmd = _run(
        [
            sys.executable,
            "tools/scc/ops/sync_task_tree_to_scc_tasks.py",
            "--task-tree",
            str(tree_path),
            "--tasks-root",
            str(args.tasks_root),
            "--emit-report",
            "--taskcode",
            sync_post,
            "--area",
            area,
        ],
        env=env,
    )
    executed.append({"step": "sync_post", "rc": rc, "cmd": cmd})
    rc_all = rc_all or rc

    # 4) Harden contracts (deterministic) so per-task contracts become executable.
    rc, cmd = _run(
        [
            sys.executable,
            "tools/scc/ops/contract_harden_job.py",
            "--area",
            area,
            "--taskcode",
            harden_code,
            "--task-tree",
            str(tree_path),
            "--limit",
            str(limit if limit > 0 else 0),
            "--include-non-tbd",
        ],
        env=env,
    )
    executed.append({"step": "harden", "rc": rc, "cmd": cmd})
    rc_all = rc_all or rc

    # 5) Optional: run a few tasks locally (deterministic) via artifacts/scc_tasks records.
    ran: List[Dict[str, Any]] = []
    for tid in picked_task_ids[:sample_run]:
        rc, cmd = _run(
            [
                sys.executable,
                "tools/scc/ops/run_contract_task.py",
                "--task-id",
                tid,
                "--tasks-root",
                str(args.tasks_root),
                "--area",
                area,
            ],
            env=env,
        )
        ran.append({"task_id": tid, "rc": rc, "cmd": cmd})
        rc_all = rc_all or rc

    artifacts_dir = (_REPO_ROOT / "docs" / "REPORT" / area / "artifacts" / taskcode).resolve()
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    pipeline_summary = {
        "schema_version": "v0.1.0",
        "taskcode": taskcode,
        "area": area,
        "limit": limit,
        "sample_run": sample_run,
        "tasks_considered": len(all_task_ids),
        "tasks_picked": len(picked_task_ids),
        "executed_steps": executed,
        "sample_task_runs": ran,
    }
    (artifacts_dir / "contractize_pipeline_summary.json").write_text(
        json.dumps(pipeline_summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        errors="replace",
    )

    evidence = [
        f"docs/REPORT/{area}/artifacts/{taskcode}/contractize_pipeline_summary.json",
        f"docs/REPORT/{area}/REPORT__{sync_pre}__{time.strftime('%Y%m%d', time.gmtime())}.md",
        f"docs/REPORT/{area}/REPORT__{sync_post}__{time.strftime('%Y%m%d', time.gmtime())}.md",
        f"docs/REPORT/{area}/REPORT__{harden_code}__{time.strftime('%Y%m%d', time.gmtime())}.md",
    ]
    # Create/refresh triplet for pipeline taskcode itself.
    subprocess.run(
        [
            sys.executable,
            "tools/scc/ops/evidence_triplet.py",
            "--taskcode",
            taskcode,
            "--area",
            area,
            "--exit-code",
            "0" if rc_all == 0 else "1",
            "--notes",
            "\n".join(
                [
                    f"- steps: sync_pre → contractize → sync_post → harden → sample_run({sample_run})",
                    f"- subtask codes: `{sync_pre}`, `{sync_post}`, `{harden_code}`",
                    "- note: contractize requires SCC_OID_PG_DSN (and PGPASSWORD if needed) to mint OIDs into PostgreSQL.",
                ]
            ),
            *sum([["--evidence", p] for p in evidence], []),
        ],
        cwd=str(_REPO_ROOT),
        env=env,
    )

    if args.run_mvm:
        p = subprocess.run([sys.executable, "tools/ci/mvm-verdict.py", "--case", "basic"], cwd=str(_REPO_ROOT), env=env)
        return int(p.returncode)

    return 0 if rc_all == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
