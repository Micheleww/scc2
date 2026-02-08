from __future__ import annotations

import json
import os
import socket
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from tools.scc.task_runner import (
    SCCTaskRequest,
    TaskContract,
    WorkspaceAdapter,
    orchestrate_plan_or_chat,
    postprocess_fullagent_patch_gate,
    resolve_orchestrator_mode,
    run_scc_task,
)
from tools.scc.event_log import get_task_logger
from tools.scc.capabilities.file_lock import FileLock, FileLockMeta, default_workspace_lock_path, FileLockTimeout
from tools.scc.autopilot_engine import apply_action as autopilot_apply
from tools.scc.autopilot_engine import classify_reason_code
from tools.scc.autopilot_engine import decide as autopilot_decide
from tools.scc.orchestrators.state_store import OrchestratorStateStore
from tools.scc.orchestrators.continuation_context import write_continuation_context
from tools.scc.orchestrators.subtask_summary import record_subtask_summary


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_mkdir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)

def _temporary_env(patch: Dict[str, str]):
    class _EnvCtx:
        def __init__(self, patch_: Dict[str, str]):
            self.patch_ = patch_
            self.prev: Dict[str, Optional[str]] = {}

        def __enter__(self):
            for k, v in self.patch_.items():
                self.prev[k] = os.environ.get(k)
                os.environ[k] = str(v)
            return self

        def __exit__(self, exc_type, exc, tb):
            for k, old in self.prev.items():
                if old is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = old
            return False

    return _EnvCtx({k: str(v) for k, v in (patch or {}).items()})


def _resolve_auto_mode(payload: Dict[str, Any]) -> str:
    """
    Backend default routing:
    - medium/high => plan
    - low => chat
    """
    try:
        task = payload.get("task") if isinstance(payload.get("task"), dict) else {}
        forced = str(task.get("difficulty") or payload.get("difficulty") or "").strip().lower()
        if forced in {"low", "medium", "high"}:
            return "plan" if forced in {"medium", "high"} else "chat"
        task_goal = str(task.get("goal") or payload.get("goal") or "").lower()
        cmd_n = len([c for c in (task.get("commands_hint") or payload.get("commands_hint") or []) if str(c).strip()])
        test_n = 0
        ws = payload.get("workspace") if isinstance(payload.get("workspace"), dict) else payload
        if isinstance(ws, dict):
            test_n = len([c for c in (ws.get("test_cmds") or payload.get("test_cmds") or []) if str(c).strip()])
        score = min(4, cmd_n) + min(3, test_n)
        if any(k in task_goal for k in ["refactor", "architecture", "migrate", "integrate", "rewrite", "pipeline", "orchestr", "deploy"]):
            score += 3
        elif any(k in task_goal for k in ["debug", "fix", "stabil", "improve", "optimi", "test", "build", "ci"]):
            score += 2
        return "plan" if score >= 3 else "chat"
    except Exception:
        return "plan"


@dataclass
class TaskRecord:
    task_id: str
    created_utc: str
    updated_utc: str
    status: str  # pending|running|done|failed|canceled
    request: Dict[str, Any]
    run_id: Optional[str] = None
    exit_code: Optional[int] = None
    verdict: Optional[str] = None  # PASS|FAIL
    out_dir: Optional[str] = None
    selftest_log: Optional[str] = None
    report_md: Optional[str] = None
    evidence_dir: Optional[str] = None
    error: Optional[str] = None


