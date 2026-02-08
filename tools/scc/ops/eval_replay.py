#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib
from datetime import datetime, timezone
from typing import Any, Dict, List


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: pathlib.Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8").lstrip("\ufeff"))


def _list_json_files(dir_path: pathlib.Path) -> List[pathlib.Path]:
    if not dir_path.exists():
        return []
    return sorted([p for p in dir_path.glob("*.json") if p.is_file()])


def _validate_playbook_shape(obj: Any) -> List[str]:
    if not isinstance(obj, dict):
        return ["not_object"]
    if obj.get("schema_version") != "scc.playbook.v1":
        return ["schema_version_mismatch"]
    for k in ("playbook_id", "version", "pattern_id", "enablement", "actions"):
        if k not in obj:
            return [f"missing_{k}"]
    en = obj.get("enablement")
    if not isinstance(en, dict) or en.get("schema_version") != "scc.enablement.v1":
        return ["enablement_invalid"]
    actions = obj.get("actions")
    if not isinstance(actions, list) or not actions:
        return ["actions_empty"]
    for i, a in enumerate(actions[:50]):
        if not isinstance(a, dict) or "type" not in a:
            return [f"action_{i}_invalid"]
    return []


def _read_jsonl_tail(path: pathlib.Path, tail: int = 6000) -> List[Dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return []
    out: List[Dict[str, Any]] = []
    for ln in lines[-int(tail) :]:
        s = str(ln or "").strip()
        if not s:
            continue
        try:
            obj = json.loads(s)
        except Exception:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def _event_matches_pattern(event: Dict[str, Any], pattern: Dict[str, Any]) -> bool:
    if not isinstance(event, dict) or not isinstance(pattern, dict):
        return False
    if pattern.get("schema_version") != "scc.pattern.v1":
        return False
    match = pattern.get("match") if isinstance(pattern.get("match"), dict) else {}
    et = str(match.get("event_type") or "").strip()
    if not et:
        return False
    if str(event.get("event_type") or "") != et:
        return False
    tool = match.get("tool")
    if tool is not None and str(event.get("executor") or "") != str(tool):
        return False
    st = match.get("stacktrace_hash")
    if st is not None and str(event.get("stacktrace_hash") or "") != str(st):
        return False
    cls = match.get("task_class")
    if cls is not None and str(event.get("task_class") or "") != str(cls):
        return False
    ft = match.get("failing_test")
    if ft is not None:
        failing = event.get("failing_tests")
        if not (isinstance(failing, list) and failing and str(failing[0]) == str(ft)):
            return False
    code = match.get("code")
    if code is not None:
        reason = str(event.get("reason") or "")
        if str(code) not in reason:
            return False
    return True


def _run_gates_on_task(task_id: str, strict: bool = True, timeout_s: int = 60) -> Dict[str, Any]:
    import subprocess

    task_id = str(task_id).strip()
    submit = (REPO_ROOT / "artifacts" / task_id / "submit.json").resolve()
    if not submit.exists():
        return {
            "task_id": task_id,
            "ok": False,
            "error": "missing_submit",
            "submit": str(submit.relative_to(REPO_ROOT)).replace("\\", "/"),
        }
    cmd = ["python", "tools/scc/gates/run_ci_gates.py"]
    if strict:
        cmd.append("--strict")
    cmd += ["--submit", str(submit.relative_to(REPO_ROOT)).replace("\\", "/")]
    try:
        r = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=max(5, int(timeout_s)))
    except subprocess.TimeoutExpired:
        return {"task_id": task_id, "ok": False, "error": "gate_timeout", "command": " ".join(cmd)}
    ok = r.returncode == 0
    return {
        "task_id": task_id,
        "ok": ok,
        "exit_code": r.returncode,
        "command": " ".join(cmd),
        "stdout": (r.stdout or "").strip()[-4000:],
        "stderr": (r.stderr or "").strip()[-4000:],
    }


