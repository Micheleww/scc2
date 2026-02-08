#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Local smoke test: SCC chat store APIs (create/append/snapshot/tail).
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

    r = client.post("/scc/chat/new", json={"title": "smoke"})
    if r.status_code != 200:
        raise RuntimeError(r.text)
    d = r.json()
    assert d["ok"] is True
    chat_id = d["chat_id"]

    client.post(f"/scc/chat/{chat_id}/append", json={"role": "user", "content": "hi"})
    client.post(f"/scc/chat/{chat_id}/append", json={"role": "assistant", "content": "hello"})

    r2 = client.get(f"/scc/chat/{chat_id}/snapshot?tail=10")
    if r2.status_code != 200:
        raise RuntimeError(r2.text)
    d2 = r2.json()
    assert d2["ok"] is True
    msgs = d2.get("messages") or []
    if len(msgs) < 2:
        raise RuntimeError("snapshot missing messages")

    r3 = client.get(f"/scc/chat/{chat_id}/messages/tail?cursor=&max_bytes=1024&max_lines=10")
    if r3.status_code != 200:
        raise RuntimeError(r3.text)
    d3 = r3.json()
    assert d3["ok"] is True
    if len(d3.get("lines") or []) < 2:
        raise RuntimeError("tail missing lines")

    print("SCC_CHAT_STORE_SMOKE_OK", chat_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

