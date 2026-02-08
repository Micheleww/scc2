#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib
from datetime import datetime, timezone
from typing import Any, Dict, List


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: pathlib.Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8").lstrip("\ufeff"))


def _write_json(path: pathlib.Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Sync skills_drafts/registry.json from skills_drafts/*.json (deterministic).")
    ap.add_argument("--out", default="skills_drafts/registry.json")
    args = ap.parse_args()

    drafts_dir = (REPO_ROOT / "skills_drafts").resolve()
    out_path = (REPO_ROOT / str(args.out)).resolve()

    rows: List[Dict[str, str]] = []
    if drafts_dir.exists():
        for p in sorted(drafts_dir.glob("*.json"))[:800]:
            if p.name == "registry.json":
                continue
            try:
                obj = _load_json(p)
            except Exception:
                continue
            if not isinstance(obj, dict) or obj.get("schema_version") != "scc.skill.v1":
                continue
            sid = str(obj.get("skill_id") or "").strip()
            if not sid:
                continue
            rows.append({"skill_id": sid, "path": str(p.relative_to(REPO_ROOT)).replace("\\", "/")})

    reg = {"schema_version": "scc.skills_drafts_registry.v1", "updated_at": _now_iso(), "skills": sorted(rows, key=lambda r: (r["skill_id"], r["path"]))}
    _write_json(out_path, reg)
    print("OK")
    print(str(out_path.relative_to(REPO_ROOT)).replace("\\", "/"))
    print(f"skills_drafts={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

