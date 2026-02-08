from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def file_contains(p: Path, needle: str) -> bool:
    try:
        return needle in p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return False


def _is_demoted_placeholder(p: Path) -> bool:
    """
    Detect the repo's standard demotion redirect stub.
    """
    try:
        head = p.read_text(encoding="utf-8", errors="replace").splitlines()[:12]
        if not head:
            return False
        h = "\n".join(head)
        return ("（占位跳转）" in h) or ("已降级为占位跳转" in h)
    except Exception:
        return False


def is_placeholder_doc(p: Path) -> bool:
    try:
        head = p.read_text(encoding="utf-8", errors="replace").splitlines()[:8]
        txt = "\n".join(head)
        return ("索引占位文件" in txt) or ("已迁移到隔离观察区" in txt)
    except Exception:
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=r"d:\quantsys")
    args = ap.parse_args()

    repo_root = Path(args.repo_root).resolve()
    docs = repo_root / "docs"
    artifacts = repo_root / "artifacts" / "scc_state"
    artifacts.mkdir(parents=True, exist_ok=True)

    # v0.1.0 SSOT single-entrypoint policy: docs/START_HERE.md is the only entrypoint.
    # SSOT Trunk provides section indices under docs/ssot/.
    required = [
        repo_root / "docs" / "START_HERE.md",
        repo_root / "docs" / "ssot" / "START_HERE.md",
        repo_root / "docs" / "ssot" / "00_index.md",
        repo_root / "docs" / "ssot" / "01_conventions" / "DOCFLOW_SSOT__v0.1.0.md",
        repo_root / "docs" / "ssot" / "02_architecture" / "SCC_TOP.md",
        repo_root / "docs" / "ssot" / "registry.json",
        repo_root / "docs" / "INPUTS" / "README.md",
    ]
    missing = [p for p in required if not p.exists()]
    if missing:
        raise SystemExit("missing required: " + ", ".join(str(p) for p in missing))

    entrypoints = [
        "docs/START_HERE.md",
        "docs/ssot/START_HERE.md",
        "docs/ssot/00_index.md",
        "docs/ssot/registry.json",
        "docs/ssot/02_architecture/SCC_TOP.md",
        "docs/INPUTS/README.md",
        "docs/INPUTS/WEBGPT/index.md",
        "docs/INPUTS/WEBGPT/memory.md",
        "docs/ssot/05_runbooks/SCC_RUNBOOK__v0.1.0.md",
        "docs/ssot/05_runbooks/SCC_OBSERVABILITY_SPEC__v0.1.0.md",
    ]

    lines: list[str] = []
    lines.append("# Docflow Audit Report")
    lines.append("")
    lines.append(f"- generated_at: \"{utc_now_iso()}\"")
    lines.append(f"- repo_root: \"{repo_root}\"")
    lines.append("")

    lines.append("## EntryPoints")
    lines.append("")
    for e in entrypoints:
        ok = (repo_root / Path(e)).exists()
        lines.append(f"- {e} : {'OK' if ok else 'MISSING'}")
    lines.append("")

    lines.append("## Legacy Navigation (should be demoted)")
    lines.append("")
    legacy: list[str] = []
    # Known legacy navigation files.
    for p0 in [
        repo_root / "docs" / "arch" / "00_index.md",
        repo_root / "docs" / "arch" / "project_navigation__v0.1.0__ACTIVE__20260115.md",
    ]:
        if p0.exists():
            legacy.append(str(p0.relative_to(repo_root)).replace("\\", "/"))
    # Heuristic: any *00_index.md outside SSOT is treated as legacy navigation.
    if docs.exists():
        for p in docs.rglob("00_index.md"):
            if not p.is_file():
                continue
            rel = str(p.relative_to(repo_root)).replace("\\", "/")
            if rel.startswith("docs/ssot/"):
                continue
            if rel not in legacy:
                legacy.append(rel)
    if legacy:
        demoted: list[str] = []
        needs: list[str] = []
        for rel in sorted(set(legacy)):
            abs_p = (repo_root / Path(rel)).resolve()
            if abs_p.exists() and abs_p.is_file() and _is_demoted_placeholder(abs_p):
                demoted.append(rel)
            else:
                needs.append(rel)
        lines.append(f"- total: {len(sorted(set(legacy)))}")
        lines.append(f"- demoted: {len(demoted)}")
        lines.append(f"- needs_demote: {len(needs)}")
        lines.append("")
        lines.append("### Demoted (redirect stubs)")
        if demoted:
            for rel in demoted:
                lines.append(f"- {rel}")
        else:
            lines.append("- none")
        lines.append("")
        lines.append("### Needs demotion")
        if needs:
            for rel in needs:
                lines.append(f"- {rel}")
        else:
            lines.append("- none")
    else:
        lines.append("- none")
    lines.append("")

    lines.append("## Placeholder Docs (moved to isolated_observatory)")
    lines.append("")
    placeholders: list[str] = []
    if docs.exists():
        for p in docs.rglob("*.md"):
            if p.is_file() and is_placeholder_doc(p):
                placeholders.append(str(p.relative_to(repo_root)).replace("\\", "/"))
    if placeholders:
        for p in sorted(placeholders):
            lines.append(f"- {p}")
    else:
        lines.append("- none")
    lines.append("")

    lines.append("## SSOT Link Check")
    lines.append("")
    start_here = repo_root / "docs" / "START_HERE.md"
    lines.append(
        "- docs/START_HERE.md -> docs/ssot/01_conventions/DOCFLOW_SSOT__v0.1.0.md : "
        + ("OK" if file_contains(start_here, "docs/ssot/01_conventions/DOCFLOW_SSOT__v0.1.0.md") else "WARN")
    )
    ssot_start = repo_root / "docs" / "ssot" / "START_HERE.md"
    lines.append(
        "- docs/ssot/START_HERE.md mentions docs/START_HERE.md (no 2nd entrypoint) : "
        + ("OK" if file_contains(ssot_start, "docs/START_HERE.md") else "WARN")
    )
    lines.append("")

    out = artifacts / f"docflow_audit__{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[docflow_audit] wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
