#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Task Ledger Audit (v0.1.0) — deterministic.

Purpose:
- Audit artifacts/scc_tasks and classify task record schemas:
  - contract_task: request.contract_ref exists (runnable by run_contract_task.py)
  - legacy_orchestrator_task: request.task.goal exists (non-contract task)
  - unknown_schema: neither
- Summarize verdict/status distribution per class.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace") or "{}")
    except Exception:
        return {}


def _date_utc() -> str:
    return time.strftime("%Y%m%d", time.gmtime())


def _stamp_utc() -> str:
    return time.strftime("%Y%m%d-%H%M%SZ", time.gmtime())


def _count(values: List[str]) -> List[Tuple[str, int]]:
    m: Dict[str, int] = {}
    for v in values:
        vv = (v or "").strip()
        if not vv:
            continue
        m[vv] = m.get(vv, 0) + 1
    return sorted(m.items(), key=lambda kv: (-kv[1], kv[0]))


def _classify(rec: dict) -> str:
    req = rec.get("request") if isinstance(rec.get("request"), dict) else {}
    if str(req.get("contract_ref") or "").strip():
        return "contract_task"
    task = req.get("task") if isinstance(req.get("task"), dict) else {}
    if str(task.get("goal") or "").strip():
        return "legacy_orchestrator_task"
    return "unknown_schema"


def main() -> int:
    ap = argparse.ArgumentParser(description="Deterministic task ledger audit.")
    ap.add_argument("--area", default="control_plane")
    ap.add_argument("--taskcode", default="TASK_LEDGER_AUDIT_V010")
    ap.add_argument("--tasks-root", default="artifacts/scc_tasks")
    ap.add_argument("--limit-latest", type=int, default=800)
    args = ap.parse_args()

    repo_root = _repo_root()
    area = str(args.area).strip() or "control_plane"
    taskcode = str(args.taskcode).strip() or "TASK_LEDGER_AUDIT_V010"

    tasks_root = Path(args.tasks_root)
    if not tasks_root.is_absolute():
        tasks_root = (repo_root / tasks_root).resolve()
    if not tasks_root.exists():
        print(json.dumps({"ok": False, "error": "missing_tasks_root", "tasks_root": str(tasks_root)}, ensure_ascii=False))
        return 2

    # latest by mtime of task.json
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
    dirs = [d for _, d in scored[: max(1, int(args.limit_latest or 800))]]

    rows: List[dict] = []
    cls_list: List[str] = []
    verdicts: Dict[str, List[str]] = {"contract_task": [], "legacy_orchestrator_task": [], "unknown_schema": []}
    statuses: Dict[str, List[str]] = {"contract_task": [], "legacy_orchestrator_task": [], "unknown_schema": []}

    for d in dirs:
        rec = _read_json(d / "task.json")
        task_id = str(rec.get("task_id") or d.name)
        cls = _classify(rec)
        verdict = str(rec.get("verdict") or "").strip().upper() or "UNKNOWN"
        status = str(rec.get("status") or "").strip() or "unknown"
        cls_list.append(cls)
        verdicts[cls].append(verdict)
        statuses[cls].append(status)
        rows.append(
            {
                "task_id": task_id,
                "class": cls,
                "verdict": verdict,
                "status": status,
                "task_dir": str(d.relative_to(repo_root)).replace("\\", "/"),
            }
        )

    summary = {
        "latest_scanned": len(rows),
        "by_class": [{"class": k, "count": v} for k, v in _count(cls_list)],
        "by_class_verdict": {k: [{"verdict": vv, "count": c} for vv, c in _count(verdicts[k])] for k in verdicts.keys()},
        "by_class_status": {k: [{"status": vv, "count": c} for vv, c in _count(statuses[k])] for k in statuses.keys()},
    }

    payload = {
        "ok": True,
        "schema_version": "v0.1.0",
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "area": area,
        "taskcode": taskcode,
        "tasks_root": str(tasks_root.relative_to(repo_root)).replace("\\", "/"),
        "limit_latest": int(args.limit_latest),
        "summary": summary,
        "rows": rows,
    }

    out_md = (repo_root / "docs" / "REPORT" / area / f"REPORT__{taskcode}__{_date_utc()}.md").resolve()
    out_json = (
        repo_root / "docs" / "REPORT" / area / "artifacts" / f"{taskcode}__{_stamp_utc()}" / "task_ledger_audit.json"
    ).resolve()
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", errors="replace")

    lines: List[str] = []
    lines.append(f"# Task Ledger Audit — {taskcode} (v0.1.0)")
    lines.append("")
    lines.append(f"- generated_at_utc: `{payload['generated_at_utc']}`")
    lines.append(f"- tasks_root: `{payload['tasks_root']}`")
    lines.append(f"- latest_scanned: `{summary['latest_scanned']}`")
    lines.append("")
    lines.append("## Summary")
    lines.append(f"- by_class: `{json.dumps(summary['by_class'], ensure_ascii=False)}`")
    lines.append(f"- by_class_verdict: `{json.dumps(summary['by_class_verdict'], ensure_ascii=False)}`")
    lines.append(f"- by_class_status: `{json.dumps(summary['by_class_status'], ensure_ascii=False)}`")
    lines.append("")
    lines.append("## Interpretation")
    lines.append("- `contract_task` are runnable by `run_contract_task.py` (contract_ref present).")
    lines.append("- `legacy_orchestrator_task` are not contractized; they require the executor/orchestrator pipeline, not contract runner.")
    lines.append("")
    lines.append("## Latest rows (sample)")
    lines.append("| class | verdict | status | task_id | task_dir |")
    lines.append("|---|---|---|---|---|")
    for r in rows[: min(60, len(rows))]:
        lines.append(f"| {r.get('class')} | {r.get('verdict')} | {r.get('status')} | {r.get('task_id')} | {r.get('task_dir')} |")
    lines.append("")
    out_md.write_text("\n".join(lines).strip() + "\n", encoding="utf-8", errors="replace")

    print(str(out_md))
    print(str(out_json))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

