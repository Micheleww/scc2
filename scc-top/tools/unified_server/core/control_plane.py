"""
Unified-server control plane endpoints.

Design:
- Keep /api reserved for the legacy A2A Hub WSGI app (mounted as a service).
- Expose unified-server native APIs under /cp/* so mounts never collide.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from tools.scc.runtime_config import load_runtime_config


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path, default: Any) -> Any:
    try:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8", errors="replace") or "null")
    except Exception:
        return default


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", errors="replace")


def _tail_lines(path: Path, *, n: int = 200) -> List[str]:
    n = max(1, min(int(n or 200), 5000))
    if not path.exists() or not path.is_file():
        return []
    # Small, robust tail for logs; fast enough for the sizes we allow.
    try:
        with path.open("rb") as f:
            f.seek(0, 2)
            end = f.tell()
            chunk = 8192
            data = b""
            pos = end
            while pos > 0 and data.count(b"\n") <= n:
                step = chunk if pos >= chunk else pos
                pos -= step
                f.seek(pos, 0)
                data = f.read(step) + data
                if len(data) > 8 * 1024 * 1024:
                    break
        lines = data.splitlines()[-n:]
        return [ln.decode("utf-8", errors="replace") for ln in lines]
    except Exception:
        try:
            return (path.read_text(encoding="utf-8", errors="replace") or "").splitlines()[-n:]
        except Exception:
            return []


def _safe_rel(repo_root: Path, p: Path) -> str:
    try:
        return str(p.resolve().relative_to(repo_root.resolve())).replace("\\", "/")
    except Exception:
        return str(p).replace("\\", "/")


def _log_stream_roots(repo_root: Path) -> Dict[str, Path]:
    # Keep the allowlist tight: only inside known log/state dirs.
    return {
        "unified_server_logs": (repo_root / "tools" / "unified_server" / "logs").resolve(),
        "logs": (repo_root / "logs").resolve(),
        "scc_state": (repo_root / "artifacts" / "scc_state").resolve(),
        "scc_tasks": (repo_root / "artifacts" / "scc_tasks").resolve(),
        "dispatch": (repo_root / "docs" / "DERIVED" / "dispatch").resolve(),
    }


def _enumerate_streams(repo_root: Path) -> List[Dict[str, Any]]:
    roots = _log_stream_roots(repo_root)
    out: List[Dict[str, Any]] = []
    exts = {".log", ".txt", ".jsonl", ".json"}

    for root_name, root in roots.items():
        if not root.exists() or not root.is_dir():
            continue
        try:
            for p in sorted(root.rglob("*")):
                if not p.is_file():
                    continue
                if p.suffix.lower() not in exts:
                    continue
                try:
                    size = int(p.stat().st_size)
                except Exception:
                    size = -1
                # Avoid surfacing huge files by default.
                if size >= 0 and size > 80 * 1024 * 1024:
                    continue
                out.append(
                    {
                        "stream": f"{root_name}:{_safe_rel(root, p)}",
                        "root": root_name,
                        "path": _safe_rel(repo_root, p),
                        "size_bytes": size,
                    }
                )
        except Exception:
            continue

    out.sort(key=lambda x: (str(x.get("root")), str(x.get("path"))))
    return out


def _resolve_stream_path(repo_root: Path, stream: str) -> Optional[Path]:
    stream = str(stream or "").strip()
    if ":" not in stream:
        return None
    root_name, rel = stream.split(":", 1)
    roots = _log_stream_roots(repo_root)
    base = roots.get(root_name)
    if base is None:
        return None
    rel = rel.lstrip("/").replace("\\", "/")
    if not rel or ".." in rel.split("/"):
        return None
    p = (base / rel).resolve()
    try:
        p.relative_to(base)
    except Exception:
        return None
    return p


def _routing_path(repo_root: Path) -> Path:
    # Volume-mounted path in docker-compose.
    return (repo_root / "tools" / "unified_server" / "state" / "model_routing.json").resolve()


def _memory_ledger_path(repo_root: Path) -> Path:
    p = (repo_root / "artifacts" / "scc_state" / "memory_ledger.jsonl").resolve()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return p


def _default_routing(repo_root: Path) -> Dict[str, Any]:
    rt = load_runtime_config(repo_root=repo_root)
    codex_default = str(os.environ.get("A2A_CODEX_MODEL") or rt.codex_model or "gpt-5.2").strip() or "gpt-5.2"
    oc_default = str(os.environ.get("A2A_OPENCODE_MODEL") or getattr(rt, "opencode_model", "") or "gpt-5.2").strip() or "gpt-5.2"
    return {
        "version": 1,
        "updated_utc": _iso_now(),
        "executors": {
            "codex": {"default": codex_default, "allowed": [codex_default]},
            "opencode": {"default": oc_default, "allowed": [oc_default]},
        },
    }


def _validate_routing(obj: Any) -> Tuple[bool, str]:
    if not isinstance(obj, dict):
        return False, "routing must be an object"
    if int(obj.get("version") or 0) != 1:
        return False, "unsupported version (expected 1)"
    ex = obj.get("executors")
    if not isinstance(ex, dict):
        return False, "executors must be an object"
    for k in ("codex", "opencode"):
        v = ex.get(k)
        if not isinstance(v, dict):
            return False, f"executors.{k} must be an object"
        d = str(v.get("default") or "").strip()
        if not d:
            return False, f"executors.{k}.default is required"
        allowed = v.get("allowed")
        if allowed is None:
            allowed = [d]
            v["allowed"] = allowed
        if not isinstance(allowed, list) or not all(isinstance(x, str) and x.strip() for x in allowed):
            return False, f"executors.{k}.allowed must be a list of non-empty strings"
        allowed2 = [str(x).strip() for x in allowed if str(x).strip()]
        # Keep deterministic order and ensure default is included.
        seen = set()
        dedup = []
        for x in allowed2:
            if x in seen:
                continue
            seen.add(x)
            dedup.append(x)
        if d not in seen:
            dedup.insert(0, d)
        v["allowed"] = dedup
    return True, ""


def _read_parent_inbox(repo_root: Path, *, limit: int = 5000) -> List[Dict[str, Any]]:
    inbox = (repo_root / "artifacts" / "scc_state" / "parent_inbox.jsonl").resolve()
    if not inbox.exists():
        return []
    out: List[Dict[str, Any]] = []
    try:
        # Read tail-ish by scanning last N lines.
        lines = _tail_lines(inbox, n=min(limit, 2000))
        for ln in lines:
            try:
                obj = json.loads(ln)
                if isinstance(obj, dict):
                    out.append(obj)
            except Exception:
                continue
    except Exception:
        return []
    return out[-limit:]


def _build_parent_status_index(repo_root: Path) -> Dict[str, Dict[str, Any]]:
    """
    Best-effort: scan automation daemon runs to build latest status per parent id.
    Matches logic in legacy /scc/parents/status.
    """
    base = (repo_root / "artifacts" / "scc_state" / "automation_daemon" / "runs").resolve()
    idx: Dict[str, Dict[str, Any]] = {}
    if not base.exists() or not base.is_dir():
        return idx
    try:
        runs = sorted([p for p in base.iterdir() if p.is_dir()], key=lambda p: p.name, reverse=True)
    except Exception:
        return idx

    for rd in runs[:200]:
        parents_path = (rd / "parents.json").resolve()
        if not parents_path.exists():
            continue
        try:
            parents_obj = json.loads(parents_path.read_text(encoding="utf-8", errors="replace") or "{}")
        except Exception:
            continue
        items = parents_obj.get("parents") if isinstance(parents_obj, dict) else None
        if not isinstance(items, list):
            continue
        for it in items:
            if not isinstance(it, dict):
                continue
            pid = str(it.get("id") or it.get("parent_id") or "").strip()
            if not pid or pid in idx:
                continue
            st = {
                "parent_id": pid,
                "status": str(it.get("status") or it.get("phase") or ""),
                "updated_utc": str(it.get("updated_utc") or it.get("finished_utc") or it.get("started_utc") or ""),
                "run_dir": _safe_rel(repo_root, rd),
                "item": it,
            }
            idx[pid] = st
    return idx


def register_control_plane_routes(app: FastAPI, *, repo_root: Path, config: Any) -> None:
    """
    Register /cp endpoints.

    Keep these endpoints thin and file-backed; SCC itself remains the source-of-truth for task execution.
    """

    @app.get("/cp/system/info")
    async def cp_system_info():
        from .service_registry import get_service_registry

        registry = get_service_registry()
        port_allocations = registry.get_port_allocations()

        services_info: Dict[str, Any] = {}
        for name, service in registry.get_all().items():
            if service.enabled:
                service_info: Dict[str, Any] = {"path": getattr(service, "path", f"/{name}")}
                if service.allocated_port:
                    service_info["allocated_port"] = service.allocated_port
                services_info[name] = service_info

        return {
            "status": "running",
            "service": getattr(config, "app_name", "unified_server"),
            "version": getattr(config, "app_version", ""),
            "server_port": getattr(config, "port", None),
            "endpoints": {
                "health": "/health",
                "ready": "/health/ready",
                "mcp": "/mcp",
                "a2a_hub": "/api",
                "opencode": "/opencode",
                "clawdbot": "/clawdbot",
                "console": "/scc",
                **{name: info["path"] for name, info in services_info.items()},
            },
            "services": services_info,
            "port_allocations": port_allocations,
        }

    @app.get("/cp/health")
    async def cp_health():
        from .health import readiness_check

        return await readiness_check()

    # --- Memory ledger (kept for compatibility; UI may hide it) ---
    _memory_lock = None
    try:
        import threading

        _memory_lock = threading.Lock()
    except Exception:
        _memory_lock = None

    @app.get("/cp/memory/tail")
    async def cp_memory_tail(n: int = 80):
        p = _memory_ledger_path(repo_root)
        lines = _tail_lines(p, n=int(n or 80))
        items: List[Dict[str, Any]] = []
        for ln in lines:
            try:
                obj = json.loads(ln)
                if isinstance(obj, dict):
                    items.append(obj)
            except Exception:
                continue
        return {"ok": True, "path": _safe_rel(repo_root, p), "items": items}

    @app.get("/cp/memory/stats")
    async def cp_memory_stats():
        p = _memory_ledger_path(repo_root)
        try:
            size = int(p.stat().st_size) if p.exists() else 0
        except Exception:
            size = -1
        return {"ok": True, "path": _safe_rel(repo_root, p), "size_bytes": size}

    @app.post("/cp/memory/append")
    async def cp_memory_append(request: Request):
        body = await request.json()
        if not isinstance(body, dict):
            return JSONResponse(status_code=400, content={"ok": False, "error": "invalid_body"})
        item = {
            "ts_utc": _iso_now(),
            "source": str(body.get("source") or "").strip() or "ui",
            "role": str(body.get("role") or "").strip() or "assistant",
            "kind": str(body.get("kind") or "").strip() or "note",
            "content": str(body.get("content") or "").strip(),
            "meta": body.get("meta") if isinstance(body.get("meta"), dict) else {},
        }
        if not item["content"]:
            return JSONResponse(status_code=400, content={"ok": False, "error": "missing_content"})
        p = _memory_ledger_path(repo_root)
        line = (json.dumps(item, ensure_ascii=False) + "\n").encode("utf-8", errors="replace")
        try:
            if _memory_lock:
                with _memory_lock:
                    with p.open("ab") as f:
                        f.write(line)
            else:
                with p.open("ab") as f:
                    f.write(line)
        except Exception as e:
            return JSONResponse(status_code=500, content={"ok": False, "error": f"append_failed: {e}"})
        return {"ok": True, "path": _safe_rel(repo_root, p), "item": item}

    # --- Routing ---
    @app.get("/cp/routing")
    async def cp_routing_get():
        p = _routing_path(repo_root)
        obj = _read_json(p, None)
        if obj is None:
            obj = _default_routing(repo_root)
            try:
                _write_json(p, obj)
            except Exception:
                pass
        ok, err = _validate_routing(obj)
        if not ok:
            return JSONResponse(status_code=500, content={"ok": False, "error": f"invalid_routing_on_disk: {err}", "path": _safe_rel(repo_root, p), "routing": obj})
        obj["updated_utc"] = obj.get("updated_utc") or _iso_now()
        return {"ok": True, "path": _safe_rel(repo_root, p), "routing": obj}

    @app.put("/cp/routing")
    async def cp_routing_put(request: Request):
        body = await request.json()
        if not isinstance(body, dict):
            return JSONResponse(status_code=400, content={"ok": False, "error": "invalid_body"})
        routing = body.get("routing") if "routing" in body else body
        ok, err = _validate_routing(routing)
        if not ok:
            return JSONResponse(status_code=400, content={"ok": False, "error": err})
        routing["updated_utc"] = _iso_now()
        p = _routing_path(repo_root)
        _write_json(p, routing)
        return {"ok": True, "path": _safe_rel(repo_root, p), "routing": routing}

    @app.post("/cp/routing/reset")
    async def cp_routing_reset():
        routing = _default_routing(repo_root)
        p = _routing_path(repo_root)
        _write_json(p, routing)
        return {"ok": True, "path": _safe_rel(repo_root, p), "routing": routing}

    # --- Tasks ---
    @app.get("/cp/tasks/list")
    async def cp_tasks_list(limit: int = 80, status: str | None = None, q: str | None = None, after: str | None = None):
        # Reuse SCC's canonical list logic by importing the queue directly.
        try:
            from tools.scc.task_queue import SCCTaskQueue

            tq = SCCTaskQueue(repo_root=repo_root)
            items = tq.list(limit=5000)
            # Mirror /scc/tasks filtering/pagination behavior.
            out: List[Dict[str, Any]] = []
            status_f = str(status or "").strip().lower() or None
            q_f = str(q or "").strip().lower() or None
            after_id = str(after or "").strip() or None
            started = after_id is None
            for rec in items:
                if not hasattr(rec, "__dict__"):
                    continue
                d = dict(rec.__dict__)
                tid = str(d.get("task_id") or "").strip()
                if not tid:
                    continue
                if not started:
                    if tid == after_id:
                        started = True
                    continue
                if status_f and str(d.get("status") or "").strip().lower() != status_f:
                    continue
                req = d.get("request") if isinstance(d.get("request"), dict) else {}
                task = req.get("task") if isinstance(req.get("task"), dict) else {}
                goal = str(task.get("goal") or req.get("goal") or "").strip()
                if q_f and q_f not in (tid + " " + goal).lower():
                    continue
                d["_goal"] = goal
                out.append(d)
                if len(out) >= int(limit or 80):
                    break
            next_cursor = out[-1]["task_id"] if out else None
            return {"ok": True, "items": out, "next_cursor": next_cursor}
        except Exception as e:
            return JSONResponse(status_code=500, content={"ok": False, "error": f"tasks_list_failed: {e}"})

    @app.get("/cp/tasks/{task_id}/children")
    async def cp_task_children(task_id: str, limit: int = 200):
        try:
            from tools.scc.task_queue import SCCTaskQueue
            from tools.scc.orchestrators.subtask_pool import list_subtasks

            tq = SCCTaskQueue(repo_root=repo_root)
            items = [r.__dict__ for r in list_subtasks(queue=tq, parent_task_id=str(task_id), limit=int(limit or 200))]
            return {"ok": True, "task_id": str(task_id), "items": items}
        except Exception as e:
            return JSONResponse(status_code=500, content={"ok": False, "error": f"task_children_failed: {e}"})

    @app.get("/cp/parents/status")
    async def cp_parents_status(limit: int = 200):
        try:
            inbox_items = _read_parent_inbox(repo_root, limit=5000)
            idx = _build_parent_status_index(repo_root)
            out: List[Dict[str, Any]] = []
            for it in reversed(inbox_items):
                pid = str(it.get("id") or it.get("parent_id") or it.get("task_id") or "").strip()
                if not pid:
                    continue
                st = idx.get(pid) or {}
                out.append(
                    {
                        "id": pid,
                        "title": str(it.get("title") or ""),
                        "goal": str(it.get("goal") or ""),
                        "status": st.get("status") or str(it.get("status") or ""),
                        "last": st.get("updated_utc") or str(it.get("ts_utc") or it.get("created_utc") or ""),
                        "run_dir": st.get("run_dir"),
                        "inbox": it,
                    }
                )
                if len(out) >= int(limit or 200):
                    break
            return {"ok": True, "items": out}
        except Exception as e:
            return JSONResponse(status_code=500, content={"ok": False, "error": f"parents_status_failed: {e}"})

    # --- Logs / Flow ---
    @app.get("/cp/logs/streams")
    async def cp_logs_streams():
        return {"ok": True, "items": _enumerate_streams(repo_root)}

    @app.get("/cp/logs/tail")
    async def cp_logs_tail(stream: str, n: int = 200):
        p = _resolve_stream_path(repo_root, stream)
        if not p:
            return JSONResponse(status_code=400, content={"ok": False, "error": "unknown_stream"})
        lines = _tail_lines(p, n=int(n or 200))
        return {"ok": True, "stream": stream, "path": _safe_rel(repo_root, p), "lines": lines}

    @app.get("/cp/flow/streams")
    async def cp_flow_streams():
        # A curated subset with high signal for dispatch/execution flow.
        candidates = [
            ("scc_state", "parent_inbox.jsonl"),
            ("scc_state", "executor_hub/events.jsonl"),
            ("dispatch", "watchdog_events.jsonl"),
            ("logs", "leader.jsonl"),
            ("logs", "jobs.jsonl"),
            ("logs", "failures.jsonl"),
            ("logs", "state_events.jsonl"),
        ]
        roots = _log_stream_roots(repo_root)
        items: List[Dict[str, Any]] = []
        for root_name, rel in candidates:
            base = roots.get(root_name)
            if not base:
                continue
            p = (base / rel).resolve()
            try:
                p.relative_to(base)
            except Exception:
                continue
            if not p.exists() or not p.is_file():
                continue
            try:
                size = int(p.stat().st_size)
            except Exception:
                size = -1
            items.append(
                {
                    "stream": f"{root_name}:{rel}",
                    "root": root_name,
                    "path": _safe_rel(repo_root, p),
                    "size_bytes": size,
                }
            )
        return {"ok": True, "items": items}

    @app.get("/cp/flow/tail")
    async def cp_flow_tail(stream: str, n: int = 200):
        # Reuse the same allowlist resolver.
        p = _resolve_stream_path(repo_root, stream)
        if not p:
            return JSONResponse(status_code=400, content={"ok": False, "error": "unknown_stream"})
        lines = _tail_lines(p, n=int(n or 200))
        return {"ok": True, "stream": stream, "path": _safe_rel(repo_root, p), "lines": lines}

    def _parse_ts(obj: Any) -> str:
        if isinstance(obj, dict):
            for k in ("ts_utc", "t", "time", "timestamp", "created_utc", "updated_utc"):
                v = obj.get(k)
                if isinstance(v, str) and v.strip():
                    return v.strip()
        return ""

    def _ts_epoch_ms(ts: str) -> int:
        ts = str(ts or "").strip()
        if not ts:
            return 0
        # Numeric epoch formats
        try:
            if ts.isdigit():
                n = int(ts, 10)
                # heuristics: seconds vs ms
                if n > 10_000_000_000:
                    return n
                return n * 1000
        except Exception:
            pass
        # ISO-like
        try:
            s = ts.replace("Z", "+00:00")
            dt = datetime.fromisoformat(s)
            return int(dt.timestamp() * 1000)
        except Exception:
            return 0

    def _normalize_ids(ids: Dict[str, str]) -> Dict[str, str]:
        """
        Normalize common id keys into canonical fields.
        """
        out: Dict[str, str] = {}
        for k, v in (ids or {}).items():
            if not v:
                continue
            kk = str(k)
            if kk in ("task_id", "taskId") and "task_id" not in out:
                out["task_id"] = str(v)
            elif kk in ("job_id", "jobId") and "job_id" not in out:
                out["job_id"] = str(v)
            elif kk in ("parent_id", "parentId") and "parent_id" not in out:
                out["parent_id"] = str(v)
            elif kk in ("run_id", "runId") and "run_id" not in out:
                out["run_id"] = str(v)
            elif kk in ("executor_id", "executorId") and "executor_id" not in out:
                out["executor_id"] = str(v)
        return out

    def _extract_ids(obj: Any) -> Dict[str, str]:
        out: Dict[str, str] = {}
        if not isinstance(obj, dict):
            return out
        for k in ("task_id", "taskId", "job_id", "jobId", "parent_id", "parentId", "run_id", "runId", "executor_id", "executorId"):
            v = obj.get(k)
            if v is None:
                continue
            s = str(v).strip()
            if s:
                out[k] = s
        # Some streams nest ids.
        if "task" in obj and isinstance(obj.get("task"), dict):
            tid = str(obj["task"].get("id") or obj["task"].get("task_id") or "").strip()
            if tid and "task_id" not in out:
                out["task_id"] = tid
        if "job" in obj and isinstance(obj.get("job"), dict):
            jid = str(obj["job"].get("id") or obj["job"].get("job_id") or "").strip()
            if jid and "job_id" not in out:
                out["job_id"] = jid
        return _normalize_ids(out)

    def _summarize(obj: Any) -> str:
        if not isinstance(obj, dict):
            return ""
        for k in ("type", "name", "event", "status", "level", "reason", "message"):
            v = obj.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
        return ""

    @app.get("/cp/flow/combined")
    async def cp_flow_combined(limit: int = 300, q: str | None = None, streams: str | None = None, include_raw: bool = False):
        """
        Merge multiple JSONL streams into a single, time-ordered list.

        This is intentionally best-effort: it trades perfect ordering for quick operator visibility.
        """
        limit = max(20, min(int(limit or 300), 2000))
        qf = str(q or "").strip().lower() or None

        curated = (await cp_flow_streams()).get("items", [])  # type: ignore[union-attr]
        if not isinstance(curated, list):
            curated = []
        curated_streams = [str(x.get("stream") or "") for x in curated if isinstance(x, dict)]
        curated_streams = [s for s in curated_streams if s]

        chosen: List[str] = []
        if streams:
            parts = [p.strip() for p in str(streams).split(",")]
            chosen = [p for p in parts if p]
        else:
            chosen = curated_streams

        events: List[Dict[str, Any]] = []
        for s in chosen:
            p = _resolve_stream_path(repo_root, s)
            if not p:
                continue
            lines = _tail_lines(p, n=max(50, min(600, limit)))
            for ln in lines:
                try:
                    obj = json.loads(ln)
                except Exception:
                    continue
                if not isinstance(obj, dict):
                    continue
                ts = _parse_ts(obj)
                ids = _extract_ids(obj)
                summary = _summarize(obj)
                row: Dict[str, Any] = {
                    "ts": ts,
                    "ts_epoch_ms": _ts_epoch_ms(ts),
                    "stream": s,
                    "summary": summary,
                    "ids": ids,
                }
                if include_raw:
                    row["raw"] = obj

                if qf:
                    hay = (s + " " + summary + " " + json.dumps(ids, ensure_ascii=False)).lower()
                    if include_raw:
                        try:
                            hay += " " + json.dumps(obj, ensure_ascii=False).lower()
                        except Exception:
                            pass
                    if qf not in hay:
                        continue
                events.append(row)

        # Order by epoch ms; fallback to ts string.
        events.sort(key=lambda e: (int(e.get("ts_epoch_ms") or 0), str(e.get("ts") or "")), reverse=True)
        events = events[:limit]
        stream_stats: Dict[str, int] = {}
        for ev in events:
            s = str(ev.get("stream") or "")
            if not s:
                continue
            stream_stats[s] = int(stream_stats.get(s) or 0) + 1
        return {
            "ok": True,
            "query": {"limit": limit, "q": qf, "streams": chosen, "include_raw": bool(include_raw)},
            "streams": chosen,
            "stream_stats": stream_stats,
            "items": events,
        }
