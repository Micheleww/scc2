#!/usr/bin/env python3
"""
Docker-first restore for SCC (local-only).

Restore a tar.gz created by docker_backup_bundle.py back into the persistent volumes.

Safety:
  - Requires SCC_RESTORE_FILE to be set (a filename under SCC_BACKUP_DIR).
  - Refuses to run if scc-server appears to be up (best-effort).
"""

from __future__ import annotations

import json
import os
import socket
import tarfile
from pathlib import Path


def _env(name: str, default: str = "") -> str:
    return str(os.environ.get(name, default) or default).strip()


def _port_open(host: str, port: int, timeout_s: float = 0.3) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True
    except OSError:
        return False


def main() -> int:
    repo_root = Path(_env("REPO_ROOT", "/app")).resolve()
    backup_dir = Path(_env("SCC_BACKUP_DIR", "/backups")).resolve()
    restore_file = _env("SCC_RESTORE_FILE", "")

    if not restore_file:
        print(json.dumps({"ok": False, "error": "SCC_RESTORE_FILE not set"}, ensure_ascii=False))
        return 2

    archive_path = (backup_dir / restore_file).resolve()
    if not archive_path.exists():
        print(json.dumps({"ok": False, "error": f"backup not found: {archive_path}"}, ensure_ascii=False))
        return 2

    # Best-effort safety: don't restore while server is listening.
    if _port_open("scc-server", 18788) or _port_open("127.0.0.1", 18788):
        print(json.dumps({"ok": False, "error": "refusing restore while server is running (port 18788 open)"}, ensure_ascii=False))
        return 3

    def _is_safe_member(member: tarfile.TarInfo) -> bool:
        name = str(member.name or "")
        if not name:
            return False
        # Disallow absolute paths and drive letters.
        if name.startswith(("/", "\\")) or ":" in name.split("/")[0]:
            return False
        # Disallow traversal.
        parts = [p for p in name.replace("\\", "/").split("/") if p and p != "."]
        if any(p == ".." for p in parts):
            return False
        return True

    with tarfile.open(archive_path, mode="r:gz") as tf:
        members = []
        for m in tf.getmembers():
            if not _is_safe_member(m):
                print(json.dumps({"ok": False, "error": f"unsafe member path: {m.name}"}, ensure_ascii=False))
                return 4
            members.append(m)
        tf.extractall(path=repo_root, members=members)

    print(json.dumps({"ok": True, "restored_from": str(archive_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
