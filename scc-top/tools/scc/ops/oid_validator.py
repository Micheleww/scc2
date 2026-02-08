#!/usr/bin/env python3
from __future__ import annotations

import sys
import argparse
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.scc.oid.pg_registry import ensure_schema, get_by_oid, get_oid_pg_dsn
from tools.scc.oid.ulid import ulid_is_placeholder, ulid_is_valid


def _repo_root() -> Path:
    return _REPO_ROOT


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _to_repo_rel(repo_root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve())).replace("\\", "/")
    except Exception:
        return str(path).replace("\\", "/")


def _parse_frontmatter_md(text: str) -> Tuple[Dict[str, Any], str]:
    """
    Parse YAML-like frontmatter without PyYAML dependency.
    Returns (meta, remainder_text).
    """
    lines = (text or "").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    meta_lines: List[str] = []
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
        meta_lines.append(lines[i])
    if end is None:
        return {}, text

    meta: Dict[str, Any] = {}
    for raw in meta_lines:
        if not raw.strip() or raw.strip().startswith("#"):
            continue
        if ":" not in raw:
            continue
        k, v = raw.split(":", 1)
        key = k.strip()
        val = v.strip()
        if not key:
            continue
        # inline list: [A, B]
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            if not inner:
                meta[key] = []
            else:
                meta[key] = [x.strip() for x in inner.split(",") if x.strip()]
        else:
            meta[key] = val

    remainder = "\n".join(lines[end + 1 :])
    return meta, remainder


_UNIT_TOKEN_RE = re.compile(r"\b([A-Z]\.[A-Z0-9_]+)\b")


def _load_unit_registry_units(repo_root: Path) -> Tuple[set[str], str]:
    p = (repo_root / "docs" / "ssot" / "01_conventions" / "UNIT_REGISTRY__v0.1.0.md").resolve()
    if not p.exists():
        return set(), _to_repo_rel(repo_root, p)
    text = _read_text(p)
    units = set(_UNIT_TOKEN_RE.findall(text))
    return units, _to_repo_rel(repo_root, p)


@dataclass
class Finding:
    level: str  # ERROR|WARN
    file: str
    code: str
    message: str


def _iter_files(repo_root: Path, roots: List[Path]) -> Iterable[Path]:
    seen: set[str] = set()
    for r in roots:
        if not r.exists():
            continue
        for p in r.rglob("*"):
            if not p.is_file():
                continue
            rel = _to_repo_rel(repo_root, p)
            if rel in seen:
                continue
            seen.add(rel)
            yield p


def _mandatory_inline_roots(repo_root: Path) -> List[Path]:
    # v0.1.0 mandatory trees (see docs/ssot/01_conventions/OID_SPEC__v0.1.0.md)
    roots: List[Path] = []
    roots.append((repo_root / "docs" / "ssot").resolve())
    roots.append((repo_root / "docs" / "CANONICAL").resolve())
    docops = (repo_root / "docs" / "DOCOPS").resolve()
    if docops.exists():
        roots.append(docops)
    arch_contracts = (repo_root / "docs" / "ARCH" / "contracts").resolve()
    if arch_contracts.exists():
        roots.append(arch_contracts)
    return roots


