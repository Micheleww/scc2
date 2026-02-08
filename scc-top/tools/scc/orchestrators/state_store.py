from __future__ import annotations

import json
import threading
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from tools.scc.orchestrators.interface import OrchestratorState


def orchestrator_state_path(repo_root: Path, task_id: str) -> Path:
    return (Path(repo_root).resolve() / "artifacts" / "scc_tasks" / str(task_id) / "orchestrator_state.json").resolve()

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def task_root_path(repo_root: Path, task_id: str) -> Path:
    return (Path(repo_root).resolve() / "artifacts" / "scc_tasks" / str(task_id)).resolve()


def task_evidence_dir(repo_root: Path, task_id: str) -> Path:
    d = (task_root_path(repo_root, task_id) / "evidence").resolve()
    d.mkdir(parents=True, exist_ok=True)
    return d


class OrchestratorStateStore:
    """
    Minimal, deterministic state store for orchestrator state snapshots.

    Stored per task to keep replay localized:
    artifacts/scc_tasks/<task_id>/orchestrator_state.json
    """

    def __init__(self, *, repo_root: Path, task_id: str):
        self.repo_root = Path(repo_root).resolve()
        self.task_id = str(task_id)
        self.path = orchestrator_state_path(self.repo_root, self.task_id)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def exists(self) -> bool:
        return self.path.exists()

    def read(self) -> Optional[OrchestratorState]:
        if not self.path.exists():
            return None
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return None
            return OrchestratorState(
                step=int(data.get("step") or 0),
                phase=str(data.get("phase") or ""),
                data=data.get("data") if isinstance(data.get("data"), dict) else {},
            )
        except Exception:
            return None

    def write(self, state: OrchestratorState) -> None:
        with self._lock:
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(json.dumps(asdict(state), ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.path)

    def init_if_missing(self, *, phase: str, data: Optional[Dict[str, Any]] = None) -> OrchestratorState:
        existing = self.read()
        if existing:
            return existing
        state = OrchestratorState(step=0, phase=str(phase or "").strip() or "init", data=data or {})
        self.write(state)
        return state

    def transition(self, *, phase: str, patch_data: Optional[Dict[str, Any]] = None) -> OrchestratorState:
        with self._lock:
            cur = self.read() or OrchestratorState(step=0, phase="init", data={})
            merged: Dict[str, Any] = dict(cur.data or {})
            if patch_data:
                merged.update(patch_data)
            nxt = OrchestratorState(step=int(cur.step) + 1, phase=str(phase or "").strip() or cur.phase, data=merged)
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(json.dumps(asdict(nxt), ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.path)
            return nxt

    def append_history(
        self,
        *,
        key: str,
        item: Dict[str, Any],
        max_items: int = 200,
    ) -> OrchestratorState:
        """
        Append an item into a list in state.data[key], keeping at most max_items.

        This is useful for mode switches / orchestration events while keeping state JSON compact.
        """
        with self._lock:
            cur = self.read() or OrchestratorState(step=0, phase="init", data={})
            merged: Dict[str, Any] = dict(cur.data or {})
            hist = merged.get(key)
            arr = list(hist) if isinstance(hist, list) else []
            entry = dict(item or {})
            entry.setdefault("ts_utc", _utc_now_iso())
            arr.append(entry)
            if max_items and len(arr) > int(max_items):
                arr = arr[-int(max_items) :]
            merged[key] = arr
            nxt = OrchestratorState(step=int(cur.step) + 1, phase=str(cur.phase or "init"), data=merged)
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(json.dumps(asdict(nxt), ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.path)
            return nxt
