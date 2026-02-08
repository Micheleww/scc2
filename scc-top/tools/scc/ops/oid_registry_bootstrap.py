#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OID Registry Bootstrap (v0.1.0)

Purpose:
- Import inline-embedded OIDs for the SSOT registry canonical set into Postgres (object_index),
  so `oid_validator` can be fail-closed.

This tool is deterministic and does not scan the whole repo: it reads only `docs/ssot/registry.json`.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.scc.oid.pg_registry import get_oid_pg_dsn, register_existing
from tools.scc.oid.ulid import ulid_is_placeholder, ulid_is_valid


def _repo_root() -> Path:
    return _REPO_ROOT


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _read_json(path: Path) -> dict:
    try:
        return json.loads(_read_text(path) or "{}")
    except Exception:
        return {}


def _utc_stamp() -> str:
    return time.strftime("%Y%m%d-%H%M%SZ", time.gmtime())


def _parse_frontmatter_md(text: str) -> Dict[str, Any]:
    lines = (text or "").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    meta_lines: List[str] = []
    end = None
    for i in range(1, min(len(lines), 200)):
        if lines[i].strip() == "---":
            end = i
            break
        meta_lines.append(lines[i])
    if end is None:
        return {}
    meta: Dict[str, Any] = {}
    for raw in meta_lines:
        if not raw.strip() or raw.strip().startswith("#") or ":" not in raw:
            continue
        k, v = raw.split(":", 1)
        key = k.strip()
        val = v.strip()
        if not key:
            continue
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            meta[key] = [x.strip() for x in inner.split(",") if x.strip()] if inner else []
        else:
            meta[key] = val
    return meta


def _load_registry_canonical_paths(repo_root: Path) -> List[str]:
    reg = (repo_root / "docs" / "ssot" / "registry.json").resolve()
    if not reg.exists():
        return []
    j = _read_json(reg)
    canonical = j.get("canonical") if isinstance(j.get("canonical"), list) else []
    out: List[str] = []
    for it in canonical:
        if not isinstance(it, dict):
            continue
        p = str(it.get("canonical_path") or "").strip()
        if p:
            out.append(p.replace("\\", "/").lstrip("./"))
    # stable de-dupe
    seen = set()
    uniq: List[str] = []
    for p in out:
        if p in seen:
            continue
        seen.add(p)
        uniq.append(p)
    return uniq


def _kind_for_path(path: Path) -> str:
    return (path.suffix or "").lstrip(".").lower() or "file"


def _extract_inline_meta(repo_root: Path, rel: str) -> Tuple[Dict[str, Any], str]:
    p = (repo_root / rel).resolve()
    if not p.exists() or not p.is_file():
        return {}, "missing_file"
    if p.suffix.lower() in (".md", ".markdown"):
        return _parse_frontmatter_md(_read_text(p)), ""
    if p.suffix.lower() == ".json":
        j = _read_json(p)
        return (j if isinstance(j, dict) else {}), ""
    return {}, "unsupported_kind"


def _infer_area_taskcode_from_report_dir(repo_root: Path, report_dir: Path) -> Tuple[str, str]:
    """
    Try to infer (area, taskcode) from a report_dir path such as:
      docs/REPORT/<area>/artifacts/<TaskCode>/
    Falls back to ("control_plane", <basename>).
    """
    try:
        rel = report_dir.resolve().relative_to(repo_root.resolve())
    except Exception:
        rel = Path(str(report_dir).replace("\\", "/"))

    parts = [p for p in rel.parts]
    area = "control_plane"
    taskcode = report_dir.name
    try:
        # ... docs/REPORT/<area>/artifacts/<taskcode>
        if len(parts) >= 5 and parts[0].lower() == "docs" and parts[1].upper() == "REPORT" and parts[3].lower() == "artifacts":
            area = parts[2]
            taskcode = parts[4]
    except Exception:
        pass
    return str(area), str(taskcode)


