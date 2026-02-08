#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Local smoke test: when a child task completes, SCC records a summary into the parent evidence folder.

This test avoids running the SCC worker and avoids executing shell commands.
"""

import json
import os
import sys
from pathlib import Path


def main() -> int:
    os.environ["PYTHONIOENCODING"] = "utf-8"
    os.environ["SCC_TASK_AUTOSTART_ENABLED"] = "false"

    repo_root = Path(__file__).resolve().parent.parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from tools.scc.task_queue import SCCTaskQueue
    from tools.scc.orchestrators.subtask_summary import record_subtask_summary

    q = SCCTaskQueue(repo_root=repo_root)

    parent_id = "SMOKE-parent"
    child_id = "SMOKE-child"

    q.submit_with_task_id(
        task_id=parent_id,
        payload={"task": {"goal": "parent"}, "workspace": {"repo_path": str(repo_root), "test_cmds": []}},
        autostart=False,
    )
    q.submit_with_task_id(
        task_id=child_id,
        payload={
            "task": {"goal": "child"},
            "workspace": {"repo_path": str(repo_root), "test_cmds": []},
            "meta": {"parent_task_id": parent_id, "task_type": "explore"},
        },
        autostart=False,
    )

    # Simulate "completed child" artifacts
    child_dir = repo_root / "artifacts" / "scc_tasks" / child_id
    task_json = child_dir / "task.json"
    data = json.loads(task_json.read_text(encoding="utf-8"))
    data["status"] = "done"
    data["verdict"] = "PASS"
    data["run_id"] = "SMOKE-run"
    data["exit_code"] = 0
    child_dir.mkdir(parents=True, exist_ok=True)
    task_json.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    out = record_subtask_summary(repo_root=repo_root, parent_task_id=parent_id, child_task_id=child_id)
    if not out or not out.exists():
        raise RuntimeError("expected parent subtask summary file")

    print("SUBTASK_SUMMARY_SMOKE_OK", str(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

