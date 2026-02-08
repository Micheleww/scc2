from __future__ import annotations

import argparse
import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


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


def _safe_rel(repo_root: Path, p: Path) -> str:
    try:
        return str(p.resolve().relative_to(repo_root.resolve()))
    except Exception:
        return str(p.resolve())


@dataclass(frozen=True)
class MoveOp:
    src: str
    dst: str
    reason: str
    status: str = "planned"
    error: str | None = None


def _default_root_globs() -> List[str]:
    return [
        "*.ack",
        "*.result.json",
        "*.log",
        "*.zip",
        "*.7z",
        "*.msi",
        "*.exe",
        "audit.log",
        "selftest.log",
        "test_results.log",
        "worker.log",
        "quant_system.log",
        "NUL",
        ".a2a_worker_version_lock",
        ".cleanup_schedule_state.json",
        "site",
    ]


def _collect_candidates(repo_root: Path, *, include_site: bool = True) -> List[Tuple[Path, str]]:
    out: List[Tuple[Path, str]] = []
    root = repo_root.resolve()
    for pat in _default_root_globs():
        if pat in {"*.zip", "*.7z", "*.msi", "*.exe"}:
            # Large binaries are only considered clutter when explicitly included (to avoid surprises).
            continue
        if pat == "site" and not include_site:
            continue
        for p in root.glob(pat):
            if not p.exists():
                continue
            # Avoid moving repo structure accidentally: only root-level items.
            if p.parent.resolve() != root:
                continue
            if p.name in {".git", ".github", ".githooks"}:
                continue
            out.append((p, f"root_glob:{pat}"))
    # Extra explicit candidates that tend to drift.
    for name in ["__pycache__", ".pytest_cache", ".ruff_cache"]:
        p = (root / name).resolve()
        if p.exists() and p.is_dir():
            out.append((p, f"root_dir:{name}"))
    # Dedupe by resolved path.
    seen = set()
    dedup: List[Tuple[Path, str]] = []
    for p, reason in out:
        k = str(p.resolve()).lower()
        if k in seen:
            continue
        seen.add(k)
        dedup.append((p, reason))
    return dedup


def _collect_root_binaries(repo_root: Path) -> List[Tuple[Path, str]]:
    root = repo_root.resolve()
    out: List[Tuple[Path, str]] = []
    for pat in ("*.zip", "*.7z", "*.msi", "*.exe"):
        for p in root.glob(pat):
            if not p.exists():
                continue
            if p.parent.resolve() != root:
                continue
            out.append((p, f"root_binary:{pat}"))
    return out


def _move_to_archive(*, repo_root: Path, p: Path, archive_root: Path, reason: str, apply: bool) -> Optional[MoveOp]:
    src = p.resolve()
    rel_src = _safe_rel(repo_root, src)
    if src.name.upper() == "NUL" and (not src.is_file()) and (not src.is_dir()):
        # "NUL" is a Windows device; attempts to move/delete it are meaningless.
        return MoveOp(src=rel_src, dst="", reason="windows_device:NUL", status="skipped", error="windows_device")
    # Windows reserved device names (e.g. "NUL") are problematic as destination names.
    # If such a file exists, archive it under a safe name.
    dst_name = src.name
    if src.name.upper() == "NUL":
        dst_name = f"NUL__archived"
    dst = (archive_root / dst_name).resolve()
    # Collision-safe suffix.
    if dst.exists():
        stem = src.name
        for i in range(1, 1000):
            cand = (archive_root / f"{stem}__{i}").resolve()
            if not cand.exists():
                dst = cand
                break
    if apply:
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.move(str(src), str(dst))
            return MoveOp(src=rel_src, dst=_safe_rel(repo_root, dst), reason=reason, status="moved")
        except Exception as e:
            return MoveOp(src=rel_src, dst=_safe_rel(repo_root, dst), reason=reason, status="failed", error=str(e))
    return MoveOp(src=rel_src, dst=_safe_rel(repo_root, dst), reason=reason, status="planned")


