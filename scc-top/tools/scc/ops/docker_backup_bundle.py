#!/usr/bin/env python3
"""
Docker-first backup for SCC (local-only).

Backs up all persistent volumes to a single tar.gz + a JSON manifest.

Expected to run inside the scc-unified container with:
  - REPO_ROOT=/app
  - SCC_BACKUP_DIR=/backups (bind mounted to host)
"""

from __future__ import annotations

import hashlib
import json
import os
import tarfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class BackupTarget:
    rel: str
    required: bool = True

    def abs_path(self, repo_root: Path) -> Path:
        return (repo_root / self.rel).resolve()


TARGETS: list[BackupTarget] = [
    BackupTarget("artifacts", required=True),
    BackupTarget("data", required=True),
    BackupTarget("logs", required=False),
    BackupTarget("tools/unified_server/state", required=True),
    BackupTarget("tools/unified_server/logs", required=False),
    BackupTarget("tools/mcp_bus/_state", required=False),
]


def _env(name: str, default: str) -> str:
    return str(os.environ.get(name, default) or default).strip()


def _iter_files(base: Path) -> Iterable[Path]:
    for p in base.rglob("*"):
        if not p.is_file():
            continue
        # Avoid packaging bytecode/cache noise.
        if "__pycache__" in p.parts:
            continue
        if p.suffix in {".pyc", ".pyo"}:
            continue
        yield p


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(8 * 1024 * 1024)
            if not b:
                break
            h.update(b)
    return h.hexdigest().upper()


def main() -> int:
    repo_root = Path(_env("REPO_ROOT", "/app")).resolve()
    out_dir = Path(_env("SCC_BACKUP_DIR", "/backups")).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    ts = time.strftime("%Y%m%d_%H%M%S", time.localtime())
    archive_name = f"scc_backup_{ts}.tar.gz"
    manifest_name = f"scc_backup_{ts}.manifest.json"

    archive_path = (out_dir / archive_name).resolve()
    manifest_path = (out_dir / manifest_name).resolve()

    included: list[dict] = []
    warnings: list[str] = []

    for target in TARGETS:
        base = target.abs_path(repo_root)
        if not base.exists():
            msg = f"missing target: {target.rel}"
            if target.required:
                raise SystemExit(msg)
            warnings.append(msg)
            continue
        base.mkdir(parents=True, exist_ok=True)
        included.append({"rel": target.rel, "abs": str(base), "required": target.required})

    started = time.time()
    with tarfile.open(archive_path, mode="w:gz") as tf:
        for target in TARGETS:
            base = target.abs_path(repo_root)
            if not base.exists():
                continue
            for fp in _iter_files(base):
                arc = str(fp.relative_to(repo_root)).replace("\\", "/")
                tf.add(fp, arcname=arc, recursive=False)

    sha = _sha256_file(archive_path)
    size = archive_path.stat().st_size

    manifest = {
        "created_at": ts,
        "repo_root": str(repo_root),
        "archive": {
            "name": archive_name,
            "sha256": sha,
            "bytes": size,
        },
        "targets": included,
        "warnings": warnings,
        "elapsed_s": round(time.time() - started, 3),
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({"ok": True, "archive": str(archive_path), "manifest": str(manifest_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

