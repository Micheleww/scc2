#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Local smoke test: SCC fullagent (model-enabled) but executor dry-run.

Guarantees:
- No real model calls (SCC_EXECUTOR_DRY_RUN=true)
- No shell execution (SCC_FULLAGENT_ALLOW_SHELL=false)
"""

import os
import sys
from pathlib import Path


def main() -> int:
    os.environ["PYTHONIOENCODING"] = "utf-8"
    os.environ["SCC_MODEL_ENABLED"] = "true"
    os.environ["SCC_EXECUTOR_DRY_RUN"] = "true"
    os.environ["SCC_FULLAGENT_ALLOW_SHELL"] = "false"
    os.environ["SCC_TASK_AUTOSTART_ENABLED"] = "false"
    os.environ["SCC_FULLAGENT_MAX_STEPS"] = "3"
    os.environ["SCC_FULLAGENT_CREATE_EXEC_TASK"] = "true"

    repo_root = Path(__file__).resolve().parent.parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from fastapi.testclient import TestClient
    from tools.unified_server.core.app_factory import create_app

    app = create_app()
    client = TestClient(app)

    payload = {
        "orchestrator": {"profile": "fullagent"},
        "task": {
            "goal": "Fullagent dry smoke (no model call)",
            "scope_allow": [],
            "success_criteria": ["returns ok", "writes evidence"],
            "stop_condition": ["no shell execution"],
            "commands_hint": [],
            "artifacts_expectation": [],
        },
        "workspace": {"repo_path": str(repo_root), "bootstrap_cmds": [], "test_cmds": [], "artifact_paths": []},
        "timeout_s": 1,
    }

    r = client.post("/scc/task/orchestrate", json=payload)
    if r.status_code != 200:
        raise RuntimeError(f"fullagent /scc/task/orchestrate failed: {r.status_code} {r.text}")
    data = r.json()
    assert data["ok"] is True
    task_id = data["task_id"]
    steps = int(((data.get("fullagent") or {}) if isinstance(data.get("fullagent"), dict) else {}).get("history_steps") or 0)
    if steps < 1:
        raise RuntimeError(f"expected >=1 fullagent steps; got {steps}")
    exec_task_id = str(((data.get("fullagent") or {}) if isinstance(data.get("fullagent"), dict) else {}).get("exec_task_id") or "")
    if not exec_task_id:
        raise RuntimeError("expected exec_task_id")

    ev = Path(data["evidence_dir"])
    if not (ev / "fullagent_summary.json").exists():
        raise RuntimeError(f"missing evidence: {ev / 'fullagent_summary.json'}")
    steps_dir = ev / "fullagent_steps"
    if not steps_dir.exists():
        raise RuntimeError("missing evidence/fullagent_steps")
    todo_state = repo_root / "artifacts" / "scc_tasks" / task_id / "todo_state.json"
    if not todo_state.exists():
        raise RuntimeError(f"missing todo_state.json: {todo_state}")
    subtask_index = repo_root / "artifacts" / "scc_tasks" / task_id / "subtasks.json"
    if not subtask_index.exists():
        raise RuntimeError(f"missing subtasks.json: {subtask_index}")
    exec_task_json = repo_root / "artifacts" / "scc_tasks" / exec_task_id / "task.json"
    if not exec_task_json.exists():
        raise RuntimeError(f"missing exec task.json: {exec_task_json}")
    patches_dir = repo_root / "artifacts" / "scc_tasks" / task_id / "evidence" / "patches"
    if not patches_dir.exists():
        raise RuntimeError(f"missing evidence/patches: {patches_dir}")
    if not any(p.suffix == ".diff" for p in patches_dir.glob("*.diff")):
        raise RuntimeError("expected at least one .diff patch in evidence/patches")

    print("FULLAGENT_DRY_SMOKE_OK", task_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
