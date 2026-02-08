from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

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


def _safe_rel(repo_root: Path, p: Path) -> str:
    try:
        return str(p.resolve().relative_to(repo_root.resolve())).replace("/", "\\")
    except Exception:
        return str(p.resolve())


def _git_untracked(repo_root: Path) -> List[str]:
    r = subprocess.run(
        ["git", "status", "--porcelain=v1", "-uall"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    out: List[str] = []
    for ln in (r.stdout or "").splitlines():
        if ln.startswith("?? "):
            out.append(_decode_git_path(ln[3:].strip()))
    return out


def _decode_git_path(s: str) -> str:
    s = str(s or "").strip()
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        inner = s[1:-1]
        out_bytes = bytearray()
        i = 0
        while i < len(inner):
            ch = inner[i]
            if ch != "\\":
                out_bytes.extend(ch.encode("utf-8", errors="replace"))
                i += 1
                continue
            i += 1
            if i >= len(inner):
                out_bytes.extend(b"\\")
                break
            esc = inner[i]
            if esc in {'\\', '"'}:
                out_bytes.extend(esc.encode("utf-8"))
                i += 1
                continue
            if esc == "n":
                out_bytes.extend(b"\n")
                i += 1
                continue
            if esc == "t":
                out_bytes.extend(b"\t")
                i += 1
                continue
            if esc == "r":
                out_bytes.extend(b"\r")
                i += 1
                continue
            if esc.isdigit():
                j = i
                digits = []
                while j < len(inner) and len(digits) < 3 and inner[j].isdigit():
                    digits.append(inner[j])
                    j += 1
                try:
                    out_bytes.append(int("".join(digits), 8) & 0xFF)
                except Exception:
                    out_bytes.extend(("\\ " + "".join(digits)).encode("utf-8", errors="replace"))
                i = j
                continue
            out_bytes.extend(("\\" + esc).encode("utf-8", errors="replace"))
            i += 1
        try:
            return out_bytes.decode("utf-8", errors="replace")
        except Exception:
            return inner
    return s


def _git_has_tracked_under(repo_root: Path, path: str) -> bool:
    """
    Returns True if git tracks this path (or anything under it).
    """
    try:
        r = subprocess.run(
            ["git", "ls-files", "--", path],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        return bool((r.stdout or "").strip())
    except Exception:
        return False


def _default_prefixes() -> List[str]:
    """
    Conservative: quarantine obvious noise/3rd-party/build outputs.
    """
    return [
        # Major noise source (3rd-party app / extracted repo)
        "tools/ui-tars-desktop",
        # Evidence-like / generated report folders outside canonical artifacts/
        "taskhub/evidence",
        "reports/config_drift",
        "reports/evidence",
        # Extracted/duplicated repos
        "frequi-main",
        "cursor-cli-windows/dist-package",
        # Common user data that should not inflate workspace scans
        "freqtrade-strategies-main/user_data",
        "ai_collaboration/data",
        # Extracted directory with spaces that is often C-quoted in porcelain.
        "shoucuo cursor",
    ]


def _match_any_prefix(path: str, prefixes: Iterable[str]) -> Optional[str]:
    p = path.replace("\\", "/").strip().lstrip("./")
    for pref in prefixes:
        pr = pref.replace("\\", "/").strip().lstrip("./")
        if not pr:
            continue
        if p == pr or p.startswith(pr + "/"):
            return pref
    return None


@dataclass(frozen=True)
class QuarantineOp:
    src: str
    dst: str
    prefix: str
    status: str
    error: Optional[str] = None


def _unique_top_targets(untracked: List[str], prefixes: List[str]) -> List[Tuple[str, str]]:
    """
    Choose minimal move targets: prefer moving top-level directories when possible.
    Returns list of (target_path, matched_prefix).
    """
    targets: Dict[str, str] = {}
    for p in untracked:
        m = _match_any_prefix(p, prefixes)
        if not m:
            continue
        # Move at the prefix root (directory or file), not each individual file.
        pref = m.replace("\\", "/").strip().lstrip("./")
        targets[pref] = m
    # Sort deeper first? We actually want to move broader first (top-level), but keep stable.
    out = sorted(targets.items(), key=lambda kv: (kv[0].count("/"), kv[0].lower()))
    return [(k, v) for k, v in out]


def _move_path(repo_root: Path, src_rel: str, quarantine_root: Path, *, apply: bool, prefix: str) -> QuarantineOp:
    src = (repo_root / src_rel).resolve()
    dst = (quarantine_root / src_rel).resolve()
    if not src.exists():
        return QuarantineOp(src=src_rel, dst=_safe_rel(repo_root, dst), prefix=prefix, status="missing")
    if _git_has_tracked_under(repo_root, src_rel):
        return QuarantineOp(src=src_rel, dst=_safe_rel(repo_root, dst), prefix=prefix, status="skipped_tracked")
    if apply:
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            return QuarantineOp(src=src_rel, dst=_safe_rel(repo_root, dst), prefix=prefix, status="moved")
        except Exception as e:
            return QuarantineOp(src=src_rel, dst=_safe_rel(repo_root, dst), prefix=prefix, status="failed", error=str(e))
    return QuarantineOp(src=src_rel, dst=_safe_rel(repo_root, dst), prefix=prefix, status="planned")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=str(_repo_root()))
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--prefix", action="append", default=[], help="Additional quarantine prefix (repeatable).")
    ap.add_argument("--no-defaults", action="store_true", help="Do not use built-in prefixes.")
    ap.add_argument("--subdir", default="OBSERVATORY_ISOLATION", help="Subdir under artifacts/_observatory_quarantine/<ts>/")
    args = ap.parse_args()

    repo_root = Path(args.repo_root).resolve()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    quarantine_root = (repo_root / "artifacts" / "_observatory_quarantine" / ts / str(args.subdir).strip()).resolve()
    report_dir = (repo_root / "artifacts" / "scc_state" / "reports").resolve()
    report_json = (report_dir / f"quarantine_untracked_{ts}.json").resolve()
    report_md = (report_dir / f"quarantine_untracked_{ts}.md").resolve()

    prefixes = []
    if not bool(args.no_defaults):
        prefixes.extend(_default_prefixes())
    prefixes.extend(list(args.prefix or []))
    prefixes = [p for p in prefixes if str(p).strip()]

    untracked = _git_untracked(repo_root)
    targets = _unique_top_targets(untracked, prefixes)

    ops: List[QuarantineOp] = []
    for src_rel, matched_prefix in targets:
        ops.append(_move_path(repo_root, src_rel, quarantine_root, apply=bool(args.apply), prefix=matched_prefix))

    payload: Dict[str, Any] = {
        "schema_version": "scc_quarantine_untracked.v0",
        "repo_root": str(repo_root),
        "ts_utc": _utc_now(),
        "apply": bool(args.apply),
        "quarantine_root": _safe_rel(repo_root, quarantine_root),
        "prefixes": prefixes,
        "untracked_count": int(len(untracked)),
        "targets_count": int(len(targets)),
        "ops": [o.__dict__ for o in ops],
    }
    _atomic_write_json(report_json, payload)

    moved = sum(1 for o in ops if o.status == "moved")
    skipped_tracked = sum(1 for o in ops if o.status == "skipped_tracked")
    failed = sum(1 for o in ops if o.status == "failed")

    lines = []
    lines.append(f"# Quarantine Untracked ({ts})")
    lines.append("")
    lines.append(f"- apply: `{payload['apply']}`")
    lines.append(f"- quarantine_root: `{payload['quarantine_root']}`")
    lines.append(f"- untracked_count: `{payload['untracked_count']}`")
    lines.append(f"- targets_count: `{payload['targets_count']}`")
    lines.append(f"- moved: `{moved}` skipped_tracked: `{skipped_tracked}` failed: `{failed}`")
    lines.append(f"- json_report: `{_safe_rel(repo_root, report_json)}`")
    lines.append("")
    for o in ops:
        if o.status in {"moved", "failed", "skipped_tracked"}:
            suffix = f" ({o.error})" if o.error else ""
            lines.append(f"- {o.status}: `{o.src}` -> `{o.dst}` [{o.prefix}]{suffix}")
    _atomic_write_text(report_md, "\n".join(lines) + "\n")

    print(f"[quarantine_untracked] apply={payload['apply']} moved={moved} skipped_tracked={skipped_tracked} failed={failed}")
    print(f"[quarantine_untracked] report_md={_safe_rel(repo_root, report_md)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
