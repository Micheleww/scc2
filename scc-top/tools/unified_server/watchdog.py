#!/usr/bin/env python3
"""
Unified Server watchdog (Windows-friendly).

Goal: improve stability by keeping the unified server on 127.0.0.1:18788 alive.

Notes:
- This does NOT (and cannot) make a process "unkillable" for an admin.
- It provides best-effort keep-alive: health-check + auto-restart.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import os
import socket
import subprocess
import sys
import tempfile
import time
import ctypes
from pathlib import Path
from typing import Optional, IO


def _now() -> str:
    return _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _append_log(log_file: Path, message: str) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with open(log_file, "a", encoding="utf-8", errors="replace") as f:
        f.write(f"[{_now()}] {message}\n")


def _port_open(host: str, port: int, timeout_s: float = 0.5) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout_s)
        return sock.connect_ex((host, port)) == 0


def _socket_lock_or_exit(host: str, port: int, log_file: Path) -> Optional[socket.socket]:
    """
    Single-instance guard using a localhost TCP bind.

    This is intentionally simple and robust on Windows where file-region locks and
    mutex last-error checks can behave unexpectedly across environments.
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # On Windows, SO_EXCLUSIVEADDRUSE is the reliable way to prevent
        # multiple processes from binding the same (host, port).
        if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)  # type: ignore[attr-defined]
        else:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        # Bind on 0.0.0.0 to prevent an accidental "dual-bind" scenario
        # (one process binds 127.0.0.1 while another binds 0.0.0.0).
        s.bind(("0.0.0.0", int(port)))
        s.listen(1)
        return s
    except Exception as e:
        try:
            _append_log(log_file, f"another watchdog instance already running (lock bind {host}:{port} failed: {e!r})")
        except Exception:
            pass
        try:
            s.close()  # type: ignore[name-defined]
        except Exception:
            pass
        return None


def _describe_port_owner_windows(port: int) -> str:
    """
    Best-effort: find PID that LISTENs on the port via netstat.
    Returns a short string for logs.
    """
    if os.name != "nt":
        return ""
    try:
        # Example line:
        #  TCP    127.0.0.1:18788        0.0.0.0:0              LISTENING       14592
        out = subprocess.check_output(["netstat", "-ano", "-p", "tcp"], text=True, errors="ignore")
        pid: Optional[str] = None
        for line in out.splitlines():
            if f":{port} " not in line:
                continue
            if "LISTENING" not in line.upper():
                continue
            parts = line.split()
            if parts and parts[-1].isdigit():
                pid = parts[-1]
                break
        if not pid:
            return ""

        try:
            task = subprocess.check_output(["tasklist", "/FI", f"PID eq {pid}"], text=True, errors="ignore")
            first_data = next((l for l in task.splitlines() if l.strip() and "PID" not in l and "INFO:" not in l), "")
            return f"pid={pid} {first_data.strip()}".strip()
        except Exception:
            return f"pid={pid}".strip()
    except Exception:
        return ""


def _pid_listening_on_port(port: int) -> Optional[int]:
    """
    Best-effort: return PID that LISTENs on localhost TCP port.
    """
    try:
        out = subprocess.check_output(["netstat", "-ano", "-p", "tcp"], text=True, errors="ignore")
        for line in out.splitlines():
            if f":{port} " not in line:
                continue
            if "LISTENING" not in line.upper():
                continue
            parts = line.split()
            if parts and parts[-1].isdigit():
                return int(parts[-1])
    except Exception:
        pass
    return None


def _best_effort_kill_duplicates(log_file: Path, *, keep_watchdog_pid: int) -> None:
    """
    Last-resort: ensure a single active watchdog/server/daemon instance.
    When multiple launchers exist (VBS/cmd/shortcuts), races can create duplicates.
    We keep the PID that owns the lock ports and kill other duplicates.
    """
    try:
        import psutil  # type: ignore

        keep_lock_pid = _pid_listening_on_port(18789)

        def match(cmd: str, needle: str) -> bool:
            return needle in cmd or needle.replace("\\", "/") in cmd

        for pid in psutil.pids():
            if not pid or pid == keep_watchdog_pid:
                continue
            try:
                proc = psutil.Process(pid)
                cmd = " ".join(proc.cmdline())
            except Exception:
                continue
            if not cmd:
                continue

            # Kill extra watchdogs, but keep the one that holds the lock port if known.
            if match(cmd, "tools\\unified_server\\watchdog.py"):
                if keep_lock_pid and pid == keep_lock_pid:
                    continue
                _append_log(log_file, f"kill duplicate watchdog pid={pid}")
                try:
                    proc.kill()
                except Exception:
                    pass
                continue

            # Intentionally do NOT kill server/daemon here.
            # Rationale: when multiple watchdogs exist, aggressive killing can cause restart loops.
            # We rely on the lock-port ownership check to make orphan watchdogs exit.
    except Exception:
        pass


