#!/usr/bin/env python3
from __future__ import annotations

import sys
import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.scc.oid.pg_registry import OidRegistryError, get_oid_pg_dsn, issue_new
from tools.scc.oid.ulid import ulid_is_placeholder


def _repo_root() -> Path:
    return _REPO_ROOT


def _to_repo_rel(repo_root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve())).replace("\\", "/")
    except Exception:
        return str(path).replace("\\", "/")


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _write_text(path: Path, s: str) -> None:
    path.write_text(s, encoding="utf-8", errors="replace")


def _parse_frontmatter_md(text: str) -> Tuple[Dict[str, Any], int, int]:
    """
    Returns (meta, start_index, end_index) for the meta block within text,
    where start_index is the index of the first meta line (after '---'),
    and end_index is the index of the closing '---' line (exclusive).
    If missing, returns ({}, -1, -1).
    """
    lines = (text or "").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, -1, -1
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return {}, -1, -1
    meta_lines = lines[1:end]
    meta: Dict[str, Any] = {}
    for raw in meta_lines:
        if ":" not in raw:
            continue
        k, v = raw.split(":", 1)
        meta[k.strip()] = v.strip()
    return meta, 1, end


def _parse_inline_list(val: str) -> List[str]:
    s = (val or "").strip()
    if s.startswith("[") and s.endswith("]"):
        s = s[1:-1].strip()
        if not s:
            return []
        return [x.strip() for x in s.split(",") if x.strip()]
    if not s:
        return []
    # comma list fallback
    return [x.strip() for x in s.split(",") if x.strip()]


def _mandatory_roots(repo_root: Path) -> List[Path]:
    return [
        (repo_root / "docs" / "ssot").resolve(),
        (repo_root / "docs" / "CANONICAL").resolve(),
    ]


@dataclass
class MintTarget:
    rel: str
    abs_path: Path
    kind: str
    layer: str
    primary_unit: str
    tags: List[str]
    status: str


def _collect_targets(repo_root: Path) -> Tuple[List[MintTarget], List[dict]]:
    targets: List[MintTarget] = []
    skipped: List[dict] = []

    for root in _mandatory_roots(repo_root):
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            rel = _to_repo_rel(repo_root, p)
            if rel.startswith("docs/REPORT/") or rel.startswith("docs/INPUTS/"):
                continue
            suf = p.suffix.lower()
            if suf not in (".md", ".markdown", ".json"):
                continue

            if suf in (".md", ".markdown"):
                text = _read_text(p)
                meta, _, _ = _parse_frontmatter_md(text)
                oid = str(meta.get("oid") or "").strip()
                if not ulid_is_placeholder(oid):
                    continue
                layer = str(meta.get("layer") or "").strip()
                primary_unit = str(meta.get("primary_unit") or "").strip()
                tags = _parse_inline_list(str(meta.get("tags") or ""))
                status = str(meta.get("status") or "active").strip() or "active"
                if not (layer and primary_unit):
                    skipped.append({"path": rel, "reason": "missing_layer_or_primary_unit"})
                    continue
                targets.append(
                    MintTarget(
                        rel=rel,
                        abs_path=p,
                        kind="md",
                        layer=layer,
                        primary_unit=primary_unit,
                        tags=tags,
                        status=status,
                    )
                )
                continue

            if suf == ".json":
                try:
                    obj = json.loads(_read_text(p) or "{}")
                except Exception:
                    skipped.append({"path": rel, "reason": "invalid_json"})
                    continue
                if not isinstance(obj, dict):
                    skipped.append({"path": rel, "reason": "json_not_object"})
                    continue
                oid = str(obj.get("oid") or "").strip()
                if not ulid_is_placeholder(oid):
                    continue
                layer = str(obj.get("layer") or "").strip()
                primary_unit = str(obj.get("primary_unit") or "").strip()
                tags = obj.get("tags") if isinstance(obj.get("tags"), list) else []
                tags = [str(x).strip() for x in tags if str(x).strip()]
                status = str(obj.get("status") or "active").strip() or "active"
                if not (layer and primary_unit):
                    skipped.append({"path": rel, "reason": "missing_layer_or_primary_unit"})
                    continue
                targets.append(
                    MintTarget(
                        rel=rel,
                        abs_path=p,
                        kind="json",
                        layer=layer,
                        primary_unit=primary_unit,
                        tags=tags,
                        status=status,
                    )
                )
                continue

    return targets, skipped


def _apply_mint(repo_root: Path, target: MintTarget, oid: str) -> None:
    if target.kind == "md":
        text = _read_text(target.abs_path)
        lines = text.splitlines()
        if not lines or lines[0].strip() != "---":
            raise RuntimeError("missing_frontmatter")
        for i in range(1, min(len(lines), 80)):
            if lines[i].startswith("oid:"):
                lines[i] = f"oid: {oid}"
                _write_text(target.abs_path, "\n".join(lines) + ("\n" if text.endswith("\n") else ""))
                return
        raise RuntimeError("oid_line_not_found")
    if target.kind == "json":
        obj = json.loads(_read_text(target.abs_path) or "{}")
        if not isinstance(obj, dict):
            raise RuntimeError("json_not_object")
        obj["oid"] = oid
        _write_text(target.abs_path, json.dumps(obj, ensure_ascii=False, indent=2) + "\n")
        return
    raise RuntimeError("unsupported_kind")


def main() -> int:
    ap = argparse.ArgumentParser(description="Mint placeholder OIDs in required doc trees (via Postgres registry)")
    ap.add_argument("--apply", action="store_true", help="Apply changes (default is dry-run)")
    ap.add_argument("--limit", type=int, default=0, help="Optional limit of files to mint")
    ap.add_argument("--hint", default="bootstrap_mint", help="Hint stored in registry")
    args = ap.parse_args()

    repo_root = _repo_root()
    dsn = get_oid_pg_dsn()
    if not dsn:
        print(json.dumps({"ok": False, "error": "missing_pg_dsn"}, ensure_ascii=False))
        return 2

    targets, skipped = _collect_targets(repo_root)
    if args.limit and args.limit > 0:
        targets = targets[: int(args.limit)]

    minted: List[dict] = []
    errors: List[dict] = []

    for t in targets:
        try:
            oid, issued = issue_new(
                dsn=dsn,
                path=t.rel,
                kind=t.kind,
                layer=t.layer,
                primary_unit=t.primary_unit,
                tags=t.tags,
                stable_key=f"path:{t.rel}",
                hint=str(args.hint),
            )
            if args.apply:
                _apply_mint(repo_root, t, oid)
            minted.append({"path": t.rel, "oid": oid, "issued": issued, "applied": bool(args.apply)})
        except OidRegistryError as e:
            errors.append({"path": t.rel, "error": str(e)})
        except Exception as e:
            errors.append({"path": t.rel, "error": f"apply_failed: {e}"})

    out = {
        "ok": not errors,
        "apply": bool(args.apply),
        "minted": minted,
        "skipped": skipped,
        "errors": errors,
        "counts": {"targets": len(targets), "minted": len(minted), "skipped": len(skipped), "errors": len(errors)},
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
