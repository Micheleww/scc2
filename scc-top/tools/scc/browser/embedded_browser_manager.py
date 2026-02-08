from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass
class BrowserProcessState:
    pid: int
    started_at_s: float
    cwd: str
    command: str
    log_path: Optional[str] = None
    last_exit_code: Optional[int] = None


class SCCEmbeddedBrowserManager:
    """
    Manage the embedded Electron "SCC ChatGPT Browser" as a subprocess.

    Intended to be used from the unified server process via /scc/browser/* endpoints.
    """

    def __init__(self, app_dir: Path):
        self.app_dir = app_dir
        self._proc: Optional[subprocess.Popen[str]] = None
        self._state: Optional[BrowserProcessState] = None
        self._log_file = None
        try:
            # app_dir = <repo>/tools/scc/apps/browser/scc-chatgpt-browser
            self._repo_root = self.app_dir.parents[4]
        except Exception:
            self._repo_root = self.app_dir

    def _external_state_path(self) -> Path:
        return (self._repo_root / "artifacts" / "scc_state" / "browser_process.json").resolve()

    def _is_pid_alive(self, pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            if os.name == "nt":
                # tasklist returns 0 even if not found; parse output.
                r = subprocess.run(  # noqa: S603
                    ["tasklist", "/FI", f"PID eq {pid}"],
                    capture_output=True,
                    text=True,
                    check=False,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                out = (r.stdout or "") + "\n" + (r.stderr or "")
                return str(pid) in out and "No tasks are running" not in out
            os.kill(pid, 0)
            return True
        except Exception:
            return False

    def _external_status(self) -> Optional[Dict[str, Any]]:
        """
        Detect an already-running browser process that was started outside this manager
        (e.g. after a server restart). Electron writes a repo-local state file.
        """
        p = self._external_state_path()
        if not p.exists():
            return None
        try:
            import json

            raw = p.read_text(encoding="utf-8", errors="replace")
            data = json.loads(raw)
            pid = int(data.get("pid") or 0)
            if not self._is_pid_alive(pid):
                return None
            return {
                "running": True,
                "pid": pid,
                "started_at_s": None,
                "uptime_s": None,
                "cwd": str(self.app_dir),
                "command": None,
                "log_path": data.get("log_path"),
                "log_tail": None,
                "last_exit_code": None,
                "external": True,
                "current_url": data.get("current_url"),
            }
        except Exception:
            return None

    def _npm_cmd(self) -> str:
        return "npm.cmd" if os.name == "nt" else "npm"

    def _electron_exe(self) -> Optional[Path]:
        if os.name == "nt":
            p = (self.app_dir / "node_modules" / "electron" / "dist" / "electron.exe").resolve()
            return p if p.exists() else None
        # Best-effort for macOS/Linux; keep npm fallback if not found.
        linux = (self.app_dir / "node_modules" / "electron" / "dist" / "electron").resolve()
        if linux.exists():
            return linux
        mac = (self.app_dir / "node_modules" / "electron" / "dist" / "Electron.app" / "Contents" / "MacOS" / "Electron").resolve()
        return mac if mac.exists() else None

    def _is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def status(self) -> Dict[str, Any]:
        running = self._is_running()
        exit_code = None
        if self._proc is not None:
            exit_code = self._proc.poll()
        state = self._state

        if not running:
            ext = self._external_status()
            if ext:
                return ext

        log_tail = None
        log_path = state.log_path if state else None
        if log_path:
            try:
                p = Path(log_path)
                if p.exists():
                    # Keep tail small to avoid huge payloads.
                    raw = p.read_text(encoding="utf-8", errors="replace")
                    lines = raw.splitlines()
                    log_tail = "\n".join(lines[-120:])
            except Exception:
                log_tail = None
        return {
            "running": running,
            "pid": state.pid if (running and state) else None,
            "started_at_s": state.started_at_s if state else None,
            "uptime_s": (time.time() - state.started_at_s) if (running and state) else None,
            "cwd": state.cwd if state else str(self.app_dir),
            "command": state.command if state else None,
            "log_path": log_path,
            "log_tail": log_tail,
            "last_exit_code": state.last_exit_code if state else exit_code,
        }

    def start(
        self,
        *,
        boot_url: Optional[str] = None,
        home_url: Optional[str] = None,
        default_endpoint: Optional[str] = None,
        webgpt_intake_endpoint: Optional[str] = None,
        webgpt_export_endpoint: Optional[str] = None,
        webgpt_backfill_autostart: Optional[bool] = None,
        webgpt_backfill_limit: Optional[int] = None,
        webgpt_backfill_scroll_steps: Optional[int] = None,
        default_autosend: Optional[bool] = None,
    ) -> Dict[str, Any]:
        if self._is_running():
            return {"ok": True, "already_running": True, **self.status()}
        ext = self._external_status()
        if ext:
            # Don't spawn a second window; report already-running instead.
            return {"ok": True, "already_running": True, **ext}

        if not self.app_dir.exists():
            return {"ok": False, "error": f"browser_app_dir_not_found: {self.app_dir}"}

        pkg = self.app_dir / "package.json"
        if not pkg.exists():
            return {"ok": False, "error": f"browser_package_json_not_found: {pkg}"}

        # Don't auto-install dependencies from the server; keep it explicit.
        # Provide a clear error if Electron isn't installed.
        if not (self.app_dir / "node_modules").exists():
            return {
                "ok": False,
                "error": "node_modules_missing",
                "detail": f"Run `npm install` in {self.app_dir}",
            }

        electron_exe = self._electron_exe()
        if electron_exe is not None:
            cmd = [str(electron_exe), "."]
        else:
            cmd = [self._npm_cmd(), "start"]

        log_dir = (self.app_dir / ".scc_browser_logs").resolve()
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            # fallback: use cwd
            log_dir = self.app_dir.resolve()
        ts = time.strftime("%Y%m%d-%H%M%S")
        log_path = (log_dir / f"browser-{ts}.log").resolve()
        log_f = open(log_path, "a", encoding="utf-8", errors="replace")  # noqa: SIM115
        self._log_file = log_f

        env = os.environ.copy()
        # Some environments export ELECTRON_RUN_AS_NODE=1 (used to run Electron as Node).
        # That breaks this embedded GUI app because we need the real Electron main process APIs.
        env.pop("ELECTRON_RUN_AS_NODE", None)
        env["SCC_BROWSER_LOG_PATH"] = str(log_path)
        if boot_url:
            env["SCC_CHATGPT_BROWSER_BOOT_URL"] = boot_url
        if home_url:
            env["SCC_CHATGPT_BROWSER_HOME_URL"] = home_url
        if default_endpoint:
            env["SCC_CHATGPT_BROWSER_DEFAULT_ENDPOINT"] = default_endpoint
        if webgpt_intake_endpoint:
            env["SCC_WEBGPT_INTAKE_ENDPOINT"] = webgpt_intake_endpoint
        if webgpt_export_endpoint:
            env["SCC_WEBGPT_EXPORT_ENDPOINT"] = webgpt_export_endpoint
        if webgpt_backfill_autostart is not None:
            env["SCC_WEBGPT_BACKFILL_AUTOSTART"] = "true" if webgpt_backfill_autostart else "false"
        if isinstance(webgpt_backfill_limit, int) and webgpt_backfill_limit > 0:
            env["SCC_WEBGPT_BACKFILL_LIMIT"] = str(webgpt_backfill_limit)
        if isinstance(webgpt_backfill_scroll_steps, int) and webgpt_backfill_scroll_steps >= 0:
            env["SCC_WEBGPT_BACKFILL_SCROLL_STEPS"] = str(webgpt_backfill_scroll_steps)
        if default_autosend is not None:
            env["SCC_CHATGPT_BROWSER_DEFAULT_AUTOSEND"] = "true" if default_autosend else "false"

        creationflags = 0
        if os.name == "nt":
            # Avoid flashing a console window.
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        proc = subprocess.Popen(  # noqa: S603
            cmd,
            cwd=str(self.app_dir),
            env=env,
            stdout=log_f,
            stderr=log_f,
            stdin=subprocess.DEVNULL,
            text=True,
            creationflags=creationflags,
        )

        self._proc = proc
        self._state = BrowserProcessState(
            pid=int(proc.pid),
            started_at_s=time.time(),
            cwd=str(self.app_dir),
            command=" ".join(cmd),
            log_path=str(log_path),
        )
        # Give the process a moment to fail fast (missing electron, etc.)
        time.sleep(0.6)
        if proc.poll() is not None:
            if self._state:
                self._state.last_exit_code = proc.poll()
            self._proc = None
            try:
                log_f.flush()
                log_f.close()
            except Exception:
                pass
            self._log_file = None
            return {"ok": False, "error": "browser_exited_early", "exit_code": proc.poll(), **self.status()}

        return {"ok": True, "already_running": False, **self.status()}

    def stop(self, timeout_s: float = 5.0) -> Dict[str, Any]:
        if self._proc is None:
            ext = self._external_status()
            if ext and ext.get("pid"):
                pid = int(ext["pid"])
                try:
                    if os.name == "nt":
                        subprocess.run(  # noqa: S603
                            ["taskkill", "/PID", str(pid), "/T", "/F"],
                            capture_output=True,
                            text=True,
                            check=False,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                        )
                    else:
                        os.kill(pid, 15)
                except Exception:
                    pass
                return {"ok": True, "already_stopped": False, "killed_pid": pid, **self.status()}
            return {"ok": True, "already_stopped": True, **self.status()}

        proc = self._proc
        if proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass

            deadline = time.time() + max(0.0, timeout_s)
            while time.time() < deadline:
                if proc.poll() is not None:
                    break
                time.sleep(0.1)

        if proc.poll() is None:
            try:
                proc.kill()
            except Exception:
                pass

        exit_code = proc.poll()
        if self._state:
            self._state.last_exit_code = exit_code

        self._proc = None
        try:
            if self._log_file:
                self._log_file.flush()
                self._log_file.close()
        except Exception:
            pass
        self._log_file = None
        return {"ok": True, "already_stopped": False, "exit_code": exit_code, **self.status()}
