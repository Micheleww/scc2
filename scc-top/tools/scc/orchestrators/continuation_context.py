from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from tools.scc.orchestrators.subtask_index import SubtaskIndexStore


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        if not path.exists():
            return None
        obj = json.loads(path.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _tail_lines(path: Path, limit: int = 80) -> List[str]:
    try:
        if not path.exists():
            return []
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        lim = max(1, min(2000, int(limit or 80)))
        return lines[-lim:]
    except Exception:
        return []


@dataclass(frozen=True)
class ContinuationContext:
    task_id: str
    updated_utc: str
    status: str
    goal: str
    repo_path: str
    run_id: Optional[str]
    verdict: Optional[str]
    artifacts: Dict[str, Any]
    orchestrator_state: Dict[str, Any]
    todo_state: Dict[str, Any]
    subtasks: List[Dict[str, Any]]
    recent_events: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def write_continuation_context(*, repo_root: Path, task_id: str, event_tail: int = 80) -> Optional[ContinuationContext]:
    """
    Deterministic "auto-compact" substitute for SCC:
    - no model calls
    - writes a compact continuation snapshot per task for collaboration
    """
    repo_root = Path(repo_root).resolve()
    task_id = str(task_id)
    task_dir = (repo_root / "artifacts" / "scc_tasks" / task_id).resolve()
    task_json = task_dir / "task.json"
    orch_json = task_dir / "orchestrator_state.json"
    todo_json = task_dir / "todo_state.json"
    events_jsonl = task_dir / "events.jsonl"

    task = _read_json(task_json) or {}
    orch = _read_json(orch_json) or {}
    todo = _read_json(todo_json) or {"items": []}
    recent = _tail_lines(events_jsonl, limit=event_tail)

    status = str(task.get("status") or "").strip() or "unknown"
    request = task.get("request") if isinstance(task.get("request"), dict) else {}
    task_goal = ""
    if isinstance(request, dict):
        t = request.get("task") if isinstance(request.get("task"), dict) else {}
        task_goal = str(t.get("goal") or request.get("goal") or "").strip()
    repo_path = ""
    if isinstance(request, dict):
        w = request.get("workspace") if isinstance(request.get("workspace"), dict) else request
        if isinstance(w, dict):
            repo_path = str(w.get("repo_path") or "").strip()

    run_id = str(task.get("run_id") or "").strip() or None
    verdict = str(task.get("verdict") or "").strip() or None

    artifacts: Dict[str, Any] = {
        "task_dir": str(task_dir),
        "events_jsonl": str(events_jsonl),
        "orchestrator_state_json": str(orch_json),
        "todo_state_json": str(todo_json),
    }
    for k in ["out_dir", "selftest_log", "report_md", "evidence_dir"]:
        v = task.get(k)
        if isinstance(v, str) and v.strip():
            artifacts[k] = v

    # Subtasks (scan local tasks dir; keep small)
    subtasks: List[Dict[str, Any]] = []
    try:
        idx = SubtaskIndexStore(repo_root=repo_root, parent_task_id=task_id).read()
        if idx:
            tasks_root = (repo_root / "artifacts" / "scc_tasks").resolve()
            for e in idx[-20:]:
                tj = (tasks_root / e.child_task_id / "task.json").resolve()
                t = _read_json(tj) or {}
                subtasks.append(
                    {
                        "task_id": str(t.get("task_id") or e.child_task_id),
                        "status": str(t.get("status") or ""),
                        "task_type": str(e.task_type or "general"),
                        "run_id": t.get("run_id"),
                        "verdict": t.get("verdict"),
                    }
                )
        else:
            tasks_root = (repo_root / "artifacts" / "scc_tasks").resolve()
            for d in sorted(tasks_root.glob("*")):
                if not d.is_dir():
                    continue
                tj = d / "task.json"
                t = _read_json(tj) or {}
                req = t.get("request") if isinstance(t.get("request"), dict) else {}
                meta = req.get("meta") if isinstance(req.get("meta"), dict) else {}
                if str(meta.get("parent_task_id") or "") != task_id:
                    continue
                subtasks.append(
                    {
                        "task_id": str(t.get("task_id") or d.name),
                        "status": str(t.get("status") or ""),
                        "task_type": str(meta.get("task_type") or "general"),
                        "run_id": t.get("run_id"),
                        "verdict": t.get("verdict"),
                    }
                )
                if len(subtasks) >= 20:
                    break
    except Exception:
        subtasks = []

    ctx = ContinuationContext(
        task_id=task_id,
        updated_utc=_utc_now_iso(),
        status=status,
        goal=task_goal,
        repo_path=repo_path,
        run_id=run_id,
        verdict=verdict,
        artifacts=artifacts,
        orchestrator_state=orch,
        todo_state=todo,
        subtasks=subtasks,
        recent_events=recent,
    )

    # Write machine + human
    (task_dir / "continuation.json").write_text(json.dumps(ctx.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    md_path = task_dir / "continuation.md"
    lines: List[str] = []
    lines.append("# SCC Continuation Context\n")
    lines.append(f"- task_id: `{task_id}`")
    lines.append(f"- updated_utc: `{ctx.updated_utc}`")
    lines.append(f"- status: `{status}`")
    if verdict:
        lines.append(f"- verdict: `{verdict}`")
    if run_id:
        lines.append(f"- run_id: `{run_id}`")
    if repo_path:
        lines.append(f"- repo_path: `{repo_path}`")
    if task_goal:
        lines.append(f"\n## Goal\n{task_goal}\n")

    lines.append("\n## Orchestrator State\n")
    lines.append("```json")
    lines.append(json.dumps(orch, ensure_ascii=False, indent=2))
    lines.append("```\n")

    lines.append("## Todos\n")
    lines.append("```json")
    lines.append(json.dumps(todo, ensure_ascii=False, indent=2))
    lines.append("```\n")

    lines.append("## Artifacts\n")
    for k, v in artifacts.items():
        lines.append(f"- {k}: `{v}`")

    if subtasks:
        lines.append("\n## Subtasks\n")
        for st in subtasks:
            lines.append(f"- `{st.get('task_id')}` status={st.get('status')} type={st.get('task_type')}")

    lines.append("\n## Recent Events (tail)\n")
    lines.append("```jsonl")
    lines.extend(recent if recent else ["(no events)"])
    lines.append("```\n")
    md_path.write_text("\n".join(lines), encoding="utf-8")

    return ctx
