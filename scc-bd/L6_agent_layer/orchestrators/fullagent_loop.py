from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from tools.scc.capabilities.permission_floor import evaluate_command
from tools.scc.event_log import get_task_logger
from tools.scc.executors.executor_client import ExecutorResult, run_executor_prompt
from tools.scc.orchestrators.execution_plan import PlannedStep, build_execution_plan, is_command_concurrency_safe
from tools.scc.orchestrators.profiles import OrchestratorProfile
from tools.scc.orchestrators.state_store import OrchestratorStateStore
from tools.scc.orchestrators.todo_state import TodoStateStore
from tools.scc.task_queue import SCCTaskQueue
from tools.scc.orchestrators.continuation_context import write_continuation_context
from tools.scc.capabilities.patch_pipeline import patch_gate_sync_from_patches_dir, preview_patch


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _task_root(repo_root: Path, task_id: str) -> Path:
    return (repo_root / "artifacts" / "scc_tasks" / str(task_id)).resolve()


def _ensure_task_evidence_dir(repo_root: Path, task_id: str) -> Path:
    d = _task_root(repo_root, task_id) / "evidence"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _sanitize_patch_name(name: str) -> str:
    n = str(name or "").strip()
    n = n.replace("\\", "_").replace("/", "_")
    n = n.replace("..", "_")
    if not n:
        n = "patch"
    if not n.endswith(".diff"):
        n += ".diff"
    return n[:120]


def _write_patches(
    *,
    repo_root: Path,
    task_id: str,
    patches: List[Dict[str, Any]],
    step_idx: int,
) -> List[str]:
    """
    Write patches to artifacts/scc_tasks/<task_id>/evidence/patches/*.diff
    Returns written file paths.
    """
    ev_dir = _ensure_task_evidence_dir(repo_root, task_id)
    out_dir = (ev_dir / "patches").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    written: List[str] = []
    for i, raw in enumerate(patches[:20], start=1):
        if not isinstance(raw, dict):
            continue
        name = _sanitize_patch_name(str(raw.get("name") or f"step_{step_idx:03d}_{i:02d}"))
        text = str(raw.get("patch_text") or raw.get("text") or "")
        if not text.strip():
            continue
        path = (out_dir / name).resolve()
        path.write_text(text, encoding="utf-8", errors="replace")
        written.append(str(path))
    return written


