import json
import pathlib


def _load_rows(path: pathlib.Path, max_lines: int = 2000) -> list[dict]:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except Exception:
        return []
    rows: list[dict] = []
    for ln in text.splitlines()[-max_lines:]:
        s = ln.strip()
        if not s:
            continue
        try:
            obj = json.loads(s)
        except Exception:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def run(repo: pathlib.Path, submit: dict) -> list[str]:
    task_id = str(submit.get("task_id") or "unknown")
    events_path = repo / "artifacts" / task_id / "events.jsonl"
    if not events_path.exists():
        cmd = f"python tools/scc/ops/backfill_events_v1.py --repo-root {repo.as_posix()} --task-id {task_id}"
        return [
            "missing artifacts/<task_id>/events.jsonl (must emit at least one scc.event.v1 SUCCESS/FAIL event)",
            f"migration_hint: run `{cmd}` to backfill legacy artifacts for strict event gating",
        ]

    rows = _load_rows(events_path)
    allowed = {"SUCCESS", "PINS_INSUFFICIENT", "PREFLIGHT_FAILED", "CI_FAILED", "EXECUTOR_ERROR", "RETRY_EXHAUSTED", "POLICY_VIOLATION"}
    ok = False
    for r in rows:
        if r.get("schema_version") != "scc.event.v1":
            continue
        if str(r.get("task_id") or "") != task_id:
            continue
        et = str(r.get("event_type") or "")
        if et in allowed:
            ok = True
            break
    if not ok:
        return ["events.jsonl has no valid scc.event.v1 event for this task_id"]
    return []
