#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Local smoke test for Executor parallel probe (token-free).

This does NOT start uvicorn; it uses the ExecutorService FastAPI app directly.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path


async def _amain() -> int:
    os.environ["PYTHONIOENCODING"] = "utf-8"

    repo_root = Path(__file__).resolve().parent.parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from fastapi.testclient import TestClient
    from tools.unified_server.services.executor_service import ExecutorService

    svc = ExecutorService(name="executor", enabled=True, repo_root=repo_root, path="/executor")
    await svc.initialize()
    app = svc.get_app()
    client = TestClient(app)

    r = client.post("/codex/parallel_probe", json={"n": 7, "max_outstanding": 3, "sleep_ms": 120})
    if r.status_code != 200:
        raise RuntimeError(r.text)
    d = r.json()
    assert d.get("ok") is True
    assert int(d.get("n") or 0) == 7
    assert int(d.get("max_outstanding") or 0) == 3
    assert int(d.get("max_concurrency_seen") or 0) <= 3
    assert int(d.get("finished_count") or 0) == 7

    print("EXECUTOR_PARALLEL_PROBE_SMOKE_OK")
    return 0


def main() -> int:
    return asyncio.run(_amain())


if __name__ == "__main__":
    raise SystemExit(main())

