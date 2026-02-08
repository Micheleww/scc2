from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from tools.mcp_bus.server.audit import AuditLogger
from tools.mcp_bus.server.security import PathSecurity, load_security_config
from tools.mcp_bus.server.tools import ATAMessageMarkParams, ATAReceiveParams, ATASendParams, ToolExecutor
from tools.scc.event_log import SCCEventLogger
from tools.scc.task_queue import SCCTaskQueue


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha1_hex(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def _to_task_payload(message: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Extract an SCC task payload from an ATA message.

    Accepted formats (minimal, fail-soft):
    - message.payload is dict and contains task/workspace or repo_path/commands_hint/test_cmds
    - message.payload.message or message.payload.text is a JSON string
    """
    payload = message.get("payload")
    if isinstance(payload, dict):
        if "workspace" in payload or "task" in payload:
            return payload, None
        if "repo_path" in payload and ("commands_hint" in payload or "test_cmds" in payload):
            return payload, None
        msg_text = payload.get("message") or payload.get("text")
        if isinstance(msg_text, str) and msg_text.strip():
            s = msg_text.strip()
            if s.startswith("{") and s.endswith("}"):
                try:
                    data = json.loads(s)
                    if isinstance(data, dict):
                        return data, None
                except Exception as e:
                    return None, f"invalid_json_in_payload_message: {e}"
    if isinstance(payload, str) and payload.strip():
        s = payload.strip()
        if s.startswith("{") and s.endswith("}"):
            try:
                data = json.loads(s)
                if isinstance(data, dict):
                    return data, None
            except Exception as e:
                return None, f"invalid_json_payload: {e}"
    return None, "no_task_payload"


@dataclass
class ATAIngestionConfig:
    enabled: bool = True
    poll_interval_s: float = 1.0
    to_agent: str = "scc"
    from_agent: str = "scc"
    kind: str = "request"
    max_batch: int = 5
    state_dir: str = "artifacts/scc_state"
    idempotency_index_file: str = "artifacts/scc_state/ata_msg_index.json"
    ack_mode: str = "plain"  # plain|chat_prefix|raw_json
    ack_prefix_template: str = ""  # e.g. "@{to_agent} "
    ack_message_template: str = "[SCC] accepted task_id={task_id}"


def _safe_format(template: str, fields: Dict[str, Any]) -> str:
    t = str(template or "")
    if not t.strip():
        return ""
    try:
        return t.format(**fields)
    except Exception:
        return t


class ATAIdempotencyIndex:
    """
    Minimal idempotency store for ATA ingestion.

    Key: msg_id -> {task_id, first_seen_at, last_seen_at, status}
    Stored as a JSON dict on disk.
    """

    def __init__(self, *, repo_root: Path, rel_path: str):
        self._lock = threading.Lock()
        self._path = (repo_root / rel_path).resolve()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._data: Dict[str, Dict[str, Any]] = {}
        self._load()

    @property
    def path(self) -> Path:
        return self._path

    def _load(self) -> None:
        try:
            if self._path.exists():
                obj = json.loads(self._path.read_text(encoding="utf-8"))
                if isinstance(obj, dict):
                    self._data = {str(k): (v if isinstance(v, dict) else {}) for k, v in obj.items()}
        except Exception:
            self._data = {}

    def _save(self) -> None:
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self._path)

    def get_task_id(self, msg_id: str) -> Optional[str]:
        msg_id = str(msg_id or "").strip()
        if not msg_id:
            return None
        with self._lock:
            rec = self._data.get(msg_id) or {}
            task_id = str(rec.get("task_id") or "").strip()
            return task_id or None

    def upsert(self, msg_id: str, *, task_id: str, status: str, now_iso: str) -> None:
        msg_id = str(msg_id or "").strip()
        task_id = str(task_id or "").strip()
        if not msg_id or not task_id:
            return
        with self._lock:
            existing = self._data.get(msg_id) or {}
            self._data[msg_id] = {
                "task_id": task_id,
                "first_seen_at": existing.get("first_seen_at") or now_iso,
                "last_seen_at": now_iso,
                "status": status,
            }
            self._save()


class ATAIngestionEngine:
    def __init__(self, *, task_queue: SCCTaskQueue, repo_root: Path, config: ATAIngestionConfig):
        self.task_queue = task_queue
        self.repo_root = Path(repo_root)
        self.cfg = config

        self._state_lock = threading.Lock()
        self._enabled = bool(self.cfg.enabled)
        self._mode = "disabled" if not self._enabled else "manual"
        self._thread_alive = False
        self._last_poll_at: Optional[str] = None
        self._last_poll_result: Dict[str, Any] = {}
        self._last_error: Optional[Dict[str, Any]] = None
        self._since_boot_counts: Dict[str, int] = {
            "polls": 0,
            "fetched": 0,
            "accepted": 0,
            "deduped": 0,
            "enqueued": 0,
            "acked": 0,
            "marked": 0,
            "skipped": 0,
            "failed": 0,
        }

        self._state_dir = (self.repo_root / (self.cfg.state_dir or "artifacts/scc_state")).resolve()
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._state_file = (self._state_dir / "ata_ingestion_state.json").resolve()
        self._events_logger = SCCEventLogger(path=(self._state_dir / "ata_ingestion_events.jsonl").resolve())

        self._id_index = ATAIdempotencyIndex(repo_root=self.repo_root, rel_path=self.cfg.idempotency_index_file)

        self.executor: Optional[ToolExecutor] = None
        self._init_executor()

    def _set_last_error(self, *, error_code: str, message: str) -> None:
        err = {
            "error_code": str(error_code or "error").strip() or "error",
            "message": str(message or "").strip(),
            "stack_hash": _sha1_hex(f"{error_code}:{message}")[:16],
            "at": _utc_now_iso(),
        }
        with self._state_lock:
            self._last_error = err
        try:
            self._state_file.write_text(json.dumps(err, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _clear_last_error(self) -> None:
        with self._state_lock:
            self._last_error = None
        try:
            if self._state_file.exists():
                self._state_file.unlink()
        except Exception:
            pass

    def _init_executor(self) -> None:
        repo_root_str = str(self.repo_root)
        config_path = str(
            Path(__file__).resolve().parents[2]
            / "tools"
            / "mcp_bus"
            / "config"
            / "config.example.json"
        )
        missing: list[str] = []
        try:
            if not Path(config_path).exists():
                missing.append("mcp_bus_config_file")
            cfg_json: dict[str, Any] = {}
            try:
                with open(config_path, encoding="utf-8") as f:
                    cfg_json = json.load(f)
            except Exception:
                cfg_json = {}
            paths_cfg = (cfg_json.get("paths") or {}) if isinstance(cfg_json, dict) else {}
            inbox_dir = paths_cfg.get("inbox_dir") or "docs/REPORT/inbox"
            board_file = paths_cfg.get("board_file") or "docs/REPORT/QCC-PROGRAM-BOARD-v0.1.md"
            log_dir = paths_cfg.get("log_dir") or "docs/LOG/mcp_bus"
            if not inbox_dir:
                missing.append("inbox_dir")
            if not board_file:
                missing.append("board_file")

            security_config = load_security_config(config_path, repo_root_str)
            security = PathSecurity(security_config, repo_root_str)
            audit_logger = AuditLogger(log_dir, repo_root_str)

            if missing:
                self._set_last_error(error_code="ata_config_invalid", message="missing: " + ",".join(missing))
                self.executor = None
                return

            self.executor = ToolExecutor(
                repo_root=repo_root_str,
                inbox_dir=inbox_dir,
                board_file=board_file,
                security=security,
                audit_logger=audit_logger,
            )
            self._clear_last_error()
        except Exception as e:
            self.executor = None
            self._set_last_error(error_code="ata_executor_init_failed", message=str(e))

    def set_mode(self, mode: str) -> None:
        with self._state_lock:
            self._mode = str(mode or "").strip() or self._mode

    def set_thread_alive(self, alive: bool) -> None:
        with self._state_lock:
            self._thread_alive = bool(alive)

    def _derive_task_id(self, msg_id: str) -> str:
        return "scc_ata_" + _sha1_hex(str(msg_id or "").strip())[:16]

    def health(self) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        with self._state_lock:
            last_poll_at = self._last_poll_at
        last_poll_result = dict(self._last_poll_result or {})
        last_error = dict(self._last_error) if self._last_error else None
        enabled = self._enabled
        mode = self._mode
        thread_alive = self._thread_alive
        since_boot_counts = dict(self._since_boot_counts or {})

        last_poll_stale = False
        if last_poll_at:
            try:
                dt = datetime.fromisoformat(last_poll_at.replace("Z", "+00:00"))
                stale_s = max(2.0, float(self.cfg.poll_interval_s or 1.0) * 3.0)
                last_poll_stale = (now - dt).total_seconds() > stale_s
            except Exception:
                last_poll_stale = True

        try:
            queue_stats = self.task_queue.stats()
        except Exception:
            queue_stats = {}

        queue_depth = int(queue_stats.get("pending") or 0)

        last_poll_counts: Dict[str, int] = {}
        if isinstance(last_poll_result.get("counts"), dict):
            for k, v in (last_poll_result.get("counts") or {}).items():
                try:
                    last_poll_counts[str(k)] = int(v)
                except Exception:
                    pass

        return {
            "ok": True,
            "enabled": enabled,
            "mode": mode,
            "thread_alive": thread_alive,
            "last_poll_at": last_poll_at,
            "last_poll_stale": last_poll_stale,
            "last_poll_result": last_poll_result,
            "last_poll_counts": last_poll_counts,
            "last_error": last_error,
            "queue_stats": queue_stats,
            "queue_depth": queue_depth,
            "since_boot_counts": since_boot_counts,
            "idempotency_index_path": str(self._id_index.path),
            "state_file_path": str(self._state_file),
        }

    def state(self) -> Dict[str, Any]:
        health = self.health()
        executor_available = self.executor is not None
        return {
            "ok": bool(health.get("ok") and executor_available),
            "executor_available": executor_available,
            "state": health,
        }

    def poll_once(self, *, max_n: Optional[int] = None) -> Dict[str, Any]:
        now_iso = _utc_now_iso()
        with self._state_lock:
            self._last_poll_at = now_iso
            self._since_boot_counts["polls"] += 1

        counts = {
            "fetched": 0,
            "accepted": 0,
            "deduped": 0,
            "enqueued": 0,
            "acked": 0,
            "marked": 0,
            "skipped": 0,
            "failed": 0,
        }
        skipped: list[dict[str, Any]] = []

        if not self.cfg.enabled:
            out = {"ok": False, "error_code": "disabled", "error": "SCC_ATA_INGEST_ENABLED=false"}
            with self._state_lock:
                self._last_poll_result = out
            self._events_logger.emit("ata_poll_skipped_disabled", data=out)
            return out

        if not self.executor:
            out = {"ok": False, "error_code": "executor_unavailable", "error": "ToolExecutor not initialized"}
            with self._state_lock:
                self._last_poll_result = out
                self._since_boot_counts["failed"] += 1
            self._events_logger.emit("ata_poll_failed_no_executor", data=out)
            return out

        try:
            params = ATAReceiveParams(
                taskcode=None,
                from_agent=None,
                to_agent=self.cfg.to_agent,
                kind=self.cfg.kind,
                priority=None,
                status=None,
                unread_only=True,
                include_context=False,
                limit=int(max_n or self.cfg.max_batch or 5),
            )
            res = self.executor.ata_receive(params, caller="scc", auth_ctx={"is_admin": True})
            if not isinstance(res, dict) or not res.get("success"):
                out = {
                    "ok": False,
                    "error_code": "ata_receive_failed",
                    "error": res.get("error") if isinstance(res, dict) else "ata_receive_failed",
                }
                with self._state_lock:
                    self._last_poll_result = out
                    self._since_boot_counts["failed"] += 1
                self._events_logger.emit("ata_poll_failed_receive", data=out)
                return out

            msgs = res.get("messages") or []
            if not isinstance(msgs, list):
                out = {"ok": False, "error_code": "invalid_messages", "error": "messages is not a list"}
                with self._state_lock:
                    self._last_poll_result = out
                    self._since_boot_counts["failed"] += 1
                return out

            counts["fetched"] = len(msgs)
            for msg in msgs:
                if not isinstance(msg, dict):
                    continue
                msg_id = str(msg.get("msg_id") or "").strip()

                if msg_id:
                    existing_task_id = self._id_index.get_task_id(msg_id)
                    if existing_task_id:
                        counts["deduped"] += 1
                        if not self.task_queue.exists(existing_task_id):
                            try:
                                self.task_queue.submit_with_task_id(
                                    task_id=existing_task_id,
                                    payload={"task": {"goal": "Rehydrated from ATA dedup index"}, "workspace": {}, "raw": msg},
                                )
                                counts["enqueued"] += 1
                            except Exception:
                                counts["failed"] += 1
                        acked, marked = self._ack_and_mark(msg, task_id=existing_task_id)
                        counts["acked"] += 1 if acked else 0
                        counts["marked"] += 1 if marked else 0
                        continue

                payload, err = _to_task_payload(msg)
                if not payload:
                    skipped.append({"msg_id": msg.get("msg_id"), "taskcode": msg.get("taskcode"), "error": err})
                    counts["skipped"] += 1
                    if msg_id:
                        try:
                            mark = ATAMessageMarkParams(msg_ids=[msg_id], status="read")
                            self.executor.ata_message_mark(mark, caller="scc", auth_ctx={"is_admin": True})
                        except Exception:
                            pass
                    continue

                if not msg_id:
                    rec = self.task_queue.submit(payload)
                    counts["accepted"] += 1
                    counts["enqueued"] += 1
                    acked, marked = self._ack_and_mark(msg, task_id=rec.task_id)
                    counts["acked"] += 1 if acked else 0
                    counts["marked"] += 1 if marked else 0
                    continue

                task_id = self._derive_task_id(msg_id)
                self._id_index.upsert(msg_id, task_id=task_id, status="mapped", now_iso=now_iso)
                if not self.task_queue.exists(task_id):
                    self.task_queue.submit_with_task_id(task_id=task_id, payload=payload)
                    counts["enqueued"] += 1
                self._id_index.upsert(msg_id, task_id=task_id, status="enqueued", now_iso=now_iso)
                counts["accepted"] += 1
                acked, marked = self._ack_and_mark(msg, task_id=task_id)
                counts["acked"] += 1 if acked else 0
                counts["marked"] += 1 if marked else 0

            out = {"ok": True, "counts": counts, "skipped": skipped}
            with self._state_lock:
                self._last_poll_result = out
                for k, v in counts.items():
                    self._since_boot_counts[k] += int(v)
            self._events_logger.emit("ata_poll_ok", data=out)
            return out
        except Exception as e:
            self._set_last_error(error_code="poll_once_exception", message=str(e))
            out = {"ok": False, "error_code": "poll_once_exception", "error": str(e)}
            with self._state_lock:
                self._last_poll_result = out
                self._since_boot_counts["failed"] += 1
            self._events_logger.emit("ata_poll_exception", data=out)
            return out

    def _ack_and_mark(self, msg: Dict[str, Any], *, task_id: str) -> tuple[bool, bool]:
        if not self.executor:
            return False, False
        msg_id = str(msg.get("msg_id") or "").strip()
        taskcode = str(msg.get("taskcode") or "").strip() or "SCC"
        from_agent = str(msg.get("from_agent") or "").strip() or "unknown"

        ack_ok = False
        mark_ok = False

        fields = {
            "task_id": str(task_id),
            "msg_id": msg_id,
            "taskcode": taskcode,
            "from_agent": str(self.cfg.from_agent),
            "to_agent": from_agent,
            "kind": "ack",
        }

        prefix = _safe_format(self.cfg.ack_prefix_template, fields)
        message = _safe_format(self.cfg.ack_message_template, fields) or f"[SCC] accepted task_id={task_id}"

        if str(self.cfg.ack_mode or "").strip().lower() == "raw_json":
            payload = {"task_id": str(task_id), "msg_id": msg_id or None, "status": "accepted", "message": message}
        else:
            payload = {"message": str(prefix or "") + str(message), "task_id": str(task_id)}

        try:
            ack = ATASendParams(
                taskcode=taskcode,
                from_agent=self.cfg.from_agent,
                to_agent=from_agent,
                kind="ack",
                payload=payload,
                priority="normal",
                requires_response=False,
                context_hint="scc_task_accept",
            )
            self.executor.ata_send(ack, caller="scc", auth_ctx={"is_admin": True})
            ack_ok = True
        except Exception:
            ack_ok = False

        if msg_id:
            try:
                mark = ATAMessageMarkParams(msg_ids=[msg_id], status="acked")
                self.executor.ata_message_mark(mark, caller="scc", auth_ctx={"is_admin": True})
                mark_ok = True
            except Exception:
                mark_ok = False

        return ack_ok, mark_ok


class SCCATAIngestionWorker:
    def __init__(
        self,
        *,
        task_queue: SCCTaskQueue,
        repo_root: Any,
        config: Optional[ATAIngestionConfig] = None,
    ):
        self.task_queue = task_queue
        self.cfg = config or ATAIngestionConfig()
        self.engine = ATAIngestionEngine(task_queue=task_queue, repo_root=Path(str(repo_root)), config=self.cfg)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if not self.cfg.enabled:
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self.engine.set_mode("thread")
        self._thread = threading.Thread(target=self._loop, name="scc-ata-ingestion", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self.engine.set_mode("manual")

    def poll_and_process_once(self) -> Dict[str, Any]:
        return self.engine.poll_once()

    def health(self) -> Dict[str, Any]:
        return self.engine.health()

    def _loop(self) -> None:
        self.engine.set_thread_alive(True)
        while not self._stop.is_set():
            try:
                res = self.engine.poll_once()
                if not res.get("ok"):
                    time.sleep(max(0.2, float(self.cfg.poll_interval_s or 1.0)))
                    continue
                fetched = int(((res.get("counts") or {}) if isinstance(res, dict) else {}).get("fetched") or 0)
                if fetched <= 0:
                    time.sleep(max(0.2, float(self.cfg.poll_interval_s or 1.0)))
                    continue
            except Exception:
                time.sleep(max(0.2, float(self.cfg.poll_interval_s or 1.0)))
        self.engine.set_thread_alive(False)
