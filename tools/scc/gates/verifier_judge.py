from __future__ import annotations

import json
import pathlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _norm_rel(p: str) -> str:
    return str(p or "").replace("\\", "/").lstrip("./")


def _gate_failures(gate_rows: List[Dict[str, Any]]) -> List[str]:
    out: List[str] = []
    for r in gate_rows:
        if not isinstance(r, dict):
            continue
        gate = str(r.get("gate") or "")
        status = str(r.get("status") or "")
        if status in {"FAIL", "ERROR"}:
            out.append(f"gate:{gate}:{status}")
    return out


def judge(repo: pathlib.Path, submit: Dict[str, Any], gate_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    task_id = str(submit.get("task_id") or "").strip() or "unknown"
    submit_status = str(submit.get("status") or "").strip()
    exit_code = submit.get("exit_code")
    tests = submit.get("tests") if isinstance(submit.get("tests"), dict) else {}
    tests_passed = tests.get("passed") if isinstance(tests, dict) else None

    reasons: List[str] = []
    actions: List[Dict[str, Any]] = []

    if submit_status == "NEED_INPUT":
        reasons.append("submit:NEED_INPUT")
        needs = submit.get("needs_input") if isinstance(submit.get("needs_input"), list) else []
        actions.append({"type": "needs_input", "notes": f"needs_input={json.dumps(needs[:20], ensure_ascii=False)}"})
        verdict = "ESCALATE"
        return {"schema_version": "scc.verdict.v1", "task_id": task_id, "verdict": verdict, "reasons": reasons, "actions": actions}

    failures = _gate_failures(gate_rows)
    reasons += failures

    if submit_status != "DONE":
        reasons.append(f"submit_status:{submit_status or 'missing'}")
    if isinstance(exit_code, int) and exit_code != 0:
        reasons.append(f"exit_code:{exit_code}")
    if isinstance(tests_passed, bool) and tests_passed is False:
        reasons.append("tests:failed")

    gate_names_failed = {f.split(":")[1] for f in failures if f.startswith("gate:") and len(f.split(":")) >= 3}
    if "map" in gate_names_failed:
        actions.append({"type": "rebuild_map", "notes": "Map gate failed; rebuild map/map.json and map/version.json."})
    if "schema" in gate_names_failed:
        actions.append({"type": "fix_schema_registry", "notes": "Schema gate failed; fix roles/skills/contracts registries."})
    if "ssot_map" in gate_names_failed:
        actions.append({"type": "sync_ssot", "notes": "SSOT drift detected; apply artifacts/<task_id>/ssot_update.json suggestions."})
    if "doclink" in gate_names_failed:
        actions.append({"type": "update_docs", "notes": "DocLink gate failed; add/update doc references in docs/."})
    if "hygiene" in gate_names_failed:
        actions.append({"type": "fix_hygiene", "notes": "Hygiene gate failed; ensure required artifacts and scope compliance."})

    gates_ok = not failures
    submit_ok = submit_status == "DONE" and (not isinstance(exit_code, int) or exit_code == 0) and (not isinstance(tests_passed, bool) or tests_passed is True)
    if gates_ok and submit_ok:
        verdict = "DONE"
    else:
        verdict = "RETRY"
        if not actions:
            actions.append({"type": "retry", "notes": "Not DONE; retry with fixups (pins/ci/policy) based on failing reasons."})

    return {"schema_version": "scc.verdict.v1", "task_id": task_id, "verdict": verdict, "reasons": reasons, "actions": actions}


def write(repo: pathlib.Path, verdict: Dict[str, Any]) -> pathlib.Path:
    task_id = str(verdict.get("task_id") or "").strip() or "unknown"
    out_dir = repo / "artifacts" / task_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "verdict.json"
    out_path.write_text(json.dumps(verdict, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out_path


def write_log(repo: pathlib.Path, task_id: str, verdict: Dict[str, Any]) -> None:
    # Best-effort append to executor_logs/verdicts.jsonl for trending.
    try:
        log = repo / "artifacts" / "executor_logs" / "verdicts.jsonl"
        log.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "t": datetime.now(timezone.utc).isoformat(),
            "task_id": task_id,
            "verdict": verdict.get("verdict"),
            "reasons": verdict.get("reasons"),
        }
        with log.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        return

