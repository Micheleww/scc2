#!/usr/bin/env python3
"""
Windows Service wrapper for unified_server watchdog.

Why:
- Windows services must report status to the Service Control Manager (SCM).
- Running a plain Python script via `sc.exe create ...` often gets stuck in START_PENDING.

This module implements a real Windows service (pywin32) and runs `watchdog.py` as a
child process. On stop, it terminates the watchdog (and best-effort terminates any
`tools\\unified_server\\main.py` processes started by it).

Important:
The service class MUST be defined at module top-level. pywin32 resolves the class
by module + name during install/start; nested classes (inside a function) will fail
with `AttributeError: module '__main__' has no attribute ...` / pickling errors.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional


def _repo_root() -> Path:
    # tools/unified_server/windows_service_watchdog.py -> tools/unified_server -> tools -> repo root
    return Path(__file__).resolve().parent.parent.parent


def _log_path() -> Path:
    # Use a location writable by LocalSystem and normal users.
    # Avoid writing under the repo, as the service account may not have access.
    program_data = os.environ.get("ProgramData") or r"C:\ProgramData"
    return Path(program_data) / "QuantSys" / "unified_server" / "service_watchdog.log"


def _append_log(line: str) -> None:
    try:
        p = _log_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8", errors="replace") as f:
            f.write(line.rstrip() + "\n")
    except Exception:
        # Never crash the service due to logging failures.
        pass


def _debug() -> int:
    """
    Local debug helper (run as normal python, not as a service):
    validates that imports and paths work similarly to the service host.
    """
    _append_log("[debug] starting debug checks")
    print("python:", sys.executable)
    print("cwd:", os.getcwd())
    print("repo_root:", _repo_root())
    print("ProgramData log:", _log_path())
    print("env REPO_ROOT:", os.environ.get("REPO_ROOT"))
    print("env PYTHONPATH:", os.environ.get("PYTHONPATH"))
    print("sys.path[0:6]:", sys.path[:6])
    try:
        import tools.unified_server.windows_service_watchdog as m  # type: ignore

        print("import tools.unified_server.windows_service_watchdog: OK")
        print("service class:", getattr(m, "QuantSysUnifiedServerWatchdogService", None))
    except Exception as e:
        print("import service module FAILED:", repr(e))
        _append_log(f"[debug] import failed: {e!r}")
        return 2
    return 0


def _best_effort_kill_unified_server() -> None:
    # Keep this best-effort (no hard dependency on psutil).
    try:
        import ctypes
        import subprocess as _sp

        if os.name != "nt":
            return
        # Use WMIC-less approach: PowerShell via taskkill matching command line is hard;
        # best-effort: kill python processes that include tools\\unified_server\\main.py.
        # taskkill can't filter by cmdline, so we fallback to powershell only if available.
        ps = r"""
