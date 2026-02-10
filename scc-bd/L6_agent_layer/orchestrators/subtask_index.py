from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def subtask_index_path(repo_root: Path, parent_task_id: str) -> Path:
    return (Path(repo_root).resolve() / "artifacts" / "scc_tasks" / str(parent_task_id) / "subtasks.json").resolve()


@dataclass(frozen=True)
class SubtaskIndexEntry:
    child_task_id: str
    task_type: str
    created_utc: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SubtaskIndexStore:
    """
    Minimal per-parent subtask index for fast listing and deterministic collaboration.

    Stored at:
      artifacts/scc_tasks/<parent_task_id>/subtasks.json
    """

    def __init__(self, *, repo_root: Path, parent_task_id: str):
        self.repo_root = Path(repo_root).resolve()
        self.parent_task_id = str(parent_task_id)
        self.path = subtask_index_path(self.repo_root, self.parent_task_id)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def read(self) -> List[SubtaskIndexEntry]:
        try:
            if not self.path.exists():
                return []
            obj = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(obj, list):
                return []
            out: List[SubtaskIndexEntry] = []
            for it in obj:
                if not isinstance(it, dict):
                    continue
                cid = str(it.get("child_task_id") or "").strip()
                if not cid:
                    continue
                out.append(
                    SubtaskIndexEntry(
                        child_task_id=cid,
                        task_type=str(it.get("task_type") or "general"),
                        created_utc=str(it.get("created_utc") or ""),
                    )
                )
            return out
        except Exception:
            return []

    def add(self, *, child_task_id: str, task_type: str) -> None:
        child_task_id = str(child_task_id or "").strip()
        if not child_task_id:
            return
        with self._lock:
            items = self.read()
            if any(e.child_task_id == child_task_id for e in items):
                return
            items.append(SubtaskIndexEntry(child_task_id=child_task_id, task_type=str(task_type or "general"), created_utc=_utc_now_iso()))
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(json.dumps([e.to_dict() for e in items], ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.path)

