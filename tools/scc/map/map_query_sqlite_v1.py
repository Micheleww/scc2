#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib
import sqlite3
import sys
from typing import Any, Dict, List, Tuple


def _norm_rel(p: str) -> str:
    return str(p or "").replace("\\", "/").lstrip("./")


def _connect(path: pathlib.Path) -> sqlite3.Connection:
    return sqlite3.connect(str(path))


def _score(kind: str) -> float:
    if kind == "key_symbol":
        return 3.0
    if kind == "entry_point":
        return 2.0
    if kind == "test_entry":
        return 1.8
    if kind == "config":
        return 1.2
    if kind == "module":
        return 0.6
    return 1.0


def query(conn: sqlite3.Connection, q: str, limit: int) -> List[Dict[str, Any]]:
    s = q.strip()
    if not s:
        return []
    like = f"%{s}%"
    out: List[Dict[str, Any]] = []

    # key symbols by symbol or path
    for row in conn.execute(
        "SELECT symbol, path, line, win_start, win_end FROM key_symbols WHERE symbol LIKE ? OR path LIKE ? LIMIT ?",
        (like, like, max(10, limit)),
    ):
        sym, path, line, ws, we = row
        out.append(
            {
                "kind": "key_symbol",
                "id": f"{sym}@{path}:{line}",
                "path": _norm_rel(path),
                "symbol": sym,
                "line": int(line),
                "line_window": [int(ws), int(we)],
                "score": 1.0 * _score("key_symbol"),
                "reason": "sqlite match key_symbol",
            }
        )

    # entry points
    for row in conn.execute(
        "SELECT id, path, command FROM entry_points WHERE id LIKE ? OR path LIKE ? OR command LIKE ? LIMIT ?",
        (like, like, like, max(10, limit)),
    ):
        i, p, cmd = row
        out.append(
            {
                "kind": "entry_point",
                "id": i,
                "path": _norm_rel(p) if p else None,
                "command": cmd,
                "score": 1.0 * _score("entry_point"),
                "reason": "sqlite match entry_point",
            }
        )

    # modules
    for row in conn.execute(
        "SELECT id, root FROM modules WHERE id LIKE ? OR root LIKE ? LIMIT ?",
        (like, like, max(10, limit)),
    ):
        i, root = row
        out.append(
            {"kind": "module", "id": i, "path": _norm_rel(root), "score": 1.0 * _score("module"), "reason": "sqlite match module"}
        )

    # configs
    for row in conn.execute(
        "SELECT key, path, line FROM configs WHERE key LIKE ? OR path LIKE ? LIMIT ?",
        (like, like, max(10, limit)),
    ):
        k, p, line = row
        out.append(
            {"kind": "config", "id": f"{k}@{p}:{line}", "path": _norm_rel(p), "key": k, "line": int(line), "score": 1.0 * _score("config"), "reason": "sqlite match config"}
        )

    # test entry points
    for row in conn.execute(
        "SELECT id, command FROM test_entry_points WHERE id LIKE ? OR command LIKE ? LIMIT ?",
        (like, like, max(10, limit)),
    ):
        i, cmd = row
        out.append({"kind": "test_entry", "id": i, "path": None, "command": cmd, "score": 1.0 * _score("test_entry"), "reason": "sqlite match test_entry"})

    # stable sort + cap
    out.sort(key=lambda r: (-float(r.get("score") or 0), str(r.get("kind") or ""), str(r.get("path") or ""), str(r.get("id") or "")))
    return out[: max(1, min(200, int(limit)))]


def main() -> int:
    ap = argparse.ArgumentParser(description="Query map/map.sqlite (best-effort).")
    ap.add_argument("--db", default="map/map.sqlite")
    ap.add_argument("--q", required=True)
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--repo-root", default="C:/scc")
    args = ap.parse_args()

    repo = pathlib.Path(args.repo_root).resolve()
    db_path = pathlib.Path(args.db)
    if not db_path.is_absolute():
        db_path = (repo / db_path).resolve()
    if not db_path.exists():
        print(f"FAIL: missing db: {db_path.as_posix()}", file=sys.stderr)
        return 2

    try:
        conn = _connect(db_path)
    except Exception as e:
        print(f"FAIL: cannot open db: {e}", file=sys.stderr)
        return 2
    try:
        res = query(conn, args.q, args.limit)
    finally:
        conn.close()

    print(json.dumps({"ok": True, "q": args.q, "results": res}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

