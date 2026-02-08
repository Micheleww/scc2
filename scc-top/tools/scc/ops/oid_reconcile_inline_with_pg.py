#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OID_RECONCILE_INLINE_WITH_PG_V010 — reconcile inline metadata to Postgres (source of truth).

Goal:
- For an explicit, caller-scoped file set, ensure inline `oid/layer/primary_unit/tags/status`
  matches the Postgres registry record for the same *path*.

Rationale:
- Postgres is authoritative. If a file is regenerated incorrectly (new oid written inline),
  this tool repairs the inline header to match the registry without changing the registry oid.

Safety:
- Only touches files matched by provided --glob (repeatable).
- Does NOT change file bodies beyond inline metadata.
- Writes a report to docs/REPORT/<area>/artifacts/<taskcode>/...
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.scc.oid.pg_registry import get_oid_pg_dsn


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


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _write_text(path: Path, s: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(s, encoding="utf-8", errors="replace")


def _read_json(path: Path) -> dict:
    try:
        return json.loads(_read_text(path) or "{}")
    except Exception:
        return {}


def _parse_frontmatter_md(text: str) -> Tuple[Dict[str, Any], List[str], int, int]:
    """
    Returns (meta, lines, start_idx, end_idx) where start_idx/end_idx refer to meta line range
    within lines (excluding the opening '---', end_idx is the index of closing '---').
    """
    lines = (text or "").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, lines, -1, -1
    end = None
    for i in range(1, min(len(lines), 200)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return {}, lines, -1, -1
    meta_lines = lines[1:end]
    meta: Dict[str, Any] = {}
    for raw in meta_lines:
        if ":" not in raw:
            continue
        k, v = raw.split(":", 1)
        meta[k.strip()] = v.strip()
    return meta, lines, 1, end


def _parse_inline_list(val: Any) -> List[str]:
    if val is None:
        return []
    if isinstance(val, list):
        return [str(x).strip() for x in val if str(x).strip()]
    s = str(val).strip()
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        if not inner:
            return []
        return [x.strip() for x in inner.split(",") if x.strip()]
    if not s:
        return []
    return [x.strip() for x in s.split(",") if x.strip()]


@dataclass(frozen=True)
class PgRow:
    oid: str
    layer: str
    primary_unit: str
    tags: List[str]
    status: str


def _pg_lookup_by_path(*, dsn: str, path: str) -> Optional[PgRow]:
    try:
        import psycopg2  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError(f"psycopg2_not_available: {e}") from e

    conn = psycopg2.connect(dsn)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT oid, layer, primary_unit, tags, status FROM objects WHERE path=%s AND status='active' LIMIT 2",
            (path,),
        )
        rows = cur.fetchall() or []
        if len(rows) != 1:
            return None
        r = rows[0]
        return PgRow(
            oid=str(r[0]),
            layer=str(r[1]),
            primary_unit=str(r[2]),
            tags=list(r[3] or []),
            status=str(r[4] or "active") or "active",
        )
    finally:
        conn.close()


def _reconcile_md(path: Path, *, pg: PgRow, apply: bool) -> Dict[str, Any]:
    repo_root = _repo_root()
    rel = _to_repo_rel(repo_root, path)
    text = _read_text(path)
    meta, lines, start, end = _parse_frontmatter_md(text)
    if start < 0 or end < 0:
        return {"path": rel, "kind": "md", "ok": False, "error": "missing_frontmatter"}
    before = {
        "oid": str(meta.get("oid") or "").strip(),
        "layer": str(meta.get("layer") or "").strip(),
        "primary_unit": str(meta.get("primary_unit") or "").strip(),
        "tags": _parse_inline_list(meta.get("tags")),
        "status": str(meta.get("status") or "").strip() or "active",
    }
    after = {"oid": pg.oid, "layer": pg.layer, "primary_unit": pg.primary_unit, "tags": pg.tags, "status": pg.status}
    if before == after:
        return {"path": rel, "kind": "md", "ok": True, "changed": False, "before": before, "after": after}

    # rewrite only the known keys; preserve unknown meta lines.
    meta_lines = lines[start:end]
    out_meta: List[str] = []
    seen = set()
    for raw in meta_lines:
        if ":" not in raw:
            out_meta.append(raw)
            continue
        k, _ = raw.split(":", 1)
        key = k.strip()
        if key in {"oid", "layer", "primary_unit", "tags", "status"}:
            if key in seen:
                continue
            seen.add(key)
            if key == "oid":
                out_meta.append(f"oid: {pg.oid}")
            elif key == "layer":
                out_meta.append(f"layer: {pg.layer}")
            elif key == "primary_unit":
                out_meta.append(f"primary_unit: {pg.primary_unit}")
            elif key == "status":
                out_meta.append(f"status: {pg.status}")
            elif key == "tags":
                out_meta.append(f"tags: [{', '.join(pg.tags)}]")
            continue
        out_meta.append(raw)

    # Ensure required keys exist
    def ensure_line(key: str, line: str) -> None:
        nonlocal out_meta
        if key in seen:
            return
        out_meta.append(line)
        seen.add(key)

    ensure_line("oid", f"oid: {pg.oid}")
    ensure_line("layer", f"layer: {pg.layer}")
    ensure_line("primary_unit", f"primary_unit: {pg.primary_unit}")
    ensure_line("tags", f"tags: [{', '.join(pg.tags)}]")
    ensure_line("status", f"status: {pg.status}")

    new_lines = [lines[0], *out_meta, lines[end], *lines[end + 1 :]]
    if apply:
        _write_text(path, "\n".join(new_lines).strip("\n") + "\n")
    return {"path": rel, "kind": "md", "ok": True, "changed": True, "before": before, "after": after}


def _reconcile_json(path: Path, *, pg: PgRow, apply: bool) -> Dict[str, Any]:
    repo_root = _repo_root()
    rel = _to_repo_rel(repo_root, path)
    obj = _read_json(path)
    if not isinstance(obj, dict):
        return {"path": rel, "kind": "json", "ok": False, "error": "json_not_object"}
    before = {
        "oid": str(obj.get("oid") or "").strip(),
        "layer": str(obj.get("layer") or "").strip(),
        "primary_unit": str(obj.get("primary_unit") or "").strip(),
        "tags": [str(x).strip() for x in (obj.get("tags") or []) if str(x).strip()] if isinstance(obj.get("tags"), list) else [],
        "status": str(obj.get("status") or "").strip() or "active",
    }
    after = {"oid": pg.oid, "layer": pg.layer, "primary_unit": pg.primary_unit, "tags": pg.tags, "status": pg.status}
    if before == after:
        return {"path": rel, "kind": "json", "ok": True, "changed": False, "before": before, "after": after}
    obj["oid"] = pg.oid
    obj["layer"] = pg.layer
    obj["primary_unit"] = pg.primary_unit
    obj["tags"] = list(pg.tags or [])
    obj["status"] = pg.status
    if apply:
        _write_text(path, json.dumps(obj, ensure_ascii=False, indent=2) + "\n")
    return {"path": rel, "kind": "json", "ok": True, "changed": True, "before": before, "after": after}


def main() -> int:
    ap = argparse.ArgumentParser(description="Reconcile inline metadata to Postgres (path-authoritative).")
    ap.add_argument("--glob", action="append", required=True, help="Repeatable repo-relative glob.")
    ap.add_argument("--dsn", default="", help="Optional Postgres DSN (else env SCC_OID_PG_DSN).")
    ap.add_argument("--apply", action="store_true", help="Apply changes (default dry-run).")
    ap.add_argument("--area", default="control_plane")
    ap.add_argument("--taskcode", default="OID_RECONCILE_INLINE_WITH_PG_V010")
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

    uniq: List[Path] = []
    seen: set[str] = set()
    for p in sorted(paths, key=lambda x: str(x)):
        rel = _to_repo_rel(repo_root, p)
        if rel in seen:
            continue
        seen.add(rel)
        uniq.append(p)
    paths = uniq

    rows: List[dict] = []
    errors: List[dict] = []
    changed = 0

    for p in paths:
        rel = _to_repo_rel(repo_root, p)
        pg = _pg_lookup_by_path(dsn=dsn, path=rel)
        if pg is None:
            errors.append({"path": rel, "error": "pg_path_not_unique_or_missing"})
            continue
        if p.suffix.lower() in (".md", ".markdown"):
            row = _reconcile_md(p, pg=pg, apply=bool(args.apply))
        elif p.suffix.lower() == ".json":
            row = _reconcile_json(p, pg=pg, apply=bool(args.apply))
        else:
            errors.append({"path": rel, "error": "unsupported_kind"})
            continue
        if row.get("changed"):
            changed += 1
        rows.append(row)

    payload = {
        "ok": not errors,
        "schema_version": "v0.1.0",
        "ts_utc": _utc_now(),
        "taskcode": str(args.taskcode),
        "apply": bool(args.apply),
        "targets": len(paths),
        "changed": changed,
        "errors": len(errors),
        "rows": rows,
        "error_list": errors,
    }

    area = str(args.area).strip() or "control_plane"
    taskcode = str(args.taskcode).strip() or "OID_RECONCILE_INLINE_WITH_PG_V010"
    out_dir = (repo_root / "docs" / "REPORT" / area / "artifacts" / taskcode / _stamp_utc()).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_json = out_dir / "oid_reconcile_inline_with_pg_summary.json"
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", errors="replace")

    out_md = (repo_root / "docs" / "REPORT" / area / f"REPORT__{taskcode}__{_date_utc()}.md").resolve()
    out_md.parent.mkdir(parents=True, exist_ok=True)
    lines: List[str] = []
    lines.append(f"# OID Reconcile Inline ↔ Postgres — {taskcode} (v0.1.0)")
    lines.append("")
    lines.append(f"- ts_utc: `{payload['ts_utc']}`")
    lines.append(f"- apply: `{payload['apply']}`")
    lines.append(f"- targets: `{payload['targets']}` changed: `{payload['changed']}` errors: `{payload['errors']}`")
    lines.append(f"- summary_json: `{_to_repo_rel(repo_root, out_json)}`")
    lines.append("")
    lines.append("## Sample")
    for r in rows[:30]:
        lines.append(f"- `{r.get('kind')}` changed={r.get('changed')} `{r.get('path')}`")
    lines.append("")
    out_md.write_text("\n".join(lines).strip() + "\n", encoding="utf-8", errors="replace")

    print(str(out_md))
    print(str(out_json))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