def _task_strict_eligible(task_id: str) -> bool:
    task_id = str(task_id).strip()
    if not task_id:
        return False
    art = (REPO_ROOT / "artifacts" / task_id).resolve()
    submit = art / "submit.json"
    pre = art / "preflight.json"
    pins = art / "pins" / "pins.json"
    rb = art / "replay_bundle.json"
    ev = art / "events.jsonl"
    if not (submit.exists() and pre.exists() and pins.exists() and rb.exists() and ev.exists()):
        return False
    try:
        pre_obj = _load_json(pre)
        if not isinstance(pre_obj, dict) or pre_obj.get("schema_version") != "scc.preflight.v1":
            return False
        pins_obj = _load_json(pins)
        if not isinstance(pins_obj, dict) or pins_obj.get("schema_version") != "scc.pins_result.v2":
            return False
    except Exception:
        return False
    return True


def _playbook_stage(obj: Any) -> str:
    if not isinstance(obj, dict):
        return "draft"
    lifecycle = obj.get("lifecycle") if isinstance(obj.get("lifecycle"), dict) else None
    stage = str(lifecycle.get("stage") or "").strip() if lifecycle else ""
    if stage in {"draft", "candidate", "active", "deprecated"}:
        return stage
    return "draft"


def _suggest_tasks_for_pattern(events: List[Dict[str, Any]], pattern: Dict[str, Any], limit: int = 5) -> List[str]:
    if not isinstance(pattern, dict):
        return []
    out: List[str] = []
    seen: set[str] = set()
    for ev in reversed(events):
        if not _event_matches_pattern(ev, pattern):
            continue
        tid = ev.get("task_id")
        if not isinstance(tid, str) or not tid.strip():
            continue
        tid = tid.strip()
        if tid in seen:
            continue
        seen.add(tid)
        if not _task_strict_eligible(tid):
            continue
        out.append(tid)
        if len(out) >= int(limit):
            break
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Eval gate for playbook drafts (offline shape + historical replay smoke).")
    ap.add_argument("--drafts", default="playbooks/drafts", help="Draft playbooks directory")
    ap.add_argument("--draft", action="append", default=[], help="Specific draft file (repeatable). If set, only these drafts are evaluated.")
    ap.add_argument("--out", default="artifacts/executor_logs/eval_replay_latest.json", help="Output report path")
    ap.add_argument("--events-tail", type=int, default=6000, help="Tail N events from artifacts/executor_logs/state_events.jsonl for sampling")
    ap.add_argument("--samples-per-playbook", type=int, default=2, help="Max historical samples per playbook for replay-smoke")
    ap.add_argument("--gates-timeout-s", type=int, default=60, help="Timeout per gate replay in seconds")
    ap.add_argument("--sample-sets-dir", default="eval/sample_sets", help="Curated sample sets dir (one JSON per pattern_id)")
    ap.add_argument("--require-sample-set", action="store_true", help="Fail if no curated sample set exists for a playbook's pattern_id")
    ap.add_argument("--candidates-only", action="store_true", help="Only evaluate playbooks with lifecycle.stage=candidate")
    ap.add_argument(
        "--todo-out",
        default="artifacts/executor_logs/eval_sample_set_todos_latest.json",
        help="Write curated sample set TODOs here (missing sets, suggested strict-eligible task_ids).",
    )
    args = ap.parse_args()

    drafts_dir = (REPO_ROOT / str(args.drafts)).resolve()
    out_path = (REPO_ROOT / str(args.out)).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    patterns_dir = (REPO_ROOT / "patterns").resolve()
    patterns_by_id: Dict[str, Dict[str, Any]] = {}
    for p in _list_json_files(patterns_dir)[:600]:
        if p.name in {"auto_summary.json"}:
            continue
        try:
            obj = _load_json(p)
        except Exception:
            continue
        if isinstance(obj, dict) and obj.get("schema_version") == "scc.pattern.v1":
            pid = str(obj.get("pattern_id") or "").strip()
            if pid:
                patterns_by_id[pid] = obj

    events_path = (REPO_ROOT / "artifacts" / "executor_logs" / "state_events.jsonl").resolve()
    events = _read_jsonl_tail(events_path, tail=int(args.events_tail)) if events_path.exists() else []

    sample_sets_dir = (REPO_ROOT / str(args.sample_sets_dir)).resolve()

    known_metrics = {
        "timeout_rate_15m",
        "ci_failed_rate_15m",
        "p95_task_duration_s",
        "first_pass_rate",
        "avg_retries",
        "token_per_done",
        "time_per_done_s",
        "ci_failed_rate",
        "timeout_rate",
    }

    rows: List[Dict[str, Any]] = []
    todos: List[Dict[str, Any]] = []
    ok = True

    draft_files: List[pathlib.Path] = []
    if args.draft:
        for d in list(args.draft)[:50]:
            rel = str(d or "").strip().replace("\\", "/").lstrip("./")
            if not rel:
                continue
            p = (REPO_ROOT / rel).resolve()
            try:
                # Fail-closed: only allow drafts under the drafts_dir.
                p.relative_to(drafts_dir)
            except Exception:
                ok = False
                rows.append({"file": rel, "ok": False, "errors": ["draft_not_under_drafts_dir"]})
                continue
            if not p.exists():
                ok = False
                rows.append({"file": rel, "ok": False, "errors": ["draft_missing_file"]})
                continue
            draft_files.append(p)
    else:
        draft_files = _list_json_files(drafts_dir)[:200]

    for p in draft_files[:200]:
        rel = str(p.relative_to(REPO_ROOT)).replace("\\", "/")
        try:
            obj = _load_json(p)
        except Exception as e:
            ok = False
            rows.append({"file": rel, "ok": False, "errors": [f"json_parse_failed:{e}"]})
            continue

        errs = _validate_playbook_shape(obj)
        warnings: List[str] = []
        extra_errs: List[str] = []

        stage = _playbook_stage(obj)
        if args.candidates_only and stage != "candidate":
            rows.append({"file": rel, "ok": True, "skipped": True, "skip_reason": "candidates_only", "errors": [], "warnings": [], "samples": [], "curated_samples": [], "curated": None})
            continue

        pid = str(obj.get("pattern_id") or "").strip() if isinstance(obj, dict) else ""
        if pid and pid not in patterns_by_id:
            extra_errs.append("pattern_id_missing_in_patterns_dir")

        en = obj.get("enablement") if isinstance(obj, dict) else None
        if isinstance(en, dict):
            rcs = en.get("rollback_conditions")
            if isinstance(rcs, list):
                for rc in rcs[:20]:
                    if not isinstance(rc, dict):
                        continue
                    m = rc.get("metric")
                    if isinstance(m, str) and m.strip() and m.strip() not in known_metrics:
                        warnings.append(f"unknown_metric:{m.strip()}")

        samples: List[Dict[str, Any]] = []
        curated_samples: List[Dict[str, Any]] = []
        curated_meta: Dict[str, Any] | None = None
        if pid and sample_sets_dir.exists():
            pth = sample_sets_dir / f"{pid}.json"
            if pth.exists():
                try:
                    curated_meta = _load_json(pth)
                except Exception as e:
                    ok = False
                    rows.append({"file": rel, "ok": False, "errors": [f"curated_sample_set_parse_failed:{e}"], "warnings": warnings, "samples": [], "curated": str(pth.relative_to(REPO_ROOT)).replace("\\", "/")})
                    continue
                task_ids = curated_meta.get("task_ids") if isinstance(curated_meta, dict) else None
                strict_required = bool(curated_meta.get("strict_required", True)) if isinstance(curated_meta, dict) else True
                min_pass = int(curated_meta.get("min_pass", 1)) if isinstance(curated_meta, dict) else 1
                if not isinstance(task_ids, list) or not task_ids:
                    ok = False
                    rows.append({"file": rel, "ok": False, "errors": ["curated_sample_set_missing_task_ids"], "warnings": warnings, "samples": [], "curated": str(pth.relative_to(REPO_ROOT)).replace("\\", "/")})
                    continue
                for tid0 in task_ids[:10]:
                    tid = str(tid0).strip()
                    if not tid:
                        continue
                    if strict_required and not _task_strict_eligible(tid):
                        curated_samples.append({"task_id": tid, "ok": False, "error": "not_strict_eligible"})
                        continue
                    curated_samples.append(_run_gates_on_task(tid, strict=True, timeout_s=int(args.gates_timeout_s)))
                pass_n = sum(1 for s in curated_samples if s.get("ok") is True)
                if pass_n < min_pass:
                    extra_errs.append("curated_replay_smoke_failed")
            elif args.require_sample_set:
                # Emit TODO with strict-eligible suggestions to make it actionable.
                sug = _suggest_tasks_for_pattern(events, patterns_by_id.get(pid, {}), limit=5) if pid in patterns_by_id else []
                todos.append(
                    {
                        "pattern_id": pid,
                        "draft": rel,
                        "reason": "missing_curated_sample_set",
                        "suggested_task_ids": sug,
                    }
                )
                extra_errs.append("missing_curated_sample_set")

        if pid and pid in patterns_by_id and int(args.samples_per_playbook) > 0:
            pat = patterns_by_id[pid]
            seen: set[str] = set()
            for ev in reversed(events):
                if not _event_matches_pattern(ev, pat):
                    continue
                tid = ev.get("task_id")
                if not isinstance(tid, str) or not tid.strip():
                    continue
                if tid in seen:
                    continue
                seen.add(tid)
                if not _task_strict_eligible(tid):
                    continue
                samples.append(_run_gates_on_task(tid, strict=True, timeout_s=int(args.gates_timeout_s)))
                if len(samples) >= int(args.samples_per_playbook):
                    break
            if not samples:
                warnings.append("no_strict_eligible_historical_samples_found")
            if any(s.get("ok") is False for s in samples):
                extra_errs.append("historical_replay_smoke_failed")

        all_errs = [*errs, *extra_errs]
        if all_errs:
            ok = False
            rows.append({"file": rel, "ok": False, "errors": all_errs, "warnings": warnings, "samples": samples, "curated_samples": curated_samples, "curated": curated_meta})
        else:
            rows.append({"file": rel, "ok": True, "errors": [], "warnings": warnings, "samples": samples, "curated_samples": curated_samples, "curated": curated_meta})

    report = {
        "schema_version": "scc.eval_replay_report.v1",
        "t": _now_iso(),
        "mode": "offline_shape_plus_historical_replay_smoke",
        "drafts_dir": str(drafts_dir.relative_to(REPO_ROOT)).replace("\\", "/") if drafts_dir.exists() else None,
        "drafts": [str(p.relative_to(REPO_ROOT)).replace("\\", "/") for p in draft_files[:200]] if args.draft else None,
        "checked": len(rows),
        "ok": ok,
        "patterns_loaded": len(patterns_by_id),
        "events_source": str(events_path.relative_to(REPO_ROOT)).replace("\\", "/") if events_path.exists() else None,
        "results": rows,
    }
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # Best-effort: write TODOs to help close the loop without blocking learning.
    try:
        todo_path = (REPO_ROOT / str(args.todo_out)).resolve()
        todo_path.parent.mkdir(parents=True, exist_ok=True)
        todo_obj = {
            "schema_version": "scc.eval_sample_set_todos.v1",
            "t": _now_iso(),
            "require_sample_set": bool(args.require_sample_set),
            "candidates_only": bool(args.candidates_only),
            "count": len(todos),
            "todos": todos[:200],
        }
        todo_path.write_text(json.dumps(todo_obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except Exception:
        pass

    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
