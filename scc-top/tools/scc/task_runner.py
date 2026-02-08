from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from uuid import uuid4

from tools.scc.event_log import get_run_logger
from tools.scc.capabilities.permission_floor import command_floor_enforce_enabled, evaluate_command, evaluate_write_path
from tools.scc.orchestrators.execution_plan import PlannedStep, build_execution_plan, is_command_concurrency_safe
from tools.scc.orchestrators.state_store import OrchestratorStateStore, task_evidence_dir

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_mkdir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _normalize_relpath(path: Path, base: Path) -> str:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except Exception:
        return str(path)


def _is_under_any_root(path: Path, roots: Sequence[Path]) -> bool:
    try:
        resolved = path.resolve()
    except Exception:
        return False
    for r in roots:
        try:
            rr = r.resolve()
            resolved.relative_to(rr)
            return True
        except Exception:
            continue
    return False


def _default_allowed_roots(repo_root: Path) -> List[Path]:
    raw = (os.environ.get("SCC_ALLOWED_REPO_ROOTS") or "").strip()
    if not raw:
        return [repo_root]
    roots: List[Path] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        roots.append(Path(part))
    return roots or [repo_root]


def _get_env_bool(name: str, default: bool) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


def _classify_fail_class(*, ok: bool, exit_code: int, steps: Sequence[Dict[str, Any]]) -> Optional[str]:
    if ok:
        return None
    for s in steps:
        if int(s.get("exit_code") or 0) == 97:
            return "command_denied"
    if int(exit_code) in {124, 137, 143}:
        return "timeout"
    return "command_failed"


def _classify_task_difficulty(*, task: "TaskContract", workspace: "WorkspaceAdapter") -> str:
    """
    Heuristic difficulty classifier (low/medium/high).

    - If `task.difficulty` is provided, it wins.
    - Otherwise we score by: command count, test count, scope size, expected artifacts, and keywords.
    """
    forced = str(getattr(task, "difficulty", "") or "").strip().lower()
    if forced in {"low", "medium", "high"}:
        return forced

    score = 0
    cmd_n = len([c for c in (task.commands_hint or []) if str(c).strip()])
    test_n = len([c for c in (workspace.test_cmds or []) if str(c).strip()])
    scope_n = len([s for s in (task.scope_allow or []) if str(s).strip()])
    art_n = len([a for a in (task.artifacts_expectation or []) if str(a).strip()])

    score += min(4, cmd_n)
    score += min(3, test_n)
    score += 1 if scope_n >= 4 else 0
    score += 1 if art_n >= 3 else 0

    g = (task.goal or "").lower()
    kw_high = ["refactor", "architecture", "migrate", "integrate", "rewrite", "pipeline", "orchestr", "deploy"]
    kw_med = ["debug", "fix", "stabil", "improve", "optimi", "test", "build", "ci"]
    if any(k in g for k in kw_high):
        score += 3
    elif any(k in g for k in kw_med):
        score += 2

    if score >= 7:
        return "high"
    if score >= 3:
        return "medium"
    return "low"