def _tree_target_paths(repo_root: Path) -> List[str]:
    """
    Deterministic target set for mandatory-tree validation (v0.1.0).

    Policy:
    - Enforce markdown under SSOT/CANONICAL/DOCOPS (if present).
    - Enforce JSON under SSOT playbook/contracts and schema files.
    - Exempt SSOT registries (index-first, no inline OID in v0.1.0).
    """
    targets: List[str] = []

    def add_glob(glob_pat: str) -> None:
        for p in repo_root.glob(glob_pat):
            if p.is_file():
                targets.append(_to_repo_rel(repo_root, p))

    # markdown trees
    add_glob("docs/ssot/**/*.md")
    add_glob("docs/CANONICAL/**/*.md")
    if (repo_root / "docs" / "DOCOPS").exists():
        add_glob("docs/DOCOPS/**/*.md")

    # optional arch contracts
    if (repo_root / "docs" / "ARCH" / "contracts").exists():
        add_glob("docs/ARCH/contracts/**/*.md")
        add_glob("docs/ARCH/contracts/**/*.json")

    # json trees (SSOT)
    add_glob("docs/ssot/03_agent_playbook/**/*.json")
    add_glob("docs/ssot/04_contracts/**/*.json")
    add_glob("docs/ssot/05_runbooks/**/*.schema.json")
    add_glob("docs/ssot/05_runbooks/verdict.schema.json")

    exempt = {"docs/ssot/registry.json", "docs/ssot/_registry.json"}
    out: List[str] = []
    seen: set[str] = set()
    for t in targets:
        tt = str(t or "").replace("\\", "/").lstrip("./")
        if not tt or tt in exempt:
            continue
        if tt in seen:
            continue
        seen.add(tt)
        out.append(tt)
    out.sort()
    return out


def _load_registry_canonical_paths(repo_root: Path) -> Tuple[List[str], str]:
    reg = (repo_root / "docs" / "ssot" / "registry.json").resolve()
    if not reg.exists():
        return [], _to_repo_rel(repo_root, reg)
    try:
        j = json.loads(_read_text(reg) or "{}")
    except Exception:
        return [], _to_repo_rel(repo_root, reg)
    canonical = j.get("canonical") if isinstance(j, dict) else None
    out: List[str] = []
    if isinstance(canonical, list):
        for item in canonical:
            if not isinstance(item, dict):
                continue
            p = str(item.get("canonical_path") or "").strip()
            if p:
                out.append(p.replace("\\", "/").lstrip("./"))
    # de-dup in order
    seen = set()
    uniq = []
    for p in out:
        if p in seen:
            continue
        seen.add(p)
        uniq.append(p)
    return uniq, _to_repo_rel(repo_root, reg)


def _validate_units(units: set[str], token: str) -> bool:
    t = (token or "").strip()
    return bool(t) and t in units


def _sorted_tags(tags: Any) -> List[str]:
    if tags is None:
        return []
    if isinstance(tags, list):
        return sorted([str(x).strip() for x in tags if str(x).strip()])
    if isinstance(tags, str):
        # allow comma-separated
        return sorted([x.strip() for x in tags.split(",") if x.strip()])
    return []


def _guess_kind(path: Path) -> str:
    return (path.suffix or "").lstrip(".").lower() or "file"


def _extract_inline_meta(repo_root: Path, path: Path) -> Tuple[Dict[str, Any], List[Finding]]:
    rel = _to_repo_rel(repo_root, path)
    findings: List[Finding] = []
    if path.suffix.lower() in (".md", ".markdown"):
        meta, _ = _parse_frontmatter_md(_read_text(path))
        if not meta:
            findings.append(Finding("ERROR", rel, "missing_frontmatter", "missing YAML frontmatter ('---' ... '---')"))
        return meta, findings
    if path.suffix.lower() == ".json":
        try:
            meta = json.loads(_read_text(path) or "{}")
            if not isinstance(meta, dict):
                findings.append(Finding("ERROR", rel, "invalid_json", "JSON root is not an object"))
                return {}, findings
            return meta, findings
        except Exception as e:
            findings.append(Finding("ERROR", rel, "invalid_json", f"failed to parse JSON: {e}"))
            return {}, findings
    # other files: index-only in v0.1.0 (no inline requirement)
    return {}, findings


