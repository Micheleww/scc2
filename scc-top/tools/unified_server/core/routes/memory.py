"""
Memory ledger and task proposal routes
Extracted from app_factory.py
"""
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse


def _tail_jsonl(path: Path, n: int = 100) -> list[dict]:
    """Read last n lines from a JSONL file"""
    n = max(1, min(int(n or 100), 2000))
    if not path.exists():
        return []
    out_lines: list[bytes] = []
    # Read from the end in chunks until we have enough newlines.
    with path.open("rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        block = 64 * 1024
        buf = b""
        pos = size
        while pos > 0 and len(out_lines) <= n:
            step = block if pos >= block else pos
            pos -= step
            f.seek(pos, os.SEEK_SET)
            chunk = f.read(step)
            buf = chunk + buf
            parts = buf.split(b"\n")
            # keep the first partial line in buf
            buf = parts[0]
            for b in parts[1:]:
                if b:
                    out_lines.append(b)
            if pos == 0 and buf:
                out_lines.append(buf)
        out_lines = out_lines[:n]
    out: list[dict] = []
    for b in reversed(out_lines):
        try:
            out.append(json.loads(b.decode("utf-8", errors="replace")))
        except Exception:
            out.append({"_raw": b.decode("utf-8", errors="replace")})
    return out


def _slug(s: str) -> str:
    """Convert string to slug"""
    s = (s or "").strip().lower()
    if not s:
        return "proposal"
    out = []
    last_dash = False
    for ch in s:
        ok = ("a" <= ch <= "z") or ("0" <= ch <= "9")
        if ok:
            out.append(ch)
            last_dash = False
        else:
            if not last_dash:
                out.append("-")
                last_dash = True
    slug = "".join(out).strip("-")
    if not slug:
        slug = "proposal"
    return slug[:60]


def create_router(repo_root: Path) -> APIRouter:
    """Create memory ledger router with repo_root dependency"""
    router = APIRouter()

    _memory_lock = threading.Lock()
    _proposals_lock = threading.Lock()

    def _memory_ledger_path() -> Path:
        p = (repo_root / "artifacts" / "scc_state" / "memory_ledger.jsonl").resolve()
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        return p

    def _task_proposals_dir() -> Path:
        p = (repo_root / "artifacts" / "scc_state" / "task_proposals").resolve()
        try:
            p.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        return p

    def _targets_path() -> Path:
        p = (repo_root / "artifacts" / "scc_state" / "secretary_targets.json").resolve()
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        return p

    @router.post("/api/memory/append")
    async def api_memory_append(request: Request):
        body = await request.json()
        if not isinstance(body, dict):
            return JSONResponse(status_code=400, content={"ok": False, "error": "invalid_body"})

        content = str(body.get("content") or "").strip()
        if not content:
            return JSONResponse(status_code=400, content={"ok": False, "error": "missing_content"})

        item = {
            "ts_utc": str(body.get("ts_utc") or "").strip() or datetime.now(timezone.utc).isoformat(),
            "source": str(body.get("source") or "").strip() or "unknown",
            "role": str(body.get("role") or "").strip() or "user",
            "kind": str(body.get("kind") or "").strip() or "message",
            "content": content,
            "meta": body.get("meta") if isinstance(body.get("meta"), dict) else {},
        }

        path = _memory_ledger_path()
        line = (json.dumps(item, ensure_ascii=False) + "\n").encode("utf-8", errors="replace")
        with _memory_lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("ab") as f:
                f.write(line)

        return {"ok": True, "path": str(path), "item": item}

    @router.get("/api/memory/tail")
    async def api_memory_tail(n: int = 100):
        path = _memory_ledger_path()
        items = _tail_jsonl(path, n=n)
        return {"ok": True, "path": str(path), "n": int(n or 100), "items": items}

    @router.get("/api/memory/stats")
    async def api_memory_stats():
        path = _memory_ledger_path()
        try:
            st = path.stat() if path.exists() else None
        except Exception:
            st = None
        return {
            "ok": True,
            "path": str(path),
            "exists": bool(path.exists()),
            "size": int(st.st_size) if st else 0,
            "mtime_utc": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat() if st else None,
        }

    @router.post("/api/tasks/propose")
    async def api_tasks_propose(request: Request):
        body = await request.json()
        if not isinstance(body, dict):
            return JSONResponse(status_code=400, content={"ok": False, "error": "invalid_body"})

        title = str(body.get("title") or "").strip()
        if not title:
            title = "Task Proposal"

        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        slug = _slug(title)
        out_dir = _task_proposals_dir()
        out_path = (out_dir / f"{ts}__{slug}.json").resolve()

        payload = {
            "ts_utc": datetime.now(timezone.utc).isoformat(),
            "title": title,
            "proposal": body,
        }

        with _proposals_lock:
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", errors="replace"
            )

        rel = None
        try:
            rel = str(out_path.relative_to(repo_root)).replace("\\", "/")
        except Exception:
            rel = str(out_path)

        return {"ok": True, "path": str(out_path), "relpath": rel, "title": title}

    @router.get("/api/tasks/proposals/list")
    async def api_tasks_proposals_list(limit: int = 50):
        limit = max(1, min(int(limit or 50), 200))
        d = _task_proposals_dir()
        if not d.exists():
            return {"ok": True, "dir": str(d), "items": []}
        items = []
        try:
            for p in sorted(d.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:limit]:
                try:
                    st = p.stat()
                    items.append(
                        {
                            "name": p.name,
                            "path": str(p),
                            "mtime_utc": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
                            "size": int(st.st_size),
                        }
                    )
                except Exception:
                    items.append({"name": p.name, "path": str(p)})
        except Exception:
            items = []
        return {"ok": True, "dir": str(d), "items": items}

    @router.get("/api/secretary/brief")
    async def api_secretary_brief(n_memory: int = 80, proposals_limit: int = 20):
        mem = _tail_jsonl(_memory_ledger_path(), n=n_memory)
        props = await api_tasks_proposals_list(limit=proposals_limit)
        targets_path = _targets_path()
        targets = None
        try:
            if targets_path.exists():
                targets = json.loads(targets_path.read_text(encoding="utf-8", errors="replace") or "null")
        except Exception:
            targets = None
        return {
            "ok": True,
            "ts_utc": datetime.now(timezone.utc).isoformat(),
            "targets": targets,
            "memory_tail": mem,
            "proposals": props.get("items", []) if isinstance(props, dict) else [],
        }

    @router.get("/api/secretary/targets")
    async def api_secretary_targets_get():
        p = _targets_path()
        if not p.exists():
            return {"ok": True, "path": str(p), "targets": None}
        try:
            return {
                "ok": True,
                "path": str(p),
                "targets": json.loads(p.read_text(encoding="utf-8", errors="replace") or "null"),
            }
        except Exception as e:
            return JSONResponse(status_code=500, content={"ok": False, "error": f"read_failed: {e}"})

    @router.post("/api/secretary/targets")
    async def api_secretary_targets_set(request: Request):
        body = await request.json()
        if not isinstance(body, dict):
            return JSONResponse(status_code=400, content={"ok": False, "error": "invalid_body"})
        p = _targets_path()
        payload = {
            "ts_utc": datetime.now(timezone.utc).isoformat(),
            "targets": body,
        }
        try:
            p.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", errors="replace")
        except Exception as e:
            return JSONResponse(status_code=500, content={"ok": False, "error": f"write_failed: {e}"})
        return {"ok": True, "path": str(p), "saved": True}

    return router