def _write_patch_index(
    *,
    repo_root: Path,
    task_id: str,
    repo_path_for_preview: Optional[str],
) -> None:
    """
    Build a lightweight patch index with stats and permission decisions.
    """
    ev_dir = _ensure_task_evidence_dir(repo_root, task_id)
    patches_dir = (ev_dir / "patches").resolve()
    if not patches_dir.exists():
        return
    items: List[Dict[str, Any]] = []
    for p in sorted(patches_dir.glob("*.diff"))[-200:]:
        patch_text = p.read_text(encoding="utf-8", errors="replace")
        if repo_path_for_preview:
            try:
                prev = preview_patch(repo_path=Path(repo_path_for_preview), patch_text=patch_text)
                items.append({"name": p.name, "path": str(p), "preview": prev.to_dict()})
            except Exception:
                items.append({"name": p.name, "path": str(p), "preview": None})
        else:
            items.append({"name": p.name, "path": str(p), "preview": None})

    idx = {"ok": True, "task_id": str(task_id), "updated_utc": _utc_now_iso(), "items": items}
    (patches_dir / "index.json").write_text(json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        patch_gate_sync_from_patches_dir(evidence_dir=ev_dir, task_id=str(task_id))
    except Exception:
        pass


@dataclass(frozen=True)
class FullAgentConfig:
    """
    fullagent loop config.

    Defaults are intentionally conservative:
    - shell is disabled unless explicitly enabled.
    - executor can be switched (codex/cursor/iflow/traeocrcli) but SCC orchestration must remain stable.
    """

    executor: str
    model: str
    max_steps: int
    allow_shell: bool
    executor_timeout_s: float
    dry_run_executor: bool
    create_exec_task: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _config_from_env(*, profile: OrchestratorProfile) -> FullAgentConfig:
    return FullAgentConfig(
        executor=(os.environ.get("SCC_FULLAGENT_EXECUTOR", "codex") or "codex").strip(),
        model=(os.environ.get("SCC_FULLAGENT_MODEL", os.environ.get("A2A_CODEX_MODEL", "gpt-5.2-codex")) or "").strip(),
        max_steps=int(os.environ.get("SCC_FULLAGENT_MAX_STEPS", str(profile.max_steps)) or profile.max_steps),
        allow_shell=(os.environ.get("SCC_FULLAGENT_ALLOW_SHELL", "false").strip().lower() == "true"),
        executor_timeout_s=float(os.environ.get("SCC_FULLAGENT_EXECUTOR_TIMEOUT_S", "900") or 900),
        dry_run_executor=(os.environ.get("SCC_EXECUTOR_DRY_RUN", "false").strip().lower() == "true"),
        create_exec_task=(os.environ.get("SCC_FULLAGENT_CREATE_EXEC_TASK", "true").strip().lower() != "false"),
    )


def _dry_executor_response(*, goal: str) -> ExecutorResult:
    payload = {
        "ok": True,
        "mode": "dry_run",
        "goal": goal,
        "actions": [
            {"type": "update_todos", "summary": "write minimal todos"},
            {"type": "create_subtasks", "summary": "spawn one explore subtask"},
            {"type": "propose", "summary": "propose safe no-op command"},
            {"type": "finish", "summary": "dry-run executor: no model calls"},
        ],
        "proposal": {
            "commands_hint": ["echo FULLAGENT_DRY_RUN_NOOP"],
            "test_cmds": [],
            "artifact_paths": [],
        },
        "todos": [
            {"content": "Review goal and constraints", "status": "pending", "activeForm": "Reviewing goal"},
            {"content": "Confirm repo_path and allowed scope", "status": "pending", "activeForm": "Confirming scope"},
        ],
        "subtasks": [
            {"task_type": "explore", "goal": "Explore repo structure (dry-run)", "commands_hint": [], "test_cmds": []}
        ],
        "patches": [
            {
                "name": "dry_step1.diff",
                "patch_text": "diff --git a/dummy_scc_fullagent_dry.txt b/dummy_scc_fullagent_dry.txt\n--- /dev/null\n+++ b/dummy_scc_fullagent_dry.txt\n@@ -0,0 +1 @@\n+FULLAGENT_DRY_PATCH\n",
            }
        ],
    }
    return ExecutorResult(success=True, exit_code=0, stdout=json.dumps(payload, ensure_ascii=False), stderr="", executor="dry")


def _build_execution_plan_for_commands(cmds: List[str]) -> Dict[str, Any]:
    steps: List[PlannedStep] = []
    for idx, cmd in enumerate(cmds, start=1):
        dec = evaluate_command(cmd=str(cmd or ""))
        steps.append(
            PlannedStep(
                idx=idx,
                kind="hint",
                cmd=str(cmd or ""),
                risk=dec.risk,
                concurrency_safe=is_command_concurrency_safe(str(cmd or "")),
            )
        )
    return build_execution_plan(steps=steps).to_dict()


def _extract_json(stdout: str) -> Dict[str, Any]:
    s = (stdout or "").strip()
    if not s:
        raise ValueError("executor_stdout_empty")
    try:
        return json.loads(s)
    except Exception as e:
        raise ValueError(f"executor_stdout_not_json: {e}")

def _normalize_model_action(parsed: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize multiple upstream-friendly schemas into a single internal action object.

    Accepted schemas:
    - {"action": {"type": "...", ...}, "proposal": {...}}
    - legacy: {"proposal": {...}, "stop": {"type":"done","summary":"..."}}  (treated as finish)
    """
    if isinstance(parsed.get("action"), dict):
        act = dict(parsed["action"])
        act_type = str(act.get("type") or "").strip().lower()
        if not act_type:
            raise ValueError("action.type_required")
        act["type"] = act_type
        return act
    stop = parsed.get("stop")
    if isinstance(stop, dict) and str(stop.get("type") or "").strip().lower() in ("done", "finish"):
        return {"type": "finish", "summary": str(stop.get("summary") or "")}
    if "proposal" in parsed:
        return {"type": "propose", "summary": ""}
    return {"type": "noop"}

def _normalize_model_actions(parsed: Dict[str, Any]) -> List[Dict[str, Any]]:
    if isinstance(parsed.get("actions"), list):
        out: List[Dict[str, Any]] = []
        for raw in parsed["actions"]:
            if not isinstance(raw, dict):
                continue
            act_type = str(raw.get("type") or "").strip().lower()
            if not act_type:
                continue
            out.append({"type": act_type, "summary": str(raw.get("summary") or "")})
        if out:
            return out
    return [_normalize_model_action(parsed)]


def _default_prompt_schema() -> str:
    return (
        "Return ONLY valid JSON (no markdown).\n"
        "Schema:\n"
        "{\n"
        '  "ok": true,\n'
        '  "actions": [\n'
        '    {"type":"propose|update_todos|create_subtasks|finish|noop","summary":"..."}\n'
        "  ],\n"
        '  "proposal": {\n'
        '    "commands_hint": ["..."],\n'
        '    "test_cmds": ["..."],\n'
        '    "artifact_paths": ["..."]\n'
        "  },\n"
        '  "todos": [\n'
        '    {"content":"...","status":"pending|in_progress|completed","activeForm":"..."}\n'
        "  ],\n"
        '  "subtasks": [\n'
        '    {"task_type":"explore|plan|code|general","goal":"...","commands_hint":[],"test_cmds":[]}\n'
        "  ]\n"
        '  ,"patches":[{"name":"...","patch_text":"..."}]\n'
        "}\n"
    )


def fullagent_orchestrate(
    *,
    repo_root: Path,
    task_queue: SCCTaskQueue,
    payload: Dict[str, Any],
    profile: OrchestratorProfile,
    task_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Minimal CC/Cursor-style fullagent loop (v0→v1):
    - multi-step loop (bounded by max_steps)
    - model calls gated by SCC_MODEL_ENABLED
    - never executes shell unless SCC_FULLAGENT_ALLOW_SHELL=true
    - can run in deterministic executor dry-run mode (SCC_EXECUTOR_DRY_RUN=true)

    This is the smallest, safest bridge from dry-run orchestration to real agent loops.
    """
    if profile.name != "fullagent":
        raise ValueError("profile_must_be_fullagent")
    if not profile.model_calls_allowed:
        raise RuntimeError("model_disabled: set SCC_MODEL_ENABLED=true to enable fullagent")

    if task_id:
        rec = task_queue.submit_with_task_id(task_id=task_id, payload=payload, autostart=False)
    else:
        rec = task_queue.submit(payload, autostart=False)

    task = payload.get("task") or {}
    goal = str(task.get("goal") or payload.get("goal") or "").strip()

    cfg = _config_from_env(profile=profile)
    evidence_dir = _ensure_task_evidence_dir(repo_root, rec.task_id)

    OrchestratorStateStore(repo_root=repo_root, task_id=rec.task_id).transition(
        phase="fullagent_loop_start",
        patch_data={"profile": profile.name, "now_utc": _utc_now_iso(), "config": cfg.to_dict()},
    )

    steps_dir = (evidence_dir / "fullagent_steps").resolve()
    steps_dir.mkdir(parents=True, exist_ok=True)

    history: List[Dict[str, Any]] = []
    final_summary = ""
    final_verdict = "UNKNOWN"
    final_proposal: Dict[str, Any] = {"commands_hint": [], "test_cmds": [], "artifact_paths": []}
    created_exec_task_id: Optional[str] = None

    for step_idx in range(1, max(1, int(cfg.max_steps or 1)) + 1):
        OrchestratorStateStore(repo_root=repo_root, task_id=rec.task_id).transition(
            phase="fullagent_step",
            patch_data={"step": step_idx, "now_utc": _utc_now_iso()},
        )
        get_task_logger(repo_root=repo_root, task_id=rec.task_id).emit(
            "fullagent_step_started",
            task_id=rec.task_id,
            data={"step": step_idx, "executor": cfg.executor, "model": cfg.model},
        )

        prompt = (
            "You are SCC fullagent.\n"
            + _default_prompt_schema()
            + "\nGoal: "
            + goal
            + "\n\nContext:\n"
            + json.dumps(
                {
                    "task_id": rec.task_id,
                    "profile": profile.name,
                    "step": step_idx,
                    "max_steps": cfg.max_steps,
                    "history_tail": history[-5:],
                    "constraints": {"allow_shell": cfg.allow_shell},
                },
                ensure_ascii=False,
            )
        )

        if cfg.dry_run_executor:
            exe = _dry_executor_response(goal=goal)
        else:
            exe = run_executor_prompt(
                executor=cfg.executor,
                prompt=prompt,
                model=cfg.model,
                timeout_s=cfg.executor_timeout_s,
                trace_id=f"scc-fullagent-{rec.task_id}-{step_idx}",
            )

        (steps_dir / f"step_{step_idx:03d}_executor_result.json").write_text(
            json.dumps(exe.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        parsed = _extract_json(exe.stdout)
        actions = _normalize_model_actions(parsed)
        proposal = parsed.get("proposal") if isinstance(parsed.get("proposal"), dict) else {}
        commands_hint = [str(x or "").strip() for x in (proposal.get("commands_hint") or []) if str(x or "").strip()]
        test_cmds = [str(x or "").strip() for x in (proposal.get("test_cmds") or []) if str(x or "").strip()]
        artifact_paths = [str(x or "").strip() for x in (proposal.get("artifact_paths") or []) if str(x or "").strip()]
        todos = parsed.get("todos") if isinstance(parsed.get("todos"), list) else None
        subtasks = parsed.get("subtasks") if isinstance(parsed.get("subtasks"), list) else None
        patches_raw = parsed.get("patches") if isinstance(parsed.get("patches"), list) else None

        plan = _build_execution_plan_for_commands(commands_hint + test_cmds)
        (steps_dir / f"step_{step_idx:03d}_execution_plan.json").write_text(
            json.dumps(plan, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        step_record = {
            "step": step_idx,
            "executor": exe.to_dict(),
            "actions": actions,
            "proposal": {"commands_hint": commands_hint, "test_cmds": test_cmds, "artifact_paths": artifact_paths},
            "plan": plan,
        }
        history.append(step_record)
        (steps_dir / f"step_{step_idx:03d}_parsed.json").write_text(
            json.dumps(step_record, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        get_task_logger(repo_root=repo_root, task_id=rec.task_id).emit(
            "fullagent_step_completed",
            task_id=rec.task_id,
            data={
                "step": step_idx,
                "actions": [a.get("type") for a in actions],
                "proposal_cmds": len(commands_hint) + len(test_cmds),
            },
        )

        if todos is not None:
            # Validate via TodoStateStore; if invalid, it will raise and get surfaced.
            TodoStateStore(repo_root=repo_root, task_id=rec.task_id).write(todos)  # type: ignore[arg-type]

        if subtasks:
            # Create structured subtasks (dry by default: do not autostart).
            from tools.scc.orchestrators.subtask_pool import submit_subtask

            for raw in subtasks[:5]:
                if not isinstance(raw, dict):
                    continue
                st_goal = str(raw.get("goal") or "").strip()
                st_type = str(raw.get("task_type") or "general").strip()
                if not st_goal:
                    continue
                st_payload = {
                    "task": {
                        "goal": st_goal,
                        "commands_hint": list(raw.get("commands_hint") or []),
                        "success_criteria": [],
                        "stop_condition": [],
                        "scope_allow": [],
                        "artifacts_expectation": [],
                    },
                    "workspace": payload.get("workspace") or payload,
                }
                submit_subtask(
                    queue=task_queue,
                    parent_task_id=rec.task_id,
                    payload=st_payload,
                    task_type=st_type,  # type: ignore[arg-type]
                    autostart=False,
                )

        patch_paths: List[str] = []
        if patches_raw:
            patch_paths = _write_patches(repo_root=repo_root, task_id=rec.task_id, patches=patches_raw, step_idx=step_idx)  # type: ignore[arg-type]
            if patch_paths:
                get_task_logger(repo_root=repo_root, task_id=rec.task_id).emit(
                    "fullagent_patches_written",
                    task_id=rec.task_id,
                    data={"step": step_idx, "count": len(patch_paths)},
                )
                # Update patch index after new patches are written.
                repo_path_for_preview = ""
                try:
                    w = payload.get("workspace") if isinstance(payload.get("workspace"), dict) else payload
                    if isinstance(w, dict):
                        repo_path_for_preview = str(w.get("repo_path") or "").strip()
                except Exception:
                    repo_path_for_preview = ""
                _write_patch_index(repo_root=repo_root, task_id=rec.task_id, repo_path_for_preview=repo_path_for_preview or None)

        if commands_hint or test_cmds or artifact_paths:
            final_proposal = {"commands_hint": commands_hint, "test_cmds": test_cmds, "artifact_paths": artifact_paths}
            OrchestratorStateStore(repo_root=repo_root, task_id=rec.task_id).transition(
                phase="fullagent_proposed",
                patch_data={"proposal": final_proposal, "step": step_idx},
            )

        # Optionally create an execution task record from the latest proposal (default: yes, but do not autostart unless allow_shell).
        if cfg.create_exec_task and (commands_hint or test_cmds or artifact_paths):
            derived = dict(payload)
            derived_task = dict(task)
            derived_workspace = dict(payload.get("workspace") or payload)
            derived_task["commands_hint"] = list(commands_hint)
            derived_workspace["test_cmds"] = list(test_cmds)
            derived_workspace["artifact_paths"] = list(artifact_paths)
            derived["task"] = derived_task
            derived["workspace"] = derived_workspace
            created_exec_task_id = f"{rec.task_id}__exec"
            task_queue.submit_with_task_id(task_id=created_exec_task_id, payload=derived, autostart=bool(cfg.allow_shell))
            OrchestratorStateStore(repo_root=repo_root, task_id=rec.task_id).transition(
                phase="fullagent_exec_task_created",
                patch_data={"exec_task_id": created_exec_task_id},
            )

        if any(a.get("type") == "finish" for a in actions):
            fin = next((a for a in actions if a.get("type") == "finish"), {})
            final_summary = str(fin.get("summary") or "") or "finished"
            break

        try:
            write_continuation_context(repo_root=repo_root, task_id=rec.task_id)
        except Exception:
            pass

    if not final_summary:
        final_summary = f"max_steps_reached ({cfg.max_steps})"

    # Optional: hand off to SCC runner (exec task) if explicitly allowed and we have a proposal.
    if cfg.allow_shell and created_exec_task_id:
        final_summary = "fullagent created exec task (autostart enabled)"

    out = {
        "ok": True,
        "task_id": rec.task_id,
        "profile": profile.name,
        "fullagent": {
            "config": cfg.to_dict(),
            "proposal": final_proposal,
            "verdict": final_verdict,
            "summary": final_summary,
            "history_steps": len(history),
            "exec_task_id": created_exec_task_id,
        },
        "evidence_dir": str(evidence_dir),
    }

    (evidence_dir / "fullagent_summary.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return out