def _http_ok(url: str, timeout_s: float = 1.5) -> bool:
    try:
        import requests  # type: ignore

        r = requests.get(url, timeout=timeout_s)
        return 200 <= r.status_code < 300
    except Exception:
        return False


def _lock_or_exit(lock_name: str, log_file: Path) -> Optional[IO[bytes]]:
    """
    Best-effort single instance guard.
    Uses an OS-level lock on a file in %TEMP% to prevent multiple watchdogs.
    (No stale-lock problem if the process is killed.)
    """
    lock_path = Path(tempfile.gettempdir()) / lock_name
    try:
        # Use binary mode + overwrite so the lock region is consistent and
        # we avoid Windows append-mode quirks (writes forced to EOF).
        lock_file = open(lock_path, "w+b")
        lock_file.write(str(os.getpid()).encode("utf-8", errors="ignore"))
        lock_file.flush()

        if os.name == "nt":
            import msvcrt  # type: ignore

            try:
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                _append_log(log_file, f"another watchdog instance already running (lock: {lock_path})")
                lock_file.close()
                return None

        return lock_file
    except Exception:
        _append_log(log_file, f"failed to acquire lock (lock: {lock_path})")
        return None


def _unlock(lock_file: IO[bytes], lock_name: str) -> None:
    try:
        if os.name == "nt":
            import msvcrt  # type: ignore

            try:
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            except Exception:
                pass
    finally:
        try:
            lock_file.close()
        except Exception:
            pass


def _mutex_or_exit(name: str, log_file: Path):
    """
    Robust single-instance guard using a named Windows mutex.
    """
    if os.name != "nt":
        return None
    try:
        # NOTE: use_last_error=True is required; otherwise last-error is unreliable and
        # multiple watchdog instances can slip past this guard.
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
        CreateMutexW = kernel32.CreateMutexW
        CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
        CreateMutexW.restype = ctypes.c_void_p

        handle = CreateMutexW(None, False, name)
        if not handle:
            return None
        already = ctypes.get_last_error() == 183  # ERROR_ALREADY_EXISTS
        if already:
            _append_log(log_file, f"another watchdog instance already running (mutex: {name})")
            try:
                kernel32.CloseHandle(handle)
            except Exception:
                pass
            return None
        return handle
    except Exception as e:
        _append_log(log_file, f"mutex init failed (mutex: {name} err={e!r})")
        return None


def _exclusive_lock_or_exit(lock_name: str, log_file: Path):
    """
    Robust single-instance guard on Windows.

    Uses CreateFileW with share_mode=0 (exclusive open). This is more reliable than
    msvcrt.locking in practice, and avoids inconsistent mutex last-error behavior.
    """
    if os.name != "nt":
        return None
    lock_path = str((Path(tempfile.gettempdir()) / lock_name).resolve())
    try:
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]

        GENERIC_READ = 0x80000000
        GENERIC_WRITE = 0x40000000
        OPEN_ALWAYS = 4
        FILE_ATTRIBUTE_NORMAL = 0x80
        INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

        CreateFileW = kernel32.CreateFileW
        CreateFileW.argtypes = [
            ctypes.c_wchar_p,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_void_p,
        ]
        CreateFileW.restype = ctypes.c_void_p

        handle = CreateFileW(
            lock_path,
            GENERIC_READ | GENERIC_WRITE,
            0,  # exclusive
            None,
            OPEN_ALWAYS,
            FILE_ATTRIBUTE_NORMAL,
            None,
        )
        if handle == INVALID_HANDLE_VALUE or handle is None:
            try:
                err = int(kernel32.GetLastError())
            except Exception:
                err = -1
            _append_log(log_file, f"another watchdog instance already running (exclusive lock failed: {lock_path} err={err})")
            return None
        return handle
    except Exception as e:
        _append_log(log_file, f"failed to acquire exclusive lock (lock: {lock_path} err={e!r})")
        return None


