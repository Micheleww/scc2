#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from tools.scc.lib.utils import load_json


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: pathlib.Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _list_playbook_files(playbooks_dir: pathlib.Path) -> List[pathlib.Path]:
    if not playbooks_dir.exists():
        return []
    out: List[pathlib.Path] = []
    for p in sorted(playbooks_dir.glob("*.json")):
        if p.name in {"overrides.json"}:
            continue
        out.append(p)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Sync playbooks/registry.json from playbooks/*.json (deterministic).")
    ap.add_argument("--out", default="playbooks/registry.json")
    args = ap.parse_args()

    playbooks_dir = (REPO_ROOT / "playbooks").resolve()
    out_path = (REPO_ROOT / str(args.out)).resolve()

    rows: List[Dict[str, str]] = []
    for p in _list_playbook_files(playbooks_dir)[:400]:
        try:
            obj = _load_json(p)
        except Exception:
            continue
        if not isinstance(obj, dict) or obj.get("schema_version") != "scc.playbook.v1":
            continue
        pid = str(obj.get("playbook_id") or "").strip()
        if not pid:
            continue
        rows.append({"playbook_id": pid, "path": str(p.relative_to(REPO_ROOT)).replace("\\", "/")})

    reg = {"schema_version": "scc.playbooks_registry.v1", "updated_at": _now_iso(), "playbooks": sorted(rows, key=lambda r: (r["playbook_id"], r["path"]))}
    _write_json(out_path, reg)
    print("OK")
    print(str(out_path.relative_to(REPO_ROOT)).replace("\\", "/"))
    print(f"playbooks={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

