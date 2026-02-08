#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Contract Runner Batch (v0.1.0) — deterministic.

Purpose:
- Re-run failed tasks under artifacts/scc_tasks using run_contract_task.py
  with guard-compatible triplet creation.
- This is a deterministic "rehydrate verdicts" job (no LLM).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace") or "{}")
    except Exception:
        return {}


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", errors="replace")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", errors="replace")


def _date_utc() -> str:
    return time.strftime("%Y%m%d", time.gmtime())


def _stamp_utc() -> str:
    return time.strftime("%Y%m%d-%H%M%SZ", time.gmtime())


def _iter_failed_tasks(tasks_root: Path) -> List[Tuple[float, str]]:
    out: List[Tuple[float, str]] = []
    for d in tasks_root.iterdir():
        if not d.is_dir():
            continue
        tj = d / "task.json"
        if not tj.exists():
            continue
        j = _read_json(tj)
        verdict = str(j.get("verdict") or "").strip().upper()
        if verdict != "FAIL":
            continue
        try:
            mt = float(tj.stat().st_mtime)
        except Exception:
            mt = 0.0
        out.append((mt, str(j.get("task_id") or d.name)))
    out.sort(key=lambda t: t[0], reverse=True)
    return out


def _iter_rerunnable_tasks(tasks_root: Path, *, include_unknown: bool) -> List[Tuple[float, str]]:
    """
    Return task_ids that should be (re)run.
    - Always includes FAIL tasks.
    - Optionally includes UNKNOWN/unset verdict tasks.
    """
    out: List[Tuple[float, str]] = []
    for d in tasks_root.iterdir():
        if not d.is_dir():
            continue
        tj = d / "task.json"
        if not tj.exists():
            continue
        j = _read_json(tj)
        req = j.get("request") if isinstance(j.get("request"), dict) else {}
        contract_ref = str(req.get("contract_ref") or "").strip()
        # Only contractized tasks can be run by run_contract_task.py.
        if not contract_ref:
            continue
        verdict = str(j.get("verdict") or "").strip().upper() or "UNKNOWN"
        if verdict == "PASS":
            continue
        if verdict == "FAIL":
            pass
        else:
            if not include_unknown:
                continue
        try:
            mt = float(tj.stat().st_mtime)
        except Exception:
            mt = 0.0
        out.append((mt, str(j.get("task_id") or d.name)))
    out.sort(key=lambda t: t[0], reverse=True)
    return out


def _read_manifest(path: Path) -> List[str]:
    raw = (path.read_text(encoding="utf-8", errors="replace") or "").splitlines()
    out: List[str] = []
    for line in raw:
        s = (line or "").strip()
        if not s or s.startswith("#"):
            continue
        out.append(s)
    # de-dup while preserving order
    seen = set()
    deduped: List[str] = []
    for t in out:
        if t in seen:
            continue
        seen.add(t)
        deduped.append(t)
    return deduped


