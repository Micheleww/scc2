#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Local smoke test: /scc/task/{task_id}/patches list + content APIs.
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

    task_id = "SMOKE-patches-api"
    pdir = (repo_root / "artifacts" / "scc_tasks" / task_id / "evidence" / "patches").resolve()
    pdir.mkdir(parents=True, exist_ok=True)
    patch_name = "p1.diff"
    patch_text = "diff --git a/x.txt b/x.txt\n--- a/x.txt\n+++ b/x.txt\n@@ -0,0 +1 @@\n+hello\n"
    (pdir / patch_name).write_text(patch_text, encoding="utf-8")

    r1 = client.get(f"/scc/task/{task_id}/patches")
    if r1.status_code != 200:
        raise RuntimeError(r1.text)
    data1 = r1.json()
    assert data1["ok"] is True
    names = [x.get("name") for x in data1.get("items") or []]
    if patch_name not in names:
        raise RuntimeError("patch not listed")

    r2 = client.get(f"/scc/task/{task_id}/patches/{patch_name}")
    if r2.status_code != 200:
        raise RuntimeError(r2.text)
    data2 = r2.json()
    assert data2["ok"] is True
    if "hello" not in str(data2.get("patch_text") or ""):
        raise RuntimeError("patch content mismatch")

    print("TASK_PATCHES_API_SMOKE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

