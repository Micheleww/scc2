#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import hashlib
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, List


def _default_repo_root() -> Path:
    # scc-top/tools/scc/ops/*.py -> repo root is 4 levels up
    return Path(os.environ.get("SCC_REPO_ROOT") or Path(__file__).resolve().parents[4]).resolve()


def _read_json(path: Path) -> Optional[Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None


def _read_jsonl_tail(path: Path, tail: int = 4000) -> List[Dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return []
    out: List[Dict[str, Any]] = []
    for line in lines[-int(tail) :]:
        s = str(line or "").strip()
        if not s:
            continue
        try:
            obj = json.loads(s)
        except Exception:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def _sha256_text(s: str) -> str:
    h = hashlib.sha256()
    h.update(s.encode("utf-8", errors="replace"))
    return h.hexdigest()


def _resolve_repo_path(p: str) -> Path:
    pp = Path(str(p))
    if pp.is_absolute():
        return pp
    return (_default_repo_root() / pp).resolve()


def _find_task(tasks: Any, task_id: str) -> Optional[Dict[str, Any]]:
    if not isinstance(tasks, list):
        return None
    for t in tasks:
        if isinstance(t, dict) and str(t.get("id") or "") == task_id:
            return t
    return None


def _extract_patch_stats(job: Dict[str, Any]) -> Tuple[int, int, int]:
    ps = job.get("patch_stats")
    if not isinstance(ps, dict):
        return (0, 0, 0)
    files = int(ps.get("filesCount") or 0)
    added = int(ps.get("added") or 0)
    removed = int(ps.get("removed") or 0)
    return (files, added, removed)

def _extract_submit(job: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    s = job.get("submit")
    if isinstance(s, dict):
        return s
    # Fallback: parse stdout for "SUBMIT: {json}"
    stdout = str(job.get("stdout") or "")
    for line in stdout.splitlines():
        if not line.startswith("SUBMIT:"):
            continue
        payload = line[len("SUBMIT:") :].strip()
        try:
            obj = json.loads(payload)
            if isinstance(obj, dict):
                return obj
        except Exception:
            return None
    return None

def _norm_path(p: str) -> str:
    s = str(p or "").replace("\\", "/").strip()
    s = re.sub(r"^[a-zA-Z]:/scc/", "", s)
    s = s.lstrip("./")
    return s


def _is_under(path: str, prefix: str) -> bool:
    p = _norm_path(path)
    a = _norm_path(prefix)
    if not a:
        return False
    return p == a or p.startswith(a.rstrip("/") + "/")


def _within_allowlist(files: Any, allowlist: Any) -> bool:
    if not isinstance(files, list) or not isinstance(allowlist, list):
        return False
    al = [str(x) for x in allowlist if x is not None]
    for f in files:
        if f is None:
            continue
        fp = str(f)
        ok = any(_is_under(fp, a) for a in al)
        if not ok:
            return False
    return True


def _looks_like_doc(path: str) -> bool:
    p = path.lower()
    return p.endswith(".md") or p.endswith(".txt") or "/docs/" in p.replace("\\", "/")


def main() -> int:
    ap = argparse.ArgumentParser(description="Task-level selftest used by CI gate (exit code 0 == PASS).")
    ap.add_argument("--task-id", required=True)
    ap.add_argument("--board-file", default=os.environ.get("BOARD_FILE") or "")
    ap.add_argument("--jobs-state", default=os.environ.get("JOBS_STATE_FILE") or "")
    args = ap.parse_args()

    task_id = str(args.task_id).strip()
    if not task_id:
        print("[FAIL] missing task-id")
        return 2

    # Defaults match gateway defaults.
    repo_root = _default_repo_root()
    board_dir = Path(os.environ.get("BOARD_DIR") or str(repo_root / "artifacts" / "taskboard"))
    exec_log_dir = Path(os.environ.get("EXEC_LOG_DIR") or str(repo_root / "artifacts" / "executor_logs"))
    board_file = Path(args.board_file) if args.board_file else (board_dir / "tasks.json")
    jobs_state = Path(args.jobs_state) if args.jobs_state else (exec_log_dir / "jobs_state.json")
    ci_gate_results = exec_log_dir / "ci_gate_results.jsonl"

    tasks = _read_json(board_file)
    if tasks is None:
        print(f"[FAIL] cannot read board file: {board_file}")
        return 2

    t = _find_task(tasks, task_id)
    if not t:
        print(f"[FAIL] task not found: {task_id}")
        return 2

    last_job_id = str(t.get("lastJobId") or "")
    if not last_job_id:
        print("[FAIL] task has no lastJobId")
        return 1

    jobs = _read_json(jobs_state)
    if not isinstance(jobs, list):
        print(f"[FAIL] cannot read jobs state: {jobs_state}")
        return 2

    job = None
    for j in jobs:
        if isinstance(j, dict) and str(j.get("id") or "") == last_job_id:
            job = j
            break
    if not job:
        print(f"[FAIL] job not found in jobs_state: {last_job_id}")
        return 2

    if str(job.get("status") or "") != "done":
        print(f"[FAIL] job status != done: {job.get('status')}")
        return 1
    exit_code = job.get("exit_code")
    if exit_code is None or int(exit_code) != 0:
        print(f"[FAIL] executor exit_code != 0: {exit_code}")
        return 1

    started_at = int(job.get("startedAt") or 0)
    finished_at = int(job.get("finishedAt") or 0)

    # From CI_ENFORCE_SINCE_MS onward, require structured evidence (fail-closed).
    enforce_since_ms = int(os.environ.get("CI_ENFORCE_SINCE_MS") or "0")
    created_at = int(t.get("createdAt") or 0)
    strict = enforce_since_ms <= 0 or created_at >= enforce_since_ms

    # Anti-forgery can be rolled out after CI enforcement without retroactively failing old tasks.
    antiforge_since_ms = int(os.environ.get("CI_ANTIFORGERY_SINCE_MS") or "0")
    antiforge = antiforge_since_ms > 0 and created_at >= antiforge_since_ms

    submit = _extract_submit(job)
    touched_files = submit.get("touched_files") if isinstance(submit, dict) else None
    tests_obj = submit.get("tests") if isinstance(submit, dict) else None
    tests_commands = tests_obj.get("commands") if isinstance(tests_obj, dict) else None
    tests_run = submit.get("tests_run") if isinstance(submit, dict) else None
    if not isinstance(tests_run, list):
        # Back-compat: SCC submit v1 stores test commands under SUBMIT.tests.commands.
        tests_run = [str(x) for x in tests_commands] if isinstance(tests_commands, list) else []

    # Anti-deception / evidence minimalism:
    # Require at least one touched file OR a patch touching at least one file for most roles.
    role = str(t.get("role") or "").strip().lower()
    task_class_id = str(t.get("task_class_id") or "")
    files_touched, added, removed = _extract_patch_stats(job)

    allow_no_patch_roles = {"auditor", "status_review", "factory_manager", "pinser"}
    allow_no_submit_roles = {"auditor", "status_review", "factory_manager", "pinser"}

    if strict and role not in allow_no_submit_roles:
        if not isinstance(submit, dict):
            print("[FAIL] missing SUBMIT contract (submit not found)")
            return 1
        if not isinstance(touched_files, list) or len(touched_files) <= 0:
            print("[FAIL] missing SUBMIT.touched_files")
            return 1
        if not isinstance(tests_obj, dict) or not isinstance(tests_commands, list):
            print("[FAIL] missing SUBMIT.tests.commands (must be a list; can be empty)")
            return 1

    # Evidence anti-forgery: require CI gate log entry and validate hashes/log-paths.
    # This prevents "report looks good but selftest didn't run" style spoofing.
    if antiforge and role not in {"auditor", "status_review", "factory_manager", "pinser"}:
        if not ci_gate_results.exists():
            print(f"[FAIL] missing ci_gate_results.jsonl: {ci_gate_results}")
            return 1
        rows = _read_jsonl_tail(ci_gate_results, tail=8000)
        match = None
        for r in reversed(rows):
            if str(r.get("job_id") or "") == last_job_id:
                match = r
                break
        if not isinstance(match, dict):
            print("[FAIL] missing CI gate evidence for job_id in ci_gate_results.jsonl")
            return 1
        if not bool(match.get("ran")):
            print("[FAIL] CI gate did not run (ran=false)")
            return 1
        if bool(match.get("required")) and not bool(match.get("ok")):
            print("[FAIL] CI gate failed (ok=false)")
            return 1
        exit_ci = match.get("exitCode")
        if exit_ci is None or int(exit_ci) != 0:
            print(f"[FAIL] CI gate exitCode != 0: {exit_ci}")
            return 1

        stdout_path = match.get("stdoutPath") or match.get("stdout_path")
        stderr_path = match.get("stderrPath") or match.get("stderr_path")
        stdout_sha = match.get("stdoutSha256") or match.get("stdout_sha256")
        stderr_sha = match.get("stderrSha256") or match.get("stderr_sha256")
        if not (stdout_path and stderr_path and stdout_sha and stderr_sha):
            print("[FAIL] CI gate missing anti-forgery fields (paths/hashes)")
            return 1
        sp = Path(str(stdout_path))
        ep = Path(str(stderr_path))
        if not sp.exists() or not ep.exists():
            print("[FAIL] CI gate log files missing:")
            print(f"- stdoutPath={sp} exists={sp.exists()}")
            print(f"- stderrPath={ep} exists={ep.exists()}")
            return 1
        try:
            stext = sp.read_text(encoding="utf-8", errors="replace")
            etext = ep.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            print(f"[FAIL] cannot read CI gate log files: {e}")
            return 1
        if _sha256_text(stext) != str(stdout_sha):
            print("[FAIL] CI gate stdout hash mismatch (possible tamper/spoof)")
            return 1
        if _sha256_text(etext) != str(stderr_sha):
            print("[FAIL] CI gate stderr hash mismatch (possible tamper/spoof)")
            return 1

    if role not in allow_no_patch_roles:
        has_patch_evidence = files_touched > 0
        has_submit_evidence = isinstance(touched_files, list) and len(touched_files) > 0
        if not (has_patch_evidence or has_submit_evidence):
            print("[FAIL] missing change evidence (no patch_stats and no SUBMIT.touched_files)")
            return 1

    # If task declares files, ensure they exist.
    declared_files = t.get("files")
    if isinstance(declared_files, list) and declared_files:
        missing = []
        for f in declared_files[:50]:
            p = Path(str(f))
            if not p.is_absolute():
                # Resolve relative to repo root if possible.
                p = (repo_root / p).resolve()
            if not p.exists():
                missing.append(str(f))
        if missing:
            print("[FAIL] declared files missing:")
            for m in missing[:20]:
                print(f"- {m}")
            return 1

    # Enforce touched_files is within pins/files when strict.
    if strict and isinstance(submit, dict) and isinstance(touched_files, list) and touched_files:
        pins = t.get("pins") if isinstance(t.get("pins"), dict) else None
        allowed_paths = pins.get("allowed_paths") if isinstance(pins, dict) else None
        forbidden_paths = pins.get("forbidden_paths") if isinstance(pins, dict) else None
        allowlist = None
        if isinstance(allowed_paths, list) and allowed_paths:
            allowlist = [str(x) for x in allowed_paths]
        elif isinstance(declared_files, list) and declared_files:
            allowlist = [str(x) for x in declared_files]
        if allowlist is not None:
            tf = [str(x) for x in touched_files]
            if not _within_allowlist(tf, allowlist):
                print("[FAIL] touched_files out of pins/files allowlist:")
                print("  touched_files=" + json.dumps(tf, ensure_ascii=False))
                print("  allowlist=" + json.dumps(allowlist, ensure_ascii=False))
                return 1

        # Enforce forbidden_paths (fail-closed).
        if isinstance(forbidden_paths, list) and forbidden_paths:
            hits = []
            for f in [str(x) for x in touched_files]:
                for p in [str(x) for x in forbidden_paths]:
                    if _is_under(f, p):
                        hits.append({"file": f, "forbidden": p})
                        break
            if hits:
                print("[FAIL] touched_files under forbidden_paths:")
                print("  hits=" + json.dumps(hits[:50], ensure_ascii=False))
                return 1

        # Evidence strength: code-touch tasks must provide an explicit tests_run beyond task_selftest.
        role = str(t.get("role") or "unknown")
        tests_run2 = submit.get("tests_run") if isinstance(submit, dict) else None
        if not isinstance(tests_run2, list):
            tests_run2 = [str(x) for x in tests_commands] if isinstance(tests_commands, list) else []
        tests = [str(x) for x in tests_run2] if isinstance(tests_run2, list) else []
        is_generic_only = (len(tests) == 0) or all("task_selftest.py" in x for x in tests)
        if role in {"engineer", "integrator"} and is_generic_only:
            non_doc = [str(x) for x in touched_files if x is not None and not _looks_like_doc(str(x))]
            if non_doc:
                print("[FAIL] insufficient tests_run evidence for code-touch task (only task_selftest):")
                print("  role=" + role)
                print("  non_doc_touched=" + json.dumps(non_doc[:50], ensure_ascii=False))
                print("  tests_run=" + json.dumps(tests[:20], ensure_ascii=False))
                return 1

        # Cross-check touched_files against filesystem mtimes within job window to reduce SUBMIT spoofing.
        if antiforge and started_at > 0 and finished_at > 0 and finished_at >= started_at:
            slack_ms = 60_000  # allow for clock skew and buffered writes
            lo = started_at - slack_ms
            hi = finished_at + slack_ms
            bad = []
            for f in [str(x) for x in touched_files][:80]:
                rp = _resolve_repo_path(_norm_path(f))
                if not rp.exists():
                    bad.append({"file": f, "reason": "missing_on_disk"})
                    continue
                mtime_ms = int(rp.stat().st_mtime * 1000)
                if mtime_ms < lo or mtime_ms > hi:
                    bad.append({"file": f, "reason": "mtime_outside_job_window", "mtime_ms": mtime_ms, "lo": lo, "hi": hi})
            if bad:
                print("[FAIL] touched_files do not match on-disk modifications within job window (possible SUBMIT spoof):")
                print("  bad=" + json.dumps(bad[:50], ensure_ascii=False))
                return 1
        elif antiforge and touched_files:
            print("[FAIL] missing job startedAt/finishedAt; cannot validate touched_files mtimes (fail-closed)")
            return 1

    # Doc sanity: doc tasks must touch at least one doc-like file.
    if strict and role == "doc":
        tf = [str(x) for x in touched_files] if isinstance(touched_files, list) else []
        if not any(_looks_like_doc(x) for x in tf):
            print("[FAIL] doc task must touch at least one doc file (SUBMIT.touched_files)")
            return 1

    print(
        json.dumps(
            {
                "ok": True,
                "task_id": task_id,
                "job_id": last_job_id,
                "role": role,
                "task_class_id": task_class_id or None,
                "patch": {"files": files_touched, "added": added, "removed": removed},
                "submit": {
                    "touched_files": touched_files if isinstance(touched_files, list) else None,
                    "tests_run": tests_run if isinstance(tests_run, list) else None,
                },
                "ci_gate": {
                    "job_id": last_job_id,
                    "verified": True,
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