def _migrate_legacy_permission_decisions(repo_root: Path) -> None:
    """
    If legacy path exists (repo_root/evidence/permission_decisions), copy it into canonical locations.
    """
    legacy = (repo_root / "evidence" / "permission_decisions").resolve()
    if not legacy.exists():
        return
    # Inline a minimal subset of migrate script behavior (copy-only) to avoid import issues.
    target = (repo_root / "artifacts" / "scc_state" / "evidence" / "permission_decisions").resolve()
    queue_target = (repo_root / "artifacts" / "scc_state" / "approval_queue").resolve()
    target.mkdir(parents=True, exist_ok=True)
    queue_target.mkdir(parents=True, exist_ok=True)

    for p in sorted(legacy.glob("*.json")):
        out = (target / p.name).resolve()
        if out.exists():
            continue
        try:
            shutil.copy2(p, out)
        except Exception:
            pass

    legacy_q = (legacy / "queue.json").resolve()
    target_q_old = (target / "queue.json").resolve()
    target_q_new = (queue_target / "permission_pdp_queue.json").resolve()
    if legacy_q.exists():
        if not target_q_old.exists():
            try:
                shutil.copy2(legacy_q, target_q_old)
            except Exception:
                pass
        if not target_q_new.exists():
            try:
                shutil.copy2(legacy_q, target_q_new)
            except Exception:
                pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=str(_repo_root()))
    ap.add_argument("--apply", action="store_true", help="Actually move files (default is dry-run).")
    ap.add_argument("--include-site", action="store_true", help="Also archive repo_root/site (mkdocs output).")
    ap.add_argument(
        "--include-tracked",
        action="store_true",
        help="Also archive git-tracked files (default: skip tracked to avoid accidental repo changes).",
    )
    ap.add_argument(
        "--purge-caches",
        action="store_true",
        help="If cache dirs cannot be moved, delete them (python caches only).",
    )
    ap.add_argument(
        "--purge-nul",
        action="store_true",
        help="If a root-level 'NUL' file exists and cannot be moved, delete it.",
    )
    ap.add_argument(
        "--include-binaries",
        action="store_true",
        help="Also isolate root-level *.zip/*.7z/*.msi/*.exe into the archive.",
    )
    ap.add_argument("--archive-subdir", default="", help="Override archive subdir under artifacts/_root_clutter/<ts>/")
    args = ap.parse_args()

    repo_root = Path(args.repo_root).resolve()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    archive_root = (repo_root / "artifacts" / "_root_clutter" / ts).resolve()
    if str(args.archive_subdir or "").strip():
        archive_root = (archive_root / str(args.archive_subdir).strip()).resolve()

    report_dir = (repo_root / "artifacts" / "scc_state" / "reports").resolve()
    report_dir.mkdir(parents=True, exist_ok=True)
    report_json = (report_dir / f"housekeeping_{ts}.json").resolve()
    report_md = (report_dir / f"housekeeping_{ts}.md").resolve()

    # If legacy evidence exists, migrate permission decisions before archiving.
    _migrate_legacy_permission_decisions(repo_root)

    moves: List[MoveOp] = []
    candidates = _collect_candidates(repo_root, include_site=bool(args.include_site))
    if args.include_binaries:
        candidates.extend(_collect_root_binaries(repo_root))
    for p, reason in candidates:
        try:
            # Never archive the canonical artifacts root.
            if p.resolve() == (repo_root / "artifacts").resolve():
                continue
            # Keep repo_root/evidence directory but remove its noisy contents by archiving subfolders.
            if p.resolve() == (repo_root / "evidence").resolve():
                continue
            if not args.include_tracked:
                try:
                    import subprocess

                    r = subprocess.run(
                        ["git", "ls-files", "--error-unmatch", str(p.name)],
                        cwd=str(repo_root),
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=5,
                    )
                    if int(r.returncode) == 0:
                        continue
                except Exception:
                    pass
            op = _move_to_archive(repo_root=repo_root, p=p, archive_root=archive_root, reason=reason, apply=bool(args.apply))
            if op is not None:
                moves.append(op)

                # Optional purge fallback for python cache dirs.
                if args.apply and op.status == "failed" and args.purge_caches:
                    try:
                        if Path(p).name.lower() in {"__pycache__", ".pytest_cache", ".ruff_cache"} and Path(p).is_dir():
                            shutil.rmtree(str(p), ignore_errors=True)
                            moves.append(
                                MoveOp(
                                    src=_safe_rel(repo_root, Path(p)),
                                    dst="",
                                    reason="purge_cache_dir",
                                    status="deleted",
                                    error=None,
                                )
                            )
                    except Exception:
                        pass

                if args.apply and op.status == "failed" and args.purge_nul:
                    try:
                        if Path(p).name.upper() == "NUL" and Path(p).is_file():
                            try:
                                Path(p).unlink(missing_ok=True)  # py>=3.8
                            except TypeError:
                                if Path(p).exists():
                                    Path(p).unlink()
                            moves.append(
                                MoveOp(
                                    src=_safe_rel(repo_root, Path(p)),
                                    dst="",
                                    reason="purge_nul_file",
                                    status="deleted",
                                    error=None,
                                )
                            )
                    except Exception:
                        pass
        except Exception:
            continue

    # Special handling: legacy evidence/permission_decisions -> archive the folder (after migration).
    legacy_pd = (repo_root / "evidence" / "permission_decisions").resolve()
    if legacy_pd.exists() and legacy_pd.is_dir():
        try:
            op = _move_to_archive(
                _move_to_archive(
                    repo_root=repo_root,
                    p=legacy_pd,
                    archive_root=archive_root,
                    reason="legacy_permission_decisions_dir",
                    apply=bool(args.apply),
                )
            )
            if op is not None:
                moves.append(op)
        except Exception:
            pass

    # Ensure evidence/README.md exists as a tombstone to prevent future writes.
    evidence_dir = (repo_root / "evidence").resolve()
    if evidence_dir.exists() and evidence_dir.is_dir():
        readme = (evidence_dir / "README.md").resolve()
        if not readme.exists():
            txt = (
                "# Legacy evidence directory (Do Not Use)\n\n"
                "This `evidence/` path is deprecated.\n\n"
                "- System evidence: `artifacts/scc_state/evidence/`\n"
                "- Task evidence: `artifacts/scc_tasks/<task_id>/evidence/`\n\n"
                "If you find files here, run:\n"
                "`python tools/scc/ops/housekeeping.py --apply --include-site`\n"
            )
            if args.apply:
                evidence_dir.mkdir(parents=True, exist_ok=True)
                _atomic_write_text(readme, txt)

    payload: Dict[str, Any] = {
        "schema_version": "scc_housekeeping.v0",
        "repo_root": str(repo_root),
        "ts_utc": _utc_now(),
        "apply": bool(args.apply),
        "archive_root": _safe_rel(repo_root, archive_root),
        "purge_caches": bool(args.purge_caches),
        "purge_nul": bool(args.purge_nul),
        "moves": [m.__dict__ for m in moves if m is not None],
    }
    _atomic_write_json(report_json, payload)

    lines = []
    lines.append(f"# SCC Housekeeping ({ts})")
    lines.append("")
    lines.append(f"- apply: `{payload['apply']}`")
    lines.append(f"- archive_root: `{payload['archive_root']}`")
    lines.append(f"- moved_count: `{len(payload['moves'])}`")
    lines.append("")
    for m in payload["moves"]:
        lines.append(f"- `{m['src']}` -> `{m['dst']}` ({m['reason']})")
    lines.append("")
    lines.append(f"- json_report: `{_safe_rel(repo_root, report_json)}`")
    _atomic_write_text(report_md, "\n".join(lines) + "\n")

    print(f"[housekeeping] apply={payload['apply']}")
    print(f"[housekeeping] archive_root={payload['archive_root']}")
    print(f"[housekeeping] moved_count={len(payload['moves'])}")
    print(f"[housekeeping] report_md={_safe_rel(repo_root, report_md)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