def main() -> int:
    ap = argparse.ArgumentParser(description="Deterministic batch contract runner for failed tasks.")
    ap.add_argument("--area", default="control_plane")
    ap.add_argument("--taskcode", default="CONTRACT_RUN_BATCH_V010")
    ap.add_argument("--tasks-root", default="artifacts/scc_tasks")
    ap.add_argument("--limit", type=int, default=None, help="Max tasks to run (default: 25 for auto-pick; unlimited for --manifest).")
    ap.add_argument("--timeout-s", type=int, default=60)
    ap.add_argument("--include-unknown", action="store_true", help="Also run tasks whose verdict is UNKNOWN/unset (default: only FAIL).")
    ap.add_argument("--jobs", type=int, default=4, help="Parallel workers (threaded).")
    ap.add_argument("--manifest", default="", help="Optional newline-separated task_id list; overrides picking logic.")
    args = ap.parse_args()

    repo_root = _repo_root()
    area = str(args.area).strip() or "control_plane"
    taskcode = str(args.taskcode).strip() or "CONTRACT_RUN_BATCH_V010"
    tasks_root = Path(args.tasks_root)
    if not tasks_root.is_absolute():
        tasks_root = (repo_root / tasks_root).resolve()
    if not tasks_root.exists():
        print(json.dumps({"ok": False, "error": "missing_tasks_root", "tasks_root": str(tasks_root)}, ensure_ascii=False))
        return 2

    manifest_path: Optional[Path] = None
    if str(args.manifest).strip():
        manifest_path = Path(str(args.manifest).strip())
        if not manifest_path.is_absolute():
            manifest_path = (repo_root / manifest_path).resolve()
        if not manifest_path.exists():
            print(json.dumps({"ok": False, "error": "missing_manifest", "manifest": str(manifest_path)}, ensure_ascii=False))
            return 3
        picked = _read_manifest(manifest_path)
    else:
        picked_pool = _iter_rerunnable_tasks(tasks_root, include_unknown=bool(args.include_unknown))
        picked = [tid for _, tid in picked_pool]

    # limit policy: auto-pick defaults to 25; manifest defaults to unlimited.
    effective_limit: int = 0
    if args.limit is None:
        effective_limit = 0 if manifest_path else 25
    else:
        effective_limit = int(args.limit or 0)
    if effective_limit > 0 and len(picked) > effective_limit:
        picked = picked[:effective_limit]

    out_json = (repo_root / "docs" / "REPORT" / area / "artifacts" / f"{taskcode}__{_stamp_utc()}" / "contract_runner_batch.json").resolve()
    live_log = out_json.parent / "live.log"

    def _log(line: str) -> None:
        ts = time.strftime("%H:%M:%S", time.gmtime())
        live_log.parent.mkdir(parents=True, exist_ok=True)
        with live_log.open("a", encoding="utf-8", errors="replace") as f:
            f.write(f"[{ts}] {line.rstrip()}\n")

    jobs = max(1, int(args.jobs or 1))
    timeout_s = int(args.timeout_s or 60)
    results: List[dict] = []
    ok_n = 0
    fail_n = 0

    def _run_one(tid: str) -> dict:
        cmd = [
            sys.executable,
            "tools/scc/ops/run_contract_task.py",
            "--task-id",
            tid,
            "--area",
            area,
            "--timeout-s",
            str(int(timeout_s)),
        ]
        try:
            p = subprocess.run(
                cmd,
                cwd=str(repo_root),
                env=dict(os.environ),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=int(timeout_s + 30),
            )
            rc = int(p.returncode or 0)
            out = (p.stdout or "").strip()
            err = (p.stderr or "").strip()
            verdict = "PASS" if rc == 0 else "FAIL"
            return {"task_id": tid, "exit_code": rc, "verdict": verdict, "stdout_head": out[:600], "stderr_head": err[:600]}
        except subprocess.TimeoutExpired:
            return {"task_id": tid, "exit_code": 124, "verdict": "FAIL", "stdout_head": "", "stderr_head": "timeout_expired"}

    _log(f"start jobs={jobs} timeout_s={timeout_s} picked={len(picked)} manifest={str(manifest_path) if manifest_path else ''}")
    with ThreadPoolExecutor(max_workers=jobs) as ex:
        futs = {ex.submit(_run_one, tid): tid for tid in picked}
        done_n = 0
        for fut in as_completed(futs):
            r = fut.result()
            results.append(r)
            done_n += 1
            if r.get("verdict") == "PASS":
                ok_n += 1
            else:
                fail_n += 1
            _log(f"done {done_n}/{len(picked)} {r.get('verdict')} {r.get('task_id')} rc={r.get('exit_code')}")

    payload = {
        "ok": True,
        "schema_version": "v0.1.0",
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "area": area,
        "taskcode": taskcode,
        "tasks_root": str(tasks_root.relative_to(repo_root)).replace("\\", "/"),
        "include_unknown": bool(args.include_unknown),
        "manifest": str(manifest_path.relative_to(repo_root)).replace("\\", "/") if manifest_path else "",
        "effective_limit": effective_limit,
        "jobs": jobs,
        "timeout_s": timeout_s,
        "picked": picked,
        "counts": {"picked": len(picked), "pass": ok_n, "fail": fail_n},
        "results": results,
    }

    out_md = (repo_root / "docs" / "REPORT" / area / f"REPORT__{taskcode}__{_date_utc()}.md").resolve()
    _write_json(out_json, payload)

    lines: List[str] = []
    lines.append(f"# Contract Runner Batch — {taskcode} (v0.1.0)")
    lines.append("")
    lines.append(f"- generated_at_utc: `{payload['generated_at_utc']}`")
    lines.append(f"- tasks_root: `{payload['tasks_root']}`")
    lines.append(f"- counts: `{json.dumps(payload['counts'], ensure_ascii=False)}`")
    lines.append("")
    lines.append("## Results")
    lines.append("| verdict | exit_code | task_id | stdout_head |")
    lines.append("|---|---:|---|---|")
    for r in results:
        sh = (r.get("stdout_head") or "").replace("\n", " ")[:120]
        lines.append(f"| {r.get('verdict')} | {r.get('exit_code')} | {r.get('task_id')} | {sh} |")
    lines.append("")
    lines.append("## Notes")
    lines.append("- Each task run produces its own guard-compatible triplet under `docs/REPORT/<area>/REPORT__CONTRACT_RUN__...`.")
    if manifest_path:
        lines.append(f"- manifest: `{payload['manifest']}`")
        lines.append(f"- live log: `{str(live_log.relative_to(repo_root)).replace('\\\\','/')}`")
    _write_text(out_md, "\n".join(lines).strip() + "\n")

    print(str(out_md))
    print(str(out_json))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
