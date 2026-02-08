#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SCC automation daemon: watch a parent inbox JSONL and execute new parents in parallel batches.

Run model: long-running background process (spawned by watchdog).
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import ctypes
import socket
from urllib.parse import urlparse
from pathlib import Path
from typing import Any, Dict, List, Tuple

repo_root = Path(__file__).resolve().parents[3]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from tools.scc.automation.run_batches import _http, _wait_ready, _get_executor_limit  # noqa: E402
from tools.scc.automation.resource_governor import GovernorConfig, decide_max_outstanding  # noqa: E402
from tools.scc.automation.system_metrics import sample_system_metrics  # noqa: E402


def _port_open(host: str, port: int, timeout_s: float = 0.3) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=timeout_s):
            return True
    except OSError:
        return False


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _append_log(path: Path, msg: str) -> None:
    def _get_env_int(name: str, default: int) -> int:
        raw = str(os.environ.get(name, "") or "").strip()
        if not raw:
            return default
        try:
            return int(raw, 10)
        except Exception:
            return default

    def _rotate_if_needed(log_file: Path) -> None:
        max_mb = _get_env_int("SCC_DAEMON_LOG_MAX_MB", 20)
        max_files = _get_env_int("SCC_DAEMON_LOG_MAX_FILES", 5)
        if max_mb <= 0 or max_files <= 0:
            return
        max_bytes = int(max_mb) * 1024 * 1024
        try:
            if log_file.exists() and log_file.stat().st_size >= max_bytes:
                # Shift: .(max_files-1) -> .max_files
                for i in range(max_files, 1, -1):
                    src = log_file.with_suffix(log_file.suffix + f".{i-1}")
                    dst = log_file.with_suffix(log_file.suffix + f".{i}")
                    if dst.exists():
                        dst.unlink(missing_ok=True)  # type: ignore[arg-type]
                    if src.exists():
                        src.rename(dst)
                rotated = log_file.with_suffix(log_file.suffix + ".1")
                if rotated.exists():
                    rotated.unlink(missing_ok=True)  # type: ignore[arg-type]
                log_file.rename(rotated)
        except Exception:
            # Rotation must never crash the daemon.
            return

    path.parent.mkdir(parents=True, exist_ok=True)
    _rotate_if_needed(path)
    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    with open(path, "a", encoding="utf-8", errors="replace") as f:
        f.write(f"[{ts}] {msg}\n")


