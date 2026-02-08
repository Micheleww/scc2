#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib
from datetime import datetime, timezone
from typing import Any


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: pathlib.Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8").lstrip("\ufeff"))


def _write_json(path: pathlib.Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Set playbook lifecycle.stage for drafts (deterministic).")
    ap.add_argument("--draft", required=True, help="Draft playbook path under playbooks/drafts/")
    ap.add_argument("--stage", required=True, choices=["draft", "candidate"], help="Target lifecycle stage")
    args = ap.parse_args()

    draft = (REPO_ROOT / str(args.draft)).resolve()
    drafts_dir = (REPO_ROOT / "playbooks" / "drafts").resolve()
    try:
        draft.relative_to(drafts_dir)
    except Exception:
        print("FAIL: --draft must be under playbooks/drafts/")
        return 2
    if not draft.exists():
        print(f"FAIL: missing draft {draft}")
        return 2

    obj = _load_json(draft)
    if not isinstance(obj, dict) or obj.get("schema_version") != "scc.playbook.v1":
        print("FAIL: not a scc.playbook.v1")
        return 2

    lifecycle = obj.get("lifecycle") if isinstance(obj.get("lifecycle"), dict) else {}
    lifecycle["stage"] = str(args.stage)
    lifecycle["updated_at"] = _now_iso()
    obj["lifecycle"] = lifecycle
    _write_json(draft, obj)

    print("OK")
    print(str(draft.relative_to(REPO_ROOT)).replace("\\", "/"))
    print(f"stage={args.stage}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

