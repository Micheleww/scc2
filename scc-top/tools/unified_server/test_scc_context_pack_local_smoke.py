#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Local smoke test: /scc/chat/{chat_id}/context_pack
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

    r = client.post("/scc/chat/new", json={"title": "context-pack-smoke"})
    if r.status_code != 200:
        raise RuntimeError(r.text)
    chat_id = r.json()["chat_id"]

    client.post(f"/scc/chat/{chat_id}/append", json={"role": "user", "content": "hello"})
    client.post(f"/scc/chat/{chat_id}/append", json={"role": "assistant", "content": "hi"})

    payload = {
        "tail": 10,
        "repo_path": str(repo_root),
        "pin_items": [{"path": "tools/scc/task_runner.py", "kind": "range", "start_line": 1, "end_line": 30}],
        "include_pin_content": True,
        "max_chars_per_pin": 2000,
        "max_total_pin_chars": 3000,
    }
    r2 = client.post(f"/scc/chat/{chat_id}/context_pack", json=payload)
    if r2.status_code != 200:
        raise RuntimeError(r2.text)
    d2 = r2.json()
    assert d2["ok"] is True
    assert d2["chat_id"] == chat_id
    assert len(d2.get("messages") or []) >= 2
    assert len(d2.get("pins") or []) >= 1
    assert isinstance(d2.get("stats") or {}, dict)

    print("SCC_CONTEXT_PACK_SMOKE_OK", chat_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

