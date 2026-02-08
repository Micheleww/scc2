#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UNKNOWN_SCHEMA_351_MIGRATION_V010 — deterministic DLQ policy runner.

Goal:
- Identify task ledger entries with schema "unknown_schema" (missing request.task.goal and request.contract_ref).
- Emit an append-only DLQ queue file for secretary/re-intake (no fabricated goals).
- Emit a report under docs/REPORT/<area>/.

Non-goals:
- Do NOT modify existing task records by default.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace") or "{}")
    except Exception:
        return {}


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _date_utc() -> str:
    return time.strftime("%Y%m%d", time.gmtime())


def _stamp_utc() -> str:
    return time.strftime("%Y%m%d-%H%M%SZ", time.gmtime())


def _classify(rec: dict) -> str:
    req = rec.get("request") if isinstance(rec.get("request"), dict) else {}
    if str(req.get("contract_ref") or "").strip():
        return "contract_task"
    task = req.get("task") if isinstance(req.get("task"), dict) else {}
    if str(task.get("goal") or "").strip():
        return "legacy_orchestrator_task"
    return "unknown_schema"


def _latest_task_dirs(tasks_root: Path, *, limit_latest: int) -> List[Path]:
    scored: List[Tuple[float, Path]] = []
    for d in tasks_root.iterdir():
        if not d.is_dir():
            continue
        tj = d / "task.json"
        if not tj.exists():
            continue
        try:
            scored.append((float(tj.stat().st_mtime), d))
        except Exception:
            scored.append((0.0, d))
    scored.sort(key=lambda t: t[0], reverse=True)
    dirs = [d for _, d in scored[: max(1, int(limit_latest or 800))]]
    return dirs


