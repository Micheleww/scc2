from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from uuid import uuid4
from typing import Any, Dict, List, Literal, Optional

from tools.scc.task_queue import SCCTaskQueue, TaskRecord
from tools.scc.orchestrators.subtask_index import SubtaskIndexStore


TaskType = Literal["explore", "plan", "code", "general"]


def _utc_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


@dataclass(frozen=True)
class SubtaskMeta:
    parent_task_id: str
    task_type: TaskType
    created_utc: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def with_subtask_meta(payload: Dict[str, Any], *, parent_task_id: str, task_type: TaskType) -> Dict[str, Any]:
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    meta = dict(meta)
    meta.update(
        {
            "parent_task_id": str(parent_task_id),
            "task_type": str(task_type),
            "created_utc": datetime.now(timezone.utc).isoformat(),
        }
    )
    out = dict(payload)
    out["meta"] = meta
    return out


def submit_subtask(
    *,
    queue: SCCTaskQueue,
    parent_task_id: str,
    task_type: TaskType,
    payload: Dict[str, Any],
    task_id: Optional[str] = None,
    autostart: Optional[bool] = None,
) -> TaskRecord:
    """
    Create a child SCC task linked to a parent task.

    This is a structural feature for orchestration and collaboration.
    Execution may still be serial depending on SCC worker settings.
    """
    child_payload = with_subtask_meta(payload, parent_task_id=parent_task_id, task_type=task_type)
    if task_id:
        rec = queue.submit_with_task_id(task_id=str(task_id), payload=child_payload, autostart=autostart)
        SubtaskIndexStore(repo_root=queue.repo_root, parent_task_id=parent_task_id).add(
            child_task_id=rec.task_id, task_type=task_type
        )
        return rec
    # Stable-ish id prefix for easier debugging
    derived_id = f"{_utc_slug()}-{task_type}-{parent_task_id[:8]}-{uuid4().hex[:6]}"
    rec = queue.submit_with_task_id(task_id=derived_id, payload=child_payload, autostart=autostart)
    SubtaskIndexStore(repo_root=queue.repo_root, parent_task_id=parent_task_id).add(
        child_task_id=rec.task_id, task_type=task_type
    )
    return rec


def list_subtasks(*, queue: SCCTaskQueue, parent_task_id: str, limit: int = 200) -> List[TaskRecord]:
    parent_task_id = str(parent_task_id)
    lim = max(1, int(limit or 200))

    # Prefer index (deterministic + fast)
    idx = SubtaskIndexStore(repo_root=queue.repo_root, parent_task_id=parent_task_id).read()
    if idx:
        out: List[TaskRecord] = []
        for e in idx[-lim:]:
            try:
                out.append(queue.get(e.child_task_id))
            except Exception:
                continue
        return out

    # Fallback scan for older tasks without index
    out2: List[TaskRecord] = []
    for rec in queue.list(limit=lim):
        req = rec.request if isinstance(rec.request, dict) else {}
        meta = req.get("meta") if isinstance(req.get("meta"), dict) else {}
        if str(meta.get("parent_task_id") or "") == parent_task_id:
            out2.append(rec)
    return out2
