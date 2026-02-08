#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OID_REGISTER_INLINE_GLOB_V010 — register/sync inline OIDs into Postgres for a deterministic file set.

Goal:
- Fix `oid_missing_in_registry` for durable JSON artifacts (e.g., generated contracts) by inserting
  existing inline OIDs into the Postgres registry without changing the inline oid.

Notes:
- This is an explicit, opt-in scan over caller-provided globs (NOT a repo-wide scan).
- Uses `register_existing` (records IMPORTED/SYNCED events).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.scc.oid.pg_registry import get_oid_pg_dsn, register_existing
from tools.scc.oid.ulid import ulid_is_placeholder, ulid_is_valid


def _repo_root() -> Path:
    return _REPO_ROOT


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _date_utc() -> str:
    return time.strftime("%Y%m%d", time.gmtime())


def _stamp_utc() -> str:
    return time.strftime("%Y%m%d-%H%M%SZ", time.gmtime())


def _to_repo_rel(repo_root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve())).replace("\\", "/")
    except Exception:
        return str(path).replace("\\", "/")


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace") or "{}")
    except Exception:
        return {}


def _kind_for_path(path: Path) -> str:
    return (path.suffix or "").lstrip(".").lower() or "file"


def main() -> int:
    ap = argparse.ArgumentParser(description="Register existing inline OIDs into Postgres (glob-scoped).")
    ap.add_argument("--glob", action="append", default=["docs/ssot/04_contracts/generated/*.json"])
    ap.add_argument("--dsn", default="", help="Optional Postgres DSN (else env SCC_OID_PG_DSN).")
    ap.add_argument("--area", default="control_plane")
    ap.add_argument("--taskcode", default="OID_REGISTER_INLINE_GLOB_V010")
    ap.add_argument("--report-dir", default="", help="Optional report dir override.")
    args = ap.parse_args()

    repo_root = _repo_root()
    dsn = str(args.dsn or "").strip() or get_oid_pg_dsn()
    if not dsn:
        print(json.dumps({"ok": False, "error": "missing_pg_dsn"}, ensure_ascii=False, indent=2))
        return 2

    paths: List[Path] = []
    for g in args.glob or []:
        gg = str(g or "").strip()
        if not gg:
            continue
        for p in repo_root.glob(gg):
            if p.is_file():
                paths.append(p.resolve())
    # stable de-dupe
    seen: set[str] = set()
    uniq: List[Path] = []
    for p in sorted(paths, key=lambda x: str(x)):
        rel = _to_repo_rel(repo_root, p)
        if rel in seen:
            continue
        seen.add(rel)
        uniq.append(p)
    paths = uniq

    rows: List[Dict[str, Any]] = []
    errors: List[Dict[str, str]] = []
    inserted = 0
    updated = 0
    noop = 0

    for p in paths:
        rel = _to_repo_rel(repo_root, p)
        obj = _read_json(p)
        if not isinstance(obj, dict):
            errors.append({"path": rel, "error": "json_not_object"})
            continue
        oid = str(obj.get("oid") or "").strip()
        if ulid_is_placeholder(oid) or not ulid_is_valid(oid):
            errors.append({"path": rel, "error": f"invalid_or_placeholder_oid:{oid}"})
            continue
        layer = str(obj.get("layer") or "").strip() or "CANON"
        primary_unit = str(obj.get("primary_unit") or "").strip() or "V.GUARD"
        tags = obj.get("tags") if isinstance(obj.get("tags"), list) else []
        tags = [str(x).strip() for x in tags if str(x).strip()]
        status = str(obj.get("status") or "active").strip() or "active"
        kind = _kind_for_path(p)
        try:
            action = register_existing(
                dsn=dsn,
                oid=oid,
                path=rel,
                kind=kind,
                layer=layer,
                primary_unit=primary_unit,
                tags=tags,
                status=status,
                hint="register_inline_glob",
            )
        except Exception as e:
            errors.append({"path": rel, "error": f"register_failed:{e}"})
            continue

        if action == "inserted":
            inserted += 1
        elif action == "updated":
            updated += 1
        else:
            noop += 1
        rows.append({"path": rel, "oid": oid, "action": action})

    payload: Dict[str, Any] = {
        "ok": not errors,
        "schema_version": "v0.1.0",
        "ts_utc": _utc_now(),
        "taskcode": str(args.taskcode),
        "globs": [str(x) for x in (args.glob or []) if str(x).strip()],
        "targets": len(paths),
        "inserted": inserted,
        "updated": updated,
        "noop": noop,
        "errors": len(errors),
        "rows": rows,
        "error_list": errors,
    }

    area = str(args.area).strip() or "control_plane"
    taskcode = str(args.taskcode).strip() or "OID_REGISTER_INLINE_GLOB_V010"
    report_dir = str(args.report_dir or "").strip()
    if report_dir:
        out_dir = Path(report_dir)
        if not out_dir.is_absolute():
            out_dir = (repo_root / out_dir).resolve()
    else:
        out_dir = (repo_root / "docs" / "REPORT" / area / "artifacts" / taskcode / _stamp_utc()).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    out_json = out_dir / "oid_register_inline_glob_summary.json"
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", errors="replace")

    out_md = (repo_root / "docs" / "REPORT" / area / f"REPORT__{taskcode}__{_date_utc()}.md").resolve()
    out_md.parent.mkdir(parents=True, exist_ok=True)
    lines: List[str] = []
    lines.append(f"# OID Register Inline Glob — {taskcode} (v0.1.0)")
    lines.append("")
    lines.append(f"- ts_utc: `{payload['ts_utc']}`")
    lines.append(f"- targets: `{payload['targets']}`")
    lines.append(f"- inserted: `{payload['inserted']}` updated: `{payload['updated']}` noop: `{payload['noop']}`")
    lines.append(f"- errors: `{payload['errors']}`")
    lines.append(f"- summary_json: `{_to_repo_rel(repo_root, out_json)}`")
    lines.append("")
    lines.append("## Sample")
    lines.append("| action | oid | path |")
    lines.append("|---|---|---|")
    for r in rows[:60]:
        lines.append(f"| {r['action']} | {r['oid']} | {r['path']} |")
    lines.append("")
    out_md.write_text("\n".join(lines).strip() + "\n", encoding="utf-8", errors="replace")

    print(str(out_md))
    print(str(out_json))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
