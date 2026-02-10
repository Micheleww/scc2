#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib
from datetime import datetime, timezone
from typing import Any, Dict, List

from tools.scc.lib.utils import load_json


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: pathlib.Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Sync patterns/registry.json from patterns/*.json (deterministic).")
    ap.add_argument("--out", default="patterns/registry.json")
    args = ap.parse_args()

    patterns_dir = (REPO_ROOT / "patterns").resolve()
    out_path = (REPO_ROOT / str(args.out)).resolve()

    rows: List[Dict[str, str]] = []
    if patterns_dir.exists():
        for p in sorted(patterns_dir.glob("*.json"))[:800]:
            if p.name in {"auto_summary.json", "registry.json"}:
                continue
            try:
                obj = _load_json(p)
            except Exception:
                continue
            if not isinstance(obj, dict) or obj.get("schema_version") != "scc.pattern.v1":
                continue
            pid = str(obj.get("pattern_id") or "").strip()
            if not pid:
                continue
            rows.append({"pattern_id": pid, "path": str(p.relative_to(REPO_ROOT)).replace("\\", "/")})

    reg = {"schema_version": "scc.patterns_registry.v1", "updated_at": _now_iso(), "patterns": sorted(rows, key=lambda r: (r["pattern_id"], r["path"]))}
    _write_json(out_path, reg)
    print("OK")
    print(str(out_path.relative_to(REPO_ROOT)).replace("\\", "/"))
    print(f"patterns={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

