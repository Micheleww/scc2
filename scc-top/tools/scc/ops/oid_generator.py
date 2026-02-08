#!/usr/bin/env python3
from __future__ import annotations

import sys
import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.scc.oid.pg_registry import (
    OidRegistryError,
    ensure_schema,
    get_by_oid,
    get_oid_pg_dsn,
    issue_new,
    migrate,
)


def _write_json(path: Optional[Path], obj: Any) -> None:
    s = json.dumps(obj, ensure_ascii=False, indent=2)
    if path is None:
        print(s)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(s + "\n", encoding="utf-8", errors="replace")


def _parse_csv(v: str) -> List[str]:
    out: List[str] = []
    for s in (v or "").split(","):
        s = s.strip()
        if s:
            out.append(s)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="SCC OID Generator (Postgres registry, ULID issuer)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ap_schema = sub.add_parser("ensure-schema", help="Ensure Postgres tables/indexes exist")
    ap_schema.add_argument("--dsn", default="", help="Optional Postgres DSN (else env)")

    ap_new = sub.add_parser("new", help="Mint a new OID (idempotent if stable_key provided)")
    ap_new.add_argument("--path", required=True, help="Repo-relative path (file object)")
    ap_new.add_argument("--kind", required=True, help="md/json/py/... (kind)")
    ap_new.add_argument("--layer", required=True, help="RAW|DERIVED|CANON|DIST|CODE|CONF|TOOL|REPORT|ARCH|DOCOPS")
    ap_new.add_argument("--primary-unit", required=True, help="Unit token (must exist in Unit Registry)")
    ap_new.add_argument("--tags", default="", help="Comma-separated unit tokens")
    ap_new.add_argument("--stable-key", default="", help="Optional stable key for idempotency")
    ap_new.add_argument("--hint", default="", help="Optional hint")
    ap_new.add_argument("--out", default="", help="Optional output JSON path")

    ap_get = sub.add_parser("get", help="Lookup an OID in registry")
    ap_get.add_argument("--oid", required=True)
    ap_get.add_argument("--out", default="", help="Optional output JSON path")

    ap_m = sub.add_parser("migrate", help="Migrate object metadata (oid remains unchanged)")
    ap_m.add_argument("--oid", required=True)
    ap_m.add_argument("--patch-json", required=True, help="JSON object with allowed keys: path/layer/primary_unit/tags/status/...")
    ap_m.add_argument("--reason", required=True)
    ap_m.add_argument("--actor", default="agent", help="Actor identifier")
    ap_m.add_argument("--out", default="", help="Optional output JSON path")

    args = ap.parse_args()
    dsn = (get_oid_pg_dsn() if not getattr(args, "dsn", "").strip() else str(args.dsn).strip())

    out_path = Path(args.out).resolve() if str(getattr(args, "out", "")).strip() else None
    try:
        if args.cmd == "ensure-schema":
            ensure_schema(dsn=dsn)
            _write_json(out_path, {"ok": True, "action": "ensure_schema"})
            return 0
        if args.cmd == "new":
            tags = _parse_csv(str(args.tags))
            stable_key = str(args.stable_key).strip() or None
            hint = str(args.hint).strip() or None
            oid, issued = issue_new(
                dsn=dsn,
                path=str(args.path),
                kind=str(args.kind),
                layer=str(args.layer),
                primary_unit=str(args.primary_unit),
                tags=tags,
                stable_key=stable_key,
                hint=hint,
            )
            _write_json(
                out_path,
                {
                    "ok": True,
                    "oid": oid,
                    "issued": issued,
                    "path": str(args.path),
                    "kind": str(args.kind),
                    "layer": str(args.layer),
                    "primary_unit": str(args.primary_unit),
                    "tags": tags,
                    "stable_key": stable_key,
                    "hint": hint,
                },
            )
            return 0
        if args.cmd == "get":
            obj = get_by_oid(dsn=dsn, oid=str(args.oid))
            _write_json(out_path, {"ok": True, "found": bool(obj), "object": obj.__dict__ if obj else None})
            return 0
        if args.cmd == "migrate":
            patch = json.loads(str(args.patch_json))
            migrated = migrate(
                dsn=dsn,
                oid=str(args.oid),
                patch=patch,
                reason=str(args.reason),
                actor=str(args.actor),
            )
            _write_json(out_path, {"ok": True, "oid": str(args.oid), "migrated": bool(migrated), "patch": patch})
            return 0
    except OidRegistryError as e:
        _write_json(out_path, {"ok": False, "error": str(e), "cmd": args.cmd})
        return 2
    except Exception as e:
        _write_json(out_path, {"ok": False, "error": f"unexpected: {e}", "cmd": args.cmd})
        return 3
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
