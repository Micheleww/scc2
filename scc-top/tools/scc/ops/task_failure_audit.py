#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Task Failure Audit (v0.1.0) — deterministic.

Goal:
- Audit SCC task ledger under artifacts/scc_tasks and summarize failure modes
  without any LLM calls.

Outputs:
- Markdown report: docs/REPORT/<area>/REPORT__<TaskCode>__YYYYMMDD.md
- JSON snapshot:   docs/REPORT/<area>/artifacts/<TaskCode>__<stamp>/task_failure_audit.json
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace") or "{}")
    except Exception:
        return {}


def _try_read_text(path: Path, *, max_bytes: int = 50_000) -> str:
    try:
        b = path.read_bytes()
        if len(b) > max_bytes:
            b = b[:max_bytes]
        return b.decode("utf-8", errors="replace")
    except Exception:
        return ""


def _utc_stamp() -> str:
    return time.strftime("%Y%m%d-%H%M%SZ", time.gmtime())


def _date_utc() -> str:
    return time.strftime("%Y%m%d", time.gmtime())


def _count(values: List[str]) -> List[Tuple[str, int]]:
    m: Dict[str, int] = {}
    for v in values:
        vv = (v or "").strip()
        if not vv:
            continue
        m[vv] = m.get(vv, 0) + 1
    return sorted(m.items(), key=lambda kv: (-kv[1], kv[0]))


def _iter_task_dirs(tasks_root: Path) -> List[Path]:
    if not tasks_root.exists():
        return []
    out: List[Path] = []
    for p in tasks_root.iterdir():
        if p.is_dir() and (p / "task.json").exists():
            out.append(p)
    out.sort(key=lambda x: x.name)
    return out


def _latest_task_dirs(tasks_root: Path, limit: int) -> List[Path]:
    dirs = _iter_task_dirs(tasks_root)
    scored: List[Tuple[float, Path]] = []
    for d in dirs:
        try:
            scored.append((float((d / "task.json").stat().st_mtime), d))
        except Exception:
            scored.append((0.0, d))
    scored.sort(key=lambda t: t[0], reverse=True)
    return [d for _, d in scored[: max(1, int(limit or 50))]]


def _load_fail_class(task_dir: Path) -> str:
    ev = task_dir / "events.jsonl"
    if not ev.exists():
        return ""
    lines = _try_read_text(ev).splitlines()
    # find latest TASK_VERIFIED
    for line in reversed(lines[-400:]):
        try:
            j = json.loads(line)
        except Exception:
            continue
        if not isinstance(j, dict):
            continue
        if str(j.get("type") or "") != "TASK_VERIFIED":
            continue
        data = j.get("data") if isinstance(j.get("data"), dict) else {}
        return str(data.get("fail_class") or "").strip()
    return ""


