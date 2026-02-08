from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from tools.scc.orchestrators.state_store import OrchestratorStateStore
from tools.scc.orchestrators.todo_state import TodoStateStore


ReminderType = Literal["todo_empty", "todo_stale"]


@dataclass(frozen=True)
class Reminder:
    type: ReminderType
    priority: Literal["low", "medium", "high"]
    message: str
    data: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def compute_reminders(*, repo_root: Path, task_id: str) -> List[Reminder]:
    """
    Minimal reminder engine (no model):
    - todo_empty: if task has no todos

    This is intentionally conservative to avoid noisy reminders.
    """
    out: List[Reminder] = []
    store = TodoStateStore(repo_root=repo_root, task_id=task_id)
    state = store.read()

    if not state or not state.items:
        orch = OrchestratorStateStore(repo_root=repo_root, task_id=task_id).read()
        phase = orch.phase if orch else "unknown"
        out.append(
            Reminder(
                type="todo_empty",
                priority="medium",
                message="Todo list is empty. Use /scc/task/{task_id}/todos to set a constrained plan (max 20, single in_progress).",
                data={"phase": phase},
            )
        )
        return out

    return out