def main() -> int:
    ap = argparse.ArgumentParser(description="Bootstrap SSOT canonical OIDs into Postgres (fail-closed support)")
    ap.add_argument("--dsn", default="", help="Optional Postgres DSN (else env SCC_OID_PG_DSN)")
    ap.add_argument("--report-dir", default="docs/REPORT/control_plane/artifacts/OID_REGISTRY_BOOTSTRAP_V010", help="Report output dir")
    args = ap.parse_args()

    repo_root = _repo_root()
    dsn = str(args.dsn or "").strip() or get_oid_pg_dsn()
    if not dsn:
        print("missing dsn: set SCC_OID_PG_DSN / DATABASE_URL")
        return 2

    targets = _load_registry_canonical_paths(repo_root)
    stamp = _utc_stamp()
    report_dir = Path(str(args.report_dir))
    if not report_dir.is_absolute():
        report_dir = (repo_root / report_dir).resolve()
    report_dir.mkdir(parents=True, exist_ok=True)

    rows: List[dict] = []
    errors: List[str] = []
    imported = 0
    updated = 0
    noop = 0

    for rel in targets:
        meta, err = _extract_inline_meta(repo_root, rel)
        if err:
            errors.append(f"{rel}: {err}")
            continue
        oid = str(meta.get("oid") or "").strip()
        if ulid_is_placeholder(oid) or not ulid_is_valid(oid):
            errors.append(f"{rel}: invalid_or_placeholder_oid: {oid}")
            continue
        layer = str(meta.get("layer") or "").strip() or "CANON"
        primary_unit = str(meta.get("primary_unit") or "").strip() or "X.UNCLASSIFIED"
        tags = meta.get("tags")
        if isinstance(tags, str):
            tags_list = [x.strip() for x in tags.split(",") if x.strip()]
        elif isinstance(tags, list):
            tags_list = [str(x).strip() for x in tags if str(x).strip()]
        else:
            tags_list = []
        status = str(meta.get("status") or "active").strip() or "active"
        kind = _kind_for_path((repo_root / rel))

        try:
            action = register_existing(
                dsn=dsn,
                oid=oid,
                path=rel,
                kind=kind,
                layer=layer,
                primary_unit=primary_unit,
                tags=tags_list,
                status=status,
                hint="bootstrap_from_inline",
            )
        except Exception as e:
            errors.append(f"{rel}: register_failed: {e}")
            continue

        if action == "inserted":
            imported += 1
        elif action == "updated":
            updated += 1
        else:
            noop += 1
        rows.append({"path": rel, "oid": oid, "action": action})

    payload = {
        "schema_version": "v0.1.0",
        "ts_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "targets": len(targets),
        "imported": imported,
        "updated": updated,
        "noop": noop,
        "errors": len(errors),
        "rows": rows,
        "error_list": errors,
    }
    report_json = report_dir / f"oid_registry_bootstrap__{stamp}.json"
    report_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", errors="replace")

    md_lines: List[str] = []
    md_lines.append("# oid_registry bootstrap report")
    md_lines.append("")
    md_lines.append(f"- ts_utc: `{payload['ts_utc']}`")
    md_lines.append(f"- targets: `{payload['targets']}`")
    md_lines.append(f"- inserted: `{imported}` updated: `{updated}` noop: `{noop}`")
    md_lines.append(f"- errors: `{payload['errors']}`")
    md_lines.append("")
    if errors:
        md_lines.append("## Errors")
        for e in errors[:200]:
            md_lines.append(f"- {e}")
        md_lines.append("")
    md_lines.append("## Sample")
    for r in rows[:30]:
        md_lines.append(f"- `{r['action']}` `{r['oid']}` `{r['path']}`")
    md = "\n".join(md_lines).strip() + "\n"
    report_md = report_dir / f"oid_registry_bootstrap__{stamp}.md"
    report_md.write_text(md, encoding="utf-8", errors="replace")

    # Create/refresh the fail-closed evidence triplet under docs/REPORT/<area>/...
    area, taskcode = _infer_area_taskcode_from_report_dir(repo_root, report_dir)
    exit_code = 0 if not errors else 1
    evidence = [
        str(report_json.resolve().relative_to(repo_root.resolve())).replace("\\", "/"),
        str(report_md.resolve().relative_to(repo_root.resolve())).replace("\\", "/"),
    ]
    subprocess.run(
        [
            sys.executable,
            "tools/scc/ops/evidence_triplet.py",
            "--taskcode",
            taskcode,
            "--area",
            area,
            "--exit-code",
            str(exit_code),
            "--notes",
            "- bootstrap imports inline OIDs listed by `docs/ssot/registry.json` into PostgreSQL (object_index) for fail-closed `oid_validator`.",
            *sum([["--evidence", p] for p in evidence], []),
        ],
        cwd=str(repo_root),
        env=dict(os.environ),
    )

    print(str(report_md))
    print(str(report_json))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