def validate(*, repo_root: Path, dsn: str) -> Tuple[bool, Dict[str, Any], List[Finding]]:
    if not (dsn or "").strip():
        summary = {
            "ok": False,
            "ts_utc": _iso_now(),
            "roots": [str(_to_repo_rel(repo_root, r)) for r in _mandatory_inline_roots(repo_root)],
            "unit_registry": _to_repo_rel(
                repo_root, (repo_root / "docs" / "ssot" / "01_conventions" / "UNIT_REGISTRY__v0.1.0.md").resolve()
            ),
            "total_files": 0,
            "checked_files": 0,
            "errors": 1,
            "warnings": 0,
        }
        findings = [
            Finding(
                "ERROR",
                "-",
                "missing_pg_dsn",
                "missing Postgres DSN: set SCC_OID_PG_DSN or SCC_OID_DATABASE_URL or DATABASE_URL",
            )
        ]
        return False, summary, findings

    # Ensure registry schema exists so validator fails on missing objects rather than missing tables.
    try:
        ensure_schema(dsn=dsn)
    except Exception as e:
        summary = {
            "ok": False,
            "ts_utc": _iso_now(),
            "registry": "docs/ssot/registry.json",
            "targets": 0,
            "unit_registry": _to_repo_rel(
                repo_root, (repo_root / "docs" / "ssot" / "01_conventions" / "UNIT_REGISTRY__v0.1.0.md").resolve()
            ),
            "total_files": 0,
            "checked_files": 0,
            "errors": 1,
            "warnings": 0,
        }
        findings = [Finding("ERROR", "-", "pg_schema_init_failed", f"failed to ensure Postgres schema: {e}")]
        return False, summary, findings

    units, unit_registry_path = _load_unit_registry_units(repo_root)
    targets, registry_path = _load_registry_canonical_paths(repo_root)
    findings: List[Finding] = []

    tree_targets = _tree_target_paths(repo_root)
    merged_targets: List[str] = []
    seen: set[str] = set()
    for rel in [*tree_targets, *targets]:
        r0 = str(rel or "").replace("\\", "/").lstrip("./")
        if not r0 or r0 in seen:
            continue
        seen.add(r0)
        merged_targets.append(r0)

    total = 0
    checked = 0
    for rel in merged_targets:
        p = (repo_root / rel).resolve()
        total += 1
        if not p.exists() or not p.is_file():
            findings.append(Finding("ERROR", rel, "missing_file", "target missing on disk"))
            continue

        meta, f = _extract_inline_meta(repo_root, p)
        findings.extend(f)
        if not meta:
            continue

        checked += 1

        oid = str(meta.get("oid") or "").strip()
        if ulid_is_placeholder(oid):
            findings.append(Finding("ERROR", rel, "oid_placeholder", "oid is placeholder; must mint via SCC OID Generator"))
            continue
        if not ulid_is_valid(oid):
            findings.append(Finding("ERROR", rel, "oid_invalid", f"oid is not a valid ULID: {oid!r}"))
            continue

        layer = str(meta.get("layer") or "").strip()
        primary_unit = str(meta.get("primary_unit") or "").strip()
        tags = _sorted_tags(meta.get("tags"))
        status = str(meta.get("status") or "active").strip() or "active"

        if not layer:
            findings.append(Finding("ERROR", rel, "missing_layer", "missing layer in inline metadata"))
        if not primary_unit:
            findings.append(Finding("ERROR", rel, "missing_primary_unit", "missing primary_unit in inline metadata"))
        elif units and not _validate_units(units, primary_unit):
            findings.append(
                Finding(
                    "ERROR",
                    rel,
                    "primary_unit_unregistered",
                    f"primary_unit not registered in {unit_registry_path}: {primary_unit}",
                )
            )
        for t in tags:
            if units and not _validate_units(units, t):
                findings.append(
                    Finding(
                        "ERROR",
                        rel,
                        "tag_unregistered",
                        f"tag not registered in {unit_registry_path}: {t}",
                    )
                )

        # Postgres authority checks
        try:
            obj = get_by_oid(dsn=dsn, oid=oid)
        except Exception as e:
            findings.append(Finding("ERROR", rel, "pg_lookup_failed", f"Postgres lookup failed: {e}"))
            continue
        if obj is None:
            findings.append(Finding("ERROR", rel, "oid_missing_in_registry", "oid not found in Postgres registry"))
            continue

        expected_path = rel
        if obj.path != expected_path:
            findings.append(
                Finding(
                    "ERROR",
                    rel,
                    "path_mismatch",
                    f"registry path mismatch: pg={obj.path!r} file={expected_path!r}",
                )
            )
        if layer and obj.layer != layer:
            findings.append(Finding("ERROR", rel, "layer_mismatch", f"registry layer mismatch: pg={obj.layer!r} file={layer!r}"))
        if primary_unit and obj.primary_unit != primary_unit:
            findings.append(
                Finding(
                    "ERROR",
                    rel,
                    "primary_unit_mismatch",
                    f"registry primary_unit mismatch: pg={obj.primary_unit!r} file={primary_unit!r}",
                )
            )
        if sorted(obj.tags or []) != sorted(tags):
            findings.append(
                Finding(
                    "ERROR",
                    rel,
                    "tags_mismatch",
                    f"registry tags mismatch: pg={sorted(obj.tags or [])!r} file={sorted(tags)!r}",
                )
            )
        if status and obj.status != status:
            findings.append(
                Finding(
                    "ERROR",
                    rel,
                    "status_mismatch",
                    f"registry status mismatch: pg={obj.status!r} file={status!r}",
                )
            )

    ok = not any(x.level == "ERROR" for x in findings)
    summary = {
        "ok": ok,
        "ts_utc": _iso_now(),
        "registry": registry_path,
        "targets": len(merged_targets),
        "targets_tree": len(tree_targets),
        "targets_registry_canonical": len(targets),
        "unit_registry": unit_registry_path,
        "total_files": total,
        "checked_files": checked,
        "errors": sum(1 for x in findings if x.level == "ERROR"),
        "warnings": sum(1 for x in findings if x.level == "WARN"),
    }
    return ok, summary, findings


