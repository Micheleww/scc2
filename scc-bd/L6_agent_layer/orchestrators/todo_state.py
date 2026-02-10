from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional


TodoStatus = Literal["pending", "in_progress", "completed"]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class TodoItem:
    content: str
    status: TodoStatus
    activeForm: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TodoState:
    updated_utc: str
    items: List[TodoItem]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "updated_utc": self.updated_utc,
            "items": [it.to_dict() for it in self.items],
        }


def validate_todos(items: List[Dict[str, Any]], *, max_items: int = 20) -> List[TodoItem]:
    if not isinstance(items, list):
        raise ValueError("todos.items must be a list")
    if len(items) > max_items:
        raise ValueError(f"Max {max_items} todos allowed")

    validated: List[TodoItem] = []
    in_progress = 0
    for idx, raw in enumerate(items):
        if not isinstance(raw, dict):
            raise ValueError(f"Item {idx}: must be object")
        content = str(raw.get("content") or "").strip()
        status = str(raw.get("status") or "pending").strip().lower()
        active = str(raw.get("activeForm") or "").strip()
        if not content:
            raise ValueError(f"Item {idx}: content required")
        if status not in ("pending", "in_progress", "completed"):
            raise ValueError(f"Item {idx}: invalid status '{status}'")
        if not active:
            raise ValueError(f"Item {idx}: activeForm required")
        if status == "in_progress":
            in_progress += 1
        validated.append(TodoItem(content=content, status=status, activeForm=active))
    if in_progress > 1:
        raise ValueError("Only one task can be in_progress at a time")
    return validated


def todo_state_path(repo_root: Path, task_id: str) -> Path:
    return (Path(repo_root).resolve() / "artifacts" / "scc_tasks" / str(task_id) / "todo_state.json").resolve()


class TodoStateStore:
    """
    Per-task todo state with Kode/learn-claude-code constraints:
    - max 20
    - only one in_progress
    - requires activeForm
    """

    def __init__(self, *, repo_root: Path, task_id: str):
        self.repo_root = Path(repo_root).resolve()
        self.task_id = str(task_id)
        self.path = todo_state_path(self.repo_root, self.task_id)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def read(self) -> Optional[TodoState]:
        if not self.path.exists():
            return None
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return None
            items_raw = data.get("items")
            items: List[TodoItem] = []
            if isinstance(items_raw, list):
                for r in items_raw:
                    if isinstance(r, dict):
                        items.append(
                            TodoItem(
                                content=str(r.get("content") or ""),
                                status=str(r.get("status") or "pending"),
                                activeForm=str(r.get("activeForm") or ""),
                            )
                        )
            return TodoState(updated_utc=str(data.get("updated_utc") or ""), items=items)
        except Exception:
            return None

    def write(self, items: List[Dict[str, Any]]) -> TodoState:
        validated = validate_todos(items)
        state = TodoState(updated_utc=_utc_now_iso(), items=validated)
        with self._lock:
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(json.dumps(state.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.path)
        return state

