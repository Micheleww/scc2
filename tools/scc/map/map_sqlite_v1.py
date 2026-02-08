#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib
import sqlite3
import sys
from typing import Any, Dict, List, Optional


def _default_repo_root() -> str:
    # tools/scc/map/*.py -> repo root is 3 levels up
    return str(pathlib.Path(__file__).resolve().parents[3])


def _load_json(path: pathlib.Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _norm_rel(p: str) -> str:
    return str(p or "").replace("\\", "/").lstrip("./")


def _connect(out_path: pathlib.Path) -> sqlite3.Connection:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(out_path))
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA temp_store=MEMORY;")
    return conn


def _create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        DROP TABLE IF EXISTS meta;
        DROP TABLE IF EXISTS modules;
        DROP TABLE IF EXISTS entry_points;
        DROP TABLE IF EXISTS key_symbols;
        DROP TABLE IF EXISTS test_entry_points;
        DROP TABLE IF EXISTS configs;
        DROP TABLE IF EXISTS doc_refs;
        DROP TABLE IF EXISTS file_index;

        CREATE TABLE meta (
          k TEXT PRIMARY KEY,
          v TEXT NOT NULL
        );

        CREATE TABLE modules (
          id TEXT PRIMARY KEY,
          root TEXT NOT NULL,
          kind TEXT NOT NULL,
          confidence REAL NOT NULL,
          signals_json TEXT NOT NULL,
          doc_refs_json TEXT NOT NULL
        );
        CREATE INDEX modules_root_idx ON modules(root);

        CREATE TABLE entry_points (
          id TEXT PRIMARY KEY,
          kind TEXT NOT NULL,
          path TEXT,
          command TEXT NOT NULL,
          confidence REAL NOT NULL,
          reason TEXT,
          doc_refs_json TEXT NOT NULL
        );
        CREATE INDEX entry_points_path_idx ON entry_points(path);

        CREATE TABLE key_symbols (
          symbol TEXT NOT NULL,
          kind TEXT NOT NULL,
          path TEXT NOT NULL,
          line INTEGER NOT NULL,
          win_start INTEGER NOT NULL,
          win_end INTEGER NOT NULL,
          confidence REAL NOT NULL,
          doc_refs_json TEXT NOT NULL,
          PRIMARY KEY(symbol, path, line)
        );
        CREATE INDEX key_symbols_symbol_idx ON key_symbols(symbol);
        CREATE INDEX key_symbols_path_idx ON key_symbols(path);

        CREATE TABLE test_entry_points (
          id TEXT PRIMARY KEY,
          kind TEXT NOT NULL,
          command TEXT NOT NULL,
          paths_json TEXT NOT NULL,
          confidence REAL NOT NULL,
          reason TEXT
        );

        CREATE TABLE configs (
          key TEXT NOT NULL,
          path TEXT NOT NULL,
          line INTEGER NOT NULL,
          confidence REAL NOT NULL,
          reason TEXT,
          PRIMARY KEY(key, path, line)
        );
        CREATE INDEX configs_key_idx ON configs(key);
        CREATE INDEX configs_path_idx ON configs(path);

        CREATE TABLE doc_refs (
          code_path TEXT NOT NULL,
          doc_path TEXT NOT NULL,
          reason TEXT,
          PRIMARY KEY(code_path, doc_path)
        );
        CREATE INDEX doc_refs_code_idx ON doc_refs(code_path);
        CREATE INDEX doc_refs_doc_idx ON doc_refs(doc_path);

        CREATE TABLE file_index (
          path TEXT PRIMARY KEY,
          mtime_ms REAL NOT NULL,
          size INTEGER NOT NULL
        );
        """
    )


def _dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def build_sqlite(map_obj: Dict[str, Any], out_path: pathlib.Path) -> None:
    conn = _connect(out_path)
    try:
        _create_schema(conn)

        # Meta
        ver = str(map_obj.get("schema_version") or "")
        gen = map_obj.get("generator") if isinstance(map_obj.get("generator"), dict) else {}
        conn.execute("INSERT INTO meta(k,v) VALUES(?,?)", ("schema_version", ver))
        conn.execute("INSERT INTO meta(k,v) VALUES(?,?)", ("generated_at", str(map_obj.get("generated_at") or "")))
        conn.execute("INSERT INTO meta(k,v) VALUES(?,?)", ("generator_name", str(gen.get("name") or "")))
        conn.execute("INSERT INTO meta(k,v) VALUES(?,?)", ("generator_version", str(gen.get("version") or "")))
        cov = map_obj.get("coverage") if isinstance(map_obj.get("coverage"), dict) else {}
        conn.execute("INSERT INTO meta(k,v) VALUES(?,?)", ("coverage_roots_json", _dumps(cov.get("roots") or [])))
        conn.execute("INSERT INTO meta(k,v) VALUES(?,?)", ("coverage_excluded_json", _dumps(cov.get("excluded_globs") or [])))
        # Optional hashes (if provided by caller via version.json)
        mh = str(map_obj.get("_meta_map_hash") or "")
        fh = str(map_obj.get("_meta_facts_hash") or "")
        if mh:
            conn.execute("INSERT INTO meta(k,v) VALUES(?,?)", ("map_hash", mh))
        if fh:
            conn.execute("INSERT INTO meta(k,v) VALUES(?,?)", ("facts_hash", fh))

        # Modules
        for m in map_obj.get("modules") or []:
            if not isinstance(m, dict):
                continue
            conn.execute(
                "INSERT OR REPLACE INTO modules(id,root,kind,confidence,signals_json,doc_refs_json) VALUES(?,?,?,?,?,?)",
                (
                    str(m.get("id") or ""),
                    _norm_rel(str(m.get("root") or "")),
                    str(m.get("kind") or ""),
                    float(m.get("confidence") or 0.0),
                    _dumps(m.get("signals") or []),
                    _dumps(m.get("doc_refs") or []),
                ),
            )

        # Entry points
        for e in map_obj.get("entry_points") or []:
            if not isinstance(e, dict):
                continue
            conn.execute(
                "INSERT OR REPLACE INTO entry_points(id,kind,path,command,confidence,reason,doc_refs_json) VALUES(?,?,?,?,?,?,?)",
                (
                    str(e.get("id") or ""),
                    str(e.get("kind") or ""),
                    _norm_rel(str(e.get("path") or "")) if e.get("path") else None,
                    str(e.get("command") or ""),
                    float(e.get("confidence") or 0.0),
                    str(e.get("reason") or ""),
                    _dumps(e.get("doc_refs") or []),
                ),
            )

        # Key symbols
        for ks in map_obj.get("key_symbols") or []:
            if not isinstance(ks, dict):
                continue
            win = ks.get("line_window") if isinstance(ks.get("line_window"), list) else [1, 1]
            ws = int(win[0]) if len(win) >= 2 else 1
            we = int(win[1]) if len(win) >= 2 else ws
            conn.execute(
                "INSERT OR REPLACE INTO key_symbols(symbol,kind,path,line,win_start,win_end,confidence,doc_refs_json) VALUES(?,?,?,?,?,?,?,?)",
                (
                    str(ks.get("symbol") or ""),
                    str(ks.get("kind") or ""),
                    _norm_rel(str(ks.get("path") or "")),
                    int(ks.get("line") or 1),
                    ws,
                    we,
                    float(ks.get("confidence") or 0.0),
                    _dumps(ks.get("doc_refs") or []),
                ),
            )

        # Test entry points
        for t in map_obj.get("test_entry_points") or []:
            if not isinstance(t, dict):
                continue
            conn.execute(
                "INSERT OR REPLACE INTO test_entry_points(id,kind,command,paths_json,confidence,reason) VALUES(?,?,?,?,?,?)",
                (
                    str(t.get("id") or ""),
                    str(t.get("kind") or ""),
                    str(t.get("command") or ""),
                    _dumps(t.get("paths") or []),
                    float(t.get("confidence") or 0.0),
                    str(t.get("reason") or ""),
                ),
            )

        # Configs
        for c in map_obj.get("configs") or []:
            if not isinstance(c, dict):
                continue
            conn.execute(
                "INSERT OR REPLACE INTO configs(key,path,line,confidence,reason) VALUES(?,?,?,?,?)",
                (
                    str(c.get("key") or ""),
                    _norm_rel(str(c.get("path") or "")),
                    int(c.get("line") or 1),
                    float(c.get("confidence") or 0.0),
                    str(c.get("reason") or ""),
                ),
            )

        # Doc refs
        for d in map_obj.get("doc_refs") or []:
            if not isinstance(d, dict):
                continue
            conn.execute(
                "INSERT OR REPLACE INTO doc_refs(code_path,doc_path,reason) VALUES(?,?,?)",
                (
                    _norm_rel(str(d.get("code_path") or "")),
                    _norm_rel(str(d.get("doc_path") or "")),
                    str(d.get("reason") or ""),
                ),
            )

        # File index
        fi = map_obj.get("file_index") if isinstance(map_obj.get("file_index"), dict) else {}
        for p, meta in fi.items():
            if not isinstance(p, str) or not p.strip():
                continue
            if not isinstance(meta, dict):
                continue
            conn.execute(
                "INSERT OR REPLACE INTO file_index(path,mtime_ms,size) VALUES(?,?,?)",
                (
                    _norm_rel(p),
                    float(meta.get("mtimeMs") or 0.0),
                    int(meta.get("size") or 0),
                ),
            )

        conn.commit()
    finally:
        conn.close()


def main() -> int:
    ap = argparse.ArgumentParser(description="Build map/map.sqlite from map/map.json (deterministic).")
    ap.add_argument("--map", default="map/map.json", help="Path to map.json")
    ap.add_argument("--out", default="map/map.sqlite", help="Output sqlite path")
    ap.add_argument("--repo-root", default=_default_repo_root(), help="Repo root (for relative paths)")
    ap.add_argument("--version", default="map/version.json", help="Optional map/version.json to embed hash metadata")
    ap.add_argument("--force", action="store_true", help="Overwrite existing sqlite file")
    args = ap.parse_args()

    repo = pathlib.Path(args.repo_root).resolve()
    map_path = pathlib.Path(args.map)
    if not map_path.is_absolute():
        map_path = (repo / map_path).resolve()
    out_path = pathlib.Path(args.out)
    if not out_path.is_absolute():
        out_path = (repo / out_path).resolve()

    if not map_path.exists():
        print(f"FAIL: missing map file: {map_path.as_posix()}", file=sys.stderr)
        return 2
    if out_path.exists() and not args.force:
        print(f"FAIL: output exists (pass --force): {out_path.as_posix()}", file=sys.stderr)
        return 2
    if out_path.exists() and args.force:
        try:
            out_path.unlink()
        except Exception as e:
            print(f"FAIL: cannot overwrite existing sqlite (unlink failed): {e}", file=sys.stderr)
            return 2
        if out_path.exists():
            print(f"FAIL: cannot overwrite existing sqlite: {out_path.as_posix()}", file=sys.stderr)
            return 2

    try:
        obj = _load_json(map_path)
    except Exception as e:
        print(f"FAIL: bad json: {e}", file=sys.stderr)
        return 2
    if not isinstance(obj, dict) or obj.get("schema_version") != "scc.map.v1":
        print("FAIL: unexpected map schema_version", file=sys.stderr)
        return 2

    # Best-effort: embed version hashes into sqlite meta so gates can detect stale sqlite.
    try:
        ver_path = pathlib.Path(args.version)
        if not ver_path.is_absolute():
            ver_path = (repo / ver_path).resolve()
        if ver_path.exists():
            ver = _load_json(ver_path)
            if isinstance(ver, dict):
                mh = str(ver.get("hash") or "").strip()
                fh = str(ver.get("facts_hash") or "").strip()
                if mh:
                    obj["_meta_map_hash"] = mh
                if fh:
                    obj["_meta_facts_hash"] = fh
    except Exception:
        pass

    build_sqlite(obj, out_path)
    print(json.dumps({"ok": True, "map": str(map_path.relative_to(repo)).replace("\\", "/"), "sqlite": str(out_path.relative_to(repo)).replace("\\", "/")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