def _default_repo_root() -> Path:
    # tools/unified_server/watchdog.py -> tools/unified_server -> tools -> repo_root
    return Path(__file__).resolve().parent.parent.parent


def _start_server(
    python_exe: str,
    main_py: Path,
    cwd: Path,
    env: dict[str, str],
    log_file: Path,
) -> subprocess.Popen:
    creationflags = 0
    if os.name == "nt":
        # Try hard to keep the server alive even if the launcher/terminal sends Ctrl+C to its job tree:
        # - DETACHED_PROCESS + CREATE_NEW_PROCESS_GROUP: detach from console CTRL signals
        # - CREATE_BREAKAWAY_FROM_JOB (if permitted): detach from a parent Job object so external aborts don't kill it
        creationflags = (
            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0)
        )

    stdout = open(log_file, "a", encoding="utf-8", errors="replace")
    stderr = stdout

    _append_log(log_file, f"starting unified server: {python_exe} {main_py}")
    return subprocess.Popen(
        [python_exe, str(main_py)],
        cwd=str(cwd),
        env=env,
        stdout=stdout,
        stderr=stderr,
        stdin=subprocess.DEVNULL,
        creationflags=creationflags,
    )


def _spawn_automation(repo_root: Path, log_file: Path) -> None:
    """
    Best-effort: spawn SCC automation daemon once per watchdog lifetime.
    The daemon watches parent inbox JSONL and runs new parents in parallel batches.
    """
    try:
        enabled = str(os.environ.get("WATCHDOG_AUTO_RUN_AUTOMATION", "") or "").strip().lower() == "true"
        if not enabled:
            return

        if getattr(_spawn_automation, "_started", False):
            return
        setattr(_spawn_automation, "_started", True)

        runner = repo_root / "tools" / "scc" / "automation" / "daemon_inbox.py"
        if not runner.exists():
            _append_log(log_file, f"automation daemon not found: {runner}")
            return

        base = str(os.environ.get("SCC_BASE_URL", "") or "").strip() or "http://127.0.0.1:18788"
        dangerously = str(os.environ.get("SCC_AUTOMATION_DANGEROUSLY_BYPASS", "") or "").strip().lower() == "true"
        max_out = str(os.environ.get("SCC_AUTOMATION_MAX_OUTSTANDING", "") or "").strip()

        # daemon uses env vars; we just ensure base is passed as env for clarity.
        env = os.environ.copy()
        env.setdefault("SCC_BASE_URL", base)
        if max_out.isdigit():
            env["SCC_AUTOMATION_MAX_OUTSTANDING"] = max_out
        if dangerously:
            env["SCC_AUTOMATION_DANGEROUSLY_BYPASS"] = "true"

        creationflags = 0
        if os.name == "nt":
            creationflags = (
                getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                | getattr(subprocess, "DETACHED_PROCESS", 0)
                | getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0)
            )

        auto_log = log_file.with_name("automation.log")
        stdout = open(auto_log, "a", encoding="utf-8", errors="replace")
        stderr = stdout
        args = [sys.executable, str(runner)]
        _append_log(log_file, f"starting automation daemon: {' '.join(args)} (log={auto_log})")
        subprocess.Popen(args, cwd=str(repo_root), env=env, stdout=stdout, stderr=stderr, stdin=subprocess.DEVNULL, creationflags=creationflags)
    except Exception as e:
        try:
            _append_log(log_file, f"failed to start automation daemon: {e!r}")
        except Exception:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Keep Unified Server alive via health-check + restart.")
    parser.add_argument("--host", default=os.environ.get("UNIFIED_SERVER_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("UNIFIED_SERVER_PORT", "18788")))
    parser.add_argument("--ready-url", default=os.environ.get("UNIFIED_SERVER_READY_URL", ""))
    parser.add_argument("--interval", type=float, default=float(os.environ.get("WATCHDOG_INTERVAL", "2.0")))
    parser.add_argument("--startup-grace", type=float, default=float(os.environ.get("WATCHDOG_STARTUP_GRACE", "20.0")))
    parser.add_argument("--log-file", default=os.environ.get("WATCHDOG_LOG_FILE", ""))
    args = parser.parse_args()

    repo_root = _default_repo_root()
    unified_dir = Path(__file__).resolve().parent
    main_py = unified_dir / "main.py"

    ready_url = args.ready_url or f"http://{args.host}:{args.port}/health/ready"
    log_file = Path(args.log_file) if args.log_file else (unified_dir / "logs" / "watchdog.log")
    _append_log(log_file, f"watchdog boot pid={os.getpid()} host={args.host} port={args.port} ready_url={ready_url}")

    # Single-instance lock port is deterministic: (unified_server_port + 1).
    # Avoid env-driven variability which can accidentally allow multiple watchdogs.
    lock_port = int(args.port) + 1
    # Hard-block duplicates even if socket binding behaves unexpectedly:
    # if another watchdog is already holding the lock port, exit quickly.
    if _port_open("127.0.0.1", lock_port, timeout_s=0.2):
        _append_log(log_file, f"another watchdog instance already running (lock port {lock_port} already listening); exiting")
        return 2
    lock_sock = _socket_lock_or_exit(args.host, lock_port, log_file)
    if lock_sock is None:
        _append_log(log_file, f"watchdog lock acquire failed (lock_port={lock_port}); exiting")
        return 2

    # After acquiring the lock, aggressively prune duplicates.
    _best_effort_kill_duplicates(log_file, keep_watchdog_pid=os.getpid())
    _append_log(log_file, f"watchdog lock acquired (lock_port={lock_port})")

    child: Optional[subprocess.Popen] = None
    last_start_ts: Optional[float] = None
    last_prune_ts: float = 0.0

    try:
        while True:
            # If we don't own the lock port anymore, exit (prevents orphan watchdogs).
            owner_pid = _pid_listening_on_port(lock_port)
            if owner_pid and owner_pid != os.getpid():
                _append_log(log_file, f"watchdog lost lock ownership (lock_port={lock_port} owner_pid={owner_pid}); exiting")
                return 2

            # Keep the runtime single-instance even under launcher races.
            if (time.time() - last_prune_ts) > 5.0:
                _best_effort_kill_duplicates(log_file, keep_watchdog_pid=os.getpid())
                last_prune_ts = time.time()

            healthy = _http_ok(ready_url)

            if healthy:
                # Optionally run automation after the server becomes ready.
                try:
                    _spawn_automation(repo_root, log_file)
                except Exception:
                    pass
                time.sleep(args.interval)
                continue

            # Not healthy. Decide whether to start/restart.
            port_in_use = _port_open(args.host, args.port)

            if child is not None and child.poll() is not None:
                _append_log(log_file, f"server exited with code={child.returncode}; will restart")
                child = None

            # If someone else occupies the port and health is failing, we do NOT kill it.
            if port_in_use and child is None:
                owner = _describe_port_owner_windows(args.port)
                _append_log(
                    log_file,
                    f"port {args.port} is in use but {ready_url} is not healthy; not starting a new instance"
                    + (f" (owner: {owner})" if owner else ""),
                )
                time.sleep(max(args.interval, 5.0))
                continue

            # If we recently started, allow a grace period before declaring failure.
            if last_start_ts is not None and (time.time() - last_start_ts) < args.startup_grace:
                time.sleep(args.interval)
                continue

            if child is None:
                _append_log(log_file, "starting unified server (watchdog decision)")
                env = os.environ.copy()
                env.setdefault("REPO_ROOT", str(repo_root))
                env.setdefault("UNIFIED_SERVER_HOST", args.host)
                env.setdefault("UNIFIED_SERVER_PORT", str(args.port))
                env.setdefault("LOG_LEVEL", env.get("LOG_LEVEL", "info"))
                env.setdefault("DEBUG", env.get("DEBUG", "false"))
                # Force disable uvicorn reload for stability: reload can auto-restart the server when Codex edits files,
                # which breaks long-running requests like /executor/codex/run.
                env["RELOAD"] = "false"

                child = _start_server(sys.executable, main_py, repo_root, env, log_file)
                last_start_ts = time.time()
                time.sleep(args.interval)
                continue

            # Child exists but still unhealthy past grace; just log and keep looping.
            _append_log(log_file, f"still unhealthy after grace (url={ready_url}); waiting")
            time.sleep(max(args.interval, 5.0))
    finally:
        try:
            lock_sock.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
