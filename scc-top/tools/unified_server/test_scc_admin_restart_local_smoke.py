#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Local smoke test for /scc/admin/restart (dry-run).

IMPORTANT: This test must not terminate the process.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    os.environ["PYTHONIOENCODING"] = "utf-8"
    os.environ["SCC_DISABLE_SELF_RESTART"] = "true"

    repo_root = Path(__file__).resolve().parent.parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from fastapi.testclient import TestClient
    from tools.unified_server.core.app_factory import create_app

    app = create_app()
    client = TestClient(app)

    r = client.post("/scc/admin/restart", json={"reason": "smoke", "delay_s": 0.1})
    if r.status_code != 200:
        raise RuntimeError(r.text)
    d = r.json()
    assert d.get("ok") is True
    assert d.get("scheduled") is False
    assert "request_file" in d

    print("SCC_ADMIN_RESTART_SMOKE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