def _append_jsonl(path: Path, rows: List[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_ids: set[str] = set()
    if path.exists():
        try:
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    j = json.loads(line)
                    tid = str(j.get("task_id") or "").strip()
                    if tid:
                        existing_ids.add(tid)
                except Exception:
                    continue
        except Exception:
            existing_ids = set()
    with path.open("a", encoding="utf-8", errors="replace") as f:
        for r in rows:
            tid = str(r.get("task_id") or "").strip()
            if tid and tid in existing_ids:
                continue
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


@dataclass(frozen=True)
class UnknownRow:
    task_id: str
    task_dir: str
    created_utc: str
    updated_utc: str
    source: str
    evidence_refs: List[str]


def main() -> int:
    ap = argparse.ArgumentParser(description="unknown_schema(351) migration runner (deterministic).")
    ap.add_argument("--area", default="control_plane")
    ap.add_argument("--taskcode", default="UNKNOWN_SCHEMA_351_MIGRATION_V010")
    ap.add_argument("--tasks-root", default="artifacts/scc_tasks")
    ap.add_argument("--limit-latest", type=int, default=2000)
    ap.add_argument("--emit-report", action="store_true", default=True)
    ap.add_argument("--dlq-out", default="docs/DERIVED/dlq/unknown_schema_tasks__v0.1.0.jsonl")
    args = ap.parse_args()

    repo_root = _repo_root()
    area = str(args.area).strip() or "control_plane"
    taskcode = str(args.taskcode).strip() or "UNKNOWN_SCHEMA_351_MIGRATION_V010"

    tasks_root = Path(args.tasks_root)
    if not tasks_root.is_absolute():
        tasks_root = (repo_root / tasks_root).resolve()
    if not tasks_root.exists():
        print(json.dumps({"ok": False, "error": "missing_tasks_root", "tasks_root": str(tasks_root)}, ensure_ascii=False, indent=2))
        return 2

    dirs = _latest_task_dirs(tasks_root, limit_latest=int(args.limit_latest or 2000))
    unknown: List[UnknownRow] = []

    for d in dirs:
        rec = _read_json(d / "task.json")
        if _classify(rec) != "unknown_schema":
            continue
        task_id = str(rec.get("task_id") or d.name)
        created_utc = str(rec.get("created_utc") or "")
        updated_utc = str(rec.get("updated_utc") or "")
        req = rec.get("request") if isinstance(rec.get("request"), dict) else {}
        source = str(req.get("source") or "")
        evidence_refs = req.get("evidence_refs") if isinstance(req.get("evidence_refs"), list) else []
        evidence_refs = [str(x).strip() for x in evidence_refs if str(x).strip()]
        unknown.append(
            UnknownRow(
                task_id=task_id,
                task_dir=str(d.relative_to(repo_root)).replace("\\", "/"),
                created_utc=created_utc,
                updated_utc=updated_utc,
                source=source,
                evidence_refs=evidence_refs,
            )
        )

    # Append-only DLQ queue (secretary consumes this).
    dlq_path = Path(args.dlq_out)
    if not dlq_path.is_absolute():
        dlq_path = (repo_root / dlq_path).resolve()
    dlq_rows = [
        {
            "schema_version": "v0.1.0",
            "kind": "unknown_schema_dlq",
            "ts_utc": _utc_now(),
            "reason": "missing_goal_and_contract_ref",
            "task_id": r.task_id,
            "task_dir": r.task_dir,
            "evidence_refs": r.evidence_refs,
        }
        for r in unknown
    ]
    if dlq_rows:
        _append_jsonl(dlq_path, dlq_rows)

    payload: Dict[str, Any] = {
        "ok": True,
        "generated_at_utc": _utc_now(),
        "schema_version": "v0.1.0",
        "area": area,
        "taskcode": taskcode,
        "tasks_root": str(tasks_root.relative_to(repo_root)).replace("\\", "/"),
        "limit_latest": int(args.limit_latest or 0),
        "unknown_schema_count": len(unknown),
        "dlq_out": str(dlq_path.relative_to(repo_root)).replace("\\", "/"),
        "rows": [r.__dict__ for r in unknown[:2000]],
    }

    if args.emit_report:
        out_md = (repo_root / "docs" / "REPORT" / area / f"REPORT__{taskcode}__{_date_utc()}.md").resolve()
        out_json = (repo_root / "docs" / "REPORT" / area / "artifacts" / f"{taskcode}__{_stamp_utc()}" / "unknown_schema_tasks.json").resolve()
        out_md.parent.mkdir(parents=True, exist_ok=True)
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", errors="replace")

        lines: List[str] = []
        lines.append(f"# Unknown Schema Migration — {taskcode} (v0.1.0)")
        lines.append("")
        lines.append(f"- generated_at_utc: `{payload['generated_at_utc']}`")
        lines.append(f"- tasks_root: `{payload['tasks_root']}`")
        lines.append(f"- limit_latest: `{payload['limit_latest']}`")
        lines.append(f"- unknown_schema_count: `{payload['unknown_schema_count']}`")
        lines.append(f"- dlq_out (append-only): `{payload['dlq_out']}`")
        lines.append(f"- evidence_json: `{str(out_json.relative_to(repo_root)).replace('\\\\','/')}`")
        lines.append("")
        lines.append("## Policy (non-fabrication)")
        lines.append("- These tasks are NOT contractized because they lack `request.task.goal` and `request.contract_ref`.")
        lines.append("- Next step is Secretary re-intake: compile Goal Brief from evidence refs, then re-derive task_tree and contractize.")
        lines.append("")
        lines.append("## Sample rows")
        lines.append("| task_id | source | created_utc | evidence_refs_count | task_dir |")
        lines.append("|---|---|---|---:|---|")
        for r in unknown[: min(60, len(unknown))]:
            lines.append(f"| {r.task_id} | {r.source} | {r.created_utc} | {len(r.evidence_refs)} | {r.task_dir} |")
        lines.append("")
        out_md.write_text("\n".join(lines).strip() + "\n", encoding="utf-8", errors="replace")
        print(str(out_md))
        print(str(out_json))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
