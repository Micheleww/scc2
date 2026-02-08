#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib
import sys

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.scc.validators.contract_validator import validate_release_record_v1


def _load(path: pathlib.Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate a release record against minimal SCC contract checks.")
    ap.add_argument("--path", required=True, help="Path to releases/<id>/release.json")
    args = ap.parse_args()

    p = (_REPO_ROOT / str(args.path).replace("\\", "/").lstrip("./")).resolve()
    if not p.exists():
        print(f"FAIL: missing {p}")
        return 2

    obj = _load(p)
    errors = validate_release_record_v1(obj)
    if errors:
        print("FAIL")
        for e in errors[:50]:
            print(f"- {e}")
        return 1

    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

