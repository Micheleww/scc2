#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Smoke: validate default automation config is readable and well-formed (no network).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[3]
    cfg = (repo_root / "configs" / "scc" / "parent_batches.v1.json").resolve()
    raw = json.loads(cfg.read_text(encoding="utf-8", errors="replace") or "{}")
    assert raw.get("version") == "scc_parent_batches_v1"
    batches = raw.get("batches")
    assert isinstance(batches, list) and len(batches) == 3
    for b in batches:
        parents = (b.get("parents") or {}).get("parents")
        assert isinstance(parents, list) and len(parents) == 5
        for it in parents:
            assert isinstance(it.get("id"), str) and it["id"].strip()
            assert isinstance(it.get("description"), str) and it["description"].strip()
    print("SCC_AUTOMATION_CONFIG_SMOKE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

