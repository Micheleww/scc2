#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib
import sqlite3
import sys
from typing import Any, Dict, List, Tuple


def _default_repo_root() -> str:
    # tools/scc/map/*.py -> repo root is 3 levels up
    return str(pathlib.Path(__file__).resolve().parents[3])


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


def _query_one(conn: sqlite3.Connection, q: str, limit: int) -> List[Dict[str, Any]]:
    s = q.strip()
    if not s:
        return []
    like = f"%{s}%"
    out: List[Dict[str, Any]] = []

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

    for row in conn.execute(
        "SELECT id, root FROM modules WHERE id LIKE ? OR root LIKE ? LIMIT ?",
        (like, like, max(10, limit)),
    ):
        i, root = row
        out.append(
            {"kind": "module", "id": i, "path": _norm_rel(root), "score": 1.0 * _score("module"), "reason": "sqlite match module"}
        )

    for row in conn.execute(
        "SELECT key, path, line FROM configs WHERE key LIKE ? OR path LIKE ? LIMIT ?",
        (like, like, max(10, limit)),
    ):
        k, p, line = row
        out.append(
            {
                "kind": "config",
                "id": f"{k}@{p}:{line}",
                "path": _norm_rel(p),
                "key": k,
                "line": int(line),
                "score": 1.0 * _score("config"),
                "reason": "sqlite match config",
            }
        )

    for row in conn.execute(
        "SELECT id, command FROM test_entry_points WHERE id LIKE ? OR command LIKE ? LIMIT ?",
        (like, like, max(10, limit)),
    ):
        i, cmd = row
        out.append(
            {
                "kind": "test_entry",
                "id": i,
                "path": None,
                "command": cmd,
                "score": 1.0 * _score("test_entry"),
                "reason": "sqlite match test_entry",
            }
        )

    out.sort(key=lambda r: (-float(r.get("score") or 0), str(r.get("kind") or ""), str(r.get("path") or ""), str(r.get("id") or "")))
    return out[: max(1, min(200, int(limit)))]


def main() -> int:
    ap = argparse.ArgumentParser(description="Batch query map/map.sqlite; input JSON via --in or stdin.")
    ap.add_argument("--db", default="map/map.sqlite")
    ap.add_argument("--repo-root", default=_default_repo_root())
    ap.add_argument("--in", dest="in_path", default="", help="Path to JSON request; default stdin")
    ap.add_argument("--limit-per-query", type=int, default=12)
    ap.add_argument("--max-queries", type=int, default=120)
    ap.add_argument("--max-results", type=int, default=120)
    args = ap.parse_args()

    repo = pathlib.Path(args.repo_root).resolve()
    db_path = pathlib.Path(args.db)
    if not db_path.is_absolute():
        db_path = (repo / db_path).resolve()
    if not db_path.exists():
        print(f"FAIL: missing db: {db_path.as_posix()}", file=sys.stderr)
        return 2

    raw = ""
    if args.in_path:
        p = pathlib.Path(args.in_path)
        if not p.is_absolute():
            p = (repo / p).resolve()
        raw = p.read_text(encoding="utf-8-sig")
    else:
        raw = sys.stdin.read()
    try:
        req = json.loads(raw) if raw.strip() else {}
    except Exception as e:
        print(f"FAIL: bad json input: {e}", file=sys.stderr)
        return 2

    queries = req.get("queries") if isinstance(req, dict) else None
    if not isinstance(queries, list):
        print("FAIL: input must be {queries:[...]}", file=sys.stderr)
        return 2
    qs = [str(x) for x in queries if isinstance(x, str) and str(x).strip()]
    qs = qs[: max(1, min(int(args.max_queries), 400))]

    limit_per = max(1, min(int(args.limit_per_query), 80))
    max_results = max(1, min(int(args.max_results), 400))

    try:
        conn = _connect(db_path)
    except Exception as e:
        print(f"FAIL: cannot open db: {e}", file=sys.stderr)
        return 2
    try:
        seen: set[str] = set()
        merged: List[Dict[str, Any]] = []
        per_query: Dict[str, List[Dict[str, Any]]] = {}
        for q in qs:
            rows = _query_one(conn, q, limit_per)
            per_query[q] = rows
            for r in rows:
                key = f"{r.get('kind')}|{r.get('id')}|{r.get('path')}"
                if key in seen:
                    continue
                seen.add(key)
                merged.append(r)
                if len(merged) >= max_results:
                    break
            if len(merged) >= max_results:
                break
        merged.sort(key=lambda r: (-float(r.get("score") or 0), str(r.get("kind") or ""), str(r.get("path") or ""), str(r.get("id") or "")))
    finally:
        conn.close()

    print(json.dumps({"ok": True, "queries": qs, "results": merged[:max_results], "per_query": per_query}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

