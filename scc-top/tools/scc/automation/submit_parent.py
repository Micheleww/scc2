#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Append one parent task to SCC parent inbox (JSONL).
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True)
    ap.add_argument("--description", required=True)
    ap.add_argument("--inbox", default=os.environ.get("SCC_PARENT_INBOX", "artifacts/scc_state/parent_inbox.jsonl"))
    args = ap.parse_args()

    repo_root = _repo_root()
    inbox = Path(args.inbox)
    if not inbox.is_absolute():
        inbox = (repo_root / inbox).resolve()
    inbox.parent.mkdir(parents=True, exist_ok=True)

    obj = {
        "id": str(args.id).strip(),
        "description": str(args.description).strip(),
        "submitted_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if not obj["id"] or not obj["description"]:
        raise SystemExit(2)

    with open(inbox, "a", encoding="utf-8", errors="replace") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")

    print(str(inbox))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

