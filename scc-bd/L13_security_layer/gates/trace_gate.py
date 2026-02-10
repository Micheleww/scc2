import os
import pathlib

from tools.scc.validators.contract_validator import load_json, validate_trace_v1


def run(repo: pathlib.Path, submit: dict) -> dict:
    task_id = str(submit.get("task_id") or "unknown")
    required = str(os.environ.get("TRACE_REQUIRED") or "false").strip().lower() in {"1", "true", "yes", "on"}
    trace_path = repo / "artifacts" / task_id / "trace.json"
    if not trace_path.exists():
        if required:
            return {"errors": ["missing artifacts/<task_id>/trace.json"], "warnings": []}
        return {"errors": [], "warnings": ["missing artifacts/<task_id>/trace.json (set TRACE_REQUIRED=true to fail-closed)"]}

    try:
        obj = load_json(trace_path)
    except Exception as e:
        return {"errors": [f"trace.json parse failed: {e}"], "warnings": []}

    errs = validate_trace_v1(obj)
    if errs:
        return {"errors": errs[:50], "warnings": []}
    return {"errors": [], "warnings": []}