$ErrorActionPreference="SilentlyContinue";
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -like '*tools\\unified_server\\main.py*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
"""
        # Run hidden and ignore failures.
        _sp.run(
            ["powershell", "-NoProfile", "-Command", ps],
            check=False,
            stdout=_sp.DEVNULL,
            stderr=_sp.DEVNULL,
        )
        _ = ctypes  # silence unused in some linters
    except Exception:
        pass


def _spawn_watchdog() -> subprocess.Popen:
    repo = _repo_root()
    watchdog_py = repo / "tools" / "unified_server" / "watchdog.py"
    # When running under pywin32 service host, sys.executable is often pythonservice.exe.
    # Prefer the repo-local venv python.exe so watchdog runs like a normal interpreter.
    python_exe = repo / ".venv" / "Scripts" / "python.exe"
    if not python_exe.exists():
        python_exe = Path(sys.executable)

    env = os.environ.copy()
    env.setdefault("REPO_ROOT", str(repo))
    env.setdefault("UNIFIED_SERVER_HOST", "127.0.0.1")
    env.setdefault("UNIFIED_SERVER_PORT", "18788")
    # Put watchdog logs under ProgramData as well (service account safe).
    env.setdefault("WATCHDOG_LOG_FILE", str(_log_path().with_name("watchdog.log")))

    log_file = _log_path()
    log_file.parent.mkdir(parents=True, exist_ok=True)
    stdout = open(log_file, "a", encoding="utf-8", errors="replace")

    # DETACHED_PROCESS to avoid console windows, CREATE_NEW_PROCESS_GROUP for clean termination.
    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)

    _append_log(f"[service] starting watchdog: {python_exe} {watchdog_py}")
    return subprocess.Popen(
        [str(python_exe), str(watchdog_py)],
        cwd=str(repo),
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=stdout,
        stderr=stdout,
        creationflags=creationflags,
    )


def _terminate_process(p: subprocess.Popen) -> None:
    try:
        if p.poll() is not None:
            return
        if os.name == "nt":
            # terminate whole process tree best-effort
            subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            p.terminate()
    except Exception:
        pass


def run_service() -> None:
    raise RuntimeError("run_service() is deprecated; use module entrypoint instead.")


if os.name == "nt":
    # Import pywin32 only on Windows so the module can be imported elsewhere safely.
    try:
        import servicemanager  # type: ignore
        import win32event  # type: ignore
        import win32service  # type: ignore
        import win32serviceutil  # type: ignore
    except Exception as e:
        _append_log(f"[service] pywin32 import failed: {e!r}")
        raise


    class QuantSysUnifiedServerWatchdogService(win32serviceutil.ServiceFramework):
        _svc_name_ = "QuantSysUnifiedServerWatchdog"
        _svc_display_name_ = "QuantSys Unified Server Watchdog"
        _svc_description_ = "Keeps QuantSys Unified Server (127.0.0.1:18788) alive via health-check + auto-restart."

        def __init__(self, args):
            super().__init__(args)
            self._stop_event = win32event.CreateEvent(None, 0, 0, None)
            self._child: Optional[subprocess.Popen] = None

        def SvcStop(self):
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            win32event.SetEvent(self._stop_event)

        def SvcDoRun(self):
            servicemanager.LogInfoMsg("QuantSysUnifiedServerWatchdog service starting")
            self.ReportServiceStatus(win32service.SERVICE_RUNNING)

            restart_delay_s = 5.0
            try:
                while True:
                    if self._child is None or self._child.poll() is not None:
                        if self._child is not None and self._child.poll() is not None:
                            _append_log(
                                f"[service] watchdog exited code={self._child.returncode}; restarting in {restart_delay_s}s"
                            )
                            time.sleep(restart_delay_s)
                        try:
                            self._child = _spawn_watchdog()
                        except Exception as e:
                            _append_log(f"[service] failed to spawn watchdog: {e!r}; retrying in {restart_delay_s}s")
                            time.sleep(restart_delay_s)

                    # Wait for stop event, but wake periodically.
                    rc = win32event.WaitForSingleObject(self._stop_event, 1000)
                    if rc == win32event.WAIT_OBJECT_0:
                        break
            finally:
                if self._child is not None:
                    _append_log("[service] stopping watchdog")
                    _terminate_process(self._child)
                _best_effort_kill_unified_server()
                self.ReportServiceStatus(win32service.SERVICE_STOPPED)
                servicemanager.LogInfoMsg("QuantSysUnifiedServerWatchdog service stopped")


if __name__ == "__main__":
    if os.name != "nt":
        raise SystemExit("This script is Windows-only.")
    if len(sys.argv) > 1 and sys.argv[1].lower() == "debug":
        raise SystemExit(_debug())

    # pywin32 entrypoint: supports `install`, `remove`, `start`, `stop`, etc.
    try:
        win32serviceutil.HandleCommandLine(QuantSysUnifiedServerWatchdogService)
    except Exception as e:
        _append_log(f"[service] HandleCommandLine failed: {e!r}")
        raise
