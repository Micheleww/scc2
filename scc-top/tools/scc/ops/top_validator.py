#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SCC_TOP compliance validator (v0.1.0).

Goal: make SCC_TOP "runnable" by enforcing a minimal closed-loop doc topology:
- SSOT authority chain exists (docs/START_HERE.md -> docs/ssot/*)
- SSOT registry exists and required documents are present
- Mandatory doc trees embed OID YAML frontmatter (when applicable)

Evidence: writes a single report under artifacts/scc_state/top_validator/.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _read_json(path: Path) -> dict:
    try:
        return json.loads(_read_text(path) or "{}")
    except Exception:
        return {}


def _iso_utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _has_yaml_frontmatter_oid(md: str) -> tuple[bool, str]:
    """
    Minimal YAML frontmatter check:
    - first non-empty line is ---
    - a closing --- exists within first 80 lines
    - an `oid:` key exists inside the frontmatter
    """
    if not isinstance(md, str) or not md.strip():
        return False, "empty"
    lines = md.splitlines()
    # skip leading blank lines
    i0 = 0
    while i0 < len(lines) and not lines[i0].strip():
        i0 += 1
    if i0 >= len(lines) or lines[i0].strip() != "---":
        return False, "missing_frontmatter_open"
    end = None
    for j in range(i0 + 1, min(len(lines), i0 + 80)):
        if lines[j].strip() == "---":
            end = j
            break
    if end is None:
        return False, "missing_frontmatter_close"
    fm = "\n".join(lines[i0 + 1 : end])
    m = re.search(r"(?m)^oid\s*:\s*(\S+)", fm)
    if not m:
        return False, "missing_oid"
    oid_val = str(m.group(1) or "").strip()
    if oid_val.startswith("<MINT_") or oid_val == "<MINT_WITH_SCC_OID_GENERATOR>":
        return True, "placeholder_oid"
    return True, ""


def _looks_like_root_nav(text: str) -> bool:
    t = (text or "").lower()
    return ("docs/ssot" in t) or ("ssot" in t and "start_here" in t)


@dataclass
class Finding:
    kind: str
    path: str
    detail: str


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry", default=os.environ.get("SCC_SSOT_REGISTRY", "docs/ssot/registry.json"))
    ap.add_argument("--out-dir", default="artifacts/scc_state/top_validator")
    ap.add_argument("--max-missing", type=int, default=200)
    args = ap.parse_args()

    repo_root = _repo_root()
    registry_path = Path(args.registry)
    if not registry_path.is_absolute():
        registry_path = (repo_root / registry_path).resolve()

    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = (repo_root / out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    findings: list[Finding] = []

    # A) SSOT authority chain (root navigation exists and mentions SSOT)
    root_nav = (repo_root / "docs" / "START_HERE.md").resolve()
    if not root_nav.exists():
        findings.append(Finding("MISSING", "docs/START_HERE.md", "root navigation not found"))
    else:
        t = _read_text(root_nav)
        if not _looks_like_root_nav(t):
            findings.append(Finding("WARN", "docs/START_HERE.md", "does not obviously reference docs/ssot/ START_HERE"))

    # B) Registry exists and includes key docs
    if not registry_path.exists():
        findings.append(Finding("MISSING", str(registry_path.relative_to(repo_root)), "SSOT registry missing"))
        reg: dict[str, Any] = {}
    else:
        reg = _read_json(registry_path)

    canonical = reg.get("canonical") if isinstance(reg.get("canonical"), list) else []
    doc_ids = {str(x.get("doc_id")) for x in canonical if isinstance(x, dict)}

    required_doc_ids = [
        "SCC-TOP",
        "OID-SPEC",
        "UNIT-REGISTRY",
        "SINGLE-TRUTH-PRIORITY",
        "CANON-GOALS",
        "CANON-ROADMAP",
        "CANON-CURRENT-STATE",
        "CANON-ADR",
        "CANON-PROGRESS",
        "TASK-MODEL-CODES",
        "CONTRACT-MIN-SPEC",
        "EXECUTOR-VERIFIER-INTERFACES",
        "REVIEW-CADENCE-OUTPUTS",
        "METRICS-ACCEPTANCE",
    ]
    for did in required_doc_ids:
        if did not in doc_ids:
            findings.append(Finding("MISSING", str(registry_path.relative_to(repo_root)), f"registry missing doc_id={did}"))

    # C) Paths exist (from default_order + canonical list)
    paths: list[str] = []
    ctx = reg.get("context_assembly") if isinstance(reg.get("context_assembly"), dict) else {}
    default_order = ctx.get("default_order") if isinstance(ctx.get("default_order"), list) else []
    for p in default_order:
        if isinstance(p, str) and p.strip():
            paths.append(p.strip())
    for item in canonical:
        if isinstance(item, dict):
            p = item.get("canonical_path")
            if isinstance(p, str) and p.strip():
                paths.append(p.strip())
    paths = list(dict.fromkeys(paths))  # preserve order + de-dupe

    missing_count = 0
    for rel in paths:
        rp = (repo_root / rel).resolve()
        if not rp.exists():
            findings.append(Finding("MISSING", rel, "path does not exist"))
            missing_count += 1
            if missing_count >= int(args.max_missing or 200):
                findings.append(Finding("INFO", "-", f"stopped after max_missing={args.max_missing}"))
                break

    # D) OID embedding (mandatory trees)
    mandatory_embed_prefixes = [
        "docs/ssot/",
        "docs/CANONICAL/",
        "docs/ARCH/",
        "docs/DOCOPS/",
        "docs/ARCH/contracts/",
    ]
    index_only_prefixes = [
        "docs/REPORT/",
        "docs/ssot/07_reports_evidence/",
    ]

    def _should_check_oid(rel: str) -> bool:
        rel = rel.replace("\\", "/")
        if not rel.endswith(".md"):
            return False
        for pfx in index_only_prefixes:
            if rel.startswith(pfx):
                return False
        return any(rel.startswith(pfx) for pfx in mandatory_embed_prefixes)

    for rel in paths:
        if not _should_check_oid(rel):
            continue
        rp = (repo_root / rel).resolve()
        if not rp.exists() or not rp.is_file():
            continue
        ok, why = _has_yaml_frontmatter_oid(_read_text(rp))
        if not ok:
            findings.append(Finding("FAIL", rel, f"OID frontmatter invalid: {why}"))
        elif why == "placeholder_oid":
            findings.append(Finding("WARN", rel, "OID is a placeholder; mint via SCC OID Generator to become compliant"))

    # Report
    stamp = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
    report = out_dir / f"top_validator__{stamp}Z.md"
    lines: list[str] = []
    lines.append(f"# SCC_TOP compliance report ({_iso_utc()})")
    lines.append("")
    lines.append(f"- registry: `{str(registry_path.relative_to(repo_root)) if registry_path.exists() else str(registry_path)}`")
    lines.append(f"- paths_checked: {len(paths)}")
    lines.append(f"- findings: {len(findings)}")
    lines.append("")
    if findings:
        lines.append("## Findings")
        for f in findings:
            lines.append(f"- {f.kind}: `{f.path}` — {f.detail}")
    else:
        lines.append("## Findings")
        lines.append("- OK: no findings")
    report.write_text("\n".join(lines) + "\n", encoding="utf-8", errors="replace")

    # Exit code policy: MISSING/FAIL are blocking; WARN/INFO are non-blocking.
    blocking = [f for f in findings if f.kind in ("MISSING", "FAIL")]
    print(str(report))
    return 0 if not blocking else 1


if __name__ == "__main__":
    raise SystemExit(main())
