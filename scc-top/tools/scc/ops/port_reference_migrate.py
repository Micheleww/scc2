from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _run_git(root: Path, args: list[str]) -> str:
    p = subprocess.run(  # noqa: S603
        ["git", *args],
        cwd=str(root),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return p.stdout


def _iter_tracked_files(root: Path) -> list[Path]:
    out = _run_git(root, ["ls-files"])
    files: list[Path] = []
    for line in out.splitlines():
        p = line.strip()
        if not p:
            continue
        files.append((root / p).resolve())
    return files


def _should_scan_file(p: Path, *, max_bytes: int, extensions: set[str]) -> bool:
    if not p.exists() or not p.is_file():
        return False
    if p.suffix.lower() not in extensions:
        return False
    try:
        if p.stat().st_size > max_bytes:
            return False
    except OSError:
        return False
    return True


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


_URL_RE = re.compile(
    r"(?P<scheme>https?|wss?)://(?P<host>localhost|127\.0\.0\.1):(?P<port>\d{2,5})(?P<path>/[^\s'\"\)]*)?",
    re.IGNORECASE,
)


def _normalize_path(p: str | None) -> str:
    if not p:
        return "/"
    if not p.startswith("/"):
        return "/" + p
    return p


def _map_old_port_to_path_prefix(*, port: int, path: str) -> str:
    """
    Map legacy port usage into unified-server path mounts.

    Notes:
    - 5001 historically used for A2A/API -> now mounted under /api
    - 8001 historically used for MCP -> now mounted under /mcp
    - 8000/8002/8080 were often "gateway-ish"; for safety we only change port and keep path unchanged.
    """
    path = _normalize_path(path)
    if port == 5001:
        if path.startswith("/api"):
            return path
        return "/api" + ("" if path == "/" else path)
    if port == 8001:
        # allow special compatibility paths that unified server already forwards to /mcp/*
        if path.startswith("/mcp") or path.startswith("/viewer") or path.startswith("/login") or path.startswith("/api/viewer/"):
            return path
        return "/mcp" + ("" if path == "/" else path)
    return path


@dataclass(frozen=True)
class Change:
    file: str
    count: int


def _rewrite_text(text: str, *, unified_port: int) -> tuple[str, int]:
    changes = 0

    def repl(m: re.Match[str]) -> str:
        nonlocal changes
        scheme = m.group("scheme")
        host = m.group("host")
        port = int(m.group("port"))
        path = _normalize_path(m.group("path"))

        legacy_ports = {5001, 8000, 8001, 8002, 8080}
        if port not in legacy_ports:
            return m.group(0)

        new_path = _map_old_port_to_path_prefix(port=port, path=path)
        new_url = f"{scheme}://{host}:{unified_port}{new_path}"
        if new_url != m.group(0):
            changes += 1
        return new_url

    out = _URL_RE.sub(repl, text)
    return out, changes


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Rewrite legacy localhost port URLs to the unified-server single entrypoint.")
    ap.add_argument("--apply", action="store_true", help="Actually rewrite files (default: dry-run).")
    ap.add_argument("--unified-port", type=int, default=18788)
    ap.add_argument("--max-bytes", type=int, default=2 * 1024 * 1024)
    ap.add_argument(
        "--extensions",
        default=".py,.js,.ts,.tsx,.json,.yml,.yaml,.md,.ps1,.cmd,.bat,.sh,.toml",
        help="Comma-separated extensions to scan.",
    )
    ap.add_argument(
        "--backup-dir",
        default="",
        help="Optional backup root (default: artifacts/_root_clutter/<ts>/PORT_MIGRATION_BACKUP).",
    )
    args = ap.parse_args(argv)

    root = _repo_root()
    ts = _utc_now().strftime("%Y%m%d_%H%M%S")
    out_dir = root / "artifacts" / "scc_state" / "reports"
    _ensure_dir(out_dir)
    report_json = out_dir / f"port_reference_migrate_{ts}.json"
    report_md = out_dir / f"port_reference_migrate_{ts}.md"

    backup_root = Path(args.backup_dir).expanduser().resolve() if args.backup_dir else (root / "artifacts" / "_root_clutter" / ts / "PORT_MIGRATION_BACKUP").resolve()
    if args.apply:
        _ensure_dir(backup_root)

    extensions = {e.strip().lower() for e in str(args.extensions).split(",") if e.strip()}
    max_bytes = int(args.max_bytes)

    files = [p for p in _iter_tracked_files(root) if _should_scan_file(p, max_bytes=max_bytes, extensions=extensions)]
    changes: list[Change] = []
    total_rewrites = 0
    touched = 0

    for p in files:
        rel = str(p.relative_to(root)).replace("\\", "/")
        try:
            original = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        updated, n = _rewrite_text(original, unified_port=int(args.unified_port))
        if n <= 0 or updated == original:
            continue
        touched += 1
        total_rewrites += n
        changes.append(Change(file=rel, count=n))

        if args.apply:
            # backup
            dst = (backup_root / rel).resolve()
            _ensure_dir(dst.parent)
            try:
                shutil.copy2(str(p), str(dst))
            except Exception:
                pass
            p.write_text(updated, encoding="utf-8", errors="ignore")

    changes.sort(key=lambda c: c.count, reverse=True)
    payload: dict[str, Any] = {
        "ts": ts,
        "apply": bool(args.apply),
        "unified_port": int(args.unified_port),
        "scanned_files": len(files),
        "touched_files": touched,
        "total_rewrites": total_rewrites,
        "backup_root": str(backup_root.relative_to(root)).replace("\\", "/") if args.apply else None,
        "top_files": [{"file": c.file, "rewrites": c.count} for c in changes[:80]],
    }
    report_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines: list[str] = []
    lines.append(f"# Port Reference Migrate ({ts})")
    lines.append("")
    lines.append(f"- apply: `{payload['apply']}`")
    lines.append(f"- unified_port: `{payload['unified_port']}`")
    lines.append(f"- scanned_files: `{payload['scanned_files']}`")
    lines.append(f"- touched_files: `{payload['touched_files']}`")
    lines.append(f"- total_rewrites: `{payload['total_rewrites']}`")
    if payload["backup_root"]:
        lines.append(f"- backup_root: `{payload['backup_root']}`")
    lines.append("")
    lines.append("## Top touched files")
    if payload["top_files"]:
        for row in payload["top_files"][:40]:
            lines.append(f"- `{row['file']}` rewrites={row['rewrites']}")
        if len(payload["top_files"]) > 40:
            lines.append("")
            lines.append(f"_truncated: showing 40/{len(payload['top_files'])}_")
    else:
        lines.append("_no changes needed_")
    lines.append("")
    report_md.write_text("\n".join(lines), encoding="utf-8")

    print(f"[port_reference_migrate] apply={payload['apply']} touched_files={touched} rewrites={total_rewrites}")
    print(f"[port_reference_migrate] report_md={report_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

