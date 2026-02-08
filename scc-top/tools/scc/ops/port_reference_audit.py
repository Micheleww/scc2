from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
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


def _format_bytes(n: int) -> str:
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    v = float(n)
    for u in units:
        if v < 1024.0 or u == units[-1]:
            return f"{int(v)} {u}" if u == "B" else f"{v:.2f} {u}"
        v /= 1024.0
    return f"{n} B"


_URL_RE = re.compile(r"(https?|wss?)://(localhost|127\.0\.0\.1):(\d{2,5})(/[^\s'\"\)]*)?", re.IGNORECASE)


@dataclass(frozen=True)
class Hit:
    path: str
    line: int
    port: int
    url: str


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


def _scan_file(root: Path, p: Path) -> list[Hit]:
    rel = str(p.relative_to(root)).replace("\\", "/")
    hits: list[Hit] = []
    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return hits
    for i, line in enumerate(text.splitlines(), 1):
        for m in _URL_RE.finditer(line):
            port = int(m.group(3))
            url = m.group(0)
            hits.append(Hit(path=rel, line=i, port=port, url=url))
    return hits


def _load_allowed_ports() -> tuple[set[int], dict[str, Any]]:
    meta: dict[str, Any] = {}
    allowed: set[int] = set()
    try:
        from config import ports as ports_mod  # type: ignore

        allowed = set(int(p) for p in getattr(ports_mod, "VALID_PORTS", set()))
        meta["source"] = "config/ports.py"
        meta["allowed_ports_count"] = len(allowed)
    except Exception as e:
        meta["source"] = "fallback"
        meta["error"] = str(e)
        allowed = {18788, 5433, 6379, 3000, 8283, 11434, 7980, 19001}
    # Always allow common web ports, even on localhost.
    allowed |= {80, 443}
    return allowed, meta


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Audit localhost/127.0.0.1 URL port references in tracked files.")
    ap.add_argument("--max-bytes", type=int, default=2 * 1024 * 1024, help="Skip files larger than this size.")
    ap.add_argument(
        "--extensions",
        default=".py,.js,.ts,.tsx,.json,.yml,.yaml,.md,.ps1,.cmd,.bat,.sh,.toml",
        help="Comma-separated extensions to scan.",
    )
    ap.add_argument(
        "--mode",
        choices=["legacy", "strict"],
        default="legacy",
        help="legacy: fail only on known legacy ports (5001/8000/8001/8002/8080); strict: fail on any disallowed ports.",
    )
    ap.add_argument("--fail-on-violations", action="store_true", help="Exit non-zero if disallowed ports found.")
    args = ap.parse_args(argv)

    root = _repo_root()
    allowed_ports, allowed_meta = _load_allowed_ports()
    extensions = {e.strip().lower() for e in str(args.extensions).split(",") if e.strip()}
    max_bytes = int(args.max_bytes)

    files = [p for p in _iter_tracked_files(root) if _should_scan_file(p, max_bytes=max_bytes, extensions=extensions)]

    all_hits: list[Hit] = []
    for p in files:
        all_hits.extend(_scan_file(root, p))

    by_port = Counter(h.port for h in all_hits)
    by_file = Counter(h.path for h in all_hits)

    old_ports = {5001, 8000, 8001, 8002, 8080}
    if args.mode == "legacy":
        violations = [h for h in all_hits if h.port in old_ports]
    else:
        violations = [h for h in all_hits if h.port not in allowed_ports]
    old_port_hits = [h for h in all_hits if h.port in old_ports]

    ts = _utc_now().strftime("%Y%m%d_%H%M%S")
    out_dir = root / "artifacts" / "scc_state" / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    report_json = out_dir / f"port_reference_audit_{ts}.json"
    report_md = out_dir / f"port_reference_audit_{ts}.md"

    payload: dict[str, Any] = {
        "ts": ts,
        "mode": str(args.mode),
        "scanned_files": len(files),
        "hits_total": len(all_hits),
        "distinct_ports": len(by_port),
        "distinct_files": len(by_file),
        "allowed_meta": allowed_meta,
        "allowed_ports": sorted(allowed_ports),
        "old_ports": sorted(old_ports),
        "violations_count": len(violations),
        "old_ports_count": len(old_port_hits),
        "top_ports": by_port.most_common(25),
        "top_files": by_file.most_common(25),
        "violations": [{"path": h.path, "line": h.line, "port": h.port, "url": h.url} for h in violations[:400]],
    }

    report_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines: list[str] = []
    lines.append(f"# Port Reference Audit ({ts})")
    lines.append("")
    lines.append(f"- mode: `{payload['mode']}`")
    lines.append(f"- scanned_files: `{payload['scanned_files']}` (max_bytes={_format_bytes(max_bytes)})")
    lines.append(f"- hits_total: `{payload['hits_total']}`")
    lines.append(f"- distinct_ports: `{payload['distinct_ports']}`")
    lines.append(f"- violations: `{payload['violations_count']}` (disallowed localhost ports)")
    lines.append(f"- old_ports_hits: `{payload['old_ports_count']}` (legacy ports: {', '.join(map(str, payload['old_ports']))})")
    lines.append("")
    lines.append("## Top ports")
    for port, n in payload["top_ports"]:
        tag = "OK" if int(port) in allowed_ports else "VIOLATION"
        lines.append(f"- {port}: {n} ({tag})")
    lines.append("")
    lines.append("## Top files")
    for path, n in payload["top_files"]:
        lines.append(f"- {path}: {n}")
    lines.append("")
    lines.append("## Violations (sample)")
    if payload["violations"]:
        for v in payload["violations"][:120]:
            lines.append(f"- `{v['path']}:{v['line']}` port={v['port']} url=`{v['url']}`")
        if len(payload["violations"]) > 120:
            lines.append("")
            lines.append(f"_truncated: showing 120/{len(payload['violations'])}_")
    else:
        lines.append("_no violations_")
    lines.append("")
    lines.append("## Governance rule")
    lines.append("")
    lines.append("- Desktop/DEV: prefer single entrypoint `http://127.0.0.1:18788` and mount services by path.")
    lines.append("- External deps (DB/Redis/Ollama/etc) may keep dedicated ports, but callers should route via `config/ports.py` where possible.")
    lines.append("")
    report_md.write_text("\n".join(lines), encoding="utf-8")

    print(f"[port_reference_audit] violations={len(violations)} hits={len(all_hits)} scanned_files={len(files)}")
    print(f"[port_reference_audit] report_md={report_md}")

    if args.fail_on_violations and violations:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