def _maybe_generate_codex_plan(
    *,
    repo_root: Path,
    workspace_path: Path,
    task: "TaskContract",
    workspace: "WorkspaceAdapter",
    evidence_dir: Path,
    run_events: Any,
    run_id: str,
    timeout_s: float,
) -> Optional[Path]:
    """
    For medium/high tasks, generate a Codex plan artifact (read-only) and save it under evidence/.

    This is "plan mode routing" on the backend: we don't depend on UI/IDE to request a plan explicitly.
    """
    mode = (os.environ.get("SCC_CODEX_PLAN_MODE") or "auto").strip().lower()
    if mode in {"0", "off", "false", "disabled"}:
        return None

    difficulty = _classify_task_difficulty(task=task, workspace=workspace)
    if mode == "auto" and difficulty == "low":
        return None

    exe = (os.environ.get("CODEX_CLI_EXE") or "codex").strip() or "codex"
    if not shutil.which(exe):
        candidates: List[str] = []
        fallback = (os.environ.get("CODEX_CLI_FALLBACK") or "").strip()
        if fallback:
            candidates.append(fallback)
        appdata = (os.environ.get("APPDATA") or "").strip()
        if appdata:
            candidates.append(str(Path(appdata) / "npm" / "codex.cmd"))
        # Back-compat: older deployments used a user-specific path; avoid hardcoding it here.
        for c in candidates:
            if c and Path(c).exists():
                exe = c
                break

    schema_path = (repo_root / "tools" / "scc" / "schemas" / "codex_plan.schema.json").resolve()
    if not schema_path.exists():
        return None

    model = (os.environ.get("SCC_CODEX_PLAN_MODEL") or os.environ.get("A2A_CODEX_MODEL") or "gpt-5.2").strip() or "gpt-5.2"
    prompt = (
        "You are SCC in PLAN mode.\n"
        "Goal: produce a step-by-step plan ONLY. Do not execute commands. Do not modify files.\n"
        "Output MUST be valid JSON matching the provided output schema.\n\n"
        f"Task goal:\n{task.goal}\n\n"
        f"Scope allow:\n{json.dumps(task.scope_allow or [], ensure_ascii=False)}\n\n"
        f"Success criteria:\n{json.dumps(task.success_criteria or [], ensure_ascii=False)}\n\n"
        f"Stop condition:\n{json.dumps(task.stop_condition or [], ensure_ascii=False)}\n\n"
        f"Commands hint:\n{json.dumps(task.commands_hint or [], ensure_ascii=False)}\n\n"
        f"Artifacts expectation:\n{json.dumps(task.artifacts_expectation or [], ensure_ascii=False)}\n"
    )

    out_json = evidence_dir / "codex_plan.json"
    out_raw = evidence_dir / "codex_plan.raw.txt"
    meta_path = evidence_dir / "codex_plan.meta.json"

    run_events.emit(
        "codex_plan_started",
        run_id=run_id,
        data={"difficulty": difficulty, "model": model, "schema": str(schema_path)},
    )

    args = [
        exe,
        "exec",
        "--full-auto",
        "-C",
        str(workspace_path),
        "-m",
        model,
        "--sandbox",
        "read-only",
        "--output-schema",
        str(schema_path),
        "-",
    ]

    start = time.time()
    try:
        p = subprocess.run(
            args,
            cwd=str(workspace_path),
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s if timeout_s > 0 else 900,
        )
        dur = max(0.0, time.time() - start)
        stdout = p.stdout or ""
        stderr = p.stderr or ""
        out_raw.write_text(stdout + ("\n\n== STDERR ==\n" + stderr if stderr else ""), encoding="utf-8", errors="replace")
        meta_path.write_text(
            json.dumps(
                {
                    "ok": p.returncode == 0,
                    "exit_code": int(p.returncode),
                    "duration_s": dur,
                    "difficulty": difficulty,
                    "model": model,
                    "args": args,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        plan_obj: Optional[Dict[str, Any]] = None
        try:
            plan_obj = json.loads(stdout)
        except Exception:
            plan_obj = None

        if isinstance(plan_obj, dict):
            out_json.write_text(json.dumps(plan_obj, ensure_ascii=False, indent=2), encoding="utf-8")
            run_events.emit(
                "codex_plan_saved",
                run_id=run_id,
                data={"ok": True, "path": str(out_json), "duration_s": dur, "exit_code": int(p.returncode)},
            )
            return out_json

        run_events.emit(
            "codex_plan_saved",
            run_id=run_id,
            data={"ok": False, "path": str(out_raw), "duration_s": dur, "exit_code": int(p.returncode), "reason": "non_json_stdout"},
        )
        return out_raw
    except Exception as e:
        out_raw.write_text(f"codex_plan_error: {e}", encoding="utf-8", errors="replace")
        try:
            meta_path.write_text(
                json.dumps(
                    {
                        "ok": False,
                        "error": str(e),
                        "difficulty": difficulty,
                        "model": model,
                        "args": args,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception:
            pass
        run_events.emit(
            "codex_plan_failed",
            run_id=run_id,
            data={"error": str(e)},
        )
        return out_raw


def resolve_orchestrator_mode(payload: Dict[str, Any]) -> str:
    """
    Extract orchestration mode from a task payload.

    - preferred: payload.orchestrator.mode / payload.orchestrator.profile
    - fallback: payload.profile
    - empty => "execute" (normal SCC runner)
    """
    orch = payload.get("orchestrator") if isinstance(payload.get("orchestrator"), dict) else {}
    raw = str(orch.get("mode") or orch.get("profile") or payload.get("profile") or "").strip().lower()
    if raw in {"plan", "chat", "fullagent", "auto"}:
        return raw
    return "execute"


def _payload_to_request(payload: Dict[str, Any]) -> SCCTaskRequest:
    task = payload.get("task") if isinstance(payload.get("task"), dict) else {}
    workspace = payload.get("workspace") if isinstance(payload.get("workspace"), dict) else payload

    goal = str(task.get("goal") or payload.get("goal") or "").strip() or "Run commands (no goal provided)"
    return SCCTaskRequest(
        task=TaskContract(
            goal=goal,
            scope_allow=list(task.get("scope_allow") or []),
            success_criteria=list(task.get("success_criteria") or []),
            stop_condition=list(task.get("stop_condition") or []),
            commands_hint=list(task.get("commands_hint") or payload.get("commands_hint") or []),
            artifacts_expectation=list(task.get("artifacts_expectation") or []),
            difficulty=str(task.get("difficulty") or payload.get("difficulty") or "").strip(),
        ),
        workspace=WorkspaceAdapter(
            repo_path=str(workspace.get("repo_path") or ""),
            bootstrap_cmds=list(workspace.get("bootstrap_cmds") or []),
            test_cmds=list(workspace.get("test_cmds") or payload.get("test_cmds") or []),
            artifact_paths=list(workspace.get("artifact_paths") or []),
        ),
        timeout_s=float(payload.get("timeout_s") or 0.0),
    )


def _fallback_codex_plan_obj(*, request: SCCTaskRequest) -> Dict[str, Any]:
    difficulty = _classify_task_difficulty(task=request.task, workspace=request.workspace)
    goal = request.task.goal.strip()
    cmds = [c for c in (request.task.commands_hint or []) if str(c).strip()]
    tests = [c for c in (request.workspace.test_cmds or []) if str(c).strip()]

    steps: List[Dict[str, Any]] = [
        {
            "id": "step_01",
            "title": "Understand scope and constraints",
            "intent": "Clarify requirements and boundaries before changing anything.",
            "commands_hint": [],
            "artifacts": [],
        },
        {
            "id": "step_02",
            "title": "Inspect relevant code paths",
            "intent": "Identify where to implement changes with minimal blast radius.",
            "commands_hint": [],
            "artifacts": [],
        },
    ]
    if cmds:
        steps.append(
            {
                "id": "step_03",
                "title": "Prepare execution commands",
                "intent": "Review command hints and decide safe ordering.",
                "commands_hint": [str(c) for c in cmds[:20]],
                "artifacts": [],
            }
        )
    if tests:
        steps.append(
            {
                "id": "step_04",
                "title": "Validate with tests",
                "intent": "Run the recommended tests to confirm behavior.",
                "commands_hint": [str(c) for c in tests[:20]],
                "artifacts": [],
            }
        )
    if len(steps) == 2:
        steps.append(
            {
                "id": "step_03",
                "title": "Implement and verify",
                "intent": "Make the minimal changes and verify locally.",
                "commands_hint": [],
                "artifacts": [],
            }
        )

    return {
        "summary": f"Plan for: {goal}",
        "difficulty": difficulty,
        "steps": steps,
        "risks": [
            "Running destructive commands without review.",
            "Changing files outside the allowed scope.",
        ],
        "acceptance": list(request.task.success_criteria or []) or ["Evidence artifacts are produced as expected."],
    }


def orchestrate_plan_or_chat(
    *,
    repo_root: Path,
    task_id: str,
    payload: Dict[str, Any],
    mode: str,
) -> Dict[str, Any]:
    """
    Deterministic plan/chat orchestration:
    - plan: always writes artifacts/scc_tasks/<task_id>/evidence/codex_plan.json
    - chat: persists chat context (messages) under evidence/
    """
    task_id = str(task_id)
    evidence_dir = task_evidence_dir(repo_root, task_id)
    req = _payload_to_request(payload)

    orch_store = OrchestratorStateStore(repo_root=repo_root, task_id=task_id)
    orch_store.append_history(key="mode_history", item={"mode": mode})
    orch_store.transition(
        phase="orchestrator_start",
        patch_data={
            "mode": mode,
            "now_utc": _utc_now_iso(),
            "difficulty": _classify_task_difficulty(task=req.task, workspace=req.workspace),
        },
    )

    if mode == "plan":
        plan_obj = _fallback_codex_plan_obj(request=req)
        plan_path = (evidence_dir / "codex_plan.json").resolve()
        plan_path.write_text(json.dumps(plan_obj, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            from tools.scc.evidence_index import build_task_evidence_index

            build_task_evidence_index(repo_root=repo_root, task_id=task_id)
        except Exception:
            pass
        orch_store.transition(
            phase="plan_ready",
            patch_data={"plan_path": str(plan_path)},
        )
        return {"ok": True, "task_id": task_id, "mode": "plan", "evidence_dir": str(evidence_dir), "plan_path": str(plan_path)}

    # chat mode: keep a compact, append-only message history
    ctx_path = (evidence_dir / "chat_context.json").resolve()
    prev: Dict[str, Any] = {}
    try:
        if ctx_path.exists():
            prev = json.loads(ctx_path.read_text(encoding="utf-8"))
            if not isinstance(prev, dict):
                prev = {}
    except Exception:
        prev = {}

    msgs = prev.get("messages") if isinstance(prev.get("messages"), list) else []
    incoming = payload.get("messages")
    if isinstance(incoming, list):
        for m in incoming[-50:]:
            if isinstance(m, dict):
                msgs.append({"ts_utc": _utc_now_iso(), **m})
            else:
                msgs.append({"ts_utc": _utc_now_iso(), "content": str(m)})
    else:
        # Minimal placeholder: record last goal update.
        msgs.append({"ts_utc": _utc_now_iso(), "role": "user", "content": req.task.goal})

    msgs = msgs[-200:]
    out_ctx = {"task_id": task_id, "updated_utc": _utc_now_iso(), "messages": msgs}
    ctx_path.write_text(json.dumps(out_ctx, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        from tools.scc.evidence_index import build_task_evidence_index

        build_task_evidence_index(repo_root=repo_root, task_id=task_id)
    except Exception:
        pass
    orch_store.transition(phase="chat_ready", patch_data={"chat_context_path": str(ctx_path), "message_count": len(msgs)})
    return {"ok": True, "task_id": task_id, "mode": "chat", "evidence_dir": str(evidence_dir), "chat_context_path": str(ctx_path)}


def postprocess_fullagent_patch_gate(*, repo_root: Path, task_id: str) -> Dict[str, Any]:
    """
    Ensure fullagent patch-gate artifacts exist:
    - evidence/patches/*.patch (copied from any existing *.diff if needed)
    - evidence/fullagent_submit.md containing a SUBMIT block
    """
    task_id = str(task_id)
    evidence_dir = task_evidence_dir(repo_root, task_id)
    patches_dir = (evidence_dir / "patches").resolve()
    patches_dir.mkdir(parents=True, exist_ok=True)

    patch_files = sorted(patches_dir.glob("*.patch"))
    if not patch_files:
        diff_files = sorted(patches_dir.glob("*.diff"))
        for d in diff_files[-200:]:
            target = (patches_dir / (d.stem + ".patch")).resolve()
            if not target.exists():
                target.write_text(d.read_text(encoding="utf-8", errors="replace"), encoding="utf-8", errors="replace")
        patch_files = sorted(patches_dir.glob("*.patch"))

    patch_paths = [str(p.resolve()) for p in patch_files[-200:]]
    submit_md = (evidence_dir / "fullagent_submit.md").resolve()
    submit_block = {
        "task_id": task_id,
        "mode": "fullagent",
        "phase": "patch_gate",
        "ts_utc": _utc_now_iso(),
        "artifacts": {
            "evidence_dir": str(evidence_dir),
            "patches": patch_paths,
        },
    }
    submit_md.write_text(
        "# SCC Fullagent Patch Gate\n\n## SUBMIT\n```submit\n"
        + json.dumps(submit_block, ensure_ascii=False, indent=2)
        + "\n```\n",
        encoding="utf-8",
        errors="replace",
    )
    try:
        from tools.scc.evidence_index import build_task_evidence_index

        build_task_evidence_index(repo_root=repo_root, task_id=task_id)
    except Exception:
        pass

    orch_store = OrchestratorStateStore(repo_root=repo_root, task_id=task_id)
    orch_store.append_history(key="mode_history", item={"mode": "fullagent"})
    orch_store.transition(
        phase="patch_gate",
        patch_data={"mode": "fullagent", "patch_count": len(patch_paths), "patches": patch_paths, "submit_md": str(submit_md)},
    )
    return {
        "ok": True,
        "task_id": task_id,
        "mode": "fullagent",
        "phase": "patch_gate",
        "evidence_dir": str(evidence_dir),
        "patches": patch_paths,
        "submit_md": str(submit_md),
    }


def _run_shell_command(cmd: str, cwd: Path, timeout_s: float) -> Tuple[int, str, str, float]:
    start = time.time()

    if os.name == "nt":
        argv = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            cmd,
        ]
        proc = subprocess.run(
            argv,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout_s if timeout_s > 0 else None,
        )
    else:
        proc = subprocess.run(
            ["bash", "-lc", cmd],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout_s if timeout_s > 0 else None,
        )

    dur = max(0.0, time.time() - start)
    return int(proc.returncode), proc.stdout or "", proc.stderr or "", dur


def _copy_artifacts(repo_path: Path, rel_paths: Sequence[str], dest_dir: Path) -> List[str]:
    copied: List[str] = []
    decisions: List[Dict[str, Any]] = []
    for rel in rel_paths:
        rel = str(rel or "").strip()
        if not rel:
            continue
        src = (repo_path / rel).resolve()
        try:
            src.relative_to(repo_path.resolve())
        except Exception:
            # Only allow paths under repo_path
            decisions.append(
                evaluate_write_path(repo_path=repo_path, target_path=rel, action="copy_artifact").to_dict()
            )
            continue
        if not src.exists():
            decisions.append(
                {
                    "ok": False,
                    "action": "copy_artifact",
                    "input_path": rel,
                    "abs_path": str(src),
                    "reason": "source_not_found",
                }
            )
            continue

        target = dest_dir / rel
        _safe_mkdir(target.parent)
        if src.is_dir():
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
            shutil.copytree(src, target, dirs_exist_ok=True)
        else:
            shutil.copy2(src, target)
        copied.append(str(target))
        decisions.append(
            {
                "ok": True,
                "action": "copy_artifact",
                "input_path": rel,
                "abs_path": str(src),
                "reason": "copied",
            }
        )
    return copied


@dataclass(frozen=True)
class TaskContract:
    goal: str
    scope_allow: List[str]
    success_criteria: List[str]
    stop_condition: List[str]
    commands_hint: List[str]
    artifacts_expectation: List[str]
    difficulty: str = ""


@dataclass(frozen=True)
class WorkspaceAdapter:
    repo_path: str
    bootstrap_cmds: List[str]
    test_cmds: List[str]
    artifact_paths: List[str]


@dataclass(frozen=True)
class SCCTaskRequest:
    task: TaskContract
    workspace: WorkspaceAdapter
    timeout_s: float = 0.0


@dataclass(frozen=True)
class SCCRunResult:
    run_id: str
    ok: bool
    exit_code: int
    out_dir: str
    selftest_log: str
    report_md: str
    evidence_dir: str
    copied_artifacts: List[str]


def run_scc_task(
    request: SCCTaskRequest,
    *,
    repo_root: Path,
    out_root: Optional[Path] = None,
) -> SCCRunResult:
    """
    Minimal SCC execution loop:
    - run bootstrap_cmds
    - run commands_hint
    - run test_cmds
    - write 3-piece deliverable set: selftest.log + report.md + evidence/
    """
    if not request.task.goal.strip():
        raise ValueError("task.goal is required")

    workspace_path = Path(request.workspace.repo_path).expanduser()
    if not workspace_path.is_absolute():
        workspace_path = (repo_root / workspace_path).resolve()

    if not workspace_path.exists() or not workspace_path.is_dir():
        raise FileNotFoundError(f"repo_path not found or not a directory: {workspace_path}")

    allowed_roots = _default_allowed_roots(repo_root)
    if not _is_under_any_root(workspace_path, allowed_roots):
        raise PermissionError(f"repo_path not under allowed roots: {workspace_path}")

    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:8]

    out_root = out_root or (repo_root / "artifacts" / "scc_runs")
    out_dir = (out_root / run_id).resolve()
    evidence_dir = out_dir / "evidence"
    logs_dir = out_dir / "logs"
    collected_dir = out_dir / "collected_artifacts"

    _safe_mkdir(evidence_dir)
    _safe_mkdir(logs_dir)
    _safe_mkdir(collected_dir)

    selftest_log = out_dir / "selftest.log"
    report_md = out_dir / "report.md"
    events_log = out_dir / "events.jsonl"
    timeout_s = float(request.timeout_s or 0.0)
    run_events = get_run_logger(repo_root=repo_root, run_id=run_id)
    run_events.emit(
        "run_started",
        run_id=run_id,
        data={
            "repo_path": str(workspace_path),
            "out_dir": str(out_dir),
            "timeout_s": timeout_s,
            "events_log": str(events_log),
        },
    )

    steps: List[Dict[str, Any]] = []
    permission_floor: Dict[str, Any] = {"commands": [], "artifact_paths": []}

    # Backend routing: for medium/high tasks, generate a Codex plan artifact (read-only) before executing any commands.
    if _get_env_bool("SCC_CODEX_PLAN_ENABLED", True):
        _maybe_generate_codex_plan(
            repo_root=repo_root,
            workspace_path=workspace_path,
            task=request.task,
            workspace=request.workspace,
            evidence_dir=evidence_dir,
            run_events=run_events,
            run_id=run_id,
            timeout_s=timeout_s,
        )

    def _run_step(kind: str, cmd: str, idx: int) -> int:
        cmd = str(cmd or "").strip()
        if not cmd:
            return 0

        log_path = logs_dir / f"{idx:03d}_{kind}.log"
        cmd_decision = evaluate_command(cmd=cmd)
        permission_floor["commands"].append({"idx": idx, "kind": kind, **cmd_decision.to_dict()})
        run_events.emit(
            "command_risk_classified",
            run_id=run_id,
            data={"idx": idx, "kind": kind, **cmd_decision.to_dict()},
        )
        if command_floor_enforce_enabled() and cmd_decision.risk == "deny":
            run_events.emit(
                "command_denied",
                run_id=run_id,
                data={"idx": idx, "kind": kind, **cmd_decision.to_dict()},
            )
            # Do not execute; return a non-zero deterministic code
            with open(log_path, "w", encoding="utf-8", errors="replace") as f:
                f.write("== SCC STEP ==\n")
                f.write(f"ts_utc={_utc_now_iso()}\n")
                f.write(f"kind={kind}\n")
                f.write(f"cwd={workspace_path}\n")
                f.write(f"cmd={cmd}\n")
                f.write("permission_floor=DENY\n")
                f.write(f"reason={cmd_decision.reason}\n")
                f.write("exit_code=97\n")
                f.write("\n== STDOUT ==\n(blocked)\n")
                f.write("\n== STDERR ==\n(blocked)\n")
            return 97
        run_events.emit(
            "step_started",
            run_id=run_id,
            data={"idx": idx, "kind": kind, "cmd": cmd, "log": str(log_path)},
        )
        exit_code, stdout, stderr, dur = _run_shell_command(cmd, cwd=workspace_path, timeout_s=timeout_s)
        payload = {
            "kind": kind,
            "cmd": cmd,
            "cwd": str(workspace_path),
            "exit_code": exit_code,
            "duration_s": dur,
            "log": str(log_path),
        }
        steps.append(payload)
        run_events.emit(
            "step_finished",
            run_id=run_id,
            data={"idx": idx, "kind": kind, "exit_code": exit_code, "duration_s": dur, "log": str(log_path)},
        )

        with open(log_path, "w", encoding="utf-8", errors="replace") as f:
            f.write(f"== SCC STEP ==\n")
            f.write(f"ts_utc={_utc_now_iso()}\n")
            f.write(f"kind={kind}\n")
            f.write(f"cwd={workspace_path}\n")
            f.write(f"cmd={cmd}\n")
            f.write(f"duration_s={dur:.3f}\n")
            f.write(f"exit_code={exit_code}\n")
            f.write("\n== STDOUT ==\n")
            f.write(stdout)
            if stdout and not stdout.endswith("\n"):
                f.write("\n")
            f.write("\n== STDERR ==\n")
            f.write(stderr)
            if stderr and not stderr.endswith("\n"):
                f.write("\n")
        return exit_code

    all_cmds: List[Tuple[str, str]] = []
    for c in request.workspace.bootstrap_cmds or []:
        all_cmds.append(("bootstrap", c))
    for c in request.task.commands_hint or []:
        all_cmds.append(("hint", c))
    for c in request.workspace.test_cmds or []:
        all_cmds.append(("test", c))

    planned_steps: List[PlannedStep] = []
    for idx, (kind, cmd) in enumerate(all_cmds, start=1):
        dec = evaluate_command(cmd=str(cmd or ""))
        planned_steps.append(
            PlannedStep(
                idx=idx,
                kind=kind,
                cmd=str(cmd or ""),
                risk=dec.risk,
                concurrency_safe=is_command_concurrency_safe(cmd),
            )
        )
    exec_plan = build_execution_plan(steps=planned_steps)
    with open(evidence_dir / "tool_execution_plan.json", "w", encoding="utf-8") as f:
        json.dump(exec_plan.to_dict(), f, ensure_ascii=False, indent=2)
    run_events.emit(
        "execution_plan_built",
        run_id=run_id,
        data={"summary": exec_plan.summary, "path": str(evidence_dir / "tool_execution_plan.json")},
    )

    final_exit = 0
    for idx, (kind, cmd) in enumerate(all_cmds, start=1):
        code = _run_step(kind, cmd, idx)
        if code != 0 and final_exit == 0:
            final_exit = code

    ok = final_exit == 0
    run_events.emit(
        "run_commands_finished",
        run_id=run_id,
        data={"ok": ok, "exit_code": final_exit, "steps": len(steps)},
    )

    copied_artifacts = _copy_artifacts(
        workspace_path,
        request.workspace.artifact_paths or [],
        dest_dir=collected_dir,
    )
    for rel in request.workspace.artifact_paths or []:
        permission_floor["artifact_paths"].append(
            evaluate_write_path(
                repo_path=workspace_path,
                target_path=str(rel),
                action="artifact_path",
                scope_allow=request.task.scope_allow or [],
            ).to_dict()
        )

    evidence_meta = {
        "run_id": run_id,
        "ts_utc": _utc_now_iso(),
        "repo_path": str(workspace_path),
        "repo_allowed_roots": [str(p) for p in allowed_roots],
        "events_log": str(events_log),
        "task": {
            "goal": request.task.goal,
            "scope_allow": request.task.scope_allow,
            "success_criteria": request.task.success_criteria,
            "stop_condition": request.task.stop_condition,
            "artifacts_expectation": request.task.artifacts_expectation,
        },
        "workspace": {
            "bootstrap_cmds": request.workspace.bootstrap_cmds,
            "test_cmds": request.workspace.test_cmds,
            "artifact_paths": request.workspace.artifact_paths,
        },
        "tool_execution_plan": str(evidence_dir / "tool_execution_plan.json"),
        "steps": steps,
        "exit_code": final_exit,
        "ok": ok,
    }

    with open(evidence_dir / "run_meta.json", "w", encoding="utf-8") as f:
        json.dump(evidence_meta, f, ensure_ascii=False, indent=2)
    with open(evidence_dir / "permission_floor.json", "w", encoding="utf-8") as f:
        json.dump(permission_floor, f, ensure_ascii=False, indent=2)
    run_events.emit(
        "permission_floor_written",
        run_id=run_id,
        data={"path": str(evidence_dir / "permission_floor.json")},
    )

    with open(selftest_log, "w", encoding="utf-8", errors="replace") as f:
        f.write("SCC SELFTEST LOG\n")
        f.write(f"run_id={run_id}\n")
        f.write(f"ts_utc={_utc_now_iso()}\n")
        f.write(f"repo_path={workspace_path}\n")
        f.write(f"out_dir={out_dir}\n")
        f.write(f"steps={len(steps)}\n")
        f.write(f"copied_artifacts={len(copied_artifacts)}\n")
        for s in steps:
            f.write(
                f"STEP kind={s['kind']} exit_code={s['exit_code']} duration_s={s['duration_s']:.3f} log={s['log']}\n"
            )
        f.write(f"EXIT_CODE={final_exit}\n")

    submit_block = {
        "run_id": run_id,
        "repo_path": str(workspace_path),
        "ok": ok,
        "exit_code": final_exit,
        "artifacts": {
            "selftest_log": str(selftest_log),
            "report_md": str(report_md),
            "evidence_dir": str(evidence_dir),
            "events_log": str(events_log),
            "logs_dir": str(logs_dir),
            "collected_artifacts_dir": str(collected_dir),
        },
    }

    with open(report_md, "w", encoding="utf-8", errors="replace") as f:
        f.write(f"# SCC Task Report\n\n")
        f.write(f"- run_id: `{run_id}`\n")
        f.write(f"- ts_utc: `{evidence_meta['ts_utc']}`\n")
        f.write(f"- repo_path: `{workspace_path}`\n")
        f.write(f"- verdict: `{'PASS' if ok else 'FAIL'}`\n")
        f.write(f"- exit_code: `{final_exit}`\n\n")
        f.write("## Task Contract\n")
        f.write(f"- goal: {request.task.goal}\n")
        if request.task.success_criteria:
            f.write("- success_criteria:\n")
            for it in request.task.success_criteria:
                f.write(f"  - {it}\n")
        if request.task.stop_condition:
            f.write("- stop_condition:\n")
            for it in request.task.stop_condition:
                f.write(f"  - {it}\n")
        if request.task.artifacts_expectation:
            f.write("- artifacts_expectation:\n")
            for it in request.task.artifacts_expectation:
                f.write(f"  - {it}\n")
        f.write("\n## Steps\n")
        if not steps:
            f.write("(no steps)\n")
        else:
            for s in steps:
                f.write(
                    f"- `{s['kind']}` exit_code={s['exit_code']} duration_s={s['duration_s']:.3f} log=`{s['log']}`\n"
                )
        if copied_artifacts:
            f.write("\n## Collected Artifacts\n")
            for p in copied_artifacts:
                f.write(f"- `{p}`\n")
        f.write("\n## Evidence\n")
        f.write(f"- `evidence/run_meta.json`\n\n")
        f.write("- `evidence/permission_floor.json`\n\n")
        f.write("- `evidence/tool_execution_plan.json`\n\n")
        f.write("## Events\n")
        f.write(f"- `events.jsonl`\n\n")
        f.write("## SUBMIT\n")
        f.write("```submit\n")
        json.dump(submit_block, f, ensure_ascii=False, indent=2)
        f.write("\n```\n")

    evidence_paths: List[str] = []
    for p in [
        selftest_log,
        report_md,
        events_log,
        evidence_dir / "run_meta.json",
        evidence_dir / "permission_floor.json",
        evidence_dir / "tool_execution_plan.json",
    ]:
        if Path(p).exists():
            evidence_paths.append(_normalize_relpath(Path(p), out_dir))
    for p in sorted(logs_dir.glob("*.log")):
        evidence_paths.append(_normalize_relpath(p, out_dir))
    for p in copied_artifacts:
        try:
            evidence_paths.append(_normalize_relpath(Path(p), out_dir))
        except Exception:
            continue

    verdict_payload = {
        "verdict": "PASS" if ok else "FAIL",
        "fail_class": _classify_fail_class(ok=ok, exit_code=final_exit, steps=steps),
        "exit_code": int(final_exit),
        "evidence_paths": sorted(set(evidence_paths)),
        "generated_utc": _utc_now_iso(),
    }
    verdict_path = evidence_dir / "verdict.json"
    verdict_path.write_text(json.dumps(verdict_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    run_events.emit(
        "run_finished",
        run_id=run_id,
        data={
            "ok": ok,
            "exit_code": final_exit,
            "report_md": str(report_md),
            "selftest_log": str(selftest_log),
            "evidence_dir": str(evidence_dir),
        },
    )

    return SCCRunResult(
        run_id=run_id,
        ok=ok,
        exit_code=final_exit,
        out_dir=str(out_dir),
        selftest_log=str(selftest_log),
        report_md=str(report_md),
        evidence_dir=str(evidence_dir),
        copied_artifacts=copied_artifacts,
    )
