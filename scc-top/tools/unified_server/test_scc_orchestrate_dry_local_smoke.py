#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Local smoke test: SCC dry-run orchestration endpoint.

This test does NOT start uvicorn; it uses FastAPI TestClient.
It must not trigger the SCC task worker even if SCC_TASK_AUTOSTART_ENABLED=true.
"""

import os
import sys
from pathlib import Path


def main() -> int:
    os.environ["PYTHONIOENCODING"] = "utf-8"
    os.environ["SCC_TASK_AUTOSTART_ENABLED"] = "true"
    os.environ["SCC_MODEL_ENABLED"] = "false"

    repo_root = Path(__file__).resolve().parent.parent.parent
    repo_root_str = str(repo_root)
    if repo_root_str not in sys.path:
        sys.path.insert(0, repo_root_str)

    from fastapi.testclient import TestClient
    from tools.unified_server.core.app_factory import create_app

    app = create_app()
    client = TestClient(app)

    payload = {
        "orchestrator": {"profile": "plan"},
        "task": {
            "goal": "Dry orchestrate smoke",
            "scope_allow": [],
            "success_criteria": ["endpoint returns ok"],
            "stop_condition": ["no worker execution"],
            "commands_hint": ["echo SHOULD_NOT_RUN"],
            "artifacts_expectation": [],
        },
        "workspace": {"repo_path": str(repo_root), "bootstrap_cmds": [], "test_cmds": [], "artifact_paths": []},
        "timeout_s": 1,
    }

    r = client.post("/scc/task/orchestrate", json=payload)
    if r.status_code != 200:
        raise RuntimeError(f"/scc/task/orchestrate failed: {r.status_code} {r.text}")
    data = r.json()
    assert data["ok"] is True
    task_id = data["task_id"]

    task_json = repo_root / "artifacts" / "scc_tasks" / task_id / "task.json"
    if not task_json.exists():
        raise RuntimeError(f"task.json missing: {task_json}")
    task = task_json.read_text(encoding="utf-8")
    if "\"status\": \"pending\"" not in task:
        raise RuntimeError(f"expected pending status; got task.json: {task_json}")

    evidence_dir = Path(data["evidence_dir"])
    if not (evidence_dir / "orchestrator_plan_graph.json").exists():
        raise RuntimeError("missing orchestrator_plan_graph.json")
    if not (evidence_dir / "tool_execution_plan.json").exists():
        raise RuntimeError("missing tool_execution_plan.json")

    print("DRY_ORCHESTRATE_SMOKE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
