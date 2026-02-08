from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", errors="replace")
    os.replace(tmp, path)


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8", errors="replace")
    os.replace(tmp, path)


def _match_root_clutter(name: str) -> str | None:
    n = name.strip()
    low = n.lower()
    if low in {"nul"}:
        return "nul_file"
    if low in {"__pycache__", ".pytest_cache", ".ruff_cache"}:
        return "python_cache_dir"
    if low in {"site"}:
        return "mkdocs_site_dir_legacy"
    if low in {".cleanup_schedule_state.json", ".a2a_worker_version_lock"}:
        return "runtime_state_file"
    if low.endswith(".log"):
        return "log_file"
    if low.endswith(".tmp"):
        return "tmp_file"
    if low.endswith(".ack"):
        return "ata_ack_file"
    if low.endswith(".result.json"):
        return "ata_result_file"
    return None


def audit_repo_root(repo_root: Path) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    """
    Returns: (violations, notices)
    - violations: clutter that should be removed/archived from repo root
    - notices: allowed-but-worth-noting items (informational)
    """
    root = repo_root.resolve()
    violations: List[Dict[str, str]] = []
    notices: List[Dict[str, str]] = []

    for p in sorted(root.iterdir(), key=lambda x: x.name.lower()):
        name = p.name
        # Ignore obvious required entries.
        if name in {".git", ".github", ".githooks"}:
            continue
        # artifacts/ is intentionally allowed (canonical output root), even though ignored in git.
        if name == "artifacts":
            continue
        # evidence/ exists as legacy tombstone dir (should be empty-ish).
        if name == "evidence":
            continue
        # IDE/user configs: allowed, but not part of SCC cleanliness focus.
        if name in {".vscode", ".idea", ".cursor", ".trae", ".gnupg", ".venv"}:
            notices.append({"path": name, "kind": "ide_or_user_state"})
            continue

        # Windows device aliases (e.g. NUL) can show up as "exists" but are not movable.
        if name.upper() == "NUL" and (not p.is_file()) and (not p.is_dir()):
            notices.append({"path": name, "kind": "windows_device"})
            continue

        kind = _match_root_clutter(name)
        if kind is None:
            continue
        if name.lower() == ".pytest_cache":
            # Often permission-locked in some setups; treat as notice if not readable.
            try:
                _ = list(p.iterdir())
            except Exception:
                notices.append({"path": name, "kind": "permission_locked_cache"})
                continue
        violations.append({"path": name, "kind": kind})

    return violations, notices


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=str(_repo_root()))
    ap.add_argument("--fail", action="store_true", help="Exit non-zero if violations exist.")
    args = ap.parse_args()

    repo_root = Path(args.repo_root).resolve()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = (repo_root / "artifacts" / "scc_state" / "reports").resolve()
    out_json = (out_dir / f"root_clutter_audit_{ts}.json").resolve()
    out_md = (out_dir / f"root_clutter_audit_{ts}.md").resolve()

    violations, notices = audit_repo_root(repo_root)
    payload: Dict[str, Any] = {
        "schema_version": "scc_root_clutter_audit.v0",
        "repo_root": str(repo_root),
        "ts_utc": _utc_now(),
        "violations": violations,
        "notices": notices,
    }
    _atomic_write_json(out_json, payload)

    lines = []
    lines.append(f"# Root Clutter Audit ({ts})")
    lines.append("")
    lines.append(f"- violations: `{len(violations)}`")
    lines.append(f"- notices: `{len(notices)}`")
    lines.append(f"- json_report: `{str(out_json.relative_to(repo_root))}`")
    lines.append("")
    if violations:
        lines.append("## Violations")
        for v in violations:
            lines.append(f"- `{v['path']}` ({v['kind']})")
        lines.append("")
        lines.append("Suggested fix:")
        lines.append("- `python tools/scc/ops/housekeeping.py --apply --include-site`")
        lines.append("")
    if notices:
        lines.append("## Notices")
        for n in notices:
            lines.append(f"- `{n['path']}` ({n['kind']})")
        lines.append("")
    _atomic_write_text(out_md, "\n".join(lines) + "\n")

    print(f"[audit] violations={len(violations)} notices={len(notices)}")
    print(f"[audit] report_md={str(out_md.relative_to(repo_root))}")
    if violations and args.fail:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
