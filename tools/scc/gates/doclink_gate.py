import pathlib
import re


def _norm_rel(p: str) -> str:
    return p.replace("\\", "/").lstrip("./")


def _extract_touched_from_patch(repo: pathlib.Path, submit: dict) -> list[str]:
    artifacts = submit.get("artifacts") or {}
    patch_rel = artifacts.get("patch_diff") or ""
    if not patch_rel:
        return []
    patch_path = repo / _norm_rel(str(patch_rel))
    if not patch_path.exists():
        return []

    root = str(repo.resolve()).replace("\\", "/").rstrip("/")
    touched: list[str] = []
    try:
        for line in patch_path.read_text(encoding="utf-8", errors="replace").splitlines():
            s = line.strip()
            if s.startswith("diff --git "):
                parts = s.split()
                if len(parts) >= 4:
                    touched.append(parts[3])
            elif s.startswith("+++ "):
                parts = s.split()
                if len(parts) >= 2:
                    touched.append(parts[1])
    except Exception:
        return []

    out: list[str] = []
    for p in touched:
        pp = _norm_rel(str(p))
        if pp in ("/dev/null", "dev/null"):
            continue
        if pp.startswith(("a/", "b/")):
            pp = pp[2:]
        # Some executors emit absolute paths (e.g. b/C:/scc/...). Normalize back to repo-relative.
        pp_norm = pp.replace("\\", "/")
        if pp_norm.lower().startswith(root.lower() + "/"):
            pp_norm = pp_norm[len(root) + 1 :]
        # Also strip drive-rooted prefix like C:/scc/
        if "/:" not in pp_norm and ":" in pp_norm[:3]:
            # looks like "C:/..." or "C:\\..."
            if pp_norm.lower().startswith(root.lower() + "/"):
                pp_norm = pp_norm[len(root) + 1 :]
        out.append(_norm_rel(pp_norm))
    # de-dup, preserve order
    seen = set()
    deduped: list[str] = []
    for p in out:
        if not p or p in seen:
            continue
        seen.add(p)
        deduped.append(p)
    return deduped


_DEP_FILES = {
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "requirements.txt",
    "pyproject.toml",
    "poetry.lock",
    "Cargo.toml",
    "Cargo.lock",
}

_ADR_PREFIXES = [
    "Context:",
    "Decision:",
    "Alternatives:",
    "Consequences:",
    "Migration:",
    "Owner:",
]


def _adr_is_valid(text: str) -> bool:
    return all(re.search(rf"^{re.escape(p)}", text, flags=re.MULTILINE) for p in _ADR_PREFIXES)


def run(repo: pathlib.Path, submit: dict) -> list[str]:
    errors: list[str] = []
    changed = [_norm_rel(x) for x in (submit.get("changed_files") or [])]
    new_files = [_norm_rel(x) for x in (submit.get("new_files") or [])]
    touched = changed + new_files + _extract_touched_from_patch(repo, submit)

    triggers = False
    for p in touched:
        if p.startswith(("contracts/", "roles/", "skills/", "eval/")):
            triggers = True
        if p == "factory_policy.json":
            triggers = True
        if pathlib.PurePosixPath(p).name in _DEP_FILES:
            triggers = True

    adr_files = [p for p in touched if p.startswith("docs/adr/ADR-") and p.endswith(".md")]
    if triggers and not adr_files:
        errors.append("ADR required for dependency/dir/protocol/control-plane changes (add docs/adr/ADR-YYYYMMDD-*.md)")

    for rel in adr_files:
        path = repo / rel
        if not path.exists():
            errors.append(f"ADR listed but missing on disk: {rel}")
            continue
        text = path.read_text(encoding="utf-8")
        if not _adr_is_valid(text):
            errors.append(f"ADR missing required 6-line template prefixes: {rel}")

    return errors
