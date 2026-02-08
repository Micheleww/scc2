#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SSOT_FRONTMATTER_BOOTSTRAP_V010 — deterministic YAML frontmatter bootstrapper.

Goal:
- For SSOT markdown files that lack YAML frontmatter, prepend a minimal frontmatter block
  with placeholder OID + required metadata, without changing the body content.
- This enables OID minting + oid_validator fail-closed gate without fabricating document content.

Non-goals:
- Do NOT rewrite existing frontmatter.
- Do NOT invent/expand document bodies.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


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


def _has_frontmatter(text: str) -> bool:
    lines = (text or "").splitlines()
    return bool(lines) and lines[0].strip() == "---"


@dataclass(frozen=True)
class Meta:
    layer: str
    primary_unit: str
    tags: List[str]
    status: str = "active"


def _meta_for_path(rel: str) -> Meta:
    """
    Minimal deterministic mapping (v0.1.0).
    """
    p = (rel or "").replace("\\", "/")
    if p == "docs/ssot/START_HERE.md":
        return Meta(layer="DOCOPS", primary_unit="S.NAV_UPDATE", tags=["V.GUARD"])
    if p.startswith("docs/ssot/00_") or p.endswith("/index.md") or p.endswith("/00_index.md"):
        return Meta(layer="DOCOPS", primary_unit="S.NAV_UPDATE", tags=["V.GUARD"])
    if p.startswith("docs/ssot/01_conventions/"):
        return Meta(layer="DOCOPS", primary_unit="V.GUARD", tags=["S.NAV_UPDATE"])
    if p.startswith("docs/ssot/02_architecture/"):
        return Meta(layer="ARCH", primary_unit="A.PLANNER", tags=["S.ADR"])
    if p.startswith("docs/ssot/03_agent_playbook/"):
        return Meta(layer="DOCOPS", primary_unit="A.ROUTER", tags=["V.SKILL_GUARD"])
    if p.startswith("docs/ssot/04_contracts/"):
        return Meta(layer="DOCOPS", primary_unit="K.CONTRACT_DOC", tags=["K.SCHEMA"])
    if p.startswith("docs/ssot/05_runbooks/"):
        return Meta(layer="DOCOPS", primary_unit="V.GUARD", tags=["V.VERDICT"])
    if p.startswith("docs/ssot/06_inputs/"):
        return Meta(layer="DOCOPS", primary_unit="G.INTAKE_ROUTING", tags=["R.CHAT_WEB"])
    if p.startswith("docs/ssot/07_reports_evidence/"):
        return Meta(layer="REPORT", primary_unit="P.REPORT", tags=["V.VERDICT"])
    return Meta(layer="DOCOPS", primary_unit="V.GUARD", tags=["S.NAV_UPDATE"])


def _frontmatter_block(meta: Meta) -> str:
    tags = ", ".join(meta.tags or [])
    return (
        "---\n"
        "oid: <MINT_WITH_SCC_OID_GENERATOR>\n"
        f"layer: {meta.layer}\n"
        f"primary_unit: {meta.primary_unit}\n"
        f"tags: [{tags}]\n"
        f"status: {meta.status}\n"
        "---\n\n"
    )


def _iter_md_files(root: Path) -> List[Path]:
    out: List[Path] = []
    if not root.exists():
        return out
    for p in root.rglob("*.md"):
        if p.is_file():
            out.append(p)
    out.sort(key=lambda x: str(x))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Bootstrap SSOT markdown frontmatter (v0.1.0).")
    ap.add_argument("--root", default="docs/ssot", help="Repo-relative root to scan (default: docs/ssot).")
    ap.add_argument("--apply", action="store_true", help="Apply changes (default is dry-run).")
    ap.add_argument("--limit", type=int, default=0, help="Optional cap on number of files to modify.")
    ap.add_argument("--area", default="control_plane")
    ap.add_argument("--taskcode", default="SSOT_FRONTMATTER_BOOTSTRAP_V010")
    args = ap.parse_args()

    repo_root = _repo_root()
    root = Path(args.root)
    if not root.is_absolute():
        root = (repo_root / root).resolve()
    if not root.exists():
        print(json.dumps({"ok": False, "error": "missing_root", "root": str(root)}, ensure_ascii=False, indent=2))
        return 2

    changed: List[Dict[str, str]] = []
    skipped: List[Dict[str, str]] = []

    files = _iter_md_files(root)
    for p in files:
        rel = _to_repo_rel(repo_root, p)
        if rel.startswith("docs/REPORT/") or rel.startswith("docs/INPUTS/"):
            skipped.append({"path": rel, "reason": "excluded_root"})
            continue
        txt = _read_text(p)
        if _has_frontmatter(txt):
            skipped.append({"path": rel, "reason": "already_has_frontmatter"})
            continue
        meta = _meta_for_path(rel)
        new_txt = _frontmatter_block(meta) + (txt or "")
        if bool(args.apply):
            _write_text(p, new_txt if new_txt.endswith("\n") else (new_txt + "\n"))
        changed.append({"path": rel, "layer": meta.layer, "primary_unit": meta.primary_unit})
        if args.limit and len(changed) >= int(args.limit):
            break

    payload = {
        "ok": True,
        "schema_version": "v0.1.0",
        "taskcode": str(args.taskcode),
        "root": _to_repo_rel(repo_root, root),
        "apply": bool(args.apply),
        "generated_at_utc": _utc_now(),
        "counts": {"changed": len(changed), "skipped": len(skipped), "scanned": len(files)},
        "changed": changed[:5000],
        "skipped_sample": skipped[:200],
    }

    if bool(args.apply):
        out_dir = (repo_root / "docs" / "REPORT" / str(args.area) / "artifacts" / str(args.taskcode) / _stamp_utc()).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "frontmatter_bootstrap_summary.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", errors="replace"
        )
        out_md = (repo_root / "docs" / "REPORT" / str(args.area) / f"REPORT__{args.taskcode}__{_date_utc()}.md").resolve()
        out_md.parent.mkdir(parents=True, exist_ok=True)
        out_md.write_text(
            "\n".join(
                [
                    f"# SSOT Frontmatter Bootstrap — {args.taskcode} (v0.1.0)",
                    "",
                    f"- generated_at_utc: `{payload['generated_at_utc']}`",
                    f"- root: `{payload['root']}`",
                    f"- changed: `{payload['counts']['changed']}`",
                    f"- skipped: `{payload['counts']['skipped']}`",
                    f"- summary_json: `{_to_repo_rel(repo_root, out_dir / 'frontmatter_bootstrap_summary.json')}`",
                    "",
                    "## Sample changed",
                    "| path | layer | primary_unit |",
                    "|---|---|---|",
                    *[f"| {c['path']} | {c['layer']} | {c['primary_unit']} |" for c in changed[:60]],
                    "",
                ]
            ).strip()
            + "\n",
            encoding="utf-8",
            errors="replace",
        )
        print(str(out_md))
        print(str(out_dir / "frontmatter_bootstrap_summary.json"))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