def _render_md(summary: Dict[str, Any], findings: List[Finding]) -> str:
    lines = []
    lines.append(f"# oid_validator report")
    lines.append("")
    lines.append(f"- ts_utc: `{summary.get('ts_utc')}`")
    lines.append(f"- ok: `{summary.get('ok')}`")
    lines.append(f"- checked_files: `{summary.get('checked_files')}` / total `{summary.get('total_files')}`")
    lines.append(f"- errors: `{summary.get('errors')}` warnings: `{summary.get('warnings')}`")
    lines.append(f"- unit_registry: `{summary.get('unit_registry')}`")
    lines.append("")
    if findings:
        lines.append("## Findings")
        for f in findings:
            lines.append(f"- {f.level} `{f.code}` `{f.file}` — {f.message}")
    else:
        lines.append("## Findings")
        lines.append("- (none)")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="SCC oid_validator (v0.1.0)")
    ap.add_argument("--report-dir", default="", help="Directory to write report artifacts")
    ap.add_argument("--json-out", default="", help="Optional JSON summary output path")
    ap.add_argument("--dsn", default="", help="Optional Postgres DSN (else env)")
    args = ap.parse_args()

    repo_root = _repo_root()
    dsn = str(args.dsn).strip() or get_oid_pg_dsn()
    ok, summary, findings = validate(repo_root=repo_root, dsn=dsn)

    if str(args.report_dir).strip():
        out_dir = Path(args.report_dir)
        if not out_dir.is_absolute():
            out_dir = (repo_root / out_dir).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = summary["ts_utc"].replace(":", "").replace("-", "")
        md_path = out_dir / f"oid_validator__{ts}.md"
        md_path.write_text(_render_md(summary, findings), encoding="utf-8", errors="replace")
        summary["report_md"] = _to_repo_rel(repo_root, md_path)

    if str(args.json_out).strip():
        p = Path(args.json_out)
        if not p.is_absolute():
            p = (repo_root / p).resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"summary": summary, "findings": [f.__dict__ for f in findings]}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", errors="replace")

    print(json.dumps(summary, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