def _socket_lock_or_exit(host: str, port: int, log_file: Path) -> socket.socket | None:
    """
    Single-instance guard using a localhost TCP bind.
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
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
        _append_log(log_file, f"another daemon instance already running (lock bind {host}:{port} failed: {e!r})")
        try:
            s.close()  # type: ignore[name-defined]
        except Exception:
            pass
        return None


def _lock_or_exit(lock_name: str, log_file: Path):
    """
    Single-instance guard using an OS-level lock file in %TEMP%.
    """
    lock_path = Path(tempfile.gettempdir()) / lock_name
    try:
        lock_file = open(lock_path, "w+b")
        lock_file.write(str(os.getpid()).encode("utf-8", errors="ignore"))
        lock_file.flush()
        if os.name == "nt":
            import msvcrt  # type: ignore

            lock_file.seek(0)
            try:
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                _append_log(log_file, f"another daemon instance already running (lock: {lock_path})")
                lock_file.close()
                return None
        return lock_file
    except Exception as e:
        _append_log(log_file, f"failed to acquire lock (lock: {lock_path} err={e!r})")
        return None


def _mutex_or_exit(name: str, log_file: Path):
    """
    Robust single-instance guard using a named Windows mutex.
    """
    if os.name != "nt":
        return None
    try:
        # NOTE: use_last_error=True is required; otherwise last-error is unreliable and
        # multiple daemon instances can slip past this guard.
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
        CreateMutexW = kernel32.CreateMutexW
        CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
        CreateMutexW.restype = ctypes.c_void_p

        handle = CreateMutexW(None, False, name)
        if not handle:
            return None
        already = ctypes.get_last_error() == 183  # ERROR_ALREADY_EXISTS
        if already:
            _append_log(log_file, f"another daemon instance already running (mutex: {name})")
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
    Robust single-instance guard on Windows using CreateFileW with share_mode=0.
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
            _append_log(log_file, f"another daemon instance already running (exclusive lock failed: {lock_path} err={err})")
            return None
        return handle
    except Exception as e:
        _append_log(log_file, f"failed to acquire exclusive lock (lock: {lock_path} err={e!r})")
        return None


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", errors="replace")
    os.replace(tmp, path)


def _read_cursor(path: Path) -> int:
    try:
        j = json.loads(path.read_text(encoding="utf-8", errors="replace") or "{}")
        return int(j.get("byte_offset") or 0)
    except Exception:
        return 0


def _save_cursor(path: Path, byte_offset: int, extra: dict | None = None) -> None:
    obj = {"byte_offset": int(byte_offset), "updated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    if extra:
        obj.update(extra)
    _write_json(path, obj)


def _read_new_lines(inbox: Path, *, byte_offset: int) -> Tuple[int, List[dict]]:
    if not inbox.exists():
        return byte_offset, []
    with open(inbox, "rb") as f:
        f.seek(max(0, int(byte_offset)))
        data = f.read()
        new_off = f.tell()
    if not data:
        return new_off, []
    lines = data.splitlines()
    out: List[dict] = []
    for b in lines:
        try:
            s = b.decode("utf-8", errors="replace").strip()
            if not s:
                continue
            j = json.loads(s)
            if isinstance(j, dict) and str(j.get("id") or "").strip() and str(j.get("description") or "").strip():
                out.append({"id": str(j["id"]).strip(), "description": str(j["description"]).strip(), "raw": j})
        except Exception:
            continue
    return new_off, out


def _run_parents(base: str, *, parents: List[dict], model: str, timeout_s: float, max_outstanding: int, dangerously_bypass: bool) -> dict:
    payload = {
        "parents": {"parents": [{"id": p["id"], "description": p["description"]} for p in parents]},
        "model": model,
        "timeout_s": timeout_s,
        "max_outstanding": max_outstanding,
        "dangerously_bypass": bool(dangerously_bypass),
    }
    code, body = _http("POST", f"{base}/executor/codex/run", json_body=payload, timeout_s=max(30.0, timeout_s + 30.0))
    try:
        j = json.loads(body or "{}")
    except Exception:
        j = {"_raw": body}
    j["_http_status"] = code
    return j


def main() -> int:
    repo_root = _repo_root()
    base = str(os.environ.get("SCC_BASE_URL", "") or "").strip() or "http://127.0.0.1:18788"
    model = str(os.environ.get("A2A_CODEX_MODEL", "gpt-5.2"))
    timeout_s = float(os.environ.get("A2A_CODEX_TIMEOUT_SEC", "900"))
    dangerously_bypass = str(os.environ.get("SCC_AUTOMATION_DANGEROUSLY_BYPASS", "") or "").strip().lower() == "true"
    poll_s = float(os.environ.get("SCC_PARENT_INBOX_POLL_S", "2.0"))
    batch_size = int(os.environ.get("SCC_PARENT_BATCH_SIZE", "5"))
    desired_max = int(os.environ.get("SCC_AUTOMATION_MAX_OUTSTANDING", "0") or 0)

    inbox = Path(os.environ.get("SCC_PARENT_INBOX", "artifacts/scc_state/parent_inbox.jsonl"))
    if not inbox.is_absolute():
        inbox = (repo_root / inbox).resolve()
    cursor_path = inbox.with_suffix(".cursor.json")

    out_root = (repo_root / "artifacts" / "scc_state" / "automation_daemon").resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    log_file = (out_root / "daemon.log").resolve()

    # Single-instance lock is deterministic: (base_port + 2).
    # Avoid env-driven variability which can accidentally allow multiple daemons.
    u = urlparse(base)
    base_port = int(u.port or 18788)
    lock_host = str(u.hostname or "127.0.0.1")
    lock_port = base_port + 2
    # Hard-block duplicates even if socket binding behaves unexpectedly:
    # if another daemon is already holding the lock port, exit quickly.
    if _port_open("127.0.0.1", lock_port, timeout_s=0.2):
        _append_log(log_file, f"another daemon instance already running (lock port {lock_port} already listening); exiting")
        return 2
    lock_sock = _socket_lock_or_exit(lock_host, lock_port, log_file)
    if lock_sock is None:
        return 2

    if not _wait_ready(base, timeout_s=180.0, interval_s=1.0):
        _write_json(out_root / "last_error.json", {"error": "server_not_ready", "base": base})
        return 3

    limit = _get_executor_limit(base)
    desired = min(limit, desired_max) if desired_max > 0 else max(1, min(limit, 3))
    current_max = desired
    gov_cfg = GovernorConfig.from_env(default_max=desired)

    state = {
        "ok": True,
        "base": base,
        "model": model,
        "max_outstanding": current_max,
        "desired_max_outstanding": desired,
        "batch_size": batch_size,
        "inbox": str(inbox),
        "cursor": str(cursor_path),
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "runs": 0,
        "processed": 0,
        "last_run_id": None,
        "pid": os.getpid(),
        "status": "idle",
        "last_metrics": None,
        "last_governor_reason": None,
        "governor": {
            "cpu_high": gov_cfg.cpu_high,
            "cpu_low": gov_cfg.cpu_low,
            "mem_high": gov_cfg.mem_high,
            "mem_low": gov_cfg.mem_low,
            "min_outstanding": gov_cfg.min_outstanding,
            "max_outstanding": gov_cfg.max_outstanding,
            "step": gov_cfg.step,
        },
    }
    _write_json(out_root / "daemon_state.json", state)

    byte_off = _read_cursor(cursor_path)
    try:
        while True:
            new_off, items = _read_new_lines(inbox, byte_offset=byte_off)
            byte_off = new_off
            if not items:
                _save_cursor(cursor_path, byte_off)
                time.sleep(max(0.5, poll_s))
                continue

            # Process in chunks.
            for i in range(0, len(items), max(1, batch_size)):
                chunk = items[i : i + batch_size]
                run_id = str(int(time.time() * 1000))
                run_dir = (out_root / "runs" / run_id).resolve()
                run_dir.mkdir(parents=True, exist_ok=True)
                _write_json(run_dir / "parents.json", {"parents": chunk})

                # Resource-aware max_outstanding (avoid OOM/CPU saturation).
                metrics = sample_system_metrics(disk_path=str(repo_root.anchor or "C:\\"))
                current_max, reason = decide_max_outstanding(
                    current=current_max,
                    desired=desired,
                    limit=limit,
                    metrics=metrics,
                    cfg=gov_cfg,
                )
                state["max_outstanding"] = current_max
                state["last_metrics"] = metrics.to_dict()
                state["last_governor_reason"] = reason

                state["status"] = "running"
                state["last_run_id"] = run_id
                _write_json(out_root / "daemon_state.json", state)

                resp = _run_parents(
                    base,
                    parents=chunk,
                    model=model,
                    timeout_s=timeout_s,
                    max_outstanding=current_max,
                    dangerously_bypass=dangerously_bypass,
                )
                _write_json(run_dir / "response.json", resp)

                state["runs"] = int(state.get("runs") or 0) + 1
                state["processed"] = int(state.get("processed") or 0) + len(chunk)
                state["status"] = "idle"
                _write_json(out_root / "daemon_state.json", state)

            _save_cursor(cursor_path, byte_off, extra={"processed": state["processed"], "runs": state["runs"]})
            time.sleep(max(0.5, poll_s))
    finally:
        try:
            lock_sock.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
