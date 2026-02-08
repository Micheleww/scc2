from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _walk_files(base: Path) -> Iterable[Path]:
    if not base.exists():
        return []
    for root, _dirs, files in os.walk(base):
        for name in files:
            yield Path(root) / name


def _format_bytes(n: int) -> str:
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    v = float(n)
    for u in units:
        if v < 1024.0 or u == units[-1]:
            return f"{int(v)} {u}" if u == "B" else f"{v:.2f} {u}"
        v /= 1024.0
    return f"{n} B"


def _default_evidence_dir(root: Path, task_id: str) -> Path:
    return root / "artifacts" / "scc_tasks" / task_id / "evidence"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Generate evidence manifest (hash/size/mtime) for a task.")
    ap.add_argument("--task-id", required=True)
    ap.add_argument("--evidence-dir", default="", help="Override evidence directory (default: artifacts/scc_tasks/<task>/evidence).")
    ap.add_argument("--out", default="", help="Output path (default: <evidence_dir>/manifest.json).")
    ap.add_argument("--max-bytes-hash", type=int, default=50 * 1024 * 1024, help="Skip hashing files larger than this size.")
    args = ap.parse_args(argv)

    root = _repo_root()
    task_id = str(args.task_id).strip()
    if not task_id:
        raise SystemExit("task_id is empty")

    evidence_dir = Path(args.evidence_dir).expanduser().resolve() if args.evidence_dir else _default_evidence_dir(root, task_id)
    if not evidence_dir.exists():
        raise SystemExit(f"evidence_dir not found: {evidence_dir}")

    out_path = Path(args.out).expanduser().resolve() if args.out else (evidence_dir / "manifest.json")
    _ensure_dir(out_path.parent)

    files: list[dict[str, Any]] = []
    total = 0
    hashed = 0
    skipped_hash = 0

    for fp in sorted(_walk_files(evidence_dir)):
        try:
            st = fp.stat()
        except OSError:
            continue
        size = int(st.st_size)
        total += size
        rel = str(fp.relative_to(root)).replace("\\", "/")
        mtime = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat()
        sha256 = None
        if size <= int(args.max_bytes_hash):
            try:
                sha256 = _sha256_file(fp)
                hashed += 1
            except Exception:
                sha256 = None
        else:
            skipped_hash += 1
        files.append(
            {
                "path": rel,
                "size_bytes": size,
                "size_h": _format_bytes(size),
                "mtime_utc": mtime,
                "sha256": sha256,
                "hash_skipped": sha256 is None and size > int(args.max_bytes_hash),
            }
        )

    payload = {
        "task_id": task_id,
        "generated_at_utc": _utc_now().isoformat(),
        "evidence_dir": str(evidence_dir.relative_to(root)).replace("\\", "/"),
        "total_files": len(files),
        "total_size_bytes": total,
        "total_size_h": _format_bytes(total),
        "hashed_files": hashed,
        "skipped_hash_files": skipped_hash,
        "max_bytes_hash": int(args.max_bytes_hash),
        "files": files,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[evidence_manifest] task_id={task_id} files={len(files)} size={payload['total_size_h']}")
    print(f"[evidence_manifest] out={out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

