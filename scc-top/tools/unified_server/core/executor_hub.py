"""
Remote executor hub (agent protocol) for SCC unified server.

Goal:
- Provide a minimal, stable HTTP protocol so non-container agents (e.g. OpenClaw on Windows)
  can register/heartbeat, claim jobs, and report results.
- Keep persistence simple and append-only where possible (file-based, no DB dependency).
"""

from __future__ import annotations

import json
import os
import time
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_slug(s: str) -> str:
    s = (s or "").strip().lower()
    if not s:
        return "job"
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
    slug = "".join(out).strip("-") or "job"
    return slug[:60]


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


@dataclass
class HubPaths:
    root: Path
    executors_json: Path
    events_jsonl: Path
    queued_dir: Path
    claimed_dir: Path
    done_dir: Path
    failed_dir: Path


class ExecutorHub:
    def __init__(self, repo_root: Path):
        base = (repo_root / "artifacts" / "scc_state" / "executor_hub").resolve()
        self.paths = HubPaths(
            root=base,
            executors_json=(base / "executors.json").resolve(),
            events_jsonl=(base / "events.jsonl").resolve(),
            queued_dir=(base / "jobs" / "queued").resolve(),
            claimed_dir=(base / "jobs" / "claimed").resolve(),
            done_dir=(base / "jobs" / "done").resolve(),
            failed_dir=(base / "jobs" / "failed").resolve(),
        )
        self._lock = threading.Lock()

        for d in [self.paths.root, self.paths.queued_dir, self.paths.claimed_dir, self.paths.done_dir, self.paths.failed_dir]:
            d.mkdir(parents=True, exist_ok=True)

        if not self.paths.executors_json.exists():
            _write_json(self.paths.executors_json, {"version": 1, "items": {}})

    def _append_event(self, ev: Dict[str, Any]) -> None:
        try:
            ev = dict(ev)
            ev.setdefault("ts_utc", _utc_now())
            line = (json.dumps(ev, ensure_ascii=False) + "\n").encode("utf-8", errors="replace")
            self.paths.events_jsonl.parent.mkdir(parents=True, exist_ok=True)
            with self.paths.events_jsonl.open("ab") as f:
                f.write(line)
        except Exception:
            pass

    def _load_executors(self) -> Dict[str, Any]:
        data = _read_json(self.paths.executors_json, {"version": 1, "items": {}})
        if not isinstance(data, dict):
            data = {"version": 1, "items": {}}
        if "items" not in data or not isinstance(data.get("items"), dict):
            data["items"] = {}
        data.setdefault("version", 1)
        return data

    def _save_executors(self, data: Dict[str, Any]) -> None:
        _write_json(self.paths.executors_json, data)

    def register_executor(self, executor_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        executor_id = (executor_id or "").strip()
        if not executor_id:
            return {"ok": False, "error": "missing_executor_id"}

        display_name = str(payload.get("display_name") or "").strip() or executor_id
        capabilities = payload.get("capabilities") if isinstance(payload.get("capabilities"), dict) else {}
        meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
        status = str(payload.get("status") or "").strip() or "online"

        with self._lock:
            data = self._load_executors()
            items = data["items"]
            existing = items.get(executor_id) if isinstance(items.get(executor_id), dict) else {}
            items[executor_id] = {
                **existing,
                "executor_id": executor_id,
                "display_name": display_name,
                "capabilities": capabilities,
                "meta": meta,
                "status": status,
                "registered_utc": existing.get("registered_utc") or _utc_now(),
                "last_seen_utc": _utc_now(),
            }
            self._save_executors(data)

        self._append_event({"type": "executor.register", "executor_id": executor_id})
        return {"ok": True, "executor": items[executor_id]}

    def heartbeat(self, executor_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        executor_id = (executor_id or "").strip()
        if not executor_id:
            return {"ok": False, "error": "missing_executor_id"}

        status = str(payload.get("status") or "").strip() or "online"
        meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else None

        with self._lock:
            data = self._load_executors()
            items = data["items"]
            ex = items.get(executor_id) if isinstance(items.get(executor_id), dict) else None
            if not ex:
                # Auto-register minimal if heartbeat arrives first.
                ex = {"executor_id": executor_id, "display_name": executor_id, "capabilities": {}, "meta": {}}
                items[executor_id] = ex
                ex["registered_utc"] = _utc_now()
            ex["last_seen_utc"] = _utc_now()
            ex["status"] = status
            if meta is not None:
                ex["meta"] = meta
            self._save_executors(data)

        self._append_event({"type": "executor.heartbeat", "executor_id": executor_id, "status": status})
        return {"ok": True, "executor": items[executor_id]}

    def list_executors(self, limit: int = 200) -> Dict[str, Any]:
        limit = max(1, min(int(limit or 200), 2000))
        with self._lock:
            data = self._load_executors()
            items = list(data.get("items", {}).values())
        items = [x for x in items if isinstance(x, dict)]
        items.sort(key=lambda x: str(x.get("last_seen_utc") or ""), reverse=True)
        return {"ok": True, "items": items[:limit]}

    def _new_job_id(self) -> str:
        # timestamp + pid + monotonic-ish time
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        return f"job_{ts}_{os.getpid()}_{int(time.time() * 1000)}"

    def enqueue_job(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        title = str(payload.get("title") or "").strip() or "Job"
        target = payload.get("target") if isinstance(payload.get("target"), dict) else {}
        body = payload.get("payload") if isinstance(payload.get("payload"), dict) else payload.get("payload")
        priority = int(payload.get("priority") or 0)

        job_id = self._new_job_id()
        slug = _safe_slug(title)
        job = {
            "job_id": job_id,
            "title": title,
            "slug": slug,
            "created_utc": _utc_now(),
            "priority": priority,
            "target": target,
            "payload": body,
            "state": "queued",
        }

        path = (self.paths.queued_dir / f"{job_id}__{slug}.json").resolve()
        with self._lock:
            _write_json(path, job)

        self._append_event({"type": "job.enqueue", "job_id": job_id, "title": title})
        return {"ok": True, "job_id": job_id, "path": str(path), "job": job}

    def list_jobs(self, state: str = "queued", limit: int = 50) -> Dict[str, Any]:
        limit = max(1, min(int(limit or 50), 500))
        state = str(state or "queued").strip().lower()
        dir_map = {
            "queued": self.paths.queued_dir,
            "claimed": self.paths.claimed_dir,
            "done": self.paths.done_dir,
            "failed": self.paths.failed_dir,
        }
        d = dir_map.get(state)
        if not d:
            return {"ok": False, "error": "invalid_state", "allowed": list(dir_map.keys())}
        items: List[Dict[str, Any]] = []
        try:
            files = sorted(d.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
            for p in files:
                items.append({"name": p.name, "path": str(p), "size": int(p.stat().st_size)})
        except Exception:
            items = []
        return {"ok": True, "state": state, "dir": str(d), "items": items}

    def _match_target(self, job: Dict[str, Any], executor_id: str, ex: Dict[str, Any]) -> bool:
        target = job.get("target")
        if not isinstance(target, dict) or not target:
            return True
        want_id = str(target.get("executor_id") or "").strip()
        if want_id and want_id != executor_id:
            return False
        # capability match (simple tags)
        want_caps = target.get("capabilities")
        if isinstance(want_caps, list) and want_caps:
            have = ex.get("capabilities") if isinstance(ex.get("capabilities"), dict) else {}
            tags = have.get("tags") if isinstance(have.get("tags"), list) else []
            for w in want_caps:
                if str(w) not in [str(t) for t in tags]:
                    return False
        return True

    def claim_jobs(self, executor_id: str, max_jobs: int = 1, lease_s: int = 900) -> Dict[str, Any]:
        executor_id = (executor_id or "").strip()
        if not executor_id:
            return {"ok": False, "error": "missing_executor_id"}
        max_jobs = max(1, min(int(max_jobs or 1), 20))
        lease_s = max(30, min(int(lease_s or 900), 86400))

        with self._lock:
            data = self._load_executors()
            ex = data.get("items", {}).get(executor_id)
            if not isinstance(ex, dict):
                ex = {"executor_id": executor_id, "display_name": executor_id, "capabilities": {}, "meta": {}}
                data["items"][executor_id] = ex
                ex["registered_utc"] = _utc_now()
            ex["last_seen_utc"] = _utc_now()
            ex["status"] = "online"
            self._save_executors(data)

            queued = sorted(self.paths.queued_dir.glob("*.json"), key=lambda p: p.stat().st_mtime)
            claimed: List[Dict[str, Any]] = []
            now = int(time.time())
            for p in queued:
                if len(claimed) >= max_jobs:
                    break
                job = _read_json(p, None)
                if not isinstance(job, dict):
                    continue
                if not self._match_target(job, executor_id, ex):
                    continue

                expires = now + lease_s
                token = f"{p.stem}__{executor_id}__lease_{expires}"
                dst = (self.paths.claimed_dir / f"{token}.json").resolve()
                # Update job state and claim info before move.
                job["state"] = "claimed"
                job["claimed_utc"] = _utc_now()
                job["claimed_by"] = executor_id
                job["lease_expires_epoch"] = expires
                _write_json(p, job)
                try:
                    p.replace(dst)  # atomic rename on same volume
                except Exception:
                    # best-effort fallback: copy then delete
                    _write_json(dst, job)
                    try:
                        p.unlink(missing_ok=True)
                    except Exception:
                        pass
                claimed.append({"claim_token": dst.stem, "job": job})
                self._append_event({"type": "job.claim", "job_id": job.get("job_id"), "executor_id": executor_id})

        return {"ok": True, "executor_id": executor_id, "items": claimed}

    def _resolve_claim_path(self, claim_token: str) -> Tuple[Optional[Path], Optional[Dict[str, Any]]]:
        claim_token = str(claim_token or "").strip()
        if not claim_token:
            return (None, None)
        p = (self.paths.claimed_dir / f"{claim_token}.json").resolve()
        if not p.exists():
            return (None, None)
        job = _read_json(p, None)
        if not isinstance(job, dict):
            return (p, None)
        return (p, job)

    def complete_job(self, executor_id: str, claim_token: str, result: Any) -> Dict[str, Any]:
        executor_id = (executor_id or "").strip()
        if not executor_id:
            return {"ok": False, "error": "missing_executor_id"}
        with self._lock:
            p, job = self._resolve_claim_path(claim_token)
            if not p:
                return {"ok": False, "error": "unknown_claim_token"}
            if not isinstance(job, dict):
                return {"ok": False, "error": "invalid_claim_job"}
            if str(job.get("claimed_by") or "") != executor_id:
                return {"ok": False, "error": "claimed_by_mismatch"}
            job["state"] = "done"
            job["completed_utc"] = _utc_now()
            job["result"] = result
            dst = (self.paths.done_dir / p.name).resolve()
            _write_json(p, job)
            p.replace(dst)
            self._append_event({"type": "job.done", "job_id": job.get("job_id"), "executor_id": executor_id})
        return {"ok": True, "job": job, "path": str(dst)}

    def fail_job(self, executor_id: str, claim_token: str, error: str) -> Dict[str, Any]:
        executor_id = (executor_id or "").strip()
        if not executor_id:
            return {"ok": False, "error": "missing_executor_id"}
        with self._lock:
            p, job = self._resolve_claim_path(claim_token)
            if not p:
                return {"ok": False, "error": "unknown_claim_token"}
            if not isinstance(job, dict):
                return {"ok": False, "error": "invalid_claim_job"}
            if str(job.get("claimed_by") or "") != executor_id:
                return {"ok": False, "error": "claimed_by_mismatch"}
            job["state"] = "failed"
            job["failed_utc"] = _utc_now()
            job["error"] = str(error or "")
            dst = (self.paths.failed_dir / p.name).resolve()
            _write_json(p, job)
            p.replace(dst)
            self._append_event({"type": "job.failed", "job_id": job.get("job_id"), "executor_id": executor_id})
        return {"ok": True, "job": job, "path": str(dst)}


def register_executor_hub(app: FastAPI, repo_root: Path, *, base_path: str = "/cp") -> None:
    hub = ExecutorHub(repo_root=repo_root)

    base_path = (base_path or "/cp").strip() or "/cp"
    if not base_path.startswith("/"):
        base_path = "/" + base_path
    base_path = base_path.rstrip("/") or "/cp"

    # NOTE: /api is reserved for the legacy A2A Hub WSGI app (mounted as a service).
    # Unified-server control plane endpoints live under /cp to avoid mount collisions.

    @app.get(base_path + "/executors/list")
    async def api_executors_list(limit: int = 200):
        return hub.list_executors(limit=limit)

    @app.post(base_path + "/executors/register")
    async def api_executors_register(request: Request):
        body = await request.json()
        if not isinstance(body, dict):
            return JSONResponse(status_code=400, content={"ok": False, "error": "invalid_body"})
        executor_id = str(body.get("executor_id") or "").strip()
        return hub.register_executor(executor_id=executor_id, payload=body)

    @app.post(base_path + "/executors/heartbeat")
    async def api_executors_heartbeat(request: Request):
        body = await request.json()
        if not isinstance(body, dict):
            return JSONResponse(status_code=400, content={"ok": False, "error": "invalid_body"})
        executor_id = str(body.get("executor_id") or "").strip()
        return hub.heartbeat(executor_id=executor_id, payload=body)

    @app.post(base_path + "/jobs/enqueue")
    async def api_jobs_enqueue(request: Request):
        body = await request.json()
        if not isinstance(body, dict):
            return JSONResponse(status_code=400, content={"ok": False, "error": "invalid_body"})
        return hub.enqueue_job(payload=body)

    @app.get(base_path + "/jobs/list")
    async def api_jobs_list(state: str = "queued", limit: int = 50):
        return hub.list_jobs(state=state, limit=limit)

    @app.post(base_path + "/jobs/claim")
    async def api_jobs_claim(request: Request):
        body = await request.json()
        if not isinstance(body, dict):
            return JSONResponse(status_code=400, content={"ok": False, "error": "invalid_body"})
        executor_id = str(body.get("executor_id") or "").strip()
        max_jobs = int(body.get("max_jobs") or 1)
        lease_s = int(body.get("lease_s") or 900)
        return hub.claim_jobs(executor_id=executor_id, max_jobs=max_jobs, lease_s=lease_s)

    @app.post(base_path + "/jobs/complete")
    async def api_jobs_complete(request: Request):
        body = await request.json()
        if not isinstance(body, dict):
            return JSONResponse(status_code=400, content={"ok": False, "error": "invalid_body"})
        executor_id = str(body.get("executor_id") or "").strip()
        claim_token = str(body.get("claim_token") or "").strip()
        result = body.get("result")
        return hub.complete_job(executor_id=executor_id, claim_token=claim_token, result=result)

    @app.post(base_path + "/jobs/fail")
    async def api_jobs_fail(request: Request):
        body = await request.json()
        if not isinstance(body, dict):
            return JSONResponse(status_code=400, content={"ok": False, "error": "invalid_body"})
        executor_id = str(body.get("executor_id") or "").strip()
        claim_token = str(body.get("claim_token") or "").strip()
        error = str(body.get("error") or "").strip()
        return hub.fail_job(executor_id=executor_id, claim_token=claim_token, error=error)
