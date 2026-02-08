from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from tools.scc.event_model import SCCEventKind, SCCUnifiedEvent, new_event_id


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_mkdir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class SCCEvent:
    """
    Minimal, append-only event for SCC replay/observability.

    - type: stable identifier (snake_case)
    - ts_utc: ISO timestamp
    - task_id/run_id: optional correlation ids
    - data: arbitrary JSON-serializable payload
    """

    type: str
    ts_utc: str
    data: Dict[str, Any]
    task_id: Optional[str] = None
    run_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"type": self.type, "ts_utc": self.ts_utc, "data": self.data}
        if self.task_id:
            out["task_id"] = self.task_id
        if self.run_id:
            out["run_id"] = self.run_id
        return out


class SCCEventLogger:
    """
    Append-only JSONL writer with a small lock for cross-thread safety.
    """

    def __init__(self, *, path: Path):
        self.path = Path(path).resolve()
        _safe_mkdir(self.path.parent)
        self._lock = threading.Lock()

    def emit(
        self,
        event_type: str,
        *,
        data: Optional[Dict[str, Any]] = None,
        task_id: Optional[str] = None,
        run_id: Optional[str] = None,
        kind: SCCEventKind = "event",
        parent_id: Optional[str] = None,
        step_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        span_id: Optional[str] = None,
        parent_span_id: Optional[str] = None,
        ts_utc: Optional[str] = None,
        event_id: Optional[str] = None,
    ) -> None:
        name = str(event_type or "").strip() or "event"
        evt = SCCUnifiedEvent(
            event_id=str(event_id or "").strip() or new_event_id(),
            ts_utc=ts_utc or _utc_now_iso(),
            kind=kind,
            task_id=task_id,
            run_id=run_id,
            parent_id=parent_id,
            step_id=step_id,
            name=name,
            data=data or {},
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
        )
        # Backward compatible fields: keep existing consumers working.
        payload = evt.to_dict()
        payload.setdefault("type", name)
        line = json.dumps(payload, ensure_ascii=False)
        with self._lock:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")


def task_events_path(repo_root: Path, task_id: str) -> Path:
    return (Path(repo_root).resolve() / "artifacts" / "scc_tasks" / str(task_id) / "events.jsonl").resolve()


def run_events_path(repo_root: Path, run_id: str) -> Path:
    return (Path(repo_root).resolve() / "artifacts" / "scc_runs" / str(run_id) / "events.jsonl").resolve()


def get_task_logger(*, repo_root: Path, task_id: str) -> SCCEventLogger:
    return SCCEventLogger(path=task_events_path(repo_root, task_id))


def get_run_logger(*, repo_root: Path, run_id: str) -> SCCEventLogger:
    return SCCEventLogger(path=run_events_path(repo_root, run_id))


def _read_task_run_id(repo_root: Path, task_id: str) -> Optional[str]:
    """
    Best-effort: read artifacts/scc_tasks/<task_id>/task.json and extract run_id.
    """
    try:
        p = (Path(repo_root).resolve() / "artifacts" / "scc_tasks" / str(task_id) / "task.json").resolve()
        if not p.exists():
            return None
        data = json.loads(p.read_text(encoding="utf-8"))
        run_id = data.get("run_id")
        run_id = str(run_id).strip() if run_id is not None else ""
        return run_id or None
    except Exception:
        return None


def resolve_events_path_for_task(repo_root: Path, task_id: str) -> Dict[str, Any]:
    """
    Resolve which events.jsonl should back a task view.

    Precedence:
    1) artifacts/scc_tasks/<task_id>/events.jsonl (task-local stream)
    2) artifacts/scc_runs/<run_id>/events.jsonl (runner stream, via task.json run_id)

    Returns a small dict for API/UI:
      - path: str
      - source: "task"|"run"
      - run_id: Optional[str]
    """
    repo_root = Path(repo_root).resolve()
    task_p = task_events_path(repo_root, task_id)
    if task_p.exists():
        return {"path": str(task_p), "source": "task", "run_id": None}

    run_id = _read_task_run_id(repo_root, task_id)
    if run_id:
        run_p = run_events_path(repo_root, run_id)
        return {"path": str(run_p), "source": "run", "run_id": run_id}

    return {"path": str(task_p), "source": "task", "run_id": None}
