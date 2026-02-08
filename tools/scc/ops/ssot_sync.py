#!/usr/bin/env python3
from __future__ import annotations

import argparse
import difflib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8").lstrip("\ufeff"))


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_patch(path: Path, before_text: str, after_text: str, label_before: str, label_after: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    diff = difflib.unified_diff(
        before_text.splitlines(keepends=True),
        after_text.splitlines(keepends=True),
        fromfile=label_before,
        tofile=label_after,
    )
    path.write_text("".join(diff), encoding="utf-8")


def _uniq_sorted(xs: List[str]) -> List[str]:
    out = sorted({str(x).strip() for x in xs if isinstance(x, str) and str(x).strip()})
    return out


def _apply_update(registry: Dict[str, Any], update: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    reg_facts = registry.get("facts") if isinstance(registry.get("facts"), dict) else {}
    missing = update.get("missing") if isinstance(update.get("missing"), dict) else {}
    stale = update.get("stale") if isinstance(update.get("stale"), dict) else {}

    out = dict(registry)
    out.setdefault("schema_version", "scc.ssot_registry.v1")
    out["updated_at"] = datetime.now(timezone.utc).date().isoformat()

    sources = update.get("sources") if isinstance(update.get("sources"), dict) else None
    if sources:
        out["sources"] = {
            "map_path": str(sources.get("map_path") or "map/map.json"),
            "map_hash": str(sources.get("map_hash") or ""),
            "facts_hash": str(sources.get("facts_hash") or ""),
        }

    next_facts = {
        "modules": _uniq_sorted([*(reg_facts.get("modules") or []), *(missing.get("modules") or [])]),
        "entry_points": _uniq_sorted([*(reg_facts.get("entry_points") or []), *(missing.get("entry_points") or [])]),
        "contracts": _uniq_sorted([*(reg_facts.get("contracts") or []), *(missing.get("contracts") or [])]),
    }

    stale_modules = {str(x) for x in (stale.get("modules") or []) if isinstance(x, str)}
    stale_entry = {str(x) for x in (stale.get("entry_points") or []) if isinstance(x, str)}
    stale_contracts = {str(x) for x in (stale.get("contracts") or []) if isinstance(x, str)}
    next_facts["modules"] = [x for x in next_facts["modules"] if x not in stale_modules]
    next_facts["entry_points"] = [x for x in next_facts["entry_points"] if x not in stale_entry]
    next_facts["contracts"] = [x for x in next_facts["contracts"] if x not in stale_contracts]

    out["facts"] = next_facts

    summary = {
        "added": {
            "modules": _uniq_sorted(list(set(next_facts["modules"]) - set(_uniq_sorted(reg_facts.get("modules") or [])))),
            "entry_points": _uniq_sorted(list(set(next_facts["entry_points"]) - set(_uniq_sorted(reg_facts.get("entry_points") or [])))),
            "contracts": _uniq_sorted(list(set(next_facts["contracts"]) - set(_uniq_sorted(reg_facts.get("contracts") or [])))),
        },
        "removed": {"modules": _uniq_sorted(list(stale_modules)), "entry_points": _uniq_sorted(list(stale_entry)), "contracts": _uniq_sorted(list(stale_contracts))},
    }
    return out, summary


def main() -> int:
    ap = argparse.ArgumentParser(description="Apply artifacts/<task_id>/ssot_update.json to docs/SSOT/registry.json (deterministic).")
    ap.add_argument("--repo-root", default="C:/scc")
    ap.add_argument("--task-id", required=True)
    ap.add_argument("--registry", default="docs/SSOT/registry.json")
    ap.add_argument("--apply", action="store_true", help="Write changes to registry (default: dry-run)")
    ap.add_argument("--patch-out", default="", help="Write unified diff patch (default: artifacts/<task_id>/ssot_update.patch)")
    args = ap.parse_args()

    repo = Path(args.repo_root).resolve()
    task_id = str(args.task_id).strip()
    if not task_id:
        print("FAIL: missing --task-id")
        return 2

    update_path = repo / "artifacts" / task_id / "ssot_update.json"
    if not update_path.exists():
        print(f"FAIL: missing {update_path.as_posix()}")
        return 2

    reg_path = repo / str(args.registry)
    if not reg_path.exists():
        print(f"FAIL: missing registry file {reg_path.as_posix()}")
        return 2

    update = _read_json(update_path)
    reg = _read_json(reg_path)
    next_reg, summary = _apply_update(reg if isinstance(reg, dict) else {}, update if isinstance(update, dict) else {})

    before_text = json.dumps(reg, ensure_ascii=False, indent=2) + "\n"
    after_text = json.dumps(next_reg, ensure_ascii=False, indent=2) + "\n"
    patch_rel_default = f"artifacts/{task_id}/ssot_update.patch"
    patch_rel = str(args.patch_out).strip() or patch_rel_default
    patch_path = (repo / patch_rel).resolve() if not Path(patch_rel).is_absolute() else Path(patch_rel)
    _write_patch(patch_path, before_text, after_text, str(reg_path.relative_to(repo)).replace("\\", "/"), str(reg_path.relative_to(repo)).replace("\\", "/"))

    print(
        json.dumps(
            {
                "ok": True,
                "task_id": task_id,
                "update": str(update_path.relative_to(repo)).replace("\\", "/"),
                "registry": str(reg_path.relative_to(repo)).replace("\\", "/"),
                "patch": str(patch_path.relative_to(repo)).replace("\\", "/") if patch_path.is_relative_to(repo) else str(patch_path),
                "summary": summary,
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    if args.apply:
        _write_json(reg_path, next_reg)
        print(f"WROTE: {reg_path.as_posix()}")
    else:
        print("DRY_RUN: pass --apply to write registry.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
