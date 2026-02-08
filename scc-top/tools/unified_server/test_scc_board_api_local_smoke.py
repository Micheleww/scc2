#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Local smoke test for SCC "board-critical" APIs:
- /scc/task/{task_id}/events/tail cursor semantics
- /scc/tasks pagination/filtering
- /scc/task/{task_id}/subtask_summaries list + read
"""

import json
import os
import sys
from pathlib import Path


def main() -> int:
    os.environ["PYTHONIOENCODING"] = "utf-8"

    repo_root = Path(__file__).resolve().parent.parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from fastapi.testclient import TestClient
    from tools.unified_server.core.app_factory import create_app

    app = create_app()
    client = TestClient(app)

    # --- events/tail ---
    task_id = "SMOKE-board-api"
    events_path = (repo_root / "artifacts" / "scc_tasks" / task_id / "events.jsonl").resolve()
    events_path.parent.mkdir(parents=True, exist_ok=True)
    events_path.write_text("", encoding="utf-8")

    def append_evt(i: int) -> None:
        with open(events_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"type": "t", "ts_utc": "x", "data": {"i": i}}, ensure_ascii=False) + "\n")

    append_evt(1)
    append_evt(2)

    r = client.get(f"/scc/task/{task_id}/events/tail?cursor=&max_bytes=1024&max_lines=100")
    if r.status_code != 200:
        raise RuntimeError(r.text)
    d = r.json()
    assert d["ok"] is True
    assert isinstance(d.get("cursor"), int)
    assert len(d.get("lines") or []) >= 2
    c1 = int(d["cursor"])

    append_evt(3)
    r2 = client.get(f"/scc/task/{task_id}/events/tail?cursor={c1}&max_bytes=1024&max_lines=100")
    if r2.status_code != 200:
        raise RuntimeError(r2.text)
    d2 = r2.json()
    assert d2["ok"] is True
    lines2 = d2.get("lines") or []
    if not any('"i": 3' in ln for ln in lines2):
        raise RuntimeError("events/tail did not return appended event")

    # --- subtask_summaries list/read ---
    sdir = (repo_root / "artifacts" / "scc_tasks" / task_id / "evidence" / "subtask_summaries").resolve()
    sdir.mkdir(parents=True, exist_ok=True)
    sname = "child_1.json"
    (sdir / sname).write_text(json.dumps({"child_task_id": "C1", "status": "done"}, ensure_ascii=False), encoding="utf-8")

    r3 = client.get(f"/scc/task/{task_id}/subtask_summaries?limit=20")
    if r3.status_code != 200:
        raise RuntimeError(r3.text)
    d3 = r3.json()
    assert d3["ok"] is True
    names = [x.get("name") for x in (d3.get("items") or [])]
    if sname not in names:
        raise RuntimeError("subtask summary not listed")

    r4 = client.get(f"/scc/task/{task_id}/subtask_summaries/{sname}")
    if r4.status_code != 200:
        raise RuntimeError(r4.text)
    d4 = r4.json()
    assert d4["ok"] is True
    if "child_task_id" not in str(d4.get("json_text") or ""):
        raise RuntimeError("subtask summary content mismatch")

    # --- /scc/tasks ---
    troot = (repo_root / "artifacts" / "scc_tasks").resolve()
    troot.mkdir(parents=True, exist_ok=True)

    def write_task(tid: str, status: str, goal: str) -> None:
        d = (troot / tid).resolve()
        d.mkdir(parents=True, exist_ok=True)
        payload = {"task": {"goal": goal}}
        rec = {
            "task_id": tid,
            "created_utc": "x",
            "updated_utc": "x",
            "status": status,
            "request": payload,
            "run_id": None,
            "exit_code": None,
            "verdict": None,
            "out_dir": None,
            "selftest_log": None,
            "report_md": None,
            "evidence_dir": None,
            "error": None,
        }
        (d / "task.json").write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")

    write_task("SMOKE-ZZZ", "done", "goal zzz")
    write_task("SMOKE-YYY", "pending", "goal yyy")

    # --- patches/index should not be shadowed by /patches/{name} ---
    r8 = client.get("/scc/task/SMOKE-ZZZ/patches/index")
    if r8.status_code != 200:
        raise RuntimeError(r8.text)
    d8 = r8.json()
    assert d8.get("ok") is True
    idx = d8.get("index") or {}
    assert isinstance(idx.get("items") or [], list)

    r5 = client.get("/scc/tasks?limit=1&q=goal")
    if r5.status_code != 200:
        raise RuntimeError(r5.text)
    d5 = r5.json()
    assert d5["ok"] is True
    assert len(d5.get("items") or []) == 1
    nxt = d5.get("next_after")
    if not nxt:
        raise RuntimeError("next_after missing")

    r6 = client.get(f"/scc/tasks?limit=10&after={nxt}")
    if r6.status_code != 200:
        raise RuntimeError(r6.text)
    d6 = r6.json()
    assert d6["ok"] is True

    r7 = client.get("/scc/tasks?limit=50&status=done&q=zzz")
    if r7.status_code != 200:
        raise RuntimeError(r7.text)
    d7 = r7.json()
    assert d7["ok"] is True
    if not any(str(it.get("task_id")) == "SMOKE-ZZZ" for it in (d7.get("items") or [])):
        raise RuntimeError("status/q filtering failed")

    print("SCC_BOARD_API_SMOKE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
