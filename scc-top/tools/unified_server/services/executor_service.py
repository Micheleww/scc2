"""
执行器服务包装器

codex-only：仅保留 Codex CLI 作为执行器
"""

import os
import logging
import subprocess
import tempfile
import json
import time
import fnmatch
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from collections import defaultdict, deque
import threading

from tools.unified_server.core.service_registry import Service, ServiceStatus
from tools.scc.runtime_config import load_runtime_config

logger = logging.getLogger(__name__)


class ExecutorService(Service):
    """执行器服务包装器"""
    
    def __init__(self, name: str, enabled: bool = True, repo_root: Optional[Path] = None, path: str = "/executor"):
        logger.info(f"Creating ExecutorService with name: {name}, enabled: {enabled}, path: {path}")
        super().__init__(name, enabled, auto_allocate_port=False)
        logger.info(f"ExecutorService super initialized with status: {self.status}")
        self.path = path
        self.repo_root = repo_root or Path(__file__).parent.parent.parent.parent
        logger.info(f"ExecutorService repo root: {self.repo_root}")
        self._app: Any = None
        self.task_execution_history = defaultdict(lambda: deque(maxlen=10))  # 任务执行历史
        self.lock = threading.Lock()  # 用于历史记录的线程安全
        
        # 执行器配置
        logger.info("Initializing executor configurations")

        rt = load_runtime_config(repo_root=self.repo_root)
        self._abandon_active_run_after_s = int(getattr(rt, "executor_abandon_active_run_after_s", 21600) or 21600)

        # Codex CLI（OpenAI Codex）配置：用于执行分解过后的子任务
        self.codex_config = {
            "exe": os.environ.get("CODEX_CLI_EXE", "codex"),
            # Use APPDATA for npm global bin fallback; avoid hardcoding developer-specific paths.
            "cmd_fallback": str(Path(os.environ.get("APPDATA") or "") / "npm" / "codex.cmd") if os.environ.get("APPDATA") else "",
            "model": str(os.environ.get("A2A_CODEX_MODEL") or rt.codex_model or "gpt-5.2"),
            "timeout": int(os.environ.get("A2A_CODEX_TIMEOUT_SEC") or rt.codex_timeout_s or 900),
            "max_outstanding_limit": int(os.environ.get("A2A_CODEX_MAX_OUTSTANDING_LIMIT") or rt.codex_max_outstanding_limit or 4),
        }
        logger.info(f"Codex config: {self.codex_config}")

        # OpenCode CLI 配置：作为与 Codex CLI 平行的执行器
        self.oc_config = {
            "exe": os.environ.get("OPENCODE_CLI_EXE", r"c:\scc\OpenCode\opencode-cli.exe"),
            "model": str(os.environ.get("A2A_OPENCODE_MODEL") or getattr(rt, "opencode_model", "") or "gpt-5.2"),
            "timeout": int(os.environ.get("A2A_OPENCODE_TIMEOUT_SEC") or getattr(rt, "opencode_timeout_s", 0) or 900),
            "max_outstanding_limit": int(
                os.environ.get("A2A_OPENCODE_MAX_OUTSTANDING_LIMIT") or getattr(rt, "opencode_max_outstanding_limit", 0) or 4
            ),
        }
        logger.info(f"OpenCode config: {self.oc_config}")

        self._state_dir = self.repo_root / "artifacts" / "codexcli_remote_runs" / "_state"
        self._active_runs_file = self._state_dir / "active_runs.json"
        self._state_lock = threading.Lock()
        self._apply_lock = threading.Lock()
        self._worktree_lock = threading.Lock()
        self._run_proc_lock = threading.Lock()
        self._run_task_lock = threading.Lock()
        # run_id -> parent_id -> {"pid": int, "started_utc": str}
        self._run_procs: dict[str, dict[str, dict[str, Any]]] = {}
        # run_id -> parent_id -> {"cancel_requested_utc": str, "reason": str}
        self._cancel_requests: dict[str, dict[str, dict[str, Any]]] = {}
        # run_id -> parent_id -> asyncio.Task (best-effort, same event loop)
        self._run_tasks: dict[str, dict[str, Any]] = {}
        
        logger.info(f"ExecutorService initialized with path: {self.path}")

    def _routing_file(self) -> Path:
        # Volume-mounted in docker-compose: unified_server_state:/app/tools/unified_server/state
        return (self.repo_root / "tools" / "unified_server" / "state" / "model_routing.json").resolve()

    def _load_model_routing(self) -> Dict[str, Any]:
        p = self._routing_file()
        try:
            if not p.exists():
                return {}
            obj = json.loads(p.read_text(encoding="utf-8", errors="replace") or "null")
            return obj if isinstance(obj, dict) else {}
        except Exception:
            return {}

    def _select_model(self, *, executor: str, requested: str) -> Tuple[str, Optional[str]]:
        """
        Resolve the effective model for an executor.

        Precedence:
        1) explicit request.model (if allowed)
        2) routing file default (if present)
        3) executor service config default
        """
        executor = str(executor or "").strip().lower()
        requested = str(requested or "").strip()

        routing = self._load_model_routing()
        ex = routing.get("executors") if isinstance(routing.get("executors"), dict) else {}
        ex_cfg = ex.get(executor) if isinstance(ex.get(executor), dict) else {}
        allowed = ex_cfg.get("allowed") if isinstance(ex_cfg.get("allowed"), list) else None
        allowed_set = {str(x).strip() for x in allowed or [] if str(x).strip()}

        default = str(ex_cfg.get("default") or "").strip()
        if not default:
            if executor == "codex":
                default = str(self.codex_config.get("model") or "").strip()
            elif executor == "opencode":
                default = str(self.oc_config.get("model") or "").strip()
        default = default or "gpt-5.2"

        if requested:
            if allowed_set and requested not in allowed_set:
                return default, f"model_not_allowed: {requested} (allowed={sorted(list(allowed_set))})"
            return requested, None

        if allowed_set and default not in allowed_set:
            # Auto-heal: fall back to first allowed model if default drifts.
            default2 = sorted(list(allowed_set))[0]
            return default2, None

        return default, None
    
    async def initialize(self) -> None:
        """初始化执行器服务"""
        logger.info("Starting executor service initialization")
        try:
            logger.info("Importing FastAPI modules")
            from fastapi import FastAPI, HTTPException, BackgroundTasks
            from fastapi.responses import JSONResponse
            
            logger.info("Creating FastAPI application for executor service")
            app = FastAPI(title="Executor Service", version="1.0.0")
            
            logger.info("Registering endpoints for executor service")
            
            from pydantic import BaseModel

            class CodexRequest(BaseModel):
                prompt: str
                model: str = ""
                dangerously_bypass: bool = False

            class CodexRunRequest(BaseModel):
                parents: Dict[str, Any]
                model: str = ""
                timeout_s: float = 0.0
                max_outstanding: int = 1
                dangerously_bypass: bool = False

            class CodexCancelRequest(BaseModel):
                run_id: str
                parent_id: str = ""  # optional
                reason: str = ""

            class OpenCodeRequest(BaseModel):
                prompt: str
                model: str = ""
                dangerously_bypass: bool = False

            class OpenCodeRunRequest(BaseModel):
                parents: Dict[str, Any]
                model: str = ""
                timeout_s: float = 0.0
                max_outstanding: int = 1
                dangerously_bypass: bool = False

            class ParallelProbeRequest(BaseModel):
                n: int = 4
                max_outstanding: int = 0
                sleep_ms: int = 600

            @app.post("/codex")
            async def run_codex(request: CodexRequest, background_tasks: BackgroundTasks):
                """运行 Codex CLI（非交互 exec）：执行单条子任务 prompt。"""
                try:
                    prompt = request.prompt
                    if not prompt:
                        raise HTTPException(status_code=400, detail="Prompt is required")

                    model, err = self._select_model(executor="codex", requested=str(request.model or ""))
                    if err:
                        raise HTTPException(status_code=400, detail=err)
                    exit_code, stdout, stderr, reason_code, meta = await self._run_codex_prompt(
                        prompt=prompt,
                        model=model,
                        dangerously_bypass=bool(request.dangerously_bypass),
                    )
                    result = {
                        "success": exit_code == 0,
                        "exit_code": exit_code,
                        "stdout": stdout,
                        "stderr": stderr,
                        "reason_code": reason_code,
                        "executor": "codex",
                        **(meta or {}),
                    }
                    return JSONResponse(content=result)
                except Exception as e:
                    logger.error(f"Codex execution error: {e}", exc_info=True)
                    raise HTTPException(status_code=500, detail=str(e))

            @app.post("/codex/run")
            async def run_codex_batch(request: CodexRunRequest, background_tasks: BackgroundTasks):
                """
                运行 Codex CLI（批量 run）：由客户端提交 parents.json_struct（不依赖客户端文件系统）。
                产物默认落盘到服务器 artifacts/codexcli_remote_runs/<run_id>/ 下。
                """
                try:
                    if not request.parents:
                        raise HTTPException(status_code=400, detail="parents is required")

                    # Safety gate: dangerously_bypass must never run without an explicit allowlist per parent.
                    # This prevents wide, accidental writes when sandbox/approvals are bypassed.
                    if bool(request.dangerously_bypass):
                        items = None
                        if isinstance(request.parents, dict):
                            items = request.parents.get("parents")
                            if not isinstance(items, list):
                                items = request.parents.get("tasks")
                        if not isinstance(items, list) or not items:
                            raise HTTPException(status_code=400, detail="parents must include a list at key 'parents' (or 'tasks')")
                        missing: list[str] = []
                        for i, p in enumerate(items, 1):
                            if not isinstance(p, dict):
                                missing.append(str(i))
                                continue
                            pid = str(p.get("id") or i)
                            globs = p.get("allowed_globs")
                            if not (isinstance(globs, list) and any(str(x).strip() for x in globs)):
                                missing.append(pid)
                        if missing:
                            raise HTTPException(
                                status_code=400,
                                detail=f"dangerously_bypass requires non-empty allowed_globs for every parent: missing={missing}",
                            )

                    model, err = self._select_model(executor="codex", requested=str(request.model or ""))
                    if err:
                        raise HTTPException(status_code=400, detail=err)
                    exit_code, stdout, stderr, reason_code, meta = await self._run_codex_run(
                        parents=request.parents,
                        model=model,
                        timeout_s=float(request.timeout_s or 0.0),
                        max_outstanding=int(request.max_outstanding or 1),
                        dangerously_bypass=bool(request.dangerously_bypass),
                    )

                    result = {
                        "success": exit_code == 0,
                        "exit_code": exit_code,
                        "stdout": stdout,
                        "stderr": stderr,
                        "reason_code": reason_code,
                        "executor": "codex",
                        **(meta or {}),
                    }
                    return JSONResponse(content=result)
                except Exception as e:
                    logger.error(f"Codex run error: {e}", exc_info=True)
                    raise HTTPException(status_code=500, detail=str(e))

            @app.post("/codex/cancel")
            async def cancel_codex_run(request: CodexCancelRequest):
                """
                Best-effort cancel for a running /executor/codex/run batch.

                This is for the "leader AI must supervise and stop problematic CLIs" rule.
                """
                try:
                    rid = str(request.run_id or "").strip()
                    if not rid:
                        raise HTTPException(status_code=400, detail="run_id is required")
                    pid = str(request.parent_id or "").strip()
                    reason = str(request.reason or "")

                    # Persist cancel request (so watchdog/UI can stop long synchronous phases too).
                    try:
                        with self._run_task_lock:
                            m = self._cancel_requests.setdefault(rid, {})
                            targets = [pid] if pid else ["*"]
                            for t in targets:
                                m[t] = {"cancel_requested_utc": datetime.now(timezone.utc).isoformat(), "reason": reason}
                    except Exception:
                        pass

                    # Also write a cancel marker into artifacts dir (if we can locate it).
                    try:
                        base = (self.repo_root / "artifacts" / "codexcli_remote_runs" / rid).resolve()
                        if base.exists():
                            if pid:
                                step_dir = base / f"parent_{pid}"
                                step_dir.mkdir(parents=True, exist_ok=True)
                                (step_dir / "cancel_requested.json").write_text(
                                    json.dumps({"run_id": rid, "parent_id": pid, "reason": reason, "ts_utc": datetime.now(timezone.utc).isoformat()}, ensure_ascii=False, indent=2)
                                    + "\n",
                                    encoding="utf-8",
                                    errors="replace",
                                )
                            else:
                                (base / "cancel_requested.json").write_text(
                                    json.dumps({"run_id": rid, "reason": reason, "ts_utc": datetime.now(timezone.utc).isoformat()}, ensure_ascii=False, indent=2) + "\n",
                                    encoding="utf-8",
                                    errors="replace",
                                )
                    except Exception:
                        pass

                    # If we have a task handle, cancel it.
                    cancelled_tasks: list[str] = []
                    try:
                        with self._run_task_lock:
                            tmap = self._run_tasks.get(rid) or {}
                            if pid:
                                task = tmap.get(pid)
                                if task is not None:
                                    try:
                                        task.cancel()
                                        cancelled_tasks.append(pid)
                                    except Exception:
                                        pass
                            else:
                                for k, task in list(tmap.items()):
                                    if task is None:
                                        continue
                                    try:
                                        task.cancel()
                                        cancelled_tasks.append(str(k))
                                    except Exception:
                                        continue
                    except Exception:
                        pass

                    killed: list[dict[str, Any]] = []
                    not_found: list[str] = []
                    with self._run_proc_lock:
                        parents = self._run_procs.get(rid) or {}
                        targets = [pid] if pid else list(parents.keys())
                        for t in targets:
                            meta = parents.get(t)
                            if not isinstance(meta, dict) or not meta.get("pid"):
                                not_found.append(t)
                                continue
                            try:
                                p_int = int(meta["pid"])
                                proc = subprocess.run(
                                    ["taskkill", "/PID", str(p_int), "/T", "/F"],
                                    capture_output=True,
                                    text=True,
                                    encoding="utf-8",
                                    errors="replace",
                                    timeout=10,
                                )
                                killed.append(
                                    {
                                        "parent_id": t,
                                        "pid": p_int,
                                        "ok": int(proc.returncode or 0) == 0,
                                        "stdout": (proc.stdout or "").strip(),
                                        "stderr": (proc.stderr or "").strip(),
                                    }
                                )
                            except Exception as e:
                                killed.append({"parent_id": t, "pid": meta.get("pid"), "ok": False, "error": str(e)})
                        # If cancel all, drop run mapping.
                        if not pid and rid in self._run_procs:
                            self._run_procs.pop(rid, None)
                    return {
                        "ok": True,
                        "run_id": rid,
                        "parent_id": pid or None,
                        "reason": reason,
                        "killed": killed,
                        "not_found": not_found,
                        "cancelled_tasks": sorted(set(cancelled_tasks)),
                    }
                except HTTPException:
                    raise
                except Exception as e:
                    logger.error(f"cancel_codex_run error: {e}", exc_info=True)
                    raise HTTPException(status_code=500, detail=str(e))

            @app.post("/codex/parallel_probe")
            async def codex_parallel_probe(request: ParallelProbeRequest):
                """
                Token-free concurrency probe for the executor.
                Runs N short async jobs under the same max_outstanding gate and reports observed concurrency.
                """
                try:
                    import asyncio

                    n = int(request.n or 1)
                    if n < 1:
                        n = 1
                    if n > 64:
                        n = 64

                    limit = int(self.codex_config.get("max_outstanding_limit") or 1)
                    max_out = int(request.max_outstanding or 0) or n
                    if max_out < 1:
                        max_out = 1
                    if max_out > limit:
                        max_out = limit

                    sleep_ms = int(request.sleep_ms or 0)
                    if sleep_ms < 10:
                        sleep_ms = 10
                    if sleep_ms > 5000:
                        sleep_ms = 5000
                    sleep_s = float(sleep_ms) / 1000.0

                    run_id = str(int(time.time() * 1000))
                    out_dir = (self.repo_root / "artifacts" / "scc_state" / "parallel_probe" / run_id).resolve()
                    out_dir.mkdir(parents=True, exist_ok=True)

                    sem = asyncio.Semaphore(max_out)
                    lock = asyncio.Lock()
                    concurrent = 0
                    max_seen = 0
                    started = []
                    finished = []

                    async def _job(i: int):
                        nonlocal concurrent, max_seen
                        async with sem:
                            async with lock:
                                concurrent += 1
                                if concurrent > max_seen:
                                    max_seen = concurrent
                                started.append(i)
                            await asyncio.sleep(sleep_s)
                            (out_dir / f"job_{i:02d}.txt").write_text(
                                json.dumps({"i": i, "sleep_ms": sleep_ms}, ensure_ascii=False),
                                encoding="utf-8",
                            )
                            async with lock:
                                finished.append(i)
                                concurrent -= 1

                    t0 = time.time()
                    await asyncio.gather(*[_job(i) for i in range(1, n + 1)])
                    dt = time.time() - t0

                    payload = {
                        "ok": True,
                        "run_id": run_id,
                        "n": n,
                        "max_outstanding": max_out,
                        "max_concurrency_seen": max_seen,
                        "duration_s": dt,
                        "out_dir": str(out_dir),
                        "limit": limit,
                        "started_count": len(started),
                        "finished_count": len(finished),
                    }
                    (out_dir / "probe_result.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                    return JSONResponse(content=payload)
                except Exception as e:
                    logger.error(f"parallel_probe error: {e}", exc_info=True)
                    raise HTTPException(status_code=500, detail=str(e))

            @app.post("/opencode")
            async def run_opencode(request: OpenCodeRequest, background_tasks: BackgroundTasks):
                """运行 OpenCode CLI：执行单条子任务 prompt。"""
                try:
                    prompt = request.prompt
                    if not prompt:
                        raise HTTPException(status_code=400, detail="Prompt is required")

                    model, err = self._select_model(executor="opencode", requested=str(request.model or ""))
                    if err:
                        raise HTTPException(status_code=400, detail=err)
                    exit_code, stdout, stderr, reason_code, meta = await self._run_opencode_prompt(
                        prompt=prompt,
                        model=model,
                        dangerously_bypass=bool(request.dangerously_bypass),
                    )
                    result = {
                        "success": exit_code == 0,
                        "exit_code": exit_code,
                        "stdout": stdout,
                        "stderr": stderr,
                        "reason_code": reason_code,
                        "executor": "opencode",
                        **(meta or {}),
                    }
                    return JSONResponse(content=result)
                except Exception as e:
                    logger.error(f"OpenCode execution error: {e}", exc_info=True)
                    raise HTTPException(status_code=500, detail=str(e))

            @app.post("/opencode/run")
            async def run_opencode_batch(request: OpenCodeRunRequest, background_tasks: BackgroundTasks):
                """
                运行 OpenCode CLI（批量 run）：由客户端提交 parents.json_struct（不依赖客户端文件系统）。
                产物默认落盘到服务器 artifacts/opencodecli_remote_runs/<run_id>/ 下。
                """
                try:
                    if not request.parents:
                        raise HTTPException(status_code=400, detail="parents is required")

                    model, err = self._select_model(executor="opencode", requested=str(request.model or ""))
                    if err:
                        raise HTTPException(status_code=400, detail=err)
                    exit_code, stdout, stderr, reason_code, meta = await self._run_opencode_run(
                        parents=request.parents,
                        model=model,
                        timeout_s=float(request.timeout_s or 0.0),
                        max_outstanding=int(request.max_outstanding or 1),
                        dangerously_bypass=bool(request.dangerously_bypass),
                    )

                    result = {
                        "success": exit_code == 0,
                        "exit_code": exit_code,
                        "stdout": stdout,
                        "stderr": stderr,
                        "reason_code": reason_code,
                        "executor": "opencode",
                        **(meta or {}),
                    }
                    return JSONResponse(content=result)
                except Exception as e:
                    logger.error(f"OpenCode run error: {e}", exc_info=True)
                    raise HTTPException(status_code=500, detail=str(e))

            @app.get("/health")
            async def health():
                """健康检查"""
                codex_available = await self._check_codex_available()
                opencode_available = await self._check_opencode_available()
                
                return {
                    "status": "healthy",
                    "executors": {
                        "codex": "available" if codex_available else "unavailable",
                        "opencode": "available" if opencode_available else "unavailable",
                    }
                }
            
            @app.get("/status")
            async def status():
                """获取执行器状态"""
                with self.lock:
                    history_summary = {}
                    for task_id, history in self.task_execution_history.items():
                        history_summary[task_id] = {
                            "executions": len(history),
                            "last_execution": history[-1]["timestamp"] if history else None
                        }
                
                def _cfg_or_disabled(cfg: dict | None, keys: list[str]):
                    if cfg is None:
                        return "disabled"
                    out: dict[str, object] = {}
                    for k in keys:
                        if k in cfg:
                            out[k] = cfg[k]
                    return out

                return {
                    "status": "running",
                    "task_history": history_summary,
                    "active_runs": self._get_active_runs_status(),
                    "config": {
                        "codex": _cfg_or_disabled(
                            self.codex_config,
                            ["exe", "timeout", "model", "max_outstanding_limit"],
                        ),
                        "opencode": _cfg_or_disabled(
                            self.oc_config,
                            ["exe", "timeout", "model", "max_outstanding_limit"],
                        ),
                    }
                }
            
            # 测试端点
            @app.get("/")
            async def root():
                """执行器服务根路径"""
                return {
                    "service": "Executor Service",
                    "version": "1.0.0",
                    "status": "running",
                    "endpoints": [
                        "/codex",
                        "/health",
                        "/status"
                    ]
                }
            
            logger.info("Setting executor service app")
            self._app = app
            logger.info(f"Executor service app created: {self._app}")
            
            # 设置服务状态为就绪
            logger.info("Executor service initialized (registry will set status to READY)")
        except Exception as e:
            logger.error(f"Failed to initialize executor service: {e}", exc_info=True)
            # 确保服务状态设置为ERROR
            self.status = ServiceStatus.ERROR
            self.error = e
            logger.error(f"Executor service status set to ERROR: {self.status}, Error: {self.error}")
            raise
    
    async def shutdown(self) -> None:
        """关闭执行器服务"""
        logger.info("Executor service shutting down")
    
    def get_app(self) -> Any:
        """获取执行器应用"""
        logger.info(f"Getting executor app: {self._app}")
        return self._app

    async def _check_codex_available(self) -> bool:
        """检查 codex CLI 是否可用"""
        try:
            exe = self.codex_config["exe"]
            if not os.path.exists(exe) and os.path.exists(self.codex_config["cmd_fallback"]):
                exe = self.codex_config["cmd_fallback"]
            # codex 可能来自 PATH，因此仅验证能否执行（优先文件存在，否则尝试 which）
            if os.path.exists(exe):
                return True
            try:
                import shutil

                return shutil.which(str(exe)) is not None
            except Exception:
                return False
        except Exception:
            return False

    async def _run_codex_prompt(
        self,
        *,
        prompt: str,
        model: str,
        dangerously_bypass: bool = False,
    ) -> Tuple[int, str, str, str | None, Dict[str, Any]]:
        """运行 codex exec（单条 prompt），并将输入/输出落盘到 artifacts 下。"""
        import asyncio

        def _run_sync():
            exe = self.codex_config["exe"]
            if not os.path.exists(exe) and os.path.exists(self.codex_config["cmd_fallback"]):
                exe = self.codex_config["cmd_fallback"]

            run_id = str(int(time.time() * 1000))
            base = (self.repo_root / "artifacts" / "codexcli_remote_runs" / run_id)
            base.mkdir(parents=True, exist_ok=True)
            prompt_path = base / "prompt.txt"
            prompt_path.write_text(prompt, encoding="utf-8")

            stdout_path = base / "stdout.log"
            stderr_path = base / "stderr.log"

            if dangerously_bypass:
                args = [
                    exe,
                    "exec",
                    "--dangerously-bypass-approvals-and-sandbox",
                    "-C",
                    str(self.repo_root),
                    "-m",
                    model,
                    "-",
                ]
            else:
                args = [
                    exe,
                    "exec",
                    "--full-auto",
                    "--sandbox",
                    "workspace-write",
                    "-C",
                    str(self.repo_root),
                    "-m",
                    model,
                    "-",
                ]

            try:
                p = subprocess.run(
                    args,
                    cwd=str(self.repo_root),
                    input=prompt,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=int(self.codex_config["timeout"]),
                )
                stdout = p.stdout or ""
                stderr = p.stderr or ""
                stdout_path.write_text(stdout, encoding="utf-8", errors="replace")
                stderr_path.write_text(stderr, encoding="utf-8", errors="replace")

                reason_code = None
                if p.returncode != 0:
                    s = (stdout + "\n" + stderr).lower()
                    if "timeout" in s or "timed out" in s or "超时" in s:
                        reason_code = "EXECUTOR_TIMEOUT"
                    elif "login" in s or "auth" in s or "token" in s:
                        reason_code = "EXECUTOR_AUTH_ERROR"
                    else:
                        reason_code = "EXECUTOR_EXECUTION_ERROR"

                return p.returncode, stdout, stderr, reason_code, {
                    "run_id": run_id,
                    "server_artifacts_dir": str(base),
                    "prompt_file": str(prompt_path),
                    "stdout_file": str(stdout_path),
                    "stderr_file": str(stderr_path),
                    "model": model,
                    "dangerously_bypass": bool(dangerously_bypass),
                }
            except subprocess.TimeoutExpired:
                stdout_path.write_text("", encoding="utf-8")
                stderr_path.write_text("Timeout expired", encoding="utf-8")
                return 1, "", "Timeout expired", "EXECUTOR_TIMEOUT", {
                    "run_id": run_id,
                    "server_artifacts_dir": str(base),
                    "prompt_file": str(prompt_path),
                    "stdout_file": str(stdout_path),
                    "stderr_file": str(stderr_path),
                    "model": model,
                    "dangerously_bypass": bool(dangerously_bypass),
                }
            except Exception as e:
                stdout_path.write_text("", encoding="utf-8")
                stderr_path.write_text(f"Codex execution failed: {e}", encoding="utf-8", errors="replace")
                return 1, "", f"Codex execution failed: {e}", "EXECUTOR_ERROR", {
                    "run_id": run_id,
                    "server_artifacts_dir": str(base),
                    "prompt_file": str(prompt_path),
                    "stdout_file": str(stdout_path),
                    "stderr_file": str(stderr_path),
                    "model": model,
                    "dangerously_bypass": bool(dangerously_bypass),
                }

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _run_sync)

    async def _run_opencode_prompt(
        self,
        *, 
        prompt: str,
        model: str,
        dangerously_bypass: bool = False,
    ) -> Tuple[int, str, str, str | None, Dict[str, Any]]:
        """运行 OpenCode CLI（单条 prompt），并将输入/输出落盘到 artifacts 下。"""
        import asyncio

        def _run_sync():
            exe = self.oc_config["exe"]

            run_id = str(int(time.time() * 1000))
            base = (self.repo_root / "artifacts" / "opencodecli_remote_runs" / run_id)
            base.mkdir(parents=True, exist_ok=True)
            prompt_path = base / "prompt.txt"
            prompt_path.write_text(prompt, encoding="utf-8")

            stdout_path = base / "stdout.log"
            stderr_path = base / "stderr.log"

            # OpenCode CLI 使用 run 命令执行任务
            args = [
                exe,
                "run",
                "--model",
                model,
                prompt,
            ]

            try:
                p = subprocess.run(
                    args,
                    cwd=str(self.repo_root),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=int(self.oc_config["timeout"]),
                )
                stdout = p.stdout or ""
                stderr = p.stderr or ""
                stdout_path.write_text(stdout, encoding="utf-8", errors="replace")
                stderr_path.write_text(stderr, encoding="utf-8", errors="replace")

                reason_code = None
                if p.returncode != 0:
                    s = (stdout + "\n" + stderr).lower()
                    if "timeout" in s or "timed out" in s or "超时" in s:
                        reason_code = "EXECUTOR_TIMEOUT"
                    elif "login" in s or "auth" in s or "token" in s:
                        reason_code = "EXECUTOR_AUTH_ERROR"
                    else:
                        reason_code = "EXECUTOR_EXECUTION_ERROR"

                return p.returncode, stdout, stderr, reason_code, {
                    "run_id": run_id,
                    "server_artifacts_dir": str(base),
                    "prompt_file": str(prompt_path),
                    "stdout_file": str(stdout_path),
                    "stderr_file": str(stderr_path),
                    "model": model,
                    "dangerously_bypass": bool(dangerously_bypass),
                }
            except subprocess.TimeoutExpired:
                stdout_path.write_text("", encoding="utf-8")
                stderr_path.write_text("Timeout expired", encoding="utf-8")
                return 1, "", "Timeout expired", "EXECUTOR_TIMEOUT", {
                    "run_id": run_id,
                    "server_artifacts_dir": str(base),
                    "prompt_file": str(prompt_path),
                    "stdout_file": str(stdout_path),
                    "stderr_file": str(stderr_path),
                    "model": model,
                    "dangerously_bypass": bool(dangerously_bypass),
                }
            except Exception as e:
                stdout_path.write_text("", encoding="utf-8")
                stderr_path.write_text(f"OpenCode execution failed: {e}", encoding="utf-8", errors="replace")
                return 1, "", f"OpenCode execution failed: {e}", "EXECUTOR_ERROR", {
                    "run_id": run_id,
                    "server_artifacts_dir": str(base),
                    "prompt_file": str(prompt_path),
                    "stdout_file": str(stdout_path),
                    "stderr_file": str(stderr_path),
                    "model": model,
                    "dangerously_bypass": bool(dangerously_bypass),
                }

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _run_sync)

    async def _run_opencode_run(
        self,
        *, 
        parents: Dict[str, Any],
        model: str,
        timeout_s: float,
        max_outstanding: int,
        dangerously_bypass: bool = False,
    ) -> Tuple[int, str, str, str | None, Dict[str, Any]]:
        """批量运行 OpenCode CLI（支持 max_outstanding 并行），并返回聚合结果。"""
        import asyncio

        def _utc_now() -> str:
            return datetime.now(timezone.utc).isoformat()

        run_id = str(int(time.time() * 1000))
        base_dir = (self.repo_root / "artifacts" / "opencodecli_remote_runs" / run_id).resolve()
        base_dir.mkdir(parents=True, exist_ok=True)

        # 提取任务列表
        items = []
        if isinstance(parents, dict):
            items = parents.get("parents") or parents.get("tasks")
        if not isinstance(items, list):
            items = []

        # 执行所有任务
        results = []
        sem = asyncio.Semaphore(min(max_outstanding, int(self.oc_config["max_outstanding_limit"])))

        async def _run_single_task(task_data: dict, task_index: int):
            async with sem:
                task_id = str(task_data.get("id") or task_index)
                step_dir = base_dir / f"parent_{task_id}"
                step_dir.mkdir(parents=True, exist_ok=True)

                prompt = str(task_data.get("prompt") or task_data.get("instruction") or "")
                if not prompt:
                    return {
                        "task_id": task_id,
                        "success": False,
                        "exit_code": 1,
                        "stderr": "No prompt provided",
                        "reason_code": "EXECUTOR_ERROR",
                    }

                # 运行单个任务
                exit_code, stdout, stderr, reason_code, meta = await self._run_opencode_prompt(
                    prompt=prompt,
                    model=model,
                    dangerously_bypass=dangerously_bypass,
                )

                # 保存任务结果
                result = {
                    "task_id": task_id,
                    "success": exit_code == 0,
                    "exit_code": exit_code,
                    "stdout": stdout,
                    "stderr": stderr,
                    "reason_code": reason_code,
                    "meta": meta,
                }
                results.append(result)
                return result

        # 并行执行所有任务
        tasks = []
        for i, task_data in enumerate(items, 1):
            if isinstance(task_data, dict):
                tasks.append(_run_single_task(task_data, i))

        if tasks:
            await asyncio.gather(*tasks)

        # 生成聚合结果
        all_success = all(r.get("success") for r in results)
        exit_code = 0 if all_success else 1

        # 构建聚合输出
        stdout_lines = []
        stderr_lines = []
        for r in results:
            stdout_lines.append(f"=== Task {r.get('task_id')} ===")
            stdout_lines.append(r.get('stdout', ''))
            if r.get('stderr'):
                stderr_lines.append(f"=== Task {r.get('task_id')} ===")
                stderr_lines.append(r.get('stderr', ''))

        stdout = "\n\n".join(stdout_lines)
        stderr = "\n\n".join(stderr_lines)

        return exit_code, stdout, stderr, None, {
            "run_id": run_id,
            "server_artifacts_dir": str(base_dir),
            "tasks_count": len(results),
            "success_count": sum(1 for r in results if r.get('success')),
            "model": model,
            "max_outstanding": max_outstanding,
        }

    async def _check_opencode_available(self) -> bool:
        """检查 OpenCode CLI 是否可用。"""
        try:
            import subprocess
            exe = self.oc_config["exe"]
            p = subprocess.run(
                [exe, "--version"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            )
            return p.returncode == 0
        except Exception:
            return False

    async def _run_codex_run(
        self,
        *,
        parents: Dict[str, Any],
        model: str,
        timeout_s: float,
        max_outstanding: int,
        dangerously_bypass: bool = False,
    ) -> Tuple[int, str, str, str | None, Dict[str, Any]]:
        """批量运行 codex exec（支持 max_outstanding 并行），并返回聚合结果。"""
        import asyncio

        def _utc_now() -> str:
            return datetime.now(timezone.utc).isoformat()

        def _atomic_write_json(path: Path, payload: Any) -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", errors="replace")
            os.replace(tmp, path)

        def _atomic_write_text(path: Path, text: str) -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(text or "", encoding="utf-8", errors="replace")
            os.replace(tmp, path)

        def _safe_dir_component(s: str) -> str:
            s = (s or "").strip()
            if not s:
                return "unknown"
            out = []
            for ch in s:
                if ch.isalnum() or ch in ("_", "-", "."):
                    out.append(ch)
                else:
                    out.append("_")
            return "".join(out)[:120] or "unknown"

        def _normalize_repo_path(p: str) -> str:
            return (p or "").replace("\\", "/").lstrip("/").strip()

        def _write_parent_state(step_dir: Path, *, run_id: str, parent_id: str, phase: str, message: str = "", **extra: Any) -> None:
            payload = {
                "ts_utc": datetime.now(timezone.utc).isoformat(),
                "run_id": str(run_id),
                "parent_id": str(parent_id),
                "phase": str(phase or ""),
                "message": str(message or ""),
                **(extra or {}),
            }
            try:
                _atomic_write_json(step_dir / "status.json", payload)
            except Exception:
                pass
            try:
                (step_dir / "events.jsonl").parent.mkdir(parents=True, exist_ok=True)
                with open(step_dir / "events.jsonl", "a", encoding="utf-8", errors="replace") as f:
                    f.write(json.dumps(payload, ensure_ascii=False) + "\n")
            except Exception:
                pass

        def _is_cancel_requested(run_id: str, parent_id: str) -> bool:
            try:
                with self._run_task_lock:
                    m = self._cancel_requests.get(str(run_id)) or {}
                    if str(parent_id) in m:
                        return True
                    if "*" in m:
                        return True
            except Exception:
                return False
            return False

        def _iter_allowlisted_files(src_root: Path, allowed: list[str]) -> list[str]:
            """
            Return repo-relative file paths that currently exist under src_root and match allowlist.
            This includes git-untracked files (important because many SSOT files may be untracked locally).
            """
            import glob

            out: set[str] = set()
            root = src_root.resolve()
            if not allowed:
                return []

            # Safety: allowlists should be narrow. If they expand too broadly, fail fast rather than scanning the whole repo.
            MAX_MATCHES = 5000

            def _add_file(p: Path) -> None:
                nonlocal out
                try:
                    if not p.exists() or not p.is_file():
                        return
                    rel = _normalize_repo_path(str(p.relative_to(root)))
                    if rel:
                        out.add(rel)
                except Exception:
                    return

            for raw_pat in allowed:
                pat = _normalize_repo_path(raw_pat)
                if not pat:
                    continue

                # Directory prefix convention: "path/to/dir/" means all files under that dir.
                if pat.endswith("/"):
                    d = (root / pat[:-1]).resolve()
                    if d.exists() and d.is_dir():
                        for p in d.rglob("*"):
                            if p.is_file():
                                _add_file(p)
                                if len(out) > MAX_MATCHES:
                                    raise RuntimeError(f"allowlist_too_broad: >{MAX_MATCHES} matches (pattern={raw_pat})")
                    continue

                # Exact path (no glob metacharacters): file or directory.
                if not any(ch in pat for ch in ["*", "?", "["]):
                    p = (root / pat).resolve()
                    if p.exists() and p.is_file():
                        _add_file(p)
                    elif p.exists() and p.is_dir():
                        for q in p.rglob("*"):
                            if q.is_file():
                                _add_file(q)
                                if len(out) > MAX_MATCHES:
                                    raise RuntimeError(f"allowlist_too_broad: >{MAX_MATCHES} matches (path={raw_pat})")
                    continue

                # Glob pattern (recursive supported).
                gpat = str((root / pat.replace("/", os.sep)).resolve())
                for m in glob.glob(gpat, recursive=True):
                    _add_file(Path(m))
                    if len(out) > MAX_MATCHES:
                        raise RuntimeError(f"allowlist_too_broad: >{MAX_MATCHES} matches (glob={raw_pat})")

            return sorted(out)

        def _read_text_best_effort(path: Path) -> str:
            try:
                return path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                try:
                    return path.read_text()
                except Exception:
                    return ""

        def _truncate_text(s: str, *, max_chars: int) -> tuple[str, bool]:
            s = s or ""
            if max_chars <= 0 or len(s) <= max_chars:
                return s, False
            head = s[: max_chars // 2]
            tail = s[-(max_chars - len(head)) :]
            return head + "\n\n...[TRUNCATED]...\n\n" + tail, True

        def _extract_keywords(desc: str) -> list[str]:
            """
            Extract a small set of keywords from the task description for snippet search.
            Deterministic and conservative to avoid token blowups.
            """
            import re

            text = (desc or "").lower()
            # Keep only word-ish tokens.
            toks = re.findall(r"[a-z0-9_./-]{4,}", text)
            stop = {
                "task",
                "goal",
                "allowed",
                "changes",
                "update",
                "create",
                "docs",
                "tools",
                "file",
                "files",
                "must",
                "should",
                "with",
                "from",
                "into",
                "this",
                "that",
                "true",
                "false",
                "json",
                "yaml",
                "python",
                "powershell",
            }
            out: list[str] = []
            seen: set[str] = set()
            for t in toks:
                if t in stop:
                    continue
                if t.startswith("http"):
                    continue
                if t in seen:
                    continue
                # avoid paths that are too generic
                if t.count("/") >= 4 and not t.endswith((".py", ".md", ".json", ".ps1")):
                    continue
                seen.add(t)
                out.append(t)
                if len(out) >= 10:
                    break
            return out

        def _run_rg_snippets(*, cwd: Path, rel_path: str, keywords: list[str], context_lines: int = 2) -> list[str]:
            """
            Run ripgrep to extract small context snippets for keywords from a file.
            Falls back to no snippets if rg is unavailable.
            """
            if not keywords:
                return []
            try:
                import shutil

                if shutil.which("rg") is None:
                    return []
            except Exception:
                return []
            snippets: list[str] = []
            for kw in keywords:
                try:
                    p = subprocess.run(
                        ["rg", "-n", "-C", str(context_lines), kw, rel_path],
                        cwd=str(cwd),
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=8,
                    )
                    if p.returncode == 0 and (p.stdout or "").strip():
                        # Hard cap per keyword.
                        s, _ = _truncate_text(p.stdout, max_chars=2000)
                        snippets.append(f"rg: {kw}\n{s}".strip())
                except Exception:
                    continue
                if len(snippets) >= 6:
                    break
            return snippets

        def _build_context_snippet_pack(
            *,
            repo_root: Path,
            allowed_globs: list[str],
            desc: str,
            embed_paths: list[str] | None,
            max_files: int = 4,
            max_total_chars: int = 45_000,
            head_lines: int = 80,
            tail_lines: int = 40,
        ) -> str:
            """
            Token-saving pack: for each selected file, include header+tail+rg hits only (not full file).
            This is meant for non-codex models that cannot run shell/file access inside CodexCLI.
            """
            if not allowed_globs:
                return ""
            keywords = _extract_keywords(desc)

            candidates: list[str] = []
            if embed_paths:
                candidates = [_normalize_repo_path(p) for p in embed_paths if _normalize_repo_path(p)]
            else:
                # Prefer the most likely files (mentioned in desc) then smaller md/py/json/ps1.
                all_files = _iter_allowlisted_files(repo_root, allowed_globs)
                mentioned = []
                d = (desc or "")
                for f in all_files:
                    if f and f in d:
                        mentioned.append(f)
                mentioned = sorted(set(mentioned))
                prefer = [p for p in all_files if p.endswith((".md", ".py", ".json", ".ps1"))]
                prefer = [p for p in prefer if p not in set(mentioned)]
                candidates = mentioned + prefer

            picked: list[str] = []
            total = 0
            for rel in candidates:
                if len(picked) >= max_files:
                    break
                p = (repo_root / rel).resolve()
                if not p.exists() or not p.is_file():
                    continue
                # per-file rough budget (header+tail+snippets)
                if total >= max_total_chars:
                    break
                picked.append(rel)
                total += 1

            if not picked:
                return ""

            parts: list[str] = []
            parts.append("Context snippets (read-only; keep output as a git patch only):")
            for rel in picked:
                p = (repo_root / rel).resolve()
                raw = _read_text_best_effort(p)
                lines = raw.splitlines()
                head = "\n".join(lines[:head_lines])
                tail = "\n".join(lines[-tail_lines:]) if len(lines) > head_lines else ""
                rg_hits = _run_rg_snippets(cwd=repo_root, rel_path=rel, keywords=keywords, context_lines=2)
                parts.append(f"\nFILE: {rel}")
                # IMPORTANT: keep section markers OUTSIDE fenced blocks to avoid "marker pollution" in patches.
                if head.strip():
                    h, _ = _truncate_text(head, max_chars=12_000)
                    parts.append("HEAD:")
                    parts.append("```text")
                    parts.append(h)
                    parts.append("```")
                if rg_hits:
                    r = "\n\n".join(rg_hits).strip()
                    r, _ = _truncate_text(r, max_chars=12_000)
                    if r:
                        parts.append("RG_HITS:")
                        parts.append("```text")
                        parts.append(r)
                        parts.append("```")
                if tail.strip():
                    t, _ = _truncate_text(tail, max_chars=12_000)
                    parts.append("TAIL:")
                    parts.append("```text")
                    parts.append(t)
                    parts.append("```")
            pack = "\n".join(parts).strip() + "\n"
            pack, _ = _truncate_text(pack, max_chars=max_total_chars)
            return pack

        def _load_ssot_registry(repo_root: Path) -> dict:
            try:
                p = (repo_root / "docs" / "ssot" / "registry.json").resolve()
                if not p.exists():
                    p = (repo_root / "docs" / "ssot" / "_registry.json").resolve()
                if not p.exists():
                    return {}
                return json.loads(p.read_text(encoding="utf-8", errors="replace") or "{}")
            except Exception:
                return {}

        def _select_context_paths_from_registry(
            *,
            repo_root: Path,
            allowed_globs: list[str],
            desc: str,
            max_candidates: int = 40,
        ) -> tuple[list[str], dict[str, Any]]:
            """
            Deterministic SSOT search:
            - Use docs/ssot/registry.json as a small "index" to pick the most relevant docs.
            - Only returns paths that exist AND match allowed_globs.
            """
            reg = _load_ssot_registry(repo_root)
            if not isinstance(reg, dict) or not allowed_globs:
                return [], {"source": "registry", "ok": False, "reason": "missing_registry_or_allowlist"}

            # Build metadata map for scoring (path -> {doc_id,title})
            meta_by_path: dict[str, dict[str, str]] = {}
            candidates: list[str] = []

            def _add_path(rel: str, *, doc_id: str = "", title: str = "") -> None:
                rel2 = _normalize_repo_path(rel)
                if not rel2:
                    return
                if not _match_any(rel2, allowed_globs):
                    return
                rp = (repo_root / rel2).resolve()
                if not rp.exists() or not rp.is_file():
                    return
                candidates.append(rel2)
                if doc_id or title:
                    meta_by_path.setdefault(rel2, {"doc_id": str(doc_id or ""), "title": str(title or "")})

            # Prefer registry-defined canonical docs and context order.
            ctx = reg.get("context_assembly") if isinstance(reg.get("context_assembly"), dict) else {}
            default_order = ctx.get("default_order") if isinstance(ctx.get("default_order"), list) else []
            for p in default_order:
                if isinstance(p, str) and p.strip():
                    _add_path(p.strip())

            canonical = reg.get("canonical") if isinstance(reg.get("canonical"), list) else []
            for item in canonical:
                if not isinstance(item, dict):
                    continue
                p = item.get("canonical_path")
                if isinstance(p, str) and p.strip():
                    _add_path(p.strip(), doc_id=str(item.get("doc_id") or ""), title=str(item.get("title") or ""))

            # De-dupe while preserving order.
            seen: set[str] = set()
            deduped: list[str] = []
            for p in candidates:
                if p not in seen:
                    deduped.append(p)
                    seen.add(p)
            candidates = deduped

            # Score candidates deterministically
            keywords = [k.lower() for k in _extract_keywords(desc)]
            dlow = (desc or "").lower()

            scored: list[tuple[int, str]] = []
            for rel in candidates:
                base = rel.lower()
                m = meta_by_path.get(rel) or {}
                doc_id = str(m.get("doc_id") or "").lower()
                title = str(m.get("title") or "").lower()

                s = 0
                if rel in (desc or ""):
                    s += 20
                if doc_id and doc_id in dlow:
                    s += 20
                for kw in keywords:
                    if not kw:
                        continue
                    if kw in base:
                        s += 8
                    if doc_id and kw in doc_id:
                        s += 10
                    if title and kw in title:
                        s += 6
                # Slight boost for "TOP chain" docs to keep system stable.
                if rel.endswith("docs/ssot/02_architecture/SCC_TOP.md") or rel.endswith("docs/START_HERE.md"):
                    s += 4
                scored.append((s, rel))

            scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
            picked = [rel for s, rel in scored if s > 0][: max_candidates]
            debug = {
                "source": "registry",
                "ok": True,
                "candidates": len(candidates),
                "picked": picked,
                "top_scores": [{"path": rel, "score": s} for s, rel in scored[: min(12, len(scored))]],
            }
            return picked, debug

        def _select_context_files(
            *,
            repo_root: Path,
            allowed_globs: list[str],
            desc: str,
            embed_paths: list[str] | None,
            max_files: int,
        ) -> tuple[list[str], dict[str, Any]]:
            """
            Select up to max_files repo-relative files to embed snippets for.
            Deterministic priority:
            1) explicit embed_paths
            2) registry-ranked docs (within allowlist)
            3) fallback: allowlisted md/py/json/ps1 files (mentioned in desc first)
            """
            if embed_paths:
                normalized = [_normalize_repo_path(p) for p in embed_paths if _normalize_repo_path(p)]
                normalized = [p for p in normalized if _match_any(p, allowed_globs)]
                return normalized[:max_files], {"source": "explicit", "picked": normalized[:max_files]}

            reg_picked, reg_dbg = _select_context_paths_from_registry(
                repo_root=repo_root,
                allowed_globs=allowed_globs,
                desc=desc,
                max_candidates=max_files,
            )
            if reg_picked:
                return reg_picked[:max_files], reg_dbg

            all_files = _iter_allowlisted_files(repo_root, allowed_globs)
            mentioned = []
            d = (desc or "")
            for f in all_files:
                if f and f in d:
                    mentioned.append(f)
            mentioned = sorted(set(mentioned))
            prefer = [p for p in all_files if p.endswith((".md", ".py", ".json", ".ps1"))]
            prefer = [p for p in prefer if p not in set(mentioned)]
            picked = (mentioned + prefer)[:max_files]
            return picked, {"source": "fallback_allowlist", "picked": picked, "allowlist_files": len(all_files)}

        def _build_embedded_files_section(
            *,
            repo_root: Path,
            allowed_globs: list[str],
            embed_paths: list[str] | None,
            max_files: int = 6,
            max_total_chars: int = 120_000,
            max_file_chars: int = 24_000,
        ) -> str:
            """
            Embed a read-only snapshot of relevant files into the prompt so the model can produce a patch
            even when shell/file access is policy-blocked in CodexCLI.
            """
            candidates: list[str] = []
            if embed_paths:
                candidates = [_normalize_repo_path(p) for p in embed_paths if _normalize_repo_path(p)]
            else:
                # Prefer smaller, more relevant files first.
                all_files = _iter_allowlisted_files(repo_root, allowed_globs)
                prefer = [p for p in all_files if p.endswith((".md", ".py", ".json", ".ps1"))]
                rest = [p for p in all_files if p not in set(prefer)]
                candidates = prefer + rest

            picked: list[str] = []
            total = 0
            for rel in candidates:
                if len(picked) >= max_files:
                    break
                try:
                    p = (repo_root / rel).resolve()
                    if not p.exists() or not p.is_file():
                        continue
                    size = int(p.stat().st_size)
                except Exception:
                    continue
                # rough sizing gate
                if total + min(size, max_file_chars) > max_total_chars:
                    continue
                picked.append(rel)
                total += min(size, max_file_chars)

            if not picked:
                return ""

            parts: list[str] = []
            parts.append("Context files (read-only snapshot; may be truncated):")
            for rel in picked:
                p = (repo_root / rel).resolve()
                raw = _read_text_best_effort(p)
                txt, truncated = _truncate_text(raw, max_chars=max_file_chars)
                parts.append(f"\nFILE: {rel}")
                parts.append("```text")
                parts.append(txt)
                parts.append("```")
                if truncated:
                    parts.append("(note: truncated)")
            return "\n".join(parts).strip() + "\n"

        def _sync_allowlisted_from_repo_to_worktree(*, repo_root: Path, worktree_root: Path, allowed: list[str]) -> None:
            """
            Copy existing allowlisted files from repo_root into worktree_root so the worker can see them,
            even if those files are git-untracked.
            """
            if not allowed:
                return
            for rel in _iter_allowlisted_files(repo_root, allowed):
                try:
                    src = (repo_root / rel).resolve()
                    dst = (worktree_root / rel).resolve()
                    if not src.exists() or not src.is_file():
                        continue
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    dst.write_bytes(src.read_bytes())
                except Exception:
                    continue

        def _file_sha256(path: Path) -> str:
            import hashlib

            h = hashlib.sha256()
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(1024 * 1024), b""):
                    h.update(chunk)
            return h.hexdigest()

        def _compute_allowlisted_touched(*, repo_root: Path, worktree_root: Path, allowed: list[str]) -> tuple[list[str], list[str]]:
            """
            Determine touched paths under allowlist by comparing current repo_root vs worktree_root.
            Returns: (modified_or_added, deleted)
            """
            touched: list[str] = []

            # Candidates are limited to allowlist expansions (fast, deterministic), not a full tree scan.
            candidates: set[str] = set()
            if allowed:
                for rel in _iter_allowlisted_files(repo_root, allowed):
                    candidates.add(rel)
                for rel in _iter_allowlisted_files(worktree_root, allowed):
                    candidates.add(rel)

            for rel in sorted(candidates):
                try:
                    src = (repo_root / rel).resolve()
                    dst = (worktree_root / rel).resolve()
                    if not src.exists():
                        if dst.exists():
                            touched.append(rel)
                    else:
                        if not dst.exists():
                            # deletion handled below
                            continue
                        if _file_sha256(src) != _file_sha256(dst):
                            touched.append(rel)
                except Exception:
                    touched.append(rel)

            deleted: list[str] = []
            for rel in _iter_allowlisted_files(repo_root, allowed):
                try:
                    if not (worktree_root / rel).exists():
                        deleted.append(rel)
                except Exception:
                    continue

            return sorted(set(touched)), sorted(set(deleted))

        def _match_any(path: str, patterns: list[str]) -> bool:
            path = _normalize_repo_path(path)
            for pat in patterns:
                pat = _normalize_repo_path(pat)
                if not pat:
                    continue
                if pat.endswith("/") and path.startswith(pat):
                    return True
                if fnmatch.fnmatchcase(path, pat):
                    return True
            return False

        def _parse_allowed_globs(desc: str) -> list[str]:
            """
            Best-effort parse of an allowlist from a parent description.

            We treat an explicit "Allowed file changes:" section as authoritative.
            Example:
              Allowed file changes:
              - Create: docs/CANONICAL/GOALS.md
              - Update: docs/ssot/02_architecture/canonical_truth.md
            """
            lines = [l.rstrip("\n") for l in (desc or "").splitlines()]
            allowed: list[str] = []
            in_section = False
            for raw in lines:
                line = raw.strip()
                if not line:
                    if in_section and allowed:
                        break
                    continue
                if line.lower().startswith("allowed file changes"):
                    in_section = True
                    continue
                if not in_section:
                    continue
                if line.startswith("-"):
                    # "- Create: path" / "- Update: path"
                    if ":" in line:
                        tail = line.split(":", 1)[1].strip()
                        if tail:
                            allowed.append(tail)
                else:
                    # section ended by first non-bullet line after starting
                    if allowed:
                        break
            # normalize and de-dupe
            out: list[str] = []
            seen: set[str] = set()
            for p in allowed:
                p2 = _normalize_repo_path(p)
                if p2 and p2 not in seen:
                    out.append(p2)
                    seen.add(p2)
            return out

        def _run_git(args: list[str], *, cwd: Path, timeout: float = 60.0) -> tuple[int, str, str]:
            try:
                p = subprocess.run(
                    ["git", *args],
                    cwd=str(cwd),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=timeout,
                )
                return int(p.returncode or 0), p.stdout or "", p.stderr or ""
            except Exception as e:
                return 1, "", str(e)

        def _ensure_worktree(worktree_dir: Path) -> tuple[bool, str]:
            """
            Create a detached worktree for this parent under artifacts/codexcli_remote_runs/<run_id>/worktrees/.
            """
            worktree_dir = worktree_dir.resolve()
            with self._worktree_lock:
                if worktree_dir.exists():
                    _run_git(["worktree", "remove", "--force", str(worktree_dir)], cwd=self.repo_root, timeout=120.0)
                worktree_dir.parent.mkdir(parents=True, exist_ok=True)
                code, _, err = _run_git(
                    ["worktree", "add", "--detach", str(worktree_dir), "HEAD"],
                    cwd=self.repo_root,
                    timeout=120.0,
                )
                if code != 0:
                    return False, err or "git worktree add failed"
            return True, ""

        exe = self.codex_config["exe"]
        if not os.path.exists(exe) and os.path.exists(self.codex_config["cmd_fallback"]):
            exe = self.codex_config["cmd_fallback"]

        run_id = str(int(time.time() * 1000))
        base = (self.repo_root / "artifacts" / "codexcli_remote_runs" / run_id)
        base.mkdir(parents=True, exist_ok=True)
        parents_path = base / "parents.json"
        parents_path.write_text(json.dumps(parents, ensure_ascii=False, indent=2), encoding="utf-8", errors="replace")

        items = parents.get("parents") if isinstance(parents, dict) else None
        if not isinstance(items, list):
            items = parents.get("tasks") if isinstance(parents, dict) else None
        if not isinstance(items, list):
            raise ValueError("parents must include a list at key 'parents' (or 'tasks')")

        effective_timeout = int(timeout_s) if timeout_s and timeout_s > 0 else int(self.codex_config["timeout"])
        effective_timeout = max(60, effective_timeout)

        limit = int(self.codex_config.get("max_outstanding_limit") or 1)
        limit = max(1, limit)
        effective_max_outstanding = max(1, int(max_outstanding or 1))
        effective_max_outstanding = min(effective_max_outstanding, limit)

        run_manifest_path = base / "run_manifest.json"
        parent_entries: list[dict[str, Any]] = []
        for idx, parent in enumerate(items, 1):
            pid = str(parent.get("id", idx))
            parent_dir = base / f"parent_{_safe_dir_component(pid)}"
            parent_entries.append(
                {
                    "id": pid,
                    "start": None,
                    "end": None,
                    "exit_code": None,
                    "artifacts_dir": str(parent_dir),
                }
            )

        manifest: dict[str, Any] = {
            "run_id": run_id,
            "start": _utc_now(),
            "end": None,
            "server_artifacts_dir": str(base),
            "parents_file": str(parents_path),
            "model": model,
            "timeout_s": effective_timeout,
            "max_outstanding": effective_max_outstanding,
            "dangerously_bypass": bool(dangerously_bypass),
            "parents": parent_entries,
        }
        _atomic_write_json(run_manifest_path, manifest)
        self._track_active_run(run_id, str(run_manifest_path))
        self._touch_active_run(run_id)

        semaphore = asyncio.Semaphore(effective_max_outstanding)
        manifest_lock = asyncio.Lock()

        results: list[dict[str, Any]] = []
        combined_stdout: list[str] = []
        combined_stderr: list[str] = []

        async def _run_one(idx: int, parent: dict[str, Any]) -> None:
            pid = str(parent.get("id", idx))
            desc = str(parent.get("description") or parent.get("title") or parent.get("task") or "").strip()
            explicit_allowed = parent.get("allowed_globs")
            require_changes = bool(parent.get("require_changes")) or bool(parent.get("require_change"))
            embed_files = bool(parent.get("embed_allowlisted_files")) or bool(parent.get("embed_files"))
            embed_paths = parent.get("embed_paths")
            if not isinstance(embed_paths, list):
                embed_paths = None
            # Token budget knobs (leader-controlled): keep prompts small/deterministic.
            try:
                context_max_files = int(parent.get("context_max_files") or 4)
            except Exception:
                context_max_files = 4
            try:
                context_max_total_chars = int(parent.get("context_max_total_chars") or 45_000)
            except Exception:
                context_max_total_chars = 45_000
            try:
                context_head_lines = int(parent.get("context_head_lines") or 80)
            except Exception:
                context_head_lines = 80
            try:
                context_tail_lines = int(parent.get("context_tail_lines") or 40)
            except Exception:
                context_tail_lines = 40

            context_max_files = max(1, min(8, context_max_files))
            context_max_total_chars = max(8_000, min(120_000, context_max_total_chars))
            context_head_lines = max(20, min(200, context_head_lines))
            context_tail_lines = max(10, min(120, context_tail_lines))
            allowed_globs: list[str] = []
            if isinstance(explicit_allowed, list):
                allowed_globs = [str(x) for x in explicit_allowed if str(x).strip()]
            if not allowed_globs:
                allowed_globs = _parse_allowed_globs(desc)
            isolate = bool(parent.get("isolate_worktree")) or bool(allowed_globs) or bool(dangerously_bypass)
            ctx_chosen: list[str] | None = None
            ctx_dbg: dict[str, Any] = {}
            prompt = (
                "你正在执行一个分解过后的子任务（子任务之间可独立执行）。\n"
                "只完成本条子任务；如果需要修改代码，请直接在工作区修改并保持变更最小。\n"
                "不要运行任何 shell/PowerShell/外部命令；本任务提供了确定性的上下文片段用于修改。\n"
                "如果你的执行环境无法直接写文件：请只输出一个可由 `git apply` 应用的 unified diff patch（以 `diff --git a/` 开头），不要使用 `*** Begin Patch` 格式，也不要输出长篇解释。\n"
                f"子任务ID: {pid}\n"
                "子任务内容:\n"
                f"{desc}\n"
            )
            if embed_files and allowed_globs:
                try:
                    ctx_chosen, ctx_dbg = _select_context_files(
                        repo_root=self.repo_root,
                        allowed_globs=allowed_globs,
                        desc=desc,
                        embed_paths=embed_paths,
                        max_files=context_max_files,
                    )
                    # Prefer snippet pack to reduce token burn for gpt-5.2.
                    prompt += "\n" + _build_context_snippet_pack(
                        repo_root=self.repo_root,
                        allowed_globs=allowed_globs,
                        desc=desc,
                        embed_paths=ctx_chosen,
                        max_files=context_max_files,
                        max_total_chars=context_max_total_chars,
                        head_lines=context_head_lines,
                        tail_lines=context_tail_lines,
                    )
                except Exception:
                    pass

            step_dir = base / f"parent_{_safe_dir_component(pid)}"
            prompt_path = step_dir / "prompt.txt"

            try:
                step_dir.mkdir(parents=True, exist_ok=True)
                _write_parent_state(step_dir, run_id=str(run_id), parent_id=str(pid), phase="prepare", message="prompt_write")

                if embed_files and allowed_globs:
                    try:
                        _atomic_write_json(
                            step_dir / "context_selection.json",
                            {
                                "ts_utc": _utc_now(),
                                "parent_id": pid,
                                "allowed_globs": allowed_globs,
                                "context_budget": {
                                    "max_files": context_max_files,
                                    "max_total_chars": context_max_total_chars,
                                    "head_lines": context_head_lines,
                                    "tail_lines": context_tail_lines,
                                },
                                "selection": ctx_dbg,
                            },
                        )
                    except Exception:
                        pass

                prompt_path.write_text(prompt, encoding="utf-8", errors="replace")

                # Register task handle for best-effort cancellation from leader/watchdog.
                try:
                    with self._run_task_lock:
                        run_map = self._run_tasks.setdefault(str(run_id), {})
                        run_map[str(pid)] = asyncio.current_task()
                except Exception:
                    pass

                if _is_cancel_requested(str(run_id), str(pid)):
                    raise asyncio.CancelledError()

                if embed_files and not allowed_globs:
                    # Hard-stop: deterministic context embedding requires an explicit allowlist
                    # to avoid accidental broad scans and token burn.
                    _write_parent_state(step_dir, run_id=str(run_id), parent_id=str(pid), phase="blocked", message="missing_allowlist_for_context")
                    (step_dir / "stdout.log").write_text("", encoding="utf-8")
                    (step_dir / "stderr.log").write_text(
                        "embed_allowlisted_files=true requires non-empty allowed_globs[] (scope+token hard-stop).",
                        encoding="utf-8",
                        errors="replace",
                    )
                    _atomic_write_json(
                        step_dir / "context_selection.json",
                        {
                            "ts_utc": _utc_now(),
                            "parent_id": pid,
                            "error": "missing_allowlist_for_context",
                            "note": "Set allowed_globs[] on this parent to enable deterministic context selection.",
                        },
                    )
                    _atomic_write_json(
                        step_dir / "scope_enforcement.json",
                        {
                            "ts_utc": _utc_now(),
                            "parent_id": pid,
                            "dangerously_bypass": bool(dangerously_bypass),
                            "isolate_worktree": True,
                            "allowed_globs": [],
                            "touched_paths": [],
                            "violations": ["MISSING_ALLOWED_GLOBS_FOR_CONTEXT"],
                            "apply_ok": False,
                            "error": "missing_allowlist_for_context",
                        },
                    )
                    async with manifest_lock:
                        manifest["parents"][idx - 1]["start"] = _utc_now()
                        manifest["parents"][idx - 1]["end"] = _utc_now()
                        manifest["parents"][idx - 1]["exit_code"] = 1
                        manifest["parents"][idx - 1]["artifacts_dir"] = str(step_dir)
                        _atomic_write_json(run_manifest_path, manifest)
                    self._touch_active_run(run_id)
                    results.append(
                        {
                            "id": pid,
                            "exit_code": 1,
                            "artifacts_dir": str(step_dir),
                            "prompt_file": str(prompt_path),
                            "dangerously_bypass": bool(dangerously_bypass),
                            "error": "missing_allowlist_for_context",
                        }
                    )
                    combined_stderr.append(
                        f"\n--- parent {pid} stderr ---\nmissing_allowlist_for_context (embed_allowlisted_files requires allowed_globs[])"
                    )
                    return

                if dangerously_bypass and not allowed_globs:
                    # Defense-in-depth: the API layer rejects this already, but keep a hard stop here.
                    _write_parent_state(step_dir, run_id=str(run_id), parent_id=str(pid), phase="blocked", message="missing_allowlist")
                    (step_dir / "stdout.log").write_text("", encoding="utf-8")
                    (step_dir / "stderr.log").write_text(
                        "dangerously_bypass requires explicit allowed_globs (scope enforcement hard-stop).",
                        encoding="utf-8",
                        errors="replace",
                    )
                    _atomic_write_json(
                        step_dir / "scope_enforcement.json",
                        {
                            "ts_utc": _utc_now(),
                            "parent_id": pid,
                            "dangerously_bypass": True,
                            "isolate_worktree": True,
                            "allowed_globs": [],
                            "touched_paths": [],
                            "violations": ["MISSING_ALLOWED_GLOBS"],
                            "apply_ok": False,
                            "error": "missing_allowlist",
                        },
                    )
                    async with manifest_lock:
                        manifest["parents"][idx - 1]["start"] = _utc_now()
                        manifest["parents"][idx - 1]["end"] = _utc_now()
                        manifest["parents"][idx - 1]["exit_code"] = 1
                        manifest["parents"][idx - 1]["artifacts_dir"] = str(step_dir)
                        _atomic_write_json(run_manifest_path, manifest)
                    self._touch_active_run(run_id)
                    results.append(
                        {
                            "id": pid,
                            "exit_code": 1,
                            "artifacts_dir": str(step_dir),
                            "prompt_file": str(prompt_path),
                            "dangerously_bypass": True,
                            "error": "missing_allowlist",
                        }
                    )
                    combined_stderr.append(f"\n--- parent {pid} stderr ---\nmissing_allowlist (dangerously_bypass requires allowed_globs)")
                    return

                worktree_dir = (base / "worktrees" / f"parent_{_safe_dir_component(pid)}").resolve()
                worktree_ok = True
                worktree_err = ""
                if isolate:
                    _write_parent_state(step_dir, run_id=str(run_id), parent_id=str(pid), phase="prepare", message="worktree_setup")
                    worktree_ok, worktree_err = _ensure_worktree(worktree_dir)

                run_root = self.repo_root
                cwd_dir = self.repo_root
                if isolate and worktree_ok:
                    # Ensure allowlisted files exist in the worktree (even if untracked in git).
                    _write_parent_state(step_dir, run_id=str(run_id), parent_id=str(pid), phase="prepare", message="sync_allowlisted_to_worktree")
                    _sync_allowlisted_from_repo_to_worktree(repo_root=self.repo_root, worktree_root=worktree_dir, allowed=allowed_globs)
                    run_root = worktree_dir
                    cwd_dir = worktree_dir

                if dangerously_bypass:
                    args = [
                        exe,
                        "exec",
                        "--dangerously-bypass-approvals-and-sandbox",
                        "-C",
                        str(run_root),
                        "-m",
                        model,
                        "-",
                    ]
                else:
                    args = [
                        exe,
                        "exec",
                        "--full-auto",
                        "--sandbox",
                        "workspace-write",
                        "-C",
                        str(run_root),
                        "-m",
                        model,
                        "-",
                    ]

                async with semaphore:
                    start = _utc_now()
                    async with manifest_lock:
                        manifest["parents"][idx - 1]["start"] = start
                        _atomic_write_json(run_manifest_path, manifest)
                    self._touch_active_run(run_id)

                    exit_code = 1
                    stdout = ""
                    stderr = ""
                    error: str | None = None
                    scope_meta: dict[str, Any] = {}
                    try:
                        if isolate and not worktree_ok:
                            error = "worktree_failed"
                            stdout = ""
                            stderr = f"Worktree setup failed: {worktree_err}"
                            exit_code = 1
                        else:
                            _write_parent_state(
                                step_dir,
                                run_id=str(run_id),
                                parent_id=str(pid),
                                phase="running_model",
                                message="codex_exec_start",
                                model=str(model),
                                sandbox="workspace-write" if not dangerously_bypass else "bypass",
                            )
                            proc = await asyncio.create_subprocess_exec(
                                *args,
                                cwd=str(cwd_dir),
                                stdin=asyncio.subprocess.PIPE,
                                stdout=asyncio.subprocess.PIPE,
                                stderr=asyncio.subprocess.PIPE,
                            )
                            # Track child pid for supervision/cancel.
                            try:
                                with self._run_proc_lock:
                                    run_map = self._run_procs.setdefault(str(run_id), {})
                                    run_map[str(pid)] = {"pid": int(proc.pid), "started_utc": start}
                            except Exception:
                                pass
                            try:
                                _atomic_write_json(step_dir / "proc.json", {"pid": int(proc.pid), "started_utc": start, "args": args, "cwd": str(cwd_dir)})
                            except Exception:
                                pass
                            try:
                                async def _heartbeat() -> None:
                                    # Emit a lightweight heartbeat so leader watchdog can distinguish
                                    # "still running" vs "no reaction" without relying on model stdout.
                                    while True:
                                        await asyncio.sleep(30.0)
                                        try:
                                            if proc.returncode is not None:
                                                return
                                        except Exception:
                                            return
                                        try:
                                            if _is_cancel_requested(str(run_id), str(pid)):
                                                return
                                        except Exception:
                                            pass
                                        try:
                                            _write_parent_state(
                                                step_dir,
                                                run_id=str(run_id),
                                                parent_id=str(pid),
                                                phase="running_model",
                                                message="heartbeat",
                                                model=str(model),
                                            )
                                            self._touch_active_run(run_id)
                                        except Exception:
                                            # Best-effort only; do not fail the run.
                                            pass

                                hb_task = asyncio.create_task(_heartbeat())
                                try:
                                    out_b, err_b = await asyncio.wait_for(
                                        proc.communicate(prompt.encode("utf-8")),
                                        timeout=effective_timeout,
                                    )
                                finally:
                                    try:
                                        hb_task.cancel()
                                    except Exception:
                                        pass
                                stdout = (out_b or b"").decode("utf-8", errors="replace")
                                stderr = (err_b or b"").decode("utf-8", errors="replace")
                                exit_code = int(proc.returncode or 0)
                                _write_parent_state(
                                    step_dir,
                                    run_id=str(run_id),
                                    parent_id=str(pid),
                                    phase="model_done",
                                    message="codex_exec_done",
                                    exit_code=exit_code,
                                )
                            except asyncio.TimeoutError:
                                error = "timeout"
                                try:
                                    proc.kill()
                                except Exception:
                                    pass
                                try:
                                    await proc.wait()
                                except Exception:
                                    pass
                                stdout = ""
                                stderr = "Timeout expired"
                                exit_code = 1
                                _write_parent_state(step_dir, run_id=str(run_id), parent_id=str(pid), phase="timeout", message="codex_exec_timeout")
                            finally:
                                try:
                                    with self._run_proc_lock:
                                        if str(run_id) in self._run_procs and str(pid) in self._run_procs[str(run_id)]:
                                            self._run_procs[str(run_id)].pop(str(pid), None)
                                        if str(run_id) in self._run_procs and not self._run_procs[str(run_id)]:
                                            self._run_procs.pop(str(run_id), None)
                                except Exception:
                                    pass
                    except Exception as e:
                        error = "executor_error"
                        stdout = ""
                        stderr = f"Codex execution failed: {e}"
                        exit_code = 1

                    patch_file = None
                    # Default to "no-op is ok" (fail-closed is enforced by require_changes when desired).
                    # Many parents are "verify" or "triage" steps where no workspace changes are expected.
                    apply_ok = True
                    apply_error = ""
                    violations: list[str] = []
                    applied_any_changes = False

                    def _extract_git_patch(text: str) -> str:
                        """
                        Extract a `git apply` compatible patch from stdout/stderr when the model cannot edit files.
                        Returns empty string if not found.
                        """
                        if not text:
                            return ""
                        lines = text.splitlines()
                        start = None
                        for i, line in enumerate(lines):
                            if line.startswith("diff --git a/"):
                                start = i
                                break
                        if start is None:
                            return ""
                        patch = "\n".join(lines[start:]).strip() + "\n"
                        # Hard cap to avoid accidental huge outputs.
                        if len(patch.encode("utf-8", errors="replace")) > 2 * 1024 * 1024:
                            return ""
                        return patch

                    def _normalize_loose_git_patch(patch_text: str) -> str:
                        """
                        Heuristic normalizer for "almost unified diff" patches produced by LLMs.

                        Common failure mode: hunk body lines are emitted without the required
                        leading marker (` ` context / `+` add / `-` remove). `git apply` rejects
                        these as "corrupt patch".

                        This function:
                        - Keeps diff/file headers
                        - Inside hunks:
                          - prefixes any non-marker line with a single leading space
                          - repairs hunk header line counts based on the actual hunk body
                        """
                        if not patch_text:
                            return ""
                        import re

                        HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$")

                        def _is_header(line0: str) -> bool:
                            return (
                                line0.startswith("diff --git a/")
                                or line0.startswith("--- a/")
                                or line0.startswith("+++ b/")
                                or line0.startswith("index ")
                                or line0.startswith("new file mode ")
                                or line0.startswith("deleted file mode ")
                                or line0.startswith("similarity index ")
                                or line0.startswith("rename from ")
                                or line0.startswith("rename to ")
                            )

                        def _fix_hunk_header(h: str, body: list[str]) -> str:
                            m = HUNK_RE.match(h)
                            if not m:
                                return h
                            a0 = int(m.group(1))
                            b0 = int(m.group(3))
                            suffix = m.group(5) or ""
                            old_n = 0
                            new_n = 0
                            for l0 in body:
                                if not l0:
                                    continue
                                if l0.startswith("\\"):
                                    continue
                                if l0.startswith((" ", "-")):
                                    old_n += 1
                                if l0.startswith((" ", "+")):
                                    new_n += 1
                            return f"@@ -{a0},{old_n} +{b0},{new_n} @@{suffix}"

                        out_lines: list[str] = []
                        in_hunk = False
                        hunk_header: str | None = None
                        hunk_body: list[str] = []

                        def _flush_hunk() -> None:
                            nonlocal hunk_header, hunk_body, in_hunk
                            if not in_hunk or not hunk_header:
                                return
                            out_lines.append(_fix_hunk_header(hunk_header, hunk_body))
                            out_lines.extend(hunk_body)
                            hunk_header = None
                            hunk_body = []
                            in_hunk = False

                        for raw in patch_text.splitlines():
                            line = raw.rstrip("\r")
                            # Start of a new file patch resets hunk state.
                            if line.startswith("diff --git a/"):
                                _flush_hunk()
                                out_lines.append(line)
                                continue
                            if _is_header(line) and not line.startswith("@@ "):
                                _flush_hunk()
                                out_lines.append(line)
                                continue
                            if line.startswith("@@ "):
                                _flush_hunk()
                                in_hunk = True
                                hunk_header = line
                                hunk_body = []
                                continue

                            if not in_hunk:
                                out_lines.append(line)
                                continue

                            # In hunk body: enforce leading marker.
                            if not line:
                                hunk_body.append(" ")
                                continue
                            if line.startswith((" ", "+", "-", "\\")):
                                hunk_body.append(line)
                                continue
                            hunk_body.append(" " + line)

                        _flush_hunk()
                        return "\n".join(out_lines).strip() + "\n"

                    def _wrap_patch_fragment_if_missing_headers(patch_text: str, allowed_globs0: list[str]) -> str:
                        """
                        Some LLM outputs start directly with a hunk (`@@ ... @@`) without file headers.
                        `git apply` rejects these as "patch fragment without header".

                        Safe heuristic:
                        - Only attempt when patch has no `diff --git` header
                        - AND first non-empty line starts with `@@`
                        - AND allowlist contains exactly one concrete (non-glob) file path
                        """
                        if not patch_text:
                            return ""
                        if "diff --git a/" in patch_text:
                            return patch_text
                        lines = [ln.rstrip("\r") for ln in patch_text.splitlines()]
                        first = ""
                        for ln in lines:
                            if ln.strip():
                                first = ln.strip()
                                break
                        if not first.startswith("@@ "):
                            return patch_text

                        # Pick a single concrete target file from allowlist.
                        concrete: list[str] = []
                        for g in allowed_globs0 or []:
                            gg = _normalize_repo_path(str(g))
                            if not gg:
                                continue
                            if any(ch in gg for ch in ["*", "?", "["]):
                                continue
                            concrete.append(gg)
                        concrete = sorted(set(concrete))
                        if len(concrete) != 1:
                            return patch_text
                        target = concrete[0]
                        try:
                            p0 = (self.repo_root / target).resolve()
                            if not p0.exists() or not p0.is_file():
                                return patch_text
                        except Exception:
                            return patch_text

                        header = "\n".join(
                            [
                                f"diff --git a/{target} b/{target}",
                                f"--- a/{target}",
                                f"+++ b/{target}",
                            ]
                        )
                        return header + "\n" + "\n".join(lines).strip() + "\n"

                    def _parse_tokens_used(stdout_text: str, stderr_text: str) -> int | None:
                        import re

                        blob = "\n".join([stdout_text or "", stderr_text or ""])
                        if not blob:
                            return None
                        m = re.search(r"tokens used\\s*\\n\\s*([0-9][0-9,]*)", blob, flags=re.IGNORECASE)
                        if not m:
                            return None
                        try:
                            return int(m.group(1).replace(",", ""))
                        except Exception:
                            return None

                    def _write_usage(step_dir0: Path, *, tokens_used: int | None, stdout_text: str, stderr_text: str) -> None:
                        try:
                            payload = {
                                "ts_utc": _utc_now(),
                                "tokens_used": tokens_used,
                                "stdout_bytes": len((stdout_text or "").encode("utf-8", errors="replace")),
                                "stderr_bytes": len((stderr_text or "").encode("utf-8", errors="replace")),
                            }
                            _atomic_write_json(step_dir0 / "usage.json", payload)
                        except Exception:
                            pass

                    def _patch_files_from_git_patch(patch_text: str) -> list[str]:
                        files: list[str] = []
                        for line in (patch_text or "").splitlines():
                            if line.startswith("diff --git a/") and " b/" in line:
                                try:
                                    tail = line.split("diff --git a/", 1)[1]
                                    a, b = tail.split(" b/", 1)
                                    p = _normalize_repo_path(b.strip())
                                    if p:
                                        files.append(p)
                                except Exception:
                                    continue
                        return sorted(set(files))

                    def _new_files_from_git_patch(patch_text: str) -> list[str]:
                        """
                        Best-effort: detect "new file" paths in a git patch so we can delete
                        pre-existing targets before `git apply` (common when retries re-run
                        the same parent and the file already exists).
                        """
                        out: list[str] = []
                        cur: str | None = None
                        is_new = False
                        for line in (patch_text or "").splitlines():
                            if line.startswith("diff --git a/") and " b/" in line:
                                # flush previous
                                if cur and is_new:
                                    out.append(cur)
                                cur = None
                                is_new = False
                                try:
                                    tail = line.split("diff --git a/", 1)[1]
                                    _a, b = tail.split(" b/", 1)
                                    cur = _normalize_repo_path(b.strip())
                                except Exception:
                                    cur = None
                                continue
                            if line.startswith("new file mode "):
                                is_new = True
                                continue
                            if line.startswith("--- /dev/null"):
                                is_new = True
                                continue
                        if cur and is_new:
                            out.append(cur)
                        # stable de-dupe
                        seen = set()
                        return [p for p in out if p and not (p in seen or seen.add(p))]

                    def _safe_to_overwrite_existing_new_file(path0: str) -> bool:
                        """
                        Guardrail: NEVER delete/overwrite existing evidence files when retrying patch apply.

                        We only allow overwriting existing files for a small set of safe, non-evidence roots
                        where "new file already exists" is a common retry artifact:
                        - generated contracts under SSOT.
                        """
                        p = _normalize_repo_path(path0)
                        if not p:
                            return False
                        safe_prefixes = [
                            "docs/ssot/04_contracts/generated/",
                            "docs/ssot/04_contracts/generated/ledger/",
                        ]
                        return any(p.startswith(pref) for pref in safe_prefixes)

                    # Hard forbidlist: NEVER allow a patch to touch these paths (even if allowlisted).
                    _FORBIDDEN_PATCH_GLOBS = [
                        "docs/REPORT/**",
                        "docs/LOG/**",
                        "docs/DERIVED/**",
                        "docs/INPUTS/**",
                        "artifacts/**",
                        "evidence/**",
                        "**/verdict.json",
                    ]

                    def _forbidden_patch_hits(paths: list[str]) -> list[str]:
                        out: list[str] = []
                        for p0 in paths or []:
                            p = _normalize_repo_path(p0)
                            if not p:
                                continue
                            if _match_any(p, _FORBIDDEN_PATCH_GLOBS):
                                out.append(p)
                        out = sorted(set(out))
                        return out[:50]

                    def _normalize_file_newlines(repo_root0: Path, rel_path: str) -> None:
                        """
                        Best-effort: normalize CRLF -> LF for patch application stability on Windows.
                        Only touches existing files.
                        """
                        try:
                            p0 = (repo_root0 / rel_path).resolve()
                            if not p0.exists() or not p0.is_file():
                                return
                            b = p0.read_bytes()
                            if b"\r\n" not in b:
                                return
                            # Avoid rewriting huge binaries accidentally.
                            if len(b) > 2 * 1024 * 1024:
                                return
                            p0.write_bytes(b.replace(b"\r\n", b"\n"))
                        except Exception:
                            return

                    # Scope enforcement: collect diff from worktree and only apply allowed paths back to repo_root.
                    if isolate and worktree_ok:
                        if _is_cancel_requested(str(run_id), str(pid)):
                            raise asyncio.CancelledError()
                        _write_parent_state(step_dir, run_id=str(run_id), parent_id=str(pid), phase="collect_changes", message="git_diff_start")
                        code_n, out_n, err_n = _run_git(["diff", "--name-only"], cwd=worktree_dir, timeout=30.0)
                        changed_files = [l.strip() for l in (out_n or "").splitlines() if l.strip()]
                        code_u, out_u, _ = _run_git(["ls-files", "-o", "--exclude-standard"], cwd=worktree_dir, timeout=30.0)
                        untracked_files = [l.strip() for l in (out_u or "").splitlines() if l.strip()]
                        # Patch
                        code_d, out_d, err_d = _run_git(["diff"], cwd=worktree_dir, timeout=30.0)
                        patch_path = (step_dir / "patch.diff").resolve()
                        patch_path.write_text(out_d or "", encoding="utf-8", errors="replace")
                        patch_file = str(patch_path)

                        # Additional touched detection via content comparison for allowlisted files (covers untracked baselines).
                        _write_parent_state(step_dir, run_id=str(run_id), parent_id=str(pid), phase="collect_changes", message="allowlist_compare_start")
                        try:
                            allow_touched, allow_deleted = _compute_allowlisted_touched(
                                repo_root=self.repo_root,
                                worktree_root=worktree_dir,
                                allowed=allowed_globs,
                            )
                        except RuntimeError as e:
                            exit_code = 1
                            error = "allowlist_too_broad"
                            stderr = f"allowlist_too_broad: {e}"
                            allow_touched, allow_deleted = [], []
                            _write_parent_state(step_dir, run_id=str(run_id), parent_id=str(pid), phase="error", message="allowlist_too_broad", error=str(e))

                        touched = sorted(set(changed_files + untracked_files + allow_touched + allow_deleted))
                        violations = sorted(
                            set([p for p in (changed_files + untracked_files) if (allowed_globs and not _match_any(p, allowed_globs))])
                        )
                        forbidden_files = _forbidden_patch_hits(list(set(changed_files + untracked_files)))
                        if forbidden_files:
                            violations = sorted(set(violations + ["FORBIDDEN_PATHS"]))
                        if error == "allowlist_too_broad":
                            violations = ["ALLOWLIST_TOO_BROAD"]
                        scope_meta = {
                            "isolate_worktree": True,
                            "worktree_dir": str(worktree_dir),
                            "allowed_globs": allowed_globs,
                            "changed_files": changed_files,
                            "untracked_files": untracked_files,
                            "allowlist_touched_files": allow_touched,
                            "allowlist_deleted_files": allow_deleted,
                            "patch_file": patch_file,
                            "violations": violations,
                            "forbidden_files": forbidden_files,
                            "git_diff_rc": int(code_d),
                            "git_diff_err": err_d,
                        }
                        (step_dir / "scope_enforcement.json").write_text(
                            json.dumps(scope_meta, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8",
                            errors="replace",
                        )

                        if allowed_globs and violations:
                            # Reject: scope violation
                            exit_code = 1
                            error = "scope_violation"
                        else:
                            # If the model couldn't edit files in-place (common for non-codex models or read-only sandboxes),
                            # allow it to return a `git apply` patch in stdout/stderr and apply it here.
                            #
                            # NOTE: `untracked_files` may be non-empty even when no edits happened (because the allowlisted
                            # file itself may be untracked in the worktree baseline). In that case `git diff` stays empty
                            # and we MUST still try patch-from-stdout.
                            if (not (out_d or "").strip()) and allowed_globs:
                                patch_from_stdout = _extract_git_patch(stdout) or _extract_git_patch(stderr)
                                if patch_from_stdout:
                                    patch_from_stdout = _wrap_patch_fragment_if_missing_headers(patch_from_stdout, allowed_globs)
                                    patch_from_stdout = _normalize_loose_git_patch(patch_from_stdout)
                                    patch_files = _patch_files_from_git_patch(patch_from_stdout)
                                    patch_violations = [p for p in patch_files if not _match_any(p, allowed_globs)]
                                    patch_forbidden = _forbidden_patch_hits(patch_files)
                                    patch_out = (step_dir / "patch_from_stdout.diff").resolve()
                                    patch_out.write_text(patch_from_stdout, encoding="utf-8", errors="replace")
                                    scope_meta["patch_from_stdout"] = str(patch_out)
                                    scope_meta["patch_from_stdout_files"] = patch_files
                                    scope_meta["patch_from_stdout_violations"] = patch_violations
                                    scope_meta["patch_from_stdout_forbidden"] = patch_forbidden
                                    if patch_violations or patch_forbidden:
                                        exit_code = 1
                                        error = "scope_violation"
                                        apply_ok = False
                                        apply_error = "scope_violation (patch_from_stdout)"
                                    else:
                                        # Normalize newline style for touched files before applying patch.
                                        for fp in patch_files:
                                            _normalize_file_newlines(self.repo_root, fp)
                                        # If the patch adds new files, avoid "already exists" failures on retries.
                                        # IMPORTANT: do NOT delete/overwrite evidence paths; only allow safe roots.
                                        for nf in _new_files_from_git_patch(patch_from_stdout):
                                            try:
                                                if nf and _match_any(nf, allowed_globs) and _safe_to_overwrite_existing_new_file(nf):
                                                    dst = (self.repo_root / nf).resolve()
                                                    if dst.exists() and dst.is_file():
                                                        dst.unlink()
                                            except Exception:
                                                pass
                                        with self._apply_lock:
                                            # Preflight check to produce clearer diagnostics than a raw apply failure.
                                            pre = subprocess.run(
                                                ["git", "apply", "--check", "--ignore-space-change", "--whitespace=nowarn", str(patch_out)],
                                                cwd=str(self.repo_root),
                                                capture_output=True,
                                                text=True,
                                                encoding="utf-8",
                                                errors="replace",
                                                timeout=90,
                                            )
                                            if int(pre.returncode or 0) != 0:
                                                ap = pre
                                            else:
                                                ap = subprocess.run(
                                                    ["git", "apply", "--ignore-space-change", "--whitespace=nowarn", str(patch_out)],
                                                    cwd=str(self.repo_root),
                                                    capture_output=True,
                                                    text=True,
                                                    encoding="utf-8",
                                                    errors="replace",
                                                    timeout=90,
                                                )
                                        apply_ok = int(ap.returncode or 0) == 0
                                        apply_error = (ap.stderr or "").strip()
                                        applied_any_changes = bool(patch_files) and bool(apply_ok)
                                        if not apply_ok:
                                            exit_code = 1
                                            error = "apply_failed"

                            # Apply back to main repo by copying allowlisted touched files (covers tracked+untracked).
                            copied: list[str] = []
                            deleted_applied: list[str] = []
                            copy_failures: list[str] = []
                            if allow_touched or allow_deleted:
                                _write_parent_state(
                                    step_dir,
                                    run_id=str(run_id),
                                    parent_id=str(pid),
                                    phase="apply_changes",
                                    message="copy_allowlisted_start",
                                    touched=len(allow_touched),
                                    deleted=len(allow_deleted),
                                )
                                with self._apply_lock:
                                    n_done = 0
                                    for rel in allow_touched:
                                        if _is_cancel_requested(str(run_id), str(pid)):
                                            raise asyncio.CancelledError()
                                        try:
                                            src = (worktree_dir / rel).resolve()
                                            dst = (self.repo_root / rel).resolve()
                                            if not src.exists() or src.is_dir():
                                                continue
                                            dst.parent.mkdir(parents=True, exist_ok=True)
                                            dst.write_bytes(src.read_bytes())
                                            copied.append(_normalize_repo_path(rel))
                                        except Exception as e:
                                            copy_failures.append(f"{rel} :: {e}")
                                        n_done += 1
                                        if n_done % 50 == 0:
                                            _write_parent_state(
                                                step_dir,
                                                run_id=str(run_id),
                                                parent_id=str(pid),
                                                phase="apply_changes",
                                                message="copy_allowlisted_progress",
                                                done=n_done,
                                                total=len(allow_touched),
                                            )
                                    for rel in allow_deleted:
                                        if _is_cancel_requested(str(run_id), str(pid)):
                                            raise asyncio.CancelledError()
                                        try:
                                            dst = (self.repo_root / rel).resolve()
                                            if dst.exists() and dst.is_file():
                                                dst.unlink()
                                                deleted_applied.append(_normalize_repo_path(rel))
                                        except Exception as e:
                                            copy_failures.append(f"delete {rel} :: {e}")
                                _write_parent_state(
                                    step_dir,
                                    run_id=str(run_id),
                                    parent_id=str(pid),
                                    phase="apply_changes",
                                    message="copy_allowlisted_done",
                                    copied=len(copied),
                                    deleted=len(deleted_applied),
                                    failures=len(copy_failures),
                                )
                                apply_ok = len(copy_failures) == 0
                                apply_error = "; ".join(copy_failures)
                                applied_any_changes = applied_any_changes or bool(copied or deleted_applied)
                            scope_meta["copied_files"] = copied
                            scope_meta["deleted_files"] = deleted_applied
                            scope_meta["copy_failures"] = copy_failures
                            if not apply_ok:
                                exit_code = 1
                                error = "apply_failed"

                        if require_changes and not applied_any_changes and exit_code == 0:
                            exit_code = 1
                            error = "no_changes"
                            scope_meta["apply_ok"] = False
                            scope_meta["apply_error"] = "no_changes (require_changes=true)"

                        # persist apply info
                        scope_meta["apply_ok"] = apply_ok
                        scope_meta["apply_error"] = apply_error
                        (step_dir / "scope_enforcement.json").write_text(
                            json.dumps(scope_meta, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8",
                            errors="replace",
                        )
                    else:
                        # Fallback: if we didn't get actual file changes (e.g., non-codex model), try applying a git patch from output.
                        patch_from_stdout = _extract_git_patch(stdout) or _extract_git_patch(stderr)
                        if patch_from_stdout and allowed_globs:
                            patch_from_stdout = _wrap_patch_fragment_if_missing_headers(patch_from_stdout, allowed_globs)
                            patch_from_stdout = _normalize_loose_git_patch(patch_from_stdout)
                            patch_files = _patch_files_from_git_patch(patch_from_stdout)
                            patch_violations = [p for p in patch_files if not _match_any(p, allowed_globs)]
                            patch_path = (step_dir / "patch_from_stdout.diff").resolve()
                            patch_path.write_text(patch_from_stdout, encoding="utf-8", errors="replace")
                            scope_meta = {
                                "ts_utc": _utc_now(),
                                "isolate_worktree": False,
                                "allowed_globs": allowed_globs,
                                "patch_from_stdout": str(patch_path),
                                "patch_files": patch_files,
                                "violations": patch_violations,
                            }
                            if patch_violations:
                                exit_code = 1
                                error = "scope_violation"
                                scope_meta["apply_ok"] = False
                                scope_meta["apply_error"] = "scope_violation"
                            else:
                                # Same guardrail as above: do NOT delete/overwrite evidence paths on retries.
                                for nf in _new_files_from_git_patch(patch_from_stdout):
                                    try:
                                        if nf and _match_any(nf, allowed_globs) and _safe_to_overwrite_existing_new_file(nf):
                                            dst = (self.repo_root / nf).resolve()
                                            if dst.exists() and dst.is_file():
                                                dst.unlink()
                                    except Exception:
                                        pass
                                for fp in patch_files:
                                    _normalize_file_newlines(self.repo_root, fp)
                                with self._apply_lock:
                                    ap = subprocess.run(
                                        ["git", "apply", "--ignore-space-change", "--whitespace=nowarn", str(patch_path)],
                                        cwd=str(self.repo_root),
                                        capture_output=True,
                                        text=True,
                                        encoding="utf-8",
                                        errors="replace",
                                        timeout=90,
                                    )
                                ok = int(ap.returncode or 0) == 0
                                scope_meta["apply_ok"] = ok
                                scope_meta["apply_error"] = (ap.stderr or "").strip()
                                if not ok:
                                    exit_code = 1
                                    error = "apply_failed"
                            (step_dir / "scope_enforcement.json").write_text(
                                json.dumps(scope_meta, ensure_ascii=False, indent=2) + "\n",
                                encoding="utf-8",
                                errors="replace",
                            )

                    (step_dir / "stdout.log").write_text(stdout, encoding="utf-8", errors="replace")
                    (step_dir / "stderr.log").write_text(stderr, encoding="utf-8", errors="replace")
                    tokens_used = _parse_tokens_used(stdout, stderr)
                    _write_usage(step_dir, tokens_used=tokens_used, stdout_text=stdout, stderr_text=stderr)
                    if tokens_used is not None:
                        scope_meta["tokens_used"] = int(tokens_used)
                        _write_parent_state(step_dir, run_id=str(run_id), parent_id=str(pid), phase="usage", message="tokens_used", tokens_used=int(tokens_used))

                    end = _utc_now()
                    async with manifest_lock:
                        manifest["parents"][idx - 1]["end"] = end
                        manifest["parents"][idx - 1]["exit_code"] = exit_code
                        manifest["parents"][idx - 1]["artifacts_dir"] = str(step_dir)
                        _atomic_write_json(run_manifest_path, manifest)
                    self._touch_active_run(run_id)

                    combined_stdout.append(f"\n--- parent {pid} stdout ---\n{stdout}")
                    combined_stderr.append(f"\n--- parent {pid} stderr ---\n{stderr}")
                    item: dict[str, Any] = {
                        "id": pid,
                        "exit_code": exit_code,
                        "artifacts_dir": str(step_dir),
                        "prompt_file": str(prompt_path),
                        "dangerously_bypass": bool(dangerously_bypass),
                        "isolate_worktree": bool(isolate),
                    }
                    if error:
                        item["error"] = error
                    if scope_meta:
                        item["scope_enforcement"] = {"patch_file": patch_file, "violations": violations, "apply_ok": apply_ok}
                    results.append(item)
            except asyncio.CancelledError:
                start = _utc_now()
                end = _utc_now()
                _write_parent_state(step_dir, run_id=str(run_id), parent_id=str(pid), phase="canceled", message="cancelled")
                try:
                    step_dir.mkdir(parents=True, exist_ok=True)
                    (step_dir / "stdout.log").write_text("", encoding="utf-8")
                    (step_dir / "stderr.log").write_text("Cancelled by leader/watchdog", encoding="utf-8", errors="replace")
                except Exception:
                    pass
                async with manifest_lock:
                    manifest["parents"][idx - 1]["start"] = manifest["parents"][idx - 1].get("start") or start
                    manifest["parents"][idx - 1]["end"] = end
                    manifest["parents"][idx - 1]["exit_code"] = 130
                    manifest["parents"][idx - 1]["artifacts_dir"] = str(step_dir)
                    _atomic_write_json(run_manifest_path, manifest)
                self._touch_active_run(run_id)
                combined_stderr.append(f"\n--- parent {pid} stderr ---\nCancelled by leader/watchdog")
                results.append(
                    {
                        "id": pid,
                        "exit_code": 130,
                        "artifacts_dir": str(step_dir),
                        "prompt_file": str(prompt_path),
                        "dangerously_bypass": bool(dangerously_bypass),
                        "error": "cancelled",
                    }
                )
            except Exception as e:
                start = _utc_now()
                end = _utc_now()
                try:
                    step_dir.mkdir(parents=True, exist_ok=True)
                    prompt_path.write_text(prompt, encoding="utf-8", errors="replace")
                    (step_dir / "stdout.log").write_text("", encoding="utf-8")
                    (step_dir / "stderr.log").write_text(f"Executor error: {e}", encoding="utf-8", errors="replace")
                except Exception:
                    pass

                async with manifest_lock:
                    manifest["parents"][idx - 1]["start"] = start
                    manifest["parents"][idx - 1]["end"] = end
                    manifest["parents"][idx - 1]["exit_code"] = 1
                    manifest["parents"][idx - 1]["artifacts_dir"] = str(step_dir)
                    _atomic_write_json(run_manifest_path, manifest)
                self._touch_active_run(run_id)

                combined_stdout.append(f"\n--- parent {pid} stdout ---\n")
                combined_stderr.append(f"\n--- parent {pid} stderr ---\nExecutor error: {e}")
                results.append(
                    {
                        "id": pid,
                        "exit_code": 1,
                        "artifacts_dir": str(step_dir),
                        "prompt_file": str(prompt_path),
                        "dangerously_bypass": bool(dangerously_bypass),
                        "error": "executor_error",
                    }
                )
            finally:
                # Best-effort task handle cleanup.
                try:
                    with self._run_task_lock:
                        if str(run_id) in self._run_tasks:
                            self._run_tasks[str(run_id)].pop(str(pid), None)
                            if not self._run_tasks[str(run_id)]:
                                self._run_tasks.pop(str(run_id), None)
                except Exception:
                    pass

        tasks = [asyncio.create_task(_run_one(i, p)) for i, p in enumerate(items, 1)]
        await asyncio.gather(*tasks, return_exceptions=True)

        async with manifest_lock:
            manifest["end"] = _utc_now()
            _atomic_write_json(run_manifest_path, manifest)
        self._touch_active_run(run_id)
        self._untrack_active_run(run_id)

        diff_path = base / "workspace.diff"
        try:
            d = subprocess.run(
                ["git", "diff"],
                cwd=str(self.repo_root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
            diff_path.write_text(d.stdout or "", encoding="utf-8", errors="replace")
        except Exception:
            diff_path.write_text("", encoding="utf-8")

        def _exit_code_ok(item: dict[str, Any]) -> bool:
            v = item.get("exit_code", None)
            if v is None:
                return False
            try:
                return int(v) == 0
            except Exception:
                return False

        overall_exit = 0 if (len(results) == len(items) and all(_exit_code_ok(r) for r in results)) else 1
        return overall_exit, "\n".join(combined_stdout), "\n".join(combined_stderr), None, {
            "run_id": run_id,
            "server_artifacts_dir": str(base),
            "parents_file": str(parents_path),
            "run_manifest_file": str(run_manifest_path),
            "workspace_diff_file": str(diff_path),
            "model": model,
            "timeout_s": effective_timeout,
            "max_outstanding": effective_max_outstanding,
            "dangerously_bypass": bool(dangerously_bypass),
            "results": results,
        }
    
    # codex-only stage: remove traeocrcli/iflow/cursor helpers

    def _read_json_file(self, path: Path) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _track_active_run(self, run_id: str, manifest_path: str) -> None:
        with self._state_lock:
            self._state_dir.mkdir(parents=True, exist_ok=True)
            data = self._read_json_file(self._active_runs_file)
            if not isinstance(data, dict):
                data = {"runs": {}}
            runs = data.get("runs")
            if not isinstance(runs, dict):
                runs = {}
                data["runs"] = runs
            runs[str(run_id)] = {"manifest_file": manifest_path, "updated_utc": datetime.now(timezone.utc).isoformat()}
            tmp = self._active_runs_file.with_suffix(self._active_runs_file.suffix + ".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8", errors="replace")
            os.replace(tmp, self._active_runs_file)

    def _touch_active_run(self, run_id: str) -> None:
        with self._state_lock:
            data = self._read_json_file(self._active_runs_file)
            if not isinstance(data, dict):
                return
            runs = data.get("runs")
            if not isinstance(runs, dict):
                return
            entry = runs.get(str(run_id))
            if not isinstance(entry, dict):
                return
            entry["updated_utc"] = datetime.now(timezone.utc).isoformat()
            runs[str(run_id)] = entry
            data["runs"] = runs
            tmp = self._active_runs_file.with_suffix(self._active_runs_file.suffix + ".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8", errors="replace")
            os.replace(tmp, self._active_runs_file)

    def _untrack_active_run(self, run_id: str) -> None:
        with self._state_lock:
            data = self._read_json_file(self._active_runs_file)
            if not isinstance(data, dict):
                return
            runs = data.get("runs")
            if not isinstance(runs, dict):
                return
            runs.pop(str(run_id), None)
            data["runs"] = runs
            tmp = self._active_runs_file.with_suffix(self._active_runs_file.suffix + ".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8", errors="replace")
            os.replace(tmp, self._active_runs_file)

    def _get_active_runs_status(self) -> list[dict[str, Any]]:
        with self._state_lock:
            data = self._read_json_file(self._active_runs_file)
            if not isinstance(data, dict):
                return []
            runs = data.get("runs")
            if not isinstance(runs, dict):
                return []
            runs = dict(runs)

        out: list[dict[str, Any]] = []
        stale: list[str] = []
        for run_id, entry in runs.items():
            if not isinstance(entry, dict):
                stale.append(run_id)
                continue
            try:
                updated_utc = entry.get("updated_utc")
                updated_dt = datetime.fromisoformat(str(updated_utc)) if updated_utc else None
            except Exception:
                updated_dt = None
            manifest_file = entry.get("manifest_file")
            if not manifest_file:
                stale.append(run_id)
                continue
            mp = Path(str(manifest_file))
            manifest = self._read_json_file(mp)
            if not isinstance(manifest, dict):
                stale.append(run_id)
                continue
            parents = manifest.get("parents")
            is_active = True
            if isinstance(parents, list) and parents:
                is_active = any((isinstance(p, dict) and not p.get("end")) for p in parents) or not manifest.get("end")
            if is_active and updated_dt is not None:
                try:
                    age_s = (datetime.now(timezone.utc) - updated_dt.astimezone(timezone.utc)).total_seconds()
                    if age_s > float(self._abandon_active_run_after_s):
                        stale.append(run_id)
                        continue
                except Exception:
                    pass
            if not is_active:
                stale.append(run_id)
                continue
            out.append(
                {
                    "run_id": manifest.get("run_id", run_id),
                    "start": manifest.get("start"),
                    "end": manifest.get("end"),
                    "max_outstanding": manifest.get("max_outstanding"),
                    "model": manifest.get("model"),
                    "run_manifest_file": str(mp),
                    "parents": parents if isinstance(parents, list) else [],
                }
            )

        for rid in stale:
            try:
                self._untrack_active_run(rid)
            except Exception:
                pass
        return out
