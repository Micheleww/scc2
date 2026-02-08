#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


_REPO_ROOT = Path(__file__).resolve().parents[3]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8", errors="replace") or "{}")


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", errors="replace")


def _iter_tasks(tree: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
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
                if isinstance(t, dict):
                    out.append(t)
    return out


@dataclass
class TaskRecord:
    task_id: str
    created_utc: str
    updated_utc: str
    status: str  # pending|running|done|failed|canceled|await_user|dlq
    request: Dict[str, Any]
    run_id: Optional[str] = None
    exit_code: Optional[int] = None
    verdict: Optional[str] = None  # PASS|FAIL
    out_dir: Optional[str] = None
    selftest_log: Optional[str] = None
    report_md: Optional[str] = None
    evidence_dir: Optional[str] = None
    error: Optional[str] = None


def _task_dir(tasks_root: Path, task_id: str) -> Path:
    return (tasks_root / str(task_id)).resolve()


def _task_json_path(tasks_root: Path, task_id: str) -> Path:
    return _task_dir(tasks_root, task_id) / "task.json"


def main() -> int:
    ap = argparse.ArgumentParser(description="Sync docs/DERIVED/task_tree.json tasks into artifacts/scc_tasks (index/ledger).")
    ap.add_argument("--task-tree", default="docs/DERIVED/task_tree.json")
    ap.add_argument("--tasks-root", default="artifacts/scc_tasks")
    ap.add_argument("--only-missing", action="store_true", help="Only create missing task.json; do not touch existing records.")
    ap.add_argument("--status", default="pending", help="Initial status for newly created tasks (default: pending).")
    ap.add_argument("--source", default="web_chat", help="Request.source for newly created tasks.")
    ap.add_argument("--emit-report", action="store_true")
    ap.add_argument("--taskcode", default="TASKTREE_SYNC_V010")
    ap.add_argument("--area", default="control_plane")
    args = ap.parse_args()

    tree_path = (Path(args.task_tree) if Path(args.task_tree).is_absolute() else (_REPO_ROOT / args.task_tree)).resolve()
    if not tree_path.exists():
        print(json.dumps({"ok": False, "error": "missing_task_tree", "path": str(tree_path)}, ensure_ascii=False))
        return 2

    tasks_root = (Path(args.tasks_root) if Path(args.tasks_root).is_absolute() else (_REPO_ROOT / args.tasks_root)).resolve()
    tasks_root.mkdir(parents=True, exist_ok=True)

    tree = _read_json(tree_path)
    tasks = _iter_tasks(tree)

    created = 0
    skipped = 0
    updated = 0

    now = _utc_now_iso()
    for t in tasks:
        task_id = str(t.get("task_id") or "").strip()
        if not task_id:
            continue
        contract_ref = str(t.get("contract_ref") or "").strip()
        evidence_refs = t.get("evidence_refs") if isinstance(t.get("evidence_refs"), list) else []

        p = _task_json_path(tasks_root, task_id)
        if p.exists():
            if args.only_missing:
                skipped += 1
                continue
            try:
                existing = _read_json(p)
            except Exception:
                existing = {}
            # Best-effort: keep existing status/verdict, but ensure request links exist.
            req = existing.get("request") if isinstance(existing.get("request"), dict) else {}
            req.setdefault("source", str(args.source))
            req.setdefault("contract_ref", contract_ref)
            if evidence_refs:
                req.setdefault("evidence_refs", evidence_refs)
            existing["request"] = req
            existing["updated_utc"] = now
            _write_json(p, existing)
            updated += 1
            continue

        rec = TaskRecord(
            task_id=task_id,
            created_utc=now,
            updated_utc=now,
            status=str(args.status).strip() or "pending",
            request={"source": str(args.source), "contract_ref": contract_ref, "evidence_refs": evidence_refs},
        )
        p.parent.mkdir(parents=True, exist_ok=True)
        _write_json(p, asdict(rec))
        created += 1

    result = {
        "ok": True,
        "task_tree": str(tree_path.relative_to(_REPO_ROOT)).replace("\\", "/"),
        "tasks_root": str(tasks_root.relative_to(_REPO_ROOT)).replace("\\", "/"),
        "tasks_in_tree": len(tasks),
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "ts_utc": now,
    }

    if args.emit_report:
        task_code = str(args.taskcode).strip() or "TASKTREE_SYNC_V010"
        area = str(args.area).strip() or "control_plane"
        artifacts = (_REPO_ROOT / "docs" / "REPORT" / area / "artifacts" / task_code).resolve()
        artifacts.mkdir(parents=True, exist_ok=True)
        _write_json(artifacts / "tasktree_sync_summary.json", result)
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
                "- This job creates/updates `artifacts/scc_tasks/<task_id>/task.json` records from derived task_tree.",
                "--evidence",
                f"docs/REPORT/{area}/artifacts/{task_code}/tasktree_sync_summary.json",
            ],
            cwd=str(_REPO_ROOT),
            env=dict(os.environ),
        )

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