class SCCTaskQueue:
    """
    Minimal autonomous task processor:
    - persists tasks to artifacts/scc_tasks/<task_id>/task.json
    - executes sequentially in a single background worker thread
    - exposes deterministic artifacts via run_scc_task (artifacts/scc_runs/<run_id>/...)

    No auto-fix, no multi-model routing.
    """

    def __init__(self, *, repo_root: Path):
        self.repo_root = repo_root
        self.tasks_root = (repo_root / "artifacts" / "scc_tasks").resolve()
        _safe_mkdir(self.tasks_root)
        self.autostart_enabled = (os.environ.get("SCC_TASK_AUTOSTART_ENABLED", "true").strip().lower() != "false")

        self._lock = threading.Lock()
        self._worker: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def start(self) -> None:
        with self._lock:
            if self._worker and self._worker.is_alive():
                return
            self._stop.clear()
            self._worker = threading.Thread(target=self._run_loop, name="scc-task-worker", daemon=True)
            self._worker.start()

    def stop(self) -> None:
        self._stop.set()

    def _task_dir(self, task_id: str) -> Path:
        return (self.tasks_root / task_id).resolve()

    def _task_path(self, task_id: str) -> Path:
        return self._task_dir(task_id) / "task.json"

    def _read_task(self, task_id: str) -> TaskRecord:
        p = self._task_path(task_id)
        data = json.loads(p.read_text(encoding="utf-8"))
        return TaskRecord(**data)

    def _write_task(self, rec: TaskRecord) -> None:
        d = self._task_dir(rec.task_id)
        _safe_mkdir(d)
        p = self._task_path(rec.task_id)
        rec.updated_utc = _utc_now_iso()
        p.write_text(json.dumps(asdict(rec), ensure_ascii=False, indent=2), encoding="utf-8")

    def _autopilot_risk_level(self, *, payload: Dict[str, Any]) -> str:
        try:
            task = payload.get("task") if isinstance(payload.get("task"), dict) else {}
            forced = str(task.get("difficulty") or payload.get("difficulty") or "").strip().lower()
            if forced in {"low", "medium", "high"}:
                return "high" if forced == "high" else ("medium" if forced == "medium" else "low")
        except Exception:
            pass
        return "low"

    def _apply_autopilot(
        self,
        *,
        task_id: str,
        payload: Dict[str, Any],
        status: str,
        error: str,
        exit_code: Optional[int] = None,
    ) -> None:
        reason_code = classify_reason_code(error=error, exit_code=exit_code)
        risk_level = self._autopilot_risk_level(payload=payload)

        decision, state = autopilot_decide(
            repo_root=self.repo_root,
            task_id=task_id,
            status=status,
            reason_code=reason_code,
            risk_level=risk_level,
        )

        task_logger = get_task_logger(repo_root=self.repo_root, task_id=task_id)
        task_logger.emit(
            "autopilot_decision",
            task_id=task_id,
            data={"reason_code": reason_code, "risk_level": risk_level, "decision": decision.to_dict()},
        )

        with self._lock:
            rec = self._read_task(task_id)
            action_out = autopilot_apply(
                repo_root=self.repo_root,
                task_id=task_id,
                decision=decision,
                state=state,
                task_record=rec.__dict__,
            )

            set_status = str(action_out.get("set_status") or "").strip()
            if set_status:
                rec.status = set_status

            if decision.model_override:
                OrchestratorStateStore(repo_root=self.repo_root, task_id=task_id).transition(
                    phase="autopilot_model_selected",
                    patch_data={"autopilot_model": decision.model_override, "reason_code": reason_code, "risk_level": risk_level},
                )

            if set_status == "await_user":
                rec.error = json.dumps({"ask_user": decision.ask_user, "reason_code": reason_code}, ensure_ascii=False)
                OrchestratorStateStore(repo_root=self.repo_root, task_id=task_id).transition(
                    phase="await_user",
                    patch_data={"status": rec.status, "reason_code": reason_code, "ask_user": decision.ask_user},
                )
            elif set_status == "dlq":
                OrchestratorStateStore(repo_root=self.repo_root, task_id=task_id).transition(
                    phase="dlq",
                    patch_data={"status": rec.status, "reason_code": reason_code, "dlq_path": action_out.get("dlq_path")},
                )
            elif set_status == "pending":
                OrchestratorStateStore(repo_root=self.repo_root, task_id=task_id).transition(
                    phase="autopilot_retry_scheduled",
                    patch_data={"status": rec.status, "reason_code": reason_code},
                )
            self._write_task(rec)

        task_logger.emit(
            "autopilot_action",
            task_id=task_id,
            data={"reason_code": reason_code, "risk_level": risk_level, "decision": decision.to_dict(), "action": action_out},
        )

    def submit(self, payload: Dict[str, Any], *, autostart: Optional[bool] = None) -> TaskRecord:
        task_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:8]
        return self.submit_with_task_id(task_id=task_id, payload=payload, autostart=autostart)

    def submit_with_task_id(self, *, task_id: str, payload: Dict[str, Any], autostart: Optional[bool] = None) -> TaskRecord:
        task_id = str(task_id or "").strip()
        if not task_id:
            raise ValueError("task_id is required")
        if self.exists(task_id):
            # Allow mode switching / re-orchestration on the same task id (when not running).
            rec = self._read_task(task_id)
            requested_mode = resolve_orchestrator_mode(payload)
            if requested_mode != "execute" and rec.status != "running":
                rec.request = payload
                # Re-queue if already finished
                if rec.status in {"done", "failed", "canceled"}:
                    rec.status = "pending"
                    rec.run_id = None
                    rec.exit_code = None
                    rec.verdict = None
                    rec.out_dir = None
                    rec.selftest_log = None
                    rec.report_md = None
                    rec.evidence_dir = None
                    rec.error = None
                self._write_task(rec)
                OrchestratorStateStore(repo_root=self.repo_root, task_id=task_id).transition(
                    phase="requeued",
                    patch_data={"status": rec.status, "requested_mode": requested_mode},
                )
                try:
                    write_continuation_context(repo_root=self.repo_root, task_id=task_id)
                except Exception:
                    pass
            return rec
        now = _utc_now_iso()
        rec = TaskRecord(
            task_id=task_id,
            created_utc=now,
            updated_utc=now,
            status="pending",
            request=payload,
        )
        self._write_task(rec)
        requested_mode = resolve_orchestrator_mode(payload)
        OrchestratorStateStore(repo_root=self.repo_root, task_id=task_id).init_if_missing(
            phase="queued",
            data={"status": "pending", "requested_mode": requested_mode},
        )
        get_task_logger(repo_root=self.repo_root, task_id=task_id).emit(
            "task_submitted",
            task_id=task_id,
            data={"status": "pending", "requested_mode": requested_mode},
        )
        try:
            write_continuation_context(repo_root=self.repo_root, task_id=task_id)
        except Exception:
            pass
        should_autostart = self.autostart_enabled if autostart is None else bool(autostart)
        if should_autostart:
            self.start()
        return rec

    def exists(self, task_id: str) -> bool:
        return self._task_path(task_id).exists()

    def cancel(self, task_id: str) -> TaskRecord:
        with self._lock:
            rec = self._read_task(task_id)
            if rec.status == "pending":
                rec.status = "canceled"
                self._write_task(rec)
                OrchestratorStateStore(repo_root=self.repo_root, task_id=task_id).transition(
                    phase="canceled",
                    patch_data={"status": "canceled"},
                )
                get_task_logger(repo_root=self.repo_root, task_id=task_id).emit(
                    "task_canceled",
                    task_id=task_id,
                    data={"status": "canceled"},
                )
                try:
                    write_continuation_context(repo_root=self.repo_root, task_id=task_id)
                except Exception:
                    pass
            return rec

    def get(self, task_id: str) -> TaskRecord:
        return self._read_task(task_id)

    def list(self, limit: int = 50) -> List[TaskRecord]:
        out: List[TaskRecord] = []
        for d in sorted(self.tasks_root.glob("*"), reverse=True):
            if not d.is_dir():
                continue
            p = d / "task.json"
            if not p.exists():
                continue
            try:
                out.append(TaskRecord(**json.loads(p.read_text(encoding="utf-8"))))
            except Exception:
                continue
            if len(out) >= max(1, int(limit or 50)):
                break
        return out

    def stats(self) -> Dict[str, int]:
        counts: Dict[str, int] = {"pending": 0, "running": 0, "done": 0, "failed": 0, "canceled": 0, "total": 0}
        for d in self.tasks_root.glob("*"):
            if not d.is_dir():
                continue
            p = d / "task.json"
            if not p.exists():
                continue
            try:
                rec = TaskRecord(**json.loads(p.read_text(encoding="utf-8")))
            except Exception:
                continue
            counts["total"] += 1
            if rec.status in counts:
                counts[rec.status] += 1
        return counts

    def _payload_to_request(self, payload: Dict[str, Any]) -> SCCTaskRequest:
        task = payload.get("task") or {}
        workspace = payload.get("workspace") or payload

        goal = str(task.get("goal") or payload.get("goal") or "").strip() or "Run commands (no goal provided)"

        return SCCTaskRequest(
            task=TaskContract(
                goal=goal,
                scope_allow=list(task.get("scope_allow") or []),
                success_criteria=list(task.get("success_criteria") or []),
                stop_condition=list(task.get("stop_condition") or []),
                commands_hint=list(task.get("commands_hint") or payload.get("commands_hint") or []),
                artifacts_expectation=list(task.get("artifacts_expectation") or []),
            ),
            workspace=WorkspaceAdapter(
                repo_path=str(workspace.get("repo_path") or ""),
                bootstrap_cmds=list(workspace.get("bootstrap_cmds") or []),
                test_cmds=list(workspace.get("test_cmds") or payload.get("test_cmds") or []),
                artifact_paths=list(workspace.get("artifact_paths") or []),
            ),
            timeout_s=float(payload.get("timeout_s") or 0.0),
        )

    def payload_to_request(self, payload: Dict[str, Any]) -> SCCTaskRequest:
        return self._payload_to_request(payload)

    def _try_record_parent_summary(self, *, task_id: str, payload: Dict[str, Any]) -> None:
        try:
            req = payload if isinstance(payload, dict) else {}
            meta = req.get("meta") if isinstance(req.get("meta"), dict) else {}
            parent_task_id = str(meta.get("parent_task_id") or "").strip()
            if not parent_task_id:
                return
            record_subtask_summary(repo_root=self.repo_root, parent_task_id=parent_task_id, child_task_id=task_id)
            try:
                write_continuation_context(repo_root=self.repo_root, task_id=parent_task_id)
            except Exception:
                pass
        except Exception:
            return

    def _run_loop(self) -> None:
        while not self._stop.is_set():
            # Find first pending task
            task_id = None
            for d in sorted(self.tasks_root.glob("*")):
                if not d.is_dir():
                    continue
                p = d / "task.json"
                if not p.exists():
                    continue
                try:
                    rec = TaskRecord(**json.loads(p.read_text(encoding="utf-8")))
                except Exception:
                    continue
                if rec.status == "pending":
                    task_id = rec.task_id
                    break

            if not task_id:
                time.sleep(0.5)
                continue

            # Execute single task (sequential)
            with self._lock:
                try:
                    rec = self._read_task(task_id)
                except Exception:
                    time.sleep(0.2)
                    continue
                if rec.status != "pending":
                    continue
                rec.status = "running"
                self._write_task(rec)
                OrchestratorStateStore(repo_root=self.repo_root, task_id=task_id).transition(
                    phase="running",
                    patch_data={"status": "running"},
                )
                get_task_logger(repo_root=self.repo_root, task_id=task_id).emit(
                    "task_started",
                    task_id=task_id,
                    data={"status": "running"},
                )
                try:
                    write_continuation_context(repo_root=self.repo_root, task_id=task_id)
                except Exception:
                    pass

            try:
                req = self._payload_to_request(rec.request)
                requested_mode = resolve_orchestrator_mode(rec.request)
                if requested_mode == "auto":
                    requested_mode = _resolve_auto_mode(rec.request)

                model_env: Dict[str, str] = {}
                try:
                    st = OrchestratorStateStore(repo_root=self.repo_root, task_id=task_id).read()
                    if st and isinstance(st.data, dict):
                        m = str(st.data.get("autopilot_model") or "").strip()
                        if m:
                            model_env["A2A_CODEX_MODEL"] = m
                            model_env["SCC_FULLAGENT_MODEL"] = m
                except Exception:
                    model_env = {}

                with _temporary_env(model_env):
                    if requested_mode in {"plan", "chat"}:
                        out = orchestrate_plan_or_chat(
                            repo_root=self.repo_root,
                            task_id=task_id,
                            payload=rec.request,
                            mode=requested_mode,
                        )
                        with self._lock:
                            rec = self._read_task(task_id)
                            rec.status = "done" if out.get("ok") else "failed"
                            rec.verdict = "PASS" if out.get("ok") else "FAIL"
                            rec.exit_code = 0 if out.get("ok") else 2
                            rec.evidence_dir = str(out.get("evidence_dir") or "").strip() or None
                            rec.error = None if out.get("ok") else str(out.get("error") or "orchestrate_failed")
                            self._write_task(rec)
                            OrchestratorStateStore(repo_root=self.repo_root, task_id=task_id).transition(
                                phase="done" if out.get("ok") else "failed",
                                patch_data={"status": rec.status, "verdict": rec.verdict, "mode": requested_mode},
                            )
                            get_task_logger(repo_root=self.repo_root, task_id=task_id).emit(
                                "orchestrator_task_finished",
                                task_id=task_id,
                                data={"status": rec.status, "verdict": rec.verdict, "mode": requested_mode, "evidence_dir": rec.evidence_dir},
                            )
                            try:
                                write_continuation_context(repo_root=self.repo_root, task_id=task_id)
                            except Exception:
                                pass
                            self._try_record_parent_summary(task_id=task_id, payload=rec.request)
                        if not out.get("ok"):
                            try:
                                self._apply_autopilot(
                                    task_id=task_id,
                                    payload=rec.request,
                                    status="failed",
                                    error=str(out.get("error") or "orchestrate_failed"),
                                    exit_code=2,
                                )
                            except Exception:
                                pass
                        continue

                    if requested_mode == "fullagent":
                        # Idempotent: if patches already exist, only post-process into patch gate artifacts.
                        ev_dir = (self.repo_root / "artifacts" / "scc_tasks" / task_id / "evidence").resolve()
                        patches_dir = (ev_dir / "patches").resolve()
                        has_any_patch = patches_dir.exists() and any(patches_dir.glob("*.patch"))
                        has_any_diff = patches_dir.exists() and any(patches_dir.glob("*.diff"))
                        if not (has_any_patch or has_any_diff):
                            from tools.scc.orchestrators.fullagent_loop import fullagent_orchestrate
                            from tools.scc.orchestrators.profiles import resolve_profile

                            profile = resolve_profile("fullagent")
                            with _temporary_env(
                                {
                                    "SCC_FULLAGENT_CREATE_EXEC_TASK": "false",
                                    "SCC_FULLAGENT_ALLOW_SHELL": "false",
                                    "SCC_FULLAGENT_MODEL": model_env.get("SCC_FULLAGENT_MODEL") or "gpt-5.2",
                                }
                            ):
                                fullagent_orchestrate(
                                    repo_root=self.repo_root,
                                    task_queue=self,
                                    payload=rec.request,
                                    profile=profile,
                                    task_id=task_id,
                                )

                        out = postprocess_fullagent_patch_gate(repo_root=self.repo_root, task_id=task_id)
                        with self._lock:
                            rec = self._read_task(task_id)
                            rec.status = "done" if out.get("ok") else "failed"
                            rec.verdict = "PASS" if out.get("ok") else "FAIL"
                            rec.exit_code = 0 if out.get("ok") else 2
                            rec.evidence_dir = str(out.get("evidence_dir") or "").strip() or None
                            rec.error = None if out.get("ok") else str(out.get("error") or "fullagent_failed")
                            self._write_task(rec)
                            OrchestratorStateStore(repo_root=self.repo_root, task_id=task_id).transition(
                                phase="patch_gate" if out.get("ok") else "failed",
                                patch_data={"status": rec.status, "verdict": rec.verdict, "mode": "fullagent"},
                            )
                            get_task_logger(repo_root=self.repo_root, task_id=task_id).emit(
                                "orchestrator_task_finished",
                                task_id=task_id,
                                data={
                                    "status": rec.status,
                                    "verdict": rec.verdict,
                                    "mode": "fullagent",
                                    "phase": "patch_gate",
                                    "evidence_dir": rec.evidence_dir,
                                },
                            )
                            try:
                                write_continuation_context(repo_root=self.repo_root, task_id=task_id)
                            except Exception:
                                pass
                            self._try_record_parent_summary(task_id=task_id, payload=rec.request)
                        if not out.get("ok"):
                            try:
                                self._apply_autopilot(
                                    task_id=task_id,
                                    payload=rec.request,
                                    status="failed",
                                    error=str(out.get("error") or "fullagent_failed"),
                                    exit_code=2,
                                )
                            except Exception:
                                pass
                        continue

                    # Default: normal SCC runner
                    task_logger = get_task_logger(repo_root=self.repo_root, task_id=task_id)
                    lock_path = default_workspace_lock_path(self.repo_root)
                try:
                    timeout_s = float(os.environ.get("SCC_WORKSPACE_WRITE_LOCK_TIMEOUT_S", "300").strip())
                except Exception:
                    timeout_s = 300.0

                lock = FileLock(
                    lock_path,
                    timeout_s=timeout_s,
                    meta=FileLockMeta(
                        task_id=task_id,
                        executor_id=str(os.environ.get("SCC_EXECUTOR_ID") or "").strip() or None,
                        pid=os.getpid(),
                        hostname=socket.gethostname(),
                        acquired_ts_utc=_utc_now_iso(),
                    ),
                )
                t0 = time.time()
                task_logger.emit(
                    "file_lock_acquire_start",
                    task_id=task_id,
                    data={
                        "reason_code": "file_lock_acquire_start",
                        "scope": "workspace_write",
                        "lock_path": str(lock_path),
                        "timeout_s": timeout_s,
                    },
                )
                try:
                    lock.acquire()
                except FileLockTimeout as e:
                    task_logger.emit(
                        "file_lock_acquire_failed",
                        task_id=task_id,
                        data={
                            "reason_code": e.reason_code,
                            "scope": "workspace_write",
                            "lock_path": str(e.lock_path),
                            "timeout_s": timeout_s,
                            "waited_s": max(0.0, time.time() - t0),
                        },
                    )
                    raise RuntimeError(f"{e.reason_code}: {e}") from e
                except Exception as e:
                    task_logger.emit(
                        "file_lock_acquire_failed",
                        task_id=task_id,
                        data={
                            "reason_code": "file_lock_error",
                            "scope": "workspace_write",
                            "lock_path": str(lock_path),
                            "timeout_s": timeout_s,
                            "waited_s": max(0.0, time.time() - t0),
                            "error": str(e),
                        },
                    )
                    raise

                task_logger.emit(
                    "file_lock_acquired",
                    task_id=task_id,
                    data={
                        "reason_code": "file_lock_acquired",
                        "scope": "workspace_write",
                        "lock_path": str(lock_path),
                        "waited_s": max(0.0, time.time() - t0),
                    },
                )
                try:
                    with _temporary_env(model_env):
                        result = run_scc_task(req, repo_root=self.repo_root)
                finally:
                    try:
                        lock.release()
                    except Exception:
                        pass
                verdict_path = None
                verdict_missing = False
                try:
                    verdict_path = Path(result.evidence_dir) / "verdict.json"
                    verdict_missing = not verdict_path.exists()
                except Exception:
                    verdict_missing = True
                final_ok = bool(result.ok) and not verdict_missing
                with self._lock:
                    rec = self._read_task(task_id)
                    rec.status = "done" if final_ok else "failed"
                    rec.run_id = result.run_id
                    rec.exit_code = int(result.exit_code)
                    rec.verdict = "PASS" if final_ok else "FAIL"
                    rec.out_dir = result.out_dir
                    rec.selftest_log = result.selftest_log
                    rec.report_md = result.report_md
                    rec.evidence_dir = result.evidence_dir
                    if final_ok:
                        rec.error = None
                    elif verdict_missing:
                        rec.error = f"verdict_missing: {verdict_path}" if verdict_path else "verdict_missing"
                    else:
                        rec.error = f"scc_run_failed: exit_code={int(result.exit_code)}"
                    self._write_task(rec)
                    OrchestratorStateStore(repo_root=self.repo_root, task_id=task_id).transition(
                        phase="done" if final_ok else "failed",
                        patch_data={
                            "status": rec.status,
                            "run_id": rec.run_id,
                            "exit_code": rec.exit_code,
                            "verdict": rec.verdict,
                        },
                    )
                    get_task_logger(repo_root=self.repo_root, task_id=task_id).emit(
                        "task_finished",
                        task_id=task_id,
                        run_id=result.run_id,
                        data={
                            "status": rec.status,
                            "verdict": rec.verdict,
                            "exit_code": rec.exit_code,
                            "report_md": rec.report_md,
                            "selftest_log": rec.selftest_log,
                        },
                    )
                    try:
                        write_continuation_context(repo_root=self.repo_root, task_id=task_id)
                    except Exception:
                        pass
                    self._try_record_parent_summary(task_id=task_id, payload=rec.request)
                if not final_ok:
                    try:
                        self._apply_autopilot(
                            task_id=task_id,
                            payload=rec.request,
                            status="failed",
                            error=str(rec.error or "scc_run_failed"),
                            exit_code=int(result.exit_code),
                        )
                    except Exception:
                        pass
            except Exception as e:
                with self._lock:
                    rec = self._read_task(task_id)
                    rec.status = "failed"
                    rec.error = str(e)
                    self._write_task(rec)
                    OrchestratorStateStore(repo_root=self.repo_root, task_id=task_id).transition(
                        phase="failed",
                        patch_data={"status": "failed", "error": str(e)},
                    )
                    get_task_logger(repo_root=self.repo_root, task_id=task_id).emit(
                        "task_failed",
                        task_id=task_id,
                        data={"error": str(e)},
                    )
                    try:
                        write_continuation_context(repo_root=self.repo_root, task_id=task_id)
                    except Exception:
                        pass
                    self._try_record_parent_summary(task_id=task_id, payload=rec.request)
                try:
                    self._apply_autopilot(
                        task_id=task_id,
                        payload=rec.request,
                        status="failed",
                        error=str(e),
                        exit_code=None,
                    )
                except Exception:
                    pass