def main() -> int:
    ap = argparse.ArgumentParser(description="Deterministic SCC task failure audit.")
    ap.add_argument("--area", default="control_plane")
    ap.add_argument("--taskcode", default="TASK_FAILURE_AUDIT_V010")
    ap.add_argument("--tasks-root", default="artifacts/scc_tasks")
    ap.add_argument("--limit-latest", type=int, default=80)
    args = ap.parse_args()

    repo_root = _repo_root()
    area = str(args.area).strip() or "control_plane"
    taskcode = str(args.taskcode).strip() or "TASK_FAILURE_AUDIT_V010"
    tasks_root = Path(args.tasks_root)
    if not tasks_root.is_absolute():
        tasks_root = (repo_root / tasks_root).resolve()

    if not tasks_root.exists():
        print(json.dumps({"ok": False, "error": "missing_tasks_root", "tasks_root": str(tasks_root)}, ensure_ascii=False))
        return 2

    latest = _latest_task_dirs(tasks_root, int(args.limit_latest or 80))
    rows: List[dict] = []
    verdicts: List[str] = []
    fail_classes: List[str] = []
    contract_scopes: List[str] = []

    for d in latest:
        tj = _read_json(d / "task.json")
        task_id = str(tj.get("task_id") or d.name)
        verdict = str(tj.get("verdict") or "").strip().upper() or "UNKNOWN"
        status = str(tj.get("status") or "").strip()
        contract_ref = ((tj.get("request") or {}) if isinstance(tj.get("request"), dict) else {}).get("contract_ref")
        contract_ref = str(contract_ref or "").replace("\\", "/").strip()
        exit_code = tj.get("exit_code")
        try:
            exit_code_i = int(exit_code) if exit_code is not None else None
        except Exception:
            exit_code_i = None

        fail_class = _load_fail_class(d)

        # Optional: peek contract scope_allow size and whether it's "contract-only".
        scope_kind = ""
        if contract_ref:
            cp = (repo_root / contract_ref).resolve()
            if cp.exists() and cp.suffix.lower() == ".json":
                c = _read_json(cp)
                sa = c.get("scope_allow")
                items: List[str] = []
                if isinstance(sa, list):
                    items = [str(x).strip().replace("\\", "/") for x in sa if str(x).strip()]
                elif isinstance(sa, str):
                    s = sa.strip()
                    if s:
                        items = [p.strip() for p in s.replace("\\", "/").split(",") if p.strip()]
                if not items:
                    scope_kind = "empty"
                else:
                    if len(items) == 1 and contract_ref and items[0] == contract_ref:
                        scope_kind = "contract_only"
                    elif all(x.startswith("docs/ssot/04_contracts/generated/") for x in items):
                        scope_kind = "generated_only"
                    else:
                        scope_kind = f"paths:{len(items)}"
                if scope_kind:
                    contract_scopes.append(scope_kind)

        verdicts.append(verdict)
        if verdict == "FAIL" and fail_class:
            fail_classes.append(fail_class)
        rows.append(
            {
                "task_id": task_id,
                "status": status,
                "verdict": verdict,
                "exit_code": exit_code_i,
                "fail_class": fail_class,
                "contract_ref": contract_ref,
                "scope_kind": scope_kind,
                "task_dir": str(d.relative_to(repo_root)).replace("\\", "/"),
            }
        )

    counts = {
        "latest_scanned": len(rows),
        "by_verdict": [{"verdict": k, "count": v} for k, v in _count(verdicts)],
        "by_fail_class": [{"fail_class": k, "count": v} for k, v in _count(fail_classes)],
        "by_scope_kind": [{"scope_kind": k, "count": v} for k, v in _count(contract_scopes)],
    }

    recs: List[str] = []
    # Heuristic suggestions
    if any(x.get("scope_kind") in ("empty", "contract_only", "generated_only") for x in rows):
        recs.append("Many tasks are not executable yet (scope_allow empty/contract_only/generated_only). Next: Planner must expand scope_allow to real code paths for at least 1 task.")
    if any((x.get("fail_class") or "").startswith("exit_") for x in rows):
        recs.append("Some contract_runner executions exit nonzero. Inspect each task evidence stdout/stderr/selftest.log under artifacts/scc_tasks/<task>/evidence/contract_runner/.")

    payload = {
        "ok": True,
        "schema_version": "v0.1.0",
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "area": area,
        "taskcode": taskcode,
        "tasks_root": str(tasks_root.relative_to(repo_root)).replace("\\", "/"),
        "counts": counts,
        "latest_rows": rows,
        "recommendations": recs,
    }

    out_md = repo_root / "docs" / "REPORT" / area / f"REPORT__{taskcode}__{_date_utc()}.md"
    out_json = repo_root / "docs" / "REPORT" / area / "artifacts" / f"{taskcode}__{_utc_stamp()}" / "task_failure_audit.json"
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", errors="replace")

    lines: List[str] = []
    lines.append(f"# Task Failure Audit — {taskcode} (v0.1.0)")
    lines.append("")
    lines.append(f"- generated_at_utc: `{payload['generated_at_utc']}`")
    lines.append(f"- tasks_root: `{payload['tasks_root']}`")
    lines.append(f"- latest_scanned: `{counts['latest_scanned']}`")
    lines.append("")
    lines.append("## Counts")
    lines.append(f"- by_verdict: `{json.dumps(counts['by_verdict'], ensure_ascii=False)}`")
    lines.append(f"- by_fail_class: `{json.dumps(counts['by_fail_class'], ensure_ascii=False)}`")
    lines.append(f"- by_scope_kind: `{json.dumps(counts['by_scope_kind'], ensure_ascii=False)}`")
    lines.append("")
    if recs:
        lines.append("## Recommendations")
        for r in recs:
            lines.append(f"- {r}")
        lines.append("")
    lines.append("## Latest tasks (sample)")
    lines.append("| verdict | fail_class | scope_kind | exit_code | task_id | contract_ref | task_dir |")
    lines.append("|---|---|---|---:|---|---|---|")
    for x in rows[: min(40, len(rows))]:
        lines.append(
            f"| {x.get('verdict','')} | {str(x.get('fail_class') or '')[:32]} | {x.get('scope_kind','')} | {x.get('exit_code') or ''} | {x.get('task_id','')} | {x.get('contract_ref','')} | {x.get('task_dir','')} |"
        )
    lines.append("")
    lines.append("## Evidence pointers")
    lines.append("- Per task: `artifacts/scc_tasks/<task_id>/task.json` + `events.jsonl` + `evidence/contract_runner/`")
    lines.append("")
    out_md.write_text("\n".join(lines).strip() + "\n", encoding="utf-8", errors="replace")

    print(str(out_md))
    print(str(out_json))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

