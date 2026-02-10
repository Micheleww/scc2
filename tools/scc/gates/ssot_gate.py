import os
import pathlib
import re

from tools.scc.lib.utils import norm_rel


def _extract_index_refs(index_text: str) -> set[str]:
    refs = set()
    for m in re.finditer(r"`([^`]+)`", index_text):
        ref = norm_rel(m.group(1))
        if ref.startswith("docs/"):
            refs.add(ref)
    return refs


def run(repo: pathlib.Path, submit: dict) -> list[str]:
    errors: list[str] = []
    warnings: list[str] = []
    index_path = repo / "docs/INDEX.md"
    nav_path = repo / "docs/NAVIGATION.md"

    if not index_path.exists():
        return {"errors": ["missing docs/INDEX.md"], "warnings": []}
    if not nav_path.exists():
        warnings.append("missing docs/NAVIGATION.md")

    index_text = index_path.read_text(encoding="utf-8")
    registered = _extract_index_refs(index_text)

    def is_exempt_doc(path: str) -> bool:
        return path.startswith("docs/archive/") or path.startswith("docs/adr/ADR-")

    changed = [norm_rel(x) for x in (submit.get("changed_files") or [])]
    new_files = [norm_rel(x) for x in (submit.get("new_files") or [])]
    touched = changed + new_files

    for p in touched:
        if not p.startswith("docs/") or is_exempt_doc(p):
            continue
        if p == "docs/INDEX.md":
            continue
        if p.endswith(".md") and p not in registered:
            warnings.append(f"unregistered docs file (must be listed in docs/INDEX.md): {p}")

    for ref in sorted(registered):
        if not (repo / ref).exists():
            errors.append(f"docs/INDEX.md references missing file: {ref}")

    control_plane_touches = any(
        p.startswith(prefix) for p in touched for prefix in ("contracts/", "roles/", "skills/", "eval/", "config/factory_policy.json")
    )
    if control_plane_touches and ("docs/INDEX.md" not in changed and "docs/NAVIGATION.md" not in changed):
        errors.append("control-plane changed but docs/INDEX.md or docs/NAVIGATION.md not updated (SSOT drift gate)")

    # Optional: strict mode upgrades warnings to errors.
    strict = str(os.environ.get("SSOT_GATE_STRICT") or "false").lower() == "true"
    if strict and warnings:
        errors += [f"WARN_UPGRADED: {w}" for w in warnings]
        warnings = []

    return {"errors": errors, "warnings": warnings}
