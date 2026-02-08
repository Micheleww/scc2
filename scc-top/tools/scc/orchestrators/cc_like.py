from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from tools.scc.event_log import get_task_logger
from tools.scc.orchestrators.execution_plan import PlannedStep, build_execution_plan, is_command_concurrency_safe
from tools.scc.orchestrators.interface import Observation, OrchestratorAction, OrchestratorContext, OrchestratorOutcome, OrchestratorState, PlanGraph
from tools.scc.orchestrators.profiles import OrchestratorProfile
from tools.scc.orchestrators.state_store import OrchestratorStateStore
from tools.scc.orchestrators.todo_state import TodoStateStore
from tools.scc.task_queue import SCCTaskQueue


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class DryOrchestrateResult:
    task_id: str
    profile: str
    plan_graph: Dict[str, Any]
    execution_plan: Dict[str, Any]
    todo_state: Dict[str, Any]
    evidence_dir: str


def _task_root(repo_root: Path, task_id: str) -> Path:
    return (repo_root / "artifacts" / "scc_tasks" / str(task_id)).resolve()


def _ensure_task_evidence_dir(repo_root: Path, task_id: str) -> Path:
    d = _task_root(repo_root, task_id) / "evidence"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _extract_all_cmds(req: Dict[str, Any]) -> List[Dict[str, Any]]:
    task = req.get("task") or {}
    workspace = req.get("workspace") or req
    out: List[Dict[str, Any]] = []
    for c in list(workspace.get("bootstrap_cmds") or []):
        out.append({"kind": "bootstrap", "cmd": str(c or "")})
    for c in list(task.get("commands_hint") or req.get("commands_hint") or []):
        out.append({"kind": "hint", "cmd": str(c or "")})
    for c in list(workspace.get("test_cmds") or req.get("test_cmds") or []):
        out.append({"kind": "test", "cmd": str(c or "")})
    return out


def _build_plan_graph(*, req: Dict[str, Any], profile: OrchestratorProfile) -> PlanGraph:
    cmds = _extract_all_cmds(req)
    nodes = ["goal", "workspace", "plan"]
    edges: List[List[str]] = [["goal", "workspace"], ["workspace", "plan"]]
    for i, c in enumerate(cmds, start=1):
        nid = f"cmd_{i:03d}"
        nodes.append(nid)
        edges.append(["plan", nid])
    return PlanGraph(
        nodes=nodes,
        edges=edges,
        meta={"profile": profile.name, "cmd_count": len(cmds)},
    )


def _build_execution_plan_dict(*, req: Dict[str, Any]) -> Dict[str, Any]:
    cmds = _extract_all_cmds(req)
    steps: List[PlannedStep] = []
    for idx, c in enumerate(cmds, start=1):
        cmd = str(c.get("cmd") or "")
        steps.append(
            PlannedStep(
                idx=idx,
                kind=str(c.get("kind") or "hint"),
                cmd=cmd,
                risk="unknown",
                concurrency_safe=is_command_concurrency_safe(cmd),
            )
        )
    return build_execution_plan(steps=steps).to_dict()


def _default_todos(*, req: Dict[str, Any], profile: OrchestratorProfile) -> List[Dict[str, Any]]:
    task = req.get("task") or {}
    goal = str(task.get("goal") or req.get("goal") or "").strip()
    todos: List[Dict[str, Any]] = []
    if goal:
        todos.append(
            {
                "content": f"[{profile.name}] Clarify goal: {goal}",
                "status": "pending",
                "activeForm": "Clarifying goal",
            }
        )
    cmds = _extract_all_cmds(req)
    if cmds:
        todos.append(
            {
                "content": f"Review commands_hint/test_cmds ({len(cmds)} steps)",
                "status": "pending",
                "activeForm": "Reviewing commands",
            }
        )
    success = list(task.get("success_criteria") or [])
    if success:
        todos.append(
            {
                "content": f"Confirm success criteria ({len(success)})",
                "status": "pending",
                "activeForm": "Confirming success criteria",
            }
        )
    stop = list(task.get("stop_condition") or [])
    if stop:
        todos.append(
            {
                "content": f"Confirm stop conditions ({len(stop)})",
                "status": "pending",
                "activeForm": "Confirming stop conditions",
            }
        )
    if not todos:
        todos.append(
            {
                "content": "No todos (empty task contract)",
                "status": "pending",
                "activeForm": "Reviewing task contract",
            }
        )
    return todos[:20]


def orchestrate_dry_run(
    *,
    repo_root: Path,
    task_queue: SCCTaskQueue,
    payload: Dict[str, Any],
    profile: OrchestratorProfile,
    task_id: Optional[str] = None,
) -> DryOrchestrateResult:
    """
    Deterministic orchestration scaffold inspired by Claude Code / Kode patterns.

    - No model calls.
    - No shell execution.
    - Produces inspectable artifacts under artifacts/scc_tasks/<task_id>/.
    """
    if profile.name == "fullagent" and not profile.model_calls_allowed:
        raise RuntimeError("model_disabled: set SCC_MODEL_ENABLED=true to allow fullagent mode")

    if task_id:
        rec = task_queue.submit_with_task_id(task_id=task_id, payload=payload, autostart=False)
    else:
        rec = task_queue.submit(payload, autostart=False)

    evidence_dir = _ensure_task_evidence_dir(repo_root, rec.task_id)

    plan_graph = _build_plan_graph(req=payload, profile=profile)
    execution_plan = _build_execution_plan_dict(req=payload)
    todos = _default_todos(req=payload, profile=profile)

    OrchestratorStateStore(repo_root=repo_root, task_id=rec.task_id).transition(
        phase="orchestrate_dry",
        patch_data={"profile": profile.name, "now_utc": _utc_now_iso()},
    )

    TodoStateStore(repo_root=repo_root, task_id=rec.task_id).write(todos)

    (evidence_dir / "orchestrator_plan_graph.json").write_text(
        json.dumps(plan_graph.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (evidence_dir / "tool_execution_plan.json").write_text(
        json.dumps(execution_plan, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    get_task_logger(repo_root=repo_root, task_id=rec.task_id).emit(
        "orchestrate_dry_completed",
        task_id=rec.task_id,
        data={"profile": profile.name, "evidence_dir": str(evidence_dir)},
    )

    return DryOrchestrateResult(
        task_id=rec.task_id,
        profile=profile.name,
        plan_graph=plan_graph.to_dict(),
        execution_plan=execution_plan,
        todo_state={"items": todos},
        evidence_dir=str(evidence_dir),
    )
