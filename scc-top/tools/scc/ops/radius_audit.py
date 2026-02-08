#!/usr/bin/env python3
"""
Minimal Change Radius Audit (v1)

Goal:
- Inspect the most recent completed task execution (or a provided task-id)
- Detect "radius expansion" behaviors:
  - touched_files outside pins allowlist
  - touched_files under forbidden paths
  - suspicious script additions
  - weak tests_run for code-touch tasks (passed gate but insufficient evidence)

Outputs (under <exec_log_dir>/radius_audit):
- report.json
- report.md

This is a machine-check + actionable guardrail recommendations.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def read_json(path: Path) -> Optional[Any]:
    try:
        return json.loads(read_text(path) or "null")
    except Exception:
        return None


def norm_path(p: str) -> str:
    s = str(p or "").replace("\\", "/").strip()
    # Strip common repo umbrella prefix to compare relative paths.
    s = re.sub(r"^[a-zA-Z]:/scc/", "", s)
    s = s.lstrip("./")
    return s


def looks_like_doc(p: str) -> bool:
    s = norm_path(p).lower()
    return s.endswith(".md") or s.endswith(".txt") or "/docs/" in s


def looks_like_script(p: str) -> bool:
    s = norm_path(p).lower()
    return s.endswith(".ps1") or s.endswith(".sh") or s.endswith(".cmd") or s.endswith(".bat") or "/scripts/" in s or s.startswith("scripts/")


def is_under(path: str, prefix: str) -> bool:
    p = norm_path(path)
    a = norm_path(prefix)
    if not a:
        return False
    return p == a or p.startswith(a.rstrip("/") + "/")


def within_allowlist(file_path: str, allowlist: List[str]) -> bool:
    fp = norm_path(file_path)
    for a in allowlist:
        if is_under(fp, a):
            return True
    return False


def load_board(board_dir: Path) -> List[Dict[str, Any]]:
    p = board_dir / "tasks.json"
    obj = read_json(p)
    return obj if isinstance(obj, list) else []


def load_jobs_state(exec_log_dir: Path) -> List[Dict[str, Any]]:
    p = exec_log_dir / "jobs_state.json"
    obj = read_json(p)
    return obj if isinstance(obj, list) else []

def load_state_events(exec_log_dir: Path, tail: int = 800) -> List[Dict[str, Any]]:
    p = exec_log_dir / "state_events.jsonl"
    raw = read_text(p)
    if not raw:
        return []
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    if tail > 0:
        lines = lines[-tail:]
    out: List[Dict[str, Any]] = []
    for ln in lines:
        try:
            obj = json.loads(ln)
        except Exception:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def pick_latest_done_task(jobs: List[Dict[str, Any]]) -> Optional[str]:
    done = [j for j in jobs if isinstance(j, dict) and j.get("status") == "done" and j.get("taskId")]
    done.sort(key=lambda j: int(j.get("finishedAt") or j.get("createdAt") or 0), reverse=True)
    return str(done[0]["taskId"]) if done else None


def find_task(board: List[Dict[str, Any]], task_id: str) -> Optional[Dict[str, Any]]:
    for t in board:
        if isinstance(t, dict) and str(t.get("id") or "") == task_id:
            return t
    return None


def find_latest_job_for_task(jobs: List[Dict[str, Any]], task_id: str) -> Optional[Dict[str, Any]]:
    rel = [j for j in jobs if isinstance(j, dict) and str(j.get("taskId") or "") == task_id]
    rel.sort(key=lambda j: int(j.get("finishedAt") or j.get("createdAt") or 0), reverse=True)
    return rel[0] if rel else None


def find_job_by_id(jobs: List[Dict[str, Any]], job_id: str) -> Optional[Dict[str, Any]]:
    for j in jobs:
        if isinstance(j, dict) and str(j.get("id") or "") == job_id:
            return j
    return None


def extract_submit(job: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    s = job.get("submit")
    if isinstance(s, dict):
        return s
    return None


def audit(task: Dict[str, Any], job: Dict[str, Any]) -> Dict[str, Any]:
    pins = task.get("pins") if isinstance(task.get("pins"), dict) else None
    allowed_paths = pins.get("allowed_paths") if isinstance(pins, dict) else None
    forbidden_paths = pins.get("forbidden_paths") if isinstance(pins, dict) else None
    allowlist = [str(x) for x in allowed_paths] if isinstance(allowed_paths, list) else []
    forbid = [str(x) for x in forbidden_paths] if isinstance(forbidden_paths, list) else []

    submit = extract_submit(job) or {}
    touched = submit.get("touched_files") if isinstance(submit, dict) else None
    tests_run = submit.get("tests_run") if isinstance(submit, dict) else None
    touched_files = [str(x) for x in touched] if isinstance(touched, list) else []
    tests = [str(x) for x in tests_run] if isinstance(tests_run, list) else []

    violations: List[Dict[str, Any]] = []

    if not allowlist:
        violations.append(
            {
                "type": "missing_allowlist",
                "detail": "pins.allowed_paths missing; cannot enforce radius",
                "severity": "S0",
                "fail_closed": {"where": "task creation validator", "action": "reject tasks without pins.allowed_paths"},
            }
        )

    if allowlist and touched_files:
        out = [f for f in touched_files if not within_allowlist(f, allowlist)]
        if out:
            violations.append(
                {
                    "type": "touched_outside_allowlist",
                    "severity": "S0",
                    "touched_outside": out[:50],
                    "fail_closed": {"where": "CI gate (task_selftest.py)", "action": "fail if touched_files not under pins.allowed_paths (dir-aware)"},
                }
            )

    if forbid and touched_files:
        bad = []
        for f in touched_files:
            for p in forbid:
                if is_under(f, p):
                    bad.append({"file": f, "forbidden": p})
                    break
        if bad:
            violations.append(
                {
                    "type": "touched_under_forbidden",
                    "severity": "S0",
                    "hits": bad[:50],
                    "fail_closed": {"where": "CI gate (task_selftest.py)", "action": "fail if touched_files under pins.forbidden_paths"},
                }
            )

    # Scripts: require explicit tests beyond generic selftest.
    script_touched = [f for f in touched_files if looks_like_script(f)]
    if script_touched:
        generic_only = (len(tests) == 0) or all("task_selftest.py" in t for t in tests)
        if generic_only:
            violations.append(
                {
                    "type": "script_added_without_validation",
                    "severity": "S1",
                    "scripts": script_touched[:50],
                    "tests_run": tests[:20],
                    "fail_closed": {
                        "where": "CI gate (task_selftest.py)",
                        "action": "if scripts touched, require at least one explicit command validating it (not only task_selftest)",
                    },
                }
            )

    # Weak tests: code touched but tests are generic only.
    code_touched = [f for f in touched_files if not looks_like_doc(f)]
    if code_touched:
        generic_only = (len(tests) == 0) or all("task_selftest.py" in t for t in tests)
        if generic_only:
            violations.append(
                {
                    "type": "insufficient_tests_evidence",
                    "severity": "S1",
                    "code_files": code_touched[:50],
                    "tests_run": tests[:20],
                    "fail_closed": {
                        "where": "CI gate (task_selftest.py)",
                        "action": "for engineer/integrator tasks that touch code, require at least one repo test command (not only task_selftest)",
                    },
                }
            )

    # Undeclared dependency: not fully checkable; flag gap when code touched but no manifest/lock touched.
    manifest_files = {"package.json", "requirements.txt", "pyproject.toml", "poetry.lock", "Cargo.toml", "go.mod", "pom.xml"}
    lock_files = {"package-lock.json", "pnpm-lock.yaml", "yarn.lock", "uv.lock", "pipfile.lock", "Cargo.lock", "go.sum"}
    touched_norm = {Path(norm_path(f)).name for f in touched_files}
    touched_manifest = bool(touched_norm & manifest_files)
    touched_lock = bool(touched_norm & lock_files)
    if code_touched and not touched_manifest and not touched_lock:
        violations.append(
            {
                "type": "undeclared_dependency_gap",
                "severity": "S2",
                "detail": "Code changed but no manifest/lockfile touched; cannot prove no new deps were introduced.",
                "fail_closed": {
                    "where": "executor SUBMIT contract + static check",
                    "action": "require SUBMIT.deps_added=[] and/or run language-specific dependency diff check in CI",
                },
            }
        )

    recommendations = [
        {
            "guardrail": "dir-aware allowlist validator",
            "where": "scc-top/tools/scc/ops/task_selftest.py",
            "change": "replace exact-match subset check with directory-aware prefix check; add forbidden_paths enforcement",
        },
        {
            "guardrail": "tests evidence rule",
            "where": "scc-top/tools/scc/ops/task_selftest.py",
            "change": "if role in {engineer,integrator} and non-doc files touched, require explicit tests_run beyond task_selftest",
        },
        {
            "guardrail": "pre-dispatch pins consistency check",
            "where": "gateway preflight (dispatch)",
            "change": "reject pins where allowed_paths intersects forbidden_paths; reject tasks without pins.allowed_paths",
        },
    ]

    return {
        "task": {
            "id": task.get("id"),
            "kind": task.get("kind"),
            "role": task.get("role"),
            "title": task.get("title"),
        },
        "job": {
            "id": job.get("id"),
            "executor": job.get("executor"),
            "model": job.get("model"),
            "status": job.get("status"),
            "createdAt": job.get("createdAt"),
            "startedAt": job.get("startedAt"),
            "finishedAt": job.get("finishedAt"),
        },
        "pins": {"allowed_paths": allowlist, "forbidden_paths": forbid},
        "submit": {"touched_files": touched_files, "tests_run": tests},
        "violations": violations,
        "recommendations": recommendations,
        "ok": len([v for v in violations if v.get("severity") == "S0"]) == 0,
    }


def render_md(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# Minimal Change Radius Audit v1")
    lines.append("")
    lines.append(f"- generated_at: `{report.get('generated_at')}`")
    t = report.get("audit", {}).get("task", {})
    j = report.get("audit", {}).get("job", {})
    lines.append(f"- task_id: `{t.get('id')}` role=`{t.get('role')}` kind=`{t.get('kind')}`")
    lines.append(f"- job_id: `{j.get('id')}` executor=`{j.get('executor')}` model=`{j.get('model')}` status=`{j.get('status')}`")
    lines.append("")
    lines.append("## Violations")
    lines.append("")
    viol = report.get("audit", {}).get("violations") or []
    if not viol:
        lines.append("- (none detected by this audit)")
    else:
        for v in viol:
            lines.append(f"- **{v.get('type')}** severity=`{v.get('severity')}`")
            if v.get("detail"):
                lines.append(f"  - detail: {v.get('detail')}")
            if v.get("touched_outside"):
                lines.append(f"  - touched_outside_allowlist: {json.dumps(v.get('touched_outside'), ensure_ascii=False)}")
            if v.get("hits"):
                lines.append(f"  - hits: {json.dumps(v.get('hits'), ensure_ascii=False)}")
            if v.get("scripts"):
                lines.append(f"  - scripts: {json.dumps(v.get('scripts'), ensure_ascii=False)}")
            if v.get("code_files"):
                lines.append(f"  - code_files: {json.dumps(v.get('code_files'), ensure_ascii=False)}")
            if v.get("tests_run"):
                lines.append(f"  - tests_run: {json.dumps(v.get('tests_run'), ensure_ascii=False)}")
            fc = v.get("fail_closed") or {}
            lines.append(f"  - fail_closed.where: {fc.get('where')}")
            lines.append(f"  - fail_closed.action: {fc.get('action')}")
    lines.append("")
    lines.append("## Fail-Closed Guardrails (Recommended)")
    lines.append("")
    for r in report.get("audit", {}).get("recommendations") or []:
        lines.append(f"- {r.get('guardrail')} @ `{r.get('where')}`: {r.get('change')}")
    lines.append("")
    return "\n".join(lines).strip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task-id", default="")
    ap.add_argument("--exec-log-dir", default="C:/scc/artifacts/executor_logs")
    ap.add_argument("--board-dir", default="C:/scc/artifacts/taskboard")
    ap.add_argument("--out-dir", default="", help="Optional output directory. If empty, uses <exec_log_dir>/radius_audit.")
    args = ap.parse_args()

    exec_log_dir = Path(args.exec_log_dir)
    board_dir = Path(args.board_dir)
    out_dir = Path(args.out_dir) if args.out_dir else (exec_log_dir / "radius_audit")
    out_dir.mkdir(parents=True, exist_ok=True)

    board = load_board(board_dir)
    jobs = load_jobs_state(exec_log_dir)
    events = load_state_events(exec_log_dir, tail=1200)

    task_id = args.task_id.strip()
    if not task_id:
        # Prefer state_events (has task_id) since jobs_state may contain split jobs with taskId=null.
        done_events = [e for e in events if isinstance(e, dict) and str(e.get("status") or "") == "done" and e.get("task_id")]
        # Prefer "work" roles (radius matters most). Fall back to any done.
        preferred_roles = {"engineer", "integrator", "qa", "doc", "architect"}
        preferred = [e for e in done_events if str(e.get("role") or "") in preferred_roles]
        if preferred:
            preferred.sort(key=lambda e: str(e.get("t") or ""), reverse=True)
            task_id = str(preferred[0].get("task_id") or "")
        else:
            done_events.sort(key=lambda e: str(e.get("t") or ""), reverse=True)
            if done_events:
                task_id = str(done_events[0].get("task_id") or "")
    if not task_id:
        task_id = pick_latest_done_task(jobs) or ""
    if not task_id:
        raise SystemExit("no_task_found")

    task = find_task(board, task_id)
    job: Optional[Dict[str, Any]] = None
    if task and task.get("lastJobId"):
        job = find_job_by_id(jobs, str(task.get("lastJobId") or ""))
    if job is None:
        job = find_latest_job_for_task(jobs, task_id)
    if not task and not job:
        raise SystemExit(f"missing_task_or_job: task={bool(task)} job={bool(job)} task_id={task_id}")

    # Fallback: if task missing, synthesize minimal pins from state_events pins_summary.
    if task is None:
        ev = next((e for e in reversed(events) if str(e.get("task_id") or "") == task_id), None)
        pins_summary = ev.get("pins_summary") if isinstance(ev, dict) else None
        task = {
            "id": task_id,
            "kind": ev.get("kind") if isinstance(ev, dict) else None,
            "role": ev.get("role") if isinstance(ev, dict) else None,
            "title": "(unknown; task not in board)",
            "pins": pins_summary if isinstance(pins_summary, dict) else {},
        }
    if job is None:
        job = {"id": None, "executor": None, "model": None, "status": None}

    audit_out = audit(task, job)
    report = {
        "version": "v1",
        "generated_at": iso_now(),
        "paths": {
            "board": str(board_dir / "tasks.json"),
            "jobs_state": str(exec_log_dir / "jobs_state.json"),
            "state_events": str(exec_log_dir / "state_events.jsonl"),
        },
        "audit": audit_out,
    }

    (out_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "report.md").write_text(render_md(report), encoding="utf-8-sig")
    print(str(out_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
