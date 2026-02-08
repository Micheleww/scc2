#!/usr/bin/env python3
"""
Restart the SCC unified server (default: 127.0.0.1:18788).

This exists because some Windows environments disable PowerShell script execution
policy, making *.ps1 runbooks unreliable by default.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]

def _now_utc_compact() -> str:
    # Avoid extra deps; format like 20260201-235959Z
    return time.strftime("%Y%m%d-%H%M%SZ", time.gmtime())


def _netstat_listen_pid(port: int) -> int | None:
    # Example line (Windows):
    #   TCP    127.0.0.1:18788        0.0.0.0:0              LISTENING       2492
    try:
        out = subprocess.check_output(["netstat", "-ano", "-p", "TCP"], text=True, stderr=subprocess.STDOUT)
    except Exception:
        return None
    needle = f":{port}"
    for raw in out.splitlines():
        line = raw.strip()
        if not line.startswith("TCP"):
            continue
        if needle not in line:
            continue
        if "LISTENING" not in line:
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        try:
            return int(parts[-1])
        except ValueError:
            continue
    return None


def _kill_pid(pid: int) -> None:
    subprocess.run(["taskkill", "/PID", str(pid), "/F"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def _find_unified_server_pids(repo_root: Path) -> list[int]:
    # Use PowerShell CIM to avoid extra python deps like psutil.
    pattern = str(repo_root / "tools" / "unified_server" / "main.py").replace("\\", "\\\\")
    cmd = (
        "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" "
        f"| Where-Object {{ $_.CommandLine -match '{pattern}' }} "
        "| Select-Object -ExpandProperty ProcessId"
    )
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", cmd],
            text=True,
            stderr=subprocess.STDOUT,
        )
    except Exception:
        return []
    pids: list[int] = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            pids.append(int(line))
        except ValueError:
            continue
    return sorted(set(pids))


def _wait_healthy(base_url: str, timeout_s: int) -> bool:
    deadline = time.time() + timeout_s
    url = f"{base_url}/api/health"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status != 200:
                    time.sleep(0.25)
                    continue
                body = resp.read().decode("utf-8", errors="replace")
                if "\"status\"" in body and "healthy" in body:
                    return True
        except (urllib.error.URLError, TimeoutError):
            time.sleep(0.25)
            continue
        time.sleep(0.25)
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18788)
    parser.add_argument("--health-timeout-s", type=int, default=20)
    args = parser.parse_args()

    repo_root = _repo_root()
    artifacts_dir = repo_root / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    ts = _now_utc_compact()
    log_path = artifacts_dir / f"unified_server_{args.port}__{ts}.log"
    latest_ptr = artifacts_dir / f"unified_server_{args.port}__LATEST.logpath.txt"
    pid_path = artifacts_dir / f"unified_server_{args.port}.pid"

    # Stop any running unified_server instances (best-effort).
    for pid in _find_unified_server_pids(repo_root):
        _kill_pid(pid)
    existing_pid = _netstat_listen_pid(args.port)
    if existing_pid:
        _kill_pid(existing_pid)
    time.sleep(0.4)

    script_path = repo_root / "tools" / "unified_server" / "start_unified_server.py"
    if not script_path.exists():
        raise FileNotFoundError(str(script_path))

    python_exe = sys.executable

    # Use a fresh timestamped log file to avoid Windows file-lock collisions.
    with open(log_path, "w", encoding="utf-8") as log_fp:
        proc = subprocess.Popen(
            [python_exe, "-u", str(script_path)],
            cwd=str(repo_root),
            stdout=log_fp,
            stderr=log_fp,
            env=os.environ.copy(),
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )

    pid_path.write_text(str(proc.pid), encoding="ascii")
    latest_ptr.write_text(str(log_path), encoding="utf-8")

    base_url = f"http://{args.host}:{args.port}"
    if not _wait_healthy(base_url, args.health_timeout_s):
        raise RuntimeError(f"Unified server did not become healthy within {args.health_timeout_s}s. See: {log_path}")

    print(f"OK unified_server pid={proc.pid} url={base_url} log={log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
