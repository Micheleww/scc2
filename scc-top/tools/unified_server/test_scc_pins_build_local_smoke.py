#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Local smoke test: /scc/pins/build
"""

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

    payload = {
        "repo_path": str(repo_root),
        "items": [
            {"path": "tools/scc/task_runner.py", "kind": "range", "start_line": 1, "end_line": 60, "label": "task_runner_head"},
            {"path": "docs/arch/project_navigation__v0.1.0__ACTIVE__20260115.md", "kind": "file", "label": "nav"},
        ],
        "include_content": True,
        "max_chars_per_item": 2000,
        "max_total_chars": 3000,
    }
    r = client.post("/scc/pins/build", json=payload)
    if r.status_code != 200:
        raise RuntimeError(r.text)
    d = r.json()
    assert d["ok"] is True
    pins = d.get("pins") or []
    if len(pins) < 1:
        raise RuntimeError("no pins returned")
    if not any("task_runner.py" in (p.get("path") or "") for p in pins):
        raise RuntimeError("expected task_runner pin missing")

    print("SCC_PINS_BUILD_SMOKE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

